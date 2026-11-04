"""The serif pages the game builds in memory, redrawn from a vector font.

Some text (menus, loading screens, "Cargando, no apague su Xbox") is drawn
from P8 pages that are in no archive: the game packs the glyphs it needs
into a 256x128 or 256x256 page of its own, in code point order (the 94
printable ASCII characters, then the others it uses, rising). A dump with
P8 (F2 "Volcar texturas", dump/p8_indices.txt) holds them. Here each page
is cut into glyphs (their ink, row by row), each glyph named by its place
(ASCII) or by the best look-alike among the rest (in order), and drawn
again from the TrueType at 4x on its ink box, as letras_vector.py does with
the archive fonts. Only pages the TrueType fits (SCORE): the western display
fonts stay the game's.

    python tools/letras_atlas.py           previews in modding/texturas/letras_atlas/
    python tools/letras_atlas.py agregar   adds them to textures.pack (font, both keys)
"""
import pathlib
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import letras  # noqa: E402
from letras_vector import Vector, ink_box  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas"
DUMP = ROOT / "dump"
OUT = ROOT / "letras_atlas"
SCALE = letras.SCALE
TTF = "pala.ttf"            # the serif letras_vector.py gives front.dat #5
SCORE = 0.55                # mean likeness of the letters and digits, 0..1
EXTRA = [chr(c) for c in range(0xA1, 0x100) if c != 0xAD] + list(
    "ŒœŠšŸŽžƒˆ˜–—‘’‚"
    "“”„†‡•…‰‹›€™")
EXTRA.sort()
SPANISH = set("áéíóúñÑ¡¿üÁÉÍÓÚ«»")


def components(m):
    """Bounding boxes [x0, y0, x1, y1] of the 8-connected blobs of m."""
    h, w = m.shape
    lab = np.zeros((h, w), bool)
    boxes = []
    for y, x in zip(*np.nonzero(m)):
        if lab[y, x]:
            continue
        lab[y, x] = True
        st, x0, x1, y0, y1 = [(y, x)], x, x, y, y
        while st:
            cy, cx = st.pop()
            x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
            for ny in (cy - 1, cy, cy + 1):
                for nx in (cx - 1, cx, cx + 1):
                    if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = True
                        st.append((ny, nx))
        boxes.append([x0, y0, x1 + 1, y1 + 1])
    return boxes


def glyph_boxes(alpha, cut=20):
    """The page's glyphs in reading order: blobs grouped into rows (by
    vertical overlap), and in a row into glyphs (by horizontal overlap:
    the dot of an i, the two marks of a quote)."""
    rows = []
    for b in sorted(components(alpha >= cut), key=lambda b: (b[1] + b[3]) / 2):
        for r in rows:
            if b[1] < r[1] and b[3] > r[0]:
                r[2].append(b)
                r[0], r[1] = min(r[0], b[1]), max(r[1], b[3])
                break
        else:
            rows.append([b[1], b[3], [b]])
    merged = []
    for r in sorted(rows):
        if merged and r[0] < merged[-1][1]:
            merged[-1][2] += r[2]
            merged[-1][1] = max(merged[-1][1], r[1])
        else:
            merged.append(r)
    out = []
    for _, _, bs in merged:
        row = []
        for b in sorted(bs):
            if row and b[0] < row[-1][2]:
                p = row[-1]
                row[-1] = [min(p[0], b[0]), min(p[1], b[1]), max(p[2], b[2]), max(p[3], b[3])]
            else:
                row.append(b)
        out += row
    return out


def likeness(cell, g):
    a = cell.astype(float) / 255
    return 1 - np.abs(a - g).mean() / max(1e-3, (a + g).mean() / 2)


def name_glyphs(alpha, boxes, vec):
    """[(box, char)] and the mean likeness of the letters and digits, or
    None when the page does not start with the 94 ASCII glyphs."""
    if len(boxes) < 94:
        return None, 0
    def fit(b, ch):
        g = vec.glyph(ch, b[2] - b[0], b[3] - b[1])
        return -1.0 if g is None else likeness(alpha[b[1]:b[3], b[0]:b[2]], np.asarray(g, float) / 255)
    named = [(b, chr(0x21 + i)) for i, b in enumerate(boxes[:94])]
    score = np.mean([fit(b, c) for b, c in named if c.isalnum()])
    rest = boxes[94:]
    if rest:
        # The others rise in code point: the best rising choice (DP).
        n, m = len(rest), len(EXTRA)
        if n > m:
            return None, 0
        # tiny accents look alike: the game's text is Spanish, prefer its letters
        s = np.array([[fit(b, c) + 0.1 * (c in SPANISH) for c in EXTRA] for b in rest])
        best = np.full((n + 1, m + 1), -1e9)
        best[0, :] = 0
        for i in range(1, n + 1):
            for j in range(i, m + 1):
                best[i, j] = max(best[i, j - 1], best[i - 1, j - 1] + s[i - 1, j - 1])
        j, pick = m, []
        for i in range(n, 0, -1):
            while best[i, j] == best[i, j - 1]:
                j -= 1
            pick.append(j - 1)
            j -= 1
        named += [(b, EXTRA[k]) for b, k in zip(rest, reversed(pick))]
    return named, score


