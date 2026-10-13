"""Broadcast compositions that carry no data of their own: the lower-third headline and place labels (phase 5 polish).

    headline     no data_source   extra {"kicker": "HURRICANE IAN", "title": "LANDFALL ON FLORIDA'S GULF COAST", "sub": "SEPTEMBER 28, 2022",
                                         "tone": "news" | "forecast" | "post"}
                 a broadcast lower-third: a coloured kicker tab, a big title, an optional date/sub line. Words only: the kicker
                 and title may not hold a digit (every number on screen comes from a data layer); the sub line is for dates.
    place_label  place "Houston, TX" (a known city) or "26.64,-81.87" with extra {"text": "FORT MYERS"}
                 a dot and the place's name on the map, so the viewer knows where they are.

Tones colour the kicker tab: news red, forecast blue, post (post-event) amber. Warning colours are never used here."""

from __future__ import annotations

import re

from ..cities import cities, norm
from . import LayerType, register

TONES = ("news", "forecast", "post")
LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def _words(row, key: str) -> str:
    return " ".join(str(row.extra.get(key, "")).split())


def check_headline(row) -> None:
    if not _words(row, "title"):
        raise ValueError('headline needs extra {"title": "..."} (and optionally kicker, sub, tone)')
    for key in ("kicker", "title"):
        if re.search(r"\d", _words(row, key)):
            raise ValueError(f"headline {key} may not hold a number ({_words(row, key)!r}): numbers come from data layers; dates go in sub")
    if row.extra.get("tone", "news") not in TONES:
        raise ValueError(f"headline tone is one of {', '.join(TONES)}")


def build_headline(row, snap, window, out) -> None:
    out.events.append({"id": f"wx_{row.id}", "type": "headline", "t_in": window.t_in, "t_out": window.t_out,
                       "kicker": _words(row, "kicker").upper(), "title": _words(row, "title").upper(), "sub": _words(row, "sub").upper(),
                       "tone": row.extra.get("tone", "news")})


def place_point(row):
    """(lon, lat, name) of a place_label row."""
    m = LATLON.match(row.place or "")
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"place_label {row.place!r} is not a latitude,longitude")
        name = _words(row, "text")
        if not name:
            raise ValueError('a place_label at a latitude,longitude needs extra {"text": "FORT MYERS"}')
        return lon, lat, name
    c = cities().get(norm(row.place or ""))
    if c is None:
        raise ValueError(f"place_label place {row.place!r} is not a known city ('City, ST' from weather/data/cities.json) "
                         "nor a latitude,longitude with extra text")
    return c.lon, c.lat, _words(row, "text") or c.name


def check_place(row) -> None:
    place_point(row)


def build_place(row, snap, window, out) -> None:
    lon, lat, name = place_point(row)
    out.events.append({"id": f"wx_{row.id}", "type": "place_label", "t_in": window.t_in, "t_out": window.t_out, "lon": lon, "lat": lat,
                       "text": name.upper()})


register(LayerType(name="headline", products=(), extra_keys=frozenset({"kicker", "title", "sub", "tone"}), build=build_headline,
                   check=check_headline, about="a broadcast lower-third headline (words only)"))
register(LayerType(name="place_label", products=(), extra_keys=frozenset({"text"}), build=build_place, check=check_place,
                   about="a dot and a place's name on the map"))
