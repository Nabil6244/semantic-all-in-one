"""
Shared types for the asset-provider system.

Three provider implementations (LocalProvider, StockProvider, FlowProvider) all
speak this interface. AssetManager and the CSV router depend only on this file,
never on a specific provider's internals — that's what lets Flow/Pexels/manual
assets be interchangeable from the renderer's point of view.
"""

from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Callable, Optional

LogFn = Callable[[str], None]


class AssetSource(str, enum.Enum):
    LOCAL = "local"
    STOCK = "stock"  # legacy: asset_type="stock" or old prompt/stock CSV — any media type
    STOCK_IMAGE = "stock_image"
    STOCK_VIDEO = "stock_video"
    FLOW_IMAGE = "flow_image"
    FLOW_VIDEO = "flow_video"
    YOUTUBE_VIDEO = "youtube_video"
    MANUAL = "manual"  # user-supplied local file for a failed scene


_STOCK_SOURCES = (AssetSource.STOCK, AssetSource.STOCK_IMAGE, AssetSource.STOCK_VIDEO)


class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class SceneStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    SEARCHING = "searching"
    GENERATING = "generating"
    DOWNLOADING = "downloading"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_ACTION = "needs_action"
    RETRYING = "retrying"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class AssetError(Exception):
    """Raised by a provider when a scene cannot be resolved. Carries a scene number
    and a short, specific reason — never caught and papered over with a substitute asset."""

    def __init__(self, scene_number: str, reason: str):
        self.scene_number = scene_number
        self.reason = reason
        super().__init__(f"Scene {scene_number}: {reason}")


