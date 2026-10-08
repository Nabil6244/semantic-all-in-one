"""Visual actions: how a resolved event is SHOWN (the resolver says what happened; this says how the camera and the craft
demonstrate it). Generic and deterministic: an action reads only the beat's resolved context and the trajectory DATA of its
craft (a surface track that starts at a site is a launch, one that ends at a site is a landing, an orbit arc has a period, a
transfer has two bodies). No mission is named here; Apollo 11, Artemis III or Voyager use the same actions.

A beat gets an action from its type column (liftoff, landing, flyby, orbit_insert ...), or extra {"action": ...}, or -- when
the type is empty and the beat shows a craft -- from its date's event (an event may declare "action" in its dataset; else
its name: launch -> liftoff, loi / orbit_insertion -> orbit_insert, landing -> landing, *flyby / closest_approach -> flyby,
tli / tei / departure -> departure, separation / undocking / docking, impact, splashdown / reentry ...).

Each action becomes:
  * a universe-time span for the beat (the clock runs through the ascent, the descent, the closest approach ...), or, for
    journeys of months to decades (a rover's drive, an interstellar cruise), a MOTION: the craft is carried along its
    trajectory by narration while the planets stay put;
  * ONE held frame: the stretch of the craft's path the beat shows (the camera's "path" shot, worked out in the engine from
    the same trajectory), seen from the side -- or from above the plane it bends in, for an orbit, a flyby, a transfer -- so
    the craft visibly crosses a still frame with its tracking box. The camera turns only if the craft would leave the frame,
    and makes at most one move with a reason (a departure for another planet pulls back to the whole leg); never a chase;
  * an engine-burn glow on the craft for a manoeuvre, and the craft shown on its pad before a liftoff.
Which of a few framings (heights of view, margins) an action uses is fixed by the beat and craft ids, so a video with two
launches does not shoot them identically and the same CSV always gives the same video.
An action the data cannot support is reported (an error when the CSV asked for it, a warning when it was inferred) instead
of a misleading static shot. The trajectory's basis and status labels are untouched: an illustrated path stays labelled."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from .beat_csv import Beat, Plan
from .catalog import Catalog, CatalogError
from .temporal import iso, iso_days, parse_iso

from .beat_csv import VISUAL_ACTIONS as ACTIONS
CANON = {"launch": "liftoff", "ascent": "liftoff", "orbit_raise": "orbit", "orbit_lower": "orbit", "arrival": "approach", "descent": "landing",
         "rover_drive": "surface_traverse", "deployment": "separation", "station_keep": "trajectory_follow"}
# an event's name -> an action (the first token rule that matches, in this order)
EVENT_RULES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("liftoff", "launch"), "liftoff"),
    (("landing", "touchdown"), "landing"),
    (("pdi", "powered_descent", "descent"), "descent"),
    (("flyby", "closest_approach", "encounter"), "flyby"),
    (("loi", "orbit_insertion", "dro_insertion", "circularization", "capture"), "orbit_insert"),
    (("tli", "tei", "departure", "lunar_transfer", "trans"), "departure"),
    (("undocking",), "undocking"),
    (("docking",), "docking"),
    (("separation", "deployed", "deployment", "release"), "separation"),
    (("impact",), "impact"),
    (("splashdown", "reentry", "entry"), "reentry"),
    (("burn",), "trajectory_follow"),
)
MOTION_OVER_DAYS = 180.0            # a span longer than this runs as a motion (narration-paced), never by spinning the planets


@dataclass
class Stage:
    """A named phase of an action, up to the mission moment it ends at (it starts where the stage before it ended; the
    first at the action's span start; the last ends at the span end). `weight` is how much narration the phase deserves
    relative to the others in the same clock segment. Presentation pacing only -- the clock still reads the true date of
    where the craft is, frame by frame; a moment (closest approach) is the boundary between two stages."""
    name: str
    until: str
    weight: float


# named emphasis: a transit (a coast, the onward cruise) gets the most narration; a key phase (a burn, the pass itself)
# gets 7/13 of a transit's -- so a burn followed by its coast takes the first 35% of the beat
TRANSIT = 1.0
KEY = 7 / 13


@dataclass
class BeatAction:
    beat: str
    action: str                                   # canonical action
    asked: str                                    # what the CSV or the event said (liftoff, rover_drive ...)
    source: str                                   # csv | event
    craft: Optional[str] = None                   # qualified craft id (the subject)
    trajectory: Optional[str] = None
    body: Optional[str] = None
    site: Optional[Tuple[float, float]] = None
    span: Optional[Tuple[str, str]] = None        # universe (clock) or craft (motion) time the beat covers
    strategy: str = "clock"                       # clock | motion
    camera: List[Tuple[float, float, Dict[str, Any]]] = field(default_factory=list)   # (start fraction, duration fraction, shot)
    intro: Optional[Dict[str, Any]] = None        # the shot the beat glides to first (None: the beat's usual shot)
    burns: List[Tuple[str, str]] = field(default_factory=list)
    show_on_pad: bool = False
    dest: Optional[str] = None                    # where the craft is heading (for the tracker's distance readout)
    readouts: Optional[List[str]] = None          # the tracker's live numbers (None: altitude and speed, + distance with a dest)
    summary: str = ""
    stages: List[Stage] = field(default_factory=list)   # optional phases across the span (none: one even span, as always)
    stages_cross_beats: bool = False              # may its stages run on through undated beats to the next clock key?

    def motion(self, start: float, end: float) -> Optional[Dict[str, Any]]:
        if self.strategy != "motion" or not self.span:
            return None
        lead = min(1.0, 0.12 * (end - start))
        return {"t0": round(start + lead, 3), "t1": round(end - 0.2, 3), "from_utc": self.span[0], "to_utc": self.span[1]}


def event_action(name: str, declared: Optional[str] = None) -> Optional[str]:
    if declared:
        return declared
    toks = set(name.lower().replace("-", "_").split("_")) | {name.lower()}
    for keys, act in EVENT_RULES:
        if any(k in toks or (len(k) > 4 and k in name.lower()) for k in keys):
            return act
    return None


def _shift(utc: str, seconds: float) -> str:
    return iso(parse_iso(utc) + timedelta(seconds=seconds))


def _gens(t: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The trajectory's generator segments, each with its time window (_t0, _t1) worked out from its neighbours: a segment
    that "continue"s starts where the one before ended; one that arrives at the "next" ends where the next one starts."""
    gens = [dict(g) for g in (t.get("generate") or [])]
    for i, g in enumerate(gens):
        g["_t0"] = g.get("from_utc") or (gens[i - 1].get("_t1") if i else None)
        g["_t1"] = g.get("to_utc") or (gens[i + 1].get("from_utc") if i + 1 < len(gens) else None)
    for i in range(len(gens) - 2, -1, -1):                     # a second pass: a window left open by a later segment
        if not gens[i]["_t1"] and gens[i + 1].get("_t0"):
            gens[i]["_t1"] = gens[i + 1]["_t0"]
    return gens


def _at(gens: List[Dict[str, Any]], kind: str, e: str, slack_days: float = 1.0) -> Optional[Dict[str, Any]]:
    """The segment of a kind whose window holds moment e (or starts within slack after it)."""
    best = None
    for g in gens:
        if g.get("kind") != kind or not g.get("_t0"):
            continue
        t1 = g.get("_t1") or g["_t0"]
        if iso_days(g["_t0"], e) >= -slack_days and iso_days(e, t1) >= -1e-6:
            d = abs(iso_days(g["_t0"], e))
            if best is None or d < best[0]:
                best = (d, g)
    return best[1] if best else None


def _radius(cat: Catalog, body: str) -> float:
    try:
        return cat.body_radius_km(body)
    except StopIteration:
        return 6371.0


def resolve_actions(plan: Plan, cat: Catalog, res: Any) -> Tuple[Dict[str, BeatAction], List[str], List[str]]:
    """Every beat's visual action (or none), with the problems: (actions by beat id, errors, warnings)."""
    out: Dict[str, BeatAction] = {}
    errors: List[str] = []
    warnings: List[str] = []
    for b in plan.beats:
        c = res.contexts.get(b.id)
        if c is None:
            continue
        asked, source = None, ""
        if b.move in ACTIONS and b.move != "orbit":
            asked, source = b.move, "csv"
        elif b.extra.get("action"):
            asked, source = str(b.extra["action"]).strip().lower(), "csv"
            if asked not in ACTIONS:
                errors.append(f"row {b.row}: extra action must be one of {', '.join(ACTIONS)} (got {asked!r})")
                continue
        crafts = [it for it in b.layers if it.type == "craft" and it.id]
        if b.move == "orbit" and crafts:
            asked, source = "orbit", "csv"
        if asked is None and crafts and c.event:
            did, name = c.event.split(".", 1)
            ev = cat.index.datasets[did].events.get(name)
            declared = (cat.index.datasets[did].data.get("events", {}).get(name) or {})
            asked = event_action(name, declared.get("action") if isinstance(declared, dict) else None)
            source = "event" if asked else ""
            del ev
        if not asked:
            continue
        try:
            act = _build(b, c, asked, source, crafts, cat, res)
        except _Incomplete as exc:
            msg = f"row {b.row}: {exc}"
            (errors if source == "csv" else warnings).append(msg + ("" if source == "csv" else " (shown as a plain shot)"))
            continue
        out[b.id] = act
    return out, errors, warnings


class _Incomplete(ValueError):
    pass


def _build(b: Beat, c: Any, asked: str, source: str, crafts: List[Any], cat: Catalog, res: Any) -> BeatAction:
    action = CANON.get(asked, asked)
    word = {"liftoff": "Launch", "landing": "Landing", "flyby": "Flyby", "orbit_insert": "Orbit insertion", "departure": "Departure",
            "transfer": "Transfer", "surface_traverse": "Surface drive", "deep_space_departure": "Deep-space departure"}.get(action, action.replace("_", " ").capitalize())
    if not crafts:
        raise _Incomplete(f"{word} visual incomplete: no spacecraft resolved (add a craft row to the beat)")
    try:
        cq = cat.craft_id(crafts[0].id, c.datasets)
    except CatalogError as exc:
        raise _Incomplete(f"{word} visual incomplete: {exc}") from None
    craft = cat.craft(cq)
    tid = craft.get("trajectory")
    if not tid or tid not in cat.index.trajectories:
        raise _Incomplete(f"{word} visual incomplete: {cq} has no trajectory")
    T = cat.index.trajectories[tid]
    data = T.data
    frame = data.get("frame") or (data.get("samples") or [{}])[0].get("anchor") or "earth"
    when = c.utc
    if not when:
        raise _Incomplete(f"{word} visual incomplete: the beat needs a date (the event to show)")
    e = cat.index.datasets[c.event.split(".", 1)[0]].events[c.event.split(".", 1)[1]].utc if c.event else when
    a = BeatAction(beat=b.id, action=action, asked=asked, source=source, craft=cq, trajectory=tid, body=frame)
    R = _radius(cat, frame)
    pick = _variant(b.id, cq)
    gens = _gens(data)

    def hold(t0: str, t1: str, el: float, km: float, fit: float = 1.35, up: str = "radial") -> Dict[str, Any]:
        """The action's frame: the stretch of the craft's path the beat shows, framed whole from the side and HELD -- the
        craft visibly crosses it and the tracker goes with it; the camera only turns if the craft would leave the frame."""
        path = {"trajectory": tid, "from_utc": t0, "to_utc": t1, "fit": fit, **({"up": up} if up != "radial" else {})}
        return {"path": path, "el_deg": el, "keep": {"trajectory": tid, "within": 0.8}, "_km": round(km)}

    if action == "liftoff":
        g = next((x for x in gens if x.get("kind") == "surface_track" and x.get("site_at") != "end"), None)
        if g is None:
            raise _Incomplete(f"Launch visual incomplete: {cq}'s trajectory has no launch track from a surface site")
        body, (lon, lat) = g["body"], g["site"]
        R = _radius(cat, body)
        a.body, a.site = body, (lon, lat)
        a.span = (_shift(g["from_utc"], -8), g["to_utc"])
        a.show_on_pad = True
        # the whole climb in one held frame, seen low from the side: the rocket rises off its pad and arcs over into orbit
        a.intro = hold(g["from_utc"], g["to_utc"], (14, 20, 27)[pick % 3], _arc_km(g, R))
        a.readouts = ["altitude", "speed"]
        a.summary = f"{cq} lifts off from {body}@{lon},{lat}; ascent {a.span[0][11:16]}→{a.span[1][11:16]} UTC"
    elif action == "landing":
        g = next((x for x in reversed(gens) if x.get("kind") == "surface_track" and x.get("site_at") == "end"), None)
        if g is None:
            raise _Incomplete(f"Landing visual incomplete: {cq}'s trajectory does not end on a surface site")
        body, (lon, lat) = g["body"], g["site"]
        R = _radius(cat, body)
        a.body, a.site = body, (lon, lat)
        a.span = (g["from_utc"], _shift(g["to_utc"], 5))
        # the whole descent held from the side: braking high and fast, then pitching up and coming straight down on the site
        a.intro = hold(g["from_utc"], g["to_utc"], (10, 16, 24)[pick % 3], _arc_km(g, R), fit=1.3)
        a.readouts = ["altitude", "speed"]
        a.summary = f"{cq} descends to {body}@{lon},{lat}; {a.span[0][11:16]}→{a.span[1][11:16]} UTC"
    elif action in ("orbit_insert", "orbit", "approach"):
        g = _at(gens, "orbit_arc", e)
        body = (g or {}).get("body") or _place_body(b, cat, c)
        if body is None:
            raise _Incomplete(f"{word} visual incomplete: no orbit around a body in {cq}'s trajectory and no body to frame")
        R = _radius(cat, body)
        P = float(g.get("period_min", 120)) * 60 if g else 3600.0
        a.body = body
        r = _orbit_radius(g, R, gens[gens.index(g) - 1] if g and gens.index(g) else None) if g else None
        if action == "orbit":
            a.span = (e, _shift(e, 0.6 * P))
        else:
            a.span = (_shift(e, -0.12 * P), _shift(e, 0.3 * P))     # the arrival and the first stretch of orbit
            if action == "orbit_insert":
                half = max(120.0, 0.04 * P)
                a.burns = [(_shift(e, -half), _shift(e, half))]
        # the stretch of orbit the beat shows, seen from above its plane and held: going round is always across the screen,
        # never towards the camera, and the body sits inside the curve
        a.intro = hold(a.span[0], a.span[1], (38, 46, 32)[pick % 3], 3 * (r or 2 * R), fit=1.3, up="plane")
        a.readouts = ["altitude", "speed"]
        a.summary = f"{cq} " + {"orbit": "orbits", "orbit_insert": "enters orbit around", "approach": "approaches"}[action] + f" {body}" + \
            (f" (period {P / 60:.0f} min)" if action == "orbit" else f" at {e[:16].replace('T', ' ')} UTC")
    elif action in ("departure", "transfer"):
        g = _at(gens, "transfer", e, slack_days=0.5)
        if g is None:
            raise _Incomplete(f"{word} visual incomplete: {cq}'s trajectory has no transfer leg at {e[:16].replace('T', ' ')} UTC")
        A, B = g.get("from"), g.get("to")
        RA = _radius(cat, A)
        a.body, a.dest = A, B
        t0, end = g.get("_t0") or e, g.get("_t1") or _shift(e, 3 * 86400)
        far = bool(B) and not _local(cat, A, B)
        leg_km = 1.5e8 if far else 4e5
        if action == "transfer":                                 # the whole leg (months or years: narration-paced, below)
            a.span = (t0, end)
            a.intro = hold(t0, end, (70, 80, 62)[pick % 3], leg_km, fit=1.25, up="plane")
        else:                                                   # leaving: the burn and the first days away
            a.span = (_shift(e, -300), end if iso_days(e, end) <= 3 else _shift(e, 3 * 86400))
            # seen from above the plane it leaves in, so the craft's climb away runs across the screen
            a.intro = hold(a.span[0], a.span[1], (58, 66, 50)[pick % 3], 60 * RA, up="plane")
            if far:
                # one move, with a reason: once it is on its way, pull back to the whole leg -- where it is going
                a.camera = [(0.5, 0.42, hold(t0, end, 72, leg_km, fit=1.25, up="plane"))]
        a.burns = [(_shift(e, -180), _shift(e, 360))]
        if action == "departure":
            # the burn gets narration time before the coast races: span start -> the burn's end, then on to the span's end
            burn_end = a.burns[0][1]
            if iso_days(a.span[0], burn_end) > 0 and iso_days(burn_end, a.span[1]) > 0:
                a.stages = [Stage("burn", burn_end, KEY), Stage("coast", a.span[1], TRANSIT)]
        a.readouts = ["distance", "speed"] if B else ["altitude", "speed"]
        a.summary = f"{cq} leaves {A}" + (f" for {B}" if B else "")
    elif action == "flyby":
        fg = _at(gens, "flyby", e, slack_days=0.5)               # a modelled pass (a hyperbola) knows its own body and window
        body = (fg or {}).get("body") or _place_body(b, cat, c) or _sample_anchor(data, e)
        if body is None:
            raise _Incomplete(f"Flyby visual incomplete: no body to fly past (give the beat a place)")
        Rb = _radius(cat, body)
        h = min(36.0, max(1.0, Rb / 2000.0)) * 3600
        a.body, a.span = body, (_shift(e, -h), _shift(e, h))
        if fg and fg.get("_t0") and fg.get("_t1"):
            a.span = (max(fg["_t0"], a.span[0]), min(fg["_t1"], a.span[1]))
        # the pass is the key phase on both sides of closest approach (a boundary, not a stage)
        if iso_days(a.span[0], e) > 0 and iso_days(e, a.span[1]) > 0:
            a.stages = [Stage("approach", e, KEY), Stage("departure", a.span[1], KEY)]
            a.stages_cross_beats = True
        # the bend of the flyby, seen from above its plane, held: the craft swings past the body and away
        a.intro = hold(a.span[0], a.span[1], (62, 75, 50)[pick % 3], 8 * Rb, fit=1.3, up="plane")
        a.readouts = ["altitude", "speed"]
        a.summary = f"{cq} flies past {body}, closest at {e[:16].replace('T', ' ')} UTC"
    elif action in ("docking", "undocking", "separation"):
        Rf = _radius(cat, frame)
        a.span = (_shift(e, -360), _shift(e, 600))
        a.intro = hold(a.span[0], a.span[1], (25, 35)[pick % 2], max(200.0, 0.5 * Rf))
        a.readouts = ["altitude", "speed"]
        a.summary = f"{cq}: {action} at {e[:16].replace('T', ' ')} UTC"
    elif action == "impact":
        body = _place_body(b, cat, c)
        if body is None:
            raise _Incomplete("Impact visual incomplete: no target body (give the beat a place)")
        a.body, a.span = body, (_shift(e, -1800), _shift(e, 10))
        a.intro = hold(a.span[0], a.span[1], (18, 26)[pick % 2], 1e4)
        a.readouts = ["altitude", "speed"]
        a.summary = f"{cq} strikes {body} at {e[:16].replace('T', ' ')} UTC"
    elif action == "reentry":
        Rf = _radius(cat, frame)
        a.span = (_shift(e, -900), e)
        a.intro = hold(a.span[0], a.span[1], (15, 24)[pick % 2], 0.6 * Rf)
        a.readouts = ["altitude", "speed"]
        a.summary = f"{cq} returns through the atmosphere of {frame}"
    elif action == "surface_traverse":
        samples = [s for s in (data.get("samples") or []) if s.get("lla")]
        if len(samples) < 2:
            raise _Incomplete(f"Surface drive visual incomplete: {cq}'s trajectory has no path on the surface")
        lon, lat = samples[0]["lla"][0], samples[0]["lla"][1]
        a.site, a.strategy = (lon, lat), "motion"
        end = T.observed_until or samples[-1]["utc"]
        a.span = (iso(parse_iso(samples[0]["utc"])), iso(parse_iso(end)))
        a.intro = hold(a.span[0], a.span[1], (55, 65)[pick % 2], 30, fit=1.4)
        a.readouts = []
        a.summary = f"{cq} drives across {frame} ({a.span[0][:10]} → {a.span[1][:10]}, shown at the pace of the narration)"
    elif action == "deep_space_departure":
        a.strategy = "motion"
        end = T.observed_until or T.end
        a.span = (e, end)
        a.body = "sun"
        a.intro = hold(e, end, (55, 68)[pick % 2], 1.5e10, fit=1.3, up="plane")
        a.readouts = ["from", "speed"]
        a.summary = f"{cq} heads out of the solar system ({e[:4]} → {end[:4]}, at the pace of the narration)"
    else:                                                       # trajectory_follow: its path for half an hour, held
        Rf = _radius(cat, frame)
        a.span = (e, _shift(e, 1800))
        a.intro = hold(a.span[0], a.span[1], 28, max(300.0, Rf))
        a.readouts = ["altitude", "speed"]
        a.summary = f"{cq} on its path at {e[:16].replace('T', ' ')} UTC"
    if any(t.b == b.id and t.kind == "continuous" for t in getattr(res, "transitions", [])):
        # time runs in from the beat before: the beat shows the path from where the clock already is, so frame that
        for sh in [a.intro] + [x[2] for x in a.camera]:
            if sh and sh.get("path") and iso_days(sh["path"]["from_utc"], when) > 0 and iso_days(when, sh["path"]["to_utc"]) > 0:
                sh["path"]["from_utc"] = when
    if c.event and "burn" in c.event.split(".", 1)[1] and not a.burns:
        a.burns = [(_shift(e, -180), _shift(e, 180))]              # a named burn glows on the craft
    if a.span and a.strategy == "clock" and iso_days(a.span[0], a.span[1]) > MOTION_OVER_DAYS:
        a.strategy = "motion"
    for sh in [a.intro] + [x[2] for x in a.camera]:
        if sh and sh.get("path"):
            # the moment the frame is worked out for: the stretch's middle while the clock runs through it; the beat's own
            # date (where the planets stay) for a narration-paced motion
            pth = sh["path"]
            pth["ref_utc"] = when if a.strategy == "motion" else _shift(pth["from_utc"], 0.5 * iso_days(pth["from_utc"], pth["to_utc"]) * 86400)
    return a


def _variant(beat: str, craft: str) -> int:
    """A stable small number per beat and craft: which of an action's framings to use (the same CSV always gives the same
    video; two launches in one video are not shot identically)."""
    import hashlib

    return int(hashlib.sha1(f"{beat}|{craft}".encode()).hexdigest()[:8], 16)


def _arc_km(g: Dict[str, Any], R: float) -> float:
    import math

    return math.radians(float(g.get("arc_deg", 10))) * R


def _local(cat: Catalog, a: str, b: str) -> bool:
    """Two bodies of one local system (a planet and its moon): a departure between them can be followed closely."""
    parent = {w["id"]: w.get("parent") for w in cat.base_world + [x for d in cat.index.datasets.values() for x in d.world]}
    return parent.get(a) == b or parent.get(b) == a


def _orbit_radius(g: Dict[str, Any], R: float, prev: Optional[Dict[str, Any]] = None) -> Optional[float]:
    if g.get("continue") and prev is not None and prev.get("alt_far_km") is not None and g.get("altitude_km") is None and not g.get("radius"):
        return R + float(prev["alt_far_km"])                    # an orbit that carries on from an ascent: its height is where the ascent ended
    if g.get("radius"):
        from .compile import KM_PER_AU, KM_PER_LY

        rr = g["radius"]
        return float(rr.get("km") or 0) or float(rr.get("au", 0)) * KM_PER_AU or float(rr.get("ly", 0)) * KM_PER_LY
    if g.get("altitude_km") is not None:
        return R + float(g["altitude_km"])
    if g.get("to_altitude_km") is not None:
        return R + float(g["to_altitude_km"])
    return None


def _place_body(b: Beat, cat: Catalog, c: Any) -> Optional[str]:
    if not b.place:
        return None
    try:
        p = cat.place(b.place, c.datasets)
    except CatalogError:
        return None
    return p.body if p.kind in ("body", "site") else p.other or p.body


def _sample_anchor(data: Dict[str, Any], e: str) -> Optional[str]:
    best = None
    for s in data.get("samples") or []:
        d = abs(iso_days(s["utc"], e))
        if s.get("anchor") not in (None, "sun") and (best is None or d < best[0]):
            best = (d, s["anchor"])
    return best[1] if best and best[0] < 5 else None
