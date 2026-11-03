"""Plan check: every finished Explainer plan is looked over for the faults found by watching renders, before a single picture is fetched or frame drawn.

Each fault here was found in a real render first (the Stibnite video, 2026-11-03): a scene CSV that was not used, one scene note covering most of the video,
the same picture prompt on beat after beat, one person (a soldier) in almost every picture, prompts that make Flow draw panels, no real map, a phrase on screen that
stops mid-thought, a board left as an empty page. `audit` returns findings in plain words; it never changes the plan and never stops it (the app shows the findings).
A new fault seen in a render belongs here as a new check, so it is caught at Direct time from then on."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Sequence

MAX_NOTE_SHARE = 0.4            # one CSV scene covering more of the video than this: its neighbours' anchors landed wrong
MIN_DISTINCT_PICTURES = 0.8     # distinct picture prompts / picture beats
MAX_REPEAT_RUN = 2              # the same prompt on more beats in a row than this
MAX_PERSON_SHARE = 0.5          # one cast member in more of the pictures than this


def _prompts(plan: Dict[str, Any]) -> List[str]:
    out = []
    for b in plan.get("beats") or []:
        for c in ((b.get("footage") or {}).get("clips") or []):
            a = str(c.get("asset") or "")
            if a.startswith("flow_image:"):
                out.append(" ".join(a[len("flow_image:"):].lower().split()))
    return out


def audit(plan: Dict[str, Any], report: Dict[str, Any], *, scene_notes: Sequence[Dict[str, Any]] = (), kept_scene_csv: bool = False, duration: float = 0.0) -> List[str]:
    """Findings, most serious first ([] = nothing wrong found)."""
    found: List[str] = []
    if not plan:
        return found
    beats = plan.get("beats") or []
    total = float(duration or plan.get("duration") or (beats[-1]["end"] if beats else 0.0))
    if kept_scene_csv and not scene_notes:
        found.append("the project has a scene CSV but this plan was made without it: load the CSV again, then Direct with Explainer")
    if scene_notes and total > 0:
        for n in scene_notes:
            span = float(n.get("end", 0)) - float(n.get("start", 0))
            if span > MAX_NOTE_SHARE * total:
                what = str(n.get("text", "")).split(";")[0].replace("place:", "").strip()
                found.append(f"one CSV scene ({what}) covers {span:.0f} s of {total:.0f} s: check the vo_anchor of the scene after it")
    ps = _prompts(plan)
    if ps:
        distinct = len(set(ps))
        if distinct < MIN_DISTINCT_PICTURES * len(ps):
            found.append(f"{len(ps)} picture beats but only {distinct} different pictures: many beats repeat the picture before them")
        run, worst = 1, 1
        for a, b in zip(ps, ps[1:]):
            run = run + 1 if a == b else 1
            worst = max(worst, run)
        if worst > MAX_REPEAT_RUN:
            found.append(f"the same picture prompt is used on {worst} beats in a row")
        if any(re.search(r"\bvariation \d", p) for p in ps):
            found.append("a picture prompt asks for a 'variation': Flow draws several pictures side by side for that")
        people = Counter(m for p in ps for m in set(re.findall(r"people: ([a-z ,]+?)(?:,|\.|;)", p)))
        if people:
            who, n = people.most_common(1)[0]
            if n > MAX_PERSON_SHARE * len(ps) and len(ps) >= 10:
                found.append(f"'{who.strip()}' is in {n} of {len(ps)} pictures: check which CSV scenes name them")
    maps = [b for b in beats if b.get("mode") in ("map", "map_footage")]
    warnings = " ".join(str(w) for w in ((report.get("selection") or {}).get("warnings") or []))
    if not maps or (len(maps) == 1 and "fallback" in warnings):
        found.append("no place in the narration got a map: the only map is the stand-in opening")
    details = report.get("beat_details") or {}
    from .director import onscreen as OS

    def unfinished(t: str) -> bool:
        last = OS._tok(t.split()[-1]) if t.split() else ""
        return bool(last) and not re.search(r"\d", last) and (last in OS.TRAILING or OS._adverb(last))

    cut = sorted({str(p.get("phrase")) for d in details.values() for p in ((d or {}).get("phrases") or []) if unfinished(str(p.get("phrase") or ""))})
    if cut:
        found.append(f"{len(cut)} phrase(s) stop mid-thought, e.g. {cut[0]!r}")
    return found
