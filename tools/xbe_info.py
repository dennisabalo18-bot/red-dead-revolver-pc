"""Read-only summary of an original Xbox XBE: header, certificate, sections, XDK libraries, kernel imports."""
import struct
import sys

RETAIL_ENTRY, DEBUG_ENTRY = 0xA8FC57AB, 0x94859D4B
RETAIL_THUNK, DEBUG_THUNK = 0x5B6D40B6, 0xEFB1F152


def u32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def main(path):
    data = open(path, "rb").read()
    if data[:4] != b"XBEH":
        sys.exit("not an XBE")
    base = u32(data, 0x104)
    hdr = lambda va: va - base  # headers are mapped at the base address

    cert = hdr(u32(data, 0x118))
    title_id = u32(data, cert + 0x8)
    title = data[cert + 0xC:cert + 0xC + 80].decode("utf-16-le").split("\0")[0]
    print(f"Title:      {title}")
    print(f"Title ID:   {title_id:08X} ({chr(title_id >> 24)}{chr((title_id >> 16) & 0xFF)}-{title_id & 0xFFFF:03d})")
    print(f"Base:       {base:08X}   image size: {u32(data, 0x10C):,} bytes")

    sections = []
    count, shdr = u32(data, 0x11C), hdr(u32(data, 0x120))
    print(f"\nSections ({count}):")
    for i in range(count):
        s = shdr + i * 56
        flags, va, vsize, raw, rsize, name_va = struct.unpack_from("<6I", data, s)
        name = data[hdr(name_va):data.index(b"\0", hdr(name_va))].decode("ascii", "replace")
        kind = "code" if flags & 4 else "data"
        print(f"  {name:<10} va {va:08X} size {vsize:>9,}  {kind}{' writable' if flags & 1 else ''}")
        sections.append((va, vsize, raw, rsize))

    def file_off(va):
        for sva, vsize, raw, rsize in sections:
            if sva <= va < sva + rsize:
                return raw + (va - sva)
        return None

    for name, ekey, tkey in (("retail", RETAIL_ENTRY, RETAIL_THUNK), ("debug", DEBUG_ENTRY, DEBUG_THUNK)):
        entry, thunk = u32(data, 0x128) ^ ekey, u32(data, 0x158) ^ tkey
        if file_off(entry) is not None and file_off(thunk) is not None:
            break
    print(f"\nBuild:      {name}   entry {entry:08X}   kernel thunk {thunk:08X}")

    nlib, lib = u32(data, 0x160), hdr(u32(data, 0x164))
    print(f"\nXDK libraries ({nlib}):")
    for i in range(nlib):
        raw_name, major, minor, build, _ = struct.unpack_from("<8s4H", data, lib + i * 16)
        print(f"  {raw_name.rstrip(b'\\0').decode():<9} {major}.{minor}.{build}")

    off, ordinals = file_off(thunk), []
    while (v := u32(data, off)) != 0:
        ordinals.append(v & 0x7FFFFFFF)
        off += 4
    print(f"\nKernel imports: {len(ordinals)} ordinals")
    print("  " + " ".join(str(o) for o in sorted(ordinals)))


if __name__ == "__main__":
    main(sys.argv[1])
