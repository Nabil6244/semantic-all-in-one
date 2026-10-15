"""The last step before Hybrid's checks: whatever is still wrong in the plan is repaired, so the video never stops on it.

Every repair before this one (weather.autofix) fixes what an AI-written CSV gets wrong. This pass works on the finished plan and
answers each of Hybrid's own checks (hybrid.plan.validate_plan) with a repair, so a plan that reaches it always passes them:

    beats out of order, gaps, overlaps, zero-length beats      re-timed, end to end, over the whole narration
    a beat id used twice                                       renamed
    an unknown mode or transition                              map / dissolve
    a footage beat with no clip (or a clip from no source)     stock footage of what is being said, else a map beat
    a footage beat holding map moves, layers or cards          they are left out (footage covers them)
    a map beat holding clips                                    footage beat when it has nothing else, else the clips go
    no camera 'start', or several                              exactly one, on the first map beat
    a camera move that is unknown, has no place or does not fit  renamed (zoom -> push_in), fitted, or left out
    a layer that is unknown, duplicated, outside its beat or incomplete  renamed, moved to its beat, or left out
    a frame the map does not know ('city')                     the nearest one it does ('local')
Each repair is a note. Nothing here invents data: a number, place or text is only ever kept or left out."""

from __future__ import annotations

from typing import List

EPS = 1e-6
FRAMES = ("globe", "continental", "country", "region", "local")
FRAME_ALIASES = {"city": "local", "town": "local", "county": "local", "metro": "local", "state": "region", "province": "region",
                 "national": "country", "nation": "country", "world": "globe", "earth": "globe", "continent": "continental",
                 "us": "continental", "usa": "continental"}
MOVE_ALIASES = {"zoom": "push_in", "zoom_in": "push_in", "push": "push_in", "pushin": "push_in", "push in": "push_in",
                "fly": "fly_to", "flyto": "fly_to", "fly to": "fly_to", "pan": "fly_to", "move": "fly_to", "go": "fly_to",
                "zoom_out": "pull_back", "pullback": "pull_back", "pull back": "pull_back", "pull_out": "pull_back", "begin": "start"}
DEFAULT_MOVE_S = {"fly_to": 2.2, "push_in": 8.0, "pull_back": 2.0}


def _frame(value: str) -> str:
    v = " ".join(str(value or "").lower().replace("_", " ").split())
    if not v or v in FRAMES:
        return v
    return FRAME_ALIASES.get(v) or next((f for f in FRAMES if f.startswith(v[:4])), "region")


def _clip_request(beat) -> str:
    from .motion import fallback_request
    from .teamplate.cutaways import request_for

    text = getattr(beat, "narration", "") or ""
    return request_for(text) or fallback_request(text, text) or ""


def make_safe(plan, notes: List[str], *, new_requests: bool = True) -> int:
    """Repair `plan` in place until hybrid.plan.validate_plan finds nothing. Returns how many repairs were made."""
    from hybrid.plan import validate_plan

    before = len(notes)
    for _ in range(4):
        _repair(plan, notes, new_requests)
        _titles_apart(plan, notes)
        if not validate_plan(plan):
            break
    left = validate_plan(plan)
    if left:   # the last resort: each beat a problem still names becomes a plain map beat (always valid)
        _flatten(plan, left, notes)
        _repair(plan, notes, new_requests)
    _compile_fit(plan, notes, new_requests)
    return len(notes) - before


def _compile_fit(plan, notes: List[str], new_requests: bool) -> None:
    """Hybrid's compiler has rules of its own (clip lengths against the dissolves, room for a photo card, a title held after
    footage): compile, repair what it names, and again, until it compiles. Titles are checked on the compiled times."""
    import re

    from hybrid.compile import HybridCompileError, plan_to_rows
    from hybrid.plan import validate_plan

    evened = set()
    for _ in range(12):
        try:
            rows = plan_to_rows(plan)[0]
        except HybridCompileError as exc:
            changed = False
            for msg in exc.problems:
                m = re.search(r"beat (\S+?):", msg)
                b = next((x for x in plan.beats if m and x.id == m.group(1)), None)
                if b is None:
                    continue
                if "would be on screen for only" in msg and len(b.clips) > 1:
                    if b.id not in evened and any(c.dur for c in b.clips):   # first: the clips share the beat evenly
                        evened.add(b.id)
                        for c in b.clips:
                            c.dur = None
                    else:                                                    # then: one clip fewer
                        b.clips.pop()
                    _say(notes, f"beat {b.id}: too many clips for its length, so it shows fewer")
                    changed = True
                elif "no room for its" in msg:
                    b.support, b.more_cards = None, []
                    b.mode = "map"
                    _say(notes, f"beat {b.id}: too short for its photo card, so the card was left out")
                    changed = True
                else:
                    _flatten(plan, [msg], notes)
                    changed = True
            if not changed:
                return
            if validate_plan(plan):
                _repair(plan, notes, new_requests)
            continue
        titles = sorted((r for r in rows if r.layer_type == "hud_title"), key=lambda r: r.t_start)
        clash = next(((a, b) for a, b in zip(titles, titles[1:]) if b.t_start < a.t_end - EPS), None)
        if clash is None:
            return
        a, b = clash
        lay = next((x for beat in plan.beats for x in beat.layers if x.id == a.layer_id), None)
        if lay is None:
            return
        cut = round(b.t_start - 0.1, 3)
        moved = True
        while moved:   # a title whose end falls under footage is held until the map is back: it ends before that run of footage
            moved = False
            for r in rows:
                if r.layer_type == "media_full" and r.t_start - EPS <= cut <= (r.t_end or r.t_start) + 1.0 and r.t_start - 0.05 < cut:
                    cut, moved = round(r.t_start - 0.05, 3), True
        if cut <= lay.t + 0.3:
            for beat in plan.beats:
                beat.layers = [x for x in beat.layers if x is not lay]
            _say(notes, f"layer {lay.id}: title left out (the next title appears straight after it)")
        else:
            lay.until, lay.hold = cut, None
            _say(notes, f"layer {lay.id}: title ends as the next title appears")


