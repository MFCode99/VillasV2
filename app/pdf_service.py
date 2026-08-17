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


def _money(value: Any) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal('0.00')
    formatted = f'{amount:,.2f}'.replace(',', ' ').replace('.', ',')
    return f'{formatted} €'


def _text(value: Any) -> str:
    return escape(str(value or '').strip())


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


def _styles():
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('OrderTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, leading=23, textColor=NAVY, spaceAfter=3),
        'subtitle': ParagraphStyle('OrderSubtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=MUTED),
        'section': ParagraphStyle('OrderSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=10, leading=13, textColor=NAVY, spaceBefore=4, spaceAfter=7),
        'body': ParagraphStyle('OrderBody', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=INK),
        'body_bold': ParagraphStyle('OrderBodyBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=12, textColor=INK),
        'small': ParagraphStyle('OrderSmall', parent=styles['Normal'], fontName='Helvetica', fontSize=7.2, leading=9.5, textColor=MUTED),
        'table_header': ParagraphStyle('OrderTableHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.2, leading=9.5, textColor=WHITE),
        'table': ParagraphStyle('OrderTable', parent=styles['Normal'], fontName='Helvetica', fontSize=7.4, leading=9.5, textColor=INK),
        'table_bold': ParagraphStyle('OrderTableBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.4, leading=9.5, textColor=INK),
        'table_right': ParagraphStyle('OrderTableRight', parent=styles['Normal'], fontName='Helvetica', fontSize=7.4, leading=9.5, textColor=INK, alignment=TA_RIGHT),
        'table_center': ParagraphStyle('OrderTableCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7.4, leading=9.5, textColor=INK, alignment=TA_CENTER),
        'total_label': ParagraphStyle('OrderTotalLabel', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=NAVY, alignment=TA_RIGHT),
        'total': ParagraphStyle('OrderTotal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=13, textColor=NAVY, alignment=TA_RIGHT),
    }


def _customer_block(order: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    name = order.get('customerName') or order.get('client') or order.get('cliente_nome') or '-'
    company = order.get('customerCompany') or order.get('cliente_empresa') or ''
    email = order.get('customerEmail') or order.get('cliente_email') or ''
    phone = order.get('customerPhone') or order.get('cliente_telefone') or ''
    nif = order.get('customerNif') or order.get('cliente_nif') or ''
    address_parts = [
        order.get('customerAddressLine1') or order.get('morada') or '',
        order.get('customerAddressLine2') or '',
        ' '.join(filter(None, [order.get('customerPostalCode') or '', order.get('customerCity') or order.get('localidade') or ''])),
        order.get('customerCountry') or order.get('pais') or '',
    ]
    address = '<br/>'.join(_text(part) for part in address_parts if str(part or '').strip()) or '-'
    left = [Paragraph('CLIENTE', styles['small']), Spacer(1, 1.5 * mm), Paragraph(_text(name), styles['body_bold'])]
    if company:
        left.extend([Spacer(1, .8 * mm), Paragraph(_text(company), styles['body'])])
    if nif:
        left.extend([Spacer(1, .8 * mm), Paragraph(f'<font color="#6F7888">NIF</font>  {_text(nif)}', styles['body'])])
    contact_lines = [part for part in [email, phone] if part]
    right = [Paragraph('CONTACTO E ENTREGA', styles['small']), Spacer(1, 1.5 * mm)]
    if contact_lines:
        right.extend([Paragraph('<br/>'.join(_text(part) for part in contact_lines), styles['body']), Spacer(1, 1.5 * mm)])
    right.append(Paragraph(address, styles['body']))
    table = Table([[left, right]], colWidths=[80 * mm, 102 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), WHITE), ('BOX', (0, 0), (-1, -1), .6, LINE),
        ('LINEBEFORE', (1, 0), (1, 0), .6, LINE), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 5 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5 * mm),
    ]))
    return table


def _items_table(order: dict[str, Any], styles: dict[str, ParagraphStyle], *, hide_prices: bool) -> LongTable:
    if hide_prices:
        headers = ['REF.', 'PRODUTO', 'COR', 'TAMANHO', 'QTD.']
        widths = [24 * mm, 82 * mm, 31 * mm, 27 * mm, 18 * mm]
    else:
        headers = ['REF.', 'PRODUTO', 'COR', 'TAM.', 'QTD.', 'PREÇO UNIT.', 'TOTAL']
        widths = [20 * mm, 58 * mm, 23 * mm, 17 * mm, 14 * mm, 25 * mm, 25 * mm]
    data: list[list[Any]] = [[Paragraph(header, styles['table_header']) for header in headers]]
    for item in order.get('items') or []:
        row = [
            Paragraph(_text(item.get('ref')) or '-', styles['table_bold']),
            Paragraph(_text(item.get('name')) or '-', styles['table']),
            Paragraph(_text(normalize_choice_text(item.get('color'))) or '-', styles['table']),
            Paragraph(_text(normalize_choice_text(item.get('size'))) or '-', styles['table_center']),
            Paragraph(_text(item.get('quantity') or 0), styles['table_center']),
        ]
        if not hide_prices:
            row.extend([
                Paragraph(_money(item.get('unitPrice') or item.get('unit_price')), styles['table_right']),
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
    for row_index in range(1, len(data)):
        if row_index % 2 == 0:
            commands.append(('BACKGROUND', (0, row_index), (-1, row_index), PALE))
    table.setStyle(TableStyle(commands))
    return table


def _page_decorator(title: str, public_number: str, hide_prices: bool):
    def draw(canvas: Canvas, doc: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setTitle(f'Villas - {title} {public_number}')
        width, height = A4
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 30 * mm, width, 30 * mm, fill=1, stroke=0)
        canvas.setFillColor(GOLD)
        canvas.roundRect(14 * mm, height - 22 * mm, 12 * mm, 12 * mm, 2.5 * mm, fill=1, stroke=0)
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 15)
        canvas.drawCentredString(20 * mm, height - 18.2 * mm, 'V')
        canvas.setFillColor(WHITE)
        canvas.setFont('Helvetica-Bold', 16)
        canvas.drawString(30 * mm, height - 15.8 * mm, 'VILLAS')
        canvas.setFillColor(colors.HexColor('#CAD1DD'))
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(WHITE)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawRightString(width - 14 * mm, height - 15.2 * mm, title.upper())
        canvas.setFillColor(colors.HexColor('#CAD1DD'))
        canvas.setFont('Helvetica', 7.5)
        canvas.drawRightString(width - 14 * mm, height - 20 * mm, public_number)
        if hide_prices:
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
        canvas.drawString(14 * mm, 9.5 * mm, 'Villas - Documento comercial gerado eletronicamente')
        canvas.drawRightString(width - 14 * mm, 9.5 * mm, f'Página {doc.page}')
        canvas.restoreState()
    return draw


def build_order_pdf(order: dict[str, Any], *, hide_prices: bool = False) -> bytes:
    buffer = BytesIO()
    styles = _styles()
    number = _order_number(order)
    title = 'Guia de preparação' if hide_prices else 'Nota de encomenda'
    frame = Frame(14 * mm, 18 * mm, A4[0] - 28 * mm, A4[1] - 53 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document = BaseDocTemplate(buffer, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=35 * mm, bottomMargin=18 * mm, title=f'Villas - {title} {number}', author='Villas', subject=title)
    document.addPageTemplates([PageTemplate(id='order', frames=[frame], onPage=_page_decorator(title, number, hide_prices))])

    status_label, status_color = _status(order)
    created_at = order.get('createdAt') or order.get('created_at') or order.get('criado_em')
    heading = Table([[
        [Paragraph(title, styles['title']), Paragraph('Documento de encomenda', styles['subtitle'])],
        [Paragraph('NÚMERO', styles['small']), Spacer(1, 1 * mm), Paragraph(_text(number), styles['body_bold'])],
        [Paragraph('DATA', styles['small']), Spacer(1, 1 * mm), Paragraph(_text(_date(created_at)), styles['body_bold'])],
        [Paragraph('ESTADO', styles['small']), Spacer(1, 1 * mm), Paragraph(_text(status_label), styles['body_bold'])],
    ]], colWidths=[71 * mm, 34 * mm, 43 * mm, 34 * mm])
    heading.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (0, 0), (0, 0), 5 * mm),
        ('LEFTPADDING', (1, 0), (-1, 0), 4 * mm), ('RIGHTPADDING', (1, 0), (-1, 0), 3 * mm),
        ('TOPPADDING', (1, 0), (-1, 0), 3 * mm), ('BOTTOMPADDING', (1, 0), (-1, 0), 3 * mm),
        ('BOX', (1, 0), (-1, 0), .6, LINE), ('LINEBEFORE', (2, 0), (-1, 0), .6, LINE),
        ('BACKGROUND', (3, 0), (3, 0), colors.Color(status_color.red, status_color.green, status_color.blue, alpha=.10)),
    ]))

    story: list[Any] = [heading, Spacer(1, 6 * mm), _customer_block(order, styles), Spacer(1, 7 * mm), Paragraph('ARTIGOS', styles['section']), _items_table(order, styles, hide_prices=hide_prices), Spacer(1, 6 * mm)]
    if hide_prices:
        summary = Table([
            [Paragraph('LINHAS', styles['small']), Paragraph('UNIDADES', styles['small'])],
            [Paragraph(_text(order.get('lines') or len(order.get('items') or [])), styles['total']), Paragraph(_text(order.get('units') or 0), styles['total'])],
        ], colWidths=[35 * mm, 35 * mm], hAlign='RIGHT')
    else:
        summary = Table([
            [Paragraph('Subtotal', styles['total_label']), Paragraph(_money(order.get('subtotal')), styles['total_label'])],
            [Paragraph('TOTAL', styles['total_label']), Paragraph(_money(order.get('total')), styles['total'])],
        ], colWidths=[35 * mm, 42 * mm], hAlign='RIGHT')
    summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PALE), ('BOX', (0, 0), (-1, -1), .6, LINE), ('LINEABOVE', (0, 1), (-1, 1), .6, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 3 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(summary)
    notes = order.get('notes') or order.get('notas') or ''
    if notes:
        notes_table = Table([[Paragraph(_text(notes).replace('\n', '<br/>'), styles['body'])]], colWidths=[182 * mm])
        notes_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), PALE), ('BOX', (0, 0), (-1, -1), .6, LINE),
            ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm), ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 4 * mm), ('BOTTOMPADDING', (0, 0), (-1, -1), 4 * mm),
        ]))
        story.extend([Spacer(1, 7 * mm), KeepTogether([Paragraph('NOTAS', styles['section']), notes_table])])
    story.extend([Spacer(1, 8 * mm), Paragraph('Obrigado pela sua encomenda.', styles['subtitle'])])
    document.build(story)
    return buffer.getvalue()
