"""The Health Cinema visual profiles (five focused ones plus Mix). One shared engine; a profile only configures it (scene-kind weights, typography, pace, glow, evidence
strictness). Profiles are not topic categories: the planner may use any scene kind whatever the profile, scaled by these weights."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Dict, Tuple

SCENE_KINDS = ("anatomy_3d", "footage", "evidence_card", "stat_card", "text_card", "chapter_card")

# Accessibility defaults for 1080p (design ranges: titles 48-72, labels 32-44, captions 28-36); scaled by height/1080 at render time.
TYPE_1080 = {"title": 64, "body": 44, "label": 40, "caption": 32, "source": 30}

@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    blurb: str
    weights: Dict[str, float]                  # preference per scene kind (0 = never chosen by the planner)
    accent: Tuple[int, int, int]               # card accent colour
    glow: Tuple[float, float, float]           # rim-glow colour for 3D scenes
    min_scene_s: float = 4.0                   # nothing shorter (reading time)
    max_scene_s: float = 14.0                  # long runs of one visual are split
    evidence_label: str = "What the evidence says"
    require_source_for_stats: bool = True      # a statistic without a source is flagged for review (always on; stricter profiles block display)
    block_unsourced_stats: bool = False        # True: the number is not shown big, the scene becomes a plain text card
    motion: str = "restrained"                 # restrained | calm | still (reduced motion)
    sound: str = "neutral"                     # sound palette tag (mix is narration-first in every profile)
    type_scale: float = 1.0
    notes: str = ""

PROFILES: Dict[str, Profile] = {p.id: p for p in (
    Profile("mix", "Mix (everything)", "A bit of everything: 3D anatomy, footage, evidence, statistics and text, rotated so no one look repeats.",
            {k: 0.6 for k in SCENE_KINDS}, (200, 160, 255), (0.7, 0.55, 1.0), sound="soft bed, light accents", notes="variety rule on"),
    Profile("medical_cinema", "Medical Cinema", "Cinematic anatomy, organs and how the body works.",
            {"anatomy_3d": 1.0, "footage": 0.5, "evidence_card": 0.4, "stat_card": 0.5, "text_card": 0.3, "chapter_card": 0.4},
            (255, 96, 80), (1.0, 0.35, 0.25), sound="low drone, soft impacts"),
    Profile("human_story", "Human Story Documentary", "People, lived experience and documentary footage; 3D only where it clarifies.",
            {"anatomy_3d": 0.25, "footage": 1.0, "evidence_card": 0.3, "stat_card": 0.3, "text_card": 0.5, "chapter_card": 0.3},
            (240, 190, 110), (1.0, 0.6, 0.3), min_scene_s=5.0, motion="calm", sound="warm ambience, minimal effects"),
    Profile("future_science", "Future Science", "Research, laboratories and biotechnology, with preliminary findings labelled as such.",
            {"anatomy_3d": 0.4, "footage": 0.8, "evidence_card": 0.8, "stat_card": 0.6, "text_card": 0.4, "chapter_card": 0.4},
            (90, 200, 255), (0.35, 0.75, 1.0), evidence_label="What the research shows", sound="clean tones, light pulses"),
    Profile("anatomy_explainer", "Anatomy Explainer", "Labelled anatomy and step-by-step mechanisms.",
            {"anatomy_3d": 1.0, "footage": 0.2, "evidence_card": 0.3, "stat_card": 0.4, "text_card": 0.6, "chapter_card": 0.5},
            (110, 220, 160), (0.4, 0.9, 0.6), min_scene_s=5.0, type_scale=1.05, sound="soft ticks on reveals"),
    Profile("health_investigative", "Health Investigative", "Claims, evidence, myths, statistics and sources.",
            {"anatomy_3d": 0.3, "footage": 0.5, "evidence_card": 1.0, "stat_card": 1.0, "text_card": 0.4, "chapter_card": 0.5},
            (255, 200, 70), (1.0, 0.8, 0.3), evidence_label="Claim versus evidence", block_unsourced_stats=True, sound="dry, minimal"),
)}
DEFAULT_PROFILE = "medical_cinema"
VARIETY_PROFILES = ("mix",)                   # planner adds a variety rule (rotate kinds, favour unused ones) for these

def get_profile(pid: str) -> Profile:
    if pid in PROFILES: return PROFILES[pid]
    for p in PROFILES.values():
        if p.name.lower() == str(pid).lower(): return p
    raise KeyError(f"unknown Health Cinema profile: {pid!r}")

def profile_names() -> Tuple[str, ...]: return tuple(p.name for p in PROFILES.values())

def type_sizes(profile: Profile, H: int) -> Dict[str, int]:
    """Text sizes for an output height: proportional to 1080p, with floors so 720p previews stay legible."""
    k = H / 1080.0
    return {n: max(round(v * profile.type_scale * k), 22 if n in ("caption", "source") else 28) for n, v in TYPE_1080.items()}

def with_motion(profile: Profile, motion: str) -> Profile:
    if motion not in ("restrained", "calm", "still"): raise ValueError(motion)
    return replace(profile, motion=motion)
