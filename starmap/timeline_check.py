"""The finished plan's rules, checked and repaired before anything is rendered (plan arithmetic only: no drawing, no AI, milliseconds).

StarMap and its Cinema option build a video in about twenty passes (budget, plates, variety, scenes, templates, cards, declutter,
pace, slivers ...) that each add, move or remove layers in one shared list. A pass does not know what another one assumed, so a
render could carry a combination nobody planned: declutter removed a full-screen number and left its plate (5 s of blank navy,
project #001 at 0:25), a CSV clip ran past its beat into the next clip (the render stopped), a time-jump card said
"15 NOV 2026 -> 15 NOV 2026". Each rule below holds for every second of every video whatever the passes did; a break is repaired
the general way and said in the notes. The screen check (repair.py, the engine's audit) still judges what the camera shows.

    footage_overlap   two footage shots on screen at once          the earlier one ends where the next begins
    footage_past_end  a shot past the end of the video             it ends with the video
    blank_plate       a full-screen plate with nothing drawn on it  removed (the map shows), or trimmed to what is drawn
    flash             a number, card or title up too short to read  removed
    same_date_jump    a time-jump card between two equal dates      removed
    no_time           a layer that ends before it starts           removed
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# drawn on a plate: what makes a plate a picture (corner instruments, citations, captions and titles are not)
NOT_GRAPHIC = {"tm_caption", "tm_title", "tm_clock", "tm_cite", "tm_fade", "tm_mission", "status_badge", "time_jump", "footnote",
               "watermark", "tracker", "cinema_plate", "cinema_plate_hero", "cinema_bubble"}
PLATE_MIN_COVER = 0.5      # a plate drawn on for less than this share of its time is trimmed to the drawing
PLATE_TAIL_S = 1.0         # ... plus this much, so the graphic's last frame is held a moment (What If's hold)
PLATE_MIN_S = 1.5          # a plate shorter than this after trimming is a flash: removed
FLASH_S = 1.0              # a number / card / title on screen shorter than this cannot be read
FLASH_TYPES = {"tm_metric", "stat_chip", "big_number", "photo_card", "tm_title", "title", "caption", "tm_caption"}
FOOTAGE_MIN_S = 0.3


def _span(L: Dict[str, Any]) -> Tuple[float, float]:
    return float(L.get("start", 0.0)), float(L.get("end", 0.0))


def _union(iv: List[Tuple[float, float]]) -> float:
    total, cur = 0.0, None
    for a, z in sorted(iv):
        if cur is None or a > cur[1]:
            if cur:
                total += cur[1] - cur[0]
            cur = [a, z]
        else:
            cur[1] = max(cur[1], z)
    return total + (cur[1] - cur[0] if cur else 0.0)


def _graphic(L: Dict[str, Any]) -> bool:
    t = str(L.get("type", ""))
    return t not in NOT_GRAPHIC and (t.startswith("tm_") or t.startswith("cinema_") or t in ("big_number", "photo_card"))


def _jump_sides(text: str) -> Tuple[str, str]:
    left, _, right = str(text or "").partition("→")
    return left.strip(), re.split(r"\s+·\s+", right.strip())[0].strip()


def check(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every break of the rules in the plan: [{kind, t0, t1, detail}] (nothing changed)."""
    out: List[Dict[str, Any]] = []
    D = float(spec.get("duration") or 0)
    layers = spec.get("layers") or []
    foot = sorted(spec.get("footage") or [], key=lambda f: float(f["start"]))
    for a, b in zip(foot, foot[1:]):
        if float(a["end"]) > float(b["start"]) + 0.01:
            out.append({"kind": "footage_overlap", "t0": float(b["start"]), "t1": float(a["end"]), "detail": f"{a.get('id')} runs into {b.get('id')}"})
    for f in foot:
        if D and float(f["end"]) > D + 0.01:
            out.append({"kind": "footage_past_end", "t0": D, "t1": float(f["end"]), "detail": str(f.get("id"))})
    graphics = [_span(L) for L in layers if _graphic(L)]
    for P in layers:
        if P.get("type") != "cinema_plate":
            continue
        a, z = _span(P)
        over = [(max(a, x), min(z, y)) for x, y in graphics if x < z and a < y]
        cover = _union(over) / max(1e-6, z - a)
        if cover < PLATE_MIN_COVER:
            out.append({"kind": "blank_plate", "t0": a, "t1": z, "detail": f"drawn on {round(100 * cover)}% of its time"})
    for L in layers:
        a, z = _span(L)
        if "start" in L and "end" in L and z <= a:
            out.append({"kind": "no_time", "t0": a, "t1": z, "detail": str(L.get("type"))})
        elif L.get("type") in FLASH_TYPES and "start" in L and z - a < FLASH_S:
            out.append({"kind": "flash", "t0": a, "t1": z, "detail": f"{L.get('type')} up {z - a:.1f} s"})
        elif L.get("type") == "time_jump":
            l, r = _jump_sides(L.get("text", ""))
            if l and l == r:
                out.append({"kind": "same_date_jump", "t0": a, "t1": z, "detail": str(L.get("text"))})
    return out


