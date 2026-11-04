"""Escala con Upscayl las texturas de texturas/dump/ que aun no estan en mejoradas/.

Una imagen por proceso, en mosaicos chicos: si la tarjeta se reinicia
("vkQueueSubmit failed -4") solo se pierde esa imagen, que se reintenta con
mosaicos mas chicos. Se puede cortar y volver a ejecutar: sigue donde quedo.

    python tools/escalar_texturas.py [modelo]      (digital-art-4x por defecto)
"""
import pathlib
import subprocess
import sys

UPSCAYL = pathlib.Path(r"C:\Program Files\Upscayl\resources")
ROOT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas"


def main():
    modelo = sys.argv[1] if len(sys.argv) > 1 else "digital-art-4x"
    exe = UPSCAYL / "bin" / "upscayl-bin.exe"
    if not exe.is_file():
        print(f"No encuentro Upscayl en {exe}")
        return 1
    salida = ROOT / "mejoradas" / f"upscayl_png_{modelo}_4x"
    salida.mkdir(parents=True, exist_ok=True)
    hechas = {p.name[:16] for p in (ROOT / "mejoradas").rglob("*.png")}
    # Font pages (Upscayl invents strokes on text) and textures the pack
    # leaves out anyway (texturas_pack.SMALL) are not worth the GPU time.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import letras
    from texturas_pack import NAME, SMALL
    fuentes = {f"{h:016X}" for h in letras.font_pages()}

    def sirve(p):
        m = NAME.match(p.stem)
        return m and p.name[:16] not in fuentes and max(int(m.group(2)), int(m.group(3))) > SMALL

    faltan = [p for p in sorted((ROOT / "dump").glob("*.png")) if p.name[:16] not in hechas and sirve(p)]
    print(f"{len(hechas)} ya escaladas, faltan {len(faltan)} (modelo {modelo})")
    fallidas = []
    for n, p in enumerate(faltan, 1):
        dest = salida / p.name
        ok = False
        for tile in ("128", "64"):
            try:
                r = subprocess.run([str(exe), "-i", str(p), "-o", str(dest), "-s", "4",
                                    "-m", str(UPSCAYL / "models"), "-n", modelo, "-t", tile, "-f", "png"],
                                   capture_output=True, text=True, errors="replace", timeout=300)
                ok = r.returncode == 0 and dest.is_file() and "failed" not in r.stdout + r.stderr
            except subprocess.TimeoutExpired:
                ok = False
            if ok:
                break
            dest.unlink(missing_ok=True)
        if not ok:
            fallidas.append(p.name)
        print(f"\r  {n}/{len(faltan)}" + (f"  ({len(fallidas)} fallaron)" if fallidas else ""), end="", flush=True)
    print()
    for f in fallidas:
        print(f"  no se pudo: {f} (queda la original)")
    print("Listo. Ahora ejecuta crear_pack_texturas.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
