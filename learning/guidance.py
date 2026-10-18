"""Runtime, style-scoped guidance for the user's external CSV workflow. Never edits a template file or an imported CSV.

* ``guidance_text(scope)``: a short, clearly marked block built ONLY from the validated active package of exactly that scope.
* ``offer_guidance(app, prompt, style)``: called when the CSV prompt is copied. If a package exists the user sees the block and
  chooses whether to append it; with no package nothing is shown and the prompt is returned unchanged.
* ``advisories(scope, structure)``: non-blocking import-time notes, only from approved asset_type_failure rules with enough
  evidence that match the imported CSV's own asset types.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import packages
from .assets import canonical_source, csv_sources
from .scope import resolve_scope

MARKER = "--- Learned guidance (advisory"
MAX_SHOWN = 5
MIN_EVIDENCE_FOR_WARNING = 8
MIN_CONFIDENCE_FOR_WARNING = 0.6
_STYLE_MODE = {"normal": "normal", "enoch_template": "normal", "overscaled": "overscaled", "exp_solar": "overscaled",
               "pakmap": "pakmap", "hybrid": "hybrid", "starmap": "starmap", "whatif": "whatif", "weather": "weather"}


def guidance_text(scope: str, root=None) -> str:
    pkg = packages.active_package(scope, root)
    if not pkg or not pkg["rules"]:
        return ""
    rules = sorted(pkg["rules"], key=lambda r: (-r["confidence"], r["id"]))[:MAX_SHOWN]
    lines = [f"{MARKER}, from {len(pkg['rules'])} reviewed rule(s) for {scope}, v{pkg['version']}) ---"]
    lines += [f"- {r['text']}" for r in rules]
    lines.append("--- end of learned guidance ---")
    return "\n".join(lines)


def apply_to_prompt(base: str, scope: str, root=None) -> str:
    g = guidance_text(scope, root)
    if not g or MARKER in base:
        return base
    return base.rstrip("\n") + "\n\n" + g + "\n"


def offer_guidance(app: Any, prompt: str, style: str) -> str:
    mode = _STYLE_MODE.get(style, "normal")
    scope = resolve_scope(app, mode)
    if mode == "weather" and scope.endswith("/default"):
        # Weather's editing style lives in its own panel: use the scope of this project's latest Weather import, if any
        try:
            from . import ledger as _l
            pid = getattr(getattr(app, "_workspace", None), "project_id", None)
            for e in (_l.default_ledger().events(event_type="csv_import", project_id=pid, newest_first=True, limit=20) if pid else []):
                if e["style_scope"].startswith("weather/"):
                    scope = e["style_scope"]
                    break
        except Exception:
            pass
    g = guidance_text(scope)
    if not g or MARKER in prompt:
        return prompt
    from tkinter import messagebox
    if messagebox.askyesno("Learned guidance for this style",
                           g + "\n\nAdd this advisory block to the copied prompt?\n(No: copy the original prompt unchanged.)"):
        return apply_to_prompt(prompt, scope)
    return prompt


def advisories(scope: str, structure: Dict[str, Any], root=None) -> List[str]:
    pkg = packages.active_package(scope, root)
    if not pkg:
        return []
    present = csv_sources(scope, (structure.get("asset_types") or {}))
    out = []
    for r in pkg["rules"]:
        if (r["kind"] == "asset_type_failure" and canonical_source(r["asset_type"]) in present and r["evidence_count"] >= MIN_EVIDENCE_FOR_WARNING
                and r["confidence"] >= MIN_CONFIDENCE_FOR_WARNING):
            out.append(f"{r['text']} (based on {r['evidence_count']} observations in {scope}; you can ignore this)")
    return out[:3]


def log_advisories(app: Any, scope: str, structure: Dict[str, Any]) -> None:
    try:
        for line in advisories(scope, structure):
            app._append_log(f"[LEARNING] {line}\n")
    except Exception:
        pass
