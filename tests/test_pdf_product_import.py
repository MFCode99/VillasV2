from io import BytesIO

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from app.pdf_product_import import parse_pdf_product_images


def _image(color: tuple[int, int, int]) -> BytesIO:
    output = BytesIO()
    Image.new('RGB', (120, 120), color).save(output, format='PNG')
    output.seek(0)
    return output


def test_pdf_product_images_are_paired_by_table_row_and_composited():
    output = BytesIO()
    canvas = Canvas(output, pagesize=(595, 842))
    canvas.drawString(153, 730, '110000 PRODUTO A 1,00 EUR')
    canvas.drawImage(ImageReader(_image((255, 0, 0))), 65, 720, 30, 15)
    canvas.drawImage(ImageReader(_image((0, 255, 0))), 65, 705, 30, 15)
    canvas.drawString(153, 670, '110001 PRODUTO B 2,00 EUR')
    canvas.drawImage(ImageReader(_image((0, 0, 255))), 65, 650, 30, 30)
    canvas.save()

    rows, issues = parse_pdf_product_images(output.getvalue())

    assert issues == []
    assert [row.ref for row in rows] == ['110000', '110001']
    assert rows[0].source_images == 2
    assert rows[1].source_images == 1
    assert rows[0].image_bytes.startswith(b'\x89PNG')
