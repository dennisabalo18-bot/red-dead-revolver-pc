"""The plain fonts of the game redrawn from a vector font, 4x and crisp.

letras.py enlarged the pages themselves, and enlarged blur stays blur. Here
every glyph of a page is drawn again from a Windows TrueType font at 4x,
stretched onto the box the original glyph's ink covers in its cell, so it
lands where the game expects it (the glyph table is unchanged). Only the
fonts in FONTS, whose look a system font matches; the western display
fonts stay the game's. A character the vector font lacks keeps the
original's sharpened cell; the controller buttons become keyboard icons
(letras.page_4x).

    python tools/letras_vector.py     writes previews to modding/texturas/letras_vector/
"""
import pathlib
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import botones_teclado  # noqa: E402
import letras  # noqa: E402
from extraer_texturas import GAME, dave_files  # noqa: E402
from fuentes_botones import glyph_table, page_of  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas" / "letras_vector"
WINFONTS = pathlib.Path(r"C:\Windows\Fonts")
SCALE = letras.SCALE
# (archive, glyph table entry) -> the TrueType font that matches it.
FONTS = {
    ("front.dat", 5): "pala.ttf",       # the serif of the legal text and menus
    ("front.dat", 184): "arialbd.ttf",  # the small bold sans
    ("front.dat", 29): "courbd.ttf",    # the typewriter
    ("front.dat", 34): "impact.ttf",    # the shop's tall condensed letters (and its buttons)
}
RENDER = 256                            # px the vector glyph is drawn at before fitting


def ink_box(a, cut=100):
    """(x0, y0, x1, y1) of the texels at least `cut` opaque, or None."""
    ys, xs = np.nonzero(a >= cut)
    if not len(xs):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


