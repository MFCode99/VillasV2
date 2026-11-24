from __future__ import annotations

import base64
import hashlib
import io
import mimetypes
import os
import re
import tempfile
from functools import lru_cache
from statistics import median
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - dependency is optional during staged deploys
    pass

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
CAMPAIGN_IMAGE_SIZE = (1500, 500)
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename_component(value: str | None) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', (value or '').strip())
    cleaned = cleaned.strip('_')
    return cleaned or 'product'


def detect_image_format(data: bytes) -> tuple[str, str]:
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='image_too_large')
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg', 'jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png', 'png'
    if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
        return 'image/gif', 'gif'
    if data[8:12] == b'WEBP' and data[:4] == b'RIFF':
        return 'image/webp', 'webp'
    if data.startswith(b'BM'):
        return 'image/bmp', 'bmp'
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_image_format')


def normalize_image_bytes(data: bytes, *, force_png: bool = False) -> tuple[bytes, str, str]:
    """Validate an actual raster image and return browser-compatible bytes."""
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='empty_image_upload')
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='image_too_large')
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as source:
            source.seek(0)
            image = ImageOps.exif_transpose(source)
            image.load()
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='image_dimensions_too_large')
            output = io.BytesIO()
            source_format = (source.format or '').upper()
            has_alpha = image.mode in {'RGBA', 'LA'} or (image.mode == 'P' and 'transparency' in image.info)
            if force_png:
                if image.mode not in {'RGB', 'RGBA'}:
                    image = image.convert('RGBA' if has_alpha else 'RGB')
                image.save(output, format='PNG', optimize=True)
                return output.getvalue(), 'image/png', 'png'
            if source_format == 'PNG' or has_alpha:
                if image.mode not in {'RGB', 'RGBA'}:
                    image = image.convert('RGBA' if has_alpha else 'RGB')
                image.save(output, format='PNG', optimize=True)
                return output.getvalue(), 'image/png', 'png'
            if source_format == 'JPEG':
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                image.save(output, format='JPEG', quality=92, optimize=True, progressive=True)
                return output.getvalue(), 'image/jpeg', 'jpg'
            if image.mode != 'RGB':
                image = image.convert('RGB')
            image.save(output, format='WEBP', quality=90, method=6)
            return output.getvalue(), 'image/webp', 'webp'
    except HTTPException:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_image_format') from exc


