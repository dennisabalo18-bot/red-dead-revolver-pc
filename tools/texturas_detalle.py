"""Which upscaled textures lost the original's fine detail.

Upscayl smooths noise (gravel, sand, dirt) into flat smears: the gravel in
the train's wagons came out a plain brown. For each upscaled image this
compares the fine detail (mean absolute Laplacian of the luminance) of the
image scaled back to the original's size with the original's own; below
KEEP of it, the original looks better and the hash is listed.

    python tools/texturas_detalle.py        writes modding/texturas/borrosas.txt
"""
import pathlib
import sys

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas"
KEEP = 0.55


def detail(img):
    a = np.asarray(img.convert("L"), np.float32)
    lap = 4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]
    return float(np.abs(lap).mean())


def main():
    dump = {p.name[:16]: p for p in (ROOT / "dump").glob("*.png")}
    out = []
    ups = sorted((ROOT / "mejoradas").rglob("*.png"))
    for n, p in enumerate(ups, 1):
        o = dump.get(p.name[:16])
        if not o:
            continue
        with Image.open(o) as a, Image.open(p) as b:
            if a.size[0] < 16 or a.size[1] < 16:
                continue
            ref = detail(a)
            if ref < 4:            # a smooth original: nothing to lose
                continue
            got = detail(b.convert("RGB").resize(a.size, Image.BOX))
        if got < KEEP * ref:
            out.append((got / ref, p.name[:16]))
        if n % 200 == 0:
            print(f"\r  {n}/{len(ups)}", end="", flush=True)
    out.sort()
    (ROOT / "borrosas.txt").write_text("".join(f"{h} {r:.2f}\n" for r, h in out))
    print(f"\n{len(out)} texturas perdieron detalle -> {ROOT / 'borrosas.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
