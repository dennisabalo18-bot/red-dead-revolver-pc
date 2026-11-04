"""An upscaled cutscene to 60 fps with RIFE, debanded, for the game.

Takes modding/videos_mejorados/<name>.mp4 (SeedVR2's, 29.97 fps), puts a
RIFE frame between every two (rife_v4.26 from ComfyUI's models; ComfyUI
need not be open, this runs with its Python), smooths the colour steps
(ffmpeg deband) and writes modding/videos_60fps/<name>.mp4 with the same
audio. Across a scene cut RIFE would blend two shots, so there the new
frame repeats the previous one. The 30 fps file is copied to
modding/videos_30fps first; --poner copies the result into mods/videos.
tools/videos_app.py --60 is the window that does this a video at a time.

    python tools/videos_60fps.py titles [--poner] [--parejo]

--parejo: smooths a source's hitches (a frame a step early, then repeated).
"""
import pathlib
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from videos_seedvr2 import Stopped  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMFY = pathlib.Path(r"C:\ComfyUI-Easy-Install\ComfyUI-Easy-Install")
MODEL = COMFY / "ComfyUI" / "models" / "frame_interpolation" / "rife_v4.26.safetensors"
SRC = ROOT / "modding" / "videos_mejorados"
OUT = ROOT / "modding" / "videos_60fps"
KEEP = ROOT / "modding" / "videos_30fps"
GAME = ROOT / "modding" / "mods" / "videos"
WORK = ROOT / "modding" / "videos_escalado"
DEBAND = "deband=1thr=0.015:2thr=0.015:3thr=0.015:range=16:blur=1"
SPEED = OUT / "velocidad.txt"  # last measured seconds a (30 fps) frame, for the estimates
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flashing under pythonw
CUT = 40.0      # mean difference (0-255, at 90x60) above which two frames are a scene cut

# Runs inside ComfyUI's Python (torch and its RIFE code): frames in, frames out.
RIFE = r'''
import sys, pathlib, numpy as np, torch
from PIL import Image
import comfy.utils
from comfy_extras.nodes_frame_interpolation import FrameInterpolationModelLoader
src, dst, model_path, cut = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3], float(sys.argv[4])
model = FrameInterpolationModelLoader._detect_and_load(comfy.utils.load_torch_file(model_path, safe_load=True))
model = model.eval().half().cuda()
align = getattr(model, "pad_align", 1)
files = sorted(src.glob("*.png"))
def load(p):
    img = Image.open(p).convert("RGB")
    small = np.asarray(img.resize((90, 60)), float)
    t = torch.from_numpy(np.array(img)).cuda().half().permute(2, 0, 1)[None] / 255
    H, W = t.shape[2:]
    return torch.nn.functional.pad(t, (0, (-W) % align, 0, (-H) % align), mode="reflect"), small, H, W
def save(t, i):
    a = (t[0, :, :H, :W].float().clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255 + 0.5).astype(np.uint8)
    Image.fromarray(a).save(dst / f"{i:06d}.png", compress_level=1)
# rdr-port: a source with a hitch (one frame a step early, the next its
# repeat, as in rslogo) gets that frame redrawn halfway between its
# neighbours: smooth instead of a jolt every so often (--parejo).
early = set()
if len(sys.argv) > 5 and sys.argv[5] == "1":
    sm = [np.asarray(Image.open(p).convert("RGB").resize((90, 60)), float) for p in files]
    d = [np.abs(sm[i + 1] - sm[i]).mean() for i in range(len(sm) - 1)]
    for k in range(1, len(d)):
        local = float(np.median(d[max(0, k - 10):k + 10]))
        if local > 0.05 and d[k - 1] > 1.7 * local and d[k] < 0.5 * local and d[k - 1] < cut:
            early.add(k)
    print(f"  {len(early)} saltos corregidos", flush=True)
prev, prev_small, H, W = load(files[0])
n = 1; save(prev, n); cuts = 0
with torch.no_grad():
    for k, f in enumerate(files[1:], 2):
        cur, small, _, _ = load(f)
        if k - 1 in early and k < len(files):
            with torch.no_grad():
                cur = model(prev, load(files[k])[0], timestep=0.5)
        if np.abs(small - prev_small).mean() > cut:
            mid = prev; cuts += 1
        else:
            mid = model(prev, cur, timestep=0.5)
        n += 1; save(mid, n)
        n += 1; save(cur, n)
        prev, prev_small = cur, small
        if k % 25 == 0:
            print(f"  RIFE {k}/{len(files)}", flush=True)
print(f"  RIFE listo: {len(files)} -> {n} frames, {cuts} cortes de escena", flush=True)
'''


