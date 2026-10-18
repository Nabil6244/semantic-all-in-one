"""StarMap Cinema: the What If references' documentary grammar added to StarMap, as an option (the StarMap tab's Cinema
switch). Classic StarMap is untouched: nothing here runs unless the project turns Cinema on (spec["cinema"]).

What it adds, each switchable (FEATURES):
  plates  diagram plates where the narration explains something the 3D map cannot draw -- a mission TIMELINE from the dataset's
          own event dates ("decades", "since 1977"), a LIGHT-TIME axis when a signal or light travels to a craft, a CROSS-SECTION
          of the Sun's bubble when the heliosphere's boundaries are named. The What If engine's tm_* layers draw them on a slate
          plate over the map, at most one every PLATE_GAP_S.
  hero    NASA 3D models (shipped with the What If engine) for known craft, and a hero close-up of the craft in a beat about the
          craft itself (its dish, instruments, record, power ...).
  type    numbers as What If's type moments (a heavy figure on the shot, a sub-line, rotating places) instead of the dark
          full-screen number.
  photos  real photos letterboxed over a blurred copy of themselves; the citation line on every shot (REAL IMAGE, ILLUSTRATION,
          DIAGRAM, VISUALISATION -- a filled dot for real material, a ring for drawn).
  cuts    cuts land in a narration pause when one is near (the references: 65-82% of cuts in a pause), else on a word.
  audio   the references' loudness (-14 LUFS) and a music bed nearer the voice.
  grade   the references' grade: a little less saturated, blacks lifted towards slate.
  templates  CSV template rows: any of What If's templates (whatif-engine/templates) and its mission card.
  blocks  What If's information blocks from the narration (whatif/typeset.py) on the map, the craft and real photos.
  cards   a real photo under a block becomes What If's photo card (framed on the right half).
  fill    a slate's graphic holds to the cut; a longer empty stretch carries the narration's words (whatif/compile.py).
  ambience  What If's scene-following beds (whatif/sound.py): the ship's hum, a world's drone, two space drones."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

FEATURES = ("motion", "budget", "plates", "hero", "type", "photos", "cuts", "audio", "grade", "templates", "blocks", "cards", "fill", "ambience")
FEATURE_LABELS = {
    "motion": "Every shot keeps moving, as the narration says",
    "budget": "Map at most 50% of screen time",
    "plates": "Diagram plates (timeline, light-time, cross-sections)",
    "hero": "Hero spacecraft shots (NASA 3D models)",
    "type": "Type moments for big numbers",
    "photos": "Documentary photos + citation line",
    "cuts": "Cuts in narration pauses",
    "audio": "Reference loudness (-14 LUFS) and music level",
    "grade": "Documentary colour grade",
    "templates": "What If templates + mission card (CSV)",
    "blocks": "Information blocks from the narration",
    "cards": "Real photos as a card on the right, beside the type",
    "fill": "Graphics hold to the cut (no blank plates)",
    "ambience": "Background sound follows the scene (What If beds)",
}
PLATE_S, PLATE_GAP_S, PLATE_MIN_S = 6.0, 20.0, 3.5
# what a CSV may ask for with a plate row (full frame, on a slate) or an instrument row (over the shot) -- the What If graphics
CSV_KINDS = {
    "plate": {"section", "logaxis", "timeline", "compare", "dial", "bars", "curve", "composition", "orbitmap", "phase", "wave", "grid",
              "discmap", "hero"},
    "instrument": {"survival", "clock", "gauge", "caption", "metric", "annotate", "title", "fade", "mission"},
}
SILENCE = re.compile(r"\b(went silent|fell silent|goes silent|lost contact|never heard from|final transmission|last signal|stopped "
                     r"transmitting|died|dies|dead|switched off for good|crushed|destroyed|burned up)\b", re.I)
TIMES = re.compile(r"\b([A-Z]?[\w'-]+(?: [\w'-]+)?) (?:is|are|was|were) (?:about |nearly |almost |over |more than |roughly )?"
                   r"(\d[\d,.]*|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|fifty|a hundred|a thousand) times "
                   r"(?:as )?(bigger|larger|wider|heavier|hotter|colder|faster|farther|further|brighter|denser|more massive|smaller|longer)"
                   r"(?: than| as) (?:the |our |a |an )?([\w'-]+(?: [\w'-]+)?)", re.I)
_NUMWORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
             "twenty": 20, "fifty": 50, "a hundred": 100, "a thousand": 1000}
CINEMA_MUSIC_GAIN = 0.3
C_KM_S = 299792.458
# NASA 3D Resources models shipped in whatif-engine/assets/models, by a word in the craft's id or label
MODELS = (("voyager", "voyager.glb"), ("cassini", "cassini.glb"), ("juno", "juno.glb"), ("galileo", "galileo.glb"),
          ("hubble", "hubble.glb"), ("webb", "jwst.glb"), ("jwst", "jwst.glb"), ("parker", "parker.glb"), ("pioneer", "pioneer10.glb"),
          ("perseverance", "perseverance.glb"), ("ingenuity", "ingenuity.glb"), ("insight", "insight.glb"), ("iss", "iss.glb"),
          ("messenger", "messenger.glb"), ("magellan", "magellan.glb"), ("rosetta", "rosetta.glb"), ("dawn", "dawn.glb"),
          ("stardust", "stardust.glb"), ("ulysses", "ulysses.glb"), ("viking", "viking_lander.glb"), ("eagle", "apollo_lm.glb"),
          (".lm", "apollo_lm.glb"), ("saturn v", "saturn_v.glb"))
HARDWARE = re.compile(r"\b(antenna|dish|instruments?|cameras?|golden record|record|plutonium|generators?|rtgs?|power|boom|"
                      r"magnetometer|thrusters?|transmitter|computer|memory|bits|watts|kilograms|weighs|built|hardware|spacecraft itself)\b", re.I)
YEARS = re.compile(r"\b(decades?|half a century|years later|years ago|since (19|20)\d\d|(19|20)\d\d)\b", re.I)
SIGNAL = re.compile(r"\b(radio|signal|message|transmission|command|light|data)\b.{0,90}?\b(takes?|took|travel\w*|reach\w*|arriv\w*|"
                    r"hours?|minutes?|light-day|light-hour)\b", re.I)


MAP_MAX = 0.5                 # the map's share of screen time when "budget" is on (the rest: footage, plates, craft shots)
FILL_GAP_S, FILL_MIN_STRETCH_S, FILL_LEAD_S = 7.0, 7.5, 3.0   # a map shot sets the scene for ~3 s, then the What If shot
# the narration decides each shot's move: far away -> pull out, a detail -> push in, round something -> orbit
OUT_W = re.compile(r"\b(far|farther|farthest|distance|distant|billions?|millions?|beyond|edge|outward|away|leav\w*|vast|whole|entire|"
                   r"across|light-years?|interstellar|tiny|speck|behind|outer)\b", re.I)
IN_W = re.compile(r"\b(closer|close|surface|details?|inside|look\w*|instruments?|record|cameras?|dish|antenna|craters?|clouds?|storms?|"
                  r"spot|face|ground|land\w*|zoom\w*|see)\b", re.I)
ORB_W = re.compile(r"\b(around|orbit\w*|circl\w*|spin\w*|turn\w*|rotat\w*|swing\w*|swung)\b", re.I)
# (entry scale, target scale, spin x): > 1 starts wider. in: wide -> close; out: close -> wider; orbit: a wider turn
MOVES = {"in": (1.3, 1.0, 1.0), "out": (0.75, 1.08, 1.0), "orbit": (1.05, 1.0, 1.6), None: (1.2, 1.0, 1.0)}


def narrative_move(words: Sequence[Any], t0: float, t1: float, text: str = "") -> Optional[str]:
    """What the narration says while a shot is on screen -> how the camera moves ("in" / "out" / "orbit", None = a gentle push)."""
    said = " ".join(str(w[0]) for w in words if t0 - 0.2 <= float(w[1]) < t1) or text
    score = {"out": len(OUT_W.findall(said)), "in": len(IN_W.findall(said)), "orbit": len(ORB_W.findall(said))}
    best = max(score, key=score.get)
    return best if score[best] > 0 and list(score.values()).count(score[best]) == 1 else None


def flags(cinema: Any) -> Optional[Dict[str, bool]]:
    """A project's Cinema setting -> {feature: on} (all on by default), or None when Cinema is off."""
    if not cinema:
        return None
    if cinema is True:
        return {k: True for k in FEATURES}
    if isinstance(cinema, dict):
        if cinema.get("enabled") is False:
            return None
        return {k: bool(cinema.get(k, True)) for k in FEATURES}
    return None


