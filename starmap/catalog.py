"""What a StarMap CSV may name: bodies, surface sites, a mission pack's events, craft, paths and orbits.

Everything here is DATA (starmap/catalog/*.json, starmap/packs/*.json); the engine knows none of it. A mission pack:

    { "id": "apollo11", "name": "Apollo 11", "met_zero": "...",
      "events":  { "launch": "1969-07-16T13:32:00Z", ... },          what a CSV's date column names
      "sites":   { "tranquility base": { "body": "moon", "lon": 23.473, "lat": 0.674, "label": "...", "aliases": [...] } },
      "trajectories": [ engine trajectory layers (illustrated generators or real samples) ],
      "craft":   { "csm": engine spacecraft layer fields },          shown by a CSV "craft" row
      "paths":   { "translunar_coast": { "of": trajectory id, "from": event, "to": event, "style": {...} } },
      "orbits":  { "lunar_orbit": { "body": "moon", "trajectory": id, "at": event, ... } },
      "craft_aliases": { "eagle": "lm" } }
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "catalog"
PACKS = HERE / "packs"


class CatalogError(ValueError):
    pass


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower().replace("’", "'"))


def available_packs() -> List[str]:
    return sorted(p.stem for p in PACKS.glob("*.json"))


@dataclass
class Place:
    """A camera target or a marker position. kind: body | site | pair."""
    kind: str
    body: str                      # the body (for a pair: the first)
    ref: str                       # the engine's target string: "moon", "moon@23.473,0.674", "earth+moon"
    label: str = ""
    lon: Optional[float] = None
    lat: Optional[float] = None
    other: str = ""                # a pair's second body


class Catalog:
    def __init__(self, pack: Optional[str] = None, pack_data: Optional[Dict[str, Any]] = None):
        self.bodies = json.loads((CATALOG / "bodies.json").read_text(encoding="utf-8"))
        self.world: List[Dict[str, Any]] = self.bodies["world"]
        self.body_ids = {b["id"] for b in self.world}
        self.aliases = {**{i: i for i in self.body_ids}, **{_norm(k): v for k, v in self.bodies.get("aliases", {}).items()}}
        self.sites: Dict[str, Dict[str, Any]] = {}
        self._site_alias: Dict[str, str] = {}
        self._add_sites(json.loads((CATALOG / "sites.json").read_text(encoding="utf-8"))["sites"])
        self.pack: Dict[str, Any] = {}
        if pack_data is not None:
            self.pack = pack_data
        elif pack:
            f = PACKS / f"{_norm(pack).replace(' ', '')}.json"
            if not f.exists():
                raise CatalogError(f"unknown mission pack {pack!r} (packs: {', '.join(available_packs()) or 'none'})")
            self.pack = json.loads(f.read_text(encoding="utf-8"))
        self._add_sites(self.pack.get("sites", {}))
        self.events: Dict[str, str] = {_norm(k): v for k, v in self.pack.get("events", {}).items()}
        self.craft: Dict[str, Dict[str, Any]] = {_norm(k): v for k, v in self.pack.get("craft", {}).items()}
        self.craft_alias = {**{k: k for k in self.craft}, **{_norm(k): _norm(v) for k, v in self.pack.get("craft_aliases", {}).items()}}
        self.paths: Dict[str, Dict[str, Any]] = {_norm(k): v for k, v in self.pack.get("paths", {}).items()}
        self.orbits: Dict[str, Dict[str, Any]] = {_norm(k): v for k, v in self.pack.get("orbits", {}).items()}
        self.trajectories = {t["id"]: t for t in self.pack.get("trajectories", [])}

    def _add_sites(self, sites: Dict[str, Dict[str, Any]]) -> None:
        for name, s in sites.items():
            key = _norm(name)
            self.sites[key] = s
            for a in [key] + [_norm(x) for x in s.get("aliases", [])]:
                self._site_alias[a] = key

    # ---- places -------------------------------------------------------------------------------------------------
    def place(self, name: str) -> Place:
        """A body ("moon"), a pair ("earth+moon"), a site ("tranquility base"), or body@lon,lat ("moon@23.47,0.67")."""
        raw = str(name).strip()
        key = _norm(raw)
        if not key:
            raise CatalogError("no place given")
        if "+" in key:
            a, b = [self.body(x) for x in key.split("+", 1)]
            return Place("pair", a, f"{a}+{b}", other=b)
        if "@" in key:
            body, at = key.split("@", 1)
            body = self.body(body)
            try:
                lon, lat = [float(x) for x in at.split(",")]
            except ValueError:
                raise CatalogError(f"{raw!r}: write body@longitude,latitude in degrees, e.g. moon@23.47,0.67") from None
            if not (-180 <= lon <= 360 and -90 <= lat <= 90):
                raise CatalogError(f"{raw!r}: longitude must be -180..360 and latitude -90..90")
            return Place("site", body, f"{body}@{lon},{lat}", lon=lon, lat=lat)
        if key in self.aliases:
            b = self.aliases[key]
            return Place("body", b, b, label=self._body_label(b))
        if key in self._site_alias:
            s = self.sites[self._site_alias[key]]
            return Place("site", s["body"], f"{s['body']}@{s['lon']},{s['lat']}", label=s.get("label", raw.upper()), lon=s["lon"], lat=s["lat"])
        raise CatalogError(f"unknown place {raw!r}" + self._suggest(key, list(self.aliases) + list(self._site_alias)))

    def body(self, name: str) -> str:
        key = _norm(name)
        if key in self.aliases:
            return self.aliases[key]
        raise CatalogError(f"unknown body {name!r}" + self._suggest(key, list(self.aliases)))

    def _body_label(self, b: str) -> str:
        return next((x.get("label", b.upper()) for x in self.world if x["id"] == b), b.upper())

    def body_radius_km(self, b: str) -> float:
        r = next(x for x in self.world if x["id"] == b)["radius"]
        return float(r.get("km") or 0) or float(r.get("ly", 0)) * 9.4607e12

    # ---- the mission pack ------------------------------------------------------------------------------------------
    def date(self, expr: str) -> str:
        """An ISO UTC date for: an ISO date, an event ("landing"), an event +/- HH:MM[:SS] ("landing-00:12:40"), or mission
        elapsed time ("T+102:45:40", needs the pack's met_zero)."""
        e = _norm(expr).replace(" ", "")
        m = re.fullmatch(r"t\+(\d+):(\d\d)(?::(\d\d))?", e)
        if m:
            if not self.pack.get("met_zero"):
                raise CatalogError(f"{expr!r}: mission time needs a mission pack with met_zero")
            return _iso(_parse_iso(self.pack["met_zero"]) + timedelta(hours=int(m[1]), minutes=int(m[2]), seconds=int(m[3] or 0)))
        m = re.fullmatch(r"([a-z0-9_'.-]+?)([+-])(\d+):(\d\d)(?::(\d\d))?", e)
        if m and _norm(m[1]) in self.events:
            delta = timedelta(hours=int(m[3]), minutes=int(m[4]), seconds=int(m[5] or 0))
            base = _parse_iso(self.events[_norm(m[1])])
            return _iso(base + delta if m[2] == "+" else base - delta)
        if e in self.events:
            return _iso(_parse_iso(self.events[e]))
        try:
            return _iso(_parse_iso(expr.strip()))
        except ValueError:
            pass
        known = ", ".join(sorted(self.events)) or "none (no mission pack)"
        raise CatalogError(f"unknown date {expr!r}: use an event ({known}), an event+HH:MM, T+HHH:MM:SS, or an ISO date like 1969-07-20T20:17:40Z")

    def craft_id(self, name: str) -> str:
        key = _norm(name)
        if key in self.craft_alias:
            return self.craft_alias[key]
        raise CatalogError(f"unknown craft {name!r}" + (self._suggest(key, list(self.craft_alias)) if self.craft else " (the CSV's plan row names no mission pack with craft)"))

    def path(self, name: str) -> Dict[str, Any]:
        key = _norm(name)
        if key not in self.paths:
            raise CatalogError(f"unknown path {name!r}" + (self._suggest(key, list(self.paths)) if self.paths else " (no mission pack paths)"))
        return self.paths[key]

    def orbit(self, name: str) -> Dict[str, Any]:
        key = _norm(name)
        if key not in self.orbits:
            raise CatalogError(f"unknown orbit {name!r}" + (self._suggest(key, list(self.orbits)) if self.orbits else " (no mission pack orbits)"))
        return self.orbits[key]

    @staticmethod
    def _suggest(key: str, options: List[str]) -> str:
        near = difflib.get_close_matches(key, options, n=3, cutoff=0.6)
        return f" (did you mean {', '.join(repr(n) for n in near)}?)" if near else ""


def _parse_iso(s: str) -> datetime:
    t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_seconds(a: str, b: str) -> float:
    """Seconds from date a to date b."""
    return (_parse_iso(b) - _parse_iso(a)).total_seconds()


def place_pair(p: Place) -> Tuple[str, str]:
    return p.body, p.other
