"""Measure a War plan (shots + layers) against its narration, without rendering. Used for baselines, regression gates and the
integrated check before any render.

    python3 -m cinematic_explainer.war.plan_audit <plan.pkl>          # pickle of {"plan": Plan, "scenes": [scene dicts]}

Every measure is general (no video-specific rule):
  footage_share          screen time on real footage (not the backdrop plate)
  backdrop_only          time where the plate shows with no full-frame graphic over it (a background is not coverage)
  reuse                  source files shown on more than MAX_REUSE separate shots
  keyword_cards          kit_keywords layers
  kinetic_fragments      kinetic text that is not a complete line of the narration
  number_cards           big-number / stat cards whose value is not a quantity stated in the narration
  map_foreign_places     tactical maps that pin a place the narration does not name while the map is on screen (+- MAP_SLACK_S)
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Sequence, Tuple

MAX_REUSE = 2
MAP_SLACK_S = 2.0
BACKDROP_MARK = "war_backdrop"
NUMBER_KINDS = ("kit_bignum", "stat_number", "lay_stat_split")
_DIGIT = re.compile(r"\d")


def _sf(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def scene_span(s: Dict[str, Any]) -> Tuple[float, float]:
    a = s.get("_start", s.get("start"))
    b = s.get("_end", s.get("end"))
    return _sf(a), _sf(b)


def scene_text(s: Dict[str, Any]) -> str:
    return str(s.get("text") or s.get("script_segment") or s.get("narration") or "")


def _merge(spans: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for a, b in sorted(spans):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _length(spans: Sequence[Tuple[float, float]]) -> float:
    return sum(b - a for a, b in _merge(spans))


def _minus(spans: Sequence[Tuple[float, float]], cut: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    out = []
    cut = _merge(cut)
    for a, b in _merge(spans):
        cur = a
        for c, d in cut:
            if d <= cur or c >= b:
                continue
            if c > cur:
                out.append((cur, c))
            cur = max(cur, d)
        if cur < b:
            out.append((cur, b))
    return out


_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                                     "seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


def spelled_to_digits(t: str) -> str:
    """'Ninety-six drones' -> '96 drones' (so a card showing 96 matches the line that says it in words)."""
    def rep(m: "re.Match[str]") -> str:
        a, b = m.group(1).lower(), (m.group(2) or "").lower()
        if a in _TENS:
            return str(_TENS[a] + _UNITS.get(b, 0))
        return str(_UNITS[a])
    words = "|".join(sorted(list(_UNITS) + list(_TENS), key=len, reverse=True))
    return re.sub(rf"\b({words})(?:[- ]({'|'.join(_UNITS)}))?\b", rep, t, flags=re.I)


def _said(scenes: Sequence[Dict[str, Any]], a: float, b: float) -> str:
    return " ".join(scene_text(s) for s in scenes if scene_span(s)[1] > a and scene_span(s)[0] < b)


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", t.lower().replace("’", "'")).strip()


def _full_kinds() -> set:
    try:
        from .direction import FULL_KINDS
        return set(FULL_KINDS) - {"kit_field"}
    except Exception:  # noqa: BLE001
        return {"tac_map", "tac_route", "map_card", "lay_document", "kit_chart", "lay_timeline", "lay_equipment_hero", "lay_stat_split"}


def _layer_text(ly: Any) -> str:
    p = ly.params or {}
    for k in ("text", "title", "headline", "words", "label"):
        v = p.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            return " ".join(v)
    return ""


def _place_names(ly: Any) -> List[str]:
    p = ly.params or {}
    names = []
    for x in p.get("places") or []:
        n = x.get("name") if isinstance(x, dict) else x
        if isinstance(n, str) and n:
            names.append(n)
    return names


def source_ids(scenes: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Clip file -> the source it was cut from (YouTube id, library file, URL): several files cut from one video are one source."""
    out: Dict[str, str] = {}
    for s in scenes:
        f = s.get("footage")
        if not f:
            continue
        m = s.get("footage_meta") or {}
        sid = m.get("provider_asset_id") or m.get("video_id") or m.get("source_url") or m.get("library_file") or ""
        out[str(f)] = str(sid) if sid else str(f).rsplit("/", 1)[-1]
    return out


