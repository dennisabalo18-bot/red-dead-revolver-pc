"""Put edited voice/music WAVs back into Red Dead Revolver's stream archives.

The WAVs go in modding/audio/reemplazos/ (subfolders allowed) under the
name extraer_audio.py gave them: 01_bull_close2_PLII.wav replaces
01_bull_close2_PLII.stm wherever it is. With ffmpeg on PATH any WAV (float
too) or .mp3/.ogg/.flac/.m4a is taken. Each is mixed to the clip's channel
count, resampled to its rate, and encoded as DVI IMA ADPCM the way
extraer_audio.py decodes it (high nibble first, 0x40-byte blocks per
channel, one decoder state a channel from 0/0).

Every archive with a replacement is rebuilt whole into modding/mods/ (the
disc's copy is not touched); with RECOMP_MODS_DIR pointing there the game
opens the rebuilt one instead. Entries keep their order and names, at
0x800-aligned offsets, uncompressed.

    python tools/meter_audio.py [game_dir] [wav_dir] [mods_dir]
"""
import array
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extraer_audio import ARCHIVES, GAME, INDEX, STEP, dave_entries  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent / "modding"
WAVS = ROOT / "audio" / "reemplazos"
MODS = ROOT / "mods"


def read_wav(path):
    """Samples as a list per channel (ints, 16-bit range), and the rate."""
    with wave.open(str(path), "rb") as w:
        ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        s = array.array("h", raw)
        if sys.byteorder != "little":
            s.byteswap()
        s = list(s)
    elif sw == 1:
        s = [(b - 128) << 8 for b in raw]
    elif sw == 3:
        s = [int.from_bytes(raw[i:i + 3], "little", signed=True) >> 8 for i in range(0, len(raw), 3)]
    elif sw == 4:
        s = [int.from_bytes(raw[i:i + 4], "little", signed=True) >> 16 for i in range(0, len(raw), 4)]
    else:
        raise ValueError(f"{sw * 8} bits")
    return [s[c::ch] for c in range(ch)], rate


def fit(chans, rate, want_ch, want_rate):
    """Mix/duplicate to want_ch channels, then resample linearly."""
    if len(chans) != want_ch:
        n = min(len(c) for c in chans)
        mono = [sum(c[i] for c in chans) // len(chans) for i in range(n)]
        chans = [mono] * want_ch
    if rate == want_rate:
        return chans
    out = []
    for c in chans:
        n = len(c) * want_rate // rate
        step = rate / want_rate
        r = []
        for i in range(n):
            x = i * step
            j = int(x)
            f = x - j
            a = c[j]
            b = c[j + 1] if j + 1 < len(c) else a
            r.append(int(a + (b - a) * f))
        out.append(r)
    return out


def encode_dvi(samples):
    """One channel to nibbles (high first), state from predictor 0, index 0."""
    p, i = 0, 0
    nib = []
    for s in samples:
        step = STEP[i]
        d = s - p
        n = 0
        if d < 0:
            n, d = 8, -d
        delta = step >> 3
        if d >= step:
            n |= 4; d -= step; delta += step
        if d >= step >> 1:
            n |= 2; d -= step >> 1; delta += step >> 1
        if d >= step >> 2:
            n |= 1; delta += step >> 2
        p = p - delta if n & 8 else p + delta
        p = max(-32768, min(32767, p))
        i = max(0, min(88, i + INDEX[n]))
        nib.append(n)
    if len(nib) & 1:
        nib.append(0)
    return bytes((nib[k] << 4) | nib[k + 1] for k in range(0, len(nib), 2))


def read_ffmpeg(path, ch, rate):
    """Any audio file (MP3, float WAV...) through ffmpeg, as 16-bit at the
    clip's rate and channels; None without ffmpeg."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    r = subprocess.run([exe, "-v", "error", "-i", str(path), "-f", "s16le", "-acodec", "pcm_s16le",
                        "-ac", str(ch), "-ar", str(rate), "-"], capture_output=True, check=True)
    s = array.array("h", r.stdout)
    if sys.byteorder != "little":
        s.byteswap()
    return [list(s[c::ch]) for c in range(ch)]


def build_stm(old, wav):
    """The .stm for wav, with old's header (rate, channels, interleave)."""
    rate, bits, ch, size, size2 = struct.unpack_from("<IIIII", old, 0x0C)
    chans = read_ffmpeg(wav, ch, rate)
    if chans is None:
        chans, wrate = read_wav(wav)
        chans = fit(chans, wrate, ch, rate)
    enc = [encode_dvi(c) for c in chans]
    il = 0x40
    blocks = (max(len(e) for e in enc) + il - 1) // il
    data = bytearray()
    for b in range(blocks):
        for e in enc:
            data += e[b * il:(b + 1) * il].ljust(il, b"\x00")
    hdr = bytearray(old[:0x800])
    struct.pack_into("<II", hdr, 0x18, len(data), len(data) + max(0, size2 - size))
    return bytes(hdr) + bytes(data)


def main():
    game = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else GAME
    wavs = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else WAVS
    mods = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else MODS
    if not wavs.is_dir():
        wavs.mkdir(parents=True, exist_ok=True)
        print(f"Pon los WAV editados en {wavs} (mismo nombre que al extraerlos).")
        return 0
    exts = {".wav"} | ({".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus"} if shutil.which("ffmpeg") else set())
    repl = {p.stem.lower(): p for p in wavs.rglob("*") if p.suffix.lower() in exts}
    if not repl:
        print(f"No hay WAV en {wavs}")
        return 0
    used = set()
    for arc in ARCHIVES:
        src = game / arc
        if not src.is_file():
            continue
        with open(src, "rb") as f:
            ents = dave_entries(f)
            hits = [e for e in ents if pathlib.Path(e[0].replace("\\", "/")).stem.lower() in repl]
            dst = mods / arc
            if not hits:
                if dst.exists():
                    dst.unlink()        # no replacements left: the disc's again
                continue
            print(f"{arc}: {len(hits)} reemplazos -> {dst}")
            f.seek(0)
            magic, count, dsz, nsz = struct.unpack("<4sIII", f.read(16))
            f.seek(0)
            head = bytearray(f.read(0x800 + dsz + nsz))
            mods.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_suffix(".tmp")
            with open(tmp, "wb") as o:
                o.write(head)
                order = sorted(range(count), key=lambda k: ents[k][1])
                for k in order:
                    name, off, size, packed = ents[k]
                    f.seek(off)
                    blob = f.read(packed)
                    stem = pathlib.Path(name.replace("\\", "/")).stem.lower()
                    if stem in repl and packed == size:
                        try:
                            blob = build_stm(blob, repl[stem])
                            size = packed = len(blob)
                            used.add(stem)
                            print(f"  {name}")
                        except Exception as ex:       # noqa: BLE001
                            print(f"  no se pudo usar {repl[stem].name}: {ex}")
                    pos = (o.tell() + 0x7FF) & ~0x7FF
                    o.write(b"\x00" * (pos - o.tell()))
                    o.write(blob)
                    struct.pack_into("<III", head, 0x800 + k * 16 + 4, pos, size, packed)
                o.write(b"\x00" * (((o.tell() + 0x7FF) & ~0x7FF) - o.tell()))
                o.seek(0)
                o.write(head)
            os.replace(tmp, dst)
    for stem in sorted(set(repl) - used):
        print(f"Sin clip con ese nombre: {repl[stem].name}")
    print(f"Listo: {len(used)} clips reemplazados en {mods}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
