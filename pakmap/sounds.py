"""The pakMap sound vocabulary (Phase 7) and how each sound finds an asset.

The vocabulary is the approved list of sound categories from the competitor sound-design analysis (their
names, not their audio files). Nothing here is copied audio and nothing is downloaded: each sound is
resolved to an entry of the app's own SFX/ambience catalog (smart_editing.SfxCatalog, ~/.videogen/sfx),
the same asset infrastructure the other video styles use.

How a sound finds its asset, in order:
  1. its listed ``candidates`` (catalog ids), first one that exists in the installed library wins;
  2. else nothing: the sound is MISSING and reported, never faked.

Each candidate carries an honest fidelity label, decided from the catalog's tags and durations (the
assets were not auditioned by ear when this table was written):
  close        the catalog describes the kind of sound the vocabulary asks for
  approximate  the nearest thing in the catalog (a different texture of the same family)
  processed    an existing asset with a deterministic filter applied (for example a low-pass)
  synthesized  the library has no such recording: an original sound generated in code (pakmap/synth.py), deterministic
A sound's ``filters`` are ffmpeg filters applied at mix time, identically on every render.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

PRIORITY_MAJOR = "major"
PRIORITY_NORMAL = "normal"
PRIORITY_AMBIENCE = "ambience"
PRIORITY_RANK = {PRIORITY_MAJOR: 0, PRIORITY_NORMAL: 1, PRIORITY_AMBIENCE: 2}

CLOSE, APPROX, PROCESSED, SYNTHESIZED = "close", "approximate", "processed", "synthesized"


@dataclass(frozen=True)
class Sound:
    id: str
    kind: str  # sfx | ambience | composite
    source: str  # the sound as the competitor analysis names it
    use: str  # when it is used
    priority: str = PRIORITY_NORMAL
    volume: float = 0.14  # linear gain before ducking (kept well under the narration)
    max_s: Optional[float] = None  # one-shots are cut to this length
    fade_in: float = 0.0
    fade_out: float = 0.15
    candidates: Tuple[Tuple[str, str], ...] = ()  # (catalog id, fidelity), best first
    synth: str = ""  # name of a pakmap.synth generator, used when no candidate is in the library
    filters: str = ""  # ffmpeg audio filters applied to the asset
    repeat: Optional[Tuple[int, float]] = None  # (times, seconds between) for rhythmic sounds (ticks, construction)
    parts: Tuple[str, ...] = ()  # composite sounds: the vocabulary ids they play together
    note: str = ""


def _s(**kw) -> Sound:
    return Sound(**kw)


SOUNDS: Dict[str, Sound] = {s.id: s for s in [
    # ---- one-shot sound effects -----------------------------------------------------------------------------
    _s(id="map_slide_whoosh", kind="sfx", source="soft map 'slide' whoosh", use="smooth, major map repositioning (never a loud cinematic whoosh)",
       priority=PRIORITY_MAJOR, volume=0.15, max_s=1.3, fade_out=0.45, candidates=(("whoosh_02", CLOSE), ("whoosh_06", APPROX))),
    _s(id="ui_click", kind="sfx", source="subtle UI click / appearance sound", use="a photo card, image overlay or filmstrip appearing",
       volume=0.13, max_s=0.35, fade_out=0.08, candidates=(("ui_click_01", CLOSE), ("tech_click_01", APPROX))),
    _s(id="data_tick", kind="sfx", source="ticking clock", use="numbers and densities building up",
       volume=0.10, max_s=0.25, fade_out=0.06, repeat=(3, 0.2), candidates=(("ui_tick_01", CLOSE), ("ui_07", APPROX)),
       note="Repeated ticks, not a clock recording; the count and spacing follow the length of the build-up."),
    _s(id="marker_pop", kind="sfx", source="soft pop", use="a marker, county or region highlight, a data point",
       volume=0.13, max_s=0.45, fade_out=0.1, candidates=(("ui_pop_01", CLOSE), ("text_pop_01", APPROX), ("ui_08", APPROX))),
    _s(id="subtle_pop", kind="sfx", source="soft pop (quieter)", use="a sticker appearing",
       volume=0.09, max_s=0.45, fade_out=0.1, candidates=(("ui_pop_01", CLOSE), ("text_pop_01", APPROX))),
    _s(id="directional_whoosh", kind="sfx", source="subtle directional whoosh", use="a migration line, path or moisture arrow drawing",
       volume=0.11, max_s=0.9, fade_out=0.3, candidates=(("whoosh_05", CLOSE), ("whoosh_04", APPROX), ("whoosh_02", APPROX))),
    _s(id="earth_spin", kind="sfx", source="deep low-pass 'earth spin'", use="the camera heading to or from a global view",
       priority=PRIORITY_MAJOR, volume=0.16, max_s=2.2, fade_in=0.2, fade_out=0.8, candidates=(("whoosh_07", PROCESSED),),
       filters="lowpass=f=420", note="A deep movement whoosh with a low-pass applied (the library has no earth-spin recording)."),
    _s(id="equator_ding", kind="sfx", source="subtle ding", use="the equator / reference line finishing its draw",
       volume=0.09, max_s=1.1, fade_out=0.6, candidates=(("ui_ping_01", APPROX), ("ui_confirm_01", APPROX))),
    _s(id="record_scratch", kind="sfx", source="muffled historical 'record scratch'", use="historical portraits and archival material",
       volume=0.10, max_s=0.8, fade_out=0.2, candidates=(), filters="lowpass=f=1800",
       note="No record-scratch recording in the library."),
    _s(id="paper_slide", kind="sfx", source="paper slide", use="archival material sliding in",
       volume=0.12, max_s=0.9, fade_out=0.25, candidates=(), synth="paper_slide", note="Band-passed noise with a rubbing wobble (the library has no paper recording)."),
    _s(id="marker_clack", kind="sfx", source="marker 'clack'", use="a dam or location marker being revealed",
       volume=0.13, max_s=0.4, fade_out=0.08, candidates=(("tech_click_01", CLOSE), ("technology_06", APPROX))),
    _s(id="shimmer_riser", kind="sfx", source="shimmer / magical riser", use="a major visual transition (for example the Green Sahara)",
       priority=PRIORITY_MAJOR, volume=0.12, max_s=3.0, fade_in=0.4, fade_out=0.8, candidates=(("riser_05", APPROX), ("riser_01", APPROX)),
       note="Nearest are tension risers, not a shimmer."),
    _s(id="bone_tap", kind="sfx", source="bone tap", use="a fossil or bone visual",
       volume=0.12, max_s=0.5, fade_out=0.1, candidates=(("impact_01", APPROX),), note="Nearest is a soft impact."),
    _s(id="steam_chug", kind="sfx", source="low-volume steam-engine chug", use="a railway being revealed",
       volume=0.09, max_s=3.2, fade_in=0.2, fade_out=0.8, candidates=(), synth="steam_chug",
       note="Eleven rhythmic chuffs with a low thump (the library has only train-station ambience)."),
    _s(id="construction_impact", kind="sfx", source="rhythmic construction impact", use="a construction visual (kept low)",
       volume=0.12, max_s=0.6, fade_out=0.15, repeat=(3, 0.55), candidates=(("impact_03", CLOSE), ("impact_10", APPROX))),
    _s(id="camera_shutter", kind="sfx", source="camera-shutter-like appearance sound", use="an infrastructure icon appearing",
       volume=0.11, max_s=0.3, fade_out=0.06, candidates=(("tech_click_01", APPROX), ("tech_activation_01", APPROX))),
    _s(id="fast_whoosh", kind="sfx", source="fast-paced whooshing transition", use="the fast transition into the summary",
       priority=PRIORITY_MAJOR, volume=0.16, max_s=1.0, fade_out=0.3, candidates=(("whoosh_01", CLOSE), ("whoosh_05", APPROX))),
    _s(id="final_chime", kind="sfx", source="restrained final impact chime", use="the final reveal (kept quiet)",
       priority=PRIORITY_MAJOR, volume=0.14, max_s=2.0, fade_out=1.0, candidates=(("ui_ping_01", APPROX), ("ui_confirm_01", APPROX)),
       note="Nearest is a ping; the library has no chime."),
    _s(id="soft_transition", kind="sfx", source="soft transition", use="a full-screen picture or clip dissolving in",
       volume=0.12, max_s=1.4, fade_out=0.6, candidates=(("whoosh_06", CLOSE), ("transition_01", APPROX))),
    # ---- reference-video sound design: data/UI, fact-specific and comparison sounds (Phase 8) -------------------------
    _s(id="deep_thud", kind="sfx", source="deep cinematic hit (muffled bass thud)", use="a title or a fact number landing",
       volume=0.16, max_s=0.9, fade_out=0.35, candidates=(), synth="deep_thud", note="A decaying 45-95 Hz sine with a low knock."),
    _s(id="draw_zap", kind="sfx", source="thin electronic 'writing' zap", use="a line or border being drawn",
       volume=0.08, max_s=0.9, fade_out=0.25, candidates=(), synth="draw_zap", note="A rising 2.4-5.6 kHz tone with a 55 Hz flutter."),
    _s(id="bubble_pluck", kind="sfx", source="high-pitched bubble / pluck", use="a region fill or a dot layer appearing",
       volume=0.12, max_s=0.3, fade_out=0.08, candidates=(), synth="bubble_pluck", note="A short rising sine blip."),
    _s(id="counter_ticks", kind="sfx", source="high-speed mechanical tick (counters rapidly increasing)", use="a counter running up",
       volume=0.10, max_s=0.06, fade_out=0.02, repeat=(10, 0.055), candidates=(("ui_tick_01", CLOSE), ("ui_07", APPROX)),
       note="Ten ticks over about half a second, matching the 0.6 s counter ramp."),
    _s(id="clock_ticking", kind="sfx", source="timeline ticking", use="a time-difference explanation",
       volume=0.08, max_s=0.1, fade_out=0.03, repeat=(6, 0.5), candidates=(("ui_click_01", CLOSE), ("ui_07", APPROX)), note="Six ticks, one every half second."),
    _s(id="clock_chime", kind="sfx", source="clock chime", use="a time-difference explanation",
       volume=0.12, max_s=1.8, fade_out=0.9, candidates=(), synth="clock_chime", note="A struck-bell tone at 880 Hz."),
    _s(id="cash_register", kind="sfx", source="cash register 'cha-ching'", use="a sale or a price (for example the Alaska sale)",
       volume=0.13, max_s=1.5, fade_out=0.6, candidates=(), synth="cash_register", note="A short ratchet then two bell tones."),
    _s(id="metal_clang", kind="sfx", source="metal clang", use="a metal object (for example a borehole cover)",
       volume=0.13, max_s=1.3, fade_out=0.6, candidates=(), synth="metal_clang", note="Five inharmonic partials with a strike transient."),
    _s(id="muffled_explosion", kind="sfx", source="muffled explosion", use="a blast (for example the Tunguska event)",
       priority=PRIORITY_MAJOR, volume=0.17, max_s=2.4, fade_in=0.0, fade_out=0.9, candidates=(), synth="muffled_explosion", note="Low-passed noise burst with a 38 Hz thump."),
    _s(id="boil_sizzle", kind="sfx", source="bubbling / sizzling", use="boiling water or a hot reaction",
       volume=0.09, max_s=2.2, fade_in=0.1, fade_out=0.6, candidates=(), synth="boil_sizzle", note="High-passed fizz with bubble blips."),
    _s(id="wood_splinter", kind="sfx", source="splintering wood", use="trees flattening",
       volume=0.12, max_s=1.4, fade_out=0.3, candidates=(), synth="wood_splinter", note="Eleven short band-passed noise cracks."),
    _s(id="ice_crack", kind="sfx", source="ice cracking", use="the Arctic coast",
       volume=0.11, max_s=1.2, fade_out=0.4, candidates=(), synth="ice_crack", note="Three snaps with a falling ping."),
    _s(id="car_gravel", kind="sfx", source="car tires on gravel", use="a drive along a border road",
       volume=0.09, max_s=3.2, fade_in=0.3, fade_out=0.6, candidates=(), synth="car_gravel", note="Dense gravel crunch over a low engine."),
    _s(id="birds_chirping", kind="sfx", source="birds chirping", use="forests",
       volume=0.07, max_s=3.6, fade_in=0.1, fade_out=0.6, candidates=(), synth="birds_chirping", note="Six groups of short FM chirps. A synthesized approximation."),
    _s(id="mammoth_trumpet", kind="sfx", source="muffled mammoth trumpeting", use="Wrangel Island", volume=0.10, max_s=2.5, candidates=(),
       note="No recording in the library and not synthesized: an animal call needs a real recording."),
    _s(id="polar_bear_growl", kind="sfx", source="polar bear growl", use="the Arctic", volume=0.10, max_s=2.0, candidates=(),
       note="No recording in the library and not synthesized: an animal call needs a real recording."),
    # ---- composite --------------------------------------------------------------------------------------------
    _s(id="archival_texture", kind="composite", source="historical transition/material (record scratch + paper slide)",
       use="historical material appearing", parts=("paper_slide", "record_scratch"),
       note="Plays whichever of its parts have an asset; a missing part is reported, the rest still plays."),
    # ---- background ambience (loops, only when a section asks for them) ------------------------------------------
    _s(id="geographic_atmosphere", kind="ambience", source="geographic atmosphere", use="a quiet bed under a whole geographic section",
       priority=PRIORITY_AMBIENCE, volume=0.05, fade_in=1.2, fade_out=1.5, candidates=(("amb_atmospheric_01", APPROX), ("amb_atmospheric_04", APPROX))),
    _s(id="desert_wind", kind="ambience", source="ambient desert wind / low wind rumble", use="desert and arid sections",
       priority=PRIORITY_AMBIENCE, volume=0.07, fade_in=1.2, fade_out=1.5, candidates=(("amb_atmospheric_05", APPROX),),
       note="A low wind rumble (chimney wind)."),
    _s(id="rushing_wind", kind="ambience", source="rushing wind", use="wind-flow visualisation",
       priority=PRIORITY_AMBIENCE, volume=0.08, fade_in=0.8, fade_out=1.2, candidates=(("amb_atmospheric_05", APPROX),)),
    _s(id="water_ambience", kind="ambience", source="soft bubbling / water ambience", use="lakes, rivers, hydrography",
       priority=PRIORITY_AMBIENCE, volume=0.07, fade_in=1.0, fade_out=1.5, candidates=(("amb_water_04", CLOSE), ("amb_water_03", CLOSE)),
       note="Lake shore recordings, not specifically bubbling."),
    _s(id="historical_texture", kind="ambience", source="historical texture", use="archival sections",
       priority=PRIORITY_AMBIENCE, volume=0.04, fade_in=1.0, fade_out=1.2, candidates=(("amb_room_03", CLOSE),), note="A quiet room tone."),
    _s(id="railway_texture", kind="ambience", source="low-volume steam/railway texture", use="railway sections",
       priority=PRIORITY_AMBIENCE, volume=0.05, fade_in=1.0, fade_out=1.5, candidates=(("amb_transport_02", APPROX), ("amb_transport_01", APPROX)),
       note="A train interior / station hall recording, not a steam engine."),
    _s(id="cold_wind", kind="ambience", source="cold wind / arid drone", use="Siberia and the Arctic: isolation",
       priority=PRIORITY_AMBIENCE, volume=0.07, fade_in=1.2, fade_out=1.5, candidates=(("amb_atmospheric_05", APPROX),), filters="highpass=f=90",
       note="The library's low wind rumble with the lowest rumble removed."),
    _s(id="industrial_hum", kind="ambience", source="industrial / urban hum", use="Norilsk, trains: human infrastructure",
       priority=PRIORITY_AMBIENCE, volume=0.05, fade_in=1.0, fade_out=1.5, candidates=(), synth="industrial_hum", note="A 50 Hz hum with harmonics and slow swell, plus a low rumble."),
    _s(id="airplane_hum", kind="ambience", source="airplane engine hum", use="flying over trees",
       priority=PRIORITY_AMBIENCE, volume=0.06, fade_in=0.8, fade_out=1.2, candidates=(), synth="airplane_hum", note="A 78 Hz buzz with a band of wash noise."),
    _s(id="space_drone", kind="ambience", source="deep hollow 'vacuum' drone", use="space comparisons (for example Pluto)",
       priority=PRIORITY_AMBIENCE, volume=0.07, fade_in=1.0, fade_out=1.5, candidates=(("amb_atmospheric_03", APPROX), ("amb_atmospheric_01", APPROX)), filters="lowpass=f=400",
       note="The library's dark drone, low-passed."),
    _s(id="water_lapping", kind="ambience", source="water lapping", use="a lake shore (for example Lake Baikal)",
       priority=PRIORITY_AMBIENCE, volume=0.07, fade_in=1.0, fade_out=1.5, candidates=(("amb_water_04", CLOSE), ("amb_water_03", CLOSE)), note="Lake shore recordings."),
    _s(id="electrical_hum", kind="ambience", source="subtle electrical hum", use="electricity and infrastructure sections",
       priority=PRIORITY_AMBIENCE, volume=0.04, fade_in=0.8, fade_out=1.2, candidates=(("amb_technology_02", CLOSE), ("amb_technology_01", APPROX))),
]}

SFX_IDS = tuple(i for i, s in SOUNDS.items() if s.kind in ("sfx", "composite"))
AMBIENCE_IDS = tuple(i for i, s in SOUNDS.items() if s.kind == "ambience")

# event type -> the sound its mapping names (the mapping is a default, not a rule that every occurrence plays)
EVENT_SOUND = {
    "CAMERA_MOVE": "map_slide_whoosh", "TITLE": "deep_thud", "MARKER_REVEAL": "marker_pop", "STAT_REVEAL": "counter_ticks", "LINE_DRAW": "draw_zap",
    "FILL_REVEAL": "bubble_pluck", "DOTS_REVEAL": "bubble_pluck", "PIP_ENTER": "ui_click", "FILMSTRIP_ENTER": "ui_click",
    "COMPARISON_ENTER": "paper_slide", "STICKER_ENTER": "subtle_pop", "MEDIA_FULL": "soft_transition", "WATER_LAYER": "water_ambience",
    "WIND_LAYER": "rushing_wind", "HISTORICAL_MEDIA": "archival_texture", "RAILWAY_REVEAL": "steam_chug", "CONSTRUCTION": "construction_impact",
    "ELECTRICITY": "electrical_hum", "FINAL_REVEAL": "final_chime",
}
