"""The "Full Guide" blueprint (docs/rep_theory/UPGRADE_LIST.md section 3, Step 6), on the planned scenes. Run last, after states.develop.
A unit is a run of scenes under one chapter the narration (or the CSV) announced; the blueprint only uses the units the script has (Rule 4: a slot the script
does not fill is skipped, never padded). Everything shown is the script's own words:
  teaser   the last seconds of a unit show NEXT and the next unit's name
  lock     an early test ("test your ...", "time yourself", "try it right now") that the script pays off later gets a RESULT AT THE END pill: the curiosity lock
  safety   once the script has stated a safety rule (a warning card), the scenes of the units carry it as a small chip
`report` says which of the unit template's slots each unit filled (title, steps, a named part, the feeling, a number, easier/harder, the mistake)."""
from __future__ import annotations
import re
from typing import Dict, List

TEST_RX = re.compile(r"\b(?:test (?:your|yourself|it)|time yourself|try (?:it|this) (?:right )?now|how long can you|count how many|write down your|note your)\b", re.I)
PAYOFF_RX = re.compile(r"\b(?:your (?:result|time|score|number)s?|at the end|retest|test again|re-test)\b", re.I)
TEASE_S, EARLY = 2.6, 0.30      # the teaser's length at a unit's end; a test counts as early in the first 30% of the video
SLOTS = {"title": lambda sc: bool(sc.get("chapter_card")), "steps": lambda sc: sc["kind"] == "steps", "part": lambda sc: bool(sc.get("glows")) or sc.get("look") in ("3d", "anatomy"),
         "feeling": lambda sc: sc["kind"] == "timeline", "number": lambda sc: sc["kind"] in ("stat", "dial", "bars", "study"), "easier/harder": lambda sc: sc["kind"] == "slider", "mistake": lambda sc: sc["kind"] == "mistake"}

def units(scenes: List[dict]) -> List[List[dict]]:
    """Runs of scenes under one announced chapter (the video's own title is not a unit)."""
    out: List[List[dict]] = []
    for i, sc in enumerate(scenes):
        s = sc.get("section") or ""
        if not s or s == sc.get("topic") or s.startswith("TIER LIST"): continue
        if out and out[-1][0].get("section") == s and i and out[-1][-1] is scenes[i - 1]: out[-1].append(sc)
        else: out.append([sc])
    return out

def apply(scenes: List[dict]) -> Dict[str, int]:
    us = units(scenes); n = {"units": len(us), "teasers": 0, "locks": 0, "safety_chips": 0}
    if len(us) >= 2:
        for u, nxt in zip(us, us[1:]):
            last = u[-1]; name = nxt[0]["section"]
            if name != u[0]["section"] and last["end"] - last["start"] >= 2.0:
                last["teaser"] = {"text": name.upper(), "at": max(last["start"] + 0.6, last["end"] - TEASE_S)}; n["teasers"] += 1; last["decisions"].append(f"blueprint: NEXT teaser for '{name}'")
    total = scenes[-1]["end"] if scenes else 0.0
    for i, sc in enumerate(scenes):
        m = TEST_RX.search(sc.get("text", ""))
        if not m or sc["start"] > EARLY * total: continue
        if any(PAYOFF_RX.search(x.get("text", "")) or x["kind"] == "result" for x in scenes[i + 1:] if x["start"] > sc["end"] + 30): sc["lock"] = {"at": _word_at(sc, m.start())}; n["locks"] += 1; sc["decisions"].append("blueprint: test locked until its payoff"); break
    warn = next((sc for sc in scenes if sc["kind"] == "warning"), None)
    if warn and us:
        rule = warn["warning"]["rules"][0]["text"]; inside = {id(x) for u in us for x in u}
        for sc in scenes:
            if id(sc) in inside and sc is not warn and sc["start"] >= us[0][0]["start"] and sc["kind"] not in ("takeaway", "engage"): sc["safety"] = rule; n["safety_chips"] += 1
    return n

def _word_at(sc: dict, pos: int) -> float:
    ws = sc.get("words") or []; i = len(sc.get("text", "")[:pos].split())
    return float(ws[min(i, len(ws) - 1)]["t0"]) if ws else float(sc["start"])

def report(scenes: List[dict]) -> List[str]:
    """One line per unit: the template slots it filled."""
    return [f"{u[0]['section']}: " + ", ".join(k for k, f in SLOTS.items() if any(f(sc) for sc in u)) for u in units(scenes)]
