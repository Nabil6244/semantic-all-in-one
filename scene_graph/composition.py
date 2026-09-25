"""SceneGraph + Layout + StylePreset + resolved media -> rendered Pillow assets.

Produces:
  - one full canvas PNG with every node/caption/arrow/anchor at its FINAL
    (fully revealed) appearance — used as the camera's background plate.
  - one canvas-sized transparent overlay PNG per node (that node + its
    caption only) and per edge (that arrow only) — used by scene_graph.render
    to fade each element in at its own appear_at/draw_at time while the
    camera pans underneath.

Pure Pillow (the same library graphics/render.py already depends on). This
is a NEW renderer for a NEW representation (a multi-node canvas), not a
competing renderer for anything graphics/ already handles — it never
touches graphics/, video_generator.py, or preview_engine.py.

Reuses the project's own bundled fonts (assets/fonts/) — including a real
hand-lettered marker face (ChalkboardSE.ttc, bundled from macOS's own
Supplemental fonts) used for titles/labels/captions, matching the reference
"Overscaled" style's whiteboard-marker lettering. The earlier geometric sans
faces (SpaceGrotesk/Outfit/Inter) stay only as a fallback chain in case that
asset is ever missing.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .layout import NodeRect, SceneGraphLayout
from .routing import ObstacleRect, keep_out_exit_point
from .schema import CaptionSpec, SceneEdge, SceneGraph, SceneNode
from .style_presets import StylePreset

_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# Chalkboard SE (bundled, see assets/fonts/ChalkboardSE.ttc) is a real
# rounded, hand-lettered marker face — matches the reference "Overscaled"
# style's whiteboard-marker lettering far closer than any of the geometric
# sans faces below, which are kept only as a fallback chain in case the
# bundle is ever missing the .ttc (e.g. a corrupted asset copy). Face index
# 2 in this collection is Bold, used everywhere for legibility at small
# caption sizes (the Light face read as too wispy once shrunk).
_HAND_FONT_FILE = "ChalkboardSE.ttc"
_HAND_FONT_BOLD_INDEX = 2
_TITLE_FONT_CANDIDATES = (
    (_HAND_FONT_FILE, _HAND_FONT_BOLD_INDEX),
    ("SpaceGrotesk-Bold.ttf", 0),
    ("Outfit-ExtraBold.ttf", 0),
)
_CAPTION_FONT_CANDIDATES = (
    (_HAND_FONT_FILE, _HAND_FONT_BOLD_INDEX),
    ("Inter-SemiBold.ttf", 0),
    ("Inter-Bold.ttf", 0),
)
_LABEL_FONT_CANDIDATES = _TITLE_FONT_CANDIDATES

_PLACEHOLDER_FILL = (222, 222, 222, 255)
_CAPTION_COLOR = (26, 26, 26, 255)
_LABEL_COLOR = (192, 57, 43, 255)  # matches style_presets arrows.default_color (#c0392b)


@dataclasses.dataclass
class CompositionAssets:
    canvas_path: Path
    node_overlay_paths: Dict[str, Path]
    edge_overlay_paths: Dict[str, Path]

    def to_dict(self) -> dict:
        return {
            "canvas_path": str(self.canvas_path),
            "node_overlay_paths": {k: str(v) for k, v in self.node_overlay_paths.items()},
            "edge_overlay_paths": {k: str(v) for k, v in self.edge_overlay_paths.items()},
        }


def _load_font(candidates, size: int) -> ImageFont.FreeTypeFont:
    for name, index in candidates:
        path = _FONTS_DIR / name
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size, index=index)
            except Exception:
                continue
    return ImageFont.load_default()


def _extract_video_thumbnail(video_path: Path, tmp_dir: Path) -> Optional[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        root = Path(__file__).resolve().parent.parent
        candidate = root / "bin" / "ffmpeg"
        ffmpeg = str(candidate) if candidate.is_file() else None
    if not ffmpeg:
        return None
    out_png = tmp_dir / f"{video_path.stem}_thumb.png"
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(video_path), "-frames:v", "1", str(out_png)],
            capture_output=True, timeout=20,
        )
        if proc.returncode == 0 and out_png.is_file():
            return out_png
    except Exception:
        return None
    return None


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def load_media_image(path: Optional[str], tmp_dir: Path) -> Optional[Image.Image]:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        if p.suffix.lower() in VIDEO_SUFFIXES:
            thumb = _extract_video_thumbnail(p, tmp_dir)
            return Image.open(thumb).convert("RGBA") if thumb else None
        return Image.open(p).convert("RGBA")
    except Exception:
        return None


def _blank_canvas(width: int, height: int, background: str, *, transparent: bool) -> Image.Image:
    if transparent:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))
    color = background or "#ffffff"
    return Image.new("RGBA", (width, height), color).convert("RGBA")


def _draw_shadow(canvas: Image.Image, rect: NodeRect, *, blur_px: int, opacity: float) -> None:
    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow_layer)
    offset = max(2, blur_px // 4)
    alpha = int(max(0.0, min(1.0, opacity)) * 255)
    d.rectangle(
        [rect.x + offset, rect.y + offset, rect.x2 + offset, rect.y2 + offset],
        fill=(0, 0, 0, alpha),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur_px))
    canvas.alpha_composite(shadow_layer)


def _resize_to_fit(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Like ``Image.thumbnail``, but scales UP as well as down. ``thumbnail``
    only ever shrinks — fine while cards were small enough that source media
    was reliably bigger than the card, but once cards are sized generously
    (see scene_graph/layout.py's slot templates) a smaller source image was
    left stranded at its native size instead of filling the card."""
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0 or max_w <= 0 or max_h <= 0:
        return image
    scale = min(max_w / src_w, max_h / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    if (new_w, new_h) == (src_w, src_h):
        return image
    return image.resize((new_w, new_h), Image.LANCZOS)


def _draw_node_media(
    canvas: Image.Image,
    node: SceneNode,
    rect: NodeRect,
    media_image: Optional[Image.Image],
    *,
    style: StylePreset,
    hollow: bool = False,
) -> None:
    """``hollow=True`` draws only the shadow+border (transparent interior) —
    used for a ``video_loop`` card whose real source video is composited
    live underneath this decoration by scene_graph.render, instead of a
    static thumbnail baked in here."""
    node_style = style.nodes or {}
    shadow_cfg = node_style.get("shadow") or {}
    border_cfg = node_style.get("border") or {}

    if shadow_cfg.get("enabled", True):
        _draw_shadow(
            canvas, rect,
            blur_px=int(shadow_cfg.get("blur_px", 18)),
            opacity=float(shadow_cfg.get("opacity", 0.25)),
        )

    if not hollow:
        if media_image is not None:
            fitted = _resize_to_fit(media_image, max(1, int(rect.width)), max(1, int(rect.height)))
            paste_x = int(rect.x + (rect.width - fitted.width) / 2)
            paste_y = int(rect.y + (rect.height - fitted.height) / 2)
            canvas.alpha_composite(fitted, (paste_x, paste_y))
        else:
            placeholder = Image.new("RGBA", (int(rect.width), int(rect.height)), _PLACEHOLDER_FILL)
            pd = ImageDraw.Draw(placeholder)
            label = f"[{node.type}]\n{node.id}"
            font = _load_font(_CAPTION_FONT_CANDIDATES, max(12, int(rect.height * 0.12)))
            pd.multiline_text((10, 10), label, fill=(90, 90, 90, 255), font=font)
            canvas.alpha_composite(placeholder, (int(rect.x), int(rect.y)))

    if border_cfg.get("enabled", True):
        d = ImageDraw.Draw(canvas)
        width_px = int(border_cfg.get("width_px", 3))
        color = border_cfg.get("color", "#1a1a1a")
        d.rectangle([rect.x, rect.y, rect.x2, rect.y2], outline=color, width=max(1, width_px))


_LABEL_RESERVE_PX = 56  # vertical room a non-empty node.label needs ABOVE the rect


def _draw_node_label(canvas: Image.Image, node: SceneNode, rect: NodeRect) -> None:
    """A short red tag directly above the media (e.g. "Vasa") — the
    reference style's per-image identifier, distinct from both the big
    centered chapter TitleCue and the longer black caption below the media."""
    label = str(node.label or "").strip()
    if not label:
        return
    font = _load_font(_LABEL_FONT_CANDIDATES, max(20, min(32, int(rect.height * 0.09))))
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), label, font=font)
    y = rect.y - (bbox[3] - bbox[1]) - 28
    draw.text((rect.x, y), label, font=font, fill=_LABEL_COLOR)


