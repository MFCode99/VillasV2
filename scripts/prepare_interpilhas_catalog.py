from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import openpyxl
from PIL import Image
from pypdf import PdfReader


MILLI = Decimal('0.001')
PDF_SELECTIONS = (
    ('1-Pilhas-Philips-.pdf', 'PHILIPS', 'Pilhas'),
    ('2-perfumes.pdf', 'AREON', 'Ambientadores'),
    ('3-TABELA-VARTA-PILHAS.pdf', 'VARTA', 'Pilhas'),
    ('4-colas-.pdf', 'MOKARI', 'Colas'),
    ('5-Pilhas-maxwell-.pdf', 'MAXELL', 'Pilhas'),
    ('6-colas-gom.pdf', 'GOMAGOM', 'Colas e adesivos'),
    ('8-Pilhas-kodak.pdf', 'KODAK', 'Pilhas'),
    ('9-fitas-adesivas-.pdf', 'MOKARI', 'Fitas adesivas'),
)
BRAND_LABELS = {
    'AREON': 'Areon',
    'GOMAGOM': 'GomaGom',
    'KODAK': 'Kodak',
    'MAXELL': 'Maxell',
    'MOKARI': 'Mokari',
    'PHILIPS': 'Philips',
    'VARTA': 'Varta',
}
CATEGORY_LABELS = {
    'interpilhas-pilhas-alcalinas': 'Alcalinas',
    'interpilhas-pilhas-zinco': 'Zinco e Heavy Duty',
    'interpilhas-pilhas-litio': 'Lítio',
    'interpilhas-pilhas-recarregaveis': 'Recarregáveis',
    'interpilhas-pilhas-relogio': 'Relógio',
    'interpilhas-pilhas-especiais': 'Especiais',
    'interpilhas-ambientadores-mon-areon': 'Mon Areon',
    'interpilhas-ambientadores-smile': 'Smile',
    'interpilhas-ambientadores-fresco': 'Fresco',
    'interpilhas-ambientadores-fresh-wave': 'Fresh Wave',
    'interpilhas-ambientadores-smile-toy': 'Smile Toy',
    'interpilhas-colas-instantaneas': 'Colas instantâneas',
    'interpilhas-colas-contacto': 'Colas de contacto',
    'interpilhas-silicones-selantes': 'Silicones e selantes',
    'interpilhas-massas-adesivas': 'Massas adesivas',
    'interpilhas-fitas-adesivas': 'Fitas adesivas',
    'interpilhas-escolar-escritorio': 'Escolar e escritório',
    'interpilhas-ferramentas-acessorios': 'Ferramentas e acessórios',
    'interpilhas-colas-especiais-universais': 'Colas especiais e universais',
}


def plain_text(value: Any) -> str:
    return '' if value is None else str(value).strip()


