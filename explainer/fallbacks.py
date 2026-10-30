"""The illustrated version of a picture beat, kept for the moment the picture cannot be had.

The picture pass turns a thin board into a stock picture beat. The board that beat would have been is drawn too (it costs a few seconds), and recorded here under the picture's query. When "Get the
scenes" finds no picture that passes (nothing fetched, or only modern photos for an old story), the fetch step uses this clip instead of stopping the run. A file next to the other Explainer clips
(`fallbacks.json`) and a process-wide table both hold it, so the later Render click finds it. Never raises."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

NAME = "fallbacks.json"
_TABLE = {}


def _key(query: str) -> str:
    return " ".join(str(query or "").lower().split())


def record(out_dir, query: str, clip_path: str) -> None:
    try:
        _TABLE[_key(query)] = str(clip_path)
        if out_dir:
            f = Path(out_dir) / NAME
            data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
            data[_key(query)] = str(clip_path)
            f.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except Exception:
        pass


def lookup(query: str, near=None) -> Optional[str]:
    """The drawn clip for a picture query, from this process or from an `explainer/fallbacks.json` in `near` or one of its three parent folders (the Visual Plan's picture folder)."""
    k = _key(query)
    paths = [_TABLE.get(k)]
    try:
        base = Path(near).resolve() if near else None
        for up in ([base, *list(base.parents)[:3]] if base else []):
            f = up / "explainer" / NAME                  # the project's own folder only: never a sibling project's file
            if f.is_file():
                paths.append(json.loads(f.read_text(encoding="utf-8")).get(k))
    except Exception:
        pass
    return next((p for p in paths if p and Path(p).is_file()), None)