# ---- camera ------------------------------------------------------------------------------------------------------------
def about_craft(text: str) -> bool:
    return bool(HARDWARE.search(text or ""))


def hero_shot(trajectory: str) -> Dict[str, Any]:
    """A close-up of the craft itself (its model fills the frame, the Sun's side lit), the camera standing just off it."""
    return {"follow": {"trajectory": trajectory, "lit": True}, "distance": {"km": 0.014}, "el_deg": 16, "az_deg": 32}


def pause_cut(words: Sequence[Any], want: float, lo: float, hi: float) -> Optional[float]:
    """The middle of the narration pause (>= 0.18 s between two words) nearest `want`, within 1.5 s and inside [lo, hi]."""
    best = None
    for a, b in zip(words, list(words)[1:]):
        gap = float(b[1]) - float(a[2])
        if gap >= 0.18:
            mid = (float(a[2]) + float(b[1])) / 2
            if lo <= mid <= hi and abs(mid - want) <= 1.5 and (best is None or abs(mid - want) < abs(best - want)):
                best = mid
    return round(best, 3) if best is not None else None


# ---- the spec ----------------------------------------------------------------------------------------------------------
def craft_model(layer: Dict[str, Any]) -> Optional[str]:
    key = f"{layer.get('id', '')} {layer.get('label', '')} {layer.get('trajectory', '')}".lower()
    return next((f"wi:{m}" for w, m in MODELS if w in key), None)


def _day_month_year(d: Any) -> str:
    """'5 MARCH 1979': strftime's %-d (no leading zero) is not supported on Windows ("Invalid format string")."""
    return f"{d.day} {d.strftime('%B %Y')}".upper()


def _fmt_light(s: float) -> str:
    for unit, sec in (("LIGHT-YEARS", 31557600), ("LIGHT-DAYS", 86400), ("LIGHT-HOURS", 3600), ("LIGHT-MINUTES", 60)):
        if s >= sec:
            v = s / sec
            return f"{v:.1f} {unit if v != 1 else unit[:-1]}"
    return f"{s:.1f} LIGHT-SECONDS"


def _when(words: Sequence[Any], b: Any, rx: "re.Pattern[str]") -> float:
    """When the narration says what triggered a plate (its first word), else a moment into the beat."""
    from .tracking import spoken_at

    m = rx.search(b.text or "")
    if m:
        t = spoken_at(list(words), b.start, b.end, m.group(0).split()[0])
        if t is not None:
            return t
        return b.start + (b.end - b.start) * m.start() / max(1, len(b.text))
    return b.start + 0.4


def _beat_craft(cat: Any, res: Any, b: Any) -> Tuple[Optional[str], Optional[Any]]:
    """The beat's craft (a craft row, else its datasets' craft flying round the Sun): (label, trajectory)."""
    from .catalog import CatalogError

    ctx = res.ctx(b.id) if res else ()
    for it in b.layers:
        if it.type == "craft" and it.id:
            try:
                cq = cat.craft_id(it.id, ctx)
                c = cat.craft(cq)
                return c.get("label", cq), cat.index.trajectories.get(c.get("trajectory") or "")
            except CatalogError:
                continue
    for did in ctx:
        for c in cat.index.datasets[did].craft.values():
            t = cat.index.trajectories.get(c.get("trajectory") or "")
            if t is not None and (t.data.get("frame") or "") == "sun":
                return c.get("label", did), t
    return None, None


