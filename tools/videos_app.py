"""A window with the game's cutscenes: a button upscales one with SeedVR2.

Each row is a video of bik\\ with its length, an estimate of how long it
takes (frames x the last measured seconds a frame) and a green tick once
modding/videos_mejorados/<name>.mp4 exists. "Reescalar" does the whole job
(videos_seedvr2.process: frames, SeedVR2 in ComfyUI, the mp4 with its audio,
only in videos_mejorados). One video at a time; pressing more
buttons queues them. "Detener" stops it and keeps what was done.

With --60 the same window takes the upscaled videos to 60 fps with RIFE and
deband (videos_60fps.process; tick = modding/videos_60fps/<name>.mp4). Those
stay out of the game until "Poner los 60 fps en el juego"; "Volver a 30 fps"
undoes it.

    pythonw tools/videos_app.py         (modding/Mejorar videos.bat)
    pythonw tools/videos_app.py --60    (modding/Videos 60 fps.bat)
"""
import collections
import json
import os
import pathlib
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import videos_60fps as v60  # noqa: E402
import videos_seedvr2 as vs  # noqa: E402

INFO = vs.DONE / "info.json"    # frames and fps of each .bik, so the window opens fast
GREEN, RED, GREY = "#1a9a3a", "#c0392b", "#777777"


class Job:
    """What the window does to a video."""
    def __init__(self, title, done_dir, verb, process, speed, comfy, sources):
        self.title, self.done_dir, self.verb, self.process = title, done_dir, verb, process
        self.speed, self.comfy, self.sources = speed, comfy, sources


SEEDVR2 = Job("mejorar videos (SeedVR2)", vs.DONE, "Reescalar", vs.process, vs.seconds_per_frame, True,
              lambda: [p.stem for p in vs.BIK.glob("*.bik")])
RIFE60 = Job("videos a 60 fps (RIFE + deband)", v60.OUT, "Pasar a 60", v60.process, v60.seconds_per_frame, False,
             lambda: [p.stem for p in v60.SRC.glob("*.mp4")])


def human(seconds):
    m = round(seconds / 60)
    if m < 1:
        return "< 1 min"
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d} min"


def load_info(names):
    try:
        info = json.loads(INFO.read_text())
    except (OSError, ValueError):
        info = {}
    missing = [n for n in names if n not in info]
    for n in missing:
        info[n] = vs.probe(vs.BIK / f"{n}.bik")
    if missing:
        vs.DONE.mkdir(parents=True, exist_ok=True)
        INFO.write_text(json.dumps(info))
    return info


class Row:
    def __init__(self, app, parent, r, name, frames, fps):
        self.app, self.name, self.frames = app, name, frames
        num, den = (fps.split("/") + ["1"])[:2]
        secs = frames * float(den) / float(num)
        self.tick = tk.Label(parent, width=2, font=("Segoe UI", 13, "bold"), fg=GREEN)
        self.tick.grid(row=r, column=0, padx=(8, 2))
        tk.Label(parent, text=name, font=("Segoe UI", 10, "bold"), anchor="w", width=11).grid(row=r, column=1, sticky="w")
        tk.Label(parent, text=f"{int(secs // 60)}:{int(secs % 60):02d}", fg=GREY, width=6).grid(row=r, column=2)
        self.est = tk.Label(parent, fg=GREY, width=11)
        self.est.grid(row=r, column=3)
        self.bar = ttk.Progressbar(parent, length=150, maximum=max(1, frames))
        self.bar.grid(row=r, column=4, padx=6)
        self.status = tk.Label(parent, anchor="w", width=30, fg=GREY)
        self.status.grid(row=r, column=5, sticky="w")
        self.button = ttk.Button(parent, width=11, command=lambda: app.press(name))
        self.button.grid(row=r, column=6, padx=(4, 8), pady=2)
        self.refresh()

    def done(self):
        return (self.app.job.done_dir / f"{self.name}.mp4").is_file()

    def refresh(self, status=None, color=GREY):
        done = self.done()
        self.tick.config(text="✔" if done else "")
        self.est.config(text=human(self.frames * self.app.job.speed()))
        if self.app.current == self.name:
            self.button.config(text="Detener")
        elif self.name in self.app.waiting:
            self.button.config(text="Quitar")
            status, color = status or "en cola", color
        else:
            self.button.config(text="Rehacer" if done else self.app.job.verb)
            if status is None:
                status = "listo" if done else ""
                color = GREEN if done else GREY
                self.bar.config(value=self.frames if done else 0)
        if status is not None:
            self.status.config(text=status, fg=color)


