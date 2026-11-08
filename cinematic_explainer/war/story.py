"""War Documentary story pass: the cold-open hook and the rhythm of long map stretches. Runs inside direction.apply, before shot treatment.

hook(plan, rows, cfg)
  The video never opens on text over the empty backdrop. When the opening scenes have no footage of their own (a 'none' row, or a clip
  dropped as off-topic), the first seconds become a fast montage of the video's own strongest clips (a teaser of what is coming: distinct
  clips from across the film, ~1.2 s hard cuts), and the opening title / date cards play OVER it instead of on an opaque plate. Only clips
  the plan already accepted for this video are used, never an unrelated one.

map_rhythm(plan, rows, cat, cfg)
  A run of back-to-back maps longer than RUN_MAX_S gets a graphic card in each map's scene, timed to the narration:
    the sentence opens with its date ("In May 2023, Russian forces captured Bakhmut") -> the date card slams in while the date is spoken,
      the map takes over as the place is named (it keeps its own clock, so pins and captures still land on their words);
    otherwise, once the map has shown what happened (its capture / its places have landed) -> the strongest card the sentence supports
      (a figure, things named, its own words as a kinetic line) holds the rest of the scene.
  Nothing is invented: every card is made from the sentence it sits under.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..render import Layer, Shot
from . import semantics as S

FPS = 25
HOOK_MAX_S = 14.0
HOOK_CUT_S = 1.25
HOOK_MIN_REL = 0.3                  # a teaser clip must have matched its own sentence (never an off-topic cut)
OPENER_MAX_S = 3.6
RUN_MAX_S = 12.0
DATE_CARD_MIN_S = 1.6
TAIL_CARD_MIN_S = 2.4
MAP_KINDS = ("tac_map", "tac_route", "map_card")
TEXT_OPENERS = {"kit_title", "kit_datecard", "kit_kinetic", "kit_keywords", "kit_quote"}


def fr(x: float) -> float:
    return round(round(x * FPS) / FPS, 4)


def _covered(plan: Any, a: float, b: float) -> float:
    tot = 0.0
    for s in plan.shots:
        lo, hi = max(a, s.start), min(b, s.end)
        if hi > lo:
            tot += hi - lo
    return tot


def _clip_len(path: str) -> float:
    try:
        from .segments import clip_duration

        return float(clip_duration(path) or 0.0)
    except Exception:
        return 0.0


# ================================================================================================================ the hook
def hook(plan: Any, rows: Sequence[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"montage_cuts": 0, "over": 0, "window": 0.0}
    rows = sorted(rows, key=lambda r: r["_start"])
    if not rows:
        return out
    end = 0.0
    for r in rows:                                     # the leading scenes that have no footage of their own
        if r["_start"] > end + 0.6 or r["_start"] >= HOOK_MAX_S:
            break
        if _covered(plan, r["_start"], r["_end"]) >= 0.5 * (r["_end"] - r["_start"]):
            break
        end = min(r["_end"], HOOK_MAX_S)
    if end < 2.0:
        return out
    rel: Dict[str, float] = {}                         # how well each clip matched its own sentence (footage_match); unknown = 0.3
    for r in rows:
        if r.get("footage"):
            m = r.get("footage_meta") or {}
            v = m.get("relevance")
            rel[str(r["footage"])] = float(v) if isinstance(v, (int, float)) else (0.0 if m.get("ai_generated") else 0.3)
    pool: List[Shot] = []
    seen = set()
    for s in sorted(plan.shots, key=lambda s: s.start):
        if s.start >= end - 0.01 and s.path not in seen and s.end - s.start >= 1.0 and rel.get(s.path, 0.3) >= HOOK_MIN_REL:
            seen.add(s.path)
            pool.append(s)
    if len(pool) > 8:                                  # the best-matched clips, still in story order
        best = set(id(x) for x in sorted(pool, key=lambda x: -rel.get(x.path, 0.3))[:8])
        pool = [x for x in pool if id(x) in best]
    later = [s for s in pool if s.start >= end + 8.0]           # a teaser of what is coming, not the very next scenes
    if len(later) >= 4:
        pool = later
    if not pool:
        return out
    n = max(2, int(math.ceil(end / HOOK_CUT_S)))
    picks = [pool[int(i * len(pool) / n) % len(pool)] for i in range(n)] if len(pool) >= n else [pool[i % len(pool)] for i in range(n)]
    t, k = 0.0, 0
    new: List[Shot] = []
    while t < end - 0.05 and k < len(picks):
        src = picks[k]
        ln = HOOK_CUT_S if end - t > HOOK_CUT_S * 1.5 else end - t
        dur = _clip_len(src.path)
        used = sum(1 for x in new if x.path == src.path)
        seek = src.seek + min(1.5, max(0.0, (src.end - src.start) - ln) / 2) + 2.6 * used     # a repeat shows another moment of it
        if dur > 0:
            seek = max(0.0, min(seek, dur - ln - 0.05))
        new.append(Shot(src.path, fr(t), fr(t + ln), round(seek, 3)))
        t += ln
        k += 1
    if new:
        new[-1] = Shot(new[-1].path, new[-1].start, fr(end), new[-1].seek)
    kept: List[Shot] = []
    for s in plan.shots:                               # a shot that runs on past the window keeps its tail, picked up where it was
        if s.start >= end - 0.01:
            kept.append(s)
        elif s.end > end + 0.2:
            kept.append(Shot(s.path, fr(end), s.end, round(s.seek + (end - s.start), 3), s.treat, 0.0))
    plan.shots[:] = kept + new
    plan.shots.sort(key=lambda s: s.start)
    for ly in plan.layers:                             # the opening words play over the montage, never on an opaque plate
        if ly.start < end - 0.05 and ly.kind in TEXT_OPENERS:
            ly.params = dict(ly.params or {}, over=True)
            ly.dim = False
            ly.end = fr(min(ly.end, ly.start + OPENER_MAX_S))     # the words land, then the montage plays clean
            out["over"] += 1
    out.update(montage_cuts=len(new), window=round(end, 2))
    return out


# ================================================================================================================ map rhythm
_DATE = re.compile(r"\b(?:on\s+)?(?:\d{1,2}\s+)?(?:(?:early|mid|late)[- ])?(January|February|March|April|May|June|July|August|September|October|November|"
                   r"December)(?:\s+\d{1,2})?,?\s+(?:19|20)\d{2}\b|\b(?:in|by|since)\s+(?:19|20)\d{2}\b|\b(?:that|this|last)\s+(?:autumn|spring|summer|"
                   r"winter|year)\b", re.IGNORECASE)


def _runs(plan: Any) -> List[List[Layer]]:
    maps = sorted([ly for ly in plan.layers if ly.kind in MAP_KINDS], key=lambda l: l.start)
    runs: List[List[Layer]] = []
    for ly in maps:
        if runs and ly.start - runs[-1][-1].end <= 1.5:
            runs[-1].append(ly)
        else:
            runs.append([ly])
    return runs


def _tail_card(sent: Any, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    from . import direction as D
    nums = [n for n in sent.numbers if not n.is_year]
    if nums:
        n = nums[0]
        lab = n.unit if n.unit and n.unit != "%" else " ".join(re.findall(r"[\w'’-]+", sent.text[n.span[1]:n.span[1] + 50])[:3])
        return "kit_bignum", {"value": n.raw, "label": lab.upper(), "sub": "", "colour": "yellow", "count": False}
    opts = {opt: params for opt, params, _s in D._floor_options(sent, True, True)}
    for opt in ("kit_icons", "kit_recap", "kit_kinetic"):          # full-frame cards (an overlay would sit on the empty backdrop)
        if opt in opts:
            return opt, opts[opt]
    return None


def map_rhythm(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from . import direction as D

    out = {"date_cards": 0, "tail_cards": 0}
    rows = sorted(rows, key=lambda r: r["_start"])
    for run in _runs(plan):
        if run[-1].end - run[0].start <= RUN_MAX_S:
            continue
        for ly in run:
            r = next((r for r in rows if r["_start"] - 0.05 <= ly.start < r["_end"]), None)
            if r is None or ly.end - ly.start < 3.0 or (ly.params or {}).get("total_dur"):
                continue                               # a building map (map_build) already lands something every few seconds
            text = str(r.get("text") or "")
            A = S.analyze_scene(text, cat, r.get("words"), r["_start"], r["_end"])
            sent = A.sentences[0] if A.sentences else None
            if sent is None:
                continue
            p = dict(ly.params or {})
            names = [str((x.get("name") if isinstance(x, dict) else x) or "") for x in p.get("places") or []]
            low = text.lower()
            name_at = [A.time_at(low.find(nm.lower())) for nm in names if nm and low.find(nm.lower()) >= 0]
            place_t = min(name_at) if name_at else None
            m = _DATE.search(text)
            if m and place_t is not None:
                date_t = A.time_at(m.start())
                a, b = fr(max(ly.start, date_t - 0.2)), fr(place_t - 0.3)
                if b - a >= DATE_CARD_MIN_S and a - ly.start < 1.0:
                    date = m.group(0).strip()
                    date = re.sub(r"^(?:on|in|by|since)\s+", "", date, flags=re.IGNORECASE)
                    shift = b - ly.start
                    plan.layers.append(Layer("kit_datecard", a, b, {"date": date[:1].upper() + date[1:], "sub": D._after_date(text, m.group(0))}, dim=False))
                    if a > ly.start + 0.05:                # a sliver of map before the card would flash: the card starts with the map
                        plan.layers[-1].start = ly.start
                    off0 = float(p.get("t_offset") or 0.0)
                    p["total_dur"] = round(float(p.get("total_dur") or 0.0) or (ly.end - ly.start + off0), 3)   # the map's own clock is unchanged
                    p["t_offset"] = round(off0 + shift, 3)
                    ly.start = b
                    ly.params = p
                    out["date_cards"] += 1
                    continue
            # the tail: once what happened has landed on the map
            landed = ly.start + 3.6
            for ev in p.get("control") or []:
                landed = max(landed, ly.start + float(ev.get("start", 0.8)) + float(ev.get("length", 1.8)) + 1.2)
            if ly.end - landed < TAIL_CARD_MIN_S:
                continue
            card = _tail_card(sent, text)
            if card is None:
                continue
            kind, params = card
            cut = fr(landed)
            plan.layers.append(Layer(kind, cut, ly.end, dict(params), dim=False))
            ly.end = cut
            out["tail_cards"] += 1
    return out
