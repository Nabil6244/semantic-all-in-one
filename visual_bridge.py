"""The Visuals tab for styles that render from their own page (Health Cinema, Rep Theory, Product Trailer, War Documentary).

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


def _war_dir(ws) -> Path:
    return Path(ws.root) / "state" / "war" / "assets"


# owner -> (the app flag that says the style is the active one, its asset folder in a project)
OWNERS: Dict[str, Tuple[str, Callable]] = {
    "health_cinema": ("_health_active", _hc_dir),
    "reptheory": ("_rt_active", _rt_dir),
    "product_trailer": ("_pt_active", _pt_dir),
    "war": ("_war_active", _war_dir),
}


def _rh_dir(ws) -> Path:
    return Path(ws.root) / "state" / "rules_horror" / "assets"


OWNERS["rules_horror"] = ("_rh_active", _rh_dir)   # Rules Horror (ui/rules_horror_section.py)


def _vm_dir(ws) -> Path:
    return Path(ws.root) / "state" / "voxel_map" / "assets"


OWNERS["voxel_map"] = ("_vm_active", _vm_dir)   # Voxel Map photo cards (ui/voxelmap_section.py, voxelmap-engine/cards.py)


def _rc_dir(ws) -> Path:
    return Path(ws.root) / "state" / "roblox_cinema" / "assets"


OWNERS["roblox_cinema"] = ("_rc_active", _rc_dir)   # Roblox Cinema horror picture cards (ui/roblox_cinema_section.py, roblox-cinema-engine/cards.py)


def _av_dir(ws) -> Path:
    return Path(ws.root) / "state" / "aviation" / "assets"


OWNERS["aviation"] = ("_av_active", _av_dir)   # Aviation footage (ui/aviation_section.py, aviation/)


def _oc_dir(ws) -> Path:
    return Path(ws.root) / "state" / "ocean" / "assets"


OWNERS["ocean"] = ("_oc_active", _oc_dir)   # Ocean Predators real clips (ui/ocean_section.py, ocean/clips.py)


def _pc_dir(ws) -> Path:
    return Path(ws.root) / "state" / "podcast_cut" / "assets"


OWNERS["podcast_cut"] = ("_pc_active", _pc_dir)   # Motivation literal stock shots (ui/podcastcut_section.py, podcast_cut/director.py)


def _gl_dir(ws) -> Path:
    return Path(ws.root) / "state" / "game_launch" / "assets"


OWNERS["game_launch"] = ("_gl_active", _gl_dir)   # Game Launch real-life clips (ui/game_launch_section.py, game_launch/)


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


def refresh_soon(app, pictures_dir, ms: int = 1000) -> None:
    """A picture landed: show it in the Visuals tab. Called from a worker thread once per picture; the table is rebuilt at most once
    per ``ms`` (each rebuild re-read the manifest and redrew every row: 100+ pictures froze the window on Windows)."""
    with _SOON_LOCK:
        if getattr(app, "_vb_refresh_pending", False):
            return
        app._vb_refresh_pending = True

    def run():
        with _SOON_LOCK:
            app._vb_refresh_pending = False
        try:
            app._hydrate_overscaled_assets_from_manifest(pictures_dir); app._render_scene_rows(); app._refresh_assets_cta()
        except Exception:
            pass

    try:
        app.after(0, lambda: app.after(ms, run))
    except Exception:
        with _SOON_LOCK:
            app._vb_refresh_pending = False


import threading as _threading
_SOON_LOCK = _threading.Lock()


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


# --- styles whose plan is a {key: picture} map (Prepper Host, Food Files): spec["pictures"] = {key: {"prompt", ...}},
#     spec["assets"]["pictures"] = {key: file}. One table row per picture; the key of each row is kept in spec_keys.json.
def _ph_dir(ws) -> Path:
    return Path(ws.root) / "state" / "prepper_host" / "assets"


def _ff_dir(ws) -> Path:
    return Path(ws.root) / "state" / "foodfiles" / "assets"


OWNERS["prepper_host"] = ("_ph_active", _ph_dir)   # Prepper Host Flow pictures (ui/prepper_host_section.py)
OWNERS["foodfiles"] = ("_ff_active", _ff_dir)      # Food Files Flow pictures (ui/foodfiles_section.py)


def spec_rows(images_dir: Path, spec: dict) -> List:
    """The plan's pictures as table rows (made ones seeded into the manifest), in plan order. Main-thread safe: only files."""
    import json
    from providers.base import SceneRow

    pics = spec.get("pictures") or {}
    have = (spec.get("assets") or {}).get("pictures") or {}
    clips = (spec.get("assets") or {}).get("clips") or {}
    rows, keys = [], {}
    try:
        old_keys = json.loads((Path(images_dir) / "spec_keys.json").read_text(encoding="utf-8"))
    except Exception:
        old_keys = {}
    stale = []
    for i, (k, p) in enumerate(pics.items(), 1):
        if old_keys.get(f"{i:03d}") not in (None, k):
            stale.append(f"{i:03d}")
    if stale:
        # Rows are numbered by position: when the plan adds/removes/reorders pictures, row 003 is a different picture now,
        # so a picture chosen for the old 003 must not be handed to the new one.
        _drop_records(images_dir, stale)
    for i, (k, p) in enumerate(pics.items(), 1):
        no = f"{i:03d}"
        prompt = str((p or {}).get("prompt") or k)
        clip = clips.get(k)
        rows.append(SceneRow(scene_number=no, script_segment=prompt[:160], asset_type="video" if clip else "image", prompt=prompt))
        keys[no] = k
        made = clip or have.get(k)
        if made:
            seed(images_dir, no, str(made), "flow", prompt=prompt, provider="flow")
    try:
        Path(images_dir).mkdir(parents=True, exist_ok=True)
        (Path(images_dir) / "spec_keys.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    except Exception:
        pass
    return rows


def _drop_records(images_dir: Path, numbers: List[str]) -> None:
    from asset_manager import AssetManifest, _key, _manifest_lock

    man = AssetManifest(Path(images_dir))
    with _manifest_lock(man.path):
        man._refresh()
        gone = [n for n in numbers if man._data.pop(_key(n), None) is not None]
        if gone:
            man.save()


def apply_spec(images_dir: Path, scene_rows: List, spec: dict) -> int:
    """Render side: every finished file the table holds replaces that key's picture (or clip) in the plan. -> how many changed."""
    import json

    try:
        keys = json.loads((Path(images_dir) / "spec_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return 0
    assets = spec.setdefault("assets", {})
    pics, clips = assets.setdefault("pictures", {}), assets.get("clips")
    changed = 0
    for no, rec in records(images_dir, scene_rows).items():
        k = keys.get(f"{no:03d}")
        if not k or k not in (spec.get("pictures") or {}):
            continue
        is_clip = Path(rec["path"]).suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".m4v")
        if is_clip and isinstance(clips, dict):
            if clips.get(k) != rec["path"]:
                clips[k] = rec["path"]
                changed += 1
        elif not is_clip and pics.get(k) != rec["path"]:
            pics[k] = rec["path"]
            if isinstance(clips, dict) and clips.pop(k, None) is not None:   # the user picked a still over the clip
                pic = (spec.get("pictures") or {}).get(k)
                if isinstance(pic, dict):
                    pic["still_chosen"] = True   # so a later asset refresh does not put the clip back
            changed += 1
    return changed


def _sm_dir(ws) -> Path:
    return Path(ws.root) / "state" / "stickman" / "assets"


OWNERS["stickman"] = ("_sm_active", _sm_dir)   # Stickman Meme look's Flow-painted rooms (ui/stickman_section.py)


def _tt_dir(ws) -> Path:
    return Path(ws.root) / "state" / "toon_tales" / "assets"


OWNERS["toon_tales"] = ("_tt_active", _tt_dir)   # Toon Tales Flow-painted places (ui/toon_tales_section.py)


# --- styles that read their pictures from fixed files (Toon Tales places, Kids Stories backgrounds): files = {key: (path, prompt)}
def file_view(files: Dict[str, Tuple[str, str]]) -> dict:
    return {"pictures": {k: {"prompt": pr} for k, (_, pr) in files.items()},
            "assets": {"pictures": {k: p for k, (p, _) in files.items() if Path(p).is_file()}}}


def file_rows(images_dir: Path, files: Dict[str, Tuple[str, str]]) -> List:
    return spec_rows(images_dir, file_view(files))


def apply_files(images_dir: Path, scene_rows: List, files: Dict[str, Tuple[str, str]], keep_original: bool = False) -> int:
    """Render side: a picture chosen in the Visuals tab is written over that key's file (same format), so the engine reads it.
    keep_original: the first time, the file there is kept as <name>.orig<ext>. -> how many files changed."""
    import shutil

    view = file_view(files)
    old = dict(view["assets"]["pictures"])
    if not apply_spec(images_dir, scene_rows, view):
        return 0
    n = 0
    for k, src in view["assets"]["pictures"].items():
        dst = Path(files[k][0])
        if src == old.get(k) or not Path(src).is_file() or Path(src).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        try:
            if dst.exists() and Path(src).resolve() == dst.resolve():
                continue
        except OSError:
            pass
        dst.parent.mkdir(parents=True, exist_ok=True)
        keep = dst.with_name(dst.stem + ".orig" + dst.suffix)
        if keep_original and dst.is_file() and not keep.exists():
            shutil.copy2(dst, keep)
        if Path(src).suffix.lower() == dst.suffix.lower():
            shutil.copy2(src, dst)
        else:
            from PIL import Image
            with Image.open(src) as im:        # closed at once: an open handle locks the source on Windows
                (im.convert("RGB") if dst.suffix.lower() in (".jpg", ".jpeg") else im.convert("RGBA")).save(dst)
        side = Path(str(dst) + ".depth.npy")   # a depth map made for the old picture (Kids Stories packs) would warp the new one
        if side.is_file():
            side.unlink()
        n += 1
    return n


def _ks_dir(ws) -> Path:
    return Path(ws.root) / "state" / "kids_stories" / "assets"


OWNERS["kids_stories"] = ("_ks_active", _ks_dir)   # Kids Stories backgrounds from the imported pack (ui/kids_stories_section.py)


def _st_dir(ws) -> Path:
    return Path(ws.root) / "state" / "senior_trivia" / "assets"


OWNERS["senior_trivia"] = ("_st_active", _st_dir)   # Senior Trivia Flow pictures (ui/senior_trivia_section.py)
