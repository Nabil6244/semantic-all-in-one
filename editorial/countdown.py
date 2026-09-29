"""Countdown ("35 wild facts") structure for normal-mode videos.

Detected from the narration itself, so it works the same for an AI plan and
for a CSV the user wrote:

  * fact headings — a sentence that starts with the fact's number:
        "34. The Roof of Florida."   "Number 34: the roof of Florida."
        "Fact 34 — The Roof of Florida"   "Number thirty-four. The roof..."
    At least three, numbered in order (counting down or up), or it isn't a
    countdown and nothing changes — so an ordinary "3 men died." never
    triggers it.
  * the hook — "Here are 35 wild facts about Florida" -> "35 WILD FACTS".

Each heading becomes an orange numbered tag ("34. THE ROOF OF FLORIDA",
bottom-left) and the hook a big yellow title, both timed to the moment the
narrator says them (see countdown_graphics).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

MIN_FACTS = 3
TAG_SECONDS = 3.8
TAG_AFTER_CUT_S = 0.3
HOOK_SECONDS = 2.6

_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD_NUM = (r"(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s-](?:one|two|three|four|five|six|"
             r"seven|eight|nine))?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
             r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|one hundred)")
# A heading starts a sentence: "34. Title", "#34 Title", "Number 34: Title",
# "Fact 34 - Title", "Number thirty-four. Title".
_HEADING = re.compile(
    r"(?:^|(?<=[.!?]\s)|(?<=[.!?]\"\s))\s*"
    r"(?:(?P<kw>number|no\.|fact|#)\s*)?"
    rf"(?P<num>\d{{1,3}}|{_WORD_NUM})"
    r"(?P<sep>\s*[.:)\-–—,]\s+|\s+(?=[A-Z]))"
    r"(?P<rest>[^.!?]*[.!?]?)",
    re.IGNORECASE,
)
_HOOK = re.compile(
    rf"\b(?P<num>\d{{1,3}}|{_WORD_NUM})\s+(?P<adj>(?:[A-Za-z'-]+\s+){{0,2}}?)"
    r"(?P<noun>facts|things|reasons|places|secrets|mysteries|myths|towns|cities|islands|animals|inventions|"
    r"events|ways|questions|stories|discoveries|locations|wonders|mistakes|disasters)\b",
    re.IGNORECASE,
)


def word_to_number(text: str) -> Optional[int]:
    t = (text or "").strip().lower().replace("-", " ")
    if t.isdigit():
        return int(t)
    if t == "one hundred":
        return 100
    parts = t.split()
    if len(parts) == 1:
        return _UNITS.get(parts[0], _TENS.get(parts[0]))
    if len(parts) == 2 and parts[0] in _TENS and parts[1] in _UNITS and 0 < _UNITS[parts[1]] < 10:
        return _TENS[parts[0]] + _UNITS[parts[1]]
    return None


@dataclass
class CountdownFact:
    number: int
    title: str
    scene_index: int  # index into the narrations list
    offset: float  # where in that scene's narration the heading starts (0..1)

    @property
    def tag_text(self) -> str:
        return f"{self.number}. {self.title}".upper() if self.title else f"{self.number}."


@dataclass
class CountdownHook:
    text: str
    scene_index: int
    offset: float


@dataclass
class Countdown:
    facts: List[CountdownFact] = field(default_factory=list)
    hook: Optional[CountdownHook] = None

    def fact_start_indices(self) -> List[int]:
        return [f.scene_index for f in self.facts]


def _title_from(rest: str) -> str:
    text = " ".join((rest or "").split()).strip(" .!?:;,-–—\"'")
    if not text:
        return ""
    words = text.split()
    if len(words) <= 7:
        return text
    try:
        from scene_graph.generator import _chapter_title

        title = _chapter_title(text)
    except Exception:
        title = ""
    return title if 2 <= len(title.split()) <= 7 else " ".join(words[:6])


def _offset(text: str, pos: int) -> float:
    before = len(text[:pos].split())
    total = max(1, len(text.split()))
    return round(min(0.95, before / total), 4)


def detect_countdown(narrations: Sequence[str]) -> Optional[Countdown]:
    """The countdown in these scene narrations (in order), or None."""
    facts: List[CountdownFact] = []
    for index, raw in enumerate(narrations):
        text = str(raw or "")
        for match in _HEADING.finditer(text):
            number = word_to_number(match.group("num"))
            if number is None or not (0 < number <= 200):
                continue
            is_word = not match.group("num").isdigit()
            if is_word and not match.group("kw"):
                continue  # "Thirty people died." is not a heading; "Number thirty" is
            if not match.group("kw") and not match.group("sep").strip():
                continue  # "3 Men Died" — a bare number needs its "." / ":" to be a heading
            facts.append(CountdownFact(number=number, title=_title_from(match.group("rest")),
                                       scene_index=index,
                                       offset=_offset(text, match.start("kw") if match.group("kw") else match.start("num"))))
    if len(facts) < MIN_FACTS:
        return None
    numbers = [f.number for f in facts]
    steps = [b - a for a, b in zip(numbers, numbers[1:])]
    descending = all(-2 <= s <= -1 for s in steps)
    ascending = all(1 <= s <= 2 for s in steps)
    if not (descending or ascending):
        return None
    countdown = Countdown(facts=facts)
    first = facts[0]
    intro = [str(n or "") for n in narrations[: first.scene_index]]
    lead = str(narrations[first.scene_index] or "")
    intro_text_by_scene = intro + [lead[: int(len(lead) * first.offset) or 0] if first.offset > 0 else ""]
    for index, text in enumerate(intro_text_by_scene):
        match = _HOOK.search(text)
        if not match:
            continue
        number = word_to_number(match.group("num"))
        if number is None:
            continue
        words = [str(number)] + match.group("adj").split() + [match.group("noun")]
        full = str(narrations[index] or "")
        countdown.hook = CountdownHook(text=" ".join(words).upper(), scene_index=index,
                                       offset=_offset(full, match.start()))
        break
    return countdown


def countdown_graphics(scenes: Sequence, countdown: Countdown) -> list:
    """GraphicSpecs for the fact tags + hook, timed on the editorial scenes
    (``scenes[i]`` matches ``narrations[i]`` given to detect_countdown)."""
    from graphics.schema import GraphicLifecycle, GraphicSpec, TextOverlaySpec

    def at(index: int, offset: float) -> float:
        scene = scenes[index]
        start, end = float(scene.start), float(scene.end)
        return round(start + max(0.0, end - start) * offset, 4)

    specs = []
    if countdown.hook is not None and countdown.hook.scene_index < len(scenes):
        t0 = at(countdown.hook.scene_index, countdown.hook.offset)
        specs.append(GraphicSpec(
            graphic_id="countdown_hook", decision="TEXT", role="TITLE",
            scene_number=str(scenes[countdown.hook.scene_index].scene_number),
            start=t0, end=round(t0 + HOOK_SECONDS, 4), track="GRAPHICS", reason="countdown hook",
            importance="critical", emphasis="dramatic", semantic_purpose="establish",
            text=TextOverlaySpec(role="TITLE", text=countdown.hook.text, start=t0, end=t0 + HOOK_SECONDS,
                                 animation="POP", metadata={"template": "countdown_hook"}),
            payload={"template": "countdown_hook"}, animation="POP", z_index=80,
            lifecycle=GraphicLifecycle(enter_s=0.22, hold_s=HOOK_SECONDS - 0.4, exit_s=0.18),
        ))
    for i, fact in enumerate(countdown.facts):
        if fact.scene_index >= len(scenes):
            continue
        t0 = at(fact.scene_index, fact.offset)
        if fact.offset <= 0.0:
            t0 = round(t0 + TAG_AFTER_CUT_S, 4)  # let the cut (often a zoom-blur) settle first
        end = t0 + TAG_SECONDS
        if i + 1 < len(countdown.facts) and countdown.facts[i + 1].scene_index < len(scenes):
            end = min(end, at(countdown.facts[i + 1].scene_index, countdown.facts[i + 1].offset) - 0.1)
        if end - t0 < 0.8:
            continue
        specs.append(GraphicSpec(
            graphic_id=f"countdown_tag_{fact.number}", decision="TEXT", role="CHAPTER",
            scene_number=str(scenes[fact.scene_index].scene_number),
            start=t0, end=round(end, 4), track="GRAPHICS", reason="countdown fact tag",
            importance="high", emphasis="strong", semantic_purpose="establish",
            text=TextOverlaySpec(role="CHAPTER", text=fact.tag_text, start=t0, end=end, animation="SLIDE_IN",
                                 metadata={"template": "countdown_tag"}),
            payload={"template": "countdown_tag", "number": fact.number}, animation="SLIDE_IN", z_index=78,
            lifecycle=GraphicLifecycle(enter_s=0.2, hold_s=max(0.4, end - t0 - 0.35), exit_s=0.15),
        ))
    return specs


def narrations_by_scene(rows: Sequence[dict]) -> Dict[str, str]:
    return {str(r.get("scene_number") or ""): str(r.get("script_segment") or "") for r in rows}
