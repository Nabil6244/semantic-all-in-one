"""A Flow picture shown the way the reference shows it (docs/rep_theory/STUDY_tendons_arm_wrestling.md, section 2): full frame, not an inset; a real camera move toward
what the sentence is about; the next sentence on the same picture re-framed close on another part instead of repeating the shot; the red paint on the named muscle or
tendon hidden at the start of the shot and growing in on its word; the words in the picture's empty side.

`study(path)` reads a picture once (cached): where its subject is, where its red paint is, which side is free for text. `plan(scenes)` gives every picture scene its
framing (`sc["cam"]`) after the pictures are known. `render(cv, ctx, sc, t)` draws one frame and returns where the words go, or None when the picture is not a landscape
picture (library poses and portrait pictures keep the inset look)."""
from __future__ import annotations
import re
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from . import library as L, theme as T

WIDE_ASPECT = 1.45      # a picture at least this wide fills the frame; narrower ones stay an inset
PUSH = {"wide": (1.0, 1.05), "medium": (1.05, 1.12), "close": (1.12, 1.22)}      # gentle push on the framed subject (render final 3: Flow pictures shown full-bleed put the person at
# 97-100% of the screen height, touching the frame edge in every shot)
FOCUS_PULL = {"wide": 0.0, "medium": 0.5, "close": 0.8}      # how far the framing moves from the subject's centre toward the shot's focus point (its red part, its face)
SUBJECT_H = 0.72      # the subject's height on screen at the start of a wide shot (the reference keeps its person at ~55-75% with black around)
AREA = 0.60      # the picture's share of the frame width; the words have the rest
HEAD_ROOM = 0.06      # the top of the subject never comes closer than this to the top of the frame (fraction of the frame height), except on close shots
RED_MIN = 0.002      # share of the picture painted red before a reveal is drawn
RED_POINT_PX = 120      # fewer red pixels than a reveal needs still say where the named part is (a small glow on a wrist)
MOVING_PARTS = {"hands", "wrists", "fingers", "forearms", "arms", "feet", "elbows", "knees", "thumb", "thumbs", "grip"}      # where these are depends on the pose
REVEAL_S = 0.9
_cache: Dict[str, dict] = {}

