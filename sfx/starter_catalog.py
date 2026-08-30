"""Starter catalog metadata (~58 slots). Does not create audio files."""

from __future__ import annotations

# Container for the WAV starter pack. Parameterised so the same builder can
# emit a catalog for a library shipped in another format.
STARTER_FORMAT = "wav"

from typing import Dict, List, Tuple

STARTER_TARGETS = {
    "whoosh": 10,
    "impact": 8,
    "transition": 8,
    "text": 6,
    "ui": 6,
    "riser": 5,
    "cinematic": 5,
    "technology": 5,
    "ambience": 5,
}

CATEGORY_TAG_POOLS: Dict[str, List[List[str]]] = {
    "whoosh": [
        ["short", "fast", "transition"],
        ["soft", "sweep", "movement"],
        ["deep", "rising", "cinematic"],
        ["falling", "movement"],
        ["fast", "sweep"],
        ["soft", "transition"],
        ["deep", "movement"],
        ["rising", "cinematic"],
        ["short", "movement"],
        ["fast", "transition", "sweep"],
    ],
    "impact": [
        ["soft", "emphasis"],
        ["medium", "punch"],
        ["deep", "heavy", "punch"],
        ["cinematic", "hit"],
        ["punch", "emphasis"],
        ["deep", "cinematic"],
        ["medium", "heavy"],
        ["soft", "punch"],
    ],
    "transition": [
        ["soft", "sweep"],
        ["fast", "movement"],
        ["cinematic", "rise"],
        ["reverse", "movement"],
        ["drop", "sweep"],
        ["soft", "transition"],
        ["fast", "sweep"],
        ["cinematic", "movement"],
    ],
    "text": [
        ["text_pop", "emphasis"],
        ["text_reveal", "reveal", "appear"],
        ["text_swipe", "movement"],
        ["text_hit", "text_emphasis", "punch"],
        ["text_type", "digital"],
        ["text_appear", "reveal"],
    ],
    "ui": [
        ["click", "tick", "select"],
        ["pop", "confirm", "digital"],
        ["ping", "beep", "blip"],
        ["confirm", "select"],
        ["tick", "digital"],
        ["beep", "interface"],
    ],
    "riser": [
        ["short", "tension"],
        ["long", "cinematic", "dark"],
        ["medium", "tension"],
        ["cinematic", "dark"],
        ["short", "cinematic"],
    ],
    "cinematic": [
        ["hit", "emphasis", "boom"],
        ["swell", "reveal", "pulse"],
        ["boom", "emphasis"],
        ["pulse", "reveal"],
        ["hit", "cinematic"],
    ],
    "technology": [
        ["mechanical_click", "computer_interface"],
        ["electronic_processing", "digital"],
        ["machine_start", "mechanical"],
        ["machine_stop", "mechanical"],
        ["electronic_activation", "digital"],
    ],
    "ambience": [
        ["room", "office"],
        ["city", "traffic"],
        ["crowd", "room"],
        ["wind", "nature"],
        ["technology", "office"],
    ],
}

SOURCE_LICENSE: Dict[str, Tuple[str, str]] = {
    category: ("Sonniss GDC", "Sonniss #GameAudioGDC Bundle License")
    for category in (
        "whoosh",
        "impact",
        "transition",
        "text",
        "ui",
        "riser",
        "cinematic",
        "technology",
        "ambience",
    )
}

INTENSITY_CYCLE = ["low", "medium", "high", "medium", "low", "high", "medium", "low", "high", "medium"]
DURATION_HINT = {
    "whoosh": 0.45,
    "impact": 0.35,
    "transition": 0.38,
    "text": 0.32,
    "ui": 0.18,
    "riser": 0.85,
    "cinematic": 0.62,
    "technology": 0.28,
    "ambience": 2.4,
}

SPECIAL_IDS: Dict[str, List[str]] = {
    "ui": ["ui_click_01", "ui_pop_01", "ui_ping_01", "ui_confirm_01", "ui_tick_01", "ui_beep_01"],
    "technology": [
        "tech_click_01",
        "tech_process_01",
        "tech_machine_start_01",
        "tech_machine_stop_01",
        "tech_activation_01",
    ],
    "ambience": [
        "ambience_room_01",
        "ambience_city_01",
        "ambience_crowd_01",
        "ambience_wind_01",
        "ambience_technology_01",
    ],
    "cinematic": [
        "cinematic_hit_01",
        "cinematic_swell_01",
        "cinematic_boom_01",
        "cinematic_pulse_01",
        "cinematic_reveal_01",
    ],
    "text": [
        "text_pop_01",
        "text_reveal_01",
        "text_swipe_01",
        "text_hit_01",
        "text_type_01",
        "text_appear_01",
    ],
}


def build_starter_catalog() -> dict:
    entries: List[dict] = []
    for category, count in STARTER_TARGETS.items():
        tags_pool = CATEGORY_TAG_POOLS[category]
        source, license_name = SOURCE_LICENSE[category]
        for i in range(1, count + 1):
            if category in SPECIAL_IDS:
                entry_id = SPECIAL_IDS[category][i - 1]
            else:
                entry_id = f"{category}_{i:02d}"
            intensity = INTENSITY_CYCLE[i - 1]
            duration = round(DURATION_HINT[category] + (i % 3) * 0.05, 2)
            entries.append(
                {
                    "id": entry_id,
                    "file": f"{category}/{entry_id}.{STARTER_FORMAT}",
                    "category": category,
                    "tags": tags_pool[i - 1],
                    "intensity": intensity,
                    "duration": duration,
                    "source": source,
                    "license": license_name,
                    "commercial_use": True,
                    "attribution_required": False,
                }
            )
    return {
        "version": 1,
        "library_root": "~/.videogen/sfx",
        "preferred_sources": [
            "sonniss_gdc",
            "mixkit",
            "youtube_audio_library",
            "pixabay",
        ],
        "sfx": entries,
    }
