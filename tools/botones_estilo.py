"""The on-screen buttons in three styles, for the F2 row "Botones en pantalla".

Every font page that holds a controller button (fuentes_botones.py), and the
shop's 32x32 button images (texturas_pack.BUTTON_IMAGES), get six entries in
textures.pack, kind 3 (BUTTON): one per style -- keyboard and mouse, Xbox,
PlayStation -- with the improved textures (F6) on and off. The runtime looks
them up first (nv2a_tex_pack_find_button), keyed

    key = hash ^ (0x9E3779B97F4A7C15 * (1 + style * 2 + art))

with hash every key the page can have (letras.page_hashes, and its indices
alone for the faded-palette fallback). So F6 changes the letters, never the
buttons' style.

A font page's variant: the letters as the pack draws them with F6 on (the
TrueType redraw, letras_vector, for its four fonts) or else as the game
does (the page enlarged 4x, bilinear, as the GPU magnifies it), and in each
button cell:
  keyboard     botones_teclado.icon (as before)
  Xbox         the game's own glyph, from the disc's archive (the copy in
               modding/mods has keys painted over it), enlarged the same way
  PlayStation  cross, circle, square, triangle, L2, R2, drawn here
The keys come from the archive the game loads (modding/mods when it has the
rebuilt copy). Entries already in the pack are written again.

    python tools/botones_estilo.py [textures.pack]
    python tools/botones_estilo.py muestra     sheet of the three styles, to look at
"""
import pathlib
import struct
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import botones_teclado  # noqa: E402
import letras  # noqa: E402
import letras_vector  # noqa: E402
from extraer_texturas import GAME, dave_files, swizzled, tex_hash  # noqa: E402
from fuentes_botones import BUTTONS, fonts, page_of  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas"
KIND_BUTTON = 3
M64 = (1 << 64) - 1
S = 8
SCALE = letras.SCALE
STYLES = ("teclado", "xbox", "playstation")

# PlayStation shapes by the Xbox button in the same place.
PS_SHAPE = {0xBA: "cross", 0xBE: "circle", 0xBD: "square", 0xBC: "triangle", 0x2020: "L2", 0x2021: "R2"}
PS_COLOUR = {"cross": (124, 178, 255), "circle": (255, 102, 102), "square": (240, 150, 205),
             "triangle": (84, 212, 160)}
XB_COLOUR = {"A": (110, 200, 80), "B": (230, 70, 60), "X": (70, 140, 235), "Y": (240, 200, 50)}
BODY, RIM, WHITE = (28, 26, 24, 255), (205, 200, 190, 255), (250, 248, 240, 255)


def key(h, style, art):
    return (h ^ (0x9E3779B97F4A7C15 * (1 + style * 2 + art) & M64)) & M64


def _disc(W, H):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = min(W, H) // 2 - S // 2
    cx, cy = W // 2, H // 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BODY, outline=RIM, width=int(1.4 * S))
    return im, d, cx, cy, r


