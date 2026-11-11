"""War Documentary: Flow pictures for what no real picture shows (owner 2026-11-12: "we can also generate images with flow to use them in the video").

    make(requests, out_dir, log)  -> {key: path}   requests = {key: prompt}; attaches to the app's running Flow engine (FlowEngineManager reuses
                                                    an engine already on its port), uses the app's saved image settings and accounts.
    credit(...)                   -> the line drawn on a card for such a picture

Rules: every picture is an illustration and is labelled so ('AI illustration · Google Flow' on cards, ai_generated on footage records); never
a real person's likeness (no portraits of named people); the prompt describes the KIND of place or event the narration names, with no text,
logos or flags. Pictures already made (index.json in out_dir) are reused, never generated twice.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Callable, Dict, Optional

STYLE = ("photorealistic documentary photograph, natural colours, realistic lighting, wide establishing shot, 16:9, no text, no letters, "
         "no numbers, no logos, no flags, no watermark, no close-up faces")
CREDIT = "AI illustration · Google Flow"
INDEX = "index.json"


def credit() -> str:
    return CREDIT


def _settings() -> Dict:
    from . import headless as H

    return dict(H.load_settings())


def make(requests: Dict[str, str], out_dir: Path, log: Callable[[str], None] = print) -> Dict[str, str]:
    """{key: picture path} for every request Flow made (or that was made before)."""
    from providers.base import SceneRow
    from providers.flow.engine_manager import FlowEngineManager
    from providers.flow.provider import FlowProvider

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    idx_p = out_dir / INDEX
    try:
        index = json.loads(idx_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {}
    done = {k: v["path"] for k, v in index.items() if k in requests and Path(v.get("path", "")).is_file() and v.get("prompt") == requests[k]}
    todo = {k: p for k, p in requests.items() if k not in done}
    if not todo:
        return done
    s = _settings()
    fs = dict(s.get("flow_settings") or {})
    agent = bool(s.get("flow_agent_images"))
    fs["generationMode"] = "agent" if agent else ("ui" if s.get("flow_ui_mode", True) else "rpc")
    accounts = None
    if agent:
        prof = next((p for p in s.get("video_profiles") or [] if p.get("id") == s.get("default_video_profile_id")), None) or \
            ((s.get("video_profiles") or [None])[0])
        accounts = (prof or {}).get("account_ids") or None
    em = FlowEngineManager(log=log)
    em.ensure_running()
    fp = FlowProvider(em, media_kind="image", account_ids=accounts, flow_settings=fs)
    keys = list(todo)
    rows = [SceneRow(scene_number=str(i + 1), script_segment=k, asset_type="image", prompt=f"{todo[k]}. {STYLE}") for i, k in enumerate(keys)]
    work = out_dir / "_flow_work"
    work.mkdir(exist_ok=True)
    log(f"[war] Flow: {len(rows)} picture(s) to make ({fs.get('generationMode')} mode)")
    res = fp.resolve_batch(rows, work, log=log) or {}
    for i, k in enumerate(keys):
        r = res.get(str(i + 1))
        src = getattr(r, "path", None) if r is not None else None
        if not src or not Path(src).is_file():
            log(f"[war] Flow: no picture for {k}: {getattr(r, 'error', '') if r is not None else 'no result'}")
            continue
        dst = out_dir / (re.sub(r"[^a-z0-9_]+", "_", k.lower()) + Path(src).suffix)
        shutil.copyfile(src, dst)
        index[k] = {"path": str(dst), "prompt": todo[k], "source": "flow", "credit": CREDIT}
        done[k] = str(dst)
    idx_p.write_text(json.dumps(index, indent=1), encoding="utf-8")
    return done
