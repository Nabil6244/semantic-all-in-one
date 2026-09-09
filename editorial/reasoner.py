"""AI Editorial Director — semantic editorial reasoning layer.

Modes:
  AI_ENABLED   — Gemini (or injected LLM) produces EditorialIntent batches
  AI_DISABLED  — skipped; deterministic engine unchanged
  AI_FALLBACK  — invalid/low-confidence/error → deterministic heuristics

The reasoner never touches FFmpeg, clip ranges, or timeline math. It only
emits soft EditorialIntent that ShotPlanner / event planners may bias on.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence

from .complements import AssetCandidate
from .intent import (
    CONF_LOW,
    CONF_MEDIUM,
    REASONER_VERSION,
    EditorialIntent,
)
from .schema import EditorialPlan, EditorialScene

SYSTEM_PROMPT = """You are the Editorial Director for a documentary video editor.
For each narration beat, decide what the viewer should see, hear, and understand.
You do NOT cut video, pick frame ranges, or write FFmpeg. You only return editorial intent.

Rules:
- Prefer evidence (documents, charts, news, maps, real footage) for factual claims.
- Prefer atmosphere/illustration for emotional or reflective lines.
- Prefer process / cause→effect sequences when narration explains a relationship.
- Do NOT recommend text or SFX for ordinary lines — only when genuinely useful.
- Do NOT create reveals for ordinary sentences.
- Prefer multi/dual shots only when they improve comprehension or variety.
- Use ONLY candidate asset ids provided; never invent filenames.
- Consider previous and next beats so reveals/withholds stay intentional.
- Vary emotional_state across the film; avoid one flat mood.

