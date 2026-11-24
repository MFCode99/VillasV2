from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, LongTable, PageTemplate, Paragraph, Spacer, Table, TableStyle

from .catalog import normalize_choice_text
from .pdf_layout import normalize_pdf_layout
from .security import public_order_number


NAVY = colors.HexColor('#17243D')
GOLD = colors.HexColor('#C6A15B')
INK = colors.HexColor('#253147')
MUTED = colors.HexColor('#6F7888')
LINE = colors.HexColor('#DFE4EC')
PALE = colors.HexColor('#F4F6F9')
WHITE = colors.white
GREEN = colors.HexColor('#2E7D61')
AMBER = colors.HexColor('#B77822')
BLUE = colors.HexColor('#3C6E9F')
REFERENCE_ALIASES = {
    '4424a': '4424-8',
    '4424b': '4424-12',
}


def _order_catalog_label(order: dict[str, Any]) -> str:
    snapshot = dict(order.get('snapshot') or order.get('snapshot_json') or {})
    if order.get('catalogLabel') or snapshot.get('catalog_label'):
        return str(order.get('catalogLabel') or snapshot.get('catalog_label'))
    catalog_slug = str(order.get('catalogSlug') or order.get('catalog_slug') or snapshot.get('catalog_slug') or 'villas').casefold()
    return 'Utilidades' if catalog_slug == 'interpilhas' else 'Villas'


def _money(value: Any) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal('0.00')
    formatted = f'{amount:,.2f}'.replace(',', ' ').replace('.', ',')
    return f'{formatted} €'


def _unit_money(value: Any, catalog_slug: str | None = None) -> str:
    try:
        decimals = Decimal('0.001') if str(catalog_slug or '').casefold() == 'interpilhas' else Decimal('0.01')
        amount = Decimal(str(value or 0)).quantize(decimals)
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal('0.000') if str(catalog_slug or '').casefold() == 'interpilhas' else Decimal('0.00')
    digits = 3 if str(catalog_slug or '').casefold() == 'interpilhas' else 2
    formatted = f'{amount:,.{digits}f}'.replace(',', ' ').replace('.', ',')
    return f'{formatted} €'


def _text(value: Any) -> str:
    return escape(str(value or '').strip())


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def _unit_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal('0.001'))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.000')


def _display_ref(value: Any) -> str:
    raw = str(value or '').strip()
    return REFERENCE_ALIASES.get(raw.casefold(), raw)


def _item_value(item: dict[str, Any], camel: str, snapshot_key: str, default: Any = None) -> Any:
    value = item.get(camel)
    if value not in (None, ''):
        return value
    return (item.get('snapshot') or {}).get(snapshot_key, default)


def _grouped_items(order: dict[str, Any]) -> list[dict[str, Any]]:
    categories: dict[tuple[int, str], dict[str, Any]] = {}
    for index, item in enumerate(order.get('items') or []):
        category_label = str(_item_value(item, 'categoryLabel', 'category_label', '') or '').strip() or 'Sem categoria'
        try:
            category_order = int(_item_value(item, 'categorySortOrder', 'category_sort_order', 9999))
        except (TypeError, ValueError):
            category_order = 9999
        try:
            product_order = int(_item_value(item, 'productSortOrder', 'product_sort_order', 9999))
        except (TypeError, ValueError):
            product_order = 9999
        category_key = (category_order, category_label.casefold())
        category = categories.setdefault(category_key, {'label': category_label, 'order': category_order, 'products': {}})
        display_ref = _display_ref(item.get('ref') or _item_value(item, '', 'product_ref', ''))
        name = str(item.get('name') or _item_value(item, '', 'product_name', '') or '').strip()
        product_key = display_ref.casefold()
        product = category['products'].setdefault(product_key, {
            'ref': display_ref,
            'name': name,
            'sort_order': product_order,
            'first_index': index,
            'catalog_slug': item.get('catalogSlug') or _item_value(item, '', 'catalog_slug', 'villas'),
            'variants': {},
        })
        color = normalize_choice_text(item.get('color'))
        size = normalize_choice_text(item.get('size'))
        unit_price = _unit_decimal(item.get('unitPrice') or item.get('unit_price'))
        variant_key = (color.casefold(), size.casefold(), unit_price)
        quantity = int(item.get('quantity') or 0)
        line_total = _decimal(item.get('lineTotal') or item.get('line_total'))
        if line_total == Decimal('0.00') and unit_price:
            line_total = (unit_price * quantity).quantize(Decimal('0.01'))
        variant = product['variants'].setdefault(variant_key, {
            'color': color,
            'size': size,
            'quantity': 0,
            'unit_price': unit_price,
            'line_total': Decimal('0.00'),
        })
        variant['quantity'] += quantity
        variant['line_total'] += line_total

    result: list[dict[str, Any]] = []
    for category in sorted(categories.values(), key=lambda row: (row['order'], row['label'].casefold())):
        products = sorted(category['products'].values(), key=lambda row: (row['sort_order'], row['first_index'], row['ref'].casefold()))
        for product in products:
            product['variants'] = sorted(product['variants'].values(), key=lambda row: (row['color'].casefold(), row['size'].casefold()))
            product['quantity'] = sum(row['quantity'] for row in product['variants'])
            product['line_total'] = sum((row['line_total'] for row in product['variants']), Decimal('0.00'))
        result.append({'label': category['label'], 'products': products})
    return result


