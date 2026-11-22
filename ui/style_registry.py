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

# Cat Theory: the Rep Theory engine with the white cat theme (reptheory/theme.py "cat"); appended here so nothing above changes
CAT_THEORY = "Cat Theory"
BUILT_ON[CAT_THEORY] = "Rep Theory"
GROUPS = tuple((title, tuple(x for n in names for x in ((n, CAT_THEORY) if n == "Rep Theory" else (n,)))) for title, names in GROUPS)
EXTRA_BLURBS[CAT_THEORY] = ("Cat behaviour explainers told the Rep Theory way (hook, roadmap, claim, proof, try-it test, comment payoff) on a white "
                            "canvas: soft storybook cat pictures through Flow, study cards, equations and charts. No 3D.")
EXTRA_CARDS[CAT_THEORY] = ("\u2665", "Cat explainers on a white canvas", "Voiceover (scenes file optional)", "Cat behaviour, health and care")

# Carl Jung Theory: the Rep Theory engine with the old-master theme (reptheory/theme.py "jung"): oil paintings of Jung from his reference images, ideas, quotes
JUNG_THEORY = "Carl Jung Theory"
BUILT_ON[JUNG_THEORY] = "Rep Theory"
GROUPS = tuple((title, tuple(x for n in names for x in ((n, JUNG_THEORY) if n == CAT_THEORY else (n,)))) for title, names in GROUPS)
EXTRA_BLURBS[JUNG_THEORY] = ("Carl Jung and psychology explainers told the Rep Theory way, as one painted film: oil paintings of Jung made from your reference "
                             "images (assets/jung/refs), paintings of the ideas, quote cards with their real source, study and versus cards. No 3D.")
EXTRA_CARDS[JUNG_THEORY] = ("\u262F", "Jung explainers as a painted film", "Voiceover (scenes file optional)", "Jung, psychology, the shadow, archetypes")

# Elder Health Theory: the Rep Theory engine with the calm clinic theme (reptheory/theme.py "elder"): soft-colour pictures of older people, organ illustrations, a handwriting board
ELDER_THEORY = "Elder Health Theory"
BUILT_ON[ELDER_THEORY] = "Rep Theory"
GROUPS = tuple((title, tuple(x for n in names for x in ((n, ELDER_THEORY) if n == JUNG_THEORY else (n,)))) for title, names in GROUPS)
EXTRA_BLURBS[ELDER_THEORY] = ("Health advice for older viewers told the Rep Theory way on a calm light canvas with large, easy type: soft-colour pictures of "
                              "older people and of the organs through Flow, tips written on a whiteboard, study, number and warning cards. No 3D.")
EXTRA_CARDS[ELDER_THEORY] = ("\u271A", "Elder health advice, calm and clear", "Voiceover (scenes file optional)", "Senior health, heart, joints, sleep, diet")


# Survival: the Rep Theory engine with the field-guide theme (reptheory/theme.py "survival"): ink-and-watercolour frontier and family pictures, countdown / ranking / timeline cards
SURVIVAL = "Survival"
BUILT_ON[SURVIVAL] = "Rep Theory"
GROUPS = tuple((title, tuple(x for n in names for x in ((n, SURVIVAL) if n == ELDER_THEORY else (n,)))) for title, names in GROUPS)
EXTRA_BLURBS[SURVIVAL] = ("Long-form survival and preparedness explainers (countdowns, one-secret myth busters, place rankings, hour-by-hour timelines, "
                          "old-timer stories, gear that lies) on white paper: ink-and-watercolour field-guide pictures through Flow, number, rule and versus cards. No 3D.")
EXTRA_CARDS[SURVIVAL] = ("\u26FA", "Survival explainers in a field guide", "Voiceover (scenes file optional)", "Blackouts, winter, water, food, frontier skills")

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


# Aviation (ui/aviation_section.py, aviation/): appended here so nothing above changes
AVIATION = "Aviation"
STANDALONE = STANDALONE + (AVIATION,)
GROUPS = tuple((title, names + (AVIATION,) if title == "Documentary" else names) for title, names in GROUPS)
EXTRA_BLURBS[AVIATION] = ("Airline business stories and flight reconstructions, the look chosen per sentence from your narration: fast real clips "
                          "and blue article cards for the news, a dark flight map with the route, holds, storms and a fuel / clock display for "
                          "the flight, slow beauty shots for the aircraft. From your voice-over, optionally with an aviation scenes CSV.")
