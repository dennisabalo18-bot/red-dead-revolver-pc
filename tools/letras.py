"""The pages of every font of the game, from its archives, 4x and sharp.

A font is a glyph table and its 128x128 P8 pages right after it in the
same archive (fuentes_botones.py). The port never dumps them (P8, linear),
so texturas_pack.py takes them from here: each page decoded through its
own palette, enlarged 4x with a crisp edge (not Upscayl, which invents
strokes on text), the controller buttons drawn as keyboard and mouse
icons at that size (botones_teclado.py's), keyed by the hash the backend gives it: the indices'
hash with the palette's folded in (tex_hash_pal in nv2a_pb_d3d11.c).
An archive rebuilt in modding/mods (botones_teclado.bat) is read from
there, since that is the copy the game loads.

    python tools/letras.py      writes the pages to modding/texturas/letras/ to look at
"""
import pathlib
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extraer_texturas import dave_files, swizzled, tex_hash, GAME  # noqa: E402
from fuentes_botones import glyph_table, page_of  # noqa: E402
import botones_teclado  # noqa: E402

MODS = pathlib.Path(__file__).resolve().parent.parent / "modding" / "mods"
OUT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas" / "letras"
SCALE = 4
EDGE = 2.0          # alpha contrast around 50%: the 4x edge as sharp as the original's


def page_hashes(idx, pal, w, h):
    """Every hash the page can have: its indices as in the file or swizzled
    (the game may swizzle them on load), the palette register saying 32 to
    256 entries."""
    pow2 = w & (w - 1) == 0 and h & (h - 1) == 0          # only those swizzle
    return [tex_hash(t) ^ (tex_hash(pal[:n * 4]) * 31 & (2**64 - 1))
            for t in ((idx, swizzled(idx, w, h)) if pow2 else (idx,))
            for n in (256, 128, 64, 32)]


def decode(page):
    """(indices, palette bytes, RGBA image) of a P8 page entry, or None."""
    w, h = struct.unpack_from("<HH", page)
    if not (w and h) or len(page) < 14 + 1024 + w * h:
        return None
    pal = page[14:14 + 1024]
    idx = page[14 + 1024:14 + 1024 + w * h]
    lut = [bytes((pal[i * 4 + 2], pal[i * 4 + 1], pal[i * 4], pal[i * 4 + 3])) for i in range(256)]
    return idx, pal, Image.frombytes("RGBA", (w, h), b"".join(lut[i] for i in idx))


def sharpen(img):
    """img at SCALE x: colour smooth (premultiplied, no dark fringe), alpha with a crisp edge."""
    size = (img.size[0] * SCALE, img.size[1] * SCALE)
    px = np.asarray(img, dtype=np.float32)
    a = px[..., 3:] / 255.0
    big = [Image.fromarray(c).resize(size, Image.BICUBIC)
           for c in [px[..., i] * a[..., 0] for i in range(3)] + [px[..., 3]]]
    big = np.stack([np.asarray(c, dtype=np.float32) for c in big], axis=-1)
    av = np.clip(big[..., 3:], 0, 255)
    rgb = np.where(av > 0, big[..., :3] * 255.0 / np.maximum(av, 1e-3), 0)   # un-premultiply
    na = (av - 127.5) * EDGE + 127.5
    return Image.fromarray(np.clip(np.concatenate([rgb, na], axis=-1), 0, 255).astype(np.uint8), "RGBA")


def page_4x(img, cells):
    """The page sharpened, each button cell [(x, y, w, h, kind)] a keyboard icon."""
    out = sharpen(img)
    for x, y, w, h, kind in cells:
        x, y, w, h = x * SCALE, y * SCALE, w * SCALE, h * SCALE
        out.paste((0, 0, 0, 0), (x, y, x + w, y + h))
        out.alpha_composite(botones_teclado.icon(kind, w, h), (x, y))
    return out


def font_pages(game=GAME, mods=MODS):
    """{hash: (archive name, entry, RGBA page, button cells)} of every font page, once each."""
    seen, out = set(), {}
    for src in sorted(game.rglob("*.dat")):
        if "stream" in src.name.lower() or "bank" in src.name.lower():
            continue
        rel = src.relative_to(game)
        arc = mods / rel if (mods / rel).is_file() else src
        ents = None
        for k, b in dave_files(arc):
            t = glyph_table(b)
            if not t:
                continue
            ents = ents or dict(dave_files(arc))
            recs, ends = t
            for p in range(len(ends)):
                page = ents.get(k + 1 + p)
                d = page and decode(page)
                if not d or d[0] + d[1] in seen:
                    continue
                seen.add(d[0] + d[1])
                cells = [(x, y, w, hh, botones_teclado.ICONS[c]) for i, (c, x, y, w, hh, _) in enumerate(recs)
                         if c in botones_teclado.ICONS and page_of(i, ends) == p and w and hh]
                for h in page_hashes(d[0], d[1], *d[2].size):
                    out[h] = (str(rel), k + 1 + p, d[2], cells)
    return out


def main():
    pages = font_pages()
    OUT.mkdir(parents=True, exist_ok=True)
    done = set()
    for h, (rel, k, img, cells) in pages.items():
        if id(img) in done:
            continue
        done.add(id(img))
        name = f"{rel.replace('/', '_').replace(chr(92), '_')}_{k}"
        img.save(OUT / f"{name}_original.png")
        page_4x(img, cells).save(OUT / f"{name}_x{SCALE}.png")
    print(f"{len(done)} paginas de letras en {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
