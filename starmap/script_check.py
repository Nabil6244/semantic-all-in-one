"""The script check: does the narration hold a viewer? Local and deterministic (no AI), so it runs on every Check plan and
from the command line before the voiceover is recorded (the voice follows the script word for word, so this is the moment
to fix it):

    hook       the first two sentences carry a question, a striking number, a superlative or stakes -- not a greeting
    opener     no "in this video", "welcome back", "today we will" in the first words (viewers leave on them)
    open loop  a question or a turn ("but", "here is the strange part") inside the first minute that the video answers later
    re-hooks   a fresh question, turn or reveal at least every RE_HOOK_S seconds of narration (at the spoken pace)
    sentences  none so long a listener loses its subject (LONG_SENTENCE words)
    payoff     the ending comes back to the opening (its question, its key words) or lands on "today" / "still"

    python3 -m starmap doctor script.txt          the report
    python3 -m starmap doctor script.txt --prompt the script doctor prompt for an AI, with the script and this report in it"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

WPS = 2.5                     # spoken words per second (the same pace the beat CSV assumes)
RE_HOOK_S = 60.0
LONG_SENTENCE = 38
_SENT = re.compile(r"[^.!?]+[.!?]*")
HOOK = re.compile(r"\?|\b\d[\d,.]*\b|\b(first|never|only|ever|biggest|largest|farthest|fastest|oldest|record|impossible|"
                  r"strange|secret|mystery|nobody|no one|died|lost|disaster|end of|last|billion|million|thousand|"
                  r"one|two|three|four|five|six|seven|eight|nine|ten|twenty|hundred)\b", re.I)
TURN = re.compile(r"\?|\b(but|until|suddenly|here is|here's|the problem|the strange|the twist|what (happened|nobody)|"
                  r"imagine|yet|instead|turns out|it turned out|surprising|shocking|incredibly|no one expected|"
                  r"which means|so how|so why|and then)\b", re.I)
BAD_OPENERS = re.compile(r"\b(in this video|in today's video|welcome back|hi everyone|hello everyone|hey guys|today we will|"
                         r"today we're going to|let's talk about|before we start|don't forget to subscribe)\b", re.I)
PAYOFF = re.compile(r"\?|\b(today|still|now|forever|one day|someday|remember)\b", re.I)
_STOP = set("the a an and or of to in on at by for with from is was are were be been it its this that these those as into "
            "than then so but if not no yes we you they he she i our their his her them us me my your would could should have has "
            "had will just about more most very there here what when which who".split())


@dataclass
class ScriptReport:
    score: int = 100
    findings: List[str] = field(default_factory=list)       # what to fix, most important first
    strengths: List[str] = field(default_factory=list)

    def to_text(self) -> str:
        out = [f"script score {self.score}/100"]
        out += [f"  + {s}" for s in self.strengths]
        out += [f"  - {f}" for f in self.findings]
        return "\n".join(out)


def _sentences(text: str) -> List[Tuple[str, int]]:
    """(sentence, index of its first word in the script)."""
    out, w = [], 0
    for m in _SENT.finditer(text or ""):
        s = m.group(0).strip()
        if s:
            out.append((s, w))
            w += len(s.split())
    return out


def _keywords(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z'-]{3,}", text.lower()) if w not in _STOP}


def check_script(text: str) -> ScriptReport:
    rep = ScriptReport()
    sents = _sentences(text)
    if not sents:
        rep.score, rep.findings = 0, ["the script is empty"]
        return rep
    words = len(text.split())
    first = " ".join(s for s, _ in sents[:2])
    if BAD_OPENERS.search(" ".join(text.split()[:25])):
        rep.score -= 20
        rep.findings.append("the opening wastes the first seconds (a greeting or 'in this video'): start on the most striking fact or question")
    if HOOK.search(first):
        rep.strengths.append("the first two sentences carry a hook (a question, a number, a superlative or stakes)")
    else:
        rep.score -= 25
        rep.findings.append(f"no hook in the first two sentences ({first[:90]!r}...): open with a question, a striking number or what is at stake")
    first_min = [s for s, w in sents if w / WPS <= 60]
    if any(TURN.search(s) for s in first_min[1:]):
        rep.strengths.append("an open loop inside the first minute (a question or a turn the video answers later)")
    else:
        rep.score -= 15
        rep.findings.append("no open loop in the first minute: raise a question the video will answer ('So how did...?', 'But...')")
    # re-hooks: the longest stretches with no question, turn or reveal
    marks = [w / WPS for s, w in sents if TURN.search(s) or (HOOK.search(s) and re.search(r"\?|\b(first|never|only|record|billion)\b", s, re.I))]
    marks = [0.0] + marks + [words / WPS]
    gaps = [(a, b) for a, b in zip(marks, marks[1:]) if b - a > RE_HOOK_S]
    for a, b in gaps[:6]:
        at = next((s for s, w in sents if w / WPS >= a + (b - a) / 2), sents[-1][0])
        rep.findings.append(f"{b - a:.0f} s with no new question or turn ({int(a // 60)}:{int(a % 60):02d}-{int(b // 60)}:{int(b % 60):02d}); "
                            f"add a re-hook around {at[:70]!r}")
    rep.score -= min(30, 6 * len(gaps))
    if not gaps and words / WPS > RE_HOOK_S:
        rep.strengths.append(f"a fresh question or turn at least every {RE_HOOK_S:.0f} s")
    long = [s for s, _ in sents if len(s.split()) > LONG_SENTENCE]
    if long:
        rep.score -= min(10, 2 * len(long))
        rep.findings.append(f"{len(long)} sentence(s) over {LONG_SENTENCE} words (hard to follow when spoken), e.g. {long[0][:70]!r}...")
    ending = " ".join(s for s, _ in sents[-3:])
    callback = _keywords(first) & _keywords(ending)
    if PAYOFF.search(ending) or len(callback) >= 2:
        rep.strengths.append("the ending pays off the opening" + (f" ({', '.join(sorted(callback)[:3])})" if callback else ""))
    else:
        rep.score -= 10
        rep.findings.append("the ending does not come back to the opening: answer its question, or land on what is true today")
    rep.score = max(0, rep.score)
    return rep
