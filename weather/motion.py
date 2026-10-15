"""The map never stands still: a Weather map beat that would sit on one frame for more than STILL_S gets slow, bounded camera motion.

A beat written "hold" (or one whose camera already arrived) can leave the same picture on screen for a minute: pakMap's drift
is off for Weather (it carried a two-minute hold from Houston to Mississippi), so nothing moves. This pass finds every stretch of
a map beat where the camera has no move, and fills it with a slow push in, the next one easing back out by the same amount, so the
view breathes but stays on the place the narration is about (the zoom returns to where it was; the centre never moves).

Graphics keep their own timing; this only adds camera steps (hybrid.plan.CameraStep) between the ones the plan already has, never
inside footage dissolves (hybrid.plan.free_interval)."""

from __future__ import annotations

from typing import List, Tuple

STILL_S = 6.0        # a still stretch longer than this gets motion
MOVE_MAX_S = 10.0    # one move lasts at most this long (a longer stretch gets several, alternating)
ZOOM = 0.3           # each push in / pull back (pakMap zoom levels): gentle
MARGIN_S = 0.3


def _busy(beat) -> List[Tuple[float, float]]:
    out = []
    for c in beat.camera:
        if c.action == "start":
            continue
        dur = c.dur if c.dur is not None else {"fly_to": 2.2, "push_in": 8.0, "pull_back": 2.0}.get(c.action, 2.0)
        out.append((c.t, c.t + dur))
    return sorted(out)


def keep_moving(plan, notes: List[str]) -> int:
    """Add camera motion to still stretches of map beats. Returns how many moves were added. The zoom is balanced over the video:
    every push in is answered by a pull back of the same size before the next push in."""
    from hybrid.plan import CameraStep, free_interval

    started = False
    pushed = False   # the last added move zoomed in: the next one eases back
    added = 0
    for i, b in enumerate(plan.beats):
        if any(c.action == "start" for c in b.camera):
            started = True
        if not plan.is_map_mode(b) or not started:
            continue
        lo, hi = free_interval(plan, i)
        gaps, cur = [], lo
        for a, z in _busy(b) + [(hi, hi)]:
            if a - cur > STILL_S:
                gaps.append((cur, a))
            cur = max(cur, z)
        new = []
        for a, z in gaps:
            t = a + MARGIN_S
            while z - MARGIN_S - t > STILL_S * 0.6:
                dur = round(min(MOVE_MAX_S, z - MARGIN_S - t), 2)
                new.append(CameraStep(action="pull_back" if pushed else "push_in", t=round(t, 2), dur=dur, zoom_delta=ZOOM))
                pushed = not pushed
                t += dur
        if new:
            b.camera = sorted(b.camera + new, key=lambda c: (c.action != "start", c.t))
            added += len(new)
    if pushed:   # end where we started: the last push in is answered within its own beat's time if there is room
        for i in range(len(plan.beats) - 1, -1, -1):
            b = plan.beats[i]
            if not plan.is_map_mode(b):
                continue
            lo, hi = free_interval(plan, i)
            end = max((c.t + (c.dur or 2.0) for c in b.camera if c.action != "start"), default=lo)
            if hi - end >= 2.0:
                b.camera.append(CameraStep(action="pull_back", t=round(end + 0.1, 2), dur=round(min(4.0, hi - end - 0.2), 2), zoom_delta=ZOOM))
                added += 1
            break
    if added:
        notes.append(f"{added} slow camera move(s) added where the map would have stood still for more than {STILL_S:g} s")
    return added