def _order_number(order: dict[str, Any]) -> str:
    existing = order.get('publicNumber') or order.get('public_number')
    if existing:
        return str(existing)
    created = order.get('createdAt') or order.get('created_at')
    year = created.year if isinstance(created, datetime) else datetime.now().year
    return public_order_number(year, int(order.get('id') or 0))


def _date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y às %H:%M')
    if not value:
        return '-'
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.strftime('%d/%m/%Y às %H:%M')
    except ValueError:
        return str(value)


def _status(order: dict[str, Any]):
    value = str(order.get('orderStatus') or order.get('order_status') or '').casefold()
    labels = {'pending': 'Pendente', 'confirmed': 'Confirmada', 'shipped': 'Enviada'}
    palette = {'pending': AMBER, 'confirmed': GREEN, 'shipped': BLUE}
    return labels.get(value, value.title() or '-'), palette.get(value, MUTED)


def _priced_styles(layout: dict[str, Any]):
    styles = getSampleStyleSheet()
    scale = {'compact': .88, 'normal': 1, 'large': 1.12}[layout['fontSize']]
    def size(value: float) -> float:
        return round(value * scale, 2)
    return {
        'title': ParagraphStyle('PricedOrderTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=size(20), leading=size(23), textColor=NAVY, spaceAfter=3),
        'subtitle': ParagraphStyle('PricedOrderSubtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=size(8.5), leading=size(12), textColor=MUTED),
        'section': ParagraphStyle('PricedOrderSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=size(10), leading=size(13), textColor=NAVY, spaceBefore=4, spaceAfter=7),
        'body': ParagraphStyle('PricedOrderBody', parent=styles['Normal'], fontName='Helvetica', fontSize=size(8.5), leading=size(12), textColor=INK),
        'body_bold': ParagraphStyle('PricedOrderBodyBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(8.5), leading=size(12), textColor=INK),
        'customer': ParagraphStyle('PricedOrderCustomer', parent=styles['Normal'], fontName='Helvetica', fontSize=size(8.3), leading=size(10.5), textColor=INK),
        'customer_bold': ParagraphStyle('PricedOrderCustomerBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(8.5), leading=size(10.8), textColor=INK),
        'small': ParagraphStyle('PricedOrderSmall', parent=styles['Normal'], fontName='Helvetica', fontSize=size(7.2), leading=size(9.5), textColor=MUTED),
        'category': ParagraphStyle('PricedOrderCategory', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(9), leading=size(11), textColor=NAVY),
        'table_header': ParagraphStyle('PricedOrderTableHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(7.2), leading=size(9.5), textColor=WHITE),
        'table': ParagraphStyle('PricedOrderTable', parent=styles['Normal'], fontName='Helvetica', fontSize=size(7.4), leading=size(9.5), textColor=INK),
        'table_bold': ParagraphStyle('PricedOrderTableBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(7.4), leading=size(9.5), textColor=INK),
        'table_right': ParagraphStyle('PricedOrderTableRight', parent=styles['Normal'], fontName='Helvetica', fontSize=size(7.4), leading=size(9.5), textColor=INK, alignment=TA_RIGHT),
        'table_center': ParagraphStyle('PricedOrderTableCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=size(7.4), leading=size(9.5), textColor=INK, alignment=TA_CENTER),
        'total_label': ParagraphStyle('PricedOrderTotalLabel', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(9), textColor=NAVY, alignment=TA_RIGHT),
        'total': ParagraphStyle('PricedOrderTotal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(13), textColor=NAVY, alignment=TA_RIGHT),
    }


def _no_price_styles(layout: dict[str, Any]):
    styles = getSampleStyleSheet()
    scale = {'compact': .88, 'normal': 1, 'large': 1.12}[layout['fontSize']]
    def size(value: float) -> float:
        return round(value * scale, 2)
    return {
        'title': ParagraphStyle('NoPriceOrderTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=size(21), leading=size(24), textColor=NAVY, spaceAfter=3),
        'subtitle': ParagraphStyle('NoPriceOrderSubtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=size(9.5), leading=size(13), textColor=MUTED),
        'section': ParagraphStyle('NoPriceOrderSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=size(11.5), leading=size(14), textColor=NAVY, spaceBefore=4, spaceAfter=7),
        'body': ParagraphStyle('NoPriceOrderBody', parent=styles['Normal'], fontName='Helvetica', fontSize=size(9.5), leading=size(13.5), textColor=INK),
        'body_bold': ParagraphStyle('NoPriceOrderBodyBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(9.5), leading=size(13.5), textColor=INK),
        'customer': ParagraphStyle('NoPriceOrderCustomer', parent=styles['Normal'], fontName='Helvetica', fontSize=size(8.3), leading=size(10.5), textColor=INK),
        'customer_bold': ParagraphStyle('NoPriceOrderCustomerBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(8.5), leading=size(10.8), textColor=INK),
        'small': ParagraphStyle('NoPriceOrderSmall', parent=styles['Normal'], fontName='Helvetica', fontSize=size(8.2), leading=size(10.5), textColor=MUTED),
        'category': ParagraphStyle('NoPriceOrderCategory', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(10), leading=size(12), textColor=NAVY),
        'table_header': ParagraphStyle('NoPriceOrderTableHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(8.1), leading=size(10.5), textColor=WHITE),
        'table': ParagraphStyle('NoPriceOrderTable', parent=styles['Normal'], fontName='Helvetica', fontSize=size(8.8), leading=size(11.5), textColor=INK),
        'table_bold': ParagraphStyle('NoPriceOrderTableBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(8.8), leading=size(11.5), textColor=INK),
        'table_center': ParagraphStyle('NoPriceOrderTableCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=size(8.8), leading=size(11.5), textColor=INK, alignment=TA_CENTER),
        'total': ParagraphStyle('NoPriceOrderTotal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size(14), textColor=NAVY, alignment=TA_RIGHT),
    }


def _priced_customer_block(order: dict[str, Any], styles: dict[str, ParagraphStyle], layout: dict[str, Any]) -> Table | None:
    if not layout['showCustomer'] or not layout['showContact'] or layout['showCarrier']:
        return _no_price_customer_block(order, styles, layout)
    name = order.get('customerName') or order.get('client') or order.get('cliente_nome') or '-'
    company = order.get('customerCompany') or order.get('cliente_empresa') or ''
    email = order.get('customerEmail') or order.get('cliente_email') or ''
    phone = order.get('customerPhone') or order.get('cliente_telefone') or ''
    nif = order.get('customerNif') or order.get('cliente_nif') or ''
    billing_parts = [order.get('customerBillingAddressLine1') or order.get('customerAddressLine1') or order.get('morada') or '', order.get('customerBillingAddressLine2') or '', ' '.join(filter(None, [order.get('customerBillingPostalCode') or order.get('customerPostalCode') or '', order.get('customerBillingCity') or order.get('customerCity') or order.get('localidade') or ''])), order.get('customerBillingCountry') or order.get('customerCountry') or order.get('pais') or '']
    delivery_parts = [order.get('customerDeliveryAddressLine1') or order.get('customerAddressLine1') or '', order.get('customerDeliveryAddressLine2') or '', ' '.join(filter(None, [order.get('customerDeliveryPostalCode') or order.get('customerPostalCode') or '', order.get('customerDeliveryCity') or order.get('customerCity') or ''])), order.get('customerDeliveryCountry') or order.get('customerCountry') or '']
    billing_address = '<br/>'.join(_text(part) for part in billing_parts if str(part or '').strip()) or '-'
    delivery_address = '<br/>'.join(_text(part) for part in delivery_parts if str(part or '').strip()) or '-'
    left = [Paragraph('CLIENTE', styles['small']), Spacer(1, 1.5 * mm), Paragraph(_text(name), styles['body_bold'])]
    if company:
        left.extend([Spacer(1, .8 * mm), Paragraph(_text(company), styles['body'])])
    if nif:
        left.extend([Spacer(1, .8 * mm), Paragraph(f'<font color="#6F7888">NIF</font>  {_text(nif)}', styles['body'])])
    contact_lines = [part for part in [email, phone] if part]
    right = [Paragraph('CONTACTO E ENTREGA', styles['small']), Spacer(1, 1.5 * mm)]
    if contact_lines:
        right.extend([Paragraph('<br/>'.join(_text(part) for part in contact_lines), styles['body']), Spacer(1, 1.5 * mm)])
    right.extend([Paragraph('<b>MORADA</b>', styles['small']), Paragraph(billing_address, styles['body'])])
    if delivery_address != billing_address:
        right.extend([Spacer(1, 1.5 * mm), Paragraph('<b>MORADA DE ENTREGA</b>', styles['small']), Paragraph(delivery_address, styles['body'])])
    table = Table([[left, right]], colWidths=[80 * mm, 102 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), WHITE), ('BOX', (0, 0), (-1, -1), .6, LINE),
        ('LINEBEFORE', (1, 0), (1, 0), .6, LINE), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 5 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5 * mm),
    ]))
    return table


def _no_price_customer_block(order: dict[str, Any], styles: dict[str, ParagraphStyle], layout: dict[str, Any]) -> Table | None:
    name = order.get('customerName') or order.get('client') or order.get('cliente_nome') or '-'
    company = order.get('customerCompany') or order.get('cliente_empresa') or ''
    email = order.get('customerEmail') or order.get('cliente_email') or ''
    phone = order.get('customerPhone') or order.get('cliente_telefone') or ''
    nif = order.get('customerNif') or order.get('cliente_nif') or ''
    customer_snapshot = order.get('customerSnapshot') or {}
    carrier = order.get('customerCarrier') or customer_snapshot.get('carrier') or (customer_snapshot.get('metadata') or {}).get('carrier') or ''
    delivery_parts = [order.get('customerDeliveryAddressLine1') or order.get('customerAddressLine1') or order.get('morada') or '', order.get('customerDeliveryAddressLine2') or order.get('customerAddressLine2') or '', ' '.join(filter(None, [order.get('customerDeliveryPostalCode') or order.get('customerPostalCode') or '', order.get('customerDeliveryCity') or order.get('customerCity') or order.get('localidade') or ''])), order.get('customerDeliveryCountry') or order.get('customerCountry') or order.get('pais') or '']
    address = '<br/>'.join(_text(part) for part in delivery_parts if str(part or '').strip()) or '-'
    columns: list[list[Any]] = []
    left = [Paragraph('CLIENTE', styles['small']), Spacer(1, .5 * mm), Paragraph(_text(name), styles['customer_bold'])]
    if company:
        left.extend([Spacer(1, .2 * mm), Paragraph(_text(company), styles['customer'])])
    if nif:
        left.extend([Spacer(1, .2 * mm), Paragraph(f'<font color="#6F7888">NIF</font>  {_text(nif)}', styles['customer'])])
    if layout['showCustomer']:
        columns.append(left)
    contact_lines = [part for part in [email, phone] if part]
    right = [Paragraph('CONTACTO E ENTREGA', styles['small']), Spacer(1, .5 * mm)]
    if contact_lines:
        right.extend([Paragraph('<br/>'.join(_text(part) for part in contact_lines), styles['customer']), Spacer(1, .4 * mm)])
    right.append(Paragraph(address, styles['customer']))
    if layout['showContact']:
        columns.append(right)
    if layout['showCarrier']:
        carrier_column = [
            Paragraph('TRANSPORTADORA / TRANSITÁRIO', styles['small']),
            Spacer(1, .5 * mm),
            Paragraph(f'<b>{_text(carrier) or "-"}</b>', styles['customer']),
        ]
        columns.append(carrier_column)
    if not columns:
        return None
    widths = [182 * mm / len(columns)] * len(columns)
    table = Table([columns], colWidths=widths, hAlign='LEFT')
    dividers = [('LINEBEFORE', (index, 0), (index, 0), .6, LINE) for index in range(1, len(columns))]
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), WHITE), ('BOX', (0, 0), (-1, -1), .6, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.2 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 3.2 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 2.6 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6 * mm),
        *dividers,
    ]))
    return table


def _priced_items_table(order: dict[str, Any], styles: dict[str, ParagraphStyle], layout: dict[str, Any]) -> LongTable:
    items = order.get('items') or []
    has_variants = any(normalize_choice_text(item.get('color')) or normalize_choice_text(item.get('size')) for item in items)
    headers = ['REF.']
    widths = [20 * mm]
    if layout['blankColumn']:
        headers.append('')
        widths.append(14 * mm)
    if layout['showProductName']:
        headers.append('PRODUTO')
        widths.append(58 * mm)
    if has_variants:
        headers.extend(['COR', 'TAM.'])
        widths.extend([23 * mm, 17 * mm])
    headers.extend(['QTD.', 'PREÇO UNIT.', 'TOTAL'])
    widths.extend([14 * mm, 25 * mm, 25 * mm])
    flexible_index = headers.index('PRODUTO') if 'PRODUTO' in headers else 0
    widths[flexible_index] += (182 - sum(width / mm for width in widths)) * mm
    data: list[list[Any]] = [[Paragraph(header, styles['table_header']) for header in headers]]
    category_rows: list[int] = []
    previous_category = None
    for item in items:
        category = str(_item_value(item, 'categoryLabel', 'category_label', '') or '').strip() or 'Sem categoria'
        if layout['showCategories'] and category != previous_category:
            category_rows.append(len(data))
            data.append([Paragraph(_text(category).upper(), styles['category'])] + [''] * (len(headers) - 1))
            previous_category = category
        row = [
            Paragraph(_text(item.get('ref')) or '-', styles['table_bold']),
        ]
        if layout['blankColumn']:
            row.append('')
        if layout['showProductName']:
            row.append(Paragraph(_text(item.get('name')) or '-', styles['table']))
        if has_variants:
            row.extend([
                Paragraph(_text(normalize_choice_text(item.get('color'))), styles['table']),
                Paragraph(_text(normalize_choice_text(item.get('size'))), styles['table_center']),
            ])
        row.extend([
            Paragraph(_text(item.get('quantity') or 0), styles['table_center']),
            Paragraph(_unit_money(
                item.get('unitPrice') or item.get('unit_price'),
                item.get('catalogSlug') or _item_value(item, '', 'catalog_slug', 'villas'),
            ), styles['table_right']),
            Paragraph(_money(item.get('lineTotal') or item.get('line_total')), styles['table_right']),
        ])
        data.append(row)
    if len(data) == 1:
        data.append([Paragraph('Sem artigos.', styles['table'])] + [''] * (len(headers) - 1))
    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    commands = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), .45, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 2.5 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 2.5 * mm),
        ('TOPPADDING', (0, 0), (-1, 0), 3 * mm), ('BOTTOMPADDING', (0, 0), (-1, 0), 3 * mm),
        ('TOPPADDING', (0, 1), (-1, -1), 3.2 * mm), ('BOTTOMPADDING', (0, 1), (-1, -1), 3.2 * mm),
    ]
    for row_index in category_rows:
        commands.extend([
            ('SPAN', (0, row_index), (-1, row_index)), ('BACKGROUND', (0, row_index), (-1, row_index), colors.HexColor('#E7D5A9')),
            ('BOX', (0, row_index), (-1, row_index), .45, GOLD),
            ('TOPPADDING', (0, row_index), (-1, row_index), 2.5 * mm), ('BOTTOMPADDING', (0, row_index), (-1, row_index), 2.5 * mm),
        ])
    for row_index in range(1, len(data)):
        if row_index not in category_rows and row_index % 2 == 0:
            commands.append(('BACKGROUND', (0, row_index), (-1, row_index), PALE))
    table.setStyle(TableStyle(commands))
    return table


def _no_price_items_tables(order: dict[str, Any], styles: dict[str, ParagraphStyle], layout: dict[str, Any]) -> list[Any]:
    grouped = _grouped_items(order)
    has_variants = any(
        variant['color'] or variant['size']
        for category in grouped
        for product in category['products']
        for variant in product['variants']
    )
    headers = ['REF.']
    widths = [22 * mm]
    if layout['blankColumn']:
        headers.append('')
        widths.append(18 * mm)
    headers.append('QTD.')
    widths.append(18 * mm)
    if layout['showProductName']:
        headers.append('PRODUTO')
        widths.append(52 * mm)
    if has_variants:
        headers.append('VARIANTES (COR · TAM. · QTD.)')
        widths.append((182 - sum(width / mm for width in widths)) * mm)
    elif layout['showProductName']:
        widths[-1] += (182 - sum(width / mm for width in widths)) * mm
    else:
        widths[0] += (182 - sum(width / mm for width in widths)) * mm
    if not grouped:
        grouped = [{'label': 'Artigos', 'products': []}]
    tables: list[Any] = []
    for category in grouped:
        data: list[list[Any]] = []
        header_row = 0
        if layout['showCategories']:
            data.append([Paragraph(_text(category['label']).upper(), styles['category'])] + [''] * (len(headers) - 1))
            header_row = 1
        data.append([Paragraph(header, styles['table_header']) for header in headers])
        for product in category['products']:
            variant_lines = []
            for variant in product['variants']:
                choices = ' · '.join(_text(value) for value in (variant['color'], variant['size']) if value)
                if choices:
                    variant_lines.append(f"<b>{choices}</b> · <b>{variant['quantity']} un.</b>")
            row = [
                Paragraph(_text(product['ref']) or '-', styles['table_bold']),
            ]
            if layout['blankColumn']:
                row.append('')
            row.append(Paragraph(str(product['quantity']), styles['table_center']))
            if layout['showProductName']:
                row.append(Paragraph(_text(product['name']) or '-', styles['table']))
            if has_variants:
                row.append(Paragraph('<br/>'.join(variant_lines), styles['table']))
            data.append(row)
        if len(data) == header_row + 1:
            data.append([Paragraph('Sem artigos.', styles['table'])] + [''] * (len(headers) - 1))
        table = LongTable(data, colWidths=widths, repeatRows=header_row + 1, hAlign='LEFT')
        commands = [
            ('BACKGROUND', (0, header_row), (-1, header_row), NAVY), ('TEXTCOLOR', (0, header_row), (-1, header_row), WHITE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, header_row), (-1, -1), .45, LINE),
            ('LEFTPADDING', (0, 0), (-1, -1), 2.7 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 2.7 * mm),
            ('TOPPADDING', (0, header_row), (-1, header_row), 2.7 * mm), ('BOTTOMPADDING', (0, header_row), (-1, header_row), 2.7 * mm),
            ('TOPPADDING', (0, header_row + 1), (-1, -1), 3 * mm), ('BOTTOMPADDING', (0, header_row + 1), (-1, -1), 3 * mm),
        ]
        if layout['showCategories']:
            commands.extend([
                ('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E7D5A9')),
                ('BOX', (0, 0), (-1, 0), .45, GOLD),
                ('TOPPADDING', (0, 0), (-1, 0), 2.5 * mm), ('BOTTOMPADDING', (0, 0), (-1, 0), 2.5 * mm),
            ])
        for row_index in range(header_row + 1, len(data)):
            if (row_index - header_row) % 2 == 0:
                commands.append(('BACKGROUND', (0, row_index), (-1, row_index), PALE))
        table.setStyle(TableStyle(commands))
        tables.extend([table, Spacer(1, 4 * mm)])
    return tables


def _page_decorator(title: str, public_number: str, hide_prices: bool, header_style: str = 'full'):
    def draw(canvas: Canvas, doc: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setTitle(f'Vitor Gouveia - {title} {public_number}')
        width, height = A4
        if header_style != 'hidden':
            header_height = 18 * mm if header_style == 'compact' else 30 * mm
            canvas.setFillColor(NAVY)
            canvas.rect(0, height - header_height, width, header_height, fill=1, stroke=0)
            logo_size = 9 * mm if header_style == 'compact' else 12 * mm
            logo_y = height - (13.5 * mm if header_style == 'compact' else 22 * mm)
            canvas.setFillColor(GOLD)
            canvas.roundRect(14 * mm, logo_y, logo_size, logo_size, 2 * mm, fill=1, stroke=0)
            canvas.setFillColor(NAVY)
            canvas.setFont('Helvetica-Bold', 11 if header_style == 'compact' else 15)
            canvas.drawCentredString(14 * mm + logo_size / 2, logo_y + logo_size * .31, 'VG')
            canvas.setFillColor(WHITE)
            canvas.setFont('Helvetica-Bold', 10 if header_style == 'compact' else 13)
            canvas.drawString(26 * mm if header_style == 'compact' else 30 * mm, height - (11.5 * mm if header_style == 'compact' else 15.8 * mm), 'VITOR GOUVEIA')
            if hide_prices and header_style == 'compact':
                canvas.setFillColor(GOLD)
                canvas.setFont('Helvetica-Bold', 5.8)
                canvas.drawString(26 * mm, height - 15.2 * mm, 'DOCUMENTO SEM PREÇOS')
                canvas.setFillColor(WHITE)
            canvas.setFont('Helvetica-Bold', 7.3 if header_style == 'compact' else 9)
            canvas.drawRightString(width - 14 * mm, height - (9 * mm if header_style == 'compact' else 15.2 * mm), title.upper())
            canvas.setFillColor(colors.HexColor('#CAD1DD'))
            canvas.setFont('Helvetica', 6.8 if header_style == 'compact' else 7.5)
            canvas.drawRightString(width - 14 * mm, height - (13 * mm if header_style == 'compact' else 20 * mm), public_number)
        if hide_prices and header_style == 'full':
            canvas.setStrokeColor(GOLD)
            canvas.setLineWidth(.7)
            canvas.roundRect(width - 57 * mm, height - 27 * mm, 43 * mm, 5.5 * mm, 1.8 * mm, fill=0, stroke=1)
            canvas.setFillColor(GOLD)
            canvas.setFont('Helvetica-Bold', 6.4)
            canvas.drawCentredString(width - 35.5 * mm, height - 25.2 * mm, 'DOCUMENTO SEM PREÇOS')
        canvas.setStrokeColor(LINE)
        canvas.line(14 * mm, 14 * mm, width - 14 * mm, 14 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 6.8)
        canvas.drawString(14 * mm, 9.5 * mm, 'Vitor Gouveia - Documento comercial gerado eletronicamente')
        canvas.drawRightString(width - 14 * mm, 9.5 * mm, f'Página {doc.page}')
        canvas.restoreState()
    return draw


def _document(buffer: BytesIO, *, title: str, number: str, hide_prices: bool, header_style: str = 'full') -> BaseDocTemplate:
    top_margin = {'full': 35, 'compact': 22, 'hidden': 10}.get(header_style, 35) * mm
    frame = Frame(14 * mm, 18 * mm, A4[0] - 28 * mm, A4[1] - top_margin - 18 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document = BaseDocTemplate(buffer, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=top_margin, bottomMargin=18 * mm, title=f'Vitor Gouveia - {title} {number}', author='Vitor Gouveia', subject=title)
    document.addPageTemplates([PageTemplate(id='order', frames=[frame], onPage=_page_decorator(title, number, hide_prices, header_style))])
    return document


def _heading(order: dict[str, Any], styles: dict[str, ParagraphStyle], *, title: str, number: str, priced: bool, show_title: bool = True) -> Table:
    status_label, status_color = _status(order)
    created_at = order.get('createdAt') or order.get('created_at') or order.get('criado_em')
    cells = [
        [Paragraph('NÚMERO', styles['small']), Spacer(1, 1 * mm), Paragraph(_text(number), styles['body_bold'])],
        [Paragraph('DATA', styles['small']), Spacer(1, 1 * mm), Paragraph(_text(_date(created_at)), styles['body_bold'])],
        [Paragraph('ESTADO', styles['small']), Spacer(1, 1 * mm), Paragraph(_text(status_label), styles['body_bold'])],
    ]
    widths = [60.6 * mm, 60.7 * mm, 60.7 * mm]
    if show_title:
        cells.insert(0, [Paragraph(title, styles['title']), Paragraph('Documento de encomenda', styles['subtitle'])])
        widths = [71 * mm, 34 * mm, 43 * mm, 34 * mm] if priced else [63 * mm, 42 * mm, 43 * mm, 34 * mm]
    heading = Table([cells], colWidths=widths)
    heading.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, 0), 4 * mm), ('RIGHTPADDING', (0, 0), (-1, 0), 3 * mm),
        ('TOPPADDING', (0, 0), (-1, 0), 3 * mm), ('BOTTOMPADDING', (0, 0), (-1, 0), 3 * mm),
        ('BOX', (1 if show_title else 0, 0), (-1, 0), .6, LINE), ('LINEBEFORE', (2 if show_title else 1, 0), (-1, 0), .6, LINE),
        ('BACKGROUND', (-1, 0), (-1, 0), colors.Color(status_color.red, status_color.green, status_color.blue, alpha=.10)),
    ]))
    if show_title:
        heading.setStyle(TableStyle([('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (0, 0), (0, 0), 5 * mm)]))
    return heading


def _pdf_notes_block(order: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    if not order.get('includePdfNotes'):
        return []
    notes = str(order.get('pdfNotes') or '').strip()
    if not notes:
        return []
    content = '<br/>'.join(_text(line) for line in notes.splitlines())
    table = Table([[Paragraph(content, styles['body'])]], colWidths=[182 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFF8E8')),
        ('BOX', (0, 0), (-1, -1), .7, GOLD),
        ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 3 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
    ]))
    return [Paragraph('OBSERVAÇÕES', styles['section']), table, Spacer(1, 5 * mm)]


def _priced_pdf(order: dict[str, Any], layout_value: dict[str, Any] | None) -> bytes:
    layout = normalize_pdf_layout(layout_value, kind='priced')
    buffer = BytesIO()
    styles = _priced_styles(layout)
    number = _order_number(order)
    title = f'Nota de encomenda - {_order_catalog_label(order)}'
    document = _document(buffer, title=title, number=number, hide_prices=False, header_style=layout['headerStyle'])
    story: list[Any] = [_heading(order, styles, title=title, number=number, priced=True, show_title=layout['showDocumentHeading']), Spacer(1, 6 * mm)]
    customer_block = _priced_customer_block(order, styles, layout)
    if customer_block is not None:
        story.extend([customer_block, Spacer(1, 7 * mm)])
    story.extend([Paragraph('ARTIGOS', styles['section']), _priced_items_table(order, styles, layout), Spacer(1, 6 * mm)])
    story.extend(_pdf_notes_block(order, styles))
    summary = Table([
        [Paragraph('Subtotal', styles['total_label']), Paragraph(_money(order.get('subtotal')), styles['total_label'])],
        [Paragraph('TOTAL', styles['total_label']), Paragraph(_money(order.get('total')), styles['total'])],
    ], colWidths=[35 * mm, 42 * mm], hAlign='RIGHT')
    summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PALE), ('BOX', (0, 0), (-1, -1), .6, LINE), ('LINEABOVE', (0, 1), (-1, 1), .6, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 3 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    if layout['showSummary']:
        story.append(summary)
    story.extend([Spacer(1, 8 * mm), Paragraph('Obrigado pela sua encomenda.', styles['subtitle'])])
    document.build(story)
    return buffer.getvalue()


def _no_price_pdf(order: dict[str, Any], layout_value: dict[str, Any] | None) -> bytes:
    layout = normalize_pdf_layout(layout_value)
    buffer = BytesIO()
    styles = _no_price_styles(layout)
    number = _order_number(order)
    title = f'Guia de preparação - {_order_catalog_label(order)}'
    document = _document(buffer, title=title, number=number, hide_prices=True, header_style=layout['headerStyle'])
    story: list[Any] = [_heading(order, styles, title=title, number=number, priced=False, show_title=layout['showDocumentHeading']), Spacer(1, 4 * mm)]
    customer_block = _no_price_customer_block(order, styles, layout)
    if customer_block is not None:
        story.extend([customer_block, Spacer(1, 5 * mm)])
    story.append(Paragraph('ARTIGOS POR CATEGORIA' if layout['showCategories'] else 'ARTIGOS', styles['section']))
    story.extend(_no_price_items_tables(order, styles, layout))
    story.extend(_pdf_notes_block(order, styles))
    if layout['showSummary']:
        item_groups = _grouped_items(order)
        summary = Table([
            [Paragraph('REFERÊNCIAS', styles['small']), Paragraph('UNIDADES', styles['small'])],
            [Paragraph(str(sum(len(group['products']) for group in item_groups)), styles['total']), Paragraph(_text(order.get('units') or 0), styles['total'])],
        ], colWidths=[35 * mm, 35 * mm], hAlign='RIGHT')
        summary.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), PALE), ('BOX', (0, 0), (-1, -1), .6, LINE), ('LINEABOVE', (0, 1), (-1, 1), .6, LINE),
            ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 3 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.extend([Spacer(1, 2 * mm), summary])
    document.build(story)
    return buffer.getvalue()


def build_order_pdf(order: dict[str, Any], *, hide_prices: bool = False, layout: dict[str, Any] | None = None) -> bytes:
    if hide_prices:
        return _no_price_pdf(order, layout)
    return _priced_pdf(order, layout)
