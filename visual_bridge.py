"""The Visuals tab for styles that render from their own page (Health Cinema, Rep Theory, Product Trailer).

pakMap, Hybrid, StarMap, Weather and What If each fill the shared Visual Plan table themselves (app._scene_rows + app._scene_rows_owner) and
point the table's actions at their own asset folder. This module does the same for any other style in one place:

    fill(app, owner, rows)      the style's asset requests (SceneRow) into the table; state comes back from the style's own manifest.
                                The rows are saved with the project, so restore(app, owner) shows them again when the style is picked
    clear(app, owner)           the style steps aside: its rows leave the table
    owns(app)                   the table holds the rows of the style that is active now (the Normal CSV refresh must leave them alone)
    images_dir(app)             the asset folder the table's actions (Retry / Change source / Local clip / Skip) write to for that style
    rows(app, owner)            the table's rows, when that style owns them (what its Render uses)
    records(folder, rows)       the finished files the table holds, by scene number: {no: {"ok", "path", "source", ...}}

A style generates its assets into its folder through the app's AssetManager, fills the table, and on Render reads `records` for the rows the
table holds: whatever the user changed there is what the video uses. Nothing here starts work; it only lists and reads."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


def _hc_dir(ws) -> Path:
    return Path(ws.root) / "state" / "health_cinema" / "assets"


def _rt_dir(ws) -> Path:
    return Path(ws.root) / "state" / "rep_theory" / "assets"


def _pt_dir(ws) -> Path:
    return Path(ws.root) / "state" / "product_trailer" / "assets"


# owner -> (the app flag that says the style is the active one, its asset folder in a project)
OWNERS: Dict[str, Tuple[str, Callable]] = {
    "health_cinema": ("_health_active", _hc_dir),
    "reptheory": ("_rt_active", _rt_dir),
    "product_trailer": ("_pt_active", _pt_dir),
}


def _scene_key(scene_number) -> str:   # the table's own key (app._scene_key): "001"
    try:
        return f"{int(str(scene_number).strip()):03d}"
    except ValueError:
        return str(scene_number).strip()


def folder(owner: str, ws) -> Path:
    return OWNERS[owner][1](ws)


def owns(app) -> bool:
    owner = getattr(app, "_scene_rows_owner", None)
    return owner in OWNERS and bool(getattr(app, OWNERS[owner][0], False))


def images_dir(app) -> Optional[Path]:
    if not owns(app) or getattr(app, "_workspace", None) is None:
        return None
    return folder(app._scene_rows_owner, app._workspace)


def rows(app, owner: str) -> List:
    return list(getattr(app, "_scene_rows", []) or []) if getattr(app, "_scene_rows_owner", None) == owner else []


def fill(app, owner: str, scene_rows: List) -> None:
    """Main thread only. The style's requests become the table's rows (one per asset); their state is read from the style's manifest."""
    keep = {_scene_key(r.scene_number) for r in scene_rows}
    app._scene_rows = list(scene_rows)
    app._scene_rows_owner = owner
    app._scene_preview_cache_sig = None
    app._asset_results = {k: v for k, v in getattr(app, "_asset_results", {}).items() if k in keep}
    if getattr(app, "_workspace", None) is not None:
        save(folder(owner, app._workspace), scene_rows)
        app._hydrate_overscaled_assets_from_manifest(folder(owner, app._workspace))
    app._render_scene_rows()
    app._refresh_assets_cta()


def restore(app, owner: str) -> bool:
    """The style was picked again (or the project reopened): its saved rows back in the table. False when it has none yet."""
    if getattr(app, "_workspace", None) is None:
        return False
    saved = load(folder(owner, app._workspace))
    if not saved:
        return False
    fill(app, owner, saved)
    return True


def save(images_dir: Path, scene_rows: List) -> None:
    import dataclasses, json

    try:
        Path(images_dir).mkdir(parents=True, exist_ok=True)
        data = [dataclasses.asdict(r) for r in scene_rows]
        (Path(images_dir) / "visual_plan.json").write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:
        pass   # the table still works; it only is not shown again after a restart


def load(images_dir: Path) -> List:
    import dataclasses, json
    from providers.base import SceneRow

    try:
        data = json.loads((Path(images_dir) / "visual_plan.json").read_text(encoding="utf-8"))
        names = {f.name for f in dataclasses.fields(SceneRow)}
        return [SceneRow(**{k: v for k, v in d.items() if k in names}) for d in data if isinstance(d, dict)]
    except Exception:
        return []


def clear(app, owner: str) -> None:
    if getattr(app, "_scene_rows_owner", None) != owner:
        return
    app._scene_rows_owner = None
    app._scene_rows = []
    app._scene_preview_cache_sig = None
    try:
        app._render_scene_rows()
    except Exception:
        pass


def record_of(rec: dict) -> dict:
    """A manifest record in the shape the styles' engines use."""
    p = rec.get("local_path") or ""
    ok = rec.get("status") == "complete" and bool(p) and Path(p).is_file()
    return {"ok": bool(ok), "path": p if ok else "", "source": rec.get("source", ""), "provider": rec.get("provider", ""), "asset_id": rec.get("provider_asset_id", ""),
            "author": rec.get("author", ""), "source_url": rec.get("source_url", ""), "query": rec.get("stock_query") or rec.get("prompt") or "",
            "error": rec.get("error") or "", "type": rec.get("type", ""), "user_override": bool(rec.get("user_override") or rec.get("source") == "manual"),
            "qa": {k: (rec.get("visual_qa") or {}).get(k) for k in ("semantic_match", "vision_used", "overall_score", "status")}}


def records(images_dir: Path, scene_rows: List) -> Dict[int, dict]:
    """The finished files the table holds for these rows (failed / missing rows are left out), each with the row's own text as `narration`."""
    from asset_manager import AssetManifest

    if not scene_rows or not Path(images_dir).is_dir():
        return {}
    man = AssetManifest(Path(images_dir))
    out: Dict[int, dict] = {}
    for r in scene_rows:
        try:
            no = int(str(r.scene_number))
        except ValueError:
            continue
        rec = record_of(man.get(str(r.scene_number)) or {})
        if rec["ok"]:
            out[no] = dict(rec, narration=str(getattr(r, "script_segment", "") or ""))
    return out


def seed(images_dir: Path, scene_number: str, path: str, source: str, *, prompt: str = "", stock: str = "", provider: str = "") -> None:
    """A file a style made itself, filed in its manifest as that scene's finished asset (so the Visuals tab shows it and its actions work on it).
    A file the user chose in the Visuals tab (user_override / Local clip) is never overwritten."""
    from asset_manager import AssetManifest

    if not path or not Path(path).is_file():
        return
    Path(images_dir).mkdir(parents=True, exist_ok=True)
    man = AssetManifest(Path(images_dir))
    old = man.get(str(scene_number)) or {}
    if old.get("status") == "complete" and (old.get("user_override") or old.get("source") == "manual"):
        return
    kind = "video" if Path(path).suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".m4v") else "image"
    man.set(str(scene_number), {"scene_number": str(scene_number), "status": "complete", "source": source, "type": kind, "local_path": str(path),
                                "prompt": prompt, "stock_query": stock, "provider": provider})


def snapshot(images_dir: Path, scene_rows: List) -> Dict[int, str]:
    """{scene no: file} the table holds now: compared later to tell whether the user changed anything there."""
    return {no: rec["path"] for no, rec in records(images_dir, scene_rows).items()}
