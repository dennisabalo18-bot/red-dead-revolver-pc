"""Dubbing desk for Red Dead Revolver's voice lines, in the browser.

Lists every voice clip (stream0.dat, and the _PLII cut scenes of
stream1.dat) with its English transcript (faster-whisper, on the GPU when
there is one), a field for the line to record, the original to play, and a
drop/paste target for the new take. A take is saved to
modding/audio/reemplazos/<clip>.<ext>, where meter_audio.py picks it up;
a clip with a file there is "hecho".

Transcripts and the typed lines live in modding/audio/doblaje.json.

    python -P tools/doblaje.py [port]
"""
import http.server
import json
import os
import pathlib
import queue
import re
import struct
import subprocess
import sys
import threading
import urllib.parse
import webbrowser

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extraer_audio import GAME, dave_entries, stm_to_wav  # noqa: E402

TOOLS = pathlib.Path(__file__).resolve().parent
ROOT = TOOLS.parent / "modding"
AUDIO = ROOT / "audio"
REPL = AUDIO / "reemplazos"
MODS = ROOT / "mods"
DB = AUDIO / "doblaje.json"
EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus")
MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".flac": "audio/flac",
        ".m4a": "audio/mp4", ".aac": "audio/aac", ".opus": "audio/ogg"}

PJ = AUDIO / "personajes.json"

# Who speaks, from the clip name's first word. Names the game files spell
# out are kept; bare initials the files don't explain carry a "?" and can be
# renamed on the page (saved to personajes.json).
NOMBRES = {
    "red": "Red Harlow (protagonista)", "redfinal": "Red Harlow (final)", "youngred": "Red de niño",
    "rd": "RD (¿Red?)", "annie": "Annie Stokes", "anniestokes": "Annie Stokes", "jack": "Jack Swift",
    "jackswift": "Jack Swift", "gd": "General Diego", "griffin": "Gobernador Griffon", "darren": "Coronel Daren",
    "perry": "Profesor Perry", "pry": "Profesor Perry", "bessie": "Bad Bessie", "mrblack": "Mr. Black",
    "mrkelley": "Mr. Kelley", "mrkelly": "Mr. Kelley", "bloodytom": "Bloody Tom", "ugl": "Ugly Chris",
    "uglystreetfight2": "Ugly Chris", "uc": "UC (¿Ugly Chris?)", "pgj": "Pig Josh", "pig": "Pig (¿Pig Josh?)",
    "ogrady": "Sheriff O'Grady", "grady": "Grady (¿Sheriff O'Grady?)", "jebidahcole": "Jebidah Cole",
    "jeb": "Jeb (¿Jebidah Cole?)", "mathiuslampry": "Mathius Lampry", "mat": "Mat (¿Mathius Lampry?)",
    "cheryllynn": "Cheryl Lynn", "chryllynn": "Cheryl Lynn", "lilybelleparsons": "Lilybelle Parsons",
    "billycougar": "Billy Cougar", "vernewiggins": "Verne Wiggins", "hanzkenyon": "Hanz Kenyon",
    "earlweatherby": "Earl Weatherby", "ralphclover": "Ralph Clover", "oscarnavarro": "Oscar Navarro",
    "jasoncornet": "Jason Cornet", "claramay": "Clara May", "fallingstar": "Falling Star",
    "horse": "Caballo", "cow": "Vaca", "bull": "Toro", "bear": "Oso", "midget": "Enano",
    "strong": "Forzudo", "blind": "Viejo ciego", "driver": "Cochero (diligencia)", "barmaid": "Camarera",
    "bride": "Novia", "caboosewoman": "Mujer del vagón de cola", "indian": "Indio", "buf": "Soldado búfalo",
    "ranch": "Peones del rancho", "royal": "Público (gritos)", "barfight": "Pelea de bar (gritos)",
    "brft": "Pelea de bar (piano)", "gigolo": "Gigoló",
}
GENERICOS = {"cowboy": "Vaquero", "cowgirl": "Vaquera", "mexcowboy": "Vaquero mexicano", "dtroops": "Tropa de Diego",
             "union": "Soldado de la Unión", "guard": "Guardia", "bandit": "Bandido", "badguy": "Maleante",
             "bargirl": "Chica del bar", "dancinggirl": "Bailarina", "cbro": "Hermano Cornet",
             "cornetbro": "Hermano Cornet"}
pj_names = {}       # renames from the page


