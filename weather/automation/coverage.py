"""What the daily forecast covers: the 20 largest US metros (weather/data/metros.json), grouped in six regions.

weather/cities.py knows the cities of phase 1 (weather/data/cities.json). The metros add the rest of the top 20 WITHOUT editing that
file: all_cities() is both lists together, and install() adds the metros to find_city's table at run time (weather/layers/trend.py
calls it when the layer types load, so a beats.csv / weather_layers.csv naming "Boston, MA" reads and renders through the phase-1
code unchanged). The lasting fix belongs in weather/cities.py; the exact change is a request in docs/weather/agent_phase2.md."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from ..cities import City, cities, norm

DATA = Path(__file__).resolve().parent.parent / "data" / "metros.json"
REGIONS = ("Northeast", "Southeast", "Midwest", "South Central", "Mountain West", "Pacific")


@dataclass(frozen=True)
class Metro:
    rank: int
    city: City
    region: str
    office: str  # NWS forecast office id (FWD)
    office_name: str  # as the NWS names it ("Fort Worth/Dallas, TX")
    office_spoken: str  # as the script says it ("Fort Worth")
    county_fips: str  # the county the city centre is in: an alert listing it covers the city

    @property
    def key(self) -> str:
        return self.city.key

    @property
    def name(self) -> str:
        return self.city.name


@lru_cache(maxsize=1)
def metros() -> List[Metro]:
    """The covered metros, largest first."""
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    out = []
    for m in raw["metros"]:
        if m["region"] not in REGIONS:
            raise ValueError(f"metros.json: {m['name']} has region {m['region']!r} (use {', '.join(REGIONS)})")
        city = City(m["name"], m["state"], float(m["lat"]), float(m["lon"]), m["tz"], m["grid"], list(m["stations"]))
        out.append(Metro(int(m["rank"]), city, m["region"], m["office"], m["office_name"], m["office_spoken"], str(m["county_fips"])))
    return sorted(out, key=lambda m: m.rank)


def metro(key: str) -> Metro:
    for m in metros():
        if norm(m.key) == norm(key):
            return m
    raise KeyError(f"{key!r} is not one of the covered metros ({', '.join(m.key for m in metros())})")


def by_region() -> Dict[str, List[Metro]]:
    out: Dict[str, List[Metro]] = {r: [] for r in REGIONS}
    for m in metros():
        out[m.region].append(m)
    return out


def all_cities() -> Dict[str, City]:
    """Every city Weather can name: phase 1's cities.json, then the metros it does not have (cities.json wins for a city in both)."""
    out = dict(cities())
    for m in metros():
        out.setdefault(norm(m.key), m.city)
    return out


def install() -> None:
    """Make weather.cities.find_city know every metro (adds to its cached table; cities.json entries are kept as they are)."""
    table = cities()
    for m in metros():
        table.setdefault(norm(m.key), m.city)
