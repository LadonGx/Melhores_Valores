"""
Gera packaging/icon.ico: o mesmo selo "MV" da barra lateral do app
(quadrado arredondado na cor --color-primary, texto branco).

Uso: python packaging/make_icon.py   (requer Pillow; o .ico gerado é versionado)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PRIMARY = "#6366f1"  # --color-primary (apps/web/src/styles/global.css)
SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT = Path(__file__).with_name("icon.ico")
FONT_CANDIDATES = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"]


def _font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=PRIMARY)
    font = _font(int(size * 0.46))
    box = draw.textbbox((0, 0), "MV", font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), "MV", font=font, fill="white")
    return img


if __name__ == "__main__":
    render(256).save(OUT, sizes=[(s, s) for s in SIZES])
    print("gerado:", OUT)