EXTRA_CARDS[AVIATION] = ("✈", "Airline stories and flight reconstructions", "Your voice-over (+ optional scenes CSV)",
                         "Airline business, aircraft programmes, incidents")


# Ocean Predators (ui/ocean_section.py, ocean/): appended here so nothing above changes
OCEAN = "Ocean Predators"
STANDALONE = STANDALONE + (OCEAN,)
GROUPS = tuple((title, names + (OCEAN,) if title == "Explainers" else names) for title, names in GROUPS)
EXTRA_BLURBS[OCEAN] = ("Sea-predator explainers drawn in code: flat 2D sharks, orcas, whales, seals and squid act every sentence in one moving "
                       "underwater world, numbers become cards (counts, dot grids, clocks, calendars), studies a paper card, 'what would "
                       "you do' the diver's view, with joke props and orange keyword captions over a music bed. From your voice-over only.")
EXTRA_CARDS[OCEAN] = ("\u25C9", "Sea predators, drawn and explained", "Your voice-over", "Ocean animals, 'what scares X', deep-sea lists")


# Toon Tales (ui/toon_tales_section.py, toontales/): appended here so nothing above changes
TOON_TALES = "Toon Tales"
STANDALONE = STANDALONE + (TOON_TALES,)
GROUPS = tuple((title, names + (TOON_TALES,) if title == "Stories" else names) for title, names in GROUPS)
EXTRA_BLURBS[TOON_TALES] = ("Walt and Pip, two flat cartoon puppets, act out a ~40 s 'How X worked' Short on painted places that change with the "
                            "story: hook card, punch-ins, yellow key-word captions, sweat/sparkle/anger reactions, a WAIT break and music that "
                            "follows the beats. From a story plan written with Claude's toon-tales skill; places are painted once with Flow.")
EXTRA_CARDS[TOON_TALES] = ("\u263A", "Cartoon history Shorts with Walt and Pip", "A story plan (plan.json)", "How X worked, cons, hoaxes, trading psychology")


# Game Launch (ui/game_launch_section.py, game_launch/): appended here so nothing above changes
GAME_LAUNCH = "Game Launch"
STANDALONE = STANDALONE + (GAME_LAUNCH,)
GROUPS = tuple((title, names + (GAME_LAUNCH,) if title == "Documentary" else names) for title, names in GROUPS)
EXTRA_BLURBS[GAME_LAUNCH] = ("A big game launch, game vs real life: the official trailers side by side with the real places they copy, a "
                             "satellite map of the game's regions, chapter cards, glitch cuts and a synthwave bed, plus Shorts (one per "
                             "chapter) and a thumbnail. From a scenes CSV and the trailer files; the voice is free.")
EXTRA_CARDS[GAME_LAUNCH] = ("\u25B6", "Game trailers vs the real places", "A scenes CSV + trailer files", "GTA 6 Leonida vs Florida, any game set in a real place")


# Toy Vehicles (ui/toy_vehicles_section.py, toycolors/): appended here so nothing above changes
TOY_VEHICLES = "Toy Vehicles"
STANDALONE = STANDALONE + (TOY_VEHICLES,)
GROUPS = tuple((title, names + (TOY_VEHICLES,) if title == "Kids" else names) for title, names in GROUPS)
EXTRA_BLURBS[TOY_VEHICLES] = ("Bright 3D toy cars and trucks with faces on a toy playground. Songs: one sung verse per colour as a vehicle "
                              "changes colour (surprise egg, paint pour, garage, magic portal, new wheels, convoy). Stories: Zip, Hooky, "
                              "Splash and friends with a narrator and their own voices: stuck in mud, tow, wash, race, ramp jump, flat "
                              "tyre, hide and seek. 720p preview or 1080p final; the voices are free.")
EXTRA_CARDS[TOY_VEHICLES] = ("◉", "3D toy vehicles: colour songs and stories", "A colour list or a story file", "Colours, vehicles, friendship adventures")


