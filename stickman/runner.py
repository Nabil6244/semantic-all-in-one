"""The Stickman runner: what the app page, make_video autorun and the command line all call.

plan(...)   = Generate: voice (+ word times), director, checker -> a plan dict. Nothing is drawn.
render(...) = Render: draw the frames, mix voice + music + effects, write the mp4.
No Gemini or other AI calls; the free Edge voice is the only network use (skipped with your own voice file).
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stickman import backgrounds, checker, csvplan, director, host as _host, looks, render as _render, voice  # noqa: E402

EDGE_VOICES = ("en-US-AndrewNeural", "en-US-AvaNeural", "en-US-BrianNeural", "en-US-EmmaNeural",
               "en-US-GuyNeural", "en-GB-RyanNeural", "en-GB-SoniaNeural")
Stopped = _render.Stopped


def split_title(text, title=None):
    lines = [l.strip() for l in (text or "").strip().splitlines()]
    if title is None and lines and lines[0] and lines[0][-1] not in ".?!" and len(lines) > 1:
        title, lines = lines[0], lines[1:]
    return title, " ".join(l for l in lines if l)


def _words(t):
    return [re.sub(r"[^a-z0-9]", "", w.lower()) for w in t.split()]


def size_for(shorts, preview):
    if shorts:
        return (720, 1280) if preview else (1080, 1920)
    return (1280, 720) if preview else (1920, 1080)


def plan(script=None, csv_path=None, voice_file=None, edge_voice=EDGE_VOICES[0], look=None, shorts=False,
         preview=False, title=None, log=print, host=None, paint=True, cancel=None):
    """script: a .txt path or the text itself. csv_path: an optional Stickman CSV (its lines are the narration).
    host: a puppet folder name (your picture in the corner), "" for none, None = the CSV's choice.
    paint: Meme look only, let Flow paint rooms not painted yet (False = drawn rooms for those)."""
    text = ""
    if script:
        sp = Path(str(script))
        text = sp.read_text(encoding="utf-8-sig") if "\n" not in str(script) and sp.is_file() else str(script)
    rows, problems = (csvplan.read(csv_path) if csv_path else (None, []))
    title, body = split_title(text, title)
    if rows:
        csv_body = csvplan.script_of(rows)
        if body and _words(body) != _words(csv_body):
            problems.append("the CSV lines are not the same words as the script: the CSV lines are spoken")
        body = csv_body
    if not body:
        raise ValueError("no narration: choose a script (.txt) or a Stickman CSV")
    look = look or csvplan.look_of(rows or []) or "ink_paper"
    looks.get(look)
    vo = voice.from_file(voice_file, log=log) if voice_file else voice.edge(body, edge_voice, log=log)
    spec = director.direct(body, vo["words"], vo["duration"], title=title, look=look,
                           size=size_for(shorts, preview), rows=rows, shorts=shorts)
    spec, notes, left = checker.repair(spec)
    spec["voice_path"] = vo["path"]
    host = csvplan.host_of(rows or []) if host is None else host
    if host:
        _host.setup(spec, host, vo["words"])
    painted, missing = {}, []
    if looks.get(look)["bg"] == "painted":
        need = [b["place"] for b in spec["beats"] if b.get("place")]
        if not spec["beats"][0].get("place"):
            need.insert(0, "void")
        need = list(dict.fromkeys(need))
        painted, missing = (backgrounds.paint(need, shorts, log=log, cancel=cancel) if paint
                            else (backgrounds.have(need, shorts), [p for p in need if p not in backgrounds.have(need, shorts)]))
        spec["backdrops"] = painted
        if missing:
            log(f"  Meme: no painted picture yet for {', '.join(missing)}: drawn rooms there (Generate again to retry Flow)")
    for p in problems:
        log(f"  CSV: {p}")
    for n in notes:
        log(f"  checker {n}")
    for p in left:
        log(f"  checker still sees: {p}")
    return {"spec": spec, "title": title or "", "seconds": spec["duration"], "beats": len(spec["beats"]),
            "notes": notes, "left": left, "problems": problems, "look": look, "shorts": shorts,
            "host": host or "", "painted": sorted(painted), "unpainted": missing}


def save(spec, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mix(spec, out_wav):
    from kids_audio import mixer
    a = spec.get("audio") or {}
    return mixer.mix({"voice": spec["voice_path"], "out": str(out_wav), "duration": spec["duration"],
                      "music": a.get("music"), "sfx": a.get("sfx") or [], "voice_lufs": -14, "target_lufs": -14})


def render(spec, out, progress=None, cancel=None, log=print, workers=None):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda f, m="": None)
    with tempfile.TemporaryDirectory() as wd:
        silent, wav = Path(wd) / "picture.mp4", Path(wd) / "mix.wav"
        _render.render(spec, silent, workers=workers, log=log, cancel=cancel,
                       progress=lambda f, m: say(0.03 + 0.87 * f, m))
        if cancel and cancel():
            raise Stopped("Stopped.")
        say(0.92, "mixing the sound")
        rep = _mix(spec, wav)
        if log:
            log(f"stickman: mix {rep.get('lufs')} LUFS, peak {rep.get('peak_dbfs')} dBFS, {rep.get('sfx')} effects")
        say(0.97, "writing the video")
        part = out.with_name(out.stem + ".part.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", str(part)], check=True, timeout=1800)
        part.replace(out)
    say(1.0, "done")
    return {"video": str(out), "seconds": spec["duration"]}