def personaje(stem):
    """(key, default name) of who speaks in the clip."""
    low = stem.lower()
    tok = re.split(r"[_\\/.]", low)[0]
    if "music" in low or tok in ("bowed", "bridge", "bullseye", "deathcam", "dueling", "mansint", "specialtackle"):
        return "musica", "Música y efectos (sin voz)"
    if tok in ("thats", "run"):
        return "sueltas", "Frases sueltas (¿quién?)"
    if "_plii" in low or tok.isdigit() or tok in ("xtra", "bomb"):
        return "escena", "Escena (varios personajes)"
    tok = re.sub(r"\d+$", "", tok) if re.fullmatch(r"(pry|pgj|ugl)\d+", tok) else tok
    if tok.startswith("ugl"):
        tok = "ugl"
    if tok.startswith("cornetbro"):
        tok = "cbro" + tok[9:]
    tok = {"diego": "gd", "anniestokes": "annie", "jackswift": "jack", "pry": "perry", "mrkelly": "mrkelley",
           "chryllynn": "cheryllynn"}.get(tok, tok)
    if tok in NOMBRES:
        return tok, NOMBRES[tok]
    m = re.fullmatch(r"([a-z]+?)(\d*)(f?)", tok)
    if m and m.group(1) in GENERICOS:
        return tok, " ".join(filter(None, (GENERICOS[m.group(1)], m.group(2).lstrip("0") or None,
                                             "(f)" if m.group(3) else None)))
    if tok in ("ab", "sbar", "san", "cp", "cr", "gw", "on", "ll", "pm", "mb", "sm", "gn", "sb", "mok", "roktoss"):
        return tok, tok.upper() + " (¿quién?)"
    return tok, tok.capitalize()


clips = {}          # key (lower stem) -> {n, arc, off, size, dur, pj}
order = []
db = {}             # key -> {"en": str, "es": str}
log = []            # keys whose transcript arrived, in order
lock = threading.Lock()
work = queue.Queue()
urgent = []
state = {"motor": "", "error": "", "activo": False, "meter": "", "metiendo": False}


def load_clips():
    for arc in ("stream0.dat", "stream1.dat"):
        p = GAME / arc
        if not p.is_file():
            continue
        with open(p, "rb") as f:
            for name, off, size, packed in dave_entries(f):
                stem = pathlib.Path(name.replace("\\", "/")).stem
                if arc != "stream0.dat" and "_plii" not in stem.lower():
                    continue
                if packed != size or stem.lower() in clips:
                    continue
                f.seek(off)
                h = f.read(0x20)
                if h[:4] != b"STMA":
                    continue
                rate, bits, ch, data = struct.unpack_from("<IIII", h, 0x0C)
                dur = data * 2 / ch / rate if rate and ch else 0
                clips[stem.lower()] = {"n": stem, "arc": arc, "off": off, "size": size, "dur": round(dur, 1),
                                       "pj": personaje(stem)}
                order.append(stem.lower())


