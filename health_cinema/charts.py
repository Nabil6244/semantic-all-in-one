"""Statistical charts from the numbers a sentence says: a bar chart (two values), a ranking (three or more), a line graph (values at years in order)
and a donut (one share of a whole). Used by the planner to turn some plain text cards into graphs, never all of them.

    chart_for(text) -> {"type": "bar" | "hbars" | "line", "points": [{"label", "value", "shown"}], "unit", "title"} | None
    donut_for(text) -> {"type": "donut", "points": [{"label", "value", "shown"}], "unit": "%", "title"} | None

Nothing is invented: every value and label comes from the sentence. A sentence with fewer than two comparable values (same unit) gives no chart."""
from __future__ import annotations
import re
from typing import Dict, List, Optional

from . import spoken as SP

FILLER = SP.STOP | {"a", "an", "have", "has", "had", "be", "been", "about", "around", "nearly", "almost", "roughly", "only", "just", "over", "under", "more", "less",
                    "than", "while", "whereas", "compared", "versus", "vs", "up", "to", "rate", "risk", "chance", "kills", "causes", "affects", "accounts",
                    "takes", "sees", "gets", "there", "were", "it", "its", "was", "is", "are", "then", "now", "today", "people", "cases", "deaths"}
CLAUSE_RE = re.compile(r"\s*(?:[,;:]|\band\b|\bbut\b|\bwhile\b|\bwhereas\b|\bcompared (?:with|to)\b|\bversus\b|\bvs\.?)\s*", re.I)
YEAR_RE = re.compile(r"^(19|20)\d\d$")
MAX_POINTS = 7
THRESHOLD = {"over", "under", "above", "below", "after", "before", "age", "aged", "ages", "within", "until", "past"}


def _numbers(text: str) -> List[dict]:
    """Every figure in the text: {value, i, j, unit, pct, year}. Same rules as spoken_number ('one ordinary morning' is not a figure)."""
    toks = SP._words(text); out = []; i = 0
    while i < len(toks):
        got = SP._value(toks, i) if toks[i] not in ",.;:!?" else None
        if not got: i += 1; continue
        v, j = got
        if toks[i].lower() in ("one", "a") and j == i + 1 and not (j < len(toks) and toks[j].lower() in ("in", "percent", "%")): i += 1; continue
        if i and toks[i - 1].lower() in THRESHOLD: i = j; continue      # "men over 45", "after 30": a cut-off, not an amount to chart
        pct = toks[i].endswith("%") or (j < len(toks) and toks[j].lower() == "percent")
        year = bool(YEAR_RE.match(toks[i])) and not pct
        unit = "%" if pct else ""
        if not pct and not year:
            k = j
            while k < len(toks) and toks[k][0].isalpha() and toks[k].lower() not in FILLER and k - j < 2: k += 1
            unit = " ".join(toks[j:k]).lower()
        out.append({"value": float(v), "i": i, "j": j + (1 if pct and not toks[i].endswith("%") else 0), "unit": unit, "pct": pct, "year": year, "toks": toks})
        i = j
    return out


def _shown(v: float, unit: str) -> str:
    for size, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= size * 10 or (v >= size and v % size == 0 and size >= 1e6):
            n = v / size; return (f"{n:.0f}" if n == int(n) else f"{n:.1f}") + suf
    s = f"{v:,.0f}" if v == int(v) else f"{v:,.1f}"
    return s + ("%" if unit == "%" else "")


def _label(words: List[str]) -> str:
    ws = [w for w in words if w[0].isalnum() and w.lower() not in FILLER]
    lab = " ".join(ws[-4:]).strip()
    return lab[:1].upper() + lab[1:]


def _same_unit(a: str, b: str) -> bool:
    if not a or not b: return True
    return a == b or a.split()[0] == b.split()[0]


