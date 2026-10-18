"""Repairs that code can make perfectly, so no AI is asked: a caption that is too long, a chip that appears too late to be read, a stat
format that writes the number itself, a wide camera frame outside the opening, and text layers piling up. Each returns whether it changed
anything; the caller validates again afterwards. Nothing here changes a beat's mode, times, words or pictures."""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from .plan import HybridPlan
from .validate import MAX_CAPTION_CHARS, MIN_READABLE_S, Finding


def _beat(plan: HybridPlan, bid: str):
    return next((b for b in plan.beats if b.id == bid), None)


def _shorten(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-—")
    return cut if len(cut) >= limit // 2 else text[:limit].rstrip()


def _widen_camera(b) -> str:
    """A map beat whose markers fall outside the camera's picture: look at a place that holds them all. A frame only scales to the
    place's own size (a small county stays small at any frame), so the candidates are the same place at wider frames, then the
    country around it. Returns what was done, or "" when nothing holds every marker (the repair pass gets it then)."""
    from pakmap.geo import GeoError

    from .geo import resolve
    from .validate import labels_outside

    def find(ref, prefer):
        try:
            return resolve(ref, prefer)
        except GeoError as exc:
            return exc

    step = next((c for c in reversed(b.camera) if c.place), None)
    loc = find(step.place, "area") if step else None
    if step is None or isinstance(loc, GeoError):
        return ""
    order = ("region", "country", "continental")
    start = order.index(step.frame) + 1 if step.frame in order else 1
    candidates = [(step.place, fr) for fr in order[start:-1]]
    if loc.iso:
        country = find(loc.iso, "area")
        if not isinstance(country, GeoError) and country.name != loc.name:
            candidates += [(country.name, fr) for fr in ("region", "country")]
    for place, frame in candidates:
        target = find(place, "area")
        if isinstance(target, GeoError) or labels_outside(b, target, frame, find):
            continue
        old = f"{step.place} ({step.frame or 'region'})"
        for c in b.camera:
            if c.place == step.place:
                c.place, c.frame = place, frame
        if b.cam_place:
            b.cam_place, b.cam_frame = place, frame
        return f"{b.id}: widened the camera from {old} to {place} ({frame}) so every marker is in view"
    return ""


def clamp_layers(plan: HybridPlan) -> List[str]:
    """The safety net behind the import: a layer timed BEFORE its map beat (its words are spoken in the beat before) appears with its beat instead of
    stopping the plan from compiling. Nothing else moves: a layer after its beat's end is a wrong beat, which only a person can decide, so it stays
    and the compile error names it. Idempotent: a second run finds nothing to move."""
    done: List[str] = []
    for b in plan.beats:
        for l in b.layers:
            if l.t < b.start - 1e-6:
                old, l.t = l.t, round(b.start, 3)
                done.append(f"{b.id}: {l.type} {l.id} is timed at {old:g}s, before its beat starts; it now appears with the beat at {l.t:g}s")
    return done


def fix(plan: HybridPlan, findings: Sequence[Finding]) -> Tuple[int, List[str]]:
    """Apply every deterministic repair the findings call for. Returns (how many fixes, what was done)."""
    from .compile import layer_end

    done: List[str] = []
    recamera = False
    for f in findings:
        b = _beat(plan, f.beat) if f.beat else None
        if b is None:
            continue
        if f.code == "text_too_long":
            for l in b.layers:
                if l.type == "caption" and len((l.text or "").strip()) > MAX_CAPTION_CHARS:
                    l.text = _shorten(l.text, MAX_CAPTION_CHARS)
                    done.append(f"{b.id}: shortened a caption to fit the screen")
        elif f.code == "stat_format":
            for l in b.layers:
                if l.type != "stat" or l.value_to is None:
                    continue
                m = re.match(r"^\s*(\d[\d,]*(?:\.\d+)?)\s*(.*)$", l.format or "")
                if m and abs(float(m.group(1).replace(",", "")) - l.value_to) <= max(1.0, abs(l.value_to) * 0.01):
                    l.format = ("#,##0 " if float(l.value_to).is_integer() else "0.0 ") + m.group(2).strip()
                    l.format = l.format.strip()
                    done.append(f"{b.id}: wrote the number format as a pattern")
        elif f.code == "layer_late":
            for l in b.layers:
                if l.type in ("stat", "caption", "hud_title"):
                    end = layer_end(plan, b, l)
                    if end - l.t < MIN_READABLE_S and end - (MIN_READABLE_S + 0.2) >= b.start:
                        l.t = round(end - (MIN_READABLE_S + 0.2), 2)
                        done.append(f"{b.id}: moved a {l.type} earlier so it can be read")
        elif f.code == "wide_view":
            if b.cam_frame in ("globe", "continental"):
                b.cam_frame = "region"
                recamera = True
                done.append(f"{b.id}: closed a wide camera view to region")
        elif f.code == "out_of_frame":
            msg = _widen_camera(b)
            if msg:
                recamera = True
                done.append(msg)
        elif f.code == "overlay_conflict" and "text layers" in f.message:
            # too much text at once: let the oldest layer that was being carried forward leave with its own beat
            carried = sorted((l.t, bb, l) for bb in plan.beats for l in bb.layers if l.until in ("after_footage", "end") and l.hold is None and l.t < b.start)
            if carried:
                _, bb, l = carried[0]
                l.until = "beat_end"
                done.append(f"{bb.id}: a carried-over {l.type} now leaves with its own beat")
    if recamera:
        from .director import derive_cameras

        derive_cameras(plan)
    return len(done), done
