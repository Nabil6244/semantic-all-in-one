"""Render graphic overlays to PNG for the existing FFmpeg overlay pipeline.

Reuses typography fonts / placement. Does NOT invent a second renderer —
produces full-frame RGBA PNGs that `_apply_overlays_to_clip` already consumes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .backgrounds import background_params, choose_background
from .design_system import DocumentaryDesignSystem, get_design_system
from .motion import overlay_animation_name
from .schema import GraphicSpec, TextOverlaySpec


def render_graphic_overlay(
    spec: GraphicSpec,
    out_path: Path | str,
    width: int,
    height: int,
    *,
    design: DocumentaryDesignSystem | None = None,
    composition: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Render one GraphicSpec to a transparent PNG. None if nothing to draw."""
    design = design or get_design_system()
    # Phase 1–3: text / statistic / lower-third / label / callout.
    # MAP / CHART / PROCESS fall back to text treatment until their phases.
    text = spec.text
    if text is None or not (text.text or "").strip():
        # Try payload text
        hint = str((spec.payload or {}).get("text") or "").strip()
        if not hint:
            return None
        text = TextOverlaySpec(role=spec.role, text=hint)

    template = str((spec.payload or {}).get("template") or "")
    if template.startswith("dataviz_") and (spec.payload or {}).get("dataviz"):
        from .dataviz import DataViz, render_dataviz

        return render_dataviz(DataViz.from_dict(spec.payload["dataviz"]), out_path, width, height, design=design)
    if template == "countdown_tag":
        return _render_countdown_tag(text.text, out_path, width, height)
    if template == "countdown_hook":
        return _render_countdown_hook(text.text, out_path, width, height)
    if template == "keyword_callout":
        return _render_countdown_hook(text.text, out_path, width, height, size_frac=0.078, center_y=0.42)
    if spec.role.upper() == "STATISTIC" or spec.decision == "STATISTIC":
        return _render_statistic(text, out_path, width, height, design=design, composition=composition)
    # Documentary default: cyan-bar lower-third panel for names, callouts, emphasis.
    if spec.role.upper() in (
        "LOWER_THIRD", "NAME", "CALLOUT", "EMPHASIS", "LABEL"
    ) or spec.decision in ("LOWER_THIRD", "CALLOUT"):
        return _render_lower_third(text, out_path, width, height, design=design)
    return _render_text_overlay(text, out_path, width, height, design=design, composition=composition)


def graphic_timed_overlay_tuple(
    spec: GraphicSpec,
    png: Path,
    *,
    scene_start: float,
) -> Tuple[Path, float, float, str, Optional[Tuple[int, int]]]:
    """Convert absolute-timeline graphic → scene-local timed overlay item."""
    t0 = max(0.0, float(spec.start) - float(scene_start))
    t1 = max(t0 + 0.12, float(spec.end) - float(scene_start))
    anim = overlay_animation_name(spec.animation or (spec.text.animation if spec.text else "FADE"))
    center = None
    if anim == "scale_fade":
        # scale_fade grows the full-frame overlay about this point (its text's centre).
        center = tuple((spec.payload or {}).get("center") or ()) or _png_center(png)
    return (png, t0, t1, anim, center)


