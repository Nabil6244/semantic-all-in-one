"""Your own footage library, reused before stock (phase 5).

A folder of your clips (Settings: weather_library_dir) is indexed by the words in each clip's folder and file names
("storms/lightning_over_field.mp4" -> storm). A plan's stock footage request ("stock_video:dark storm clouds rolling over farmland")
is matched to the same weather condition, and a clip of yours with that condition is used instead, each clip once per video.
Nothing is moved or copied; the plan names the file where it is. Matching is by words only, so a clip's name must say what it shows."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
# condition -> words that mean it (in a clip's path, or in a stock request). First condition that matches wins.
CONDITIONS = {
    "storm": ("storm", "thunder", "lightning", "tornado", "hail", "supercell"),
    "snow": ("snow", "blizzard", "flurries", "ice", "icy", "frost", "sleet"),
    "rain": ("rain", "rainy", "shower", "showers", "drizzle", "wet", "umbrella", "puddle", "raindrops", "drops"),
    "fog": ("fog", "foggy", "mist", "haze", "hazy", "smoke"),
    "wind": ("wind", "windy", "breezy", "gust", "gusty"),
    "heat": ("heat", "hot", "heatwave", "scorching"),
    "cloud": ("cloud", "clouds", "cloudy", "overcast", "gray", "grey"),
    "sun": ("sun", "sunny", "clear", "sunshine", "blue", "sunrise", "sunset", "beach"),
}


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z]+", str(text).lower())


def condition_of(text: str) -> Optional[str]:
    words = set(_words(text))
    for cond, keys in CONDITIONS.items():
        if words & set(keys):
            return cond
    return None


@dataclass
class LibraryClip:
    path: Path
    condition: Optional[str]
    words: Set[str] = field(default_factory=set)


def index(folder: "str | Path") -> List[LibraryClip]:
    """Every video under `folder` with the condition its folder and file names say (clips that say none are kept, unused)."""
    root = Path(folder)
    if not root.is_dir():
        return []
    out = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in VIDEO_EXT and not f.name.startswith("."):
            rel = " ".join(f.relative_to(root).with_suffix("").parts)
            out.append(LibraryClip(f, condition_of(rel), set(_words(rel))))
    return out


def pick(request: str, library: Iterable[LibraryClip], used: Set[Path]) -> Optional[Path]:
    """The library clip for a stock request: same condition, most words in common, not used yet in this video."""
    cond = condition_of(request)
    if cond is None:
        return None
    want = set(_words(request))
    best = None
    for c in library:
        if c.condition != cond or c.path in used:
            continue
        score = len(want & c.words)
        if best is None or score > best[0]:
            best = (score, c.path)
    return best[1] if best else None


def prefer_library(beats_csv: str, folder: "str | Path") -> "tuple[str, List[str]]":
    """beats.csv with each stock_video clip replaced by a matching clip of yours (when there is one), and notes of what changed."""
    lib = index(folder)
    if not lib:
        return beats_csv, []
    rows = list(csv.reader(io.StringIO(beats_csv.lstrip("﻿"))))
    if not rows:
        return beats_csv, []
    head = [c.strip().lower() for c in rows[0]]
    if "row" not in head or "asset" not in head:
        return beats_csv, []
    i_row, i_asset = head.index("row"), head.index("asset")
    used: Set[Path] = set()
    notes: List[str] = []
    for cells in rows[1:]:
        if len(cells) <= max(i_row, i_asset) or cells[i_row].strip().lower() != "clip":
            continue
        asset = cells[i_asset].strip()
        if not asset.lower().startswith("stock_video:"):
            continue
        hit = pick(asset.split(":", 1)[1], lib, used)
        if hit is not None:
            used.add(hit)
            cells[i_asset] = str(hit)
            notes.append(f"your clip {hit.name} instead of {asset}")
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue(), notes


def library_summary(folder: "str | Path") -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for c in index(folder):
        counts[c.condition or "unlabelled"] = counts.get(c.condition or "unlabelled", 0) + 1
    return counts
