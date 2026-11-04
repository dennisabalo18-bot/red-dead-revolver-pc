"""Build the D3D11 backend's texture pack from upscaled texture dumps.

The game writes its textures, when "Volcar texturas" is on in the F2 menu,
as modding/texturas/dump/<HASH>_<w>x<h>.png. Upscale any of them (any
factor; keep the file name, extra text after the size is fine, e.g.
"..._256x256_x4.png") into modding/texturas/mejoradas/, then run
crear_pack_texturas.bat (this script). It writes modding/texturas/textures.pack,
which the game loads at start (RECOMP_TEXTURES_PACK in env.bat). A texture
with transparency takes it from the original (the game's archives, else
texturas/dump/), scaled, and the original's colour where it is see-through
(restore), whatever the upscaler did to it. The game's font pages
go in too, 4x and sharp (letras.py), as the "font" kind the F2 menu can
turn off.

Format: xboxrecomp-apex/docs/formats/texture-pack.md, version 2: every
entry A8R8G8B8 with a full mip chain, keyed by the dump's hash; kind 0
(art) for the upscaled images, 1 (font) for the font pages.

    python tools/texturas_pack.py [mejoradas_dir] [out.pack]
"""
import pathlib
import re
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import botones_teclado  # noqa: E402
import letras  # noqa: E402
import letras_vector  # noqa: E402
from extraer_texturas import GAME, dave_files, dds_level0, tex_hash, texture  # noqa: E402
from fuentes_botones import glyph_table  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas"
NAME = re.compile(r"^([0-9A-Fa-f]{16})_(\d+)x(\d+)")
MAX_DIM = 16384
KIND_FONT = 1
# Textures up to this size stay the game's own: gradients and soft spots,
# which an upscaler turns into shapes (a 32x32 vignette on the loading
# screen came out a hard oval frame with a canvas weave).
SMALL = 32


def blurred():
    """Hashes texturas_detalle.py found smoothed by the upscaler (gravel,
    sand, dirt): the game's own look better."""
    f = ROOT / "borrosas.txt"
    return {int(l.split()[0], 16) for l in f.read_text().splitlines() if l.strip()} if f.is_file() else set()


