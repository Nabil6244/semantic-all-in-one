"""
YouTube subsystem — smart clip discovery for asset_type=youtube_video.

Mirrors the shape of providers/stock/base.py: a small, swappable
`YouTubeSearchBackend` does the actual network/yt-dlp work (search, transcript
retrieval, segment-only download), while `YouTubeProvider` owns the
search -> rank -> transcript-match -> timestamp -> clip pipeline once,
identically, regardless of backend. Tests inject a fake backend so none of
this needs real network access or yt-dlp installed (see test_asset_pipeline.py).
"""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import List, Optional, Set

from ..base import (
    AssetProvider,
    AssetResult,
    AssetSource,
    LogFn,
    MediaType,
    SceneRow,
    SceneStatus,
    sniff_media_kind,
)
from .matching import best_transcript_match
from .ranking import rank_candidates
from .query import expand_youtube_query

DEFAULT_CLIP_DURATION = 3.5
DEFAULT_LEAD_IN = 1.0
DEFAULT_MAX_RESULTS = 5


def unique_youtube_queries(scene: SceneRow) -> List[str]:
    """Ordered, de-duplicated YouTube search queries for one resolution attempt."""
    raw: List[str] = []
    extras = [str(q).strip() for q in (getattr(scene, "search_queries", None) or [])]
    prompt = (scene.prompt or "").strip()
    if extras:
        raw.extend(extras)
    elif "||" in prompt:
        raw.extend(p.strip() for p in prompt.split("||"))
    elif prompt:
        raw.append(prompt)
    seen = set()
    out: List[str] = []
    for query in raw:
        query = " ".join(query.split())
        key = query.lower()
        if not query or key in seen:
            continue
        seen.add(key)
        out.append(query)
    return out


@dataclasses.dataclass
class TranscriptSegment:
    start: float
    duration: float
    text: str


@dataclasses.dataclass
class VideoCandidate:
    video_id: str
    url: str
    title: str
    channel: str
    duration: Optional[float] = None
    description: str = ""
    width: int = 0
    height: int = 0
    has_captions: bool = False
    license: Optional[str] = None  # yt-dlp's self-reported license string, if any


