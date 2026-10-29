"""Named seas, gulfs, straits, lagoons and a few coast/peninsula words the atlas (map_scene) has no polygon for.

The atlas knows countries, states, counties and named regions; it does not know "the Adriatic", "the Baltic" or "the Venetian Lagoon", so a script that says
"look east across the Adriatic" lost its place. A water body is not a shape the map engine fills, it is an area the camera frames and a label names, so each entry is a
bounding box (west, south, east, north) with the label to print. `find(name)` returns None for anything not listed (never a near match). Adjective forms that the atlas
answers wrongly ("Balkan" is a province of Turkmenistan there) are listed under `OVERRIDES`: they point at the real place."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

BBox = Tuple[float, float, float, float]

# label -> (bbox, aliases). Boxes are generous around the open water, tight enough that the region frame reads the sea and both its shores.
_WATERS: Dict[str, Tuple[BBox, List[str]]] = {
    "Adriatic Sea": ((12.0, 39.7, 20.0, 45.9), ["adriatic", "adriatic sea", "adriatic coast", "adriatic coastline"]),
    "Venetian Lagoon": ((12.15, 45.15, 12.62, 45.6), ["venetian lagoon", "lagoon of venice", "venice lagoon", "the lagoon"]),
    "Gulf of Venice": ((12.2, 44.9, 14.0, 45.8), ["gulf of venice"]),
    "Mediterranean Sea": ((-6.0, 30.0, 36.0, 46.0), ["mediterranean", "mediterranean sea"]),
    "Ionian Sea": ((14.5, 35.5, 22.0, 41.0), ["ionian", "ionian sea"]),
    "Aegean Sea": ((22.5, 35.0, 28.0, 41.0), ["aegean", "aegean sea"]),
    "Tyrrhenian Sea": ((9.0, 37.8, 16.5, 43.5), ["tyrrhenian", "tyrrhenian sea"]),
    "Ligurian Sea": ((7.5, 42.5, 10.5, 44.6), ["ligurian sea"]),
    "Black Sea": ((27.3, 40.8, 41.8, 46.7), ["black sea"]),
    "Sea of Azov": ((34.8, 45.2, 39.4, 47.4), ["sea of azov", "azov sea"]),
    "Sea of Marmara": ((26.5, 40.3, 30.0, 41.1), ["sea of marmara", "marmara sea"]),
    "Caspian Sea": ((46.5, 36.5, 54.8, 47.2), ["caspian", "caspian sea"]),
    "Red Sea": ((32.3, 12.5, 43.6, 28.5), ["red sea"]),
    "Persian Gulf": ((48.0, 24.0, 56.7, 30.5), ["persian gulf", "arabian gulf"]),
    "Gulf of Oman": ((56.0, 22.5, 61.5, 26.5), ["gulf of oman"]),
    "Arabian Sea": ((55.0, 6.0, 77.0, 25.0), ["arabian sea"]),
    "Bay of Bengal": ((79.0, 5.0, 100.0, 23.0), ["bay of bengal"]),
    "South China Sea": ((105.0, 0.0, 121.0, 23.0), ["south china sea"]),
    "East China Sea": ((118.5, 25.0, 128.5, 33.5), ["east china sea"]),
    "Sea of Japan": ((127.0, 33.0, 142.5, 51.0), ["sea of japan", "east sea"]),
    "Yellow Sea": ((119.0, 31.0, 126.5, 40.0), ["yellow sea"]),
    "Sea of Okhotsk": ((135.0, 44.0, 163.0, 62.0), ["sea of okhotsk"]),
    "Bering Sea": ((162.0, 51.0, 200.0, 66.0), ["bering sea"]),
    "North Sea": ((-4.0, 51.0, 9.0, 61.0), ["north sea"]),
    "Baltic Sea": ((9.5, 53.5, 30.5, 66.0), ["baltic", "baltic sea"]),
    "Gulf of Bothnia": ((16.0, 59.8, 26.0, 66.0), ["gulf of bothnia"]),
    "Barents Sea": ((16.0, 66.0, 56.0, 78.0), ["barents sea"]),
    "Norwegian Sea": ((-5.0, 62.0, 15.0, 73.0), ["norwegian sea"]),
    "Irish Sea": ((-6.5, 52.0, -2.8, 55.5), ["irish sea"]),
    "English Channel": ((-5.8, 48.4, 2.0, 51.2), ["english channel", "the channel"]),
    "Bay of Biscay": ((-10.0, 43.0, -1.0, 48.5), ["bay of biscay", "biscay"]),
    "Strait of Gibraltar": ((-6.5, 35.5, -4.8, 36.5), ["strait of gibraltar", "straits of gibraltar"]),
    "Bosphorus": ((28.9, 40.9, 29.3, 41.3), ["bosphorus", "bosporus"]),
    "Strait of Hormuz": ((55.5, 25.5, 57.5, 27.2), ["strait of hormuz", "straits of hormuz"]),
    "Strait of Malacca": ((98.0, 1.0, 104.5, 6.5), ["strait of malacca", "straits of malacca", "malacca strait"]),
    "Suez Canal": ((32.2, 29.8, 32.7, 31.4), ["suez canal"]),
    "Panama Canal": ((-80.0, 8.8, -79.4, 9.5), ["panama canal"]),
    "Gulf of Mexico": ((-98.0, 18.0, -80.0, 30.8), ["gulf of mexico"]),
    "Caribbean Sea": ((-88.0, 9.0, -60.0, 22.0), ["caribbean", "caribbean sea"]),
    "Hudson Bay": ((-95.0, 51.0, -77.0, 64.0), ["hudson bay"]),
    "Gulf of Guinea": ((-8.0, -2.0, 10.0, 6.5), ["gulf of guinea"]),
    "Mozambique Channel": ((33.0, -26.0, 45.0, -10.0), ["mozambique channel"]),
    "Coral Sea": ((142.0, -25.0, 164.0, -9.0), ["coral sea"]),
    "Tasman Sea": ((148.0, -47.0, 175.0, -29.0), ["tasman sea"]),
    "Sea of Galilee": ((35.4, 32.7, 35.7, 32.95), ["sea of galilee"]),
    "Dead Sea": ((35.3, 30.9, 35.7, 31.8), ["dead sea"]),
    "Lake Victoria": ((31.5, -3.1, 34.9, 0.5), ["lake victoria"]),
}

# the real place for a name the atlas answers with something else (or a coast/peninsula word the atlas lacks): alias -> (label, atlas reference)
OVERRIDES: Dict[str, Tuple[str, str]] = {
    "balkan": ("Balkans", "Balkans"), "balkans": ("Balkans", "Balkans"), "balkan coast": ("Balkans", "Balkans"), "balkan coastline": ("Balkans", "Balkans"),
    "balkan peninsula": ("Balkans", "Balkans"), "the balkans": ("Balkans", "Balkans"),
}

# words that make a capitalised name a water body or a shore ("the Adriatic coast", "the Venetian Lagoon")
WATER_WORDS = frozenset("sea seas gulf bay strait straits channel lagoon lagoons sound firth canal coast coastline shore shoreline".split())


def _key(name: str) -> str:
    t = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    return re.sub(r"\s+", " ", t).strip()


_INDEX: Dict[str, str] = {}
for _label, (_bb, _al) in _WATERS.items():
    _INDEX[_key(_label)] = _label
    for _a in _al:
        _INDEX[_key(_a)] = _label


def find(name: str) -> Optional[Tuple[str, BBox]]:
    """(label, bbox) of a listed water body, else None. Case, punctuation and a leading 'the' do not matter."""
    k = _key(name)
    k = re.sub(r"^the ", "", k)
    lab = _INDEX.get(k)
    return (lab, _WATERS[lab][0]) if lab else None


def override(name: str) -> Optional[str]:
    """The atlas reference a name must be read as ('Balkan' -> 'Balkans'), else None."""
    hit = OVERRIDES.get(re.sub(r"^the ", "", _key(name)))
    return hit[1] if hit else None
