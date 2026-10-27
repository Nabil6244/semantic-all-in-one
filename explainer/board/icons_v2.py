"""Tile pictures for the "scenes v2" pack (opt-in). `register()` adds `pic:<name>` ids to the board icon registry (board/icons.py is not edited): each picture is the pack's prop drawn
into the 100 x 100 icon box, so it works wherever an icon asset is accepted (cards, tiles, circles). A missing or damaged pack draws a plain role-coloured rounded square instead of stopping.

    register()  ->  list of the ids added (idempotent); ids() ->  the ids the pack would add."""

from __future__ import annotations

from typing import Callable, List

from PIL import Image

from . import icons as I

NAMES = ("coin_stack", "gold_bars", "vault_door", "folder", "letter", "train", "truck", "tank", "plane", "ship", "barbed_wire", "border_post", "radio", "lantern", "map_table")


def ids() -> List[str]:
    return [f"pic:{n}" for n in NAMES]


def _picture(name: str) -> Callable:
    def draw(d, c, o, w):
        try:
            from ..cartoon import kit_v2
            im = kit_v2.prop_full(name)
            k = d.k
            box = 88 * k                                                        # leave a margin inside the 100-unit box
            s = min(box / im.width, box / im.height)
            sp = im.resize((max(2, round(im.width * s)), max(2, round(im.height * s))), Image.LANCZOS)
            target = d.d._image
            target.alpha_composite(sp, (round((100 * k - sp.width) / 2), round((100 * k - sp.height) / 2)))
        except Exception:                                                       # never stop: a neutral stand-in square
            d.rounded_rectangle([14, 14, 86, 86], radius=12, fill=c, outline=o, width=w)
    return draw


def register() -> List[str]:
    added = []
    for n in NAMES:
        key = f"pic:{n}"
        if key not in I.ICONS:
            I.ICONS[key] = _picture(n)
            added.append(key)
    return added
