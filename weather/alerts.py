"""NWS alerts -> areas to draw. An alert either carries its own polygon (most warnings for storms and floods), or names the
counties it covers by their SAME codes (0 + state FIPS + county FIPS), which are drawn with the US county outlines the app
already ships (map_scene/data/us_counties.json.gz, Census cartographic boundaries). Marine-zone alerts have neither; they are
left out and reported (marine areas are not part of phase 1)."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

# Hazard colours of the NWS watch/warning map (weather.gov map legend). Anything not listed falls back by severity.
ALERT_COLORS = {
    "Tornado Warning": "#FF0000", "Tornado Watch": "#FFFF00",
    "Severe Thunderstorm Warning": "#FFA500", "Severe Thunderstorm Watch": "#DB7093",
    "Flash Flood Warning": "#8B0000", "Flash Flood Watch": "#2E8B57", "Flood Warning": "#00FF00", "Flood Watch": "#2E8B57",
    "Flood Advisory": "#00FF7F", "Coastal Flood Warning": "#228B22", "Coastal Flood Advisory": "#7CFC00",
    "Coastal Flood Statement": "#6B8E23",
    "Extreme Wind Warning": "#FF8C00", "Special Marine Warning": "#FFA500", "Snow Squall Warning": "#C71585",
    "Hurricane Warning": "#DC143C", "Hurricane Watch": "#FF00FF", "Tropical Storm Warning": "#B22222", "Tropical Storm Watch": "#F08080",
    "Storm Surge Warning": "#B524F7", "Storm Surge Watch": "#DB7FF7",
    "Extreme Heat Warning": "#C71585", "Excessive Heat Warning": "#C71585", "Extreme Heat Watch": "#800000",
    "Excessive Heat Watch": "#800000", "Heat Advisory": "#FF7F50",
    "Winter Storm Warning": "#FF69B4", "Winter Storm Watch": "#4682B4", "Winter Weather Advisory": "#7B68EE",
    "Blizzard Warning": "#FF4500", "Ice Storm Warning": "#8B008B", "Lake Effect Snow Warning": "#008B8B",
    "Extreme Cold Warning": "#0000FF", "Extreme Cold Watch": "#5F9EA0", "Cold Weather Advisory": "#AFEEEE",
    "Wind Chill Warning": "#B0C4DE", "Wind Chill Advisory": "#AFEEEE",
    "Freeze Warning": "#483D8B", "Freeze Watch": "#00FFFF", "Frost Advisory": "#6495ED",
    "High Wind Warning": "#DAA520", "High Wind Watch": "#B8860B", "Wind Advisory": "#D2B48C",
    "Red Flag Warning": "#FF1493", "Fire Weather Watch": "#FFDEAD",
    "Dense Fog Advisory": "#708090", "Air Quality Alert": "#808080", "Dust Storm Warning": "#FFE4C4",
    "Beach Hazards Statement": "#40E0D0", "Rip Current Statement": "#40E0D0", "High Surf Advisory": "#BA55D3",
    "Special Weather Statement": "#FFE4B5",
}
SEVERITY_COLORS = {"Extreme": "#C8102E", "Severe": "#F28C28", "Moderate": "#F2C230", "Minor": "#7DB5E8"}


def alert_color(event: str, severity: str = "") -> str:
    return ALERT_COLORS.get(event) or SEVERITY_COLORS.get(severity) or "#B0B0B0"


def _counties_file() -> Path:
    try:
        from map_scene.render import _find

        found = _find("map_scene/data/us_counties.json.gz")
        if found is not None:
            return found
    except Exception:
        pass
    return Path(__file__).resolve().parent.parent / "map_scene" / "data" / "us_counties.json.gz"


@lru_cache(maxsize=1)
def county_shapes() -> Dict[str, Any]:
    """FIPS (5 digits) -> {"name", "state", "polys": MultiPolygon coordinates}."""
    raw = json.loads(gzip.open(_counties_file()).read().decode("utf-8"))
    out = {}
    for f in raw["features"]:
        g = f["g"]
        out[str(f["fips"])] = {"name": f["n"], "state": f.get("state", ""),
                               "polys": [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]}
    return out


@dataclass
class AlertArea:
    id: str  # the NWS alert id (URL)
    event: str
    severity: str
    headline: str
    sent: str
    expires: str
    ends: str
    sender: str
    how: str  # "polygon" | "counties"
    polys: list = field(default_factory=list)  # MultiPolygon coordinates
    counties: List[str] = field(default_factory=list)  # FIPS, when drawn from counties

    @property
    def color(self) -> str:
        return alert_color(self.event, self.severity)

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in ("id", "event", "severity", "headline", "sent", "expires", "ends", "sender", "how", "polys", "counties")}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AlertArea":
        return AlertArea(**d)


@dataclass
class AlertSet:
    areas: List[AlertArea]
    skipped: List[str]  # "Gale Warning (marine zone, no county)" ...


def alert_areas(feature_collection: Dict[str, Any], *, events: Optional[List[str]] = None) -> AlertSet:
    """Every land alert in an NWS FeatureCollection as an area to draw. `events` keeps only those event names."""
    areas, skipped = [], []
    shapes = None
    for f in feature_collection.get("features", []):
        p = f.get("properties") or {}
        event = p.get("event", "")
        if events and event not in events:
            continue
        base = dict(id=str(p.get("id") or f.get("id") or ""), event=event, severity=p.get("severity", ""), headline=p.get("headline") or "",
                    sent=p.get("sent") or "", expires=p.get("expires") or "", ends=p.get("ends") or "", sender=p.get("senderName") or "")
        g = f.get("geometry")
        if g and g.get("type") in ("Polygon", "MultiPolygon"):
            areas.append(AlertArea(**base, how="polygon", polys=[g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]))
            continue
        same = [s[-5:] for s in (p.get("geocode") or {}).get("SAME", []) if len(s) == 6]
        shapes = shapes if shapes is not None else county_shapes()
        hits = [c for c in same if c in shapes]
        if not hits:
            skipped.append(f"{event} ({p.get('areaDesc') or 'no area'}): marine or offshore zone, not drawn")
            continue
        polys = [poly for c in hits for poly in shapes[c]["polys"]]
        areas.append(AlertArea(**base, how="counties", polys=polys, counties=hits))
    return AlertSet(areas, skipped)
