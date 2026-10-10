"""The StarMap beat-plan prompt (composition_styles/starmap_beats_prompt.txt), filled in: the dataset library's vocabulary
(every dataset, its qualified ids and statuses), and optionally the script. Its worked example is the shipped sample
(starmap/samples/apollo11_beats.csv) word for word; a test keeps them the same.

The prompt is for the AI that writes the CSV BEFORE StarMap runs; StarMap itself never calls an AI."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .catalog import Catalog
from .datasets import Dataset, DatasetIndex, norm
from .temporal import show_date

PACK_PLACEHOLDER = "<<<DATASETS>>>"
BODIES_PLACEHOLDER = "<<<BODIES>>>"
FULL_DETAIL_UP_TO = 12            # with more datasets than this, only the ones the script names are listed in full


def prompt_path() -> Path:
    """composition_styles/starmap_beats_prompt.txt (inside the packaged app when frozen)."""
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "composition_styles" / "starmap_beats_prompt.txt"


def _when(ds: Dataset) -> str:
    a, b = ds.years
    return "" if a is None else (f"{a}" if a == b else f"{a}–{b}")


def _event(ds: Dataset, name: str) -> str:
    e = ds.events[name]
    when = show_date(e.utc, e.precision if e.precision in ("day", "month", "year") else "minute", e.net)
    return f"{e.qid} ({when}" + (f", {e.status}" if e.status != "historical" else "") + ")"


def dataset_detail(ds: Dataset) -> List[str]:
    alias = {}
    for a, c in ds.craft_aliases.items():
        alias.setdefault(c, []).append(a)
    bases = sorted({t.basis for t in ds.trajectories.values()})
    head = f"{ds.id} = {ds.name} ({ds.status}" + (f", {_when(ds)}" if _when(ds) else "") + (f", {ds.kind.replace('_', ' ')}" if ds.kind else "") \
        + (f", geometry {'/'.join(bases)}" if bases else "") + (f", as of {ds.as_of[:10]}" if ds.as_of else "") + ")"
    lines = [head]
    if ds.met_zero:
        lines.append(f"  mission time T+0 = {ds.met_zero[:16].replace('T', ' ')} UTC (write {ds.id}.T+HH:MM:SS, or T- before it)")
    if ds.events:
        lines.append("  events: " + ", ".join(_event(ds, n) for n in ds.events))
    if ds.craft:
        lines.append("  craft: " + ", ".join(f"{ds.q(c)} ({v.get('label', '')}" + (f"; also {', '.join(alias[c])}" if c in alias else "") + ")"
                                             for c, v in ds.craft.items()))
    if ds.paths:
        lines.append("  paths: " + ", ".join(f"{ds.q(k)} ({v['from']} to {v['to']})" for k, v in ds.paths.items()))
    if ds.orbits:
        lines.append("  orbits: " + ", ".join(f"{ds.q(k)} (around {v['body']})" for k, v in ds.orbits.items()))
    if ds.sites:
        lines.append("  sites: " + ", ".join(f"{ds.q(k)} ({v['body']})" for k, v in ds.sites.items()))
    if ds.world:
        lines.append("  bodies: " + ", ".join(b["id"] for b in ds.world))
    for t in ds.trajectories.values():
        if t.observed_until:
            lines.append(f"  observed data through {t.observed_until[:10]}" + (f"; estimated up to {t.extrapolate['max_days']} days after" if t.extrapolate else "; nothing after"))
    return lines


def body_names(cat: Catalog) -> str:
    """Every body the catalog knows, by its clearest name, wrapped for the prompt -- generated from the registry
    (starmap/catalog/bodies.json), so a body added there is offered to the AI with no prompt edit. Moons say whose."""
    aliases = cat.bodies.get("aliases", {})
    parents = cat.bodies.get("parent_system", {})
    names = []
    for w in cat.world:
        bid = w["id"]
        cands = [k for k, v in aliases.items() if v == bid and not k.startswith("the ") and "'s moon" not in k and k.isascii()]
        name = max([bid] + cands, key=len)
        names.append(f"{name} (moon of {parents[bid]})" if bid in parents and w.get("kind") == "body" and name != "moon" else name)
    lines, line = [], ""
    for n in names:
        if line and len(line) + len(n) + 2 > 78:
            lines.append(line + ",")
            line = n
        else:
            line = f"{line}, {n}" if line else n
    return ("\n" + " " * 15).join(lines + [line])


def pack_vocabulary(cat: Catalog, script: Optional[str] = None, *, force: Optional[List[str]] = None) -> str:
    """The library for the prompt: a line per dataset, and full detail for all of them (or, in a large library, for the ones
    the script names and any `force`d)."""
    idx: DatasetIndex = cat.index
    many = len(idx.datasets) > FULL_DETAIL_UP_TO
    named = set(idx.narration_matches(script or "")) | {norm(f) for f in (force or []) if f}
    lines = ["DATASETS (found by the app automatically; nothing is selected). Write their contents as qualified ids <dataset>.<name>:"]
    for ds in sorted(idx.datasets.values(), key=lambda d: d.id):
        lines.append(f"- {ds.id}: {ds.name} · {ds.status}" + (f" · {_when(ds)}" if _when(ds) else ""))
    shown = [d for d in sorted(idx.datasets.values(), key=lambda d: d.id) if not many or d.id in named]
    if shown:
        lines.append("")
        lines.append("DETAILS" + (" (the datasets your script names)" if many else "") + ":")
        for ds in shown:
            lines += dataset_detail(ds)
    if not idx.datasets:
        lines.append("(none: dates are ISO dates; there are no craft, paths or orbits)")
    lines.append("")
    lines.append("Shared sites (any video): " + ", ".join(f"{k} ({v['body']})" for k, v in sorted(cat.sites.items())))
    lines.append("Bodies: " + ", ".join(sorted(cat.body_ids)) + " (and pairs such as earth+moon)")
    return "\n".join(lines)


def short_prompt_path() -> Path:
    """composition_styles/starmap_short_prompt.txt (inside the packaged app when frozen)."""
    return prompt_path().with_name("starmap_short_prompt.txt")


def build_prompt(pack: Optional[str] = None, script: Optional[str] = None) -> str:
    """The prompt with the library's vocabulary and the script. `pack` (old callers) only makes sure that dataset is listed
    in full."""
    cat = Catalog()
    if script and script.strip() and not pack and not cat.index.narration_matches(script):
        # a story about space itself (a moon, a planet, the scale of things) that names no built-in mission: the short
        # prompt, with only the rows such a story needs, so the CSV it brings back loads without errors
        text = short_prompt_path().read_text(encoding="utf-8")
        return text.replace(BODIES_PLACEHOLDER, body_names(cat)).replace("<<<PASTE THE SCRIPT HERE>>>", script.strip())
    text = prompt_path().read_text(encoding="utf-8")
    text = text.replace(BODIES_PLACEHOLDER, body_names(cat))
    text = text.replace(PACK_PLACEHOLDER, pack_vocabulary(cat, script, force=[pack] if pack else None))
    if script:
        text = text.replace("<<<PASTE THE SCRIPT HERE>>>", script.strip())
    return text
