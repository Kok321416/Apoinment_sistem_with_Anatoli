"""Generate brand PNG assets (light theme) from the calendar mark.
Run: python scripts/generate_brand_pngs.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "static" / "img" / "brand"
FONT = Path(r"C:\Windows\Fonts\segoeuib.ttf")
FONT_REG = Path(r"C:\Windows\Fonts\segoeui.ttf")
INK = (10, 10, 10, 255)
MUTED = (115, 115, 115, 255)
SECONDARY = (82, 82, 82, 255)
BG = (250, 250, 250, 255)
WHITE = (255, 255, 255, 255)
GRID = (229, 229, 229, 255)
BORDER = (218, 218, 218, 255)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT if bold else FONT_REG
    return ImageFont.truetype(str(path), size)


def draw_mark(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """Draw framed calendar mark into a square of `size` px at (x,y)."""
    s = size / 64.0

    def sx(v: float) -> int:
        return int(round(x + v * s))

    def sy(v: float) -> int:
        return int(round(y + v * s))

    def sw(v: float) -> int:
        return max(1, int(round(v * s)))

    # outer frame
    draw.rounded_rectangle(
        [sx(6), sy(6), sx(58), sy(58)],
        radius=sw(14),
        outline=INK,
        width=sw(3),
    )
    # calendar body
    draw.rounded_rectangle(
        [sx(16), sy(18), sx(48), sy(46)],
        radius=sw(4),
        outline=INK,
        width=sw(2.5),
    )
    # header line + rings
    draw.line([(sx(16), sy(28)), (sx(48), sy(28))], fill=INK, width=sw(2.5))
    for px in (24, 40):
        draw.line([(sx(px), sy(14)), (sx(px), sy(22))], fill=INK, width=sw(2.5))
    r = max(1, sw(2.2))
    for cx, cy in ((24, 36), (32, 36), (40, 36), (24, 44), (32, 44), (40, 44)):
        draw.ellipse([sx(cx) - r, sy(cy) - r, sx(cx) + r, sy(cy) + r], fill=INK)


def save_square(path: Path, size: int) -> None:
    img = Image.new("RGBA", (size, size), WHITE)
    draw = ImageDraw.Draw(img)
    pad = int(size * 0.06)
    draw_mark(draw, pad, pad, size - 2 * pad)
    img.save(path, "PNG", optimize=True)


def save_horizontal(path: Path, height: int) -> None:
    # width scales with text
    mark = int(height * 0.92)
    pad = int(height * 0.08)
    f = font(int(height * 0.42), bold=True)
    text = "Все клиенты здесь"
    tw = int(f.getlength(text))
    width = pad + mark + int(height * 0.18) + tw + pad
    img = Image.new("RGBA", (width, height), WHITE)
    draw = ImageDraw.Draw(img)
    my = (height - mark) // 2
    draw_mark(draw, pad, my, mark)
    tx = pad + mark + int(height * 0.18)
    ty = (height - int(height * 0.42)) // 2 - int(height * 0.05)
    draw.text((tx, ty), text, font=f, fill=INK)
    img.save(path, "PNG", optimize=True)


def save_og(path: Path) -> None:
    w, h = 1200, 630
    img = Image.new("RGBA", (w, h), BG)
    draw = ImageDraw.Draw(img)
    # grid
    for gy in range(0, h, 105):
        draw.line([(0, gy), (w, gy)], fill=GRID, width=1)
    for gx in range(0, w, 150):
        draw.line([(gx, 0), (gx, h)], fill=GRID, width=1)
    # card
    card = (80, 80, 1120, 550)
    draw.rounded_rectangle(card, radius=24, fill=WHITE, outline=GRID, width=2)
    mark = 170
    mx = (w - mark) // 2
    my = 150
    draw_mark(draw, mx, my, mark)
    title = font(44, bold=True)
    sub = font(24, bold=False)
    t = "Все клиенты здесь"
    s = "Онлайн-запись и кабинет специалиста"
    tw = title.getlength(t)
    sw = sub.getlength(s)
    draw.text(((w - tw) / 2, 360), t, font=title, fill=INK)
    draw.text(((w - sw) / 2, 420), s, font=sub, fill=MUTED)
    img.save(path, "PNG", optimize=True)


def save_empty(path: Path) -> None:
    w, h = 720, 560
    img = Image.new("RGBA", (w, h), BG)
    draw = ImageDraw.Draw(img)
    for gy in range(0, h, 80):
        draw.line([(0, gy), (w, gy)], fill=GRID, width=1)
    for gx in range(0, w, 80):
        draw.line([(gx, 0), (gx, h)], fill=GRID, width=1)
    draw.rounded_rectangle([120, 90, 600, 450], radius=20, fill=WHITE, outline=BORDER, width=2)
    mark = 96
    draw_mark(draw, (w - mark) // 2, 140, mark)
    title = font(28, bold=True)
    body = font(16)
    hint = font(14)
    lines = [
        (title, "Все клиенты здесь", INK, 260),
        (body, "Кабинет специалиста. Выберите раздел слева.", SECONDARY, 300),
        (hint, "Подсказка: начните с «Календари».", MUTED, 330),
    ]
    for fnt, text, color, y in lines:
        tw = fnt.getlength(text)
        draw.text(((w - tw) / 2, y), text, font=fnt, fill=color)
    img.save(path, "PNG", optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    save_square(OUT / "logo-square-512.png", 512)
    save_square(OUT / "logo-square-1024.png", 1024)
    save_horizontal(OUT / "logo-horizontal-512.png", 512)
    save_horizontal(OUT / "logo-horizontal-1024.png", 1024)
    # also useful smaller horizontal for headers
    save_horizontal(OUT / "logo-horizontal-128.png", 128)
    save_og(OUT / "og-banner-1200x630.png")
    save_empty(OUT / "cabinet-empty-light.png")
    # keep PWA raster twin
    save_square(OUT / "service-icon-512.png", 512)
    print("Wrote brand PNGs to", OUT)


if __name__ == "__main__":
    main()
