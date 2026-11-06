"""The video styles as the picker groups them, plus the styles that exist only as a card (StarMap Cinema: the StarMap engine with
its Cinema option on). Pure data and small helpers, no Tk: app.py keeps STYLE_CHOICES / STYLE_BLURBS / STYLE_CARDS and only adds
what is here."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

# (group title, styles in the order they are shown). A style missing from the app's choices (Weather when it is off) is skipped.
GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("General", ("Normal video", "Story Motion", "Modern Tech News", "Overscaled", "Exp Solar")),
    ("Maps", ("pakMap", "Hybrid Map")),
    ("Space", ("StarMap", "StarMap Cinema")),
    ("Explainers", ("What If", "Explainer", "Rep Theory", "Product Trailer")),
    ("Documentary", ("War Documentary", "Enoch Template")),
    ("Specialist", ("Health Cinema", "Weather")),
)

STARMAP_CINEMA = "StarMap Cinema"
EXPLAINER = "Explainer"
PRODUCT_TRAILER = "Product Trailer"
STORY_MOTION = "Story Motion"
# styles of their own engine that app.STYLE_CHOICES does not list (their page lives in ui/): appended after the app's choices
STANDALONE: Tuple[str, ...] = (PRODUCT_TRAILER,)
# card-only style -> the style whose engine it runs (with its look switched on)
BUILT_ON: Dict[str, str] = {STARMAP_CINEMA: "StarMap", EXPLAINER: "Hybrid Map", STORY_MOTION: "Normal video"}

EXTRA_BLURBS: Dict[str, str] = {
    STORY_MOTION: "Normal video where the pictures never sit still: one picture per narration phrase, layered depth parallax, short links "
                  "between pictures, and a quality check after the render. Needs a dense CSV (one row per picture).",
    STARMAP_CINEMA: "StarMap with the What If documentary look: diagram plates where the map cannot explain, the spacecraft up close, "
                    "numbers as type, documentary photos with a source line, cuts in the narration's pauses.",
    EXPLAINER: "Explainer videos on a board: drawn clips, a narrator, captions. Planned from your narration (Hybrid Map's engine "
               "with the Explainer look).",
    PRODUCT_TRAILER: "Phone launch trailers built in code: the phone in 3D on a star field, one feature at a time, cut to your "
                     "music, a disclaimer card at the end. From a short feature CSV.",
}

# icon, one-line pitch, what it needs, what it suits (the same shape as app.STYLE_CARDS)
EXTRA_CARDS: Dict[str, Tuple[str, str, str, str]] = {
    STORY_MOTION: ("\u25B6", "Moving pictures that follow the voice", "A dense CSV (one row per picture) + your voiceover", "Story videos from AI stills"),
    STARMAP_CINEMA: ("✸", "StarMap with the What If documentary look", "A StarMap beat CSV", "Space stories told like a documentary"),
    EXPLAINER: ("\u270E", "Board clips, a narrator and captions", "Your voiceover", "Explainers on any topic"),
    PRODUCT_TRAILER: ("\u25AF", "A phone launch trailer, cut to music", "A feature CSV (+ music)", "Phone launches, concept trailers"),
}

# Roblox Cinema (ui/roblox_cinema_section.py, roblox-cinema-engine/): appended here so nothing above changes
ROBLOX_CINEMA = "Roblox Cinema"
STANDALONE = STANDALONE + (ROBLOX_CINEMA,)
GROUPS = tuple((title, names + (ROBLOX_CINEMA,) if title == "Documentary" else names) for title, names in GROUPS)
EXTRA_BLURBS[ROBLOX_CINEMA] = ("History told in a block-toy 3D world: planned from your narration into scenes, cast, vehicles, cameras and "
                               "tabletop maps, cut to your voice, with music and sound. From a story CSV or plain narration.")
EXTRA_CARDS[ROBLOX_CINEMA] = ("\u25A6", "History as a block-world film", "A story CSV or narration (+ voice-over)", "War and history stories")


def with_extras(choices: Tuple[str, ...]) -> Tuple[str, ...]:
    """The app's choices plus the card-only styles, each right after the style it is built on."""
    out: List[str] = []
    for name in choices:
        out.append(name)
        out.extend(extra for extra, base in BUILT_ON.items() if base == name and extra not in choices)
    out.extend(name for name in STANDALONE if name not in out)
    return tuple(out)


