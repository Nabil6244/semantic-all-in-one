"""Draws a board clip frame by frame (Pillow) and encodes it with ffmpeg. Default look: the Phase 1 board theme (theme.py: Patrick Hand body with
wide tracking, outlined Kalam Bold titles, flat objects with a thin dark outline); objects are still placeholder discs (icons are Phase 3), no
narrator. Passing an explicit `font_path` selects the legacy placeholder look of the feasibility stage. The drawing is deterministic: a frame
depends only on its time.

`instrument=True` adds what the verification reads back from a render: a 16-bit frame number in the top-left cells and a red border at the
exact frame edges. Production clips are drawn without it."""

from __future__ import annotations

import subprocess
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from . import anim as AN
from . import elements as E
from . import layout as LY
from . import theme as T
from .cues import NEW_KINDS, ResolvedCue

RECT_KINDS = NEW_KINDS + ("narrator",)       # items whose collision box is `rect` (the legacy kinds use `bbox`)

BOARD = (192, 192, 192)                      # about the board grey measured in the reference (#C0C0C0), compressed 640x360 source
INK = (40, 40, 40)
ROLES = {"blue": (40, 80, 170), "green": (30, 130, 70), "gold": (200, 150, 20), "red": (190, 40, 40)}
CODE_CELL = 20
TYPE_Y = (120, 860, 960)                     # y of the 1st, 2nd, 3rd typed line when a cue gives no position
POP_X0, POP_DX, POP_Y = 800, 380, 620
TITLE_C = (960, 400)
POP_R = 90
POP_IN_S, TITLE_IN_S = 0.25, 0.25


@dataclass
class Item:
    cue_id: str
    kind: str                                # type | pop | title
    onset: float                             # clip seconds
    text: str
    role: str
    pos: Tuple[int, int]
    cps: float
    type_duration: float
    hide_at: Optional[float]                 # clip second a later clear empties the board (None = stays)
    bbox: Tuple[int, int, int, int]          # x0, y0, x1, y1 the item can ever cover (largest overshoot)
    first_frame: int = 0
    # Milestone 1 kinds (header, card, icon, chip, arrow); unused by the legacy kinds
    slot: str = ""
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)   # the box the element occupies (collision box)
    asset: str = ""
    lines: Tuple[str, ...] = ()
    px: int = 0
    end: Tuple[float, float] = (0.0, 0.0)            # arrow: tip (pos is the start)
    grow_s: float = 0.4
    src: str = ""
    dst: str = ""
    reveal_frames: Tuple[int, ...] = ()              # caption: the clip frame each displayed word appears on
    rung: int = 0                                    # caption: the timing rung (1 all matched, 2 partial, 3 typed, 4 unresolvable)
    word_boxes: Tuple[Tuple[int, int, int, int], ...] = ()
    style: str = ""                                  # visual: the reference-style element
    tint: bool = False                               # visual line: draw in the role colour (else ink)
    align: str = ""                                  # visual line: "center" centres the text in its box
    vparams: Any = None                              # visual set / figure / crowd / prop: the cue's params (what to draw)


def _font(path: str, px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(6, int(px)))


def title_px(text: str, cx: int, base_px: float, sw: int, font_for) -> float:
    """The title size that keeps the whole word line inside the frame (80 px side margin around its centre cx); the usual size when it already fits."""
    f = font_for(base_px)
    x0, _y0, x1, _y1 = ImageDraw.Draw(Image.new("L", (4, 4))).textbbox((0, 0), text, font=f, anchor="mm", stroke_width=sw)
    half = max(1, min(cx, 1920 - cx) - 80)
    return base_px if (x1 - x0) <= 2 * half else base_px * (2 * half) / (x1 - x0)


def _overshoot(k: float) -> float:
    k = max(0.0, min(1.0, k))
    s = 1.5
    return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2


