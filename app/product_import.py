from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
import re
import unicodedata
from typing import Any

from openpyxl import load_workbook
from pypdf import PdfReader


MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_PDF_IMPORT_BYTES = 40 * 1024 * 1024
MAX_PDF_IMPORT_PAGES = 250
_PDF_DASHES = {'-', '–', '—', '―'}
_PDF_ROW_TAIL = re.compile(
    r'^(?P<prefix>.+?)\s+(?P<ean>\d{8,14}|[-–—―])\s+'
    r'(?P<inner>\d+|[-–—―])\s+(?P<outer>\d+|[-–—―])\s+'
    r'(?P<price>\d+(?:[.,]\d{2,3}))\s*(?:€|EUR)?\s*$',
    re.IGNORECASE,
)
_PDF_ROW_WITH_ECO = re.compile(
    r'^(?P<ref>[A-Z0-9][A-Z0-9./_-]{2,})\s+(?P<body>.+?)\s*'
    r'(?P<ean>\d{8,14}|[-–—―])\s+(?P<outer>\d+|[-–—―])\s+'
    r'(?P<inner>\d+|[-–—―])\s+(?P<base>\d+(?:[.,]\d{2,3}))\s*(?:€|EUR)\s+'
    r'(?P<eco>\d+(?:[.,]\d{1,3})|[-–—―])\s*(?:€|EUR)?'
    r'(?:\s+(?P<total>\d+(?:[.,]\d{2,3}))\s*(?:€|EUR)?)?\s*$',
    re.IGNORECASE,
)
_PDF_ATTACHED_FAMILIES = ('RECARREGÁVEL', 'CARREGADOR', 'LANTERNA', 'ALCALINA', 'LITIUM', 'ZINCO')
def _text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _key(value: Any) -> str:
    normalized = unicodedata.normalize('NFKD', _text(value)).encode('ascii', 'ignore').decode('ascii').casefold()
    return re.sub(r'[^a-z0-9]+', ' ', normalized).strip()


