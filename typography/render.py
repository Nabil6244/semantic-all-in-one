"""Render helpers: drawtext filter params + Pillow overlays for typography styles."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .fonts import resolve_font_path
from .placement import compute_xy, drawtext_x_expr, resolve_placement
from .styles import casing_mode_for_style, get_style, style_dict
from .theme import TypographyTheme, get_theme

# Single filler tokens look amateur as hero overlays — skip at render only.
_WEAK_SINGLE_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at",
        "by", "for", "from", "with", "as", "is", "are", "was", "were", "be", "been",
        "being", "it", "its", "this", "that", "these", "those", "we", "you", "they",
        "he", "she", "i", "me", "my", "our", "your", "their", "into", "onto", "upon",
        "about", "over", "under", "again", "then", "than", "so", "just", "also",
        "very", "really", "even", "still", "through", "across", "between", "among",
        "while", "when", "where", "what", "which", "who", "whom", "how", "why",
        "can", "could", "should", "would", "will", "shall", "may", "might", "must",
        "do", "does", "did", "done", "have", "has", "had", "not", "no", "yes",
        "every", "single", "one", "two", "all", "any", "some", "more", "most",
        "such", "only", "own", "same", "other", "another", "each", "few", "both",
    }
)
_SMALL_TITLE_WORDS = frozenset(
    {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by", "from", "as"}
)


def _escape_drawtext(text: str) -> str:
    escaped = (text or "").replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return escaped.replace("%", "\\%")


def _escape_filter_expr(expr: str) -> str:
    return (expr or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def _escape_fontfile(path: str) -> str:
    return (
        (path or "")
        .replace("\\", "/")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
    )


def _capitalize_word(raw: str) -> str:
    chars = list(raw)
    for j, ch in enumerate(chars):
        if ch.isalpha():
            chars[j] = ch.upper()
            for k in range(j + 1, len(chars)):
                if chars[k].isalpha():
                    chars[k] = chars[k].lower()
            break
    return "".join(chars)


def format_display_text(text: str, *, casing: str = "sentence", uppercase: bool = False) -> str:
    """Style-aware display casing. Source text stays separate from presentation.

    casing:
      - sentence: natural narration ("Technology is changing…")
      - title: short keyword Title Case
      - upper: emphasis uppercase
      - preserve: keep numbers / mixed tokens mostly as-is
    """
    text = (text or "").strip()
    if not text:
        return ""
    if uppercase or casing == "upper":
        return text.upper()

    # Keep short ALL-CAPS tokens (AI, NASA, GDP) when preserve/title.
    if text.isupper() and 1 < len(text) <= 8 and " " not in text and casing != "sentence":
        return text
    if re.fullmatch(r"[\$€£]?\d[\d,\.]*%?", text):
        return text

    if casing == "preserve":
        # If whisper dumped lowercase, still sentence-case once.
        if text.lower() == text:
            return format_display_text(text, casing="sentence")
        return text

    words = text.split()
    if casing == "title":
        out: List[str] = []
        for i, word in enumerate(words):
            letters = "".join(ch for ch in word if ch.isalpha())
            if letters and any(ch.isupper() for ch in letters[1:]) and any(ch.islower() for ch in letters):
                out.append(word[0].upper() + word[1:] if word[0].islower() else word)
                continue
            core = re.sub(r"[^a-zA-Z']+", "", word).lower()
            if i > 0 and core in _SMALL_TITLE_WORDS:
                out.append(word.lower() if word.isalpha() else word)
            else:
                out.append(_capitalize_word(word))
        return " ".join(out)

    # Sentence casing — first letter capital; rest lower unless acronym-like token.
    out = []
    for i, word in enumerate(words):
        letters = "".join(ch for ch in word if ch.isalpha())
        if letters and letters.isupper() and 1 < len(letters) <= 5:
            out.append(word)  # keep AI / NASA mid-sentence
            continue
        if letters and any(ch.isupper() for ch in letters[1:]) and any(ch.islower() for ch in letters):
            # Preserve camel / brand casing; ensure leading capital if first word.
            if i == 0 and word and word[0].islower():
                out.append(word[0].upper() + word[1:])
            else:
                out.append(word)
            continue
        if i == 0:
            out.append(_capitalize_word(word))
        else:
            # Normalize whisper ALLCAPS / mixed into readable sentence words.
            out.append(word.lower() if letters else word)
    return " ".join(out)


def _is_weak_overlay_text(text: str) -> bool:
    words = (text or "").strip().split()
    if len(words) != 1:
        return False
    token = re.sub(r"[^a-zA-Z']+", "", words[0]).lower()
    return token in _WEAK_SINGLE_WORDS


def _prepare_text(raw_text: str, style_id: str, uppercase_flag: bool, max_chars: int) -> str:
    mode = casing_mode_for_style(style_id, raw_text, uppercase_flag=uppercase_flag)
    text = format_display_text(raw_text, casing=mode)
    if not text or _is_weak_overlay_text(text):
        return ""
    if max_chars > 0 and len(text) > max_chars:
        text = text[: max(1, max_chars - 1)].rstrip() + "…"
    return text


def _font_size(height: int, size_vh: float, intensity: float, theme: TypographyTheme) -> int:
    boost = 1.0 + max(0.0, min(1.0, intensity) - 0.5) * theme.intensity_size_boost * 2
    return max(20, int(round(height * size_vh * boost)))


def _alpha_expr(t0: float, t1: float, fade_in: float, fade_out: float, animation: str) -> str:
    """Smooth fade in/out (no bounce)."""
    fi = fade_in * (1.15 if animation == "reveal" else 1.0)
    fo = fade_out
    hold_end = max(t0 + fi + 0.04, t1 - fo)
    fade_in_end = round(t0 + fi, 3)
    fade_out_start = round(hold_end, 3)
    return (
        f"if(lt(t,{t0:.3f}),0,"
        f"if(lt(t,{fade_in_end}),(t-{t0:.3f})/{fi:.3f},"
        f"if(lt(t,{fade_out_start}),1,"
        f"if(lt(t,{t1:.3f}),({t1:.3f}-t)/{fo:.3f},0))))"
    )


def _y_expr(base_y: int, t0: float, animation: str, theme: TypographyTheme) -> str:
    if animation not in ("slide_fade", "reveal", "slide_in"):
        return str(base_y)
    slide = theme.slide_px
    fi = theme.fade_in
    # slide_in settles vertically less; still a soft rise for readability.
    amount = slide * (0.65 if animation == "slide_in" else 1.0)
    return (
        f"if(lt(t,{t0:.3f}+{fi:.3f}),"
        f"{base_y}+{amount:.1f}*(1-(t-{t0:.3f})/{fi:.3f}),"
        f"{base_y})"
    )


def _composition_from_fx(fx: dict) -> Dict[str, Any]:
    raw = fx.get("composition") or fx.get("scene_composition") or {}
    if isinstance(raw, dict):
        return raw
    return {}


def typography_params_for_effect(
    fx: dict,
    width: int,
    height: int,
    *,
    theme: Optional[TypographyTheme] = None,
    record_history: bool = True,
) -> Dict[str, Any]:
    """Pure parameter generation for one Smart Editing text effect event."""
    from .variation import plan_typography_decision

    theme = theme or get_theme()
    effect = str(fx.get("effect") or "highlight")
    raw_text = str(fx.get("text") or "")
    intensity = float(fx.get("intensity") or 0.65)
    t0 = float(fx.get("local_start") or 0.0)
    t1 = float(fx.get("local_end") or t0 + 0.3)
    if t1 <= t0:
        t1 = t0 + 0.12
    duration = float(fx.get("scene_duration") or (t1 - t0) or 0.6)

    decision = plan_typography_decision(
        raw_text,
        effect,
        width=width,
        height=height,
        duration=duration,
        record=record_history,
        composition=_composition_from_fx(fx),
    )
    style_id = decision.style_id
    style = get_style(style_id, theme=theme)
    text = _prepare_text(raw_text, style.id, style.uppercase, style.max_chars_hard)
    fontsize = _font_size(height, style.size_vh, intensity, theme)
    nchars = len(text.replace(" ", ""))
    if nchars <= 6 and style.id in ("kinetic_punch", "fact_number", "keyword_highlight"):
        fontsize = int(fontsize * 1.12)
    elif len(text) >= 36:
        fontsize = int(fontsize * 0.88)
    if style.id == "minimal_caption":
        fontsize = min(fontsize, int(height * 0.045))

    # Animation from variation planner (accent_wipe → fade motion + accent).
    animation = decision.animation
    accent_wipe = animation == "accent_wipe"
    if accent_wipe:
        animation = "fade"

    placement = resolve_placement(
        style.id,
        text or raw_text,
        width,
        height,
        fontsize=fontsize,
        theme=theme,
        composition=_composition_from_fx(fx),
        effect=effect,
        forced_placement=decision.placement,
    )
    y_base = int(height * float(placement["anchor_y_ratio"]))
    font_path = resolve_font_path(style.font_family, style.weight)
    margin_x = int(width * theme.margin_x_ratio)
    accent_bar = bool(style.accent_bar or accent_wipe)
    return {
        "style_id": style_id,
        "style": style_dict(style),
        "text": text,
        "raw_text": raw_text,
        "effect": effect,
        "semantic": decision.semantic,
        "local_start": t0,
        "local_end": t1,
        "fontsize": fontsize,
        "letter_spacing": style.letter_spacing,
        "stroke_width": style.stroke_width,
        "animation": animation,
        "accent_bar": accent_bar,
        "backplate": style.backplate or accent_wipe,
        "placement": placement["placement"],
        "placement_info": placement,
        "x_align": placement["x_align"],
        "y": y_base,
        "font_path": font_path,
        "font_family": style.font_family,
        "weight": style.weight,
        "margin_x": margin_x,
        "fill": theme.fill,
        "stroke": theme.stroke,
        "accent": theme.accent,
        "fade_in": theme.fade_in,
        "fade_out": theme.fade_out,
        "slide_px": theme.slide_px,
        "scale_from": theme.scale_from,
        "width": width,
        "height": height,
        "intensity": intensity,
        "decision_score": decision.score,
    }


def build_drawtext_filters(
    effects: Sequence[dict],
    width: int,
    height: int,
    *,
    theme: Optional[TypographyTheme] = None,
) -> str:
    """Build an ffmpeg drawtext chain from Smart Editing local text effects."""
    from .variation import reset_variation_history

    theme = theme or get_theme()
    reset_variation_history()
    filters: List[str] = []
    for fx in effects:
        params = typography_params_for_effect(fx, width, height, theme=theme)
        text = _escape_drawtext(params["text"])
        if not text:
            continue
        t0 = params["local_start"]
        t1 = params["local_end"]
        alpha = _escape_filter_expr(
            _alpha_expr(t0, t1, params["fade_in"], params["fade_out"], params["animation"])
        )
        # drawtext y is top of glyphs — nudge up from center anchor.
        y_top = max(0, int(params["y"] - params["fontsize"] * 0.55))
        y_raw = _y_expr(y_top, t0, params["animation"], theme)
        y_expr = _escape_filter_expr(y_raw) if "if(" in str(y_raw) else str(y_raw)
        fontsize = params["fontsize"]
        if params["animation"] == "scale_fade":
            sf = params["scale_from"]
            fi = params["fade_in"]
            fontsize_expr = _escape_filter_expr(
                f"if(lt(t,{t0:.3f}+{fi:.3f}),"
                f"{fontsize}*({sf:.3f}+(1-{sf:.3f})*(t-{t0:.3f})/{fi:.3f}),"
                f"{fontsize})"
            )
        else:
            fontsize_expr = str(fontsize)

        x_expr = drawtext_x_expr(params["placement_info"], params["margin_x"])
        parts = [
            f"text='{text}'",
            f"enable='between(t\\,{t0:.3f}\\,{t1:.3f})'",
            f"fontsize={fontsize_expr}",
            f"fontcolor=white@({alpha})",
            f"borderw={int(params['stroke_width'])}",
            "bordercolor=black@0.85",
            f"letter_spacing={float(params['letter_spacing']):.2f}",
            f"x={x_expr}",
            f"y={y_expr}",
        ]
        if params["font_path"]:
            parts.insert(1, f"fontfile={_escape_fontfile(params['font_path'])}")
        if params["backplate"] or params["accent_bar"]:
            parts.append("box=1")
            parts.append("boxborderw=16" if params["accent_bar"] else "boxborderw=12")
            parts.append("boxcolor=black@0.40" if params["accent_bar"] else "boxcolor=black@0.32")
        filters.append("drawtext=" + ":".join(parts))
    return ",".join(filters)


def _load_pil_font(font_path: Optional[str], size: int):
    from PIL import ImageFont

    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            pass
    from .fonts import FontRegistry

    for candidate in FontRegistry().candidates("Inter", "Bold"):
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_tracking_text(draw, xy, text: str, font, fill, stroke_width: int, stroke_fill, tracking: float):
    x, y = xy
    if tracking <= 0:
        draw.text(
            (x, y),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        return
    for ch in text:
        draw.text(
            (x, y),
            ch,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        bbox = draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_width)
        x += (bbox[2] - bbox[0]) + tracking


def _measure_tracking(draw, text: str, font, stroke_width: int, tracking: float) -> tuple[int, int]:
    if not text:
        return 0, 0
    if tracking <= 0:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    total_w = 0
    max_h = 0
    for i, ch in enumerate(text):
        bbox = draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_width)
        total_w += bbox[2] - bbox[0]
        if i < len(text) - 1:
            total_w += tracking
        max_h = max(max_h, bbox[3] - bbox[1])
    return int(total_w), int(max_h)


def render_style_overlay(
    fx: dict,
    out_path: Path | str,
    width: int,
    height: int,
    *,
    theme: Optional[TypographyTheme] = None,
    params: Optional[Dict[str, Any]] = None,
    record_history: bool = True,
) -> Optional[Path]:
    """Render one styled transparent PNG for ffmpeg timed overlay (no drawtext needed)."""
    theme = theme or get_theme()
    if params is None:
        params = typography_params_for_effect(
            fx, width, height, theme=theme, record_history=record_history
        )
    text = params["text"]
    if not text:
        return None

    from PIL import Image, ImageDraw, ImageFilter

    font = _load_pil_font(params["font_path"], params["fontsize"])
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tracking = float(params["letter_spacing"])
    stroke_w = max(1, int(params["stroke_width"]))
    tw, th = _measure_tracking(draw, text, font, stroke_w, tracking)
    x, y = compute_xy(
        params["placement_info"],
        width,
        height,
        tw,
        th,
        params["margin_x"],
    )

    pad_x = max(18, int(params["fontsize"] * 0.36))
    pad_y = max(10, int(params["fontsize"] * 0.24))
    plate = [x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y]

    use_plate = bool(params["backplate"] or params["accent_bar"])
    # Long lines always get a soft plate for readability.
    if len(text) >= 24:
        use_plate = True
    if use_plate:
        # Strong enough to read on dark cinematic footage.
        plate_alpha = 175 if params["accent_bar"] else 140
        if params["style_id"] == "minimal_caption":
            plate_alpha = 120
        if params["style_id"] == "proof_modern":
            plate_alpha = 200
        draw.rounded_rectangle(
            plate,
            radius=max(8, int(params["fontsize"] * 0.16)),
            fill=(0, 0, 0, plate_alpha),
        )

    if params["accent_bar"]:
        ay = plate[3] - 5
        accent = params["accent"]
        thickness = 5 if params["style_id"] == "proof_modern" else 4
        draw.rounded_rectangle(
            [plate[0] + 10, ay, plate[2] - 10, ay + thickness],
            radius=2,
            fill=(accent[0], accent[1], accent[2], 255),
        )

    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    _draw_tracking_text(
        sdraw,
        (x + 2, y + 3),
        text,
        font,
        fill=(0, 0, 0, 130),
        stroke_width=0,
        stroke_fill=(0, 0, 0, 0),
        tracking=tracking,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=1.1))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    _draw_tracking_text(
        draw,
        (x, y),
        text,
        font,
        fill=params["fill"],
        stroke_width=stroke_w,
        stroke_fill=params["stroke"],
        tracking=tracking,
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path
