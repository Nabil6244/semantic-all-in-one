"""More graphics from the narration itself: the planner's extra pass so a long What If video uses the template library, not only
captions and numbers (project 015, 16 minutes: 17 different graphics, 6 a minute).

Everything here is taken from what the narrator says -- a year, a question, "one in a million", "First, ...", a spoken number --
never from a template's sample data, so nothing is invented. Overlay templates (plate: false) go over the picture already on
screen; a question card or odds dial gets a plate of its own inside the plate budget. Every placement is written to the notes.

    dated_caption     "In 1976, NASA's Viking landers ..."      -> 1976 · NASA'S VIKING LANDERS, top-left over the picture
    stage_header      "First, ..." / "Second, ..." / "Finally, ..." -> PART 1 · <the clause>, top-left
    big_number_lower  every second spoken number on a picture  -> a counted number at the lower left (the tm_metric look alternates)
    question_card     a question the narrator asks (5-14 words) -> the question on its own plate, white and gold
    odds_dial         "one in a million" / "1 in 4"              -> a dial with a thin slice lit
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ORDINALS = {"first": "PART 1", "second": "PART 2", "third": "PART 3", "fourth": "PART 4", "fifth": "PART 5", "finally": "FINALLY",
            "lastly": "FINALLY", "next": "NEXT"}
WORD_NUM = {"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000, "trillion": 1_000_000_000_000}
QUESTION_GAP_S, DATED_GAP_S, STAGE_GAP_S, BIG_NUMBER_EVERY = 120.0, 45.0, 40.0, 2
SMALL = {"the", "a", "an", "of", "to", "and", "that", "which", "was", "were", "is", "had", "has", "have", "it", "its", "their", "this", "these"}


def _clean(words: Sequence[str], n: int = 5) -> str:
    ws = [re.sub(r"[^\w'*%°.-]", "", w).strip(".-") for w in words]
    ws = [w for w in ws if w]
    while ws and ws[0].lower() in SMALL:
        ws.pop(0)
    cut = ws[:n]
    while len(cut) > 1 and cut[-1].lower() in SMALL:
        cut.pop()
    return " ".join(cut).upper()


def _overlaps(layers: Sequence[Dict[str, Any]], t0: float, t1: float, types: Sequence[str]) -> bool:
    return any(L.get("type") in types and float(L.get("start", 0)) < t1 and t0 < float(L.get("end", 0)) for L in layers)


def _overlay_busy(layers, t0, t1) -> bool:
    """Another top-left / lower-left graphic, a title card or an instrument already there."""
    if _overlaps(layers, t0, t1, ("tm_title", "tm_survival", "tm_fade")):
        return True
    return any(L.get("type") == "tm_template" and not L.get("plate", True) and float(L["start"]) < t1 and t0 < float(L["end"]) for L in layers)


def _layer(tid: str, slots: Dict[str, Any], t0: float, t1: float, words=(), cues_from=None) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    from . import templates as tpl

    it = type("Row", (), {"id": tid, "hold": t1 - t0, "extra": {"slots": slots}, **{c: None for c in tpl.COLUMNS}})()
    return tpl.layer_for(it, t0, t1, words)


def engage(shots: List[Any], layers: List[Dict[str, Any]], words: Sequence[Any], sn: Sequence[Tuple[int, int]], metrics: Sequence[Any],
           duration: float, notes: List[str], *, carve: Callable[..., Any], shot_cls: Any, plate_budget: float, span_text: Callable[..., str],
           hook_s: float = 20.0) -> Tuple[List[Any], float]:
    """-> (shots, plate budget left). Adds the graphics above to `layers` (and question / odds plates to the shots)."""
    from . import templates as tpl

    if not words or not tpl.load_library():
        return shots, plate_budget
    on_plate = lambda t0, t1: any(s.kind == "plate" and s.start - 0.05 < t1 and t0 < s.end + 0.05 for s in shots)   # noqa: E731
    plates = lambda: [(s.start, s.end) for s in shots if s.kind == "plate"]  # noqa: E731
    added: Dict[str, int] = {}

    def add(L, pl=None) -> None:
        layers.append(L)
        tid = L["template"]["id"]
        added[tid] = added.get(tid, 0) + 1

    last = {"dated": -1e9, "stage": -1e9, "question": -1e9}
    for a, b in sn:
        sent = span_text(words, a, b)
        toks = sent.split()
        if not toks:
            continue
        t0 = max(0.0, float(words[a].start) - 0.1)
        # a dated sentence: "In 1976, ..." / "Back in 2004 ..." / "On July 20, 1969, ..."
        m = re.match(r"^(?:back )?(?:in|by|on|around)\s+(?:[A-Z][a-z]+\s+\d{1,2},?\s+)?((?:1[5-9]|20)\d\d)\b[,]?\s*(.*)$", sent, re.I)
        if m and t0 >= hook_s and t0 - last["dated"] >= DATED_GAP_S:
            label = _clean(m.group(2).split(), 5)
            t1 = min(t0 + 4.5, duration - 0.3)
            if len(label) >= 4 and not on_plate(t0, t1) and not _overlay_busy(layers, t0, t1):
                L, _ = _layer("dated_caption", {"year": m.group(1), "label": label, "sub": ""}, t0, t1, words)
                add(L)
                last["dated"] = t0
                continue
        # "First, ..." / "Finally, ..."
        first = re.sub(r"[^\w]", "", toks[0]).lower()
        if first in ORDINALS and len(toks) > 4 and toks[0].endswith(",") and t0 >= hook_s and t0 - last["stage"] >= STAGE_GAP_S:
            label = _clean(toks[1:], 4)
            t1 = min(t0 + 4.0, duration - 0.3)
            if len(label) >= 4 and not on_plate(t0, t1) and not _overlay_busy(layers, t0, t1):
                L, _ = _layer("stage_header", {"label": label, "sub": ORDINALS[first]}, t0, t1, words)
                add(L)
                last["stage"] = t0
                continue
        # a question the narrator asks: its own card (not the title question at the start, not the closing one)
        if sent.rstrip().endswith("?") and 5 <= len(toks) <= 14 and hook_s + 10 <= t0 <= duration - 30 and t0 - last["question"] >= QUESTION_GAP_S:
            if any(L.get("type") == "tm_title" and abs(float(L["start"]) - t0) < 3 for L in layers):
                continue
            t1 = min(max(t0 + 3.5, float(words[b].end) + 0.6), t0 + 5.5, duration - 0.5)
            if t1 - t0 >= 3.0 and plate_budget >= t1 - t0 and not any(x < t1 and t0 < y for x, y in plates()):
                half = (len(toks) + 1) // 2
                L, pl = _layer("question_card", {"label": " ".join(toks[:half]).upper(), "sub": " ".join(toks[half:]).upper()}, t0, t1, words)
                carved = carve(shots, shot_cls(id="", start=t0, end=t1, kind="plate", tint="cool", text=sent, cite=pl["cite"]), force=True)
                if carved:
                    shots = carved
                    add(L)
                    plate_budget -= t1 - t0
                    last["question"] = t0
                continue
        # "one in a million" / "1 in 4"
        m = re.search(r"\b(?:one|1)\s+in\s+(?:a\s+|every\s+)?(\d[\d,]*|hundred|thousand|million|billion|trillion)\b", sent, re.I)
        if m and t0 >= hook_s and added.get("odds_dial", 0) < 2:
            raw = m.group(1).lower().replace(",", "")
            n = WORD_NUM.get(raw) or (int(raw) if raw.isdigit() else 0)
            hit = next((w for w in words[a:b + 1] if re.sub(r"[^\w]", "", w.text).lower() in ("one", "1")), words[a])
            t1 = min(float(hit.start) + 4.5, duration - 0.5)
            ts = max(0.0, float(hit.start) - 0.1)
            if n >= 2 and plate_budget >= t1 - ts and not any(x < t1 and ts < y for x, y in plates()):
                L, pl = _layer("odds_dial", {"label": f"1 IN {n:,}", "sub": "", "share": max(0.004, 1.0 / n)}, ts, t1, words)
                carved = carve(shots, shot_cls(id="", start=ts, end=t1, kind="plate", tint="cool", text=sent, cite=pl["cite"]), force=True)
                if carved:
                    shots = carved
                    add(L)
                    plate_budget -= t1 - ts
    # every second number over a picture: the counted lower-left look (a change of look, the same number and words). A CSV number is
    # its "text" ("1.5×", "92 BAR"), an automatic one its "value" + "unit"
    metric_layers = [L for L in layers if L.get("type") == "tm_metric" and (L.get("value") or L.get("text")) and not L.get("rows")]
    for k, L in enumerate(metric_layers):
        if k % BIG_NUMBER_EVERY != 1:
            continue
        shown = str(L.get("value") or L.get("text"))
        m = re.match(r"^\s*[≈~]?\s*(-?\d[\d,]*(?:\.\d+)?)\s*(.*)$", shown)
        if not m:
            continue
        t0, t1 = float(L["start"]), float(L["end"])
        if on_plate(t0, t1) or _overlay_busy(layers, t0, t1):
            continue
        num = float(m.group(1).replace(",", ""))
        unit = (str(L.get("unit") or "") + " " + m.group(2)).strip()
        slots = {"value_from": 0, "value_to": int(num) if num.is_integer() else num, "format": unit.upper(), "sub": str(L.get("sub") or "").upper()}
        NL, _ = _layer("big_number_lower", slots, t0, max(t1, t0 + 3.5), words)
        layers.remove(L)
        add(NL)
    shots = vary_looks(shots, layers, words, lambda tid: added.__setitem__(tid, added.get(tid, 0) + 1))
    if added:
        notes.append("plan: more graphics from the narration: " + ", ".join(f"{k} ×{v}" for k, v in sorted(added.items())))
    return shots, plate_budget


def vary_looks(shots: List[Any], layers: List[Dict[str, Any]], words: Sequence[Any], tally: Callable[[str], None]) -> List[Any]:
    """The same information in a different template every other time, so a long video does not show the same diagram twelve times:
    two-sided compare cards -> theories_split (two panels), a numeric compare or bar chart -> bar_race, a timeline -> discovery_timeline,
    every third context caption -> statement. Same words and numbers, same timing; only the look changes."""
    def swap(old: Dict[str, Any], tid: str, slots: Dict[str, Any]) -> None:
        NL, _ = _layer(tid, slots, float(old["start"]), float(old["end"]), words)
        layers[layers.index(old)] = NL
        tally(tid)

    seen = {"compare": 0, "bars": 0, "timeline": 0, "caption": 0}
    for L in list(layers):
        ty = L.get("type")
        try:
            if ty == "tm_compare" and L.get("mode") != "particles":
                seen["compare"] += 1
                if seen["compare"] % 2:
                    continue
                le, ri = L.get("left") or {}, L.get("right") or {}
                if L.get("mode") == "bars" and le.get("amount") and ri.get("amount"):
                    rows = [{"name": str(x.get("label", "")).upper(), "value": str(x.get("value", "")).upper(), "num": float(x.get("amount") or 0)} for x in (le, ri)]
                    swap(L, "bar_race", {"rows": rows, "max": max(r["num"] for r in rows) or 1, "label": "", "sub": ""})
                else:
                    swap(L, "theories_split", {"label": "", "left": str(le.get("label", "")).upper(), "left_sub": str(le.get("value", "")).upper(),
                                               "right": str(ri.get("label", "")).upper(), "right_sub": str(ri.get("value", "")).upper()})
            elif ty == "tm_bars" and L.get("rows"):
                seen["bars"] += 1
                if seen["bars"] % 2:
                    continue
                rows = [{"name": str(r.get("label", "")).upper(), "value": str(r.get("text", r.get("value", ""))).upper(), "num": float(r.get("value") or 0)}
                        for r in L["rows"][:6]]
                swap(L, "bar_race", {"rows": rows, "max": max([r["num"] for r in rows] + [1]), "label": str(L.get("title", "")).upper(), "sub": ""})
            elif ty == "tm_timeline" and L.get("events"):
                seen["timeline"] += 1
                if seen["timeline"] % 2:
                    continue
                ev = [{"name": str(e.get("label", "")).upper(), "value": str(e.get("year", "")), "num": float(e.get("year", 0))} for e in L["events"]]
                swap(L, "discovery_timeline", {"events": ev, "from_year": L.get("from", min(e["num"] for e in ev) - 1),
                                               "to_year": L.get("to", max(e["num"] for e in ev) + 1), "label": "", "sub": ""})
            elif ty == "tm_caption" and L.get("size", "small") == "small" and not L.get("anchor") and L.get("text"):
                seen["caption"] += 1           # a context caption (a lockup under a named picture is anchored or large and stays)
                if seen["caption"] % 3:
                    continue
                swap(L, "statement", {"label": str(L["text"]).upper(), "sub": str(L.get("sub", "")).upper()})
        except (ValueError, TypeError, KeyError):
            continue
    return shots
