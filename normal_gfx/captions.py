"""Where the captions really are, and whether a rendered graphic can sit with them.

video_generator draws each scene's caption (its script segment) for the whole scene, at the bottom (classic: centred lines above an 8 % margin; pakmap: a
chip). The captions are drawn BEFORE graphics, so a graphic would cover them. Instead of a blanket rule about the bottom of the frame, this module
  1. draws each scene's caption the way the renderer does (video_generator.render_caption_overlay) and keeps its pixels, a little dilated;
  2. tests a graphic's alpha envelope (gfx-overlay-engine writes the strongest alpha every pixel ever gets) against those pixels, for the scenes the graphic
     overlaps: its opaque parts must not touch a caption, and nothing denser than a faint fringe (alpha <= FRINGE) may lie over one;
  3. if it collides, looks for the smallest upward shift (the engine moves the whole graphic, animation and proportions unchanged) that clears every caption
     and keeps its opaque parts inside the frame; then for a uniform scale-down (0.9 .. 0.7, about the top corner nearest the graphic) that does; only when
     there is none is the graphic skipped, with the reason. A sub-second transition (a glitch cut) is not moved: it is over before a caption can be read.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageFilter

FRINGE = 96          # a backing or dim at most 38 % dark may lie over a caption: white type stays at least 62 % bright (>= 158/255) with its black outline; denser may not
INK = 200            # opaque parts: type, bars, rings
MAX_SHIFT = 0.12     # at most this share of the frame height upward
SCALES = (0.9, 0.8, 0.7)   # never smaller: type must stay legible
TRANSIENT_S = 1.0
STEP = 0.01
MARGIN_PX = 6        # clear space around the caption's own pixels (at 1080p; scaled)


@dataclass
class SceneCaption:
    start: float
    end: float
    mask: np.ndarray          # bool (H, W): where the caption (plus margin) is


def scene_masks(rows: Sequence[dict], display_timeline: Sequence[Tuple[float, float]], width: int, height: int, style: str = "classic") -> List[SceneCaption]:
    """One mask per scene that has a caption, drawn by the render's own caption function."""
    import video_generator as vg

    out: List[SceneCaption] = []
    k = max(1, round(MARGIN_PX * min(width, height) / 1080)) * 2 + 1
    with tempfile.TemporaryDirectory(prefix="gfxcap_") as tmp:
        for i, row in enumerate(rows):
            if i >= len(display_timeline):
                break
            png = vg.render_caption_overlay(str(row.get("script_segment", "") or ""), Path(tmp) / f"c{i}.png", width, height, style=style)
            if png is None:
                continue
            a = Image.open(png).convert("RGBA").getchannel("A").point(lambda v: 255 if v > 12 else 0).filter(ImageFilter.MaxFilter(k if k % 2 else k + 1))
            out.append(SceneCaption(float(display_timeline[i][0]), float(display_timeline[i][1]), np.asarray(a) > 0))
    return out


@dataclass
class Fit:
    ok: bool
    dy: float = 0.0           # share of the frame height to move the graphic (negative = up); 0 = as drawn
    scale: float = 1.0        # uniform scale about `anchor` (1 = as drawn)
    anchor: Tuple[float, float] = (0.0, 0.0)
    reason: str = ""
    kind: str = ""            # why it failed: "ink" (type/bars touch a caption), "backing" (only its soft backing is over a caption), "offscreen", "envelope"

    @property
    def changed(self) -> bool:
        return bool(self.dy) or self.scale != 1.0


def _load_env(result: Any) -> Optional[np.ndarray]:
    try:
        return np.asarray(Image.open(result.envelope).convert("L"))
    except (OSError, AttributeError, ValueError):
        return None


def _collides(env: np.ndarray, masks: Sequence[np.ndarray]) -> Optional[Tuple[str, str]]:
    for m in masks:
        if m.shape != env.shape:
            continue
        if np.any((env >= INK) & m):
            return "ink", "its opaque parts touch a caption"
    for m in masks:
        if m.shape == env.shape and np.any((env > FRINGE) & m):
            return "backing", "its backing is denser than a faint fringe over a caption"
    return None


def _scaled(env: np.ndarray, s: float, ax: float, ay: float) -> np.ndarray:
    h, w = env.shape
    small = np.asarray(Image.fromarray(env).resize((max(1, int(round(w * s))), max(1, int(round(h * s)))), Image.BILINEAR))
    out = np.zeros_like(env)
    x0, y0 = int(round(ax * w * (1 - s))), int(round(ay * h * (1 - s)))
    out[y0:y0 + small.shape[0], x0:x0 + small.shape[1]] = small[: h - y0, : w - x0]
    return out


def fit(result: Any, t0: float, t1: float, captions: Sequence[SceneCaption], width: int, height: int) -> Fit:
    """Can this rendered graphic (on screen t0..t1) be shown with the captions of the scenes it overlaps, as drawn, moved up, or scaled down?"""
    env = _load_env(result)
    if env is None:
        return Fit(False, reason="its drawing envelope is missing, so caption overlap cannot be checked", kind="envelope")
    masks = [c.mask for c in captions if c.start < t1 and t0 < c.end]
    if not masks:
        return Fit(True)
    hit = _collides(env, masks)
    if hit is None:
        return Fit(True)
    kind, why = hit
    if t1 - t0 <= TRANSIENT_S:
        return Fit(True, reason=f"a {t1 - t0:.1f}s transition: shown over the caption as designed")
    ink_rows = np.where((env >= INK).any(axis=1))[0]
    ink_cols = np.where((env >= INK).any(axis=0))[0]
    top = int(ink_rows.min()) if len(ink_rows) else 0          # a soft backing running off the top edge is invisible; the opaque parts must stay in
    tried = ""
    n = 1
    while n * STEP <= MAX_SHIFT + 1e-9:
        px = int(round(n * STEP * height))
        if top - px < int(0.01 * height):
            tried = f"moving it up would push it off the top of the frame (its opaque parts already start at {top / height:.0%})"
            break
        shifted = np.zeros_like(env)
        shifted[: height - px] = env[px:]
        if _collides(shifted, masks) is None:
            return Fit(True, dy=-n * STEP, reason=f"moved up {n * STEP:.0%} to clear the caption")
        n += 1
    else:
        tried = f"no upward move of up to {MAX_SHIFT:.0%} of the frame clears it"
    if float((env >= INK).mean()) > 0.6:       # a card that fills the frame would only become a smaller card floating on the picture: not scaled
        return Fit(False, reason=f"{why}; {tried}; it fills the frame, so scaling it down would not give a sensible graphic (scaling not applied)", kind="fullframe")
    ax = 1.0 if (len(ink_cols) and (ink_cols.min() + ink_cols.max()) / 2 > width / 2) else 0.0
    for sc in SCALES:
        if _collides(_scaled(env, sc, ax, 0.0), masks) is None:
            return Fit(True, scale=sc, anchor=(ax, 0.0), reason=f"scaled to {sc:.0%} (proportions kept) to clear the caption")
    return Fit(False, reason=f"{why}; {tried}; scaling it down to {SCALES[-1]:.0%} does not clear it either",
               kind=kind if kind == "backing" else ("offscreen" if "off the top" in tried else kind))