_CAPTION_MAX_LINES = 3
# Must stay >= the largest |dx|/dy in routing._CAPTION_OFFSET_LADDER (48/52)
# — the reveal frame's local sub-canvas padding (render_node_reveal_frame)
# uses this so a solved alternate caption position never clips against the
# sub-canvas's own edge.
_CAPTION_OFFSET_MARGIN_PX = 60


def _wrap_caption_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: float, max_lines: int) -> List[str]:
    """Greedy word-wrap so a caption never runs past its own card's width —
    the layout engine reserves the vertical room (CAPTION_RESERVE_PX in
    scene_graph/layout.py); this is what keeps it from overflowing
    horizontally too. Truncates with an ellipsis if it still doesn't fit in
    ``max_lines`` (captions are meant to be short — 6-14 words — so this is
    a safety net, not the normal case)."""
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    consumed = 1
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
            consumed += 1
        else:
            lines.append(current)
            current = word
            consumed += 1
            if len(lines) == max_lines - 1:
                break
    lines.append(current)
    if consumed < len(words):
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "…", font=font)[2] > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else ""
        lines[-1] = f"{last}…" if last else "…"
    return lines[:max_lines]


def _highlight_terms(highlight: Optional[str]) -> List[str]:
    """``highlight`` is one or more comma-separated substrings (see
    CaptionSpec docstring) — longest-first so e.g. "Bay of Biscay" is matched
    whole rather than a shorter overlapping term inside it winning first."""
    if not highlight:
        return []
    terms = [t.strip() for t in str(highlight).split(",") if t.strip()]
    return sorted(set(terms), key=len, reverse=True)


