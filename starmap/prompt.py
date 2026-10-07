"""The StarMap beat-plan prompt (composition_styles/starmap_beats_prompt.txt), filled in: the mission pack's vocabulary, and
optionally the script. Its worked example is the shipped sample (starmap/samples/apollo11_beats.csv) word for word; a test keeps
them the same."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .catalog import Catalog

PACK_PLACEHOLDER = "<<<MISSION PACK>>>"


def prompt_path() -> Path:
    """composition_styles/starmap_beats_prompt.txt (inside the packaged app when frozen)."""
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "composition_styles" / "starmap_beats_prompt.txt"


def pack_vocabulary(cat: Catalog) -> str:
    lines = []
    p = cat.pack
    if p:
        lines.append(f"Mission pack: {p.get('id', '')} ({p.get('name', '')}). Put {p.get('id', '')} in the plan row's id.")
        lines.append("Events (for the date column): " + ", ".join(f"{k} ({v[:16].replace('T', ' ')} UTC)" for k, v in p.get("events", {}).items()))
        if p.get("met_zero"):
            lines.append(f"Mission time T+0 is {p['met_zero'][:19].replace('T', ' ')} UTC.")
        alias = {}
        for a, c in p.get("craft_aliases", {}).items():
            alias.setdefault(c, []).append(a)
        lines.append("Craft: " + ", ".join(f"{c} ({v.get('label', '')}" + (f"; also {', '.join(alias[c])}" if c in alias else "") + ")" for c, v in p.get("craft", {}).items()))
        lines.append("Paths: " + ", ".join(f"{k} ({v['from']} to {v['to']})" for k, v in p.get("paths", {}).items()))
        lines.append("Orbits: " + ", ".join(f"{k} (around {v['body']})" for k, v in p.get("orbits", {}).items()))
        lines.append("Mission sites: " + ", ".join(f"{k} ({v['body']})" for k, v in p.get("sites", {}).items()))
    else:
        lines.append("No mission pack: leave the plan row's id empty. Dates are ISO dates (e.g. 2024-04-08T18:00:00Z); there are no craft, paths or orbits.")
    other = [f"{k} ({v['body']})" for k, v in sorted(cat.sites.items()) if k not in {s.lower() for s in p.get("sites", {})}]
    lines.append("Other sites: " + ", ".join(other))
    lines.append("Bodies: " + ", ".join(sorted(cat.body_ids)) + " (and earth+moon as a pair)")
    return "\n".join(lines)


def build_prompt(pack: Optional[str] = None, script: Optional[str] = None) -> str:
    text = prompt_path().read_text(encoding="utf-8")
    text = text.replace(PACK_PLACEHOLDER, pack_vocabulary(Catalog(pack)))
    if script:
        text = text.replace("<<<PASTE THE SCRIPT HERE>>>", script.strip())
    return text
