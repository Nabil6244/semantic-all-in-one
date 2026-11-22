"""Prepper Host runner: what the app page, make_video and the command line call.

plan(...)   = Generate: voice + word times, director, then Flow makes the missing pictures (host pictures with his reference
              pictures, product photos, the thumbnail picture) and, if asked, the host's talking clips. -> a plan dict.
render(...) = Render: draw every shot, mix voice + effects (+ music), write the mp4 and a thumbnail .jpg next to it.
No Gemini. Flow pictures are free; talking clips use Flow video credits and are made once per host, then reused.

  python -m prepper_host.runner my.csv [--voice file.mp3] [--preview] [--no-flow] [--talking] [--out video.mp4]
"""
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prepper_host import csvplan, director, flow, host as _host, render as _render  # noqa: E402

EDGE_VOICES = ("en-US-AndrewNeural", "en-US-BrianNeural", "en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-EricNeural")
Stopped = _render.Stopped
TALK_LINES = (
    "Here's the thing nobody tells you about the first week without power, and it's the reason most families run out early.",
    "Now, I want you to write this one down, because this is the item that carries you all the way to day ninety.",
    "People do the exact opposite, they panic and grab the wrong stuff first. Don't be that family. Here's what I'd do.",
)


def size_for(preview):
    return (1280, 720) if preview else (1920, 1080)


def _rows_from_script(text):
    return [{"line": s, "shot": "", "visual": "", "product": "", "title": "", "rows": "", "chapter": "", "n": i + 1}
            for i, s in enumerate(director.sentences(text))]


def _voice(body, voice_file, edge_voice, log):
    from prepper_host import voice as pv
    return pv.from_file(voice_file, log=log) if voice_file else pv.edge(body, edge_voice or EDGE_VOICES[0], log=log)


def _flow_voice(rows, spec, meta, edge_voice, size, title, use_flow, log, cancel):
    """Second pass for Flow voice: host lines spoken by his own Flow clips, the rest by Edge, timed again."""
    from prepper_host import flowvoice as fv
    rows2 = fv.split_rows(rows, spec)
    jobs = {fv.clip_key(meta, r["line"]): fv.clip_prompt(meta, r["line"]) for r in rows2 if r.get("say")}
    missing = {k: p for k, p in jobs.items() if not flow.have(k, "mp4")}
    log(f"prepper host: Flow voice: {len(jobs)} host line(s), {len(jobs) - len(missing)} already spoken, {len(missing)} to make")
    if missing and use_flow and not (cancel and cancel()):
        try:
            with flow.Session(log=log) as fs:
                fs.clips(missing, refs=_host.refs(meta), cancel=cancel, voice=fv.flow_voice(meta))
        except Exception as e:  # noqa: BLE001 - a missing clip leaves its line on the Edge voice
            log(f"prepper host: Flow trouble ({type(e).__name__}: {e}); those lines keep the Edge voice")
    clips = {k: flow.have(fv.clip_key(meta, r["line"]), "mp4") for k, r in enumerate(rows2) if r.get("say")}
    clips = {k: v for k, v in clips.items() if v}
    left = sum(1 for r in rows2 if r.get("say")) - len(clips)
    if left:
        log(f"prepper host: {left} host line(s) on the Edge voice (no Flow clip yet; Generate again to retry)")
    cloned = {}
    sample = fv.voice_sample(meta, list(clips.values()))   # this host's own spoken clips only
    if sample:                # the other lines in the same voice: his Flow voice copied by the voice clone
        try:
            cloned = fv.clone_lines([r["line"] for k, r in enumerate(rows2) if k not in clips], sample, log=log, cancel=cancel)
        except Exception as e:  # noqa: BLE001 - the Edge voice stands in
            log(f"prepper host: voice clone not used ({e}); the other lines use the Edge voice")
    else:
        log("prepper host: not enough of his Flow voice yet to copy; the other lines use the Edge voice")
    vo = fv.build(rows2, clips, edge_voice, log=log, cloned=cloned)
    spec = director.direct(rows2, vo["words"], vo["duration"], size=size, host_meta=meta, title=title or "")
    fv.attach(spec, rows2, vo["said"])
    spec["flow_voice"] = {"lines": len(jobs), "spoken": len(clips), "cloned": len(cloned), "sample": str(sample or "")}
    return rows2, spec, vo


