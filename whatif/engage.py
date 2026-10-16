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

    last = {"dated": -1e9, "stage": -1e9, "question": -1e9, "ring": -1e9}
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
        free_plate = lambda a0, a1: plate_budget >= a1 - a0 and not any(x < a1 and a0 < y for x, y in plates())  # noqa: E731
        # a percentage on its own: a ring filling to it ("about 1 percent of Earth's air")
        m = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\b", sent, re.I)
        if m and t0 >= hook_s and added.get("ring_value", 0) < 3 and t0 - last.get("ring", -1e9) >= 90:
            t1 = min(t0 + 5.0, duration - 0.5)
            if free_plate(t0, t1) and 0 < float(m.group(1)) <= 100:
                rest = _clean(sent[m.end():].split(), 5)
                L, pl = _layer("ring_value", {"label": f"{m.group(1)}%", "sub": rest, "share": float(m.group(1)) / 100}, t0, t1, words)
                carved = carve(shots, shot_cls(id="", start=t0, end=t1, kind="plate", tint="cool", text=sent, cite=pl["cite"]), force=True)
                if carved:
                    shots, plate_budget = carved, plate_budget - (t1 - t0)
                    add(L); last["ring"] = t0
                    continue
        # "9 of the 17 astronauts" / "3 out of 4": a row of dots
        m = re.search(r"\b(\d{1,2}) (?:out )?of (?:the |its |their )?(\d{1,2})\b\s*([A-Za-z]+)?", sent)
        if m and t0 >= hook_s and 0 < int(m.group(1)) <= int(m.group(2)) <= 60 and added.get("dot_tally", 0) < 2:
            t1 = min(t0 + 5.0, duration - 0.5)
            if free_plate(t0, t1):
                L, pl = _layer("dot_tally", {"value_to": int(m.group(1)), "total": int(m.group(2)), "label": (m.group(3) or "").upper(), "sub": ""}, t0, t1, words)
                carved = carve(shots, shot_cls(id="", start=t0, end=t1, kind="plate", tint="cool", text=sent, cite=pl["cite"]), force=True)
                if carved:
                    shots, plate_budget = carved, plate_budget - (t1 - t0)
                    add(L)
                    continue
        # a quotation with its speaker: "...," said Carl Sagan
        m = re.search(r"[\"“]([^\"”]{8,110})[\"”]", sent)
        who = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){1,2})\b(?=[^.]{0,30}\b(?:said|wrote|called|asked|put it|once))|(?:said|wrote|asked)\s+([A-Z][a-z]+(?: [A-Z][a-z]+){1,2})", sent)
        if m and who and t0 >= hook_s and added.get("quote_person", 0) < 3:
            t1 = min(max(t0 + 4.5, float(words[b].end) + 0.5), t0 + 7.0, duration - 0.5)
            if free_plate(t0, t1):
                L, pl = _layer("quote_person", {"label": m.group(1).strip().upper(), "person": (who.group(1) or who.group(2)).upper(), "year": ""}, t0, t1, words)
                carved = carve(shots, shot_cls(id="", start=t0, end=t1, kind="plate", tint="cool", text=sent, cite=pl["cite"]), force=True)
                if carved:
                    shots, plate_budget = carved, plate_budget - (t1 - t0)
                    add(L)
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
        except (ValueError, TypeError, KeyError):
            continue
    return shots


COVER_MIN = 0.5               # a picture shot with graphics over less than half of it gets a line of its own
COVER_TYPES = ("tm_caption", "tm_title", "tm_metric", "tm_annotate", "tm_survival", "tm_mission", "tm_clock", "tm_gauge")


def _covered(s: Any, layers: Sequence[Dict[str, Any]]) -> float:
    spans = sorted((max(s.start, float(L["start"])), min(s.end, float(L["end"]))) for L in layers
                   if "start" in L and (L.get("type") in COVER_TYPES or (L.get("type") == "tm_template" and not L.get("plate", True)))
                   and float(L["start"]) < s.end and s.start < float(L["end"]))
    tot, cur = 0.0, None
    for a, b in spans:
        if cur and a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            if cur:
                tot += cur[1] - cur[0]
            cur = [a, b]
    if cur:
        tot += cur[1] - cur[0]
    return tot / max(0.1, s.length)


