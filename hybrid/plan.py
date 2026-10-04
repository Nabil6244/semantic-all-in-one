"""The Hybrid plan: an ordered, gap-free list of story beats, each MAP or FOOTAGE (H1: hand-authored, no AI).

JSON shape (all times are narration seconds):

    {"version": 1, "duration": 24.0,
     "settings": {"dissolve_s": 0.5, "return_grace_s": 0.8, "pause_overlays": true, "drift_pct_per_s": 0.0},
     "beats": [
       {"id": "b1", "mode": "map", "start": 0, "end": 9, "purpose": "where we are",
        "camera": [{"action": "start", "place": "Kenya", "frame": "country"},
                   {"action": "fly_to", "t": 4, "dur": 2, "place": "Nairobi", "frame": "region"}],
        "layers": [{"id": "nbo", "type": "marker", "t": 3, "place": "Nairobi", "label": "NAIROBI", "until": "after_footage"}]},
       {"id": "b2", "mode": "footage", "start": 9, "end": 15, "purpose": "what it looks like",
        "footage": {"clips": [{"asset": "stock_video:farmers in a field"}, {"asset": "media/market.jpg", "kenburns": true}]}},
       {"id": "b3", "mode": "map", "start": 15, "end": 24, "layers": [...]}]}

A layer lives until: "beat_end" (default), "after_footage" (the end of the next map beat after this one, so it is still there
when the map comes back), "end" (the end of the video), a number of seconds, or `hold` seconds after it appears."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

MODES = ("map", "footage", "map_footage")  # map_footage: a map beat with a supporting photo card (the map says where, the card shows what)
SOURCES = ("stock_image", "stock_video", "flow_image", "flow_video", "youtube_video")
TRANSITIONS = ("dissolve",)
LAYER_TYPES = ("hud_title", "marker", "zone_label", "fill", "line", "stat", "caption")
CAMERA_ACTIONS = ("start", "fly_to", "push_in", "pull_back")
UNTIL_WORDS = ("beat_end", "after_footage", "end")
EPS = 1e-6

DEFAULT_SETTINGS = {
    "dissolve_s": 0.5,          # map <-> footage and clip <-> clip dissolves
    "return_grace_s": 0.8,      # a layer whose planned end fell under footage is held this long after the map returns, then leaves
    "pause_overlays": True,     # freeze the map layers' animations under footage and resume them on return
    "globe_hop_km": 1800,       # a camera jump at least this long pulls out to the globe and back in
    "globe_opening": True,      # a Director-made plan opens on the whole planet for ~1.4 s, then flies in and stays close
    "cover_ui": True,           # footage covers chips, cards, captions and the title
    "drift_pct_per_s": 0.5,     # the always-on camera drift (the same default as pakMap)
    "dissolve_centered": True,  # the dissolve is centred on the beat boundary, so it does not eat the footage beat's own time
}


class PlanError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Layer:
    id: str
    type: str
    t: float
    place: str = ""
    places: List[str] = field(default_factory=list)  # a line's waypoints
    label: str = ""
    sub: str = ""
    text: str = ""
    role: str = ""
    kind: str = ""  # a line's kind
    value_from: Optional[float] = None
    value_to: Optional[float] = None
    format: str = ""
    anchor: str = ""
    until: Any = "beat_end"
    hold: Optional[float] = None
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CameraStep:
    action: str
    place: str = ""
    frame: str = ""
    t: float = 0.0
    dur: Optional[float] = None
    zoom_delta: Optional[float] = None


@dataclass
class Clip:
    asset: str  # a file, or a source reference such as stock_video:farmers in a field
    dur: Optional[float] = None
    kenburns: bool = False
    loop: bool = False
    reason: str = ""  # why this picture: what it shows that the map cannot


@dataclass
class Support:
    """A map_footage beat's supporting photo card."""
    asset: str
    t: Optional[float] = None  # when it appears (default: a little after the beat starts)
    place: str = ""  # draws a leader line to this place
    label: str = ""
    hold: Optional[float] = None