def ps_button(shape, w, h):
    """A round PlayStation-style button with its shape, w x h; L2/R2 as a
    trigger tab with the label."""
    W, H = w * S, h * S
    if shape in ("L2", "R2"):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        r = min(W, H) // 3
        d.rounded_rectangle([S // 2, S, W - S // 2 - 1, H - S // 2 - 1], r, fill=BODY, outline=RIM,
                            width=int(1.4 * S))
        f = botones_teclado.font(int(H * 0.5))
        box = d.textbbox((0, 0), shape, font=f)
        d.text(((W - (box[2] - box[0])) / 2 - box[0], (H - (box[3] - box[1])) / 2 - box[1] + S // 3),
               shape, font=f, fill=WHITE)
        return im.resize((w, h), Image.LANCZOS)
    im, d, cx, cy, r = _disc(W, H)
    c, t, k = PS_COLOUR[shape], max(S, int(r * 0.17)), r * 0.5
    if shape == "cross":
        d.line([(cx - k, cy - k), (cx + k, cy + k)], fill=c, width=t)
        d.line([(cx - k, cy + k), (cx + k, cy - k)], fill=c, width=t)
    elif shape == "circle":
        d.ellipse([cx - k, cy - k, cx + k, cy + k], outline=c, width=t)
    elif shape == "square":
        k *= 0.9
        d.rectangle([cx - k, cy - k, cx + k, cy + k], outline=c, width=t)
    else:
        d.polygon([(cx, cy - k * 1.05), (cx + k * 1.1, cy + k * 0.8), (cx - k * 1.1, cy + k * 0.8)],
                  outline=c, width=t)
    return im.resize((w, h), Image.LANCZOS)


def xbox_button(letter, w, h):
    """A round Xbox-style button with its coloured letter (the shop's images)."""
    im, d, cx, cy, r = _disc(w * S, h * S)
    f = botones_teclado.font(int(r * 1.25))
    box = d.textbbox((0, 0), letter, font=f)
    d.text((cx - (box[2] - box[0]) / 2 - box[0], cy - (box[3] - box[1]) / 2 - box[1]),
           letter, font=f, fill=XB_COLOUR[letter] + (255,))
    return im.resize((w, h), Image.LANCZOS)


def fit(icon_fn, w, h):
    """icon_fn(side, side) centred in a w x h cell (wide trigger cells)."""
    side = min(w, h)
    if w == h:
        return icon_fn(w, h)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if w > h * 3 // 2:
        tw = min(w, h * 3 // 2)
        im.paste(icon_fn(tw, h), ((w - tw) // 2, 0))
    else:
        im.paste(icon_fn(side, side), ((w - side) // 2, (h - side) // 2))
    return im


def plain(img):
    """The page as the game draws it, 4x: bilinear, as the GPU magnifies the
    original (letras.sharpen's 4x was the look the user turned down)."""
    return img.resize((img.width * SCALE, img.height * SCALE), Image.BILINEAR)


def cell_icon(style, c, orig_cell, art, W, H):
    if style == 0:
        return botones_teclado.icon(botones_teclado.ICONS[c], W, H)
    if style == 1:
        return plain(orig_cell)
    shape = PS_SHAPE[c]
    return fit(lambda a, b: ps_button(shape, a, b), W, H)


def page_variant(base, orig, cells, style, art):
    out = base.copy()
    for c, x, y, w, h in cells:
        X, Y, W, H = x * SCALE, y * SCALE, w * SCALE, h * SCALE
        out.paste((0, 0, 0, 0), (X, Y, X + W, Y + H))
        ic = cell_icon(style, c, orig.crop((x, y, x + w, y + h)), art, W, H)
        if ic.size != (W, H):
            ic = ic.resize((W, H), Image.LANCZOS)
        out.alpha_composite(ic, (X, Y))
    return out


def button_pages():
    """[(keys, {(style, art): page})] for every distinct font page with a button."""
    out, seen = [], set()
    vec_cache = {}
    for src in sorted(GAME.rglob("*.dat")):
        if "stream" in src.name.lower() or "bank" in src.name.lower():
            continue
        rel = src.relative_to(GAME)
        arc = letras.MODS / rel if (letras.MODS / rel).is_file() else src
        loaded = None
        for k, recs, ends, pages in fonts(arc):
            loaded = loaded or dict(dave_files(arc))
            orig_ents = dict(dave_files(src)) if arc != src else loaded
            for p, ent in enumerate(pages):
                cells = [(c, x, y, w, h) for i, (c, x, y, w, h, _) in enumerate(recs)
                         if c in BUTTONS and page_of(i, ends) == p and w and h]
                d = cells and letras.decode(loaded.get(ent, b""))
                o = d and letras.decode(orig_ents.get(ent, b""))
                if not d or not o or d[0] + d[1] in seen:
                    continue
                seen.add(d[0] + d[1])
                img, (pw, ph) = d[2], d[2].size
                fk = (src.name, k)
                if fk in letras_vector.FONTS:
                    if fk not in vec_cache:
                        vec_cache[fk] = letras_vector.Vector(letras_vector.FONTS[fk])
                    art_base = letras_vector.vector_page(img, recs, ends, p, vec_cache[fk])
                else:
                    art_base = plain(img)          # no pack letters for it: as the game
                bases = {0: plain(img), 1: art_base}
                keys = list(letras.page_hashes(d[0], d[1], pw, ph))
                pow2 = pw & (pw - 1) == 0 and ph & (ph - 1) == 0
                keys += [tex_hash(t) for t in ((d[0], swizzled(d[0], pw, ph)) if pow2 else (d[0],))]
                var = {(s, a): page_variant(bases[a], o[2], cells, s, a) for s in range(3) for a in (0, 1)}
                out.append((sorted(set(keys)), var, f"{rel}#{ent}"))
    return out


def shop_images():
    """[(keys, {(style, art): image})] for the shop's 32x32 buttons, at 128x128."""
    import texturas_pack
    letter = {"space": "A", "R": "Y", "E": "X", "C": "B"}
    xb_char = {"A": 0xBA, "Y": 0xBC, "X": 0xBD, "B": 0xBE}
    out = []
    for h, kb in texturas_pack.BUTTON_IMAGES.items():
        L = letter[kb]
        imgs = (botones_teclado.icon(kb, 128, 128), xbox_button(L, 128, 128),
                ps_button(PS_SHAPE[xb_char[L]], 128, 128))
        out.append(([h], {(s, a): imgs[s] for s in range(3) for a in (0, 1)}, f"tienda {L}"))
    return out


def _blobs(alpha):
    """Bounding boxes of the 8-connected blobs of alpha > 40."""
    import numpy as np
    m = alpha > 40
    h, w = m.shape
    seen = np.zeros_like(m)
    out = []
    for y0, x0 in zip(*np.nonzero(m)):
        if seen[y0, x0]:
            continue
        seen[y0, x0] = True
        st, bx = [(y0, x0)], [x0, y0, x0, y0]
        while st:
            y, x = st.pop()
            bx = [min(bx[0], x), min(bx[1], y), max(bx[2], x), max(bx[3], y)]
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        st.append((ny, nx))
        out.append((bx[0], bx[1], bx[2] + 1, bx[3] + 1))
    return out


# The dump's font pages with round buttons drawn in, checked by eye
# (modding/texturas/dump): the Xbox ones (the diary's "Entrar"/"Opciones"
# uses 7ACEF9DD) and the PlayStation 2 ones the game also carries.
DUMPED_BUTTON_PAGES = {
    0x7ACEF9DD0C1DD730: "xbox", 0x79FDC7EA054E2A39: "xbox",
    0xD46B274BA63AC7B1: "ps", 0x2769F5D34A552E9A: "ps", 0xA6C14E4962D3F1F6: "ps",
    0xAF53E2C229534915: "ps", 0xB8A0F684C56194DF: "ps",
}


def _button_cells(img, family):
    """[(letter, x, y, w, h)] of the round coloured buttons drawn in a font
    page (family "xbox": A/Y/X/B; "ps": cross, triangle, square, circle,
    named by the Xbox button in their place): each coloured symbol (its
    pieces joined), the dark disc round it sized by its area but never past
    halfway to the next button, one size for the page."""
    import colorsys
    import numpy as np
    px = np.asarray(img.convert("RGBA")).astype(float)
    a = px[..., 3]
    rgb = px[..., :3] / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    vivid = (a > 128) & (sat > 0.28) & (mx > 0.25)
    h_, w_ = a.shape
    sym = []
    for x0, y0, x1, y1 in _blobs(np.where(vivid, 255, 0)):
        n = vivid[y0:y1, x0:x1].sum()
        if n < 6:
            continue
        hues = [colorsys.rgb_to_hsv(*c)[0] * 360 for c in rgb[y0:y1, x0:x1][vivid[y0:y1, x0:x1]]]
        sym.append([float(np.median(hues)), (x0 + x1 - 1) / 2, (y0 + y1 - 1) / 2, n])
    # pieces of one symbol: same colour, close together
    merged = []
    for hue, cx, cy, n in sorted(sym, key=lambda t: -t[3]):
        for m in merged:
            if min(abs(hue - m[0]), 360 - abs(hue - m[0])) < 30 and (cx - m[1]) ** 2 + (cy - m[2]) ** 2 < 16 ** 2:
                break
        else:
            merged.append([hue, cx, cy, n])
    merged = [m for m in merged if m[3] >= 12]
    if len(merged) < 2:
        return []
    rs = []
    for hue, cx, cy, _ in merged:
        others = [((cx - o[1]) ** 2 + (cy - o[2]) ** 2) ** 0.5 for o in merged if o[1:3] != [cx, cy]]
        lim = min([20.0] + [d / 2 + 0.5 for d in others])
        X0, Y0 = max(0, int(cx - lim)), max(0, int(cy - lim))
        X1, Y1 = min(w_, int(cx + lim) + 1), min(h_, int(cy + lim) + 1)
        yy, xx = np.mgrid[Y0:Y1, X0:X1]
        near = (xx - cx) ** 2 + (yy - cy) ** 2 <= lim ** 2
        disc = (a[Y0:Y1, X0:X1] > 128) & ((mx[Y0:Y1, X0:X1] < 0.5) | vivid[Y0:Y1, X0:X1]) & near
        rs.append(min(lim, float(np.sqrt(disc.sum() / np.pi)) + 1.5))
    r = int(round(float(np.median(rs))))
    cells = []
    for hue, cx, cy, _ in merged:
        if hue < 20 or hue >= 345:
            L = "B"                                        # red B, or the circle
        elif hue < 75:
            L = "Y"                                        # yellow Y
        elif hue < 175:
            L = "A" if family == "xbox" else "Y"           # green A, or the triangle
        elif hue < 255:
            L = "X" if family == "xbox" else "A"           # blue X, or the cross
        else:
            L = "X"                                        # the pink square
        x, y = int(round(cx - r)), int(round(cy - r))
        cells.append((L, max(0, x), max(0, y), 2 * r + 1, 2 * r + 1))
    return cells


def dumped_pages():
    """[(keys, {(style, art): page})] for the font pages of the dump with
    round buttons drawn in (the diary's "Entrar"/"Opciones"): not in any
    archive's glyph table, they went into the pack as art (Upscayl) and kept
    the Xbox look in every style. F6 on: the pack's upscale with the cells
    replaced; off: the original, 4x bilinear. Xbox style on the Xbox page
    keeps the game's own glossy button."""
    import re
    dump, ups = ROOT / "dump", ROOT / "mejoradas"
    up = {p.stem: p for p in ups.rglob("*.png")}
    kb = {"A": "space", "Y": "R", "X": "E", "B": "C"}
    ps = {"A": "cross", "Y": "triangle", "X": "square", "B": "circle"}
    out = []
    for p in sorted(dump.glob("*.png")):
        m = re.match(r"([0-9A-F]{16})_(\d+)x(\d+)$", p.stem)
        if not m or int(m.group(1), 16) not in DUMPED_BUTTON_PAGES or p.stem not in up:
            continue
        orig = Image.open(p).convert("RGBA")
        family = DUMPED_BUTTON_PAGES[int(m.group(1), 16)]
        cells = _button_cells(orig, family)
        if not cells:
            continue
        big =Image.open(up[p.stem]).convert("RGBA").resize(
            (orig.width * SCALE, orig.height * SCALE), Image.LANCZOS)
        bases = {0: plain(orig), 1: big}
        is_xbox = family == "xbox"
        var = {}
        for a in (0, 1):
            for s in range(3):
                page = bases[a].copy()
                for L, x, y, w, h in cells:
                    X, Y, W, H = x * SCALE, y * SCALE, w * SCALE, h * SCALE
                    if s == 1 and is_xbox:
                        continue                           # the game's own Xbox button
                    page.paste((0, 0, 0, 0), (X, Y, X + W, Y + H))
                    ic = (botones_teclado.icon(kb[L], W, H) if s == 0 else
                          xbox_button(L, W, H) if s == 1 else ps_button(ps[L], W, H))
                    page.alpha_composite(ic, (X, Y))
                var[(s, a)] = page
        out.append(([int(m.group(1), 16)], var, f"volcado {p.stem} " + "".join(c[0] for c in cells)))
    return out


def write(pack, items):
    from texturas_pack import mip_chain
    with open(pack, "r+b") as f:
        magic, ver, count, scale, index_off, extra = struct.unpack("<4sIIIQQ", f.read(32))
        if magic != b"XRTP" or ver not in (1, 2):
            print(f"{pack} no es un pack de texturas")
            return 1
        f.seek(index_off)
        index = {e[0]: e for e in (struct.unpack("<QIIIIQ", f.read(32)) for _ in range(count))}
        f.seek(0, 2)
        n = 0
        for keys, var, _ in items:
            for (s, a), img in var.items():
                off = f.tell()
                levels = mip_chain(img)
                for lv in levels:
                    f.write(lv.tobytes("raw", "BGRA"))
                for h in keys:
                    kk = key(h, s, a)
                    index[kk] = (kk, img.size[0], img.size[1], len(levels), KIND_BUTTON, off)
                    n += 1
        new_off = f.tell()
        for h in sorted(index):
            f.write(struct.pack("<QIIIIQ", *index[h]))
        f.seek(0)
        f.write(struct.pack("<4sIIIQII", b"XRTP", 2, len(index), scale,
                            new_off, extra & 0xFFFFFFFF if ver == 2 else 0, 0))
    print(f"{len(items)} paginas/imagenes de botones, {n} claves (3 estilos x F6 si/no) en {pack}")
    return 0


def sample(items, out):
    """The button cells of the first font page and the shop images, one row a style."""
    rows = []
    for s in range(3):
        tiles = []
        for keys, var, name in items:
            if name.startswith("tienda"):
                tiles.append(var[(s, 1)].resize((96, 96), Image.LANCZOS))
        rows.append(tiles)
    W = max(len(r) for r in rows) * 104 + 8
    sheet = Image.new("RGBA", (W, 3 * 104 + 8), (60, 50, 40, 255))
    for j, r in enumerate(rows):
        for i, t in enumerate(r):
            sheet.alpha_composite(t, (8 + i * 104, 8 + j * 104))
    sheet.save(out)
    page = next(v for k, v, n in items if not n.startswith("tienda"))
    strip = Image.new("RGBA", (page[(0, 1)].width * 3, page[(0, 1)].height), (60, 50, 40, 255))
    for s in range(3):
        strip.alpha_composite(page[(s, 1)], (s * page[(0, 1)].width, 0))
    strip.save(out.with_name(out.stem + "_pagina.png"))
    print(f"muestra en {out}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "volcado":
        # only the dump's font pages with buttons drawn in (dumped_pages)
        items = dumped_pages()
        for _, _, name in items:
            print(name)
        if len(sys.argv) > 2 and sys.argv[2] == "muestra":
            for keys, var, name in items:
                w, h = var[(0, 1)].size
                strip = Image.new("RGBA", (w * 3, h * 2), (70, 70, 90, 255))
                for s in range(3):
                    for a in (0, 1):
                        strip.alpha_composite(var[(s, a)], (s * w, (1 - a) * h))
                strip.save(ROOT / f"botones_volcado_{keys[0]:016X}.png")
            return 0
        return write(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack", items)
    if len(sys.argv) > 1 and sys.argv[1] == "muestra":
        items = shop_images() + button_pages()[:1]
        sample(items, ROOT / "botones_estilos_muestra.png")
        return 0
    pack = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "textures.pack"
    items = shop_images() + button_pages()
    return write(pack, items)


if __name__ == "__main__":
    sys.exit(main())
