"""Footage acquisition for Health Cinema through the app's own AssetManager (no downloader, Flow client or manifest of our own).

`make_acquirer(build_manager)` returns acquire(rows) -> {scene_no: record}. `build_manager(images_dir, rows)` is the app's `_build_asset_manager`
(Pexels/Pixabay/Openverse, YouTube, Archive, NASA, local, and Flow providers exactly as the user has configured them). Rows are only ever
stock_video or youtube_video here: Flow (credits) is never requested unless the caller passes allow_flow=True after the user opted in.
Results are read back from the shared manifest (<Images>/.asset_manifest.json) so source/provider/author/url provenance is the app's own."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

ALLOWED = {"stock_video", "youtube_video", "archive_video", "nasa_video"}

def rows_for(dscenes_by_no: Dict[int, dict], allow_youtube: bool, allow_flow: bool) -> List:
    """SceneRows (the app's own type) for the scenes that want footage, coerced to what the user allowed."""
    from providers.base import SceneRow
    rows = []
    for no, d in dscenes_by_no.items():
        sc = d["scene"]; at = d["asset_type"]
        if at in ("video", "flow_video") and not allow_flow: at = "stock_video"
        if at == "youtube_video" and not allow_youtube: at = "stock_video"
        if at in ("image", "flow_image", "stock_image"): at = "stock_video"
        if at not in ALLOWED and not (at in ("video", "flow_video") and allow_flow): at = "stock_video"
        sc.asset_type = at; row = sc.to_scene_row(); row.scene_number = str(no)
        if not (row.stock or row.prompt): row.stock = d.get("description") or d.get("narration", "")[:80]
        rows.append(row)
    return rows

def make_acquirer(build_manager: Callable, images_dir: Path, log: Callable[[str], None] = lambda m: None, cancel: Optional[Callable[[], bool]] = None) -> Callable:
    def acquire(rows: List) -> Dict[int, dict]:
        if not rows: return {}
        images_dir.mkdir(parents=True, exist_ok=True)
        mgr = build_manager(images_dir, rows)
        if cancel is not None:
            import threading
            stop = threading.Event()
            def watch():
                while not stop.wait(0.3):
                    if cancel():
                        try: mgr.request_cancel()
                        except Exception: pass
                        return
            threading.Thread(target=watch, daemon=True, name="hc-asset-cancel").start()
        try:
            summary = mgr.resolve_all(rows)
        finally:
            if cancel is not None: stop.set()
        from asset_manager import AssetManifest
        man = AssetManifest(images_dir); out: Dict[int, dict] = {}
        for r in rows:
            no = int(r.scene_number); rec = man.get(r.scene_number) or {}
            p = rec.get("local_path") or ""
            ok = rec.get("status") == "complete" and p and Path(p).is_file()
            out[no] = {"ok": bool(ok), "path": p if ok else "", "source": rec.get("source", ""), "provider": rec.get("provider", ""), "asset_id": rec.get("provider_asset_id", ""),
                       "author": rec.get("author", ""), "source_url": rec.get("source_url", ""), "query": rec.get("stock_query") or rec.get("prompt") or "", "error": rec.get("error") or "",
                       "type": rec.get("type", "")}
        return out
    return acquire

def settings_stock_manager(settings: dict):
    """Headless stand-in for the app's `_build_asset_manager` (stock only: keys from settings/env). Used by tests and the CLI, never by the app."""
    import os
    from asset_manager import AssetManager
    from providers.stock.factory import build_stock_provider
    def build(images_dir: Path, rows):
        sp = build_stock_provider(images_dir, pexels_api_key=settings.get("pexels_api_key") or os.environ.get("PEXELS_API_KEY", ""),
                                  pixabay_api_key=settings.get("pixabay_api_key") or os.environ.get("PIXABAY_API_KEY", ""), include_openverse=True)
        return AssetManager(images_dir, stock_provider=sp, log=print, settings=settings)
    return build
