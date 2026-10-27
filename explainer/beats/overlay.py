"""Map overlay (Phase D of docs/explainer/explainer_major_upgrade_plan.md): arrows, a stamp, plates, a pin disc with a cast figure and a draw-on outline, drawn by the Explainer on a TRANSPARENT clip
that is placed over a map beat the application renders. Nothing here edits hybrid/ or pakmap/ (both are read only, through explainer.beats.framing).

Why a separate clip: the Hybrid plan (hybrid/plan.py LAYER_TYPES = hud_title, marker, zone_label, fill, line, stat, caption, template) cannot stack a user clip over a map beat, so the overlay is rendered
with the Explainer's own drawing code (board arrow, motion stamp/plate sprites, cartoon figures) and composited with ffmpeg by `composite_over` wherever the caller decides.

Geometry: a cue is placed with the view the framing proof says is in force (`framing.plan_views` / `view_at`, the same rule `check_framing` uses) projected with `framing.project` (the engine's own
projection) on the 1920 x 1080 reference frame; `composite_over` scales the overlay to the map clip. An element that would leave the safe area of that view (4% margin, caption band kept free) is DROPPED with
a note, never an error. A cue ends where the next camera step of the beat starts, because after that the map moves under the overlay.

API:  plan_overlay(beat, words, cues, ...) -> plan dict (cue records, notes)   render_overlay(plan, out_path, ...) -> stats   composite_over(map_clip, overlay_clip, out_path, ...)
Cue specs (dicts), all times come from the spoken words of the beat (`word` = a phrase that must be spoken inside the beat; an optional `occurrence`):
  {"type": "arrow",   "from": "Germany", "to": "France", "role": "red"}                    grows from the spoken start of `from` (or `word`)
  {"type": "outline", "place": "Switzerland", "role": "red", "tint": true}                 draws on around the place at its spoken start; no polygon -> a ring (noted)
  {"type": "stamp",   "text": "SURROUNDED", "word": "surrounded", "place": optional, "role": "red"}
  {"type": "plate",   "text": "JUNE 1940", "word": "1940", "place": optional}           beside the place when one is given, else in the top-left corner
  {"type": "pin",     "place": "Switzerland", "figure": "gold", "pose": "idle"}          a glowing disc with a small cast figure standing on it
Opt-in flag proposal: DirectorOptions.mapoverlay (default False)."""

from __future__ import annotations

import math
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from . import framing as F
from .relevance import beat_tokens, find_phrase

W, H = 1920, 1080                      # the reference frame (the engine's default output)
FPS = 30
SAFE_MARGIN = F.MARGIN                 # fraction of the frame kept free on every side
BOTTOM_BAND = F.CAPTION_BAND           # captions and statistics sit here
OFFSET = {"arrow": 0.05, "outline": 0.0, "stamp": 0.1, "plate": 0.05, "pin": 0.1}      # seconds after the spoken word starts (all inside 0 to +0.3)
MAX_LATE_S = 0.3
ARROW_W = 14
ARROW_MIN_PX = 90
OUTLINE_S = 1.3
FIG_H = 210
DISC_W, DISC_H = 190, 64
REL_VERSION = 1

Rect = Tuple[float, float, float, float]


# ---------------------------------------------------------------- geometry
def safe_rect() -> Rect:
    return (W * SAFE_MARGIN, H * SAFE_MARGIN, W * (1 - SAFE_MARGIN), H * (1 - BOTTOM_BAND))


def rect_inside(r: Rect, s: Optional[Rect] = None) -> bool:
    s = s or safe_rect()
    return r[0] >= s[0] - 1e-6 and r[1] >= s[1] - 1e-6 and r[2] <= s[2] + 1e-6 and r[3] <= s[3] + 1e-6


def rects_overlap(a: Rect, b: Rect, gap: float = 0.0) -> bool:
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def beat_views(beat: Dict[str, Any], views=None):
    """The camera views of the beat as the framing proof sees them: [(time in force, (lon, lat, zoom), step)]. Pass `views` (framing.plan_views over the whole plan) when the camera carries over
    from earlier map beats."""
    return views if views is not None else F.plan_views([beat])


