"""A StarMap plan (beat_csv.Plan) -> an engine spec (starmap-engine/README.md).

The CSV speaks in story terms; this turns them into the engine's generic layers:
  * a map beat's place + frame + type -> a camera shot, and a glide to it when the beat starts (moves happen on the map;
    after footage the camera glides from where it was, so the viewer always sees where they are);
  * a beat's date (an event of a dataset, an event +/- time, mission time, now, or an ISO date) -> a universe clock key; between
    two beats time runs on screen or jumps (resolve.py decides; a jump is hidden by footage or by a time-jump card);
  * layer rows -> title / marker / region / trajectory / spacecraft / orbit / stat_chip / caption / distance layers;
  * cards -> photo_card layers; clips -> footage beats (a beat's clips play one after another);
  * automatic: atmospheres (bodies whose catalog entry has one), body labels, a mission clock per mission (T+ / T-, its own
    T-zero), status badges (PLANNED / PROJECTED / HYPOTHETICAL / ESTIMATED), the FLIGHT PATH ILLUSTRATED footnote, the
    channel name (the app's watermark setting).
Every name is resolved in its beat's context (resolve.py): a video may draw on any number of datasets at once. Nothing here
knows a mission: Apollo 11 is a dataset (starmap/packs/apollo11.json).
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .beat_csv import DEFAULT_HOLD, Beat, Item, Plan
from .catalog import Catalog, CatalogError, Place, iso_seconds
from .actions import BeatAction, resolve_actions
from .resolve import BeatContext, Resolution, resolve
from .temporal import BADGE, CERTAINTY, iso, least_certain, parse_iso

W, H, FOV = 1920, 1080, 40.0
TAN_HALF = math.tan(math.radians(FOV / 2))
CARD_W, CARD_H = 420, 303
CARD_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}     # a card with one of these plays the clip
CARD_XY = {"tr": (W - 63 - CARD_W, 170), "mr": (W - 63 - CARD_W, 520), "ml": (63, 330), "bl": (63, 560)}
CARD_ORDER = ("tr", "ml", "mr", "bl")
DEFAULT_DATE = "2025-01-01T00:00:00Z"
# how uncertain things look: a generic palette by status (the engine only ever sees colours and dashes)
STATUS_STYLE = {"planned": "#5fd3ff", "projected": "#c79bff", "hypothetical": "#ff9f5a"}
ESTIMATED_COLOR = "#ffc857"
JUMP_LEAD_S, JUMP_TAIL_S, JUMP_CUT_S = 0.45, 1.8, 0.02
UNIVERSE_VIEW_LY = 4.2e10          # the universe frame: far enough out to see the 13.8-billion-light-year ball whole
KM_PER_LY, KM_PER_AU, C_KM_S = 9.4607e12, 1.496e8, 299792.458
_SCALE_WORDS = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
_LIGHT_S = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800}


def ring_radius(text: str) -> Dict[str, float]:
    """ "1 light-hour", "13 billion light-years", "100 AU", "384,400 km" -> an engine distance."""
    m = re.fullmatch(r"\s*([\d.,]+)\s*(thousand|million|billion)?\s*(light[- ]?(second|minute|hour|day|week|year)s?|ly|au|km)\s*", text.lower())
    if not m:
        raise CatalogError(f"a ring is a number and a unit, like 1 light-hour, 1 light-year, 100 AU or 13 billion light-years (got {text!r})")
    n = float(m.group(1).replace(",", "")) * _SCALE_WORDS.get(m.group(2) or "", 1)
    unit, light = m.group(3), m.group(4)
    if unit in ("ly",) or light == "year":
        return {"ly": n}
    if light:
        return {"km": n * _LIGHT_S[light] * C_KM_S}
    return {"au": n} if unit == "au" else {"km": n}


@dataclass
class Compiled:
    spec: Dict[str, Any]
    notes: List[str] = field(default_factory=list)
    needs_media: List[Tuple[int, str]] = field(default_factory=list)      # (row, asset) still to be found
    resolution: Optional[Any] = None                                       # resolve.Resolution: datasets, beat contexts, jumps
    actions: Dict[str, Any] = field(default_factory=dict)                  # actions.BeatAction by beat: how each event is shown
    warnings: List[str] = field(default_factory=list)


class CompileError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# ---- camera ---------------------------------------------------------------------------------------------------------
def _approx_km(shot: Dict[str, Any], cat: Catalog, place: Place) -> float:
    """Rough camera distance of a shot (for choosing how long a glide between shots takes)."""
    if "_km" in shot:                                          # an action's path frame says how big it is
        return float(shot["_km"])
    if "distance" in shot:
        d = shot["distance"]
        return d.get("km") or d.get("au", 0) * 1.496e8 or d.get("ly", 0) * 9.4607e12
    if "fill" in shot:
        return cat.body_radius_km(place.body if place.kind != "pair" else place.body) / TAN_HALF / shot["fill"]
    if "fit" in shot:
        return 3.9e5 / 2 / TAN_HALF * shot["fit"]
    return 1e4


def shot_for(cat: Catalog, beat: Beat, ctx: Sequence[str] = ()) -> Tuple[Dict[str, Any], Place]:
    """The camera shot for a map beat: what (place) at what size (frame), lit from the Sun's side."""
    p = cat.place(beat.place, ctx)
    f = beat.frame
    shot: Dict[str, Any]
    galaxy = lambda b: next((x.get("kind") for x in cat.world if x["id"] == b), "") == "galaxy"  # noqa: E731
    if f == "universe":
        shot = {"target": p.body, "distance": {"ly": UNIVERSE_VIEW_LY}, "el_deg": 30}   # the whole observable universe
    elif p.kind == "pair" and (galaxy(p.body) or galaxy(p.other)):
        shot = {"target": p.ref, "fit": 1.05, "el_deg": 30}                    # galaxies: no Sun to light them from
    elif f == "galaxy" or galaxy(p.body):
        g = p.body if galaxy(p.body) else "milkyway"
        shot = {"target": g, "distance": {"ly": round(cat.body_radius_km(g) / 9.4607e12 * 3.1)}, "el_deg": 58}
    elif f in ("solar", "inner", "heliosphere") or (p.body == "sun" and p.kind == "body" and f not in ("body", "close", "surface")):
        au = {"solar": 45, "heliosphere": 420}.get(f, 3.2)          # heliosphere: out past the planets, where Voyager is now
        shot = {"target": "sun", "distance": {"au": au}, "el_deg": 35 if f in ("solar", "heliosphere") else 40}
    elif p.kind == "pair":
        shot = {"target": p.ref, "fit": {"system": 1.5, "body": 1.3}.get(f, 1.15), "light": "front", "el_deg": 25}
    elif f == "system":
        parent = cat.bodies.get("parent_system", {}).get(p.body)
        child = cat.bodies.get("system_view", {}).get(p.body)       # a planet's system: the planet with its main moon
        shot = ({"target": f"{parent}+{p.body}", "fit": 1.5, "light": "front", "el_deg": 25} if parent
                else {"target": f"{p.body}+{child}", "fit": 1.5, "light": "front", "el_deg": 25} if child
                else {"target": p.body, "fill": 0.3, "light": "side", "el_deg": 20})   # no moon to pair with: the planet itself
    elif p.kind == "site":
        R = cat.body_radius_km(p.body)
        if f == "surface":
            shot = {"target": p.ref, "distance": {"km": round(max(300.0, 0.3 * R))}, "light": "side", "el_deg": 25}
        elif f == "close":
            shot = {"target": p.ref, "distance": {"km": round(1.2 * R)}, "light": "side", "el_deg": 55}
        else:                                                   # body: the whole body, the site facing the camera
            shot = {"target": p.ref, "distance": {"km": round(R / (TAN_HALF * 0.5) - R)}, "light": "front", "el_deg": 80}
    else:
        shot = {"target": p.body, "fill": {"body": 0.5, "close": 1.25, "surface": 2.2}[f], "light": "side", "el_deg": {"body": 20, "close": 8, "surface": 4}[f]}
    if beat.move == "orbit":
        shot["orbit_deg_per_s"] = 2.0
    if any(L.type in ("orbit", "path") for L in beat.layers) and "el_deg" in shot and p.kind != "site" and f not in ("galaxy", "solar", "inner"):
        shot["el_deg"] = max(shot["el_deg"], 45)               # look down on an orbit or a path, not along it
    if "fit" in beat.extra and "fit" in shot:                # a pair framed wider or tighter
        shot["fit"] = float(beat.extra["fit"])
    for k in ("az_deg", "el_deg", "light"):                   # a hand-written CSV may fine-tune through extra
        if k in beat.extra:
            shot[k] = beat.extra[k]
    return shot, p


def _scaled(shot: Dict[str, Any], k: float) -> Dict[str, Any]:
    s = copy.deepcopy(shot)
    if "distance" in s:
        s["distance"] = {u: v * k for u, v in s["distance"].items()}
    elif "fill" in s:
        s["fill"] = s["fill"] / k
    elif "fit" in s:
        s["fit"] = s["fit"] * k
    elif "path" in s:
        s["path"]["fit"] = s["path"].get("fit", 1.3) * k      # a held stretch of a craft's path: framed a little wider
    return s


OWN_MOVES = ("push_in", "pull_out", "orbit")              # a beat's own camera move; anything else (an action, hold) creeps


def _creep(length: float) -> float:
    """push_in of a quiet beat (no move of its own, nothing travelling in it): how much wider it starts than it ends.
    Restrained -- at most 6% over the whole beat; the always-on drift is what keeps a shot alive, not a zoom."""
    return min(1.06, 1.0 + 0.006 * max(0.0, length))


# each new view opens with a purposeful move, in rotation, so consecutive beats never feel the same:
#   push    starts wider and closes in on the subject as it is named
#   reveal  starts close on the subject and pulls back to show where it is
#   settle  a gentle creep (the classic quiet shot), between the two stronger ones
RECIPES = (("push", 1.5), ("settle", 1.15), ("reveal", 0.65))
# Cinema's "every shot keeps moving": a shot is on screen a few seconds between cuts, so each one visibly pushes in and turns
CINEMA_PUSH, CINEMA_SPIN, CINEMA_SPIN_CLOSE, CINEMA_SPIN_ANGLE, CINEMA_SPIN_ACTION, CINEMA_CUT_PUSH = 1.2, 3.5, 4.0, 4.5, 2.0, 1.2
OPENING_PUSH = 1.7              # the video's first shot pushes in hard: the first seconds decide whether a viewer stays
DRIFT_DEG_PER_S = 0.9                     # the slow orbit round each subject: a planet's face visibly turns (0.35 read as frozen)
VARY_AFTER_S = 15.0                       # one view held this long across beats: the next beat sees it from a new angle
_VARY_AZ = (32.0, -28.0, 20.0, -36.0)
_VARY_EL = (12.0, -8.0, 18.0, -4.0)


CUT_MIN_S = 4.0                 # no cut leaves a shot shorter than this
CUTS_FROM_S = (9.0, 15.0)       # a beat this long is cut into 2, this long into 3 shots


def _close_up(shot: Dict[str, Any], cat: Catalog) -> Optional[Dict[str, Any]]:
    """The close-up of a view: its body bigger in frame, a pair's first body on its own, a far view much nearer."""
    t = str(shot.get("target", ""))
    if "fill" in shot:
        s = copy.deepcopy(shot)
        s["fill"] = min(0.95, float(shot["fill"]) * 1.9)
        return s
    if "fit" in shot and "+" in t:
        a = t.split("+")[0].strip()
        if a in cat.body_ids and next((w.get("kind") for w in cat.world if w["id"] == a), "") in ("body", "star"):
            return {"target": a, "fill": 0.45, "light": shot.get("light", "side"), "el_deg": 20}
        return None
    if "distance" in shot:
        return _scaled(shot, 0.38)
    return None