def _say(notes: List[str], text: str) -> None:
    if text not in notes:
        notes.append(text)


def _repair(plan, notes: List[str], new_requests: bool = True) -> None:
    from hybrid.plan import CAMERA_ACTIONS, CARD_ANCHORS, LAYER_TYPES, MAX_CARDS, MODES, TRANSITIONS, UNTIL_WORDS, asset_problem, free_interval

    beats = plan.beats
    if not beats:
        return
    # ---- the beats: ids, modes, order and times ----
    seen = set()
    for b in beats:
        if b.id in seen:
            new = next(f"{b.id}_{k}" for k in range(2, 999) if f"{b.id}_{k}" not in seen)
            _say(notes, f"beat id {b.id!r} was used twice: the second one is now {new!r}")
            b.id = new
        seen.add(b.id)
        if b.mode not in MODES:
            m = str(b.mode or "").strip().lower()
            b.mode = m if m in MODES else ("footage" if b.clips and not (b.camera or b.layers) else "map")
            _say(notes, f"beat {b.id}: its mode is now {b.mode}")
        if b.transition not in TRANSITIONS:
            b.transition = "dissolve"
    beats.sort(key=lambda b: b.start)
    if plan.duration <= 0:
        plan.duration = max(b.end for b in beats)
    kept = []
    for b in beats:   # end to end: each beat starts where the last one ended; a beat with no time left is folded into the one before
        start = kept[-1].end if kept else 0.0
        if b.end <= start + 0.2 and kept:
            _say(notes, f"beat {b.id}: it had no time of its own (its words come too soon), so it is part of beat {kept[-1].id}")
            continue
        if abs(b.start - start) > 1e-3:
            b.start = start
        kept.append(b)
    for a, nxt in zip(kept, kept[1:]):
        a.end = nxt.start
    kept[-1].end = plan.duration
    if kept[-1].end <= kept[-1].start + EPS and len(kept) > 1:
        kept[-2].end = plan.duration
        kept.pop()
    plan.beats = beats = kept
    # ---- each beat ----
    layer_ids = set()
    for i, b in enumerate(beats):
        b.cam_frame = _frame(b.cam_frame)
        if b.mode == "footage":
            if b.camera or b.layers or b.support or b.more_cards:
                b.camera, b.layers, b.support, b.more_cards = [], [], None, []
                _say(notes, f"beat {b.id}: map moves, layers and cards under full-screen footage were left out (they would not be seen)")
            good = [c for c in b.clips if not asset_problem(c.asset)]
            if len(good) < len(b.clips):
                _say(notes, f"beat {b.id}: {len(b.clips) - len(good)} clip(s) with no usable source were left out")
            b.clips = good
            if not b.clips:
                want = _clip_request(b) if new_requests else ""
                if want:
                    from hybrid.plan import Clip

                    b.clips = [Clip(asset=f"stock_video:{want}", reason="footage beat with no clip (weather.guard)")]
                    _say(notes, f"beat {b.id}: a footage beat with no clip shows stock footage of {want!r}")
                else:
                    b.mode = "map"
                    _say(notes, f"beat {b.id}: a footage beat with no clip stays on the map")
            continue
        if b.clips:
            if not (b.camera or b.layers or b.cards):
                b.mode = "footage"
                b.clips = [c for c in b.clips if not asset_problem(c.asset)]
                if not b.clips:
                    b.mode = "map"
                _say(notes, f"beat {b.id}: a map beat with only clips is a footage beat")
                continue
            b.clips = []
            _say(notes, f"beat {b.id}: clips on a map beat were left out (the map has things to show there)")
        if b.mode == "map" and b.cards:
            b.mode = "map_footage"
        if b.mode == "map_footage":
            cards = [c for c in b.cards if not asset_problem(c.asset)][:MAX_CARDS]
            for c in cards:
                if c.t is not None and not (b.start - EPS <= c.t < b.end - EPS):
                    c.t = None
                if c.anchor and c.anchor not in CARD_ANCHORS:
                    c.anchor = ""
            b.support, b.more_cards = (cards[0], cards[1:]) if cards else (None, [])
            if b.support is None:
                b.mode = "map"
        # camera
        lo, hi = free_interval(plan, i)
        cams = []
        for c in b.camera:
            act = str(c.action or "").strip().lower()
            act = act if act in CAMERA_ACTIONS else MOVE_ALIASES.get(act.replace("-", "_"), MOVE_ALIASES.get(act, ""))
            if not act:
                _say(notes, f"beat {b.id}: camera move {c.action!r} is not one the map makes, so it was left out")
                continue
            c.action = act
            c.frame = _frame(c.frame)
            if act in ("start", "fly_to") and not c.place:
                _say(notes, f"beat {b.id}: camera {act} with no place was left out")
                continue
            if act != "start":
                dur = c.dur if c.dur is not None and c.dur > 0 else DEFAULT_MOVE_S[act]
                room = hi - lo
                if room < 0.3:
                    _say(notes, f"beat {b.id}: camera {act} was left out (no time clear of footage in this beat)")
                    continue
                if dur > room:
                    dur = room
                c.dur = round(dur, 3)
                c.t = round(min(max(c.t, lo), hi - dur), 3)
            cams.append(c)
        b.camera = cams
        # layers
        lays = []
        for lay in b.layers:
            if lay.type not in LAYER_TYPES:
                _say(notes, f"layer {lay.id}: {lay.type!r} is not a map layer, so it was left out")
                continue
            if lay.id in layer_ids:
                new = next(f"{lay.id}_{k}" for k in range(2, 999) if f"{lay.id}_{k}" not in layer_ids)
                _say(notes, f"layer id {lay.id!r} was used twice: the second one is now {new!r}")
                lay.id = new
            if not (b.start - EPS <= lay.t < b.end - EPS):
                lay.t = b.start
            u = lay.until
            if not (isinstance(u, (int, float)) or u in UNTIL_WORDS) or (isinstance(u, (int, float)) and u <= lay.t):
                lay.until = "beat_end"
            if lay.hold is not None and lay.hold <= 0:
                lay.hold = None
            need = {"hud_title": lay.label, "marker": lay.place and lay.label, "zone_label": lay.place and lay.label, "fill": lay.place,
                    "line": len(lay.places) >= 2 and lay.kind, "stat": lay.value_to is not None, "caption": lay.text}[lay.type]
            if not need:
                _say(notes, f"layer {lay.id}: a {lay.type} with something missing was left out")
                continue
            layer_ids.add(lay.id)
            lays.append(lay)
        b.layers = lays
    # ---- exactly one opening camera, on the first map beat ----
    starts = [(b, c) for b in beats for c in b.camera if c.action == "start"]
    maps = [b for b in beats if b.mode != "footage"]
    if not maps:   # all footage: Hybrid still needs the map's opening camera, so the first 1.5 s open on the map
        from hybrid.plan import Beat

        first = beats[0]
        cut = round(first.start + min(1.5, (first.end - first.start) / 2), 3)
        opener = Beat(id=f"{first.id}_map", mode="map", start=first.start, end=cut, narration=first.narration, purpose="opening map (weather.guard)")
        first.start = cut
        beats.insert(0, opener)
        maps = [opener]
        _say(notes, "the plan had no map at all: the video opens on the map for 1.5 s (the map needs an opening camera)")
    if not starts:
        from hybrid.plan import CameraStep

        place = next((c.place for b in beats for c in b.camera if c.place), "") or next((b.cam_place for b in beats if b.cam_place), "")
        maps[0].camera.insert(0, CameraStep(action="start", place=place or "38.5,-97.5", frame="region" if place else "continental",
                                            t=maps[0].start))
        _say(notes, f"beat {maps[0].id}: the map had no opening camera, so it opens on {place or 'the whole country'}")
    elif len(starts) > 1:
        for b, c in starts[1:]:
            c.action = "fly_to"
            c.dur = DEFAULT_MOVE_S["fly_to"]
        _say(notes, f"the plan had {len(starts)} opening cameras: the later ones are camera moves")
        _repair_moves_fit(plan)