def mip_chain(img):
    """Level 0 and every level after it, each half the last (floor, min 1)."""
    levels = [img]
    w, h = img.size
    while w > 1 or h > 1:
        w, h = max(1, w // 2), max(1, h // 2)
        levels.append(img.resize((w, h), Image.LANCZOS))
    return levels


def originals(want):
    """{hash: level 0 RGBA} of the textures in `want` that have transparency,
    straight from the game's archives (extraer_texturas.py's hashes)."""
    out = {}
    archives = sorted(p for p in GAME.rglob("*.dat") if p.name.lower() != "banks.dat"
                      and not p.name.lower().startswith("stream"))
    for arc in archives:
        for _, u in dave_files(arc):
            t = texture(u)
            if not t:
                continue
            h = tex_hash(t[3])
            if h in want and h not in out:
                img = dds_level0(*t[:4])
                if img.getchannel("A").getextrema()[0] < 255:
                    out[h] = img
    return out


def restore(img, orig):
    """img (upscaled) with the original's transparency, and its colour where
    it is see-through. Upscalers lose alpha or smear it (a black edge around
    leaves and fences) and blacken the colour under transparent texels, which
    darkened glows and the loading animation: a cut-out (only 0 and 255) keeps
    a sharp edge, a soft alpha is smoothed, and each texel's colour is the
    upscaler's as far as it is opaque, the original's (smoothly scaled) as
    far as it is not."""
    a = orig.getchannel("A")
    cutout = sum(a.histogram()[1:255]) == 0
    soft = np.asarray(a.resize(img.size, Image.BICUBIC), np.float32)[..., None] / 255.0
    base = np.asarray(orig.convert("RGB").resize(img.size, Image.BICUBIC), np.float32)
    up = np.asarray(img.convert("RGB"), np.float32)
    rgb = np.clip(up * soft + base * (1.0 - soft), 0, 255).astype(np.uint8)
    out = Image.fromarray(rgb, "RGB").convert("RGBA")
    a = a.resize(img.size, Image.BICUBIC)
    out.putalpha(a.point(lambda v: 255 if v >= 128 else 0) if cutout else a)
    return out


def dump_original(dump, h):
    """The dump's own image of h when it has transparency (a texture the
    archives do not hold as a plain entry), or None."""
    found = list(dump.glob(f"{h:016X}_*.png")) if dump.is_dir() else []
    if not found:
        return None
    with Image.open(found[0]) as o:
        o = o.convert("RGBA")
    return o if o.getchannel("A").getextrema()[0] < 255 else None


def drop(out, gone, what):
    """The pack without the entries gone(entry) says, in place: a new index
    at the end."""
    with open(out, "r+b") as f:
        magic, ver, count, scale, index_off, extra = struct.unpack("<4sIIIQQ", f.read(32))
        if magic != b"XRTP" or ver not in (1, 2):
            print(f"{out} no es un pack de texturas")
            return 1
        f.seek(index_off)
        keep = [e for e in (struct.unpack("<QIIIIQ", f.read(32)) for _ in range(count))
                if not gone(e, scale)]
        new_off = f.seek(0, 2)
        for e in keep:
            f.write(struct.pack("<QIIIIQ", *e))
        f.seek(0)
        f.write(struct.pack("<4sIIIQII", b"XRTP", 2, len(keep), scale,
                            new_off, extra & 0xFFFFFFFF if ver == 2 else 0, 0))
    print(f"{count - len(keep)} {what} quitadas de {out}")
    return 0


def add_fonts(out, vector=False):
    """Put the font pages into an existing pack without rebuilding it: their
    texels and a new index go at the end, the header points to that index
    (the old one stays as dead space; a full build drops it). Fonts already
    in it are replaced. vector: the plain fonts redrawn from TrueType
    (letras_vector.py) instead of every page enlarged (letras.py)."""
    with open(out, "r+b") as f:
        magic, ver, count, scale, index_off, extra = struct.unpack("<4sIIIQQ", f.read(32))
        if magic != b"XRTP" or ver not in (1, 2):
            print(f"{out} no es un pack de texturas")
            return 1
        f.seek(index_off)
        old = [struct.unpack("<QIIIIQ", f.read(32)) for _ in range(count)]
        index = {e[0]: e for e in old if e[4] & 3 != KIND_FONT}
        f.seek(0, 2)
        added, offs = 0, {}
        pages = ({h: (v[2], None) for h, v in letras_vector.vector_pages().items()} if vector
                 else {h: (v[2], v[3]) for h, v in letras.font_pages().items()})
        for h, (page, cells) in pages.items():
            if h in index:
                continue
            if id(page) not in offs:
                offs[id(page)] = f.tell()
                for lv in mip_chain(page if vector else letras.page_4x(page, cells)):
                    f.write(lv.tobytes("raw", "BGRA"))
            k = 1 if vector else letras.SCALE
            w, hh = page.width * k, page.height * k
            levels = len(mip_chain(Image.new("L", (w, hh))))
            index[h] = (h, w, hh, levels, KIND_FONT, offs[id(page)])
            added += 1
        new_off = f.tell()
        for h in sorted(index):
            f.write(struct.pack("<QIIIIQ", *index[h]))
        f.seek(0)
        f.write(struct.pack("<4sIIIQII", b"XRTP", 2, len(index), scale,
                            new_off, extra & 0xFFFFFFFF if ver == 2 else 0, 0))
    print(f"{added} claves de letras agregadas a {out}")
    return 0


# The menus' controller buttons are 32x32 images of their own (the shop's A
# and Y, first seen by a dump of the shop), not font glyphs: each becomes the
# key the PC layout puts there (botones_teclado.ICONS), drawn at 128x128.
BUTTON_IMAGES = {
    0x562B8D102E7C0525: "space",    # A
    0x2F64743FD0FFABF7: "R",        # Y
    0x945255403598B301: "E",        # X
    0x96886387F3E236AB: "E",        # X (the other copy)
    0x40669087AF0A4BAD: "C",        # B
}


def add_new(out, src):
    """Append to an existing pack, without rebuilding it, every upscaled image
    in src whose hash it lacks (as a full build would make it) and the
    keyboard keys of BUTTON_IMAGES; a new index at the end, as add_fonts."""
    dump = src.parent / "dump"
    with open(out, "r+b") as f:
        magic, ver, count, scale, index_off, extra = struct.unpack("<4sIIIQQ", f.read(32))
        if magic != b"XRTP" or ver not in (1, 2):
            print(f"{out} no es un pack de texturas")
            return 1
        f.seek(index_off)
        index = {e[0]: e for e in (struct.unpack("<QIIIIQ", f.read(32)) for _ in range(count))}
        new = {h: botones_teclado.icon(kind, 128, 128) for h, kind in BUTTON_IMAGES.items()}
        gone = blurred()
        for p in sorted(src.rglob("*.png")):
            m = NAME.match(p.stem)
            if not m:
                continue
            h, gw, gh = int(m.group(1), 16), int(m.group(2)), int(m.group(3))
            if h in index or h in new or max(gw, gh) <= SMALL or h in gone:
                continue
            img = Image.open(p).convert("RGBA")
            k = max(1, round(img.size[0] / gw))
            if img.size != (gw * k, gh * k):
                img = img.resize((gw * k, gh * k), Image.LANCZOS)
            o = dump_original(dump, h)
            new[h] = restore(img, o) if o else img
        f.seek(0, 2)
        for h, img in new.items():
            off = f.tell()
            levels = mip_chain(img)
            for lv in levels:
                f.write(lv.tobytes("raw", "BGRA"))
            index[h] = (h, img.size[0], img.size[1], len(levels), 0, off)
        new_off = f.tell()
        for h in sorted(index):
            f.write(struct.pack("<QIIIIQ", *index[h]))
        f.seek(0)
        f.write(struct.pack("<4sIIIQII", b"XRTP", 2, len(index), scale,
                            new_off, extra & 0xFFFFFFFF if ver == 2 else 0, 0))
    print(f"{len(new)} texturas agregadas a {out} ({len(BUTTON_IMAGES)} botones como teclas)")
    return 0


def replace(out, src, names):
    """Write again, from src, the pack entries of the images named in names
    (texturas_ultrasharp.py's picks): data appended, a new index at the end,
    as add_new. Names the pack lacks are left for add_new."""
    dump = src.parent / "dump"
    files = {p.name: p for p in src.rglob("*.png")}
    with open(out, "r+b") as f:
        magic, ver, count, scale, index_off, extra = struct.unpack("<4sIIIQQ", f.read(32))
        if magic != b"XRTP" or ver not in (1, 2):
            print(f"{out} no es un pack de texturas")
            return 1
        f.seek(index_off)
        index = {e[0]: list(e) for e in (struct.unpack("<QIIIIQ", f.read(32)) for _ in range(count))}
        f.seek(0, 2)
        done = 0
        for name in names:
            m = NAME.match(name)
            h = int(m.group(1), 16) if m else None
            if h not in index or name not in files:
                continue
            gw, gh = int(m.group(2)), int(m.group(3))
            img = Image.open(files[name]).convert("RGBA")
            k = max(1, round(img.size[0] / gw))
            if img.size != (gw * k, gh * k):
                img = img.resize((gw * k, gh * k), Image.LANCZOS)
            o = dump_original(dump, h)
            img = restore(img, o) if o else img
            off = f.tell()
            levels = mip_chain(img)
            for lv in levels:
                f.write(lv.tobytes("raw", "BGRA"))
            e = index[h]
            e[1], e[2], e[3], e[5] = img.size[0], img.size[1], len(levels), off
            done += 1
        new_off = f.tell()
        for h in sorted(index):
            f.write(struct.pack("<QIIIIQ", *index[h]))
        f.seek(0)
        f.write(struct.pack("<4sIIIQII", b"XRTP", 2, len(index), scale,
                            new_off, extra & 0xFFFFFFFF if ver == 2 else 0, 0))
    print(f"{done} texturas reemplazadas en {out}")
    return 0


def add_font_indices(out):
    """A second key for every font page already in the pack: the hash of its
    indices alone (as in the file and swizzled), for the runtime's fallback
    when the game draws the page with a palette of its own (a fade); the
    entry points at the same texels."""
    with open(out, "r+b") as f:
        magic, ver, count, scale, index_off, extra = struct.unpack("<4sIIIQQ", f.read(32))
        if magic != b"XRTP" or ver not in (1, 2):
            print(f"{out} no es un pack de texturas")
            return 1
        f.seek(index_off)
        index = {e[0]: e for e in (struct.unpack("<QIIIIQ", f.read(32)) for _ in range(count))}
        added = 0
        for (arc_name, k) in letras_vector.FONTS:
            src = next(GAME.rglob(arc_name))
            rel = src.relative_to(GAME)
            arc = letras.MODS / rel if (letras.MODS / rel).is_file() else src
            ents = dict(dave_files(arc))
            recs, ends = glyph_table(ents[k])
            for p in range(len(ends)):
                d = letras.decode(ents[k + 1 + p])
                if not d:
                    continue
                w, h = d[2].size
                e = next((index[x] for x in letras.page_hashes(d[0], d[1], w, h) if x in index), None)
                if not e or e[4] & 3 != KIND_FONT:
                    continue
                pow2 = w & (w - 1) == 0 and h & (h - 1) == 0
                for t in ((d[0], letras.swizzled(d[0], w, h)) if pow2 else (d[0],)):
                    ih = tex_hash(t)
                    if ih not in index:
                        index[ih] = (ih, e[1], e[2], e[3], KIND_FONT, e[5])
                        added += 1
        f.seek(0, 2)
        new_off = f.tell()
        for h in sorted(index):
            f.write(struct.pack("<QIIIIQ", *index[h]))
        f.seek(0)
        f.write(struct.pack("<4sIIIQII", b"XRTP", 2, len(index), scale,
                            new_off, extra & 0xFFFFFFFF if ver == 2 else 0, 0))
    print(f"{added} claves de letras por sus indices agregadas a {out}")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() == "sin_borrosas":
        gone = blurred()
        return drop(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack",
                    lambda e, k: e[0] in gone, "texturas borrosas")
    if len(sys.argv) > 1 and sys.argv[1].lower() == "agregar":
        return add_new(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack", ROOT / "mejoradas")
    if len(sys.argv) > 1 and sys.argv[1].lower() == "reemplazar":
        names = [l.split()[0] for l in (ROOT / "ultrasharp.txt").read_text().splitlines() if l.strip()]
        return replace(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack",
                       ROOT / "mejoradas", names)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "letras_indices":
        return add_font_indices(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack")
    if len(sys.argv) > 1 and sys.argv[1].lower() == "sin_letras":
        return drop(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack",
                    lambda e, k: e[4] & 3 == KIND_FONT, "claves de letras")
    if len(sys.argv) > 1 and sys.argv[1].lower() == "sin_chicas":
        return drop(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack",
                    lambda e, k: e[4] & 3 != KIND_FONT and max(e[1], e[2]) <= SMALL * k, "texturas chicas")
    if len(sys.argv) > 1 and sys.argv[1].lower() == "letras_vector":
        return add_fonts(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack", vector=True)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "letras":
        out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack"
        return add_fonts(out)
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "mejoradas"
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "textures.pack"
    if not src.is_dir():
        print(f"No existe la carpeta {src}")
        return 1
    dump = src.parent / "dump"
    # Pass 1: names and sizes only (Image.open reads the header), so a pack
    # of hundreds of large images never sits in memory at once.
    entries = {}
    skipped = 0
    gone = blurred()
    # Subfolders too: Upscayl writes a batch into one of its own.
    for p in sorted(src.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga"):
            continue
        m = NAME.match(p.stem)
        if not m:
            print(f"  ignorada (el nombre no empieza por HASH_ANCHOxALTO): {p.name}")
            skipped += 1
            continue
        h, gw, gh = int(m.group(1), 16), int(m.group(2)), int(m.group(3))
        if max(gw, gh) <= SMALL or h in gone:
            continue
        if h in entries:
            print(f"  repetida, se usa la primera: {p.name}")
            continue
        try:
            with Image.open(p) as img:
                iw = img.size[0]
        except OSError:
            print(f"  ignorada (imagen rota o a medio escribir): {p.name}")
            skipped += 1
            continue
        # The pack keeps the guest's aspect exactly: a whole factor of it.
        k = max(1, round(iw / gw))
        while k > 1 and max(gw, gh) * k > MAX_DIM:
            k -= 1
        entries[h] = (p, gw * k, gh * k, k, 0)
    # The font pages go in only on request (texturas_pack.py letras): 4x, they
    # looked worse in the game than the originals.
    fonts = 0

    def level_sizes(w, h):
        out = [(w, h)]
        while w > 1 or h > 1:
            w, h = max(1, w // 2), max(1, h // 2)
            out.append((w, h))
        return out

    print("  buscando las originales con transparencia en los archivos del juego...")
    orig = originals({h for h, e in entries.items() if e[4] != KIND_FONT})
    hashes = sorted(entries)
    count = len(hashes)
    index_off = 32
    off = index_off + 32 * count
    index = bytearray()
    payload = {}                                 # source -> its offset, written once
    for h in hashes:
        p, w, hh, _, kind = entries[h]
        sizes = level_sizes(w, hh)
        if id(p) not in payload:
            payload[id(p)] = off
            off += sum(a * b * 4 for a, b in sizes)
        index += struct.pack("<QIIIIQ", h, w, hh, len(sizes), kind, payload[id(p)])
    scale = max((e[3] for e in entries.values()), default=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write(struct.pack("<4sIIIQII", b"XRTP", 2, count, scale, index_off, 0, 0))
        f.write(index)
        written = set()
        for n, h in enumerate(hashes, 1):
            p, w, hh, _, kind = entries[h]
            if id(p) in written:
                continue
            written.add(id(p))
            if kind == KIND_FONT:
                for lv in mip_chain(letras.page_4x(*p)):
                    f.write(lv.tobytes("raw", "BGRA"))
                continue
            img = Image.open(p).convert("RGBA")
            if img.size != (w, hh):
                img = img.resize((w, hh), Image.LANCZOS)
            o = orig.get(h) or dump_original(dump, h)
            if o:
                img = restore(img, o)
            for lv in mip_chain(img):
                f.write(lv.tobytes("raw", "BGRA"))
            if n % 50 == 0:
                print(f"  {n}/{count}")
    tmp.replace(out)
    mb = off / (1024 * 1024)
    print(f"{count - fonts} texturas y {fonts} claves de letras en {out} ({mb:.1f} MB, escala hasta x{scale})"
          + (f", {skipped} ignoradas" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