def chart_for(text: str) -> Optional[Dict]:
    nums = _numbers(text)
    # line graph: values at two or more years, in time order ("In 1990 ... 12 million; by 2019 ... 18.6 million")
    years = [n for n in nums if n["year"]]
    if len(years) >= 2:
        pts = []
        for k, y in enumerate(years):      # each year takes the first figure after it, before the next year (or, for the last one, the figure just before it)
            nxt = years[k + 1]["i"] if k + 1 < len(years) else 10 ** 6
            vals = [n for n in nums if not n["year"] and y["i"] < n["i"] < nxt] or [n for n in nums if not n["year"] and (years[k - 1]["i"] if k else -1) < n["i"] < y["i"]]
            if vals: pts.append((int(y["value"]), vals[0]))
        if len(pts) >= 2 and [p[0] for p in pts] == sorted(p[0] for p in pts) and all(_same_unit(pts[0][1]["unit"], p[1]["unit"]) for p in pts):
            unit = next((p[1]["unit"] for p in pts if p[1]["unit"]), "")
            return {"type": "line", "unit": unit, "title": "",
                    "points": [{"label": str(y), "value": n["value"], "shown": _shown(n["value"], unit)} for y, n in pts[:MAX_POINTS]]}
    # bar chart / ranking: one figure per clause, the same unit, each with its own label ("Smokers 40 percent, non-smokers 15 percent")
    clauses = [c for c in CLAUSE_RE.split(text) if c and c.strip()]
    pts, unit = [], ""
    for c in clauses:
        ns = [n for n in _numbers(c) if not n["year"]]
        if len(ns) != 1: continue
        n = ns[0]; toks = n["toks"]
        if unit and n["unit"] and not _same_unit(unit, n["unit"]): return None      # mixed units are not one chart
        lab = _label(toks[:n["i"]]) or _label(toks[n["j"] + len(n["unit"].split()):])
        if not lab: continue
        unit = unit or n["unit"]; pts.append({"label": lab, "value": n["value"]})
    labels = [p["label"].lower() for p in pts]
    if len(pts) < 2 or len(set(labels)) < len(labels) or any(p["value"] <= 0 for p in pts): return None
    pts = pts[:MAX_POINTS]
    for p in pts: p["shown"] = _shown(p["value"], unit)
    if len(pts) >= 3: pts = sorted(pts, key=lambda p: -p["value"])
    return {"type": "hbars" if len(pts) >= 3 else "bar", "unit": unit, "title": "", "points": pts}


QUALIFIERS = (("up to", "Up to"), ("as many as", "As many as"), ("nearly", "Nearly"), ("almost", "Almost"), ("about", "About"), ("around", "About"), ("roughly", "About"), ("more than", "Over"), ("at least", "At least"))

def donut_for(text: str) -> Optional[Dict]:
    """One percentage that is a share of something ("80 percent of heart disease is preventable") -> a donut. Two or more percentages are a bar chart instead."""
    pcts = [n for n in _numbers(text) if n["pct"]]
    if len(pcts) != 1 or not 0 < pcts[0]["value"] <= 100: return None
    n = pcts[0]; toks = n["toks"]; after = toks[n["j"]:]
    if after and after[0].lower() == "of":      # "80 percent of heart disease is preventable" -> "of heart disease is preventable": the share and what it is
        ws = []
        for w in after:
            if w in ",.;:!?" or len(ws) == 8: break
            ws.append(w)
        lab = " ".join(ws)
    else: lab = _label(toks[:n["i"]])
    lab = lab if lab.startswith("of ") else lab[:1].upper() + lab[1:]
    pre = " ".join(w.lower() for w in toks[max(0, n["i"] - 2):n["i"]]); qual = next((q for k, q in QUALIFIERS if pre.endswith(k)), "")      # "up to 80%" is not "80%": the hedge stays with the figure
    if qual: lab = f"{qual} {_shown(n['value'], '%')} {lab}" if lab.startswith("of ") else f"{lab} ({qual.lower()} {_shown(n['value'], '%')})"
    return {"type": "donut", "unit": "%", "title": "", "points": [{"label": lab, "value": n["value"], "shown": _shown(n["value"], "%"), "qualifier": qual}]}
