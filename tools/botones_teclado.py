"""Keyboard and mouse icons in place of the Xbox buttons in the game's text.

The prompts ("Press <A> to continue") are characters of the game's fonts
(fuentes_botones.py): U+BA A, U+BC Y, U+BD X, U+BE B, U+2020 left trigger,
U+2021 right trigger. Every font page holding one gets, in that glyph's
cell, the key the PC layout puts there (rdr-apex/src/main.c):

    A -> Space   Y -> R (reload)   X -> E (use)   B -> C
    left trigger -> right mouse button   right trigger -> left mouse button

A page is P8: the icons' colours go into palette slots no pixel outside the
cells uses. Every archive with such a page is rebuilt whole into the mods
folder (RECOMP_MODS_DIR) byte for byte, the changed pages written over
their own (rebuild), compressed again as the originals were. The
disc's copy is not touched; "quitar" deletes the rebuilt archives.

The game copies each level archive to its hard-disk cache (Z:, the
runtime's <LOCALAPPDATA>/xboxrecomp/Cache) the first time and loads it from
there after, so botones_teclado.bat empties the cache's level folders
(with rd: a Store Python sees a virtualized LOCALAPPDATA and cannot): the
next load copies them again, through the mods folder.

    python tools/botones_teclado.py [game_dir] [mods_dir] [quitar]
"""
import hashlib
import os
import pathlib
import shutil
import struct
import sys
import zlib

from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extraer_texturas import dave_files, GAME  # noqa: E402
from fuentes_botones import PAGE, PAGE4, fonts, page_of  # noqa: E402

MODS = pathlib.Path(__file__).resolve().parent.parent / "modding" / "mods"
ICONS = {0xBA: "space", 0xBC: "R", 0xBD: "E", 0xBE: "C", 0x2020: "mouse_r", 0x2021: "mouse_l"}
S = 8                                    # supersampling
FACE, EDGE, TEXT, HOT = (34, 30, 26, 255), (232, 222, 200, 255), (255, 250, 240, 255), (214, 84, 44, 255)
FONT = None