def plan(csv_path=None, script=None, voice_file=None, edge_voice=None, host="dale", talking=False, preview=False,
         sound="fx", use_flow=True, title=None, log=print, cancel=None):
    """csv_path: a Prepper Host CSV (recommended). script: a .txt path or text (lines become shots, the director picks)."""
    problems, rows, thumb_row = [], None, None
    text = ""
    if script:
        sp = Path(str(script))
        text = sp.read_text(encoding="utf-8-sig") if "\n" not in str(script) and sp.is_file() else str(script)
        lines = [l.strip() for l in text.strip().splitlines()]
        if title is None and len(lines) > 1 and lines[0] and lines[0][-1] not in ".?!":
            title, text = lines[0], " ".join(lines[1:])
    if csv_path:
        rows, problems = csvplan.read(csv_path)
        thumb_row = next((r for r in rows if r["shot"] == "thumbnail"), None)
        rows = [r for r in rows if r["shot"] != "thumbnail"]
        if title is None:
            title = Path(str(csv_path)).stem.replace("_", " ")
    if not rows:
        if not text.strip():
            raise ValueError("no narration: choose a Prepper Host CSV or a script")
        rows = _rows_from_script(text)
    body = csvplan.script_of(rows)
    meta = _host.load(host or "dale")
    if not meta.get("portrait"):
        raise ValueError(f"host '{host}' has no portrait.png in {meta['dir']}")
    vo = _voice(body, voice_file, edge_voice, log)
    spec = director.direct(rows, vo["words"], vo["duration"], size=size_for(preview), host_meta=meta, title=title or "")
    if talking == "flow":
        if voice_file:
            log("prepper host: Flow voice works with the Edge voice for the other lines; your voice file is used as it is")
        else:
            rows, spec, vo = _flow_voice(rows, spec, meta, edge_voice or EDGE_VOICES[0], size_for(preview), title, use_flow, log, cancel)
    spec["voice_path"] = vo["path"]
    spec["sound"] = sound
    spec["host"] = {k: meta.get(k) for k in ("name", "tagline", "look", "set_image", "portrait", "dir")}
    first_host = next((s for s in spec["shots"] if s["kind"] in ("host", "split")), None)
    if first_host:
        first_host["namebar"] = True

    # thumbnail picture
    prods = [p["name"] for s in spec["shots"] for p in s.get("card", {}).get("products", [])]
    if thumb_row:
        tprompt = thumb_row["visual"] or "{host} holding " + (thumb_row["product"] or (prods[0] if prods else "a bag of rice"))
        tlines = [x.strip() for x in (thumb_row["title"] or title or "").split("|")]
    else:
        tprompt = ("{host} standing in front of a big warehouse store at dusk, holding " + (prods[0] if prods else "a big bag of rice")
                   + ", a loaded shopping cart beside him, looking at the camera, confident")
        words = (title or "").split()
        tlines = [" ".join(words[:3]), " ".join(words[3:6])] if words else ["", ""]
    tfull = _host.expand(tprompt, meta) + ". Photorealistic, bright, high contrast YouTube thumbnail photo, no text."
    tkey = director.key_of(f"{meta['name']}|{tfull}")
    spec["pictures"][tkey] = {"prompt": tfull, "host": True}
    spec["thumbnail"] = {"pic": tkey, "lines": tlines, "visual": tprompt, "title": " | ".join(tlines),
                         "product": thumb_row["product"] if thumb_row else ""}

    # pictures
    for k, p in spec["pictures"].items():
        p["prompt"] = _host.expand(p["prompt"], meta)
    missing = {k: p for k, p in spec["pictures"].items() if not flow.have(k)}
    clips = list(meta.get("talk_clips") or [])
    if use_flow and (missing or (talking and len(clips) < 3)) and not (cancel and cancel()):
        try:
            with flow.Session(log=log) as fs:
                hosty = {k: p["prompt"] for k, p in missing.items() if p.get("host")}
                plain = {k: p["prompt"] for k, p in missing.items() if not p.get("host")}
                if hosty:
                    fs.pictures(hosty, refs=_host.refs(meta), cancel=cancel)
                if plain:
                    fs.pictures(plain, refs=None, cancel=cancel)
                if talking and len(clips) < 3:
                    jobs = {}
                    for i, line in enumerate(TALK_LINES[len(clips):3], len(clips) + 1):
                        jobs[f"talk_{meta['name'].lower()}_{i}"] = (
                            f"Photorealistic video, static medium shot on a tripod. The man from the reference pictures {meta['set']}. "
                            f"He looks straight into the camera and talks calmly with small natural hand gestures. He says: \"{line}\" "
                            "No music, quiet room tone. No text, no subtitles, no logos.")
                    made = fs.clips(jobs, refs=_host.refs(meta), cancel=cancel)
                    for i, (k, pth) in enumerate(sorted(made.items()), 1):
                        dst = Path(meta["dir"]) / f"talk_{len(clips) + i}.mp4"
                        if not dst.exists():
                            dst.write_bytes(Path(pth).read_bytes())
                    clips = [str(p) for p in sorted(Path(meta["dir"]).glob("talk_*.mp4"))]
        except Exception as e:  # noqa: BLE001 - the video never stops for Flow
            log(f"prepper host: Flow trouble ({type(e).__name__}: {e}); stand-ins are used for what is missing")
    have = {k: flow.have(k) for k in spec["pictures"] if flow.have(k)}
    left = [k for k in spec["pictures"] if k not in have]
    if talking and clips:
        rnd = random.Random(7)
        for s in spec["shots"]:
            if s["kind"] in ("host", "split", "pip") and not s.get("talk"):   # Flow-voiced shots keep their own clip
                s["talk"] = clips[rnd.randrange(len(clips))]
                s["talk_at"] = round(rnd.uniform(0, 1.0), 2)   # Flow agent clips are ~4 s
    spec["assets"] = {"pictures": have, "fallback": meta.get("set_image") or meta["portrait"]}
    for p in problems:
        log(f"  CSV: {p}")
    if left:
        log(f"prepper host: {len(left)} picture(s) not made by Flow yet: stand-ins used (Generate again to retry)")
    kinds = {}
    for s in spec["shots"]:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    return {"spec": spec, "title": title or "", "seconds": spec["duration"], "shots": len(spec["shots"]), "kinds": kinds,
            "pictures": len(have), "missing": len(left), "problems": problems, "talking": bool(talking and clips)}