@dataclass
class Beat:
    id: str
    mode: str
    start: float
    end: float
    purpose: str = ""
    narration: str = ""
    camera: List[CameraStep] = field(default_factory=list)
    layers: List[Layer] = field(default_factory=list)
    clips: List[Clip] = field(default_factory=list)
    support: Optional[Support] = None
    # the editorial record of the beat (what the Director decided and why)
    geo_intent: str = ""        # map beats: what the map explains
    footage_intent: str = ""    # footage beats: what the viewer should experience
    overlay_intent: str = ""    # map beats: which overlays and why
    transition: str = "dissolve"
    keep_overlays: bool = False  # footage draws UNDER the chips, cards and title instead of over them
    transition_sound: str = ""  # a sound id for the entry into this footage beat; empty = no sound
    confidence: float = 1.0
    validation: str = ""        # "", "ok", "warnings" or "errors" (set by the validator)
    findings: List[str] = field(default_factory=list)
    cam_place: str = ""        # the place the camera should be looking at during this map beat (the Director's target; camera steps are derived from it)
    cam_frame: str = ""
    cam_move: str = ""
    chapter: int = 0            # long-form: the planning chapter this beat belongs to (0 = the plan has no chapters)


@dataclass
class HybridPlan:
    duration: float
    beats: List[Beat]
    settings: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    chapters: List[Dict[str, Any]] = field(default_factory=list)  # long-form: [{"id": 1, "title": "...", "start": s, "end": s}], in order

    def setting(self, key: str) -> Any:
        return {**DEFAULT_SETTINGS, **self.settings}[key]

    def footage_windows(self) -> List["tuple[float, float]"]:
        """When footage is on screen, dissolves included. A centred dissolve starts half a dissolve before the beat and ends half after,
        so the footage is fully visible for (almost) the whole beat; where the footage meets the video's start or end there is no half."""
        half = float(self.setting("dissolve_s")) / 2 if self.setting("dissolve_centered") else 0.0
        out = []
        for b in self.beats:
            if b.mode == "footage":
                out.append((max(0.0, b.start - half) if b.start > EPS else b.start, min(self.duration, b.end + half) if b.end < self.duration - EPS else b.end))
        return out

    def is_map_mode(self, beat: "Beat") -> bool:
        return beat.mode in ("map", "map_footage")

    def beat_at(self, t: float) -> Optional[Beat]:
        for b in self.beats:
            if b.start - EPS <= t < b.end - EPS:
                return b
        return None

    # ---- JSON -----------------------------------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "HybridPlan":
        problems: List[str] = []
        if not isinstance(data, dict):
            raise PlanError(["the plan must be a JSON object"])
        known = {"version", "duration", "settings", "beats", "chapters"}
        for k in data:
            if k not in known:
                problems.append(f"unknown plan field {k!r}")
        beats = []
        for i, raw in enumerate(data.get("beats") or []):
            try:
                beats.append(_beat(raw))
            except (KeyError, TypeError, ValueError) as exc:
                problems.append(f"beat {i + 1}: {exc.args[0] if exc.args else exc}")
        if problems:
            raise PlanError(problems)
        try:
            duration = float(data["duration"])
        except (KeyError, TypeError, ValueError):
            raise PlanError(["the plan needs a duration in seconds"])
        return cls(duration=duration, beats=beats, settings=dict(data.get("settings") or {}), version=int(data.get("version", 1)),
                   chapters=[dict(c) for c in data.get("chapters") or [] if isinstance(c, dict)])

    @classmethod
    def load(cls, path: "str | Path") -> "HybridPlan":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items() if v not in (None, "", [], {}) and not (k in ("kenburns", "loop") and v is False)}
            if isinstance(o, list):
                return [clean(v) for v in o]
            return o

        from dataclasses import asdict

        d = asdict(self)
        d["beats"] = [{k: v for k, v in b.items() if k != "clips"} | ({"footage": {"clips": b["clips"]}} if b["mode"] == "footage" else {}) for b in d["beats"]]
        for b in d["beats"]:
            if b.get("transition") == "dissolve":
                b.pop("transition")
            if b.get("confidence") == 1.0:
                b.pop("confidence")
            if b.get("keep_overlays") is False:
                b.pop("keep_overlays", None)
            if not b.get("chapter"):
                b.pop("chapter", None)
        for b in d["beats"]:
            for lay in b.get("layers", []):
                if lay.get("until") == "beat_end":
                    lay.pop("until")
                for ours, theirs in (("value_from", "from"), ("value_to", "to")):  # the JSON names
                    if ours in lay:
                        lay[theirs] = lay.pop(ours)
        return clean(d)

    def save(self, path: "str | Path") -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def _beat(raw: dict) -> Beat:
    if raw.get("mode") not in MODES:
        raise ValueError(f"mode must be 'map' or 'footage' (got {raw.get('mode')!r})")
    b = Beat(id=str(raw["id"]), mode=raw["mode"], start=float(raw["start"]), end=float(raw["end"]), purpose=str(raw.get("purpose", "")), narration=str(raw.get("narration", "")),
             geo_intent=str(raw.get("geo_intent", "")), footage_intent=str(raw.get("footage_intent", "")), overlay_intent=str(raw.get("overlay_intent", "")),
             transition=str(raw.get("transition", "dissolve")), keep_overlays=bool(raw.get("keep_overlays", False)), transition_sound=str(raw.get("transition_sound", "")),
             confidence=float(raw.get("confidence", 1.0)), validation=str(raw.get("validation", "")), findings=[str(x) for x in raw.get("findings") or []],
             cam_place=str(raw.get("cam_place", "")), cam_frame=str(raw.get("cam_frame", "")), cam_move=str(raw.get("cam_move", "")), chapter=int(raw.get("chapter", 0) or 0))
    if raw.get("support"):
        sp = raw["support"]
        b.support = Support(asset=str(sp["asset"]), t=None if sp.get("t") is None else float(sp["t"]), place=str(sp.get("place", "")), label=str(sp.get("label", "")),
                            hold=None if sp.get("hold") is None else float(sp["hold"]))
    for c in raw.get("camera") or []:
        b.camera.append(CameraStep(action=str(c["action"]), place=str(c.get("place", "")), frame=str(c.get("frame", "")), t=float(c.get("t", b.start)),
                                   dur=None if c.get("dur") is None else float(c["dur"]), zoom_delta=None if c.get("zoom_delta") is None else float(c["zoom_delta"])))
    for lay in raw.get("layers") or []:
        b.layers.append(Layer(
            id=str(lay["id"]), type=str(lay["type"]), t=float(lay.get("t", b.start)), place=str(lay.get("place", "")), places=[str(p) for p in lay.get("places") or []],
            label=str(lay.get("label", "")), sub=str(lay.get("sub", "")), text=str(lay.get("text", "")), role=str(lay.get("role", "")), kind=str(lay.get("kind", "")),
            value_from=None if lay.get("from") is None else float(lay["from"]), value_to=None if lay.get("to") is None else float(lay["to"]),
            format=str(lay.get("format", "")), anchor=str(lay.get("anchor", "")), until=lay.get("until", "beat_end"),
            hold=None if lay.get("hold") is None else float(lay["hold"]), params=dict(lay.get("params") or {})))
    for c in (raw.get("footage") or {}).get("clips") or []:
        b.clips.append(Clip(asset=str(c["asset"]), dur=None if c.get("dur") is None else float(c["dur"]), kenburns=bool(c.get("kenburns", False)), loop=bool(c.get("loop", False)),
                            reason=str(c.get("reason", ""))))
    return b