def cover_pictures(shots: Sequence[Any], layers: List[Dict[str, Any]], words: Sequence[Any], cl: Sequence[Tuple[int, int]], notes: List[str],
                   *, filler: set, tail: set, lead: float = 0.1) -> int:
    """Text on every picture (project 015 had 40 % of its runtime as pictures with nothing over them): a picture shot that graphics cover
    for less than half its length gets the key words of what the narrator says over it -- a caption, or every third time a bold statement --
    held to the shot's end (at most 6 s). Only the narration's own words are shown."""
    added = 0
    for s in shots:
        if s.kind not in ("image", "video", "globe", "craft", "hero") or s.length < 3.0 or _covered(s, layers) >= COVER_MIN:
            continue
        starts = [(a, b) for a, b in cl if s.start - 0.2 <= float(words[a].start) <= s.end - 2.0]
        if starts:
            a, b = starts[0]
        else:                   # no clause starts inside the shot: the words spoken while it is on screen
            inside = [i for i, w in enumerate(words) if s.start <= float(w.start) <= s.end - 1.5]
            if not inside:
                continue
            a, b = inside[0], inside[-1]
        phrase = [re.sub(r"[^\w'°%.\-]", "", w.text).strip(".-") for w in words[a:b + 1]]
        phrase = [p for p in phrase if p]
        while phrase and phrase[0].lower() in filler:
            phrase.pop(0)
        cut = phrase[:6]
        while len(cut) > 2 and (cut[-1].lower() in filler or cut[-1].lower() in tail):
            cut.pop()
        if len(cut) < 2:
            continue
        t0 = max(s.start + 0.25, float(words[a].start) - lead)
        t1 = min(s.end - 0.15, t0 + 6.0)
        if t1 - t0 < 2.2 or any(L.get("type") in ("tm_caption", "tm_title", "tm_metric", "tm_fade") and float(L["start"]) < t1 and t0 < float(L["end"]) for L in layers):
            continue
        text = " ".join(cut).upper()
        subj = (s.name or s.place or "").upper()
        if False:
            pass
        else:
            L = {"type": "tm_caption", "text": text, **({"sub": subj} if subj and subj not in text else {}), "start": round(t0, 3), "end": round(t1, 3),
                 "fade_in": 0.05, "fade_out": 0.3, "z": 5}
        layers.append(L)
        added += 1
    if added:
        notes.append(f"plan: {added} picture shot(s) with nothing over them got the narrator's key words on screen")
    return added


def coverage(shots: Sequence[Any], layers: Sequence[Dict[str, Any]], duration: float) -> float:
    """Share of the video with a graphic or text on screen (a diagram plate counts as covered)."""
    tot = 0.0
    for s in shots:
        tot += s.length if s.kind == "plate" else _covered(s, layers) * s.length
    return tot / max(0.1, duration)



# ---- the graphics director: every plan, CSV or not --------------------------------------------------------------------------------
TEXT_LAYOUTS = ("kicker_headline", "lower_third", "side_note", "underline_title", "two_tone_headline", "key_word", "boxed_fact", "typewriter_line", "statement")
REPEAT_GAP_S = 60.0           # never the same template twice within this
PLAIN_EVERY = 3               # one context line in three stays a plain caption (the calm reference look)
BOTTOM = ("lower_third", "key_word", "typewriter_line")
TOP_LEFT = ("kicker_headline", "underline_title", "two_tone_headline", "statement", "stage_header", "dated_caption", "mission_intro")


def _text_slots(tid: str, text: str, sub: str) -> Dict[str, str]:
    words = text.split()
    if tid == "two_tone_headline" and len(words) >= 3:
        h = (len(words) + 1) // 2
        return {"label": " ".join(words[:h]), "sub": " ".join(words[h:])}
    if tid == "key_word":                  # only a short line is shown big: the whole of it, never words picked out of it
        return {"label": text, "sub": sub}
    return {"label": text, "sub": sub}