def _png_center(png: Path) -> Optional[Tuple[int, int]]:
    try:
        from PIL import Image

        with Image.open(png) as im:
            box = im.getbbox()
            if box:
                return ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
            return (im.width // 2, im.height // 2)
    except Exception:
        return None


def render_graphics_for_scene(
    specs: Sequence[GraphicSpec],
    *,
    scene_number: str,
    scene_start: float,
    scene_end: float,
    width: int,
    height: int,
    out_dir: Path,
    composition: Optional[Dict[str, Any]] = None,
    design: DocumentaryDesignSystem | None = None,
) -> List[Tuple[Path, float, float, str, Optional[Tuple[int, int]]]]:
    """Render all graphics overlapping a scene window → timed overlay list."""
    design = design or get_design_system()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sn = str(scene_number)
    timed: List[Tuple[Path, float, float, str, Optional[Tuple[int, int]]]] = []
    for i, spec in enumerate(specs):
        if sn and str(spec.scene_number) not in ("", sn, sn.zfill(3), sn.lstrip("0") or sn):
            # Still allow cross-scene graphics that overlap this window.
            if not (spec.start < scene_end and spec.end > scene_start):
                continue
        elif not (spec.start < scene_end and spec.end > scene_start):
            continue
        # Skip unimplemented complex graphics that have no text fallback.
        if spec.decision in ("MAP", "CHART", "PROCESS", "TIMELINE") and not (
            spec.text and spec.text.text
        ):
            continue
        png_path = out_dir / f"gfx_{sn}_{i:02d}_{spec.role.lower()}.png"
        png = render_graphic_overlay(
            spec, png_path, width, height, design=design, composition=composition
        )
        if png is None:
            continue
        timed.append(graphic_timed_overlay_tuple(spec, png, scene_start=scene_start))
    return timed


# ---------------------------------------------------------------------------
# Internal renderers
# ---------------------------------------------------------------------------

def _load_font(family: str, weight: str, size: int):
    from typography.fonts import resolve_font_path
    from PIL import ImageFont

    path = resolve_font_path(family, weight)
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            pass
    try:
        return ImageFont.truetype("Arial.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def _measure(draw, text: str, font, stroke: int = 0) -> tuple[int, int]:
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_lines(draw, text: str, font, max_width: int, max_lines: int) -> List[str]:
    words = (text or "").split()
    if not words:
        return [""]
    max_lines = max(1, int(max_lines))
    lines: List[str] = []
    cur = ""
    for word in words:
        trial = word if not cur else f"{cur} {word}"
        tw, _ = _measure(draw, trial, font)
        if tw <= max_width or not cur:
            cur = trial
            continue
        lines.append(cur)
        cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        head = lines[: max_lines - 1]
        tail = " ".join(lines[max_lines - 1 :])
        lines = head + [tail]
    return lines


def _fit_fontsize(
    draw,
    text: str,
    *,
    load_font,
    family: str,
    weight: str,
    start_size: int,
    min_size: int,
    max_width: int,
    max_height: int,
    max_lines: int,
) -> tuple[int, object, List[str], int, int]:
    """Shrink until wrapped block fits max_width × max_height."""
    size = max(min_size, int(start_size))
    font = load_font(family, weight, size)
    lines = _wrap_lines(draw, text, font, max_width, max_lines)
    tw = th = 0
    for _ in range(12):
        font = load_font(family, weight, size)
        lines = _wrap_lines(draw, text, font, max_width, max_lines)
        widths = [_measure(draw, ln, font)[0] for ln in lines] or [0]
        heights = [_measure(draw, ln, font)[1] for ln in lines] or [size]
        tw = max(widths)
        gap = max(2, int(size * 0.18))
        th = sum(heights) + gap * max(0, len(lines) - 1)
        too_wide = tw > max_width
        too_tall = th > max_height
        if (not too_wide and not too_tall) or size <= min_size:
            break
        size = max(min_size, int(size * 0.90))
    return size, font, lines, tw, th


def _draw_background(img, draw, kind_params: dict, x: int, y: int, tw: int, th: int, width: int, height: int):
    from PIL import Image, ImageDraw, ImageFilter

    if not kind_params.get("draw"):
        return img, draw
    shape = kind_params.get("shape") or "ellipse"
    pad_x = int(kind_params.get("pad_x") or 0)
    pad_y = int(kind_params.get("pad_y") or 0)
    fill = tuple(kind_params.get("fill") or (0, 0, 0, 140))
    radius = int(kind_params.get("radius") or 0)
    blur = int(kind_params.get("blur") or 0)

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    if shape == "full_width":
        y0 = max(0, y - pad_y)
        y1 = min(height, y + th + pad_y)
        ld.rectangle([0, y0, width, y1], fill=fill)
    elif shape == "lower_third":
        y0 = max(0, y - pad_y)
        y1 = min(height, y + th + pad_y + int(th * 0.85))
        x0 = max(0, x - pad_x)
        x1 = min(width, x + max(tw, int(width * 0.42)) + pad_x)
        ld.rectangle([x0, y0, x1, y1], fill=fill)
        if kind_params.get("accent_bar"):
            accent = (0, 220, 255, 255)
            ld.rectangle([x0, y0, x0 + 4, y1], fill=accent)
    elif shape == "rounded" or shape == "pill":
        box = [x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y]
        try:
            ld.rounded_rectangle(box, radius=max(4, radius), fill=fill)
        except Exception:
            ld.rectangle(box, fill=fill)
        if kind_params.get("accent_line"):
            accent = (0, 220, 255, 220)
            ly = y + th + max(4, pad_y // 3)
            ld.rectangle([x, ly, x + tw, ly + 2], fill=accent)
    elif shape == "gradient":
        ld.ellipse(
            [x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y],
            fill=fill,
        )
    else:  # ellipse scrim
        ld.ellipse(
            [x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y],
            fill=fill,
        )

    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))
    img = Image.alpha_composite(img, layer)
    return img, ImageDraw.Draw(img)


def _anchor_xy(
    width: int,
    height: int,
    tw: int,
    th: int,
    *,
    position_x: float,
    position_y: float,
    alignment: str,
    margin: int,
    safe_top: int | None = None,
    safe_bottom: int | None = None,
) -> tuple[int, int]:
    cx = int(width * float(position_x))
    cy = int(height * float(position_y))
    if alignment == "left":
        x = max(margin, cx)
    elif alignment == "right":
        x = min(width - margin - tw, cx - tw)
    else:
        x = cx - tw // 2
    y = cy - th // 2
    x = max(margin, min(x, width - margin - max(tw, 1)))
    top = int(height * 0.10) if safe_top is None else int(safe_top)
    bottom = int(height * 0.10) if safe_bottom is None else int(safe_bottom)
    # Documentary rule: prefer the lower third, but never leave the safe area.
    y_min = int(height * 0.70)
    y_max = height - th - bottom
    if y_max < y_min:
        y_min = max(top, height - th - bottom)
        y_max = max(y_min, height - th - bottom)
    y = max(y_min, min(y, y_max))
    y = max(top, min(y, height - th - bottom))
    x = max(margin, min(x, width - margin - max(tw, 1)))
    return x, y


def _render_text_overlay(
    spec: TextOverlaySpec,
    out_path: Path | str,
    width: int,
    height: int,
    *,
    design: DocumentaryDesignSystem,
    composition: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    from PIL import Image, ImageDraw, ImageFilter
    from .composition import max_lines_for_role

    text = (spec.text or "").strip()
    if not text:
        return None
    size_vh = float((spec.metadata or {}).get("size_vh") or design.size_vh_for(spec.role))
    # Scale is layout-only; composition already baked hierarchy into size_vh.
    start_size = max(16, int(height * size_vh))
    min_size = max(14, int(height * 0.026))
    max_width = int(width * 0.52)
    max_height = int(height * 0.16)
    max_lines = max_lines_for_role(spec.role)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    family = spec.font_family or design.font_body
    weight = spec.weight or "Bold"
    fontsize, font, lines, tw, th = _fit_fontsize(
        draw,
        text,
        load_font=_load_font,
        family=family,
        weight=weight,
        start_size=start_size,
        min_size=min_size,
        max_width=max_width,
        max_height=max_height,
        max_lines=max_lines,
    )
    display = "\n".join(lines)
    sec = (spec.secondary_text or "").strip()
    sec_font = None
    sec_h = 0
    if sec:
        sec_font = _load_font(design.font_ui, "Medium", max(12, int(fontsize * 0.45)))
        _, sec_h = _measure(draw, sec, sec_font)
        th = th + int(fontsize * 0.25) + sec_h
        tw = max(tw, _measure(draw, sec, sec_font)[0])

    margin = int(width * design.margin_x_ratio)
    x, y = _anchor_xy(
        width, height, tw, th,
        position_x=spec.position_x,
        position_y=spec.position_y,
        alignment=spec.alignment,
        margin=margin,
        safe_top=int(height * design.safe_top_ratio),
        safe_bottom=int(height * design.safe_bottom_ratio),
    )

    bg_kind = spec.background
    if composition:
        bg_kind = choose_background(
            role=spec.role, text=text, composition=composition, design=design
        )
    params = background_params(bg_kind, fontsize=fontsize, text_w=tw, text_h=th, design=design)
    img, draw = _draw_background(img, draw, params, x, y, tw, th - (sec_h if sec else 0), width, height)

    if spec.shadow and bg_kind != "NONE":
        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).multiline_text(
            (x, y + max(2, int(fontsize * 0.04))),
            display,
            font=font,
            fill=(0, 0, 0, 170),
            spacing=max(2, int(fontsize * 0.18)),
            align=spec.alignment or "center",
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(2.5, fontsize * 0.04)))
        img = Image.alpha_composite(img, shadow)
        draw = ImageDraw.Draw(img)

    draw.multiline_text(
        (x, y),
        display,
        font=font,
        fill=design.fill,
        spacing=max(2, int(fontsize * 0.18)),
        align=spec.alignment or "center",
    )
    if sec and sec_font is not None:
        sy = y + (th - sec_h)
        stx, _ = _measure(draw, sec, sec_font)
        sx = x if spec.alignment == "left" else x + (tw - stx) // 2
        draw.text((sx, sy), sec, font=sec_font, fill=design.fill_muted)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


