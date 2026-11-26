"""Paint a story's narration-matched pictures with Flow (once; painted pictures are skipped).
Usage: python3 -m reddit_shorts.paint <story_id> [...] | all   (built-in stories)"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from toontales import runner as tt  # noqa: E402

STYLE = ("2D cartoon illustration for an animated story Short, flat colours with soft simple shading, "
         "clean bold dark-brown outlines, warm bright storybook palette, expressive funny faces, vector illustration")
FRAME = ("Vertical 9:16 picture. The people and the main action fill the upper two thirds; keep the lower third "
         "simple and uncluttered. No text, no letters, no words on screens or papers, no logos, no speech bubbles")
STORY_DIR = os.path.join(ROOT, "reddit_shorts", "stories")


def builtin_dir(sid):
    return os.path.join(STORY_DIR, sid)


def cast_people(cast):
    """'Narrator: ... . Sister: ...' or 'Narrator: ...; Sister: ...' -> ['Narrator: ...', 'Sister: ...']"""
    return [c.strip() for c in re.split(r"[;\n]|\.\s+(?=[A-Z][\w ]{0,20}:)", cast or "") if ":" in c]


def with_cast(prompt, cast):
    """Each picture names only the people in that moment, and says who is absent: Flow otherwise adds the rest of
    the cast on its own (grandma at the dinner after her funeral)."""
    people = cast_people(cast)
    who = [c for c in people if c.split(":")[0].strip().lower() in prompt.lower()]
    gone = [c.split(":")[0].strip() for c in people if c not in who]
    prompt = prompt.rstrip(". ")
    out = prompt + (". Characters: " + ". ".join(who) if who else "")
    if gone:
        out += ". " + ", ".join(gone) + (" is" if len(gone) == 1 else " are") + " NOT in this picture"
    return out


def prompts(st):
    return {f"b{i}": with_cast(p, st.get("cast", "")) for i, (_, p) in enumerate(st["beats"])}


def write_plan(st, work):
    places = os.path.join(work, "places")
    os.makedirs(places, exist_ok=True)
    plan = {"id": f"reddit_{st['id']}", "paint_style": STYLE, "frame": FRAME, "cast": "same characters as described",
            "backgrounds": "flow", "places": {k: {"prompt": p} for k, p in prompts(st).items()}}
    path = os.path.join(work, "plan.json")
    with open(path, "w") as f:
        json.dump(plan, f, indent=1)
    return path


def painted(st, work):
    d = os.path.join(work, "places")
    return {k: os.path.join(d, f"{k}.png") for k in prompts(st) if os.path.isfile(os.path.join(d, f"{k}.png"))}


def paint_story(st, work, log=print, cancel=None):
    """Paint the missing pictures (one retry for any Flow drops). Starts the Flow server only if it is not up,
    and stops only that one. -> {key: path} of every painted picture."""
    want = prompts(st)
    if len(painted(st, work)) == len(want):
        return painted(st, work)
    started = None
    if not tt._flow_up():
        log("starting the Flow server")
        started = subprocess.Popen(["node", "server.js"], cwd=str(tt.FLOW), stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(30):
            if tt._flow_up():
                break
            time.sleep(1)
        else:
            tt._stop(started)
            raise RuntimeError("The Flow server did not start (flow-engine/server.js).")
    env = dict(os.environ, FLOW_ALLOW_REAL_CREDITS="1")
    try:
        for _ in range(2):
            left = [k for k in want if k not in painted(st, work)]
            if not left:
                break
            log(f"painting {len(left)} picture(s) with Flow")
            proc = subprocess.Popen(["node", str(tt.TT / "sets" / "paint_places.mjs"), write_plan(st, work)],
                                    cwd=str(tt.FLOW), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, start_new_session=True)
            for ln in proc.stdout:
                if cancel and cancel():
                    tt._stop(proc)
                    raise RuntimeError("Stopped.")
                if ln.startswith(("PLACE", "MISSING", "ERROR")):
                    log(ln.strip().split(" -> ")[0])
            proc.wait()
    finally:
        if started is not None:
            tt._stop(started)
    return painted(st, work)


def main(ids):
    from reddit_shorts import story
    for sid in (story.builtin_ids() if ids == ["all"] else ids):
        st = story.builtin(sid)
        got = paint_story(st, builtin_dir(sid))
        print("DONE" if len(got) == len(st["beats"]) else "MISSING", sid, f"{len(got)}/{len(st['beats'])}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["all"])