def layout(resolved: Sequence[ResolvedCue], font_path: Optional[str], fps: int, narrator=None) -> List[Item]:
    """Give every drawable cue a position and a bounding box. Every cue gets its own place, so detection and drawing never depend on what an
    earlier cue left behind. A clear cue empties everything that appeared before it."""
    ok = [r for r in resolved if not r.problems and r.onset_clip is not None]
    clears = sorted(r.onset_clip for r in ok if r.cue.kind == "clear")
    items: List[Item] = []
    n_type = n_pop = 0
    dummy = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    for r in ok:
        c = r.cue
        if c.kind == "clear" or c.kind in NEW_KINDS or c.kind == "narrator":
            continue
        later = [t for t in clears if t > r.onset_clip + 1e-9]
        hide = later[0] if later else None
        if c.kind == "type":
            pos = c.pos or (700, TYPE_Y[min(n_type, len(TYPE_Y) - 1)])
            n_type += 1
            if font_path is None:
                th = T.THEME
                x0, y0, x1, y1 = T.tracked_bbox(pos, T.body_text(th, c.text), T.font("body", th.body_px), th.body_px * th.tracking_em)
            else:
                x0, y0, x1, y1 = dummy.textbbox(pos, c.text, font=_font(font_path, 64))
            bbox = (x0 - 4, y0 - 4, x1 + 4, y1 + 4)
        elif c.kind == "title":
            pos = c.pos or TITLE_C
            if font_path is None:
                f, sw = T.font("title", title_px(c.text, pos[0], T.THEME.title_px * 1.15, 8, lambda q: T.font("title", q))), 8
            else:
                f, sw = _font(font_path, title_px(c.text, pos[0], 120 * 1.15, 6, lambda q: _font(font_path, q))), 6
            x0, y0, x1, y1 = dummy.textbbox(pos, c.text, font=f, anchor="mm", stroke_width=sw)
            bbox = (x0 - 4, y0 - 4, x1 + 4, y1 + 4)
        else:   # pop
            pos = c.pos or (POP_X0 + POP_DX * n_pop, POP_Y)
            n_pop += 1
            r_max = int(POP_R * 1.2)
            bbox = (pos[0] - r_max - 4, pos[1] - r_max - 4, pos[0] + r_max + 4, pos[1] + r_max + 110)
        bbox = (max(0, bbox[0]), max(0, bbox[1]), min(1920, bbox[2]), min(1080, bbox[3]))
        items.append(Item(c.id, c.kind, r.onset_clip, c.text, c.role, pos, c.cps, r.type_duration_s or 0.0, hide, bbox, r.first_frame or 0))
    if narrator is not None:      # the narrator is a layout object: its whole animated box is registered before any new element is placed
        allb, _settled = narrator.bounds()
        first = next(r for r in ok if r.cue.kind == "narrator" and r.first_frame == narrator.f_first)
        items.append(Item(first.cue.id, "narrator", narrator.f_first / fps, "", "", (int(allb[0]), int(allb[1])), 0.0, 0.0,
                          None if narrator.f_end is None else narrator.f_end / fps, LY.clamp((int(allb[0]), int(allb[1]), int(allb[2]), int(allb[3]))), narrator.f_first,
                          slot="narrator", rect=(int(allb[0]), int(allb[1]), int(math.ceil(allb[2])), int(math.ceil(allb[3])))))
    if any(r.cue.kind in NEW_KINDS for r in ok):
        items += _place_new(ok, items, clears)
    return items


