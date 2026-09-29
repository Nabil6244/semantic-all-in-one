"""Find a mappable place in a line of narration (for the Local Visual Planner).

Deliberately conservative — a wrong map is worse than no map:
  * only names the bundled data knows (country, state/province, named
    region, or a US county written with "County"), never an AI guess,
  * only when the line talks about it AS A PLACE: the name follows a location
    word ("in Egypt", "along the Florida Panhandle") or is followed by one
    ("Nevada's desert", "the Ohio border"),
  * the whole capitalized name must match: "Colorado River" or "Florida State
    University" never become a map of Colorado or Florida.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .places import PlaceNotFound, find_place

_LOCATION_BEFORE = {
    "in", "across", "along", "near", "to", "from", "through", "into", "throughout", "within",
    "at", "around", "outside", "inside", "off", "over", "under", "toward", "towards", "beyond",
    "between", "entering", "crossing", "visit", "visited", "visiting", "reached",
}
_LOCATION_AFTER = {
    "state", "county", "region", "coast", "coastline", "border", "borders", "territory", "province",
    "desert", "mountains", "countryside", "shore", "shores",
}
_JOINERS = {"of", "and", "de", "del", "la"}
# Words that name a direction or a vague area, not a place — some provinces
# carry them as alternative names ("Southwest" is a Cameroonian province).
_GENERIC_NAMES = {
    "north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest", "central",
    "midwest", "center", "centre", "capital", "coast", "interior", "western", "eastern", "northern",
    "southern", "upper", "lower", "american", "national", "federal", "north east", "north west",
    "south east", "south west", "far north", "far west", "the west", "the south",
}
_CAP_RUN = re.compile(r"[A-Z][\w'\.-]*(?:\s+(?:(?:of|and|de|del|la)\b|[A-Z][\w'\.-]*))*")
_SKIP_WORDS = {"The", "A", "An", "It", "This", "That", "These", "Those", "In", "On", "At", "But", "And",
               "So", "Then", "Today", "Here", "There", "When", "While", "After", "Before", "During", "Its"}


@dataclass
class MapPick:
    prompt: str  # a map prompt, e.g. "United States of America > Florida"
    name: str  # the place as named in the narration


def _clean_run(run: str):
    """(name, led_by_location_word): drops a capitalized sentence-start word
    ("The", or a location word like "Across" — which then counts as the cue),
    trailing joiners, and a possessive 's."""
    words = run.split()
    led_by_location = False
    while words and (words[0] in _SKIP_WORDS or words[0].lower() in _LOCATION_BEFORE):
        led_by_location = led_by_location or words[0].lower() in _LOCATION_BEFORE
        words.pop(0)
    while words and words[-1].lower() in _JOINERS:
        words.pop()
    name = " ".join(words).strip(".,;:")
    if name.endswith("'s") or name.endswith("’s"):
        name = name[:-2]
    return name.strip(), led_by_location


def _prompt_for(place, name: str) -> Optional[str]:
    if place.kind == "country":
        return place.name
    if place.kind == "admin1":
        country = "United States of America" if place.country == "USA" else ""
        if not country:
            from .places import _dataset

            hit = next((f for f in _dataset("admin1") if f["n"] == place.name and f.get("iso") == place.country), None)
            country = (hit or {}).get("country", "")
        return f"{country} > {place.name}" if country else place.name
    if place.kind == "region" and place.state:
        return f"{place.state} > {place.name}"
    if place.kind == "county" and place.state:
        return f"{place.state} > {place.name}"
    return None


def _us_state_names() -> set:
    from .places import _dataset

    return {f["n"] for f in _dataset("admin1") if f.get("iso") == "USA"}


def _prefer_us_state(place, candidate: str, context: str):
    """"Georgia" is a country and a US state: in a script about other US
    states (or "America"/"U.S."), it means the state."""
    if place.kind != "country" or not context:
        return place
    states = _us_state_names()
    if candidate not in states:
        return place
    others = [n for n in states if n != candidate and re.search(rf"\b{re.escape(n)}\b", context)]
    if others or re.search(r"\b(America|American|United States|U\.S\.)", context):
        try:
            state = find_place(candidate, parent=find_place("United States of America"))
            return state if state.kind == "admin1" else place
        except PlaceNotFound:
            return place
    return place


def detect_place_in_title(title: str, *, context: str = "") -> Optional[MapPick]:
    """A fact/chapter title names its subject: "The Roof of Florida" ->
    Florida, "Florida's Rust Belt" -> Florida. No location word needed, but
    the same whole-name rule applies to each capitalized part."""
    for match in _CAP_RUN.finditer(title or ""):
        # "Florida's Rust Belt": the possessive ends one name and starts another.
        pieces = [p.strip() for p in re.split(r"['’]s\b", match.group(0)) if p.strip()]
        parts = [part for piece in pieces for part in re.split(r"\s+(?:of|and|de|del|la)\s+", piece)]
        for part in parts:
            name, _ = _clean_run(part)
            if not name or name.lower() in _GENERIC_NAMES:
                continue
            try:
                place = find_place(name)
            except PlaceNotFound:
                continue
            if place.kind == "county" and not name.lower().endswith(" county"):
                continue
            if place.kind == "admin1" and place.country != "USA" and place.name.lower() != name.lower():
                continue
            place = _prefer_us_state(place, name, context)
            prompt = _prompt_for(place, name)
            if prompt:
                return MapPick(prompt=prompt, name=name)
    return None


def detect_map_place(text: str, *, context: str = "") -> Optional[MapPick]:
    """``context``: the wider script, used only to read an ambiguous name
    (Georgia the state vs the country)."""
    text = text or ""
    for match in _CAP_RUN.finditer(text):
        name, led_by_location = _clean_run(match.group(0))
        if not name:
            continue
        before = re.findall(r"[A-Za-z']+", text[: match.start()].lower())[-2:]
        after = re.findall(r"[A-Za-z']+", text[match.end():].lower())[:2]
        # "the Florida Panhandle": the location word may sit one article back.
        cue = led_by_location or (before[-1:] and before[-1] in _LOCATION_BEFORE) or (
            len(before) == 2 and before[-1] == "the" and before[0] in _LOCATION_BEFORE
        ) or any(w in _LOCATION_AFTER for w in after)
        if not cue:
            continue
        # "between Arizona and Nevada": the pair isn't a place, each part is.
        for candidate in [name] + ([p.strip() for p in name.split(" and ")] if " and " in name else []):
            county = candidate.lower().endswith(" county")
            if candidate.lower() in _GENERIC_NAMES:
                continue
            try:
                place = find_place(candidate)
            except PlaceNotFound:
                continue
            if place.kind == "county" and not county:
                continue
            if place.kind == "admin1" and place.country != "USA" and place.name.lower() != candidate.lower():
                continue  # matched only an alternative spelling abroad: too easy to be wrong
            place = _prefer_us_state(place, candidate, context or text)
            prompt = _prompt_for(place, candidate)
            if prompt:
                return MapPick(prompt=prompt, name=candidate)
    return None
