"""Beats from the narration itself, for a Weather project with no beat plan (script + voiceover -> video, no CSV).

The narration's sentences (hybrid.narration.build_sentences: the script when there is one, else the transcript's pauses) are
sorted into two kinds and grouped into beats:

  map      a sentence that names a number, a place, a time, a warning or a data product (and the opening and the closing):
           the camera goes to the place it names (a county or city: its point, close up; otherwise the story's state)
  footage  a sentence that describes what people saw or went through (damage, debris, flooding, rescues, shelter ...) and names
           something a camera can film: 1-3 stock shots of exactly that (your footage library first, when you have one)

A new beat starts where the kind changes, where a map sentence names another place, or when a beat reaches BEAT_TARGET_S;
beats end on sentence ends. Footage is kept to FOOTAGE_SHARE of the video and never shorter than FOOTAGE_MIN_S; anything shorter
or over the share stays on the map. Hybrid's own director.derive_cameras turns the camera targets into camera moves. The result is
an ordinary hybrid.plan.HybridPlan built through the existing interfaces — no CSV is written. Deterministic: the engine (before
Check plan / Generate) and the render build the same plan from the same words."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

BEAT_TARGET_S = 14.0
BEAT_MAX_S = 24.0
BEAT_MIN_S = 5.0            # a map beat shorter than this does not start for a new place (it keeps the previous target)
FOOTAGE_MIN_S = 4.0         # a run of footage sentences shorter than this stays on the map
FOOTAGE_MAX_S = 12.0        # a longer run is split into several footage beats
FOOTAGE_SHARE = 0.40        # Weather Teamplate's own cap (weather.teamplate.cutaways.MAX_SHARE)
SHOT_S = 5.0                # about one shot every 5 s inside a footage beat
MAX_SHOTS = 3

# what people saw or went through -> what to ask the stock providers for (most specific first). The request uses only things a camera
# can film; the beat's narration is kept with it, so Weather Teamplate's relevance check can confirm it.
IMPACT_SUBJECTS = (
    (("mobile home", "mobile homes", "trailer", "trailers"), "damaged mobile home after a storm"),
    (("roof", "roofs", "shingles", "siding"), "storm damaged roof"),
    (("debris", "rubble", "wreckage"), "storm debris on a street"),
    (("uprooted", "fallen trees", "trees down", "downed trees", "snapped trees", "tree damage", "damage to trees", "trees"), "fallen trees after a storm"),
    (("power lines", "power line", "without power", "power outages", "outages", "outage", "utility crews"), "utility crew repairing power lines"),
    (("rescue", "rescued", "rescues", "rescuers", "first responders", "boats"), "rescue crew in floodwater"),
    (("evacuate", "evacuated", "evacuation", "evacuations", "evacuating"), "cars evacuating on a highway"),
    # shelter advice: stock "people sheltering" comes back as families on sofas and in beds; the storm over homes is what to show
    (("shelter", "shelters", "interior room", "basement", "lowest floor", "take cover"), "dark storm clouds over houses"),
    (("cleanup", "clean up", "cleaning up", "volunteers"), "storm cleanup crews"),
    (("croplands", "cropland", "pastures", "farmland", "fields", "crops"), "flooded farmland"),
    (("flooded", "floodwater", "floodwaters", "underwater", "inundated", "high water", "flooding"), "flooded street"),
    (("hail", "hailstones"), "hailstones bouncing on the ground"),
    (("windows", "vehicles", "cars"), "storm damaged cars"),
    (("homes", "houses", "neighborhood", "neighborhoods", "buildings"), "storm damaged houses"),
    (("destroyed", "damaged", "damage", "flattened", "ripped", "torn", "collapsed", "toppled"), "storm damage"),
)
IMPACT_WORDS = re.compile(r"\b(" + "|".join(sorted({re.escape(w) for keys, _r in IMPACT_SUBJECTS for w in keys}, key=len, reverse=True))
                          + r")\b", re.I)


def _norm(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z']+", str(text).lower().replace("’", "'"))) + " "


def impact_request(text: str) -> Optional[str]:
    """The stock request for a sentence about impacts (None when it names none)."""
    low = _norm(text)
    for keys, req in IMPACT_SUBJECTS:
        if any(f" {k} " in low for k in keys):
            return req
    return None


SPELLED = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "fifteen", "twenty",
           "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "dozen", "half", "quarter"}


def _is_data(text: str, local_place: bool) -> bool:
    """A sentence the map should show: a number, a place close up, a warning / product / source being read out. A unit with no
    number ("for miles") is not a number being read."""
    from ..teamplate.cutaways import NOT_WEATHER, NUMBER_WORDS, SOURCE_WORDS

    if local_place:
        return True
    low = str(text).lower()
    if NOT_WEATHER.search(low) or re.search(r"\d", low):
        return True
    words = re.findall(r"[a-z]+", low)
    if any(w in NUMBER_WORDS and k > 0 and words[k - 1] in SPELLED for k, w in enumerate(words)) or "category" in words:
        return True
    return bool(set(words) & SOURCE_WORDS)


def footage_request(text: str) -> Optional[str]:
    """What a footage sentence asks the stock providers for: the impact it describes, else the weather it describes, else the
    filmable things it names. None when nothing in it can be filmed."""
    from ..motion import fallback_request
    from ..teamplate.cutaways import request_for

    if not IMPACT_WORDS.search(str(text)):
        return None
    return fitting((impact_request(text), request_for(text), fallback_request(text)), text)


def fitting(requests, narration: str) -> Optional[str]:
    """The first request that does not contradict the narration (Weather Teamplate's relevance rule, weather.teamplate.footage:
    "flooded street" for a line about country roads is a contradiction), else its version without the setting."""
    from ..teamplate.footage import _trimmed, conflicts

    reqs = [r for r in requests if r]
    for r in reqs + [_trimmed(r) for r in reqs]:
        if r and not conflicts(r, narration):
            return r
    return None


def plan_from_narration(words: Sequence, duration: float, notes: List[str], *, script: str = ""):
    from hybrid.director import derive_cameras
    from hybrid.narration import build_sentences
    from hybrid.plan import Beat, Clip, HybridPlan

    from .catalog import state_name
    from .understand import Segment, understand

    sents = build_sentences(list(words), script or None, duration)
    if not sents:
        raise ValueError("the narration has no sentences to build beats from")
    n = len(sents)
    starts = [0.0] + [s.start for s in sents[1:]]
    ends = [sents[i + 1].start for i in range(n - 1)] + [duration]
    spans = [max(0.0, ends[i] - starts[i]) for i in range(n)]

    # what each sentence names: one understanding of the whole story, with each sentence as its own segment
    u = understand([Segment(f"s{i}", "map", s.text, starts[i], ends[i]) for i, s in enumerate(sents)])
    local, named = {}, {}
    for p in u.places:
        if p.kind in ("county", "city") and p.lat is not None and p.seg not in local:
            local[p.seg] = f"{p.lat:.2f},{p.lon:.2f}"
        if p.kind == "state" and p.state:
            named.setdefault(p.seg, []).append(state_name(p.state))
    for seg, names in named.items():   # the state named most in the sentence, the first one said on a tie
        text = sents[int(seg[1:])].text
        named[seg] = min(set(names), key=lambda x: (-names.count(x), text.find(x) if x in text else len(text)))
    state = u.states[0] if u.states else ""
    region = state_name(state) if state else "United States"

    # 1. the kind of each sentence; the opening and the closing stay on the map
    kind, request, data = [], [], []
    for i, s in enumerate(sents):
        data.append(i == 0 or i == n - 1 or _is_data(s.text, f"s{i}" in local))
        req = None if data[-1] else footage_request(s.text)
        kind.append("footage" if req else "map")
        request.append(req)

    def runs():
        out, i = [], 0
        while i < n:
            j = i
            while j + 1 < n and kind[j + 1] == kind[i]:
                j += 1
            out.append((i, j))
            i = j + 1
        return out

    # 2. a short line with nothing for the map to show ("take cover now.") next to footage joins that footage
    for i in range(n):
        near = (i > 0 and kind[i - 1] == "footage") or (i + 1 < n and kind[i + 1] == "footage")
        if kind[i] == "map" and near and not data[i] and spans[i] < FOOTAGE_MIN_S:
            kind[i] = "footage"
    # too short to be a shot, or over the footage share: back on the map (the shortest runs go first)
    for a, z in runs():
        if kind[a] == "footage" and sum(spans[a:z + 1]) < FOOTAGE_MIN_S:
            for k in range(a, z + 1):
                kind[k] = "map"
    budget = FOOTAGE_SHARE * duration
    foot = sorted(((sum(spans[a:z + 1]), a, z) for a, z in runs() if kind[a] == "footage"), reverse=True)
    used = 0.0
    for length, a, z in foot:
        if used + length <= budget + 1e-6:
            used += length
        else:
            for k in range(a, z + 1):
                kind[k] = "map"

    # 3. sentences -> beats
    groups: List[List[int]] = []
    for i in range(n):
        cur = groups[-1] if groups else None
        if cur is None or kind[i] != kind[cur[0]]:
            groups.append([i])
            continue
        span = ends[i] - starts[cur[0]]
        full = ends[cur[-1]] - starts[cur[0]]
        if kind[i] == "footage":
            new = span > FOOTAGE_MAX_S and full >= FOOTAGE_MIN_S
        else:
            target = next((local.get(f"s{k}") for k in cur if local.get(f"s{k}")), None)
            moved = f"s{i}" in local and target is not None and local[f"s{i}"] != target and full >= BEAT_MIN_S
            new = moved or span > BEAT_MAX_S or full >= BEAT_TARGET_S
        if new:
            groups.append([i])
        else:
            cur.append(i)

    beats, shots, last = [], 0, ""
    said_local = [None] * n   # the last county / city named up to each sentence
    for i in range(n):
        # a state named on its own ("Turning to Oklahoma") ends the last county's story
        said_local[i] = local.get(f"s{i}") or (None if f"s{i}" in named or not i else said_local[i - 1])
    for gi, g in enumerate(groups):
        start = 0.0 if gi == 0 else starts[g[0]]
        end = duration if gi == len(groups) - 1 else starts[groups[gi + 1][0]]
        text = " ".join(sents[k].text for k in g)
        if kind[g[0]] == "footage":
            # each request checked against the whole beat's words (what the relevance check reads), never a contradiction
            reqs = list(dict.fromkeys(r for r in (fitting((request[k],), text) for k in g if request[k]) if r))
            if not reqs:
                from ..teamplate.cutaways import request_for

                reqs = [fitting((request_for(text), "dark storm clouds rolling"), text) or "dark storm clouds rolling"]
            count = max(1, min(MAX_SHOTS, int(round((end - start) / SHOT_S))))   # a repeated request is reframed (motion.vary_repeats)
            clips = [Clip(asset=f"stock_video:{reqs[k % len(reqs)]}", reason="footage of what the narration describes")
                     for k in range(count)]
            shots += count
            beats.append(Beat(id=f"b{gi + 1}", mode="footage", start=round(start, 3), end=round(end, 3), narration=text, purpose="impact",
                              clips=clips, footage_intent="show what the narration describes"))
            continue
        b = Beat(id=f"b{gi + 1}", mode="map", start=round(start, 3), end=round(end, 3), narration=text,
                 purpose="opening" if gi == 0 else ("closing" if gi == len(groups) - 1 else ""))
        target = next((local.get(f"s{k}") for k in g if local.get(f"s{k}")), None)
        said_state = next((named[f"s{k}"] for k in g if f"s{k}" in named), "")
        if target is not None and gi not in (0, len(groups) - 1):
            b.cam_place, b.cam_frame = target, "local"
        elif said_state or gi in (0, len(groups) - 1) or not last:
            # the state this beat names; the opening and the closing (and a beat before any place) show the story's region
            b.cam_place, b.cam_frame = said_state or region, ("region" if (said_state or state) else "continental")
        elif said_local[g[0]]:   # names no place: the camera goes back to the last county / city the story named
            b.cam_place, b.cam_frame = said_local[g[0]], "local"
        else:   # names no place and none was named yet: the camera stays where the story is
            b.cam_place, b.cam_frame = last, next(x.cam_frame for x in reversed(beats) if x.mode == "map")
        last = b.cam_place
        beats.append(b)
    plan = HybridPlan(duration=duration, beats=beats, settings={"drift_pct_per_s": 0.0})
    derive_cameras(plan)
    nf = sum(1 for b in beats if b.mode == "footage")
    notes.append(f"the project has no beat plan, so {len(beats)} beats were made from the narration's {n} sentences: "
                 f"{len(beats) - nf} on the map, {nf} of footage ({shots} shot(s)) where it describes what people saw or went through")
    return plan


def use_library(plan, folder, notes: List[str], *, strict: bool = False) -> int:
    """Each stock footage request of the plan swapped for a matching clip of yours (weather.footage_library), like the CSV path does
    to beats.csv. `strict` (Weather Teamplate) also checks the clip against its beat's narration. Returns how many were swapped."""
    from ..footage_library import index, pick

    lib = index(folder) if folder else []
    if not lib:
        return 0
    if strict:
        from ..teamplate.footage import _pick as strict_pick
    used, n = set(), 0
    for b in plan.beats:
        for c in b.clips:
            kind, sep, what = str(c.asset).partition(":")
            if not sep or kind != "stock_video":
                continue
            hit = strict_pick(what, b.narration, lib, used) if strict else pick(what, lib, used)
            if hit is not None:
                used.add(hit)
                notes.append(f"your clip {hit.name} instead of {c.asset}")
                c.asset = str(hit)
                n += 1
    return n