def asset_problem(asset: str) -> str:
    """'' when `asset` is a file or a supported source reference; otherwise why not."""
    import re

    text = (asset or "").strip()
    if not text:
        return "no asset"
    m = re.match(r"^([A-Za-z_]{3,20}):(?![\\/])(.*)$", text, re.S)
    if m:
        if m.group(1).lower() not in SOURCES:
            return f"unsupported asset type {m.group(1)!r} (use {', '.join(SOURCES)}, or a file)"
        if not m.group(2).strip():
            return f"{m.group(1)} needs a description of what to find"
    elif "|" in text:
        return "one clip per entry: use several clips, not a | list"
    return ""


def free_interval(plan: HybridPlan, i: int) -> "tuple[float, float]":
    """The part of map beat i where the camera may move: not under the footage dissolves on either side."""
    half = float(plan.setting("dissolve_s")) / 2 if plan.setting("dissolve_centered") else 0.0
    d = float(plan.setting("dissolve_s"))
    b = plan.beats[i]
    prev_f = i > 0 and plan.beats[i - 1].mode == "footage"
    next_f = i + 1 < len(plan.beats) and plan.beats[i + 1].mode == "footage"
    lo = b.start + ((half if plan.setting("dissolve_centered") else d) if prev_f else 0.0)
    hi = b.end - ((half if plan.setting("dissolve_centered") else d) if next_f else 0.0)
    return lo, hi