def _split_highlight_runs(line: str, terms: List[str]) -> List[Tuple[str, bool]]:
    """Splits ``line`` into ``(text, is_highlighted)`` runs, scanning for the
    earliest/longest matching term at each position, left to right."""
    if not terms:
        return [(line, False)]
    runs: List[Tuple[str, bool]] = []
    i = 0
    n = len(line)
    while i < n:
        match = None
        for term in terms:
            if line.startswith(term, i):
                match = term
                break
        if match:
            runs.append((match, True))
            i += len(match)
        else:
            start = i
            i += 1
            while i < n and not any(line.startswith(t, i) for t in terms):
                i += 1
            runs.append((line[start:i], False))
    return runs


def _draw_caption(
    canvas: Image.Image, caption: CaptionSpec, rect: NodeRect, *, style: StylePreset,
    offset: Tuple[float, float] = (0.0, 0.0),
) -> None:
    """``offset`` is an ALREADY-SOLVED (dx, dy) nudge away from the default
    position — see scene_graph.layout.compute_layout's narration-caption
    pass / scene_graph.routing.solve_caption_position. (0, 0), the default,
    reproduces the exact pre-existing position: nothing here ever searches
    for a placement itself, it only draws at rect's position plus whatever
    offset the caller (already computed once, at layout time) supplies."""
    if not caption or not caption.text:
        return
    highlight_color = (style.arrows or {}).get("default_color", "#c0392b")
    # Capped, not just proportional: the layout engine reserves a FIXED
    # pixel caption clearance (CAPTION_RESERVE_PX in scene_graph/layout.py),
    # and an uncapped font would keep growing with a bigger card and could
    # outgrow that reserved band.
    font = _load_font(_CAPTION_FONT_CANDIDATES, min(34, max(14, int(rect.height * 0.09))))
    draw = ImageDraw.Draw(canvas)

    terms = _highlight_terms(caption.highlight)
    lines = _wrap_caption_lines(draw, caption.text, font, rect.width, _CAPTION_MAX_LINES)
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + 6
    x = rect.x + offset[0]
    y = rect.y2 + 10 + offset[1]

    for line in lines:
        cursor_x = x
        for segment, is_highlight in _split_highlight_runs(line, terms):
            if not segment:
                continue
            color = highlight_color if is_highlight else _CAPTION_COLOR
            draw.text((cursor_x, y), segment, font=font, fill=color)
            bbox = draw.textbbox((cursor_x, y), segment, font=font)
            cursor_x = bbox[2]
        y += line_height


def _draw_anchor(canvas: Image.Image, node: SceneNode, rect: NodeRect, media_image: Optional[Image.Image]) -> None:
    d = ImageDraw.Draw(canvas)
    d.ellipse([rect.x, rect.y, rect.x2, rect.y2], outline="#1a1a1a", width=4)
    if media_image is not None:
        inset = int(rect.width * 0.12)
        fitted = _resize_to_fit(media_image, int(rect.width) - 2 * inset, int(rect.height) - 2 * inset)
        canvas.alpha_composite(
            fitted,
            (int(rect.x + (rect.width - fitted.width) / 2), int(rect.y + (rect.height - fitted.height) / 2)),
        )


def _bezier_point(p0, p1, p2, p3, t: float):
    mt = 1.0 - t
    x = mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0]
    y = mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1]
    return (x, y)


