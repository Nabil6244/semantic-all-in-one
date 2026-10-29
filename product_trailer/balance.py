"""Variety pass for Review films: the scene-writer (AI or rules) tends to favour whichever picture a sentence suggests first, so a film can end up all
flat phones or all 3D. `balance` runs after it and keeps the reference looks in rotation: no look three times in a row, and every look the script has a
reason for (3D render, measured bench set, stock footage) appears at least once in a film of five scenes or more. Directives the author wrote are never touched.

    balance(parsed, phone="", footage=False) -> parsed copy with the same sentences and adjusted scene items
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from . import director

KINDS_3D = ("xray", "fold", "chip", "macro", "lineup")
MAX_RUN = 2
MIN_SCENES = 5
ROTATION: Tuple[Dict[str, Any], ...] = (
    {"kind": "macro", "text": "Design", "move": "edge"}, {"kind": "lineup", "text": "The phone", "room": None, "pose": None},
    {"kind": "macro", "text": "Display", "move": "screen"}, {"kind": "chip", "label": "CHIP", "text": "Performance"}, {"kind": "macro", "text": "Camera", "move": "island"})


def family(it: Dict[str, Any]) -> Optional[str]:
    """The look a scene item belongs to, or None for anything that is not a picked scene."""
    k = it.get("kind")
    if k == "scene":
        return "evidence" if (it.get("layer") or {}).get("type") == "pt_doc" else "flat"
    return {"tweet": "evidence", "curve": "chart", "bench": "bench", "footage": "footage"}.get(k) or ("3d" if k in KINDS_3D else None)


def _bench_from(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A flat two-phone scene whose figures share a unit, as a bench set (glass cards over phones on stands)."""
    phones = (it.get("layer") or {}).get("phones") or []
    rows = []
    for p in phones[:3]:
        n = director._numbers(str(p.get("text") or (p.get("side") or {}).get("text") or ""))
        if not n:
            return None
        rows.append((p.get("label") or "Phone", n[0]))
    if len(rows) < 2 or len({r[1]["unit"] for r in rows}) != 1 or len({r[1]["v"] for r in rows}) < 2:
        return None
    return {"kind": "bench", "heading": str((it["layer"].get("title") or "Measured")).upper()[:30],
            "items": [{"label": str(l)[:24], "value": n["v"], "unit": n["unit"]} for l, n in rows]}


def _line_after(items: List[Dict[str, Any]], i: int) -> str:
    return next((x["text"] for x in items[i + 1:] if x["kind"] == "line"), "")


def _alt(it: Dict[str, Any], line: str, k: int) -> Dict[str, Any]:
    """Another look for the same sentence: its measured figures as a bench set, a 3D shot its words call for, else the next 3D shot in rotation."""
    if family(it) == "flat":
        b = _bench_from(it)
        if b:
            return b
    return director.three_d_for(line) or dict(ROTATION[k % len(ROTATION)])


def balance(parsed: Dict[str, Any], phone: str = "", footage: bool = False) -> Dict[str, Any]:
    out = copy.deepcopy(parsed)
    k = 0
    run_fam, run_n = None, 0
    for ch in out["chapters"]:
        items = ch["items"]
        for i, it in enumerate(items):
            f = family(it)
            if f is None:
                continue
            run_n = run_n + 1 if f == run_fam else 1
            run_fam = f
            if run_n > MAX_RUN and not it.get("_own"):
                items[i] = it = _alt(it, _line_after(items, i), k)
                k += 1
                run_fam, run_n = family(it), 1
    scenes = [it for ch in out["chapters"] for it in ch["items"] if family(it)]
    if len(scenes) >= MIN_SCENES:
        have = {family(it) for it in scenes}
        missing = [f for f in ("3d", "bench", "footage") if f not in have and (f != "footage" or footage)]
        if "bench" in missing:                                                  # a measured pair already on a flat scene becomes the bench set
            for ch in out["chapters"]:
                for i, it in enumerate(ch["items"]):
                    b = _bench_from(it) if family(it) == "flat" and not it.get("_own") else None
                    if b and "bench" in missing:
                        ch["items"][i] = b
                        missing.remove("bench")
        missing = [f for f in missing if f != "bench"]                           # no measured pair in the script: no bench set to force
        plain: List[Tuple[List[Dict[str, Any]], int]] = []                      # sentences with no scene of their own
        for ch in out["chapters"]:
            for i, it in enumerate(ch["items"]):
                if it["kind"] == "line" and not (i and family(ch["items"][i - 1])):
                    plain.append((ch["items"], i))
        for n, f in enumerate(missing):
            def pick_for(line: str) -> Optional[Dict[str, Any]]:
                if f == "3d":
                    return director.three_d_for(line) or dict(ROTATION[k % len(ROTATION)])
                hint = director.footage_hint(line)
                return {"kind": "footage", "query": hint, "text": ""} if hint else None

            done = False
            for off in range(len(plain)):                                       # first choice: a sentence that has no scene yet
                items, i = plain[(len(plain) * (n + 1) // (len(missing) + 1) + off) % len(plain)]
                pick = pick_for(items[i]["text"])
                if pick:
                    items.insert(i, pick)
                    plain = [(it2, j + (1 if it2 is items and j >= i else 0)) for it2, j in plain if not (it2 is items and j == i)]
                    done = True
                    break
            if not done:                                                        # else swap a scene of a look the film has more than one of
                counts: Dict[str, int] = {}
                for ch in out["chapters"]:
                    for it in ch["items"]:
                        if family(it):
                            counts[family(it)] = counts.get(family(it), 0) + 1
                cands = sorted(((counts[family(it)], ci, ch["items"], i) for ci, ch in enumerate(out["chapters"]) for i, it in enumerate(ch["items"])
                                if family(it) and counts[family(it)] > 1 and not it.get("_own")), key=lambda c: (-c[0], c[1]))
                for _, _, items, i in cands:
                    pick = pick_for(_line_after(items, i))
                    if pick:
                        items[i] = pick
                        break
            k += 1
    for ch in out["chapters"]:
        for it in ch["items"]:
            it.pop("_own", None)
    return out