def _render_statistic(
    spec: TextOverlaySpec,
    out_path: Path | str,
    width: int,
    height: int,
    *,
    design: DocumentaryDesignSystem,
    composition: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    from PIL import Image, ImageDraw, ImageFilter

    primary = (spec.text or "").strip()
    if not primary:
        return None
    label = (spec.secondary_text or "").strip().upper()
    big = bool((spec.metadata or {}).get("big_number"))        # a style's big centred number (Book of Enoch)
    size_vh = float((spec.metadata or {}).get("size_vh") or design.size_statistic)
    size_vh = min(size_vh, 0.26 if big else 0.078)
    fontsize = max(22, int(height * size_vh))
    max_width = int(width * (0.7 if big else 0.42))
    max_height = int(height * (0.32 if big else 0.14))
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fontsize, font, lines, tw, th = _fit_fontsize(
        draw,
        primary,
        load_font=_load_font,
        family=design.font_data,
        weight="Bold",
        start_size=fontsize,
        min_size=max(18, int(height * 0.032)),
        max_width=max_width,
        max_height=max_height,
        max_lines=2,
    )
    primary_display = "\n".join(lines)
    label_font = _load_font(design.font_ui, "SemiBold", max(12, int(fontsize * 0.28)))
    lw = lh = 0
    if label:
        lw, lh = _measure(draw, label, label_font)
    block_w = max(tw, lw)
    block_h = th + (int(fontsize * 0.35) + lh if label else 0)

    margin = int(width * design.margin_x_ratio)
    x, y = _anchor_xy(
        width, height, block_w, block_h,
        position_x=spec.position_x or 0.72,
        position_y=spec.position_y or 0.78,
        alignment=spec.alignment or "center",
        margin=margin,
        safe_top=int(height * design.safe_top_ratio),
        safe_bottom=int(height * design.safe_bottom_ratio),
    )
    # Center the number within the block.
    num_x = x + (block_w - tw) // 2

    bg_kind = spec.background or "PANEL"
    if composition and not big:
        bg_kind = choose_background(
            role="STATISTIC", text=primary, composition=composition,
            importance="high", design=design,
        )
    params = background_params(bg_kind, fontsize=fontsize, text_w=block_w, text_h=block_h, design=design)
    img, draw = _draw_background(img, draw, params, x, y, block_w, block_h, width, height)

    spacing = max(2, int(fontsize * 0.18))
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).multiline_text(
        (num_x, y + max(2, int(fontsize * 0.04))),
        primary_display,
        font=font,
        fill=(0, 0, 0, 180),
        spacing=spacing,
        align="center",
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(3.0, fontsize * 0.05)))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    draw.multiline_text(
        (num_x, y),
        primary_display,
        font=font,
        fill=design.fill,
        spacing=spacing,
        align="center",
    )
    if label:
        lx = x + (block_w - lw) // 2
        ly = y + th + int(fontsize * 0.18)
        draw.text((lx, ly), label, font=label_font, fill=design.fill_muted)
        # Underline accent
        if (spec.metadata or {}).get("underline", True):
            uy = ly + lh + max(4, int(fontsize * 0.06))
            draw.rectangle(
                [x + int(block_w * 0.1), uy, x + block_w - int(block_w * 0.1), uy + 2],
                fill=design.accent,
            )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


