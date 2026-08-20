"""Typography style definitions + Smart Editing effect → style mapping."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from .theme import TypographyTheme, get_theme

# Style ids requested for the modern documentary layer.
TYPOGRAPHY_STYLE_IDS = (
    "kinetic_punch",
    "keyword_highlight",
    "statement",
    "question",
    "minimal_caption",
    "fact_number",
    "word_reveal",
    "quote",
    "proof_modern",
)

# Soft defaults from Smart Editing effect names — content rules may override.
# Detection / effect assignment stays unchanged; this is render-only.
EFFECT_TO_STYLE: Dict[str, str] = {
    "punch": "kinetic_punch",
    "pop": "kinetic_punch",
    "impact": "fact_number",
    "highlight": "keyword_highlight",
    "fade": "minimal_caption",
    "rise": "statement",
    "scale": "keyword_highlight",
    "word_reveal": "word_reveal",
}


@dataclass(frozen=True)
class TypographyStyle:
    id: str
    font_family: str
    weight: str
    # Font size as fraction of frame height.
    size_vh: float
    letter_spacing: float
    # Default placement hint (resolved further in placement.py).
    position: str
    # Motion: fade | scale_fade | slide_fade | reveal
    animation: str
    stroke_width: int
    # When True, short emphasis may render UPPERCASE (never blind-force long sentences).
    uppercase: bool = False
    accent_bar: bool = False
    backplate: bool = True
    max_chars_hard: int = 42


TYPOGRAPHY_STYLES: Dict[str, TypographyStyle] = {
    "kinetic_punch": TypographyStyle(
        id="kinetic_punch",
        font_family="Manrope",
        weight="ExtraBold",
        size_vh=0.072,
        letter_spacing=1.6,
        position="center",
        animation="scale_fade",
        stroke_width=4,
        uppercase=True,
        accent_bar=False,
        backplate=False,
        max_chars_hard=28,
    ),
    "keyword_highlight": TypographyStyle(
        id="keyword_highlight",
        font_family="Plus Jakarta Sans",
        weight="ExtraBold",
        size_vh=0.072,
        letter_spacing=1.0,
        position="bottom_center",
        animation="fade",
        stroke_width=4,
        uppercase=False,
        accent_bar=True,
        backplate=True,
        max_chars_hard=32,
    ),
    "statement": TypographyStyle(
        id="statement",
        font_family="Outfit",
        weight="Bold",
        size_vh=0.054,
        letter_spacing=0.4,
        position="center",
        animation="slide_fade",
        stroke_width=3,
        uppercase=False,
        accent_bar=False,
        backplate=True,
        max_chars_hard=48,
    ),
    "question": TypographyStyle(
        id="question",
        font_family="Inter",
        weight="SemiBold",
        size_vh=0.052,
        letter_spacing=0.3,
        position="center",
        animation="fade",
        stroke_width=3,
        uppercase=False,
        accent_bar=False,
        backplate=True,
        max_chars_hard=56,
    ),
    "minimal_caption": TypographyStyle(
        id="minimal_caption",
        font_family="DM Sans",
        weight="Medium",
        size_vh=0.038,
        letter_spacing=0.2,
        position="bottom_center",
        animation="fade",
        stroke_width=2,
        uppercase=False,
        accent_bar=False,
        backplate=True,
        max_chars_hard=64,
    ),
    "fact_number": TypographyStyle(
        id="fact_number",
        font_family="Space Grotesk",
        weight="Bold",
        size_vh=0.088,
        letter_spacing=1.8,
        position="top_right",
        animation="scale_fade",
        stroke_width=4,
        uppercase=False,
        accent_bar=True,
        backplate=True,
        max_chars_hard=18,
    ),
    "word_reveal": TypographyStyle(
        id="word_reveal",
        font_family="Inter",
        weight="Bold",
        size_vh=0.056,
        letter_spacing=0.6,
        position="bottom_center",
        animation="reveal",
        stroke_width=3,
        uppercase=False,
        accent_bar=False,
        backplate=True,
        max_chars_hard=36,
    ),
    "quote": TypographyStyle(
        id="quote",
        font_family="Outfit",
        weight="Bold",
        size_vh=0.048,
        letter_spacing=0.35,
        position="bottom_center",
        animation="slide_fade",
        stroke_width=3,
        uppercase=False,
        accent_bar=False,
        backplate=True,
        max_chars_hard=56,
    ),
    # Unmistakable verification style — VIDEOGEN_TYPOGRAPHY_PROOF=1 only.
    "proof_modern": TypographyStyle(
        id="proof_modern",
        font_family="Manrope",
        weight="ExtraBold",
        size_vh=0.11,
        letter_spacing=2.0,
        position="top_left",
        animation="scale_fade",
        stroke_width=5,
        uppercase=False,
        accent_bar=True,
        backplate=True,
        max_chars_hard=40,
    ),
}


_FACT_RE = re.compile(r"[\$€£]?\d[\d,\.]*%?")


def _is_all_caps_emphasis(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return False
    return all(c.isupper() for c in letters)


def _looks_like_sentence(text: str, n_words: int) -> bool:
    if n_words >= 7:
        return True
    if n_words >= 5 and text[-1:] in ".!":
        return True
    if n_words >= 6 and text[-1:] == "?":
        return True
    return False


def map_effect_to_style(
    effect: str,
    text: str = "",
    *,
    theme: Optional[TypographyTheme] = None,
) -> str:
    """Map a Smart Editing effect (+ content cues) to a typography style id.

    Priority: question → fact → all-caps punch/statement → length/effect rules.
    Prefers fewer high-impact styles over turning every line into a punch.
    """
    del theme  # reserved for future theme-driven overrides
    try:
        from .debug import typography_proof_enabled

        if typography_proof_enabled():
            return "proof_modern"
    except Exception:
        pass

    effect = str(effect or "highlight").lower().strip()
    text = (text or "").strip()
    words = text.split()
    n = len(words)
    all_caps = _is_all_caps_emphasis(text)

    # 1) Questions always read as questions.
    if "?" in text:
        return "question"

    # 1b) Quoted lines.
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return "quote"

    # 2) Stats / currency / percents.
    if _FACT_RE.fullmatch(text) or (
        effect == "impact" and any(ch.isdigit() for ch in text)
    ):
        return "fact_number"

    # 3) Word-by-word reveal — only for short beats; long copy becomes statement.
    if effect == "word_reveal":
        return "word_reveal" if n <= 5 else "statement"

    # 4) Source all-caps emphasis (script intentional shouting).
    if all_caps and n <= 4:
        return "kinetic_punch"
    if all_caps and n >= 5:
        return "statement"

    # 5) Full narration sentences stay quiet.
    if _looks_like_sentence(text, n):
        return "minimal_caption"

    # 6) Effect-aware short/mid phrases.
    if effect in ("punch", "pop"):
        return "kinetic_punch" if n <= 3 else "statement"
    if effect == "impact":
        return "keyword_highlight"
    if effect == "rise":
        return "statement"
    if effect == "fade":
        return "minimal_caption"
    if effect in ("highlight", "scale"):
        if n <= 3:
            return "keyword_highlight"
        if n <= 6:
            return "statement"
        return "minimal_caption"

    # 7) Soft fallback from EFFECT_TO_STYLE, then length.
    style_id = EFFECT_TO_STYLE.get(effect, "")
    if style_id in TYPOGRAPHY_STYLES and not _looks_like_sentence(text, n):
        if style_id == "kinetic_punch" and n > 3:
            return "statement"
        return style_id
    if n <= 2:
        return "keyword_highlight"
    if n <= 5:
        return "statement"
    return "minimal_caption"


def casing_mode_for_style(style_id: str, raw_text: str, *, uppercase_flag: bool) -> str:
    """Decide display casing without destroying natural narration."""
    text = (raw_text or "").strip()
    words = text.split()
    n = len(words)
    all_caps = _is_all_caps_emphasis(text)

    if style_id == "kinetic_punch" and uppercase_flag and n <= 4:
        return "upper"
    if style_id == "statement" and all_caps and n <= 10:
        # Keep intentional all-caps dramatic statements.
        return "upper"
    if style_id == "fact_number":
        return "preserve"
    if style_id in ("keyword_highlight", "word_reveal") and n <= 3 and not _looks_like_sentence(text, n):
        return "title"
    # Questions, captions, quotes, long statements: natural sentence casing.
    return "sentence"


def get_style(style_id: str, theme: Optional[TypographyTheme] = None) -> TypographyStyle:
    theme = theme or get_theme()
    base = TYPOGRAPHY_STYLES.get(style_id) or TYPOGRAPHY_STYLES["keyword_highlight"]
    overrides = (theme.style_overrides or {}).get(style_id) or {}
    if not overrides:
        return base
    data = asdict(base)
    data.update({k: v for k, v in overrides.items() if k in data})
    return TypographyStyle(**data)


def style_dict(style: TypographyStyle) -> Dict[str, Any]:
    return deepcopy(asdict(style))
