"""The last word on what a board shows as text, after every composer has run: whichever pass wrote a phrase, it must read as a finished thought.

`finish_texts(cues)` trims a phrase that stops on a word that needs more after it ("buried on the", "heavy concentrations of", "remains dangerously")
and drops what is left when it says nothing by itself ("after", "becomes"). Cues an arrow points at keep their text, trimmed."""

from __future__ import annotations

import re
from typing import List, Sequence

from . import lexicon as LX

LINKING = frozenset("becomes become became remains remain remained seems seem seemed gets get makes make keeps keep".split())
NUMBER_WORDS = frozenset("two three four five six seven eight nine ten eleven twelve twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion "
                         "trillion dozen half".split())
TRAILING = LX.STOP | LX.DANGLING_END | LINKING | frozenset("very more most less least such only even just also still rather quite per".split())
TEXT_KINDS = ("type", "title", "header", "chip", "caption", "card")


LEADS_ON = LX.STOP - frozenset("and or but".split())      # after a verdict word, these mean it is not a verdict ("lies a canyon", "enough to drive", "trapped beneath")


def stands_alone(words, g: int, sent_end: int) -> bool:
    """The word at g ends its thought (the sentence ends, or "and" / "but" follows): only then is it a verdict or a cry ("it was all lies", not "lies a canyon")."""
    if g >= sent_end or g + 1 >= len(words):
        return True
    return _tok(words[g + 1][0]) not in LEADS_ON


def _tok(w: str) -> str:
    return re.sub(r"[^\w']", "", w.lower())


def _adverb(t: str) -> bool:
    return len(t) > 4 and t.endswith("ly") and t not in ("only", "early", "family", "italy", "supply", "assembly", "july", "apply", "rally", "ally", "belly")


def _says_something(raw: Sequence[str]) -> bool:
    """at least two content words, a number, or one name ("Stibnite")"""
    content = [r for r in raw if _tok(r) and _tok(r) not in LX.STOP and _tok(r) not in LX.WEAK]
    return len(content) >= 2 or any(re.search(r"\d", r) or _tok(r) in NUMBER_WORDS for r in raw) or (len(content) == 1 and content[0][:1].isupper() and len(content[0]) > 3)


def finish_phrase(text: str) -> str:
    """The phrase with its unfinished tail trimmed, or "" when nothing left says anything. Line breaks are layout and are kept.
    A count of nothing ("0 metric") says nothing; "15 year" (a 15-year plan) reads "15-year"."""
    if re.match(r"\s*0(?![\d.,%])", text or ""):
        return ""
    text = re.sub(r"\b(\d+) (year|month|week|day|mile|foot|ton)\b(?!s)", r"\1-\2", text or "")
    raw = text.replace("\n", " \n ").split(" ")
    raw = [r for r in raw if r]
    while raw and (raw[-1] == "\n" or ((_tok(raw[-1]) in TRAILING or _adverb(_tok(raw[-1]))) and not re.search(r"\d", raw[-1]))):
        raw.pop()
    if not raw or not _says_something([r for r in raw if r != "\n"]):
        return ""
    return " ".join(raw).replace(" \n ", "\n").rstrip(",;:-")


def finish_texts(cues: list) -> int:
    """Every text cue finished in place; a type / caption / title that says nothing is removed. -> how many cues were changed."""
    pointed = {c.src for c in cues if c.kind == "arrow"} | {c.dst for c in cues if c.kind == "arrow"}
    changed = 0
    keep = []
    for c in cues:
        tag = c.kind == "visual" and (c.params or {}).get("style") == "tag"
        if (c.kind in TEXT_KINDS or tag) and c.text and not (c.params or {}).get("verbatim"):
            new = finish_phrase(c.text)
            if new != c.text:
                changed += 1
                if not new and c.id not in pointed and not (c.kind == "card" and c.asset):
                    continue
                c.text = new or c.text if c.id in pointed else new
        keep.append(c)
    cues[:] = keep
    return changed


WAR_CTX = frozenset("""war wars army armies soldier soldiers troops battle battles enemy enemies invasion invaded invaders fought fighting weapons rebels siege conquest
conquered military forces navy regiment cavalry infantry tanks bombs combat""".split())
POWER_CTX = frozenset("king kings queen emperor empire empires kingdom kingdoms ruler rulers rule ruled government governments monarchy republic throne capital regime dynasty".split())
ESCAPE_CTX = frozenset("prison prisoner captured capture exile exiled escape escaped freedom free jail chains".split())
# a picture word with more than one sense: its icon shows only when a word of that sense is said close by ("crushed ore" is not a battle, "the United States" is not a castle)
SENSE = {**{w: ("prop:swords", WAR_CTX) for w in "crushed crush fought fight fighting attack attacked captured destroyed won win wins victory victories clash clashes resist "
                                                 "resistance defeat defeated defeating conflicts fighters battle battles".split()},
         **{w: ("prop:cannon", WAR_CTX) for w in "fire fired force forces guns gun".split()},
         **{w: ("prop:castle", POWER_CTX) for w in "state states territory territories capital".split()},
         **{w: ("prop:key", ESCAPE_CTX) for w in "returned regained escaped opportunity".split()}}
SENSE_WINDOW = 10


def icon_in_sense(words, g: int, asset: str) -> bool:
    """False when the word at g picked `asset` in a sense the narration is not using here."""
    t = _tok(words[g][0])
    rule = SENSE.get(t)
    if rule is None or not asset.endswith(rule[0].split(":", 1)[1]):
        return True
    if rule[0] == "prop:castle" and g > 0 and _tok(words[g - 1][0]) == "united":
        return False
    near = {_tok(words[j][0]) for j in range(max(0, g - SENSE_WINDOW), min(len(words), g + SENSE_WINDOW + 1)) if j != g}
    return bool(near & rule[1])


def drop_icons_out_of_sense(cues: list, words, start: float, end: float) -> int:
    """Icons (tile / circle pictures) whose word is used in another sense are removed. -> how many."""
    bw = [i for i, w in enumerate(words) if start - 1e-6 <= w[1] < end - 1e-6]
    pointed = {c.src for c in cues if c.kind == "arrow"} | {c.dst for c in cues if c.kind == "arrow"}
    keep, n = [], 0
    for c in cues:
        idx = (c.anchor or {}).get("index")
        if c.kind in ("visual", "icon") and c.asset and c.id not in pointed and isinstance(idx, int) and 0 <= idx < len(bw) and not icon_in_sense(words, bw[idx], c.asset):
            n += 1
            continue
        keep.append(c)
    cues[:] = keep
    return n
