"""Narration importance vs visual opportunity (deterministic heuristics)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from visual_director.schema import VisualScene

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_GENERIC_STOCK_RE = re.compile(
    r"\b(cinematic\s+footage(\s+of)?|stock\s+footage(\s+of)?|generic\s+shot\s+of|"
    r"beautiful\s+shot\s+of|epic\s+footage(\s+of)?)\b",
    re.I,
)

_HIGH_NARR = frozenset({
    "because", "therefore", "however", "critical", "crucial", "essential",
    "secret", "truth", "reveal", "finally", "never", "always", "must",
    "warning", "danger", "breakthrough", "discovery", "evidence", "proof",
})
_HIGH_VISUAL = frozenset({
    "see", "look", "watch", "show", "appears", "emerges", "explodes",
    "crashes", "launches", "builds", "rises", "falls", "burns", "floods",
    "crowd", "skyline", "factory", "machine", "map", "chart", "planet",
    "ocean", "mountain", "face", "hands", "weapon", "ship", "city",
})
_GENERIC = frozenset({
    "thing", "things", "stuff", "someone", "something", "people", "way",
    "world", "life", "time", "today", "really", "just", "very", "important",
    "cinematic", "footage", "beautiful", "epic", "amazing", "stunning",
})
_META_SUBJECT = frozenset({
    "show", "shows", "showing", "footage", "video", "clip", "shot", "image",
    "visual", "scene", "cinematic", "documentary", "idea", "concept", "support",
})
_SPECIFIC_HINTS = frozenset({
    "named", "called", "located", "built", "founded", "percent", "million",
    "billion", "year", "century", "street", "river", "company", "president",
})

# High-value opportunity families
_TAG_PATTERNS: List[Tuple[str, Tuple[str, ...]]] = [
    ("statistic", ("percent", "%", "million", "billion", "trillion", "rate", "average", "number")),
    ("reveal", ("reveal", "secret", "truth", "finally", "actually", "twist", "uncover", "hidden")),
    ("important_object", ("device", "machine", "document", "artifact", "weapon", "engine", "product", "tool")),
    ("human_consequence", ("worker", "family", "child", "victim", "patient", "refugee", "crowd", "people")),
    ("dramatic_action", ("explodes", "crashes", "launches", "collapses", "attacks", "floods", "burns", "erupts")),
    ("unusual_scale", ("massive", "tiny", "enormous", "vast", "microscopic", "planet", "molecule", "skyscraper")),
    ("important_location", ("city", "capital", "border", "factory", "hospital", "battlefield", "ocean", "river")),
    ("historical_evidence", ("archive", "photograph", "footage", "recorded", "194", "195", "196", "197", "198", "199", "20th")),
]


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def importance_label_score(label: str) -> float:
    key = (label or "medium").strip().lower()
    if key == "high":
        return 0.85
    if key == "low":
        return 0.3
    return 0.55


def detect_opportunity_tags(*parts: str) -> List[str]:
    blob = " ".join(p for p in parts if p).lower()
    toks = _tokens(blob)
    tags: List[str] = []
    for tag, keys in _TAG_PATTERNS:
        if any(k in blob or k in toks for k in keys):
            tags.append(tag)
    if any(ch.isdigit() for ch in blob) and "statistic" not in tags:
        # Digits often signal measurable claims
        if any(w in blob for w in ("percent", "%", "million", "billion", "times", "fold")):
            tags.append("statistic")
    return tags


def idea_count(text: str) -> int:
    """Approximate distinct ideas in a narration span (not a fixed-seconds rule)."""
    raw = (text or "").strip()
    if not raw:
        return 1
    # Clause-ish splits
    parts = re.split(r"[.;:!?]|(?:\s+(?:and then|but then|however|meanwhile|while)\s+)", raw, flags=re.I)
    clauses = [p.strip() for p in parts if p and len(p.strip().split()) >= 4]
    n = max(1, len(clauses))
    # Extra idea if multiple numbers / distinct concrete nouns density is high
    if len(re.findall(r"\d", raw)) >= 2:
        n += 1
    return min(5, n)


def narrative_importance(scene: VisualScene) -> float:
    base = importance_label_score(scene.importance)
    toks = _tokens(scene.narration)
    tags = detect_opportunity_tags(scene.narration, scene.visual_goal)
    bonus = 0.0
    if toks & _HIGH_NARR:
        bonus += 0.12
    if len(scene.narration.split()) >= 28:
        bonus += 0.05
    if any(ch.isdigit() for ch in scene.narration):
        bonus += 0.06
    if "reveal" in tags:
        bonus += 0.1
    if "statistic" in tags:
        bonus += 0.08
    if "human_consequence" in tags:
        bonus += 0.06
    return round(min(1.0, base + bonus), 3)


def visual_opportunity(
    scene: VisualScene,
    *,
    duration: float = 0.0,
    speech_density: float = 0.0,
) -> float:
    """How much visual payoff the narration can support — separate from narrative importance."""
    blob = f"{scene.narration} {scene.visual_goal} {scene.visual_description}".lower()
    toks = _tokens(blob)
    tags = detect_opportunity_tags(scene.narration, scene.visual_goal, scene.visual_description)
    score = 0.4
    if toks & _HIGH_VISUAL:
        score += 0.18
    if toks & _SPECIFIC_HINTS:
        score += 0.12
    if toks & _GENERIC and not (toks & _SPECIFIC_HINTS):
        score -= 0.12
    if _GENERIC_STOCK_RE.search(blob):
        score -= 0.1
    # Concrete visual description from Script Analyzer
    desc_words = len((scene.visual_description or "").split())
    if desc_words >= 8:
        score += 0.1
    if desc_words <= 3:
        score -= 0.08
    # Tag boosts — high-value narration classes
    tag_boost = {
        "reveal": 0.16,
        "dramatic_action": 0.14,
        "statistic": 0.12,
        "unusual_scale": 0.12,
        "important_object": 0.1,
        "human_consequence": 0.12,
        "important_location": 0.08,
        "historical_evidence": 0.1,
    }
    for tag in tags:
        score += tag_boost.get(tag, 0.0)
    # Longer beats with moderate density = room for strong coverage
    if duration >= 5.0:
        score += 0.08
    if duration >= 8.0:
        score += 0.06
    if speech_density > 4.2:
        score -= 0.05
    if (scene.importance or "").lower() == "high":
        score += 0.05
    return round(max(0.05, min(1.0, score)), 3)


def subject_from_text(*parts: str) -> str:
    blob = " ".join(p for p in parts if p).strip()
    cleaned = _GENERIC_STOCK_RE.sub(" ", blob)
    words = [
        w for w in _TOKEN_RE.findall(cleaned.lower())
        if len(w) > 3 and w not in _GENERIC and w not in _META_SUBJECT
    ]
    if not words:
        return "subject"
    return words[0]


def location_from_text(*parts: str) -> str:
    blob = " ".join(p for p in parts if p).lower()
    loc_keys = (
        "city", "street", "factory", "ocean", "river", "border", "hospital",
        "capital", "battlefield", "valley", "mountain", "harbor", "desert",
        "forest", "island", "station", "lab", "laboratory", "court", "prison",
    )
    toks = _tokens(blob)
    for key in loc_keys:
        if key in toks or key in blob:
            return key
    return ""


def meaningful_action_from_text(*parts: str) -> str:
    blob = " ".join(p for p in parts if p).lower()
    actions = (
        "launch", "explode", "crash", "build", "assemble", "collapse", "flood",
        "burn", "rise", "fall", "march", "fight", "open", "close", "reveal",
        "operate", "ignite", "evacuate", "sign", "testify",
    )
    for a in actions:
        if a in blob or f"{a}s" in blob or f"{a}ing" in blob or f"{a}ed" in blob:
            return a
    return ""


def generic_risk_score(scene: Optional[VisualScene], subject: str, description: str = "") -> float:
    blob = f"{subject} {description} {(scene.narration if scene else '')}"
    toks = _tokens(blob)
    risk = 0.25
    if toks & _GENERIC:
        risk += 0.25
    if not (toks & (_HIGH_VISUAL | _SPECIFIC_HINTS)):
        risk += 0.2
    if len(toks) < 4:
        risk += 0.15
    if _GENERIC_STOCK_RE.search(blob):
        risk += 0.25
    if subject in ("subject", "people", "world", "thing"):
        risk += 0.2
    return round(min(1.0, risk), 3)


def specificity_score(description: str, subject: str) -> float:
    toks = _tokens(f"{description} {subject}")
    score = 0.35
    if toks & _SPECIFIC_HINTS:
        score += 0.25
    if any(ch.isdigit() for ch in (description or "")):
        score += 0.15
    if len(toks) >= 6:
        score += 0.15
    if toks & _GENERIC and len(toks) < 5:
        score -= 0.2
    if _GENERIC_STOCK_RE.search(description or ""):
        score -= 0.2
    return round(max(0.05, min(1.0, score)), 3)


def strip_generic_stock_language(text: str) -> str:
    cleaned = _GENERIC_STOCK_RE.sub("", text or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")


def quality_requirements(
    *,
    subject: str,
    action: str,
    evidence: str,
    motion: str,
    specificity: float,
    generic_risk: float,
    repetition_risk: float,
    strong: bool,
    tags: List[str],
    editability: str,
) -> Dict:
    """Compact quality contract for Claude — concrete, not 'cinematic footage of X'."""
    req = {
        "specific_subject": subject if subject and subject != "subject" else "concrete_named_subject",
        "meaningful_action": action or "observable_change_or_state",
        "useful_motion": motion if motion not in ("", "static") else "prefer_motivated_motion_or_hold",
        "strong_evidence": evidence,
        "editability": editability,
        "max_generic_stock_risk": round(max(0.15, 0.55 - (0.2 if strong else 0.0)), 2),
        "max_repetition_risk": round(max(0.2, 0.6 - (0.15 if strong else 0.0)), 2),
        "forbid_generic_phrasing": True,
        "prefer_tags": list(tags)[:4],
    }
    if generic_risk >= 0.55:
        req["note"] = "reject_decorative_filler"
    if specificity < 0.45:
        req["note"] = "increase_subject_specificity"
    return req


def editability_for(strategy: str, motion: str, tags: List[str]) -> str:
    if strategy in ("punch_in", "multi_shot", "image_motion"):
        return "high"
    if "dramatic_action" in tags or "reveal" in tags:
        return "high"
    if motion in ("push_in", "orbit", "handheld"):
        return "high"
    if strategy == "hold" or motion == "static":
        return "medium"
    return "medium"