def _red(a: np.ndarray) -> np.ndarray:
    """Pixels painted red (not the character's orange): strong red over green and blue."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return ((r > 120) & (r - g > 70) & (r - b > 60) & (g < 0.55 * r) & (g - b < 50)).astype(np.float32)      # orange (the waistband) has far more green than blue; red and pink do not

def _centroid(w: np.ndarray, default=(0.5, 0.5)) -> tuple:
    s = float(w.sum())
    if s < 1e-6: return default
    ys, xs = np.mgrid[0:w.shape[0], 0:w.shape[1]]
    return float((xs * w).sum() / s / w.shape[1]), float((ys * w).sum() / s / w.shape[0])

def study(path: str) -> Optional[dict]:
    """{img, size, wide, subject (x, y), red: mask or None, red_c (x, y), red_axis (x0, y0, x1, y1), free: 'left'|'right'} for one picture file; None when unreadable."""
    if path in _cache: return _cache[path]
    try: im = Image.open(path).convert("RGB")
    except Exception: _cache[path] = None; return None
    a = np.asarray(im, dtype=np.float32); lum = a.mean(axis=2); ink = np.clip((lum - 28) / 90, 0, 1)
    red = _red(a); share = float(red.mean()); W, H = im.size
    subj = _centroid(ink); halves = (float(ink[:, : W // 2].mean()), float(ink[:, W // 2:].mean()))
    rows = np.nonzero(ink.mean(axis=1) > 0.02)[0]; top = float(rows[0]) / H if len(rows) else 0.0      # where the subject starts (its head, usually)
    cols = np.nonzero(ink.mean(axis=0) > 0.02)[0]; bottom = float(rows[-1] + 1) / H if len(rows) else 1.0
    bbox = (float(cols[0]) / W, top, float(cols[-1] + 1) / W, bottom) if len(cols) and len(rows) else (0.0, 0.0, 1.0, 1.0)      # the drawn subject, without the black around it
    info = {"img": im, "size": (W, H), "wide": W / H >= WIDE_ASPECT, "subject": subj, "top": top, "bbox": bbox, "free": "right" if halves[0] >= halves[1] else "left", "red": None, "red_c": subj, "red_axis": None,
            "red_pt": _centroid(red) if float(red.sum()) >= RED_POINT_PX else None}      # 2026-11-02: a small red wrist glow, below RED_MIN, left the ring guessing a standing pose (it circled the waistband)
    if share >= RED_MIN:
        ys, xs = np.nonzero(red); info["red"] = red; info["red_c"] = _centroid(red)
        if xs.max() - xs.min() >= ys.max() - ys.min(): i0, i1 = xs.argmin(), xs.argmax()      # the reveal runs along the red region's long side, from the end nearer the picture's centre outwards
        else: i0, i1 = ys.argmin(), ys.argmax()
        p0, p1 = (xs[i0] / W, ys[i0] / H), (xs[i1] / W, ys[i1] / H)
        if abs(p1[0] - 0.5) + abs(p1[1] - 0.5) < abs(p0[0] - 0.5) + abs(p0[1] - 0.5): p0, p1 = p1, p0
        info["red_axis"] = (*p0, *p1)
        g = np.repeat(lum[..., None], 3, axis=2) * 0.85; info["grey"] = Image.fromarray(np.clip(a * (1 - red[..., None]) + g * red[..., None], 0, 255).astype("uint8"))      # the picture with its red paint turned to ink grey
    _cache[path] = info; return info

def _path(art: str) -> Optional[str]:
    e = L.find(art) if art else None
    return e.get("path") if e else None

BODY_WORD = re.compile(r"\b(tendons?|muscles?|forearms?|wrists?|hands?|fingers?|biceps?|triceps?|shoulders?|chest|back|core|abs|glutes?|quads?|thighs?|hamstrings?|calf|calves|knees?|elbows?|neck|spine|hips?|legs?|arms?|grip)\b", re.I)

def _reveal_at(sc: dict) -> float:
    """When the red grows in: the first word that names a body part, else just after the shot opens (seconds from the scene's start)."""
    for w in sc.get("words") or []:
        if BODY_WORD.search(str(w.get("w", ""))): return max(0.15, float(w["t0"]) - sc["start"] - 0.1)
    return 0.35

def plan(scenes: List[dict]) -> int:
    """Framing for every full-frame picture scene. A picture shown again in the next scene is re-framed: wide, then medium on its red part (or the upper part of its subject:
    the face and hands, where the action is), then close, then wide; never two close shots in a row. The CSV's `camera` column, when filled, wins. Returns how many scenes were re-framed."""
    n = 0; prev_art = None; run = 0; prev_mode = ""; prev_label = None
    for sc in scenes:
        if sc.get("kind") == "illus":      # the same part label on two picture scenes running is said once: the second keeps its glow and ring, without the label
            g = (sc.get("glows") or [None])[-1]; lab = (g.get("word") or g.get("label")) if g else None
            if lab and lab == prev_label: sc["_label_off"] = True
            else: sc.pop("_label_off", None)
            if lab: prev_label = lab
        if sc.get("kind") != "illus": prev_art = None; prev_mode = ""; continue
        info = study(_path(sc.get("art")) or "")
        if not info or not info["wide"]: prev_art = None; prev_mode = ""; continue
        run = run + 1 if sc.get("art") == prev_art else 0; prev_art = sc.get("art")
        mode, focus = "wide", info["subject"]
        if run:
            n += 1; mode = ("medium", "close", "wide")[(run - 1) % 3]      # medium first: a close-up only every third re-frame
            sx, sy = info["subject"]; focus = info["red_c"] if info["red"] is not None else (sx, max(info["top"] + 0.15, sy - 0.12))
        asked = str(sc.get("camera") or "").strip().lower()
        if asked:
            for m in PUSH:
                if m in asked: mode = m
            fx, fy = focus
            if "left" in asked: fx = 0.3
            if "right" in asked: fx = 0.7
            if "top" in asked: fy = 0.3
            if "bottom" in asked: fy = 0.7
            if any(w in asked for w in ("red", "part", "muscle", "tendon")) and info["red"] is not None: fx, fy = info["red_c"]
            focus = (fx, fy)
        if mode == "close" and prev_mode == "close": mode = "medium"      # two close shots running read as a picture that is too big for the screen
        prev_mode = mode
        sc["cam"] = {"mode": mode, "focus": [round(focus[0], 3), round(focus[1], 3)], "reveal_at": _reveal_at(sc) if info["red"] is not None and not run else None}
        plan_cues(sc)
    return n

def _window(info: dict, cam: dict, p: float, W: int, H: int) -> tuple:
    """The part of the picture shown in a W x H area at progress p (0..1), framed on the drawn subject: the subject fits inside the area at SUBJECT_H of its height (less when
    it is wide), with black around it (the box may reach past the picture's edge: that is black), pushed gently toward the shot's focus, and never closer than HEAD_ROOM to the top."""
    iw, ih = info["size"]; bx0, by0, bx1, by1 = info.get("bbox", (0.0, 0.0, 1.0, 1.0)); pad = 0.03
    bx0, by0, bx1, by1 = max(0.0, bx0 - pad) * iw, max(0.0, by0 - pad) * ih, min(1.0, bx1 + pad) * iw, min(1.0, by1 + pad) * ih; bw, bh = max(1.0, bx1 - bx0), max(1.0, by1 - by0)
    mode = cam.get("mode", "wide"); z0, z1 = PUSH.get(mode, PUSH["wide"]); e = T.ease_in_out(min(1.0, max(0.0, p))); z = z0 + (z1 - z0) * e
    s = min(W * 0.92 / bw, H * SUBJECT_H / bh) * z
    fx, fy = cam.get("focus") or info["subject"]; k = FOCUS_PULL.get(mode, 0.0) * (0.4 + 0.6 * e)
    cx = (bx0 + bx1) / 2 + (fx * iw - (bx0 + bx1) / 2) * k; cy = (by0 + by1) / 2 + (fy * ih - (by0 + by1) / 2) * k
    cw, ch = W / s, H / s; x0 = cx - cw / 2; y0 = cy - ch / 2 - 0.02 * ch      # the subject sits a touch above the middle
    if mode != "close": y0 = min(y0, by0 - HEAD_ROOM * ch)      # keep the head in, with room above it
    return x0, y0, x0 + cw, y0 + ch


def _revealed(info: dict, t_rel: float) -> Image.Image:
    """The picture with its red paint grown in to t_rel seconds after the reveal starts: grey ink before, a soft front moving along the red region's long side."""
    if info.get("red") is None or t_rel >= REVEAL_S: return info["img"]
    if t_rel <= 0: return info["grey"]
    W, H = info["size"]; x0, y0, x1, y1 = info["red_axis"]; dx, dy = (x1 - x0) * W, (y1 - y0) * H; ln = max(1.0, (dx * dx + dy * dy) ** 0.5)
    if "proj" not in info:
        ys, xs = np.mgrid[0:H, 0:W]; info["proj"] = ((xs - x0 * W) * dx + (ys - y0 * H) * dy) / (ln * ln)
    front = T.ease_out(t_rel / REVEAL_S) * 1.25; m = np.clip((front - info["proj"]) / 0.18, 0, 1) * info["red"]
    return Image.composite(info["img"], info["grey"], Image.fromarray((m * 255).astype("uint8"), "L"))

def render(cv: Image.Image, ctx, sc: dict, t: float) -> Optional[dict]:
    """Draws the full-frame picture for time t (seconds into the scene). Returns {"x", "width"[, "anchor_y"]} for the words (1080p px), or None when this picture keeps the inset look."""
    info = study(_path(sc.get("art")) or "")
    if not info or not info["wide"]: return None
    cam = sc.get("cam") or {"mode": "wide", "focus": info["subject"], "reveal_at": None}
    d = max(2.0, sc["end"] - sc["start"]); src = _revealed(info, t - cam["reveal_at"]) if cam.get("reveal_at") is not None else info["img"]; p = max(0.0, t) / d
    if "_layout" not in sc:      # chosen once per shot: the words go on the side away from where the subject is drawn, so the picture keeps its own composition
        sc["_layout"] = ("right" if info["subject"][0] <= 0.55 else "left", "framed")
    side = sc["_layout"][0]; aw = int(ctx.W * AREA); ax0 = int(ctx.W * 0.02) if side == "right" else ctx.W - aw - int(ctx.W * 0.02); rect = (ax0, 0, ax0 + aw, ctx.H)
    box = _window(info, cam, p, aw, ctx.H)
    cv.paste(src.crop(tuple(int(round(v)) for v in box)).resize((aw, ctx.H), Image.BICUBIC), rect[:2], _feather(aw, ctx.H, side, vertical=True))      # outside the picture is black
    sc["_shown"] = (box, rect)      # where the picture is on screen this frame: overlays() pins labels to its parts
    text_x = (ax0 + aw) / ctx.S + 50 if side == "right" else 110
    return {"x": text_x, "width": 0.0 if side == "right" else ax0 / ctx.S - 170}

def to_screen(sc: dict, fx: float, fy: float, info: dict) -> Optional[tuple]:
    """A point of the picture (fractions of it) on screen this frame, or None when it is out of view."""
    if not sc.get("_shown"): return None
    (x0, y0, x1, y1), (rx0, ry0, rx1, ry1) = sc["_shown"]; iw, ih = info["size"]
    sx = rx0 + (fx * iw - x0) / max(1e-6, x1 - x0) * (rx1 - rx0); sy = ry0 + (fy * ih - y0) / max(1e-6, y1 - y0) * (ry1 - ry0)
    return (sx, sy) if rx0 <= sx <= rx1 and ry0 <= sy <= ry1 else None

# ---------------------------------------------------------------- layered picture shots (docs/rep_theory/AUDIT_2026-11-01_final3.md: a picture with one headline beside it)
# Every mark comes from the sentence's own shape, never from a topic list: a body part named, a direction, an edge or level, an alignment, a number with its unit, an everyday object.
PART_Y = {"brain": 0.05, "neck": 0.14, "shoulders": 0.22, "chest": 0.30, "heart": 0.30, "lungs": 0.30, "arms": 0.36, "back": 0.40, "forearms": 0.46, "core": 0.50, "hands": 0.52,
          "hips": 0.58, "legs": 0.72, "knees": 0.78, "calves": 0.88, "feet": 0.96}      # where a part sits down the drawn subject (fraction of its height) when the picture has no red paint for it
ARROW_RX = (("up", re.compile(r"\b(?:(?:curl|lift|raise|pull|bring|push|hold|stand|get|come)\w*\s+(?:\w+\s+){0,2}up|lift(?:s|ing)?|raise[sd]?|upward)\b", re.I)),
            ("down", re.compile(r"\b(?:drop(?:s|ped|ping)?|lower(?:s|ed|ing)?|downward|(?:put|bring|let|go|come|sit|press)\w*\s+(?:\w+\s+)?down)\b", re.I)),
            ("toward", re.compile(r"\b(?:pull(?:s|ing)?|toward(?:s)? you|in toward|curl\w* (?:it )?in|squeez\w*)\b", re.I)),
            ("away", re.compile(r"\b(?:push(?:es|ing)?|away from you|press(?:es|ing)? away|drive[sn]? away)\b", re.I)),
            ("side", re.compile(r"\b(?:sideways|to the side|out to the side)\b", re.I)))
EDGE_RX = re.compile(r"\b(?:edge|below the \w+|above the \w+|level with|off the \w+|over the \w+)\b", re.I)
ALIGN_RX = re.compile(r"\b(?:stand(?:ing)? tall|straight|one (?:straight )?line|in a (?:straight )?line|in line)\b", re.I)
OBJECT_RX = re.compile(r"\b(backpack|bag|books?|towel|table|chair|bucket|hammer|pan|band|rope|bar|bench|dumbbells?|kettlebells?|plate|bottle|wall|floor|ball)\b", re.I)
HOLD_RX = re.compile(r"\b(?:hold|holding|grab|grip|carry|carrying|squeez\w*|lift)\b", re.I)
CUE_MAX, CUE_GAP_S = 4, 0.6
CARD_KINDS = {"stat", "dial", "study", "bars", "graph", "slots", "race", "formula", "mechanism", "promise", "steps", "checklist", "versus", "mistake", "myth", "timeline", "calendar", "result", "warning", "engage", "question", "takeaway"}

def _word_time(sc: dict, pos: int) -> float:
    ws = sc.get("words") or []; i = len((sc.get("text") or "")[:pos].split())
    return float(ws[min(i, len(ws) - 1)]["t0"]) if ws else float(sc["start"]) + 0.3

def plan_cues(sc: dict) -> List[dict]:
    """The marks this picture shot gets, from its own words: sc["pic_cues"] = [{kind, at (absolute), ...}] in the order said, at most CUE_MAX, CUE_GAP_S apart.
    part = a body part named (ring + line + its word), arrow = a direction, edge = a dashed level line, align = a straight line along the body, badge = a number with its unit,
    inset = a round close-up of an everyday object named. Only for picture scenes; a card already spells its own words out."""
    from . import states as ST, narrative as N
    if sc.get("kind") in CARD_KINDS: sc["pic_cues"] = []; return []
    text = sc.get("text") or ""; words = sc.get("words") or []; cand: List[dict] = []
    tones = {g.get("word") or g.get("label"): g.get("tone") for g in sc.get("glows") or []}
    for part, at, word in ST.parts_named_words(words, text): cand.append({"kind": "part", "part": part, "word": word, "at": at, "tone": tones.get(word)})
    for d, rx in ARROW_RX:
        m = rx.search(text)
        if m: cand.append({"kind": "arrow", "dir": d, "at": _word_time(sc, m.start())})
    m = EDGE_RX.search(text)
    if m: cand.append({"kind": "edge", "at": _word_time(sc, m.start())})
    m = ALIGN_RX.search(text)
    if m: cand.append({"kind": "align", "at": _word_time(sc, m.start())})
    for e in N.entities(text)["numbers"][:1]:
        v = e["value"]; v = float(v) if not isinstance(v, str) else float(re.sub(r"[^\d.]", "", v) or 0)
        if v > 0: cand.append({"kind": "badge", "text": f"{v:g}", "unit": str(e["unit"]).upper(), "at": _word_time(sc, e["pos"])})
    m = OBJECT_RX.search(text)
    if m and HOLD_RX.search(text) and not re.search(r"\b(?:like|as|than)\s+(?:a |an |the )?(?:\w+\s+){0,3}$", text[:m.start()], re.I):      # "slack in a rope" is said "like" a rope: an analogy, not something in the picture
        cand.append({"kind": "inset", "word": m.group(1).upper(), "held": True, "at": max(float(sc["start"]) + 0.4, _word_time(sc, m.start()))})
    out: List[dict] = []
    for c in sorted(cand, key=lambda c: c["at"]):
        if len(out) >= CUE_MAX: break
        if out and c["at"] - out[-1]["at"] < CUE_GAP_S: c = dict(c, at=out[-1]["at"] + CUE_GAP_S)      # never two marks at once: the later one waits its turn
        if c["at"] > float(sc["end"]) - 0.35: continue      # too late to be seen
        if c["kind"] == "inset" and any(x["kind"] == "inset" for x in out): continue
        out.append(c)
    sc["pic_cues"] = out; return out

def cue_count(sc: dict) -> int:
    """What happens on a picture shot besides its headline: marks planned + highlights + a body change (the quality gate wants at least 2 per picture shot)."""
    return len(sc.get("pic_cues") or []) + len(sc.get("glows") or []) + (1 if sc.get("morph") else 0)

EXTREMITY = {"hands", "feet"}      # parts at the end of a limb: the far end of the red region; others its near end

def _red_ends(info: dict) -> tuple:
    """The two ends of the red region along its long side, from its 5th / 95th percentiles (stray red pixels do not count): (end nearer the subject's centre, far end)."""
    if "red_ends" not in info:
        ys, xs = _main_red(info); W, H = info["size"]; v = xs if np.ptp(xs) >= np.ptp(ys) else ys; lo, hi = np.percentile(v, 5), np.percentile(v, 95)
        def end(q):
            sel = np.abs(v - q) <= max(2.0, 0.03 * float(np.ptp(v))); return float(np.median(xs[sel])) / W, float(np.median(ys[sel])) / H
        a, b = end(lo), end(hi); sx, sy = _head(info)      # near / far measured from the head: a hand is the end of the arm farthest from it
        info["red_ends"] = (a, b) if (a[0] - sx) ** 2 + (a[1] - sy) ** 2 <= (b[0] - sx) ** 2 + (b[1] - sy) ** 2 else (b, a)
    return info["red_ends"]

def _main_red(info: dict) -> tuple:
    """(ys, xs) full-size pixel coordinates of the largest connected red region: the painted part, without stray red shading elsewhere (a glow on the back, a pink rim)."""
    if "main_red" not in info:
        k = 8; m = info["red"]; Hs, Ws = m.shape[0] // k, m.shape[1] // k; g = m[:Hs * k, :Ws * k].reshape(Hs, k, Ws, k).mean(axis=(1, 3)) > 0.15
        lab = np.zeros(g.shape, dtype=np.int32); best, best_n, cur = 0, 0, 0
        for y0, x0 in zip(*np.nonzero(g)):
            if lab[y0, x0]: continue
            cur += 1; stack = [(y0, x0)]; lab[y0, x0] = cur; n = 0
            while stack:
                y, x = stack.pop(); n += 1
                for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= yy < Hs and 0 <= xx < Ws and g[yy, xx] and not lab[yy, xx]: lab[yy, xx] = cur; stack.append((yy, xx))
            if n > best_n: best, best_n = cur, n
        keep = np.kron(lab == best, np.ones((k, k), dtype=bool)) if best else np.zeros((Hs * k, Ws * k), dtype=bool)
        ys, xs = np.nonzero(m[:Hs * k, :Ws * k] * keep)
        info["main_red"] = (ys, xs) if len(xs) else np.nonzero(m)
    return info["main_red"]

def _head(info: dict) -> tuple:
    """Where the head of the drawn subject is (fractions): the middle of the ink in the top 15% of its box."""
    if "head" not in info:
        bx0, by0, bx1, by1 = info.get("bbox", (0.0, 0.0, 1.0, 1.0)); W, H = info["size"]; a = np.asarray(info["img"].convert("L"), dtype=np.float32)
        y0, y1, x0, x1 = int(by0 * H), int((by0 + 0.15 * (by1 - by0)) * H) + 1, int(bx0 * W), int(bx1 * W) + 1; band = a[y0:y1, x0:x1] > 60
        info["head"] = ((x0 + float(np.nonzero(band)[1].mean())) / W if band.any() else (bx0 + bx1) / 2, (y0 + y1) / 2 / H)
    return info["head"]

def _part_point(info: dict, cue: dict, k: int) -> tuple:
    """Where a named part is in the picture (fractions): the red paint for the first part; for the next ones the red region's far end (a hand, a foot) or near end; without red,
    down the drawn subject by the part."""
    bx0, by0, bx1, by1 = info.get("bbox", (0.0, 0.0, 1.0, 1.0))
    if info["red"] is not None:
        if k == 0 and cue.get("part") not in EXTREMITY: ys, xs = _main_red(info); return float(xs.mean()) / info["size"][0], float(ys.mean()) / info["size"][1]
        near, far = _red_ends(info); return far if cue.get("part") in EXTREMITY else near
    if info.get("red_pt"): return info["red_pt"]      # a small red patch still marks the part
    if cue.get("part") in MOVING_PARTS: return None      # no red to go by and the part moves with the pose: no ring rather than a ring in the wrong place
    return ((bx0 + bx1) / 2, by0 + PART_Y.get(cue.get("part"), 0.4) * (by1 - by0))

def _arrow(d, a, b, col, w, head):
    d.line((a, b), fill=col, width=w); ang = np.arctan2(b[1] - a[1], b[0] - a[0])
    d.polygon([b, (b[0] - head * np.cos(ang - 0.45), b[1] - head * np.sin(ang - 0.45)), (b[0] - head * np.cos(ang + 0.45), b[1] - head * np.sin(ang + 0.45))], fill=col)

def _draw_cues(cv: Image.Image, ctx, sc: dict, t: float, info: dict) -> int:
    """Draws the planned marks on the picture, each arriving on its word and staying to the end of the shot, following the camera push (to_screen)."""
    from PIL import ImageDraw
    from . import draw as D, states as ST
    cues = sc.get("pic_cues") or []
    if not cues: return 0
    rect = sc["_shown"][1]; rx0, ry0, rx1, ry1 = rect; side = (sc.get("_layout") or ("right", ""))[0]; away = -1 if side == "right" else 1      # labels go away from the words' column
    bx0, by0, bx1, by1 = info.get("bbox", (0.0, 0.0, 1.0, 1.0)); n = 0; parts = [c for c in cues if c["kind"] == "part"]; last_pt = None
    clamp = lambda p: (min(max(p[0], rx0 + ctx.px(24)), rx1 - ctx.px(24)), min(max(p[1], ry0 + ctx.px(60)), ry1 - ctx.px(40)))
    for c in cues:
        tr = t - (c["at"] - sc["start"])
        if tr < 0: continue
        q = T.ease_out(min(1.0, tr / 0.45)); d = ImageDraw.Draw(cv, "RGBA")
        if c["kind"] == "part":
            k = parts.index(c); fp = _part_point(info, c, k)
            if fp is None: continue
            fx, fy = fp; pt = to_screen(sc, fx, fy, info)
            if not pt: continue
            last_pt = pt; col = ST.TONES.get(c.get("tone"), T.ORANGE)
            r = ctx.px(46) * (0.6 + 0.4 * q); d.ellipse((pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r), outline=col + (int(235 * q),), width=ctx.px(5))
            rr = ctx.px(46) * (1.0 + 0.7 * min(1.0, tr / 0.7)); d.ellipse((pt[0] - rr, pt[1] - rr, pt[0] + rr, pt[1] + rr), outline=col + (int(150 * max(0.0, 1 - tr / 0.7)),), width=ctx.px(3))      # the ring pops once on the word
            if k == 0 and sc.get("_label_off"): n += 1; continue      # the picture before showed this label: ring only
            label = c["word"]; lw = D._text_w(d, label, ctx.font(T.BODY_FONT, 36), ctx.px(1.5)) + ctx.px(60); dx = away
            if dx > 0 and pt[0] + ctx.px(130) + lw > rx1 - ctx.px(16): dx = -1
            elif dx < 0 and pt[0] - ctx.px(130) - lw < rx0 + ctx.px(16): dx = 1
            ly = min(max(ry0 + ctx.px(70), pt[1] - ctx.px(120) + k * ctx.px(96)), ry1 - ctx.px(90)); lx = pt[0] + dx * ctx.px(130); lx = min(max(lx, rx0 + ctx.px(16) + (lw if dx < 0 else 0)), rx1 - ctx.px(16) - (lw if dx > 0 else 0))
            D.leader(cv, ctx, (pt[0] + dx * r * 0.75, pt[1] - r * 0.4), (lx, ly + ctx.px(6)), min(1.0, max(0.0, (tr - 0.1) / 0.35)), "", 0.0)      # the line draws from the part to its label
            pa = min(1.0, max(0.0, (tr - 0.35) / 0.35))
            if pa > 0:
                bx = lx - (0 if dx > 0 else lw); ImageDraw.Draw(cv, "RGBA").rounded_rectangle((bx, ly - ctx.px(30), bx + lw, ly + ctx.px(42)), radius=ctx.px(36), fill=(10, 10, 12, int(215 * pa)))
                D.pill(cv, ctx, bx, ly - ctx.px(30), label, (tr - 0.35) / 0.4)
        elif c["kind"] == "arrow":
            o = last_pt or to_screen(sc, *(info["red_c"] if info["red"] is not None else info["subject"]), info) or ((rx0 + rx1) / 2, (ry0 + ry1) / 2); L_ = ctx.px(150) * q
            sc_c = to_screen(sc, (bx0 + bx1) / 2, (by0 + by1) / 2, info) or o; v = {"up": (0, -1), "down": (0, 1), "side": (away, 0)}.get(c["dir"])
            if v is None:      # toward / away from the body: horizontal, toward the head's side (the torso), not down to the picture's centre
                hx = (to_screen(sc, *_head(info), info) or sc_c)[0]; sx = 1 if hx > o[0] + ctx.px(10) else -1 if hx < o[0] - ctx.px(10) else -away; v = (sx, 0)
                if c["dir"] == "away": v = (-v[0], -v[1])
            a = (o[0] + v[0] * ctx.px(60), o[1] + v[1] * ctx.px(60)); b = clamp((a[0] + v[0] * L_, a[1] + v[1] * L_))
            if L_ > ctx.px(10): _arrow(d, a, b, T.ORANGE + (255,), ctx.px(9), ctx.px(34) * min(1.0, q * 1.5))
        elif c["kind"] == "edge":
            fy = info["red_c"][1] if info["red"] is not None else (by0 + by1) / 2; p0 = to_screen(sc, bx0, fy, info) or (rx0, (ry0 + ry1) / 2); p1 = to_screen(sc, bx1, fy, info) or (rx1, p0[1])
            x0, x1 = max(rx0 + ctx.px(20), p0[0] - ctx.px(40)), min(rx1 - ctx.px(20), p1[0] + ctx.px(40)); xe = x0 + (x1 - x0) * q; x = x0
            while x < xe: d.line((x, p0[1], min(xe, x + ctx.px(22)), p0[1]), fill=(255, 200, 60, 235), width=ctx.px(5)); x += ctx.px(40)      # a dashed level line drawn on, left to right
        elif c["kind"] == "align":
            p0 = to_screen(sc, (bx0 + bx1) / 2, by0 + 0.02, info) or ((rx0 + rx1) / 2, ry0 + ctx.px(60)); p1 = to_screen(sc, (bx0 + bx1) / 2, by1 - 0.02, info) or (p0[0], ry1 - ctx.px(40))
            if info["red"] is not None and abs(info["red_axis"][3] - info["red_axis"][1]) > abs(info["red_axis"][2] - info["red_axis"][0]):      # a long upright red region: the line runs along it
                p0 = to_screen(sc, info["red_axis"][0], info["red_axis"][1], info) or p0; p1 = to_screen(sc, info["red_axis"][2], info["red_axis"][3], info) or p1
            p0, p1 = clamp(p0), clamp(p1); d.line((p0, (p0[0] + (p1[0] - p0[0]) * q, p0[1] + (p1[1] - p0[1]) * q)), fill=(74, 222, 128, 235), width=ctx.px(6))
        elif c["kind"] == "badge":
            e = T.ease_back(min(1.0, tr / 0.4)); R = ctx.px(78) * e; top = to_screen(sc, bx1 if away < 0 else bx0, by0 + 0.1 * (by1 - by0), info) or (rx1 - ctx.px(120), ry0 + ctx.px(140))
            cxb, cyb = clamp((top[0] - away * ctx.px(40), top[1])); cxb = min(max(cxb, rx0 + R + ctx.px(10)), rx1 - R - ctx.px(10)); cyb = max(cyb, ry0 + R + ctx.px(50))
            if R > 2:
                d.ellipse((cxb - R, cyb - R, cxb + R, cyb + R), fill=(14, 14, 16, 235), outline=T.ORANGE + (255,), width=ctx.px(5))
                f = ctx.font(T.HEAD_FONT, int(64 * e) + 1); tw = D._text_w(d, c["text"], f, 0); D.text_spaced(d, (cxb - tw / 2, cyb - ctx.px(52) * e), c["text"], f, T.WHITE + (255,), 0)
                fu = ctx.font(T.BODY_FONT, int(26 * e) + 1); uw = D._text_w(d, c["unit"], fu, ctx.px(2)); D.text_spaced(d, (cxb - uw / 2, cyb + ctx.px(18) * e), c["unit"], fu, T.ORANGE + (255,), ctx.px(2))
        elif c["kind"] == "inset":
            e = T.ease_back(min(1.0, tr / 0.45)); R = int(ctx.H * 0.12 * e)
            if R < 4: continue
            if not (c.get("held") and info["red"] is not None): continue      # only an object held in the red-painted hand can be found in the picture; a guessed spot showed a thigh as "TABLE"
            loc = c.get("_pt") or _red_ends(info)[1]      # the far end of the painted arm: the hand holding it
            c["_pt"] = loc; fx, fy = loc; (sx0, sy0, sx1, sy1) = sc["_shown"][0]
            scale = (rx1 - rx0) / max(1.0, sx1 - sx0) * 2.2; half = R / scale; iw, ih = info["size"]; ox, oy = fx * iw, fy * ih
            crop = info["img"].crop((int(ox - half), int(oy - half), int(ox + half), int(oy + half))).resize((2 * R, 2 * R), Image.BICUBIC)
            if float((np.asarray(crop.convert("L")) > 60).mean()) < 0.12: continue      # an inset of black is no close-up: skip it
            m = Image.new("L", (2 * R, 2 * R), 0); ImageDraw.Draw(m).ellipse((0, 0, 2 * R - 1, 2 * R - 1), fill=255)
            icx = rx0 + ctx.px(40) + R if away > 0 else rx1 - ctx.px(40) - R; icy = ry1 - ctx.px(120) - R      # bottom corner of the picture area, away from the words
            cv.paste(crop, (int(icx - R), int(icy - R)), m); d = ImageDraw.Draw(cv, "RGBA"); d.ellipse((icx - R, icy - R, icx + R, icy + R), outline=T.ORANGE + (255,), width=ctx.px(4))
            lw = D._text_w(d, c["word"], ctx.font(T.BODY_FONT, 30), ctx.px(1.5)) + ctx.px(50); D.pill(cv, ctx, icx - lw / 2, icy + R + ctx.px(10), c["word"], (tr - 0.2) / 0.4, size=30)
        n += 1
    return n

def overlays(cv: Image.Image, ctx, sc: dict, t: float) -> int:
    """What the older looks drew on the figure, drawn on the picture (render final 2 dropped them on every picture scene): the part the narration names lights up on its word
    (a soft glow + a ring that pops + a leader label with the word as said: FOREARM, BICEP; no label when the picture before showed the same one; in the part's state colour: orange, red when it works hard, icy blue when it rests), and a body change on "bulk" /
    "lose fat" as a labelled arrow. The part's place in the picture is its red paint (beat_art asks Flow to paint the named part red), else the upper part of the subject.
    Returns how many things were drawn."""
    from . import draw as D, states as ST
    info = study(_path(sc.get("art")) or "")
    if not info or not sc.get("_shown"): return 0
    n = 0; live = [g for g in sc.get("glows") or [] if g["at"] - sc["start"] <= t + 1e-6]
    if any(c["kind"] == "part" for c in sc.get("pic_cues") or []): live = []      # every part said gets its own ring and label below (_draw_cues), not only the latest
    if live:
        g = live[-1]; at = g["at"] - sc["start"]; col = ST.TONES.get(g.get("tone"), T.ORANGE); label = "" if sc.get("_label_off") else (g.get("word") or g.get("label") or ""); fx, fy = info["red_c"] if info["red"] is not None else info.get("red_pt") or (info["subject"][0], max(info["top"] + 0.12, info["subject"][1] - 0.1))
        pt = to_screen(sc, fx, fy, info)
        if pt:
            lay = Image.new("RGBA", cv.size, (0, 0, 0, 0)); d = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(lay); q = T.ease_out((t - at) / 0.5); pulse = 0.85 + 0.15 * np.sin((t - at) * 4.0)
            r = ctx.px(70) * (0.6 + 0.4 * q); d.ellipse((pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r), outline=col + (int(230 * q * pulse),), width=ctx.px(5))
            rr = ctx.px(70) * (1.0 + 0.6 * min(1.0, (t - at) / 0.7)); d.ellipse((pt[0] - rr, pt[1] - rr, pt[0] + rr, pt[1] + rr), outline=col + (int(160 * max(0.0, 1 - (t - at) / 0.7)),), width=ctx.px(3))      # the ring pops once on the word
            side = (sc.get("_layout") or ("right", ""))[0]; (rx0, _ry0, rx1, _ry1) = sc["_shown"][1]      # the label goes away from the words' column and stays on the picture
            dx = -1 if side == "right" else 1 if side == "left" else (-1 if pt[0] > ctx.W / 2 else 1)
            lw = D._text_w(d, label, ctx.font(T.BODY_FONT, 36), ctx.px(1.5)) + ctx.px(60)      # the pill's real width (draw.pill)
            if dx > 0 and pt[0] + ctx.px(150) + lw > min(rx1, ctx.W) - ctx.px(20): dx = -1      # no room on that side: the other one
            elif dx < 0 and pt[0] - ctx.px(150) - lw < max(rx0, 0) + ctx.px(20): dx = 1
            lx = pt[0] + dx * ctx.px(150); lx = min(max(lx, ctx.px(20) + (lw if dx < 0 else 0)), ctx.W - ctx.px(20) - (lw if dx > 0 else 0)); ly = max(ctx.px(110), pt[1] - ctx.px(130)); k = min(1.0, max(0.0, (t - at - 0.15) / 0.35))
            if label: d.line((pt[0] + dx * r * 0.7, pt[1] - r * 0.7, pt[0] + dx * r * 0.7 + (lx - pt[0] - dx * r * 0.7) * k, pt[1] - r * 0.7 + (ly - pt[1] + r * 0.7) * k), fill=col + (230,), width=ctx.px(3))
            cv.paste(lay, (0, 0), lay)
            if k > 0.6 and label:
                bx = lx - (0 if dx > 0 else lw); pa = min(1.0, max(0.0, (t - at - 0.35) / 0.4))
                if pa > 0: __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(cv, "RGBA").rounded_rectangle((bx, ly - ctx.px(30), bx + lw, ly + ctx.px(42)), radius=ctx.px(36), fill=(10, 10, 12, int(215 * pa)))      # a dark plate: the label reads over any ink
                D.pill(cv, ctx, bx, ly - ctx.px(30), label, (t - at - 0.35) / 0.4)
            n += 1
    n += _draw_cues(cv, ctx, sc, t, info)
    bm = sc.get("beam")
    if bm and bm.get("at") is not None:      # a signal from the brain to the part it drives: from the top of the drawn subject to its red part
        bx0, by0, bx1, by1 = info.get("bbox", (0.0, 0.0, 1.0, 1.0)); p0 = to_screen(sc, (bx0 + bx1) / 2, by0 + 0.04, info); p1 = to_screen(sc, *(info["red_c"] if info["red"] is not None else ((bx0 + bx1) / 2, (by0 + by1) / 2)), info)
        if p0 and p1: D.beam(cv, ctx, p0, p1, t - (bm["at"] - sc["start"])); n += 1
    mo = sc.get("morph")
    if mo and t >= mo["at"] - sc["start"]:      # the figure used to widen / slim on the word: here an arrow and its word beside the subject
        pt = to_screen(sc, info["subject"][0], info["subject"][1], info) or (ctx.W * 0.4, ctx.H * 0.5); q = T.ease_back(min(1.0, (t - mo["at"] + sc["start"]) / 0.5)); up = mo["to"] > 0
        d = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(cv, "RGBA"); x, y = pt[0] + ctx.px(170), pt[1]; s = ctx.px(34) * q; col = (74, 222, 128) if up else (90, 190, 255)
        d.polygon([(x, y - s * (1 if up else -1)), (x - s * 0.8, y + s * 0.4 * (1 if up else -1)), (x + s * 0.8, y + s * 0.4 * (1 if up else -1))], fill=col + (255,))
        D.pill(cv, ctx, x + ctx.px(30), y - ctx.px(30), "BIGGER" if up else "LEANER", (t - mo["at"] + sc["start"]) / 0.4); n += 1
    return n

_feathers: Dict[tuple, Image.Image] = {}

def _feather(w: int, h: int, side: str, vertical: bool = True) -> Image.Image:
    """The picture area's mask: opaque in the middle, soft on every edge (wider on the words' side), so the picture melts into the black canvas without a box."""
    k = (w, h, side, vertical)
    if k not in _feathers:
        x = np.linspace(0, 1, w); y = np.linspace(0, 1, h)
        mx = np.clip((1 - x) / 0.14, 0, 1) * np.clip(x / 0.05, 0, 1) if side == "right" else np.clip(x / 0.14, 0, 1) * np.clip((1 - x) / 0.05, 0, 1)
        my = np.clip(np.minimum(y, 1 - y) / 0.06, 0, 1) if vertical else np.ones(h)
        _feathers[k] = Image.fromarray((np.outer(my, mx) * 255).astype("uint8"), "L")
    return _feathers[k]