def enforce(spec: Dict[str, Any], notes: List[str]) -> int:
    """Repairs every break check() finds, in place; one note per rule. Returns how many were repaired."""
    D = float(spec.get("duration") or 0)
    layers = spec.get("layers") or []
    done: Dict[str, int] = {}
    bump = lambda k: done.__setitem__(k, done.get(k, 0) + 1)       # noqa: E731

    foot = sorted(spec.get("footage") or [], key=lambda f: float(f["start"]))
    for a, b in zip(foot, foot[1:]):
        if float(a["end"]) > float(b["start"]) + 0.01:
            a["end"] = round(float(b["start"]), 3)
            bump("footage_overlap")
    for f in foot:
        if D and float(f["end"]) > D + 0.01:
            f["end"] = round(D, 3)
            bump("footage_past_end")
    kept = [f for f in foot if float(f["end"]) - float(f["start"]) >= FOOTAGE_MIN_S]
    if "footage" in spec:
        spec["footage"] = kept

    drop: List[int] = []
    for i, L in enumerate(layers):
        a, z = _span(L)
        if "start" in L and "end" in L and z <= a:
            drop.append(i)
            bump("no_time")
        elif L.get("type") in FLASH_TYPES and "start" in L and z - a < FLASH_S:
            drop.append(i)
            bump("flash")
        elif L.get("type") == "time_jump":
            l, r = _jump_sides(L.get("text", ""))
            if l and l == r:
                drop.append(i)
                bump("same_date_jump")
    gone = {id(layers[i]) for i in drop}
    layers[:] = [L for L in layers if id(L) not in gone]

    graphics = [_span(L) for L in layers if _graphic(L)]
    blank: List[Dict[str, Any]] = []
    for P in layers:
        if P.get("type") != "cinema_plate":
            continue
        a, z = _span(P)
        over = [(max(a, x), min(z, y)) for x, y in graphics if x < z and a < y]
        if _union(over) / max(1e-6, z - a) >= PLATE_MIN_COVER:
            continue
        if over:
            a2, z2 = min(x for x, _ in over), min(z, max(y for _, y in over) + PLATE_TAIL_S)
            if z2 - a2 >= PLATE_MIN_S:
                P["start"], P["end"] = round(a2, 3), round(z2, 3)
                bump("blank_plate")
                continue
        blank.append(P)
        bump("blank_plate")
    if blank:
        layers[:] = [L for L in layers if not any(L is P for P in blank)]
    if spec.get("shots") is not None and done.get("blank_plate"):
        spec["shots"] = [s for s in spec["shots"] if s.get("kind") != "plate"] + \
                        [{"start": L["start"], "end": L["end"], "kind": "plate"} for L in layers if L.get("type") == "cinema_plate"]

    words = {"footage_overlap": "footage shot(s) ran into the next and now end where it begins",
             "footage_past_end": "footage shot(s) ran past the end of the video",
             "blank_plate": "full-screen plate(s) with nothing drawn on them removed or trimmed (the map shows instead)",
             "flash": "number(s) / card(s) up too briefly to read left out",
             "same_date_jump": "time-jump card(s) between two equal dates left out",
             "no_time": "layer(s) that ended before they started left out"}
    for k, n in done.items():
        notes.append(f"Timeline check: {n} {words[k]}")
    return sum(done.values())