# Kids Stories (ui/kids_stories_section.py, cartoon2d/): appended here so nothing above changes
KIDS_STORIES = "Kids Stories"
STANDALONE = STANDALONE + (KIDS_STORIES,)
GROUPS = tuple((title, names + (KIDS_STORIES,) if title == "Kids" else names) for title, names in GROUPS)
EXTRA_BLURBS[KIDS_STORIES] = ("2D cartoon kids episodes from a story file written for you: Channel 3 play adventures with Ms Lina, "
                              "Tobi, Rosie, Fizz, Pip, Dot, Nia and Poppy (a goal to find, rides, games, songs, a hero who gets "
                              "brave), and Ms Molly learning episodes. Generate voices every line and checks the story; Render "
                              "draws, mixes and exports. The voices are free; no Gemini, no Flow.")
EXTRA_CARDS[KIDS_STORIES] = ("\u263A", "2D cartoon kids stories", "A story file (.kidstory)", "Play adventures, lost-and-found quests, learning songs")

# Stickman (ui/stickman_section.py, stickman/): appended here so nothing above changes
STICKMAN = "Stickman"
STANDALONE = STANDALONE + (STICKMAN,)
GROUPS = tuple((title, names + (STICKMAN,) if title == "Explainers" else names) for title, names in GROUPS)
EXTRA_BLURBS[STICKMAN] = ("Faceless stickman explainers drawn in code: two stick figures act out every spoken line with 40 poses, 77 "
                          "props and 8 places picked from the words, spoken-word captions, a calm bed and effects. Five looks (Ink "
                          "Paper, Chalk Dark, Colour Pop, Retro TV, Night Thriller), 16:9 or a native 9:16 Short. From a script, a "
                          "Stickman CSV, or both; the voice is free.")
EXTRA_CARDS[STICKMAN] = ("\u2659", "Stickman explainers and Shorts", "A script or a Stickman CSV", "Habits, money, psychology, 'why you...' explainers")


# Prepper Host (ui/prepper_host_section.py, prepper_host/): appended here so nothing above changes
PREPPER_HOST = "Prepper Host"
STANDALONE = STANDALONE + (PREPPER_HOST,)
GROUPS = tuple((title, names + (PREPPER_HOST,) if title == "Explainers" else names) for title, names in GROUPS)
EXTRA_BLURBS[PREPPER_HOST] = ("A talking-host prepper explainer, 'the exact cart I'd buy': the same AI host in every picture (Flow keeps his "
                              "face), split screen, a round host cam over b-roll, camera moves, product photo cards that pop in, math "
                              "rows that count up, checklists, bars, big numbers, chapter bumpers, his name bar and a thumbnail. "
                              "From a Prepper Host CSV or a script; the voice is free.")
EXTRA_CARDS[PREPPER_HOST] = ("\u2302", "Talking-host prepper explainers", "A Prepper Host CSV or a script",
                             "90 days without power, what to buy, store carts, emergency food and water")


# Food Files (ui/foodfiles_section.py, foodfiles/): appended here so nothing above changes
FOOD_FILES = "Food Files"
STANDALONE = STANDALONE + (FOOD_FILES,)
GROUPS = tuple((title, names + (FOOD_FILES,) if title == "Explainers" else names) for title, names in GROUPS)
EXTRA_BLURBS[FOOD_FILES] = ("A host-led countdown of real food stories, 'The Deadliest Candy Ever Sold': the same AI host (Theo) in every "
                            "clip, speaking his own lines in his Flow voice, #N item cards, maps that light up the place, rubber stamps, "
                            "case folders, headlines, big numbers that count up, flat icon explainers and word captions. From a Food "
                            "Files CSV or a script.")
EXTRA_CARDS[FOOD_FILES] = ("\u26a0", "Deadliest-food countdowns", "A Food Files CSV or a script",
                           "Deadliest candy, snacks, energy drinks, recalls, banned foods, chains that destroyed themselves")


# PK (ui/pk_section.py): the Normal video engine with the Pakistan documentary recipe (Hybrid graphics + sound, CSV graphics, English
# on-screen text for Urdu narration, levelled voice and music); appended here so nothing above changes
from . import pk_section as _pk

PK = _pk.STYLE
BUILT_ON[PK] = "Normal video"
GROUPS = tuple((title, tuple(x for n in names for x in ((n, PK) if n == "Normal video" else (n,)))) for title, names in GROUPS)
EXTRA_BLURBS[PK] = _pk.BLURB
EXTRA_CARDS[PK] = _pk.CARD