def _hand_drawn_curve(
    x0: float, y0: float, x1: float, y1: float, *, jitter: float = 10.0, seed: str = "", samples: int = 28,
) -> List[Tuple[float, float]]:
    """A cubic-Bezier stroke with a DETERMINISTIC, asymmetric wobble standing
    in for a hand-drawn/marker curve — same edge id always renders the same
    curve (no per-render randomness), never a perfectly straight technical
    line. Densely sampled so the progressive draw-on animation looks like a
    continuous stroke rather than a coarse polyline.

    Fallback-only: the real production path (scene_graph.render) always has
    an ALREADY-SOLVED, obstacle-aware route (see
    scene_graph.routing.solve_edge_route, cached once per edge at layout
    time) and applies this same jitter to it via _jitter_polyline instead —
    this direct-line-plus-jitter version only runs for callers that never
    solved a route (the legacy render_composition, or a direct test)."""
    import hashlib
    import math

    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length  # unit normal

    digest = hashlib.sha1((seed or f"{x0},{y0},{x1},{y1}").encode("utf-8")).digest()

    def _unit(byte_index: int) -> float:
        return (digest[byte_index] / 255.0) * 2.0 - 1.0  # -> [-1, 1], deterministic per seed

    off1 = jitter * (0.6 + 0.4 * _unit(0))
    off2 = jitter * (0.6 + 0.4 * _unit(1))
    along1 = 0.30 + 0.08 * _unit(2)
    along2 = 0.66 + 0.08 * _unit(3)
    bow = jitter * 0.35 * _unit(4)  # slight overall bow — never perfectly straight

    p0 = (x0, y0)
    p1 = (x0 + dx * along1 + nx * (off1 + bow), y0 + dy * along1 + ny * (off1 + bow))
    p2 = (x0 + dx * along2 + nx * (off2 - bow * 0.4), y0 + dy * along2 + ny * (off2 - bow * 0.4))
    p3 = (x1, y1)
    return [_bezier_point(p0, p1, p2, p3, i / (samples - 1)) for i in range(samples)]


def _polyline_length(points) -> float:
    import math

    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])) or 1e-6


def _truncate_polyline(points, progress: float):
    """The leading `progress` fraction (by arc length) of a polyline —
    the geometric core of the arrow's progressive draw-on animation."""
    import math

    progress = max(0.0, min(1.0, progress))
    if progress >= 1.0:
        return list(points)
    target = _polyline_length(points) * progress
    out = [points[0]]
    covered = 0.0
    for a, b in zip(points, points[1:]):
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        if covered + seg_len >= target:
            remaining = target - covered
            t = remaining / seg_len if seg_len else 0.0
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            return out
        out.append(b)
        covered += seg_len
    return out


def _rect_keep_out_box(rect: NodeRect) -> ObstacleRect:
    """A card's rect expanded to include its caption band below (the same
    keep-out zone used throughout: arrows, labels, and — in
    scene_graph.layout's one-time route solve — obstacle avoidance)."""
    from .layout import CAPTION_RESERVE_PX

    return ObstacleRect(rect.x, rect.y, rect.x2, rect.y2 + CAPTION_RESERVE_PX)


def _keep_out_exit_point(cx: float, cy: float, tx: float, ty: float, rect: NodeRect, *, pad: float) -> Tuple[float, float]:
    """Where the ray from (cx, cy) toward (tx, ty) first exits ``rect``'s
    keep-out box (expanded by ``pad``) — so an arrow starts/ends at the
    card's edge, never cutting across its own or the OTHER card's caption
    text along the way. Cheap O(1) ray/AABB math (see
    routing.keep_out_exit_point) — safe every frame, unlike the route
    SHAPE itself (bow_bulge/bow_side), which is solved once and cached."""
    return keep_out_exit_point(cx, cy, tx, ty, _rect_keep_out_box(rect), pad=pad)