def _place_new(ok: Sequence[ResolvedCue], placed: Sequence[Item], clears: Sequence[float]) -> List[Item]:
    """Give every Milestone 1 cue a slot, text fit and collision check. A problem is added to the cue (it is then not drawn); other cues are unaffected.
    Order: non-arrow cues in the order given, then arrows (they need their endpoints' boxes)."""
    new: List[Item] = []
    everything: List[Item] = list(placed)      # legacy items first: new cues avoid them, they never move

    def hide_of(t: float) -> Optional[float]:
        later = [c for c in clears if c > t + 1e-9]
        return later[0] if later else None

    def collides(rect, onset, hide, ignore=(), mine: str = "") -> Optional[str]:
        for o in everything:
            if o.cue_id in ignore or o.kind == "arrow" or o.style == "set":        # a backdrop is under everything
                continue
            if o.style == "prop" and mine in ("figure", "crowd", "prop"):           # props are scenery: figures stand in front of them and props may overlap each other
                continue
            if mine == "prop" and o.style in ("figure", "crowd"):
                continue
            box = o.rect if o.kind in RECT_KINDS else o.bbox
            if LY.visible_overlap(onset, hide, o.onset, o.hide_at) and LY.intersects(rect, box):
                return o.cue_id
        return None

    for r in (r for r in ok if r.cue.kind in NEW_KINDS and r.cue.kind != "arrow"):
        c = r.cue
        hide = hide_of(r.onset_clip)
        cls = c.kind
        w0, h0 = LY.DEFAULT_SIZE[cls]
        if cls == "visual":
            from . import styles as ST
            prm = c.params or {}
            if prm.get("style") in ST.CARTOON_STYLES:
                st_ = prm["style"]
                m = ST.measure(st_, "", prm, "")
                if m is None:
                    r.problems.append(f"cue {c.id}: the {st_} cannot be drawn ({__import__('explainer.cartoon.kit', fromlist=['kit']).problem(st_, prm) or 'unknown'})")
                    continue
                if st_ == "set":
                    rect_v = (0, 0, 1920, 1080)
                else:
                    rect_v = (int(c.pos[0]), int(c.pos[1]), int(c.pos[0]) + m["w"], int(c.pos[1]) + m["h"])
                    if not LY.inside(rect_v):
                        r.problems.append(f"cue {c.id}: the {st_} box {rect_v} is outside the {LY.MARGIN} px margins")
                        continue
                    hit = collides(rect_v, r.onset_clip, hide, mine=st_)
                    if hit:
                        r.problems.append(f"cue {c.id}: the {st_} at {tuple(c.pos)} collides with {hit!r}, which is on screen at the same time")
                        continue
                r.slot, r.lines, r.font_px = ("backdrop" if st_ == "set" else "free"), [], 0
                it = Item(c.id, "visual", r.onset_clip, "", c.role, (rect_v[0], rect_v[1]), c.cps, 0.0, hide, LY.clamp(rect_v), r.first_frame or 0, slot=r.slot, rect=rect_v, style=st_, vparams=dict(prm))
                new.append(it)
                everything.append(it)
                continue
            m = ST.measure(prm.get("style", ""), str(c.text), prm, c.asset)
            if m is None:
                r.problems.append(f"cue {c.id}: the {prm.get('style')} text {str(c.text)[:30]!r} does not fit")
                continue
            if prm.get("style") == "tag":
                m["w"], m["h"] = m["w"], m["h"]
            rect_v = (int(c.pos[0]), int(c.pos[1]), int(c.pos[0]) + m["w"], int(c.pos[1]) + m["h"])
            if not LY.inside(rect_v):
                r.problems.append(f"cue {c.id}: the box {rect_v} is outside the {LY.MARGIN} px margins")
                continue
            hit = collides(rect_v, r.onset_clip, hide, ignore=tuple(prm.get("over") or ()))       # a cross-out lies over its picture (schema v1.6)
            if hit:
                r.problems.append(f"cue {c.id}: the box at {tuple(c.pos)} collides with {hit!r}, which is on screen at the same time")
                continue
            r.slot, r.lines, r.font_px = "free", list(m["lines"]), m["px"]
            it = Item(c.id, "visual", r.onset_clip, str(c.text), c.role, (rect_v[0], rect_v[1]), c.cps, 0.0, hide, LY.clamp(LY.inflate(rect_v, 24)), r.first_frame or 0,
                      slot="free", rect=rect_v, asset=c.asset, lines=tuple(m["lines"]), px=m["px"], style=prm.get("style", ""), tint=bool(prm.get("tint", False)), align=str(prm.get("align", "")), vparams=dict(prm) if (prm.get("count") or "sv" in prm or "pv" in prm or prm.get("style") in ("bars", "photo") or prm.get("motion")) else None)
            it.word_boxes = (tuple(m.get("inner", (0, 0))),)
            if r.caption:                                            # a synced typed line: each word appears when it is spoken (the caption ladder of schema v1.2)
                it.reveal_frames = tuple(r.caption["reveal_frames"])
                it.rung = r.caption["rung"]
            new.append(it)
            everything.append(it)
            continue
        if cls == "caption":
            text = str(c.text).strip()
            cap = r.caption
            names = [c.slot] if c.slot else LY.SLOT_CLASS["caption"]
            chosen_c, why_c = None, ""
            for nm in (["pos"] if c.pos is not None else names):
                if nm != "pos" and (nm not in LY.SLOTS or nm not in LY.SLOT_CLASS["caption"]):
                    why_c = f"slot {nm!r} is not a caption slot ({', '.join(LY.SLOT_CLASS['caption'])})"
                    continue
                sr = LY.SLOTS[nm] if nm != "pos" else (int(c.pos[0]), int(c.pos[1]), int(c.pos[0]) + 1184, int(c.pos[1]) + 84)
                fit = LY.fit_text(text, sr[2] - sr[0] - 16, 70, "body", 52, 36, 1)
                if fit is None:
                    why_c = f"the text does not fit one line in slot {nm} ({sr[2] - sr[0] - 16} px) even at 36 px"
                    continue
                px_c, ln_c = fit
                fnt = T.font("body", px_c)
                tw = int(T.tracked_width(fnt, ln_c[0], px_c * T.THEME.tracking_em)) + 1
                asc, desc = fnt.getmetrics()
                th_ = asc + desc
                if nm == "pos":
                    rect_c = (sr[0], sr[1], sr[0] + tw + 16, sr[1] + th_ + 8)
                    if not LY.inside(rect_c):
                        why_c = f"the box {rect_c} is outside the {LY.MARGIN} px margins"
                        continue
                else:
                    cx_ = (sr[0] + sr[2]) // 2
                    cy_ = (sr[1] + sr[3]) // 2
                    rect_c = (cx_ - (tw + 16) // 2, cy_ - (th_ + 8) // 2, cx_ - (tw + 16) // 2 + tw + 16, cy_ - (th_ + 8) // 2 + th_ + 8)
                hit = collides(rect_c, r.onset_clip, hide)
                if hit is None:
                    chosen_c = (nm, rect_c, px_c, ln_c)
                    break
                why_c = f"slot {nm} is taken by {hit!r}" if nm != "pos" else f"the box at {tuple(c.pos)} collides with {hit!r}, which is on screen at the same time"
            if chosen_c is None:
                r.problems.append(f"cue {c.id}: no place for the caption ({why_c or 'none tried'})")
                continue
            nm, rect_c, px_c, ln_c = chosen_c
            x_text = rect_c[0] + 8
            fnt = T.font("body", px_c)
            tr_ = px_c * T.THEME.tracking_em
            boxes, off_ = [], 0
            asc, desc = fnt.getmetrics()
            for w_ in ln_c[0].split(" "):
                x0_ = x_text + sum(fnt.getlength(ch) for ch in ln_c[0][:off_]) + tr_ * off_
                boxes.append((int(x0_), rect_c[1] + 4, int(x0_ + T.tracked_width(fnt, w_, tr_)) + 1, rect_c[1] + 4 + asc + desc))
                off_ += len(w_) + 1
            r.slot, r.lines, r.font_px = nm, list(ln_c), px_c
            r.caption["slot"], r.caption["word_boxes"] = nm, [list(b_) for b_ in boxes]
            it = Item(c.id, "caption", r.onset_clip, text, c.role, (x_text, rect_c[1] + 4), c.cps, 0.0, hide, LY.clamp(LY.inflate(rect_c, 24)), r.first_frame or 0,
                      slot=nm, rect=rect_c, lines=tuple(ln_c), px=px_c, reveal_frames=tuple(r.caption["reveal_frames"]), rung=r.caption["rung"], word_boxes=tuple(tuple(b_) for b_ in boxes))
            new.append(it)
            everything.append(it)
            continue
        # text fit
        lines: Tuple[str, ...] = ()
        px = 0
        text = str(c.text).strip()
        rect_size = (w0, h0)
        if cls == "header":
            fit = LY.fit_text(text, w0, 70, "body", 60, 44, 1)
            if fit is None:
                r.problems.append(f"cue {c.id}: the header text does not fit one line of {w0} px even at 44 px")
                continue
            px, ln = fit
            lines = tuple(ln)
        elif cls == "chip":
            px = int((c.params or {}).get("px", T.THEME.chip_px))
            while px > 30 and E.chip_size(text, px)[0] > w0:
                px -= 2
            cw, ch = E.chip_size(text, px)
            if cw > w0:
                r.problems.append(f"cue {c.id}: the chip text is wider than the {w0} px chip slot even at 30 px")
                continue
            rect_size = (cw, ch)
        elif cls in ("card", "icon"):
            avail_w = w0 - 2 * LY.CARD_PAD - ((LY.CARD_ICON_PX + LY.CARD_ICON_GAP) if (cls == "card" and c.asset) else 0)
            avail_h = h0 - 24 - LY.CARD_PAD if cls == "card" else h0 - 220
            if text:
                fit = LY.fit_text(text, avail_w if cls == "card" else w0 - 2 * LY.CARD_PAD, avail_h, "body")
                if fit is None:
                    r.problems.append(f"cue {c.id}: the text does not fit the {cls} (at most {LY.FIT_MAX_LINES} lines, {LY.FIT_MIN_PX} px minimum)")
                    continue
                px, ln = fit
                lines = tuple(ln)
        # slot
        chosen: Optional[Tuple[str, LY.Rect]] = None
        why = ""
        if c.pos is not None:
            rect = (int(c.pos[0]), int(c.pos[1]), int(c.pos[0]) + rect_size[0], int(c.pos[1]) + rect_size[1])
            if not LY.inside(rect):
                r.problems.append(f"cue {c.id}: the box {rect} is outside the {LY.MARGIN} px margins")
                continue
            hit = collides(rect, r.onset_clip, hide)
            if hit:
                r.problems.append(f"cue {c.id}: the box at {tuple(c.pos)} collides with {hit!r}, which is on screen at the same time")
                continue
            chosen = ("pos", rect)
        else:
            names = [c.slot] if c.slot else LY.SLOT_CLASS[cls]
            for nm in names:
                if nm not in LY.SLOTS or nm not in LY.SLOT_CLASS[cls]:
                    why = f"slot {nm!r} is not a {cls} slot ({', '.join(LY.SLOT_CLASS[cls])})"
                    continue
                sr = LY.SLOTS[nm]
                if cls == "chip":        # centre the pill in its slot
                    cx = (sr[0] + sr[2]) // 2
                    sr = (cx - rect_size[0] // 2, sr[1] + (sr[3] - sr[1] - rect_size[1]) // 2, cx - rect_size[0] // 2 + rect_size[0], sr[1] + (sr[3] - sr[1] - rect_size[1]) // 2 + rect_size[1])
                hit = collides(sr, r.onset_clip, hide)
                if hit is None:
                    chosen = (nm, sr)
                    break
                why = f"slot {nm} is taken by {hit!r}"
            if chosen is None:
                r.problems.append(f"cue {c.id}: no free {cls} slot ({why or 'none tried'})")
                continue
        nm, rect = chosen
        r.slot, r.lines, r.font_px = nm, list(lines), px
        it = Item(c.id, c.kind, r.onset_clip, text, c.role, (rect[0], rect[1]), c.cps, r.type_duration_s or 0.0, hide, LY.clamp(LY.inflate(rect, 24)), r.first_frame or 0,
                  slot=nm, rect=rect, asset=c.asset, lines=lines, px=px, vparams=dict(c.params) if (c.params or {}).get("count") else None)
        new.append(it)
        everything.append(it)
    by_id = {i.cue_id: i for i in everything}
    for r in (r for r in ok if r.cue.kind == "arrow"):
        c = r.cue
        hide = hide_of(r.onset_clip)
        a, b = by_id.get(c.src), by_id.get(c.dst)
        if a is None or b is None:
            r.problems.append(f"cue {c.id}: an endpoint ({c.src!r} or {c.dst!r}) was not placed, so the arrow cannot be drawn")
            continue
        ra = a.rect if a.kind in RECT_KINDS else a.bbox
        rb = b.rect if b.kind in RECT_KINDS else b.bbox
        g = LY.arrow_geometry(ra, rb)
        if g is None:
            r.problems.append(f"cue {c.id}: {c.src!r} and {c.dst!r} are too close for an arrow (less than {LY.ARROW_MIN_LEN} px of shaft)")
            continue
        p0, p1 = g
        blocker = next((o.cue_id for o in everything if o.cue_id not in (c.src, c.dst) and o.kind != "arrow" and LY.visible_overlap(r.onset_clip, hide, o.onset, o.hide_at)
                        and LY.segment_hits(p0, p1, o.rect if o.kind in RECT_KINDS else o.bbox, pad=10)), None)
        if blocker:
            r.problems.append(f"cue {c.id}: the arrow would cross {blocker!r}")
            continue
        if not (LY.inside(LY.clamp((int(min(p0[0], p1[0])), int(min(p0[1], p1[1])), int(max(p0[0], p1[0])), int(max(p0[1], p1[1])))), (0, 0, LY.W, LY.H))):
            r.problems.append(f"cue {c.id}: the arrow leaves the frame")
            continue
        seg = LY.clamp((int(min(p0[0], p1[0])) - 12, int(min(p0[1], p1[1])) - 12, int(max(p0[0], p1[0])) + 12, int(max(p0[1], p1[1])) + 12))
        n0 = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        q = (p0[0] + (p1[0] - p0[0]) * min(1.0, 60.0 / n0), p0[1] + (p1[1] - p0[1]) * min(1.0, 60.0 / n0))
        # detection box: only the first 60 px of the shaft, where it starts to grow. The far end can touch an endpoint card that is still scaling in
        bb = LY.clamp((int(min(p0[0], q[0])) - 14, int(min(p0[1], q[1])) - 14, int(max(p0[0], q[0])) + 14, int(max(p0[1], q[1])) + 14))
        r.slot = f"{c.src}->{c.dst}"
        it = Item(c.id, "arrow", r.onset_clip, "", c.role, (p0[0], p0[1]), 0.0, 0.0, hide, bb, r.first_frame or 0, slot=r.slot, rect=seg, px=int((c.params or {}).get("width", 0)), end=p1, grow_s=c.grow_s, src=c.src, dst=c.dst)
        new.append(it)
        everything.append(it)
    return new


def draw_frame(items: Sequence[Item], t: float, size: Tuple[int, int], font_path: Optional[str], frame_no: int, instrument: bool, narrator=None, background: str = "grey",
               camera: str = "off", texture=False, n_frames: int = 0, fps: int = 30, camera_focus: Optional[Tuple[float, float]] = None) -> Image.Image:
    """camera / texture (both off by default; off returns the frame exactly as before): see explainer/motion/camera.py and texture.py. The camera needs the clip's `n_frames` (and `fps`)
    because it is a function of the clip length; it is not applied to instrumented frames (they must stay pixel-exact)."""
    W, H = size
    th = T.THEME
    if background in MATTES:                           # see-through boards: the frame is drawn once on black and once on white, and the difference gives each pixel's transparency
        im = Image.new("RGB", (W, H), MATTES[background])
    elif background != "grey" and font_path is None:
        from . import backdrops
        im = backdrops.image(background, (W, H))
    else:
        im = Image.new("RGB", (W, H), BOARD if font_path is not None else th.board)
    for it in items:                                   # a cartoon set is the backdrop: under the narrator and everything else
        if it.style == "set" and not (t + 1e-9 < it.onset or (it.hide_at is not None and t + 1e-9 >= it.hide_at)):
            E.draw_visual(im, it, t - it.onset, frame_no)
    d = ImageDraw.Draw(im)
    if narrator is not None:
        narrator.draw(im, frame_no)
    if any(AN.has_motion(i_.vparams) for i_ in items if i_.vparams):          # layers (bg/mid/fg) of moving elements: a stable sort, so everything else keeps its cue order
        items = sorted(items, key=lambda i_: AN.layer_of(i_.vparams))
    for it in items:
        if it.kind == "narrator" or it.style == "set":
            continue
        if t + 1e-9 < it.onset or (it.hide_at is not None and t + 1e-9 >= it.hide_at):
            continue
        age = t - it.onset
        if it.kind in NEW_KINDS:
            if it.kind == "caption":
                E.draw_caption(im, it, age, frame_no)
            elif it.kind == "visual":
                if it.vparams and AN.has_motion(it.vparams):                 # opt-in per-element motion (board/anim.py): only a cue with params["motion"] takes this path
                    AN.draw_moving(im, E.draw_visual, it, age, frame_no)
                else:
                    E.draw_visual(im, it, age, frame_no)
            else:
                {"header": E.draw_header, "card": E.draw_card, "icon": E.draw_icon, "chip": E.draw_chip, "arrow": E.draw_arrow}[it.kind](im, it, age)
            d = ImageDraw.Draw(im)
            continue
        if it.kind == "type":
            n = min(len(it.text), int(age * it.cps) + 1)          # the first character is on the onset frame itself
            if font_path is None:
                T.draw_tracked(d, it.pos, T.body_text(th, it.text)[:n], T.font("body", th.body_px), th.ink, th.body_px * th.tracking_em)
            else:
                d.text(it.pos, it.text[:n], font=_font(font_path, 64), fill=INK)
        elif it.kind == "title":
            s = 0.3 + 0.7 * _overshoot(age / TITLE_IN_S)
            if font_path is None:
                s *= title_px(it.text, it.pos[0], th.title_px * 1.15, 8, lambda q: T.font("title", q)) / (th.title_px * 1.15)
                d.text(it.pos, it.text, font=T.font("title", th.title_px * s), fill=th.title_fill, anchor="mm", stroke_width=max(1, int(8 * s)), stroke_fill=th.title_stroke)
            else:
                d.text(it.pos, it.text, font=_font(font_path, 120 * s), fill=(240, 200, 40), anchor="mm", stroke_width=max(1, int(6 * s)), stroke_fill=(60, 40, 20))
        else:
            s = 0.4 + 0.6 * _overshoot(age / POP_IN_S)
            r = int(POP_R * s)
            cx, cy = it.pos
            if font_path is None:
                T.draw_object(d, it.pos, r, it.role, th)
                if it.text and age >= POP_IN_S:
                    T.draw_tracked(d, (cx, cy + POP_R + 26), T.body_text(th, it.text), T.font("body", th.label_px), th.ink, th.label_px * th.tracking_em, anchor="m")
            else:
                col = ROLES.get(it.role, ROLES["blue"])
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(250, 250, 250), outline=col, width=10)
                if it.text and age >= POP_IN_S:
                    d.text((cx, cy + POP_R + 50), it.text, font=_font(font_path, 48), fill=col, anchor="mm")
    if instrument:
        for b in range(16):
            bit = (frame_no >> (15 - b)) & 1
            d.rectangle([b * CODE_CELL, 0, b * CODE_CELL + CODE_CELL - 1, CODE_CELL - 1], fill=(255, 255, 255) if bit else (0, 0, 0))
        d.rectangle([0, CODE_CELL, W - 1, H - 1], outline=(220, 0, 0), width=6)
    elif camera != "off" or texture:
        im = _finish(im, size, frame_no, camera, texture, n_frames, fps, camera_focus)
    return im


def _finish(im: Image.Image, size: Tuple[int, int], frame_no: int, camera: str, texture, n_frames: int, fps: int, camera_focus) -> Image.Image:
    """Opt-in camera + film texture on the finished frame (camera first, so the grain and vignette stay fixed to the screen)."""
    from ..motion import camera as CAM
    from ..motion import texture as TX
    box = CAM.camera_box(camera, n_frames, frame_no, fps, size, camera_focus)
    if box is not None:
        im = CAM.apply(im, box)
    mode = TX.normalize(texture)
    if mode:
        layer, _note = TX.get_layer(size)            # a missing asset gives layer None: plain frame (encode() reports the note)
        im = TX.apply(im, layer, frame_no, fps, mode)
    return im


MATTES = {"matte_black": (0, 0, 0), "matte_white": (255, 255, 255)}
ALPHA = "alpha"                       # background name for a see-through board: an RGBA QuickTime clip laid over a picture after the render
GLOW_RGB = (240, 233, 218)            # the paper colour of the soft glow behind text and cards, so dark ink reads on any picture
GLOW_ALPHA = 0.84


def matte_rgba(black: Image.Image, white: Image.Image, glow: bool = True) -> Image.Image:
    """One RGBA frame from the same frame drawn on black and on white: alpha = 1 - (white - black), colour = black / alpha. Exact for anything drawn by normal blending (text, sprites,
    shadows), with no change to the drawing code. `glow` lays a soft paper-coloured halo under every drawn element (wider than the element, feathered), so the board reads over a busy picture."""
    import numpy as np
    from PIL import ImageFilter
    b = np.asarray(black, dtype=np.float32) / 255.0
    w = np.asarray(white, dtype=np.float32) / 255.0
    a = np.clip(1.0 - (w - b).mean(axis=2), 0.0, 1.0)
    rgb = np.where(a[..., None] > 1e-3, np.clip(b / np.maximum(a[..., None], 1e-3), 0.0, 1.0), 0.0)
    if glow:
        H, W = a.shape
        small = Image.fromarray((a * 255).astype(np.uint8)).resize((max(1, W // 8), max(1, H // 8)), Image.BILINEAR)
        small = small.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(2.5))      # a soft rim about 20 px wide, not a sticker
        s = np.asarray(small.resize((W, H), Image.BILINEAR), dtype=np.float32) / 255.0
        s = np.clip(s * 2.0, 0.0, 1.0) * GLOW_ALPHA
        g = np.array(GLOW_RGB, dtype=np.float32) / 255.0
        out_a = a + s * (1.0 - a)
        rgb = (rgb * a[..., None] + g * (s * (1.0 - a))[..., None]) / np.maximum(out_a[..., None], 1e-3)
        a = out_a
    return Image.fromarray(np.dstack([(np.clip(rgb, 0, 1) * 255).astype(np.uint8), (a * 255).astype(np.uint8)]), "RGBA")


def encode(items: Sequence[Item], n_frames: int, fps: int, size: Tuple[int, int], out_path: Path, font_path: Optional[str], instrument: bool, narrator=None, background: str = "grey",
           camera: str = "off", texture=False, camera_focus: Optional[Tuple[float, float]] = None, notes: Optional[List[str]] = None) -> int:
    """`notes`, when given, receives one line per degraded opt-in (for example a missing texture asset). With camera "off" and texture False nothing changes.
    background "alpha": an RGBA QuickTime Animation clip (no camera, no texture: the picture under it moves instead)."""
    W, H = size
    if background == ALPHA:
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-an", "-c:v", "qtrle", "-pix_fmt", "argb", str(out_path)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        last = None
        for i in range(n_frames):
            blk = draw_frame(items, i / fps, size, font_path, i, False, narrator, "matte_black", "off", False, n_frames, fps)
            key = blk.tobytes()
            if key != last:                                  # a still stretch costs one matte, not one per frame
                frame = matte_rgba(blk, draw_frame(items, i / fps, size, font_path, i, False, narrator, "matte_white", "off", False, n_frames, fps)).tobytes()
                last = key
            p.stdin.write(frame)
        p.stdin.close()
        try:
            return p.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            p.kill()
            return -1
    if texture:
        from ..motion import texture as TX
        if TX.normalize(texture) and TX.get_layer(size)[0] is None and notes is not None:
            notes.append(TX.get_layer(size)[1])
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-an", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", "-preset", "medium", "-movflags", "+faststart", str(out_path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n_frames):
        p.stdin.write(draw_frame(items, i / fps, size, font_path, i, instrument, narrator, background, camera, texture, n_frames, fps, camera_focus).tobytes())
    p.stdin.close()
    try:
        return p.wait(timeout=3600)
    except subprocess.TimeoutExpired:
        p.kill()
        return -1
