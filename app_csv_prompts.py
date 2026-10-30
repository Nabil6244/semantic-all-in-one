"""The copyable CSV prompt for each style ("Copy the CSV prompt" in every style's panel).

Each prompt file in composition_styles/ teaches an AI the exact CSV that style's importer reads (test_csv_prompts.py loads
every prompt's own example through the real importer). The prompt ends with SCRIPT_PLACEHOLDER; when the user has a script,
it is put there, so one paste into any AI is enough.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

SCRIPT_PLACEHOLDER = "<<<PASTE THE SCRIPT HERE>>>"
TEMPLATE_PLACEHOLDER = "<<<TEMPLATE CATALOG>>>"      # What If: its template library; pakMap: the universal gfx-core templates

# style -> prompt file in composition_styles/
CSV_PROMPTS = {
    "normal": "normal_csv_prompt.txt",
    "overscaled": "overscaled_csv_prompt.txt",
    "exp_solar": "exp_solar_csv_prompt.txt",
    "pakmap": "pakmap_csv_prompt.txt",
    "hybrid": "hybrid_beats_prompt.txt",
    "starmap": "starmap_beats_prompt.txt",
    "whatif": "whatif_csv_prompt.txt",
    "enoch_template": "enoch_template_csv_prompt.txt",
    "explainer_scenes": "explainer_scene_csv_prompt.txt",
    "health_cinema": "health_cinema_csv_prompt.txt",
}

# the prompts of the styles that can use the universal graphics (gfx-core templates): the longer text, with the template list and an example row,
# is used only when the graphics switch is on (Settings > Graphics "Doc Style"); with it off the prompt is exactly the one the style always had
CSV_PROMPTS_GRAPHICS = {
    "pakmap": "pakmap_csv_prompt_graphics.txt",
    "hybrid": "hybrid_beats_prompt_graphics.txt",
}

STYLE_NAMES = {"normal": "Normal", "overscaled": "Overscaled", "exp_solar": "Exp Solar", "pakmap": "pakMap", "hybrid": "Hybrid Map", "starmap": "StarMap", "whatif": "What If",
               "enoch_template": "Enoch Template", "explainer_scenes": "Explainer scenes", "health_cinema": "Health Cinema"}


def prompt_path(style: str, graphics: bool = False) -> Path:
    """The prompt file of a style (inside the packaged app when frozen); the graphics variant when asked for and the style has one."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    name = CSV_PROMPTS_GRAPHICS.get(style) if graphics else None
    return base / "composition_styles" / (name or CSV_PROMPTS[style])


def build_prompt(style: str, script: Optional[str] = None, *, pack: Optional[str] = None, graphics: bool = False) -> str:
    """The prompt text, with the script in place of the placeholder when one is given (else the placeholder stays, for
    the user to replace). StarMap's prompt also lists what the chosen mission pack lets the CSV name (starmap/prompt.py)."""
    if style == "starmap":
        from starmap.prompt import build_prompt as starmap_prompt

        return starmap_prompt(pack or None, (script or "").strip() or None)
    text = prompt_path(style, graphics).read_text(encoding="utf-8")
    if style in ("pakmap", "hybrid") and TEMPLATE_PLACEHOLDER in text:
        from gfx_templates import catalog_text as gfx_catalog      # the universal graphics, listed from gfx-core/templates

        text = text.replace(TEMPLATE_PLACEHOLDER, "\n".join("  " + ln for ln in gfx_catalog("map", footage=(style == "hybrid" and graphics)).splitlines()))
    if style == "whatif" and TEMPLATE_PLACEHOLDER in text:
        from whatif.templates import catalog_text      # the template list comes from the template files, so it is never out of date

        text = text.replace(TEMPLATE_PLACEHOLDER, catalog_text())
    script = (script or "").strip()
    if script:
        text = text.replace(SCRIPT_PLACEHOLDER, script)
    return text
