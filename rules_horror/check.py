"""Story and screen checks. They only WARN (a list of plain sentences); nothing here ever blocks Generate or Render.
Story (docs/rules_horror/PLAN.md): hook, rules (card rows), rule 1 within 30-80 s, twist 17-37 % of the words from rule 7 on, a closing line that repeats the title.
Screen: every shot has something to look at, no shot is long, no card row is silent, each caption is short."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .planner import MAX_BEAT_S, SETS


def _words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9']+", str(text).lower()) if w]


def check_story(data: Dict[str, Any], align: Dict[str, Any], duration: float) -> List[str]:
    rows, spans, out = data["rows"], align["spans"], []
    if not rows:
        return ["The CSV has no rows."]
    cards = [i for i, r in enumerate(rows) if r["set"] == "card" or "rule_card" in r["action"].split("+")]
    if len(cards) != 7:
        out.append(f"The story has {len(cards)} rule card(s); the format uses 7 rules.")
    if cards:
        t1 = spans[cards[0]][0]
        if not (30 <= t1 <= 80):
            out.append(f"Rule 1 starts at {t1:.0f} s; the format puts it between 30 and 80 s.")
    if len(cards) >= 7:
        counts = [len(_words(r["line"])) for r in rows]
        total = sum(counts) or 1
        share = sum(counts[cards[6]:]) / total
        if not (0.17 <= share <= 0.37):
            out.append(f"{share * 100:.0f}% of the words come from rule 7 on; the twist normally takes 17-37%.")
    first = _words(" ".join(r["line"] for r in rows[:2]))
    last = _words(" ".join(r["line"] for r in rows[-4:]))        # the closing section: the title is repeated, then one last scare
    stop = {"a", "an", "the", "and", "to", "of", "in", "on", "you", "your", "if", "so", "it", "is"}
    key = {w for w in first if w not in stop and len(w) > 3}
    if key and len(key & set(last)) < max(1, len(key) // 3):
        out.append("The closing line does not repeat the title's words (usually 'So if you ever ...').")
    if not any(re.search(r"\b(third|most people|break)\b", r["line"].lower()) for r in rows[:cards[0] if cards else len(rows)]):
        out.append("No promise before the rules (for example 'most people break the third one').")
    return out


def check_screen(pl: Dict[str, Any]) -> List[str]:
    out, limit = [], float(pl.get("max_beat") or MAX_BEAT_S)
    for i, b in enumerate(pl["beats"]):
        dur = b["end"] - b["start"]
        if dur > limit + 0.05:
            out.append(f"Shot {i + 1} is {dur:.1f} s long (the limit is {limit:g} s).")
        if b["set"] not in SETS and not b["card"] and not b["figures"] and not b.get("layers"):
            out.append(f"Shot {i + 1} has nothing on screen.")
        if not b["card"] and not b["captions"] and dur > 1.0:
            out.append(f"Shot {i + 1} ({b['start']:.1f} s) has no caption phrase.")
        for c in b["captions"]:
            if len(c["text"].split()) > 8:
                out.append(f"A caption at {c['start']:.1f} s has more than 8 words.")
    still = 0.0
    for a, b in zip(pl["beats"], pl["beats"][1:]):
        # the same picture AND the same camera move: a part cut with the other angle (push in / pull out) counts as a change
        same = (a["set"] == b["set"] and a["figures"] == b["figures"] and a["marks"] == b["marks"] and not b["card"] and not a["card"]
                and (a["cam"]["push"] > 0) == (b["cam"]["push"] > 0) and a["cam"].get("focus") == b["cam"].get("focus") and a.get("layers") == b.get("layers"))
        still = still + (a["end"] - a["start"]) if same else 0.0
        if still > 8.0:
            out.append(f"The same picture stays on screen for over 8 s around {b['start']:.0f} s.")
            still = 0.0
    return out
