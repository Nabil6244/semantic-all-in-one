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
        shot = ({"target": f"{parent}+{p.body}", "fit": 1.5, "light": "front", "el_deg": 25} if parent
                else {"target": p.body, "fill": 0.12, "light": "side", "el_deg": 20})
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
    return s


def _creep(length: float) -> float:
    """How much wider a beat with no move of its own starts than it ends: a slow push-in keeps every shot alive (a held
    camera reads as stuck). Longer beats creep a little further, never more than a quarter."""
    return min(1.25, 1.0 + 0.035 * max(0.0, length))


def _action_shot(shot: Optional[Dict[str, Any]], usual: Dict[str, Any], act: BeatAction, b: Beat) -> Dict[str, Any]:
    """An action's camera intent as a shot of the existing camera (None = the beat's usual view; a motion placeholder gets the
    beat's narration-paced motion)."""
    s = copy.deepcopy(usual if shot is None else shot)
    if s.get("follow") and s["follow"].get("motion") == "beat":
        s["follow"]["motion"] = act.motion(b.start, b.end)
        if s["follow"]["motion"] is None:
            del s["follow"]["motion"]
    return s


def build_camera(cat: Catalog, plan: Plan, notes: List[str], res: Optional[Resolution] = None,
                 actions: Optional[Dict[str, BeatAction]] = None) -> Dict[str, Any]:
    start: Optional[Dict[str, Any]] = None
    moves: List[Dict[str, Any]] = []
    prev_key, prev_km, cur = None, None, None
    for b in plan.beats:
        if b.mode == "footage":
            continue
        shot, place = shot_for(cat, b, res.ctx(b.id) if res else ())
        km = _approx_km(shot, cat, place)
        act = (actions or {}).get(b.id)
        if act is not None and (act.intro is not None or act.camera):
            # a visual action: glide to its first view, then its camera intents (follow the craft, settle, pull back)
            length = b.end - b.start
            intro = _action_shot(act.intro, shot, act, b)
            if start is None:
                start, glide = intro, 0.0
            else:
                ikm = _approx_km(intro, cat, place)
                glide = min(max(2.0, 2.0 + 0.5 * abs(math.log10(max(ikm, 1e-3) / max(prev_km, 1e-3)))), 4.5, max(1.0, 0.3 * length))
                moves.append({"t": round(b.start, 3), "dur": round(glide, 3), "to": intro})
            last = b.start + glide
            for frac, dfrac, s in act.camera:
                t = max(b.start + frac * length, last)
                d = max(0.5, min(dfrac * length, b.end - 0.2 - t))
                if t >= b.end - 0.4:
                    break
                moves.append({"t": round(t, 3), "dur": round(d, 3), "to": _action_shot(s, shot, act, b)})
                last = t + d
            cur = moves[-1]["to"] if moves else start
            prev_key, prev_km = ("action", b.id), _approx_km(cur, cat, place)
            continue
        key = (b.place.lower(), b.frame, b.move, tuple(sorted(b.extra.items())))
        length = b.end - b.start
        creep = b.move == ""                                      # no move asked for: creep in slowly through the beat
        first = shot
        if b.move == "push_in":
            first = _scaled(shot, 1.6)
        elif b.move == "pull_out":
            first = _scaled(shot, 1 / 1.6)
        elif creep:
            first = _scaled(shot, _creep(length))
        if start is None:
            start, glide = first, 0.0
        elif key == prev_key and b.move in ("", "hold", "orbit"):
            glide = 0.0                                           # the same view: no new glide...
            if creep and cur is not None and length >= 1.3:      # ...but it keeps creeping in from where the last beat ended
                cur = _scaled(cur, 1 / _creep(length))
                moves.append({"t": round(b.start, 3), "dur": round(length - 0.3, 3), "to": cur})
            prev_key, prev_km = key, km
            continue
        else:
            glide = min(max(2.5, 2.5 + 0.55 * abs(math.log10(km / prev_km))), 6.0, max(1.0, 0.7 * length))
            if creep and length - glide - 0.3 < 1.0:
                first = shot                                      # too short to creep: glide straight to the shot
            moves.append({"t": round(b.start, 3), "dur": round(glide, 3), "to": first})
        cur = first
        if b.move in ("push_in", "pull_out") or (creep and first is not shot):
            rest = length - glide - 0.3
            if rest >= 1.0:
                moves.append({"t": round(b.start + glide, 3), "dur": round(rest, 3), "to": shot})
                cur = shot
            elif not creep:
                notes.append(f"row {b.row}: beat {b.id} is too short to {b.move.replace('_', ' ')}; the camera holds")
        prev_key, prev_km = key, km
    if start is None:
        start = {"target": "earth", "fill": 0.5, "light": "side", "el_deg": 20}
    return {"drift_deg_per_s": 0.35, "start": start, "moves": moves}


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
    for k, (i, utc) in enumerate(dated):
        b = beats[i]
        act = acts.get(b.id)
        tr = jumps.get(b.id)
        if tr is not None and keys:
            a = beats[dated[k - 1][0]]
            t0, u0 = held.get(a.id, (a.start, dated[k - 1][1]))
            add(b.start - JUMP_CUT_S, shifted(u0, b.start - JUMP_CUT_S - t0))   # the old date holds to the cut
        # the beat's date is its first moment; an action the CSV asked for by name starts where the action starts
        add(b.start, act.span[0] if act and act.source == "csv" else utc)
        if act and b.id not in continuous_from:
            # the action's own end (an ascent, a descent, a closest approach) when time does not run on into the next beat
            add(b.end - 0.05, act.span[1])
            held[b.id] = (b.end - 0.05, act.span[1])
        nxt = dated[k + 1][0] if k + 1 < len(dated) else len(beats)
        cut = next((j for j in range(i + 1, nxt) if beats[j].mode == "footage"), None)
        if cut is not None and k + 1 < len(dated):
            add(beats[cut].start, shifted(utc, beats[cut].start - b.start))   # hold (real time) until the footage
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