class Vector:
    def __init__(self, name):
        self.font = ImageFont.truetype(str(WINFONTS / name), RENDER)
        self.missing = self.mask("\U0010FFFD")

    def mask(self, ch):
        img = Image.new("L", (RENDER * 2, RENDER * 2), 0)
        ImageDraw.Draw(img).text((RENDER // 2, RENDER // 4), ch, 255, font=self.font)
        return img

    def glyph(self, ch, w, h):
        """The character's ink, w x h, or None when the font lacks it."""
        m = self.mask(ch)
        if m.tobytes() == self.missing.tobytes():
            return None
        box = m.getbbox()
        return m.crop(box).resize((w, h), Image.LANCZOS) if box else None


def vector_page(img, recs, ends, p, vec):
    """The page p at SCALE x: each glyph from the vector font, the rest of the
    page (and what the font lacks) letras.sharpen's, buttons as icons."""
    out = letras.sharpen(img)
    px = np.asarray(img)
    for i, (c, x, y, w, h, _) in enumerate(recs):
        if page_of(i, ends) != p or not (w and h):
            continue
        if c in botones_teclado.ICONS:
            X, Y, W, H = x * SCALE, y * SCALE, w * SCALE, h * SCALE
            out.paste((0, 0, 0, 0), (X, Y, X + W, Y + H))
            out.alpha_composite(botones_teclado.icon(botones_teclado.ICONS[c], W, H), (X, Y))
            continue
        cell = px[y:y + h, x:x + w]
        box = ink_box(cell[..., 3])
        if not box or c < 0x21:
            continue
        x0, y0, x1, y1 = box
        g = vec.glyph(chr(c), (x1 - x0) * SCALE, (y1 - y0) * SCALE)
        if g is None:
            continue
        # The glyph's colour: the original's most opaque texel.
        r, gg, b = cell.reshape(-1, 4)[cell[..., 3].argmax()][:3]
        X, Y = x * SCALE, y * SCALE
        out.paste((0, 0, 0, 0), (X, Y, X + w * SCALE, Y + h * SCALE))
        ink = Image.new("RGBA", g.size, (int(r), int(gg), int(b), 255))
        ink.putalpha(g)
        out.alpha_composite(ink, (X + x0 * SCALE, Y + y0 * SCALE))
    return out


def vector_pages(game=GAME, mods=letras.MODS):
    """{hash: (archive name, entry, page at SCALE x)} of the pages of FONTS."""
    out = {}
    for (arc_name, k), ttf in FONTS.items():
        src = next(game.rglob(arc_name))
        rel = src.relative_to(game)
        arc = mods / rel if (mods / rel).is_file() else src
        ents = dict(dave_files(arc))
        recs, ends = glyph_table(ents[k])
        vec = Vector(ttf)
        for p in range(len(ends)):
            d = letras.decode(ents[k + 1 + p])
            if not d:
                continue
            page = vector_page(d[2], recs, ends, p, vec)
            for h in letras.page_hashes(d[0], d[1], *d[2].size):
                out[h] = (str(rel), k + 1 + p, page)
    return out


def page_image(page):
    """A page's RGBA image, P8 or 16-colour (P4: 64-byte palette, two texels
    a byte, low nibble first). The pack only takes the P8 ones: how the game
    uploads a P4 page, and so its hash, is not known."""
    d = letras.decode(page)
    if d:
        return d[2]
    w, h = struct.unpack_from("<HH", page)
    if len(page) < 14 + 64 + w * h // 2:
        return Image.new("RGBA", (128, 128))
    pal = page[14:78]
    lut = [bytes((pal[i * 4 + 2], pal[i * 4 + 1], pal[i * 4], pal[i * 4 + 3])) for i in range(16)]
    px = b"".join(lut[b & 15] + lut[b >> 4] for b in page[78:78 + w * h // 2])
    return Image.frombytes("RGBA", (w, h), px)


def preview(arc_name, k, text, zoom=2.6):
    """The text as the game draws it (bilinear from the page, zoom x the
    page's size on screen): original above, vector below."""
    src = next(GAME.rglob(arc_name))
    rel = src.relative_to(GAME)
    arc = letras.MODS / rel if (letras.MODS / rel).is_file() else src
    ents = dict(dave_files(arc))
    recs, ends = glyph_table(ents[k])
    vec = Vector(FONTS[(arc_name, k)])
    pages = [page_image(ents[k + 1 + p]) for p in range(len(ends))]
    big = [vector_page(pg, recs, ends, p, vec) for p, pg in enumerate(pages)]
    by = {r[0]: (i, r) for i, r in enumerate(recs)}
    lh = max(r[4] for r in recs)
    base = max((-r[5] for r in recs if -2 * lh < r[5] < 0), default=lh)
    rows = []
    for src_pages, s in ((pages, 1), (big, SCALE)):
        width = int(sum(by[ord(ch)][1][3] + 1 if ord(ch) in by else lh // 3 for ch in text) * zoom) + 20
        line = Image.new("RGBA", (width, int((lh + base) * zoom) + 20), (0, 0, 0, 255))
        pen = 10.0
        for ch in text:
            if ord(ch) not in by:
                pen += lh // 3 * zoom
                continue
            i, (c, x, y, w, h, yoff) = by[ord(ch)]
            g = src_pages[page_of(i, ends)].crop((x * s, y * s, (x + w) * s, (y + h) * s))
            g = g.resize((max(1, round(w * zoom)), max(1, round(h * zoom))), Image.BILINEAR)
            line.alpha_composite(g, (int(pen), int(10 + (base + yoff if -2 * lh < yoff < 0 else lh - h) * zoom)))
            pen += (w + 1) * zoom
        rows.append(line)
    out = Image.new("RGBA", (max(r.width for r in rows), sum(r.height for r in rows)), (0, 0, 0, 255))
    out.alpha_composite(rows[0], (0, 0))
    out.alpha_composite(rows[1], (0, rows[0].height))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pages = vector_pages()
    done = set()
    for h, (rel, k, img) in pages.items():
        if id(img) not in done:
            done.add(id(img))
            img.save(OUT / f"{rel.replace(chr(92), '_')}_{k}_vector.png")
    preview("front.dat", 5, "Rockstar Games y el logotipo, Copyright 2004.").save(OUT / "comparar_serif.png")
    preview("front.dat", 184, "Presionar START para comenzar. Cargando partida.").save(OUT / "comparar_sans.png")
    preview("front.dat", 29, "RED DEAD REVOLVER 0123456789").save(OUT / "comparar_maquina.png")
    preview("front.dat", 34, "COMPRAR ARMAS $250 VENDER").save(OUT / "comparar_tienda.png")
    print(f"{len(done)} paginas en {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
