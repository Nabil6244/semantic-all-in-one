"""The What If shot CSV: an AI (or a person) writes the shot list from the script; it is loaded AS WRITTEN. One row per shot,
timed by the narrator's own words; layer rows (metric, diagram, hud, caption, title, fade) hang under the shot they belong to.

    row    what it is        columns used
    plan   the plan (first)  label = the video title
    shot   a full-frame shot vo_anchor (its first words), kind (image video plate craft globe hero black), asset (nasa_image:... flow_image:...
                             flow_video:... stock_video:... archive_video:... file:<name>), model (a craft: voyager, cassini ... or a .glb; for kind hero the scene: venera_ground | venera_descent),
                             texture (a world: venus, mars ... or a file), label (the name in the lower-left lockup), sub (its date / line),
                             why, extra {"tint": "warm", "cam": {...}, "exit": "push", "cite": "SOURCE TEXT"}
    layer  a graphic         type (metric diagram hud caption title fade), vo_anchor | t, id (kind), label, sub, text, value_from, value_to,
                             format, anchor, hold, extra
A shot runs until the next shot's words. Everything the narration says that the CSV does not mention (callouts for numbers, the
survival clock, ratio diagrams, the title, fades) is still added automatically unless the plan row says {"auto": false}.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dataclasses import dataclass, field

from anchor_clock import AnchorClock

from .narration import Word
from .planner import CRAFT, WORLDS, Shot

COLUMNS = ("row", "shot", "vo_anchor", "kind", "asset", "model", "texture", "label", "sub", "text", "type", "id", "value_from", "value_to",
           "format", "anchor", "until", "hold", "why", "extra", "t", "end")
KINDS = ("image", "video", "plate", "craft", "globe", "hero", "black")
HERO_SCENES = ("venera_ground", "venera_descent", "cloud_airship", "ship_engine", "blackhole_disc", "blackhole_top", "blackhole_ring", "blackhole_lensing",
               "blackhole_horizon")
LAYER_TYPES = ("metric", "diagram", "hud", "caption", "title", "fade", "annotate", "template")
ASSET_SOURCES = ("nasa_image", "nasa_video", "stock_image", "stock_video", "flow_image", "flow_video", "youtube_video", "archive_video",
                 "commons_image", "commons_video", "file")


@dataclass
class Item:
    """One layer row of the CSV."""
    row: int
    kind: str = "layer"
    type: str = ""
    t: Optional[float] = None
    id: str = ""
    label: str = ""
    sub: str = ""
    text: str = ""
    value_from: Optional[float] = None
    value_to: Optional[float] = None
    format: str = ""
    anchor: str = ""
    hold: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    vo_anchor: str = ""                       # the row's own words, kept to find them again on the script-aligned narration


class PlanError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def is_whatif_csv(text: str) -> bool:
    head = (text.lstrip("﻿").split("\n", 1) or [""])[0].lower()
    return "shot" in head and "kind" in head and "vo_anchor" in head


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s]", "", str(s).lower())


_SMALL = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                                     "seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_SCALE = {"thousand": 1_000}           # the transcript keeps "6 billion", "9 5 trillion" as words: those stay words


def _small(w: str) -> Optional[int]:
    """one word below a hundred: "four", "forty", "fortynine" (a hyphen already dropped by _norm)"""
    if w in _SMALL:
        return _SMALL[w]
    if w in _TENS:
        return _TENS[w]
    for tw, tv in _TENS.items():
        if w.startswith(tw) and w[len(tw):] in _SMALL and 0 < _SMALL[w[len(tw):]] < 10:
            return tv + _SMALL[w[len(tw):]]
    return None


def spoken_numbers(text: str) -> str:
    """Numbers spelled out in a vo_anchor ("four point three seven", "three hundred eightyfour thousand") in the form the transcript
    times them: Whisper writes 4.37 as the two words "4" "37" and 384,000 as "384" "0" (joined back to 384000 on the transcript side,
    see read_shots). A cue written as the narrator says the number now finds it instead of landing at the start of its shot."""
    low = _norm(text)
    low = re.sub(r"\b(\d+)s\b", r"\1", low)                                   # "voyager 1's" -> voyager 1 (the transcript drops the 's)
    low = re.sub(r"\b(?:kilomet(?:er|re)s?|km)\b", "kilometers", low)            # km / kilometres -> kilometers
    low = re.sub(r"\bmetres?\b", "meters", low)
    toks = low.split()
    out: List[str] = []
    i = 0
    while i < len(toks):
        if _small(toks[i]) is None and not (toks[i] == "a" and i + 1 < len(toks) and toks[i + 1] in ("hundred", "thousand", "million")):
            out.append(toks[i])
            i += 1
            continue
        total, cur, j = 0, 0, i
        if toks[j] == "a":
            cur, j = 1, j + 1
        while j < len(toks):
            w = toks[j]
            v = _small(w)
            if v is not None and (cur == 0 or cur % 100 == 0 or (cur % 10 == 0 and cur % 100 >= 20 and v < 10)):
                cur += v                   # "one" / "hundred ninety two" / "ninety two"; "five six" stops at "six"
            elif w == "hundred" and cur:
                cur *= 100
            elif w in _SCALE and (cur or total):
                total += max(cur, 1) * _SCALE[w]
                cur = 0
            elif w == "and" and j + 1 < len(toks) and _small(toks[j + 1]) is not None and cur >= 100:
                pass
            else:
                break
            j += 1
        value = total + cur
        frac = ""
        if j + 1 < len(toks) and toks[j] == "point" and toks[j + 1] in _SMALL and _SMALL[toks[j + 1]] < 10:
            k = j + 1
            while k < len(toks) and toks[k] in _SMALL and _SMALL[toks[k]] < 10:
                frac += str(_SMALL[toks[k]])
                k += 1
            j = k
        elif toks[j:j + 3] == ["and", "a", "half"]:                         # "nine and a half" -> 9 5 (as 9.5 is transcribed)
            frac, j = "5", j + 3
        elif j < len(toks) and toks[j] == "point" and j + 1 == len(toks):   # a cue cut after "point": the number alone
            j += 1
        out += [str(value)] + ([frac] if frac else [])
        i = j
    return " ".join(out)


def _transcript_numbers(words: Sequence[Any]) -> List[Tuple[str, float, float]]:
    """The transcript's thousands back in one word ("384" "0" -> 384000, "6" "800" -> 6800), as spoken_numbers writes them."""
    w = [(spoken_numbers(x[0]) or _norm(x[0]), float(x[1]), float(x[2])) for x in words]
    out: List[Tuple[str, float, float]] = []
    i = 0
    while i < len(w):
        if i + 1 < len(w) and w[i][0].isdigit() and w[i + 1][2] >= w[i + 1][1] and w[i + 1][1] - w[i][2] < 0.05 \
                and (w[i + 1][0] == "0" or re.fullmatch(r"\d{3}", w[i + 1][0])):
            out.append((str(int(w[i][0]) * 1000 + int(w[i + 1][0])), w[i][1], w[i + 1][2]))
            i += 2
            continue
        out.append(w[i])
        i += 1
    return out


