from __future__ import annotations

import base64
import hashlib
import io
import mimetypes
import os
import re
import tempfile
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


def normalize_image_bytes(data: bytes) -> tuple[bytes, str, str]:
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


def prepare_product_image(media_root: Path, ref: str, data: bytes) -> tuple[bytes, Path, str, str, str]:
    normalized, mime, ext = normalize_image_bytes(data)
    checksum = sha256_bytes(normalized)
    relative_path = Path('products') / safe_filename_component(ref) / f'{checksum[:16]}.{ext}'
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


def save_product_image_bytes(media_root: Path, ref: str, data: bytes) -> tuple[str, str, str]:
    normalized, absolute_path, relative_path, checksum, mime = prepare_product_image(media_root, ref, data)
    persist_prepared_image(absolute_path, normalized, checksum)
    return relative_path, checksum, mime


async def save_uploaded_product_image(upload: UploadFile, media_root: Path, ref: str) -> tuple[str, str, str]:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='empty_image_upload')
    return save_product_image_bytes(media_root, ref, data)
