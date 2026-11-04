"""Decode one flip of an [MLOG] capture into draws.

    py -3 mlog_draws.py <log> <flip-index (0 = first capture)> [filter]

For each NV2A draw (SET_BEGIN_END prim ... 0) prints: primitive, transform
mode (fixed/program and the program start), vertex attribute formats, the
inline vertex count and the bounding box of attribute 0 (position) as it
arrives, so screen-space batches and their placement can be read off.
"""
import re
import struct
import sys

PRIMS = {1: "points", 2: "lines", 3: "loop", 4: "strip", 5: "tris", 6: "tristrip",
         7: "trifan", 8: "quads", 9: "quadstrip", 10: "polygon"}
TYPES = {0: "UB_D3D", 1: "S1", 2: "F", 4: "UB_OGL", 5: "S32K", 6: "CMP"}


def words_of(fmt):
    t, n = fmt & 0xF, (fmt >> 4) & 0xF
    if n == 0:
        return 0
    if t == 2:
        return n
    if t in (0, 4, 6):
        return 1
    if t in (1, 5):
        return (n + 1) // 2
    return n


def main(path, which, flt):
    flips, cur = [], None
    for line in open(path, errors="replace"):
        if line.startswith("[MLOG] capturing flip"):
            cur = []
            flips.append(cur)
            continue
        m = re.match(r"\[MLOG\] (\d+) ([0-9A-F]{4}) ([0-9A-F]{8})", line)
        if m and cur is not None:
            cur.append((int(m[1]), int(m[2], 16), int(m[3], 16)))
    ms = flips[which]
    fmt = [0] * 16
    mode, prog_start, prim, inline, n_draw = 0, 0, 0, [], 0
    for sub, meth, p in ms:
        if 0x1760 <= meth < 0x17A0:
            fmt[(meth - 0x1760) // 4] = p
        elif meth == 0x1E94:            # SET_TRANSFORM_EXECUTION_MODE
            mode = p & 3
        elif meth == 0x1EA0:            # SET_TRANSFORM_PROGRAM_START
            prog_start = p
        elif meth == 0x1818:
            inline.append(p)
        elif meth == 0x17FC:            # SET_BEGIN_END
            if p:
                prim, inline = p, []
                continue
            n_draw += 1
            per = sum(words_of(f) for f in fmt)
            nv = len(inline) // per if per else 0
            box = ""
            if nv and (fmt[0] & 0xF) == 2 and ((fmt[0] >> 4) & 0xF) >= 2:
                xs, ys = [], []
                for v in range(nv):
                    w = inline[v * per: v * per + 2]
                    x, y = struct.unpack("<2f", struct.pack("<2I", *w))
                    xs.append(x); ys.append(y)
                box = "x %.1f..%.1f y %.1f..%.1f" % (min(xs), max(xs), min(ys), max(ys))
            attrs = " ".join("v%d:%s%d" % (i, TYPES.get(f & 0xF, f & 0xF), (f >> 4) & 0xF)
                             for i, f in enumerate(fmt) if (f >> 4) & 0xF)
            line = "#%03d %-8s %s inline %4d verts  %-34s %s" % (
                n_draw, PRIMS.get(prim, prim),
                "prog@%d" % prog_start if mode == 2 else "fixed" if mode == 0 else "mode%d" % mode,
                nv, box, attrs)
            if not flt or flt in line:
                print(line)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "")
