from io import BytesIO

from PIL import Image, ImageDraw

from app.media import calculate_image_zoom, normalize_campaign_image_bytes


def _png_with_box(box: tuple[int, int, int, int]) -> bytes:
    image = Image.new('RGB', (200, 200), 'white')
    ImageDraw.Draw(image).rectangle(box, fill='black')
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def test_image_zoom_shrinks_tightly_cropped_images_for_breathing_room():
    assert calculate_image_zoom(_png_with_box((0, 0, 199, 199))) == 0.84


def test_image_zoom_enlarges_images_with_large_empty_margins():
    zoom = calculate_image_zoom(_png_with_box((50, 50, 149, 149)))
    assert 1.6 <= zoom <= 1.7


def test_campaign_artwork_uses_its_corner_colour_to_complete_three_to_one_banner():
    image = Image.new('RGB', (900, 600), 'white')
    ImageDraw.Draw(image).rectangle((180, 180, 720, 420), fill='black')
    source = BytesIO()
    image.save(source, format='PNG')

    normalized, mime, extension = normalize_campaign_image_bytes(source.getvalue())

    assert (mime, extension) == ('image/png', 'png')
    with Image.open(BytesIO(normalized)) as banner:
        assert banner.size == (1500, 500)
        assert banner.getpixel((0, 0))[:3] == (255, 255, 255)
        assert banner.getpixel((750, 250))[:3] == (0, 0, 0)


def test_campaign_photo_is_cropped_to_three_to_one_banner():
    image = Image.new('RGB', (500, 900))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
    source = BytesIO()
    image.save(source, format='JPEG', quality=90)

    normalized, mime, extension = normalize_campaign_image_bytes(source.getvalue())

    assert (mime, extension) == ('image/jpeg', 'jpg')
    with Image.open(BytesIO(normalized)) as banner:
        assert banner.size == (1500, 500)
