"""News Doc's optional plan: a story CSV, one row per sentence (docs/weather/news_doc_research.md §3.1).

    sentence,vo_anchor,part,shot,search,graphic,g_text,g_value,g_items,place,when

Every cell is optional. What a row fills in overrides News Doc's own choice for that sentence; what it leaves empty stays
automatic, and every News Doc graphic is still in the video (weather.newsdoc.plan.ensure_all). A row is matched to the narration by
its vo_anchor (the first words of the sentence as spoken), else by its sentence number (s1 = the first sentence).

  shot     news | broll | map | card | interview      (interview = news footage)
  search   the YouTube search (shot news) or the stock search (shot broll) for that sentence
  graphic  one of GRAPHICS below; g_text / g_value / g_items fill it (items separated by ";")
  place    the place the sentence is about ("Pecos County, TX"); when: its date or time

Never stops: a row that cannot be read or matched is left out with a note naming it. Saved in the project as
weather/newsdoc_story.csv (the Weather card's Load plan, when News Doc is the editing style)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FILE = "newsdoc_story.csv"
COLUMNS = ("sentence", "vo_anchor", "part", "shot", "search", "graphic", "g_text", "g_value", "g_items", "place", "when")
SHOTS = {"news": "news", "broll": "broll", "b-roll": "broll", "stock": "broll", "map": "map", "card": "card", "graphic": "card",
         "interview": "news", "drone": "news"}
GRAPHICS = {"place_tag": "place", "place": "place", "yellow_tag": "ytag", "ytag": "ytag", "big_number": "number", "number": "number",
            "corner_number": "number", "year": "year", "big_year": "year", "ring": "ring", "ring_gauge": "ring", "line_chart": "line",
            "line": "line", "bar_chart": "chart", "chart": "chart", "hbars": "hbars", "horizontal_bars": "hbars", "checklist": "checklist",
            "three_rings": "rings", "rings": "rings", "quote_card": "quote_card", "quote": "quote", "pull_quote": "pullquote",
            "pullquote": "pullquote", "name_tag": "nametag", "nametag": "nametag", "chapter": "chapter", "caption": "caption",
            "side_panel": "panel", "panel": "panel", "dossier": "dossier", "headline": "headline", "framed": "framed",
            "framed_picture": "framed", "polaroids": "polaroids", "forecast_strip": "forecast", "forecast": "forecast",
            "orange_tag": "orange_place", "orange_place": "orange_place"}
LENGTH = {"place": 3.6, "ytag": 3.2, "number": 3.4, "year": 3.0, "ring": 4.0, "line": 5.5, "chart": 5.0, "hbars": 5.0, "checklist": 5.5,
          "rings": 4.0, "quote_card": 5.0, "quote": 5.0, "pullquote": 5.0, "nametag": 3.5, "chapter": 2.5, "caption": 3.4, "panel": 5.5,
          "dossier": 4.4, "headline": 4.2, "framed": 4.5, "polaroids": 5.0, "forecast": 5.0, "orange_place": 3.4}


@dataclass
class Row:
    line: int                      # csv line, for notes
    sentence: str = ""
    vo_anchor: str = ""
    part: str = ""
    shot: str = ""
    search: str = ""
    graphic: str = ""
    g_text: str = ""
    g_value: str = ""
    g_items: List[str] = field(default_factory=list)
    place: str = ""
    when: str = ""


def _clean(text: str) -> str:
    """The CSV out of whatever an AI wrote around it (words before it, a code fence)."""
    text = str(text or "").lstrip("﻿")
    fence = re.search(r"```(?:csv)?\s*\n(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if "vo_anchor" in ln.lower() and "shot" in ln.lower()), None)
    return "\n".join(lines[start:]) if start is not None else ""


def is_story_csv(text: str) -> bool:
    return bool(_clean(text))


def parse(text: str, notes: Optional[List[str]] = None) -> List[Row]:
    notes = notes if notes is not None else []
    body = _clean(text)
    if not body:
        return []
    rows = list(csv.reader(io.StringIO(body)))
    head = [h.strip().lower() for h in rows[0]]
    out: List[Row] = []
    for n, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        d = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h in COLUMNS}
        shot = SHOTS.get(d.get("shot", "").lower(), "")
        if d.get("shot") and not shot:
            notes.append(f"story CSV line {n}: shot {d['shot']!r} is not one of {', '.join(sorted(set(SHOTS)))}; News Doc chooses it")
        graphic = GRAPHICS.get(d.get("graphic", "").lower().replace(" ", "_"), "")
        if d.get("graphic") and not graphic:
            notes.append(f"story CSV line {n}: graphic {d['graphic']!r} is not a News Doc graphic; left out")
        out.append(Row(n, d.get("sentence", ""), d.get("vo_anchor", ""), d.get("part", ""), shot, d.get("search", ""), graphic,
                       d.get("g_text", ""), d.get("g_value", ""), [x.strip() for x in re.split(r"[;|]", d.get("g_items", "")) if x.strip()],
                       d.get("place", ""), d.get("when", "")))
    return out


def load(project_root: "str | Path", notes: Optional[List[str]] = None) -> List[Row]:
    p = Path(project_root) / FILE
    try:
        return parse(p.read_text(encoding="utf-8"), notes) if p.is_file() else []
    except OSError:
        return []


def _norm(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower().replace("’", "'"))


def match(rows: List[Row], story, notes: Optional[List[str]] = None) -> Dict[int, Row]:
    """story line index -> its row: by vo_anchor (the sentence's first words), else by sentence number."""
    notes = notes if notes is not None else []
    lines = [_norm(x.text) for x in story.lines]
    out: Dict[int, Row] = {}
    for r in rows:
        want = _norm(r.vo_anchor)[:6]
        hit = None
        if want:
            hit = next((i for i, w in enumerate(lines) if i not in out and w[:len(want)] == want), None)
            if hit is None:
                hit = next((i for i, w in enumerate(lines) if i not in out and " ".join(want) in " ".join(w)), None)
        if hit is None:
            m = re.match(r"s?(\d+)$", r.sentence.strip().lower())
            if m and 0 < int(m.group(1)) <= len(lines) and int(m.group(1)) - 1 not in out:
                hit = int(m.group(1)) - 1
        if hit is None:
            notes.append(f"story CSV line {r.line}: {r.vo_anchor or r.sentence!r} is not in the narration; left out")
            continue
        out[hit] = r
    return out


def _num(text: str) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*\.?\d*", str(text))
    return float(m.group(0).replace(",", "")) if m else None


def graphic_params(kind: str, r: Row, line, story) -> Optional[Dict]:
    """The overlay parameters of a graphic the row asks for (its own cells first, the sentence's own words for what is missing)."""
    text, val, items = r.g_text, r.g_value, r.g_items
    title = (r.part or (story.parts[line.part][1] if line.part < len(story.parts) else "") or text or "").upper()
    if kind in ("place", "orange_place"):
        place = (text or r.place or (line.places[0][0] if line.places else "")).upper()
        return {"name": place, "sub": (line.states or story.states or [""])[0].upper()} if place else None
    if kind == "ytag":
        return {"text": (text or (line.yellow[0] if line.yellow else "")).upper()} if (text or line.yellow) else None
    if kind == "number":
        v = _num(val) if val else (line.numbers[0].value if line.numbers else None)
        if v is None:
            return None
        shown = val or line.numbers[0].shown
        return {"value": v, "shown": shown, "label": (text or (line.numbers[0].label if line.numbers else "")).upper(),
                "corner": r.graphic == "number" and "corner" in (r.g_text or "").lower()}
    if kind == "year":
        y = re.search(r"\b(1[89]\d\d|20\d\d)\b", val or text or line.text)
        return {"text": y.group(1)} if y else None
    if kind == "ring":
        v = _num(val) if val else next((n.value for n in line.numbers if n.shown.endswith("%")), None)
        return {"value": v, "label": text.upper()} if v is not None else None
    if kind in ("line", "chart", "hbars", "forecast"):
        pairs = [(p.split("=", 1)[0].strip(), p.split("=", 1)[1].strip()) for p in items if "=" in p]
        if not pairs and line.numbers:
            pairs = [("", n.shown) for n in line.numbers]
        vals = [_num(v) for _l, v in pairs]
        if len([v for v in vals if v is not None]) < 2:
            return None
        labels = [lab.upper() for lab, _v in pairs]
        unit = (val or (line.numbers[0].label if line.numbers else "")).upper()
        if kind == "forecast":
            return {"title": title, "days": labels[:5], "values": [v for _l, v in pairs][:5], "unit": unit}
        return {"title": title, "unit": unit, "values": [v for v in vals if v is not None], "shown": [v for _l, v in pairs], "labels": labels}
    if kind in ("checklist", "rings"):
        its = items or (line.items if kind == "checklist" else [])
        if kind == "rings":
            its = [i.upper() for i in its][:3]
            return {"items": its} if len(its) == 3 else None
        return {"title": (text or title or "IN THE PATH").upper(), "items": its[:6]} if len(its) >= 2 else None
    if kind in ("quote_card", "quote"):
        q = text or line.text
        words = re.sub(r"[.!?]+$", "", q).split()
        return {"text": q, "red": val or " ".join(words[-3:])}
    if kind == "pullquote":
        return {"text": text or line.text, "who": (val or "").upper(), "role": ""}
    if kind == "nametag":
        return {"name": (text or "").upper(), "role": (val or "").upper()} if text else None
    if kind in ("chapter", "caption"):
        return {"text": (text or title or line.text[:30]).upper()}
    if kind == "panel":
        bullets = items or [line.text]
        return {"title": (text or title or "WHY IT MATTERS").upper(), "bullets": bullets[:3]}
    if kind == "dossier":
        return {"title": (text or title).upper(), "fields": [("EVENT", text or title), ("DATE", r.when or "—"),
                                                            ("AREA", r.place or ", ".join(line.states) or "—"), ("STATUS", val or "—")]}
    if kind == "headline":
        return {"title": (text or line.text[:60]).upper(), "sub": " · ".join(x for x in (r.place, r.when) if x)}
    if kind == "framed":
        return {"caption": (text or r.place or title).upper()}
    if kind == "polaroids":
        labs = [i.upper() for i in items][:2] or ["BEFORE", "AFTER"]
        return {"title": (text or "TWO SIDES").upper(), "labels": labs if len(labs) == 2 else labs + ["AFTER"]}
    return None