class YouTubeSearchBackend:
    """Swappable acquisition layer — YtDlpBackend (ytdlp_backend.py) is the
    real implementation; tests use a fake."""

    def search(self, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> List[VideoCandidate]:
        raise NotImplementedError

    def get_transcript(self, candidate: VideoCandidate) -> Optional[List[TranscriptSegment]]:
        """Return timestamped transcript segments, or None if no captions
        (manual or automatic) are available for this video."""
        raise NotImplementedError

    def download_segment(
        self, candidate: VideoCandidate, start: float, duration: float, dest: Path, log: LogFn = print
    ) -> Path:
        """Fetch ONLY [start, start+duration) of the source video to `dest`
        (segment-first acquisition — see providers/youtube/ytdlp_backend.py).
        Must raise, never silently fall back to a full download. `log` is
        used to surface acquisition-attempt progress (e.g. a 403 client
        fallback) in the app's activity log — implementations without any
        such retry behavior can ignore it."""
        raise NotImplementedError


_LONG_FORM_THRESHOLD = 20 * 60  # 20 minutes — beyond this, "midpoint" stops being a meaningful guess


def compute_fallback_timestamp(video_duration: Optional[float], clip_duration: float) -> float:
    """Fallback target timestamp when no transcript match exists. Short
    videos: duration/2 (a single-topic video's middle is a reasonable
    representative guess). Long videos: a small fixed offset near the start
    instead of a random deep point with no semantic basis whatsoever — see
    _pick_timestamp's caller comment."""
    if not video_duration or video_duration <= 0:
        return 0.0
    if video_duration <= _LONG_FORM_THRESHOLD:
        if video_duration > clip_duration:
            return max(0.0, (video_duration / 2.0) - (clip_duration / 2.0))
        return 0.0
    return min(30.0, max(0.0, video_duration - clip_duration))


def compute_clip_window(
    target_ts: float,
    video_duration: Optional[float],
    clip_duration: float = DEFAULT_CLIP_DURATION,
    lead_in: float = DEFAULT_LEAD_IN,
) -> tuple:
    """start = target - ~1s, clamped to [0, video_duration - clip_duration]."""
    start = max(0.0, target_ts - lead_in)
    end = start + clip_duration
    if video_duration and video_duration > 0 and end > video_duration:
        end = video_duration
        start = max(0.0, end - clip_duration)
    duration = max(0.1, end - start)
    return start, duration


class YouTubeProvider(AssetProvider):
    name = "youtube"
    source = AssetSource.YOUTUBE_VIDEO

    def __init__(
        self,
        backend: YouTubeSearchBackend,
        max_results: int = DEFAULT_MAX_RESULTS,
        clip_duration: float = DEFAULT_CLIP_DURATION,
        transcript_matching: bool = True,
        require_creative_commons: bool = False,
    ):
        self.backend = backend
        self.max_results = max_results
        self.clip_duration = clip_duration
        self.transcript_matching = transcript_matching
        # Best-effort rights filter based on YouTube's own self-reported license
        # field (yt-dlp's `license`/`license` metadata — usually only populated
        # for videos the uploader explicitly marked Creative Commons). This is
        # NOT legal advice or a guarantee of clearance; it only lets a user who
        # wants to restrict themselves to CC-tagged sources do so. Default off,
        # matching "prefer... when appropriate" rather than "always require".
        self.require_creative_commons = require_creative_commons
        self.should_stop_scene = None

    def _scene_stopped(self, scene: SceneRow) -> bool:
        cb = getattr(self, "should_stop_scene", None)
        return bool(callable(cb) and cb(str(scene.scene_number)))

    # ---------- search ----------

    def _search_query(self, scene: SceneRow) -> str:
        queries = unique_youtube_queries(scene)
        return queries[0] if queries else scene.prompt.strip()

    def _match_text(self, scene: SceneRow) -> str:
        return f"{scene.script_segment} {self._search_query(scene)}".strip()

    def _rights_ok(self, candidate: VideoCandidate) -> bool:
        if not self.require_creative_commons:
            return True
        lic = (candidate.license or "").lower()
        return "creative commons" in lic

    def _search(self, scene: SceneRow, log: LogFn, exclude_ids: Set[str]) -> List[VideoCandidate]:
        queries = unique_youtube_queries(scene)
        if not queries:
            return []
        attempted: Set[str] = set()
        total = len(queries)
        sn = scene.scene_number
        for index, query in enumerate(queries, start=1):
            # Try the declared query first; if ytsearch returns nothing, broaden
            # cinematic paragraphs into shorter variants (stock already does this).
            variants = expand_youtube_query(query)
            if not variants:
                variants = [query]
            for v_i, variant in enumerate(variants):
                key = variant.lower()
                if key in attempted:
                    continue
                attempted.add(key)
                label = f"query {index}/{total}" + (f" variant {v_i + 1}" if v_i else "")
                log(f"[YOUTUBE] Scene {sn} -> searching {label}:")
                log(f"\"{variant}\"")
                if self._scene_stopped(scene):
                    log(f"[YOUTUBE] Scene {sn} -> cancelled")
                    return []
                started = time.perf_counter()
                try:
                    candidates = self.backend.search(variant, max_results=self.max_results)
                except Exception as exc:
                    elapsed = time.perf_counter() - started
                    log(f"[YOUTUBE] Scene {sn} -> search failed ({elapsed:.1f}s): {exc}")
                    continue
                elapsed = time.perf_counter() - started
                hits = list(candidates or [])
                if not hits:
                    log(f"[YOUTUBE] Scene {sn} -> 0 results ({elapsed:.1f}s)")
                    continue
                log(f"[YOUTUBE] Scene {sn} -> {len(hits)} results ({elapsed:.1f}s)")
                hits = [c for c in hits if c.video_id not in exclude_ids]
                rights_filtered = [c for c in hits if self._rights_ok(c)]
                if self.require_creative_commons and not rights_filtered and hits:
                    log(
                        f"[YOUTUBE] Scene {sn} -> {len(hits)} result(s) found "
                        f"but none are Creative Commons-licensed (policy requires it)."
                    )
                ranked = rank_candidates(rights_filtered, query=variant)
                if ranked:
                    log(f"[YOUTUBE] Scene {sn} -> candidates found")
                    return ranked
                log(f"[YOUTUBE] Scene {sn} -> 0 usable candidates after ranking")
        log(f"[YOUTUBE] Scene {sn} -> all {total} search queries exhausted")
        return []

    # ---------- AssetProvider interface ----------

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        return self._resolve(scene, images_dir, log, exclude_ids=set())

    def regenerate(
        self, scene: SceneRow, images_dir: Path, exclude: Optional[dict] = None, log: LogFn = print
    ) -> AssetResult:
        exclude_ids: Set[str] = set()
        # AssetManager.regenerate_scene() reads the previous result's
        # "provider_asset_id" field generically (same key StockProvider uses)
        # and passes it back here — see _extract()'s metadata below.
        if exclude and exclude.get("provider_asset_id"):
            exclude_ids.add(str(exclude["provider_asset_id"]))
        return self._resolve(scene, images_dir, log, exclude_ids=exclude_ids)

    def _resolve(
        self, scene: SceneRow, images_dir: Path, log: LogFn, exclude_ids: Set[str]
    ) -> AssetResult:
        source = self.source
        queries = unique_youtube_queries(scene)
        if not queries:
            return AssetResult(
                scene.scene_number, None, None, source, SceneStatus.FAILED,
                error="No search query given for this youtube_video scene.",
                metadata={"youtube_phase": "search"},
            )

        candidates = self._search(scene, log, exclude_ids)
        if not candidates:
            reason = (
                "no Creative Commons-licensed result found"
                if self.require_creative_commons
                else "no results found"
            )
            n = len(queries)
            return AssetResult(
                scene.scene_number, None, None, source, SceneStatus.FAILED,
                error=(
                    f"YouTube search exhausted: {reason} after {n} "
                    f"unique quer{'y' if n == 1 else 'ies'}."
                ),
                metadata={
                    "youtube_phase": "search",
                    "queries_attempted": n,
                },
            )

        log(f"[YOUTUBE] Scene {scene.scene_number} -> browser acquisition")
        match_text = self._match_text(scene)

        # Candidate-fallback loop. Acquisition-strategy fallback (different
        # player clients, HLS, PO-token) already lives one layer down, inside
        # YtDlpBackend.download_segment/strategies.py, for ONE candidate; this
        # is the outer layer for when a candidate's video is unusable no
        # matter which strategy fetches it (DRM, taken down, etc.). Each
        # candidate gets its own timestamp pick (transcript match if
        # available, else its own bounded fallback) and its own extraction
        # attempt; a failed extraction moves to the next ranked candidate.
        last_error: Optional[str] = None
        reason_counts: dict = {}
        strategies_attempted = 0
        for idx, candidate in enumerate(candidates, start=1):
            if self._scene_stopped(scene):
                log(f"[YOUTUBE] Scene {scene.scene_number} -> cancelled")
                return AssetResult(
                    scene.scene_number, None, None, source, SceneStatus.CANCELLED,
                    error="Cancelled.",
                )
            log(f"[YOUTUBE] Candidate {idx} -> \"{candidate.title}\"")
            target_ts, selection_method, matched_text = self._pick_timestamp(
                scene, candidate, match_text, log
            )
            result = self._extract(
                scene, candidate, target_ts, selection_method, matched_text, images_dir, log
            )
            if result.ok:
                strategy = (result.metadata or {}).get("strategy", "?")
                clip_duration = (result.metadata or {}).get("clip_duration", 0.0)
                log(
                    f"[YOUTUBE] Scene {scene.scene_number} SUCCESS — Source: Candidate {idx}, "
                    f"Strategy: {strategy}, Clip: {clip_duration:.1f}s"
                )
                return result
            log(f"[YOUTUBE] Candidate {idx} -> extraction failed: {result.error}")
            last_error = result.error
            for _, kind in (result.metadata or {}).get("strategy_attempts", []):
                reason_counts[kind] = reason_counts.get(kind, 0) + 1
                strategies_attempted += 1
            if idx < len(candidates):
                log(f"[YOUTUBE] Trying candidate {idx + 1}")

        summary = ", ".join(f"{k}: {v}" for k, v in sorted(reason_counts.items())) or "no strategies were attempted"
        log(
            f"[YOUTUBE] Scene {scene.scene_number} FAILED — Candidates attempted: {len(candidates)}, "
            f"Strategies attempted: {strategies_attempted}, Reason summary: {summary}"
        )
        return AssetResult(
            scene.scene_number, None, None, source, SceneStatus.FAILED,
            error=(
                f"YouTube candidates exhausted. Candidates attempted: {len(candidates)}. "
                f"Successful: 0. Reason summary: {summary}. Last error: {last_error}"
            ),
            metadata={"youtube_phase": "acquisition"},
        )

    def _pick_timestamp(
        self, scene: SceneRow, candidate: VideoCandidate, match_text: str, log: LogFn
    ) -> tuple:
        """Best timestamp for THIS candidate: transcript match if available and
        matching (never fabricated — a 429/missing-captions/no-match all fall
        through to the controlled per-candidate fallback below), else this
        candidate's own bounded fallback estimate.

        IMPORTANT LIMITATION: a transcript match is supporting evidence that
        the audio around a timestamp discusses the right topic — it is NOT
        visual proof the frame at that moment shows the requested subject
        (spec: a narrator's voice talking about a flight doesn't prove the
        video is showing an airplane in clouds at that exact second). This
        provider has no visual/frame-content understanding at all; ranking
        (see ranking.py) and this timestamp choice are both best-effort
        lexical/duration heuristics, not scene comprehension."""
        if self.transcript_matching:
            log(
                f"[YOUTUBE] Scene {scene.scene_number} -> matching transcript for "
                f"\"{candidate.title}\" ({candidate.channel})"
            )
            try:
                transcript = self.backend.get_transcript(candidate)
            except Exception as exc:
                log(f"[YOUTUBE] Scene {scene.scene_number} -> transcript fetch failed for "
                    f"{candidate.video_id}: {exc}")
                transcript = None
            if transcript:
                match = best_transcript_match(transcript, match_text)
                if match is not None:
                    segment, score = match
                    log(
                        f"[YOUTUBE] Scene {scene.scene_number} -> matched transcript at "
                        f"{segment.start:.1f}s (score {score:.2f}): \"{segment.text[:80]}\""
                    )
                    return segment.start, "transcript_match", segment.text

        # Controlled fallback: no usable transcript match for this candidate
        # (or transcript matching is disabled) — always recorded as
        # "fallback", never disguised as a transcript match. A blind
        # duration/2 midpoint is a reasonable representative guess for a
        # short, single-topic video, but has ZERO semantic basis for a long
        # video (e.g. picking 2145s into a 1-hour ambience loop, as observed
        # in real testing) — ranking already penalizes long-form/ambience
        # candidates heavily (see ranking.py) so this path should rarely be
        # reached for one, but if every candidate is long, prefer a fixed,
        # honest, early-in-the-video guess over an arbitrarily deep one.
        target = compute_fallback_timestamp(candidate.duration, self.clip_duration)
        log(
            f"[YOUTUBE] Scene {scene.scene_number} -> no transcript match, falling back to "
            f"\"{candidate.title}\" at {target:.1f}s"
        )
        return target, "fallback", None

    def _extract(
        self,
        scene: SceneRow,
        candidate: VideoCandidate,
        target_ts: float,
        selection_method: str,
        matched_text: Optional[str],
        images_dir: Path,
        log: LogFn,
    ) -> AssetResult:
        source = self.source
        start, duration = compute_clip_window(target_ts, candidate.duration, self.clip_duration)
        log(
            f"[YOUTUBE] Scene {scene.scene_number} -> extracting clip "
            f"({start:.1f}s-{start + duration:.1f}s) from \"{candidate.title}\""
        )
        n = int(str(scene.scene_number).strip())
        target_path = Path(images_dir) / f"{n:03d}.mp4"
        try:
            path = self.backend.download_segment(candidate, start, duration, target_path, log=log)
        except Exception as exc:
            # Duck-typed: YtDlpBackend's AllStrategiesFailed carries the full
            # per-strategy attempt breakdown for the candidate-loop's
            # exhaustion summary (spec §16); other backends (e.g. the test
            # fake) just raise a plain exception and this stays empty.
            attempts_meta = []
            outcome = getattr(exc, "outcome", None)
            if outcome is not None:
                attempts_meta = [(a.strategy, a.kind) for a in outcome.attempts]
            return AssetResult(
                scene.scene_number, None, None, source, SceneStatus.FAILED,
                error=f"Segment extraction failed: {exc}",
                metadata={"strategy_attempts": attempts_meta} if attempts_meta else {},
            )

        actual = sniff_media_kind(path)
        if actual is not None and actual != "video":
            path.unlink(missing_ok=True)
            return AssetResult(
                scene.scene_number, None, None, source, SceneStatus.FAILED,
                error=f"YouTube segment extraction returned a {actual}, not a video — not using it.",
            )

        log(f"[YOUTUBE] Scene {scene.scene_number} -> downloaded {path.name}")
        # Duck-typed, like the failure path above: YtDlpBackend records which
        # strategy actually won (spec §18's manifest "strategy" field); other
        # backends without that concept simply have nothing to report here.
        strategy_used = getattr(self.backend, "_last_strategy", None)
        return AssetResult(
            scene_number=scene.scene_number,
            path=path,
            media_type=MediaType.VIDEO,
            source=source,
            status=SceneStatus.READY,
            metadata={
                "source_url": candidate.url,
                "video_id": candidate.video_id,
                "provider_asset_id": candidate.video_id,
                "video_title": candidate.title,
                "channel": candidate.channel,
                "license": candidate.license,
                "selection_method": selection_method,
                "matched_text": matched_text,
                "match_timestamp": target_ts,
                "clip_start": start,
                "clip_duration": duration,
                "timestamp_end": start + duration,
                "strategy": strategy_used,
            },
        )