def audit(plan: Any, scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = max([scene_span(s)[1] for s in scenes] + [0.0])
    shots = list(getattr(plan, "shots", []) or [])
    layers = list(getattr(plan, "layers", []) or [])
    real = [(s.start, s.end) for s in shots if BACKDROP_MARK not in str(s.path)]
    footage_s = _length(real)
    full = _full_kinds()
    covered = real + [(ly.start, ly.end) for ly in layers if ly.kind in full]
    holes = _minus([(0.0, total)], covered)
    backdrop_only = [(round(a, 1), round(b, 1)) for a, b in holes if b - a >= 0.5]

    src = source_ids(scenes)
    uses: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for s in sorted(shots, key=lambda x: x.start):
        if BACKDROP_MARK in str(s.path):
            continue
        lst = uses[src.get(str(s.path), str(s.path).rsplit("/", 1)[-1])]
        if not lst or s.start - lst[-1][1] > 1.0:          # touching pieces of one shot are one use
            lst.append((s.start, s.end))
        else:
            lst[-1] = (lst[-1][0], s.end)
    reuse = {p: [round(a, 1) for a, _b in v] for p, v in uses.items() if len(v) > MAX_REUSE}

    kinds = Counter(ly.kind for ly in layers)
    kinetic_frag = []
    for ly in layers:
        if ly.kind != "kit_kinetic":
            continue
        txt = _norm(_layer_text(ly))
        if not txt:
            continue
        lines = [_norm(x) for x in re.split(r"(?<=[.?!])\s+", _said(scenes, ly.start, ly.end))]
        if not any(txt == ln for ln in lines if ln):
            kinetic_frag.append({"t": round(ly.start, 1), "text": _layer_text(ly)})

    numbers = []
    for ly in layers:
        if ly.kind not in NUMBER_KINDS:
            continue
        p = ly.params or {}
        val = str(p.get("value") or p.get("number") or p.get("big") or "")
        if not val:
            continue
        said = spelled_to_digits(_said(scenes, ly.start - MAP_SLACK_S, ly.end + MAP_SLACK_S)).replace(",", "")
        if not _DIGIT.search(val) or not re.search(rf"(?<![\w-]){re.escape(val.replace(',', ''))}(?![\w-])", said):
            numbers.append({"t": round(ly.start, 1), "kind": ly.kind, "value": val, "label": str(p.get("label") or "")})

    foreign = []
    for ly in layers:
        if ly.kind not in ("tac_map", "tac_route", "map_card"):
            continue
        said = _norm(_said(scenes, ly.start - MAP_SLACK_S, ly.end + MAP_SLACK_S))
        for nm in _place_names(ly):
            key = _norm(nm.split(" (")[0])
            if key and key not in said and key.split()[0] not in said:
                foreign.append({"t": round(ly.start, 1), "place": nm})

    return {"total_s": round(total, 1), "footage_s": round(footage_s, 1), "footage_share": round(footage_s / total, 3) if total else 0.0,
            "backdrop_only_s": round(sum(b - a for a, b in backdrop_only), 1), "backdrop_only": backdrop_only,
            "reuse": reuse, "keyword_cards": kinds.get("kit_keywords", 0), "kinetic": kinds.get("kit_kinetic", 0),
            "kinetic_fragments": kinetic_frag, "number_cards_bad": numbers, "map_foreign_places": foreign,
            "layers": dict(kinds.most_common())}


def text(rep: Dict[str, Any]) -> str:
    lines = [f"footage {rep['footage_s']} s of {rep['total_s']} s ({rep['footage_share'] * 100:.0f}%)",
             f"backdrop only {rep['backdrop_only_s']} s in {len(rep['backdrop_only'])} stretches",
             f"clips used more than {MAX_REUSE}x: {len(rep['reuse'])}",
             f"keyword cards {rep['keyword_cards']}, kinetic {rep['kinetic']} ({len(rep['kinetic_fragments'])} fragments)",
             f"number cards without a stated quantity: {len(rep['number_cards_bad'])}",
             f"map places not named while on screen: {len(rep['map_foreign_places'])}"]
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    import json
    import pickle

    d = pickle.load(open(argv[0], "rb"))
    rep = audit(d["plan"], d["scenes"])
    print(text(rep))
    if len(argv) > 1:
        open(argv[1], "w").write(json.dumps(rep, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
