"""Rename generated function definitions to <name>_pad so src/mouselook.c's
wrappers of the same name (and src/widescreen.c's, src/movies.c's) get every call, including calls from the same file.

Run after regenerating rdr-apex/src/recomp/gen (idempotent):
    python tools/rename_pads.py
"""
import pathlib
import re
import sys

GEN = pathlib.Path(__file__).resolve().parent.parent / "rdr-apex" / "src" / "recomp" / "gen"

# file -> functions whose definition is wrapped in src/mouselook.c
PADS = {
    "recomp_0031.c": ["sub_001A8DD0", "sub_001A98C0"],
    "recomp_0023.c": ["sub_0014DB20", "sub_0014DBF0"],
    "recomp_0027.c": ["sub_0017E370"],
    "recomp_0009.c": ["sub_00071080", "sub_00072110"],
    # XInputGetState: src/mando_directo.c reads the host state instead.
    "recomp_0077.c": ["sub_003C88B4"],
}


def main():
    bad = 0
    for fname, funcs in PADS.items():
        p = GEN / fname
        s = p.read_text(encoding="utf-8")
        for f in funcs:
            if re.search(r"^void %s_pad\(void\)" % f, s, re.M):
                print(f"{fname}: {f} already renamed")
                continue
            s, n = re.subn(r"^void %s\(void\)" % f,
                           "void %s_pad(void) /* rdr-port: wrapped in src/mouselook.c */" % f,
                           s, count=1, flags=re.M)
            if n != 1:
                print(f"{fname}: definition of {f} not found", file=sys.stderr)
                bad = 1
            else:
                print(f"{fname}: {f} -> {f}_pad")
        p.write_text(s, encoding="utf-8")
    return bad


if __name__ == "__main__":
    sys.exit(main())
