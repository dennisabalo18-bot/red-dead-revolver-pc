"""The icons of the game and of Configuración.exe, from the cover the user gave
(assets/iconos/portada_x4.png, Upscayl ultrasharp 4x of it).

    python tools/iconos.py      writes assets/iconos/{juego,config}_{cuadrado,redondo}.ico
                                and muestra.png (all four, several sizes)

Square: the top of the cover (logo and face), rounded corners. Round: the
same in a disc with a dark rim. Configuración: the same picture, a little
darker, with a cream gear in the lower right corner.
"""
import math
import pathlib

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

DIR = pathlib.Path(__file__).resolve().parent.parent / "assets" / "iconos"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
BIG = 1024
CREAM, INK = (238, 226, 196, 255), (34, 26, 20, 255)


def crop():
    im = Image.open(DIR / "portada_x4.png").convert("RGBA")
    w = im.width
    top = int(im.height * 0.035)
    return im.crop((0, top, w, top + w)).resize((BIG, BIG), Image.LANCZOS)


def square(img):
    mask = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, BIG - 1, BIG - 1], BIG // 7, fill=255)
    out = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    d = ImageDraw.Draw(out)
    d.rounded_rectangle([6, 6, BIG - 7, BIG - 7], BIG // 7 - 6, outline=(20, 16, 12, 230), width=14)
    return out


def round_(img):
    mask = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, BIG - 1, BIG - 1], fill=255)
    out = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    ImageDraw.Draw(out).ellipse([7, 7, BIG - 8, BIG - 8], outline=(20, 16, 12, 235), width=16)
    return out


def gear(size):
    """A cream gear with a dark outline, size x size, transparent around."""
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = s / 2
    teeth, r_out, r_in, r_hole = 9, s * 0.47, s * 0.36, s * 0.14
    pts = []
    for i in range(teeth * 4):
        a = 2 * math.pi * i / (teeth * 4) - math.pi / 2
        r = r_out if i % 4 in (1, 2) else r_in
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(pts, fill=(0, 0, 0, 170))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(s * 0.03)), (int(s * 0.02), int(s * 0.03)))
    d.polygon(pts, fill=CREAM, outline=INK, width=int(s * 0.035))
    d.ellipse([cx - r_in * 0.62, cy - r_in * 0.62, cx + r_in * 0.62, cy + r_in * 0.62], outline=INK,
              width=int(s * 0.03))
    d.ellipse([cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole], fill=(0, 0, 0, 0), outline=INK,
              width=int(s * 0.035))
    hole = Image.new("L", (s, s), 255)
    ImageDraw.Draw(hole).ellipse([cx - r_hole + s * 0.017, cy - r_hole + s * 0.017,
                                  cx + r_hole - s * 0.017, cy + r_hole - s * 0.017], fill=0)
    im.putalpha(Image.fromarray(__import__("numpy").minimum(__import__("numpy").asarray(im.getchannel("A")),
                                                             __import__("numpy").asarray(hole))))
    return im.resize((size, size), Image.LANCZOS)


def config(img, shape):
    base = ImageEnhance.Brightness(img).enhance(0.72)
    out = shape(base)
    g = gear(int(BIG * 0.5))
    out.alpha_composite(g, (BIG - g.width - int(BIG * 0.03), BIG - g.height - int(BIG * 0.03)))
    return out


def save_ico(img, path):
    img.save(path, format="ICO", sizes=SIZES)


def main():
    img = crop()
    icons = {
        "juego_cuadrado": square(img), "juego_redondo": round_(img),
        "config_cuadrado": config(img, square), "config_redondo": config(img, round_),
    }
    for name, im in icons.items():
        save_ico(im, DIR / f"{name}.ico")
        im.resize((256, 256), Image.LANCZOS).save(DIR / f"{name}.png")
    sheet = Image.new("RGBA", (4 * 280, 280 + 70), (238, 238, 238, 255))
    dark = Image.new("RGBA", (4 * 280, 70), (40, 40, 44, 255))
    for i, (name, im) in enumerate(icons.items()):
        sheet.alpha_composite(im.resize((256, 256), Image.LANCZOS), (i * 280 + 12, 12))
        x = i * 280 + 20
        for sz in (48, 32, 16):
            sheet.alpha_composite(im.resize((sz, sz), Image.LANCZOS), (x, 280 + 4))
            dark.alpha_composite(im.resize((sz, sz), Image.LANCZOS), (x + 140, 4))
            x += sz + 12
    sheet.alpha_composite(dark.crop((0, 0, 4 * 280, 70)), (0, 280))
    sheet.save(DIR / "muestra.png")
    print("iconos en", DIR)


if __name__ == "__main__":
    main()