def identifier(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def ascii_upper(value: str) -> str:
    decomposed = unicodedata.normalize('NFKD', value)
    return ''.join(char for char in decomposed if not unicodedata.combining(char)).upper()


def milli(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MILLI, rounding=ROUND_HALF_UP)


def classify_product(row: dict[str, Any]) -> tuple[str, str, str]:
    source_category = plain_text(row['Categoria'])
    description = ascii_upper(plain_text(row['Descrição']))
    brand = ascii_upper(plain_text(row['Marca']))
    ref = ascii_upper(identifier(row['Referência']))

    if source_category == 'Ambientadores':
        if 'SMILE TOY' in description:
            slug = 'interpilhas-ambientadores-smile-toy'
        elif 'FRESH WAVE' in description:
            slug = 'interpilhas-ambientadores-fresh-wave'
        elif 'MON AREON' in description:
            slug = 'interpilhas-ambientadores-mon-areon'
        elif 'FRESCO' in description:
            slug = 'interpilhas-ambientadores-fresco'
        elif 'SMILE' in description:
            slug = 'interpilhas-ambientadores-smile'
        else:
            raise ValueError(f'Unclassified ambientador: {ref} {description}')
        return 'Ambientadores', slug, CATEGORY_LABELS[slug]

    if source_category == 'Pilhas':
        if 'RECARREG' in description or ' REC.' in description:
            slug = 'interpilhas-pilhas-recarregaveis'
        elif any(token in description for token in ('SUPERLIFE', 'HEAVY DUTY', ' ZINC ')):
            slug = 'interpilhas-pilhas-zinco'
        elif (
            'SILVER OXIDE' in description
            or (brand == 'MAXELL' and re.search(r'PILHAS\s+3\d{2}\b', description))
            or (brand == 'VARTA' and re.fullmatch(r'I3\d{2}', ref))
        ):
            slug = 'interpilhas-pilhas-relogio'
        elif 'LITHIUM' in description or re.search(r'\b(?:CR\s?\d{4}|2CR5)\b', description):
            slug = 'interpilhas-pilhas-litio'
        elif re.search(r'\b(?:23\s?A|27\s?A|A76|LR44|4LR44|LR1|V\d{2}(?:GA|PX))\b', description):
            slug = 'interpilhas-pilhas-especiais'
        else:
            slug = 'interpilhas-pilhas-alcalinas'
        return 'Pilhas', slug, CATEGORY_LABELS[slug]

    if source_category == 'Fitas adesivas':
        slug = 'interpilhas-fitas-adesivas'
        return 'Colas e adesivos', slug, CATEGORY_LABELS[slug]

    if source_category in {'Colas', 'Colas e adesivos'}:
        if any(token in description for token in ('FITA', 'AUTOCOLANTE', 'AUTO-ADESIV', 'PONTOS ADESIV')):
            slug = 'interpilhas-fitas-adesivas'
        elif any(token in description for token in ('SILICONE', 'SELICONE', 'SELANTE')):
            slug = 'interpilhas-silicones-selantes'
        elif any(token in description for token in ('MASSA ', 'PLASTICINA COLANTE')):
            slug = 'interpilhas-massas-adesivas'
        elif 'CONTACTO' in description:
            slug = 'interpilhas-colas-contacto'
        elif any(
            token in description
            for token in ('PISTOLA', 'RECARGAS', 'LIMPADOR', 'DISOLVENTE')
        ):
            slug = 'interpilhas-ferramentas-acessorios'
        elif any(
            token in description
            for token in (
                'COLA STICK',
                'COLA ESCOLAR',
                'PURPURINA',
                'CORRECTOR',
                'FURADOR',
                'TESOURA',
                'AGRAFADOR',
                'APAGADOR MAGICO',
                'COLA ESPECIAL PARA GOMA EVA',
            )
        ):
            slug = 'interpilhas-escolar-escritorio'
        elif any(token in description for token in ('INSTANT', 'CIANOCRILATO', 'COLA EPOXY', 'COLA EPOXI', 'SUPER COLA', 'SUPERCOLA')):
            slug = 'interpilhas-colas-instantaneas'
        else:
            slug = 'interpilhas-colas-especiais-universais'
        return 'Colas e adesivos', slug, CATEGORY_LABELS[slug]

    raise ValueError(f'Unknown source category: {source_category}')


def read_products(workbook_path: Path) -> list[dict[str, Any]]:
    workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    sheet = workbook['PRODUTOS']
    headers = [plain_text(cell.value) for cell in sheet[1]]
    required = {
        'Referência', 'Marca', 'Categoria', 'Descrição', 'EAN', 'Cx Interior',
        'Cx Exterior', 'Preço Base', 'Ecovalor', 'Preço Unitário',
    }
    if not required.issubset(headers):
        raise ValueError(f'Missing workbook columns: {sorted(required - set(headers))}')
    products = []
    for sort_order, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=1):
        row = dict(zip(headers, values))
        ref = identifier(row['Referência'])
        if not ref:
            continue
        product_type, category_slug, family = classify_product(row)
        price_base = milli(row['Preço Base'])
        eco_value = milli(row['Ecovalor'])
        unit_price = milli(row['Preço Unitário'])
        if price_base + eco_value != unit_price:
            raise ValueError(f'Price mismatch for {ref}')
        products.append(
            {
                'ref': ref,
                'name': plain_text(row['Descrição']),
                'product_type': product_type,
                'category_slug': category_slug,
                'brand': BRAND_LABELS[ascii_upper(plain_text(row['Marca']))],
                'source_brand': ascii_upper(plain_text(row['Marca'])),
                'source_category': plain_text(row['Categoria']),
                'family': family,
                'ean': identifier(row['EAN']) or None,
                'case_inner': int(row['Cx Interior']) if row['Cx Interior'] is not None else None,
                'case_outer': int(row['Cx Exterior']) if row['Cx Exterior'] is not None else None,
                'price_base': f'{price_base:.3f}',
                'eco_value': f'{eco_value:.3f}',
                'price': f'{unit_price:.3f}',
                'quantity_step': 1,
                'sort_order': sort_order,
            }
        )
    refs = [product['ref'] for product in products]
    if len(products) != 419 or len(refs) != len(set(refs)):
        raise ValueError(f'Unexpected workbook product count or duplicate refs: {len(products)}')
    return products


