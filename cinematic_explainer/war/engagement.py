"""War Documentary engagement check: where would this plan sag? Measured on the PLAN (no render), against what kept the 21-minute
reference watchable (docs/war/REFERENCE_AIR_DEFENSE.md): the cut rate never drops, something new lands every few seconds, the kind of
picture keeps rotating, a question or a turn comes every minute or two.

    check(plan, rows) -> {"blocks": [...], "issues": [...], "score": 0-100, "summary": str}
    fix(plan, rows, report) -> number of slow-block shots re-cut (only clips known to fit their sentence)
    text(report) -> the readable report written next to the video (<video>.engagement.txt) and logged after Generate scenes

Measures (0.5 s steps)
  cut rate        per 3-minute block: seconds between picture changes (a cut, or a full-frame graphic coming / going); flag above 5.5 s
  same picture    the longest stretch of one kind (footage, map, document, card, chart ...); flag maps above 25 s, anything else above 15 s
  nothing new     the longest stretch with no cut and no graphic or text starting; flag above 7 s
  turns           the gap between questions or turns in the narration ("So why ...?", "Then ...", "But ..."); flag above 150 s
  footage share   per block; noted when under 30 % (the reference keeps footage ~60 %)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

from ..render import Shot

STEP = 0.5
BLOCK_S = 180.0
CUT_SLOW_S = 5.5
SAME_MAX = {"map": 25.0}
SAME_DEFAULT = 15.0
NOTHING_NEW_S = 7.0
CARD_HOLD_S = 10.0
TURN_GAP_S = 150.0
FPS = 25
MAPS = {"tac_map", "tac_route", "map_card"}
DOCS = {"lay_document", "lay_satellite", "evidence_card", "lay_claim"}
CARDS = {"kit_quote", "lay_speaker_quote", "lay_figure_hero", "lay_figure_pair", "figure_card", "institution_card", "lay_equipment_hero",
         "lay_equipment_compare", "equipment_card"}
DATA = {"kit_chart", "lay_stat_split", "stat_compare", "stat_number", "kit_bignum", "kit_versus", "lay_timeline", "timeline", "split_compare"}
TEXTS = {"kit_title", "kit_datecard", "kit_kinetic", "kit_keywords", "kit_dossier", "kit_radar", "kit_icons", "kit_flag", "kit_recap", "kit_scale"}
SMALL = {"kit_grain", "kit_badge", "status_chip", "kicker", "source_label", "bc_source"}
_TURN = re.compile(r"\?\s*$|^\W*(then|but|so|meanwhile|now|yet|here is|here's|first|second|third|finally)\b", re.IGNORECASE)


def fr(x: float) -> float:
    return round(round(x * FPS) / FPS, 4)


def _mmss(t: float) -> str:
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def _kind_at(plan: Any, t: float) -> str:
    from .direction import FULL_KINDS

    full = [ly for ly in plan.layers if ly.start <= t < ly.end and ly.kind in FULL_KINDS and not (ly.params or {}).get("over")]
    if full:
        k = max(full, key=lambda l: l.start).kind
        return "map" if k in MAPS else "document" if k in DOCS else "card" if k in CARDS else "data" if k in DATA else "text card" if k in TEXTS else "graphic"
    if any(s.start <= t < s.end for s in plan.shots):
        return "footage"
    return "backdrop"


def check(plan: Any, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = max([r["_end"] for r in rows] + [s.end for s in plan.shots] + [0.0])
    times = [i * STEP for i in range(int(total / STEP))]
    kinds = [_kind_at(plan, t) for t in times]
    events = sorted({round(s.start, 2) for s in plan.shots} | {round(ly.start, 2) for ly in plan.layers if ly.kind not in SMALL}
                    | {round(ly.end, 2) for ly in plan.layers if ly.kind not in SMALL and ly.kind in _full()})
    changes = sorted({round(s.start, 2) for s in plan.shots} | {round(x, 2) for ly in plan.layers if ly.kind in _full() and not (ly.params or {}).get("over")
                                                                for x in (ly.start, ly.end)})
    issues: List[Dict[str, Any]] = []
    blocks = []
    b0 = 0.0
    while b0 < total - 1.0:
        b1 = min(total, b0 + BLOCK_S)
        ch = [c for c in changes if b0 <= c < b1]
        per = (b1 - b0) / max(1, len(ch))
        idx = [i for i, t in enumerate(times) if b0 <= t < b1]
        foot = sum(1 for i in idx if kinds[i] == "footage") / max(1, len(idx))
        blocks.append({"start": b0, "end": b1, "cut_s": round(per, 1), "footage": round(foot, 2)})
        if per > CUT_SLOW_S:
            issues.append({"kind": "slow", "start": b0, "end": b1, "text": f"{_mmss(b0)}-{_mmss(b1)}: one picture change every {per:.1f} s "
                                                                             f"(the reference never goes above ~4 s)"})
        if foot < 0.30 and b1 - b0 > 60:
            issues.append({"kind": "footage", "start": b0, "end": b1, "text": f"{_mmss(b0)}-{_mmss(b1)}: footage only {foot:.0%} of the time "
                                                                                f"(the reference keeps ~60 %)"})
        b0 = b1
    # same picture for too long
    i = 0
    while i < len(kinds):
        j = i
        while j + 1 < len(kinds) and kinds[j + 1] == kinds[i]:
            j += 1
        dur = (j - i + 1) * STEP
        lim = SAME_MAX.get(kinds[i], SAME_DEFAULT)
        if kinds[i] not in ("footage",) and dur > lim:
            issues.append({"kind": "same", "start": times[i], "end": times[j] + STEP,
                           "text": f"{_mmss(times[i])}-{_mmss(times[j] + STEP)}: {dur:.0f} s of {kinds[i]} without a change of picture"})
        i = j + 1
    # nothing new
    ev = [0.0] + [e for e in events if 0 < e < total] + [total]
    for a, b in zip(ev, ev[1:]):
        card = [ly for ly in plan.layers if ly.kind in _full() and not (ly.params or {}).get("over") and ly.start <= a + 0.05 and ly.end >= b - 0.05]
        lim = CARD_HOLD_S if card else NOTHING_NEW_S     # an animated card (typing, bars, highlight) holds like the reference's, up to 10 s
        if b - a > lim:
            issues.append({"kind": "still", "start": a, "end": b, "text": f"{_mmss(a)}-{_mmss(b)}: {b - a:.0f} s with no cut and nothing new on screen"})
    # turns in the narration
    turns = [r["_start"] for r in rows if any(_TURN.search(s.strip()) for s in re.split(r"(?<=[.?!])\s+", str(r.get("text") or "")) if s.strip())]
    tv = [0.0] + sorted(turns) + [total]
    for a, b in zip(tv, tv[1:]):
        if b - a > TURN_GAP_S:
            issues.append({"kind": "turn", "start": a, "end": b, "text": f"{_mmss(a)}-{_mmss(b)}: {b - a:.0f} s without a question or a turn in the "
                                                                         f"narration (script: add 'So why ...?' / 'Then ...' / 'But ...')"})
    issues.sort(key=lambda x: x["start"])
    weight = {"slow": 14, "same": 8, "still": 6, "turn": 10, "footage": 4}
    score = max(0, 100 - sum(weight.get(x["kind"], 5) for x in issues))
    return {"blocks": blocks, "issues": issues, "score": score, "total": total,
            "summary": f"engagement {score}/100: {len(issues)} spot(s) to look at" if issues else f"engagement {score}/100: no sagging stretch found"}


def _full() -> set:
    from .direction import FULL_KINDS

    return set(FULL_KINDS)


def fix(plan: Any, rows: Sequence[Dict[str, Any]], report: Dict[str, Any]) -> int:
    """Slow blocks: footage shots longer than 4.5 s on clips known to fit their sentence are re-cut into ~3 s pieces (different moments of
    the clip). Maps, cards and the narration are never touched here; the other findings are for the editor / script."""
    from .broadcast import _fits
    from .story import _clip_len

    slow = [(x["start"], x["end"]) for x in report["issues"] if x["kind"] in ("slow", "still")]
    if not slow:
        return 0
    fit_paths = {str(r["footage"]) for r in rows if r.get("footage") and _fits(r.get("footage_meta") or {})}
    out: List[Shot] = []
    n = 0
    for s in sorted(plan.shots, key=lambda s: s.start):
        dur = s.end - s.start
        if dur <= 4.5 or s.path not in fit_paths or not any(a - 0.01 <= s.start < b for a, b in slow):
            out.append(s)
            continue
        k = max(2, int(round(dur / 3.0)))
        piece = dur / k
        clen = _clip_len(s.path)
        for i in range(k):
            a, b = fr(s.start + i * piece), fr(s.end if i == k - 1 else s.start + (i + 1) * piece)
            seek = s.seek + i * piece * 1.3
            if clen > 0:
                seek = min(seek, max(0.0, clen - (b - a) - 0.1))
            out.append(Shot(s.path, a, b, round(seek, 3), s.treat, s.dissolve_in if i == 0 else 0.0))
        n += 1
    plan.shots[:] = out
    return n


def text(report: Dict[str, Any]) -> str:
    lines = [f"ENGAGEMENT CHECK ({report['summary']})", "", "Per 3 minutes (seconds between picture changes, footage share):"]
    for b in report["blocks"]:
        lines.append(f"  {_mmss(b['start'])}-{_mmss(b['end'])}  {b['cut_s']:.1f} s per change  ·  footage {b['footage']:.0%}")
    lines.append("")
    if report["issues"]:
        lines.append("Where it may sag:")
        lines += ["  " + x["text"] for x in report["issues"]]
    else:
        lines.append("No sagging stretch found.")
    if report.get("fixed"):
        lines += ["", f"Fixed automatically: {report['fixed']} long shot(s) re-cut in slow stretches (clips that fit their sentence)."]
    return "\n".join(lines) + "\n"