@dataclasses.dataclass
class SceneRow:
    """One CSV row, normalized.

    Two supported CSV shapes, auto-detected by whether an `asset_type` column
    is present:

    - New:    scene_number, script_segment, asset_type, prompt
              asset_type in {image, video, flow_image, flow_video, stock_image,
              stock_video, youtube_video, stock, local}.
              `flow_video`/`flow_image` are aliases for `video`/`image`.
              For a stock_* (or legacy "stock") asset_type, the single `prompt`
              column doubles as the stock search query (normalized into `.stock`
              below so the rest of the code only ever deals with
              `.prompt`/`.stock`, unchanged from the legacy shape). For
              youtube_video, `prompt` stays put — it's the YouTube search query
              and is also used, together with `.script_segment`, as the text
              matched against each candidate video's transcript.
    - Legacy: scene_number, script_segment, prompt, stock
              prompt implies AI image generation (the only kind the legacy
              format ever supported); stock implies a Pexels search across any
              media type; both empty falls back to a local file. Still fully
              supported — asset_type is '' for these (including plain
              2-column CSVs).
    """

    scene_number: str
    script_segment: str
    asset_type: str = ""
    prompt: str = ""
    stock: str = ""
    # Optional Visual Director extras — unused by manual CSV. YouTube scenes may
    # carry several search queries plus declared provider fallbacks.
    search_queries: list = dataclasses.field(default_factory=list)
    fallbacks: list = dataclasses.field(default_factory=list)
    visual_description: str = ""

    @classmethod
    def from_csv_row(cls, row: dict) -> "SceneRow":
        asset_type = str(row.get("asset_type", "") or "").strip().lower()
        prompt = str(row.get("prompt", "") or "").strip()
        stock = str(row.get("stock", "") or "").strip()
        search_queries: list = []

        if asset_type in ("flow_video", "video"):
            asset_type = "video"
        elif asset_type in ("flow_image", "image"):
            asset_type = "image"

        if asset_type in ("stock", "stock_image", "stock_video"):
            # New format: one `prompt` column doubles as the stock query.
            stock = stock or prompt
            prompt = ""
        elif asset_type == "local":
            prompt = ""
            stock = ""
        elif asset_type == "youtube_video" and "||" in prompt:
            search_queries = [p.strip() for p in prompt.split("||") if p.strip()]
            prompt = search_queries[0] if search_queries else prompt

        return cls(
            scene_number=str(row.get("scene_number", "")).strip(),
            script_segment=str(row.get("script_segment", "")).strip(),
            asset_type=asset_type,
            prompt=prompt,
            stock=stock,
            search_queries=search_queries,
        )

    @property
    def wants_flow_video(self) -> bool:
        if self.asset_type:
            return self.asset_type == "video" and bool(self.prompt)
        return False  # the legacy (no asset_type) format never meant video

    @property
    def wants_flow_image(self) -> bool:
        if self.asset_type:
            return self.asset_type == "image" and bool(self.prompt)
        return bool(self.prompt)  # legacy format: a prompt always meant an AI image

    @property
    def wants_flow(self) -> bool:
        """Any AI/Flow generation, image or video — used where callers only need
        to know "does this project need the Flow engine at all"."""
        return self.wants_flow_image or self.wants_flow_video

    @property
    def wants_stock(self) -> bool:
        if self.asset_type:
            return self.asset_type in ("stock", "stock_image", "stock_video") and bool(self.stock)
        return bool(self.stock) and not self.prompt

    @property
    def wants_youtube(self) -> bool:
        """asset_type=youtube_video — `prompt` doubles as the YouTube search
        query here (never moved into `.stock`, unlike stock_*), since it also
        feeds transcript matching alongside `.script_segment`."""
        return self.asset_type == "youtube_video" and bool(self.prompt)

    def as_fallback(self, provider: str) -> "SceneRow":
        """Same scene, switched to a declared Visual Director fallback provider."""
        key = (provider or "").strip().lower().replace(" ", "_").replace("-", "_")
        asset_map = {
            "youtube": "youtube_video",
            "youtube_video": "youtube_video",
            "stock_video": "stock_video",
            "stock": "stock_video",
            "pexels": "stock_video",
            "stock_image": "stock_image",
            "flow_image": "image",
            "image": "image",
            "flow": "image",
            "flow_video": "video",
            "video": "video",
            "local": "local",
        }
        asset_type = asset_map.get(key, key)
        query = (self.stock or self.prompt or "").strip()
        description = (self.visual_description or self.prompt or "").strip()
        if asset_type == "youtube_video":
            # Stock/flow rows often keep the search text in `.stock` with empty `.prompt`.
            yt_prompt = (self.prompt or self.stock or "").strip()
            if not yt_prompt:
                yt_prompt = (self.script_segment or "").strip()[:160]
            queries = [str(q).strip() for q in (self.search_queries or []) if str(q).strip()]
            if yt_prompt and yt_prompt not in queries:
                queries = [yt_prompt] + queries
            return SceneRow(
                scene_number=self.scene_number,
                script_segment=self.script_segment,
                asset_type="youtube_video",
                prompt=yt_prompt,
                search_queries=queries,
                visual_description=self.visual_description,
                fallbacks=list(self.fallbacks or []),
            )
        if asset_type in ("stock_video", "stock_image", "stock"):
            return SceneRow(
                scene_number=self.scene_number,
                script_segment=self.script_segment,
                asset_type=asset_type,
                stock=query,
                visual_description=self.visual_description,
            )
        if asset_type in ("image", "video"):
            prompt = (description or query or self.script_segment).strip()
            return SceneRow(
                scene_number=self.scene_number,
                script_segment=self.script_segment,
                asset_type=asset_type,
                prompt=prompt,
                visual_description=self.visual_description,
            )
        return SceneRow(
            scene_number=self.scene_number,
            script_segment=self.script_segment,
            asset_type="local",
        )

    @property
    def stock_media_type(self) -> str:
        """What Pexels media type to search for: "image", "video", or "all"
        (legacy asset_type="stock" / old prompt-stock CSVs — search everything,
        same as always). Drives StockProvider's search — see providers/stock/base.py."""
        if self.asset_type == "stock_image":
            return "image"
        if self.asset_type == "stock_video":
            return "video"
        return "all"

    @property
    def stock_source(self) -> AssetSource:
        if self.asset_type == "stock_image":
            return AssetSource.STOCK_IMAGE
        if self.asset_type == "stock_video":
            return AssetSource.STOCK_VIDEO
        return AssetSource.STOCK

    @property
    def ignored_stock_warning(self) -> Optional[str]:
        # Only the legacy format can have both populated (new format's `stock`
        # is never set unless asset_type is literally "stock").
        if not self.asset_type and self.prompt and self.stock:
            return (
                f"Scene {self.scene_number}: both prompt and stock are set — "
                f"using Flow (prompt); ignoring stock query \"{self.stock}\"."
            )
        return None


