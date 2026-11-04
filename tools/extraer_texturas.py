"""Dump Red Dead Revolver's textures to PNG straight from the disc files,
under the same names the game's own dump (F2 "Volcar texturas a carpeta")
gives them, so texturas_pack.py takes them as they are.

The level and front-end archives are "Dave" archives (Rockstar San Diego):
the "DAVE" layout (see extraer_audio.py) with every entry raw-deflated
(packed size != size) and the names packed. A standalone texture entry is

    0x00  u16 width, u16 height
    0x04  u16 format: 0x16 DXT1, 0x1A DXT5, 0x0E P8 (0x10 P4 + palette,
          0x11 24-bit RGB, 0x08 8-bit and 0x0B are converted at load and
          left out here)
    0x06  u16 mip levels
    0x08  6 bytes of flags
    0x0E  the levels, one after another, as the GPU reads them

DXT is not swizzled, so those bytes are the texture's memory once loaded,
and the pack key is nv2a_tex_hash (kernel/nv2a_backend_common.c) over all
the levels. A P8 entry is the 1024-byte BGRA palette, then the indices of
every level in rows; the game swizzles them on load, and the key is the
hash of the swizzled levels with the palette's (256 entries) folded in,
as tex_hash_pal in nv2a_pb_d3d11.c does (checked against a run's log: 195
of them matched). A model (RSC0 entry: "RSC0", the chunk count, the
header's size, then (tag, end) pairs from 0x0C; the first chunk starts at
the header's end) keeps its textures in each MIP0 chunk (u32 count, u32 offset of count D3D texture descriptors of
20 bytes: common, data offset in the chunk, lock, format word, size) already
swizzled, and their palette in the PAL0 chunk after it, at +0x40: the key
is the same (checked: a model texture of swat.dat matched a run's miss). A
level's scenery is one such entry with hundreds of chunks (PMT0, BND0, then
MIP0/PAL0/TEX0/MOD0 groups).

    python tools/extraer_texturas.py [game_dir] [out_dir]
"""
import array
import hashlib
import io
import pathlib
import struct
import sys
import zlib

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extraer_audio import GAME  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "texturas" / "dump"
FORMATS = {0x16: (b"DXT1", 8), 0x1A: (b"DXT5", 16)}
SEED = 0xCBF29CE484222325
PRIME = 0x100000001B3
M64 = (1 << 64) - 1


def tex_hash(b):
    """nv2a_tex_hash(b, len(b), NV2A_TEX_HASH_SEED)."""
    n = len(b) // 32 * 32
    w = array.array("Q", b[:n])
    if sys.byteorder != "little":
        w.byteswap()
    l0, l1, l2, l3 = SEED, SEED ^ 1, SEED ^ 2, SEED ^ 3
    for i in range(0, len(w), 4):
        l0 = ((l0 ^ w[i]) * PRIME) & M64
        l1 = ((l1 ^ w[i + 1]) * PRIME) & M64
        l2 = ((l2 ^ w[i + 2]) * PRIME) & M64
        l3 = ((l3 ^ w[i + 3]) * PRIME) & M64
    for c in b[n:]:
        l0 = ((l0 ^ c) * PRIME) & M64
    return ((l0 ^ ((l1 << 1) & M64) ^ ((l2 << 2) & M64) ^ ((l3 << 3) & M64)) * PRIME) & M64