def _cut_times(b: Beat, words: List[Any], n: int) -> List[float]:
    """n - 1 cut moments spread through the beat, each on the start of a spoken word near its even share (a cut on a word
    reads as edited; between words it reads as a glitch)."""
    out = []
    for k in range(1, n):
        want = b.start + (b.end - b.start) * k / n
        near = [w[1] for w in words if abs(w[1] - want) <= 1.2 and b.start + CUT_MIN_S <= w[1] <= b.end - CUT_MIN_S]
        t = min(near, key=lambda x: abs(x - want)) if near else want
        if (not out or t - out[-1] >= CUT_MIN_S) and b.end - t >= CUT_MIN_S and t - b.start >= CUT_MIN_S:
            out.append(round(t, 3))
    return out


def _view_sig(shot: Dict[str, Any]) -> Tuple[Any, ...]:
    """What the viewer would call the same picture: the same subject, at about the same size, from about the same angle."""
    if "path" in shot:
        p = shot["path"]
        return ("path", p.get("trajectory"), p.get("from_utc", "")[:7], p.get("to_utc", "")[:7], round(float(shot.get("el_deg", 25)) / 10))
    size = next(((k, round(math.log10(max(float(v), 1e-9)) * 3)) for k, v in (shot.get("distance") or {}).items()), None) \
        or ("fill", round(float(shot.get("fill", 0)) * 4)) if "fill" in shot else ("fit", round(float(shot.get("fit", 0)) * 2))
    return (shot.get("target"), str(shot.get("follow")), size, round(float(shot.get("el_deg", 0)) / 10), round(float(shot.get("az_deg", 0)) / 15))


def _variant(shot: Dict[str, Any], n: int) -> Dict[str, Any]:
    """The same subject at the same size, seen from another angle (the n-th of a run): a pair framed by its separation only
    rises or sinks (its side-on view is its point), anything else also turns round it -- a lit side stays lit."""
    s = copy.deepcopy(shot)
    el = float(s.get("el_deg", 20))
    s["el_deg"] = max(6.0, min(80.0, el + _VARY_EL[n % len(_VARY_EL)] * (1.4 if "fit" in s and "+" in str(s.get("target")) else 1.0)))
    if not ("fit" in s and "+" in str(s.get("target"))) and "path" not in s and "follow" not in s:
        s["az_deg"] = float(s.get("az_deg", 0)) + _VARY_AZ[n % len(_VARY_AZ)]
    return s


def _reveal_s(from_km: float, to_km: float, length: float) -> float:
    """How long a pull_out / push_in between two scales takes: long enough to read as one deliberate camera move (about
    2.2 s per factor of e in scale, so 35x takes about 8 s), never more than 85% of the beat."""
    ratio = abs(math.log(max(to_km, 1e-3) / max(from_km, 1e-3)))
    return min(max(4.5, 2.2 * ratio), 0.85 * length)


JOURNEY_EL = (35.0, 58.0, 24.0, 48.0)     # a run of journey views: each beat looks at the journey from a new angle


def _sun_km(samples: List[Dict[str, Any]], utc: str) -> float:
    """How far from the Sun a craft is at utc (km), from its samples (a straight line on past the last two)."""
    t = parse_iso(utc)
    a, b = samples[0], samples[1]
    for a, b in zip(samples, samples[1:]):
        if parse_iso(b["utc"]) >= t:
            break
    ta, tb = parse_iso(a["utc"]), parse_iso(b["utc"])
    k = max(0.0, (t - ta).total_seconds() / ((tb - ta).total_seconds() or 1.0))
    return math.hypot(*(a["km"][i] + (b["km"][i] - a["km"][i]) * k for i in range(3)))


def _boundaries_named(cat: Catalog, b: Beat) -> List[Dict[str, Any]]:
    """The boundaries round a map beat's body (bodies.json "boundaries") that its narration names, each with _body and the
    _hit phrase."""
    known = (cat.bodies.get("boundaries") or {}) if isinstance(getattr(cat, "bodies", None), dict) else {}
    if b.mode == "footage" or not known:
        return []
    try:
        body = cat.place(b.place, ()).body
    except CatalogError:
        return []
    said = re.sub(r"[^a-z ]", " ", (b.text or "").lower())
    out = []
    for bd in known.get(body, []):
        hit = next((s for s in bd.get("says", []) if re.search(rf"\b{re.escape(s)}\b", said)), None)
        if hit:
            out.append({**bd, "_body": body, "_hit": hit})
    return out


def _named_boundaries(cat: Catalog, plan: Plan, layers: List[Dict[str, Any]], notes: List[str]) -> List[Dict[str, Any]]:
    """A map beat whose narration names a boundary round a body it frames ("the termination shock", "the heliopause", "an
    enormous bubble ... called the heliosphere") shows it: a labelled ring round the body, facing the camera (a bubble's
    outline from any angle), from the word that names it to the end of the beat. These had no geometry, so the CSV could
    only caption them, and eight minutes of the 011 Voyager video were one Sun-to-craft path while the narration explained
    the heliosphere's layers. A beat whose CSV already draws rings round that body is left as written."""
    out: List[Dict[str, Any]] = []
    words = [(re.sub(r"[^a-z]", "", str(w[0]).lower()), float(w[1])) for w in (plan.words or ())]
    for b in plan.beats:
        named = _boundaries_named(cat, b)
        if not named:
            continue
        body = named[0]["_body"]
        if any(L.get("type") == "rings" and L.get("around") == body and L["start"] < b.end and L["end"] > b.start for L in layers):
            continue
        rings, first = [], b.end
        for bd in named:
            w0 = bd["_hit"].split()[0]
            t = next((t for w, t in words if w == w0 and b.start - 0.2 <= t < b.end), b.start)
            first = min(first, t)
            rings.append({"radius": {"au": bd["au"]}, "label": bd["label"], "names": bd.get("says", [])})
        hit = next((L for L in layers if L.get("type") == "spacecraft" and L.get("id") and L["start"] < b.end - 1.0
                    and L["end"] > first), None)
        craft = hit["id"] if hit else None
        if hit is not None and hit["start"] > first:
            first = hit["start"]                     # the craft first, then the boundary drawn through where it is
        end = b.end
        i = plan.beats.index(b)
        nxt = plan.beats[i + 1] if i + 1 < len(plan.beats) else None
        if end - first < 4.0 and nxt is not None and nxt.mode != "footage" and nxt.place.lower() == b.place.lower():
            end = min(nxt.end, first + 6.0)          # named in a beat's last words: it stays long enough to be seen
        if rings and end - first >= 1.0:
            # each stretch is drawn through the craft on screen in it (a beat's craft leaves with its beat)
            for t0, t1 in ([(first, b.end), (b.end, end)] if end > b.end else [(first, end)]):
                c = next((L["id"] for L in layers if L.get("type") == "spacecraft" and L.get("id") and L["start"] < t1 - 0.5 and L["end"] > t0 + 0.5), craft)
                if t1 - t0 >= 0.5:
                    out.append({"type": "rings", "around": body, "plane": "view", **({"through": c, "arc_deg": 40} if c else {}), "subject": True,
                                "rings": rings, "start": round(t0, 3), "end": round(t1, 3), **({"fade_in": 0.6} if t0 == first else {}), "_row": b.row})
            notes.append(f"beat {b.id}: the narration names {', '.join(r['label'] for r in rings)}; drawn as rings round {body}")
    return out


def _craft_sun_km(cat: Catalog, b: Beat, res: Optional[Resolution], clock: Optional[Dict[str, Any]]) -> float:
    """How far from the Sun the beat's farthest craft row gets during the beat (km; 0 when it has none flying round the Sun)."""
    if not clock or not clock.get("keys"):
        return 0.0
    far = 0.0
    for it in b.layers:
        if it.type != "craft" or not it.id:
            continue
        try:
            T = cat.index.trajectories.get(cat.craft(cat.craft_id(it.id, res.ctx(b.id) if res else ())).get("trajectory") or "")
        except CatalogError:
            continue
        if T is None or (T.data.get("frame") or "") != "sun":
            continue
        samples = [x for x in T.data.get("samples") or [] if x.get("km") and x.get("anchor", "sun") == "sun"]
        for t in (b.start, max(b.start, b.end - 0.05)):
            u = _clock_utc(clock, t)
            if len(samples) >= 2 and u and parse_iso(u) > parse_iso(samples[0]["utc"]):
                far = max(far, _sun_km(samples, u))
    return far


def journeys(cat: Catalog, plan: Plan, res: Optional[Resolution], clock: Optional[Dict[str, Any]],
             actions: Optional[Dict[str, BeatAction]] = None) -> Dict[str, Dict[str, Any]]:
    """Heliosphere beats with a craft out past the planets -> the stretch of its path from launch to where it is at the end of
    the beat, framed whole (a camera "path" shot): the Sun and planets at one end, the craft at the other. The fixed
    Sun-centred view 420 AU out left the planets a speck in an empty black frame and the craft at its edge, or off it, and
    a run of such beats read as one frozen picture. The stretch already runs to where the craft is by the end of the beat,
    so the shot needs no keep. A beat with no craft row of its own keeps the last one's craft."""
    out: Dict[str, Dict[str, Any]] = {}
    if not clock or not clock.get("keys"):
        return out
    carry: Optional[str] = None
    for b in plan.beats:
        if b.mode == "footage":
            continue
        act = (actions or {}).get(b.id)
        if b.frame != "heliosphere" or (act is not None and (act.intro is not None or act.camera)):
            carry = None if b.frame not in ("heliosphere", "solar") else carry
            continue
        tid = None
        for it in b.layers:
            if it.type == "craft" and it.id:
                try:
                    tid = cat.craft(cat.craft_id(it.id, res.ctx(b.id) if res else ())).get("trajectory")
                except CatalogError:
                    tid = None
                if tid:
                    break
        if not tid and res is not None:
            # no craft row: the craft of the beat's own mission (the only one flying out among the planets), else the last one
            for did in res.ctx(b.id):
                for cr in cat.index.datasets[did].craft.values():
                    t = cat.index.trajectories.get(cr.get("trajectory") or "")
                    if t is not None and (t.data.get("frame") or "") == "sun":
                        tid = tid or t.id
        tid = tid or carry
        T = cat.index.trajectories.get(tid or "")
        if T is None or (T.data.get("frame") or "") != "sun":
            continue
        samples = [x for x in T.data.get("samples") or [] if x.get("km") and x.get("anchor", "sun") == "sun"]
        # the beat's own last moment, not b.end: the next beat's date takes over exactly there (a jump back to 1977 at the end
        # of a "now" beat dropped its craft framing and left the Sun-centred planets on screen while the craft was named)
        to_utc = _clock_utc(clock, max(b.start, b.end - 0.05))
        if len(samples) < 2 or not to_utc or parse_iso(to_utc) <= parse_iso(samples[0]["utc"]):
            continue
        r = _sun_km(samples, to_utc)
        if r < 5 * KM_PER_AU:
            continue                                              # still among the inner planets: the usual view shows it
        carry = tid
        out[b.id] = {"path": {"trajectory": tid, "from_utc": samples[0]["utc"], "to_utc": to_utc, "ref_utc": to_utc, "fit": 1.45},
                     "el_deg": float(b.extra.get("el_deg", 35)),
                     "_km": round(r / 2 * 1.45 / TAN_HALF), "_r": r}
    return out


def _repaired(shot: Dict[str, Any], fix: Dict[str, Any]) -> Dict[str, Any]:
    """An action's path frame as the screen audit asked: fit (> 1 wider), stretch (the stretch of path shown, x its length, about
    its middle -- a stretch so short the craft sits alone in black space)."""
    if not fix or "path" not in shot:
        return shot
    s = copy.deepcopy(shot)
    p = s["path"]
    if fix.get("fit"):
        p["fit"] = p.get("fit", 1.3) * fix["fit"]
    if fix.get("stretch") and p.get("from_utc") and p.get("to_utc"):
        a, z = parse_iso(p["from_utc"]), parse_iso(p["to_utc"])
        mid, half = a + (z - a) / 2, (z - a) / 2 * fix["stretch"]
        p["from_utc"], p["to_utc"] = iso(mid - half), iso(mid + half)
        if p.get("ref_utc"):
            p["ref_utc"] = iso(mid)
    return s


