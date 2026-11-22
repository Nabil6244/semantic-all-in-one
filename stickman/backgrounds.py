"""Meme look rooms: one Flow picture per place, painted once per shape (16:9 / 9:16) and kept for every later video.

paint(places_needed, shorts) runs on Generate (never before). It starts the Flow server for the run if it is not up
and stops only that one. If Flow cannot paint a place, that place is drawn in code instead: the video never stops.
"""
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / "flow-engine"
STORE = ROOT / "state" / "stickman_backgrounds"

STYLE = ("Funny internet meme comic background painting, bright cartoon colours, bold clean dark outlines, "
         "simple soft shading, slightly exaggerated everyday scene")
FRAME = ("Eye-level view of an empty room or place. The bottom third of the picture is open, empty, flat floor or "
         "ground seen from slightly above, where characters will stand; the scenery is behind it. No people, no "
         "animals, no characters, no text, no letters, no signs with writing, no logos")
PROMPTS = {
    "void": "a plain soft-coloured studio wall with a simple floor, a few soft light spots",
    "bedroom": "a cosy messy bedroom, an unmade bed at the side, a window with curtains, a bedside lamp, posters",
    "kitchen": "a home kitchen, fridge, counter with a coffee machine and mugs, a window, hanging pans",
    "office": "an open office, desks with computers at the back, a whiteboard, a potted plant, a water cooler",
    "street": "a city street on a sunny day, shops and apartment buildings behind the pavement, a street lamp",
    "park": "a green park on a sunny day, trees, a bench, a path, bushes, blue sky with clouds",
    "city_night": "a city street at night, lit windows in tall buildings, street lamps, a dark blue sky with a moon",
    "classroom": "a school classroom, a green chalkboard at the back, desks, a wall clock, bookshelves",
}


def _shape(shorts):
    return "portrait" if shorts else "landscape"


def path_for(place, shorts):
    return STORE / _shape(shorts) / f"{place}.png"


def have(places_needed, shorts):
    """{place: picture path} for the places already painted."""
    return {p: str(path_for(p, shorts)) for p in places_needed if path_for(p, shorts).is_file()}


def _flow_up():
    from toontales.runner import _flow_up as up
    return up()


def paint(places_needed, shorts=False, log=print, cancel=None, timeout=15 * 60, tries=2):
    """Paint the missing places with Flow. -> (have: {place: path}, missing: [place]). Never raises for Flow trouble.
    A run can come back empty (seen once on a freshly started server), so missing rooms get one more try."""
    got, missing = _paint_once(places_needed, shorts, log, cancel, timeout)
    for _ in range(tries - 1):
        if not missing or (cancel and cancel()):
            break
        log(f"stickman: trying Flow again for {', '.join(missing)}")
        got, missing = _paint_once(places_needed, shorts, log, cancel, timeout)
    return got, missing


def _paint_once(places_needed, shorts, log, cancel, timeout):
    places_needed = [p for p in dict.fromkeys(places_needed) if p in PROMPTS]
    todo = [p for p in places_needed if not path_for(p, shorts).is_file()]
    if not todo:
        return have(places_needed, shorts), []
    from toontales.runner import _stop
    started = None
    try:
        if not _flow_up():
            log("stickman: starting the Flow server to paint the rooms")
            started = subprocess.Popen(["node", "server.js"], cwd=str(FLOW), stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
            for _ in range(30):
                if _flow_up():
                    break
                time.sleep(1)
            else:
                raise RuntimeError("the Flow server did not start")
        out = path_for("x", shorts).parent
        out.mkdir(parents=True, exist_ok=True)
        job = {"id": f"stickman-meme-{_shape(shorts)}", "aspect": _shape(shorts), "out": str(out),
               "prompts": {p: f"{STYLE}. {PROMPTS[p]}. {FRAME}." for p in todo}}
        jf = out / "job.json"
        jf.write_text(json.dumps(job, indent=1))
        log(f"stickman: Flow is painting {len(todo)} room(s): {', '.join(todo)}")
        env = dict(os.environ, FLOW_ALLOW_REAL_CREDITS="1")
        proc = subprocess.Popen(["node", str(Path(__file__).with_name("paint_places.mjs")), str(jf)], cwd=str(FLOW),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                                start_new_session=True)
        end = time.time() + timeout
        try:
            for ln in proc.stdout:
                ln = ln.strip()
                if ln.startswith(("PLACE", "MISSING", "ERROR")):
                    log(f"stickman: {ln}")
                if (cancel and cancel()) or time.time() > end:
                    break
        finally:
            if proc.poll() is None:
                _stop(proc)
            proc.wait()
        if cancel and cancel():
            from .render import Stopped
            raise Stopped("Stopped.")
    except RuntimeError as e:
        log(f"stickman: Flow could not paint the rooms ({e})")
    finally:
        if started is not None:
            _stop(started)
    got = have(places_needed, shorts)
    return got, [p for p in places_needed if p not in got]