@dataclasses.dataclass
class AssetResult:
    scene_number: str
    path: Optional[Path]
    media_type: Optional[MediaType]
    source: AssetSource
    status: SceneStatus
    metadata: dict = dataclasses.field(default_factory=dict)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == SceneStatus.READY and self.path is not None


def sniff_media_kind(path: Path) -> Optional[str]:
    """Identify a file's real type from its magic bytes — used by FlowProvider
    and StockProvider so a scene is never marked READY just because a file with
    the expected extension exists; the actual bytes must match too. Returns
    "image", "video", or None if unrecognized (unrecognized is treated as
    "don't block on this" rather than a false failure, since a valid but
    uncommon container format shouldn't wrongly fail a scene)."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if head.startswith(b"\xff\xd8\xff"):
        return "image"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image"
    if head[:2] == b"BM":
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "video"
    # MP4/MOV/M4V family: an "ftyp" box, usually at offset 4 but scan a little
    # further since some muxers prepend a free/uuid box first.
    if b"ftyp" in head[:32]:
        return "video"
    if head[:4] == b"\x1aE\xdf\xa3":  # WebM/Matroska (EBML header)
        return "video"
    return None


class AssetProvider:
    """Common interface every asset source implements."""

    name: str = "base"
    source: AssetSource

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        """Return an AssetResult for this scene. Must not raise for expected failure
        modes (missing file, no search results, API error) — return a FAILED
        AssetResult with `.error` set instead, so the caller can report per-scene
        reasons instead of aborting the whole run."""
        raise NotImplementedError

    def regenerate(
        self,
        scene: SceneRow,
        images_dir: Path,
        exclude: Optional[dict] = None,
        log: LogFn = print,
    ) -> AssetResult:
        """Force a fresh asset, bypassing any cache. `exclude` is provider-specific
        (e.g. StockProvider excludes a previous asset id so re-search doesn't repeat it)."""
        return self.resolve(scene, images_dir, log=log)

    def resolve_batch(
        self,
        scenes: list,
        images_dir: Path,
        log: LogFn = print,
        should_stop: Optional[Callable[[], bool]] = None,
        on_scene_ready: Optional[Callable] = None,
    ) -> dict:
        """Resolve several scenes at once. Default just loops resolve() one at a time,
        checking `should_stop()` between scenes so a cancellation request doesn't wait
        for every remaining scene to finish; FlowProvider overrides this to issue a
        single multi-account GENERATE call so the Node engine's concurrency/session
        slicing is actually used, instead of one round-trip per scene.
        `on_scene_ready` is optional — FlowProvider calls it as each scene's file
        lands so the UI can leave PROCESSING before the whole batch ends."""
        results = {}
        for s in scenes:
            if should_stop is not None and should_stop():
                results[s.scene_number] = AssetResult(
                    s.scene_number, None, None, self.source, SceneStatus.CANCELLED,
                    error="Cancelled before this scene started.",
                )
                continue
            results[s.scene_number] = self.resolve(s, images_dir, log=log)
            if on_scene_ready is not None:
                on_scene_ready(s, results[s.scene_number])
        return results