def _action_shot(shot: Optional[Dict[str, Any]], usual: Dict[str, Any], act: BeatAction, b: Beat) -> Dict[str, Any]:
    """An action's camera intent as a shot of the existing camera (None = the beat's usual view; a motion placeholder gets the
    beat's narration-paced motion)."""
    s = copy.deepcopy(usual if shot is None else shot)
    if s.get("follow") and s["follow"].get("motion") == "beat":
        s["follow"]["motion"] = act.motion(b.start, b.end)
        if s["follow"]["motion"] is None:
            del s["follow"]["motion"]
    if s.get("keep") and act.motion(b.start, b.end):
        s["keep"]["motion"] = act.motion(b.start, b.end)      # a narration-paced craft: keep it in frame where IT is
    return s


HELIO_AU = {"mercury": 0.39, "venus": 0.72, "earth": 1.0, "moon": 1.0, "mars": 1.52, "phobos": 1.52, "deimos": 1.52, "ceres": 2.77,
            "jupiter": 5.2, "io": 5.2, "europa": 5.2, "ganymede": 5.2, "callisto": 5.2, "saturn": 9.54, "titan": 9.54, "enceladus": 9.54,
            "uranus": 19.2, "neptune": 30.1, "triton": 30.1, "pluto": 39.5, "charon": 39.5}
TRAVEL_MIN_AU = 0.6           # two bodies closer together than this (the Earth and the Moon) are a short hop, not a journey


def _helio(shot: Optional[Dict[str, Any]]) -> Optional[float]:
    """The Sun distance (AU) of the body a plain shot looks at; None for a path, a craft, a pair or a place not in the table."""
    if not shot or "path" in shot or "follow" in shot:
        return None
    t = str(shot.get("target", ""))
    return HELIO_AU.get(t) if t and "+" not in t and "@" not in t else None


def _travel_via(prev: Optional[Dict[str, Any]], nxt: Dict[str, Any], glide: float, length: float) -> Optional[Dict[str, Any]]:
    """The wide shot a camera passes through going from one body to another (zoom out over the system, zoom in on the next), or
    None when they are the same body, close together, or the beat is too short to afford the trip."""
    a, b = _helio(prev), _helio(nxt)
    if a is None or b is None or prev.get("target") == nxt.get("target") or abs(a - b) < TRAVEL_MIN_AU or length < 6.0:
        return None
    return {"target": "sun", "distance": {"au": round(max(a, b) * 2.2 + 2.0, 1)}, "el_deg": 38, "spin": CINEMA_SPIN, "_travel": True}


