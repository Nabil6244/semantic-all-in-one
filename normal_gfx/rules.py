"""More narration rules for Normal Video graphics: variants of facts the planners already read, and two new rules. Every graphic shows words or numbers the
narrator said, verbatim or as the extractors already read them; nothing is written for the graphic.

VARIANTS (same fact, another gfx-core template, so a long video does not repeat one look; the least-used look in the video comes first)
  big_number -> stat_countup | counter_corner            the number and its label; the unit moves to the small line
  ring_percent -> gold_stat                              the same percentage, a serif gold numeral
  name_bar -> lower_kicker                               the same person and role
  strong line (Doc Style "quote") -> text_* | headline_wash | quote_boxed   the narrator's own sentence, as one of 12 text styles (short lines only)
NEW RULES (placed in free time, with the same pacing as the other planners)
  end_question   a question the narrator asks (4-14 words), words popping in on a darkened frame
  chapter_words  "Part two", "Chapter 3", "Step one" ...: the part title, huge, word by word
"""

from __future__ import annotations

import copy
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import gfx_templates as G

TEXT_STYLES = ["text_slam", "text_stamp", "text_typewriter", "text_word_pop", "text_underline", "text_split", "text_glow", "text_outline", "text_box",
               "text_sweep", "text_stack", "headline_wash"]
STRONG_MAX_WORDS = 9
_PART = re.compile(r"^\s*(?P<k>Part|Chapter|Step|Stage|Phase|Day|Round|Lesson)\s+(?P<n>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b", re.I)
_QUESTION_WORDS = (4, 14)


def _public(tid: str) -> Dict[str, Any]:
    return G._footage_backing(copy.deepcopy(G._public(G.get(tid))))


def _swap(ev: Dict[str, Any], tid: str, slots: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The same event (time, id, replaces) in another template, or None when that template cannot take the slots."""
    try:
        t = G.get(tid)
    except ValueError:
        return None
    slots = {k: v for k, v in slots.items() if k in t.get("slots", {})}
    for k, spec in (t.get("slots") or {}).items():       # an optional line the narration gave nothing for is blank, never the template's example
        if k not in slots and not spec.get("required") and isinstance(spec.get("default"), str):
            slots[k] = ""
    if not G._required_slots_filled(t, slots):
        return None
    out = dict(ev, template=_public(tid), slots=slots)
    out.pop("cues", None)
    return out


class Rotation:
    """Picks, among a fact's looks, the one used least so far in this video (ties: the listed order)."""
    def __init__(self) -> None:
        self.used: Dict[str, int] = {}

    def pick(self, options: Sequence[str]) -> List[str]:
        order = sorted(range(len(options)), key=lambda i: (self.used.get(options[i], 0), i))
        return [options[i] for i in order]

    def took(self, tid: str) -> None:
        self.used[tid] = self.used.get(tid, 0) + 1


def _unit_line(slots: Dict[str, Any]) -> str:
    return " ".join(x for x in (str(slots.get("unit") or "").strip(), str(slots.get("sub") or "").strip()) if x)


def adapt(ev: Dict[str, Any], rot: Rotation) -> Dict[str, Any]:
    """The event in the least-used look of its fact (see VARIANTS); unchanged when nothing else fits."""
    tid = ev.get("template", {}).get("id")
    slots = ev.get("slots") or {}
    candidates: List[Tuple[str, Dict[str, Any]]] = []
    if tid == "big_number" and not slots.get("prefix"):
        sub = _unit_line(slots)
        base = {"value": slots.get("value"), "label": slots.get("label", ""), "sub": sub}
        candidates = [("big_number", slots), ("stat_countup", base), ("counter_corner", dict(base, anchor="tr"))]
    elif tid == "ring_percent" and isinstance(slots.get("value"), (int, float)):
        candidates = [("ring_percent", slots), ("gold_stat", {"value": slots["value"], "unit": "%", "dec": 0, "label": str(slots.get("label") or slots.get("title") or "")})]
    elif tid == "name_bar":
        candidates = [("name_bar", slots), ("lower_kicker", {"title": slots.get("label", ""), "sub": slots.get("sub", ""), "kicker": ""})]
    elif tid == "quote_boxed" and ev.get("id", "").startswith("ngfx_doc_quote") and len(str(slots.get("text", "")).split()) <= STRONG_MAX_WORDS:
        text = str(slots.get("text", ""))
        candidates = [("quote_boxed", slots)] + [(s, {"title": text} if s == "headline_wash" else {"text": text}) for s in TEXT_STYLES]
    if len(candidates) < 2:
        return ev
    by_id = dict(candidates)
    for choice in rot.pick([c[0] for c in candidates]):
        new = ev if choice == tid else _swap(ev, choice, by_id[choice])
        if new is not None:
            rot.took(choice)
            return new
    return ev


def _free(a: float, b: float, busy: Sequence[Tuple[float, float]]) -> bool:
    return all(b + G.MIN_GAP_AFTER_S <= x or a - G.MIN_GAP_AFTER_S >= y for x, y in busy)


def new_events(words: Sequence[Tuple[str, float, float]], total: float, busy: List[Tuple[float, float]], placed: Sequence[Dict[str, Any]],
               start_index: int = 0) -> List[Dict[str, Any]]:
    """end_question and chapter_words in time nothing else uses. `busy` = every window already taken (it grows as events are added)."""
    out: List[Dict[str, Any]] = []
    asked = 0
    for text, a, b in G.sentences(words):
        if a < G.FIRST_AT_S:
            continue
        spoken = text.strip()
        n = len(spoken.split())
        kind = None
        m = _PART.match(spoken)
        if m:
            kind = ("chapter_words", {"text": " ".join(spoken.split()[:2]).upper().rstrip(",.:;")})
        elif spoken.endswith("?") and _QUESTION_WORDS[0] <= n <= _QUESTION_WORDS[1] and asked < 2:
            kind = ("end_question", {"text": spoken.upper(), "kicker": ""})
        if kind is None:
            continue
        tid, slots = kind
        t = G.get(tid)
        hold = min(float(t.get("hold", 4)), max(3.0, (b - a) + 2.0))
        t0, t1 = a + 0.1, min(a + 0.1 + hold, total)
        if t1 - t0 < 2.4 or not _free(t0, t1, busy):
            continue
        everyone = sorted(list(placed) + out, key=lambda e: e["t_in"])
        if any(t0 - e["t_out"] < G.MIN_SPACING_S and e["t_in"] - t1 < G.MIN_SPACING_S for e in everyone):
            continue
        if sum(1 for e in everyone if t0 - 60 < e["t_in"] <= t0) >= G.MAX_PER_MINUTE:
            continue
        ev = {"id": f"ngfx_{tid}_{start_index + len(out) + 1}", "type": "map_template", "template": _public(tid), "slots": slots, "t_in": round(t0, 3),
              "t_out": round(t1, 3), "over_footage": True}
        if not G._required_slots_filled(t, slots):
            continue
        out.append(ev)
        busy.append((t0, t1))
        busy.sort()
        asked += 1 if tid == "end_question" else 0
    return out
