"""Brand Kit + Video Style schema (versioned JSON)."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

VIDEO_STYLE_VERSION = 1
VIDEO_STYLE_VERSION_3 = 3
BRAND_KIT_VERSION = 1

STYLE_MODES = frozenset({"auto", "manual", "custom"})


@dataclasses.dataclass
class StyleIdentity:
    description: str = ""
    tone: str = ""
    best_for: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class StyleCamera:
    preferred: List[str] = dataclasses.field(default_factory=list)
    intensity: float = 0.5


@dataclasses.dataclass
class StyleVisual:
    treatment: str = ""
    camera: StyleCamera = dataclasses.field(default_factory=StyleCamera)
    motion_rules: Dict[str, Any] = dataclasses.field(default_factory=dict)
    variety: Dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class StylePacing:
    default: str = "normal"
    hook: str = "normal"
    exposition: str = "normal"
    evidence: str = "normal"
    climax: str = "fast"
    reflection: str = "slow"
    transition_density: float = 0.35


@dataclasses.dataclass
class StyleTransitions:
    default: str = "cut"
    preferred: List[str] = dataclasses.field(default_factory=list)
    avoid: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class StyleAudio:
    ambience_intensity: float = 0.55
    sfx_intensity: float = 0.45
    music_intensity: float = 0.5
    music_duck_db: float = -10.0


@dataclasses.dataclass
class StyleHook:
    window_seconds: float = 30.0
    attention_target: float = 0.7
    prefer_visual_change: bool = True


@dataclasses.dataclass
class StyleAssets:
    preferred: List[str] = dataclasses.field(default_factory=list)
    avoid_repetition: bool = True


@dataclasses.dataclass
class StyleCaptions:
    style: str = "documentary"
    density: str = "medium"
    emphasis: str = "subtle"


@dataclasses.dataclass
class StyleAIVisualPrompt:
    style: str = ""
    realism: float = 0.7
    composition: str = ""
    avoid: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class StyleIntelligence:
    """Compatibility weights + preview tags for AUTO scoring / UI."""

    weights: Dict[str, float] = dataclasses.field(default_factory=dict)
    preview_visual: str = ""
    preview_camera: str = ""
    preview_pacing: str = ""
    preview_audio: str = ""
    variety_family: str = ""
    influences: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class StyleVisualRoleWeights:
    """Role preference weights for smart visual selection (0–1)."""

    weights: Dict[str, float] = dataclasses.field(default_factory=dict)
    avoid: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class StyleSourcePreferences:
    """Ordered source ranking preferences — not mandatory assignments."""

    ranked: List[str] = dataclasses.field(default_factory=list)
    avoid: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class StyleSearchGuidance:
    prefer_terms: List[str] = dataclasses.field(default_factory=list)
    avoid_terms: List[str] = dataclasses.field(default_factory=list)
    evidence_bias: str = "medium"  # low | medium | high
    query_expansion: bool = True


@dataclasses.dataclass
class StyleSelectionRules:
    prefer_evidence_when_factual: bool = True
    avoid_generic_when_specific: bool = True
    repetition_penalty: float = 0.35
    provider_repetition_penalty: float = 0.25
    concept_repetition_penalty: float = 0.4


@dataclasses.dataclass
class StyleStorytelling:
    narrative: str = ""
    hook_strategy: str = ""
    evidence_priority: str = "medium"


@dataclasses.dataclass
class StyleShotSelection:
    establishing_weight: float = 0.5
    evidence_weight: float = 0.5
    atmosphere_weight: float = 0.3
    process_weight: float = 0.4


@dataclasses.dataclass
class VideoStyle:
    id: str
    version: int = VIDEO_STYLE_VERSION
    name: str = ""
    identity: StyleIdentity = dataclasses.field(default_factory=StyleIdentity)
    visual: StyleVisual = dataclasses.field(default_factory=StyleVisual)
    pacing: StylePacing = dataclasses.field(default_factory=StylePacing)
    transitions: StyleTransitions = dataclasses.field(default_factory=StyleTransitions)
    audio: StyleAudio = dataclasses.field(default_factory=StyleAudio)
    hook: StyleHook = dataclasses.field(default_factory=StyleHook)
    assets: StyleAssets = dataclasses.field(default_factory=StyleAssets)
    captions: StyleCaptions = dataclasses.field(default_factory=StyleCaptions)
    ai_visual_prompt: StyleAIVisualPrompt = dataclasses.field(
        default_factory=StyleAIVisualPrompt
    )
    intelligence: StyleIntelligence = dataclasses.field(default_factory=StyleIntelligence)
    # Style Intelligence 3.0 — optional; older JSON files omit these safely.
    visual_roles: StyleVisualRoleWeights = dataclasses.field(default_factory=StyleVisualRoleWeights)
    source_preferences: StyleSourcePreferences = dataclasses.field(default_factory=StyleSourcePreferences)
    search_guidance: StyleSearchGuidance = dataclasses.field(default_factory=StyleSearchGuidance)
    selection_rules: StyleSelectionRules = dataclasses.field(default_factory=StyleSelectionRules)
    storytelling: StyleStorytelling = dataclasses.field(default_factory=StyleStorytelling)
    shot_selection: StyleShotSelection = dataclasses.field(default_factory=StyleShotSelection)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VideoStyle":
        if not isinstance(data, dict):
            raise ValueError("VideoStyle requires a dict")
        sid = str(data.get("id") or "").strip()
        if not sid:
            raise ValueError("VideoStyle.id is required")
        identity = data.get("identity") if isinstance(data.get("identity"), dict) else {}
        visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
        cam = visual.get("camera") if isinstance(visual.get("camera"), dict) else {}
        pacing = data.get("pacing") if isinstance(data.get("pacing"), dict) else {}
        transitions = data.get("transitions") if isinstance(data.get("transitions"), dict) else {}
        audio = data.get("audio") if isinstance(data.get("audio"), dict) else {}
        hook = data.get("hook") if isinstance(data.get("hook"), dict) else {}
        assets = data.get("assets") if isinstance(data.get("assets"), dict) else {}
        captions = data.get("captions") if isinstance(data.get("captions"), dict) else {}
        ai = data.get("ai_visual_prompt") if isinstance(data.get("ai_visual_prompt"), dict) else {}
        intel = data.get("intelligence") if isinstance(data.get("intelligence"), dict) else {}
        vroles = data.get("visual_roles") if isinstance(data.get("visual_roles"), dict) else {}
        sprefs = data.get("source_preferences") if isinstance(data.get("source_preferences"), dict) else {}
        sguide = data.get("search_guidance") if isinstance(data.get("search_guidance"), dict) else {}
        srules = data.get("selection_rules") if isinstance(data.get("selection_rules"), dict) else {}
        story = data.get("storytelling") if isinstance(data.get("storytelling"), dict) else {}
        shots = data.get("shot_selection") if isinstance(data.get("shot_selection"), dict) else {}
        return cls(
            id=sid,
            version=int(data.get("version") or VIDEO_STYLE_VERSION),
            name=str(data.get("name") or sid),
            identity=StyleIdentity(
                description=str(identity.get("description") or ""),
                tone=str(identity.get("tone") or ""),
                best_for=list(identity.get("best_for") or []),
            ),
            visual=StyleVisual(
                treatment=str(visual.get("treatment") or ""),
                camera=StyleCamera(
                    preferred=list(cam.get("preferred") or []),
                    intensity=float(cam.get("intensity") if cam.get("intensity") is not None else 0.5),
                ),
                motion_rules=dict(visual.get("motion_rules") or {}),
                variety=dict(visual.get("variety") or {}),
            ),
            pacing=StylePacing(
                default=str(pacing.get("default") or "normal"),
                hook=str(pacing.get("hook") or "normal"),
                exposition=str(pacing.get("exposition") or "normal"),
                evidence=str(pacing.get("evidence") or "normal"),
                climax=str(pacing.get("climax") or "fast"),
                reflection=str(pacing.get("reflection") or "slow"),
                transition_density=float(
                    pacing.get("transition_density")
                    if pacing.get("transition_density") is not None
                    else 0.35
                ),
            ),
            transitions=StyleTransitions(
                default=str(transitions.get("default") or "cut"),
                preferred=list(transitions.get("preferred") or []),
                avoid=list(transitions.get("avoid") or []),
            ),
            audio=StyleAudio(
                ambience_intensity=float(
                    audio.get("ambience_intensity")
                    if audio.get("ambience_intensity") is not None
                    else 0.55
                ),
                sfx_intensity=float(
                    audio.get("sfx_intensity") if audio.get("sfx_intensity") is not None else 0.45
                ),
                music_intensity=float(
                    audio.get("music_intensity")
                    if audio.get("music_intensity") is not None
                    else 0.5
                ),
                music_duck_db=float(
                    audio.get("music_duck_db") if audio.get("music_duck_db") is not None else -10.0
                ),
            ),
            hook=StyleHook(
                window_seconds=float(
                    hook.get("window_seconds") if hook.get("window_seconds") is not None else 30.0
                ),
                attention_target=float(
                    hook.get("attention_target")
                    if hook.get("attention_target") is not None
                    else 0.7
                ),
                prefer_visual_change=bool(
                    hook.get("prefer_visual_change")
                    if hook.get("prefer_visual_change") is not None
                    else True
                ),
            ),
            assets=StyleAssets(
                preferred=list(assets.get("preferred") or []),
                avoid_repetition=bool(
                    assets.get("avoid_repetition")
                    if assets.get("avoid_repetition") is not None
                    else True
                ),
            ),
            captions=StyleCaptions(
                style=str(captions.get("style") or "documentary"),
                density=str(captions.get("density") or "medium"),
                emphasis=str(captions.get("emphasis") or "subtle"),
            ),
            ai_visual_prompt=StyleAIVisualPrompt(
                style=str(ai.get("style") or ""),
                realism=float(ai.get("realism") if ai.get("realism") is not None else 0.7),
                composition=str(ai.get("composition") or ""),
                avoid=list(ai.get("avoid") or []),
            ),
            intelligence=StyleIntelligence(
                weights={str(k): float(v) for k, v in dict(intel.get("weights") or {}).items()},
                preview_visual=str(intel.get("preview_visual") or ""),
                preview_camera=str(intel.get("preview_camera") or ""),
                preview_pacing=str(intel.get("preview_pacing") or ""),
                preview_audio=str(intel.get("preview_audio") or ""),
                variety_family=str(intel.get("variety_family") or ""),
                influences=list(intel.get("influences") or []),
            ),
            visual_roles=StyleVisualRoleWeights(
                weights={
                    str(k): float(v)
                    for k, v in (
                        dict(vroles.get("weights") or {}).items()
                        if isinstance(vroles.get("weights"), dict)
                        else {
                            str(k): float(v)
                            for k, v in vroles.items()
                            if k not in ("avoid", "weights") and isinstance(v, (int, float))
                        }
                    )
                },
                avoid=list(vroles.get("avoid") or []),
            ),
            source_preferences=StyleSourcePreferences(
                ranked=list(sprefs.get("ranked") or sprefs.get("preferred") or []),
                avoid=list(sprefs.get("avoid") or []),
            ),
            search_guidance=StyleSearchGuidance(
                prefer_terms=list(sguide.get("prefer_terms") or []),
                avoid_terms=list(sguide.get("avoid_terms") or []),
                evidence_bias=str(sguide.get("evidence_bias") or "medium"),
                query_expansion=bool(sguide.get("query_expansion") if sguide.get("query_expansion") is not None else True),
            ),
            selection_rules=StyleSelectionRules(
                prefer_evidence_when_factual=bool(
                    srules.get("prefer_evidence_when_factual")
                    if srules.get("prefer_evidence_when_factual") is not None
                    else True
                ),
                avoid_generic_when_specific=bool(
                    srules.get("avoid_generic_when_specific")
                    if srules.get("avoid_generic_when_specific") is not None
                    else True
                ),
                repetition_penalty=float(srules.get("repetition_penalty") if srules.get("repetition_penalty") is not None else 0.35),
                provider_repetition_penalty=float(
                    srules.get("provider_repetition_penalty")
                    if srules.get("provider_repetition_penalty") is not None
                    else 0.25
                ),
                concept_repetition_penalty=float(
                    srules.get("concept_repetition_penalty")
                    if srules.get("concept_repetition_penalty") is not None
                    else 0.4
                ),
            ),
            storytelling=StyleStorytelling(
                narrative=str(story.get("narrative") or story.get("storytelling") or ""),
                hook_strategy=str(story.get("hook_strategy") or ""),
                evidence_priority=str(story.get("evidence_priority") or "medium"),
            ),
            shot_selection=StyleShotSelection(
                establishing_weight=float(shots.get("establishing_weight") if shots.get("establishing_weight") is not None else 0.5),
                evidence_weight=float(shots.get("evidence_weight") if shots.get("evidence_weight") is not None else 0.5),
                atmosphere_weight=float(shots.get("atmosphere_weight") if shots.get("atmosphere_weight") is not None else 0.3),
                process_weight=float(shots.get("process_weight") if shots.get("process_weight") is not None else 0.4),
            ),
        )


@dataclasses.dataclass
class BrandKit:
    id: str
    version: int = BRAND_KIT_VERSION
    name: str = ""
    channel_name: str = ""
    logo_path: str = ""
    watermark: Dict[str, Any] = dataclasses.field(default_factory=dict)
    accent_color: str = ""
    typography: Dict[str, Any] = dataclasses.field(default_factory=dict)
    captions: Dict[str, Any] = dataclasses.field(default_factory=dict)
    intro: Dict[str, Any] = dataclasses.field(default_factory=dict)
    outro: Dict[str, Any] = dataclasses.field(default_factory=dict)
    preferred_visual_identity: str = ""
    default_style_id: str = ""
    ai_prompt_additions: str = ""
    # Soft editorial overrides (only applied when explicitly set / non-empty)
    overrides: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BrandKit":
        if not isinstance(data, dict):
            raise ValueError("BrandKit requires a dict")
        kid = str(data.get("id") or "").strip()
        if not kid:
            raise ValueError("BrandKit.id is required")
        return cls(
            id=kid,
            version=int(data.get("version") or BRAND_KIT_VERSION),
            name=str(data.get("name") or kid),
            channel_name=str(data.get("channel_name") or ""),
            logo_path=str(data.get("logo_path") or ""),
            watermark=dict(data.get("watermark") or {}),
            accent_color=str(data.get("accent_color") or ""),
            typography=dict(data.get("typography") or {}),
            captions=dict(data.get("captions") or {}),
            intro=dict(data.get("intro") or {}),
            outro=dict(data.get("outro") or {}),
            preferred_visual_identity=str(data.get("preferred_visual_identity") or ""),
            default_style_id=str(data.get("default_style_id") or ""),
            ai_prompt_additions=str(data.get("ai_prompt_additions") or ""),
            overrides=dict(data.get("overrides") or {}),
        )


@dataclasses.dataclass
class ResolvedStyle:
    """Runtime resolution result passed into EditorialPlan builder."""

    mode: str  # auto | manual | custom
    style: VideoStyle
    brand_kit: Optional[BrandKit] = None
    confidence: float = 1.0
    reason: str = ""
    detected_style_id: str = ""
    alternatives: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    influences: List[str] = dataclasses.field(default_factory=list)
    content_profile: Dict[str, Any] = dataclasses.field(default_factory=dict)
    style_scores: List[Dict[str, Any]] = dataclasses.field(default_factory=list)

    @property
    def style_id(self) -> str:
        return self.style.id

    @property
    def style_version(self) -> int:
        return int(self.style.version)

    @property
    def brand_kit_id(self) -> str:
        return self.brand_kit.id if self.brand_kit else ""

    @property
    def brand_version(self) -> int:
        return int(self.brand_kit.version) if self.brand_kit else 0

    def fingerprint(self) -> dict:
        return {
            "mode": self.mode,
            "style_id": self.style_id,
            "style_version": self.style_version,
            "brand_kit_id": self.brand_kit_id or None,
            "brand_version": self.brand_version or None,
            "confidence": round(float(self.confidence), 3),
        }

    def to_resolution_meta(self) -> dict:
        return {
            "mode": self.mode,
            "style_id": self.style_id,
            "style_version": self.style_version,
            "brand_kit_id": self.brand_kit_id or None,
            "confidence": round(float(self.confidence), 3),
            "reason": self.reason,
            "detected_style_id": self.detected_style_id or self.style_id,
            "alternatives": list(self.alternatives or []),
            "influences": list(self.influences or []),
            "content_profile": {
                k: self.content_profile.get(k)
                for k in (
                    "domain",
                    "narrative_type",
                    "presentation",
                    "source_hash",
                )
                if self.content_profile
            },
            "style_scores": list(self.style_scores or [])[:4],
        }
