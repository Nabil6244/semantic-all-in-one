"""Check plan: read a StarMap beat CSV against the narration and report, without rendering.

    errors    stop the render: the CSV itself (a bad column, a phrase the narrator never says, an unknown or ambiguous place,
              event, craft or dataset, a status the data contradicts, a date past a dataset's data), beats that do not fit
              together, a footage clip under 2 s
    detected  the datasets the CSV uses, found automatically (nothing is selected): status, years, geometry, freshness, beats
    warnings  never block: the rhythm (footage share, a long still map, nothing new for a while), crowding (stat chips,
              cards in the same place), very short or long footage
    notes     what the loader adjusted (a row spoken outside its beat, a near-miss word match)
    to find   pictures and clips named by description that the Visual Plan still has to find
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .beat_csv import Plan, PlanError, read_plan
from .catalog import Catalog, CatalogError
from .compile import CompileError, Compiled, compile_plan

FOOTAGE_SHARE = (0.25, 0.45)
MAX_STILL_MAP_S = 25.0        # a map stretch with no card and no footage
MAX_QUIET_S = 6.0             # map time with nothing new appearing
MIN_CLIP_S, SHORT_CLIP_S, LONG_FOOTAGE_S = 2.0, 3.5, 14.0
REPEAT_SHOTS = 4              # map beats in a row on the same place and frame: the camera has nowhere to go
SAME_SHOT_SHARE = 0.40        # one place+frame holding this much of the map time


@dataclass
class Report:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    to_find: List[Tuple[int, str]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    detected: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    jumps: List[str] = field(default_factory=list)
    plan: Optional[Plan] = None
    compiled: Optional[Compiled] = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_text(self) -> str:
        out: List[str] = []
        s = self.summary
        if s:
            out.append(f"{s['beats']} beats, {s['duration']:.0f} s: map {s['map_s']:.0f} s, footage {s['footage_s']:.0f} s "
                       f"({s['footage_share'] * 100:.0f}%), {s['cards']} photo cards, {s['clips']} clips, {s['layers']} map layers"
                       )
        if self.detected:
            out.append("Detected (found from the CSV, nothing to select):")
            out += self.detected
        elif s:
            out.append("Detected: no mission data (the sky, the planets and the stars only)")
        if self.jumps:
            out.append("Time jumps: " + "; ".join(self.jumps))
        if self.actions:
            out.append("Visual actions:")
            out += self.actions
        out += [f"ERROR {e}" for e in self.errors]
        out += [f"WARNING {w}" for w in self.warnings]
        out += [f"NOTE {n}" for n in self.notes]
        if self.to_find:
            out.append(f"TO FIND ({len(self.to_find)}): " + "; ".join(f"row {r}: {a}" for r, a in self.to_find))
        out.append("OK: ready to render" if self.ok and not self.to_find else ("OK once the pictures and clips are found" if self.ok else "NOT READY"))
        return "\n".join(out)


def check_csv(text: str, words: Sequence = (), duration: Optional[float] = None, *, pack: Optional[str] = None,
              media: Optional[Dict[str, Any]] = None, reference_now: Optional[str] = None, catalog: Optional[Catalog] = None) -> Report:
    """`pack` is accepted for old callers and only starts the context (like the plan row's id); `reference_now` is the
    project's saved "now" (the plan row's date wins). `catalog` lets a caller use another dataset library (tests)."""
    rep = Report()
    try:
        plan = read_plan(text, words, duration)
    except PlanError as exc:
        rep.errors = list(exc.problems)
        return rep
    rep.plan = plan
    if pack and not plan.pack:
        plan.pack = pack
    try:
        cat = catalog or Catalog()
    except CatalogError as exc:
        rep.errors.append(str(exc))
        return rep
    from .resolve import resolve

    res = resolve(plan, cat, reference_now=plan.reference_now or reference_now)
    rep.detected = res.detected(cat)
    rep.jumps = [f"{t.a}→{t.b} {t.label}" + (" (under footage)" if t.hidden_by_footage else "") for t in res.transitions if t.kind == "jump"]
    rep.warnings += res.warnings
    try:
        comp = compile_plan(plan, cat, media=media, resolve_media=False, resolution=res)
    except CompileError as exc:
        rep.errors = list(exc.problems)
        rep.notes = list(plan.notes)
        return rep
    rep.detected = res.detected(cat)
    rep.compiled = comp
    rep.notes = comp.notes
    rep.warnings += comp.warnings
    rep.actions = [f"  {bid} → {a.action}" + (f" (asked: {a.asked})" if a.asked != a.action else "") + f": {a.summary}"
                   + (" [narration-paced]" if a.strategy == "motion" else "") for bid, a in comp.actions.items()]
    rep.to_find = comp.needs_media
    _rhythm(plan, comp, rep)
    _shots(plan, cat, rep)
    return rep


def _bodies_named(text: str, cat: Catalog) -> set:
    """Catalog bodies the narration names (by any alias of at least 3 letters)."""
    import re

    low = (text or "").lower()
    return {b for a, b in cat.aliases.items() if len(a) >= 3 and a not in ("galaxy", "the galaxy", "sol")
            and re.search(rf"(?<![\w]){re.escape(a)}(?![\w])", low)}


def _shots(plan: Plan, cat: Catalog, rep: Report) -> None:
    """Warnings about what the camera is pointed at (never errors, never moves the camera):
    * the same shot (place + frame) for REPEAT_SHOTS map beats in a row, or one shot holding most of the map time -- a still
      view is fine while one idea is explained, but a whole stretch of it reads as a stuck camera. Beats marked
      {"hold": true} in `extra` are intentional and not counted;
    * the narration names a moon of the body on screen ("Europa" while the camera shows Jupiter): the subject can be shown
      itself (place=europa, or jupiter+europa). A deliberate context shot says so with {"context": "europa"} in `extra`."""
    W = rep.warnings
    maps = [b for b in plan.beats if b.mode in ("map", "map_footage") and b.place]
    key = lambda b: (b.place.strip().lower(), (b.frame or "").strip().lower())   # noqa: E731
    run: list = []

    def flush() -> None:
        if len(run) >= REPEAT_SHOTS and not all(b.extra.get("hold") for b in run):
            W.append(f"rows {run[0].row}-{run[-1].row}: {len(run)} map beats in a row show the same shot (place={run[0].place}, "
                     f"frame={run[0].frame}); change the view (close / body / system), the place, or use footage")

    for b in maps:
        if run and key(b) != key(run[-1]):
            flush()
            run = []
        run.append(b)
    flush()
    map_s = sum(b.end - b.start for b in maps)
    if map_s >= 60 and len(maps) >= REPEAT_SHOTS:
        held: Dict[Tuple[str, str], float] = {}
        for b in maps:
            held[key(b)] = held.get(key(b), 0.0) + (b.end - b.start)
        (place, frame), s = max(held.items(), key=lambda kv: kv[1])
        if s / map_s > SAME_SHOT_SHARE:
            W.append(f"one shot (place={place}, frame={frame}) is {s / map_s * 100:.0f}% of the map time; vary the view or the place")
    parent = {w["id"]: w.get("parent") for w in cat.world}
    planet = {w["id"] for w in cat.world if w.get("kind") == "body"}     # a moon's PLANET on screen, not the Sun or a galaxy
    for b in maps:
        if b.extra.get("context"):
            continue
        try:
            pl = cat.place(b.place)
        except CatalogError:
            continue
        if pl.kind == "site" or any(L.type in ("craft", "path", "orbit") for L in b.layers):
            continue   # a launch site, or a beat following a spacecraft's path, is about that place or motion, not a moon
        shown = {pl.body, getattr(pl, "other", None)} - {None, ""}
        for nb in sorted(_bodies_named(b.text, cat) - shown):
            if parent.get(nb) in shown & planet:
                W.append(f"row {b.row}: the narration names {nb.upper()} but the camera shows {pl.body.upper()}; use "
                         f"place={nb} (or {parent[nb]}+{nb}), or add {{\"context\": \"{nb}\"}} to extra if the wider view is meant")


def _rhythm(plan: Plan, comp: Compiled, rep: Report) -> None:
    beats, spec = plan.beats, comp.spec
    total = plan.duration
    foot_s = sum(b.end - b.start for b in beats if b.mode == "footage")
    rep.summary = {"beats": len(beats), "duration": total, "map_s": total - foot_s, "footage_s": foot_s, "footage_share": foot_s / total if total else 0,
                   "cards": sum(len(b.cards) for b in beats), "clips": sum(len(b.clips) for b in beats),
                   "layers": sum(len(b.layers) for b in beats), "datasets": spec.get("starmap", {}).get("datasets", [])}
    W = rep.warnings
    share = rep.summary["footage_share"]
    if total >= 60 and not (FOOTAGE_SHARE[0] <= share <= FOOTAGE_SHARE[1]):
        W.append(f"footage is {share * 100:.0f}% of the video (StarMap aims for {FOOTAGE_SHARE[0] * 100:.0f}-{FOOTAGE_SHARE[1] * 100:.0f}%)")
    for e in spec["footage"]:
        d = e["end"] - e["start"]
        if d < MIN_CLIP_S:
            rep.errors.append(f"footage {e['id']}: {d:.1f} s on screen is too short (at least {MIN_CLIP_S:.0f} s a clip)")
        elif d < SHORT_CLIP_S:
            W.append(f"footage {e['id']}: only {d:.1f} s on screen")
    for b in beats:
        d = b.end - b.start
        if b.mode == "footage" and d > LONG_FOOTAGE_S and len(b.clips) == 1:
            W.append(f"row {b.row}: footage beat {b.id} holds one clip for {d:.0f} s (use two or three clips)")
    # a long stretch of map with no picture at all
    run_start = None
    for b in beats + [None]:
        pictured = b is None or b.mode != "map" or bool(b.cards)
        if not pictured and run_start is None:
            run_start = b
        if pictured and run_start is not None:
            end = b.start if b is not None else total
            if end - run_start.start > MAX_STILL_MAP_S:
                W.append(f"row {run_start.row}: {end - run_start.start:.0f} s of map from {run_start.start:.0f}s with no photo card or footage")
            run_start = None
    # nothing new on the map for a while
    news = sorted({round(L["start"], 2) for L in spec["layers"] if "start" in L} | {round(m["t"], 2) for m in spec["camera"]["moves"]}
                  | {round(b.start, 2) for b in beats})
    for b in beats:
        if b.mode == "footage":
            continue
        pts = [b.start] + [t for t in news if b.start < t < b.end] + [b.end]
        gaps = [(a, c) for a, c in zip(pts, pts[1:]) if c - a > MAX_QUIET_S]
        for a, c in gaps:
            W.append(f"row {b.row}: nothing new on the map for {c - a:.0f} s ({a:.0f}-{c:.0f}s in beat {b.id})")
    # crowding: stat chips and cards
    def overlapping(kind: str, key=None):
        Ls = [L for L in spec["layers"] if L["type"] == kind]
        for i, a in enumerate(Ls):
            for c in Ls[i + 1:]:
                if a["start"] < c["end"] and c["start"] < a["end"] and (key is None or key(a) == key(c)):
                    yield a, c
    for a, c in overlapping("stat_chip", key=lambda L: L.get("corner")):
        W.append(f"rows {a['_row']} and {c['_row']}: two stat chips in the same corner at once")
    for a, c in overlapping("photo_card", key=lambda L: (L["x"], L["y"])):
        W.append(f"rows {a['_row']} and {c['_row']}: two photo cards in the same place at once (give them different anchors)")
    for a, c in overlapping("caption"):
        W.append(f"rows {a['_row']} and {c['_row']}: two captions at once")
