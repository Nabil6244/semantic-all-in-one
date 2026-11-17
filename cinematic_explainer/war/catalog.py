"""Offline war catalog: equipment, figures, institutions, places. Data lives in war/data/*.json (extend by adding entries).

    find_equipment(text)    -> [Match]   specific systems by alias; a generic word ('tank', 'missile') gives a class-level match only
    find_figure(text)       -> [Match]
    find_institution(text)  -> [Match]
    find_place(text)        -> [Match]

Match.confidence: 'exact' (one entry owns the alias), 'ambiguous' (several entries share it: never pick one silently),
'generic' (a class word; Match.entry is None and Match.class_id names the class). Matching is word-bounded, case- and
diacritic-insensitive; an alias that starts with '=' is matched case-sensitively (acronyms such as UN or EU).
A model-name suffix (T-72B3, M1A2) still matches its base alias. Nothing here guesses an identity from similarity.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parent / "data"

EQUIPMENT_CLASSES = ("tank", "ifv", "apc", "artillery", "rocket_artillery", "mortar", "missile_ballistic", "missile_cruise", "air_defense",
                     "interceptor", "drone", "fighter", "helicopter", "bomber", "ship", "radar", "ew", "logistics")


@dataclass(frozen=True)
class Match:
    entry: Optional[Dict[str, Any]]
    matched_alias: str
    confidence: str                 # exact | ambiguous | generic
    start: int = 0
    end: int = 0
    class_id: str = ""              # set for generic matches and copied from the entry for equipment


def normalise(text: str) -> str:
    """Lower-case, strip diacritics, turn every run of non-alphanumerics into one space."""
    t = unicodedata.normalize("NFKD", str(text or "")).lower()
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[\W_]+", " ", t).strip()


def _load(name: str) -> dict:
    try:
        with open(DATA_DIR / name, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=None)
def _equipment() -> Tuple[List[dict], Dict[str, List[str]]]:
    d = _load("equipment.json")
    return list(d.get("entries") or []), dict(d.get("generic") or {})


@lru_cache(maxsize=None)
def _entries(name: str) -> List[dict]:
    return list(_load(name).get("entries") or [])


def _alias_index(entries: List[dict]) -> List[Tuple[str, bool, str, dict]]:
    """[(pattern text, case_sensitive, alias as written, entry)] longest first."""
    out = []
    for e in entries:
        names = [e.get("name", "")] + list(e.get("aliases") or [])
        for a in names:
            if not a:
                continue
            cs = a.startswith("=")
            raw = a[1:] if cs else a
            n = normalise(raw)
            if n:
                out.append((n, cs, raw, e))
    out.sort(key=lambda x: (-len(x[0]), x[0]))
    return out


@lru_cache(maxsize=None)
def _compiled(kind: str) -> List[Tuple[re.Pattern, bool, str, dict]]:
    entries = _equipment()[0] if kind == "equipment" else _entries(f"{kind}.json")
    comp = []
    for n, cs, raw, e in _alias_index(entries):
        body = r"\s+".join(re.escape(p) for p in n.split())
        # a model suffix that starts with a letter (T-72B3, M1A2) still belongs to an alias that ends in a digit
        suffix = r"(?:[a-z][a-z0-9]{0,3})?" if (kind == "equipment" and n[-1:].isdigit()) else ""
        pat = re.compile(r"(?<![^\W_])" + body + suffix + r"(?![^\W_])")
        comp.append((pat, cs, raw, e))
    return comp


def _span_map(text: str) -> Tuple[str, List[int]]:
    """Normalised text plus, for each normalised char, its index in the original text (so spans refer to the caller's string)."""
    out_chars: List[str] = []
    idx: List[int] = []
    prev_sep = True
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKD", ch).lower():
            if unicodedata.combining(c):
                continue
            if re.match(r"[\W_]", c):
                if not prev_sep:
                    out_chars.append(" ")
                    idx.append(i)
                    prev_sep = True
            else:
                out_chars.append(c)
                idx.append(i)
                prev_sep = False
    while out_chars and out_chars[-1] == " ":
        out_chars.pop()
        idx.pop()
    return "".join(out_chars), idx


_FIND_CACHE: Dict[Tuple[Any, ...], List[Match]] = {}
_FIND_MAX = 50000


def _find(kind: str, text: str) -> List[Match]:
    """Cached per (kind, text) (2026-11-12 speed pass: ~26,000 lookups of the same few hundred lines per film, 30 s of planning)."""
    key = (kind, id(_compiled(kind)), str(text or ""))       # a reloaded catalogue (new compiled list) never reuses old results
    hit = _FIND_CACHE.get(key)
    if hit is None:
        hit = _find_uncached(kind, key[2])
        if len(_FIND_CACHE) >= _FIND_MAX:
            _FIND_CACHE.clear()
        _FIND_CACHE[key] = hit
    return list(hit)


def _find_uncached(kind: str, text: str) -> List[Match]:
    text = str(text or "")
    if not text.strip():
        return []
    norm, idx = _span_map(text)
    raw_hits: List[Tuple[int, int, str, dict, bool]] = []
    for pat, cs, raw, e in _compiled(kind):
        for m in pat.finditer(norm):
            s, e_ = idx[m.start()], idx[m.end() - 1] + 1
            if cs and text[s:e_].strip() != raw and raw not in text[s:e_ + 1]:
                continue
            raw_hits.append((s, e_, raw, e, cs))
    # drop hits wholly inside a longer hit of the same text span
    raw_hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    kept: List[Tuple[int, int, str, dict, bool]] = []
    for h in raw_hits:
        if any(k[0] <= h[0] and h[1] <= k[1] and (k[1] - k[0]) > (h[1] - h[0]) for k in kept):
            continue
        kept.append(h)
    # several entries owning the same alias at the same place are ambiguous
    groups: Dict[Tuple[int, int, str], List[dict]] = {}
    for s, e_, raw, e, _ in kept:
        groups.setdefault((s, e_, normalise(raw)), [])
        if e not in groups[(s, e_, normalise(raw))]:
            groups[(s, e_, normalise(raw))].append(e)
    result: List[Match] = []
    for (s, e_, _), ents in sorted(groups.items(), key=lambda kv: kv[0][0]):
        alias = text[s:e_]
        conf = "exact" if len(ents) == 1 else "ambiguous"
        for e in ents:
            result.append(Match(e, alias, conf, s, e_, str(e.get("class", ""))))
    return result


def find_equipment(text: str) -> List[Match]:
    specific = _find("equipment", text)
    generic = _generic_equipment(text)
    spec_classes = {m.class_id for m in specific}
    covered = [(m.start, m.end) for m in specific]
    out = list(specific)
    for g in generic:
        if g.class_id in spec_classes:
            continue                       # 'the T-72 tank' is the T-72, not also a class mention
        if any(s <= g.start and g.end <= e for s, e in covered):
            continue
        out.append(g)
    return sorted(out, key=lambda m: (m.start, m.confidence != "exact"))


def _generic_equipment(text: str) -> List[Match]:
    key = ("__generic__", id(_equipment()), str(text or ""))
    hit = _FIND_CACHE.get(key)
    if hit is None:
        hit = _generic_equipment_uncached(key[2])
        if len(_FIND_CACHE) >= _FIND_MAX:
            _FIND_CACHE.clear()
        _FIND_CACHE[key] = hit
    return list(hit)


def _generic_equipment_uncached(text: str) -> List[Match]:
    text = str(text or "")
    if not text.strip():
        return []
    norm, idx = _span_map(text)
    hits: List[Match] = []
    for cls, words in _equipment()[1].items():
        for w in words:
            body = r"\s+".join(re.escape(p) for p in normalise(w).split())
            if not body:
                continue
            for m in re.finditer(r"(?<![^\W_])" + body + r"(?![^\W_])", norm):
                s, e = idx[m.start()], idx[m.end() - 1] + 1
                hits.append(Match(None, text[s:e], "generic", s, e, cls))
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    kept: List[Match] = []
    for h in hits:
        if any(k.start <= h.start and h.end <= k.end for k in kept):
            continue
        kept.append(h)
    return kept


def find_figure(text: str) -> List[Match]:
    return _find("figures", text)


def find_institution(text: str) -> List[Match]:
    return _find("institutions", text)


def find_place(text: str) -> List[Match]:
    hits = _find("places", text)
    try:
        world = _world_find(str(text or ""))
        # a longer world name swallows a War-list name inside it ('South Georgia' is not the country Georgia)
        hits = [h for h in hits if not any(w.start <= h.start and h.end <= w.end and (w.end - w.start) > (h.end - h.start) for w in world)]
        hits = hits + [w for w in world if not any(h.start < w.end and w.start < h.end for h in hits)]
        hits.sort(key=lambda m: m.start)
    except Exception:  # noqa: BLE001 - the world list only adds places; it never stops a render
        pass
    return hits


# ------------------------------------------------------------------------------------------------ the world beyond the War list
# The War list above covers Ukraine / Russia / the Middle East. Any other war (owner, 2026-11-17: a Falklands film asked for 9 maps and 4
# routes, and every one fell back to text because Port Stanley, Argentina and South Georgia were "no place or country named") finds its
# countries and towns in the app's own Natural Earth data (public domain): map_scene/data/countries.json.gz (countries and territories,
# placed at the middle of their largest outline) and pakmap-engine/data/places_index.json.gz (towns). Names match as written (capitalised),
# a town only when one place owns the name (or one is 10x bigger than the next), and never a common English word.
_ROOT = Path(__file__).resolve().parents[2]
WORLD_ALIASES = {"Britain": "GBR", "Great Britain": "GBR", "the UK": "GBR", "Malvinas": "FLK", "Las Malvinas": "FLK", "Falklands": "FLK",
                 "South Georgia": "SGS", "Holland": "NLD", "Burma": "MMR"}
_COMMON = {"Most", "March", "May", "Victoria", "Victor", "Hope", "Mobile", "Reading", "Split", "Nice", "Darwin", "Of", "Union", "Liberty",
           "Independence", "Commerce", "Paradise", "Friendship", "Concord", "Hermes", "Invincible", "Conqueror", "Sheffield", "Glasgow",
           "Coventry", "Ardent", "Antelope", "Plymouth", "Belgrano", "General", "President", "Admiral", "Fort", "Port", "Mount", "Saint", "San",
           "Santa", "Bay", "Sound", "Islands", "Island", "Green", "North", "South", "East", "West", "Central", "New", "Old", "Royal", "British",
           "American", "French", "German", "Long", "Grand", "Great", "Little", "Lima", "Delta", "Echo", "Sierra", "Alpha", "Bravo", "Charlie"}


@lru_cache(maxsize=1)
def _world() -> Dict[str, dict]:
    """name as written -> place entry (type 'country' for countries / territories, 'city' for towns)."""
    import gzip
    out: Dict[str, dict] = {}
    by_iso: Dict[str, dict] = {}
    try:
        feats = json.load(gzip.open(_ROOT / "map_scene" / "data" / "countries.json.gz")).get("features") or []
    except Exception:  # noqa: BLE001
        feats = []
    for f in feats:
        g = f.get("g") or {}
        polys = g.get("coordinates") or []
        polys = polys if g.get("type") == "MultiPolygon" else [polys]
        best = max((ring[0] for ring in polys if ring and ring[0]), key=len, default=None)
        if not best:
            continue
        xs, ys = [pt[0] for pt in best], [pt[1] for pt in best]
        name = str((f.get("alt") or [f.get("n")])[0] or f.get("n") or "").split(" / ")[0]
        e = {"id": "world_" + str(f.get("iso") or name).lower(), "name": name, "lat": round((min(ys) + max(ys)) / 2, 3),
             "lon": round((min(xs) + max(xs)) / 2, 3), "type": "country", "approximate": True, "world": True}
        by_iso[str(f.get("iso") or "")] = e
        for a in [f.get("n")] + list(f.get("alt") or []):
            a = str(a or "").split(" / ")[0].strip()
            if len(a) >= 4 and "." not in a and a[0].isupper():
                out.setdefault(a, e)
    for a, iso in WORLD_ALIASES.items():
        if iso in by_iso:
            out.setdefault(a, by_iso[iso])
    try:
        towns = json.load(gzip.open(_ROOT / "pakmap-engine" / "data" / "places_index.json.gz"))
    except Exception:  # noqa: BLE001
        towns = []
    named: Dict[str, List[list]] = {}
    for t in towns:
        for a in {t[0], t[1]}:
            if a and len(a) >= 4 and a[0].isupper() and a not in _COMMON:
                named.setdefault(a, []).append(t)
    for a, ts in named.items():
        if a in out:
            continue
        ts = sorted(ts, key=lambda t: -(t[5] or 0))
        if len(ts) > 1 and (ts[0][5] or 0) < 10 * (ts[1][5] or 1):
            continue                                     # several towns of this name and none clearly the one meant
        t = ts[0]
        out[a] = {"id": "world_" + normalise(a).replace(" ", "_") + "_" + str(t[6]).lower(), "name": a, "lat": float(t[4]),
                  "lon": float(t[3]), "type": "city", "approximate": False, "world": True}
    return out


_WORLD_RX = re.compile(r"\b(?:the\s+)?[A-Z][\w'\-]+(?:\s+(?:of\s+|and\s+the\s+|de\s+|del\s+)?[A-Z][\w'\-]+){0,4}")


def _world_find(text: str) -> List[Match]:
    """Capitalised names in the text that the world lists know (the longest name wins; 'Port Stanley' -> Stanley when only that is known)."""
    w = _world()
    out: List[Match] = []
    for m in _WORLD_RX.finditer(text):
        words = m.group(0).split()
        i = 0
        while i < len(words):
            hit = None
            for j in range(len(words), i, -1):
                cand = " ".join(words[i:j])
                if cand in w:
                    hit = (i, j, cand)
                    break
            if not hit:
                i += 1
                continue
            a = m.start() + len(" ".join(words[:hit[0]])) + (1 if hit[0] else 0)
            out.append(Match(w[hit[2]], hit[2], "exact", a, a + len(hit[2])))
            i = hit[1]
    return out


def get_equipment(entry_id: str) -> Optional[dict]:
    for e in _equipment()[0]:
        if e.get("id") == entry_id:
            return e
    return None


def get_place(entry_id: str) -> Optional[dict]:
    for e in _entries("places.json"):
        if e.get("id") == entry_id:
            return e
    if str(entry_id).startswith("world_"):
        return next((e for e in _world().values() if e["id"] == entry_id), None)
    return None


def equipment_card_params(entry: dict) -> dict:
    """Params for the equipment card from a catalog entry: only what the entry states; status attributed, confidence from the match."""
    return {"name": entry.get("name", ""), "role": entry.get("role", ""), "class": entry.get("class", ""),
            "operator": ", ".join(o.get("country", "") for o in entry.get("operators") or [] if o.get("country")),
            "specs": [{"label": s["label"], "value": s["value"]} for s in (entry.get("specs") or []) if s.get("source")],
            "source": "reference data; verify before publishing", "status": "attributed", "image_hint": entry.get("image_hint", "")}
