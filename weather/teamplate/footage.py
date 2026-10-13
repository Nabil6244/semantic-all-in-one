"""Teamplate's footage rules, on top of the Weather style's own (weather/footage.py still decides which SOURCES are allowed).

1. Relevance: a stock request must show the kind of weather and the kind of place the narration of its beat describes. A clip of
   palm trees in a tropical storm on a beat about damaging winds in Wyoming is refused, naming the beat. The check is by words
   (the same weather words as weather.footage_library), so it catches contradictions, not every weak match.
2. Your library first, strictly: weather.footage_library swaps a stock request for one of your clips with the same weather
   condition; Teamplate also refuses a clip of yours whose name contradicts the beat's narration (tropical, coast, desert ...).
3. Rhythm: a single stock shot of 9 s or more is cut into shots of about 5 s (the reference's median shot), each asking the stock
   providers for the same subject at a different framing, so the cut shows the same thing from another angle. Event footage and
   your own files are never split (cutting inside one real clip is a jump cut, and a second clip of the same event may not exist).
Nothing is ever generated: where no relevant footage exists the beat stays on the map."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from ..footage_library import CONDITIONS, LibraryClip, _words, index
from . import MAX_SHOTS, SHOT_S, SHOT_SPLIT_FROM_S

# conditions that can honestly illustrate each other (a rain story can show storm clouds; it cannot show a heatwave)
FAMILIES = ({"storm", "rain", "wind", "cloud", "fog"}, {"snow", "wind", "cloud", "fog"}, {"heat", "sun"}, {"sun", "cloud"})
# settings a clip can show that the narration must allow (word lists; the narration allows a setting if it names any of its words)
SETTINGS = {
    "tropical": ({"palm", "palms", "tropical", "tropics", "caribbean", "jungle", "rainforest"},
                 {"tropical", "tropics", "hurricane", "hurricanes", "typhoon", "cyclone", "caribbean", "florida", "puerto", "hawaii",
                  "gulf", "keys", "bahamas", "palm"}),
    "coast": ({"beach", "beaches", "surf", "seaside", "ocean", "shoreline", "coastline", "coast", "coastal", "waves", "pier", "harbor"},
              {"beach", "beaches", "coast", "coastal", "coastline", "shore", "shoreline", "ocean", "sea", "gulf", "lake", "lakeshore",
               "waves", "surge", "harbor", "bay", "island", "islands", "landfall", "hurricane", "erosion", "pier", "atlantic", "pacific"}),
    "desert": ({"desert", "cactus", "cacti", "dunes", "sand", "sandstorm", "dust"},
               {"desert", "dust", "dunes", "sand", "sandstorm", "arizona", "nevada", "mojave", "drought", "haboob", "beach", "dune"}),
    "city": ({"city", "street", "streets", "downtown", "skyline", "traffic", "skyscraper", "skyscrapers"},
             {"city", "cities", "street", "streets", "downtown", "urban", "metro", "town", "neighborhood", "neighborhoods", "houston", "chicago",
              "dallas", "york", "miami", "angeles", "orleans", "atlanta", "denver", "phoenix", "boston", "seattle", "traffic", "roads", "road"}),
}


def conditions(text: str) -> Set[str]:
    """Every weather condition the text names (weather.footage_library's words), not only the first."""
    words = set(_words(text))
    return {c for c, keys in CONDITIONS.items() if words & set(keys)}


def conflicts(shows: str, narration: str) -> List[str]:
    """Why footage described by `shows` does not belong on narration `narration` (empty when nothing contradicts)."""
    out = []
    want, have = conditions(narration), conditions(shows)
    if want and have and not any(any(a in f and b in f for f in FAMILIES) for a in have for b in want):
        out.append(f"it shows {', '.join(sorted(have))} weather and the narration is about {', '.join(sorted(want))}")
    words, said = set(_words(shows)), set(_words(narration))
    for name, (marks, allowed) in SETTINGS.items():
        if words & marks and not said & allowed:
            out.append(f"it shows a {name} setting ({', '.join(sorted(words & marks))}) the narration does not mention")
    return out


def _request(asset: str) -> Optional[str]:
    head, sep, rest = str(asset).partition(":")
    return rest.strip() if sep and head.lower() in ("stock_video", "stock_image") else None


def relevance_problems(plan) -> List[str]:
    """Every stock clip or card whose description contradicts its beat's narration, naming the beat (the render does not start)."""
    out = []
    for b in plan.beats:
        if not b.narration:
            continue
        assets = [("clip", c.asset) for c in b.clips] + [("card", s.asset) for s in b.cards]
        for what, asset in assets:
            req = _request(asset)
            if req is None:
                continue
            why = conflicts(req, b.narration)
            if why:
                out.append(f"beats.csv beat {b.id}: {what} {asset!r} does not match what the narration describes: {'; '.join(why)}. "
                           f"Describe footage of this beat's own weather and place, or leave the beat on the map (Weather Teamplate)")
    return out


PLACE_WORDS = {"on", "in", "over", "across", "along", "at", "near", "through", "by", "down", "into", "above", "under", "beside"}


def _trimmed(req: str) -> str:
    """The request without the setting it adds: cut before the place phrase that names it ("heavy rain falling on a quiet
    residential street" -> "heavy rain falling"); '' when the setting is the subject itself ("palm trees ...")."""
    marks = set().union(*(m for m, _a in SETTINGS.values()))
    toks = str(req).split()
    first = next((i for i, w in enumerate(toks) if w.lower().strip(".,;:!?\"'") in marks), None)
    if first is None:
        return req
    cut = next((i for i in range(first - 1, -1, -1) if toks[i].lower() in PLACE_WORDS), None)
    return " ".join(toks[:cut]) if cut is not None and cut >= 2 else ""


def fix_relevance(plan, notes: Optional[List[str]] = None) -> int:
    """Every stock clip or card that contradicts its beat's narration gets a request that does not (in place), so the render
    never stops for it: the request without its setting, else one built from the beat's own words (cutaways.request_for), else
    it is kept as written with a note. Returns how many were changed."""
    from .cutaways import request_for

    notes = notes if notes is not None else []
    changed = 0
    for b in plan.beats:
        if not b.narration:
            continue
        for item in list(b.clips) + list(b.cards):
            req = _request(item.asset)
            if req is None or not conflicts(req, b.narration):
                continue
            kind = str(item.asset).partition(":")[0]
            new = next((r for r in (_trimmed(req), request_for(b.narration)) if r and not conflicts(r, b.narration)), None)
            if new is None:
                notes.append(f"beat {b.id}: footage {req!r} may not match the narration; kept as written")
                continue
            item.asset = f"{kind}:{new}"
            changed += 1
            notes.append(f"beat {b.id}: footage {req!r} did not match the narration, so it asks for {new!r} instead")
    return changed


FRAMINGS = ("", "close up", "wide shot", "aerial view")


def split_long_shots(plan, notes: Optional[List[str]] = None) -> None:
    """A footage beat with one stock clip of SHOT_SPLIT_FROM_S or more becomes ~SHOT_S shots of the same subject (in place)."""
    from hybrid.plan import Clip

    for b in plan.beats:
        if b.mode != "footage" or len(b.clips) != 1:
            continue
        c = b.clips[0]
        req = _request(c.asset)
        span = b.end - b.start
        if req is None or c.dur is not None or span < SHOT_SPLIT_FROM_S:
            continue
        n = max(2, min(MAX_SHOTS, int(round(span / SHOT_S))))
        head = c.asset.split(":", 1)[0]
        b.clips = [Clip(asset=f"{head}:{req}" + (f", {f}" if f else ""), kenburns=c.kenburns, loop=c.loop, reason=c.reason) for f in FRAMINGS[:n]]
        if notes is not None:
            notes.append(f"beat {b.id}: {span:.1f}s of {req!r} cut into {n} shots of about {span / n:.1f}s (Weather Teamplate)")


def _pick(request: str, narration: str, library: Iterable[LibraryClip], used: Set[Path]) -> Optional[Path]:
    want_cond = conditions(request)
    if not want_cond:
        return None
    want = set(_words(request)) | set(_words(narration))
    best = None
    for c in library:
        if c.path in used or c.condition not in want_cond:
            continue
        if conflicts(" ".join(sorted(c.words)), narration):
            continue
        score = len(want & c.words)
        if best is None or score > best[0]:
            best = (score, c.path)
    return best[1] if best else None


def prefer_library_strict(beats_csv: str, folder: "str | Path") -> "tuple[str, List[str]]":
    """weather.footage_library.prefer_library, with the clip also checked against its beat's narration (see the module notes)."""
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
    i_beat = head.index("beat") if "beat" in head else None
    i_text = head.index("text") if "text" in head else None
    said: Dict[str, str] = {}
    for cells in rows[1:]:
        if i_beat is not None and i_text is not None and len(cells) > max(i_beat, i_text, i_row) and cells[i_row].strip().lower() == "beat":
            said[cells[i_beat].strip()] = cells[i_text]
    used: Set[Path] = set()
    notes: List[str] = []
    for cells in rows[1:]:
        if len(cells) <= max(i_row, i_asset) or cells[i_row].strip().lower() != "clip":
            continue
        asset = cells[i_asset].strip()
        if not asset.lower().startswith("stock_video:"):
            continue
        narration = said.get(cells[i_beat].strip(), "") if i_beat is not None and len(cells) > i_beat else ""
        hit = _pick(asset.split(":", 1)[1], narration, lib, used)
        if hit is not None:
            used.add(hit)
            cells[i_asset] = str(hit)
            notes.append(f"your clip {hit.name} instead of {asset}")
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue(), notes