def validate_plan(plan: HybridPlan) -> List[str]:
    """Technical checks that need no place lookup. Returns plain-language problems naming the beat / layer. Every one is an error:
    editorial judgement lives in hybrid.validate (warnings)."""
    out: List[str] = []
    if plan.duration <= 0:
        out.append("the duration must be more than 0")
    if not plan.beats:
        return out + ["the plan has no beats"]
    ids = [b.id for b in plan.beats]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        out.append(f"beat id {dup!r} is used more than once")
    t = 0.0
    for b in plan.beats:
        if b.end <= b.start + EPS:
            out.append(f"beat {b.id}: it ends ({b.end:g}s) before it starts ({b.start:g}s)")
        if abs(b.start - t) > 1e-3:
            out.append(f"beat {b.id}: starts at {b.start:g}s but the previous beat ended at {t:g}s (beats must follow each other with no gap or overlap)")
        t = b.end
        if b.transition not in TRANSITIONS:
            out.append(f"beat {b.id}: transition {b.transition!r} is not supported (use {', '.join(TRANSITIONS)})")
    if abs(t - plan.duration) > 1e-3:
        out.append(f"the beats end at {t:g}s but the plan is {plan.duration:g}s long")
    starts = [(b.id, c) for b in plan.beats for c in b.camera if c.action == "start"]
    if len(starts) != 1:
        out.append("the plan needs exactly one camera 'start' (where the map begins)" + (f"; found {len(starts)}" if starts else ""))
    layer_ids: List[str] = []
    for i, b in enumerate(plan.beats):
        if b.mode == "footage":
            if b.camera or b.layers or b.support:
                out.append(f"beat {b.id}: a footage beat cannot hold map camera moves, layers or a supporting card (they belong to a map beat)")
            if not b.clips:
                out.append(f"beat {b.id}: a footage beat needs at least one clip")
            for k, c in enumerate(b.clips):
                why = asset_problem(c.asset)
                if why:
                    out.append(f"beat {b.id}: clip {k + 1}: {why}")
            continue
        if b.clips:
            out.append(f"beat {b.id}: a map beat cannot hold footage clips")
        if b.mode == "map" and b.support:
            out.append(f"beat {b.id}: a plain map beat has no supporting card (use mode map_footage)")
        if b.mode == "map_footage":
            if b.support is None:
                out.append(f"beat {b.id}: a map_footage beat needs a supporting card (what the footage shows)")
            else:
                why = asset_problem(b.support.asset)
                if why:
                    out.append(f"beat {b.id}: supporting card: {why}")
                if b.support.t is not None and not (b.start - EPS <= b.support.t < b.end - EPS):
                    out.append(f"beat {b.id}: the supporting card appears at {b.support.t:g}s, outside its beat")
        lo, hi = free_interval(plan, i)
        for c in b.camera:
            if c.action not in CAMERA_ACTIONS:
                out.append(f"beat {b.id}: camera action {c.action!r} must be one of {', '.join(CAMERA_ACTIONS)}")
                continue
            if c.action in ("start", "fly_to") and not c.place:
                out.append(f"beat {b.id}: camera {c.action} needs a place")
            if c.action != "start":
                dur = c.dur if c.dur is not None else {"fly_to": 2.2, "push_in": 8.0, "pull_back": 2.0}[c.action]
                if c.t < lo - EPS or c.t + dur > hi + EPS:
                    out.append(f"beat {b.id}: camera {c.action} at {c.t:g}s for {dur:g}s does not fit in the part of the beat that is clear of footage dissolves ({lo:g}-{hi:g}s): the camera cannot move under footage")
        for lay in b.layers:
            if lay.id in layer_ids:
                out.append(f"layer id {lay.id!r} is used more than once")
            layer_ids.append(lay.id)
            if lay.type not in LAYER_TYPES:
                out.append(f"layer {lay.id}: type {lay.type!r} is not supported yet (use {', '.join(LAYER_TYPES)})")
            if not (b.start - EPS <= lay.t < b.end - EPS):
                out.append(f"layer {lay.id}: appears at {lay.t:g}s, outside its map beat {b.id} ({b.start:g}-{b.end:g}s); layers cannot appear under footage")
            u = lay.until
            if not (isinstance(u, (int, float)) or u in UNTIL_WORDS):
                out.append(f"layer {lay.id}: until must be one of {', '.join(UNTIL_WORDS)} or a number of seconds")
            elif isinstance(u, (int, float)) and u <= lay.t:
                out.append(f"layer {lay.id}: until {u:g}s is not after it appears ({lay.t:g}s)")
            if lay.hold is not None and lay.hold <= 0:
                out.append(f"layer {lay.id}: hold must be more than 0")
            need = {"hud_title": lay.label, "marker": lay.place and lay.label, "zone_label": lay.place and lay.label, "fill": lay.place,
                    "line": len(lay.places) >= 2 and lay.kind, "stat": lay.value_to is not None, "caption": lay.text}[lay.type] if lay.type in LAYER_TYPES else True
            if not need:
                out.append(f"layer {lay.id}: a {lay.type} is missing something it needs ({_NEEDS[lay.type]})")
    return out


_NEEDS = {"hud_title": "label", "marker": "place and label", "zone_label": "place and label", "fill": "place", "line": "at least two places and a kind", "stat": "'to'", "caption": "text"}