Return ONLY valid JSON:
{"intents":[{
  "scene_number":"1",
  "visual_role":"process|evidence|explanation|geography|person|object|scale|comparison|historical|atmosphere|reveal|consequence|cause_effect|data|document|metaphor|context",
  "visual_strategy":"single|process_sequence|cause_effect|evidence|atmosphere|reveal|comparison|scale_progression|illustration",
  "evidence_level":"none|low|medium|high",
  "shot_strategy":"auto|single|multi|dual",
  "pacing":"hold|normal|build|fast|impact|reflective|reset",
  "reveal":false,
  "reveal_phase":"none|setup|build|withhold|reveal|emphasize",
  "text_strategy":"none|caption|emphasis|statistic|name|location|quote|callout|chapter|data_graphic",
  "graphic_strategy":"none|chart|map|document|data_graphic|label",
  "sound_strategy":"none|ambience|action_sfx|transition_sfx|impact|silence|music_lift|music_drop|music_hold",
  "emotional_state":"curiosity|understanding|anticipation|tension|surprise|impact|emotional_weight|relief|reset",
  "preferred_asset_ids":["001","001_b"],
  "primary_claim":"short claim",
  "viewer_goal":"what viewer should understand",
  "confidence":0.0-1.0,
  "reasoning":"one short sentence"
}]}
"""


class EditorialReasoner(Protocol):
    """Provider-agnostic editorial reasoning."""

    def reason(
        self,
        plan: EditorialPlan,
        *,
        candidates_by_scene: Optional[Mapping[str, Sequence[AssetCandidate]]] = None,
    ) -> Dict[str, EditorialIntent]:
        ...


def reasoner_mode(settings: Optional[Mapping[str, Any]] = None) -> str:
    """Return AI_ENABLED | AI_DISABLED based on settings / env."""
    settings = settings or {}
    flag = settings.get("editorial_ai")
    if flag is False or str(flag).strip().lower() in ("0", "false", "off", "disabled"):
        return "AI_DISABLED"
    try:
        from visual_director.llm import gemini_configured

        if gemini_configured(settings):
            return "AI_ENABLED"
    except Exception:
        pass
    return "AI_DISABLED"


def intent_fingerprint(
    plan: EditorialPlan,
    *,
    candidates_by_scene: Optional[Mapping[str, Sequence[AssetCandidate]]] = None,
) -> str:
    """Stable hash so we can reuse cached intents across recompiles."""
    payload: Dict[str, Any] = {
        "v": REASONER_VERSION,
        "scenes": [
            {
                "n": str(s.scene_number),
                "t": (s.narration_excerpt or "")[:160],
                "g": (s.visual_goal or "")[:80],
                "d": round(float(s.duration), 2),
            }
            for s in plan.scenes
        ],
    }
    if candidates_by_scene:
        assets: Dict[str, List[str]] = {}
        for s in plan.scenes:
            sn = str(s.scene_number)
            cands = (
                candidates_by_scene.get(sn)
                or candidates_by_scene.get(sn.zfill(3))
                or []
            )
            assets[sn] = [c.asset_id for c in cands][:8]
        payload["assets"] = assets
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def parse_intent_payload(
    payload: dict,
    *,
    valid_scenes: Sequence[str],
) -> Dict[str, EditorialIntent]:
    """Validate AI JSON → EditorialIntent map. Invalid rows dropped."""
    items = payload.get("intents") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {}
    valid = {str(s) for s in valid_scenes}
    valid |= {s.zfill(3) for s in valid if s.isdigit()}
    out: Dict[str, EditorialIntent] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        intent = EditorialIntent.from_dict(raw)
        intent.source = "ai"
        sn = intent.scene_number.strip()
        if not sn:
            continue
        # Normalize to plan's scene number form when possible
        if sn not in valid:
            alt = sn.lstrip("0") or sn
            if alt in valid:
                sn = alt
            elif sn.zfill(3) in valid:
                sn = sn.zfill(3)
            else:
                continue
        intent.scene_number = sn
        # Drop absurdly low-confidence AI rows (treat as missing)
        if intent.confidence < CONF_LOW:
            continue
        out[sn] = intent
        out[sn.zfill(3)] = intent
        out[sn.lstrip("0") or sn] = intent
    return out


def _truncate(text: str, n: int = 140) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t if len(t) <= n else t[: n - 1] + "…"


def _beat_payload(
    scenes: Sequence[EditorialScene],
    *,
    candidates_by_scene: Optional[Mapping[str, Sequence[AssetCandidate]]],
    start: int,
    end: int,
) -> List[dict]:
    rows: List[dict] = []
    total = len(scenes)
    for i in range(start, end):
        scene = scenes[i]
        sn = str(scene.scene_number)
        prev_t = _truncate(scenes[i - 1].narration_excerpt, 80) if i > 0 else ""
        next_t = _truncate(scenes[i + 1].narration_excerpt, 80) if i + 1 < total else ""
        cands = []
        if candidates_by_scene:
            raw = (
                candidates_by_scene.get(sn)
                or candidates_by_scene.get(sn.zfill(3))
                or candidates_by_scene.get(sn.lstrip("0") or sn)
                or []
            )
            for c in raw[:6]:
                cands.append(
                    {
                        "id": c.asset_id,
                        "class": c.asset_class or ("primary" if c.is_primary else "complement"),
                        "role": c.visual_role or "",
                        "hint": _truncate(c.query_hint, 60),
                        "primary": bool(c.is_primary),
                    }
                )
        rows.append(
            {
                "scene_number": sn,
                "index": i,
                "duration": round(float(scene.duration), 2),
                "narration": _truncate(scene.narration_excerpt, 160),
                "visual_goal": _truncate(scene.visual_goal, 80),
                "visual_description": _truncate(scene.visual_description, 80),
                "asset_type": scene.asset_type_intent,
                "seed_purpose": scene.purpose,
                "prev": prev_t,
                "next": next_t,
                "candidates": cands,
            }
        )
    return rows


class NullEditorialReasoner:
    """AI_DISABLED — returns empty intents (deterministic path unchanged)."""

    def reason(
        self,
        plan: EditorialPlan,
        *,
        candidates_by_scene: Optional[Mapping[str, Sequence[AssetCandidate]]] = None,
    ) -> Dict[str, EditorialIntent]:
        return {}


class StaticEditorialReasoner:
    """Test double: returns a fixed intent map or parses fixed JSON text."""

    def __init__(self, intents: Optional[Dict[str, EditorialIntent]] = None, raw_json: str = ""):
        self.intents = intents or {}
        self.raw_json = raw_json
        self.calls = 0

    def reason(
        self,
        plan: EditorialPlan,
        *,
        candidates_by_scene: Optional[Mapping[str, Sequence[AssetCandidate]]] = None,
    ) -> Dict[str, EditorialIntent]:
        self.calls += 1
        if self.intents:
            return dict(self.intents)
        payload = _extract_json_object(self.raw_json)
        return parse_intent_payload(
            payload, valid_scenes=[str(s.scene_number) for s in plan.scenes]
        )


class GeminiEditorialReasoner:
    """Batched Gemini editorial intents. Fail-open on any error."""

    def __init__(
        self,
        settings: Optional[Mapping[str, Any]] = None,
        *,
        llm: Any = None,
        batch_size: int = 28,
        timeout: float = 75.0,
    ):
        self.settings = dict(settings or {})
        self.llm = llm
        self.batch_size = max(8, min(40, int(batch_size)))
        self.timeout = timeout

    def _ensure_llm(self) -> Any:
        if self.llm is not None:
            return self.llm
        from visual_director.llm import GeminiLLM

        self.llm = GeminiLLM(
            settings=self.settings,
            timeout=self.timeout,
        )
        return self.llm

    def reason(
        self,
        plan: EditorialPlan,
        *,
        candidates_by_scene: Optional[Mapping[str, Sequence[AssetCandidate]]] = None,
    ) -> Dict[str, EditorialIntent]:
        scenes = list(plan.scenes)
        if not scenes:
            return {}
        try:
            llm = self._ensure_llm()
        except Exception:
            return {}

        out: Dict[str, EditorialIntent] = {}
        valid = [str(s.scene_number) for s in scenes]
        for start in range(0, len(scenes), self.batch_size):
            end = min(len(scenes), start + self.batch_size)
            beats = _beat_payload(
                scenes,
                candidates_by_scene=candidates_by_scene,
                start=start,
                end=end,
            )
            user = (
                "Documentary editorial intents for these beats. "
                "Return JSON only.\n\n"
                + json.dumps({"beats": beats}, ensure_ascii=False)
            )
            try:
                # Prefer low thinking for cost; fall back to complete()
                if hasattr(llm, "complete"):
                    try:
                        from visual_director.llm import GeminiLLM

                        if isinstance(llm, GeminiLLM):
                            raw = llm.complete(
                                SYSTEM_PROMPT,
                                user,
                                thinking_level="low",
                                max_output_tokens=min(8192, 400 + len(beats) * 180),
                            )
                        else:
                            raw = llm.complete(SYSTEM_PROMPT, user)
                    except TypeError:
                        raw = llm.complete(SYSTEM_PROMPT, user)
                else:
                    return out
            except Exception:
                # Partial results from earlier batches still returned
                break
            parsed = parse_intent_payload(
                _extract_json_object(raw), valid_scenes=valid
            )
            out.update(parsed)
        return out


def build_editorial_reasoner(
    settings: Optional[Mapping[str, Any]] = None,
    *,
    llm: Any = None,
) -> EditorialReasoner:
    mode = reasoner_mode(settings)
    if mode == "AI_DISABLED" and llm is None:
        return NullEditorialReasoner()
    if llm is not None:
        return GeminiEditorialReasoner(settings=settings, llm=llm)
    if mode == "AI_ENABLED":
        return GeminiEditorialReasoner(settings=settings)
    return NullEditorialReasoner()


def apply_intents_to_scenes(
    plan: EditorialPlan,
    intents: Mapping[str, EditorialIntent],
) -> None:
    """Soft-apply high/medium confidence intents onto EditorialScene fields.

    Never changes duration / start / end. Only purpose, pacing_bias, attention,
    and ambience intensity hints that downstream directors already understand.
    """
    for scene in plan.scenes:
        sn = str(scene.scene_number)
        intent = (
            intents.get(sn)
            or intents.get(sn.zfill(3))
            or intents.get(sn.lstrip("0") or sn)
        )
        if intent is None or intent.confidence < CONF_MEDIUM:
            continue
        # Pacing
        bias = intent.pacing_bias()
        if bias in ("slow", "normal", "fast"):
            scene.pacing_bias = bias  # type: ignore[assignment]
        # Purpose — only high confidence overrides heuristic purpose
        if intent.confidence >= 0.75:
            purpose = intent.purpose_hint()
            if purpose:
                from .schema import ALLOWED_PURPOSES

                if purpose in ALLOWED_PURPOSES:
                    scene.purpose = purpose  # type: ignore[assignment]
        # Attention from emotional state
        emo = intent.emotional_state
        boost = {
            "curiosity": 0.72,
            "anticipation": 0.78,
            "surprise": 0.85,
            "impact": 0.88,
            "tension": 0.8,
            "emotional_weight": 0.75,
            "understanding": 0.55,
            "relief": 0.45,
            "reset": 0.4,
        }.get(emo)
        if boost is not None and intent.confidence >= CONF_MEDIUM:
            scene.attention_score = round(
                max(float(scene.attention_score), boost) if intent.confidence < 0.85
                else boost,
                3,
            )
        # Evidence-heavy beats: slightly lower ambience so VO/text dominate
        if intent.evidence_level == "high" and intent.confidence >= 0.7:
            scene.ambience_intensity = min(float(scene.ambience_intensity), 0.7)
        if intent.sound_strategy == "silence":
            scene.allow_silence = True
            scene.ambience_intensity = min(float(scene.ambience_intensity), 0.35)


def intents_to_serializable(intents: Mapping[str, EditorialIntent]) -> List[dict]:
    """Deduped list for plan persistence."""
    seen = set()
    out: List[dict] = []
    for intent in intents.values():
        sn = str(intent.scene_number)
        key = sn.lstrip("0") or sn
        if key in seen:
            continue
        seen.add(key)
        out.append(intent.to_dict())
    return out


def intents_from_plan(plan: EditorialPlan) -> Dict[str, EditorialIntent]:
    raw = getattr(plan, "editorial_intents", None) or []
    if not isinstance(raw, list):
        return {}
    out: Dict[str, EditorialIntent] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        intent = EditorialIntent.from_dict(item)
        if not intent.scene_number:
            continue
        sn = intent.scene_number
        out[sn] = intent
        out[sn.zfill(3)] = intent
        out[sn.lstrip("0") or sn] = intent
    return out


def enrich_plan_with_editorial_ai(
    plan: EditorialPlan,
    *,
    candidates_by_scene: Optional[Mapping[str, Sequence[AssetCandidate]]] = None,
    settings: Optional[Mapping[str, Any]] = None,
    reasoner: Optional[EditorialReasoner] = None,
    force: bool = False,
) -> Dict[str, EditorialIntent]:
    """Run AI editorial director (or reuse cache). Fail-open to {}.

    Returns intent map (may be empty). Mutates plan.editorial_intents when
    new intents are produced.
    """
    fp = intent_fingerprint(plan, candidates_by_scene=candidates_by_scene)
    cached_fp = str(getattr(plan, "editorial_intent_fingerprint", "") or "")
    cached = intents_from_plan(plan)
    if not force and cached and cached_fp == fp:
        apply_intents_to_scenes(plan, cached)
        return cached

    active = reasoner or build_editorial_reasoner(settings)
    try:
        intents = active.reason(plan, candidates_by_scene=candidates_by_scene) or {}
    except Exception:
        intents = {}

    if intents:
        apply_intents_to_scenes(plan, intents)
        setattr(plan, "editorial_intents", intents_to_serializable(intents))
        setattr(plan, "editorial_intent_fingerprint", fp)
        setattr(plan, "editorial_reasoner_version", REASONER_VERSION)
    else:
        # Keep prior cache if fingerprint still matches somehow; else clear soft fields
        if cached and cached_fp == fp:
            apply_intents_to_scenes(plan, cached)
            return cached
    return intents