MAP_LIMIT = 0.50   # the map is on screen at most half the video; footage fills the rest
# things a camera can film -> what to ask the stock providers for (first ones said win)
FILMABLE = {
    "lakefront": "lakefront homes", "lake": "lake from above", "lakes": "lake from above", "dam": "concrete dam", "dams": "concrete dam",
    "spillway": "dam spillway water", "reservoir": "reservoir water", "river": "river flowing", "rivers": "river flowing",
    "creek": "creek flowing", "stream": "creek flowing", "water": "water surface", "homes": "houses in a neighborhood",
    "houses": "houses in a neighborhood", "house": "house exterior", "neighborhood": "houses in a neighborhood", "town": "small town main street",
    "village": "small town main street", "downtown": "downtown street", "city": "city skyline", "road": "road through the countryside",
    "roads": "road through the countryside", "highway": "highway traffic", "bridge": "bridge over water", "boat": "boats on the water",
    "boats": "boats on the water", "dock": "boat dock", "docks": "boat dock", "marina": "marina boats", "beach": "beach waves",
    "sand": "sand beach", "ocean": "ocean waves", "sea": "ocean waves", "harbor": "harbor", "pier": "pier over the ocean",
    "mountains": "mountains aerial", "mountain": "mountains aerial", "forest": "forest aerial", "trees": "forest aerial",
    "farm": "farm fields", "farms": "farm fields", "crops": "farm fields", "fields": "farm fields", "valley": "valley aerial",
    "officials": "town hall meeting", "council": "town hall meeting", "meeting": "town hall meeting", "mayor": "town hall meeting",
    "workers": "construction workers", "crews": "construction workers", "construction": "construction site", "repair": "construction workers",
    "repairs": "construction workers", "engineers": "engineer inspecting", "engineer": "engineer inspecting", "inspection": "engineer inspecting",
    "inspector": "engineer inspecting", "money": "counting money", "dollars": "counting money", "grants": "documents on a desk",
    "funding": "documents on a desk", "budget": "documents on a desk", "insurance": "insurance paperwork", "school": "school building",
    "hospital": "hospital exterior", "power": "power lines", "outage": "power lines", "traffic": "traffic", "residents": "people walking in town",
    "families": "family at home", "people": "people walking in town", "evacuation": "cars evacuating", "tourists": "tourists walking",
    "tourism": "tourists walking", "visitors": "tourists walking", "sandbags": "sandbags", "pumps": "water pump", "pipes": "pipes",
}


def fallback_request(spoken: str, beat_text: str = ""):
    """A stock request for a stretch whose words name no weather: the filmable things said there ("lakefront homes"), else the
    ones its beat talks about most. None when the stretch talks about the data or names nothing a camera can film."""
    import re
    from collections import Counter

    from .teamplate.cutaways import NOT_WEATHER, SOURCE_WORDS

    said = re.findall(r"[a-z]+", NOT_WEATHER.sub(" ", str(spoken).lower()))
    if set(said) & SOURCE_WORDS:
        return None
    here = list(dict.fromkeys(FILMABLE[w] for w in said if w in FILMABLE))
    if not here:
        counts = Counter(FILMABLE[w] for w in re.findall(r"[a-z]+", str(beat_text).lower()) if w in FILMABLE)
        here = [k for k, _ in counts.most_common(1)]
    return here[0] if here else None


VARIANTS = ("close up", "wide shot", "aerial view", "detail", "from the side", "at golden hour", "in the rain", "from far away")


def vary_repeats(plan, notes: List[str]) -> int:
    """The same stock search asked for again later in the video would show the same clip again (project #006: "concrete dam" 7
    times): each repeat asks for another framing of the same subject instead ("concrete dam, close up"). Returns how many changed."""
    seen = set()
    changed = []
    for b in plan.beats:
        for c in b.clips:
            kind, sep, what = str(c.asset).partition(":")
            if not sep or kind not in ("stock_video", "stock_image"):
                continue
            key = (kind, " ".join(what.lower().split()))
            if key in seen:
                base = what.strip()
                fresh = next((f"{base}, {v}" for v in VARIANTS if (kind, f"{base}, {v}".lower()) not in seen), None)
                if fresh is None:
                    continue
                c.asset = f"{kind}:{fresh}"
                key = (kind, fresh.lower())
                changed.append(b.id)
            seen.add(key)
    if changed:
        notes.append(f"{len(changed)} stock clip(s) asked for something an earlier clip already shows: each asks for another framing "
                     f"of it, so no clip is shown twice ({', '.join(dict.fromkeys(changed))})")
    return len(changed)


def keep_map_under(plan, words, payload, notes: List[str], limit: float = MAP_LIMIT) -> int:
    """The map is a part of the video, not all of it: while it is on screen more than `limit` of the time, quiet map stretches
    (nothing arriving, no camera move, no loop, no number being read) cut to footage of what is being said. Data graphics keep
    their map time. Returns how many cutaways were added."""
    from .teamplate.cutaways import add_cutaways

    total = sum(b.end - b.start for b in plan.beats) or 1.0
    on_map = sum(b.end - b.start for b in plan.beats if b.mode != "footage")
    if on_map / total <= limit + 1e-6:
        return 0
    def fallback(spoken: str, beat):
        return fallback_request(spoken, getattr(beat, "narration", "") or "")

    n = add_cutaways(plan, words, payload, notes, max_share=1.0 - limit, fallback=fallback, label="map under half the video")
    after = sum(b.end - b.start for b in plan.beats if b.mode != "footage") / total
    notes.append(f"the map was on screen {on_map / total:.0%} of the video; {n} cutaway(s) to footage bring it to {after:.0%}"
                 + ("" if after <= limit + 0.02 else " (the rest of the map time shows data, camera moves or numbers being read)"))
    return n
