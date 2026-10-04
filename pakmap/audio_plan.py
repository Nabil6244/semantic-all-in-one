"""Phase 7: from the compiled pakMap spec to a list of sound cues (no audio is touched here).

    spec events + camera moves + the author's sfx/ambience columns  ->  AudioPlan

Every cue is caused by a visual event the viewer can see (a marker appearing, a card entering, a line being
drawn, a major camera move). Nothing is random, and camera drift/slow push-ins never make a sound on their own.
The plan is a pure function of its inputs: the same spec always gives the same plan.

Restraint, applied in this order to the automatic cues (an explicit `sfx=` in the CSV always plays):
  1. the same sound is not repeated within SAME_SOUND_GAP_S
  2. two cues closer than MIN_GAP_S: the higher priority wins (major > normal), then the earlier one
  3. a normal cue that starts while a major cue is sounding (from just before it to MAJOR_SHADOW_S after) is dropped
  4. at most MAX_PER_WINDOW cues in any WINDOW_S seconds: the latest, lowest-priority ones are dropped
Priority is Narration > major sfx > normal sfx > ambience; the narration part is enforced by the mixer (ducking).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .sounds import (EVENT_SOUND, PRIORITY_AMBIENCE, PRIORITY_MAJOR, PRIORITY_NORMAL, PRIORITY_RANK, SOUNDS, Sound)

SAME_SOUND_GAP_S = 0.6
MIN_GAP_S = 0.35
MAJOR_SHADOW_S = 0.5
MAX_PER_WINDOW = 8
WINDOW_S = 10.0
MAJOR_MOVE_KM = 600.0
MINOR_MOVE_KM = 60.0  # a fly_to at least this far (or this zoom change) gets the soft whoosh at normal priority
MAJOR_MOVE_ZOOM = 1.5
GLOBE_ZOOM = 2.6
ZOOM_SOUND_MIN = 0.9  # a push_in / pull_back that changes the zoom by at least this much gets a soft whoosh
END_MARGIN_S = 0.1
LINE_DRAW_S = 0.9  # pakmap-engine TIMING.lineDraw

CATALOG_PREFIX = "catalog:"
NONE = "none"


def catalog_sound(catalog_id: str, kind: str = "sfx") -> Sound:
    """An explicit `sfx=catalog:<id>` / `ambience=catalog:<id>`: play exactly that library entry."""
    if kind == "ambience":
        return Sound(id=CATALOG_PREFIX + catalog_id, kind="ambience", source=catalog_id, use="explicit", priority=PRIORITY_AMBIENCE,
                     volume=0.06, fade_in=1.0, fade_out=1.2, candidates=((catalog_id, "close"),))
    return Sound(id=CATALOG_PREFIX + catalog_id, kind="sfx", source=catalog_id, use="explicit", volume=0.14, max_s=2.5,
                 candidates=((catalog_id, "close"),))


def sound_for(sound_id: str, kind: str = "sfx") -> Optional[Sound]:
    if sound_id.startswith(CATALOG_PREFIX):
        return catalog_sound(sound_id[len(CATALOG_PREFIX):], kind)
    return SOUNDS.get(sound_id)


@dataclass
class Cue:
    t: float
    sound: str
    reason: str  # why it plays, in words
    source: str  # event id / camera move / csv row
    explicit: bool = False
    priority: str = PRIORITY_NORMAL
    repeat_index: int = 0
    asset: Optional[str] = None  # filled by resolve_assets

    def to_dict(self) -> dict:
        return {"t": round(self.t, 3), "sound": self.sound, "reason": self.reason, "source": self.source, "explicit": self.explicit,
                "priority": self.priority, "asset": self.asset}


@dataclass
class Bed:
    start: float
    end: float
    sound: str
    reason: str
    explicit: bool = True
    asset: Optional[str] = None

    def to_dict(self) -> dict:
        return {"start": round(self.start, 3), "end": round(self.end, 3), "sound": self.sound, "reason": self.reason, "asset": self.asset}


@dataclass
class AudioPlan:
    cues: List[Cue] = field(default_factory=list)
    beds: List[Bed] = field(default_factory=list)
    dropped: List[Tuple[Cue, str]] = field(default_factory=list)  # (cue, why)
    silent: List[Tuple[str, str]] = field(default_factory=list)  # (event, why it makes no sound)
    missing: Dict[str, str] = field(default_factory=dict)  # sound id -> what is missing
    approximate: Dict[str, str] = field(default_factory=dict)  # sound id -> how it is approximated
    warnings: List[str] = field(default_factory=list)
    enabled: bool = True
    assets: Dict[str, Any] = field(default_factory=dict)  # sound id -> ResolvedAsset (audio_mix.resolve_assets)

    def majors(self) -> List[Tuple[float, float]]:
        out = []
        for c in self.cues:
            s = sound_for(c.sound)
            if c.priority == PRIORITY_MAJOR and s is not None:
                out.append((c.t, c.t + (s.max_s or 1.0)))
        return out

    def to_text(self) -> str:
        if not self.enabled:
            return "Sound design: OFF (narration only)."
        lines = [f"Sound design: {len(self.cues)} effect(s), {len(self.beds)} ambience bed(s), {len(self.dropped)} dropped for restraint."]
        for c in sorted(self.cues, key=lambda c: c.t):
            lines.append(f"  {c.t:6.2f}s  {c.sound:<20} {c.reason}" + ("  [explicit]" if c.explicit else ""))
        for b in self.beds:
            lines.append(f"  {b.start:6.2f}-{b.end:.2f}s  ambience {b.sound}: {b.reason}")
        for c, why in self.dropped:
            lines.append(f"  {c.t:6.2f}s  (dropped {c.sound}: {why})")
        for sid, what in sorted(self.missing.items()):
            lines.append(f"  MISSING {sid}: {what}")
        for w in self.warnings:
            lines.append(f"  note: {w}")
        return "\n".join(lines)


def distance_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    (lo1, la1), (lo2, la2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    d = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(d)))


def _camera_cues(spec: dict, camera_hints: Sequence[dict], plan: AudioPlan) -> List[Cue]:
    cam = spec.get("camera") or {}
    start = cam.get("start") or {}
    pos = (float(start.get("lon", 0)), float(start.get("lat", 0)))
    zoom = float(start.get("zoom", 2))
    override = {round(float(h["t"]), 2): h["sfx"] for h in camera_hints}
    out: List[Cue] = []
    for i, m in enumerate(cam.get("moves") or []):
        to = m.get("to") or {}
        new_pos = (float(to.get("lon", pos[0])), float(to.get("lat", pos[1])))
        new_zoom = float(to.get("zoom", zoom))
        src = f"camera {m.get('type')} at {m['t']:.1f}s"
        forced = override.get(round(float(m["t"]), 2))
        if forced == NONE:
            plan.silent.append((src, "sfx=none"))
        elif forced:
            out.append(Cue(float(m["t"]), forced, "explicit sfx on the camera row", src, explicit=True,
                           priority=(sound_for(forced).priority if sound_for(forced) else PRIORITY_NORMAL)))
        else:
            dz, km = abs(new_zoom - zoom), distance_km(pos, new_pos)
            kind = m.get("type")
            if kind == "drift":
                plan.silent.append((src, "slow camera motion alone makes no sound"))
            elif min(zoom, new_zoom) < GLOBE_ZOOM and dz >= 1.0:
                out.append(Cue(float(m["t"]), "earth_spin", "camera moves to or from a global view", src, priority=PRIORITY_MAJOR))
            elif kind == "fly_to" and (km >= MAJOR_MOVE_KM or dz >= MAJOR_MOVE_ZOOM) or kind == "pull_back" and dz >= MAJOR_MOVE_ZOOM:
                out.append(Cue(float(m["t"]), "map_slide_whoosh", f"major reposition ({km:.0f} km, zoom {dz:+.1f})".replace("+", ""), src, priority=PRIORITY_MAJOR))
            elif kind == "fly_to" and (km >= MINOR_MOVE_KM or dz >= ZOOM_SOUND_MIN):
                out.append(Cue(float(m["t"]), "map_slide_whoosh", f"the camera pans {km:.0f} km (zoom {dz:.1f})", src, priority=PRIORITY_NORMAL))
            elif kind in ("push_in", "pull_back") and dz >= ZOOM_SOUND_MIN:
                out.append(Cue(float(m["t"]), "map_slide_whoosh", f"zoom {'in' if new_zoom > zoom else 'out'} by {dz:.1f} levels", src, priority=PRIORITY_NORMAL))
            else:
                plan.silent.append((src, f"minor move ({km:.0f} km, zoom change {dz:.1f}): no sound"))
        pos, zoom = new_pos, new_zoom
    return out


def _event_cue(ev: dict, forced: Optional[str]) -> Tuple[List[Cue], Optional[str]]:
    """Returns (cues, why_silent). Most events make one cue; a drawn reference line makes two (zap, then ding)."""
    eid, t = ev["id"], float(ev["t_in"])
    typ = ev["type"]
    if forced == NONE:
        return [], "sfx=none"
    if forced:
        s = sound_for(forced)
        return [Cue(t, forced, "explicit sfx on the row", eid, explicit=True, priority=s.priority if s else PRIORITY_NORMAL)], None
    if typ == "hud_title":
        return [Cue(t, "deep_thud", "a title lands", eid)], None
    if typ == "marker":
        if ev.get("dot") is False:
            return [], "a text label alone makes no sound"
        return [Cue(t, "marker_pop", "marker appears", eid)], None
    if typ == "stat":
        return [Cue(t, "counter_ticks", "a counter runs up", eid)], None
    if typ == "line":
        cues = [Cue(t, "draw_zap", f"a {ev.get('kind')} line is drawn", eid)]
        if ev.get("kind") == "reference":
            cues.append(Cue(t + LINE_DRAW_S, "equator_ding", "the reference line finishes drawing", eid))
        return cues, None
    if typ in ("fill", "dots", "cluster"):
        return [Cue(t, "bubble_pluck", {"fill": "a region fills", "dots": "dots appear", "cluster": "dots appear"}[typ], eid)], None
    if typ in ("pip", "filmstrip"):
        return [Cue(t, "ui_click", "a picture card appears" if typ == "pip" else "a filmstrip appears", eid)], None
    if typ == "ghost_shape":
        return [Cue(t, "paper_slide", "a comparison shape slides on", eid)], None
    if typ == "sticker":
        return [Cue(t, "subtle_pop", "a sticker appears", eid)], None
    if typ == "media_full":
        return [Cue(t, "soft_transition", "full-screen footage dissolves in", eid)], None
    if typ == "streak":
        return [], "its wind is an ambience bed, not an effect"
    return [], f"a {typ} makes no sound by default"


def _restrain(cues: List[Cue], plan: AudioPlan, duration: float) -> List[Cue]:
    """Anti-stacking. Deterministic: cues are processed in (time, priority, order)."""
    order = sorted(range(len(cues)), key=lambda i: (cues[i].t, PRIORITY_RANK[cues[i].priority], i))
    kept: List[Cue] = []

    def drop(c: Cue, why: str) -> None:
        plan.dropped.append((c, why))

    for i in order:
        c = cues[i]
        if c.t > duration - END_MARGIN_S:
            drop(c, "too close to the end of the video")
            continue
        if c.explicit:
            kept.append(c)
            continue
        same = next((k for k in reversed(kept) if k.sound == c.sound and c.t - k.t < SAME_SOUND_GAP_S), None)
        if same is not None:
            drop(c, f"{c.sound} already played {c.t - same.t:.2f}s earlier")
            continue
        near = next((k for k in kept if abs(k.t - c.t) < MIN_GAP_S and PRIORITY_RANK[k.priority] <= PRIORITY_RANK[c.priority]), None)
        if near is not None:
            drop(c, f"too close to {near.sound} ({abs(near.t - c.t):.2f}s)")
            continue
        shadow = next((k for k in kept if k.priority == PRIORITY_MAJOR and k.t - 0.1 <= c.t < k.t + MAJOR_SHADOW_S and k is not c), None)
        if shadow is not None and c.priority != PRIORITY_MAJOR:
            drop(c, f"would sit under the {shadow.sound} at {shadow.t:.1f}s")
            continue
        kept.append(c)
    # a major cue that arrives after a normal one inside its shadow replaces it
    for k in [k for k in kept if k.priority == PRIORITY_MAJOR]:
        for c in [c for c in kept if c is not k and not c.explicit and c.priority != PRIORITY_MAJOR and k.t - 0.1 <= c.t < k.t + MAJOR_SHADOW_S]:
            kept.remove(c)
            drop(c, f"would sit under the {k.sound} at {k.t:.1f}s")
    # density cap
    changed = True
    while changed:
        changed = False
        times = sorted(kept, key=lambda c: c.t)
        for c in times:
            window = [k for k in times if c.t <= k.t < c.t + WINDOW_S]
            if len(window) > MAX_PER_WINDOW:
                victims = sorted((k for k in window if not k.explicit), key=lambda k: (-PRIORITY_RANK[k.priority], -k.t))
                if victims:
                    kept.remove(victims[0])
                    drop(victims[0], f"more than {MAX_PER_WINDOW} effects in {WINDOW_S:.0f}s")
                    changed = True
                    break
    return sorted(kept, key=lambda c: c.t)


def _beds(spec: dict, ambience_hints: Sequence[dict], duration: float, plan: AudioPlan) -> List[Bed]:
    beds: List[Bed] = []
    marks = sorted(ambience_hints, key=lambda h: float(h["t"]))
    for i, h in enumerate(marks):
        if h["ambience"] == NONE:
            continue
        nxt = marks[i + 1]["t"] if i + 1 < len(marks) else duration
        beds.append(Bed(float(h["t"]), min(float(nxt), duration), h["ambience"], "ambience set in the script"))
    # a wind-streak layer carries its own wind, unless an ambience bed is already playing
    for ev in spec.get("events") or []:
        if ev.get("type") != "streak":
            continue
        s, e = float(ev["t_in"]), float(ev["t_out"])
        if any(b.start < e and s < b.end for b in beds):
            plan.silent.append((ev["id"], "an ambience bed is already playing: the wind layer adds no extra sound"))
            continue
        beds.append(Bed(s, e, "rushing_wind", "a wind-flow layer is on screen", explicit=False))
    return sorted(beds, key=lambda b: b.start)


def plan_audio(spec: dict, hints: Optional[dict] = None, *, enabled: bool = True, duration: Optional[float] = None) -> AudioPlan:
    """hints (from the compiler): {"events": {event_id: sfx}, "camera": [{"t", "sfx"}], "cues": [{"t","sfx","source"}],
    "ambience": [{"t","ambience"}]}. enabled=False gives an empty plan (narration only)."""
    plan = AudioPlan(enabled=enabled)
    if not enabled:
        return plan
    hints = hints or {}
    total = float(duration if duration is not None else spec.get("duration", 0))
    forced_by_event = hints.get("events") or {}
    cues: List[Cue] = []
    for ev in spec.get("events") or []:
        made, why = _event_cue(ev, forced_by_event.get(ev["id"]))
        if made:
            cues.extend(made)
        elif why:
            plan.silent.append((ev["id"], why))
    cues += _camera_cues(spec, hints.get("camera") or [], plan)
    for h in hints.get("cues") or []:
        if h["sfx"] == NONE:
            continue
        s = sound_for(h["sfx"])
        cues.append(Cue(float(h["t"]), h["sfx"], "explicit sound row", h.get("source", "sound row"), explicit=True,
                        priority=s.priority if s else PRIORITY_NORMAL))
    plan.cues = _restrain(cues, plan, total)
    plan.beds = _beds(spec, hints.get("ambience") or [], total, plan)
    return plan


def expand(cue: Cue) -> List[Cue]:
    """Composite and rhythmic sounds -> the individual hits the mixer places."""
    s = sound_for(cue.sound)
    if s is None:
        return [cue]
    if s.kind == "composite":
        out = []
        for n, part in enumerate(s.parts):
            ps = SOUNDS[part]
            out.append(Cue(cue.t + 0.12 * n, part, cue.reason, cue.source, cue.explicit, ps.priority))
        return out
    if s.repeat:
        times, gap = s.repeat
        return [Cue(cue.t + gap * n, cue.sound, cue.reason, cue.source, cue.explicit, cue.priority, repeat_index=n) for n in range(times)]
    return [cue]
