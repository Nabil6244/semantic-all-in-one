"""Ambience profile taxonomy for documentary-style scene beds."""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

# Primary smart-editing profile → target pick count when curating Sonniss source.
AMBIENCE_PROFILE_TARGETS: Dict[str, int] = {
    "city": 7,
    "nature": 6,
    "rain": 6,
    "room": 6,
    "technology": 5,
    "traffic": 5,
    "water": 5,
    "fire": 4,
    "transport": 5,
    "crowd": 4,
    "atmospheric": 5,
}

AMBIENCE_SHORTLIST_CAP = sum(AMBIENCE_PROFILE_TARGETS.values())  # 58

# Tags stored in catalog.json (first tag is primary profile for matching).
PROFILE_SECONDARY_TAGS: Dict[str, Tuple[str, ...]] = {
    "city": ("urban", "street", "downtown"),
    "nature": ("forest", "wind", "wilderness", "outdoor"),
    "rain": ("storm", "weather", "drizzle"),
    "room": ("indoor", "office", "quiet", "subtle"),
    "technology": ("lab", "digital", "machine", "electronic"),
    "traffic": ("highway", "road", "intersection"),
    "water": ("ocean", "river", "shore", "waves"),
    "fire": ("campfire", "crackle", "warm"),
    "transport": ("train", "subway", "airport", "station"),
    "crowd": ("people", "public", "busy"),
    "atmospheric": ("dark", "tension", "drone", "mysterious"),
}

# Ordered rules — first match wins (more specific profiles first).
_PROFILE_RULES: Sequence[Tuple[str, Tuple[str, ...]]] = (
    ("rain", (r"\brain\b", r"\bstorm\b", r"\bthunder\b", r"\bdrizzle\b", r"\bdownpour\b")),
    ("fire", (r"\bfire\b", r"\bfireplace\b", r"\bcampfire\b", r"\bcrackl", r"\bember\b")),
    ("water", (r"\bocean\b", r"\bwave\b", r"\bshore\b", r"\bbeach\b", r"\briver\b", r"\bunderwater\b", r"\bstream\b", r"\blake\b", r"\bwater\b")),
    ("transport", (r"\btrain\b", r"\bsubway\b", r"\bmetro\b", r"\bairport\b", r"\bstation\b", r"\bplatform\b")),
    ("traffic", (
        r"\bhighway\b", r"\btraffic\b", r"\bintersection\b", r"\bfreeway\b", r"\broad\b", r"\bmotorway\b",
        r"\bcar interior\b", r"\bdriving ambience\b", r"\bvehicle interior\b",
    )),
    ("crowd", (r"\bcrowd\b", r"\bpeople\b", r"\baudience\b", r"\bstadium\b", r"\bmarket\b")),
    ("atmospheric", (
        r"\bdark\b", r"\bdrone\b", r"\btension\b", r"\bhaunting\b", r"\bghostly\b",
        r"\batmospheric\b", r"\bmyster", r"\bominous\b", r"\bdeep\s*amb",
    )),
    ("technology", (
        r"\bserver\b", r"\bdata\s*center\b", r"\blab\b", r"\bcomputer\b", r"\bdigital\b",
        r"\belectronic\b", r"\bsci[\s\-]?fi\b", r"\bmachine\b", r"\btech\b",
    )),
    ("room", (r"\broom\b", r"\broomtone\b", r"\broom\s*tone\b", r"\bindoor\b", r"\bhallway\b", r"\blibrary\b", r"\bhouse\b", r"\boffice\b")),
    ("city", (r"\bcity\b", r"\burban\b", r"\bdowntown\b", r"\bstreet\b", r"\bskyline\b", r"\bnight\s*city\b")),
    ("nature", (
        r"\bforest\b", r"\bnature\b", r"\bbird\b", r"\bmeadow\b", r"\bwildlife\b",
        r"\bmountain\b", r"\bwind\b", r"\btree\b", r"\boutdoor\b",
    )),
)


def infer_ambience_profile(text: str) -> str:
    blob = re.sub(r"[_\-]+", " ", (text or "").lower())
    blob = re.sub(r"\s+", " ", blob).strip()
    for profile, patterns in _PROFILE_RULES:
        if any(re.search(p, blob, re.I) for p in patterns):
            return profile
    if re.search(r"\bambien", blob):
        return "room"
    return "room"


def ambience_tags_for_text(text: str, profile: str | None = None) -> List[str]:
    key = profile or infer_ambience_profile(text)
    tags: List[str] = [key]
    for extra in PROFILE_SECONDARY_TAGS.get(key, ()):
        if extra not in tags:
            tags.append(extra)
    blob = re.sub(r"[_\-]+", " ", (text or "").lower())
    for token in ("soft", "quiet", "distant", "night", "loop", "subtle", "gentle"):
        if re.search(rf"\b{token}\b", blob) and token not in tags:
            tags.append(token)
    return tags


def smart_editing_profile_tags() -> Dict[str, Tuple[str, ...]]:
    """Map smart-editing profile names to catalog tag hints."""
    out: Dict[str, Tuple[str, ...]] = {}
    for profile, extras in PROFILE_SECONDARY_TAGS.items():
        out[profile] = (profile, *extras)
    # Legacy aliases used in older catalog entries.
    out["room"] = ("room", "office", "indoor", "quiet", "subtle")
    out["city"] = ("city", "traffic", "urban", "street")
    out["crowd"] = ("crowd", "people", "room", "public", "busy")
    out["nature"] = ("nature", "wind", "forest", "outdoor", "wilderness")
    out["technology"] = ("technology", "office", "lab", "digital", "electronic")
    return out