def calculate_image_zoom(data: bytes) -> float:
    """Return a display zoom that gives the visible product consistent breathing room."""
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert('RGBA')
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        width, height = image.size
        pixels = image.load()
        sample_size = max(1, min(width, height) // 20)
        corners: list[tuple[int, int, int]] = []
        for left, top in ((0, 0), (width - sample_size, 0), (0, height - sample_size), (width - sample_size, height - sample_size)):
            for y in range(top, top + sample_size):
                for x in range(left, left + sample_size):
                    red, green, blue, alpha = pixels[x, y]
                    if alpha > 32:
                        corners.append((red, green, blue))
        background = tuple(int(median(channel)) for channel in zip(*corners)) if corners else (255, 255, 255)
        mask = Image.new('L', image.size)
        mask_pixels = mask.load()
        transparent_background = not corners
        for y in range(height):
            for x in range(width):
                red, green, blue, alpha = pixels[x, y]
                color_distance = max(abs(red - background[0]), abs(green - background[1]), abs(blue - background[2]))
                visible = alpha > 32 and (transparent_background or color_distance > 28)
                mask_pixels[x, y] = 255 if visible else 0
        bounds = mask.getbbox()
        if bounds is None:
            return 1.0 if min(background) >= 245 else 0.84
        content_extent = max((bounds[2] - bounds[0]) / width, (bounds[3] - bounds[1]) / height)
        if content_extent <= 0:
            return 1.0
        return round(max(0.84, min(1.7, 0.84 / content_extent)), 2)


@lru_cache(maxsize=4096)
def _calculate_image_zoom_file_cached(path_value: str, modified_ns: int, size: int) -> float:
    del modified_ns, size
    return calculate_image_zoom(Path(path_value).read_bytes())


def calculate_image_zoom_file(path: Path) -> float:
    try:
        stat = path.stat()
        return _calculate_image_zoom_file_cached(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, UnidentifiedImageError, ValueError):
        return 1.0


def prepare_product_image(media_root: Path, ref: str, data: bytes) -> tuple[bytes, Path, str, str, str]:
    normalized, mime, ext = normalize_image_bytes(data)
    checksum = sha256_bytes(normalized)
    relative_path = Path('products') / safe_filename_component(ref) / f'{checksum[:16]}.{ext}'
    return normalized, media_root / relative_path, relative_path.as_posix(), checksum, mime


def _campaign_corner_background(image: Image.Image) -> tuple[tuple[int, int, int, int], bool]:
    """Return the dominant corner colour and whether the edges behave like a flat artwork background."""
    sample = image.copy()
    sample.thumbnail((480, 480), Image.Resampling.LANCZOS)
    sample = sample.convert('RGBA')
    width, height = sample.size
    size = max(2, min(width, height) // 12)
    colors: list[tuple[int, int, int, int]] = []
    total_pixels = size * size * 4
    pixels = sample.load()
    for left, top in ((0, 0), (width - size, 0), (0, height - size), (width - size, height - size)):
        for y in range(top, top + size):
            for x in range(left, left + size):
                colors.append(pixels[x, y])
    opaque = [color for color in colors if color[3] > 32]
    if len(opaque) < total_pixels * .25:
        return (255, 255, 255, 0), True
    background = tuple(int(median(color[channel] for color in opaque)) for channel in range(3))
    distances = sorted(max(abs(color[channel] - background[channel]) for channel in range(3)) for color in opaque)
    percentile_90 = distances[min(len(distances) - 1, int(len(distances) * .9))]
    return (*background, 255), percentile_90 <= 32


def normalize_campaign_image_bytes(data: bytes, *, force_png: bool = False) -> tuple[bytes, str, str]:
    """Create a consistent 3:1 banner, preserving flat artwork and cropping photographic imagery."""
    normalized, source_mime, _ = normalize_image_bytes(data, force_png=force_png)
    with Image.open(io.BytesIO(normalized)) as source:
        image = source.convert('RGBA')
        background, flat_artwork = _campaign_corner_background(image)
        if flat_artwork:
            banner = Image.new('RGBA', CAMPAIGN_IMAGE_SIZE, background)
            scale = min(CAMPAIGN_IMAGE_SIZE[0] / image.width, CAMPAIGN_IMAGE_SIZE[1] / image.height)
            contained = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
            left = (CAMPAIGN_IMAGE_SIZE[0] - contained.width) // 2
            top = (CAMPAIGN_IMAGE_SIZE[1] - contained.height) // 2
            banner.alpha_composite(contained, (left, top))
        else:
            banner = ImageOps.fit(image, CAMPAIGN_IMAGE_SIZE, method=Image.Resampling.LANCZOS, centering=(.5, .5))

        output = io.BytesIO()
        has_alpha = banner.getextrema()[3][0] < 255
        if force_png or source_mime == 'image/png' or has_alpha:
            banner.save(output, format='PNG', optimize=True)
            return output.getvalue(), 'image/png', 'png'
        if source_mime == 'image/jpeg':
            banner.convert('RGB').save(output, format='JPEG', quality=90, optimize=True, progressive=True)
            return output.getvalue(), 'image/jpeg', 'jpg'
        banner.convert('RGB').save(output, format='WEBP', quality=88, method=6)
        return output.getvalue(), 'image/webp', 'webp'


def prepare_campaign_image(media_root: Path, campaign_id: int, data: bytes, *, convert_to_png: bool = False) -> tuple[bytes, Path, str, str, str]:
    normalized, mime, ext = normalize_campaign_image_bytes(data, force_png=convert_to_png)
    checksum = sha256_bytes(normalized)
    relative_path = Path('campaigns') / str(campaign_id) / f'{checksum[:16]}.{ext}'
    return normalized, media_root / relative_path, relative_path.as_posix(), checksum, mime


def persist_prepared_image(absolute_path: Path, data: bytes, checksum: str) -> bool:
    """Write with an atomic rename. Returns True only when this call created the file."""
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    if absolute_path.exists() and sha256_bytes(absolute_path.read_bytes()) == checksum:
        return False
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=absolute_path.parent, prefix='.upload-', suffix='.tmp', delete=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        temp_path.replace(absolute_path)
        return True
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def decode_data_url(image_value: str | None) -> tuple[bytes | None, str | None, str | None]:
    text = (image_value or '').strip()
    if not text or not text.startswith('data:image/'):
        return None, None, None
    try:
        header, payload = text.split(',', 1)
        mime = header.split(';', 1)[0][5:].lower()
        ext = mimetypes.guess_extension(mime) or '.bin'
        if ext == '.jpe':
            ext = '.jpg'
        data = base64.b64decode(payload, validate=True)
        return data, mime, ext.lstrip('.')
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_image_payload') from exc


def save_product_image_bytes(media_root: Path, ref: str, data: bytes) -> tuple[str, str, str, float]:
    normalized, absolute_path, relative_path, checksum, mime = prepare_product_image(media_root, ref, data)
    persist_prepared_image(absolute_path, normalized, checksum)
    return relative_path, checksum, mime, calculate_image_zoom(normalized)


async def save_uploaded_product_image(upload: UploadFile, media_root: Path, ref: str) -> tuple[str, str, str, float]:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='empty_image_upload')
    return save_product_image_bytes(media_root, ref, data)
