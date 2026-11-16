"""Aviation adapter for Wall Moments (docs/wall/PLAN.md, Phase 3): Aviation's own layer lists for the shared wall/adapter.py.

    planner_input(shots, layers, scenes) -> (wall scenes, wall shots, blocks)
    apply(shots, layers, scenes, words, *, pct=20, work=None, log=print) -> (layers, report)
        the scenes the wall planner picks lose their card / stage / source-tag layers and get one "wall.lay_wall" layer instead;
        the clips before and after become the wall's entry and exit prints. Base shots are not touched (the wall layer is opaque
        over them). report = {"segments": [{start, end, scenes, closing}], "share", "spans", "cues": [(t, sound)], "plan"}
Nothing outside the picked spans changes. Maps (flight map, HUD) and the end card always stay as they are.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence

from wall import adapter as WA

CARD_PREFIXES = ("cards.lay_article", "cards.lay_collage", "dossier.", "gfx_air.", "gfx.lay_counters", "gfx.lay_sheet", "gfx.lay_altitude",
                 "gfx.lay_place_title", "war.lay_document", "stage.lay_stage", "gfx_flight.lay_report")
KEEP_PREFIXES = ("flightmap.", "hud.", "gfx.lay_weather", "gfx.lay_end_card", "gfx_flight.lay_instrument", "gfx_flight.lay_speed_tape",
                 "gfx_air.lay_runway", "gfx_air.lay_approach", "gfx_air.lay_descent", "flir.")
TRANSIENT = ("retention.lay_rehook", "transitions.lay_out", "cards.tag_source")
THEME = "slate"


def _prefixes(names: Sequence[str]) -> tuple:
    """Aviation names its layers 'module.fn': a name ending in '.' is a whole module, else the exact layer or its 'module.fn' prefix."""
    return tuple(n if n.endswith(".") else n + "." for n in names) + tuple(names)


STYLE = WA.Style(card=_prefixes(CARD_PREFIXES), keep=_prefixes(KEEP_PREFIXES), transient=_prefixes(TRANSIENT), theme=THEME, name="Aviation")


def planner_input(shots: Sequence[Any], layers: Sequence[Any], scenes: Sequence[Dict[str, Any]]):
    return WA.planner_input(shots, layers, scenes, STYLE)


def apply(shots: Sequence[Any], layers: Sequence[Any], scenes: Sequence[Dict[str, Any]], words: Any, *, pct: float = 20.0,
          work: Optional[str] = None, log: Callable[[str], None] = lambda m: None, theme: str = THEME):
    style = STYLE if theme == THEME else WA.Style(**{**STYLE.__dict__, "theme": theme})
    return WA.apply(shots, layers, scenes, words, style, pct=pct, work=work, log=log)
