"""StarMap's pictures and clips in the app's EXISTING Visual Plan table, and getting them.

Every card and clip that names a source (nasa_image:, stock_video:, flow_video: ...) is one Visual Plan row, numbered 1, 2, 3 ...
in CSV order; file:<name> assets are the author's own files and are not rows. The rows are resolved like every other style's,
into one folder with its .asset_manifest.json (so a replacement made in the table survives re-runs and nothing is fetched or
generated twice):
  * nasa_image  -> shown as a stock_image row; StarMap tries NASA's image library first (starmap/nasa_images.py)
  * nasa_video  -> the app's NASA video provider (providers/nasa)
  * stock_ / flow_ / youtube_ / archive_ / commons_  -> the shared resolver (video_generator.resolve_scene_assets)
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .beat_csv import Plan, asset_source

TABLE_TYPE = {"nasa_image": "stock_image"}        # how a StarMap source appears in the Visual Plan table
_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


@dataclass
class MediaRow:
    scene_number: str
    row: int                                     # the CSV row
    kind: str                                    # card | clip
    source: str                                  # nasa_image, stock_video, ...
    prompt: str
    beat: str
    t: float
    label: str = ""

    def as_dict(self) -> Dict[str, str]:
        what = "photo card" if self.kind == "card" else "footage"
        when = f"{int(self.t // 60)}:{int(self.t % 60):02d}  " if self.t >= 0 else ""
        seg = f"{when}StarMap beat {self.beat} · {what}" + (f" — {self.label}" if self.label else "")
        if self.source == "nasa_image":
            seg += " (NASA image library first)"
        return {"scene_number": self.scene_number, "script_segment": seg, "asset_type": TABLE_TYPE.get(self.source, self.source), "prompt": self.prompt}


def media_rows(plan: Plan) -> List[MediaRow]:
    out: List[MediaRow] = []
    for b in plan.beats:
        items = [(c, "card") for c in b.cards] + [(c, "clip") for c in b.clips]
        for it, kind in sorted(items, key=lambda x: x[0].row):
            src = asset_source(it.asset)
            if src == "file":
                continue
            prompt = " ".join(it.asset.split(":", 1)[1].split())
            out.append(MediaRow(str(len(out) + 1), it.row, kind, src, prompt, b.id, it.t if it.t is not None else b.start, it.label or it.why))
    return out


def media_rows_from_csv(text: str) -> List[MediaRow]:
    """The same rows, numbered the same way, straight from the CSV (no narration needed: no times). Rows with a bad asset are
    left out here; loading the plan reports them."""
    import csv
    import io

    out: List[MediaRow] = []
    for n, r in enumerate(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))), start=2):
        kind = (r.get("row") or "").strip().lower()
        if kind not in ("card", "clip"):
            continue
        asset = (r.get("asset") or "").strip()
        try:
            src = asset_source(asset)
        except ValueError:
            continue
        if src == "file":
            continue
        label = (r.get("label") or "").strip() if kind == "card" else (r.get("why") or "").strip()
        out.append(MediaRow(str(len(out) + 1), n, kind, src, " ".join(asset.split(":", 1)[1].split()), (r.get("beat") or "").strip(), -1.0, label))
    return out


def visual_dicts(plan: Plan) -> List[Dict[str, str]]:
    """The rows for the Visual Plan table (SceneRow.from_csv_row shape)."""
    return [m.as_dict() for m in media_rows(plan)]


def make_resolver(nasa_clip_s: float = 6.0, base: Optional[Callable[..., Any]] = None) -> Callable[..., Any]:
    """A resolver for pakmap.sourcing.fetch_scenes that adds the NASA video provider to the shared one: nasa_video rows go to an
    AssetManager with that provider (same manifest, same reuse rule), the rest to video_generator.resolve_scene_assets."""

    def resolve(row_dicts: List[dict], images_dir: Path, log: Callable[[str], None] = print, on_scene_start=None, on_scene_complete=None,
                on_scene_generating=None, on_manager_ready=None, **kw: Any) -> None:
        nasa = [d for d in row_dicts if (d.get("asset_type") or "").lower() == "nasa_video"]
        rest = [d for d in row_dicts if d not in nasa]
        callbacks = dict(on_scene_start=on_scene_start, on_scene_complete=on_scene_complete, on_scene_generating=on_scene_generating)
        if nasa:
            from asset_manager import AssetManager
            from providers.base import SceneRow
            from providers.nasa.provider import NasaProvider

            mgr = AssetManager(Path(images_dir), nasa_provider=NasaProvider(clip_duration=nasa_clip_s), log=log)
            if on_manager_ready is not None:
                try:
                    on_manager_ready(mgr)
                except Exception:
                    pass
            mgr.resolve_all([SceneRow.from_csv_row(d) for d in nasa], **{k: v for k, v in callbacks.items() if v is not None})
        if rest:
            fn = base
            if fn is None:
                import video_generator as vg

                fn = vg.resolve_scene_assets
            fn(rest, images_dir, log=log, on_manager_ready=on_manager_ready, **{k: v for k, v in callbacks.items() if v is not None}, **kw)

    return resolve


@dataclass
class Fetched:
    media: Dict[str, Dict[str, str]] = field(default_factory=dict)     # "row:<csv row>" -> {"file", "credit"}
    missing: List[str] = field(default_factory=list)                   # messages, one per scene still without a file
    unresolved: List[str] = field(default_factory=list)                # their scene numbers
    credits: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)                     # rows left out on purpose, and why


def still_of(video: Path, out: Path) -> Path:
    """A photo card needs a still: the clip's frame one second in (or its first)."""
    from map_scene.render import _ffmpeg

    out.parent.mkdir(parents=True, exist_ok=True)
    for ss in ("1", "0"):
        subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", ss, "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)],
                       check=False, capture_output=True)
        if out.is_file() and out.stat().st_size > 0:
            return out
    raise RuntimeError(f"could not take a still from {video.name}")


