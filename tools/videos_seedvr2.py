"""The game's cutscenes upscaled with SeedVR2 through ComfyUI, frame by frame.

Each Bink video (bik\\, 720x480 at 29.97 fps) is cut into PNG frames with
ffmpeg, the frames go to ComfyUI (must be open, http://127.0.0.1:8188) in
chunks of CHUNK through SeedVR2's video node, which upscales several frames
together so they don't flicker. Each chunk loads CONTEXT frames before it
and drops them, so chunk seams don't jump. The upscaled frames and the
video's own audio are joined into modding/videos_mejorados/<name>.mp4, and
only there: mods/videos (what the game plays) is left alone. Then its work
files are deleted. tools/videos_app.py is the
window that does this a video at a time.

Resumable: a chunk already done is skipped, so it can be stopped (Ctrl+C)
and run again. Work files in modding/videos_escalado/<name>/.

    python tools/videos_seedvr2.py              all the videos, shortest first
    python tools/videos_seedvr2.py bridge01     only these
    python tools/videos_seedvr2.py --lista      durations, nothing processed
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
# The game folder: RDR_JUEGO, or juego\ in the project (a link to it; see README).
GAME = pathlib.Path(os.environ.get("RDR_JUEGO") or pathlib.Path(__file__).resolve().parent.parent / "juego")
BIK = GAME / "bik"
WORK = ROOT / "modding" / "videos_escalado"
DONE = ROOT / "modding" / "videos_mejorados"   # the finished videos; one here = ready
COMFY = "http://127.0.0.1:8188"

MODEL = "seedvr2_ema_3b_fp8_e4m3fn.safetensors"  # the one of the image workflow
RESOLUTION = 960        # short side: 480 x2, the same as upscale_by 2.0
BATCH = 21              # frames SeedVR2 sees together (4n+1)
CHUNK = 84              # frames per ComfyUI job, 4 batches
CONTEXT = 4             # frames before the chunk loaded and dropped
SEED = 4025834193
SPEED = DONE / "velocidad.txt"  # last measured seconds a frame, for the estimates


class Stopped(Exception):
    pass


def seconds_per_frame():
    try:
        return float(SPEED.read_text())
    except (OSError, ValueError):
        return 2.3              # coach02 on the RTX 5070
VAE_TILE = 512          # px of the VAE tiles: 10.4 GB peak; 768 fills the 12 GB and runs 6x slower
VAE_OVERLAP = 32        # px the tiles share: 32 is 8% faster than 64, no seam seen


def api(path, data=None):
    req = urllib.request.Request(COMFY + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    return json.loads(body) if body.strip() else {}  # /interrupt and /queue answer with nothing


def probe(path):
    """(frames, fps string) of the video."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-count_packets",
                          "-show_entries", "stream=nb_read_packets,r_frame_rate", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    return int(out[1]), out[0]


def graph(frames_dir, skip, cap, drop):
    """The ComfyUI job: frames skip..skip+cap, upscaled, the first `drop` thrown away."""
    return {
        "1": {"class_type": "VHS_LoadImagesPath",
              "inputs": {"directory": str(frames_dir), "skip_first_images": skip, "image_load_cap": cap,
                         "select_every_nth": 1}},
        "2": {"class_type": "SeedVR2LoadDiTModel", "inputs": {"model": MODEL, "device": "cuda:0", "cache_model": True, "offload_device": "cpu"}},
        # Tiled: 21 frames at 1440x960 don't fit 12 GB, and spilling to RAM takes minutes a batch.
        "3": {"class_type": "SeedVR2LoadVAEModel",
              "inputs": {"model": "ema_vae_fp16.safetensors", "device": "cuda:0", "cache_model": True, "offload_device": "cpu", "encode_tiled": True,
                         "encode_tile_size": VAE_TILE, "encode_tile_overlap": VAE_OVERLAP, "decode_tiled": True,
                         "decode_tile_size": VAE_TILE, "decode_tile_overlap": VAE_OVERLAP}},
        "4": {"class_type": "SeedVR2VideoUpscaler",
              "inputs": {"image": ["1", 0], "dit": ["2", 0], "vae": ["3", 0], "seed": SEED,
                         "resolution": RESOLUTION, "max_resolution": 0, "batch_size": BATCH,
                         "uniform_batch_size": True, "color_correction": "lab", "temporal_overlap": 2,
                         "offload_device": "cpu"}},
        "5": {"class_type": "ImageFromBatch", "inputs": {"image": ["4", 0], "batch_index": drop, "length": cap - drop}},
        # PreviewImage: ComfyUI's temp folder, emptied when it restarts.
        "6": {"class_type": "PreviewImage", "inputs": {"images": ["5", 0]}},
    }