def vertical_gap(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_bottom, first_top = first['y'], first['y'] + first['h']
    second_bottom, second_top = second['y'], second['y'] + second['h']
    if first_top < second_bottom:
        return second_bottom - first_top
    if second_top < first_bottom:
        return first_bottom - second_top
    return 0.0


def horizontally_related(first: dict[str, Any], second: dict[str, Any]) -> bool:
    left = max(first['x'], second['x'])
    right = min(first['x'] + first['w'], second['x'] + second['w'])
    overlap = max(0.0, right - left)
    return overlap >= min(first['w'], second['w']) * 0.7


def same_product_image(first: dict[str, Any], second: dict[str, Any]) -> bool:
    if not horizontally_related(first, second):
        return False
    first_bottom, first_top = first['y'], first['y'] + first['h']
    second_bottom, second_top = second['y'], second['y'] + second['h']
    overlap = max(0.0, min(first_top, second_top) - max(first_bottom, second_bottom))
    if overlap >= min(first['h'], second['h']) * 0.5:
        return True
    # A few supplier PDFs split one product photo into a large body plus a
    # narrow strip. Normal neighbouring rows can almost touch too, so only
    # join touching boxes when one of the pieces is clearly a small fragment.
    return (
        vertical_gap(first, second) <= 0.25
        and min(first['h'], second['h']) <= max(first['h'], second['h']) * 0.5
    )


def image_groups(page) -> list[list[dict[str, Any]]]:
    resources = page['/Resources'].get('/XObject', {})
    drawn = []

    def visitor(operator, operands, cm_matrix, _tm_matrix):
        if operator != b'Do':
            return
        name = str(operands[0])
        target = resources.get(operands[0])
        if target is None or str(target.get_object().get('/Subtype')) != '/Image':
            return
        image_file = page.images[name]
        drawn.append(
            {
                'index': len(drawn),
                'name': name,
                'image': image_file.image.convert('RGBA'),
                'x': float(cm_matrix[4]),
                'y': float(cm_matrix[5]),
                'w': abs(float(cm_matrix[0])),
                'h': abs(float(cm_matrix[3])),
            }
        )

    page.extract_text(visitor_operand_before=visitor)
    parent = list(range(len(drawn)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    for first_index, first in enumerate(drawn):
        for second_index in range(first_index + 1, len(drawn)):
            second = drawn[second_index]
            if same_product_image(first, second):
                union(first_index, second_index)

    grouped: dict[int, list[dict[str, Any]]] = {}
    for index, item in enumerate(drawn):
        grouped.setdefault(find(index), []).append(item)
    groups = list(grouped.values())
    groups.sort(key=lambda group: max(item['y'] + item['h'] for item in group), reverse=True)
    return groups


def compose_group(group: list[dict[str, Any]]) -> Image.Image:
    left = min(item['x'] for item in group)
    bottom = min(item['y'] for item in group)
    right = max(item['x'] + item['w'] for item in group)
    top = max(item['y'] + item['h'] for item in group)
    scales = [item['image'].width / item['w'] for item in group if item['w']]
    scale = max(1.0, median(scales))
    canvas = Image.new('RGBA', (max(1, round((right - left) * scale)), max(1, round((top - bottom) * scale))), (255, 255, 255, 0))
    for item in sorted(group, key=lambda value: value['index']):
        width = max(1, round(item['w'] * scale))
        height = max(1, round(item['h'] * scale))
        layer = item['image'].resize((width, height), Image.Resampling.LANCZOS)
        x = round((item['x'] - left) * scale)
        y = round((top - (item['y'] + item['h'])) * scale)
        canvas.alpha_composite(layer, (x, y))
    return canvas


def normalize_product_image(image: Image.Image) -> Image.Image:
    flattened = Image.new('RGB', image.size, 'white')
    if image.mode == 'RGBA':
        flattened.paste(image.convert('RGB'), mask=image.getchannel('A'))
    else:
        flattened.paste(image.convert('RGB'))
    array = np.asarray(flattened)
    mask = np.any(array < 247, axis=2)
    if mask.any():
        ys, xs = np.where(mask)
        pad = max(4, round(max(flattened.size) * 0.025))
        box = (
            max(0, int(xs.min()) - pad),
            max(0, int(ys.min()) - pad),
            min(flattened.width, int(xs.max()) + pad + 1),
            min(flattened.height, int(ys.max()) + pad + 1),
        )
        flattened = flattened.crop(box)
    contained = flattened.copy()
    contained.thumbnail((760, 760), Image.Resampling.LANCZOS)
    output = Image.new('RGB', (800, 800), 'white')
    output.paste(contained, ((800 - contained.width) // 2, (800 - contained.height) // 2))
    return output


def unique_matches(text: str, pattern: str) -> list[str]:
    result = []
    for match in re.findall(pattern, text, flags=re.IGNORECASE):
        value = str(match).upper()
        if value not in result:
            result.append(value)
    return result


def selected_refs_on_page(text: str, products: list[dict[str, Any]]) -> list[str]:
    matches = []
    normalized_text = re.sub(r'\s+', ' ', text)
    for product in products:
        ref = product['ref']
        match = re.search(rf'(?<![A-Z0-9]){re.escape(ref)}(?![A-Z0-9])', normalized_text, flags=re.IGNORECASE)
        if match:
            matches.append((match.start(), ref))
    return [ref for _, ref in sorted(matches)]


def extract_images(source_dir: Path, output_dir: Path, products: list[dict[str, Any]]) -> None:
    by_ref = {product['ref']: product for product in products}
    images_dir = output_dir / 'images'
    images_dir.mkdir(parents=True, exist_ok=False)
    assigned: set[str] = set()

    for pdf_name, source_brand, source_category in PDF_SELECTIONS:
        selected = [
            product for product in products
            if product['source_brand'] == source_brand and product['source_category'] == source_category
        ]
        reader = PdfReader(str(source_dir / pdf_name))
        for page_index, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            if source_brand == 'PHILIPS':
                page_refs = [product['ref'] for product in selected]
            elif source_brand == 'KODAK':
                page_refs = unique_matches(text, r'\bK\d+\b')
            else:
                page_refs = selected_refs_on_page(text, selected)

            groups = image_groups(page)
            # Supplier logos are embedded above the table. Some PDFs expose a
            # logo as one image and others as several adjacent strips; product
            # groups always follow it in top-to-bottom order.
            if len(groups) > len(page_refs):
                groups = groups[len(groups) - len(page_refs):]
            if len(groups) != len(page_refs):
                raise ValueError(
                    f'Image/row mismatch in {pdf_name} page {page_index + 1}: '
                    f'{len(groups)} image groups for {len(page_refs)} rows'
                )

            for ref, group in zip(page_refs, groups):
                if ref not in by_ref:
                    continue
                image = normalize_product_image(compose_group(group))
                filename = f'{ref}.webp'
                target = images_dir / filename
                image.save(target, 'WEBP', quality=88, method=6)
                checksum = hashlib.sha256(target.read_bytes()).hexdigest()
                by_ref[ref]['image_file'] = filename
                by_ref[ref]['image_checksum'] = checksum
                by_ref[ref]['image_mime_type'] = 'image/webp'
                assigned.add(ref)

    missing = sorted(set(by_ref) - assigned)
    if missing:
        raise ValueError(f'Missing images for {len(missing)} products: {missing[:20]}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Prepare the Interpilhas import package from the supplier workbook and PDFs.')
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f'Output directory already exists: {output_dir}')
    output_dir.mkdir(parents=True)

    products = read_products(source_dir / '7-Interpilhas.xlsx')
    extract_images(source_dir, output_dir, products)
    category_counts: dict[str, int] = {}
    brand_counts: dict[str, int] = {}
    for product in products:
        category_counts[product['family']] = category_counts.get(product['family'], 0) + 1
        brand_counts[product['brand']] = brand_counts.get(product['brand'], 0) + 1
        product.pop('source_brand', None)
        product.pop('source_category', None)

    manifest = {
        'catalog': 'interpilhas',
        'source': 'Interpilhas 2026',
        'product_count': len(products),
        'products': products,
    }
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {
        'products': len(products),
        'images': len(list((output_dir / 'images').glob('*.webp'))),
        'categories': dict(sorted(category_counts.items())),
        'brands': dict(sorted(brand_counts.items())),
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
