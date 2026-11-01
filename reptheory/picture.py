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
PUSH = {"wide": (1.0, 1.22), "medium": (1.28, 1.48), "close": (1.75, 1.95)}      # zoom at the shot's start and end: the reference pushes 20-35% on every picture
RED_MIN = 0.002      # share of the picture painted red before a reveal is drawn
REVEAL_S = 0.9
_cache: Dict[str, dict] = {}

def _red(a: np.ndarray) -> np.ndarray:
    """Pixels painted red (not the character's orange): strong red over green and blue."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return ((r > 120) & (r - g > 70) & (r - b > 60) & (g < 0.55 * r)).astype(np.float32)

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
    info = {"img": im, "size": (W, H), "wide": W / H >= WIDE_ASPECT, "subject": subj, "free": "right" if halves[0] >= halves[1] else "left", "red": None, "red_c": subj, "red_axis": None}
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
    """Framing for every full-frame picture scene. A picture shown again in the next scene is re-framed: wide, then close on its red part (or the other side of its subject),
    then medium; the CSV's `camera` column, when filled, wins. Returns how many scenes were re-framed."""
    n = 0; prev_art = None; run = 0
    for sc in scenes:
        if sc.get("kind") != "illus": prev_art = None; continue
        info = study(_path(sc.get("art")) or "")
        if not info or not info["wide"]: prev_art = None; continue
        run = run + 1 if sc.get("art") == prev_art else 0; prev_art = sc.get("art")
        mode, focus = "wide", info["subject"]
        if run:
            n += 1; mode = ("close", "medium", "close")[(run - 1) % 3]
            sx, sy = info["subject"]; focus = info["red_c"] if (run % 2 and info["red"] is not None) else (min(0.85, max(0.15, sx + (0.18 if run % 2 else -0.18))), sy - 0.08)
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
        sc["cam"] = {"mode": mode, "focus": [round(focus[0], 3), round(focus[1], 3)], "reveal_at": _reveal_at(sc) if info["red"] is not None and not run else None}
    return n

def _window(info: dict, cam: dict, p: float, W: int, H: int) -> tuple:
    """The crop of the picture shown in a W x H area at progress p (0..1): cover-fit, zoomed toward the focus point, never past the picture's edge."""
    iw, ih = info["size"]; base = max(W / iw, H / ih); z0, z1 = PUSH.get(cam.get("mode"), PUSH["wide"]); e = T.ease_in_out(min(1.0, p))
    z = z0 + (z1 - z0) * e; cw, ch = W / (base * z), H / (base * z); fx, fy = cam.get("focus") or info["subject"]
    pull = 0.35 + 0.65 * e if cam.get("mode") == "wide" else 1.0      # a wide shot starts centred and drifts to its subject as it pushes in
    cx = iw / 2 + (fx * iw - iw / 2) * pull; cy = ih / 2 + (fy * ih - ih / 2) * pull
    x0 = min(max(0.0, cx - cw / 2), iw - cw); y0 = min(max(0.0, cy - ch / 2), ih - ch)
    return x0, y0, x0 + cw, y0 + ch

PANEL = 0.64      # a picture with no empty side is set in this share of the frame, feathered into the black, the words beside it
BUSY = 0.10      # ink share of the words' side above which the picture is set as a panel

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
    if "_layout" not in sc:      # chosen once per shot, on the framing it holds longest, so the words never jump as the camera moves
        side, ink = _free_side(info["img"].resize((192, 108), Image.BILINEAR, box=_window(info, cam, 0.7, ctx.W, ctx.H)))
        sc["_layout"] = (side, "full") if ink <= BUSY or side == "top" else ("right" if info["subject"][0] <= 0.5 else "left", "panel")
    side, how = sc["_layout"]
    if how == "full":
        cv.paste(src.resize((ctx.W, ctx.H), Image.BICUBIC, box=_window(info, cam, p, ctx.W, ctx.H)), (0, 0)); _scrim(cv, side)
    else:
        pw = int(ctx.W * PANEL); x0 = 0 if side == "right" else ctx.W - pw
        cv.paste(src.resize((pw, ctx.H), Image.BICUBIC, box=_window(info, cam, p, pw, ctx.H)), (x0, 0), _feather(pw, ctx.H, side))
    return {"right": {"x": 1180 if how == "full" else int(1920 * PANEL) + 40, "width": 0.0}, "left": {"x": 110, "width": 640.0 if how == "full" else int(1920 * (1 - PANEL)) - 150},
            "top": {"x": 110, "width": 1100.0, "anchor_y": 0.2}}[side]

_feathers: Dict[tuple, Image.Image] = {}

def _feather(w: int, h: int, side: str) -> Image.Image:
    """The panel's mask: opaque, fading to nothing over its last fifth on the words' side."""
    k = (w, h, side)
    if k not in _feathers:
        x = np.linspace(0, 1, w); a = np.clip((1 - x) / 0.2, 0, 1) if side == "right" else np.clip(x / 0.2, 0, 1)
        _feathers[k] = Image.fromarray(np.tile((a * 255).astype("uint8"), (h, 1)), "L")
    return _feathers[k]

def _free_side(cv: Image.Image) -> tuple:
    """(side, ink share there) for the words on this framing: the emptier of the left and right 40%; when both are busy, the top band if it is clearly emptier."""
    a = np.asarray(cv.convert("L").resize((96, 54)), dtype=np.float32); ink = (a > 40).astype(np.float32)
    left, right, top = float(ink[13:41, 4:38].mean()), float(ink[13:41, 58:92].mean()), float(ink[:12, 4:80].mean())      # where the word block actually sits on each side
    if min(left, right) > BUSY and top < BUSY * 0.6: return "top", top
    return ("right", right) if right <= left else ("left", left)

_scrims: Dict[tuple, Image.Image] = {}

def _scrim(cv: Image.Image, side: str) -> None:
    """A soft dark gradient on the words' side, so they read over any picture."""
    k = (cv.size, side)
    if k not in _scrims:
        W, H = cv.size
        if side == "top": y = np.linspace(0, 1, H); al = np.tile((np.clip((0.42 - y) / 0.3, 0, 1) * 185).astype("uint8")[:, None], (1, W))
        else: x = np.linspace(0, 1, W); a = np.clip((x - 0.45) / 0.35, 0, 1) if side == "right" else np.clip((0.55 - x) / 0.35, 0, 1); al = np.tile((a * 175).astype("uint8"), (H, 1)); _scrims[k] = Image.merge("RGBA", (*[Image.new("L", (W, H), 0)] * 3, Image.fromarray(al, "L")))
    cv.paste(_scrims[k], (0, 0), _scrims[k])