def camera_starts(beat: Dict[str, Any]) -> List[float]:
    """Times at which a camera step of this beat begins to move (the map moves under the overlay from then on)."""
    return sorted(float(c.get("t", beat["start"])) for c in beat.get("camera", []) if c.get("action") != "start")


def view_pixel(lon: float, lat: float, view: Sequence[float]) -> Tuple[float, float]:
    return F.project(lon, lat, view, W, H)


def _locate(place: str):
    return F._geo().resolve(place)


# ---------------------------------------------------------------- planning
def _word_t(tokens, phrase: str, occurrence: int = 1):
    m = find_phrase(tokens, phrase, occurrence)
    return m


def suggest_cues(beat: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Overlay cues a map beat's own fill layers suggest (an outline per filled place that is spoken); a convenience for the caller, never used implicitly."""
    return [{"type": "outline", "place": l["place"], "word": l["place"], "role": "red"} for l in beat.get("layers", []) if l.get("type") == "fill" and l.get("place")]


def plan_overlay(beat: Dict[str, Any], words: Sequence[Tuple[str, float, float]], cues: Sequence[Dict[str, Any]], *, views=None) -> Dict[str, Any]:
    """Cue records for a map beat. `beat` is the Hybrid-schema beat dict (id, start, end, camera), `words` the narration words [(word, start, end)] in absolute seconds.
    Returns {"beat", "start", "end", "fps", "size", "cues": [...], "dropped": [...], "notes": [...]}. A cue that cannot be placed inside the view is dropped and said; nothing raises for a cue."""
    start, end = float(beat["start"]), float(beat["end"])
    tk = beat_tokens(words, start, end)
    vws = beat_views(beat, views)
    starts = camera_starts(beat)
    out: Dict[str, Any] = {"v": REL_VERSION, "beat": beat.get("id", ""), "start": start, "end": end, "fps": FPS, "size": [W, H], "cues": [], "dropped": [], "notes": []}
    placed: List[Dict[str, Any]] = []

    def drop(i: int, spec: Dict[str, Any], why: str) -> None:
        out["dropped"].append({"index": i, "type": spec.get("type", ""), "why": why})
        out["notes"].append(f"overlay cue {i} ({spec.get('type', '?')}) left out: {why}")

    order = sorted(range(len(cues)), key=lambda k: (cues[k].get("type") in ("stamp", "plate"), k))       # cues tied to a place first: floating stamps and plates then find the free spots
    for i in order:
        spec = cues[i]
        try:
            rec = _plan_cue(i, spec, beat, tk, vws, starts, placed, out["notes"])
        except _Drop as d:
            drop(i, spec, str(d))
            continue
        except Exception as exc:              # never stop: a cue that cannot be planned is left out
            drop(i, spec, f"{type(exc).__name__}: {str(exc)[:80]}")
            continue
        placed.append(rec)
        out["cues"].append(rec)
    out["cues"].sort(key=lambda r: (r["t"], r["id"]))
    return out


class _Drop(Exception):
    pass


def _life(t: float, end: float, starts: Sequence[float]) -> float:
    nxt = [s for s in starts if s > t + 0.05]
    return min(end, nxt[0]) if nxt else end


def _blockers(rec_rects: Sequence[Rect], t0: float, t1: float, placed: Sequence[Dict[str, Any]], gap: float = 8.0, with_outline: bool = False):
    """The first placed element alive at the same time whose area meets one of `rec_rects`. An outline is only a line on the map, so it blocks floating stamps and plates (by its bounding box), not arrows or pins."""
    for p in placed:
        if p["type"] == "outline" and not with_outline:
            continue
        theirs = [tuple(p["bbox"])] if p["type"] == "outline" else p["rects"]
        if p["t"] < t1 and t0 < p["until"] and any(rects_overlap(a, tuple(b), gap) for a in rec_rects for b in theirs):
            return p
    return None


def _segment_rects(p0, p1, half: float = 26.0, step: float = 36.0) -> List[Rect]:
    n = max(1, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) // step))
    return [(p0[0] + (p1[0] - p0[0]) * k / n - half, p0[1] + (p1[1] - p0[1]) * k / n - half, p0[0] + (p1[0] - p0[0]) * k / n + half, p0[1] + (p1[1] - p0[1]) * k / n + half) for k in range(n + 1)]


def _plan_cue(i: int, spec: Dict[str, Any], beat: Dict[str, Any], tk, vws, starts, placed, notes) -> Dict[str, Any]:
    typ = spec.get("type")
    if typ not in OFFSET:
        raise _Drop(f"unknown cue type {typ!r}")
    end = float(beat["end"])
    phrase = spec.get("word") or spec.get("from") or spec.get("place") or ""
    if typ == "arrow" and not spec.get("word"):
        phrase = spec.get("from", "")
    m = _word_t(tk, phrase, int(spec.get("occurrence", 1))) if phrase else None
    if m is None:
        raise _Drop(f"{phrase!r} is not spoken inside this beat's narration")
    t = round(m["start"] + float(spec.get("offset_s", OFFSET[typ])), 4)
    if not 0.0 <= t - m["start"] <= MAX_LATE_S + 1e-9:
        raise _Drop("the offset puts the cue more than 0.3 s after its word")
    if t >= end - 0.4:
        raise _Drop("it would appear in the last 0.4 s of the beat")
    view = F.view_at(vws, t)
    if view is None:
        raise _Drop("no camera view is in force at that time")
    until = _life(t, end, starts)
    if until - t < 0.6:
        raise _Drop("the camera moves again less than 0.6 s after it would appear")
    role = spec.get("role", "red")
    rec: Dict[str, Any] = {"id": f"{beat.get('id', 'b')}_ov{i}_{typ}", "type": typ, "t": t, "until": round(until, 4), "role": role, "view": [round(v, 5) for v in view], "word_match": {"phrase": phrase, "start": m["start"], "end": m["end"]}}
    s = safe_rect()

    def pt(place: str) -> Tuple[float, float]:
        loc = _locate(place)
        return view_pixel(loc.lon, loc.lat, view)

    if typ == "arrow":
        a, b = pt(spec["from"]), pt(spec["to"])
        tm = _word_t(tk, spec["to"], int(spec.get("to_occurrence", 1)))
        grow = 0.7 if tm is None else max(0.4, min(1.2, tm["start"] - t))
        ux, uy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ux, uy)
        if L < ARROW_MIN_PX + 50:
            raise _Drop("the two places are too close together at this zoom for an arrow")
        ux, uy = ux / L, uy / L
        lo, hi = min(40.0, 0.12 * L), L - min(60.0, 0.2 * L)
        for _ in range(40):
            p0, p1 = (a[0] + ux * lo, a[1] + uy * lo), (a[0] + ux * hi, a[1] + uy * hi)
            rr = _segment_rects(p0, p1)
            blk = _blockers(rr, t, until, placed)
            if blk is None:
                break
            # shorten the end nearest to the blocker
            if any(rects_overlap(rr[-1], r, 8) for r in blk["rects"]):
                hi -= 20
            else:
                lo += 20
            if hi - lo < ARROW_MIN_PX:
                raise _Drop(f"it would cross {blk['id']}")
        else:
            raise _Drop("it would cross another overlay element")
        if not (rect_inside(_pt_rect(p0), s) and rect_inside(_pt_rect(p1), s)):
            raise _Drop("an end of the arrow would leave the camera view")
        rec.update(p0=[round(p0[0], 1), round(p0[1], 1)], p1=[round(p1[0], 1), round(p1[1], 1)], grow_s=round(grow, 3), rects=[list(r) for r in rr])
    elif typ == "outline":
        loc = _locate(spec["place"])
        poly_ok = getattr(loc, "is_area", False) and loc.polys
        rings: List[List[Tuple[float, float]]] = []
        if poly_ok:
            for poly in loc.polys:
                pts = [view_pixel(q[0], q[1], view) for q in (poly[0] if poly else [])]
                if len(pts) < 4:
                    continue
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                if rect_inside((min(xs), min(ys), max(xs), max(ys)), s):
                    rings.append(_simplify(pts))
            area = sum(_ring_len(r) for r in rings)
            if not rings or area < 120:
                poly_ok = False
        if poly_ok:
            xs = [p[0] for r in rings for p in r]
            ys = [p[1] for r in rings for p in r]
            rec.update(rings=[[[round(x, 1), round(y, 1)] for x, y in r] for r in rings], rects=[], bbox=[min(xs), min(ys), max(xs), max(ys)], tint=bool(spec.get("tint", True)), draw_s=OUTLINE_S, fallback="")
        else:
            c = view_pixel(loc.lon, loc.lat, view)
            r = float(spec.get("ring_px", 110))
            bb = (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
            if not rect_inside(bb, s):
                raise _Drop("the place (no polygon in the geo data) is outside the camera view")
            notes.append(f"overlay cue {i} (outline): no polygon inside the view for {spec['place']!r}: a ring is drawn instead")
            rec.update(rings=[], rects=[], bbox=list(bb), centre=[round(c[0], 1), round(c[1], 1)], radius=r, tint=False, draw_s=OUTLINE_S * 0.7, fallback="ring")
    elif typ == "pin":
        c = pt(spec["place"])
        fig = spec.get("figure", "gold")
        w = DISC_W
        box = (c[0] - w / 2, c[1] - FIG_H - 6, c[0] + w / 2, c[1] + DISC_H / 2)
        if not rect_inside(box, s):
            raise _Drop("the pin would leave the camera view")
        blk = _blockers([box], t, until, placed)
        if blk is not None:
            raise _Drop(f"it would overlap {blk['id']}")
        rec.update(c=[round(c[0], 1), round(c[1], 1)], figure=fig, pose=spec.get("pose", "idle"), kit=spec.get("kit", "a"), rects=[list(box)])
    elif typ in ("stamp", "plate"):
        from ..motion import sprites as MS
        text = " ".join(str(spec.get("text", "")).upper().split())
        meas = (MS.measure_stamp if typ == "stamp" else MS.measure_plate)(text, {"px": spec.get("px", 100 if typ == "stamp" else 44)})
        if not meas:
            raise _Drop("the text does not fit")
        w, h = meas["w"], meas["h"]
        cands = _candidates(typ, w, h, pt(spec["place"]) if spec.get("place") else None)
        chosen = None
        pad = 22 if typ == "stamp" else 6
        for avoid_outline in ((True, False) if typ == "stamp" else (True,)):          # a verdict stamp may land on the outlined country when nothing else is free (as in the reference)
            for cx, cy in cands:
                box = (cx - w / 2 - pad, cy - h / 2 - pad, cx + w / 2 + pad, cy + h / 2 + pad)
                if rect_inside(box, s) and _blockers([box], t, until, placed, with_outline=avoid_outline) is None:
                    chosen = (cx, cy, box)
                    break
            if chosen:
                break
        if chosen is None:
            raise _Drop("no free place inside the camera view")
        cx, cy, box = chosen
        rec.update(text=text, w=w, h=h, px=meas["px"], c=[round(cx, 1), round(cy, 1)], rects=[list(box)], variant=int(spec.get("variant", i % 3)))
    return rec


def _pt_rect(p) -> Rect:
    return (p[0], p[1], p[0], p[1])


def _candidates(typ: str, w: int, h: int, at: Optional[Tuple[float, float]]):
    out = []
    if at is not None:
        ax, ay = at
        if typ == "plate":
            out += [(ax, ay - h / 2 - 90), (ax, ay + h / 2 + 50), (ax + w / 2 + 70, ay - 30), (ax - w / 2 - 70, ay - 30)]
        else:
            out += [(ax + w / 2 + 40, ay - h / 2 - 110), (ax - w / 2 - 40, ay - h / 2 - 110), (ax, ay + h / 2 + 90), (ax, ay - h / 2 - 160)]
    if typ == "plate":
        out += [(w / 2 + 110, 130), (W - w / 2 - 110, 130), (w / 2 + 110, 250), (W - w / 2 - 110, 250)]
    else:
        out += [(x * W, y) for y in (250, 190, 700, 760, 480) for x in (0.74, 0.26, 0.5, 0.88, 0.12)]
    return out


def _ring_len(r: Sequence[Tuple[float, float]]) -> float:
    return sum(math.hypot(r[k][0] - r[k - 1][0], r[k][1] - r[k - 1][1]) for k in range(1, len(r)))


def _simplify(pts: Sequence[Tuple[float, float]], eps: float = 2.0) -> List[Tuple[float, float]]:
    out = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= eps:
            out.append(p)
    if out[-1] != pts[0]:
        out.append(pts[0])
    return out


# ---------------------------------------------------------------- drawing
def _over(canvas: Image.Image, sp: Image.Image, x: int, y: int) -> None:
    """Alpha-composite `sp` onto the RGBA canvas at (x, y), cropping what lies outside."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.width, x + sp.width), min(canvas.height, y + sp.height)
    if x1 <= x0 or y1 <= y0:
        return
    sub = sp.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    canvas.alpha_composite(sub, (x0, y0))


def _ease(k: float) -> float:
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


def _frame_of(age: float) -> int:
    return max(0, int(age * FPS + 1e-6))


def _role_rgb(role: str) -> Tuple[int, int, int]:
    from ..board import theme as T
    return T.THEME.roles.get(role, T.THEME.roles["red"])


def _arrow_state(rec, age):
    total = math.hypot(rec["p1"][0] - rec["p0"][0], rec["p1"][1] - rec["p0"][1])
    return max(6, int(round(total * _ease(age / max(0.05, rec["grow_s"])))))


def _draw_arrow(canvas, rec, age):
    from ..board import elements as E
    sp, xy = E.arrow_sprite((rec["p0"][0], rec["p0"][1]), (rec["p1"][0], rec["p1"][1]), _arrow_state(rec, age), rec["role"], ARROW_W)
    _over(canvas, sp, xy[0], xy[1])


@lru_cache(maxsize=256)
def _outline_sprite(rec_key: str, rings: Tuple, bbox: Tuple, frac_q: int, tint: bool, role: str) -> Tuple[Image.Image, Tuple[int, int]]:
    ss = 2
    pad = 24
    x0, y0, x1, y1 = int(bbox[0] - pad), int(bbox[1] - pad), int(bbox[2] + pad), int(bbox[3] + pad)
    big = Image.new("RGBA", ((x1 - x0) * ss, (y1 - y0) * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    col = _role_rgb(role)
    total = sum(_ring_len(r) for r in rings)
    budget = total * frac_q / 100.0
    if tint and frac_q >= 100:
        for r in rings:
            d.polygon([((x - x0) * ss, (y - y0) * ss) for x, y in r], fill=col + (58,))
    for wd, fill in ((9, (38, 38, 40, 255)), (5, col + (255,))):
        left = budget
        for r in rings:
            pts = [((x - x0) * ss, (y - y0) * ss) for x, y in r]
            seg_pts = [pts[0]]
            for k in range(1, len(pts)):
                sl = math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]) / ss
                if left >= sl:
                    seg_pts.append(pts[k])
                    left -= sl
                else:
                    f = left / sl if sl > 0 else 0
                    seg_pts.append((pts[k - 1][0] + (pts[k][0] - pts[k - 1][0]) * f, pts[k - 1][1] + (pts[k][1] - pts[k - 1][1]) * f))
                    left = 0
                    break
            if len(seg_pts) > 1:
                d.line(seg_pts, fill=fill, width=wd * ss, joint="curve")
            if left <= 0:
                break
    return big.resize((x1 - x0, y1 - y0), Image.LANCZOS), (x0, y0)


def _outline_state(rec, age):
    return min(100, int(100 * _ease(age / rec["draw_s"]) // 4 * 4)) if _ease(age / rec["draw_s"]) < 0.999 else 100


def _draw_outline(canvas, rec, age):
    q = _outline_state(rec, age)
    if rec.get("fallback") == "ring":
        c, r = rec["centre"], rec["radius"]
        ss = 2
        n = int(2 * r + 60)
        big = Image.new("RGBA", (n * ss, n * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        col = _role_rgb(rec["role"])
        a0 = -90
        for wd, fill in ((9, (38, 38, 40, 255)), (5, col + (255,))):
            d.arc([30 * ss, 30 * ss, (n - 30) * ss, (n - 30) * ss], a0, a0 + 360 * q / 100.0, fill=fill, width=wd * ss)
        _over(canvas, big.resize((n, n), Image.LANCZOS), int(c[0] - n / 2), int(c[1] - n / 2))
        return
    key = rec["id"]
    sp, xy = _outline_sprite(key, tuple(tuple(tuple(p) for p in r) for r in rec["rings"]), tuple(rec["bbox"]), q, rec["tint"], rec["role"])
    _over(canvas, sp, xy[0], xy[1])


def _stamp_state(rec, age):
    from ..motion import presets as P
    return min(_frame_of(age), P.SLAM_FRAMES - 1)


def _draw_stamp(canvas, rec, age):
    from ..motion import sprites as MS
    sp, (dx, dy) = MS.stamp_frame(rec["text"], rec["role"], rec["w"], rec["h"], rec["px"], MS.variant_for(rec["id"]), MS.available_cached(), MS.tilt_for(rec["id"]), _stamp_state(rec, age), rec["variant"])
    _over(canvas, sp, int(rec["c"][0] - sp.width // 2 + dx), int(rec["c"][1] - sp.height // 2 + dy))


def _plate_state(rec, age):
    from ..motion import presets as P
    return min(_frame_of(age), P.SLIDE_FRAMES - 1)


def _draw_plate(canvas, rec, age):
    from ..motion import presets as P
    from ..motion import sprites as MS
    dx, dy, alpha = P.plate_motion(age, rec["variant"])
    sp = MS._with_alpha(MS.plate_sprite(rec["text"], rec["role"], rec["w"], rec["h"], rec["px"]), alpha)
    _over(canvas, sp, int(rec["c"][0] - rec["w"] / 2 + dx), int(rec["c"][1] - rec["h"] / 2 + dy))


@lru_cache(maxsize=8)
def _disc(w: int, h: int, role: str) -> Image.Image:
    ss = 2
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = _role_rgb(role)
    for k in range(8):                                   # a soft glow: wide faint rings, then the bright disc
        g = 1 - k / 8
        m = int((1 - g) * 0.0 + k * 3 * ss)
        d.ellipse([m, m, w * ss - 1 - m, h * ss - 1 - m], fill=col + (int(16 + 14 * k),))
    d.ellipse([w * ss * 0.16, h * ss * 0.16, w * ss * 0.84, h * ss * 0.84], fill=(255, 255, 255, 235))
    return im.resize((w, h), Image.LANCZOS)


def _pin_state(rec, age):
    return min(_frame_of(age), 8)


def _draw_pin(canvas, rec, age):
    from ..board import elements as E
    cx, cy = rec["c"]
    k = E.scale_at(min(age, E.POP_IN_S))
    k = max(0.4, k)
    disc = _disc(DISC_W, DISC_H, rec["figure"])
    dw, dh = max(2, round(disc.width * k)), max(2, round(disc.height * k))
    _over(canvas, disc.resize((dw, dh), Image.BICUBIC), int(cx - dw / 2), int(cy - dh / 2))
    try:
        from ..cartoon import kit
        fig = kit.cast_sprite(rec["figure"], rec["pose"], rec["kit"], int(FIG_H * k / 0.62), False)       # the canvas is taller than the figure: scale so the figure is about FIG_H tall
        bb = fig.getchannel("A").getbbox()
        if bb:
            fx = int(cx - (bb[0] + bb[2]) / 2)
            fy = int(cy - 4 - bb[3])                                       # the feet stand on the disc's centre
            _over(canvas, fig, fx, fy)
    except Exception:
        pass                                                              # no cast art: the disc alone is the pin


DRAW = {"arrow": (_draw_arrow, _arrow_state), "outline": (_draw_outline, _outline_state), "stamp": (_draw_stamp, _stamp_state), "plate": (_draw_plate, _plate_state), "pin": (_draw_pin, _pin_state)}


def draw_frame(plan: Dict[str, Any], t_abs: float, cache: Optional[Dict[str, Any]] = None) -> Image.Image:
    """The overlay at absolute time t_abs as an RGBA image (transparent where nothing is drawn); a frame depends only on the plan and the time."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for rec in plan["cues"]:
        if rec["t"] - 1e-6 <= t_abs < rec["until"] - 1e-6:
            DRAW[rec["type"]][0](im, rec, max(0.0, t_abs - rec["t"]))
    return im


def frame_key(plan: Dict[str, Any], t_abs: float):
    return tuple((rec["id"], DRAW[rec["type"]][1](rec, max(0.0, t_abs - rec["t"]))) for rec in plan["cues"] if rec["t"] - 1e-6 <= t_abs < rec["until"] - 1e-6)


# ---------------------------------------------------------------- render + composite
CODECS = {"qtrle": ["-c:v", "qtrle", "-pix_fmt", "argb"],
          "prores4444": ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"],
          "vp9": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "20", "-auto-alt-ref", "0"]}
