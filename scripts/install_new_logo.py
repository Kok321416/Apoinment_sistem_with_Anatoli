"""Install Flux logo into site brand pack. Run: python scripts/install_new_logo.py"""
from __future__ import annotations

import base64
import io
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(
    r"C:\Users\Artem\.cursor\projects\c-Users-Artem-PycharmProjects-Apoinment-sistem-with-Anatoli"
    r"\assets\c__Users_Artem_AppData_Roaming_Cursor_User_workspaceStorage_"
    r"000235c813c6832f7496d3aeb7a32586_images_flux2_klein_hiwo3yg4-b3e9ee90-f30d-4e13-8995-6b8599476550.png"
)
IMG = ROOT / "app" / "static" / "img" / "brand"
SVG = ROOT / "app" / "static" / "svg"
BRAND_SVG = SVG / "brand"
FONT = Path(r"C:\Windows\Fonts\segoeuib.ttf")
FONT_REG = Path(r"C:\Windows\Fonts\segoeui.ttf")
WHITE = (255, 255, 255, 255)
INK = (10, 10, 10, 255)
MUTED = (115, 115, 115, 255)


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT if bold else FONT_REG), size)


def trim_to_square(raw: Image.Image) -> Image.Image:
    bg = Image.new("RGBA", raw.size, WHITE)
    composited = Image.alpha_composite(bg, raw.convert("RGBA"))
    rgb = composited.convert("RGB")
    pixels = rgb.load()
    w, h = rgb.size
    minx, miny, maxx, maxy = w, h, 0, 0
    thresh = 248
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            if r < thresh or g < thresh or b < thresh:
                found = True
                minx = min(minx, x)
                miny = min(miny, y)
                maxx = max(maxx, x)
                maxy = max(maxy, y)
    if not found:
        return composited
    pad = 8
    minx = max(0, minx - pad)
    miny = max(0, miny - pad)
    maxx = min(w - 1, maxx + pad)
    maxy = min(h - 1, maxy + pad)
    cropped = composited.crop((minx, miny, maxx + 1, maxy + 1))
    cw, ch = cropped.size
    side = max(cw, ch)
    square = Image.new("RGBA", (side, side), WHITE)
    square.paste(cropped, ((side - cw) // 2, (side - ch) // 2), cropped)
    return square


def resize_mark(square: Image.Image, size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), WHITE)
    inset = max(2, int(size * 0.04))
    mark = square.resize((size - 2 * inset, size - 2 * inset), Image.Resampling.LANCZOS)
    canvas.paste(mark, (inset, inset), mark)
    return canvas


def save_png(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    print("wrote", path.relative_to(ROOT), img.size)


def save_horizontal(square: Image.Image, path: Path, height: int) -> None:
    mark_h = int(height * 0.92)
    pad = int(height * 0.08)
    f = font(int(height * 0.42), True)
    text = "Все клиенты здесь"
    tw = int(f.getlength(text))
    mark = resize_mark(square, mark_h)
    width = pad + mark_h + int(height * 0.18) + tw + pad
    img = Image.new("RGBA", (width, height), WHITE)
    img.paste(mark, (pad, (height - mark_h) // 2), mark)
    draw = ImageDraw.Draw(img)
    ty = (height - int(height * 0.42)) // 2 - int(height * 0.02)
    draw.text((pad + mark_h + int(height * 0.18), ty), text, font=f, fill=INK)
    save_png(img, path)


def svg_embed(png: Image.Image, out: Path, view: int) -> None:
    buf = io.BytesIO()
    png.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view} {view}" '
        f'role="img" aria-hidden="true">\n'
        f'  <image href="data:image/png;base64,{b64}" width="{view}" height="{view}" '
        f'preserveAspectRatio="xMidYMid meet"/>\n'
        f"</svg>\n",
        encoding="utf-8",
    )
    print("wrote", out.relative_to(ROOT), f"({out.stat().st_size} bytes)")


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Source logo not found: {SRC}")
    square = trim_to_square(Image.open(SRC))
    master = resize_mark(square, 1024)
    save_png(master, IMG / "logo-mark-master.png")
    save_png(master, IMG / "logo-square-1024.png")
    for name in ("logo-square-512.png", "service-icon-512.png", "vse-klienty-service-512.png"):
        save_png(resize_mark(square, 512), IMG / name)
    for h, name in (
        (128, "logo-horizontal-128.png"),
        (512, "logo-horizontal-512.png"),
        (1024, "logo-horizontal-1024.png"),
    ):
        save_horizontal(square, IMG / name, h)

    og = Image.new("RGBA", (1200, 630), (250, 250, 250, 255))
    draw = ImageDraw.Draw(og)
    draw.rounded_rectangle([24, 24, 1175, 605], radius=28, outline=(229, 229, 229, 255), width=2)
    mark = resize_mark(square, 220)
    og.paste(mark, (90, (630 - 220) // 2), mark)
    draw.text((360, 230), "Все клиенты здесь", font=font(54, True), fill=INK)
    draw.text(
        (360, 310),
        "Онлайн-запись для специалистов и клиентов",
        font=font(28, False),
        fill=MUTED,
    )
    save_png(og, IMG / "og-banner-1200x630.png")

    save_png(resize_mark(square, 512), SVG / "telegram-bot-avatar.png")
    save_png(resize_mark(square, 512), IMG / "telegram-channel-512.png")

    mark512 = resize_mark(square, 512)
    mark128 = resize_mark(square, 128)
    svg_embed(mark512, SVG / "logo.svg", 512)
    svg_embed(mark512, SVG / "logo-mark.svg", 512)
    svg_embed(mark128, SVG / "favicon.svg", 128)
    svg_embed(mark512, BRAND_SVG / "logo-square.svg", 512)
    svg_embed(mark512, BRAND_SVG / "service-icon-512.svg", 512)

    horiz = Image.open(IMG / "logo-horizontal-512.png").convert("RGBA")
    buf = io.BytesIO()
    horiz.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    hw, hh = horiz.size
    (BRAND_SVG / "logo-horizontal.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {hw} {hh}" '
        f'role="img" aria-hidden="true">\n'
        f'  <image href="data:image/png;base64,{b64}" width="{hw}" height="{hh}"/>\n'
        f"</svg>\n",
        encoding="utf-8",
    )
    print("wrote brand/logo-horizontal.svg")

    # Lightweight OG SVG with mark reference (PNG companion is canonical)
    og_svg_mark = resize_mark(square, 256)
    buf = io.BytesIO()
    og_svg_mark.save(buf, format="PNG", optimize=True)
    b64m = base64.b64encode(buf.getvalue()).decode("ascii")
    (BRAND_SVG / "og-banner.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" fill="none" '
        'aria-hidden="true">\n'
        '  <rect width="1200" height="630" fill="#FAFAFA"/>\n'
        '  <rect x="24" y="24" width="1152" height="582" rx="28" stroke="#E5E5E5" '
        'stroke-width="2"/>\n'
        f'  <image href="data:image/png;base64,{b64m}" x="90" y="187" width="256" height="256"/>\n'
        '  <text x="390" y="300" font-family="Segoe UI, Arial, sans-serif" font-size="54" '
        'font-weight="700" fill="#0A0A0A">Все клиенты здесь</text>\n'
        '  <text x="390" y="360" font-family="Segoe UI, Arial, sans-serif" font-size="28" '
        'fill="#737373">Онлайн-запись для специалистов и клиентов</text>\n'
        "</svg>\n",
        encoding="utf-8",
    )
    print("wrote brand/og-banner.svg")

    shutil.copy2(SRC, IMG / "logo-source-flux.png")

    # Compact embeds for <img> fallbacks + header-sized PNGs
    for size, name in ((160, "logo-mark-160.png"), (64, "logo-mark-64.png")):
        save_png(resize_mark(square, size), IMG / name)
    svg_embed(resize_mark(square, 160), SVG / "logo.svg", 160)
    svg_embed(resize_mark(square, 160), SVG / "logo-mark.svg", 160)
    svg_embed(resize_mark(square, 64), SVG / "favicon.svg", 64)
    svg_embed(resize_mark(square, 256), BRAND_SVG / "logo-square.svg", 256)
    svg_embed(resize_mark(square, 256), BRAND_SVG / "service-icon-512.svg", 256)

    # Android launcher icons
    res = ROOT / "mobile" / "android" / "app" / "src" / "main" / "res"
    dens_sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    fg_sizes = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
    for dens, s in dens_sizes.items():
        folder = res / f"mipmap-{dens}"
        if not folder.exists():
            continue
        icon = resize_mark(square, s)
        for name in ("ic_launcher.png", "ic_launcher_round.png"):
            save_png(icon, folder / name)
    for dens, s in fg_sizes.items():
        path = res / f"mipmap-{dens}" / "ic_launcher_foreground.png"
        if not path.exists():
            continue
        canvas = Image.new("RGBA", (s, s), WHITE)
        inner = int(s * 0.66)
        mark = resize_mark(square, inner)
        canvas.paste(mark, ((s - inner) // 2, (s - inner) // 2), mark)
        save_png(canvas, path)

    print("done")


if __name__ == "__main__":
    main()