def load_db():
    global db, pj_names
    try:
        db = json.loads(DB.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        db = {}
    try:
        pj_names = json.loads(PJ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pj_names = {}


def pj_table():
    """key -> name shown, renames over the defaults."""
    t = {}
    for c in clips.values():
        t[c["pj"][0]] = c["pj"][1]
    t.update({k: v for k, v in pj_names.items() if k in t})
    return t


def save_db():
    with lock:
        text = json.dumps(db, ensure_ascii=False, indent=0)
    tmp = DB.with_suffix(".tmp")
    AUDIO.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, DB)


def original(key):
    """The clip's WAV, extracted from its archive the first time."""
    c = clips[key]
    wav = AUDIO / pathlib.Path(c["arc"]).stem / (c["n"] + ".wav")
    if not wav.exists():
        wav.parent.mkdir(parents=True, exist_ok=True)
        with open(GAME / c["arc"], "rb") as f:
            f.seek(c["off"])
            stm_to_wav(f.read(c["size"]), wav)
    return wav


def take(key):
    for e in EXTS:
        for p in (REPL / (clips[key]["n"] + e), REPL / (key + e)):
            if p.exists():
                return p
    return None


def done_set():
    have = set()
    if REPL.is_dir():
        for p in REPL.rglob("*"):
            if p.suffix.lower() in EXTS:
                have.add(p.stem.lower())
    return have


def pcm16k(path):
    import numpy as np
    import wave
    with wave.open(str(path), "rb") as w:
        ch, rate = w.getnchannels(), w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    x = x.reshape(-1, ch).mean(1)
    n = int(len(x) * 16000 / rate)
    return np.interp(np.arange(n) * rate / 16000, np.arange(len(x)), x).astype(np.float32)


def transcriber():
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        state["error"] = "Falta faster-whisper: python -m pip install --user faster-whisper"
        return
    name = os.environ.get("DOBLAJE_MODELO", "small.en")
    model = None
    for dev, ct in (("cuda", "float16"), ("cpu", "int8")):
        try:
            model = WhisperModel(name, device=dev, compute_type=ct)
            model.transcribe(pcm16k(original(order[0])), language="en")
            state["motor"] = f"{name} en {'placa de video' if dev == 'cuda' else 'procesador'}"
            break
        except Exception as ex:      # noqa: BLE001
            model = None
            state["error"] = f"{dev}: {ex}"
    if not model:
        return
    state["error"] = ""
    pending = 0
    while True:
        with lock:
            key = urgent.pop() if urgent else None
        if key is None:
            try:
                key = work.get(timeout=1.0)
            except queue.Empty:
                state["activo"] = False
                if pending:
                    save_db()
                    pending = 0
                continue
        with lock:
            if db.get(key, {}).get("en") is not None:
                continue
        state["activo"] = True
        try:
            segs, _ = model.transcribe(pcm16k(original(key)), language="en", beam_size=5,
                                       condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segs).strip()
        except Exception as ex:      # noqa: BLE001
            text = ""
            state["error"] = f"{clips[key]['n']}: {ex}"
        with lock:
            db.setdefault(key, {})["en"] = text
            log.append(key)
        pending += 1
        if pending >= 50:
            save_db()
            pending = 0


def run_meter():
    state["metiendo"] = True
    state["meter"] = "Metiendo en el juego..."
    try:
        r = subprocess.run([sys.executable, "-P", str(TOOLS / "meter_audio.py"), str(GAME), str(REPL), str(MODS)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = (r.stdout + r.stderr).strip().splitlines()
        state["meter"] = "\n".join(lines[-12:])
    except Exception as ex:          # noqa: BLE001
        state["meter"] = f"Error: {ex}"
    state["metiendo"] = False


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def file(self, path):
        self.send(200, path.read_bytes(), MIME.get(path.suffix.lower(), "application/octet-stream"))

    def key(self, part):
        k = urllib.parse.unquote(part).lower()
        return k if k in clips else None

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        parts = u.path.strip("/").split("/")
        if u.path == "/":
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/clips":
            have = done_set()
            with lock:
                rows = [[clips[k]["n"], clips[k]["dur"], db.get(k, {}).get("en"), db.get(k, {}).get("es", ""),
                         k in have, clips[k]["arc"] != "stream0.dat", clips[k]["pj"][0]] for k in order]
                cur = len(log)
            return self.send(200, json.dumps({"rows": rows, "log": cur, "pj": pj_table()}, ensure_ascii=False))
        if u.path == "/api/estado":
            since = int(urllib.parse.parse_qs(u.query).get("desde", ["0"])[0])
            with lock:
                news = [[clips[k]["n"], db[k].get("en")] for k in log[since:]]
                cur = len(log)
                hechas = sum(1 for k in order if db.get(k, {}).get("en") is not None)
            return self.send(200, json.dumps({"nuevas": news, "log": cur, "transcritas": hechas,
                                              "total": len(order), **state}, ensure_ascii=False))
        if len(parts) == 2 and parts[0] in ("orig", "nuevo"):
            k = self.key(parts[1])
            if not k:
                return self.send(404, "{}")
            p = original(k) if parts[0] == "orig" else take(k)
            return self.file(p) if p else self.send(404, "{}")
        self.send(404, "{}")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        parts = u.path.strip("/").split("/")
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if u.path == "/api/meter":
            if not state["metiendo"]:
                threading.Thread(target=run_meter, daemon=True).start()
            return self.send(200, "{}")
        if len(parts) == 3 and parts[:2] == ["api", "transcribir"]:
            k = self.key(parts[2])
            if k:
                with lock:
                    db.get(k, {}).pop("en", None)
                    urgent.append(k)
            return self.send(200, "{}")
        if len(parts) == 3 and parts[:2] == ["api", "texto"]:
            k = self.key(parts[2])
            if k:
                with lock:
                    db.setdefault(k, {})["es"] = body.decode("utf-8", "replace")
                save_db()
            return self.send(200, "{}")
        if len(parts) == 3 and parts[:2] == ["api", "personaje"]:
            k = urllib.parse.unquote(parts[2])
            name = body.decode("utf-8", "replace").strip()
            with lock:
                if name:
                    pj_names[k] = name
                else:
                    pj_names.pop(k, None)       # empty: back to the default
                text = json.dumps(pj_names, ensure_ascii=False, indent=0)
            AUDIO.mkdir(parents=True, exist_ok=True)
            PJ.write_text(text, encoding="utf-8")
            return self.send(200, json.dumps({"pj": pj_table()}, ensure_ascii=False))
        if len(parts) == 3 and parts[:2] == ["api", "subir"]:
            k = self.key(parts[2])
            ext = urllib.parse.parse_qs(u.query).get("ext", [".wav"])[0].lower()
            if not k or ext not in EXTS or not body:
                return self.send(400, json.dumps({"error": "Formato no admitido (wav, mp3, ogg, flac, m4a)"}))
            REPL.mkdir(parents=True, exist_ok=True)
            old = take(k)
            while old:
                old.unlink()
                old = take(k)
            (REPL / (clips[k]["n"] + ext)).write_bytes(body)
            return self.send(200, "{}")
        if len(parts) == 3 and parts[:2] == ["api", "quitar"]:
            k = self.key(parts[2])
            old = take(k) if k else None
            while old:
                old.unlink()
                old = take(k)
            return self.send(200, "{}")
        self.send(404, "{}")


PAGE = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Doblaje RDR</title>
<style>
:root{--bg:#1b1714;--panel:#262019;--line:#3a3128;--text:#eadfcf;--dim:#a3947f;--acc:#d9822b;--ok:#6fae5a;--bad:#c2553f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);padding:10px 16px;z-index:2}
h1{font-size:17px;margin:0 0 8px}h1 span{color:var(--dim);font-weight:400;font-size:13px;margin-left:8px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
input,select,button,textarea{font:inherit;color:var(--text);background:#14110e;border:1px solid var(--line);border-radius:6px;padding:6px 8px}
button{cursor:pointer;background:#33291f}button:hover{border-color:var(--acc)}button.pri{background:var(--acc);color:#1b1714;border-color:var(--acc);font-weight:600}
#q{flex:1;min-width:180px}.st{color:var(--dim);font-size:13px}.prog{height:4px;background:#14110e;border-radius:2px;margin-top:8px;overflow:hidden}.prog i{display:block;height:100%;background:var(--acc);width:0}
main{padding:8px 16px 40px}
.row{display:grid;grid-template-columns:28px minmax(160px,1.1fr) 2fr 2fr 190px;gap:10px;align-items:start;padding:8px;border-bottom:1px solid var(--line);border-radius:6px}
.row.sel{background:#2d251d;outline:1px solid var(--acc)}.row.drag{background:#3a2c1c}
.ok{color:var(--ok);font-size:18px}.no{color:var(--dim);font-size:18px}
.pjn{font-weight:600;color:var(--acc)}.ren{padding:0 5px;font-size:11px;background:none;border-color:transparent;color:var(--dim)}
.name{font-family:Consolas,monospace;font-size:12px;word-break:break-all}.dur{color:var(--dim);font-size:12px}
.en{white-space:pre-wrap}.en.empty{color:var(--dim);font-style:italic}
textarea{width:100%;min-height:38px;resize:vertical}
.acts{display:flex;flex-wrap:wrap;gap:4px}.acts button{padding:3px 7px;font-size:12px}
.more{margin:16px auto;display:block}#log{white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;color:var(--dim);margin-top:6px}
.hint{color:var(--dim);font-size:12px;margin-top:6px}
@media(max-width:800px){.row{grid-template-columns:24px 1fr}.row>*:nth-child(n+3){grid-column:1/-1}}
</style></head><body>
<header>
<h1>Doblaje de voces <span id="cnt"></span></h1>
<div class="bar">
<input id="q" placeholder="Buscar por nombre o por texto...">
<select id="pj"><option value="">Todos los personajes</option></select>
<select id="f"><option value="pend">Pendientes</option><option value="done">Hechas</option><option value="all">Todas</option></select>
<label class="st"><input type="checkbox" id="habla" checked> solo con habla</label>
<label class="st"><input type="checkbox" id="cine"> solo escenas</label>
<button class="pri" id="meter">Meter en el juego</button>
</div>
<div class="prog"><i id="pb"></i></div>
<div class="st" id="motor"></div>
<div class="hint">Elige una fila y pega el audio con Ctrl+V (archivo copiado en el Explorador), arrástralo encima o usa "Subir". Se guarda solo con el nombre correcto.</div>
<div id="log"></div>
</header>
<main id="list"></main>
<input type="file" id="pick" accept="audio/*,.wav,.mp3,.ogg,.flac,.m4a" hidden>
<script>
let rows=[],byName={},logPos=0,shown=150,sel=null,pjs={};
const $=s=>document.querySelector(s);
const esc=s=>(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function load(){const r=await (await fetch('/api/clips')).json();
 rows=r.rows.map(a=>({n:a[0],d:a[1],en:a[2],es:a[3],done:a[4],cine:a[5],pj:a[6]}));byName={};rows.forEach(x=>byName[x.n]=x);logPos=r.log;pjs=r.pj;pjMenu();draw();}
function pjMenu(){const cur=$('#pj').value,cnt={},hecho={};rows.forEach(x=>{cnt[x.pj]=(cnt[x.pj]||0)+1;if(x.done)hecho[x.pj]=(hecho[x.pj]||0)+1});
 const ks=Object.keys(cnt).sort((a,b)=>pjs[a].localeCompare(pjs[b],'es'));
 $('#pj').innerHTML='<option value="">Todos los personajes</option>'+ks.map(k=>`<option value="${esc(k)}">${esc(pjs[k])} (${hecho[k]||0}/${cnt[k]})</option>`).join('');$('#pj').value=cur;}
function talks(x){return x.pj!='musica'&&(x.en==null||/[a-z]{2}/i.test(x.en))}
function list(){const q=$('#q').value.trim().toLowerCase(),f=$('#f').value,h=$('#habla').checked,c=$('#cine').checked,p=$('#pj').value;
 return rows.filter(x=>(f=='all'||(f=='done')==x.done)&&(!p||x.pj==p)&&(!h||talks(x))&&(!c||x.cine)&&(!q||x.n.toLowerCase().includes(q)||pjs[x.pj].toLowerCase().includes(q)||(x.en||'').toLowerCase().includes(q)||(x.es||'').toLowerCase().includes(q)));}
function rowHtml(x){return `<div class="row${sel==x.n?' sel':''}" data-n="${esc(x.n)}">
<div class="${x.done?'ok':'no'}" title="${x.done?'Hecha':'Pendiente'}">${x.done?'✔':'○'}</div>
<div><div class="pjn">${esc(pjs[x.pj])} <button class="ren" data-a="ren" title="Cambiar el nombre de este personaje">✎</button></div><div class="name">${esc(x.n)}</div><div class="dur">${x.d}s${x.cine?' · escena':''}</div></div>
<div class="en${x.en?'':' empty'}">${x.en==null?'(sin transcribir)':(x.en||'(sin habla)')}</div>
<div><textarea placeholder="Texto a grabar (ej. tu traducción)">${esc(x.es)}</textarea></div>
<div class="acts"><button data-a="orig">▶ Original</button><button data-a="copy">Copiar texto</button>
<button data-a="up">Subir</button>${x.done?'<button data-a="nuevo">▶ Nuevo</button><button data-a="quitar">Quitar</button>':''}
<button data-a="tr">Transcribir</button></div></div>`}
function draw(){const l=list();const done=rows.filter(x=>x.done).length;
 $('#cnt').textContent=`${done} hechas de ${rows.length} · mostrando ${Math.min(shown,l.length)} de ${l.length}`;
 $('#list').innerHTML=l.slice(0,shown).map(rowHtml).join('')+(l.length>shown?'<button class="more" id="more">Mostrar más</button>':'');}
function redraw(n){const el=document.querySelector(`.row[data-n="${CSS.escape(n)}"]`);if(el){const t=document.createElement('div');t.innerHTML=rowHtml(byName[n]);el.replaceWith(t.firstChild)}
 const done=rows.filter(x=>x.done).length;$('#cnt').textContent=$('#cnt').textContent.replace(/^\d+ hechas/,done+' hechas');}
let player=new Audio();
function play(u){player.pause();player=new Audio(u+'?t='+Date.now());player.play()}
async function upload(n,file){const m=/\.[a-z0-9]+$/i.exec(file.name);const ext=m?m[0].toLowerCase():'.wav';
 const r=await fetch(`/api/subir/${encodeURIComponent(n)}?ext=${ext}`,{method:'POST',body:file});
 if(!r.ok){alert((await r.json()).error||'No se pudo guardar');return}
 byName[n].done=true;redraw(n);}
$('#list').addEventListener('click',async e=>{const row=e.target.closest('.row');if(!row)return;const n=row.dataset.n,x=byName[n];
 if(e.target.id=='more')return;
 if(sel!=n){const o=document.querySelector('.row.sel');if(o)o.classList.remove('sel');sel=n;row.classList.add('sel')}
 const a=e.target.dataset.a;if(!a)return;
 if(a=='orig')play('/orig/'+encodeURIComponent(n));
 if(a=='nuevo')play('/nuevo/'+encodeURIComponent(n));
 if(a=='copy'){await navigator.clipboard.writeText(x.es||x.en||'');e.target.textContent='Copiado';setTimeout(()=>e.target.textContent='Copiar texto',1200)}
 if(a=='up'){$('#pick').dataset.n=n;$('#pick').click()}
 if(a=='quitar'&&confirm('¿Quitar el audio nuevo de '+n+'?')){await fetch('/api/quitar/'+encodeURIComponent(n),{method:'POST'});x.done=false;redraw(n)}
 if(a=='ren'){const v=prompt('Nombre para todas las frases de "'+pjs[x.pj]+'" (vacío = el de antes):',pjs[x.pj]);if(v==null)return;
  const r=await (await fetch('/api/personaje/'+encodeURIComponent(x.pj),{method:'POST',body:v})).json();pjs=r.pj;pjMenu();draw()}
 if(a=='tr'){await fetch('/api/transcribir/'+encodeURIComponent(n),{method:'POST'});x.en=null;redraw(n)}});
document.addEventListener('click',e=>{if(e.target.id=='more'){shown+=150;draw()}});
$('#pick').addEventListener('change',e=>{const f=e.target.files[0];if(f)upload(e.target.dataset.n,f);e.target.value=''});
let tmr={};
$('#list').addEventListener('input',e=>{if(e.target.tagName!='TEXTAREA')return;const n=e.target.closest('.row').dataset.n;byName[n].es=e.target.value;
 clearTimeout(tmr[n]);tmr[n]=setTimeout(()=>fetch('/api/texto/'+encodeURIComponent(n),{method:'POST',body:byName[n].es}),600)});
$('#list').addEventListener('dragover',e=>{const r=e.target.closest('.row');if(r){e.preventDefault();r.classList.add('drag')}});
$('#list').addEventListener('dragleave',e=>{const r=e.target.closest('.row');if(r)r.classList.remove('drag')});
$('#list').addEventListener('drop',e=>{const r=e.target.closest('.row');if(!r)return;e.preventDefault();r.classList.remove('drag');
 const f=e.dataTransfer.files[0];if(f)upload(r.dataset.n,f)});
document.addEventListener('paste',e=>{if(!sel||e.target.tagName=='TEXTAREA'&&!e.clipboardData.files.length)return;const f=e.clipboardData.files[0];
 if(f){e.preventDefault();upload(sel,f)}});
['#q','#f','#pj','#habla','#cine'].forEach(s=>$(s).addEventListener('input',()=>{shown=150;draw()}));
$('#meter').onclick=()=>fetch('/api/meter',{method:'POST'});
async function poll(){try{const s=await (await fetch('/api/estado?desde='+logPos)).json();logPos=s.log;
 s.nuevas.forEach(([n,en])=>{if(byName[n]){byName[n].en=en;redraw(n)}});
 $('#pb').style.width=(100*s.transcritas/s.total)+'%';
 $('#motor').textContent=`Transcritas ${s.transcritas} de ${s.total}`+(s.motor?` · ${s.motor}`:' · cargando el reconocimiento de voz...')+(s.activo?' · trabajando':'')+(s.error?' · '+s.error:'');
 $('#log').textContent=s.meter||'';}catch(e){}setTimeout(poll,1500)}
load().then(poll);
</script></body></html>"""


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    load_clips()
    if not order:
        print(f"No encuentro stream0.dat en {GAME}")
        return 1
    load_db()
    for k in order:              # everything not yet transcribed, in order
        if db.get(k, {}).get("en") is None:
            work.put(k)
    threading.Thread(target=transcriber, daemon=True).start()
    for p in range(port, port + 20):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    else:
        print("No hay puerto libre")
        return 1
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"Doblaje: {url}  ({len(order)} clips). Cierra esta ventana para salir.")
    if not os.environ.get("DOBLAJE_SIN_NAVEGADOR"):
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    save_db()
    return 0


if __name__ == "__main__":
    sys.exit(main())