def build_camera(cat: Catalog, plan: Plan, notes: List[str], res: Optional[Resolution] = None,
                 actions: Optional[Dict[str, BeatAction]] = None, clock: Optional[Dict[str, Any]] = None,
                 repairs: Optional[Dict[str, Dict[str, Any]]] = None, cinema: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    """cinema: the Cinema option's features (cinema.py), None for Classic StarMap.
    repairs: per beat, what the screen audit asked for (see repair.py): scale (> 1 frames wider, < 1 closer), creep (how
    much wider the beat starts than it ends), orbit (degrees a second round the subject)."""
    start: Optional[Dict[str, Any]] = None
    view_t0, nvar, view_sig = 0.0, 0, None                        # the picture on screen: since when, how varied, which
    recipe_n = 0                                                  # new views opened so far (they take the recipes in turn)
    journey = journeys(cat, plan, res, clock, actions)
    run = 0                                                       # journey views in a row so far
    moves: List[Dict[str, Any]] = []
    prev_key, prev_km, cur, prev_end = None, None, None, -1.0
    # a jump in time between missions or eras: the map dips dark behind the time-jump card, and the camera CUTS there
    # instead of sweeping across the solar system
    cut_in = {t.b for t in (res.transitions if res else []) if t.kind == "jump" and not t.hidden_by_footage}
    for b in plan.beats:
        if b.mode == "footage":
            continue
        shot, place = shot_for(cat, b, res.ctx(b.id) if res else ())
        if b.id in journey:
            # the same journey beat after beat: each one glides to a new angle on it, so a long run never sits on one
            # picture (the creep alone is too slow to see at this scale)
            run = run + 1 if prev_key and prev_key[0] == "journey" else 0
            shot = copy.deepcopy(journey[b.id])
            r_named = max([bd["au"] * KM_PER_AU for bd in _boundaries_named(cat, b)] + [0.0])
            if r_named > 0.8 * shot["_r"]:
                # a boundary the narration names is part of the picture: the frame widens to hold it (the journey camera's drift
                # now swings within 14 degrees of the framed angle, so a wider frame no longer turns end-on)
                k = min(2.5, 1.15 * r_named / shot["_r"])
                shot["path"]["fit"] = round(shot["path"]["fit"] * k, 3)
                shot["_km"] = shot["_km"] * k
            shot.pop("_r", None)
            if "el_deg" not in b.extra:
                shot["el_deg"] = JOURNEY_EL[run % len(JOURNEY_EL)]
        fix = (repairs or {}).get(b.id, {})
        if fix.get("scale"):
            shot = _scaled(shot, fix["scale"])
            if "_km" in shot:
                shot["_km"] *= fix["scale"]
            if "fit" in shot and "+" in str(shot.get("target")):
                shot["fit"] = max(1.15, shot["fit"])               # a pair is never framed tighter than both ends
        if fix.get("orbit") and "path" not in shot and "follow" not in shot:
            shot["orbit_deg_per_s"] = fix["orbit"]
        if fix.get("spin"):
            shot["spin"] = fix["spin"]                            # the slow drift round the subject, faster here
        mv = bool(cinema and cinema.get("motion", True))          # Cinema: every shot keeps moving
        if mv and "spin" not in shot and "follow" not in shot:
            shot["spin"] = CINEMA_SPIN
        # (a view straight down on a surface site barely changes when it turns, so it pushes in harder)
        push = lambda L: fix.get("creep") or (max(_creep(L), 1.4 if "@" in str(shot.get("target", "")) else CINEMA_PUSH) if mv else _creep(L))   # noqa: E731
        if mv and not fix.get("creep") and "follow" not in shot:
            # Cinema: the beat's opening shot moves as its first words say (out: starts closer and pulls back; orbit: turns wider)
            from .cinema import MOVES, narrative_move

            _nm = narrative_move(plan.words, b.start, min(b.end, b.start + 8.0), b.text[:160])
            if _nm:
                _e, _kt, _ks = MOVES[_nm]
                shot["spin"] = float(shot.get("spin", CINEMA_SPIN)) * _ks
                push = (lambda L, _e=_e: _e)   # noqa: E731
        km = _approx_km(shot, cat, place)
        act = (actions or {}).get(b.id)
        if act is not None and (act.intro is not None or act.camera):
            # a visual action: glide to its first view, then its camera intents (follow the craft, settle, pull back)
            length = b.end - b.start
            intro = _repaired(_action_shot(act.intro, shot, act, b), fix)
            if mv and "spin" not in intro and "follow" not in intro:
                intro["spin"] = CINEMA_SPIN_ACTION                 # Cinema: an action's held frame turns too, gently (the craft still crosses it)
            # an action beat: drift only, no push_in (the craft is what moves)
            if start is None:
                start, glide = intro, 0.0
            elif b.id in cut_in:
                glide = 0.0
                moves.append({"t": round(b.start, 3), "dur": 0.0, "to": intro})
            else:
                ikm = _approx_km(intro, cat, place)
                glide = max(1.5, _reveal_s(prev_km, ikm, length))  # one deliberate move into the action's view, never squeezed
                if ikm < prev_km:
                    # ...but a dive in to the action arrives while it is being told: 85% of a Saturn flyby beat spent closing in
                    # from the whole solar system left the planet a speck until the narration had moved on
                    glide = min(glide, max(1.5, 0.4 * length))
                t0 = b.start
                if ikm > 3 * prev_km and b.start - prev_end < 0.5:
                    # a pull_out straight on from the beat before starts a little early, so the wider view is already opening
                    # when the craft leaves (its clock may carry it far in the first second); a cut never does
                    busy = max([m["t"] + m["dur"] for m in moves] + [0.0])
                    t0 = max(busy, b.start - min(3.0, 0.4 * glide))
                    glide += b.start - t0
                moves.append({"t": round(t0, 3), "dur": round(glide, 3), "to": intro})
            last = b.start + glide
            for frac, dfrac, s in act.camera:
                t = max(b.start + frac * length, last)
                d = max(0.5, min(dfrac * length, b.end - 0.2 - t))
                if t >= b.end - 0.4:
                    break
                moves.append({"t": round(t, 3), "dur": round(d, 3), "to": _repaired(_action_shot(s, shot, act, b), fix)})
                last = t + d
            if fix.get("creep") and not act.camera and b.end - 0.3 - last >= 2.0 and "path" in intro:
                # the screen check found the held frame still for seconds: it closes in slowly through the rest of the beat
                moves.append({"t": round(last, 3), "dur": round(b.end - 0.3 - last, 3), "to": _repaired(intro, {"fit": 1 / fix["creep"]})})
            # the composition stays stable (a slow creep, never frozen): the craft moves through the frame and the tracker
            # follows it, not the camera
            cur = moves[-1]["to"] if moves else start
            prev_key, prev_km, prev_end = ("action", b.id), _approx_km(cur, cat, place), b.end
            continue
        key = ("journey", b.id) if b.id in journey else (b.place.lower(), b.frame, b.move, tuple(sorted(b.extra.items())))
        length = b.end - b.start
        # no move asked for: the beat creeps in slowly, whatever moves in it (the camera never reacts to the craft)
        creep = b.move not in OWN_MOVES
        first = shot
        if b.move == "push_in":
            first = _scaled(shot, 1.6)
        elif b.move == "pull_out":
            first = _scaled(shot, 1 / 1.6)
        elif creep:
            first = _scaled(shot, push(length))
        same = start is not None and key == prev_key and b.move in ("", "hold", "orbit")
        sig = _view_sig(shot)
        if sig != view_sig:
            view_t0, nvar, view_sig = b.start, 0, sig
        vary = start is not None and b.move in ("", "hold") and b.start - view_t0 >= VARY_AFTER_S and length >= 4.0
        if start is None:
            if creep and not fix.get("creep") and "path" not in shot and "follow" not in shot:
                first = _scaled(shot, OPENING_PUSH)
            start, glide = first, 0.0
        elif same and not vary:
            glide = 0.0                                           # the same view: no new glide...
            if creep and cur is not None and length >= 1.3:      # ...but it keeps creeping in from where the last beat ended
                cur = _scaled(cur, 1 / push(length))
                moves.append({"t": round(b.start, 3), "dur": round(length - 0.3, 3), "to": cur})
            prev_km = km
            continue
        else:
            if vary:
                # held for a while already: this beat sees the same subject from a new angle (a glide round it), not the
                # same picture again
                shot = _variant(shot, nvar)
                nvar += 1
                view_t0 = b.start
                first = _scaled(shot, push(length)) if creep else shot
                glide = min(4.0, max(1.0, 0.5 * length))
            else:
                glide = 0.0 if b.id in cut_in else min(max(2.5, 2.5 + 0.55 * abs(math.log10(km / prev_km))), 6.0, max(1.0, 0.7 * length))
                if creep and not fix.get("creep") and b.id not in journey and "path" not in shot and length - glide >= 5.0:
                    name, k = RECIPES[recipe_n % len(RECIPES)]
                    recipe_n += 1
                    first = _scaled(shot, k)
                    if "fit" in first and "+" in str(first.get("target")):
                        first["fit"] = max(1.05, first["fit"])      # a pair revealed from close still has both ends in frame
            if creep and length - glide - 0.3 < 1.0:
                first = shot                                      # too short to creep: glide straight to the shot
            wide = _travel_via(moves[-1]["to"] if moves else start, first, glide, length) if mv and b.id not in cut_in else None
            if wide is not None:
                # Cinema: between two bodies the camera pulls out over the solar system, then closes in on the next
                # (zoom out, cross, zoom in) instead of a straight slide
                glide = min(max(glide, 4.5), 0.7 * length)
                g1 = 0.42 * glide
                moves.append({"t": round(b.start, 3), "dur": round(g1, 3), "to": wide})
                moves.append({"t": round(b.start + g1, 3), "dur": round(glide - g1, 3), "to": first})
            else:
                moves.append({"t": round(b.start, 3), "dur": round(glide, 3), "to": first})
        cur = first
        # a long beat is cut into shots, as an editor would: the view -> a close-up -> the view again from a new angle (each
        # with its own slow creep); never a beat with its own move, a craft's path, a surface site
        n_cut = fix.get("cuts") or (3 if length >= CUTS_FROM_S[1] else 2 if length >= CUTS_FROM_S[0] else 1)
        if cinema and cinema.get("cuts") and not fix.get("cuts"):
            n_cut = max(1, round(length / 8.0))            # Cinema: the references' rhythm, a shot about every 8 s (median 6-10 s)
        cuts = []
        # a beat that draws a line between two things (a sight line, a signal, a distance) is about that relationship: a
        # close-up of one end drops the other (b19: Jupiter fullscreen while the narration is about Voyager's view of Io)
        relation = any(L.type in ("line", "distance") and ";" in (L.place or "") for L in b.layers)
        if creep and n_cut > 1 and not relation and b.move in ("", "hold") and ("path" not in shot or mv) and "follow" not in shot and "@" not in str(shot.get("target", "")):
            close = _close_up(shot, cat)
            if close is None and mv and "path" in shot:
                # Cinema: a journey is cut too -- the path seen closer from higher up, then from a new angle (never one long hold)
                close = copy.deepcopy(shot)
                close["el_deg"] = min(80.0, float(shot.get("el_deg", 35)) + 22)
                close["path"]["fit"] = float(shot["path"].get("fit", 1.3)) * 0.85
            r = _craft_sun_km(cat, b, res, clock) if close and shot.get("target") == "sun" and "distance" in shot else 0.0
            if r:
                # the close-up of a Sun-centred view keeps the beat's own craft in frame: 0.38x of the view put the inner planets
                # on screen while the narration named a craft 40 AU out (six billion km, a light-day), and its line ran off the
                # edge. It closes in only as far as the craft allows; with no room to close in, the cut is a new angle instead
                d = next(iter(shot["distance"].values())) * {"au": KM_PER_AU, "ly": KM_PER_LY}.get(next(iter(shot["distance"])), 1.0)
                k = max(0.38, r / (0.8 * TAN_HALF) / d)
                close = _scaled(shot, k) if k <= 0.75 else _variant(shot, nvar + 2)
            cuts = _cut_times(b, plan.words, n_cut) if close else []
            if cinema and cinema.get("cuts"):
                # Cinema: a cut lands in a narration pause when one is near (the references cut in pauses 65-82% of the time)
                from .cinema import pause_cut

                cuts = [pause_cut(plan.words, t, b.start + CUT_MIN_S, b.end - CUT_MIN_S) or t for t in cuts]
            cuts = [t for t in cuts if t - (b.start + glide) >= 2.0]
        elif cinema and cinema.get("hero") and creep and "path" in shot and length >= 2 * CUT_MIN_S + 1:
            # Cinema: a journey beat about the craft itself cuts once, in a pause near its middle, to the craft's hero close-up
            from .cinema import about_craft, craft_alive, hero_shot, pause_cut

            tid = shot["path"].get("trajectory")
            if tid and about_craft(b.text):
                mid = b.start + length / 2
                tc = pause_cut(plan.words, mid, b.start + CUT_MIN_S, b.end - CUT_MIN_S) or round(mid, 3)
                if tc - (b.start + glide) >= 2.0 and craft_alive(cat, tid, clock, tc):
                    close, cuts = hero_shot(tid), [tc]
        if cuts:
            # inside each shot the picture must visibly move: a 12% push-in and a clear arc round the subject
            s_close, s_angle = (CINEMA_SPIN_CLOSE, CINEMA_SPIN_ANGLE) if mv else (2.5, 3.0)
            seq = [dict(close, spin=fix.get("spin") or s_close), dict(_scaled(_variant(shot, nvar + 1), 1.2), spin=fix.get("spin") or s_angle)]
            while len(seq) < len(cuts):
                # a longer beat (Cinema's rhythm): close-ups and new angles in turn, each from its own side
                i = len(seq)
                seq.append(dict(_variant(close, i), spin=fix.get("spin") or s_close) if i % 2 == 0
                           else dict(_scaled(_variant(shot, nvar + i), 1.2), spin=fix.get("spin") or s_angle))
            seq = seq[:len(cuts)]
            first["spin"] = shot["spin"] = fix.get("spin") or (CINEMA_SPIN if mv else 2.0)    # the opening shot arcs too
            if cinema and cinema.get("hero"):
                # Cinema: a beat about the craft itself (its dish, instruments, record ...) cuts to a hero close-up of its model
                from .cinema import about_craft, craft_alive, hero_shot

                tid = None
                for it in b.layers:
                    if it.type == "craft" and it.id and (it.t if it.t is not None else b.start) <= cuts[0]:
                        try:
                            tid = cat.craft(cat.craft_id(it.id, res.ctx(b.id) if res else ())).get("trajectory")
                        except CatalogError:
                            tid = None
                        if tid:
                            break
                if tid and about_craft(b.text) and craft_alive(cat, tid, clock, cuts[0]):
                    seq[0] = dict(hero_shot(tid), spin=1.5)
            rest = cuts[0] - b.start - glide - 0.05
            if rest >= 1.0 and first is not shot:
                moves.append({"t": round(b.start + glide, 3), "dur": round(rest, 3), "to": shot})
            for i, (tc, sub) in enumerate(zip(cuts, seq)):
                t_end = cuts[i + 1] if i + 1 < len(cuts) else b.end
                entry, target = _scaled(sub, CINEMA_CUT_PUSH if mv else 1.12), sub
                if mv and "follow" not in sub:
                    # Cinema: the words said while this shot is up decide its move -- pull out on "far / billions / beyond", push in on
                    # "surface / instruments / record", a wider turn on "around / orbit"; otherwise a gentle push and arc
                    from .cinema import MOVES, narrative_move

                    e, k_t, k_s = MOVES[narrative_move(plan.words, tc, t_end)]
                    spin = float(sub.get("spin", CINEMA_SPIN)) * k_s
                    entry, target = dict(_scaled(sub, e), spin=spin), dict(_scaled(sub, k_t), spin=spin)
                moves.append({"t": tc, "dur": 0.0, "to": entry})          # the cut
                moves.append({"t": round(tc + 0.02, 3), "dur": round(t_end - tc - 0.35, 3), "to": target})   # and its move
                cur = target
            prev_key, prev_km, prev_end = key, km, b.end
            continue
        if b.move in ("push_in", "pull_out") or (creep and first is not shot):
            rest = length - glide - 0.3
            if rest >= 1.0:
                moves.append({"t": round(b.start + glide, 3), "dur": round(rest, 3), "to": shot})
                cur = shot
            elif not creep:
                notes.append(f"row {b.row}: beat {b.id} is too short to {b.move.replace('_', ' ')}; the camera holds")
        prev_key, prev_km, prev_end = key, km, b.end
    if start is None:
        start = {"target": "earth", "fill": 0.5, "light": "side", "el_deg": 20}
    for sh in [start] + [m["to"] for m in moves]:
        sh.pop("_km", None)
        sh.pop("_r", None)
    # the drift never rests: a stable shot is still alive (a frozen camera reads as a stuck video)
    return {"drift_deg_per_s": DRIFT_DEG_PER_S, "start": start, "moves": moves}




# ---- clock ------------------------------------------------------------------------------------------------------------
def build_clock(cat: Catalog, plan: Plan, problems: List[str], notes: List[str], res: Resolution,
                actions: Optional[Dict[str, BeatAction]] = None) -> Dict[str, Any]:
    """Resolved beat dates -> universe clock keys. Between two dated map beats time either runs on screen (continuous: the
    spacecraft flies its path between them) or JUMPS: the earlier date runs in real time and the later one arrives in a
    single frame -- under the footage when footage comes between them, else at the next beat's start, hidden by a
    time-jump card (see the time_jump layers). Never a decade of planets spinning by on screen."""
    beats = plan.beats
    keys: List[Dict[str, Any]] = []

    def add(t: float, utc: str) -> None:
        if keys and abs(keys[-1]["t"] - t) < 1e-6:
            keys[-1]["utc"] = utc
        else:
            keys.append({"t": round(t, 3), "utc": utc})

    def shifted(utc: str, seconds: float) -> str:
        from datetime import timedelta

        return iso(parse_iso(utc) + timedelta(seconds=seconds))

    for b in beats:
        if b.mode == "footage" and b.date:
            notes.append(f"row {b.row}: a footage beat's date is ignored (the map is hidden); give it to the next map beat")
    dated = [(beats.index(b), res.contexts[b.id].utc) for b in beats if b.mode != "footage" and res.contexts.get(b.id) and res.contexts[b.id].utc]
    jumps = {t.b: t for t in res.transitions if t.kind == "jump" and not t.hidden_by_footage}
    continuous_from = {t.a for t in res.transitions if t.kind == "continuous"}
    acts = {k: v for k, v in (actions or {}).items() if v.strategy == "clock" and v.span}
    held: Dict[str, Tuple[float, str]] = {}               # beat -> (narration t, utc) its action ends on, for the hold before a jump
    pushed: Optional[str] = None                          # where a zero-length beat's action left time (never run back from it)
    began: Dict[str, str] = {}                            # beat -> the date it starts at, where that is not its own date
    for k, (i, utc) in enumerate(dated):
        b = beats[i]
        act = acts.get(b.id)
        tr = jumps.get(b.id)
        if tr is not None and keys:
            a = beats[dated[k - 1][0]]
            t0, u0 = held.get(a.id, (a.start, began.get(a.id, dated[k - 1][1])))
            add(b.start - JUMP_CUT_S, shifted(u0, b.start - JUMP_CUT_S - t0))   # the old date holds to the cut
        # the beat's date is its first moment; an action the CSV asked for by name starts where the action starts
        incoming = any(t.b == b.id and t.kind == "continuous" for t in res.transitions)
        start_utc = act.span[0] if act and act.source == "csv" and not incoming else utc   # time already running in keeps running
        if pushed is not None and incoming and iso_seconds(start_utc, pushed) > 0:
            start_utc = began[b.id] = pushed                 # the beat before ran its action on past this beat's own date
        pushed = None
        add(b.start, start_utc)
        nxt = dated[k + 1][0] if k + 1 < len(dated) else len(beats)
        cut = next((j for j in range(i + 1, nxt) if beats[j].mode == "footage"), None)
        # time "runs on" into a next beat at the very same date: nothing would move for the whole beat (the clock stood still
        # at Saturn's closest approach). Then the action's own span end ends the beat, as when time does not run on
        still = act is not None and b.id in continuous_from and cut is None and k + 1 < len(dated) \
            and iso_seconds(start_utc, dated[k + 1][1]) <= 0 and iso_seconds(start_utc, act.span[1]) > 0
        if act and (b.id not in continuous_from or still):
            # the action's own end (an ascent, a descent, a closest approach) when time does not run on into the next beat
            add(b.end - 0.05, act.span[1])
            held[b.id] = (b.end - 0.05, act.span[1])
            if still:
                pushed = act.span[1]
        if cut is not None and k + 1 < len(dated):
            add(beats[cut].start, shifted(began.get(b.id, utc), beats[cut].start - b.start))   # hold (real time) until the footage
        if b.extra.get("date_end"):
            try:
                add(b.end, cat.date(str(b.extra["date_end"]), res.ctx(b.id), res.reference_now))
            except CatalogError as exc:
                problems.append(f"row {b.row}: date_end: {exc}")
    keys.sort(key=lambda x: x["t"])
    for a, b2 in zip(keys, keys[1:]):
        if iso_seconds(a["utc"], b2["utc"]) < 0 and b2["t"] - a["t"] > JUMP_CUT_S + 1e-6 and \
                not any(abs(beats[[x.id for x in beats].index(t.b)].start - b2["t"]) < 1e-6 for t in res.transitions if t.kind == "jump"):
            notes.append(f"the universe clock runs backwards between {a['t']:.1f}s and {b2['t']:.1f}s ({a['utc']} -> {b2['utc']}): a flashback?")
    if keys:
        return {"keys": keys}
    if cat.default and cat.events:
        return {"utc": cat.date(next(iter(cat.events)))}
    return {"utc": res.reference_now or DEFAULT_DATE}


# ---- layers -----------------------------------------------------------------------------------------------------------
_PLACEHOLDER = re.compile(r"[#0][#0,]*(?:\.(0+))?")


def stat_parts(fmt: str) -> Tuple[int, str, str]:
    """A stat format ("#,##0.0 MILLION KM") -> (decimals, text before, text after)."""
    m = _PLACEHOLDER.search(fmt or "")
    if not m:
        return 0, "", (fmt or "").strip()
    return len(m.group(1) or ""), fmt[:m.start()].strip(), fmt[m.end():].strip()


def _join_same_file(footage: List[Dict[str, Any]], notes: List[str]) -> List[Dict[str, Any]]:
    """Two footage shots back to back that show the same file (same path or same bytes) are one shot. Each shot starts its
    clip at in_s (0) and its picture's slow push from the start, so the second one replayed the clip from frame 0 and
    restarted the push, faster, on the shorter shot. Joined, the clip plays on and the push runs once. A shot with its
    own in_s (the writer chose where it starts) is left alone."""
    import hashlib

    digest: Dict[str, str] = {}

    def same(name: str) -> str:
        if name not in digest:
            try:
                h = hashlib.md5()
                with open(name, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                digest[name] = h.hexdigest()
            except OSError:
                digest[name] = name
        return digest[name]

    joined: List[Dict[str, Any]] = []
    merged = 0
    for d in footage:
        p = joined[-1] if joined else None
        kind = "image" if "image" in d else "file"
        if (p is not None and kind in p and p[kind] and d.get(kind) and "in_s" not in d and abs(p["end"] - d["start"]) < 0.05
                and same(p[kind]) == same(d[kind])):
            p["end"] = d["end"]
            merged += 1
            continue
        joined.append(d)
    if merged:
        notes.append(f"{merged} cut(s) between two footage shots of the same picture or clip removed: it plays on instead of restarting")
    return joined


def compile_plan(plan: Plan, cat: Catalog, *, media: Optional[Dict[str, Any]] = None, resolve_media: bool = True,
                 width: int = W, height: int = H, fps: int = 30, watermark: Optional[Dict[str, Any]] = None,
                 reference_now: Optional[str] = None, resolution: Optional[Resolution] = None,
                 repairs: Optional[Dict[str, Dict[str, Any]]] = None, cinema: Any = None) -> Compiled:
    """Plan -> spec. media maps "row:<csv row>" or an asset string to a file (or {"file", "credit"}); "file:<name>" assets name a file in the
    spec's media folder directly. resolve_media=False (Check plan) lists what is still to be found instead of failing."""
    media = media or {}
    problems: List[str] = []
    notes = list(plan.notes)
    needs: List[Tuple[int, str]] = []
    beats = plan.beats
    end_of_video = plan.duration

    def find_media(row: int, asset: str) -> Optional[Dict[str, Any]]:
        a = asset.strip()
        hit = media.get(f"row:{row}")                           # per row: the Visual Plan's file, or a file: name the app resolved
        if not hit and a.lower().startswith("file:"):
            return {"file": a[5:].strip()}                       # a bare file: name (the command line serves it from its media folder)
        hit = hit or media.get(a)                               # else by description
        if hit:
            return hit if isinstance(hit, dict) else {"file": str(hit)}
        needs.append((row, a))
        if resolve_media:
            problems.append(f"row {row}: no picture or clip yet for {a!r} (find it in the Visual Plan, or write file:<name>)")
        return None

    def until_end(it: Item, b: Beat) -> float:
        u = it.until
        if not u:
            end = b.end
        elif u == "end":
            end = end_of_video
        elif u == "after_footage":
            i = beats.index(b)
            nxt = next((k for k in range(i + 1, len(beats)) if beats[k].mode == "footage"), None)
            back = next((k for k in range(nxt + 1, len(beats)) if beats[k].mode != "footage"), None) if nxt is not None else None
            end = beats[back].end if back is not None else end_of_video
        else:
            tgt = next((x for x in beats if x.id.lower() == u), None)
            if tgt is None:
                problems.append(f"row {it.row}: until must be empty, after_footage, end, or a beat id (got {it.until!r})")
                end = b.end
            else:
                end = tgt.end
        # hold only ever makes a layer leave sooner; the usual lengths apply when the row gives no until
        key = "card" if it.kind == "card" else it.type
        hold = it.hold if it.hold is not None else (DEFAULT_HOLD.get(key) if not it.until else None)
        if hold is not None:
            end = min(end, it.t + hold)
        return round(max(end, it.t + 0.5), 3)

    # which datasets and which moment every beat is about (deterministic: the CSV, the local library, the reference date)
    res = resolution if resolution is not None else resolve(plan, cat, reference_now=reference_now)
    problems += res.errors
    notes += res.notes
    cat.used = set(res.used)
    # the beats' own places first, so one report lists every problem
    for b in beats:
        if b.mode != "footage":
            try:
                p = shot_for(cat, b, res.ctx(b.id))[1]
                if p.dataset:
                    cat.used.add(p.dataset)
            except CatalogError as exc:
                problems.append(f"row {b.row}: {exc}")
    actions, act_errors, act_warnings = resolve_actions(plan, cat, res)
    problems += act_errors
    # what the narration says is moving gets a marker from the moment it is named (after the actions: an added craft row
    # never turns a plain beat into a visual action)
    from .tracking import accelerate, add_auto_rows

    notes += add_auto_rows(plan, cat, res)
    # two clocks: the stage-free one decides every frame (staging changes pacing, never composition); the staged one is
    # what the video shows -- the true date of where each craft is, with each action's phases given their narration time
    free = build_clock(cat, plan, problems, notes, res, actions)
    notes += accelerate(free, plan, cat, actions)                 # an orbit the narration is about visibly turns
    _frame_what_the_clock_shows(plan, free, actions, act_warnings)
    clock = _with_stages(free, plan, actions)
    journey_views = journeys(cat, plan, res, free, actions)
    ctx_of = {b.id: res.ctx(b.id) for b in beats}
    tctx = {b.id: res.contexts.get(b.id) for b in beats}

    def entity_status(qid: str, tid: Optional[str], bc: Optional[BeatContext]) -> Optional[str]:
        """How certain one drawn thing is: its dataset's and its trajectory's own status (only the uncertain ones count), made
        less certain if the CSV lowered the whole beat."""
        did = qid.split(".", 1)[0]
        ds = cat.index.datasets[did]
        st = [ds.status] if CERTAINTY[ds.status] > 0 else []
        t = cat.index.trajectories.get(tid) if tid else None
        if t is not None and CERTAINTY[t.status] > 0:
            st.append(t.status)
        if bc is not None and bc.lowered_by_csv:
            st.append(bc.status)
        return least_certain(st)

    def styled(style: Optional[Dict[str, Any]], status: Optional[str]) -> Dict[str, Any]:
        st = dict(style or {})
        if status in STATUS_STYLE:
            col = STATUS_STYLE[status]
            st.update(color=col, future_color=col, dash=[18, 12], future="dashed", glow=0)
        return st

    layers: List[Dict[str, Any]] = []
    trackers: List[Dict[str, Any]] = []
    used_trajectories: set = set()
    craft_windows: Dict[str, List[Tuple[float, float, str]]] = {}
    title_layers: List[Dict[str, Any]] = []
    distances: List[Tuple[Item, Dict[str, Any]]] = []
    for b in beats:
        card_slots = iter([a for a in CARD_ORDER])
        taken_anchor: List[str] = []
        for it in b.layers:
            try:
                start, end = round(it.t, 3), until_end(it, b)
                timing = {"start": start, "end": end}
                ty = it.type
                if ty == "title":
                    if not it.label:
                        raise CatalogError("a title needs a label")
                    for prev in title_layers:                       # one title at a time: the old one leaves
                        if prev["end"] > start:
                            prev["end"] = start
                    L = {"type": "title", "text": it.label.upper(), **({"subtitle": it.sub.upper()} if it.sub else {}), **timing}
                    title_layers.append(L)
                elif ty == "marker":
                    p = cat.place(it.place or b.place, ctx_of[b.id])
                    if p.kind != "site":
                        raise CatalogError(f"a marker needs a surface site (a named site or body@lon,lat), not {p.kind} {it.place!r}")
                    L = {"type": "marker", "body": p.body, "lon": p.lon, "lat": p.lat, "label": (it.label or p.label).upper(), **timing}
                    if it.sub:
                        L["description"] = it.sub.upper()
                elif ty == "zone":
                    p = cat.place(it.place or b.place, ctx_of[b.id])
                    if p.kind != "site":
                        raise CatalogError("a zone needs a surface site to draw around")
                    L = {"type": "region", "body": p.body, "geometry": {"circle": {"lon": p.lon, "lat": p.lat, "radius_km": it.value_to or 25}},
                         "reveal": {"t0": start, "t1": start + 1.5}, "z": -1, **timing}
                    if it.label:
                        L["label"] = it.label.upper()
                elif ty == "path":
                    qid, path = cat.lookup("path", it.id, ctx_of[b.id])
                    did = qid.split(".", 1)[0]
                    used_trajectories.add(path["of"])
                    status = entity_status(qid, path["of"], tctx[b.id])
                    L = {"type": "trajectory", "of": path["of"], "draw_utc": [cat.date(path["from"], [did]), cat.date(path["to"], [did])], **timing,
                         "_status": status, "_basis": cat.index.trajectories[path["of"]].basis}
                    if path.get("style") or status in STATUS_STYLE:
                        L["style"] = styled(path.get("style"), status)
                    act = actions.get(b.id)
                    if act is not None and act.trajectory == path["of"] and act.motion(b.start, b.end):
                        L["motion"] = act.motion(b.start, b.end)            # the trail keeps up with the narration-paced craft
                elif ty == "craft":
                    cid = cat.craft_id(it.id, ctx_of[b.id])
                    base = copy.deepcopy(cat.craft(cid))
                    used_trajectories.add(base.get("trajectory"))
                    n = len(craft_windows.setdefault(cid, []))
                    lid = cid if n == 0 else f"{cid}~{n + 1}"
                    craft_windows[cid].append((start, end, lid))
                    status = entity_status(cid, base.get("trajectory"), tctx[b.id])
                    L = {**base, "type": "spacecraft", "id": lid, **timing, "_status": status,
                         "_basis": cat.index.trajectories[base["trajectory"]].basis if base.get("trajectory") else None}
                    if it.label:
                        L["label"] = it.label.upper()
                    bc = tctx[b.id]
                    estimated = bc is not None and bc.estimated_from and cat.index.trajectories.get(base.get("trajectory") or "") is not None \
                        and cat.index.trajectories[base["trajectory"]].observed_until
                    if L.get("label") and (status in BADGE or estimated):
                        L["label"] = f"{L['label']} · {BADGE[status] if status in BADGE else 'ESTIMATED'}"
                        L["label_bg"] = STATUS_STYLE.get(status, ESTIMATED_COLOR)
                    act = actions.get(b.id)
                    mine = act is not None and act.craft == cid
                    if mine:
                        if act.show_on_pad:
                            L["show"] = "always"                            # on its pad before the liftoff
                        if act.burns:
                            L["burns"] = [{"from_utc": x, "to_utc": y} for x, y in act.burns]
                        if act.motion(b.start, b.end):
                            L["motion"] = act.motion(b.start, b.end)
                    traj = cat.index.trajectories.get(base.get("trajectory") or "")
                    if traj is not None and L.get("label"):
                        # TRACKING: the craft's name rides in a tracking box that follows it (the camera does not have to).
                        # Live readouts only while it performs an action -- otherwise the box is just its name, no HUD for show
                        drawn = traj.basis in ("illustrated", "illustrative")
                        T = {"type": "tracker", "craft": lid, "trajectory": traj.id, "label": L["label"], "readouts": [],
                             "start": L["start"], "end": L["end"], "_row": it.row}
                        if mine:
                            want = act.readouts or ["altitude", "speed"] + (["distance"] if act.dest else [])
                            # speed only from real or modelled data: an illustrated path's timing is drawn, not flown
                            T["readouts"] = [r for r in want if not (r == "speed" and drawn)]
                            T.update(altitude_of=act.body or traj.data.get("frame"), approx=drawn)
                            if act.dest:
                                T["to"] = act.dest
                            if "from" in T["readouts"]:
                                T["from"] = act.body
                            if L.get("motion"):
                                T["motion"] = L["motion"]
                        if L.get("label_bg"):
                            T["color"] = L["label_bg"]
                        if it.extra.get("auto"):
                            T["trail"] = True                       # named as moving: its actual trajectory as a fading trail
                        trackers.append(T)
                        L["label"] = ""                                 # the tracking box carries the name
                elif ty == "orbit":
                    qid, o = cat.lookup("orbit", it.id, ctx_of[b.id])
                    did = qid.split(".", 1)[0]
                    used_trajectories.add(o["trajectory"])
                    status = entity_status(qid, o["trajectory"], tctx[b.id])
                    L = {"type": "orbit", **{k: v for k, v in o.items() if k != "at"}, "at_utc": cat.date(o["at"], [did]), **timing,
                         "_status": status, "_basis": cat.index.trajectories[o["trajectory"]].basis}
                    if status in STATUS_STYLE:
                        L["style"] = {**(o.get("style") or {}), "color": STATUS_STYLE[status], "dash": [14, 10]}
                elif ty == "stat":
                    if it.value_to is None:
                        raise CatalogError("a stat needs value_to (the number the narrator says)")
                    dec, before, after = stat_parts(it.format)
                    if before:
                        notes.append(f"row {it.row}: the stat shows {it.value_to} {after}; text before the number ({before!r}) is left out")
                    corner = it.anchor if it.anchor in ("bl", "br", "tl", "tr") else "bl"
                    L = {"type": "stat_chip", "value": it.value_to, "decimals": dec, "label": it.sub.upper(), "corner": corner,
                         "count_up": {"t0": start, "t1": start + 1.6, "from": it.value_from or 0}, **timing}
                    if after:
                        L["unit"] = after.upper()
                elif ty == "caption":
                    if not it.text:
                        raise CatalogError("a caption needs text")
                    L = {"type": "caption", "text": it.text.upper(), **({"sub": it.sub.upper()} if it.sub else {}), **timing}
                elif ty == "distance":
                    L = {"type": "distance", "label": (it.sub or it.label or "DISTANCE").upper(), **timing}
                    distances.append((it, L))
                elif ty == "line":
                    style = (it.id or "light").lower()
                    if style not in ("light", "measure"):
                        raise CatalogError(f"a line's id is its style: light (light travelling) or measure (a measuring line), not {it.id!r}")
                    # dur: how long the line takes to draw from its first thing to its second -- something that TRAVELS between
                    # them (a solar storm reaching a craft over the beat), not a line that is simply there
                    L = {"type": "link", "style": style, "reveal": {"t0": start, "t1": start + max(1.0, float(it.dur or 1.0))}, **timing}
                    if it.label or it.text:
                        L["label"] = (it.label or it.text).upper()
                    distances.append((it, L))
                elif ty == "rings":
                    p = cat.place(it.place or b.place, ctx_of[b.id])
                    parts = [x.strip() for x in (it.text or "").split(";") if x.strip()]
                    if not parts:
                        raise CatalogError("rings need text: the rings' sizes separated by ; (e.g. 1 light-hour; 1 light-day; 1 light-year)")
                    rings = []
                    for x in parts:
                        size, _, label = x.partition("=")
                        rings.append({"radius": ring_radius(size), "label": (label or size).strip().upper()})
                    L = {"type": "rings", "around": p.body, "rings": rings, **timing}
                elif ty in ("plate", "instrument"):
                    # Cinema's What If graphics, written by the CSV: id = the graphic (bars, curve, survival, clock, hero ...), extra = its
                    # settings as JSON. A plate is full-frame on a slate; an instrument sits over the shot. Only with Cinema on (see below)
                    from .cinema import CSV_KINDS

                    kind = (it.id or "").strip().lower()
                    if kind not in CSV_KINDS[ty]:
                        raise CatalogError(f"{ty} id must be one of {', '.join(sorted(CSV_KINDS[ty]))} (got {it.id!r})")
                    L = {"type": "cinema_hero" if kind == "hero" else f"tm_{kind}", **it.extra, **timing, "_cinema_row": ty}
                    if kind == "mission" and not it.until:
                        L["end"] = end_of_video                 # the mission card is pinned for the whole trip (What If V4)
                    if it.label and "title" not in it.extra and kind not in ("caption", "metric", "fade", "hero", "annotate", "clock"):
                        L["title"] = it.label.upper()
                    if kind in ("caption", "annotate", "metric") and it.label and not any(k in it.extra for k in ("text", "label", "value")):
                        L["label" if kind == "annotate" else ("value" if kind == "metric" else "text")] = it.label.upper()
                    if it.sub and "sub" not in it.extra:
                        L["sub"] = it.sub.upper()
                elif ty == "template":
                    # Cinema: any What If template by id (fact_bullets, mission_intro, before_after ...), its slots from the row's columns as
                    # in a What If CSV, timed on the narration. A plate template is full-frame on a slate; any other sits over the shot
                    from whatif import templates as wi_tpl

                    try:
                        t_end = until_end(it, b) if it.until else None
                        L, wi_plate = wi_tpl.layer_for(it, start, t_end, plan.words)
                    except ValueError as exc:
                        raise CatalogError(str(exc)) from None
                    if L.get("image_slot"):
                        m = find_media(it.row, it.asset) if it.asset else None
                        if m and m.get("file"):
                            L["slots"][L["image_slot"]] = m["file"]
                        else:
                            L["slots"].pop(L["image_slot"], None)
                    L["_cinema_row"] = "plate" if wi_plate else "instrument"
                    if wi_plate:
                        kind, text = wi_plate.get("cite") or ("DIAGRAM", "")
                        L["_tpl_cite"] = f"{kind} · {text}".rstrip(" ·")
                elif ty == "track":
                    # a marker on a moving planet or moon (its recent orbital path as a dotted trail); a craft named here is
                    # tracked like a craft row
                    try:
                        cid = cat.craft_id(it.place, ctx_of[b.id])
                    except CatalogError:
                        cid = None
                    if cid:
                        raise CatalogError(f"track {it.place!r} is a spacecraft: give it a craft row (id={cid})")
                    p = cat.place(it.place, ctx_of[b.id])
                    if p.kind not in ("body",):
                        raise CatalogError(f"track needs a planet or moon, not {p.kind} {it.place!r}")
                    L = {"type": "tracker", "body": p.body, "label": (it.label or p.body).upper(), "trail": True, **timing}
                elif ty == "pointer":
                    p = cat.place(it.place or b.place, ctx_of[b.id])
                    L = {"type": "pointer", "at": p.ref, "label": (it.label or "YOU ARE HERE").upper(), **timing}
                    if it.sub:
                        L["sub"] = it.sub.upper()
                else:
                    raise CatalogError(f"unknown layer type {ty!r}")
                L["_row"] = it.row
                layers.append(L)
            except CatalogError as exc:
                problems.append(f"row {it.row}: {exc}")
        for it in b.cards:
            anchor = it.anchor or next((a for a in card_slots if a not in taken_anchor), "tr")
            taken_anchor.append(anchor)
            m = find_media(it.row, it.asset)
            x, y = CARD_XY[anchor]
            f = (m or {}).get("file", "")
            # a card shows a picture, or plays a video clip (the renderer cuts its frames; the card holds the last one)
            L = {"type": "photo_card", ("video" if Path(f).suffix.lower() in CARD_VIDEO_EXT else "image"): f, "x": x, "y": y,
                 "start": round(it.t, 3), "end": until_end(it, b), "_row": it.row}
            if it.label:
                L["title"] = it.label.upper()
            if it.sub:
                L["caption"] = it.sub.upper()
            if m and m.get("credit"):
                L["credit"] = m["credit"]
            layers.append(L)
    _big_numbers(layers, beats, plan.duration)
    # a journey view draws the road travelled (launch to the craft) until a path row of that craft takes over: the line
    # that ties the planets at one end to the craft at the other
    for b in beats:
        sh = journey_views.get(b.id)
        if sh is None or b.mode == "footage":
            continue
        tid = sh["path"]["trajectory"]
        end = min([L["start"] for L in layers if L.get("type") == "trajectory" and L.get("of") == tid
                   and L["start"] < b.end and L["end"] > b.start] + [b.end])
        if end - b.start < 1.0:
            continue
        used_trajectories.add(tid)
        layers.append({"type": "trajectory", "of": tid, "draw_utc": [sh["path"]["from_utc"], sh["path"]["to_utc"]],
                       "start": round(b.start, 3), "end": round(end, 3), "style": {"future": "hidden"}, "_row": b.row, "_basis": cat.index.trajectories[tid].basis})
    layers += _named_boundaries(cat, plan, layers, notes)
    # a distance or a line names bodies, sites or craft ("earth;csm"): a craft is whichever of its appearances is on screen then
    lines: List[Dict[str, Any]] = []
    for it, L in distances:
        refs = []
        bid = next((b.id for b in beats if it in b.layers), "")
        for name in [x.strip() for x in it.place.split(";") if x.strip()]:
            try:
                p = cat.place(name, ctx_of.get(bid, ()))
                refs.append(p.ref)
            except CatalogError:
                try:
                    cid = cat.craft_id(name, ctx_of.get(bid, ()))
                except CatalogError as exc:
                    problems.append(f"row {it.row}: distance: {name!r} is neither a place nor a craft ({exc})")
                    continue
                win = [w for w in craft_windows.get(cid, []) if w[0] <= it.t + 1e-6 < w[1]]
                later = sorted(w for w in craft_windows.get(cid, []) if it.t < w[0] < L["end"] - 1.0)
                if not win and later:
                    # the distance is said a moment before the craft row's words ("about six billion km from the Sun,
                    # Voyager 1 pointed..."): the line waits for the craft instead of being left out of the video
                    win = later[:1]
                    L["start"] = round(win[0][0], 3)
                    if L.get("reveal"):
                        span = L["reveal"]["t1"] - L["reveal"]["t0"]
                        L["reveal"] = {"t0": L["start"], "t1": round(min(L["end"], L["start"] + span), 3)}
                    notes.append(f"row {it.row}: the distance to {name!r} starts at {L['start']:.1f}s, when that craft comes on screen")
                if not win:
                    problems.append(f"row {it.row}: distance to {name!r}, but that craft is not on screen at {it.t:.1f}s (add a craft row first)")
                    continue
                refs.append(win[0][2])
        if L["type"] == "link":
            if len(refs) == 2:
                L["between"] = refs
            elif len(refs) == 1 and "@" not in refs[0] and "+" not in refs[0]:
                L["across"] = refs[0]                           # one body: a line across it (a galaxy's width)
            else:
                problems.append(f"row {it.row}: a line needs two things separated by ; (moon;earth), or one body to measure across")
        elif len(refs) == 2:
            L["between"] = refs
            if it.extra.get("line", True):                      # the distance drawn as a measuring line between the two
                lines.append({"type": "link", "style": "measure", "between": refs, "start": L["start"], "end": L["end"],
                              "reveal": {"t0": L["start"], "t1": L["start"] + 1.0}, "_row": it.row})
        elif not it.place:
            pass                                                # the camera's distance
        else:
            problems.append(f"row {it.row}: distance needs two things separated by ; (e.g. earth;csm)")
    # a distance's own measuring line steps aside where a line row already joins the same two things at that time
    drawn = [L for _, L in distances if L["type"] == "link" and L.get("between")]
    layers += [x for x in lines if not any(set(x["between"]) == set(L["between"]) and x["start"] < L["end"] and L["start"] < x["end"] for L in drawn)]
    if problems:
        raise CompileError(problems)

    # footage: each beat's clips, one after another
    footage: List[Dict[str, Any]] = []
    for b in beats:
        if b.mode != "footage":
            continue
        span = b.end - b.start
        fixed = sum(c.dur for c in b.clips if c.dur)
        untimed = [c for c in b.clips if not c.dur]
        share = (span - fixed) / len(untimed) if untimed else 0
        t = b.start
        for k, c in enumerate(b.clips):
            d = c.dur if c.dur else share
            m = find_media(c.row, c.asset)
            f = (m or {}).get("file", "")
            entry: Dict[str, Any] = {"id": f"{b.id}_{k + 1}", "start": round(t, 3), "end": round(t + d, 3)}
            entry["image" if re.search(r"\.(jpe?g|png|webp)$", f, re.I) or c.asset.lower().startswith(("stock_image:", "nasa_image:")) else "file"] = f
            if m and m.get("credit"):
                entry["credit"] = m["credit"]
            for k2 in ("in_s", "speed", "loop", "fit", "ken_burns"):
                if k2 in c.extra:
                    entry[k2] = c.extra[k2]
            footage.append(entry)
            t += d
        if abs(t - b.end) > 0.05:
            notes.append(f"row {b.row}: beat {b.id}'s clips run {t - b.start:.1f}s of its {span:.1f}s")
    footage = _join_same_file(footage, notes)
    if problems:
        raise CompileError(problems)

    # automatic layers
    used_bodies = {b["id"] for b in cat.world}
    auto: List[Dict[str, Any]] = []
    for body, atm in cat.bodies.get("atmosphere", {}).items():
        if body in used_bodies:
            auto.append({"type": "atmosphere", "body": body, **atm})
    last_utc = max((parse_iso(c.utc) for c in res.contexts.values() if c and c.utc), default=None)
    trajectories = [_with_extrapolation(dict(cat.trajectories[t], draw=False), cat, last_utc) for t in sorted(x for x in used_trajectories if x)]
    tail = [{"type": "body_labels"}]
    if any(x.get("kind") == "galaxy" and x.get("features") for x in cat.world):
        tail.insert(0, {"type": "galaxy_guide"})               # a galaxy seen from outside: you are here, its centre, its arms
    if clock.get("keys"):
        tail += _mission_clocks(plan, res, actions)
    _hand_over(layers, trackers, craft_windows, plan)
    tail += trackers + _badges(plan, res) + _footnotes(layers) + _time_jumps(plan, res)
    for d in sorted(cat.used):
        if d not in res.used:
            res.used.append(d)
    res.used.sort()
    from .cinema import flags as _cinema_flags

    cinema_fl = _cinema_flags(cinema)
    spec: Dict[str, Any] = {
        "width": width, "height": height, "fps": fps, "duration": round(plan.duration, 3),
        "clock": clock, "world": copy.deepcopy(cat.world), "camera": build_camera(cat, plan, notes, res, actions, free, repairs, cinema_fl),
        "layers": auto + trajectories + layers + tail, "footage": footage,
        "starmap": {"pack": cat.default or "", "datasets": list(res.used), "title": plan.title, "reference_now": res.reference_now,
                    "beats": {bid: {"status": c.status, "basis": c.basis, "utc": c.utc, "timeline": c.timeline, "badge": c.badge,
                                    "datasets": c.datasets} for bid, c in res.contexts.items()},
                    "beat_times": [{"id": b.id, "start": round(b.start, 3), "end": round(b.end, 3), "mode": b.mode, "row": b.row}
                                   for b in beats]},
    }
    if watermark and watermark.get("text"):
        spec["watermark"] = watermark
    if cinema_fl:
        # the Cinema option (the StarMap tab's Cinema switch): What If's plates, type moments, citations, models (cinema.py)
        from . import cinema as _cinema

        _cinema.apply(spec, plan, cat, res, free, cinema_fl, notes)
        for m in spec["camera"]["moves"]:
            m["to"].pop("_travel", None)
    else:
        # Classic StarMap: Cinema's own rows are left out (they need the Cinema option), the rest renders as always
        kept = [L for L in spec["layers"] if not L.get("_cinema_row")]
        for L in spec["layers"]:
            if L.get("_cinema_row"):
                notes.append(f"row {L.get('_row')}: a {L['_cinema_row']} row ({L['type']}) is shown only with Cinema on (StarMap tab, Cinema)")
        spec["layers"] = kept
    spec["starmap"]["actions"] = {bid: {"action": a.action, "craft": a.craft, "strategy": a.strategy, "span": list(a.span) if a.span else None}
                                  for bid, a in actions.items()}
    return Compiled(spec=spec, notes=notes, needs_media=needs, resolution=res, actions=actions, warnings=act_warnings)


BIG_NUMBER_S, BIG_NUMBER_GAP_S, BIG_NUMBER_MAX = 3.2, 60.0, 6
_BIG_WORDS = re.compile(r"BILLION|MILLION|YEAR|LIGHT|KM/H|KM/S|AU\b|DAYS?\b|HOURS?\b", re.I)


def _big_numbers(layers: List[Dict[str, Any]], beats: List[Beat], duration: float) -> None:
    """The few numbers a video turns on get a full-screen moment: the map dims and the figure counts up huge in the middle
    for BIG_NUMBER_S, then it hands over to its usual corner chip. The biggest (by size and by unit: billions, years,
    light-time, speeds) first, at most one a minute and BIG_NUMBER_MAX a video, never in the opening seconds or over
    footage."""
    map_beat = lambda t: next((b for b in beats if b.start <= t < b.end and b.mode != "footage"), None)   # noqa: E731
    cands = []
    for L in layers:
        if L.get("type") != "stat_chip" or not isinstance(L.get("value"), (int, float)) or L["start"] < 4.0 or not map_beat(L["start"]):
            continue
        text = f"{L.get('unit', '')} {L.get('label', '')}".upper()
        scale = 9 if "BILLION" in text else 6 if "MILLION" in text else 3 if "THOUSAND" in text else 0   # "25 BILLION KM" is 25e9
        score = math.log10(max(1.0, abs(float(L["value"])))) + scale + (2.0 if _BIG_WORDS.search(text) else 0.0)
        if score >= 3.0:
            cands.append((score, L))
    chosen: List[Dict[str, Any]] = []
    for score, L in sorted(cands, key=lambda x: -x[0]):
        if len(chosen) >= min(BIG_NUMBER_MAX, max(1, int(duration // 90))):
            break
        if all(abs(L["start"] - c["start"]) >= BIG_NUMBER_GAP_S for c in chosen):
            chosen.append(L)
    for L in chosen:
        t0 = L["start"]
        layers.append({"type": "big_number", "value": L["value"], "unit": L.get("unit", ""), "label": L.get("label", ""),
                       "decimals": L.get("decimals", 0), "start": round(t0, 3), "end": round(t0 + BIG_NUMBER_S, 3),
                       "fade_in": 0.35, "fade_out": 0.5, "_row": L.get("_row")})
        # the chip takes over in its corner once the moment has passed (no second count-up)
        L["start"] = round(min(L["end"] - 0.5, t0 + BIG_NUMBER_S - 0.3), 3)
        L.pop("count_up", None)


def _clock_utc(clock: Dict[str, Any], t: float) -> Optional[str]:
    """The universe date at narration t, from the clock keys (exact at a key; between keys, where only the ends matter here,
    a straight line, or real time when the clock runs at real time or slower)."""
    keys = clock.get("keys") or []
    if not keys:
        return clock.get("utc")
    if t <= keys[0]["t"]:
        return iso(parse_iso(keys[0]["utc"]) - timedelta(seconds=keys[0]["t"] - t))
    for a, b in zip(keys, keys[1:]):
        if t <= b["t"]:
            ua, ub = parse_iso(a["utc"]), parse_iso(b["utc"])
            span = b["t"] - a["t"]
            if span <= 0:
                return b["utc"]
            if (ub - ua).total_seconds() <= span * 1.01:
                return iso(min(ua + timedelta(seconds=t - a["t"]), ub))
            return iso(ua + (ub - ua) * ((t - a["t"]) / span))
    return iso(parse_iso(keys[-1]["utc"]) + timedelta(seconds=t - keys[-1]["t"]))


def _with_stages(clock: Dict[str, Any], plan: Plan, actions: Dict[str, BeatAction]) -> Dict[str, Any]:
    """The rendered clock: the stage-free clock plus a key at each stage boundary of an action, inside the clock segment the
    action owns -- from its beat's own start key to the next key (the next dated beat, or the hold before footage or a time
    jump, which end continuous time). Undated beats in between are crossed; nothing before the action's own start key is
    touched (that time belongs to the beat before); what is left of the segment after the last stage runs on as a
    transit. Stage-free actions, and segments that hold at real time, are left exactly as they were."""
    from .actions import TRANSIT

    keys = [dict(k) for k in (clock.get("keys") or [])]
    added: List[Dict[str, Any]] = []
    for b in plan.beats:
        a = actions.get(b.id)
        if a is None or a.strategy != "clock" or not a.stages or not a.span:
            continue
        i = next((j for j, k in enumerate(keys) if abs(k["t"] - b.start) < 1e-6), None)
        if i is None or i + 1 >= len(keys):
            continue
        (t0, u0), (t1, u1) = (keys[i]["t"], keys[i]["utc"]), (keys[i + 1]["t"], keys[i + 1]["utc"])
        if not a.stages_cross_beats and abs(t1 - round(b.end - 0.05, 3)) > 1e-6:
            continue                                          # (a departure: only when it ends its own beat, as approved)
        if t1 - t0 < 1.0 or iso_seconds(u0, u1) <= (t1 - t0) * 1.01:
            continue                                          # a hold or a real-time stretch: nothing to pace
        parts, lo = [], a.span[0]
        for stg in a.stages:                                  # each stage clipped to the segment
            x, y = (u0 if iso_seconds(lo, u0) > 0 else lo), (u1 if iso_seconds(u1, stg.until) > 0 else stg.until)
            if iso_seconds(x, y) > 0:
                parts.append((y, stg.weight))
            lo = stg.until
        if iso_seconds(parts[-1][0] if parts else u0, u1) > 0:
            parts.append((u1, TRANSIT))                       # the rest of the segment runs on: the onward transit
        if len(parts) < 2:
            continue
        total, done, t, prev, new = sum(w for _, w in parts), 0.0, t0, u0, []
        for until, w in parts:
            done += w
            nt = t0 + round(done / total, 12) * (t1 - t0)       # (rounded: 7/13 of 20/13 is exactly the 35% it was)
            if nt - t < 0.5 or iso_seconds(prev, until) <= (nt - t) * 1.01:
                new = []                                      # a phase too short to show, or slower than real time: leave it
                break
            t = nt
            new.append({"t": round(t, 3), "utc": until})
            prev = until
        added += new[:-1]                                     # the last one is the segment's own end key
    if not added:
        return clock
    return {**clock, "keys": sorted(keys + added, key=lambda k: k["t"])}


def _frame_what_the_clock_shows(plan: Plan, clock: Dict[str, Any], actions: Dict[str, BeatAction], warnings: List[str]) -> None:
    """An action's held frame shows the stretch of path the clock actually runs through in its beat. The action proposes
    its stretch (the ascent, the descent, the pass); when the beat's clock runs somewhere else (it holds at real time before
    a footage cut, it starts late) the frame moves to what is on screen, keeping at least the action's own length so it is
    never a close-up of a craft standing still; when the clock runs far longer (a separation in a beat whose clock races
    seventeen days of widening orbits to the next event) the frame widens to all of it, seen from above the plane the craft
    travels in, and an action the CSV asked for by name says so."""
    for b in plan.beats:
        a = actions.get(b.id)
        if a is None or a.strategy != "clock":
            continue
        cut = [k["utc"] for k in clock.get("keys") or [] if b.end - 3 * JUMP_CUT_S < k["t"] < b.end - 1e-6]   # a jump at its end
        u0, u1 = _clock_utc(clock, b.start), cut[0] if cut else _clock_utc(clock, b.end)
        if not u0 or not u1:
            continue
        for sh in [a.intro] + [x[2] for x in a.camera]:
            pth = (sh or {}).get("path")
            if not pth:
                continue
            s0, s1 = parse_iso(pth["from_utc"]), parse_iso(pth["to_utc"])
            v0, v1 = parse_iso(u0), parse_iso(u1)
            slack = max(timedelta(seconds=10), (s1 - s0) * 0.1)  # a wait on the pad, a rest after touchdown
            if v0 >= s0 - slack and v1 <= s1 + slack:
                continue                                           # the clock stays inside the action's stretch
            own, shown = s1 - s0, v1 - v0
            if shown > 3 * own:
                lo, hi = v0, v1
                pth["up"] = "plane"
                if sh is a.intro:
                    a.camera = []                                  # one frame for all of it
                    a.summary += " (framed whole: its time runs on to the next beat's date)"
                    if a.source == "csv":
                        warnings.append(f"row {b.row}: the {a.action} is framed with everything the beat's clock runs through "
                                        f"({shown.total_seconds() / 3600:.1f} h; the action itself covers {own.total_seconds() / 3600:.1f} h); "
                                        f"put a footage beat or a closer date after it to see it close up")
            else:
                half = max(own, shown) / 2
                lo, hi = v0 + shown / 2 - half, v0 + shown / 2 + half
            pth.update(from_utc=iso(lo), to_utc=iso(hi), ref_utc=iso(lo + (hi - lo) / 2))


# ---- automatic temporal layers ------------------------------------------------------------------------------------------
def _runs(plan: Plan, res: Resolution, key: Callable[[BeatContext], Any]) -> List[Tuple[Any, float, float]]:
    """Consecutive beats with the same key -> (key, start, end); footage beats carry the run on (the map is hidden there)."""
    out: List[List[Any]] = []
    for b in plan.beats:
        c = res.contexts.get(b.id)
        if c is None:
            if out:
                out[-1][2] = b.end
            continue
        k = key(c)
        if out and out[-1][0] == k:
            out[-1][2] = b.end
        else:
            out.append([k, b.start, b.end])
    return [(k, s, e) for k, s, e in out]


HAND_OVER_GAP_S = 1.0       # the same craft (or path) shown again within this many seconds, map to map, is one continuous thing
PATH_CROSSFADE_S = 1.0


def _hand_over(layers: List[Dict[str, Any]], trackers: List[Dict[str, Any]], craft_windows: Dict[str, List[Tuple[float, float, str]]],
               plan: Plan) -> None:
    """A craft that carries on into the next beat stays the same object on screen: its layer and tracker meet the next
    beat's at one moment with no fade (no gap, no second copy fading in -- it used to vanish for 0.3 s in the middle of a
    camera move). A path of the same flight cross-fades into the next beat's path instead of blinking out. Not across
    footage (the map is hidden there anyway)."""
    footage = [(b.start, b.end) for b in plan.beats if b.mode == "footage"]
    covered = lambda a, b: any(fa < b + 1e-6 and fb > a - 1e-6 for fa, fb in footage)   # noqa: E731

    def meet(first: Dict[str, Any], second: Dict[str, Any]) -> None:
        at = min(first["end"], second["start"]) if first["end"] > second["start"] else first["end"]
        first["end"], first["fade_out"] = round(at, 3), 0
        second["start"], second["fade_in"] = round(at, 3), 0

    by_id = {L.get("id"): L for L in layers if L["type"] == "spacecraft"}
    track = {T["craft"]: T for T in trackers}
    for wins in craft_windows.values():
        for (_, e1, l1), (s2, _, l2) in zip(wins, wins[1:]):
            if s2 - e1 > HAND_OVER_GAP_S or covered(min(e1, s2), max(e1, s2)) or l1 not in by_id or l2 not in by_id:
                continue
            meet(by_id[l1], by_id[l2])
            if l1 in track and l2 in track:
                meet(track[l1], track[l2])
    paths = sorted((L for L in layers if L["type"] == "trajectory" and L.get("start") is not None and L.get("end") is not None),
                   key=lambda L: L["start"])
    for i, a in enumerate(paths):
        b = next((x for x in paths[i + 1:] if x["of"] == a["of"] and x["start"] >= a["start"] + 1e-6), None)
        if b is None or b["start"] - a["end"] > HAND_OVER_GAP_S or covered(min(a["end"], b["start"]), max(a["end"], b["start"])):
            continue
        at = min(a["end"], b["start"])
        b["start"], b["fade_in"] = round(at, 3), 0.6
        a["end"], a["fade_out"] = round(max(a["end"], at + PATH_CROSSFADE_S), 3), PATH_CROSSFADE_S


def _edge(start: float, end: float, plan: Plan) -> Dict[str, Any]:
    return {"start": round(start, 3), "end": round(end, 3), "fade_in": 0 if start <= 1e-6 else 0.3, "fade_out": 0 if end >= plan.duration - 1e-6 else 0.3}


def _mission_clocks(plan: Plan, res: Resolution, actions: Optional[Dict[str, BeatAction]] = None) -> List[Dict[str, Any]]:
    """One mission clock per stretch of one mission (its own T-zero: T+ after, T- before) or of one date precision. Through a
    narration-paced motion (a years-long cruise, where the planets hold still) the clock shows the craft's date, so it never
    reads launch day while the craft arrives."""
    out = []
    motions = [(b.start, b.end, m) for b in plan.beats for m in [(actions or {}).get(b.id) and actions[b.id].motion(b.start, b.end)] if m]
    for (met, prefix, prec), a, b in _runs(plan, res, lambda c: (c.met_zero, c.clock_prefix, c.precision if c.precision in ("day", "month", "year") else "minute")):
        L = {"type": "mission_clock", "show": "met+utc" if met else "utc", **_edge(a, b, plan)}
        if met:
            L["met_zero"] = met
        if prefix and met:
            L["prefix"] = prefix                                 # a planned T+ clock says so; a date-only clock leaves it to the badge
        if prec != "minute":
            L["date_precision"] = prec
        own = [{"start": round(s, 3), "end": round(e, 3), **m} for s, e, m in motions if s >= a - 1e-6 and e <= b + 1e-6]
        if own:
            L["motions"] = own
        out.append(L)
    return out


def _badges(plan: Plan, res: Resolution) -> List[Dict[str, Any]]:
    out = []
    for text, a, b in _runs(plan, res, lambda c: c.badge):
        if not text:
            continue
        word = text.split(" · ")[0]
        bg = {"PLANNED": STATUS_STYLE["planned"], "PROJECTED": STATUS_STYLE["projected"], "HYPOTHETICAL": STATUS_STYLE["hypothetical"]}.get(word, ESTIMATED_COLOR)
        out.append({"type": "status_badge", "text": text, "bg": bg, "fg": "#06121d", **_edge(a, b, plan)})
    return out


def _footnotes(layers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """FLIGHT PATH ILLUSTRATED (small, bottom centre) while a drawn path or craft's geometry is illustrated or modelled and
    the thing itself is not already labelled PLANNED / PROJECTED / HYPOTHETICAL."""
    spans: Dict[str, List[List[float]]] = {}
    for L in layers:
        if L.get("_basis") in ("illustrated", "modelled") and L.get("_status") not in BADGE and L["type"] in ("trajectory", "spacecraft", "orbit"):
            spans.setdefault(L["_basis"], []).append([L["start"], L["end"]])
    out = []
    for basis, ws in sorted(spans.items()):
        ws.sort()
        merged = [ws[0]]
        for a, b in ws[1:]:
            if a <= merged[-1][1] + 0.5:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            out.append({"type": "footnote", "text": f"FLIGHT PATH {basis.upper()}", "start": round(a, 3), "end": round(b, 3)})
    return out


def _time_jumps(plan: Plan, res: Resolution) -> List[Dict[str, Any]]:
    """A jump in time with no footage to hide it: the map dips dark for a moment and a card says where time went."""
    out = []
    start_of = {b.id: b.start for b in plan.beats}
    for t in res.transitions:
        if t.kind == "jump" and not t.hidden_by_footage:
            at = start_of[t.b]
            out.append({"type": "time_jump", "at": round(at, 3), "text": t.label, "start": round(max(0.0, at - JUMP_LEAD_S), 3),
                        "end": round(min(plan.duration, at + JUMP_TAIL_S), 3), "fade_in": 0, "fade_out": 0, "z": 90})
    return out


def _with_extrapolation(t: Dict[str, Any], cat: Catalog, until) -> Dict[str, Any]:
    """An observed trajectory whose dataset allows linear extrapolation, carried on past its last sample far enough for the
    latest date the video shows (the beats that need it are labelled ESTIMATED; a date past the dataset's limit never gets here:
    resolve.py reports it)."""
    tr = cat.index.trajectories.get(t.get("id", ""))
    if tr is None or not tr.extrapolate or until is None or not t.get("samples") or len(t["samples"]) < 2:
        return t
    a, b = t["samples"][-2], t["samples"][-1]
    if a.get("anchor") != b.get("anchor") or not (a.get("km") and b.get("km")):
        return t
    ta, tb = parse_iso(a["utc"]), parse_iso(b["utc"])
    if until <= tb:
        return t
    from datetime import timedelta

    step = (tb - ta).total_seconds()
    v = [(b["km"][i] - a["km"][i]) / step for i in range(3)]
    end = until + timedelta(days=30)
    out = dict(t, samples=list(t["samples"]))
    when, k = tb, 1
    while when < end:
        when = min(end, tb + timedelta(seconds=step * k))
        dt = (when - tb).total_seconds()
        out["samples"].append({"utc": iso(when), "anchor": b["anchor"], "km": [b["km"][i] + v[i] * dt for i in range(3)], "estimated": True})
        k += 1
    return out


def strip_private(spec: Dict[str, Any]) -> Dict[str, Any]:
    """The spec as the engine reads it (the _row bookkeeping removed)."""
    out = copy.deepcopy(spec)
    for L in out.get("layers", []):
        for k in [k for k in L if k.startswith("_")]:
            L.pop(k)
    return out
