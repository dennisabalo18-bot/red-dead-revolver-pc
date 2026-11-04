"""Re-upscale with ultrasharp-4x the textures texturas_halos.py lists, and keep
the ultrasharp one where it has clearly fewer halos and keeps the detail.

The ultrasharp images go to modding/texturas/ultrasharp/. A kept one replaces
the digital-art image in mejoradas/ (that one stays as <name>.digital-art.bak)
and the pack's entry (texturas_pack.py reemplazar). Writes
modding/texturas/ultrasharp.txt with what it chose.

    python tools/texturas_ultrasharp.py
"""
import pathlib
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from escalar_texturas import UPSCAYL  # noqa: E402
from texturas_halos import ROOT, UP, halo  # noqa: E402

OUT = ROOT / "ultrasharp"
MODEL = "ultrasharp-4x"


def detail(img):
    g = np.asarray(img.convert("L"), float)
    return np.abs(g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]).mean()


def upscale(src, dest):
    exe = UPSCAYL / "bin" / "upscayl-bin.exe"
    for tile in ("128", "64"):
        r = subprocess.run([str(exe), "-i", str(src), "-o", str(dest), "-s", "4", "-m", str(UPSCAYL / "models"),
                            "-n", MODEL, "-t", tile, "-f", "png"], capture_output=True, text=True, errors="replace")
        if r.returncode == 0 and dest.is_file() and "failed" not in r.stdout + r.stderr:
            return True
        dest.unlink(missing_ok=True)
    return False


def main():
    OUT.mkdir(exist_ok=True)
    names = [l.split()[0] for l in (ROOT / "halos.txt").read_text().splitlines() if l.strip()]
    kept = []
    for n, name in enumerate(names, 1):
        orig, da, us = ROOT / "dump" / name, UP / name, OUT / name
        print(f"\r  {n}/{len(names)}", end="", flush=True)
        if not (orig.is_file() and da.is_file()) or not (us.is_file() or upscale(orig, us)):
            continue
        o, a, u = Image.open(orig), Image.open(da), Image.open(us)
        ha, hu = halo(o, a), halo(o, u)
        base = detail(o) or 1.0
        du = detail(u.resize(o.size, Image.BOX)) / base
        if hu <= ha * 0.6 and du >= 0.55:
            kept.append(f"{name} halo {ha:.3f}->{hu:.3f} detalle {du:.2f}")
            bak = da.with_name(da.stem + ".digital-art.bak")
            if not bak.exists():
                shutil.copy2(da, bak)
            shutil.copy2(us, da)
    print()
    (ROOT / "ultrasharp.txt").write_text("".join(k + "\n" for k in kept))
    print(f"{len(kept)} de {len(names)} pasan a ultrasharp (lista en {ROOT / 'ultrasharp.txt'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
