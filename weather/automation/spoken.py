"""Numbers and weather words as a narrator says them: 92 -> "ninety-two", 62 -> "in the low sixties", "Chance Showers And
Thunderstorms" -> "there is a chance of showers and thunderstorms". Pure functions; the script writer and its tests share them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}
DECADES = {1: "teens", 2: "twenties", 3: "thirties", 4: "forties", 5: "fifties", 6: "sixties", 7: "seventies", 8: "eighties", 9: "nineties"}
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
            11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth", 16: "sixteenth", 17: "seventeenth",
            18: "eighteenth", 19: "nineteenth", 20: "twentieth", 30: "thirtieth"}
STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
          "DE": "Delaware", "DC": "the District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
          "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
          "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
          "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
          "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
          "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
          "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico"}
# Pronunciation hints, written in brackets after the word the first time it appears (only names a narrator is likely to trip on).
HINTS = {"Maricopa": "mair-ih-KOH-puh", "Hennepin": "HEN-uh-pin", "Suffolk": "SUF-uk", "Hillsborough": "HILLS-bur-oh",
         "Natchitoches": "NAK-uh-tush", "Tchoupitoulas": "CHOP-uh-too-lus", "Puyallup": "pyoo-AL-up", "Willamette": "wil-AM-it",
         "Spokane": "spoh-KAN", "Boise": "BOY-see", "Des Moines": "deh MOYN", "Coeur d'Alene": "kor duh-LAYN"}


def words(n: int) -> str:
    """0..199 (and negatives) in words: 92 -> 'ninety-two', 104 -> 'one hundred four', -5 -> 'five below zero'."""
    n = int(n)
    if n < 0:
        return f"{words(-n)} below zero"
    if n < 20:
        return ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return TENS[t] + (f"-{ONES[o]}" if o else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return f"{ONES[h]} hundred" + (f" {words(r)}" if r else "")
    raise ValueError(f"{n} is out of range for a spoken temperature")


def ordinal(n: int) -> str:
    if n in ORDINALS:
        return ORDINALS[n]
    t, o = divmod(n, 10)
    return f"{TENS[t]}-{ORDINALS[o]}"


def band(n: int) -> Optional[str]:
    """'in the low sixties' for 60..63, 'mid' 64..66, 'upper' 67..69; None outside 10..99 (said exactly instead)."""
    if not 10 <= n <= 99:
        return None
    t, o = divmod(n, 10)
    return f"in the {'low' if o <= 3 else 'mid' if o <= 6 else 'upper'} {DECADES[t]}"


def in_band(phrase: str, n: int) -> bool:
    return band(n) == phrase


def temp(n: int, exact: bool) -> str:
    """A temperature after 'a high' / 'a low': 'near ninety-two' or 'in the low sixties'."""
    b = band(n)
    return b if (b and not exact) else f"near {words(n)}"


def state_list(codes: List[str], limit: int = 3) -> str:
    names = [STATES.get(c, c) for c in codes[:limit]]
    if len(codes) > limit:
        return ", ".join(names) + " and beyond"
    return join_and(names)


def join_and(items: List[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def event_phrase(event: str, count: int) -> str:
    """'Flood Watch', 3 -> 'flood watches'; 1 -> 'a flood watch'."""
    e = event.lower()
    if count == 1:
        return ("an " if e[0] in "aeiou" else "a ") + e
    for end, plural in (("watch", "watches"), ("warning", "warnings"), ("advisory", "advisories"), ("statement", "statements"), ("alert", "alerts")):
        if e.endswith(end):
            return e[: -len(end)] + plural
    return e + "s"


def hint(name: str, said: set) -> str:
    """The name with its pronunciation hint the first time it is said ('Maricopa [mair-ih-KOH-puh]'), else the name."""
    if name in HINTS and name not in said:
        said.add(name)
        return f"{name} [{HINTS[name]}]"
    return name


def strip_hints(text: str) -> str:
    return re.sub(r"\s*\[[^\]]*\]", "", text)


# ---- the NWS short forecast as words ----------------------------------------------------------------------------------------

SKY = ("sunny", "mostly sunny", "partly sunny", "partly cloudy", "mostly cloudy", "cloudy", "clear", "mostly clear", "fair", "overcast")
CERT_ORDER = {"slight": 1, "chance": 2, "likely": 3, "plain": 4}


@dataclass(frozen=True)
class Part:
    cert: str  # plain | slight | chance | likely
    noun: str  # 'showers and thunderstorms', 'mostly sunny', 'patchy fog'

    @property
    def sky(self) -> bool:
        return self.noun in SKY or self.noun in ("hot", "sunny and hot")

    @property
    def wet(self) -> bool:
        return any(w in self.noun for w in ("rain", "shower", "thunder", "drizzle", "snow", "sleet", "flurr", "freezing", "ice", "blizzard"))


def parse_short(short: str) -> List[Part]:
    """'Slight Chance Showers And Thunderstorms then Mostly Sunny' -> [Part(slight, showers and thunderstorms), Part(plain, mostly sunny)].
    Parts with the same weather keep the surer wording."""
    out: List[Part] = []
    for raw in re.split(r"\s+then\s+", (short or "").strip(), flags=re.I):
        s = " ".join(raw.lower().split())
        if not s:
            continue
        cert = "plain"
        if s.startswith("slight chance "):
            cert, s = "slight", s[len("slight chance "):]
        elif s.startswith("chance "):
            cert, s = "chance", s[len("chance "):]
        if s.endswith(" likely"):
            cert, s = "likely", s[: -len(" likely")]
        for pre in ("isolated ", "scattered ", "widely scattered "):
            if s.startswith(pre):
                s = s[len(pre):]
        s = s.replace("t-storms", "thunderstorms").replace("rain showers", "showers").replace("/", " and ")
        p = Part(cert, s)
        if out and out[-1].noun == p.noun:
            if CERT_ORDER[p.cert] > CERT_ORDER[out[-1].cert]:
                out[-1] = p
            continue
        out.append(p)
    return out or [Part("plain", "cloudy")]


def _be(noun: str) -> str:
    return "are" if noun.endswith("s") and not noun.endswith("ss") else "is"


def clause(part: Part, first: bool = True) -> str:
    """One part as a clause: 'it stays mostly sunny', 'showers are likely', 'there is a chance of thunderstorms'."""
    n = part.noun
    if part.sky:
        if n in ("hot", "sunny and hot"):
            return "it is sunny and hot" if first else "turning sunny and hot"
        adj = {"fair": "fair", "overcast": "overcast"}.get(n, n)
        return f"it stays {adj}" if first else f"turning {adj}"
    if part.cert == "slight":
        c = f"there is a slight chance of {n}"
    elif part.cert == "chance":
        c = f"there is a chance of {n}"
    elif part.cert == "likely":
        c = f"{n} {_be(n)} likely"
    elif part.wet:
        c = f"expect {n}"
    else:  # fog, haze, smoke, wind
        c = f"there is {n} around" if not n.startswith(("breezy", "windy", "blustery")) else f"it is {n}"
    return c if first else f"then {c}"


def condition_clause(short: str) -> str:
    parts = parse_short(short)[:2]
    return ", ".join(clause(p, i == 0) for i, p in enumerate(parts))


def noun_phrase(part: Part) -> str:
    """'a chance of showers', 'showers', 'sunshine' (for 'brings ...')."""
    if part.sky:
        return {"sunny": "sunshine", "mostly sunny": "mostly sunny skies", "clear": "clear skies"}.get(part.noun, f"{part.noun} skies")
    if part.cert == "slight":
        return f"a slight chance of {part.noun}"
    if part.cert == "chance":
        return f"a chance of {part.noun}"
    if part.cert == "likely":
        return f"likely {part.noun}"
    return part.noun


def category(short: str, high: int, pop: int) -> str:
    """The footage condition of a day: storm, snow, rain (wet at a chance of 30 % or more), fog, heat (90 F+), cold (40 F or less),
    sun or cloud."""
    parts = parse_short(short)
    wet = [p for p in parts if p.wet and p.cert != "slight"]
    if wet and pop >= 30:
        n = " ".join(p.noun for p in wet)
        if "thunder" in n:
            return "storm"
        if any(w in n for w in ("snow", "sleet", "flurr", "blizzard", "ice", "freezing")):
            return "snow"
        return "rain"
    if any(w in p.noun for p in parts for w in ("fog", "haze", "smoke")):
        return "fog"
    if high >= 90:
        return "heat"
    if high <= 40:
        return "cold"
    if any(w in p.noun for p in parts for w in ("breezy", "windy", "blustery")):
        return "wind"
    last_sky = [p.noun for p in parts if p.sky]
    if last_sky and any(w in last_sky[-1] for w in ("sunny", "clear", "fair", "hot")) and "partly" not in last_sky[-1]:
        return "sun"
    return "cloud"


def spoken_numbers(text: str) -> List[Tuple[str, int]]:
    """Every number spoken in the text with its value: [('ninety-two', 92), ...] (ordinals like 'thirteenth' are dates, not numbers)."""
    lookup = {words(n): n for n in range(0, 200)}
    out = []
    for m in re.finditer(r"\b(?:" + "|".join(re.escape(w) for w in sorted(lookup, key=len, reverse=True)) + r")\b", text.lower()):
        out.append((m.group(0), lookup[m.group(0)]))
    return out


def spoken_bands(text: str) -> List[str]:
    return re.findall(r"in the (?:low|mid|upper) (?:" + "|".join(DECADES.values()) + ")", text.lower())
