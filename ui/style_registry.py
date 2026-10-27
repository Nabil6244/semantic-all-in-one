"""The video styles as the picker groups them, plus the styles that exist only as a card (StarMap Cinema: the StarMap engine with
its Cinema option on). Pure data and small helpers, no Tk: app.py keeps STYLE_CHOICES / STYLE_BLURBS / STYLE_CARDS and only adds
what is here."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

# (group title, styles in the order they are shown). A style missing from the app's choices (Weather when it is off) is skipped.
GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("General", ("Normal video", "Modern Tech News", "Overscaled", "Exp Solar")),
    ("Maps", ("pakMap", "Hybrid Map")),
    ("Space", ("StarMap", "StarMap Cinema")),
    ("Explainers", ("What If", "Explainer")),
    ("Documentary", ("War Documentary", "Enoch Template")),
    ("Specialist", ("Health Cinema", "Weather")),
)

STARMAP_CINEMA = "StarMap Cinema"
EXPLAINER = "Explainer"
# card-only style -> the style whose engine it runs (with its look switched on)
BUILT_ON: Dict[str, str] = {STARMAP_CINEMA: "StarMap", EXPLAINER: "Hybrid Map"}

EXTRA_BLURBS: Dict[str, str] = {
    STARMAP_CINEMA: "StarMap with the What If documentary look: diagram plates where the map cannot explain, the spacecraft up close, "
                    "numbers as type, documentary photos with a source line, cuts in the narration's pauses.",
    EXPLAINER: "Explainer videos on a board: drawn clips, a narrator, captions. Planned from your narration (Hybrid Map's engine "
               "with the Explainer look).",
}

# icon, one-line pitch, what it needs, what it suits (the same shape as app.STYLE_CARDS)
EXTRA_CARDS: Dict[str, Tuple[str, str, str, str]] = {
    STARMAP_CINEMA: ("✸", "StarMap with the What If documentary look", "A StarMap beat CSV", "Space stories told like a documentary"),
    EXPLAINER: ("\u270E", "Board clips, a narrator and captions", "Your voiceover", "Explainers on any topic"),
}


def with_extras(choices: Tuple[str, ...]) -> Tuple[str, ...]:
    """The app's choices plus the card-only styles, each right after the style it is built on."""
    out: List[str] = []
    for name in choices:
        out.append(name)
        out.extend(extra for extra, base in BUILT_ON.items() if base == name and extra not in choices)
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