def seconds_per_frame():
    try:
        return float(SPEED.read_text())
    except (OSError, ValueError):
        return 0.31             # titles on the RTX 5070


def put_in_game():
    """The 60 fps videos into mods/videos; their names."""
    done = sorted(OUT.glob("*.mp4"))
    for f in done:
        shutil.copyfile(f, GAME / f.name)
    return [f.stem for f in done]


def back_to_30():
    """mods/videos back to the 30 fps upscaled videos; their names."""
    done = sorted(OUT.glob("*.mp4"))
    for f in done:
        src = KEEP / f.name if (KEEP / f.name).is_file() else SRC / f.name
        shutil.copyfile(src, GAME / f.name)
    return [f.stem for f in done]


def process(name, progress=None, stop=None, even=False):
    """One video; progress(text, done frames, total, seconds left) as it goes, stop() true cancels."""
    say = progress or (lambda text, done, total, left: print(f"{name}: {text}", flush=True))
    src = SRC / f"{name}.mp4"
    work = WORK / f"{name}_60fps"
    f30, f60 = work / "f30", work / "f60"
    shutil.rmtree(work, ignore_errors=True)
    f30.mkdir(parents=True)
    f60.mkdir()
    KEEP.mkdir(parents=True, exist_ok=True)
    if not (KEEP / src.name).is_file():
        shutil.copyfile(src, KEEP / src.name)
    say("separando frames", 0, 1, None)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), str(f30 / "%06d.png")], check=True,
                   creationflags=NO_WINDOW)
    total = len(list(f30.glob("*.png")))
    script = work / "rife_run.py"
    script.write_text(RIFE)
    t0 = time.time()
    proc = subprocess.Popen([str(COMFY / "python_embeded" / "python.exe"), "-s", str(script), str(f30), str(f60),
                             str(MODEL), str(CUT), "1" if even else "0"], cwd=COMFY / "ComfyUI", stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace",
                            creationflags=NO_WINDOW)
    tail = []
    reader = threading.Thread(target=lambda: tail.extend(proc.stdout), daemon=True)
    reader.start()
    while proc.poll() is None:
        if stop and stop():
            proc.kill()
            proc.wait()
            shutil.rmtree(work, ignore_errors=True)
            raise Stopped()
        marks = [line for line in tail if line.startswith("  RIFE ") and "/" in line]
        done = int(marks[-1].split()[1].split("/")[0]) if marks else 0
        if done:
            rate = (time.time() - t0) / done
            say(f"RIFE {done}/{total} frames", done, total, (total - done) * rate)
        time.sleep(1)
    reader.join()
    if proc.returncode:
        raise RuntimeError("RIFE fallo: " + "".join(tail[-3:]).strip()[-200:])
    OUT.mkdir(parents=True, exist_ok=True)
    SPEED.write_text(f"{(time.time() - t0) / total:.2f}")
    dst = OUT / f"{name}.mp4"
    say("armando el video", total, total, None)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "60000/1001", "-i", str(f60 / "%06d.png"),
                    "-i", str(src), "-map", "0:v", "-map", "1:a?", "-vf", DEBAND, "-c:v", "libx264",
                    "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
                    str(dst)], check=True, creationflags=NO_WINDOW)
    shutil.rmtree(work)
    say("listo", total, total, 0)
    return dst


def main(args):
    for name in (a for a in args if not a.startswith("--")):
        dst = process(name, even="--parejo" in args)
        if "--poner" in args:
            shutil.copyfile(dst, GAME / dst.name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
