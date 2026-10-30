"""Event-based sound effects: a sound only where the narration or the picture shows something happening that the sound library can actually
voice (an impact, machinery, a click, water, fast movement, a moment of tension). It never picks a sound just to fill a silence, and a
sound the library has no entry for is simply not planned (the library has no footsteps or doors, so those events are not planned).

Timing: the trigger word's position in the scene's narration, as a share of the scene, placed in the scene's time (a Hindi transcript
spells words differently from the script, so exact word times are not relied on). Levels: the same ladder as every other planned effect,
scaled per event and capped under the narration. Spacing and density limits keep the mix from getting busy."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import lexicon as L
from .core import TELEMETRY

TASK = "sfx"
MIN_CONFIDENCE = 0.8     # evidence needed before a sound is planned
PICTURE_W = 0.6          # the picture shows the action but the narration says when it happens
MIN_GAP_S = 8.0          # between two event sounds
MAX_PER_MINUTE = 4
MIN_SCENE_S = 1.5
CLEAR_S = 0.6            # distance kept from any other planned effect


def detect_events(text: str, prompt: str) -> List[dict]:
    """[{event, confidence, word_pos}] for the events found in a scene, strongest first. `word_pos` (0..1) = where in the narration the
    trigger word is (0.5 when only the picture shows it)."""
    found = []
    low = (text or "").lower()
    for name, spec in L.EVENTS.items():
        hits = L.find_terms(text, spec["terms"])
        narr = max((w for _t, w, _p in hits), default=0.0)
        pic = max((w for _t, w, _p in L.find_terms(prompt, spec["terms"])), default=0.0) * PICTURE_W
        conf = max(narr, pic)
        if conf < MIN_CONFIDENCE:
            continue
        pos = min(h[2] for h in hits) / max(1, len(low)) if hits else 0.5
        found.append({"event": name, "confidence": round(conf, 2), "word_pos": round(pos, 3)})
    return sorted(found, key=lambda f: (-f["confidence"], f["event"]))


def _pick_entry(catalog: Any, spec: Mapping[str, Any], avoid_ids: Sequence[str]) -> Optional[Any]:
    """The library entry that best voices the event: right category, most matching tags, short enough, not just used. None = no honest match."""
    want = {t.lower() for t in spec["tags"]}
    best, best_key = None, None
    for entry in catalog._by_category.get(spec["category"], []):
        hits = len(want & {t.lower() for t in entry.tags})
        if hits == 0 or not entry.resolved_path(catalog.root).is_file():
            continue
        key = (hits, entry.id not in avoid_ids, -abs(entry.duration - spec["max_s"]), entry.id)
        if best_key is None or key > best_key:
            best, best_key = entry, key
    return best


def plan_event_sfx(aligned_rows: Sequence[Mapping], catalog: Any, *, existing: Sequence[Mapping] = (), base_volume: float = 0.28,
                   sfx_gain_cap: float = 0.48, avoid_ids: Sequence[str] = (), request_factory: Any = None, entry_to_event: Any = None) -> List[dict]:
    """Event sounds for the scenes, as event dicts (same shape as the rest of plan_sfx_events). `existing` = events already planned (text
    ticks, transition whooshes): an event sound keeps CLEAR_S away from them and counts toward the density limit."""
    planned: List[dict] = []
    recent: List[str] = list(avoid_ids)
    times = sorted(float(e.get("start") or 0.0) for e in existing)
    for row in aligned_rows:
        start, end = float(row.get("start_time") or 0.0), float(row.get("end_time") or 0.0)
        dur = end - start
        if dur < MIN_SCENE_S:
            continue
        events = detect_events(str(row.get("script_segment") or ""), str(row.get("prompt") or ""))
        for ev in events[:1]:   # one event sound per scene
            spec = L.EVENTS[ev["event"]]
            entry = _pick_entry(catalog, spec, recent)
            if entry is None:
                continue
            at = start + min(max(ev["word_pos"], 0.05), 0.85) * dur
            near = [t for t in times if abs(t - at) < CLEAR_S]
            if near:
                at = max(start + 0.1, near[0] + CLEAR_S) if near[0] + CLEAR_S < end - 0.3 else None
            if at is None:
                continue
            if any(abs(t - at) < MIN_GAP_S for t in [float(p["start"]) for p in planned]):
                continue
            minute = [p for p in planned if abs(float(p["start"]) - at) < 30.0]
            if len(minute) >= MAX_PER_MINUTE // 2:   # at most 4 a minute: two in any 30 s
                continue
            vol = min(sfx_gain_cap, base_volume * 0.62 * spec["gain"] * (0.85 + 0.15 * min(1.0, ev["confidence"])))
            request = request_factory(spec["category"]) if request_factory else None
            event = entry_to_event(entry, request, start=at, volume=round(vol, 3), scene_number=str(row.get("scene_number") or ""),
                                   play_s=spec["max_s"]) if entry_to_event else {"sfx_id": entry.id, "start": round(at, 3), "volume": round(vol, 3), "scene_number": str(row.get("scene_number") or "")}
            event["event"] = ev["event"]
            event["confidence"] = ev["confidence"]
            event["provenance"] = "rules"
            planned.append(event)
            recent = (recent + [entry.id])[-4:]
            times = sorted(times + [at])
    TELEMETRY.add(TASK, decisions=len(aligned_rows), rules=len(planned))
    return planned