def save(spec, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def refresh_assets(spec):
    """Pictures made after Generate (a retry, another run) are picked up at Render."""
    pics = spec.setdefault("assets", {}).setdefault("pictures", {})
    for k in spec.get("pictures", {}):
        if k not in pics and flow.have(k):
            pics[k] = flow.have(k)
    return spec


def render(spec, out, progress=None, cancel=None, log=print, workers=None):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda f, m="": None)
    spec = refresh_assets(spec)
    with tempfile.TemporaryDirectory() as wd:
        silent, wav = Path(wd) / "picture.mp4", Path(wd) / "mix.wav"
        _render.render_picture(spec, spec["assets"], silent, workers=workers, cancel=cancel,
                               progress=lambda f, m: say(0.02 + 0.9 * f, m))
        if cancel and cancel():
            raise Stopped("Stopped.")
        say(0.93, "mixing the sound")
        rep = _render.mix(spec, wav, sound=spec.get("sound", "fx"))
        log(f"prepper host: mix peak {rep['peak_db']} dBFS")
        say(0.97, "writing the video")
        part = out.with_name(out.stem + ".part.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(part)],
                       check=True, timeout=3600)
        part.replace(out)
    th = spec.get("thumbnail") or {}
    tp = spec["assets"]["pictures"].get(th.get("pic")) or spec["assets"].get("fallback")
    thumb = None
    if tp:
        try:
            thumb = str(_render.thumbnail(tp, th.get("lines") or [], out.with_suffix(".jpg")))
        except Exception as e:  # noqa: BLE001
            log(f"prepper host: thumbnail not made ({e})")
    say(1.0, "done")
    return {"video": str(out), "seconds": spec["duration"], "thumbnail": thumb}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Prepper Host video from a CSV or a script")
    ap.add_argument("source")
    ap.add_argument("--voice")
    ap.add_argument("--edge", default=EDGE_VOICES[0])
    ap.add_argument("--host", default="dale")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--talking", action="store_true")
    ap.add_argument("--flow-voice", action="store_true", help="host lines spoken by his own Flow clips (lips match)")
    ap.add_argument("--no-flow", action="store_true")
    ap.add_argument("--sound", default="fx", choices=("voice", "fx", "music"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    src = Path(a.source)
    is_csv = src.suffix.lower() == ".csv"
    r = plan(csv_path=str(src) if is_csv else None, script=None if is_csv else str(src), voice_file=a.voice, edge_voice=a.edge,
             host=a.host, talking="flow" if a.flow_voice else a.talking, preview=a.preview, sound=a.sound, use_flow=not a.no_flow)
    print(json.dumps({k: v for k, v in r.items() if k != "spec"}))
    out = a.out or str(ROOT / "out" / "prepper_host" / f"{re.sub(r'[^A-Za-z0-9]+', '_', src.stem)}.mp4")
    save(r["spec"], Path(out).with_suffix(".plan.json"))
    res = render(r["spec"], out, progress=lambda f, m="": print(f"{int(f * 100)}% {m}", flush=True))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