def _jitter_polyline(points: List[Tuple[float, float]], *, jitter: float, seed: str) -> List[Tuple[float, float]]:
    """Applies the small deterministic hand-drawn wobble to an
    ALREADY-SOLVED polyline (see routing.solve_edge_route, cached once per
    edge onto SceneGraphLayout) — never re-solves or re-searches the route,
    just perturbs it slightly for texture, per "solve clean curve, then
    apply subtle deterministic wobble." Tapers to zero at both ends so the
    endpoints stay EXACTLY anchored at the card boundary the solve chose."""
    import hashlib

    if jitter <= 0 or len(points) < 3:
        return list(points)
    digest = hashlib.sha1((seed or "edge").encode("utf-8")).digest()
    n = len(points)
    taper_span = max(1, min(4, n // 4))
    out: List[Tuple[float, float]] = []
    for i, (x, y) in enumerate(points):
        a = points[max(0, i - 1)]
        b = points[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx, ny = -dy / length, dx / length
        unit = (digest[i % len(digest)] / 255.0) * 2.0 - 1.0
        taper = min(1.0, min(i, n - 1 - i) / taper_span)
        off = jitter * unit * taper
        out.append((x + nx * off, y + ny * off))
    return out


def _draw_arrow(
    canvas: Image.Image, edge: SceneEdge, from_rect: NodeRect, to_rect: NodeRect, *, style: StylePreset,
    progress: float = 1.0, route_points: Optional[List[Tuple[float, float]]] = None,
    label_pos: Optional[Tuple[float, float]] = None,
) -> None:
    """Draws the arrow up to `progress` (0..1) of its length — progress=1.0
    is the classic fully-drawn arrow; progress<1.0 is one frame of the
    cause->effect draw-on animation (see render_edge_reveal_frame).

    ``route_points`` and ``label_pos`` are ALREADY-SOLVED, cached values
    from scene_graph.layout.compute_layout (see routing.solve_edge_route /
    routing.solve_label_position — a route that bends around any
    third-party card between the two endpoints, tried once at layout time,
    never per frame). This function only SAMPLES that solved shape into
    pixels (applying the small cosmetic jitter on top — see
    _jitter_polyline) once per frame; it never searches for a route or
    label position itself. Both default to None ("no obstacle avoidance" —
    a direct line, on-the-fly label placement) so any caller that hasn't
    solved a route yet (e.g. the legacy render_composition below, or a
    direct test) keeps working exactly as before."""
    import math

    if progress <= 0.0:
        return
    arrow_cfg = style.arrows or {}
    is_callout = str(edge.kind or "sequential").lower() == "callout"
    # Sequential (default) connectors are the plain black cause->effect
    # chain; a "callout" arrow is the reference style's rare, thicker RED
    # pointer used to call out a specific proof/detail (e.g. caption text ->
    # the photo that proves it) — visually distinct so it doesn't blend into
    # the ordinary connector chain.
    if is_callout:
        color = edge.color or arrow_cfg.get("default_color", "#c0392b")
        line_width = 11
    else:
        color = edge.color or arrow_cfg.get("alt_color", "#1a1a1a")
        line_width = 6
    jitter = 10.0 if arrow_cfg.get("organic_jitter", True) else 0.0

    if route_points is not None:
        full_points = _jitter_polyline(list(route_points), jitter=jitter, seed=edge.id)
    else:
        # Fallback for callers that never solved a route (e.g. the legacy
        # render_composition, or a direct unit test) — a direct line built
        # on the fly, same as the original always-search behavior. The
        # real per-frame production path (scene_graph.render) always passes
        # cached route_points and never reaches this branch.
        from_cx, from_cy = from_rect.center
        to_cx, to_cy = to_rect.center
        x0, y0 = _keep_out_exit_point(from_cx, from_cy, to_cx, to_cy, from_rect, pad=16)
        x1, y1 = _keep_out_exit_point(to_cx, to_cy, from_cx, from_cy, to_rect, pad=16)
        full_points = _hand_drawn_curve(x0, y0, x1, y1, jitter=jitter, seed=edge.id)

    points = _truncate_polyline(full_points, progress)
    if len(points) < 2:
        return

    d = ImageDraw.Draw(canvas)
    d.line(points, fill=color, width=line_width, joint="curve")

    # Arrowhead only once the stroke has essentially reached its target —
    # appearing naturally at the end of the draw-on, not from frame one.
    if progress >= 0.96:
        ax, ay = points[-2]
        bx, by = points[-1]
        angle = math.atan2(by - ay, bx - ax)
        head_len, head_w = (34, 20) if is_callout else (28, 16)
        left = (bx - head_len * math.cos(angle - math.radians(25)), by - head_len * math.sin(angle - math.radians(25)))
        right = (bx - head_len * math.cos(angle + math.radians(25)), by - head_len * math.sin(angle + math.radians(25)))
        d.polygon([(bx, by), left, right], fill=color)

        label = str((edge.metadata or {}).get("label") or "").strip()
        if label:
            if label_pos is not None:
                _draw_edge_label_at(canvas, label_pos, label)
            else:
                # Fallback for callers that never solved a route (e.g. the
                # legacy render_composition, or a direct unit test) — an
                # on-the-fly search, same as the old always-search
                # behavior. The real per-frame production path
                # (scene_graph.render) always passes a cached label_pos and
                # never reaches this branch.
                from .routing import solve_label_position

                font = _load_font(_CAPTION_FONT_CANDIDATES, 26)
                bbox = ImageDraw.Draw(canvas).textbbox((0, 0), label, font=font)
                half_w, half_h = (bbox[2] - bbox[0]) / 2.0, (bbox[3] - bbox[1]) / 2.0
                pos = solve_label_position(
                    full_points, half_w, half_h,
                    keep_out=[_rect_keep_out_box(from_rect), _rect_keep_out_box(to_rect)],
                )
                _draw_edge_label_at(canvas, pos, label)


def _draw_edge_label_at(canvas: Image.Image, position: Tuple[float, float], label: str) -> None:
    """Draws ``label`` centered at an ALREADY-SOLVED position (see
    routing.solve_label_position, cached once per edge onto
    SceneGraphLayout) — the reference "Overscaled" style's inline arrow
    annotations (e.g. "In 1628"). No search happens here."""
    font = _load_font(_CAPTION_FONT_CANDIDATES, 26)
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), label, font=font)
    half_w, half_h = (bbox[2] - bbox[0]) / 2.0, (bbox[3] - bbox[1]) / 2.0
    x, y = position
    draw.text((x - half_w, y - half_h), label, font=font, fill=_CAPTION_COLOR)


def render_edge_reveal_frame(
    edge: SceneEdge, from_rect: NodeRect, to_rect: NodeRect, style: StylePreset,
    *, canvas_size, progress: float, route_points: Optional[List[Tuple[float, float]]] = None,
    label_pos: Optional[Tuple[float, float]] = None,
) -> Image.Image:
    """One transparent canvas-sized frame of the arrow's draw-on animation
    at the given progress (0..1) — used by scene_graph.render to build a
    real multi-frame FFmpeg overlay input, not a single static fade.
    ``route_points``/``label_pos`` are the cached, already-solved
    route/label from SceneGraphLayout (see scene_graph.routing) — passed
    straight through to _draw_arrow, never re-solved here."""
    frame = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    eased = 1 - (1 - max(0.0, min(1.0, progress))) ** 2  # ease-out — a restrained, not-cheesy draw-on
    _draw_arrow(
        frame, edge, from_rect, to_rect, style=style, progress=eased,
        route_points=route_points, label_pos=label_pos,
    )
    return frame


def render_node_reveal_frame(
    node: SceneNode, rect: NodeRect, media_image: Optional[Image.Image], style: StylePreset,
    *, canvas_size, background: str, progress: float, hollow: bool = False,
    caption_offset: Tuple[float, float] = (0.0, 0.0),
) -> Image.Image:
    """One transparent canvas-sized frame of a node's reveal: a restrained
    scale-in (95% -> 100%) + fade, easing out, never a 'cheesy' bounce.

    ``caption_offset`` is the same ALREADY-SOLVED (dx, dy) nudge
    _draw_caption takes — see scene_graph.layout.compute_layout's
    narration-caption pass. (0, 0), the default, reproduces the exact
    pre-existing layout."""
    progress = max(0.0, min(1.0, progress))
    eased = 1 - (1 - progress) ** 3
    frame = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if progress <= 0.0:
        return frame

    # Draw the node at FULL size on its own small canvas, then scale that
    # sub-image down to the current eased scale and re-paste centered on
    # the rect's own center, so it grows INTO place rather than shifting.
    # `pad` is just scale-in growth headroom (~24px on every side is
    # plenty) — but the caption is drawn BELOW sub_rect and the label ABOVE
    # it, inside this same sub-canvas, so each needs a much bigger margin
    # than that or its own text gets clipped by the sub-canvas's edge
    # regardless of how much room scene_graph/layout.py's
    # CAPTION_RESERVE_PX reserved in the outer canvas (a real bug: those
    # two numbers were unrelated). side_pad/bottom_pad also unconditionally
    # cover the caption offset ladder's worst case (_CAPTION_OFFSET_MARGIN_PX)
    # so a solved alternate position never clips against this sub-canvas's
    # own edge, whether or not THIS particular node actually got nudged.
    pad = 24
    side_pad = pad
    bottom_pad = pad
    if node.type != "anchor" and node.caption and node.caption.text:
        # Up to 3 lines at the caption's own font-size cap (see
        # _draw_caption), plus the leading gap — with a safety margin.
        bottom_pad = max(pad, 200) + _CAPTION_OFFSET_MARGIN_PX
        side_pad = pad + _CAPTION_OFFSET_MARGIN_PX
    top_pad = pad
    if node.type != "anchor" and node.label:
        top_pad = max(pad, _LABEL_RESERVE_PX + pad)
    sub = Image.new(
        "RGBA", (int(rect.width) + 2 * side_pad, int(rect.height) + top_pad + bottom_pad), (0, 0, 0, 0)
    )
    sub_rect = NodeRect(node_id=rect.node_id, x=side_pad, y=top_pad, width=rect.width, height=rect.height)
    if node.type == "anchor":
        _draw_anchor(sub, node, sub_rect, media_image)
    else:
        _draw_node_media(sub, node, sub_rect, media_image, style=style, hollow=hollow)
        _draw_node_label(sub, node, sub_rect)
        if node.caption:
            _draw_caption(sub, node.caption, sub_rect, style=style, offset=caption_offset)

    scale = 0.95 + 0.05 * eased
    new_w, new_h = max(1, round(sub.width * scale)), max(1, round(sub.height * scale))
    scaled = sub.resize((new_w, new_h), Image.LANCZOS)
    if eased < 1.0:
        alpha = scaled.split()[-1].point(lambda a: int(a * eased))
        scaled.putalpha(alpha)

    # Anchor on sub_rect's OWN center (scaled), not the whole sub-canvas's
    # center — top_pad/bottom_pad above are asymmetric (room for the label
    # above and caption below), so the sub-canvas's own center no longer
    # coincides with the card's.
    cx, cy = rect.center
    sub_rect_cx, sub_rect_cy = side_pad + rect.width / 2.0, top_pad + rect.height / 2.0
    paste_x = int(round(cx - sub_rect_cx * scale))
    paste_y = int(round(cy - sub_rect_cy * scale))
    frame.alpha_composite(scaled, (paste_x, paste_y))
    return frame


def render_node_media_only_frame(
    node: SceneNode, rect: NodeRect, media_image: Optional[Image.Image], style: StylePreset,
) -> Image.Image:
    """Just the fitted media — no label, no caption — cropped to exactly
    ``rect``'s own size, in LOCAL (0,0)-origin coordinates, not the full
    canvas. This is the KEN BURNS input: scene_graph.render feeds this one
    small static image straight to FFmpeg's own zoompan filter (never
    re-rendered per frame in Python — see that module), the same way
    _node_video_layer already feeds a video_loop's real footage cropped to
    its own rect before overlaying it at (rect.x, rect.y) — so only the
    photo pans/zooms while the label/caption (rendered separately at their
    real canvas position, see render_node_decoration_frame) stay put:
    "only the image content/object moves inside its assigned visual area,"
    never the camera, never the surrounding text."""
    local_rect = NodeRect(node_id=rect.node_id, x=0.0, y=0.0, width=rect.width, height=rect.height)
    frame = Image.new("RGBA", (max(1, round(rect.width)), max(1, round(rect.height))), (0, 0, 0, 0))
    _draw_node_media(frame, node, local_rect, media_image, style=style)
    return frame


def render_node_decoration_frame(
    node: SceneNode, rect: NodeRect, style: StylePreset, *, canvas_size,
    caption_offset: Tuple[float, float] = (0.0, 0.0),
) -> Image.Image:
    """Just the label (above) and caption (below) — no media — the
    complement to render_node_media_only_frame: composited on top of the
    (Ken-Burns-animated, via FFmpeg zoompan) media layer so the text stays
    perfectly still while the photo underneath moves.

    ``caption_offset`` — see render_node_reveal_frame's docstring; same
    already-solved (dx, dy), same (0, 0) no-op default."""
    frame = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    _draw_node_label(frame, node, rect)
    if node.caption:
        _draw_caption(frame, node.caption, rect, style=style, offset=caption_offset)
    return frame


def render_title_reveal_frame(text: str, *, canvas_size, top_margin: int, progress: float) -> Image.Image:
    """One transparent canvas-sized frame of a persistent chapter/subject
    title's reveal: bold, centered, near the top — a simple fade-in (no
    scale, no card) matching the reference "Overscaled" style's per-subject
    header (e.g. "Vasa", "HMS Captain"), independent of any image node."""
    progress = max(0.0, min(1.0, progress))
    frame = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if progress <= 0.0 or not text:
        return frame

    font = _load_font(_TITLE_FONT_CANDIDATES, max(36, int(canvas_size[1] * 0.07)))
    draw = ImageDraw.Draw(frame)
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (canvas_size[0] - (bbox[2] - bbox[0])) / 2.0
    y = top_margin
    alpha = int(255 * progress)
    draw.text((x, y), text, font=font, fill=(20, 20, 20, alpha))
    return frame


_CHECKLIST_INACTIVE_FILL = (208, 208, 208, 255)  # grey — not yet reached
_CHECKLIST_CURRENT_FILL = (192, 57, 43, 255)  # matches _LABEL_COLOR / arrows.default_color
_CHECKLIST_COMPLETED_FILL = (90, 90, 90, 255)  # darker neutral — reached and passed
_CHECKLIST_CELL_GUTTER_PX = 6
_CHECKLIST_CELL_TOP_PX = 14  # top padding inside the reserved band


def render_checklist_strip_frame(
    labels: List[str], current_index: int, *, canvas_size: Tuple[int, int], band_height: float, margin_px: int,
) -> Image.Image:
    """One transparent canvas-sized frame of Exp Solar's persistent
    checklist header strip: up to CHECKLIST_MAX_ITEMS (15) evenly-spaced
    cells across the reserved top band (scene_graph.layout.CHECKLIST_BAND_PX/
    checklist_band_px), each a small filled rounded cell + centered number
    + a short label beneath it. State is purely a function of position
    relative to ``current_index`` (items before it: completed/darker;
    ``current_index`` itself: highlighted; after it: inactive/grey) — never
    per-frame animation, matching the reference's instant state-change
    ("turns to full color once its segment is reached") rather than a
    fade. No per-item thumbnail: text-only, so this never depends on asset
    resolution — only Exp Solar's own CSV-declared labels.
    """
    frame = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    n = len(labels)
    if n == 0:
        return frame

    draw = ImageDraw.Draw(frame)
    stage_w = canvas_size[0] - 2 * margin_px
    cell_w = stage_w / n
    cell_h = max(24.0, band_height - _CHECKLIST_CELL_TOP_PX - 10)
    number_font = _load_font(_LABEL_FONT_CANDIDATES, max(14, min(22, int(cell_h * 0.42))))
    label_font = _load_font(_CAPTION_FONT_CANDIDATES, max(10, min(14, int(cell_h * 0.22))))

    for i, label in enumerate(labels):
        if i < current_index:
            fill = _CHECKLIST_COMPLETED_FILL
        elif i == current_index:
            fill = _CHECKLIST_CURRENT_FILL
        else:
            fill = _CHECKLIST_INACTIVE_FILL

        cell_x = margin_px + i * cell_w
        box = [
            cell_x + _CHECKLIST_CELL_GUTTER_PX / 2, _CHECKLIST_CELL_TOP_PX,
            cell_x + cell_w - _CHECKLIST_CELL_GUTTER_PX / 2, _CHECKLIST_CELL_TOP_PX + cell_h,
        ]
        radius = min(10.0, cell_h * 0.2, cell_w * 0.2)
        draw.rounded_rectangle(box, radius=radius, fill=fill)

        number_text = str(i + 1)
        nb = draw.textbbox((0, 0), number_text, font=number_font)
        nx = (box[0] + box[2]) / 2.0 - (nb[2] - nb[0]) / 2.0
        ny = box[1] + cell_h * 0.12
        draw.text((nx, ny), number_text, font=number_font, fill=(255, 255, 255, 255))

        short_label = (label or "").strip()
        if short_label:
            if len(short_label) > 10:
                short_label = short_label[:9] + "…"
            lb = draw.textbbox((0, 0), short_label, font=label_font)
            lx = (box[0] + box[2]) / 2.0 - (lb[2] - lb[0]) / 2.0
            ly = box[1] + cell_h * 0.55
            if ly + (lb[3] - lb[1]) <= box[3]:  # only draw if it actually fits the cell
                draw.text((lx, ly), short_label, font=label_font, fill=(255, 255, 255, 255))

    return frame


def render_composition(
    scene_graph: SceneGraph,
    layout: SceneGraphLayout,
    style: StylePreset,
    *,
    resolved_media: Optional[Dict[str, str]] = None,
    out_dir: Path,
) -> CompositionAssets:
    """Render the final canvas plus per-node/per-edge fade-in overlay PNGs."""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    resolved_media = resolved_media or {}
    background = (style.canvas or {}).get("background", "#ffffff")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        media_images: Dict[str, Optional[Image.Image]] = {
            n.id: load_media_image(resolved_media.get(n.id), tmp_dir) for n in scene_graph.nodes
        }

        canvas = _blank_canvas(layout.canvas_width, layout.canvas_height, background, transparent=False)
        node_overlays: Dict[str, Path] = {}
        edge_overlays: Dict[str, Path] = {}

        for node in scene_graph.nodes:
            rect = layout.node_rects.get(node.id)
            if rect is None:
                continue
            if node.type == "anchor":
                _draw_anchor(canvas, node, rect, media_images.get(node.id))
            else:
                _draw_node_media(canvas, node, rect, media_images.get(node.id), style=style)
                _draw_node_label(canvas, node, rect)
                if node.caption:
                    _draw_caption(canvas, node.caption, rect, style=style)

            # Standalone transparent overlay for this node (fade-in source).
            overlay = _blank_canvas(layout.canvas_width, layout.canvas_height, background, transparent=True)
            if node.type == "anchor":
                _draw_anchor(overlay, node, rect, media_images.get(node.id))
            else:
                _draw_node_media(overlay, node, rect, media_images.get(node.id), style=style)
                _draw_node_label(overlay, node, rect)
                if node.caption:
                    _draw_caption(overlay, node.caption, rect, style=style)
            overlay_path = out_dir / f"node_{node.id}.png"
            overlay.save(overlay_path)
            node_overlays[node.id] = overlay_path

        for edge in scene_graph.edges:
            from_rect = layout.node_rects.get(edge.from_node)
            to_rect = layout.node_rects.get(edge.to_node)
            if from_rect is None or to_rect is None:
                continue
            _draw_arrow(canvas, edge, from_rect, to_rect, style=style)

            overlay = _blank_canvas(layout.canvas_width, layout.canvas_height, background, transparent=True)
            _draw_arrow(overlay, edge, from_rect, to_rect, style=style)
            overlay_path = out_dir / f"edge_{edge.id}.png"
            overlay.save(overlay_path)
            edge_overlays[edge.id] = overlay_path

        canvas_path = out_dir / "canvas.png"
        canvas.convert("RGB").save(canvas_path)

    return CompositionAssets(canvas_path=canvas_path, node_overlay_paths=node_overlays, edge_overlay_paths=edge_overlays)