def _report_left_out(provider_kwargs: Dict[str, Any], table: Sequence[Any], n: str, why: str) -> None:
    """Tell the Visual Plan table a row was left out (it would otherwise stay QUEUED): the app's own scene callback, with a
    failed result carrying the reason, so the row shows NEEDS ACTION with Retry / Change source."""
    done = provider_kwargs.get("on_scene_complete")
    row = next((r for r in table if str(r.scene_number) == n), None)
    if done is None or row is None:
        return
    try:
        from providers.base import AssetResult, AssetSource, SceneStatus

        done(row, AssetResult(scene_number=n, path=None, media_type=None, source=AssetSource.STOCK_IMAGE, status=SceneStatus.FAILED, error=why))
    except Exception:
        pass


def fetch_media(plan: Plan, images_dir: Path, *, scene_rows: Optional[Sequence[Any]] = None, log: Callable[[str], None] = print,
                cancel_check: Optional[Callable[[], bool]] = None, stills_dir: Optional[Path] = None, nasa_get=None,
                fetch_scenes: Optional[Callable[..., Any]] = None, manifest_cls: Any = None, mission: Any = "", **provider_kwargs: Any) -> Fetched:
    """Every row's file (or why not). `scene_rows` is the Visual Plan table as the user left it; without it the rows come from the plan.
    `mission` steers NASA picture search towards the story's own mission: one name, or {scene number: name} when the video
    covers several missions (each row then prefers its own beat's mission)."""
    from providers.base import SceneRow

    from . import nasa_images

    rows_info = media_rows(plan)
    out = Fetched()
    if not rows_info:
        return out
    table = list(scene_rows) if scene_rows else [SceneRow.from_csv_row(m.as_dict()) for m in rows_info]
    wanted = {m.scene_number for m in rows_info}
    table = [r for r in table if str(r.scene_number) in wanted]
    all_rows = list(table)                                     # before NASA's misses are taken out (to report them)
    nasa_rows = {m.scene_number: m.prompt for m in rows_info if m.source == "nasa_image"}
    unanswered: Dict[str, str] = {}
    no_match: Dict[str, str] = {}
    if nasa_rows:
        nasa_images.prefetch(table, nasa_rows, images_dir, manifest_cls=manifest_cls, log=log, get=nasa_get, cancel_check=cancel_check,
                             context=mission, unanswered=unanswered, no_match=no_match)
        # A story about a mission keeps NASA's answer: no stock photo stands in for the mission's own picture. A story with no
        # mission (a moon, a planet, the scale of space) lets a NASA miss try the stock search, which also reaches Wikimedia.
        mission_story = (any(str(v).strip() for v in mission.values()) if isinstance(mission, dict) else bool(str(mission or "").strip())) \
            or any("." in (b.date or "") or b.extra.get("mission") or any(L.type in ("craft", "path", "orbit") for L in b.layers)
                   for b in plan.beats)
        if not mission_story:
            for n in list(no_match):
                log(f"[StarMap] No NASA image for scene {n}; this story names no mission, so it tries the stock search")
                del no_match[n]
        # not to the stock search: NASA was unreachable, or (for a mission) has no picture that is really this one
        table = [r for r in table if str(r.scene_number) not in unanswered and str(r.scene_number) not in no_match]
    if fetch_scenes is None:
        from pakmap.sourcing import fetch_scenes
    got = fetch_scenes(table, images_dir, resolver=provider_kwargs.pop("resolver", None) or make_resolver(), manifest_cls=manifest_cls, log=log, dedupe=True,
                       **provider_kwargs)
    if manifest_cls is None:
        from asset_manager import AssetManifest as manifest_cls
    for m in rows_info:
        n = m.scene_number
        if n in unanswered:
            out.missing.append(f"Visual Plan scene {n} ({m.kind} in beat {m.beat}, CSV row {m.row}: nasa_image:{m.prompt}): NASA's image library "
                               f"did not answer ({unanswered[n]}). Generate again to retry; pictures already found are kept.")
            out.unresolved.append(n)
            continue
        if n in got.skipped:
            out.media[f"row:{m.row}"] = {"file": ""}
            continue
        if n in no_match:                                       # left out: a card goes, a clip leaves its time to the map
            out.media[f"row:{m.row}"] = {"file": ""}
            _report_left_out(provider_kwargs, all_rows, n, f"Left out: {no_match[n]} (nasa_image:{m.prompt}). Change source, "
                                                         f"use a local clip, or describe it the way NASA titles it.")
            out.notes.append(f"Visual Plan scene {n} ({m.kind} in beat {m.beat}, CSV row {m.row}: nasa_image:{m.prompt}): {no_match[n]}, "
                             f"so it is left out. Describe it the way NASA titles it, or give it another source in the Visual Plan.")
            continue
        path = got.paths.get(n)
        if not path:
            out.missing.append(f"Visual Plan scene {n} ({m.kind} in beat {m.beat}, CSV row {m.row}: {m.source}:{m.prompt}): {got.missing.get(n, 'no file')}")
            out.unresolved.append(n)
            continue
        p = Path(path)                                          # a card's clip stays a clip: the card plays it
        rec = manifest_cls(images_dir).get(n) or {}
        credit = rec.get("credit") or _credit_from(rec)
        # only NASA material is credited on screen; stock (Pexels and the like) is credited in the credits file alone
        on_screen = credit and m.kind == "clip" and _is_nasa(rec)
        out.media[f"row:{m.row}"] = {"file": str(p), **({"credit": credit} if on_screen else {})}
        if credit and credit not in out.credits:
            out.credits.append(credit)
    return out


def _is_nasa(rec: Dict[str, Any]) -> bool:
    """A manifest record for NASA material (the NASA image or video library), not a stock provider's."""
    return any("nasa" in str(rec.get(k) or "").lower() for k in ("source", "provider", "asset_type", "author"))


def _credit_from(rec: Dict[str, Any]) -> str:
    """A credit line from a provider's manifest record (author / provider / source page), when it has one."""
    who = rec.get("author") or rec.get("photographer") or rec.get("channel") or ""
    src = rec.get("source") or ""
    url = rec.get("source_url") or rec.get("url") or ""
    if not (who or url):
        return ""
    return " · ".join(x for x in (who, src.replace("_", " "), url) if x)