def _titles_apart(plan, notes: List[str]) -> None:
    """One title on screen at a time (the renderer refuses two): a title ends just before the next one appears."""
    titles = sorted(((b, lay) for b in plan.beats for lay in b.layers if lay.type == "hud_title"), key=lambda x: x[1].t)
    drop = []
    for (b, lay), (_b2, nxt) in zip(titles, titles[1:]):
        if lay.hold:
            end = lay.t + lay.hold
        elif isinstance(lay.until, (int, float)):
            end = float(lay.until)
        elif lay.until == "beat_end":
            end = b.end
        else:   # "end" / "after_footage": later than any title that follows
            end = plan.duration
        if nxt.t < end - EPS:
            cut = round(nxt.t - 0.05, 3)
            if cut <= lay.t + 0.3:
                drop.append(lay)
                _say(notes, f"layer {lay.id}: title left out (the next title {nxt.id} appears straight after it)")
            else:
                lay.until, lay.hold = cut, None
                _say(notes, f"layer {lay.id}: title ends as the next title ({nxt.id}) appears")
    for b in plan.beats:
        b.layers = [x for x in b.layers if not any(x is d for d in drop)]


def _repair_moves_fit(plan) -> None:
    from hybrid.plan import free_interval

    for i, b in enumerate(plan.beats):
        if b.mode == "footage":
            continue
        lo, hi = free_interval(plan, i)
        for c in b.camera:
            if c.action != "start" and c.dur:
                c.dur = round(min(c.dur, max(0.3, hi - lo)), 3)
                c.t = round(min(max(c.t, lo), hi - c.dur), 3)