def craft_model(name: str) -> str:
    n = (name or "").strip().lower()
    if n.endswith(".glb"):
        return n
    for pat, model, label in CRAFT:
        if re.search(pat, n) or n == model.replace(".glb", ""):
            return model
    raise ValueError(f"model {name!r} is not in the library (voyager, cassini, juno, galileo, magellan, parker, perseverance, viking_lander, jwst, "
                     f"hubble, apollo_lm, saturn_v, dsn_70m, dawn, messenger, rosetta, ulysses, ingenuity, insight, iss, pioneer10, deep_space_1, "
                     f"stardust) and is not a .glb file")


def world_texture(name: str) -> Tuple[str, str]:
    n = (name or "").strip().lower()
    if re.search(r"\.(jpe?g|png)$", n):
        return n, ""
    for pat, tex, label, atm in WORLDS:
        if re.search(pat, n) or n.replace("_", " ") == label.lower().replace("the ", ""):
            return tex, atm or ""
    raise ValueError(f"texture {name!r} is not a world in the library (venus, mars, mercury, jupiter, uranus, neptune, earth, moon, sun) and is not an image file")


def read_shots(text: str, raw_words: Sequence[Any], duration: float) -> Tuple[List[Shot], List[Tuple[Dict[str, Any], str]], Dict[str, Any], List[str]]:
    """-> (shots, layer rows [(row dict, shot id)], plan info, notes). Raises PlanError listing every problem by row."""
    problems: List[str] = []
    notes: List[str] = []
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or not is_whatif_csv(text):
        raise PlanError(["this is not a What If shot CSV: the first row must be the header " + ",".join(COLUMNS[:12])])
    head = [h.strip().lower() for h in rows[0]]
    words = _transcript_numbers(raw_words) if raw_words else []
    clock = AnchorClock(words, notes, normalize=spoken_numbers, unit="shot")
    shots: List[Shot] = []
    layer_rows: List[Tuple[Dict[str, Any], str, Any]] = []
    info: Dict[str, Any] = {"title": "", "auto": True}
    for n, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        r = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h}
        kind = r.get("row", "").lower()
        try:
            extra = json.loads(r.get("extra") or "{}")
            if not isinstance(extra, dict):
                raise ValueError("extra must be a JSON object")
            anchor = r.get("vo_anchor", "")
            if kind == "plan":
                info["title"] = r.get("label", "")
                info["auto"] = extra.get("auto", True) is not False
            elif kind == "shot":
                k = r.get("kind", "").lower()
                if k not in KINDS:
                    raise ValueError(f"kind must be one of {', '.join(KINDS)} (got {r.get('kind')!r})")
                start = float(r["t"]) if r.get("t") else None
                if start is None and anchor:
                    start = clock.at(anchor, advance=True, before=shots[-1].text if shots else "")
                if start is None:
                    if shots:
                        raise ValueError("a shot needs a vo_anchor (its first words) or a t in seconds")
                    start = 0.0
                if not shots:
                    start = 0.0
                s = Shot(id=f"s{len(shots) + 1}", start=start, end=-1.0, kind=k, text=r.get("text", ""), name=r.get("label", "").upper(), extra=extra)
                s.place = (r.get("label") or r.get("model") or r.get("texture") or "")
                if k in ("image", "video"):
                    a = r.get("asset", "")
                    src = a.split(":", 1)[0].strip().lower()
                    if ":" not in a or src not in ASSET_SOURCES or not a.split(":", 1)[1].strip():
                        raise ValueError(f"asset {a!r} must be <source>:<what to find> with a source of {', '.join(ASSET_SOURCES)}")
                    s.asset = a
                    s.cite = ("REAL IMAGE" if src.startswith(("nasa", "archive", "commons")) else "AI ILLUSTRATION" if src.startswith("flow") else "IMAGE", "")
                elif k == "craft":
                    s.model = craft_model(r.get("model", ""))
                    s.cite = ("ILLUSTRATION", "NASA 3D MODEL")
                    s.cam = extra.get("cam", {})
                elif k == "hero":
                    sc = (r.get("model") or "").strip().lower()
                    if sc not in HERO_SCENES:
                        raise ValueError(f"a hero shot's model is its scene: {', '.join(HERO_SCENES)} (got {r.get('model')!r})")
                    s.scene, s.cam, s.cite = sc, extra.get("cam", {}), ("ILLUSTRATION", "")
                elif k == "globe":
                    s.texture, s.atmosphere = world_texture(r.get("texture", ""))
                    s.cite, s.cam = ("ILLUSTRATION", ""), extra.get("cam", {})
                elif k == "plate":
                    s.tint, s.title, s.sub, s.cite = extra.get("tint", "cool"), r.get("label", ""), r.get("sub", ""), ("DIAGRAM", str(extra.get("cite", "")))
                    s.name = ""
                if extra.get("exit") in ("push", "cut"):
                    s.exit = extra["exit"]
                if r.get("sub") and k != "plate":
                    s.sub = r["sub"]
                shots.append(s)
            elif kind == "layer":
                if not shots:
                    raise ValueError("a layer row must come after the shot row it belongs to")
                if r.get("type", "").lower() not in LAYER_TYPES:
                    raise ValueError(f"layer type must be one of {', '.join(LAYER_TYPES)} (got {r.get('type')!r})")
                if r.get("type", "").lower() == "template":
                    from . import templates as tpl
                    tpl.get(r.get("id", ""))                       # an unknown template id is named here, with its row
                if r.get("type", "").lower() == "annotate" and (extra.get("x") is None or extra.get("y") is None):
                    raise ValueError("an annotate row needs extra {\"x\": 0.73, \"y\": 0.36} (where the ring goes, as fractions of the frame)")
                t = float(r["t"]) if r.get("t") else None
                if t is None and anchor:
                    try:
                        t = clock.at(anchor, advance=False, before=shots[-1].text)
                    except ValueError as exc:
                        notes.append(f"row {n}: {exc}; it appears at the start of shot {shots[-1].id}")
                it = Item(row=n, kind="layer", type=r["type"].lower(), t=t, id=r.get("id", ""), label=r.get("label", ""), sub=r.get("sub", ""),
                          text=r.get("text", ""), value_from=_f(r, "value_from"), value_to=_f(r, "value_to"), format=r.get("format", ""),
                          anchor=r.get("anchor", "").lower(), hold=_f(r, "hold"), extra=extra, vo_anchor=anchor if t is None else "")
                layer_rows.append((it, shots[-1].id, _f(r, "end")))
            else:
                raise ValueError(f"row must be plan, shot or layer (got {r.get('row')!r})")
        except (ValueError, KeyError) as exc:
            problems.append(f"row {n}: {exc}")
    if not shots:
        problems.append("the CSV has no shot rows")
    if problems:
        raise PlanError(problems)
    # order, then each shot runs to the next one's start
    for i in range(1, len(shots)):
        if shots[i].start < shots[i - 1].start + 0.5:
            notes.append(f"{shots[i].id} starts at {shots[i].start:.1f}s, before the shot above it ends; moved to follow it")
            shots[i].start = shots[i - 1].start + 0.5
    for a, b in zip(shots, shots[1:]):
        a.end = b.start
    shots[-1].end = duration
    return shots, layer_rows, info, notes


