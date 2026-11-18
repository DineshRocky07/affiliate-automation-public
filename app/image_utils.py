"""Shared Pillow helpers: safe font loading, emoji stripping, aspect-preserving fit."""
import re

from PIL import Image, ImageFont

_EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]")

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def load_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


def fit_image(image: Image.Image, width: int, height: int, background: str = "#ffffff") -> Image.Image:
    """Letterbox an image into a width x height canvas without distortion."""
    image = image.convert("RGB")
    ratio = min(width / image.width, height / image.height)
    new_size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
    resized = image.resize(new_size, Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (width, height), color=background)
    x = (width - new_size[0]) // 2
    y = (height - new_size[1]) // 2
    canvas.paste(resized, (x, y))
    return canvas
