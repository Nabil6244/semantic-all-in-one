"""Deterministic validation of a HybridPlan, before any rendering and before the critic.

Errors block rendering. Warnings never do: they are reported (and tell the critic where to look). Each finding names its beat."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from .plan import EPS, HybridPlan, validate_plan

FOOTAGE_MIN_ERROR_S = 2.0      # a footage beat shorter than this cannot be taken in
FOOTAGE_MIN_WARN_S = 3.5       # ... and under this it barely registers
MAP_MIN_WARN_S = 2.5
LONG_MAP_S = 16.0              # a map run this long should change something
LONG_FOOTAGE_S = 18.0          # footage this long with one clip is a still holding the screen
MAX_CAPTION_CHARS = 44         # the engine does not wrap a caption: longer text runs off both edges of the frame
MIN_READABLE_S = 2.5           # a number chip, caption or title needs this long on screen to be read
FIRST_CARD_WARN_S = 15.0      # the first photo card should be on screen by now
QUIET_MAP_WARN_S = 7.0        # a stretch of one map beat with nothing new appearing
BARE_MAP_WARN_S = 20.0        # the map alone for longer than this feels like a slide
SWITCHES_PER_MIN_WARN = 6.0    # visual churn
MIN_SWITCHES_FOR_CHURN = 4


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    code: str
    beat: str  # "" for the whole plan
    message: str

    def to_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code, "beat": self.beat, "message": self.message}

    def __str__(self) -> str:
        return f"{self.severity.upper()}: {self.message}"


def _beat_of(message: str, plan: HybridPlan) -> str:
    m = re.match(r"^(?:beat|layer) ([\w-]+)", message)
    if not m:
        return ""
    token = m.group(1)
    if any(b.id == token for b in plan.beats):
        return token
    for b in plan.beats:
        if any(l.id == token for l in b.layers):
            return b.id
    return ""


def validate(plan: HybridPlan) -> List[Finding]:
    out: List[Finding] = []
    err = lambda code, beat, msg: out.append(Finding("error", code, beat, msg))  # noqa: E731
    warn = lambda code, beat, msg: out.append(Finding("warning", code, beat, msg))  # noqa: E731

    for problem in validate_plan(plan):  # structure, timing, camera, layers, assets
        err("technical", _beat_of(problem, plan), problem)
    if not plan.beats:
        return out

    map_like = [b for b in plan.beats if plan.is_map_mode(b)]
    for i, b in enumerate(plan.beats):
        dur = b.end - b.start
        if b.mode in ("map", "map_footage"):
            targets = [c.place for c in b.camera if c.place] + [l.place for l in b.layers if l.place] + [p for l in b.layers for p in l.places] + ([b.cam_place] if b.cam_place else [])
            if not targets and not b.geo_intent:
                err("map_no_geography", b.id, f"beat {b.id}: a map beat with no place, no layer and no stated geographic intent has no reason to be on the map")
            elif not b.geo_intent:
                warn("map_no_intent", b.id, f"beat {b.id}: no geographic intent is stated (what should the map explain?)")
            elif not b.layers and not any(c.action != "start" for c in b.camera) and i > 0 and plan.beats[i - 1].mode in ("map", "map_footage"):
                prev_targets = {c.place for c in plan.beats[i - 1].camera if c.place}
                if not prev_targets or {c.place for c in b.camera if c.place} <= prev_targets:
                    warn("map_redundant", b.id, f"beat {b.id}: it follows another map beat, adds no layer and moves nowhere: merge it into the previous beat")
            if dur < MAP_MIN_WARN_S and 0 < i < len(plan.beats) - 1:
                warn("map_short", b.id, f"beat {b.id}: a map beat of {dur:.1f}s is too short to read")
            if dur > LONG_MAP_S:
                changes = len(b.layers) + sum(1 for c in b.camera if c.action != "start")
                if changes < 2:
                    warn("map_static", b.id, f"beat {b.id}: {dur:.0f}s on the map with {changes} change(s) will feel static")
        if b.mode == "footage":
            if b.clips and not (b.footage_intent or any(c.reason for c in b.clips)):
                warn("footage_no_intent", b.id, f"beat {b.id}: the footage has no stated purpose (what does the viewer experience that the map cannot show?)")
            if dur < FOOTAGE_MIN_ERROR_S:
                err("footage_too_short", b.id, f"beat {b.id}: {dur:.1f}s of footage is too short to be meaningful (minimum {FOOTAGE_MIN_ERROR_S:g}s)")
            elif dur < FOOTAGE_MIN_WARN_S:
                warn("footage_short", b.id, f"beat {b.id}: {dur:.1f}s of footage barely registers; give it more narration or fold it into a card")
            if dur > LONG_FOOTAGE_S and len(b.clips) < 2:
                warn("footage_long", b.id, f"beat {b.id}: {dur:.0f}s of footage from one clip; use a second clip or return to the map")
        if b.mode == "map_footage" and b.support is not None and not (b.footage_intent or b.support.label):
            warn("support_no_intent", b.id, f"beat {b.id}: the supporting card has no stated purpose")
        if b.confidence is not None and b.confidence < 0.4:
            warn("low_confidence", b.id, f"beat {b.id}: the Director was not confident about this beat ({b.confidence:.2f})")

    # duplicates and repetition
    seen: dict = {}
    for b in plan.beats:
        assets = [c.asset.strip().lower() for c in b.clips] + [card.asset.strip().lower() for card in b.cards]
        for a in assets:
            if a in seen and seen[a] != b.id:
                warn("repeated_footage", b.id, f"beat {b.id}: the same footage ({a[:60]}) is already used in beat {seen[a]}")
            seen.setdefault(a, b.id)
    for prev, cur in zip(plan.beats, plan.beats[1:]):
        if prev.mode == cur.mode == "footage" and prev.footage_intent and prev.footage_intent.strip().lower() == cur.footage_intent.strip().lower():
            warn("duplicate_beat", cur.id, f"beat {cur.id}: it repeats beat {prev.id}'s footage intent; make it one beat")

    # visual churn
    kinds = ["f" if b.mode == "footage" else "m" for b in plan.beats]
    switches = sum(1 for a, b in zip(kinds, kinds[1:]) if a != b)
    minutes = max(plan.duration / 60.0, 1e-6)
    if switches >= MIN_SWITCHES_FOR_CHURN and switches / minutes > SWITCHES_PER_MIN_WARN:
        warn("churn", "", f"{switches} map/footage switches in {plan.duration:.0f}s ({switches / minutes:.1f} per minute): the story will feel cut up; group related narration into longer beats")
    if len(plan.beats) >= 7 and sum(1 for b in plan.beats if b.end - b.start < 5.0) / len(plan.beats) > 0.5:
        warn("churn", "", "more than half of the beats are shorter than 5 seconds: the video changes visual too often")
    if len(map_like) == 0 and len(plan.beats) > 0:
        warn("no_map", "", "the plan never shows the map: that is footage with no geography (use PakMap or Fact Map for that)")
    if all(b.mode != "footage" for b in plan.beats) and not any(b.support for b in plan.beats) and plan.duration > 30:
        warn("no_footage", "", "the plan has no footage at all: the viewer never sees the place, only the map")

    # when does the viewer first see a picture, and how long does the map run bare?
    pic_times = []
    for b in plan.beats:
        if b.mode == "footage":
            pic_times.append((b.start, b.end))
        for card in b.cards:
            t0 = card.t if card.t is not None else min(b.start + 1.0, b.end - 2.0)
            pic_times.append((t0, min(b.end, t0 + (card.hold or 6.0))))
    pic_times.sort()
    card_starts = [(card.t if card.t is not None else min(b.start + 1.0, b.end - 2.0)) for b in plan.beats for card in b.cards]
    if plan.duration > 40 and (not card_starts or min(card_starts) > FIRST_CARD_WARN_S):
        warn("late_first_card", "", f"the first photo card appears at {min(card_starts) if card_starts else plan.duration:.0f}s: open with a card inside the first {FIRST_CARD_WARN_S:.0f} seconds so the picture work starts early")
    cursor = 0.0
    for a, z in pic_times + [(plan.duration, plan.duration)]:
        if a - cursor > BARE_MAP_WARN_S:
            warn("bare_map", "", f"{cursor:.0f}s to {a:.0f}s ({a - cursor:.0f}s) has no photo card or footage: add a card to a beat in that stretch")
        cursor = max(cursor, z)

    # a map that has nothing new for a while, or says the same thing twice, feels still
    seen_fill: Dict[str, str] = {}
    for b in plan.beats:
        for l in b.layers:
            if l.type == "fill" and l.place:
                k = l.place.strip().lower()
                if k in seen_fill and seen_fill[k] != b.id:
                    warn("repeat_fill", b.id, f"beat {b.id}: {l.place} is filled again (beat {seen_fill[k]} already did): fill the specific part the narrator is on, or leave it out")
                seen_fill.setdefault(k, b.id)
        if b.mode != "footage":
            moments = sorted([l.t for l in b.layers] + [c.t for c in b.cards if c.t is not None] + [c.t for c in b.camera if c.action != "start"] + [b.start, b.end])
            for a, z in zip(moments, moments[1:]):
                if z - a > QUIET_MAP_WARN_S and not b.cards:
                    warn("quiet_map", b.id, f"beat {b.id}: {a:.0f}s to {z:.0f}s has nothing new on the map: add a marker, a line, a label, a number or a card there")
                    break
    if plan.duration > 90 and not any(l.type == "line" for b in plan.beats for l in b.layers):
        warn("no_lines", "", "the plan draws no route, river or border line: a flow, a trade route or a boundary mentioned in the story is worth drawing")

    # overlays that cannot coexist (the renderer enforces these; saying so here names the beat)
    from .compile import layer_end

    live = []
    for b in plan.beats:
        for l in b.layers:
            live.append((l.t, layer_end(plan, b, l), l, b))
    for t0, e0, l, b in live:
        if l.type in ("stat", "caption", "hud_title") and e0 - t0 < MIN_READABLE_S:
            warn("layer_late", b.id, f"beat {b.id}: the {l.type} {(l.label or l.text or '').strip()[:30]!r} appears at {t0:.1f}s with only {e0 - t0:.1f}s left before it must go: too short to read; anchor it earlier in the narration or drop it")
        if l.type == "stat":
            m = re.search(r"[#0,]*0(?:\.0+)?", l.format or "#,##0")
            lit = (l.format or "")[: m.start()] + "\x00" + (l.format or "")[m.end():] if m else ""
            if m is None or re.search(r"\d{2,}|\d[,.]?\x00|\x00[,.]?\d", lit):
                err("stat_format", b.id, f"beat {b.id}: the number format {l.format!r} writes the number itself; use a pattern such as '0 MILLION PEOPLE' or '#,##0 KM' (0 stands for the counting number) and put the value in 'to'")
        if l.type == "caption" and len((l.text or "").strip()) > MAX_CAPTION_CHARS:
            warn("text_too_long", b.id, f"beat {b.id}: the caption is {len((l.text or '').strip())} characters ({(l.text or '').strip()[:30]!r}...) and would run off the screen; keep captions under {MAX_CAPTION_CHARS} characters")
        alive = [x for x in live if x[0] <= t0 + EPS < x[1] - EPS]
        if sum(1 for x in alive if x[2].type == "stat") > 2:
            err("overlay_conflict", b.id, f"beat {b.id}: more than 2 stat chips are on screen at {t0:.1f}s; shorten one with hold or until")
        if sum(1 for x in alive if x[2].type == "hud_title") > 1:
            err("overlay_conflict", b.id, f"beat {b.id}: two titles are on screen at {t0:.1f}s")
        text = sum({"hud_title": 2 if x[2].sub else 1, "stat": 1, "caption": 1, "marker": 2 if x[2].sub else 1}.get(x[2].type, 0) for x in alive)
        if text > 5:   # the renderer's own rule: more than 5 text layers at once is refused, so it is an error here too
            err("overlay_conflict", b.id, f"beat {b.id}: {text} text layers are on screen at {t0:.1f}s (the renderer allows 5); shorten one with hold or until")
        labelled = sum(1 for x in alive if x[2].type in ("marker", "zone_label", "caption", "stat", "hud_title"))
        if text <= 5 and labelled > 5:
            warn("overlay_dense", b.id, f"beat {b.id}: {labelled} labelled layers are on screen at {t0:.1f}s; keep the map readable")

    # every place must be one pakMap can locate (and a fill must be an area); coordinates far from the rest of the story are suspect
    from .geo import GeoError, resolve

    cache: dict = {}

    def find(ref: str, prefer: str):
        key = (ref, prefer)
        if key not in cache:
            try:
                cache[key] = resolve(ref, prefer)
            except GeoError as exc:
                cache[key] = exc
        return cache[key]

    located = []
    for b in plan.beats:
        wanted = [(c.place, "area", "camera") for c in b.camera if c.place]
        for l in b.layers:
            if l.type == "fill":
                wanted.append((l.place, "area", "fill"))
            elif l.type in ("marker", "zone_label"):
                wanted.append((l.place, "point", l.type))
            elif l.type == "line":
                wanted += [(p, "point", "line point") for p in l.places]
        for card in b.cards:
            if card.place:
                wanted.append((card.place, "point", "supporting card"))
        for ref, prefer, what in wanted:
            r = find(ref, prefer)
            if isinstance(r, GeoError):
                err("unresolved_place", b.id, f"beat {b.id}: the {what} place {ref!r} cannot be found. Use a country, province or city by its atlas name, or coordinates as \"lat,lon\" for a river, mountain, pass, sea or small town")
            else:
                if what == "fill" and not r.is_area:
                    err("fill_not_area", b.id, f"beat {b.id}: a fill needs an area (country, province, region) but {ref!r} is a point")
                located.append((b.id, ref, r.lat, r.lon))
    if len(located) >= 5:
        import math, statistics

        mlat, mlon = statistics.median(x[2] for x in located), statistics.median(x[3] for x in located)
        for bid, ref, lat, lon in located:
            dx = (lon - mlon) * math.cos(math.radians(mlat)) * 111.0
            dy = (lat - mlat) * 111.0
            if math.hypot(dx, dy) > 1800.0:
                warn("place_outlier", bid, f"beat {bid}: {ref!r} is {math.hypot(dx, dy):.0f} km from the rest of the story's places: check the coordinates (latitude first)")

    # everything a map beat labels must be inside the frame the camera ends up with (a marker the viewer cannot see is a defect)
    import math

    from pakmap.geo import view_for

    for b in plan.beats:
        if not plan.is_map_mode(b) or not b.camera:
            continue
        target = next((c for c in reversed(b.camera) if c.place), None)
        if target is None:
            continue
        loc = find(target.place, "area")
        if isinstance(loc, GeoError):
            continue
        frame = target.frame or "region"
        if frame in ("globe", "continental") and not (b.start < EPS and len(b.camera) > 1):
            warn("wide_view", b.id, f"beat {b.id}: the camera stays on the {frame} (globe-like) view for {b.end - b.start:.0f}s; keep that for the first 1-2 seconds and when the story really is planet-wide, otherwise fly to the country or region")
        if frame in ("country", "region") and not loc.is_area and re.fullmatch(r"\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*", target.place or ""):
            warn("point_zoom", b.id, f"beat {b.id}: {target.place!r} is a coordinate, so the camera shows it at street-level zoom whatever the frame; name the country or region (for example 'Niger', 'Sahel') to get a proper {frame} view")
        lon, lat, zoom = view_for(loc, frame)
        half_w = 40075.0 * math.cos(math.radians(lat)) / (512.0 * 2 ** zoom) * 1920.0 / 2.0
        half_h = half_w * 9.0 / 16.0
        out_of_frame = []
        for l in b.layers:
            if l.type not in ("marker", "zone_label"):
                continue
            r = find(l.place, "point")
            if isinstance(r, GeoError):
                continue
            dx = (r.lon - lon) * math.cos(math.radians(lat)) * 111.0
            dy = (r.lat - lat) * 111.0
            if abs(dx) > half_w * 0.96 or abs(dy) > half_h * 0.96:
                out_of_frame.append(l.label or l.place)
        if out_of_frame:
            warn("out_of_frame", b.id, f"beat {b.id}: {', '.join(out_of_frame)} would be outside the camera's view of {target.place} (frame {target.frame or 'region'}): widen the frame or move the camera")

    # write the verdict back onto each beat
    for b in plan.beats:
        mine = [f for f in out if f.beat == b.id]
        b.findings = [str(f) for f in mine]
        b.validation = "errors" if any(f.severity == "error" for f in mine) else ("warnings" if mine else "ok")
    return out


def errors(findings: List[Finding]) -> List[Finding]:
    return [f for f in findings if f.severity == "error"]


def warnings(findings: List[Finding]) -> List[Finding]:
    return [f for f in findings if f.severity == "warning"]
