"""Reddit Shorts: plan (story -> Edge voice + picture cues + Flow pictures) then render (frames + mix -> mp4).
No Gemini calls. The app (ui/reddit_shorts_section.py) imports this only inside its button handlers."""
from __future__ import annotations

import json
import os
from pathlib import Path

from reddit_shorts import paint, render as _render


def plan(st, work, pictures_dir=None, music_index=0, use_flow=True, log=print, cancel=None):
    """-> spec. The voice comes first so a picture cue the voice does not say is caught before Flow paints."""
    work = str(work)
    pdir = str(pictures_dir or (paint.builtin_dir(st["id"]) if st.get("builtin") else work))
    log(f"reddit shorts: voice ({st['voice']})")
    voice = _render.make_voice(st, os.path.join(work, "voice"))
    words = json.load(open(voice["words"]))
    starts = _render.beat_times(st["beats"], words, _render.title_words(st["title"]), st["id"])
    if cancel and cancel():
        raise RuntimeError("Stopped.")
    prompts = paint.prompts(st)
    made = paint.paint_story(st, pdir, log=log, cancel=cancel) if use_flow else paint.painted(st, pdir)
    spec = {"story": {k: st[k] for k in ("id", "sub", "user", "voice", "ups", "com", "title", "body")},
            "voice": voice, "music_index": music_index, "pictures_dir": pdir,
            "beats": [{"key": k, "start": t, "cue": b[0]} for (k, t, b) in zip(prompts, starts, st["beats"])],
            "pictures": {k: {"prompt": p} for k, p in prompts.items()},   # visual_bridge reads {key: {"prompt"}}
            "assets": {"pictures": made}, "duration": voice["duration"] + 0.7}
    log(f"reddit shorts: planned {spec['duration']:.0f} s, {len(made)}/{len(prompts)} pictures")
    return spec


def refresh_assets(spec):
    """Pictures painted after the plan (a retry) are picked up at render."""
    pics = spec.setdefault("assets", {}).setdefault("pictures", {})
    for k in spec.get("pictures", {}):
        f = os.path.join(spec.get("pictures_dir", ""), "places", f"{k}.png")
        if k not in pics and os.path.isfile(f):
            pics[k] = f
    return spec


def save(spec, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render(spec, out, progress=None, cancel=None, log=print):
    return _render.render_spec(refresh_assets(spec), out, progress=progress, cancel=cancel, log=log)