def _flatten(plan, problems: List[str], notes: List[str]) -> None:
    import re

    named = {m for p in problems for m in re.findall(r"beat (\S+?)[:\s]", p)}
    for b in plan.beats:
        if b.id in named:
            keep = [c for c in b.camera if c.action == "start"]
            b.mode, b.camera, b.layers, b.clips, b.support, b.more_cards = "map", keep, [], [], None, []
            _say(notes, f"beat {b.id}: it could not be repaired, so it shows the map with nothing on it ({'; '.join(p for p in problems if b.id in p)[:200]})")


def frames_ok(plan, notes: List[str]) -> None:
    """Frames the map does not know (pakMap's compiler refuses them): the nearest it does."""
    for b in plan.beats:
        f = _frame(b.cam_frame)
        if f != b.cam_frame:
            b.cam_frame = f
        for c in b.camera:
            c.frame = _frame(c.frame)


def drop_clips(plan, problems: List[str], notes: List[str]) -> int:
    """Clips and cards weather.footage refuses (each problem names its asset): left out; make_safe then fills or reverts the beat."""
    n = 0
    for b in plan.beats:
        def bad(asset) -> bool:
            return any(repr(asset) in p or str(asset) in p for p in problems)

        keep = [c for c in b.clips if not bad(c.asset)]
        n += len(b.clips) - len(keep)
        b.clips = keep
        cards = [c for c in b.cards if not bad(c.asset)]
        if len(cards) != len(b.cards):
            n += len(b.cards) - len(cards)
            b.support, b.more_cards = (cards[0], cards[1:]) if cards else (None, [])
    if n:
        notes.append(f"{n} clip(s) or card(s) Weather may not use were left out: " + "; ".join(problems)[:300])
    return n


def drop_unfound(plan, script_csv, unresolved, notes: List[str]) -> int:
    """After a run in which some clips could not be found (no stock result, a YouTube clip that would not download): those clips are
    left out of the plan, so the next run makes the video with the rest. `unresolved` are the Visual Plan scene numbers the
    generator reported; `script_csv` is the compiled script they were numbered from (hybrid_script.csv)."""
    from pakmap.schema import parse_csv
    from pakmap.sourcing import find_occurrences

    want = {str(n) for n in unresolved}
    gone = {f"{o.kind}:{' '.join(o.prompt.split())}" for o in find_occurrences(parse_csv(script_csv)[0]) if str(o.scene_number) in want}
    if not gone:
        return 0
    norm = lambda a: ":".join(" ".join(x.split()) for x in str(a).split(":", 1))  # noqa: E731
    n = 0
    for b in plan.beats:
        keep = [c for c in b.clips if norm(c.asset) not in gone]
        n += len(b.clips) - len(keep)
        b.clips = keep
        cards = [c for c in b.cards if norm(c.asset) not in gone]
        if len(cards) != len(b.cards):
            n += len(b.cards) - len(cards)
            b.support, b.more_cards = (cards[0], cards[1:]) if cards else (None, [])
    if n:
        notes.append(f"{n} clip(s) could not be found ({'; '.join(sorted(gone))[:300]}): the video is made without them "
                     "(Retry or Change source in the Visual Plan table and Generate again to add them)")
    return n
