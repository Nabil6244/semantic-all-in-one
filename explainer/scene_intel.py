"""Scene intelligence for the Explainer: what place, period, architecture, people and mood does a narration beat describe, and can the composed library show it truthfully?

Three parts, all pure (no network, no files):
  * `SceneSpec`          what a beat describes. Built from the narration's words (`from_words`) and, when the CSV gives a scene note for the beat, from that note (`from_notes`, its values win).
                         No AI service is used.
  * `decide(spec)`       "compose" when a library set fits the place, period and architecture, else "flow" with the reasons: the beat gets a new image made for it.
  * `flow_prompt(spec)`  the image request for such a beat, written once per beat from the spec so every Flow image shares one style line.
  * `no_repeat(...)`     the same background + cast arrangement is never used in consecutive beats unless the narration asks for continuity.

Nothing here draws or renders; callers decide what to do with the answer."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# What the composed library can show truthfully, as data: a set can stand in for a beat only when the beat's place type is one of its `places`, its period falls in `years`, and nothing
# in the beat names an architecture the set does not have. Add a set here when a set is added to explainer/assets/scenes_v2.
LIBRARY: Dict[str, Dict[str, Any]] = {
    "barn":          {"places": {"farm", "rural", "field"},          "years": (1850, 2100), "architecture": {"generic"}},
    "border_wall":   {"places": {"border", "frontier", "checkpoint"}, "years": (1900, 2100), "architecture": {"generic"}},
    "mountain_pass": {"places": {"mountain", "pass", "highland"},    "years": (-5000, 2100), "architecture": {"generic"}},
    "old_town":      {"places": {"town", "village", "street"},       "years": (1850, 2100), "architecture": {"generic"}},
    "shallows":      {"places": {"coast", "shore", "lagoon", "sea"}, "years": (-5000, 2100), "architecture": {"generic"}},
    "snowy_village": {"places": {"village", "snow", "winter"},       "years": (1850, 2100), "architecture": {"generic"}},
    "station":       {"places": {"station", "railway", "train"},     "years": (1840, 2100), "architecture": {"generic"}},
}

ERA_YEARS = {"ancient": -500, "classical": 0, "medieval": 1100, "renaissance": 1500, "early modern": 1650, "colonial": 1700, "industrial": 1850, "modern": 1990}
YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2}|[2-9][0-9]{2})\b")


@dataclass
class SceneSpec:
    place: str = ""                    # "canal city on a lagoon"
    place_type: str = ""               # one of the LIBRARY place words, or "" when none fits
    region: str = ""                   # "Venice", "Korea"
    year: Optional[int] = None         # the period the beat is about (negative = BC)
    architecture: str = "generic"      # "Gothic palazzi", "Joseon hanok"; "generic" when nothing specific is called for
    people: List[str] = field(default_factory=list)       # "merchant in a wool cloak", "soldier"
    clothing: str = ""
    activity: str = ""
    objects: List[str] = field(default_factory=list)
    atmosphere: str = ""               # light and mood: "dusk, tense"
    source: str = "words"              # "words" or "csv"
    continues_previous: bool = False   # the narration itself says the scene goes on
    route: str = "auto"                # "auto" | "compose" | "flow": the CSV may force the route
    background: str = ""               # the CSV's own words for the backdrop, added to the Flow request
    looks: List[str] = field(default_factory=list)       # fixed descriptions of the cast (from the CSV cast rows), repeated in every request that has them

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _int_year(v: Any) -> Optional[int]:
    m = re.search(r"-?\d{1,4}", str(v or ""))
    if not m:
        return None
    n = int(m.group(0))
    return -abs(n) if re.search(r"\bbc\b|\bbce\b", str(v).lower()) else n


NOTE_KEYS = {"place": "place", "type": "place_type", "place_type": "place_type", "region": "region", "year": "year", "period": "year", "architecture": "architecture", "people": "people",
             "clothing": "clothing", "activity": "activity", "objects": "objects", "props": "objects", "mood": "atmosphere", "light": "atmosphere", "atmosphere": "atmosphere",
             "background": "background", "route": "route", "continues": "continues_previous", "looks": "looks"}


def from_notes(text: str, base: Optional[SceneSpec] = None) -> Optional[SceneSpec]:
    """The spec from a CSV scene note: `key: value` pairs separated by `;` or new lines, e.g. `place: canal city; type: coast; period: 1450; architecture: Gothic palazzi;
    people: merchant, doge; clothing: wool cloaks; mood: dusk`. Keys it does not know are ignored; the note's values win over `base` (the spec read from the words). None when the note
    has no known key (then it is only prose and the words decide)."""
    got: Dict[str, str] = {}
    for part in re.split(r"[;\n]", text or ""):
        k, sep, v = part.partition(":")
        key = NOTE_KEYS.get(k.strip().lower())
        if sep and key and v.strip():
            got[key] = v.strip()
    if not got:
        return None
    s = SceneSpec(**(base.to_dict() if base else {}))
    s.source = "csv"
    for key, v in got.items():
        if key == "year":
            s.year = _int_year(v) if _int_year(v) is not None else s.year
        elif key in ("people", "objects"):
            setattr(s, key, [x.strip() for x in v.split(",") if x.strip()])
        elif key == "looks":
            s.looks = [x.strip() for x in v.split("|") if x.strip()]
        elif key == "continues_previous":
            s.continues_previous = v.strip().lower() in ("yes", "true", "1", "y")
        elif key == "route":
            s.route = v.strip().lower() if v.strip().lower() in ("auto", "compose", "flow") else "auto"
        elif key == "place_type":
            s.place_type = v.lower()
        else:
            setattr(s, key, v)
    return s


def from_words(text: str, context_year: Optional[int] = None) -> SceneSpec:
    """A spec from the words alone: only the period (years and era words) and the place type are read; anything else stays empty/generic, which makes `decide` ask for a Flow image
    whenever the period is old or the beat names a place no set can be vouched for."""
    low = (text or "").lower()
    year = None
    ys = [int(y) for y in YEAR_RE.findall(low)]
    if ys:
        year = ys[0]
    else:
        for name, y in ERA_YEARS.items():
            if name in low:
                year = y
                break
    if year is None:
        year = context_year
    place_type = ""
    best = 0
    for words, label in (({"farm", "farmer", "farmers", "field", "fields", "harvest"}, "farm"), ({"village", "villages"}, "village"), ({"town", "towns", "street", "streets"}, "town"),
                         ({"border", "frontier", "checkpoint"}, "border"), ({"station", "railway", "train", "trains"}, "station"), ({"mountain", "mountains", "pass", "highlands"}, "mountain"),
                         ({"coast", "shore", "lagoon", "sea", "harbour", "harbor", "port"}, "coast")):
        hits = sum(1 for t in re.findall(r"[a-z]+", low) if t in words)
        if hits > best:
            best, place_type = hits, label
    named = re.findall(r"\b[A-Z][a-z]{3,}\b", text or "")          # a proper noun that is not the sentence's first word names a particular place or people
    region = named[1] if len(named) > 1 else ""
    return SceneSpec(place_type=place_type, region=region, year=year, source="words", architecture="specific" if region else "generic")


@dataclass
class Decision:
    route: str                         # "compose" | "flow"
    set_name: str = ""
    reasons: List[str] = field(default_factory=list)


def decide(spec: SceneSpec) -> Decision:
    """Compose from the library only when a set matches the place type, the period and the architecture; otherwise ask Flow, and say why."""
    reasons: List[str] = []
    if spec.route == "flow":
        return Decision("flow", "", ["the CSV asks for a made picture"])
    if not spec.place_type:
        reasons.append("the beat does not say what kind of place it is")
    if spec.architecture.lower() not in ("generic", ""):
        reasons.append(f"it needs {spec.architecture} architecture, which no library set has")
    if not reasons:
        for name, cap in LIBRARY.items():
            if spec.place_type not in cap["places"]:
                continue
            lo, hi = cap["years"]
            if spec.year is not None and not (lo <= spec.year <= hi):
                reasons.append(f"{name} cannot show the year {spec.year}")
                continue
            return Decision("compose", name)
        if not any(spec.place_type in cap["places"] for cap in LIBRARY.values()):
            reasons.append(f"no library set shows a {spec.place_type}")
    return Decision("flow", "", reasons)


def flow_prompt(spec: SceneSpec, style_line: str = "flat 2D documentary cartoon illustration, muted palette, soft light, no text, 16:9") -> str:
    """The Flow image request for a beat: every scene gets the same `style_line`, so a run's images look like one film."""
    bits = [spec.place or spec.place_type or ("" if spec.region else "a place"), f"{spec.region}" if spec.region else "", f"around {abs(spec.year)}{' BC' if spec.year < 0 else ''}" if spec.year is not None else "",
            f"{spec.architecture} architecture" if spec.architecture.lower() not in ("generic", "") else "", f"people: {', '.join(spec.people)}" if spec.people else "",
            f"wearing {spec.clothing}" if spec.clothing else "", "; ".join(spec.looks), spec.background, spec.activity, f"with {', '.join(spec.objects)}" if spec.objects else "", spec.atmosphere]
    return ", ".join(b for b in bits if b) + ". " + style_line


def arrangement(set_name: str, cast: Sequence[str]) -> Tuple[str, Tuple[str, ...]]:
    return set_name, tuple(sorted(cast))


def no_repeat(history: Sequence[Tuple[str, Tuple[str, ...]]], new: Tuple[str, Tuple[str, ...]], continues: bool = False, window: int = 3) -> bool:
    """True when `new` (a background and a cast) may be used: it is not one of the last `window` arrangements, unless the narration says the scene continues."""
    if continues:
        return True
    return new not in list(history)[-window:]
