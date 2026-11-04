"""The game's fonts and their controller-button glyphs.

A font is a glyph table entry (float scale 1.02, then the glyph count at
0x2C, 10-byte records from 0x30: u32 character, u8 x, y, w, h, s16 y
offset; then u32 page count and each page's cumulative glyph count) and
its pages, the 128x128 P8 entries right after it in the same archive.
The buttons are characters: U+BA A, U+BC Y, U+BD X, U+BE B, U+2020 left
trigger, U+2021 right trigger.

    python tools/fuentes_botones.py      lists every font with buttons
"""
import hashlib
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extraer_texturas import dave_files, GAME  # noqa: E402

BUTTONS = {0xBA: "A", 0xBC: "Y", 0xBD: "X", 0xBE: "B", 0x2020: "LT", 0x2021: "RT"}
PAGE = 14 + 1024 + 128 * 128          # header, palette, 128x128 indices
PAGE4 = 14 + 64 + 128 * 128 // 2      # the 16-colour kind: two texels a byte, low nibble first


def glyph_table(b):
    """[(char, x, y, w, h, yoff)], [cumulative count per page], or None."""
    if len(b) < 0x34 or b[:4] != b"\x5c\x8f\x82\x3f":
        return None
    n = struct.unpack_from("<I", b, 0x2C)[0]
    end = 0x30 + n * 10
    if not 0 < n < 1000 or end + 4 > len(b):
        return None
    recs = [struct.unpack_from("<IBBBBh", b, 0x30 + i * 10) for i in range(n)]
    pages = struct.unpack_from("<I", b, end)[0]
    if not 0 < pages < 16 or end + 4 + pages * 4 > len(b):
        return None
    ends = list(struct.unpack_from(f"<{pages}I", b, end + 4))
    return recs, ends


def page_of(i, ends):
    for p, c in enumerate(ends):
        if i < c:
            return p
    return None


def fonts(path):
    """(table entry index, recs, ends, [page entry indices]) of every font
    in the archive with a button glyph."""
    ents = dict(dave_files(path))
    out = []
    for k, b in ents.items():
        t = glyph_table(b)
        if not t or not any(r[0] in BUTTONS for r in t[0]):
            continue
        recs, ends = t
        pages = [k + 1 + p for p in range(len(ends))]
        # A page holding a button that repaint() knows: 128x128 P8, or P4
        # (16 colours). The rest are left as they are (the shop's B, in a
        # page of a size of its own).
        holders = {pages[page_of(i, ends)] for i, r in enumerate(recs) if r[0] in BUTTONS}
        if any(len(ents.get(p, b"")) in (PAGE, PAGE4) for p in holders):
            out.append((k, recs, ends, pages))
    return out


def main():
    seen = {}
    for p in sorted(GAME.rglob("*.dat")):
        if "stream" in p.name or "bank" in p.name:
            continue
        ents = None
        for k, recs, ends, pages in fonts(p):
            ents = ents or dict(dave_files(p))
            sig = hashlib.md5(b"".join(ents[q] for q in [k] + pages)).hexdigest()[:8]
            btn = {BUTTONS[r[0]]: page_of(i, ends) for i, r in enumerate(recs) if r[0] in BUTTONS}
            print(f"{p.relative_to(GAME)} #{k} pages {pages} {sig}{' (same as ' + seen[sig] + ')' if sig in seen else ''} {btn}")
            seen.setdefault(sig, f"{p.name}#{k}")


if __name__ == "__main__":
    main()
