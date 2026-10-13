"""The cities Weather can name ('Dallas, TX'), from weather/data/cities.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

DATA = Path(__file__).resolve().parent / "data" / "cities.json"

US_STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR "
             "PA RI SC SD TN TX UT VT VA WA WV WI WY PR").split()


@dataclass(frozen=True)
class City:
    name: str
    state: str
    lat: float
    lon: float
    tz: str
    grid: str
    stations: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.name}, {self.state}"


@lru_cache(maxsize=1)
def cities() -> Dict[str, City]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))["cities"]
    return {norm(f"{c['name']}, {c['state']}"): City(c["name"], c["state"], float(c["lat"]), float(c["lon"]), c["tz"], c["grid"],
                                                     list(c.get("stations") or [])) for c in raw}


def norm(text: str) -> str:
    name, _, state = str(text).partition(",")
    return f"{' '.join(name.split()).lower()},{state.strip().upper()}"


def find_city(text: str) -> City:
    c = cities().get(norm(text))
    if c is None:
        known = ", ".join(sorted(v.key for v in cities().values()))
        raise KeyError(f"unknown city {text!r}: write it as 'City, ST' (known: {known}; add more to weather/data/cities.json)")
    return c