def extent(w, h, levels, bb):
    n = 0
    for _ in range(levels):
        n += ((w + 3) // 4) * ((h + 3) // 4) * bb
        w, h = max(1, w // 2), max(1, h // 2)
    return n


def dds_level0(fourcc, w, h, data):
    """Level 0 decoded through a minimal DDS header."""
    hdr = struct.pack("<4sIIIIIII44sII4s20sI16s", b"DDS ", 124, 0x1007, h, w, len(data), 0, 1,
                      b"\0" * 44, 32, 0x4, fourcc, b"\0" * 20, 0x1000, b"\0" * 16)
    return Image.open(io.BytesIO(hdr + data)).convert("RGBA")


def dave_files(path):
    """(name index, bytes) of every entry of a "Dave" archive."""
    with open(path, "rb") as f:
        magic, count, dsz, nsz = struct.unpack("<4sIII", f.read(16))
        if magic != b"Dave":
            return
        f.seek(0x800)
        d = f.read(dsz)
        for k in range(count):
            no, off, size, packed = struct.unpack_from("<IIII", d, k * 16)
            f.seek(off)
            b = f.read(packed)
            try:
                yield k, zlib.decompress(b, -15) if packed != size else b
            except zlib.error:
                continue


def texture(u):
    """(fourcc, w, h, all levels' bytes) of a standalone DXT entry, or None."""
    if len(u) < 14:
        return None
    w, h, fmt, levels = struct.unpack_from("<HHHH", u)
    if fmt not in FORMATS or not (0 < levels <= 13):
        return None
    if not (4 <= w <= 4096 and 4 <= h <= 4096) or w & (w - 1) or h & (h - 1):
        return None
    fourcc, bb = FORMATS[fmt]
    n = extent(w, h, levels, bb)
    if not n <= len(u) - 14 < n + 0x800:
        return None
    return fourcc, w, h, u[14:14 + n], bb


def zorder(w, h):
    """The swizzled position of every texel of a w x h texture, row by row."""
    ys, xs = np.mgrid[0:h, 0:w]
    o, bit = np.zeros((h, w), np.int64), 0
    for b in range(16):
        if 1 << b < w:
            o |= ((xs >> b) & 1) << bit
            bit += 1
        if 1 << b < h:
            o |= ((ys >> b) & 1) << bit
            bit += 1
    return o.ravel()


def p8_image(idx, pal, w, h):
    """RGBA of w x h palette indices in rows, palette BGRA."""
    lut = np.frombuffer(pal, np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    return Image.fromarray(lut[np.frombuffer(idx, np.uint8)].reshape(h, w, 4), "RGBA")


def model_textures(u):
    """[(key, level 0 RGBA)] of the P8 textures of a model (RSC0) entry."""
    if u[:4] != b"RSC0" or len(u) < 0x100:
        return []
    n, start = struct.unpack_from("<II", u, 4)
    if not 0 < n < 4096 or 12 + 8 * n > start or start > len(u):
        return []
    chunks = []
    for i in range(n):
        end = struct.unpack_from("<I", u, 16 + 8 * i)[0]
        chunks.append((u[12 + 8 * i:16 + 8 * i], start, end))
        start = end
    out = []
    for j, (t, a, b) in enumerate(chunks):
        if t != b"MIP0" or b - a < 12 or b > len(u):
            continue
        nxt = chunks[j + 1] if j + 1 < len(chunks) else None
        if not nxt or nxt[0] != b"PAL0" or nxt[2] - nxt[1] < 0x440:
            continue
        pal = u[nxt[1] + 0x40:nxt[1] + 0x440]
        count, _, off = struct.unpack_from("<III", u, a)
        for i in range(min(count, 256)):
            d = a + off + 20 * i
            if d + 20 > b:
                break
            _, data, _, fmt, _ = struct.unpack_from("<IIIII", u, d)
            if (fmt >> 8) & 0xFF != 0x0B:
                continue
            levels, w, h = max(1, (fmt >> 16) & 0xF), 1 << ((fmt >> 20) & 0xF), 1 << ((fmt >> 24) & 0xF)
            size, lw, lh = 0, w, h
            for _ in range(levels):
                size += lw * lh
                lw, lh = max(1, lw // 2), max(1, lh // 2)
            texels = u[a + data:a + data + size]
            if len(texels) != size:
                continue
            key = tex_hash(texels) ^ (tex_hash(pal) * 31 & M64)
            lin = np.frombuffer(texels[:w * h], np.uint8)[zorder(w, h)]
            out.append((key, p8_image(lin.tobytes(), pal, w, h)))
    return out


def swizzled(idx, w, h):
    """8-bit texels in the GPU's Z-order (d3d8_swizzle.h): x bits on the even
    positions, y on the odd, while each axis has bits left."""
    ys, xs = np.mgrid[0:h, 0:w]
    o, bit = np.zeros((h, w), np.int64), 0
    for b in range(16):
        if 1 << b < w:
            o |= ((xs >> b) & 1) << bit
            bit += 1
        if 1 << b < h:
            o |= ((ys >> b) & 1) << bit
            bit += 1
    out = np.zeros(w * h, np.uint8)
    out[o.ravel()] = np.frombuffer(idx, np.uint8)
    return out.tobytes()


def p8_texture(u):
    """(key, level 0 RGBA) of a standalone P8 entry, or None."""
    if len(u) < 14 + 1024 + 64:
        return None
    w, h, fmt, levels = struct.unpack_from("<HHHH", u)
    if fmt != 0x0E or not (8 <= w <= 1024 and 8 <= h <= 1024) or w & (w - 1) or h & (h - 1)             or not 0 < levels <= 11:
        return None
    sizes, lw, lh = [], w, h
    for _ in range(levels):
        sizes.append((lw, lh))
        lw, lh = max(1, lw // 2), max(1, lh // 2)
    n = sum(a * b for a, b in sizes)
    if len(u) < 14 + 1024 + n:
        return None
    pal, idx = u[14:14 + 1024], u[14 + 1024:14 + 1024 + n]
    sw, off = bytearray(), 0
    for a, b in sizes:
        sw += swizzled(idx[off:off + a * b], a, b)
        off += a * b
    key = tex_hash(bytes(sw)) ^ (tex_hash(pal) * 31 & M64)
    lut = np.frombuffer(pal, np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    img = Image.fromarray(lut[np.frombuffer(idx[:w * h], np.uint8)].reshape(h, w, 4), "RGBA")
    return key, img


def main():
    game = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else GAME
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else OUT
    out.mkdir(parents=True, exist_ok=True)
    seen = set()
    new = old = bad = 0
    archives = sorted(p for p in game.rglob("*.dat") if p.name.lower() not in
                      ("banks.dat",) and not p.name.lower().startswith("stream"))
    for arc in archives:
        found = 0
        for _, u in dave_files(arc):
            for key, img in model_textures(u):
                if key in seen:
                    continue
                seen.add(key)
                found += 1
                png = out / f"{key:016X}_{img.width}x{img.height}.png"
                if png.exists():
                    old += 1
                else:
                    img.save(png)
                    new += 1
            p8 = p8_texture(u)
            if p8:
                key, img = p8
                if key in seen:
                    continue
                seen.add(key)
                found += 1
                png = out / f"{key:016X}_{img.width}x{img.height}.png"
                if png.exists():
                    old += 1
                else:
                    img.save(png)
                    new += 1
                continue
            t = texture(u)
            if not t:
                continue
            fourcc, w, h, data, bb = t
            md = hashlib.md5(data).digest()
            if md in seen:
                continue
            seen.add(md)
            found += 1
            png = out / f"{tex_hash(data):016X}_{w}x{h}.png"
            if png.exists():
                old += 1
                continue
            try:
                dds_level0(fourcc, w, h, data[:((w + 3) // 4) * ((h + 3) // 4) * bb]).save(png)
                new += 1
            except Exception as ex:       # noqa: BLE001
                bad += 1
                print(f"  no se pudo decodificar {png.name}: {ex}")
        print(f"{arc.relative_to(game)}: {found} texturas nuevas")
    print(f"Listo: {new} PNG nuevos ({old} ya estaban) en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