def _render_lower_third(
    spec: TextOverlaySpec,
    out_path: Path | str,
    width: int,
    height: int,
    *,
    design: DocumentaryDesignSystem,
) -> Optional[Path]:
    from PIL import Image, ImageDraw

    name = (spec.text or "").strip()
    if not name:
        return None
    title = (spec.secondary_text or "").strip()
    tertiary = (spec.tertiary_text or "").strip()

    name_vh = float((spec.metadata or {}).get("size_vh") or design.size_lower_third_name)
    name_vh = min(name_vh, 0.042)
    name_size = max(16, int(height * name_vh))
    role_size = max(12, int(height * design.size_lower_third_role))
    name_font = _load_font(design.font_ui, "Bold", name_size)
    role_font = _load_font(design.font_ui, "Medium", role_size)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    max_name_w = int(width * 0.50)
    name_size, name_font, name_lines, nw, nh = _fit_fontsize(
        draw,
        name,
        load_font=_load_font,
        family=design.font_ui,
        weight="Bold",
        start_size=name_size,
        min_size=max(14, int(height * 0.026)),
        max_width=max_name_w,
        max_height=int(height * 0.10),
        max_lines=2,
    )
    name_display = "\n".join(name_lines)
    rw = rh = 0
    if title:
        rw, rh = _measure(draw, title, role_font)
    tw = max(nw, rw, int(width * 0.28))
    th = nh + (int(name_size * 0.25) + rh if title else 0)
    if tertiary:
        th += int(role_size * 1.1)

    margin = int(width * design.margin_x_ratio)
    x = margin
    y = int(height * 0.78)
    y = min(y, height - th - int(height * design.safe_bottom_ratio))
    y = max(int(height * design.safe_top_ratio), y)

    params = background_params(
        "LOWER_THIRD", fontsize=name_size, text_w=tw, text_h=th, design=design
    )
    img, draw = _draw_background(img, draw, params, x, y, tw, th, width, height)

    draw.multiline_text(
        (x, y),
        name_display,
        font=name_font,
        fill=design.fill,
        spacing=max(2, int(name_size * 0.16)),
        align="left",
    )
    cy = y + nh + int(name_size * 0.18)
    if title:
        draw.text((x, cy), title, font=role_font, fill=design.fill_muted)
        cy += rh + int(role_size * 0.35)
    if tertiary:
        small = _load_font(design.font_ui, "Medium", max(12, int(role_size * 0.9)))
        draw.text((x, cy), tertiary, font=small, fill=design.fill_muted)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


