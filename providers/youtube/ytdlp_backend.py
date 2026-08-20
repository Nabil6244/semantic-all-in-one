"""Real YouTubeSearchBackend, built on yt-dlp — no YouTube Data API key needed
(ytsearch: and metadata probing work unauthenticated). yt-dlp is imported
lazily (inside each method, not at module scope) so the rest of the app keeps
working without it installed; a youtube_video scene fails clearly instead of
the whole app failing to start. Install with `pip install yt-dlp`.

Segment acquisition itself (the actual media download) lives in
strategies.py. Browser playback is primary when Chrome/Node are available;
the yt-dlp client/format chain remains as a legacy fallback only when the
browser worker cannot run. This file owns search/probe/transcript and wires
candidates into that strategy chain.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import requests

from ..base import LogFn
from .base import TranscriptSegment, VideoCandidate, YouTubeSearchBackend
from .strategies import AllStrategiesFailed, _require_yt_dlp, build_strategy_chain, run_strategy_chain

_PROBE_TIMEOUT = 20
_CAPTION_LANG_PREFERENCE = ("en", "en-US", "en-GB", "en-orig")


def _pick_caption_track(tracks: dict) -> Optional[list]:
    """`tracks` is yt-dlp's subtitles/automatic_captions dict: lang -> list of
    {ext, url} entries. Prefer English, prefer a text/vtt or json3 format."""
    if not tracks:
        return None
    for lang in _CAPTION_LANG_PREFERENCE:
        if lang in tracks:
            return tracks[lang]
    # No English track — take whatever the first available language offers
    # rather than guessing; better than silently using non-English text.
    return None


def _pick_format_url(entries: list) -> Optional[tuple]:
    if not entries:
        return None
    for entry in entries:
        if entry.get("ext") == "vtt":
            return entry["url"], "vtt"
    for entry in entries:
        if entry.get("ext") == "json3":
            return entry["url"], "json3"
    first = entries[0]
    return first.get("url"), first.get("ext", "vtt")


_VTT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
_TAG_RE = re.compile(r"<[^>]+>")


def _vtt_timestamp_to_seconds(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(text: str) -> List[TranscriptSegment]:
    """Minimal WebVTT parser — good enough for YouTube's own auto-caption
    output, without pulling in a webvtt-parsing dependency the project doesn't
    already have. Strips YouTube's inline <00:00:01.360><c> word</c> tags."""
    segments: List[TranscriptSegment] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _VTT_TIME_RE.search(lines[i])
        if not m:
            i += 1
            continue
        start = _vtt_timestamp_to_seconds(*m.groups()[0:4])
        end = _vtt_timestamp_to_seconds(*m.groups()[4:8])
        i += 1
        text_lines = []
        while i < len(lines) and lines[i].strip() and not _VTT_TIME_RE.search(lines[i]):
            text_lines.append(lines[i])
            i += 1
        cue_text = _TAG_RE.sub("", " ".join(text_lines)).strip()
        if cue_text:
            segments.append(TranscriptSegment(start=start, duration=max(0.1, end - start), text=cue_text))
    return segments


def parse_json3(data: dict) -> List[TranscriptSegment]:
    segments: List[TranscriptSegment] = []
    for event in data.get("events", []) or []:
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text:
            continue
        start = event.get("tStartMs", 0) / 1000.0
        dur = event.get("dDurationMs", 0) / 1000.0
        segments.append(TranscriptSegment(start=start, duration=max(0.1, dur), text=text))
    return segments