EXT = {"qtrle": ".mov", "prores4444": ".mov", "vp9": ".webm"}


def render_overlay(plan: Dict[str, Any], out_path: "str | Path", codec: str = "qtrle") -> Dict[str, Any]:
    """Write the overlay as an alpha clip of the beat's duration (QuickTime Animation by default: lossless, small for mostly empty frames). Returns {"frames", "seconds", "rendered", "path", "returncode"}.
    Frames whose drawn state is identical to the previous one are not redrawn."""
    import time
    n = max(1, int(round((plan["end"] - plan["start"]) * FPS)))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-map_metadata", "-1",
           *CODECS[codec], str(out_path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    empty = bytes(W * H * 4)
    last_key, last_bytes, drawn = None, empty, 0
    t0 = time.perf_counter()
    for i in range(n):
        t = plan["start"] + i / FPS
        key = frame_key(plan, t)
        if key != last_key:
            last_bytes = draw_frame(plan, t).tobytes() if key else empty
            last_key = key
            drawn += 1
        p.stdin.write(last_bytes)
    p.stdin.close()
    rc = p.wait(timeout=3600)
    return {"frames": n, "rendered": drawn, "seconds": round(time.perf_counter() - t0, 3), "path": str(out_path), "returncode": rc}


def composite_over(map_clip: "str | Path", overlay_clip: "str | Path", out_path: "str | Path", *, start_s: float = 0.0, crf: int = 12) -> int:
    """Lay the alpha overlay over a map clip with ffmpeg (the overlay starts `start_s` seconds into the map clip, is scaled to the map's size, the map's audio is kept). Returns ffmpeg's exit code.
    The result is H.264 yuv420p at the map clip's duration."""
    fc = f"[1:v]format=rgba,setpts=PTS-STARTPTS+{start_s}/TB,scale={{w}}:{{h}}[ov];[0:v][ov]overlay=0:0:format=auto:eof_action=pass[v]"
    w, h = probe_size(map_clip)
    fc = fc.replace("{w}", str(w)).replace("{h}", str(h))
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(map_clip), "-i", str(overlay_clip), "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-preset", "medium", "-c:a", "copy", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-map_metadata", "-1", "-movflags", "+faststart", str(out_path)]
    return subprocess.run(cmd).returncode


def probe_size(path: "str | Path") -> Tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)], capture_output=True, text=True)
    a, b = r.stdout.strip().split("x")
    return int(a), int(b)