# ---------------------------------------------------------------------------
# Countdown ("35 wild facts") templates — the reference style's look
# ---------------------------------------------------------------------------

_COUNTDOWN_FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Outfit-ExtraBold.ttf"
_COUNTDOWN_ORANGE = (246, 146, 30, 255)
_HOOK_YELLOW = (255, 222, 40, 255)
_HOOK_OUTLINE = (20, 20, 20, 255)


def _countdown_font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(str(_COUNTDOWN_FONT), size)
    except OSError:
        return ImageFont.load_default()


def _render_countdown_tag(text: str, out_path, width: int, height: int) -> Optional[Path]:
    """ "34. THE ROOF OF FLORIDA" — white bold capitals on an orange box,
    bottom-left, above where subtitles sit."""
    from PIL import Image, ImageDraw

    text = " ".join(str(text or "").upper().split())
    if not text:
        return None
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    size = max(14, int(height * 0.044))
    font = _countdown_font(size)
    max_w = int(width * 0.62)
    while size > 14 and draw.textlength(text, font=font) > max_w:
        size -= 2
        font = _countdown_font(size)
    pad_x, pad_y = int(size * 0.45), int(size * 0.22)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    box_w, box_h = (right - left) + 2 * pad_x, (bottom - top) + 2 * pad_y
    x0, y1 = int(width * 0.035), int(height * 0.845)
    y0 = y1 - box_h
    draw.rectangle([x0, y0, x0 + box_w, y1], fill=_COUNTDOWN_ORANGE)
    draw.text((x0 + pad_x - left, y0 + pad_y - top), text, font=font, fill=(255, 255, 255, 255))
    out_path = Path(out_path)
    img.save(out_path)
    return out_path


def _render_countdown_hook(text: str, out_path, width: int, height: int, *, size_frac: float = 0.10,
                           center_y: float = 0.5) -> Optional[Path]:
    """ "35 WILD FACTS" — big yellow capitals with a dark outline and shadow,
    centred (the reference's hook title). Keyword callouts ("345 FT ABOVE SEA
    LEVEL") use the same look a little smaller and higher."""
    from PIL import Image, ImageDraw, ImageFilter

    text = " ".join(str(text or "").upper().split())
    if not text:
        return None
    size = max(18, int(height * size_frac))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    font = _countdown_font(size)
    while size > 18 and probe.textlength(text, font=font) > width * 0.84:
        size -= 4
        font = _countdown_font(size)
    stroke = max(2, int(size * 0.07))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font, stroke_width=stroke)
    x = (width - (right - left)) // 2 - left
    y = int(height * center_y) - (bottom - top) // 2 - top
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x + int(size * 0.04), y + int(size * 0.06)), text, font=font,
                                fill=(0, 0, 0, 170), stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
    img = shadow.filter(ImageFilter.GaussianBlur(max(2, size // 14)))
    ImageDraw.Draw(img).text((x, y), text, font=font, fill=_HOOK_YELLOW, stroke_width=stroke, stroke_fill=_HOOK_OUTLINE)
    out_path = Path(out_path)
    img.save(out_path)
    return out_path