class YtDlpBackend(YouTubeSearchBackend):
    def __init__(
        self,
        format_selector: str = "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    ):
        # DASH video+audio (merged by ffmpeg) is the default/primary
        # strategy — empirically the most reliable single choice — but no
        # longer the ONLY thing tried; see strategies.py for the full
        # candidate-level fallback chain (alternate clients, HLS, PO-token
        # when available) that runs when this one fails.
        _require_yt_dlp()  # fail fast/clearly at construction, not on first scene
        self.format_selector = format_selector
        self._last_strategy: Optional[str] = None

    def _ydl(self, extra_opts: Optional[dict] = None):
        yt_dlp = _require_yt_dlp()
        # source_address 0.0.0.0 forces IPv4. Broken IPv6 (SYN_SENT forever to
        # Google) makes ytsearch look like a freeze with no log after
        # "searching …".
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": _PROBE_TIMEOUT,
            "source_address": "0.0.0.0",
        }
        opts.update(extra_opts or {})
        return yt_dlp.YoutubeDL(opts)

    def search(self, query: str, max_results: int = 5) -> List[VideoCandidate]:
        """YouTube search only. Uses yt-dlp's flat extractor (ids/titles/durations)
        and does NOT probe each watch page. Per-result extract_info was the
        ~20s×N delay (up to ~120s for 5 hits). Ranking still has title +
        duration from the search listing; captions/size are filled later if
        transcript matching probes a chosen candidate."""
        if not query.strip():
            return []
        with self._ydl({"extract_flat": "in_playlist"}) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        candidates: List[VideoCandidate] = []
        for entry in (info or {}).get("entries") or []:
            if not entry:
                continue
            cand = self._candidate_from_search_entry(entry)
            if cand is not None:
                candidates.append(cand)
        return candidates

    def _candidate_from_search_entry(self, entry: dict) -> Optional[VideoCandidate]:
        video_id = entry.get("id") or ""
        if not video_id:
            return None
        duration = entry.get("duration")
        try:
            duration = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration = None
        return VideoCandidate(
            video_id=video_id,
            url=entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
            title=entry.get("title", "") or "",
            channel=entry.get("channel") or entry.get("uploader") or "",
            duration=duration,
            description=entry.get("description") or "",
            width=int(entry.get("width") or 0),
            height=int(entry.get("height") or 0),
            has_captions=False,
            license=entry.get("license"),
        )

    def _probe(self, video_id: str) -> Optional[VideoCandidate]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        with self._ydl() as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return None
        subs = info.get("subtitles") or {}
        auto_subs = info.get("automatic_captions") or {}
        has_captions = bool(_pick_caption_track(subs) or _pick_caption_track(auto_subs))
        return VideoCandidate(
            video_id=video_id,
            url=url,
            title=info.get("title", "") or "",
            channel=info.get("channel") or info.get("uploader") or "",
            duration=info.get("duration"),
            description=info.get("description") or "",
            width=info.get("width") or 0,
            height=info.get("height") or 0,
            has_captions=has_captions,
            license=info.get("license"),
        )

    def get_transcript(self, candidate: VideoCandidate) -> Optional[List[TranscriptSegment]]:
        with self._ydl() as ydl:
            info = ydl.extract_info(candidate.url, download=False)
        if not info:
            return None
        subs = info.get("subtitles") or {}
        auto_subs = info.get("automatic_captions") or {}
        track = _pick_caption_track(subs) or _pick_caption_track(auto_subs)
        if not track:
            return None
        picked = _pick_format_url(track)
        if not picked:
            return None
        url, ext = picked
        # One request only — a 429/timeout here must fall through to the
        # existing fallback-timestamp path (see providers/youtube/base.py),
        # never be retried; this method already only ever makes one HTTP call.
        resp = requests.get(url, timeout=_PROBE_TIMEOUT)
        resp.raise_for_status()
        if ext == "json3":
            return parse_json3(resp.json())
        return parse_vtt(resp.text)

    def download_segment(self, candidate: VideoCandidate, start: float, duration: float, dest: Path, log: LogFn = print) -> Path:
        """Segment-first acquisition. When Chrome/Node are available this uses
        browser playback capture only (then the caller moves to the next
        candidate on failure). The legacy yt-dlp strategy chain is used only
        if the browser worker cannot run on this machine."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        from .acquisition.browser_client import set_log as set_browser_log

        set_browser_log(log)
        chain = build_strategy_chain(self.format_selector)
        if chain and getattr(chain[0], "name", None) == "browser_playback":
            log("[YOUTUBE] -> browser acquisition")
        outcome = run_strategy_chain(chain, candidate, start, duration, dest, log)
        if outcome.ok:
            self._last_strategy = outcome.strategy
            return dest
        raise AllStrategiesFailed(outcome)