def direct(shots: Sequence[Any], layers: List[Dict[str, Any]], words: Sequence[Any], duration: float, notes: List[str]) -> Dict[str, Any]:
    """The program's guarantee, whatever the CSV did: context lines rotate through the text layouts (never the same template within
    REPEAT_GAP_S, one in PLAIN_EVERY stays a plain caption), and every minute has at least one template. Same words, same timing."""
    def used_near(tid: str, t: float) -> bool:
        return any(L.get("type") == "tm_template" and L["template"]["id"] == tid and abs(float(L["start"]) - t) < REPEAT_GAP_S for L in layers)

    def corner_busy(tid: str, t0: float, t1: float) -> bool:
        if tid in TOP_LEFT:
            return any(L.get("type") == "tm_template" and L["template"]["id"] in TOP_LEFT and float(L["start"]) < t1 and t0 < float(L["end"]) for L in layers)
        if tid in BOTTOM:          # a photo's caption, a craft's name or a picture lockup already owns the bottom of the frame
            return any((L.get("type") == "tm_caption" and (L.get("size") in ("photo", "large") or L.get("anchor")))
                       or (L.get("type") == "tm_template" and L["template"]["id"] in BOTTOM + ("big_number_lower",))
                       for L in layers if float(L.get("start", 0)) < t1 and t0 < float(L.get("end", 0)))
        if tid == "boxed_fact":
            return any(L.get("type") in ("tm_mission", "tm_clock", "tm_gauge") and float(L.get("start", 0)) < t1 and t0 < float(L.get("end", 1e9)) for L in layers)
        return False

    k = 0
    swapped = 0
    rot = 0
    context = [L for L in sorted(layers, key=lambda L: float(L.get("start", 0)))
               if L.get("type") == "tm_caption" and not L.get("auto") and L.get("size", "small") == "small" and not L.get("anchor") and L.get("text")]
    fades = [(float(L["start"]), float(L["end"])) for L in layers if L.get("type") == "tm_fade"]
    context = [L for L in context if not any(a < float(L["end"]) and float(L["start"]) < b for a, b in fades)]   # nobody sees text in a fade to black
    for L in context:
        k += 1
        if k % PLAIN_EVERY == 0:
            continue
        t0, t1 = float(L["start"]), float(L["end"])
        for n in range(len(TEXT_LAYOUTS)):
            tid = TEXT_LAYOUTS[(rot + n) % len(TEXT_LAYOUTS)]
            if tid == "key_word" and len(str(L["text"]).split()) > 3:
                continue
            if used_near(tid, t0) or corner_busy(tid, t0, t1):
                continue
            NL, _ = _layer(tid, _text_slots(tid, str(L["text"]).upper(), str(L.get("sub", "")).upper()), t0, max(t1, t0 + 3.5), words)
            layers[layers.index(L)] = NL
            rot = (rot + n + 1) % len(TEXT_LAYOUTS)
            swapped += 1
            break
    # every minute at least one template: a minute without one turns its first remaining caption into a free layout
    empty = []
    for m0 in range(0, int(duration), 60):
        m1 = min(duration, m0 + 60)
        if any(L.get("type") == "tm_template" and m0 <= float(L["start"]) < m1 for L in layers):
            continue
        cap = next((L for L in layers if L.get("type") == "tm_caption" and not L.get("auto") and m0 <= float(L["start"]) < m1 and L.get("text")), None)
        done = False
        if cap is not None:
            t0, t1 = float(cap["start"]), float(cap["end"])
            for tid in TEXT_LAYOUTS:
                if tid == "key_word" and len(str(cap["text"]).split()) > 3:
                    continue
                if not used_near(tid, t0) and not corner_busy(tid, t0, t1):
                    NL, _ = _layer(tid, _text_slots(tid, str(cap["text"]).upper(), str(cap.get("sub", "")).upper()), t0, max(t1, t0 + 3.5), words)
                    layers[layers.index(cap)] = NL
                    swapped += 1
                    done = True
                    break
        if not done:
            empty.append(m0 // 60 + 1)
    tl = [L for L in layers if L.get("type") == "tm_template"]
    stats = {"templates": len(tl), "different": len({L["template"]["id"] for L in tl}), "per_min": round(len(tl) / max(1.0, duration / 60), 1),
             "minutes_without": empty}
    notes.append(f"plan: graphics director: {swapped} line(s) in varied text layouts; {stats['templates']} templates, {stats['different']} different, "
                 f"{stats['per_min']} a minute" + (f"; minutes with none: {empty}" if empty else ""))
    return stats



# ---- the readout card and counting numbers ------------------------------------------------------------------------------------
READOUT_NAMES = {"key": "KEY NUMBERS", "temperature": "TEMPERATURE", "pressure": "AIR PRESSURE", "distance": "DISTANCE", "speed": "SPEED", "duration": "TIME",
                 "light": "LIGHT TRAVEL TIME", "mass": "MASS", "age": "YEARS AGO", "years": "YEARS", "percent": "SHARE", "count": "COUNT"}


def readout_card(layers: List[Dict[str, Any]], metrics: Sequence[Any], duration: float, notes: List[str], *, title: str = "") -> bool:
    """Every video gets the reference's pinned card (V4 'DISTANCE TO THE EDGE', V5 'YOUR WEIGHT') unless it already has an instrument:
    the kind of number the narration keeps coming back to (3+ values of the same kind and unit) becomes a top-right card whose reading
    updates -- and counts -- each time the narrator gives a new value. Every value is one the narration says."""
    if any(L.get("type") in ("tm_mission", "tm_survival", "tm_clock", "tm_gauge") for L in layers):
        return False
    groups: Dict[Tuple[str, str], List[Any]] = {}
    for m in metrics:
        if m.kind in ("ratio",) or not re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", str(m.shown)):
            continue
        groups.setdefault((m.kind, m.unit), []).append(m)
    best = max(groups.items(), key=lambda kv: (len({str(m.shown) for m in kv[1]}), len(kv[1])), default=None)
    series = bool(best) and len(best[1]) >= 3 and len({str(m.shown) for m in best[1]}) >= 2
    if series:
        (kind, unit), ms = best
    else:
        # no single quantity the story follows: the KEY NUMBERS card -- each number the narrator gives, with its kind, in turn
        ms = [m for m in metrics if m.kind != "ratio" and re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", str(m.shown))]
        if len(ms) < 4:
            return False
        kind, unit = "key", ""
    ms = sorted(ms, key=lambda m: m.t)
    keys = []
    for m in ms:
        if not series:
            v = float(str(m.shown).replace(",", ""))
            if keys and abs(keys[-1]["value"] - v) < 1e-9 and keys[-1]["unit"] == m.unit.upper():
                continue
            keys.append({"t": round(max(0.0, m.t - 0.1), 3), "value": int(v) if v.is_integer() else v, "unit": m.unit.upper(),
                         "label": READOUT_NAMES.get(m.kind, m.kind.upper()), "status": "", "stage": 0})
            continue
        v = float(str(m.shown).replace(",", ""))
        if keys and abs(keys[-1]["value"] - v) < 1e-9:
            continue
        keys.append({"t": round(max(0.0, m.t - 0.1), 3), "value": int(v) if v.is_integer() else v, "unit": unit.upper(), "label": READOUT_NAMES.get(kind, kind.upper()),
                     "status": "", "stage": 0})
    if len(keys) < 2:          # three mentions, at least two different readings: the card changes at least once
        return False
    kicker = READOUT_NAMES.get(kind, kind.upper())          # never a cut-off title: the card says what it shows
    keys = [k for k in keys if k["t"] >= 20.0] or keys[-2:]  # the opening (title card, hook) has the frame to itself
    if len(keys) < 2:
        return False
    layers.append({"type": "tm_mission", "auto": True, "kicker": kicker, "stages": [], "keys": keys,
                   "start": keys[0]["t"], "end": round(min(duration, keys[-1]["t"] + 45.0), 3), "z": 11})
    notes.append(f"plan: readout card '{'KEY NUMBERS' if kind == 'key' else READOUT_NAMES.get(kind, kind.upper())}' pinned top-right with {len(keys)} readings from the narration")
    return True


def count_up(layers: List[Dict[str, Any]]) -> int:
    """Every number on screen counts up to its value (the reference counters): an automatic callout's value, or a CSV number written as
    text ("6 MBAR", "1.5×", "-63 °C") whose leading number can be read."""
    n = 0
    for L in layers:
        if L.get("type") != "tm_metric" or L.get("count") or L.get("rows"):
            continue
        shown = str(L.get("value") if L.get("value") is not None else L.get("text") or "")
        m = re.match(r"^\s*([≈~]?)\s*(-?\d[\d,]*(?:\.\d+)?)\s*(.*)$", shown)
        if not m or re.match(r"^\s*(?:[-–—]|to\b)\s*\d", m.group(3)) or re.search(r"\d\s*[/:]\s*\d", shown):
            continue                      # a range ("3–22 MIN"), a fraction or a time stays as written
        num = float(m.group(2).replace(",", ""))
        dec = len(m.group(2).split(".")[1]) if "." in m.group(2) else 0
        unit = (m.group(3) + (" " + str(L.get("unit")) if L.get("value") is not None and L.get("unit") else "")).strip()
        L["count"] = {"from": 0, "to": num, "decimals": dec, "s": 1.2}
        L["unit"] = unit
        L["value"] = m.group(1) + m.group(2)       # kept: the renderer needs a value; the count wins while it runs
        L.pop("text", None)
        n += 1
    return n
