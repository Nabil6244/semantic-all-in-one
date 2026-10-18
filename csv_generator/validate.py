"""Pre-render validation of a generated plan, using the app's own parsers where they exist."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

# asset_type vocabulary providers.base.SceneRow understands (docstring + from_csv_row)
KNOWN_ASSET_TYPES = frozenset({"image", "video", "flow_image", "flow_video", "stock", "stock_image", "stock_video", "youtube_video",
                               "archive_video", "nasa_video", "commons_video", "commons_image", "map", "local", "local_video", "local_image"})
NEEDS_PROMPT = KNOWN_ASSET_TYPES - {"local", "local_video", "local_image"}
_WORD = re.compile(r"[a-z0-9']+")


@dataclass
class Issue:
    severity: str          # "error" blocks use; "warning" is advisory
    message: str
    scene: Optional[str] = None

    def __str__(self) -> str:
        return f"{'Scene ' + self.scene + ': ' if self.scene else ''}{self.message} [{self.severity}]"


def _words(text: str) -> List[str]:
    return _WORD.findall((text or "").lower())


def validate_rows(rows: Sequence[Mapping[str, Any]], *, columns: Sequence[str], style: str, script: str = "",
                  allowed_asset_types: Optional[Sequence[str]] = None) -> List[Issue]:
    issues: List[Issue] = []
    if not rows:
        return [Issue("error", "The plan has no scenes.")]
    for col in ("scene_number", "script_segment", "asset_type", "prompt"):
        if col not in columns:
            issues.append(Issue("error", f"Missing required column '{col}'."))
    if issues:
        return issues
    seen = set()
    for i, r in enumerate(rows, 1):
        sn = str(r.get("scene_number", "")).strip()
        if sn != str(i):
            issues.append(Issue("error", f"Scene numbers must run 1..n in order (found {sn!r} at position {i}).", sn or None))
        if sn in seen:
            issues.append(Issue("error", "Repeated scene_number.", sn))
        seen.add(sn)
        if not str(r.get("script_segment", "")).strip():
            issues.append(Issue("error", "Empty narration.", sn))
        at = str(r.get("asset_type", "")).strip().lower()
        if at not in KNOWN_ASSET_TYPES:
            issues.append(Issue("error", f"asset_type {at!r} is not one the renderer understands.", sn))
        elif allowed_asset_types is not None and at not in allowed_asset_types:
            issues.append(Issue("error", f"asset_type {at!r} was not enabled for this plan.", sn))
        if at in NEEDS_PROMPT and not str(r.get("prompt", "")).strip():
            issues.append(Issue("error", f"asset_type {at!r} needs a prompt/search query.", sn))
        if len(str(r.get("prompt", ""))) > 600:
            issues.append(Issue("warning", "Very long prompt.", sn))
    if script.strip():       # narration coverage: every script word appears, in order, across the scenes
        want = _words(script)
        got = _words(" ".join(str(r.get("script_segment", "")) for r in rows))
        if got != want:
            missing = len(want) - len(got)
            issues.append(Issue("error", f"The scenes do not reproduce the script exactly ({abs(missing)} word(s) "
                                         f"{'missing' if missing > 0 else 'extra'} or reordered)."))
    # style-specific: the app's own parsers decide
    try:
        dict_rows = [{k: str(v) for k, v in r.items()} for r in rows]
        if style == "overscaled":
            from scene_graph.overscaled_csv import compile_overscaled_csv
            res = compile_overscaled_csv(dict_rows, segment_id="csv_generator", title="")
            issues += [Issue("error", f"Overscaled compiler: {e}") for e in (res.errors or [])]
        elif style == "exp_solar":
            from scene_graph.exp_solar_csv import validate_exp_solar_csv
            issues += [Issue("error", f"Exp Solar: {e}") for e in validate_exp_solar_csv(dict_rows)]
    except Exception as exc:
        issues.append(Issue("warning", f"The style's own parser could not be run ({type(exc).__name__})."))
    return issues
