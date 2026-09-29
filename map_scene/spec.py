"""Map prompt format (same in normal, Overscaled and Exp Solar CSVs):

    Florida > Florida Panhandle > Eglin Air Force Base | camera: zoom_out | label: FIRST CAPITAL

Big to small: parent area > focus area > inner area. Only the focus is
required. Options after ``|``: camera (zoom_in, zoom_out, drift), label,
style (dark, natural).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CAMERAS = ("zoom_in", "zoom_out", "drift")
_WORLD_WORDS = frozenset({"world", "the world", "earth", "the earth", "globe", "the globe", "planet earth"})
STYLES = ("dark", "natural")


class MapPromptError(ValueError):
    pass


@dataclass
class MapSpec:
    focus: str
    parent: Optional[str] = None
    inner: Optional[str] = None
    label: Optional[str] = None
    camera: str = "zoom_in"
    style: str = "dark"

    @property
    def label_text(self) -> str:
        return (self.label or self.focus).strip().upper()


def parse_map_prompt(prompt: str) -> MapSpec:
    text = (prompt or "").strip()
    if not text:
        raise MapPromptError("Map prompt is empty — write at least the place to show, e.g. 'Florida > Florida Panhandle'.")
    places_part, *option_parts = [p.strip() for p in text.split("|")]
    places = [p.strip() for p in places_part.split(">") if p.strip()]
    # "World > Africa": the whole world isn't a mappable area and adds nothing
    # as a wider level, so it is simply left out.
    places = [p for p in places if p.strip().lower() not in _WORLD_WORDS]
    if not places:
        raise MapPromptError(
            f"Map prompt has no place: {prompt!r}. Name a continent, country or smaller area (e.g. 'Africa').")
    if len(places) > 3:
        raise MapPromptError(f"Map prompt has more than three levels (parent > focus > inner): {prompt!r}")
    if len(places) == 1:
        spec = MapSpec(focus=places[0])
    elif len(places) == 2:
        spec = MapSpec(parent=places[0], focus=places[1])
    else:
        spec = MapSpec(parent=places[0], focus=places[1], inner=places[2])
    for option in option_parts:
        if not option:
            continue
        key, sep, value = option.partition(":")
        key, value = key.strip().lower(), value.strip()
        if not sep or not value:
            raise MapPromptError(f"Map option {option!r} should look like 'camera: zoom_out'.")
        if key == "camera":
            if value.lower() not in CAMERAS:
                raise MapPromptError(f"Unknown camera {value!r}; use one of {', '.join(CAMERAS)}.")
            spec.camera = value.lower()
        elif key == "style":
            if value.lower() not in STYLES:
                raise MapPromptError(f"Unknown style {value!r}; use one of {', '.join(STYLES)}.")
            spec.style = value.lower()
        elif key == "label":
            spec.label = value
        else:
            raise MapPromptError(f"Unknown map option {key!r}; use camera, label or style.")
    return spec
