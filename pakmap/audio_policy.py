"""Which audio systems may play for which video mode (Phase 7).

pakMap owns its sound design. While a pakMap video renders, the generic Smart-Editing sound effects, the generic
scene ambience and the zoom-blur transition sound are off; and nothing pakMap-specific is ever active for the
other styles. ``None`` means "follow the user's global setting" (the style's own behaviour is untouched)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

MODES = ("pakmap", "overscaled", "exp_solar", "map_facts", "other")


@dataclass(frozen=True)
class AudioPolicy:
    narration: bool = True
    pakmap_sfx: bool = False
    pakmap_ambience: bool = False
    generic_sfx: Optional[bool] = None
    generic_ambience: Optional[bool] = None
    zoom_blur_sound: Optional[bool] = None


PAKMAP_POLICY = AudioPolicy(narration=True, pakmap_sfx=True, pakmap_ambience=True, generic_sfx=False, generic_ambience=False, zoom_blur_sound=False)


def policy_for(mode: str, sound_design: bool = True) -> AudioPolicy:
    """``sound_design`` is pakMap's own switch; it never touches the generic flags (those stay off for pakMap)."""
    if mode == "pakmap":
        return PAKMAP_POLICY if sound_design else replace(PAKMAP_POLICY, pakmap_sfx=False, pakmap_ambience=False)
    return AudioPolicy()


def generic_flags_for(mode: str, user: Dict[str, bool]) -> Dict[str, bool]:
    """The generic audio flags a render of ``mode`` should use, given the user's global settings (not mutated)."""
    pol = policy_for(mode)
    out = dict(user)
    for key, forced in (("sound_effects", pol.generic_sfx), ("scene_ambience", pol.generic_ambience), ("zoom_blur_sound", pol.zoom_blur_sound)):
        if forced is not None:
            out[key] = forced
    return out
