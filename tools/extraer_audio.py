"""Extract Red Dead Revolver's streamed audio (voices, music, ambience) to WAV.

The disc's stream0.dat .. stream4.dat are "DAVE" archives (Rockstar San
Diego): a 16-byte header (magic, count, directory size, name table size),
the directory at 0x800 (16 bytes an entry: name offset, data offset, size,
packed size) and the name table right after it. Each file is an .stm:

    0x00  "STMA"
    0x08  interleave * channels (0x40 a channel)
    0x0C  sample rate
    0x10  bits per sample (4)
    0x14  channels
    0x18  data bytes
    0x800 data: DVI IMA ADPCM (high nibble first), 0x40-byte blocks
          alternating between the channels, one decoder state a channel
          carried across the whole file

stream0.dat holds the voice lines (8000+ clips); 1-4 music and ambience.

    python tools/extraer_audio.py [game_dir] [out_dir] [filter]

filter: only files whose name contains it (case-insensitive), e.g. "jack".
"""
import array
import os
import pathlib
import struct
import sys
import wave

# The game folder: RDR_JUEGO, or juego\ in the project (a link to it; see README).
GAME = pathlib.Path(os.environ.get("RDR_JUEGO") or pathlib.Path(__file__).resolve().parent.parent / "juego")
OUT = pathlib.Path(__file__).resolve().parent.parent / "modding" / "audio"
ARCHIVES = ["stream0.dat", "stream1.dat", "stream2.dat", "stream3.dat", "stream4.dat"]

STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50,
        55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253,
        279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060,
        1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
        4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487,
        12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
INDEX = [-1, -1, -1, -1, 2, 4, 6, 8] * 2

# Per (predictor-independent) nibble and step index: the delta and next index.
DELTA = [[0] * 16 for _ in range(89)]
for _i, _s in enumerate(STEP):
    for _n in range(16):
        _d = _s >> 3
        if _n & 4: _d += _s
        if _n & 2: _d += _s >> 1
        if _n & 1: _d += _s >> 2
        DELTA[_i][_n] = -_d if _n & 8 else _d
NEXT = [[max(0, min(88, i + INDEX[n])) for n in range(16)] for i in range(89)]


def decode_dvi(data, state):
    """Bytes of one channel, high nibble first; state = [predictor, index]."""
    p, i = state
    out = array.array("h")
    app = out.append
    for b in data:
        for n in (b >> 4, b & 15):
            p += DELTA[i][n]
            if p > 32767: p = 32767
            elif p < -32768: p = -32768
            i = NEXT[i][n]
            app(p)
    state[0], state[1] = p, i
    return out


def stm_to_wav(blob, path):
    if blob[:4] != b"STMA":
        return False
    rate, bits, ch, size = struct.unpack_from("<IIII", blob, 0x0C)
    if bits != 4 or ch not in (1, 2) or not rate:
        return False
    data = blob[0x800:0x800 + size]
    il = 0x40
    states = [[0, 0] for _ in range(ch)]
    chans = [array.array("h") for _ in range(ch)]
    for off in range(0, len(data), il * ch):
        for c in range(ch):
            chans[c].extend(decode_dvi(data[off + c * il:off + (c + 1) * il], states[c]))
    n = min(len(x) for x in chans)
    if ch == 1:
        pcm = chans[0]
    else:
        pcm = array.array("h", bytes(n * 4))
        pcm[0::2] = chans[0][:n]
        pcm[1::2] = chans[1][:n]
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return True


def dave_entries(f):
    magic, count, dsz, nsz = struct.unpack("<4sIII", f.read(16))
    if magic != b"DAVE":
        return []     # "Dave": packed names, not an audio archive here
    f.seek(0x800)
    d = f.read(dsz)
    names = f.read(nsz)
    out = []
    for k in range(count):
        no, off, size, packed = struct.unpack_from("<IIII", d, k * 16)
        end = names.index(b"\0", no)
        out.append((names[no:end].decode("latin-1"), off, size, packed))
    return out


def main():
    game = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else GAME
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else OUT
    flt = sys.argv[3].lower() if len(sys.argv) > 3 else ""
    total = 0
    for arc in ARCHIVES:
        p = game / arc
        if not p.is_file():
            print(f"No encuentro {p}")
            continue
        dest = out / p.stem
        with open(p, "rb") as f:
            ents = [e for e in dave_entries(f) if flt in e[0].lower()]
            print(f"{arc}: {len(ents)} archivos -> {dest}")
            if ents:
                dest.mkdir(parents=True, exist_ok=True)
            for k, (name, off, size, packed) in enumerate(ents, 1):
                wav = dest / (pathlib.Path(name.replace("\\", "/")).stem + ".wav")
                if wav.exists():
                    continue
                if packed != size:
                    print(f"  comprimido, se omite: {name}")
                    continue
                f.seek(off)
                if stm_to_wav(f.read(size), wav):
                    total += 1
                else:
                    print(f"  formato desconocido, se omite: {name}")
                if k % 500 == 0:
                    print(f"  {k}/{len(ents)}")
    print(f"Listo: {total} WAV nuevos en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
