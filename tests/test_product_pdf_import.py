from io import BytesIO

from reportlab.pdfgen.canvas import Canvas

from app.product_import import parse_product_file


def _supplier_pdf() -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=(595, 842))
    canvas.drawString(35, 800, 'FOTO Nº REFERÊNCIA DESCRIÇÃO EAN CAIXA INTERIOR CAIXA EXTERIOR PREÇO DE VENDA')
    canvas.drawString(35, 760, '110000 23172-CARIOCA - ESTOJO ESCOLAR NEON - 6 24 6,08 EUR')
    canvas.drawString(35, 730, '110292 43091 CARIOCA - 6 LAPIS HB GRAFITE 8003511430917 12 144 0,70 EUR')
    canvas.drawString(35, 700, '110500 40427/03 - CARIOCA - TEMPERA AMARELA - - 12 1,75 EUR')
    canvas.save()
    return output.getvalue()


def test_pdf_product_table_extracts_references_names_and_box_quantities():
    parsed = parse_product_file(_supplier_pdf(), 'catalogo.pdf', 'villas', category_label='Escolar')

    assert parsed['source_type'] == 'pdf'
    assert parsed['errors'] == []
    assert len(parsed['rows']) == 3
    first = parsed['rows'][0]
    assert first['ref'] == '110000'
    assert first['name'] == '23172 - CARIOCA - ESTOJO ESCOLAR NEON'
    assert first['case_inner'] == 6
    assert first['case_outer'] == 24
    assert first['quantity_step'] == 6
    assert first['quick_quantities'] == [6, 24]
    assert first['price'] == '6.080'
    assert first['category_label'] == 'Escolar'
    assert parsed['rows'][1]['ref'] == '110292'
    assert parsed['rows'][1]['name'].startswith('43091 - CARIOCA')
    assert parsed['rows'][2]['ref'] == '110500'
    assert parsed['rows'][2]['case_inner'] is None
    assert parsed['rows'][2]['quantity_step'] == 12


def test_pdf_product_table_detects_ecovalue_layout_and_reversed_box_columns():
    output = BytesIO()
    canvas = Canvas(output, pagesize=(595, 842))
    canvas.drawString(20, 800, 'Foto Nº Referência Descrição Família EAN UN/CX Exterior UN/CX Interior PREÇO ECOVALOR Preço de Venda + Ecovalor')
    canvas.drawString(20, 760, '49820 TOSHIBA High Power LR03-AAA Bl 4 ALCALINA 4904530592607 48 12 0,89 EUR 0,023 EUR 0,913 EUR')
    canvas.drawString(20, 730, '49923 TOSHIBA TNH-6GAE (AA 2600mAh x 2 pcs)RECARREGÁVEL4904530594724 100 10 4,25 EUR 0,012 EUR 4,262 EUR')
    canvas.drawString(20, 700, '49941 TOSHIBA Lanterna Mini LED KFL-403M BPLANTERNA 4904530630774 100 10 3,60 EUR - 3,600 EUR')
    canvas.save()

    parsed = parse_product_file(output.getvalue(), 'toshiba.pdf', 'interpilhas', category_label='Pilhas')

    assert parsed['errors'] == []
    assert len(parsed['rows']) == 3
    first = parsed['rows'][0]
    assert first['ref'] == '49820'
    assert first['name'] == 'TOSHIBA High Power LR03-AAA Bl 4'
    assert first['brand'] == 'TOSHIBA'
    assert first['family'] == 'ALCALINA'
    assert first['ean'] == '4904530592607'
    assert first['case_outer'] == 48
    assert first['case_inner'] == 12
    assert first['quantity_step'] == 12
    assert first['price_base'] == '0.890'
    assert first['eco_value'] == '0.023'
    assert first['price'] == '0.913'
    assert parsed['rows'][1]['ref'] == '49923'
    assert parsed['rows'][1]['family'] == 'RECARREGÁVEL'
    assert parsed['rows'][1]['ean'] == '4904530594724'
    assert parsed['rows'][1]['price'] == '4.262'
    assert parsed['rows'][2]['name'].endswith('BP')
    assert parsed['rows'][2]['family'] == 'LANTERNA'
    assert parsed['rows'][2]['eco_value'] == '0.000'
