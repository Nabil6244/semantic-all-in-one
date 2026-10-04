"""Which Visual Plan row is which clip, across plan changes.

The Visual Plan numbers its rows in order of appearance, and a file the user picked (Change source, Local clip) belongs to a row NUMBER.
When a plan changes (a repair turns one beat into footage, a new plan is made, a hand edit adds a card) the numbers after the change
shift, and a user's clip would silently end up on a different moment of the video. Here every row has a logical identity (which beat,
which clip or card, when), the identities are saved with the plan, and when the plan changes the saved files and manifest records follow
their logical row. A clip whose row no longer exists is set aside in `_unattached/`, never deleted and never attached to something else."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .plan import HybridPlan

KEYS_FILE = "row_keys.json"
UNATTACHED = "_unattached"


def row_descriptors(plan: HybridPlan) -> List[Dict[str, Any]]:
    from .app_integration import _scene_map

    beats = {b.id: b for b in plan.beats}
    out = []
    for item in _scene_map(plan):
        b = beats.get(item["beat"])
        if b is None:
            continue
        out.append({"scene": str(item["occ"].scene_number), "beat": b.id, "start": round(b.start, 3), "end": round(b.end, 3),
                    "kind": "card" if item["card"] else "clip", "idx": 0 if item["card"] else int(item["clip"] or 1)})
    return out


def load_descriptors(folder: "str | Path") -> Optional[List[Dict[str, Any]]]:
    try:
        data = json.loads((Path(folder) / KEYS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else None
    except (OSError, ValueError):
        return None


def save_descriptors(folder: "str | Path", rows: List[Dict[str, Any]]) -> None:
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder) / KEYS_FILE).write_text(json.dumps(rows), encoding="utf-8")
    except OSError:
        pass


def _overlap(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    lo, hi = max(a["start"], b["start"]), min(a["end"], b["end"])
    return max(0.0, hi - lo) / max(0.1, min(a["end"] - a["start"], b["end"] - b["start"]))


def match_rows(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """old scene number -> new scene number (None when the row is gone). Exactly the same beat, span, kind and clip first; otherwise the
    new row of the same kind and clip number that covers most of the old one's time (at least 60%)."""
    taken: Dict[str, str] = {}
    out: Dict[str, Optional[str]] = {}
    for o in old:
        hit = next((n for n in new if n["scene"] not in taken and n["beat"] == o["beat"] and n["kind"] == o["kind"] and n["idx"] == o["idx"]
                    and abs(n["start"] - o["start"]) < 0.05 and abs(n["end"] - o["end"]) < 0.05), None)
        if hit is None:
            cands = [(n, _overlap(o, n)) for n in new if n["scene"] not in taken and n["kind"] == o["kind"] and n["idx"] == o["idx"]]
            cands = [c for c in cands if c[1] >= 0.6]
            hit = max(cands, key=lambda c: c[1])[0] if cands else None
        if hit is not None:
            taken[hit["scene"]] = o["scene"]
        out[o["scene"]] = hit["scene"] if hit is not None else None
    return out


def _files_of(images_dir: Path, number: str, record: Optional[dict]) -> List[Path]:
    files = []
    n = f"{int(number):03d}"
    for p in sorted(images_dir.glob(f"{n}.*")):
        if p.is_file():
            files.append(p)
    lp = (record or {}).get("local_path")
    if lp and Path(lp).is_file() and Path(lp) not in files and Path(lp).parent == images_dir:
        files.append(Path(lp))
    return files


def reconcile(images_dir: "str | Path", old: List[Dict[str, Any]], new: List[Dict[str, Any]], manifest_cls: Any = None) -> Dict[str, Any]:
    """Make the saved files and manifest records follow their logical rows. Returns {"moved": n, "unattached": [scene numbers]}."""
    if manifest_cls is None:
        from asset_manager import AssetManifest as manifest_cls
    images_dir = Path(images_dir)
    summary: Dict[str, Any] = {"moved": 0, "unattached": []}
    if not old or not images_dir.is_dir():
        return summary
    mapping = match_rows(old, new)
    manifest = manifest_cls(images_dir)
    changes = {o: n for o, n in mapping.items() if n != o}
    if not changes:
        return summary
    staged = []   # (new number or None, record, [(temp file, extension)])
    stage = images_dir / f".reconcile_{uuid.uuid4().hex[:8]}"
    stage.mkdir()
    try:
        for o, n in changes.items():
            rec = manifest.get(o)
            files = _files_of(images_dir, o, rec)
            if not rec and not files:
                continue
            kept = []
            for k, f in enumerate(files):
                tmp = stage / f"{o}_{k}{f.suffix}"
                shutil.move(str(f), str(tmp))
                kept.append(tmp)
            staged.append((o, n, rec, kept))
        for o, _n, _rec, _kept in staged:   # the old numbers are free now
            manifest.set(o, {})
        for o, n, rec, kept in staged:
            overridden = bool(rec and (rec.get("user_override") or rec.get("source") == "manual"))
            if n is None:
                if overridden or kept:
                    dest = images_dir / UNATTACHED
                    dest.mkdir(exist_ok=True)
                    for f in kept:
                        shutil.move(str(f), str(dest / f"was_scene_{int(o):03d}{f.suffix}"))
                    summary["unattached"].append(o)
                continue
            new_paths = []
            for f in kept:
                target = images_dir / f"{int(n):03d}{f.suffix}"
                shutil.move(str(f), str(target))
                new_paths.append(target)
            if rec:
                rec = dict(rec)
                main = next((p for p in new_paths if str(rec.get("local_path", "")).endswith(p.suffix)), new_paths[0] if new_paths else None)
                if main is not None:
                    rec["local_path"] = str(main)
                manifest.set(n, rec)
            summary["moved"] += 1
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return summary
