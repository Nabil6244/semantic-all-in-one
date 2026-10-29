"""What idea does a beat need the audience to understand? Deterministic rules, no network, no model.

Six internal signals (never user-selectable styles): spatial, quantitative, comparative, dialogue, evidence, cause. A beat gets the scores of each and, when one clearly leads, an `idea`.
The result steers the choice between a cartoon scene, footage, a map and a board (select.py) and, later, the composition recipe; with `DirectorOptions.meaning` off nothing here is called.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

IDEAS = ("spatial", "quantitative", "comparative", "dialogue", "evidence", "cause")      # the tie-break order too

SPATIAL = frozenset("""invaded invade invading marched march marching sailed sail sailing crossed crossing retreated retreat advanced advance landed landing border borders frontier route routes
north south east west northern southern eastern western coast coastline territory territories region regions across toward towards capital""".split())
QUANT_WORDS = frozenset("""million millions billion billions thousand thousands hundred hundreds percent percentage half double doubled tripled quarter third tons tonnes dollars pounds
majority minority total average rate rates number numbers""".split())
COMPARE_STRONG = frozenset("than versus compared unlike whereas".split())          # one of these is a comparison on its own
COMPARE = frozenset("""both either instead rather stronger weaker bigger smaller larger richer poorer faster slower better worse older younger more less fewer greater
same different difference similar opposite contrast""".split())
COMPARE_PHRASES = ("on the other hand", "as opposed to", "while the", "compared to", "compared with", "in contrast", "the same as", "twice as", "times as")
DIALOGUE = frozenset("said says asked asks told tells replied answered shouted whispered declared argued begged warned promised claimed announced cried".split())
EXCHANGE = frozenset("met meeting demanded refused negotiated negotiation talks debated debate argued agreed signed ordered commanded confronted accused persuaded convinced threatened".split())
EVIDENCE = frozenset("""painting paintings photograph photographs photo portrait document documents letter letters diary diaries records record archive archives newspaper newspapers
treaty manuscript manuscripts inscription inscriptions testimony according historians historian evidence sources source witness witnesses reported wrote written""".split())
CAUSE = frozenset("because therefore thus hence consequently caused causes causing leads leading resulted results meant means due triggered sparked forced reason why".split())
CAUSE_PHRASES = ("as a result", "which meant", "which means", "that is why", "that's why", "this led to", "led to", "ended up", "so that", "in order to", "because of", "due to", "as a consequence")
TIME_UNITS = frozenset("year years decade decades century centuries month months week weeks day days hour hours minute minutes".split())
NUMBER_WORDS = frozenset("two three four five six seven eight nine ten eleven twelve twenty thirty forty fifty sixty seventy eighty ninety".split())


@dataclass
class Meaning:
    scores: Dict[str, int] = field(default_factory=dict)
    idea: str = ""                              # "" when no signal leads clearly: the older selection rules decide alone
    why: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {"idea": self.idea, "scores": {k: v for k, v in self.scores.items() if v}, "why": self.why}


def _is_year(t: str) -> bool:
    return t.isdigit() and len(t) == 4 and 1000 <= int(t) <= 2100


def classify(tokens: Sequence[str], text: str = "", has_place: bool = False, has_named: bool = False) -> Meaning:
    """Score one beat. `tokens` are its lower-case words, `text` the script text of its sentences (quote marks survive there), `has_place` / `has_named` say a map place / a named person was spoken."""
    toks = [t for t in tokens if t]
    low = " " + " ".join(toks) + " "
    sc = {k: 0 for k in IDEAS}
    why: List[str] = []

    def hit(idea: str, n: int, reason: str) -> None:
        sc[idea] += n
        why.append(f"{idea}+{n}: {reason}")

    sp = [t for t in toks if t in SPATIAL]
    if sp:
        hit("spatial", min(len(sp), 3), "movement/direction words " + ",".join(sorted(set(sp))[:3]))
    if has_place:
        hit("spatial", 2, "a map place is spoken")
    # a number that counts time ("200 years ago", "after 10 days") is a date, not a quantity of things
    nums = [t for k, t in enumerate(toks) if t.isdigit() and not _is_year(t) and not (k + 1 < len(toks) and toks[k + 1] in TIME_UNITS)]
    qw = [t for t in toks if t in QUANT_WORDS]
    nw = [t for t in toks if t in NUMBER_WORDS]
    if nums:
        hit("quantitative", 3, "a spoken number " + nums[0])
    if qw:
        hit("quantitative", min(2 * len(qw), 4), "quantity words " + ",".join(sorted(set(qw))[:3]))
    if nw and (qw or nums):
        hit("quantitative", 1, "a counted amount")
    cp = [t for t in toks if t in COMPARE]
    cph = [p for p in COMPARE_PHRASES if (" " + p + " ") in low]
    cs = [t for t in toks if t in COMPARE_STRONG]
    if cs:
        hit("comparative", 3, "comparison word " + cs[0])
    if cp:
        hit("comparative", min(len(cp), 2), "comparison words " + ",".join(sorted(set(cp))[:3]))
    if cph:
        hit("comparative", 3, "phrase '" + cph[0] + "'")
    quoted = bool(re.search(r"[\"“”]\s*[^\"“”]{3,}\s*[\"“”]", text or ""))
    dw = [t for t in toks if t in DIALOGUE]
    if quoted:
        hit("dialogue", 4, "a quotation in the script")
    if dw:
        hit("dialogue", 2 * min(len(dw), 2), "speech verbs " + ",".join(sorted(set(dw))[:2]))
    ex = [t for t in toks if t in EXCHANGE]
    if ex:
        hit("dialogue", 1, "people deal with each other: " + ",".join(sorted(set(ex))[:2]))
    ev = [t for t in toks if t in EVIDENCE]
    if ev:
        hit("evidence", min(2 * len(ev), 4), "evidence words " + ",".join(sorted(set(ev))[:3]))
    if has_named and ev:
        hit("evidence", 1, "a named subject is also spoken")
    ca = [t for t in toks if t in CAUSE]
    cap = [p for p in CAUSE_PHRASES if (" " + p + " ") in low]
    if ca:
        hit("cause", min(2 * len(ca), 4), "cause words " + ",".join(sorted(set(ca))[:3]))
    if cap:
        hit("cause", 2, "phrase '" + cap[0] + "'")
    best = max(IDEAS, key=lambda k: (sc[k], -IDEAS.index(k)))
    ordered = sorted(sc.values(), reverse=True)
    lead = ordered[0] - (ordered[1] if len(ordered) > 1 else 0)
    idea = best if sc[best] >= 3 and lead >= 2 else ""            # a weak or tied signal decides nothing
    return Meaning(scores=sc, idea=idea, why=why)


# What each idea means for the choice of a visual (select.py consults these; an idea of "" changes nothing).
# A cartoon scene acts out people and events; a quantity or a comparison reads better as a board diagram, so those ideas never become a cartoon or a footage beat.
NOT_CARTOON = frozenset({"quantitative", "comparative"})
NOT_FOOTAGE = frozenset({"quantitative", "comparative", "cause"})
CARTOON_BONUS = {"dialogue": 3}
FOOTAGE_BONUS = {"evidence": 3}
