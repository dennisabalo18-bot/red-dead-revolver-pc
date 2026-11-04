"""Upscaled textures with light halos around dark lines (pencil drawings,
engravings): digital-art-4x brightens the paper next to every stroke.

halo() is the share of the upscale's opaque texels clearly brighter than the
brightest original texel around them. On the shop's revolver drawing
digital-art gave 6.6 %, ultrasharp-4x 3 %. Writes modding/texturas/halos.txt
(hash, size, halo), the worst first.

    python tools/texturas_halos.py
"""
import pathlib
import sys

import numpy as np
from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas"
UP = ROOT / "mejoradas" / "upscayl_png_digital-art-4x_4x"
LIMIT = 0.04


def halo(orig, up):
    g = orig.convert("L").filter(ImageFilter.MaxFilter(3)).resize(up.size, Image.NEAREST)
    a = np.asarray(up.convert("RGBA"))[..., 3] > 128
    l = np.asarray(up.convert("L"), np.int16)
    return float(((l > np.asarray(g, np.int16) + 25) & a).sum() / max(1, a.sum()))


def main():
    dump = {p.name[:16]: p for p in (ROOT / "dump").glob("*.png")}
    rows = []
    ups = sorted(UP.glob("*.png"))
    for n, p in enumerate(ups, 1):
        o = dump.get(p.name[:16])
        if o:
            rows.append((halo(Image.open(o), Image.open(p)), p.name))
        print(f"\r  {n}/{len(ups)}", end="", flush=True)
    print()
    rows.sort(reverse=True)
    (ROOT / "halos.txt").write_text("".join(f"{name} {h:.4f}\n" for h, name in rows if h >= LIMIT))
    print(f"{sum(h >= LIMIT for h, _ in rows)} con halos (>= {LIMIT:.0%}) en {ROOT / 'halos.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