class App:
    def __init__(self, root, job):
        self.root, self.job = root, job
        self.rows = {}
        self.waiting = collections.deque()
        self.current = None
        self.stop_flag = threading.Event()
        self.events = queue.Queue()
        self.wake = threading.Event()
        root.title(f"Red Dead Revolver - {job.title}")
        root.geometry("900x720")
        root.protocol("WM_DELETE_WINDOW", self.close)

        top = tk.Frame(root)
        top.pack(fill="x", padx=10, pady=8)
        self.comfy = tk.Label(top, font=("Segoe UI", 10, "bold"))
        self.comfy.pack(side="left")
        job.done_dir.mkdir(parents=True, exist_ok=True)
        ttk.Button(top, text="Abrir carpeta", command=lambda: os.startfile(job.done_dir)).pack(side="right")
        if job is RIFE60:
            ttk.Button(top, text="Volver a 30 fps", command=self.back_to_30).pack(side="right", padx=4)
            ttk.Button(top, text="Poner los 60 fps en el juego", command=self.put_in_game).pack(side="right", padx=4)
        self.total = tk.Label(top, fg=GREY)
        self.total.pack(side="right", padx=12)
        if job is SEEDVR2:
            help_text = ("Un video a la vez: los botones que aprietes mientras trabaja quedan en cola. "
                         "Detener guarda lo hecho; al volver a reescalarlo sigue desde ahi.")
        else:
            help_text = ("Un video a la vez, de los ya mejorados (videos_mejorados). Quedan en videos_60fps: el juego "
                         "no los usa hasta apretar 'Poner los 60 fps en el juego'. Detener descarta ese video.")
        tk.Label(root, text=help_text, fg=GREY, anchor="w", justify="left", wraplength=860).pack(fill="x", padx=10)

        box = tk.Frame(root)
        box.pack(fill="both", expand=True, padx=4, pady=6)
        canvas = tk.Canvas(box, highlightthickness=0)
        scroll = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        self.table = tk.Frame(canvas)
        self.table.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.table, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-e.delta // 120, "units"))
        for c, h in enumerate(("", "Video", "Duracion", "Tarda aprox.", "", "Estado", "")):
            tk.Label(self.table, text=h, font=("Segoe UI", 9, "bold")).grid(row=0, column=c)
        self.loading = tk.Label(self.table, text="leyendo los videos...", fg=GREY)
        self.loading.grid(row=1, column=1, columnspan=5, pady=20)

        threading.Thread(target=self.read_videos, daemon=True).start()
        threading.Thread(target=self.worker, daemon=True).start()
        if job.comfy:
            threading.Thread(target=self.watch_comfy, daemon=True).start()
        self.root.after(200, self.pump)

    # -- threads; they only talk to the window through self.events --
    def read_videos(self):
        names = sorted(self.job.sources())
        self.events.put(("videos", {n: v for n, v in load_info(names).items() if n in names}))

    def watch_comfy(self):
        while True:
            try:
                vs.api("/system_stats")
                ok = True
            except OSError:
                ok = False
            self.events.put(("comfy", ok))
            threading.Event().wait(5)

    def worker(self):
        while True:
            self.wake.wait()
            self.wake.clear()
            while True:
                name = self.events_take()
                if name is None:
                    break
                self.stop_flag.clear()

                def progress(text, done, total, left, name=name):
                    self.events.put(("progress", name, text, done, left))
                try:
                    self.job.process(name, progress, self.stop_flag.is_set)
                    self.events.put(("finished", name, "listo", GREEN))
                except vs.Stopped:
                    kept = "lo hecho queda guardado" if self.job.comfy else "descartado"
                    self.events.put(("finished", name, f"detenido ({kept})", GREY))
                except OSError as e:
                    text = f"ComfyUI: {e}" if self.job.comfy else f"error: {e}"
                    self.events.put(("finished", name, text[:60], RED))
                except Exception as e:  # noqa: BLE001 - shown in the row
                    self.events.put(("finished", name, f"error: {e}"[:60], RED))

    def events_take(self):
        """The next queued video, made current (under the window's lock: the deque)."""
        try:
            name = self.waiting.popleft()
        except IndexError:
            self.current = None
            return None
        self.current = name
        self.events.put(("started", name))
        return name

    # -- window side --
    def pump(self):
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            kind = ev[0]
            if kind == "videos":
                self.loading.destroy()
                info = ev[1]
                for r, name in enumerate(sorted(info, key=lambda n: info[n][0]), 1):
                    self.rows[name] = Row(self, self.table, r, name, *info[name])
            elif kind == "comfy":
                self.comfy.config(text="● ComfyUI abierto" if ev[1] else "● ComfyUI cerrado: abrilo antes de reescalar",
                                  fg=GREEN if ev[1] else RED)
            elif kind == "started":
                self.rows[ev[1]].refresh("empezando...", "black")
            elif kind == "progress":
                _, name, text, done, left = ev
                row = self.rows[name]
                row.bar.config(value=done)
                row.status.config(text=text + (f", faltan ~{human(left)}" if left else ""), fg="black")
            elif kind == "finished":
                _, name, text, color = ev
                if self.current == name:
                    self.current = None
                self.rows[name].refresh(text, color)
                for other in self.rows.values():
                    if other.name != name:
                        other.refresh()
            self.update_total()
        self.root.after(200, self.pump)

    def update_total(self):
        left = [r for r in self.rows.values() if not r.done()]
        if self.rows:
            self.total.config(text=f"{len(self.rows) - len(left)}/{len(self.rows)} listos, faltan ~"
                                   f"{human(sum(r.frames for r in left) * self.job.speed())} en total")

    def press(self, name):
        row = self.rows[name]
        if self.current == name:
            self.stop_flag.set()
            row.status.config(text="deteniendo (hasta ~30 s)..." if self.job.comfy else "deteniendo...",
                              fg="black")
            return
        if name in self.waiting:
            self.waiting.remove(name)
        else:
            if row.done() and not messagebox.askyesno("Rehacer", f"{name} ya esta hecho. Hacerlo de nuevo?"):
                return
            self.waiting.append(name)
            self.wake.set()
        row.refresh()

    def put_in_game(self):
        names = [p.stem for p in v60.OUT.glob("*.mp4")]
        if not names:
            messagebox.showinfo("60 fps", "Todavia no hay videos a 60 fps.")
            return
        if messagebox.askyesno("Poner en el juego", f"Reemplazar en mods\\videos estos {len(names)} videos por su "
                               f"version de 60 fps?\n\n{', '.join(names)}\n\nLos de 30 fps quedan en videos_30fps."):
            v60.put_in_game()
            messagebox.showinfo("Listo", "El juego ya usa los videos de 60 fps.")

    def back_to_30(self):
        if messagebox.askyesno("Volver a 30 fps", "Poner en mods\\videos la version de 30 fps de los videos "
                               "que estan a 60? Los de 60 fps no se borran."):
            v60.back_to_30()
            messagebox.showinfo("Listo", "El juego vuelve a usar los videos de 30 fps.")

    def close(self):
        if self.current and not messagebox.askyesno(
                "Salir", f"Se esta mejorando {self.current}. Detenerlo y salir? Lo hecho queda guardado."):
            return
        if self.current:
            self.stop_flag.set()
            if self.job.comfy:
                try:
                    vs.api("/interrupt", {})
                except OSError:
                    pass
            else:
                threading.Event().wait(2)  # the worker kills RIFE within a second
        self.root.destroy()


def main():
    try:
        root = tk.Tk()
        App(root, RIFE60 if "--60" in sys.argv else SEEDVR2)
        root.mainloop()
    except Exception:  # pythonw has no console: leave the error where it can be read
        import traceback
        vs.DONE.mkdir(parents=True, exist_ok=True)
        (vs.DONE / "error_app.txt").write_text(traceback.format_exc())
        messagebox.showerror("Mejorar videos", "Fallo la aplicacion:\n" + traceback.format_exc()[-600:])


if __name__ == "__main__":
    main()