def redraw(img, named, vec):
    """img at SCALE x: each named glyph from the vector font on its ink box,
    in the colour of the original's most opaque texel; a glyph the font
    lacks keeps letras.sharpen's."""
    out = letras.sharpen(img)
    px = np.asarray(img)
    for (x0, y0, x1, y1), ch in named:
        cell = px[y0:y1, x0:x1]
        box = ink_box(cell[..., 3])
        if not box:
            continue
        bx0, by0, bx1, by1 = box
        g = vec.glyph(ch, (bx1 - bx0) * SCALE, (by1 - by0) * SCALE)
        if g is None:
            continue
        r, gg, b = cell.reshape(-1, 4)[cell[..., 3].argmax()][:3]
        out.paste((0, 0, 0, 0), (x0 * SCALE, y0 * SCALE, x1 * SCALE, y1 * SCALE))
        ink = Image.new("RGBA", g.size, (int(r), int(gg), int(b), 255))
        ink.putalpha(g)
        out.alpha_composite(ink, ((x0 + bx0) * SCALE, (y0 + by0) * SCALE))
    return out


def atlas_pages(ttf=TTF):
    """[(palette key, indices key, original, page at SCALE x, named, score)] of
    the dumped P8 pages the TrueType fits."""
    vec = Vector(ttf)
    out = []
    for line in (DUMP / "p8_indices.txt").read_text().splitlines():
        h, ih, size = line.split()
        img = Image.open(DUMP / f"{h}_{size}.png").convert("RGBA")
        alpha = np.asarray(img)[..., 3]
        named, score = name_glyphs(alpha, glyph_boxes(alpha), vec)
        if named and score >= SCORE:
            out.append((int(h, 16), int(ih, 16), img, redraw(img, named, vec), named, score))
    return out


def preview(img, big, named, text, zoom=2.6):
    """The text as the game draws it (bilinear): original above, redrawn below."""
    by = {c: b for b, c in named}
    lh = max(b[3] - b[1] for b in by.values())
    rows = []
    for src, s in ((img, 1), (big, SCALE)):
        line = Image.new("RGBA", (int(len(text) * lh * zoom * 0.7) + 20, int(lh * zoom) + 20), (0, 0, 0, 255))
        pen = 10.0
        for ch in text:
            b = by.get(ch)
            if not b:
                pen += lh * zoom / 3
                continue
            x0, y0, x1, y1 = b
            g = src.crop((x0 * s, y0 * s, x1 * s, y1 * s))
            g = g.resize((max(1, round((x1 - x0) * zoom)), max(1, round((y1 - y0) * zoom))), Image.BILINEAR)
            # glyphs are top-cut ink: sit lowercase and caps on one baseline
            base = by["x"][3] - by["x"][1]
            top = {",": 0.8, ".": 0.8, "-": 0.45, "'": 0.0, '"': 0.0}.get(ch)
            if top is not None:
                y = top * lh * 0.7
            elif ch in "gjpqy":
                y = lh * 0.7 - base
            else:
                y = lh * 0.7 - (y1 - y0)
            line.alpha_composite(g, (int(pen), int(10 + y * zoom)))
            pen += (x1 - x0 + 1) * zoom
        rows.append(line)
    out = Image.new("RGBA", (rows[0].width, rows[0].height * 2), (0, 0, 0, 255))
    out.alpha_composite(rows[0], (0, 0))
    out.alpha_composite(rows[1], (0, rows[0].height))
    return out


def add_to_pack(out):
    from texturas_pack import KIND_FONT, mip_chain
    pages = atlas_pages()
    with open(out, "r+b") as f:
        magic, ver, count, scale, index_off, extra = struct.unpack("<4sIIIQQ", f.read(32))
        if magic != b"XRTP" or ver not in (1, 2):
            print(f"{out} no es un pack de texturas")
            return 1
        f.seek(index_off)
        index = {e[0]: e for e in (struct.unpack("<QIIIIQ", f.read(32)) for _ in range(count))}
        f.seek(0, 2)
        added = 0
        for h, ih, _, big, _, _ in pages:
            off = f.tell()
            levels = mip_chain(big)
            for lv in levels:
                f.write(lv.tobytes("raw", "BGRA"))
            for k in (h, ih):
                index[k] = (k, big.width, big.height, len(levels), KIND_FONT, off)
                added += 1
        new_off = f.tell()
        for k in sorted(index):
            f.write(struct.pack("<QIIIIQ", *index[k]))
        f.seek(0)
        f.write(struct.pack("<4sIIIQII", b"XRTP", 2, len(index), scale,
                            new_off, extra & 0xFFFFFFFF if ver == 2 else 0, 0))
    print(f"{len(pages)} paginas, {added} claves de letras agregadas a {out}")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() == "agregar":
        return add_to_pack(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack")
    OUT.mkdir(parents=True, exist_ok=True)
    for h, ih, img, big, named, score in atlas_pages():
        extra = "".join(c for _, c in named[94:])
        print(f"{h:016X} {img.width}x{img.height} {len(named)} letras, parecido {score:.2f}, otras: {extra}")
        big.save(OUT / f"{h:016X}_x4.png")
        text = "Cargando, no apague su Xbox. Guardar partida?"
        preview(img, big, named, text).save(OUT / f"{h:016X}_comparar.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
