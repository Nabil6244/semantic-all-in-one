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
  * camera intents as the existing camera's shots: frame the body or site, then FOLLOW the craft (a shot on its trajectory),
    then settle or pull back -- glides, never cuts;
  * an engine-burn glow on the craft for a manoeuvre, and the craft shown on its pad before a liftoff.
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
    summary: str = ""

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
    follow = lambda dist_km, el=25, **k: {"target": frame, "follow": {"trajectory": tid}, "distance": {"km": round(dist_km)},  # noqa: E731
                                          "light": "side", "el_deg": el, **k}
    gens = _gens(data)
    if action == "liftoff":
        g = next((x for x in gens if x.get("kind") == "surface_track" and x.get("site_at") != "end"), None)
        if g is None:
            raise _Incomplete(f"Launch visual incomplete: {cq}'s trajectory has no launch track from a surface site")
        body, (lon, lat) = g["body"], g["site"]
        R = _radius(cat, body)
        a.body, a.site = body, (lon, lat)
        a.span = (_shift(g["from_utc"], -8), g["to_utc"])
        a.show_on_pad = True
        a.intro = {"target": f"{body}@{lon},{lat}", "distance": {"km": round(0.22 * R)}, "light": "side", "el_deg": 28}
        a.camera = [(0.30, 0.25, follow(0.06 * R, 22)), (0.60, 0.38, follow(0.6 * R, 30))]
        a.summary = f"{cq} lifts off from {body}@{lon},{lat}; ascent {a.span[0][11:16]}→{a.span[1][11:16]} UTC"
    elif action == "landing":
        g = next((x for x in reversed(gens) if x.get("kind") == "surface_track" and x.get("site_at") == "end"), None)
        if g is None:
            raise _Incomplete(f"Landing visual incomplete: {cq}'s trajectory does not end on a surface site")
        body, (lon, lat) = g["body"], g["site"]
        R = _radius(cat, body)
        a.body, a.site = body, (lon, lat)
        a.span = (g["from_utc"], _shift(g["to_utc"], 5))
        site = f"{body}@{lon},{lat}"
        a.intro = {"target": site, "distance": {"km": round(0.5 * R)}, "light": "side", "el_deg": 50}
        a.camera = [(0.20, 0.25, {"target": body, "follow": {"trajectory": tid}, "distance": {"km": round(0.05 * R)}, "light": "side", "el_deg": 30}),
                    (0.65, 0.30, {"target": site, "distance": {"km": round(max(30, 0.08 * R))}, "light": "side", "el_deg": 22})]
        a.summary = f"{cq} descends to {site}; {a.span[0][11:16]}→{a.span[1][11:16]} UTC"
    elif action in ("orbit_insert", "orbit", "approach"):
        g = _at(gens, "orbit_arc", e)
        body = (g or {}).get("body") or _place_body(b, cat, c)
        if body is None:
            raise _Incomplete(f"{word} visual incomplete: no orbit around a body in {cq}'s trajectory and no body to frame")
        R = _radius(cat, body)
        P = float(g.get("period_min", 120)) * 60 if g else 3600.0
        a.body = body
        r = _orbit_radius(g, R) if g else None
        # the whole orbit in view (its real size from the data), looked down on
        whole = {"target": body, "distance": {"km": round(3.4 * r)}, "light": "side", "el_deg": 40} if r else None
        if action == "orbit":
            a.span = (e, _shift(e, 0.6 * P))
            a.intro = whole
            a.summary = f"{cq} orbits {body} (period {P / 60:.0f} min)"
        else:
            a.span = (_shift(e, -0.12 * P), _shift(e, 0.5 * P))
            if action == "orbit_insert":
                half = max(120.0, 0.04 * P)
                a.burns = [(_shift(e, -half), _shift(e, half))]
            a.camera = [(0.15, 0.25, {"target": body, "follow": {"trajectory": tid}, "distance": {"km": round(1.2 * R)}, "light": "side", "el_deg": 55}),
                        (0.55, 0.40, whole)]                                     # the orbit it settled into (None: the usual view)
            a.summary = f"{cq} {'enters orbit around' if action == 'orbit_insert' else 'approaches'} {body} at {e[:16].replace('T', ' ')} UTC"
    elif action in ("departure", "transfer"):
        g = _at(gens, "transfer", e, slack_days=0.5)
        if g is None:
            raise _Incomplete(f"{word} visual incomplete: {cq}'s trajectory has no transfer leg at {e[:16].replace('T', ' ')} UTC")
        A, B = g.get("from"), g.get("to")
        RA = _radius(cat, A)
        a.body = A
        end = g.get("_t1") or _shift(e, 3 * 86400)
        if action == "transfer":                                 # the whole leg (months or years: narration-paced, below)
            a.span = (g.get("_t0") or e, end)
        else:                                                   # leaving: the burn and the first days away
            a.span = (_shift(e, -300), end if iso_days(e, end) <= 3 else _shift(e, 3 * 86400))
        a.burns = [(_shift(e, -180), _shift(e, 360))]
        wide = {"target": f"{A}+{B}", "fit": 1.4, "light": "front", "el_deg": 25} if B else follow(8 * RA, 30)
        if action == "transfer":
            a.intro = wide
            a.camera = [(0.35, 0.3, follow(3 * RA, 25)), (0.7, 0.28, wide)]
        else:
            a.intro = {"target": A, "fill": 0.45, "light": "side", "el_deg": 25}
            if B and not _local(cat, A, B):
                a.camera = [(0.35, 0.5, wide)]                  # across the solar system: the whole leg, not a close follow
            else:
                a.camera = [(0.25, 0.3, {"target": A, "follow": {"trajectory": tid}, "distance": {"km": round(1.2 * RA)}, "light": "side", "el_deg": 25}),
                            (0.6, 0.38, wide)]
        a.summary = f"{cq} leaves {A}" + (f" for {B}" if B else "")
    elif action == "flyby":
        body = _place_body(b, cat, c) or _sample_anchor(data, e)
        if body is None:
            raise _Incomplete(f"Flyby visual incomplete: no body to fly past (give the beat a place)")
        Rb = _radius(cat, body)
        h = min(36.0, max(1.0, Rb / 2000.0)) * 3600
        a.body, a.span = body, (_shift(e, -h), _shift(e, h))
        a.intro = {"target": body, "fill": 0.3, "light": "side", "el_deg": 15}
        a.camera = [(0.30, 0.25, follow(4 * Rb, 20)), (0.62, 0.35, follow(12 * Rb, 25))]
        a.summary = f"{cq} flies past {body}, closest at {e[:16].replace('T', ' ')} UTC"
    elif action in ("docking", "undocking", "separation"):
        Rf = _radius(cat, frame)
        a.span = (_shift(e, -360), _shift(e, 600))
        a.intro = follow(max(60.0, 0.03 * Rf), 30)
        a.camera = [(0.5, 0.45, follow(max(200.0, 0.12 * Rf), 30))]
        a.summary = f"{cq}: {action} at {e[:16].replace('T', ' ')} UTC"
    elif action == "impact":
        body = _place_body(b, cat, c)
        if body is None:
            raise _Incomplete("Impact visual incomplete: no target body (give the beat a place)")
        Rb = max(0.05, _radius(cat, body))
        a.body, a.span = body, (_shift(e, -1800), _shift(e, 10))
        a.intro = {"target": body, "distance": {"km": round(max(60.0, 40 * Rb))}, "light": "side", "el_deg": 20}
        a.camera = [(0.2, 0.3, follow(max(25.0, 10 * Rb), 20)), (0.7, 0.28, {"target": body, "distance": {"km": round(max(12.0, 5 * Rb))}, "light": "side", "el_deg": 20})]
        a.summary = f"{cq} strikes {body} at {e[:16].replace('T', ' ')} UTC"
    elif action == "reentry":
        Rf = _radius(cat, frame)
        a.span = (_shift(e, -900), e)
        a.camera = [(0.2, 0.3, follow(0.1 * Rf, 25)), (0.65, 0.32, follow(0.25 * Rf, 35))]
        a.summary = f"{cq} returns through the atmosphere of {frame}"
    elif action == "surface_traverse":
        samples = [s for s in (data.get("samples") or []) if s.get("lla")]
        if len(samples) < 2:
            raise _Incomplete(f"Surface drive visual incomplete: {cq}'s trajectory has no path on the surface")
        lon, lat = samples[0]["lla"][0], samples[0]["lla"][1]
        a.site, a.strategy = (lon, lat), "motion"
        end = T.observed_until or samples[-1]["utc"]
        a.span = (iso(parse_iso(samples[0]["utc"])), iso(parse_iso(end)))
        a.intro = {"target": f"{frame}@{lon},{lat}", "distance": {"km": 60}, "light": "side", "el_deg": 40}
        a.camera = [(0.15, 0.25, {"target": frame, "follow": {"trajectory": tid, "motion": "beat"}, "distance": {"km": 25}, "light": "side", "el_deg": 35})]
        a.summary = f"{cq} drives across {frame} ({a.span[0][:10]} → {a.span[1][:10]}, shown at the pace of the narration)"
    elif action == "deep_space_departure":
        a.strategy = "motion"
        end = T.observed_until or T.end
        a.span = (e, end)
        a.intro = {"target": "sun", "distance": {"au": 300}, "el_deg": 30}
        a.camera = [(0.3, 0.6, {"target": "sun", "follow": {"trajectory": tid, "motion": "beat"}, "distance": {"au": 90}, "el_deg": 30})]
        a.summary = f"{cq} heads out of the solar system ({e[:4]} → {end[:4]}, at the pace of the narration)"
    else:                                                       # trajectory_follow: ride along
        Rf = _radius(cat, frame)
        a.span = (e, _shift(e, 1800))
        a.camera = [(0.2, 0.5, follow(max(300.0, 0.15 * Rf), 30))]
        a.summary = f"{cq} on its path at {e[:16].replace('T', ' ')} UTC"
    if c.event and "burn" in c.event.split(".", 1)[1] and not a.burns:
        a.burns = [(_shift(e, -180), _shift(e, 180))]              # a named burn glows on the craft
    if a.span and a.strategy == "clock" and iso_days(a.span[0], a.span[1]) > MOTION_OVER_DAYS:
        a.strategy = "motion"
    return a


def _local(cat: Catalog, a: str, b: str) -> bool:
    """Two bodies of one local system (a planet and its moon): a departure between them can be followed closely."""
    parent = {w["id"]: w.get("parent") for w in cat.base_world + [x for d in cat.index.datasets.values() for x in d.world]}
    return parent.get(a) == b or parent.get(b) == a


def _orbit_radius(g: Dict[str, Any], R: float) -> Optional[float]:
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