def compile_plan(plan: Plan, cat: Catalog, *, media: Optional[Dict[str, Any]] = None, resolve_media: bool = True,
                 width: int = W, height: int = H, fps: int = 30, watermark: Optional[Dict[str, Any]] = None,
                 reference_now: Optional[str] = None, resolution: Optional[Resolution] = None) -> Compiled:
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
    _fit_actions_to_time(plan, res, actions, act_warnings)
    clock = build_clock(cat, plan, problems, notes, res, actions)
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
                    act = actions.get(b.id)
                    if act is not None and act.craft == cid:
                        if act.show_on_pad:
                            L["show"] = "always"                            # on its pad before the liftoff
                        if act.burns:
                            L["burns"] = [{"from_utc": x, "to_utc": y} for x, y in act.burns]
                        if act.motion(b.start, b.end):
                            L["motion"] = act.motion(b.start, b.end)
                    bc = tctx[b.id]
                    estimated = bc is not None and bc.estimated_from and cat.index.trajectories.get(base.get("trajectory") or "") is not None \
                        and cat.index.trajectories[base["trajectory"]].observed_until
                    if L.get("label") and (status in BADGE or estimated):
                        L["label"] = f"{L['label']} · {BADGE[status] if status in BADGE else 'ESTIMATED'}"
                        L["label_bg"] = STATUS_STYLE.get(status, ESTIMATED_COLOR)
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
                    L = {"type": "link", "style": style, "reveal": {"t0": start, "t1": start + 1.0}, **timing}
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
        free = [c for c in b.clips if not c.dur]
        share = (span - fixed) / len(free) if free else 0
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
        tail += _mission_clocks(plan, res)
    tail += _badges(plan, res) + _footnotes(layers) + _time_jumps(plan, res)
    for d in sorted(cat.used):
        if d not in res.used:
            res.used.append(d)
    res.used.sort()
    spec: Dict[str, Any] = {
        "width": width, "height": height, "fps": fps, "duration": round(plan.duration, 3),
        "clock": clock, "world": copy.deepcopy(cat.world), "camera": build_camera(cat, plan, notes, res, actions),
        "layers": auto + trajectories + layers + tail, "footage": footage,
        "starmap": {"pack": cat.default or "", "datasets": list(res.used), "title": plan.title, "reference_now": res.reference_now,
                    "beats": {bid: {"status": c.status, "basis": c.basis, "utc": c.utc, "timeline": c.timeline, "badge": c.badge,
                                    "datasets": c.datasets} for bid, c in res.contexts.items()}},
    }
    if watermark and watermark.get("text"):
        spec["watermark"] = watermark
    spec["starmap"]["actions"] = {bid: {"action": a.action, "craft": a.craft, "strategy": a.strategy, "span": list(a.span) if a.span else None}
                                  for bid, a in actions.items()}
    return Compiled(spec=spec, notes=notes, needs_media=needs, resolution=res, actions=actions, warnings=act_warnings)


def _fit_actions_to_time(plan: Plan, res: Resolution, actions: Dict[str, BeatAction], warnings: List[str]) -> None:
    """When a beat's time runs on into the next beat's date (continuous) far beyond what its action shows -- an orbit insertion
    in a beat whose clock races three days to the next event -- a close follow would look at empty space. The action keeps its
    burn and span but shows in the beat's usual view; an action the CSV asked for by name says so."""
    beats = plan.beats
    nxt: Dict[str, str] = {}
    for t in res.transitions:
        if t.kind == "continuous":
            nxt[t.a] = t.b_utc
    for bid, a in actions.items():
        if a.strategy != "clock" or not a.span or bid not in nxt or not a.camera:
            continue
        b = next(x for x in beats if x.id == bid)
        start = a.span[0] if a.source == "csv" else res.contexts[bid].utc
        runs, own = abs(iso_seconds(start, nxt[bid])), max(1.0, abs(iso_seconds(*a.span)))
        if runs > 3 * own:
            a.camera, a.intro = [], None
            a.summary += " (shown in the beat's usual view: its time runs on to the next beat's date)"
            if a.source == "csv":
                warnings.append(f"row {b.row}: the {a.action} is shown in the usual view: this beat's time runs {runs / 3600:.1f} h on to the next "
                                f"beat's date (the action itself covers {own / 3600:.1f} h); put a footage beat or a closer date after it to see it close up")


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


def _edge(start: float, end: float, plan: Plan) -> Dict[str, Any]:
    return {"start": round(start, 3), "end": round(end, 3), "fade_in": 0 if start <= 1e-6 else 0.3, "fade_out": 0 if end >= plan.duration - 1e-6 else 0.3}


def _mission_clocks(plan: Plan, res: Resolution) -> List[Dict[str, Any]]:
    """One mission clock per stretch of one mission (its own T-zero: T+ after, T- before) or of one date precision."""
    out = []
    for (met, prefix, prec), a, b in _runs(plan, res, lambda c: (c.met_zero, c.clock_prefix, c.precision if c.precision in ("day", "month", "year") else "minute")):
        L = {"type": "mission_clock", "show": "met+utc" if met else "utc", **_edge(a, b, plan)}
        if met:
            L["met_zero"] = met
        if prefix and met:
            L["prefix"] = prefix                                 # a planned T+ clock says so; a date-only clock leaves it to the badge
        if prec != "minute":
            L["date_precision"] = prec
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
