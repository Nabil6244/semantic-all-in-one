"""Pictures and clips for pakMap that come from the app's existing Flow / stock / YouTube providers (Phase 8).

In the CSV, `asset_path` is a file as before, or `<source>:<what to find>` with the source named exactly like the other
styles name theirs: stock_image, stock_video, flow_image, flow_video, youtube_video.

    stock_image:Nairobi skyline at dusk
    flow_video:aerial of Lake Victoria at sunrise
    stock_image:Nairobi skyline|stock_image:Kenyan highlands      (a cross-fade is still `a|b`)

Each sourced reference becomes one row of the app's EXISTING Visual Plan table (a SceneRow with a scene number, an
asset_type and a prompt), so the user inspects and changes it there with the normal Retry / Change source / Skip / Local clip
actions. Assets are resolved by the existing AssetManager (video_generator.resolve_scene_assets) into one images folder and
remembered in its .asset_manifest.json, exactly like the other styles; a user's replacement is a manifest "user_override"
that survives re-runs, and nothing is downloaded or generated twice (a Flow picture costs credits). At render time each
picture is read back from that folder by scene number and swapped into the script, so the CSV is never edited.

Scene numbers: sourced references are numbered 1, 2, 3 ... in script order, one per use (the same text written twice is two
rows, so each use can be replaced on its own). Local-file references are not rows: they are the author's own choice.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

KINDS = ("stock_image", "stock_video", "flow_image", "flow_video", "youtube_video")
FLOW_KINDS = ("flow_image", "flow_video")
MANIFEST = "manifest.json"
_PREFIX = re.compile(r"^([A-Za-z_]{3,20}):(?![\\/])(.*)$", re.S)


def split_parts(asset_path: str) -> List[str]:
    return [p.strip() for p in (asset_path or "").split("|") if p.strip()]


def parse_spec(part: str) -> Optional["tuple[str, str]"]:
    """(kind, prompt) when `part` names a source, else None (it is a file path)."""
    m = _PREFIX.match(part.strip())
    if not m or m.group(1).lower() not in KINDS:
        return None
    prompt = m.group(2).strip()
    return m.group(1).lower(), prompt


def spec_key(kind: str, prompt: str) -> str:
    return f"{kind}:{' '.join(prompt.split())}"


def misspelled_source(part: str) -> Optional[str]:
    """A hint when `part` looks like `source:text` with a source we do not know."""
    m = _PREFIX.match(part.strip())
    if not m or m.group(1).lower() in KINDS:
        return None
    hint = difflib.get_close_matches(m.group(1).lower(), KINDS, n=1, cutoff=0.6)
    return hint[0] if hint else None


@dataclass
class Occurrence:
    scene_number: int
    line: int  # CSV row number
    part: int  # index among the `|`-separated parts of that row's asset_path
    kind: str
    prompt: str
    layer: str = ""  # the layer type (pip, filmstrip, media_full)
    label: str = ""
    anchor: str = ""  # the narration words the layer is tied to
    uses_flow: bool = False

    @property
    def key(self) -> str:
        return spec_key(self.kind, self.prompt)

    @property
    def description(self) -> str:
        """The text shown in the Visual Plan row."""
        what = {"pip": "photo card", "filmstrip": "filmstrip card", "media_full": "full-screen"}.get(self.layer, self.layer)
        bits = [what + (f" · {self.label}" if self.label else "")]
        if self.anchor:
            bits.append(f"“{self.anchor}”")
        return " — ".join(bits)


def find_occurrences(rows) -> List[Occurrence]:
    out: List[Occurrence] = []
    for row in rows:
        for i, part in enumerate(split_parts(getattr(row, "asset_path", ""))):
            spec = parse_spec(part)
            if spec is None:
                continue
            out.append(Occurrence(len(out) + 1, row.line, i, spec[0], " ".join(spec[1].split()), row.layer_type, getattr(row, "label_text", "") or "",
                                  (getattr(row, "vo_anchor", "") or "").split("|")[0].strip(), spec[0] in FLOW_KINDS))
    return out


def scene_row_dicts(occurrences: Sequence[Occurrence]) -> List[Dict[str, str]]:
    """The CSV-row-shaped dicts the existing providers / SceneRow.from_csv_row expect."""
    return [{"scene_number": str(o.scene_number), "script_segment": o.description, "asset_type": o.kind, "prompt": o.prompt} for o in occurrences]


def media_for(row, media_map: Optional[Dict[Any, Optional[str]]]) -> str:
    """The row's asset_path with each sourced part replaced by its fetched file, keyed (csv row, part index). A part mapped to
    None is dropped (the author skipped that picture). Plain file parts, and every part when there is no map, are unchanged."""
    if not media_map:
        return row.asset_path
    parts = []
    for i, part in enumerate(split_parts(row.asset_path)):
        if (row.line, i) in media_map:
            if media_map[(row.line, i)]:
                parts.append(media_map[(row.line, i)])
        else:
            parts.append(part)
    return "|".join(parts)


# ---- fetching through the existing providers -------------------------------------------------------------------

def _row_dict(scene) -> Dict[str, str]:
    """A Visual Plan SceneRow (as the table holds it, possibly after Change source) back to the dict the providers take."""
    return {"scene_number": str(scene.scene_number), "script_segment": getattr(scene, "script_segment", "") or "",
            "asset_type": getattr(scene, "asset_type", "") or "", "prompt": getattr(scene, "prompt", "") or getattr(scene, "stock", "") or ""}


@dataclass
class FetchResult:
    paths: Dict[str, str] = field(default_factory=dict)  # scene number -> file
    missing: Dict[str, str] = field(default_factory=dict)  # scene number -> why
    skipped: List[str] = field(default_factory=list)  # scene numbers the author chose to skip
    reused: int = 0
    fetched: int = 0


def _record(manifest_cls, images_dir: Path, scene_number: str) -> Dict[str, Any]:
    try:
        return manifest_cls(images_dir).get(scene_number) or {}
    except Exception:
        return {}


def fetch_scenes(
    scenes: Sequence[Any], images_dir: "str | Path", *, resolver: Optional[Callable[..., Any]] = None,
    find_file: Optional[Callable[[Path, str], Optional[Path]]] = None, manifest_cls: Any = None,
    log: Callable[[str], None] = print, **provider_kwargs: Any,
) -> FetchResult:
    """Resolve the Visual Plan rows through the existing providers and return a file for each. The AssetManager behind
    `resolver` reuses any scene whose manifest record is complete (including a user's replacement), so only new or failed
    scenes touch Flow / stock / YouTube. `provider_kwargs` go to video_generator.resolve_scene_assets. A provider failure never
    raises: the scene comes back in `missing` (or `skipped` when the author chose Skip)."""
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    result = FetchResult()
    if not scenes:
        return result
    if resolver is None or find_file is None or manifest_cls is None:
        import video_generator as vg
        from asset_manager import AssetManifest

        resolver = resolver or vg.resolve_scene_assets
        find_file = find_file or vg.find_image_for_scene
        manifest_cls = manifest_cls or AssetManifest
    before = {str(sc.scene_number): _record(manifest_cls, images_dir, str(sc.scene_number)) for sc in scenes}
    error = ""
    try:
        resolver([_row_dict(sc) for sc in scenes], images_dir, log=log, **provider_kwargs)
    except SystemExit as exc:
        error = str(exc) or "the provider stopped"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    for sc in scenes:
        n = str(sc.scene_number)
        rec = _record(manifest_cls, images_dir, n)
        err_text = str(rec.get("error") or "")
        if rec.get("status") == "failed" and ("skipped" in err_text.lower() or "placeholder only" in err_text.lower()):
            result.skipped.append(n)
            continue
        found = find_file(images_dir, n)
        if found is not None and Path(found).is_file() and rec.get("status", "complete") != "failed":
            result.paths[n] = str(found)
            if before.get(n, {}).get("status") == "complete":
                result.reused += 1
            else:
                result.fetched += 1
        else:
            result.missing[n] = err_text or error or "no picture was found for it"
    return result