def grouped(choices: Iterable[str]) -> List[Tuple[str, List[str]]]:
    """[(group title, [style, ...]), ...] for the styles in `choices`; a style no group lists goes into a last "More" group."""
    have = list(choices)
    seen = set()
    out: List[Tuple[str, List[str]]] = []
    for title, names in GROUPS:
        row = [n for n in names if n in have]
        seen.update(row)
        if row:
            out.append((title, row))
    rest = [n for n in have if n not in seen]
    if rest:
        out.append(("More", rest))
    return out


def group_of(name: str) -> Optional[str]:
    for title, names in GROUPS:
        if name in names:
            return title
    return None


# Voxel Map (ui/voxelmap_section.py, voxelmap-engine/): appended here so nothing above changes
VOXEL_MAP = "Voxel Map"
STANDALONE = STANDALONE + (VOXEL_MAP,)
GROUPS = tuple((title, names + (VOXEL_MAP,) if title == "Maps" else names) for title, names in GROUPS)
EXTRA_BLURBS[VOXEL_MAP] = ("A block-world 3D history map from a story CSV: real terrain, the camera flying from the globe down to ground scenes, "
                           "territory colours, captions, music, sound effects and your voice-over.")
EXTRA_CARDS[VOXEL_MAP] = ("\u25A9", "History on a 3D block-world map", "A story CSV (+ voice-over)", "War and history map stories")


# Rules Horror (ui/rules_horror_section.py, rules_horror/): appended here so nothing above changes
RULES_HORROR = "Rules Horror"
STANDALONE = STANDALONE + (RULES_HORROR,)
GROUPS = GROUPS + (("Stories", (RULES_HORROR,)),)
EXTRA_BLURBS[RULES_HORROR] = ("Narrated survival-rules horror in nine looks taken from nine reference videos: white line art on black, navy cartoon "
                              "(plane, cinema), bright filled rooms (mall, store, school) and underwater teal. Auto picks the look from the story's places, "
                              "with that reference's pacing and rule card. Cartoon people, filled rooms, glitches and a low sound bed, cut to your voice-over.")
EXTRA_CARDS[RULES_HORROR] = ("\u25D0", "Survival-rules horror, nine looks", "A story CSV + voice-over", "Rules and creepypasta-style horror stories")


# Kids Learn (ui/kids_learn_section.py, cartoon3d-engine/ + kids_audio/): appended here so nothing above changes
KIDS_LEARN = "Kids Learn"
STANDALONE = STANDALONE + (KIDS_LEARN,)
GROUPS = GROUPS + (("Kids", (KIDS_LEARN,)),)
EXTRA_BLURBS[KIDS_LEARN] = ("Preschool lessons with a friendly 3D host in a toy playroom: she talks to the child, presents toys, counts, chants on the beat "
                            "and waits for 'your turn', with captions, word cards, music and sound effects. From a lesson CSV; the voice is free.")
EXTRA_CARDS[KIDS_LEARN] = ("\u2605", "A preschool lesson with a 3D host", "A lesson CSV", "First words, counting, colours, chants")


# City Timelapse (ui/city_timelapse_section.py, citygrow-engine/): appended here so nothing above changes
CITY_TIMELAPSE = "City Timelapse"
STANDALONE = STANDALONE + (CITY_TIMELAPSE,)
GROUPS = tuple((title, names + (CITY_TIMELAPSE,) if title == "Maps" else names) for title, names in GROUPS)
EXTRA_BLURBS[CITY_TIMELAPSE] = ("A low-poly 3D city growing over the centuries on its real ground and water: houses rise street by street, landmarks "
                                "appear in their year, the camera never stops, with the year, population, era flag, titles and captions over music.")
EXTRA_CARDS[CITY_TIMELAPSE] = ("▲", "A city growing through history", "A story CSV", "How a city grew, era by era")
