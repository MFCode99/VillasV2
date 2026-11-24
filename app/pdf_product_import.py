from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Any

from fastapi import HTTPException, status
from PIL import Image
from pypdf import PdfReader


MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PDF_PAGES = 250
REFERENCE_LINE = re.compile(r'^\s*([0-9]{4,12})\b', re.MULTILINE)


@dataclass(slots=True)
class PdfProductImage:
    ref: str
    page: int
    image_bytes: bytes
    source_images: int


@dataclass(slots=True)
class _Placement:
    name: str
    x: float
    y: float
    width: float
    height: float
    data: bytes

    @property
    def bottom(self) -> float:
        return self.y

    @property
    def top(self) -> float:
        return self.y + self.height


def _page_references(page: Any) -> list[str]:
    text = page.extract_text() or ''
    return list(dict.fromkeys(REFERENCE_LINE.findall(text)))


def _page_placements(page: Any) -> list[_Placement]:
    placements: list[_Placement] = []

    def visitor(op: bytes, args: list[Any], cm: list[float], tm: list[float]) -> None:
        if op != b'Do' or not args:
            return
        x, y = float(cm[4]), float(cm[5])
        width, height = abs(float(cm[0])), abs(float(cm[3]))
        # Supplier table PDFs place product images in the first column. This
        # excludes logos, headers and decorative images elsewhere on the page.
        if x >= 110 or x + width > 115 or width <= 1 or height <= 1:
            return
        name = str(args[0])
        try:
            data = page.images[name].data
        except (KeyError, AttributeError):
            return
        placements.append(_Placement(name=name, x=x, y=y, width=width, height=height, data=data))

    page.extract_text(visitor_operand_before=visitor)
    return placements


def _group_placements(placements: list[_Placement]) -> list[list[_Placement]]:
    groups: list[list[_Placement]] = []
    for placement in sorted(placements, key=lambda item: item.top, reverse=True):
        matching = None
        for group in groups:
            group_bottom = min(item.bottom for item in group)
            group_top = max(item.top for item in group)
            if placement.top >= group_bottom - 0.1 and placement.bottom <= group_top + 0.1:
                matching = group
                break
        if matching is None:
            groups.append([placement])
        else:
            matching.append(placement)
    return sorted(groups, key=lambda group: max(item.top for item in group), reverse=True)


def _composite(group: list[_Placement]) -> bytes:
    if len(group) == 1:
        return group[0].data
    min_x = min(item.x for item in group)
    min_y = min(item.y for item in group)
    max_x = max(item.x + item.width for item in group)
    max_y = max(item.y + item.height for item in group)
    scale = 10
    canvas = Image.new('RGBA', (max(1, round((max_x - min_x) * scale)), max(1, round((max_y - min_y) * scale))), (255, 255, 255, 0))
    for item in group:
        with Image.open(BytesIO(item.data)) as source:
            image = source.convert('RGBA')
            image = image.resize((max(1, round(item.width * scale)), max(1, round(item.height * scale))), Image.Resampling.LANCZOS)
            left = round((item.x - min_x) * scale)
            top = round((max_y - (item.y + item.height)) * scale)
            canvas.alpha_composite(image, (left, top))
    output = BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    return output.getvalue()


def parse_pdf_product_images(data: bytes) -> tuple[list[PdfProductImage], list[dict[str, Any]]]:
    if not data or not data.startswith(b'%PDF'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_pdf')
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='pdf_too_large')
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_pdf') from exc
    if reader.is_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='encrypted_pdf_not_supported')
    if not reader.pages or len(reader.pages) > MAX_PDF_PAGES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_pdf_page_count')

    result: list[PdfProductImage] = []
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page_number, page in enumerate(reader.pages, start=1):
        references = _page_references(page)
        groups = _group_placements(_page_placements(page))
        if len(references) != len(groups):
            issues.append({'page': page_number, 'references': len(references), 'images': len(groups), 'message': 'A quantidade de referências não coincide com as imagens.'})
            continue
        for ref, group in zip(references, groups, strict=True):
            if ref in seen:
                issues.append({'page': page_number, 'ref': ref, 'message': 'Referência repetida no PDF.'})
                continue
            seen.add(ref)
            result.append(PdfProductImage(ref=ref, page=page_number, image_bytes=_composite(group), source_images=len(group)))
    return result, issues