def font(px):
    for name in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def keycap(w, h, label):
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = min(w, h) * S // 5
    d.rounded_rectangle([S // 2, S, w * S - S // 2 - 1, h * S - S // 2 - 1], r, fill=FACE, outline=EDGE,
                        width=int(1.6 * S))
    if label == "space":
        y, x0, x1, t = int(h * S * 0.64), int(w * S * 0.26), int(w * S * 0.74), int(1.6 * S)
        d.rectangle([x0, y, x1, y + t], fill=TEXT)
        d.rectangle([x0, y - int(h * S * 0.18), x0 + t, y + t], fill=TEXT)
        d.rectangle([x1 - t, y - int(h * S * 0.18), x1, y + t], fill=TEXT)
    else:
        f = font(int(h * S * 0.62))
        box = d.textbbox((0, 0), label, font=f)
        d.text(((w * S - (box[2] - box[0])) / 2 - box[0], (h * S - (box[3] - box[1])) / 2 - box[1] + S // 2),
               label, font=f, fill=TEXT)
    return im.resize((w, h), Image.LANCZOS)


def mouse(w, h, right):
    W, H = w * S, h * S
    body = Image.new("L", (W, H), 0)
    ImageDraw.Draw(body).rounded_rectangle([S, S, W - S - 1, H - S - 1], int(W * 0.46), fill=255)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (W, H), FACE), (0, 0), body)
    hot = Image.new("L", (W, H), 0)
    split = int(H * 0.42)
    ImageDraw.Draw(hot).rectangle([W // 2 if right else 0, 0, W if right else W // 2, split], fill=255)
    im.paste(Image.new("RGBA", (W, H), HOT), (0, 0), ImageChops.multiply(hot, body))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([S, S, W - S - 1, H - S - 1], int(W * 0.46), outline=EDGE, width=int(1.6 * S))
    d.line([(W // 2, S), (W // 2, split)], fill=EDGE, width=int(1.4 * S))
    d.line([(S, split), (W - S, split)], fill=EDGE, width=int(1.4 * S))
    return im.resize((w, h), Image.LANCZOS)


def icon(kind, w, h):
    if kind.startswith("mouse"):
        # A wide trigger cell ("L-1" bars): the mouse keeps its shape, centred.
        mw = min(w, max(6, h * 13 // 20))
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        im.paste(mouse(mw, h, kind == "mouse_r"), ((w - mw) // 2, 0))
        return im
    if w > h * 3 // 2:                   # a wide key cell: a keycap, centred
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        im.paste(keycap(h * 6 // 5, h, kind), ((w - h * 6 // 5) // 2, 0))
        return im
    return keycap(w, h, kind)


def repaint(page, cells):
    """The P8 or P4 page entry with icons in cells [(x, y, w, h, kind)]."""
    w, h = struct.unpack_from("<HH", page)
    if len(page) == PAGE4:
        return repaint4(page, cells, w, h)
    pal = bytearray(page[14:14 + 1024])
    px = bytearray(page[14 + 1024:14 + 1024 + w * h])
    inside = bytearray(w * h)
    for x, y, cw, ch, _ in cells:
        for yy in range(y, min(y + ch, h)):
            for xx in range(x, min(x + cw, w)):
                inside[yy * w + xx] = 1
    used = {px[i] for i in range(w * h) if not inside[i]}
    clear = next((i for i in range(256) if pal[i * 4 + 3] == 0), None)
    free = [i for i in range(256) if i not in used and i != clear]
    if len(free) < 8:
        raise ValueError(f"solo {len(free)} colores libres en la paleta")
    # All the page's icons quantized together into the free slots.
    tiles = [(x, y, icon(kind, cw, ch)) for x, y, cw, ch, kind in cells]
    strip = Image.new("RGBA", (sum(t[2].width for t in tiles), max(t[2].height for t in tiles)), (0, 0, 0, 0))
    ox = 0
    for _, _, t in tiles:
        strip.paste(t, (ox, 0))
        ox += t.width
    q = strip.quantize(colors=min(len(free), 96), method=Image.Quantize.FASTOCTREE)
    qp = q.getpalette(rawmode="RGBA")
    for j in range(min(len(free), len(qp) // 4)):
        r, g, b, a = qp[j * 4:j * 4 + 4]
        pal[free[j] * 4:free[j] * 4 + 4] = bytes((b, g, r, a))      # BGRA
    qd = q.load()
    sd = strip.load()
    ox = 0
    for x, y, t in tiles:
        for yy in range(t.height):
            for xx in range(t.width):
                a = sd[ox + xx, yy][3]
                i = clear if (a < 8 and clear is not None) else free[qd[ox + xx, yy]]
                if 0 <= x + xx < w and 0 <= y + yy < h:
                    px[(y + yy) * w + x + xx] = i
        ox += t.width
    return page[:14] + bytes(pal) + bytes(px) + page[14 + 1024 + w * h:]


def repaint4(page, cells, w, h):
    """repaint for a 16-colour page (64-byte BGRA palette, two texels a byte,
    low nibble first). Its few free slots get the icons' main colours; with
    fewer than 3 free, the icons take the nearest of the page's own colours
    (a white font: white keys the game tints like the letters)."""
    pal = bytearray(page[14:78])
    raw = page[78:78 + w * h // 2]
    px = bytearray(n for b in raw for n in (b & 15, b >> 4))
    inside = bytearray(w * h)
    for x, y, cw, ch, _ in cells:
        for yy in range(y, min(y + ch, h)):
            for xx in range(x, min(x + cw, w)):
                inside[yy * w + xx] = 1
    used = {px[i] for i in range(w * h) if not inside[i]}
    clear = next((i for i in range(16) if pal[i * 4 + 3] == 0), None)
    free = [i for i in range(16) if i not in used and i != clear]
    tiles = [(x, y, icon(kind, cw, ch)) for x, y, cw, ch, kind in cells]
    if len(free) >= 3:
        strip = Image.new("RGBA", (sum(t[2].width for t in tiles), max(t[2].height for t in tiles)), (0, 0, 0, 0))
        ox = 0
        for _, _, t in tiles:
            strip.paste(t, (ox, 0))
            ox += t.width
        qp = strip.quantize(colors=len(free), method=Image.Quantize.FASTOCTREE).getpalette(rawmode="RGBA")
        for j in range(min(len(free), len(qp) // 4)):
            r, g, b, a = qp[j * 4:j * 4 + 4]
            pal[free[j] * 4:free[j] * 4 + 4] = bytes((b, g, r, a))
    cols = [(pal[i * 4 + 2], pal[i * 4 + 1], pal[i * 4], pal[i * 4 + 3]) for i in range(16)]

    def nearest(c):
        if c[3] < 8 and clear is not None:
            return clear
        return min(range(16), key=lambda i: sum((a - b) ** 2 for a, b in zip(c, cols[i])))
    memo = {}
    for x, y, t in tiles:
        d = t.load()
        for yy in range(t.height):
            for xx in range(t.width):
                c = d[xx, yy]
                if c not in memo:
                    memo[c] = nearest(c)
                if 0 <= x + xx < w and 0 <= y + yy < h:
                    px[(y + yy) * w + x + xx] = memo[c]
    out = bytes(px[i] | px[i + 1] << 4 for i in range(0, w * h, 2))
    return page[:78] + out + page[78 + w * h // 2:]


def rebuild(src, dst, repl):
    """dst = src byte for byte, with entries {index: new bytes} (uncompressed)
    written over their own: same offset when the new data fits before the
    next entry, else at the end on a 0x800 boundary. The file stays a whole
    number of 0x800 sectors, as on the disc (the game reads whole sectors: a
    file packed tighter hung it at the title screen)."""
    with open(src, "rb") as f:
        magic, count, dsz, nsz = struct.unpack("<4sIII", f.read(16))
        f.seek(0x800)
        d = f.read(dsz)
    ents = [list(struct.unpack_from("<IIII", d, k * 16)) for k in range(count)]
    total = src.stat().st_size
    offs = sorted({e[1] for e in ents} | {total})
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    shutil.copyfile(src, tmp)
    moved = 0
    with open(tmp, "r+b") as o:
        for k, new in repl.items():
            no, off, size, packed = ents[k]
            if packed != size:
                c = zlib.compressobj(9, zlib.DEFLATED, -15)
                blob = c.compress(new) + c.flush()
            else:
                blob = new
            room = next(x for x in offs if x > off) - off
            if len(blob) <= room:
                o.seek(off)
                o.write(blob + b"\x00" * max(0, packed - len(blob)))
                pos = off
            else:
                o.seek(0, 2)
                pos = (o.tell() + 0x7FF) & ~0x7FF
                o.write(b"\x00" * (pos - o.tell()) + blob)
                moved += 1
            end = o.seek(0, 2)
            o.write(b"\x00" * (((end + 0x7FF) & ~0x7FF) - end))
            o.seek(0x800 + k * 16 + 4)
            o.write(struct.pack("<III", pos, len(new), len(blob)))
    os.replace(tmp, dst)
    return moved


def main():
    args = [a for a in sys.argv[1:] if a.lower() != "quitar"]
    quitar = len(args) != len(sys.argv) - 1
    game = pathlib.Path(args[0]) if args and args[0] else GAME
    mods = pathlib.Path(args[1]) if len(args) > 1 and args[1] else MODS
    done = {}                                # page md5 -> repainted page
    n = 0
    for src in sorted(game.rglob("*.dat")):
        if "stream" in src.name or "bank" in src.name:
            continue
        rel = src.relative_to(game)
        dst = mods / rel
        found = fonts(src)
        if quitar:
            if found and dst.exists():
                dst.unlink()
                print(f"quitado {rel}")
            continue
        if not found:
            continue
        ents = dict(dave_files(src))
        repl = {}
        for k, recs, ends, pages in found:
            cells = {}
            for i, r in enumerate(recs):
                if r[0] in ICONS:
                    cells.setdefault(page_of(i, ends), []).append((r[1], r[2], r[3], r[4], ICONS[r[0]]))
            for p, cs in cells.items():
                e = pages[p]
                if len(ents.get(e, b"")) not in (PAGE, PAGE4):
                    continue                     # an odd page (the shop's B): not known
                key = hashlib.md5(ents[e] + repr(cs).encode()).hexdigest()
                if key not in done:
                    done[key] = repaint(ents[e], cs)
                repl[e] = done[key]
        moved = rebuild(src, dst, repl)
        n += 1
        print(f"{rel}: {len(repl)} páginas con teclas{f' ({moved} al final)' if moved else ''} -> {dst}")
    if not quitar:
        print(f"Listo: {n} archivos en {mods}. Para volver a los botones de Xbox: botones_teclado.bat quitar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
