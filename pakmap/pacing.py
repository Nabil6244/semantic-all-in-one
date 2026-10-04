"""PakMap pacing, applied by the PakMap app layer only (pakmap.app_integration: Check plan and Generate), never by the
shared compiler, so Hybrid Map and anything else that compiles pakMap rows is unchanged.

The reference (sample.mov, 5.4 min) keeps the map on screen and changes something small every ~2.4 s; a picture (photo card,
filmstrip, sticker, a short footage insert) arrives about every 10-20 s and is up more than half the time, often handing over
straight to the next card. Two things here:

* card handoff: a photo card that starts at the same corner while an earlier card is still up replaces it: the earlier card
  ends just after the new one has snapped in, so it fades out under it instead of peeking out behind it until its own end;
* density warnings (never errors, never a renderer rule): a long stretch of narration with no picture, a long PART with few
  picture moments per minute, more than one footage insert in a PART. A PART marked abstract (hud_title params
  {"pacing": "abstract"}) is not measured: a reflective passage needs no picture, and none should be invented for it."""

from __future__ import annotations

from typing import Dict, List, Sequence

PICTURE_TYPES = ("pip", "filmstrip", "sticker", "media_full")
CARD_OUT_S = 0.45          # pakmap-engine TIMING.cardOut: a card's fade-out
HANDOFF_MIN_S = 1.0        # an earlier card is never cut to less than this on screen
MOMENT_JOIN_S = 1.5        # pictures that start this close together are one picture moment (two cards side by side)
MAX_PICTURE_GAP_S = 25.0   # narration with no picture for longer than this is sparse
LONG_PART_S = 60.0         # density per minute is only judged on a PART at least this long
MIN_MOMENTS_PER_MIN = 3.0
INSERT_MAX_S = 12.0        # a footage insert is short: about 5-12 s


def apply_card_handoff(spec: dict, report) -> List[str]:
    """Shorten an earlier photo card that a later card at the same anchor replaces. Returns notes for the plan."""
    notes: List[str] = []
    cards = sorted((e for e in spec.get("events", []) if e.get("type") == "pip"), key=lambda e: e["t_in"])
    info = {e.id: e for e in getattr(report, "events", [])}
    for i, a in enumerate(cards):
        for b in cards[i + 1:]:
            if b["t_in"] >= a["t_out"]:
                break
            if (b.get("anchor") or "tr") != (a.get("anchor") or "tr"):
                continue  # side by side (tl + tr ...): both stay
            new_out = round(max(a["t_in"] + HANDOFF_MIN_S, b["t_in"] + CARD_OUT_S), 3)
            if new_out < a["t_out"]:
                notes.append(f"photo card {a['id']!r} hands over to {b['id']!r} at {b['t_in']:.1f}s (same corner): it now ends at {new_out:.1f}s")
                a["t_out"] = new_out
                if a["id"] in info:
                    info[a["id"]].t_out = new_out
            break
    return notes


def _moments(starts: Sequence[float]) -> List[float]:
    out: List[float] = []
    for t in sorted(starts):
        if not out or t - out[-1] > MOMENT_JOIN_S:
            out.append(t)
    return out


def density_warnings(spec: dict, report, rows: Sequence = ()) -> List[str]:
    """Plain-language warnings about picture pacing, per PART (an item: its hud_title names it)."""
    events = getattr(report, "events", [])
    if not events:
        return []
    titles: Dict[int, str] = {}
    abstract = set()
    for r in rows:
        if r.layer_type == "hud_title" and r.item_no not in titles:
            titles[r.item_no] = " ".join(x for x in (r.label_text, r.sub_text) if x).strip()
            if str((r.params or {}).get("pacing", "")).lower() == "abstract":
                abstract.add(r.item_no)
    by_item: Dict[int, list] = {}
    for e in events:
        by_item.setdefault(e.item, []).append(e)
    out: List[str] = []
    for item in sorted(by_item):
        evs = by_item[item]
        t0, t1 = min(e.t_in for e in evs), max(e.t_out for e in evs)
        name = f"PART {item}" + (f" ({titles[item]})" if titles.get(item) else "")
        pics = [e for e in evs if e.type in PICTURE_TYPES]
        inserts = sorted({e.row: e for e in pics if e.type == "media_full"}.values(), key=lambda e: e.t_in)
        if len(inserts) > 1:
            out.append(f"{name}, {t0:.1f}-{t1:.1f}s: {len(inserts)} full-screen footage inserts (rows {', '.join(str(e.row) for e in inserts)}); "
                       f"PakMap stays on the map, so prefer about one short insert per PART")
        for e in inserts:
            span = max((x.t_out for x in pics if x.row == e.row), default=e.t_out) - e.t_in
            if span > INSERT_MAX_S + 1e-6:
                out.append(f"{name}: the footage insert on row {e.row} is {span:.1f}s long; an insert is short (about 5-{INSERT_MAX_S:g}s) so the map stays the main surface")
        if item in abstract:
            continue
        moments = _moments([e.t_in for e in pics])
        # a gap runs from the moment the last picture LEFT the screen to the next one arriving
        gaps, shown_until = [], t0
        for e in sorted(pics, key=lambda x: x.t_in):
            if e.t_in > shown_until:
                gaps.append((shown_until, e.t_in))
            shown_until = max(shown_until, e.t_out)
        gaps.append((shown_until, t1))
        for a, b in gaps:
            if b - a > MAX_PICTURE_GAP_S:
                out.append(f"{name}: no picture from {a:.1f}s to {b:.1f}s ({b - a:.0f}s of narration); if the narration names a person, object, flag, "
                           f"place or event there, give it a photo card (or mark the PART abstract with hud_title params {{\"pacing\": \"abstract\"}})")
        span = t1 - t0
        if span >= LONG_PART_S:
            rate = len(moments) / (span / 60.0)
            if rate < MIN_MOMENTS_PER_MIN:
                out.append(f"{name}, {t0:.1f}-{t1:.1f}s: {len(moments)} picture moment{'s' if len(moments) != 1 else ''} in {span:.0f}s "
                           f"({rate:.1f} per minute; about {MIN_MOMENTS_PER_MIN:g} or more keeps a long PART alive, one every 10-20 s); "
                           f"sparse only where the narration names things that could be shown")
    return out


def apply_pacing(res, csv_path) -> None:
    """Card handoff + density warnings on a compiled PakMap script (its CSV re-read for the PART titles)."""
    from .schema import parse_csv

    try:
        rows = parse_csv(csv_path)[0]
    except Exception:
        rows = []
    res.report.info.extend(apply_card_handoff(res.spec, res.report))
    res.report.warnings.extend(density_warnings(res.spec, res.report, rows))
