"""Deterministic typography variation — anti-repetition style/position/animation.

No LLM. Scores semantic candidates against recent history so consecutive
effects do not reuse the same template look.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .placement import PLACEMENTS
from .styles import TYPOGRAPHY_STYLES, map_effect_to_style

# User-facing positions (subset + aliases map into PLACEMENTS).
VARIATION_POSITIONS = (
    "top_left",
    "top_center",
    "center",
    "bottom_center",
    "bottom_left",
    "bottom_right",
)

_ANIMATIONS = (
    "fade",
    "slide_fade",  # slide-up
    "slide_in",  # horizontal settle
    "scale_fade",  # punch
    "reveal",  # word / tracking-ish reveal
    "accent_wipe",  # treated as fade + accent emphasis at style level
)

_FACT_RE = re.compile(r"[\$€£]?\d[\d,\.]*%?")
_TECH_RE = re.compile(
    r"\b(ai|api|gpu|cpu|ml|llm|neural|algorithm|protocol|quantum|blockchain|"
    r"satellite|firmware|bandwidth|latency|dataset|model|chip|sensor)\b",
    re.I,
)
_QUOTE_RE = re.compile(r'^[\"“].+[\"”]$|^\'.+\'$')


@dataclass
class TypographyDecision:
    style_id: str
    placement: str
    animation: str
    semantic: str
    score: float
    raw_text: str = ""


@dataclass
class VariationHistory:
    """Rolling history of applied typography decisions (one render pass)."""

    decisions: List[TypographyDecision] = field(default_factory=list)
    max_keep: int = 8

    def record(self, decision: TypographyDecision) -> None:
        self.decisions.append(decision)
        if len(self.decisions) > self.max_keep:
            self.decisions = self.decisions[-self.max_keep :]

    def clear(self) -> None:
        self.decisions.clear()

    @property
    def previous(self) -> Optional[TypographyDecision]:
        return self.decisions[-1] if self.decisions else None

    def recent_styles(self, n: int = 3) -> List[str]:
        return [d.style_id for d in self.decisions[-n:]]

    def recent_placements(self, n: int = 3) -> List[str]:
        return [d.placement for d in self.decisions[-n:]]

    def recent_animations(self, n: int = 3) -> List[str]:
        return [d.animation for d in self.decisions[-n:]]

    def recent_combos(self, n: int = 4) -> List[Tuple[str, str]]:
        return [(d.style_id, d.placement) for d in self.decisions[-n:]]


_HISTORY = VariationHistory()


def get_variation_history() -> VariationHistory:
    return _HISTORY


def reset_variation_history() -> None:
    _HISTORY.clear()


def _stable_jitter(seed: str, amplitude: float = 2.5) -> float:
    """Tiny deterministic tie-break so equal scores do not always pick index 0."""
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return ((int(digest[:6], 16) / float(0xFFFFFF)) - 0.5) * 2.0 * amplitude


def classify_semantic(text: str, effect: str = "") -> str:
    """Lightweight semantic bucket for scoring (no LLM)."""
    text = (text or "").strip()
    effect = str(effect or "").lower().strip()
    words = text.split()
    n = len(words)
    if not text:
        return "empty"
    if "?" in text:
        return "question"
    if _FACT_RE.fullmatch(text) or (any(ch.isdigit() for ch in text) and n <= 3):
        return "fact"
    if _QUOTE_RE.match(text) or (text.startswith('"') and text.endswith('"')):
        return "quote"
    letters = [c for c in text if c.isalpha()]
    all_caps = bool(letters) and all(c.isupper() for c in letters)
    if all_caps and n <= 4:
        return "dramatic"
    if all_caps and n >= 5:
        return "conclusion"
    if effect in ("punch", "pop"):
        return "dramatic" if n <= 4 else "conclusion"
    if n >= 8 or (n >= 6 and text[-1:] in ".!"):
        return "long_narration"
    if n >= 5 and text[-1:] in ".!":
        return "long_narration"
    if _TECH_RE.search(text) and n <= 4:
        return "technical"
    if effect in ("highlight", "scale", "impact") and n <= 3:
        return "keyword" if n <= 2 else "statement"
    if effect == "rise" or (n <= 6 and n >= 3 and text[-1:] in ".!"):
        return "conclusion" if n >= 4 else "statement"
    if effect == "word_reveal":
        return "keyword" if n <= 4 else "statement"
    if effect == "fade" or n >= 6:
        return "long_narration" if n >= 6 else "narration"
    if n <= 2:
        return "keyword"
    if n <= 5:
        return "statement"
    return "narration"


def style_candidates(semantic: str, effect: str, text: str) -> List[Tuple[str, float]]:
    """(style_id, base_score) for this semantic situation."""
    primary = map_effect_to_style(effect, text)
    table: Dict[str, List[Tuple[str, float]]] = {
        "question": [("question", 100.0), ("statement", 55.0), ("minimal_caption", 40.0)],
        "fact": [("fact_number", 100.0), ("keyword_highlight", 50.0), ("kinetic_punch", 35.0)],
        "quote": [("quote", 100.0), ("statement", 60.0), ("minimal_caption", 45.0)],
        "dramatic": [("kinetic_punch", 100.0), ("statement", 70.0), ("keyword_highlight", 55.0)],
        "conclusion": [("statement", 100.0), ("kinetic_punch", 65.0), ("keyword_highlight", 45.0)],
        "long_narration": [("minimal_caption", 100.0), ("statement", 50.0), ("quote", 35.0)],
        "narration": [("minimal_caption", 95.0), ("statement", 55.0), ("keyword_highlight", 40.0)],
        "technical": [("keyword_highlight", 100.0), ("fact_number", 45.0), ("statement", 40.0)],
        "keyword": [("keyword_highlight", 100.0), ("word_reveal", 70.0), ("kinetic_punch", 50.0)],
        "statement": [("statement", 95.0), ("keyword_highlight", 60.0), ("minimal_caption", 45.0)],
        "empty": [("minimal_caption", 10.0)],
    }
    cands = list(table.get(semantic, [("keyword_highlight", 70.0), ("minimal_caption", 50.0)]))
    # Boost primary mapping if present.
    boosted = False
    out: List[Tuple[str, float]] = []
    for sid, score in cands:
        if sid not in TYPOGRAPHY_STYLES:
            continue
        if sid == primary:
            score += 12.0
            boosted = True
        out.append((sid, score))
    if primary in TYPOGRAPHY_STYLES and not boosted:
        out.append((primary, 88.0))
    # Dedup keep best score
    best: Dict[str, float] = {}
    for sid, score in out:
        best[sid] = max(best.get(sid, -1e9), score)
    return sorted(best.items(), key=lambda x: -x[1])


def placement_candidates(
    style_id: str,
    text: str,
    *,
    semantic: str,
    aspect: str = "landscape",
) -> List[Tuple[str, float]]:
    text = (text or "").strip()
    n = len(text.split())
    n_chars = len(text)
    long = n >= 7 or n_chars >= 36
    short = n <= 2 and n_chars <= 16

    if semantic == "question":
        base = [("center", 100.0), ("top_center", 85.0), ("bottom_center", 50.0)]
    elif semantic == "fact":
        base = [("center", 100.0), ("top_center", 80.0), ("top_left", 60.0)]
    elif semantic == "dramatic":
        base = [("center", 95.0), ("top_center", 70.0), ("bottom_center", 45.0)]
    elif long or style_id == "minimal_caption":
        base = [
            ("bottom_center", 100.0),
            ("bottom_left", 75.0),
            ("bottom_right", 75.0),
            ("center", 40.0),
        ]
    elif short or style_id == "keyword_highlight":
        base = [
            ("bottom_left", 90.0),
            ("bottom_right", 90.0),
            ("top_left", 70.0),
            ("top_center", 55.0),
            ("bottom_center", 50.0),
        ]
    elif style_id == "quote":
        base = [("bottom_center", 90.0), ("center", 80.0), ("bottom_left", 60.0)]
    else:
        base = [
            ("center", 80.0),
            ("bottom_center", 75.0),
            ("top_center", 60.0),
            ("bottom_left", 55.0),
            ("bottom_right", 55.0),
        ]

    if aspect == "vertical":
        remapped: List[Tuple[str, float]] = []
        for p, s in base:
            if p.endswith(("_left", "_right")):
                col = (
                    "bottom_center"
                    if p.startswith("bottom")
                    else ("top_center" if p.startswith("top") else "center")
                )
                remapped.append((col, s * 0.9))
            else:
                remapped.append((p, s))
        base = remapped

    best: Dict[str, float] = {}
    for p, s in base:
        if p in VARIATION_POSITIONS or p in PLACEMENTS:
            # Prefer the documented variation set; still allow PLACEMENTS.
            if p not in VARIATION_POSITIONS and p not in PLACEMENTS:
                continue
            best[p] = max(best.get(p, -1e9), s)
    return sorted(best.items(), key=lambda x: -x[1])


def animation_candidates(
    style_id: str,
    *,
    semantic: str,
    duration: float,
) -> List[Tuple[str, float]]:
    short = duration < 0.55
    long = duration >= 1.4
    by_style: Dict[str, List[Tuple[str, float]]] = {
        "kinetic_punch": [("scale_fade", 100.0), ("fade", 60.0), ("slide_in", 40.0)],
        "fact_number": [("scale_fade", 95.0), ("fade", 70.0), ("accent_wipe", 55.0)],
        "keyword_highlight": [
            ("fade", 90.0),
            ("slide_in", 85.0),
            ("slide_fade", 75.0),
            ("accent_wipe", 70.0),
        ],
        "question": [("fade", 95.0), ("slide_fade", 70.0), ("reveal", 55.0)],
        "statement": [("slide_fade", 95.0), ("fade", 75.0), ("slide_in", 65.0)],
        "minimal_caption": [("fade", 100.0), ("slide_fade", 55.0)],
        "word_reveal": [("reveal", 100.0), ("fade", 60.0), ("slide_in", 45.0)],
        "quote": [("fade", 90.0), ("slide_fade", 80.0), ("reveal", 50.0)],
        "proof_modern": [("scale_fade", 100.0), ("fade", 50.0)],
    }
    cands = list(by_style.get(style_id, [("fade", 80.0), ("slide_fade", 60.0)]))
    if semantic == "dramatic":
        cands = [("scale_fade", 100.0)] + cands
    # Duration shaping
    adjusted: List[Tuple[str, float]] = []
    for anim, score in cands:
        if short and anim in ("reveal", "slide_fade"):
            score -= 25.0
        if short and anim in ("fade", "scale_fade", "slide_in", "accent_wipe"):
            score += 10.0
        if long and anim == "fade":
            score += 8.0
        if long and anim == "scale_fade" and style_id == "minimal_caption":
            score -= 20.0
        adjusted.append((anim, score))
    best: Dict[str, float] = {}
    for a, s in adjusted:
        if a in _ANIMATIONS:
            best[a] = max(best.get(a, -1e9), s)
    return sorted(best.items(), key=lambda x: -x[1])


def _penalty_style(style_id: str, history: VariationHistory) -> float:
    penalty = 0.0
    recent = history.recent_styles(3)
    if recent and style_id == recent[-1]:
        penalty += 42.0
    if len(recent) >= 2 and style_id == recent[-2]:
        penalty += 28.0
    if len(recent) >= 3 and style_id == recent[-3]:
        penalty += 16.0
    # Frequency in last 5
    freq = sum(1 for s in history.recent_styles(5) if s == style_id)
    penalty += freq * 10.0
    return penalty


def _penalty_placement(placement: str, history: VariationHistory) -> float:
    penalty = 0.0
    recent = history.recent_placements(3)
    if recent and placement == recent[-1]:
        penalty += 38.0
    if len(recent) >= 2 and placement == recent[-2]:
        penalty += 22.0
    freq = sum(1 for p in history.recent_placements(5) if p == placement)
    penalty += freq * 9.0
    return penalty


def _penalty_animation(animation: str, history: VariationHistory) -> float:
    penalty = 0.0
    recent = history.recent_animations(3)
    if recent and animation == recent[-1]:
        penalty += 30.0
    if len(recent) >= 2 and animation == recent[-2]:
        penalty += 18.0
    freq = sum(1 for a in history.recent_animations(5) if a == animation)
    penalty += freq * 8.0
    return penalty


def _penalty_combo(style_id: str, placement: str, history: VariationHistory) -> float:
    combo = (style_id, placement)
    penalty = 0.0
    for prev in history.recent_combos(4):
        if prev == combo:
            penalty += 24.0
    return penalty


def plan_typography_decision(
    text: str,
    effect: str = "highlight",
    *,
    width: int = 1920,
    height: int = 1080,
    duration: float = 0.6,
    history: Optional[VariationHistory] = None,
    record: bool = True,
    composition: Optional[Dict[str, Any]] = None,
) -> TypographyDecision:
    """Score candidates and pick style + placement + animation (deterministic)."""
    history = history if history is not None else _HISTORY
    text = (text or "").strip()
    effect = str(effect or "highlight")
    semantic = classify_semantic(text, effect)
    aspect = "vertical" if height > width * 1.15 else ("landscape" if width > height * 1.15 else "square")

    # Proof mode short-circuit
    try:
        from .debug import typography_proof_enabled

        if typography_proof_enabled():
            decision = TypographyDecision(
                style_id="proof_modern",
                placement="top_left",
                animation="scale_fade",
                semantic=semantic,
                score=999.0,
                raw_text=text,
            )
            if record:
                history.record(decision)
            return decision
    except Exception:
        pass

    composition = dict(composition or {})
    preferred_placement = str(composition.get("prefer") or composition.get("placement") or "").strip()

    style_cands = style_candidates(semantic, effect, text)
    best_style = "minimal_caption"
    best_style_score = -1e9
    for sid, base in style_cands:
        score = base - _penalty_style(sid, history) + _stable_jitter(f"{text}|{sid}|style")
        if score > best_style_score:
            best_style_score = score
            best_style = sid

    place_cands = placement_candidates(best_style, text, semantic=semantic, aspect=aspect)
    if preferred_placement in PLACEMENTS:
        place_cands = [(preferred_placement, 120.0)] + place_cands

    best_place = "bottom_center"
    best_place_score = -1e9
    for place, base in place_cands:
        score = (
            base
            - _penalty_placement(place, history)
            - _penalty_combo(best_style, place, history)
            + _stable_jitter(f"{text}|{best_style}|{place}|pos")
        )
        if score > best_place_score:
            best_place_score = score
            best_place = place

    anim_cands = animation_candidates(best_style, semantic=semantic, duration=float(duration or 0.6))
    best_anim = "fade"
    best_anim_score = -1e9
    for anim, base in anim_cands:
        score = base - _penalty_animation(anim, history) + _stable_jitter(f"{text}|{anim}|anim")
        if score > best_anim_score:
            best_anim_score = score
            best_anim = anim

    # accent_wipe is a style cue — render treats it as fade motion
    render_anim = "fade" if best_anim == "accent_wipe" else best_anim

    total = best_style_score + best_place_score + best_anim_score
    decision = TypographyDecision(
        style_id=best_style,
        placement=best_place,
        animation=render_anim,
        semantic=semantic,
        score=total,
        raw_text=text,
    )
    # Stash accent_wipe flag on decision via animation name for params if needed
    if best_anim == "accent_wipe":
        decision.animation = "accent_wipe"
    if record:
        history.record(decision)
    return decision


def score_style_only(
    style_id: str,
    text: str,
    effect: str,
    history: Optional[VariationHistory] = None,
) -> float:
    """Test helper: net score for a style candidate given current history."""
    history = history if history is not None else _HISTORY
    semantic = classify_semantic(text, effect)
    base_map = dict(style_candidates(semantic, effect, text))
    base = base_map.get(style_id, 20.0)
    return base - _penalty_style(style_id, history)
