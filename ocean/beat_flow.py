"""Flow illustrations for Ocean beat mode (ocean/beats.py): one picture per `picture` beat, in the channel's illustration
look (beats.STYLE, already in each slot's query), filed in the Visuals tab as that beat's finished asset, the same way
War files its flow_image rows, so the user can review, Retry or Change source there before Render.

    make(slots, images_dir, log, manager, should_stop) -> {beat_no: path}   pictures already in the tab are kept
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence


def make(slots: Sequence[Dict[str, Any]], images_dir: Path, log: Callable[[str], None] = print, manager: Any = None,
         should_stop: Optional[Callable[[], bool]] = None, mode: Optional[str] = None,
         account_ids: Optional[Sequence[str]] = None) -> Dict[str, str]:
    """mode: the app's Flow image mode ("agent" = up to ~14 pictures per request on the Video Profile's accounts, the app's
    "Fast Flow images" switch; "ui" / "rpc" = one picture per request). None reads the app's saved settings."""
    import visual_bridge
    from asset_manager import AssetManifest
    from providers.base import SceneRow
    from providers.flow.engine_manager import FlowEngineManager
    from providers.flow.provider import FlowProvider

    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Any] = []
    for s in slots:
        if s.get("kind") not in ("picture", "act"):
            continue
        r = SceneRow(scene_number=str(s["scene_no"]), script_segment=str(s.get("text", "")), asset_type="image",
                     prompt=str(s["query"]))
        held = AssetManifest(images_dir).get(str(r.scene_number)) or {}
        from .clips import green_screen
        lp = str(held.get("local_path") or "")
        stale = held.get("source") == "flow_image" and (held.get("prompt") != r.prompt or (lp and Path(lp).is_file() and green_screen(lp)))
        if visual_bridge.records(images_dir, [r]) and not stale:
            continue                                   # already made for this prompt (or the user's own pick): kept
        rows.append(r)
    if not rows:
        return {}
    log(f"Flow: {len(rows)} beat picture(s) in the illustration look (free images)…")
    if mode is None:                                     # headless: the app's own saved choice (Settings -> Flow)
        mode, saved_accounts = _saved_mode()
        account_ids = account_ids or saved_accounts
    mgr = manager or FlowEngineManager(log=log)
    if manager is None:
        mgr.ensure_running()
    fs: Dict[str, Any] = {"model": "GEM_PIX_2", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"}
    if mode:
        fs["generationMode"] = mode
    log(f"Flow mode: {fs.get('generationMode', 'default')}" + (f" on {len(account_ids)} account(s)" if account_ids else ""))
    prov = FlowProvider(mgr, media_kind="image", account_ids=list(account_ids) if account_ids else None, flow_settings=fs)
    tmp = Path(tempfile.mkdtemp(prefix="ocean_beats_"))
    res = dict(prov.resolve_batch(rows, tmp, log=log, should_stop=should_stop) or {})
    for lead in REWORD:                                      # Flow's duplicate guard / a timeout: ask again in other words
        blocked = [r for r in rows if _ledger_blocked(res.get(str(r.scene_number)))]
        if not blocked or (should_stop and should_stop()):
            break
        log(f"Flow: {len(blocked)} beat(s) not made (held or timed out); asking again with a reworded prompt")
        again = [SceneRow(scene_number=r.scene_number, script_segment=r.script_segment, asset_type="image",
                          prompt=lead + r.prompt) for r in blocked]
        res.update(prov.resolve_batch(again, tmp, log=log, should_stop=should_stop) or {})
    man = AssetManifest(images_dir)
    made: Dict[str, str] = {}
    for r in rows:
        got = res.get(str(r.scene_number))
        src = getattr(got, "path", None) if got is not None else None
        if not (src and Path(src).is_file()):
            log(f"beat {r.scene_number}: no picture ({getattr(got, 'error', None) or 'Flow returned nothing'})")
            continue
        no = str(r.scene_number)
        dest = images_dir / (f"{int(no):03d}{Path(src).suffix}" if no.isdigit() else f"{no}{Path(src).suffix}")
        shutil.copyfile(src, dest)
        man.set(no, {"status": "complete", "type": "image", "source": "flow_image", "asset_type": "local", "local_path": str(dest),
                     "prompt": r.prompt, "ai_generated": True, "selection_method": "flow_picture", "credit": "Illustration: Flow",
                     "resolved_at": time.time(), "error": None})
        made[no] = str(dest)
    log(f"Flow: {len(made)} of {len(rows)} beat pictures made" + ("" if len(made) == len(rows) else "; the rest show the animal on the stage"))
    return made


def _saved_mode():
    """(mode, accounts) from the app's settings.json, as the app picks them: agent mode batches on the default Video
    Profile's accounts; otherwise UI mode (default) or RPC on every signed-in account."""
    try:
        from cinematic_explainer.war.flow_pictures import _settings
        s = _settings()
    except Exception:  # noqa: BLE001
        return None, None
    if s.get("flow_agent_images"):
        prof = next((p for p in s.get("video_profiles") or [] if p.get("id") == s.get("default_video_profile_id")), None) or \
            ((s.get("video_profiles") or [None])[0])
        return "agent", (prof or {}).get("account_ids") or None
    return ("ui" if s.get("flow_ui_mode", True) else "rpc"), None


REWORD = ("Wide cinematic scene. ", "Detailed illustrated scene. ")


def _ledger_blocked(result: Any) -> bool:
    err = str(getattr(result, "error", "") or "") if result is not None else ""
    return bool(err) and any(k in err for k in ("may already have been accepted", "already exists on Flow", "already generated",
                                                 "timeout", "did not produce an image"))