def plates(plan: Any, cat: Any, res: Any, clock: Dict[str, Any], notes: List[str],
           taken: Sequence[Tuple[float, float]] = ()) -> List[Dict[str, Any]]:
    """Diagram plates for what the narration explains and the map cannot draw (see the module text). `taken`: the windows the
    CSV's own plates use (an automatic one never lands on them)."""
    from .compile import _boundaries_named, _clock_utc, _sun_km
    from .temporal import parse_iso

    out: List[Dict[str, Any]] = []
    last = -1e9
    compares = [(t, (layer, cite)) for t, layer, cite in compare_plates(plan, notes)]    # exact times: a rounded one fell before its beat
    for b in plan.beats:
        if b.mode != "map" or not b.text or b.end - b.start < PLATE_MIN_S + 1:
            continue
        label, traj = _beat_craft(cat, res, b)
        layer, cite = None, ""
        bounds = _boundaries_named(cat, b)
        if bounds:
            t0 = _when(plan.words, b, re.compile("|".join(re.escape(s) for x in bounds for s in x.get("says", [])) or "x", re.I))
            known = sorted((x for x in (cat.bodies.get("boundaries") or {}).get(bounds[0]["_body"], []) if x.get("au")), key=lambda x: x["au"])
            edges = [0.0] + [float(x["au"]) for x in known] + [float(known[-1]["au"]) * 1.35 if known else 160.0]
            names = ["SUPERSONIC SOLAR WIND"] + [str(x.get("id", "")).replace("_", " ").upper() for x in known[1:]] + ["INTERSTELLAR SPACE"]
            bands = [{"from": a, "to": z, "label": n, "sub": f"{a:.0f}-{z:.0f} AU" if z < edges[-1] else f"BEYOND {a:.0f} AU"}
                     for a, z, n in zip(edges, edges[1:], names)]
            if len(bands) >= 2:
                bands[1]["label"] = "HELIOSHEATH" if "termination" in known[0].get("id", "") else bands[1]["label"]
            layer = {"type": "tm_section", "title": "THE SUN'S BUBBLE", "unit": "AU", "max": edges[-1], "layers": bands,
                     "marks": [{"v": float(x["au"]), "label": str(x.get("label", "")), "color": "amber", "t": t0 + 1.2 + i} for i, x in enumerate(known)]}
            if traj is not None:
                when = _clock_utc(clock, min(b.end - 0.1, t0 + 1))
                samples = [s for s in traj.data.get("samples") or [] if s.get("km") and s.get("anchor", "sun") == "sun"]
                if when and len(samples) >= 2:
                    layer["you"] = [{"t": t0 + 0.6, "v": round(_sun_km(samples, when) / 1.496e8, 1)}]
            cite = "DIAGRAM · THE HELIOSPHERE, DISTANCES FROM THE SUN (APPROXIMATE)"
        elif traj is not None and SIGNAL.search(b.text):
            t0 = _when(plan.words, b, SIGNAL)
            when = _clock_utc(clock, min(b.end - 0.1, t0 + 1))
            samples = [s for s in traj.data.get("samples") or [] if s.get("km") and s.get("anchor", "sun") == "sun"]
            if when and len(samples) >= 2:
                ls = max(2.0, _sun_km(samples, when) / C_KM_S)
                layer = {"type": "tm_logaxis", "min": 0.5, "max": max(3.2e7, ls * 3), "y": 0.56,
                         "marks": [m for m in ({"v": 1.28, "label": "MOON", "sub": "1.3 LIGHT-SECONDS"}, {"v": 499, "label": "SUN", "sub": "8.3 LIGHT-MINUTES"},
                                               {"v": 14900, "label": "NEPTUNE", "sub": "4.1 LIGHT-HOURS"})
                                   if not (ls / 12 < m["v"] < ls * 12)]      # a reference too near the craft's mark would sit on it
                                  + [{"v": round(ls, 1), "label": str(label or "CRAFT").upper(), "sub": _fmt_light(ls)}],
                         "keys": [{"t": t0 + 0.6, "v": 1.28}, {"t": t0 + 2.6, "v": round(ls, 1)}], "node_label": "SIGNAL",
                         "caption": {"text": f"LIGHT FROM EARTH TO {str(label or 'THE CRAFT').upper()}", "color": "amber"}}
                cite = "DIAGRAM · DISTANCES IN LIGHT-TRAVEL TIME, LOGARITHMIC SCALE"
        elif YEARS.search(b.text) and res is not None and res.ctx(b.id):
            t0 = _when(plan.words, b, YEARS)
            ds = cat.index.datasets[res.ctx(b.id)[0]]
            now = _clock_utc(clock, b.start)
            evs = sorted(((parse_iso(e.utc), n) for n, e in ds.events.items() if e.utc and (not now or e.utc <= now)),
                         key=lambda x: x[0])
            evs = [(d, n) for d, n in evs if not n.lower().startswith("t+")][:7]
            if len(evs) >= 3:
                y0, y1 = evs[0][0].year, max(evs[-1][0].year, parse_iso(now).year if now else evs[-1][0].year)
                step = 10 if y1 - y0 <= 60 else 20
                layer = {"type": "tm_timeline", "from": (y0 // 10) * 10, "to": int(math.ceil(y1 / 10.0)) * 10, "step": step,
                         "events": [{"t": round(t0 + 0.5 + 0.55 * i, 3), "year": d.year, "label": n.replace("_", " ").upper()} for i, (d, n) in enumerate(evs)]}
                cite = f"DIAGRAM · {ds.name.upper()} TIMELINE · DATES: {ds.source.upper() or 'MISSION RECORD'}"[:110]
        if layer is None:
            hit = next(((t, v) for t, v in compares if b.start - 1e-6 <= t < b.end), None)
            if hit:
                t0, (layer, cite) = hit
        if layer is None:
            continue
        t0 = max(b.start + 0.2, min(t0, b.end - PLATE_MIN_S - 0.2))
        t1 = min(b.end - 0.2, t0 + PLATE_S)
        if t1 - t0 < PLATE_MIN_S or t0 - last < PLATE_GAP_S or any(a < t1 and t0 < z for a, z in taken):
            continue
        last = t0
        out.append({"type": "cinema_plate", "start": round(t0, 3), "end": round(t1, 3), "fade_in": 0.25, "fade_out": 0.3, "_cite": cite})
        out.append({**layer, "start": round(t0, 3), "end": round(t1, 3), "fade_in": 0.25, "fade_out": 0.3})
        notes.append(f"beat {b.id}: Cinema diagram plate ({layer['type'][3:]}) at {t0:.1f}s")
    return out


def compare_plates(plan: Any, notes: List[str]) -> List[Tuple[float, Dict[str, Any], str]]:
    """'Jupiter is eleven times wider than Earth' -> two bars to scale (a log scale past 50x, it says so): (time, layer, citation)."""
    from .tracking import spoken_at

    out = []
    for b in plan.beats:
        if b.mode != "map" or not b.text:
            continue
        m = TIMES.search(b.text)
        if not m:
            continue
        raw = m.group(2).lower().replace(",", "")
        try:
            n = float(_NUMWORDS.get(raw, raw))
        except ValueError:
            continue
        t0 = spoken_at(list(plan.words), b.start, b.end, m.group(1).split()[0]) or (b.start + (b.end - b.start) * m.start() / max(1, len(b.text)))
        adj = m.group(3).upper()
        out.append((t0, {"type": "tm_compare", "mode": "bars", "title": f"{n:g} TIMES {adj}",
                         "left": {"label": m.group(1).upper(), "value": f"{n:g}×", "color": "amber", "amount": n},
                         "right": {"label": m.group(4).upper(), "value": "1×", "color": "cyan", "amount": 1}},
                    f"DIAGRAM · {adj} TO SCALE, AS THE NARRATION SAYS"))
    return out


def titles(layers: List[Dict[str, Any]]) -> None:
    """StarMap titles become What If title cards: a white first line, a bigger accent second line, centred in the upper third."""
    for i, L in enumerate(layers):
        if L.get("type") != "title":
            continue
        words = str(L.get("text", "")).split()
        k = max(1, len(words) // 2)
        layers[i] = {"type": "tm_title", "line1": " ".join(words[:k]) if len(words) > 1 else "", "line2": " ".join(words[k:]) if len(words) > 1 else " ".join(words),
                     "accent": "amber", "sub": L.get("subtitle", ""), "start": L["start"], "end": L["end"]}


def fades(plan: Any, layers: List[Dict[str, Any]], notes: List[str]) -> None:
    """A probe goes silent, a world kills: the frame fades to black and back in the pause after the sentence (at most three, a
    minute apart) -- the references keep fades for exactly these moments."""
    from .tracking import spoken_at

    last, n = -1e9, 0
    for b in plan.beats:
        for m in re.finditer(r"[^.!?]+[.!?]*", b.text or ""):
            if not SILENCE.search(m.group(0)) or n >= 3:
                continue
            words = m.group(0).split()
            t = spoken_at(list(plan.words), b.start, b.end, words[-1].strip(".,!?")) if words else None
            t = (t + 0.6) if t is not None else b.start + (b.end - b.start) * m.end() / max(1, len(b.text))
            t = min(t, b.end - 1.5)                                    # inside its own beat
            if t - last < 60 or t < b.start:
                continue
            last, n = t, n + 1
            layers.append({"type": "tm_fade", "start": round(t, 3), "end": round(t + 1.4, 3), "fade_in": 0.6, "fade_out": 0.6})
            notes.append(f"beat {b.id}: Cinema fade to black at {t:.1f}s ('{SILENCE.search(m.group(0)).group(0)}')")


def lockups(spec: Dict[str, Any], clock: Dict[str, Any]) -> None:
    """Under a hero close-up of a craft: its name and the date, centred at the bottom (as under the references' hero shots)."""
    from .compile import _clock_utc
    from .temporal import parse_iso

    for m in spec["camera"].get("moves", []):
        f = m["to"].get("follow") or {}
        if not f.get("lit") or m.get("dur"):
            continue
        t = m["t"]
        name = next((L.get("label") for L in spec["layers"] if L.get("type") == "tracker" and L.get("trajectory") == f.get("trajectory")
                     and L["start"] <= t + 0.5 and L["end"] >= t), "") or next(
            (L.get("label") for L in spec["layers"] if L.get("type") == "spacecraft" and L.get("trajectory") == f.get("trajectory")), "")
        if not name:
            continue
        when = _clock_utc(clock, t)
        sub = _day_month_year(parse_iso(when)) if when else ""
        spec["layers"].append({"type": "tm_caption", "text": str(name).split(" · ")[0], "sub": sub, "size": "large", "anchor": "bc",
                               "start": round(t + 0.3, 3), "end": round(t + 4.3, 3), "fade_in": 0.3, "fade_out": 0.4})


_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
          "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1e3, "million": 1e6, "billion": 1e9}
SPOKEN_NUMBER = re.compile(r"\b((?:\d[\d,.]*|(?:%s)(?:[ -](?:%s))?)(?:\s+(?:hundred|thousand|million|billion))*)\s+"
                           r"(kilomet(?:er|re)s? (?:per|an|a) hour|km/h|kilomet(?:er|re)s?|km|miles|light-(?:years?|hours?|days?|minutes?)|years|degrees|hours|days|minutes|moons|"
                           r"watts|kilograms|kg|tonnes|AU|astronomical units|metres|meters|km/h|percent)\b"
                           % ("|".join(list(_UNITS) + list(_TENS)), "|".join(_UNITS)), re.I)


def spoken_number(phrase: str) -> Optional[Tuple[float, str]]:
    """'twenty six billion' -> (26e9, 'BILLION'), '722' -> (722, ''): the figure and the scale word to show with it."""
    words = re.split(r"[ -]+", phrase.lower().replace(",", ""))
    total, cur, scale = 0.0, 0.0, ""
    for w in words:
        if re.fullmatch(r"\d+(\.\d+)?", w):
            cur += float(w)
        elif w in _UNITS:
            cur += _UNITS[w]
        elif w in _TENS:
            cur += _TENS[w]
        elif w == "hundred":
            cur = (cur or 1) * 100
        elif w in ("thousand", "million", "billion"):
            if w in ("million", "billion"):
                scale = w.upper()
                total += cur or 1
                cur = 0
            else:
                cur = (cur or 1) * 1000
        else:
            return None
    v = total + cur
    return (v, scale) if v > 0 else None


def _covered(spec: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Where the map is not on screen: footage, full-frame plates and scenes, and the hero close-ups of a craft."""
    # footage with no file never shows (Generate gives its time back to the clips around it): it does not cover the map
    # a clip that lost its file still covers its time when a clip of the same beat has one: Generate spreads that beat's clips over
    # the whole beat (share_missing_clip_time), so a photo placed in the gap would be laid under them
    has = lambda f: bool(f.get("image") or f.get("file") or f.get("video"))   # noqa: E731
    beat = lambda f: str(f.get("id", "")) if str(f.get("id", "")).startswith("cinema_") else str(f.get("id", "")).rsplit("_", 1)[0]   # noqa: E731
    shown = {beat(f) for f in spec.get("footage", []) if has(f)}
    iv = [(f["start"], f["end"]) for f in spec.get("footage", []) if has(f) or beat(f) in shown]
    iv += [(L["start"], L["end"]) for L in spec["layers"] if L.get("type") in ("cinema_plate", "cinema_hero", "cinema_craft")]
    moves = sorted(spec["camera"].get("moves", []), key=lambda m: m["t"])
    for i, m in enumerate(moves):
        if (m["to"].get("follow") or {}).get("lit"):
            nxt = next((x["t"] for x in moves[i + 1:] if not (x["to"].get("follow") or {}).get("lit")), spec["duration"])
            iv.append((m["t"], nxt))
    iv.sort()
    out: List[List[float]] = []
    for a, z in iv:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], z)
        else:
            out.append([a, z])
    return [(a, z) for a, z in out]


def _map_stretches(spec: Dict[str, Any]) -> List[Tuple[float, float]]:
    out, t = [], 0.0
    for a, z in _covered(spec):
        if a > t:
            out.append((t, a))
        t = max(t, z)
    if t < spec["duration"]:
        out.append((t, spec["duration"]))
    return out


def map_share(spec: Dict[str, Any]) -> float:
    return sum(z - a for a, z in _map_stretches(spec)) / max(1e-6, float(spec["duration"]))


def budget(spec: Dict[str, Any], plan: Any, cat: Any, res: Any, clock: Dict[str, Any], notes: List[str]) -> None:
    """Map at most MAP_MAX of the screen time: the longest map stretches get What If shots, each at the words that call for it --
    the craft in deep space (a craft on screen there), a number full frame (a stat said there), the journey as an orbit map
    (a craft flying round the Sun), the mission timeline (a dated story). Each 4-6 s, never two within FILL_GAP_S."""
    from .compile import _clock_utc
    from .temporal import parse_iso

    layers, D = spec["layers"], float(spec["duration"])
    before = map_share(spec)
    if before <= MAP_MAX:
        return
    added: List[float] = []
    cands: List[Tuple[float, str, Dict[str, Any]]] = []
    for L in layers:
        if L.get("type") == "spacecraft" and L.get("model"):
            for k in range(0, 40):
                t = L["start"] + 1.0 + k * 9.0
                if t > L["end"] - 4.5:
                    break
                cands.append((t, "craft", L))
        elif L.get("type") == "stat_chip" and isinstance(L.get("value"), (int, float)):
            cands.append((L["start"], "number", L))
        elif L.get("type") == "photo_card" and (L.get("image") or L.get("video")):
            cands.append((L["start"], "photo", L))
    for b in plan.beats:
        if b.mode == "footage":
            continue
        label, traj = _beat_craft(cat, res, b)
        if traj is not None and b.end - b.start >= 6:
            for k in range(0, 1 + int((b.end - b.start - 6) // 18)):
                cands.append((b.start + 1.0 + 18 * k, "orbit", {"traj": traj, "label": label, "b": b}))
        # a number the narrator says (digits or words) with its unit: a full-frame number at the words that say it
        from .tracking import spoken_at

        for m in SPOKEN_NUMBER.finditer(b.text or ""):
            got = spoken_number(m.group(1))
            if not got:
                continue
            v, scale = got
            t = spoken_at(list(plan.words), b.start, b.end, m.group(1).split()[0]) or (b.start + (b.end - b.start) * m.start() / max(1, len(b.text)))
            unit = (f"{scale} " if scale else "") + m.group(2).upper().replace("KILOMETERS", "KM").replace("KILOMETRES", "KM").replace("KILOMETER", "KM").replace("KILOMETRE", "KM")
            cands.append((t, "number", {"value": v, "unit": unit.strip(), "label": "", "decimals": 0 if float(v).is_integer() else 1}))
        ctx = res.ctx(b.id) if res else []
        if ctx and len([e for e in cat.index.datasets[ctx[0]].events.values() if e.utc]) >= 3 and b.end - b.start >= 6:
            cands.append((b.start + 1.5, "timeline", {"ds": cat.index.datasets[ctx[0]], "b": b}))
    order = {"photo": 0, "craft": 1, "number": 2, "orbit": 3, "timeline": 4}
    for _ in range(200):
        if map_share(spec) <= MAP_MAX:
            break
        stretches = sorted((s for s in _map_stretches(spec) if s[1] - s[0] >= FILL_MIN_STRETCH_S), key=lambda s: s[0] - s[1])
        placed = False
        for a, z in stretches:
            mid = (a + z) / 2
            # options made for this stretch: the craft on screen here, the journey of the beat's craft, the beat's mission timeline
            local = []
            tl = min(a + FILL_LEAD_S, z - 5.0)
            for L in layers:
                if L.get("type") == "spacecraft" and L.get("model") and L["start"] < z - 5 and L["end"] > a + 3:
                    local.append((max(tl, L["start"] + 0.5), "craft", L))
                    break
            bt = next((b for b in plan.beats if b.mode != "footage" and b.start <= tl < b.end), None)
            if bt is not None:
                label_b, traj_b = _beat_craft(cat, res, bt)
                if traj_b is not None:
                    local.append((tl, "orbit", {"traj": traj_b, "label": label_b, "b": bt}))
                ctx_b = res.ctx(bt.id) if res else []
                if ctx_b and len([e for e in cat.index.datasets[ctx_b[0]].events.values() if e.utc]) >= 3:
                    local.append((tl, "timeline", {"ds": cat.index.datasets[ctx_b[0]], "b": bt}))
            pool = [c for c in cands + local if a + 2.5 <= c[0] <= z - 4.5 and all(abs(c[0] - x) >= FILL_GAP_S for x in added)]
            if not pool:
                continue
            t, kind, src = min(pool, key=lambda c: (order[c[1]], abs(c[0] - (a + FILL_LEAD_S))))
            if (t, kind, src) in cands:
                cands.remove((t, kind, src))
            dur = 5.0 if kind != "photo" else 6.0
            t1 = min(z - 0.3, t + dur)
            if kind == "photo":
                # a photo card becomes the references' real-photo shot: full frame, letterboxed, cited (the card steps aside meanwhile)
                f = {"id": f"cinema_photo_{len(added)}", "start": round(t, 3), "end": round(min(t1, src["end"]), 3),
                     ("video" if src.get("video") else "image"): src.get("video") or src.get("image")}
                if src.get("credit"):
                    f["credit"] = src["credit"]
                if f["end"] - f["start"] < 3.0:
                    continue
                spec.setdefault("footage", []).append(f)
                spec["footage"].sort(key=lambda x: x["start"])
                src["start"] = max(src["start"], f["end"])
                if src["start"] >= src["end"] - 0.5:
                    src["end"] = src["start"]                       # nothing left of the card after its full-frame moment
            elif kind == "timeline":
                ds, b = src["ds"], src["b"]
                now = _clock_utc(clock, t)
                evs = sorted(((parse_iso(e.utc), n) for n, e in ds.events.items() if e.utc and (not now or e.utc <= now)), key=lambda x: x[0])
                evs = [(d, n) for d, n in evs if not n.lower().startswith("t+")][:7]
                if len(evs) < 3:
                    continue
                y0, y1 = evs[0][0].year, max(evs[-1][0].year, parse_iso(now).year if now else evs[-1][0].year)
                layers.append({"type": "cinema_plate", "start": round(t, 3), "end": round(t1, 3), "fade_in": 0.2, "fade_out": 0.3,
                               "_cite": f"DIAGRAM · {ds.name.upper()} TIMELINE"[:100]})
                layers.append({"type": "tm_timeline", "from": (y0 // 10) * 10, "to": int(math.ceil(y1 / 10.0)) * 10, "step": 10 if y1 - y0 <= 60 else 20,
                               "events": [{"t": round(t + 0.5 + 0.55 * i, 3), "year": d.year, "label": n.replace("_", " ").upper()} for i, (d, n) in enumerate(evs)],
                               "start": round(t, 3), "end": round(t1, 3), "fade_in": 0.2, "fade_out": 0.3})
            elif kind == "craft":
                when = _clock_utc(clock, t)
                layers.append({"type": "cinema_craft", "model": src["model"], "start": round(t, 3), "end": round(t1, 3), "fade_in": 0.2,
                               "fade_out": 0.25, "az": 20 + 37 * (len(added) % 4), "_cite": f"NASA 3D MODEL OF {str(next((T.get('label') for T in layers if T.get('type') == 'tracker' and T.get('craft') == src.get('id')), '') or src.get('id', 'THE CRAFT')).split(' · ')[0].upper()}"})
                name = next((T.get("label") for T in layers if T.get("type") == "tracker" and T.get("craft") == src.get("id")), "") or src.get("label") or ""
                layers.append({"type": "tm_caption", "text": str(name).split(" · ")[0].upper() or "SPACECRAFT",
                               "sub": _day_month_year(parse_iso(when)) if when else "", "size": "large", "anchor": "bc",
                               "start": round(t + 0.4, 3), "end": round(t1 - 0.2, 3), "fade_in": 0.3, "fade_out": 0.3, "z": 4})
            elif kind == "number":
                v, dec = src["value"], int(src.get("decimals") or 0)
                layers.append({"type": "cinema_plate", "start": round(t, 3), "end": round(t1, 3), "fade_in": 0.2, "fade_out": 0.3,
                               "_cite": f"DIAGRAM · {str(src.get('label', '')).upper()}".rstrip(" ·")})
                layers.append({"type": "tm_metric", "value": f"{float(v):,.{dec}f}", "unit": src.get("unit", ""), "sub": src.get("label", ""),
                               "size": "hero", "anchor": "center", "count": {"from": 0, "to": float(v), "decimals": dec, "s": 1.0},
                               "start": round(t, 3), "end": round(t1, 3), "fade_in": 0.2, "fade_out": 0.3})
            else:
                traj, b = src["traj"], src["b"]
                when = _clock_utc(clock, t)
                samples = [x for x in traj.data.get("samples") or [] if x.get("km") and x.get("anchor", "sun") == "sun" and (not when or x["utc"] <= when)]
                if len(samples) < 3:
                    continue
                pick = samples[:: max(1, len(samples) // 8)] + [samples[-1]]
                au = [math.hypot(*p["km"]) / 1.496e8 for p in pick]
                ang = [math.degrees(math.atan2(p["km"][2], p["km"][0])) for p in pick]
                path = [{"t": round(t + 0.4 + 4.0 * i / max(1, len(pick) - 1), 3), "au": round(r, 2), "angle": round(g, 1),
                         **({"label": f"{str(src['label']).upper()} · {pick[i]['utc'][:4]}"} if i == len(pick) - 1 else {})}
                        for i, (r, g) in enumerate(zip(au, ang))]
                layers.append({"type": "cinema_plate", "start": round(t, 3), "end": round(t1, 3), "fade_in": 0.2, "fade_out": 0.3,
                               "_cite": "DIAGRAM · THE JOURNEY FROM ABOVE, FROM ITS TRAJECTORY (SQUARE-ROOT DISTANCES)"})
                layers.append({"type": "tm_orbitmap", "scale": "sqrt", "extent_au": round(max(au) * 1.15 + 1, 1), "path": path,
                               "you": str(src["label"] or "").upper(), "start": round(t, 3), "end": round(t1, 3), "fade_in": 0.2, "fade_out": 0.3})
            added.append(t)
            placed = True
            break
        if not placed:
            break
    notes.append(f"Cinema map budget: map {before * 100:.0f}% -> {map_share(spec) * 100:.0f}% of the screen time ({len(added)} What If shots added)")


def _craft_vec(samples: List[Dict[str, Any]], utc: str) -> Optional[List[float]]:
    """The craft's position (km, the trajectory's Sun frame) at utc, between samples (a straight line past the last two)."""
    from .temporal import parse_iso

    if len(samples) < 2:
        return None
    t = parse_iso(utc)
    a, b = samples[0], samples[1]
    for a, b in zip(samples, samples[1:]):
        if parse_iso(b["utc"]) >= t:
            break
    ta, tb = parse_iso(a["utc"]), parse_iso(b["utc"])
    k = (t - ta).total_seconds() / ((tb - ta).total_seconds() or 1.0)
    return [a["km"][i] + (b["km"][i] - a["km"][i]) * k for i in range(3)]


def _earth_vec(utc: str) -> List[float]:
    """Earth round the Sun (km) in the engine's Sun frame (x = equinox, y = celestial north, z = -equatorial y): the standard
    low-precision solar formula (about 0.01 degree), enough for a light time to the second at any interplanetary distance."""
    from datetime import datetime, timezone

    from .temporal import parse_iso

    d = (parse_iso(utc) - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400
    g = math.radians(357.528 + 0.9856003 * d)
    lam = math.radians(280.460 + 0.9856474 * d + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g) + 180.0)   # Earth = Sun + 180
    r = 1.00014 - 0.01671 * math.cos(g) - 0.00014 * math.cos(2 * g)
    eps = math.radians(23.439)
    X, Y, Z = math.cos(lam), math.sin(lam) * math.cos(eps), math.sin(lam) * math.sin(eps)
    return [X * r * 1.495978707e8, Z * r * 1.495978707e8, -Y * r * 1.495978707e8]


def light_clock(spec: Dict[str, Any], plan: Any, cat: Any, res: Any, clock: Dict[str, Any]) -> None:
    """What If's LIGHT FROM EARTH clock, top-left, for a story that follows a craft round the Sun: the real light time from Earth
    to the craft for the date on screen (its trajectory, Earth's place that day), running between keys; the year and the craft
    under it. From the craft's first appearance to the end."""
    from .compile import _clock_utc
    from .temporal import parse_iso

    label, traj = None, None
    for b in plan.beats:
        label, traj = _beat_craft(cat, res, b)
        if traj is not None:
            break
    if traj is None:
        return
    samples = [x for x in traj.data.get("samples") or [] if x.get("km") and x.get("anchor", "sun") == "sun"]
    shown = [L["start"] for L in spec["layers"] if L.get("type") in ("spacecraft", "tracker") and L.get("trajectory", L.get("id", "")) and
             (L.get("trajectory") == traj.id)]
    if len(samples) < 2 or not shown:
        return
    t0, D = min(shown), float(spec["duration"])
    keys, notes = [], []
    t = t0
    while t <= D + 1e-6:
        utc = _clock_utc(clock, t)
        if utc and utc >= samples[0]["utc"]:
            c, e = _craft_vec(samples, utc), _earth_vec(utc)
            sec = math.dist(c, e) / C_KM_S
            keys.append({"t": round(t, 3), "seconds": round(sec, 1)})
            yr = parse_iso(utc).year
            if not notes or notes[-1]["text"] != f"{yr} · {str(label or '').upper()}":
                notes.append({"t": round(t, 3), "text": f"{yr} · {str(label or '').upper()}"})
        t += 4.0
    if keys:
        spec["layers"].append({"type": "tm_clock", "mode": "light", "label": "LIGHT FROM EARTH", "keys": keys, "notes": notes,
                               "start": round(keys[0]["t"], 3), "end": round(D, 3), "fade_in": 0.4, "z": 5})


def headlines(spec: Dict[str, Any], plan: Any, cat: Any) -> None:
    """The CSV's captions become What If headlines: a small cyan kicker ("AT SATURN") over a heavy white line or two, at the left."""
    from .catalog import CatalogError

    for i, L in enumerate(spec["layers"]):
        if L.get("type") != "caption":
            continue
        b = next((x for x in plan.beats if x.start <= L["start"] < x.end), None)
        kicker = L.get("sub", "")
        if not kicker and b is not None and b.place and (b.frame or "") in ("body", "system", "close", "surface"):
            try:
                kicker = f"AT {cat.place(b.place, ()).body.upper()}"
            except CatalogError:
                kicker = ""
        # a long headline: a big first line and a smaller second line, split at a comma or near the middle (as the references)
        text, second = str(L["text"]), str(L.get("sub", "") if kicker != L.get("sub", "") else "")
        if len(text) > 22 and not second:
            words = text.replace(",", ",|").replace(" · ", " ·|").split("|") if ("," in text or " · " in text) else None
            if words and len(words) >= 2:
                text, second = words[0].strip().rstrip(",·").strip(), " ".join(w.strip() for w in words[1:])
            else:
                ws = text.split()
                k = max(1, len(ws) // 2)
                text, second = " ".join(ws[:k]), " ".join(ws[k:])
        spec["layers"][i] = {"type": "tm_caption", "kicker": kicker, "kicker_color": "cyan", "text": text, **({"sub": second} if second else {}),
                             "size": "large", "anchor": "ml",
                             "start": L["start"], "end": max(L["end"], L["start"] + 4.0), "fade_in": 0.25, "fade_out": 0.35, "z": 3}


def whatif_callouts(spec: Dict[str, Any], plan: Any) -> None:
    """What If's own number callouts from the narration (its planner's metrics), where Cinema has none of its own nearby."""
    try:
        from whatif.planner import plan as wi_plan

        script = " ".join(b.text for b in plan.beats if b.text)
        got = wi_plan(list(plan.words), script, float(spec["duration"]), flow_video=False).layers
    except Exception:
        return
    mine = [L["start"] for L in spec["layers"] if L.get("type") in ("tm_metric", "big_number")]
    covered = _covered(spec)
    for L in got:
        if L.get("type") != "tm_metric" or not str(L.get("value", "")).strip() or str(L.get("value", "")).lstrip("≈ ").startswith("0"):
            continue
        t = float(L.get("start", 0))
        if any(abs(t - x) < 6.0 for x in mine) or any(a - 0.5 <= t <= z for a, z in covered):
            continue
        spec["layers"].append({**L, "z": 3})
        mine.append(t)


# StarMap layers that already put words on screen: an information block never lands on them
_TEXT_LAYERS = ("caption", "title", "stat_chip", "big_number", "photo_card", "pointer", "distance", "time_jump", "tm_caption", "tm_metric",
                "tm_title", "tm_annotate", "tm_survival", "tm_fade", "tm_template")


def _wi_words(plan: Any) -> List[Any]:
    """The narration as What If's timed words (whatif.narration.Word), matched to the beats' text."""
    from whatif import narration as nr

    try:
        return nr.words_of(list(plan.words or ()), " ".join(b.text for b in plan.beats if b.text))
    except Exception:
        return []


def info_blocks(spec: Dict[str, Any], plan: Any, notes: List[str], *, cards: bool) -> None:
    """What If's information block (whatif/typeset.py) on the map, the craft and real photos: a cyan kicker, a huge headline or number
    and a sub-line at the left, from the narration's own words, every few seconds where nothing else is said on screen. With `cards`, a
    real photo under a block becomes What If's photo card (the picture framed on the right half, the block beside it)."""
    from types import SimpleNamespace

    from whatif import narration as nr
    from whatif.typeset import typeset

    words = _wi_words(plan)
    if not words:
        return
    hosts: List[Any] = [SimpleNamespace(kind="hero", start=a, end=z, cite=("", "")) for a, z in _map_stretches(spec) if z - a >= 3.0]
    hosts += [SimpleNamespace(kind="craft" if L["type"] == "cinema_craft" else "hero", start=float(L["start"]), end=float(L["end"]), cite=("", ""))
              for L in spec["layers"] if L.get("type") in ("cinema_craft", "cinema_hero")]
    stills = [f for f in spec.get("footage", []) if (f.get("image") or re.search(r"\.(jpe?g|png|webp)$", str(f.get("file", "")), re.I))
              and "AI ILLUSTRATION" not in str(f.get("credit", "")).upper()]
    if cards:
        hosts += [SimpleNamespace(kind="image", start=float(f["start"]), end=float(f["end"]), cite=("REAL IMAGE", "")) for f in stills]
    hosts.sort(key=lambda h: h.start)
    seen = [{"type": "tm_caption", "start": float(L["start"]), "end": float(L["end"]), "text": str(L.get("text") or L.get("value") or "")}
            for L in spec["layers"] if L.get("type") in _TEXT_LAYERS and L.get("start") is not None and L.get("end") is not None]
    n0 = len(seen)
    typeset(hosts, seen, words, nr.extract_metrics(words), float(spec["duration"]), notes)
    added = seen[n0:]
    for L in added:
        L.update(over_footage=True, z=3)
        spec["layers"].append(L)
    if cards:
        for f in stills:
            if any(float(f["start"]) - 0.05 <= L["start"] < float(f["end"]) for L in added):
                f["compose"] = "card_right"


def hold_and_fill(spec: Dict[str, Any], plan: Any, notes: List[str]) -> None:
    """What If's plate rules on Cinema's slates: a graphic that ends a moment before its plate holds its last frame to the next one or the
    cut, and a longer empty stretch carries the words spoken over it (whatif/compile.py), so a slate is never blank."""
    from whatif.compile import _fill_empty_plates
    from whatif.planner import Shot

    slates = [L for L in spec["layers"] if L.get("type") == "cinema_plate"]
    if not slates:
        return
    shots = [Shot(id=f"plate{i}", start=float(L["start"]), end=float(L["end"]), kind="plate") for i, L in enumerate(slates)]
    drawn = [L for L in spec["layers"] if str(L.get("type", "")).startswith(("tm_", "cinema_")) and L.get("type") not in ("cinema_plate", "cinema_plate_hero", "cinema_bubble")]
    for L in _fill_empty_plates(shots, drawn, notes, _wi_words(plan)):
        L.setdefault("z", 4)
        spec["layers"].append(L)


def ambience_shots(spec: Dict[str, Any], plan: Any) -> List[Dict[str, Any]]:
    """What is on screen, as What If's sound reads it (whatif/sound.py picks a bed per shot kind): a craft close-up or hero scene is
    the ship's hum, a beat at a world (body / close / surface frame) a deep drone, footage by the words said over it, else space."""
    out: List[Dict[str, Any]] = []
    for b in plan.beats:
        kind = "image" if b.mode == "footage" else ("globe" if (b.frame or "") in ("body", "close", "surface") else "plate")
        out.append({"start": float(b.start), "end": float(b.end), "kind": kind})
    for L in spec["layers"]:
        if L.get("type") in ("cinema_craft", "cinema_hero"):
            out.append({"start": float(L["start"]), "end": float(L["end"]), "kind": "craft"})
    return [x for x in out if x["end"] > x["start"]]


def date_corner(spec: Dict[str, Any]) -> None:
    """What If's date, top-right, from the universe date on screen, instead of StarMap's mission clock."""
    spec["layers"][:] = [L for L in spec["layers"] if L.get("type") != "mission_clock"]
    if any(L.get("type") == "tm_mission" for L in spec["layers"]):
        return                                        # the CSV's mission card holds the top-right corner (What If V4)
    spec["layers"].append({"type": "tm_clock", "mode": "date", "from_clock": True, "start": 0.0, "end": float(spec["duration"]), "z": 5})


def bubbles(spec: Dict[str, Any], plan: Any, cat: Any) -> None:
    """The heliosphere as the references draw it: a glowing bubble round the Sun at the heliopause, while a heliosphere view is up."""
    known = (cat.bodies.get("boundaries") or {}).get("sun", [])
    au = max((float(x["au"]) for x in known if x.get("au")), default=0)
    if not au:
        return
    spans: List[List[float]] = []
    for b in plan.beats:
        if b.mode != "footage" and (b.frame or "") == "heliosphere":
            if spans and b.start <= spans[-1][1] + 0.5:
                spans[-1][1] = b.end
            else:
                spans.append([b.start, b.end])
    for a, z in spans:
        spec["layers"].append({"type": "cinema_bubble", "around": "sun", "radius_au": au, "start": round(a, 3), "end": round(z, 3), "fade_in": 0.8, "fade_out": 0.8})


def type_moments(layers: List[Dict[str, Any]]) -> None:
    """The full-screen big numbers become type moments on the shot (no dark scrim), in rotating places."""
    anchors = ("upper_left", "upper_right", "mid")
    k = 0
    for i, L in enumerate(layers):
        if L.get("type") != "big_number":
            continue
        v, dec = L.get("value"), int(L.get("decimals") or 0)
        num = f"{float(v):,.{dec}f}" if isinstance(v, (int, float)) else str(v)
        layers[i] = {"type": "tm_metric", "value": num, "unit": L.get("unit", ""), "sub": L.get("label", ""), "size": "hero",
                     "anchor": anchors[k % len(anchors)], "start": L["start"], "end": L["end"], "fade_in": 0.2, "fade_out": 0.4,
                     **({"count": {"from": 0, "to": float(v), "decimals": dec, "s": 1.0}} if isinstance(v, (int, float)) else {})}
        k += 1


def citations(spec: Dict[str, Any], plate_layers: List[Dict[str, Any]]) -> None:
    """The citation line on every shot: footage by its source (a real image, an AI illustration, footage), a plate as a diagram,
    the map as a visualisation. The footage's own credit text moves into it (not drawn twice)."""
    dur = float(spec["duration"])
    spans: List[Tuple[float, float, str, str]] = []
    for f in spec.get("footage", []):
        c = str(f.pop("credit", "") or "")
        if "AI ILLUSTRATION" in c.upper():
            spans.append((f["start"], f["end"], "ILLUSTRATION", "AI-GENERATED (GOOGLE FLOW)"))
        elif c:
            spans.append((f["start"], f["end"], "REAL IMAGE", c.upper()))
        else:
            spans.append((f["start"], f["end"], "FOOTAGE", ""))
    for L in spec.get("layers", []):
        if L.get("type") == "cinema_craft":                      # the craft's NASA model over an illustrative sky
            spans.append((L["start"], L["end"], "ILLUSTRATION", f"{L.pop('_cite', 'NASA 3D MODEL')} · SKY: ILLUSTRATIVE"))
        if L.get("type") == "cinema_hero":                       # a composed 3D scene: drawn, so an illustration
            spans.append((L["start"], L["end"], "ILLUSTRATION", f"{str(L.get('scene', '')).replace('_', ' ').upper()} · COMPOSED 3D SCENE"))
    for p in plate_layers:
        if p.get("type") == "cinema_plate":
            kind, _, text = p.pop("_cite", "").partition(" · ")   # "DIAGRAM · ...", or a template's own ("REAL IMAGE · ...", "ILLUSTRATION")
            spans.append((p["start"], p["end"], kind or "DIAGRAM", text))
    spans.sort()
    segs, t = [], 0.0
    for a, z, kind, text in spans:
        if a > t + 0.3:
            segs.append({"t0": round(t, 3), "t1": round(a, 3), "kind": "VISUALISATION", "text": "REAL SKY FOR THE STORY'S DATES · NASA TEXTURES"})
        segs.append({"t0": round(max(a, t), 3), "t1": round(z, 3), "kind": kind, "text": text})
        t = max(t, z)
    if t < dur - 0.3:
        segs.append({"t0": round(t, 3), "t1": round(dur, 3), "kind": "VISUALISATION", "text": "REAL SKY FOR THE STORY'S DATES · NASA TEXTURES"})
    spec["layers"].append({"type": "tm_cite", "segments": segs, "start": 0.0, "end": dur})


def apply(spec: Dict[str, Any], plan: Any, cat: Any, res: Any, clock: Dict[str, Any], fl: Dict[str, bool], notes: List[str]) -> None:
    """Cinema's changes to a compiled spec (in place)."""
    spec["cinema"] = dict(fl)
    layers = spec["layers"]
    if not fl.get("templates"):
        dropped = [L for L in layers if L.get("_cinema_row") and L.get("type") in ("tm_template", "tm_mission")]
        layers[:] = [L for L in layers if not any(L is D for D in dropped)]
        if dropped:
            notes.append(f"Cinema: {len(dropped)} template / mission row(s) left out (the Templates box is off)")
    plate_layers: List[Dict[str, Any]] = []
    # the CSV's own plates: a slate under each (inserted just before it, so it draws underneath)
    csv_plates = []
    for i in range(len(layers) - 1, -1, -1):
        L = layers[i]
        if L.get("_cinema_row") == "plate" and L.get("type") != "cinema_hero":
            bg = {"type": "cinema_plate", "start": L["start"], "end": L["end"], "fade_in": 0.25, "fade_out": 0.3,
                  "_cite": L.pop("_tpl_cite", None) or f"DIAGRAM · {str(L.get('title', '')).upper()}".rstrip(" ·")}
            layers.insert(i, bg)
            csv_plates.append(bg)
        elif L.get("type") == "cinema_hero":
            csv_plates.append({"type": "cinema_plate_hero", "start": L["start"], "end": L["end"]})
    if fl.get("plates"):
        plate_layers = plates(plan, cat, res, clock, notes, taken=[(p["start"], p["end"]) for p in csv_plates])
        layers.extend(plate_layers)
    plate_layers = plate_layers + [p for p in csv_plates if p.get("type") == "cinema_plate"]
    titles(layers)
    fades(plan, layers, notes)
    headlines(spec, plan, cat)
    date_corner(spec)
    light_clock(spec, plan, cat, res, clock)
    bubbles(spec, plan, cat)
    for L in layers:
        if L.get("type") == "tracker" and not L.get("body"):
            L["style"] = "node"                                   # What If's marker: a small node, a leader, the name
    if fl.get("hero"):
        lockups(spec, clock)
    if fl.get("type"):
        type_moments(layers)
    if fl.get("hero"):
        for L in layers:
            if L.get("type") == "spacecraft" and not L.get("model"):
                m = craft_model(L)
                if m:
                    L["model"] = m
    if fl.get("budget"):
        budget(spec, plan, cat, res, clock, notes)
    if fl.get("type"):
        whatif_callouts(spec, plan)
        plate_layers = plate_layers + [L for L in layers if L.get("type") == "cinema_plate" and L not in plate_layers]
    if fl.get("fill"):
        hold_and_fill(spec, plan, notes)
    if fl.get("blocks"):
        info_blocks(spec, plan, notes, cards=bool(fl.get("cards") and fl.get("photos")))
    # layering as in What If: instruments and the citation line stay over a hero scene; they step back over a diagram plate (What If's
    # plateAlpha reads spec.shots); a fade covers everything; a title card leaves when a plate, a hero scene or a survival intro opens
    spec["shots"] = [{"start": L["start"], "end": L["end"], "kind": "plate"} for L in layers if L.get("type") == "cinema_plate"]
    for L in layers:
        if L.get("type") in ("tm_survival", "tm_clock", "tm_gauge", "tm_cite"):
            L["z"] = 5
        elif L.get("type") == "tm_fade":
            L["z"] = 10
    scene_starts = sorted([L["start"] for L in layers if L.get("type") in ("cinema_plate", "cinema_hero")]
                          + [L["intro"]["start"] for L in layers if L.get("type") == "tm_survival" and isinstance(L.get("intro"), dict)])
    for L in layers:
        if L.get("type") == "tm_title":
            nxt = next((t for t in scene_starts if t > L["start"] + 0.5), None)
            if nxt is not None and nxt < L["end"]:
                L["end"] = round(nxt - 0.05, 3)
    if fl.get("photos"):
        citations(spec, plate_layers)
        for L in layers:
            if L.get("type") == "tm_cite":
                L["z"] = 5
    else:
        for p in plate_layers:
            p.pop("_cite", None)
