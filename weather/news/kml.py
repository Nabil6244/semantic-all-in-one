"""A small reader for the KML / KMZ files NHC and WPC publish (wind-speed probabilities, arrival times of tropical-storm-force
winds, WPC rain forecasts): placemarks with their style's colour, their name / description, and their geometry.

    read(blob) -> [Placemark]     blob: KMZ (zip) or KML bytes
Colours: KML writes aabbggrr; Placemark.color is #RRGGBB and .alpha 0..1 (a fully transparent style is a band not drawn)."""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

Ring = List[Tuple[float, float]]


@dataclass
class Placemark:
    name: str
    text: str  # the description, tags removed
    style: str
    color: str = "#FFFFFF"
    alpha: float = 1.0
    polygons: List[List[Ring]] = field(default_factory=list)  # [outer, holes...]
    lines: List[Ring] = field(default_factory=list)
    points: List[Tuple[float, float]] = field(default_factory=list)


def _kml_bytes(blob: bytes) -> bytes:
    if blob[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(blob))
        name = next(n for n in z.namelist() if n.lower().endswith(".kml"))
        return z.read(name)
    return blob


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _coords(text: str) -> Ring:
    out = []
    for tok in (text or "").split():
        parts = tok.split(",")
        if len(parts) >= 2:
            out.append((round(float(parts[0]), 4), round(float(parts[1]), 4)))
    return out


def _abgr(c: str) -> Tuple[str, float]:
    c = (c or "ffffffff").strip().lower()
    if len(c) != 8:
        return "#FFFFFF", 1.0
    a, b, g, r = c[0:2], c[2:4], c[4:6], c[6:8]
    return f"#{r}{g}{b}".upper(), int(a, 16) / 255.0


def read(blob: bytes) -> List[Placemark]:
    root = ET.fromstring(_kml_bytes(blob))
    styles: Dict[str, Tuple[str, float]] = {}
    for el in root.iter():
        if _local(el.tag) == "Style" and el.get("id"):
            col = None
            for sub in el.iter():
                if _local(sub.tag) == "PolyStyle":
                    col = next((x.text for x in sub if _local(x.tag) == "color"), col)
                elif _local(sub.tag) == "LineStyle" and col is None:
                    col = next((x.text for x in sub if _local(x.tag) == "color"), None)
            styles[el.get("id")] = _abgr(col)
    out: List[Placemark] = []
    for pm in root.iter():
        if _local(pm.tag) != "Placemark":
            continue
        name = desc = style = ""
        for ch in pm:
            t = _local(ch.tag)
            if t == "name":
                name = (ch.text or "").strip()
            elif t == "description":
                desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", ch.text or "")).strip()
            elif t == "styleUrl":
                style = (ch.text or "").strip().lstrip("#")
        color, alpha = styles.get(style, ("#FFFFFF", 1.0))
        p = Placemark(name, desc, style, color, alpha)
        for g in pm.iter():
            t = _local(g.tag)
            if t == "Polygon":
                rings = []
                for b in g:
                    for lr in b.iter():
                        if _local(lr.tag) == "coordinates":
                            rings.append(_coords(lr.text))
                if rings:
                    p.polygons.append(rings)
            elif t == "LineString":
                c = next((x for x in g.iter() if _local(x.tag) == "coordinates"), None)
                if c is not None:
                    p.lines.append(_coords(c.text))
            elif t == "Point":
                c = next((x for x in g.iter() if _local(x.tag) == "coordinates"), None)
                if c is not None and _coords(c.text):
                    p.points.append(_coords(c.text)[0])
        out.append(p)
    return out


def clip_bbox(rings: List[Ring], bbox) -> bool:
    """True when the outer ring touches [west, south, east, north]."""
    w, s, e, n = bbox
    return any(w <= x <= e and s <= y <= n for x, y in rings[0]) if rings and rings[0] else False


def thin(ring: Ring, keep: int = 400) -> Ring:
    """At most `keep` points (every k-th, the ring stays closed): forecast contours are drawn, not measured."""
    if len(ring) <= keep:
        return ring
    k = len(ring) // keep + 1
    out = ring[::k]
    return out + [ring[0]] if out[-1] != ring[0] else out