def cancel(pid):
    """Stop the job and wait until ComfyUI has let it go. SeedVR2 looks at the
    interrupt between its batches of 21, so this takes up to ~30 s."""
    api("/interrupt", {"prompt_id": pid})
    api("/queue", {"delete": [pid]})
    for _ in range(90):
        q = api("/queue")
        if not any(pid in item for item in q.get("queue_running", []) + q.get("queue_pending", [])):
            return
        time.sleep(1)


def run_chunk(frames_dir, start, n, total, dest, stop=None):
    """Frames start..start+n into dest/<index>.png; stop() true cancels the job."""
    skip = max(0, start - CONTEXT)
    drop = start - skip
    pid = api("/prompt", {"prompt": graph(frames_dir, skip, n + drop, drop)})["prompt_id"]
    while True:
        time.sleep(2)
        if stop and stop():
            cancel(pid)
            raise Stopped()
        h = api(f"/history/{pid}").get(pid)
        if not h:
            continue
        st = h.get("status", {})
        if st.get("status_str") == "error":
            msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
            raise RuntimeError(msgs[0][1].get("exception_message", "error") if msgs else "error en ComfyUI")
        if st.get("completed"):
            break
    imgs = h["outputs"]["6"]["images"]
    if len(imgs) != n:
        raise RuntimeError(f"ComfyUI devolvio {len(imgs)} frames, se esperaban {n}")
    for i, im in enumerate(imgs):
        q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"], "type": im["type"]})
        with urllib.request.urlopen(f"{COMFY}/view?{q}", timeout=60) as r:
            (dest / f"{start + i + 1:06d}.png").write_bytes(r.read())


def process(name, progress=None, stop=None):
    """The whole video; progress(text, done frames, total, seconds left) as it goes."""
    say = progress or (lambda text, done, total, left: print(f"  {name}: {text}", flush=True))
    src = BIK / f"{name}.bik"
    work = WORK / name
    frames_dir, up_dir = work / "frames", work / "escalado"
    total, fps = probe(src)
    if not frames_dir.is_dir() or len(list(frames_dir.glob("*.png"))) != total:
        say("separando frames", 0, total, None)
        shutil.rmtree(frames_dir, ignore_errors=True)
        frames_dir.mkdir(parents=True)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), str(frames_dir / "%06d.png")], check=True)
        total = len(list(frames_dir.glob("*.png")))
    up_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    done_now = 0
    for start in range(0, total, CHUNK):
        n = min(CHUNK, total - start)
        if all((up_dir / f"{start + i + 1:06d}.png").is_file() for i in range(n)):
            continue
        left = sum(1 for i in range(total) if not (up_dir / f"{i + 1:06d}.png").is_file())
        rate = (time.time() - t0) / done_now if done_now else seconds_per_frame()
        say(f"SeedVR2 {total - left}/{total} frames", total - left, total, left * rate)
        run_chunk(frames_dir, start, n, total, up_dir, stop)
        done_now += n
        DONE.mkdir(parents=True, exist_ok=True)
        SPEED.write_text(f"{(time.time() - t0) / done_now:.2f}")
    say("armando el video", total, total, None)
    DONE.mkdir(parents=True, exist_ok=True)
    dst = DONE / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", fps, "-i", str(up_dir / "%06d.png"),
                    "-i", str(src), "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "14", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", "-shortest", str(dst)],
                   check=True)
    shutil.rmtree(work)  # ~2.5 MB a frame; the mp4 is what stays
    say("listo", total, total, 0)


def main(args):
    names = sorted(p.stem for p in BIK.glob("*.bik"))
    want = [a for a in args if not a.startswith("--")]
    if want:
        bad = [w for w in want if w not in names]
        if bad:
            print("no existen:", ", ".join(bad))
            return 1
        names = want
    info = {n: probe(BIK / f"{n}.bik") for n in names}
    names.sort(key=lambda n: info[n][0])
    if "--lista" in args:
        for n in names:
            print(f"{n:12} {info[n][0]:6} frames")
        print(f"total {sum(v[0] for v in info.values())} frames")
        return 0
    try:
        api("/system_stats")
    except OSError:
        print("ComfyUI no responde en", COMFY, "- abrilo primero")
        return 1
    for i, n in enumerate(names, 1):
        print(f"[{i}/{len(names)}] {n} ({info[n][0]} frames)", flush=True)
        process(n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