def _f(r: Dict[str, str], col: str) -> Optional[float]:
    v = r.get(col, "")
    if v == "":
        return None
    try:
        return float(v.replace(",", ""))
    except ValueError:
        raise ValueError(f"{col} must be a number (got {v!r})") from None


def layers_from_rows(layer_rows: List[Tuple[Any, str, Any]], shots: List[Shot], words: Sequence[Any] = (), script: str = "",
                    notes: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], List[Shot]]:
    """Layer rows -> engine layers; a diagram row also brings its plate shot (carved into the timeline by the planner). A row whose
    words the anchor clock could not hear (a decimal the transcript split, a "percent" it dropped) is found again on the
    script-aligned narration. With `notes`, a row that cannot be drawn is left out and named there instead of stopping the plan."""
    from . import narration as nr

    aligned = nr.words_of(words, script) if words else []

    by_id = {s.id: s for s in shots}
    layers: List[Dict[str, Any]] = []
    plates: List[Shot] = []
    for it, sid, end in layer_rows:
        n_layers, n_plates = len(layers), len(plates)
        try:
            sh = by_id[sid]
            if it.t is None and it.vo_anchor and aligned:
                it.t = nr.find_anchor(aligned, it.vo_anchor, sh.start - 0.5, sh.end + 0.5)
            start = it.t if it.t is not None else sh.start
            stop = end or min(sh.end, start + (it.hold if it.hold else (5.5 if it.type == "diagram" else 3.5)))
            timing = {"start": round(start, 3), "end": round(stop, 3)}
            if it.type == "caption":
                layers.append({"type": "tm_caption", "text": (it.label or it.text).upper(), **({"sub": it.sub.upper()} if it.sub else {}),
                               "kicker": it.extra.get("kicker", ""), "size": it.extra.get("size", "small"), **timing, "fade_in": 0.05, "fade_out": 0.3, "z": 5})
            elif it.type == "title":
                layers.append({**nr._title_lines(it.label or it.text), **({"sub": it.sub} if it.sub else {}), "type": "tm_title", **timing,
                               "fade_in": 0.05, "fade_out": 0.3, "z": 6})
            elif it.type == "annotate":            # a ring and a label on the picture: extra {"x": 0.73, "y": 0.36, "r": 0.027}
                if it.extra.get("x") is None or it.extra.get("y") is None:
                    raise ValueError("an annotate row needs extra {\"x\": ..., \"y\": ...} (fractions of the frame)")
                layers.append({"type": "tm_annotate", "x": float(it.extra["x"]), "y": float(it.extra["y"]), "r": float(it.extra.get("r", 0.027)),
                               "label": it.label or it.text, "sub": it.sub, **timing, "fade_in": 0.1, "fade_out": 0.3, "z": 6})
            elif it.type == "fade":
                layers.append({"type": "tm_fade", **timing, "fade_in": 0.6, "fade_out": 0.5, "z": 20})
            elif it.type == "template":          # any visual of the template library (whatif/templates.py); a plate template brings its plate
                from . import templates as tpl
                L, pl = tpl.layer_for(it, start, end, aligned or words)
                layers.append(L)
                if pl:
                    plates.append(Shot(id="", start=L["start"], end=L["end"], kind="plate", tint=pl["tint"], cite=pl["cite"], asset=pl["asset"]))
            else:
                made = nr.layers_from_row(it, start, stop)
                for L in made:
                    if L["type"] == "tm_plate":
                        plates.append(Shot(id="", start=start, end=stop, kind="plate", tint=L.get("tint", "cool"), title=L.get("title", ""), sub=L.get("sub", ""),
                                           cite=tuple(L.get("cite") or ("DIAGRAM", "")), asset=str(L.get("asset", ""))))
                    else:
                        layers.append(L)
        except Exception as exc:          # noqa: BLE001 -- one row never stops the video
            if notes is None:
                raise
            del layers[n_layers:], plates[n_plates:]
            notes.append(f"row {it.row}: {exc}; left out")
    return _merge_missions(layers), plates


def _merge_missions(layers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every mission hud row is one beat of ONE mission card (V4): its keys are joined, it runs from the first beat to the last row's end."""
    ms = [L for L in layers if L.get("type") == "tm_mission"]
    if len(ms) < 2:
        return layers
    first = ms[0]
    merged = {**first, "keys": sorted((k for L in ms for k in L["keys"]), key=lambda k: k["t"]),
              "start": min(L["start"] for L in ms), "end": max(L["end"] for L in ms)}
    for L in ms[1:]:
        for k in ("kicker", "stages"):
            if L.get(k) and not first.get(k):
                merged[k] = L[k]
    return [merged if L is first else L for L in layers if L.get("type") != "tm_mission" or L is first]
