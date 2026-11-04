"""Map kernel thunk slots to ordinals/names and list the guest call sites of chosen ordinals."""
import json
import struct
import sys

XREFS = r"C:\rdr-port\analysis\disasm\xrefs.json"
ANALYSIS = r"C:\rdr-port\game_files\default_analysis.json"
THUNK_KEY = 0x5B6D40B6


def main(xbe_path, *wanted):
    data = open(xbe_path, "rb").read()
    base = struct.unpack_from("<I", data, 0x104)[0]
    thunk = struct.unpack_from("<I", data, 0x158)[0] ^ THUNK_KEY
    # .rdata raw 0x3CE000 maps VA 0x3CF520
    off = 0x3CE000 + (thunk - 0x3CF520)
    names = {}
    try:
        an = json.load(open(ANALYSIS))
        for imp in an.get("kernel_imports", []):
            names[imp.get("ordinal")] = imp.get("name")
    except (OSError, ValueError):
        pass
    slots = []
    while (v := struct.unpack_from("<I", data, off + 4 * len(slots))[0]) != 0:
        slots.append(v & 0x7FFFFFFF)
    for want in wanted:
        if want.startswith("slot"):
            i = int(want[4:])
            print(f"slot {i}: ordinal {slots[i]} {names.get(slots[i], '')}  thunk VA {thunk + 4 * i:08X}")
            continue
        o = int(want)
        i = slots.index(o)
        va = thunk + 4 * i
        print(f"ordinal {o} {names.get(o, '')}: slot {i}, thunk VA {va:08X}")
        xrefs = json.load(open(XREFS))
        items = xrefs if isinstance(xrefs, list) else xrefs.get("xrefs", [])
        for x in items:
            if int(str(x.get("to", "0")), 16) == va:
                print(f"   called from {x.get('from')} ({x.get('type')}) in {x.get('func', '?')}")


if __name__ == "__main__":
    main(*sys.argv[1:])
