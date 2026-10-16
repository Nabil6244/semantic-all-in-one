"""The What If template library on the planner's side (the visuals in whatif-engine/templates/<family>/<id>.json).

A CSV layer row `type=template, id=<template id>` becomes one tm_template layer: the template JSON itself (so the renderer needs no
lookups), the slot values the row gives (each template slot says which column fills it: label, sub, text, value_from, value_to,
format; extra {"slots": {...}} sets any slot), and the narration cues -- the moments the narrator says the words a template waits
for ("@photon" in a template = when "photon" is heard). A template with "plate": true brings its own dark plate shot, like a
diagram row; "plate": false draws over the shot already on screen (a stage header, a lower-left number, the end question).

The auto planner (no CSV) also uses templates: a sentence matching a template's "triggers" gets that visual when the template
needs nothing the narration cannot give (no required slot), within the plate budget.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

COLUMNS = ("label", "sub", "text", "value_from", "value_to", "format")


def library_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "whatif-engine" / "templates"


@lru_cache(maxsize=1)
def load_library() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    root = library_dir()
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        out[t["id"]] = t
    return out


def validate(t: Dict[str, Any]) -> List[str]:
    """The same contract whatif-engine/lib/library.mjs checks (the engine test also draws every template)."""
    p: List[str] = []
    for k in ("id", "family", "use", "items"):
        if k not in t:
            p.append(f"{t.get('id', '?')}: {k!r} is missing")
    slots = t.get("slots", {})
    used = set(re.findall(r"\{([a-zA-Z_]\w*)(?:\.[\w.]+)?\}", json.dumps(t.get("items", []))))
    for k in sorted(used - set(slots) - {"it", "i", "n", "len"}):
        p.append(f"{t.get('id')}: uses {{{k}}} but has no slot {k!r}")
    for k, s in slots.items():
        if s.get("from") and s["from"] not in COLUMNS:
            p.append(f"{t.get('id')}: slot {k!r} comes from an unknown column {s['from']!r}")
    if t.get("triggers"):
        try:
            re.compile(t["triggers"])
        except re.error as exc:
            p.append(f"{t.get('id')}: triggers is not a valid pattern ({exc})")
    return p


# ---- slot values from a CSV row -------------------------------------------------------------------------------------------------
def _num(v: Any) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*\.?\d*", str(v or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _pairs(text: str) -> List[Tuple[str, str]]:
    out = []
    for part in str(text or "").split(";"):
        if not part.strip():
            continue
        k, _, v = part.partition("=")
        out.append((k.strip(), v.strip()))
    return out


def _pair_item(k: str, v: str) -> Dict[str, Any]:
    """NAME=value -> {name, value, num}; "value|67" sets the number explicitly; "0.73,0.36" also gives x and y (a place on the frame)."""
    shown, _, explicit = v.partition("|")
    d: Dict[str, Any] = {"name": k.upper(), "value": shown.strip().upper(), "num": _num(explicit) if explicit else _num(shown)}
    m = re.fullmatch(r"\s*(0?\.\d+|[01](?:\.\d+)?)\s*,\s*(0?\.\d+|[01](?:\.\d+)?)\s*", shown)
    if m:
        d["x"], d["y"], d["value"] = float(m.group(1)), float(m.group(2)), ""
    if d["num"] is None:
        d["num"] = 0
    return d


def slots_from_row(t: Dict[str, Any], it: Any) -> Dict[str, Any]:
    """The slot values a CSV row gives a template (columns by each slot's "from", then extra {"slots": {...}}). Raises ValueError naming
    a required slot the row left empty."""
    out: Dict[str, Any] = {}
    for name, spec in (t.get("slots") or {}).items():
        frm = spec.get("from")
        raw = getattr(it, frm, None) if frm else None
        if raw is None or raw == "":
            continue
        kind = spec.get("kind")
        if kind == "list":
            out[name] = [x.strip().upper() for x in str(raw).split(";") if x.strip()]
        elif kind == "pairs":
            out[name] = [_pair_item(k, v) for k, v in _pairs(str(raw))]
        elif kind == "parts":
            out[name] = [{"label": k.upper(), "text": v.upper(), "v": _num(v) or 0} for k, v in _pairs(str(raw))]
        elif isinstance(raw, float) and raw.is_integer():
            out[name] = int(raw)
        else:
            out[name] = raw.upper() if isinstance(raw, str) and frm in ("label", "sub", "format") else raw
    extra = (getattr(it, "extra", None) or {}).get("slots") or {}
    if not isinstance(extra, dict):
        raise ValueError('extra "slots" must be a JSON object, e.g. {"slots": {"ratio_to": 100}}')
    out.update(extra)
    missing = [n for n, s in (t.get("slots") or {}).items() if s.get("required") and out.get(n) in (None, "", [])]
    if missing:
        cols = ", ".join(f"{n} ({t['slots'][n].get('from') or 'extra slots'})" for n in missing)
        raise ValueError(f"template {t['id']} needs {cols}")
    return out


# ---- cues: the words a template waits for ---------------------------------------------------------------------------------------
def cue_names(t: Dict[str, Any]) -> List[str]:
    return sorted(set(m.lower() for m in re.findall(r'"@([\w\'-]+)', json.dumps(t.get("items", [])))))


def find_cues(t: Dict[str, Any], words: Sequence[Any], start: float, end: float) -> Dict[str, float]:
    """name -> seconds after `start` when the narrator first says a word starting with it, inside [start - 0.3, end]."""
    out: Dict[str, float] = {}
    names = cue_names(t)
    if not names:
        return out
    for w in words:
        ws = float(getattr(w, "start", 0.0))
        if ws < start - 0.3 or ws > end:
            continue
        norm = (getattr(w, "norm", "") or re.sub(r"[^\w'-]", "", str(getattr(w, "text", "")).lower()))
        for n in names:
            if n not in out and norm.startswith(n):
                out[n] = round(max(0.0, ws - start), 3)
    return out


# ---- a row -> a layer (and its plate) -------------------------------------------------------------------------------------------
def _public(t: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in t.items() if not k.startswith("_") and k not in ("triggers", "source")}


def split_cite(cite: str) -> Tuple[str, str]:
    kind, _, text = str(cite or "ILLUSTRATION").partition(" · ")
    return kind.strip().upper() or "ILLUSTRATION", text.strip().upper()


def get(template_id: str) -> Dict[str, Any]:
    lib = load_library()
    t = lib.get((template_id or "").strip().lower())
    if t is None:
        close = difflib.get_close_matches((template_id or "").lower(), list(lib), n=3)
        raise ValueError(f"unknown template {template_id!r}" + (f" (did you mean {', '.join(close)}?)" if close else "; see the template list in the CSV prompt"))
    return t


def layer_for(it: Any, start: float, end: Optional[float], words: Sequence[Any] = ()) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """A template row -> (tm_template layer, plate fields or None). The plate fields: tint, cite (kind, text), asset (a photo to fetch)."""
    t = get(it.id)
    slots = slots_from_row(t, it)
    stop = float(end) if end else start + float(getattr(it, "hold", None) or t.get("hold", 6))
    plate = None
    photo_slot = t.get("image_slot")
    asset = ""
    if photo_slot and isinstance(slots.get(photo_slot), str) and ":" in slots[photo_slot]:
        asset = slots.pop(photo_slot)
        if asset.lower().startswith("file:") and Path(asset.split(":", 1)[1].strip()).is_file():
            slots[photo_slot], asset = asset, asset           # compile.py places a local file like any fetched one
    if t.get("plate", True):
        plate = {"tint": (getattr(it, "extra", None) or {}).get("tint", t.get("tint", "cool")), "cite": split_cite(t.get("cite", "ILLUSTRATION")), "asset": asset}
    layer = {"type": "tm_template", "template": _public(t), "slots": slots, "cues": find_cues(t, words, start, stop),
             "start": round(start, 3), "end": round(stop, 3), "fade_in": 0.05, "fade_out": 0.05 if plate else 0.3, "z": 4 if plate else 6,
             "plate": bool(plate)}
    if photo_slot:
        layer["image_slot"] = photo_slot
    return layer, plate


# ---- the auto planner ---------------------------------------------------------------------------------------------------------
def auto_candidates() -> List[Dict[str, Any]]:
    """Templates the planner may place on its own: marked "auto" (a concept with no figures of its own -- light bending, a spacetime well --
    never one whose default data would be shown as fact), a trigger pattern, a plate, and no slot that only a CSV could fill."""
    out = []
    for t in load_library().values():
        if not t.get("auto") or not t.get("triggers") or not t.get("plate", True) or t.get("image_slot"):
            continue
        if any(s.get("required") for s in (t.get("slots") or {}).values()):
            continue
        out.append(t)
    return out


def match(sentence: str, used: Sequence[str] = ()) -> Optional[Dict[str, Any]]:
    """The first auto template whose trigger the sentence matches (not one already used in this video)."""
    for t in auto_candidates():
        if t["id"] in used:
            continue
        if re.search(t["triggers"], sentence, re.I):
            return t
    return None


def catalog_text() -> str:
    """The template list for the CSV prompt, generated from the files so it is never out of date."""
    lines = []
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for t in load_library().values():
        by_family.setdefault(t["family"], []).append(t)
    for fam in sorted(by_family):
        lines.append(f"[{fam}]")
        for t in sorted(by_family[fam], key=lambda x: x["id"]):
            cols = []
            for name, s in (t.get("slots") or {}).items():
                if s.get("from"):
                    kind = {"pairs": " as NAME=value; NAME=value", "list": " as A; B; C", "parts": " as PART=percent; PART=percent"}.get(s.get("kind", ""), "")
                    cols.append(f"{s['from']}={name}{kind}{' (required)' if s.get('required') else ''}")
            where = "" if t.get("plate", True) else " [draws over the shot on screen, no plate]"
            photo = f" [photo: extra {{\"slots\": {{\"{t['image_slot']}\": \"nasa_image:<what>\"}}}}]" if t.get("image_slot") else ""
            lines.append(f"  {t['id']}: {t['use']}{where}{photo}" + (f" Columns: {', '.join(cols)}." if cols else ""))
    return "\n".join(lines)