def _decimal(value: Any) -> str | None:
    if value in (None, ''):
        return None
    raw = _text(value).replace('€', '').replace(' ', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    else:
        raw = raw.replace(',', '.')
    try:
        return f'{Decimal(raw):.3f}'
    except (InvalidOperation, ValueError):
        return None


def _integer(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        result = int(Decimal(_text(value).replace(',', '.')))
        return result if result > 0 else None
    except (InvalidOperation, ValueError):
        return None


def _boolean(value: Any, default: bool = True) -> bool:
    if value in (None, ''):
        return default
    return _key(value) not in {'0', 'nao', 'no', 'false', 'inativo', 'off'}


def _field_for_header(header: Any) -> str | None:
    value = _key(header)
    if value in {'ref', 'sku', 'codigo', 'codigo produto'} or value.startswith('refer'):
        return 'ref'
    if 'marca' in value or value == 'brand':
        return 'brand'
    if 'subcategoria' in value:
        return 'subcategory'
    if 'categoria' in value:
        return 'category'
    if any(term in value for term in ('descricao', 'descri', 'designacao')) or value in {'nome', 'produto', 'name'}:
        return 'name'
    if value in {'ean', 'gtin', 'codigo barras', 'codigo de barras'}:
        return 'ean'
    if 'interior' in value:
        return 'case_inner'
    if 'exterior' in value or 'master' in value:
        return 'case_outer'
    if value.startswith('eco') or 'ecotaxa' in value:
        return 'eco_value'
    if ('base' in value and value.startswith('pre')) or value == 'base price':
        return 'price_base'
    if 'pvp' in value:
        return 'pvp'
    if (value.startswith('pre') and any(term in value for term in ('unit', 'final', 'venda'))) or 'unit price' in value or value in {'preco', 'pre o', 'preo'}:
        return 'price'
    if 'familia' in value or value == 'family':
        return 'family'
    if value in {'tipo', 'type', 'tipo produto'}:
        return 'product_type'
    if 'multiplo' in value or 'passo quantidade' in value:
        return 'quantity_step'
    if 'atalho' in value:
        return 'quick_quantities'
    if value in {'ativo', 'active'}:
        return 'active'
    if value in {'cores', 'colors'}:
        return 'colors'
    if value in {'tamanhos', 'sizes'}:
        return 'sizes'
    return None


def _rows_from_xlsx(content: bytes) -> tuple[str, list[list[Any]]]:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    sheet = next((item for item in workbook.worksheets if _key(item.title) in {'produtos', 'products'}), workbook.active)
    return sheet.title, [list(row) for row in sheet.iter_rows(values_only=True)]


def _rows_from_csv(content: bytes) -> tuple[str, list[list[Any]]]:
    decoded = content.decode('utf-8-sig', errors='replace')
    dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=';,\t')
    return 'CSV', [list(row) for row in csv.reader(StringIO(decoded), dialect)]


def _pdf_value(value: str) -> int | None:
    return None if value.strip() in _PDF_DASHES else _integer(value)


def _decimal_sum(first: str, second: str) -> str:
    return f'{Decimal(first) + Decimal(second):.3f}'


def _pdf_family_and_name(body: str) -> tuple[str | None, str]:
    value = re.sub(r'\s+', ' ', body).strip()
    upper_value = value.upper()
    for family in _PDF_ATTACHED_FAMILIES:
        if upper_value.endswith(family) and len(value) > len(family):
            return family, value[:-len(family)].strip()
    parts = value.rsplit(maxsplit=1)
    if len(parts) == 2:
        candidate = parts[1].strip('()[]')
        letters = re.sub(r'[^A-Za-zÀ-ſ]', '', candidate)
        if len(letters) >= 4 and letters == letters.upper():
            return candidate, parts[0].strip()
    return None, value


def _pdf_product_lead(prefix: str, has_photo_column: bool) -> tuple[str, str] | None:
    value = prefix.strip()
    if has_photo_column:
        photo_match = re.match(r'^(\d{4,12})\s+(.+)$', value)
        if photo_match is None:
            return None
        product_ref = photo_match.group(1).strip()
        product_name = photo_match.group(2).strip()
        product_name = re.sub(r'^([A-Z]*\d[A-Z0-9./_]*)-(?=\S)', r'\1 - ', product_name, flags=re.IGNORECASE)
        name_parts = product_name.split(maxsplit=1)
        if len(name_parts) == 2 and not product_name.startswith(f'{name_parts[0]} - '):
            product_name = f'{name_parts[0]} - {name_parts[1].lstrip("- ")}'
        return product_ref, product_name
    attached = re.match(r'^([A-Z]*\d[A-Z0-9./_]*)-(.+)$', value, re.IGNORECASE)
    if attached is not None:
        return attached.group(1).strip(), attached.group(2).strip()
    if ' - ' in value:
        ref, name = value.split(' - ', 1)
        if ' ' in ref.strip():
            ref, name = value.split(maxsplit=1)
        return ref.strip(), name.strip()
    parts = value.split(maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None


def _parse_pdf_products(content: bytes, filename: str, catalog_slug: str, category_label: str = '') -> dict[str, Any]:
    if len(content) > MAX_PDF_IMPORT_BYTES:
        raise ValueError('import_file_too_large')
    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise ValueError('invalid_pdf') from exc
    if reader.is_encrypted:
        raise ValueError('encrypted_pdf_not_supported')
    if not reader.pages or len(reader.pages) > MAX_PDF_IMPORT_PAGES:
        raise ValueError('invalid_pdf_page_count')

    page_texts = [page.extract_text() or '' for page in reader.pages]
    if sum(len(text.strip()) for text in page_texts) < 40:
        raise ValueError('pdf_text_not_detected')
    header_text = '\n'.join(page_texts[:3])
    has_photo_column = 'FOTO' in header_text.upper() and 'REFER' in _key(header_text).upper()

    products: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidate_lines = 0
    for page_number, text in enumerate(page_texts, start=1):
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = re.sub(r'\s+', ' ', raw_line).strip()
            eco_row = _PDF_ROW_WITH_ECO.match(line)
            if eco_row is not None:
                candidate_lines += 1
                ref = _text(eco_row.group('ref')).upper()
                if ref in seen:
                    errors.append({'row': page_number, 'ref': ref, 'messages': ['Referência duplicada no PDF']})
                    continue
                seen.add(ref)
                family, name = _pdf_family_and_name(eco_row.group('body'))
                case_inner = _pdf_value(eco_row.group('inner'))
                case_outer = _pdf_value(eco_row.group('outer'))
                quantity_step = case_inner or case_outer or 1
                quick_quantities = sorted({value for value in (case_inner, case_outer) if value and value > 1})
                price_base = _decimal(eco_row.group('base')) or '0.000'
                eco_value = '0.000' if eco_row.group('eco').strip() in _PDF_DASHES else (_decimal(eco_row.group('eco')) or '0.000')
                price = _decimal(eco_row.group('total')) if eco_row.group('total') else _decimal_sum(price_base, eco_value)
                products.append({
                    'source_row': page_number,
                    'ref': ref,
                    'catalog_slug': catalog_slug,
                    'name': name,
                    'product_type': family or category_label or 'Produto',
                    'category_label': category_label,
                    'parent_category_label': '',
                    'brand': name.split(maxsplit=1)[0] if name else None,
                    'family': family,
                    'ean': None if eco_row.group('ean').strip() in _PDF_DASHES else eco_row.group('ean').strip(),
                    'price': price,
                    'price_base': price_base,
                    'eco_value': eco_value,
                    'pvp': None,
                    'case_inner': case_inner,
                    'case_outer': case_outer,
                    'colors': [],
                    'sizes': [],
                    'season': 'ambos',
                    'quantity_step': quantity_step,
                    'quick_quantities': quick_quantities[:4],
                    'sort_order': len(products),
                    'active': True,
                    'manual_active': True,
                    'description': None,
                })
                continue
            tail = _PDF_ROW_TAIL.match(line)
            if tail is None:
                continue
            candidate_lines += 1
            lead = _pdf_product_lead(tail.group('prefix'), has_photo_column)
            if lead is None:
                errors.append({
                    'row': page_number,
                    'ref': '',
                    'messages': [f'Não foi possível separar a referência e o nome (linha {line_number} da página).'],
                })
                continue

            ref = _text(lead[0]).upper()
            name = re.sub(r'^[-–—―\s]+|[-–—―\s]+$', '', _text(lead[1]))
            row_errors: list[str] = []
            if not ref:
                row_errors.append('Referência em falta')
            if not name:
                row_errors.append('Nome em falta')
            if ref in seen:
                row_errors.append('Referência duplicada no PDF')
            seen.add(ref)
            if row_errors:
                errors.append({'row': page_number, 'ref': ref, 'messages': row_errors})
                continue

            case_inner = _pdf_value(tail.group('inner'))
            case_outer = _pdf_value(tail.group('outer'))
            quantity_step = case_inner or case_outer or 1
            quick_quantities = sorted({value for value in (case_inner, case_outer) if value and value > 1})
            name_parts = [part.strip() for part in name.split(' - ') if part.strip()]
            brand = name_parts[1] if len(name_parts) > 1 and re.fullmatch(r'[A-Z]*\d[A-Z0-9./_-]*', name_parts[0], re.IGNORECASE) else (name_parts[0] if len(name_parts) > 1 else None)
            products.append({
                'source_row': page_number,
                'ref': ref,
                'catalog_slug': catalog_slug,
                'name': name,
                'product_type': category_label or 'Produto',
                'category_label': category_label,
                'parent_category_label': '',
                'brand': brand,
                'family': None,
                'ean': None if tail.group('ean').strip() in _PDF_DASHES else tail.group('ean').strip(),
                'price': _decimal(tail.group('price')),
                'price_base': None,
                'eco_value': '0.000',
                'pvp': None,
                'case_inner': case_inner,
                'case_outer': case_outer,
                'colors': [],
                'sizes': [],
                'season': 'ambos',
                'quantity_step': quantity_step,
                'quick_quantities': quick_quantities[:4],
                'sort_order': len(products),
                'active': True,
                'manual_active': True,
                'description': None,
            })
    if not candidate_lines:
        raise ValueError('pdf_product_table_not_detected')
    return {
        'sheet': f'PDF · {len(reader.pages)} páginas',
        'source_type': 'pdf',
        'rows': products,
        'errors': errors,
        'headers': ['Referência', 'Descrição', 'EAN', 'Caixa interior', 'Caixa exterior', 'Preço'],
    }


def parse_product_file(content: bytes, filename: str, catalog_slug: str, category_label: str = '') -> dict[str, Any]:
    if not content:
        raise ValueError('import_file_empty')
    lower_name = (filename or '').casefold()
    limit = MAX_PDF_IMPORT_BYTES if lower_name.endswith('.pdf') else MAX_IMPORT_BYTES
    if len(content) > limit:
        raise ValueError('import_file_too_large')
    if lower_name.endswith('.pdf'):
        return _parse_pdf_products(content, filename, catalog_slug, category_label.strip())
    if lower_name.endswith('.xlsx'):
        sheet_name, raw_rows = _rows_from_xlsx(content)
    elif lower_name.endswith(('.csv', '.txt')):
        sheet_name, raw_rows = _rows_from_csv(content)
    else:
        raise ValueError('import_file_type')
    raw_rows = [row for row in raw_rows if any(_text(value) for value in row)]
    if not raw_rows:
        raise ValueError('import_file_empty')

    header_index = 0
    mapping: dict[int, str] = {}
    for index, row in enumerate(raw_rows[:20]):
        candidate = {column: _field_for_header(value) for column, value in enumerate(row)}
        candidate = {column: field for column, field in candidate.items() if field}
        if {'ref', 'name'}.issubset(set(candidate.values())):
            header_index = index
            mapping = candidate
            break
    if not mapping or 'price' not in mapping.values():
        raise ValueError('import_columns_missing')

    products: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sheet_row, values in enumerate(raw_rows[header_index + 1:], start=header_index + 2):
        source = {field: values[column] if column < len(values) else None for column, field in mapping.items()}
        ref = _text(source.get('ref')).upper()
        name = _text(source.get('name'))
        price = _decimal(source.get('price'))
        row_errors: list[str] = []
        if not ref:
            row_errors.append('Referência em falta')
        if not name:
            row_errors.append('Nome em falta')
        if price is None:
            row_errors.append('Preço inválido ou em falta')
        if ref and ref in seen:
            row_errors.append('Referência duplicada no ficheiro')
        if ref:
            seen.add(ref)
        if row_errors:
            errors.append({'row': sheet_row, 'ref': ref, 'messages': row_errors})
            continue
        case_inner = _integer(source.get('case_inner'))
        case_outer = _integer(source.get('case_outer'))
        quick_raw = re.findall(r'\d+', _text(source.get('quick_quantities')))
        quick_quantities = sorted({int(value) for value in quick_raw if int(value) > 0})
        if not quick_quantities and catalog_slug == 'interpilhas':
            quick_quantities = sorted({value for value in (case_inner, case_outer) if value and value > 1})
        parent_category = _text(source.get('category'))
        category = _text(source.get('subcategory')) or parent_category
        products.append({
            'source_row': sheet_row,
            'ref': ref,
            'catalog_slug': catalog_slug,
            'name': name,
            'product_type': _text(source.get('product_type')) or category or 'Produto',
            'category_label': category,
            'parent_category_label': parent_category if category != parent_category else '',
            'brand': _text(source.get('brand')) or None,
            'family': _text(source.get('family')) or None,
            'ean': _text(source.get('ean')) or None,
            'price': price,
            'price_base': _decimal(source.get('price_base')),
            'eco_value': _decimal(source.get('eco_value')) or '0.000',
            'pvp': _decimal(source.get('pvp')),
            'case_inner': case_inner,
            'case_outer': case_outer,
            'colors': [value.strip() for value in re.split(r'[,;|]', _text(source.get('colors'))) if value.strip()],
            'sizes': [value.strip() for value in re.split(r'[,;|]', _text(source.get('sizes'))) if value.strip()],
            'season': 'ambos',
            'quantity_step': _integer(source.get('quantity_step')) or 1,
            'quick_quantities': quick_quantities[:4],
            'sort_order': 0,
            'active': _boolean(source.get('active')),
            'manual_active': True,
            'description': None,
        })
    return {'sheet': sheet_name, 'rows': products, 'errors': errors, 'headers': [_text(value) for value in raw_rows[header_index]]}
