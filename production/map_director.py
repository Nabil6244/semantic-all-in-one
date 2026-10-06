"""Map Director — decides whether a narration beat EARNS a map, and what that map should communicate.

A planning layer only. It never renders: its output is the existing map prompt format
("Florida > Florida Panhandle | camera: zoom_out", see map_scene/spec.py), consumed unchanged by the existing map
renderers (map_scene for normal / Overscaled / Exp Solar; pakMap and Hybrid have their own map-led directors).

How a decision is made (deterministic — no AI):
  1. A place must be found by the existing conservative detector (map_scene.detect: bundled borders only, the name
     must be used AS a place). No detected place -> no map. The director never invents geography.
  2. The line's geographic intent is read from what it says about the place:
       locate    where something is ("lies on the coast", "north of", "in the heart of")
       move      something goes there ("moved to", "spread to", "sailed for")
       route     from one real place to another ("from Egypt to Syria")
       distance  how far ("400 miles", "far from")
       scale     how big ("stretches across", "the size of", "spans")
       boundary  borders / territory ("the border", "annexed", "split between")
       change    geography over time ("the empire expanded", "by 1900")
  3. A place the film has ALREADY shown earns another map only when the line adds geographic information (one of the
     intents above). Merely naming a place again ("Back in Texas, the governor said...") is not a reason for a map.
     The first time the story arrives somewhere, the map establishes it.
  4. The intent picks the camera: on a first arrival the map establishes WHERE (push in) unless the line is about how
     big the place is (pull out). On a later map, scale and distance pull OUT, locate / move / boundary push IN,
     route and change drift.
Pacing (at most ~one map per 30 s, never two in a row) stays with the callers, unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Set

INTENTS = {
    "route": r"\bfrom\s+(?:the\s+)?[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)*\s+(?:to|into|toward|towards)\s+(?:the\s+)?[A-Z]",
    "distance": r"\b\d[\d,.]*\s*(?:miles?|km|kilomet(?:er|re)s?)\b|\b(?:far from|away from|halfway between|distance)\b",
    "scale": r"\b(?:stretch(?:es|ing)?|spans?|spanning|the size of|square (?:miles|kilomet(?:er|re)s)|larger than|"
             r"smaller than|covers?|covering|vast|sprawl(?:s|ing)?|across the (?:whole|entire)?\s*(?:country|continent|region|state))\b",
    "boundary": r"\b(?:border(?:s|ed|ing)?|boundar(?:y|ies)|frontier|territor(?:y|ies)|annex(?:ed|ation)?|partition(?:ed)?|"
                r"occupied|split between|divided between|claimed by|landlocked)\b",
    "locate": r"\b(?:located|lies|lying|sits|situated|nestled|tucked|on the (?:coast|edge|banks|shores?)|"
              r"(?:north|south|east|west)(?:ern)? (?:of|part of|edge of|tip of|coast)|heart of|corner of|capital of|"
              r"at the mouth of|along the (?:coast|border|river))\b",
    "move": r"\b(?:moved to|spread (?:to|into|across)|sailed (?:to|for)|marched (?:to|on|into)|fled to|migrat\w+ to|"
            r"travel+ed to|arrived in|headed (?:to|for|north|south|east|west)|expanded into|invaded|shipped to|flew to)\b",
    "change": r"\b(?:empire|expanded|shrank|grew to|by (?:1[5-9]|20)\d\d|over the (?:next|following) (?:decade|century|years))\b",
}
_COMPILED = {k: re.compile(v, re.IGNORECASE if k != "route" else 0) for k, v in INTENTS.items()}
CAMERA_FOR_INTENT = {"scale": "zoom_out", "distance": "zoom_out", "route": "drift", "change": "drift",
                     "boundary": "zoom_in", "locate": "zoom_in", "move": "zoom_in", "establish": "zoom_in"}
_INTENT_ORDER = ("route", "scale", "distance", "boundary", "change", "locate", "move")


@dataclass
class MapDecision:
    use_map: bool
    reason: str
    intent: str = ""  # one of INTENTS, or "establish" (first arrival), or "" when no map
    intents: List[str] = field(default_factory=list)
    place: str = ""  # as named in the narration
    prompt: str = ""  # the existing map prompt format, ready for the map renderers
    camera: str = "zoom_in"
    confidence: float = 0.0
    pick: object = None  # the detector's MapPick (callers that need the raw place)

    def to_dict(self) -> dict:
        return {"use_map": self.use_map, "reason": self.reason, "intent": self.intent, "intents": self.intents,
                "place": self.place, "prompt": self.prompt, "camera": self.camera, "confidence": round(self.confidence, 2)}


def geographic_intents(text: str) -> List[str]:
    found = [k for k in _INTENT_ORDER if _COMPILED[k].search(text or "")]
    return found


def _base_prompt(prompt: str) -> str:
    return (prompt or "").split("|", 1)[0].strip()


class MapDirector:
    """One per plan: remembers which places the film has already shown."""

    def __init__(self, *, detect: Optional[Callable] = None, context: str = "") -> None:
        if detect is None:
            from map_scene.detect import detect_map_place as _plain

            detect = (lambda text, _p=_plain, _c=context: _p(text, context=_c))
        self._detect = detect
        self.shown: Set[str] = set()
        self.decisions: List[MapDecision] = []

    def note_shown(self, prompt: str) -> None:
        """A map the author (or a countdown title) placed: later lines about the same place are repeats."""
        base = _base_prompt(prompt)
        if base:
            self.shown.add(base.lower())

    def decide(self, narration: str) -> MapDecision:
        text = (narration or "").strip()
        try:
            pick = self._detect(text) if text else None
        except Exception:
            pick = None
        if pick is None:
            d = MapDecision(False, "No mappable place is named as a place in this line.")
            self.decisions.append(d)
            return d
        base = _base_prompt(getattr(pick, "prompt", ""))
        intents = geographic_intents(text)
        repeat = base.lower() in self.shown
        if repeat and not intents:
            d = MapDecision(False, f"{pick.name} was already shown and this line adds no geographic information.",
                            place=pick.name, pick=pick)
            self.decisions.append(d)
            return d
        if not repeat:
            # First arrival: the map's job is to establish WHERE — push in, unless the line is explicitly about how big
            # the place is ("stretches across", "the size of"), which needs the wide view.
            intent = "scale" if "scale" in intents else "establish"
        else:
            intent = intents[0]
        camera = CAMERA_FOR_INTENT.get(intent, "zoom_in")
        prompt = base if camera == "zoom_in" else f"{base} | camera: {camera}"
        confidence = min(1.0, 0.55 + 0.15 * len(intents) + (0.15 if not repeat else 0.0))
        reason = (f"First time the story is in {pick.name}: establish where it is." if intent == "establish"
                  else f"The line is about {intent} ({', '.join(intents)}) — a map shows it better than footage.")
        d = MapDecision(True, reason, intent=intent, intents=intents, place=pick.name, prompt=prompt, camera=camera,
                        confidence=confidence, pick=pick)
        self.shown.add(base.lower())
        self.decisions.append(d)
        return d
