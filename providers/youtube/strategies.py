"""
YouTube segment-acquisition strategy layer.

Empirically (see prior debugging in this project's history), which specific
yt-dlp mechanism actually succeeds at fetching a few seconds of a given
YouTube video is unpredictable: the same video/format can succeed one moment
and 403 the next, a DASH stream can be blocked while an alternate player
client isn't, and some videos are outright unusable (DRM) no matter what is
tried. A single fixed "one right way to download" doesn't survive contact
with YouTube's current anti-bot enforcement.

This module owns exactly ONE job: given one candidate video, try a short,
ordered list of independent acquisition strategies, stop at the first one
that produces a REAL validated clip, and classify every failure precisely
enough that the caller (providers/youtube/base.py's candidate loop) can tell
"try the next strategy" apart from "this candidate is unusable, move to the
next candidate" (DRM, unavailable) instead of treating every failure as an
opaque ffmpeg exit code.

Nothing here downloads a full source video — every strategy uses the same
proven segment-first mechanism (yt-dlp's download_ranges + force_keyframes_at_
cuts, i.e. the API equivalent of --download-sections), only varying the
player-client identity / format family used to reach it.
"""

from __future__ import annotations

import contextlib
import dataclasses
import enum
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from ..base import LogFn, sniff_media_kind
from providers import hidden_subprocess

if TYPE_CHECKING:
    from .base import VideoCandidate

_PROBE_TIMEOUT = 20
_FFMPEG_PROBE_TIMEOUT = 20
MIN_CLIP_BYTES = 2000  # a real few-second h264/aac mp4 is comfortably larger; catches HTML/JSON error bodies
DURATION_SLACK = 3.0   # seconds of tolerance either side of the requested clip length


def _require_yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError(
            "yt-dlp is not installed. Run `pip install yt-dlp` to enable "
            "youtube_video scenes (search, transcript matching, and segment "
            "download). No fallback to full-video download was attempted."
        ) from exc
    return yt_dlp


class _CapturingLogger:
    """Swallows yt-dlp's own informational messages (to_screen/to_stderr) into
    a list instead of letting them print directly — quieter logs without
    passing quiet=True (which would also suppress ffmpeg's own diagnostics).
    NOTE: this does NOT capture ffmpeg's own stderr — yt-dlp's FFmpegFD
    invokes ffmpeg with no stdout/stderr redirection at all, so ffmpeg writes
    straight to the process's real, inherited file descriptors, bypassing
    this logger entirely. See _capture_fd2() below for what actually does."""

    def __init__(self):
        self.lines: List[str] = []

    def debug(self, msg):
        self.lines.append(str(msg))

    def warning(self, msg):
        self.lines.append(str(msg))

    def error(self, msg):
        self.lines.append(str(msg))


@contextlib.contextmanager
def _capture_fd2():
    """Temporarily redirect the process's real OS-level stderr (file
    descriptor 2) into a pipe, so whatever a child subprocess writes there
    can actually be read back. This exists specifically because yt-dlp's
    FFmpegFD spawns ffmpeg with no stdout/stderr redirection at all — ffmpeg's
    real diagnostics (e.g. "HTTP error 403 Forbidden") go straight to the
    inherited fd and are invisible to yt-dlp's own logger/exception, and
    invisible to a fresh separate probe request too (a new extract_info()
    call mints a new signed URL, which isn't necessarily bound to the same
    session/token as the one that actually failed).

    fd 2 is process-wide, not per-thread, so this briefly affects any other
    thread's raw stderr writes too — acceptable for the short window a single
    ffmpeg segment-extraction attempt takes. Yields a callable returning the
    bytes captured so far; only meaningful after this context exits (fd 2 is
    restored, drain thread joined) — read it after the `with` block."""
    try:
        saved_fd = os.dup(2)
    except OSError:
        yield lambda: b""
        return
    read_fd, write_fd = os.pipe()
    buf = bytearray()

    def _drain():
        while True:
            try:
                chunk = os.read(read_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf.extend(chunk)

    drainer = threading.Thread(target=_drain, daemon=True)
    try:
        os.dup2(write_fd, 2)
        os.close(write_fd)
        drainer.start()
        yield lambda: bytes(buf)
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)
        drainer.join(timeout=2)
        try:
            os.close(read_fd)
        except OSError:
            pass


# ---------- failure classification ----------

class FailureKind(str, enum.Enum):
    HTTP_403 = "http_403"
    DRM = "drm"
    UNAVAILABLE = "unavailable"
    FORMAT_MISSING = "format_missing"
    JS_CHALLENGE = "js_challenge"
    INVALID_OUTPUT = "invalid_output"
    OTHER = "other"
    AGE_RESTRICTED = "age_restricted"
    BOT_BLOCKED = "bot_blocked"
    CONSENT_FAILED = "consent_failed"
    PLAYBACK_FAILED = "playback_failed"
    CAPTURE_FAILED = "capture_failed"
    TIMEOUT = "timeout"
    BROWSER_CRASHED = "browser_crashed"
    CONVERSION_FAILED = "conversion_failed"

    @property
    def is_candidate_fatal(self) -> bool:
        """True when retrying this SAME candidate with a different strategy
        is pointless — the problem is the video itself, not the request:
        DRM can never be bypassed here (and never should be), and an
        unavailable/private/removed video won't become available under a
        different player client. Browser-playback failures are also fatal
        for this candidate so we never fall through into the legacy yt-dlp
        chain for the same video."""
        return self in (
            FailureKind.DRM,
            FailureKind.UNAVAILABLE,
            FailureKind.AGE_RESTRICTED,
            FailureKind.BOT_BLOCKED,
            FailureKind.CONSENT_FAILED,
            FailureKind.PLAYBACK_FAILED,
            FailureKind.CAPTURE_FAILED,
            FailureKind.TIMEOUT,
            FailureKind.BROWSER_CRASHED,
            FailureKind.CONVERSION_FAILED,
        )


def classify_failure(exc_text: str, stderr_text: str) -> FailureKind:
    """Classify a failed acquisition attempt from the REAL captured output
    (ffmpeg's actual stderr via _capture_fd2, not just yt-dlp's opaque
    exception text) — see module docstring for why each kind is handled
    differently by the strategy/candidate loops."""
    text = (exc_text + "\n" + stderr_text).lower()
    if "drm" in text and "protected" in text:
        return FailureKind.DRM
    if (
        "video unavailable" in text or "private video" in text
        or "no longer available" in text or "has been removed" in text
        or "account associated with this video has been terminated" in text
        or "this video is not available" in text
    ):
        return FailureKind.UNAVAILABLE
    if (
        "403" in text or "forbidden" in text or "access denied" in text
        or "po token" in text or "sign in to confirm" in text
    ):
        return FailureKind.HTTP_403
    if "requested format is not available" in text or "no video formats found" in text:
        return FailureKind.FORMAT_MISSING
    if "page needs to be reloaded" in text or ("js" in text and "runtime" in text):
        return FailureKind.JS_CHALLENGE
    return FailureKind.OTHER


def _friendly_message(kind: FailureKind, exc_text: str, stderr_text: str) -> str:
    tail = "\n".join(stderr_text.strip().splitlines()[-6:])
    if kind == FailureKind.HTTP_403:
        return (
            "YouTube rejected the download (HTTP 403) — yt-dlp could not obtain "
            "a valid Proof-of-Origin token for this stream/format. External "
            "YouTube/yt-dlp limitation, not a bug in this app.\n" + (tail or exc_text)
        )
    if kind == FailureKind.DRM:
        return "This video is DRM-protected — cannot be used (never bypassed)."
    if kind == FailureKind.UNAVAILABLE:
        return f"Video is unavailable/private/removed.\n{tail or exc_text}"
    if kind == FailureKind.AGE_RESTRICTED:
        return "This video is age-restricted and cannot be played in the capture browser."
    if kind == FailureKind.BOT_BLOCKED:
        return "playback blocked: bot verification"
    if kind == FailureKind.CONSENT_FAILED:
        return "Could not pass the YouTube cookie-consent screen."
    if kind == FailureKind.PLAYBACK_FAILED:
        return f"YouTube player did not start or seek.\n{tail or exc_text}"
    if kind == FailureKind.CAPTURE_FAILED:
        return f"captureStream/MediaRecorder produced no usable clip.\n{tail or exc_text}"
    if kind == FailureKind.TIMEOUT:
        return f"Browser acquisition timed out.\n{tail or exc_text}"
    if kind == FailureKind.BROWSER_CRASHED:
        return f"Chrome/worker crashed.\n{tail or exc_text}"
    if kind == FailureKind.CONVERSION_FAILED:
        return f"ffmpeg could not convert the captured WebM to MP4.\n{tail or exc_text}"
    if tail:
        return f"{exc_text}\n{tail}"
    return exc_text


class StrategyFailed(Exception):
    def __init__(self, kind: FailureKind, exc_text: str, stderr_text: str):
        self.kind = kind
        self.exc_text = exc_text
        self.stderr_text = stderr_text
        self.message = _friendly_message(kind, exc_text, stderr_text)
        super().__init__(self.message)


# ---------- real media validation (never trust "download_segment returned" alone) ----------

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
_VIDEO_STREAM_RE = re.compile(r"Stream #\d+:\d+.*Video:")


def validate_clip(path: Path, expected_duration: float, log: LogFn = print) -> Optional[str]:
    """Returns None if `path` is a real, usable clip; otherwise a short human
    reason it must be rejected. Uses only the bundled `ffmpeg` binary (no
    ffprobe — the app doesn't bundle it) plus the existing magic-byte sniffer
    already used elsewhere in this provider, so this works identically in the
    packaged app as in dev. Checks: exists, not a .part leftover, minimum
    size, real video magic bytes (not HTML/JSON/thumbnail), ffmpeg can open
    it, has a video stream, and duration is in the right ballpark — not 0s,
    and not "somehow got the whole source video"."""
    if not path.is_file():
        return "output file does not exist"
    if path.name.endswith(".part") or path.name.endswith(".temp"):
        return "output is a partial/temp file, not a finished clip"
    size = path.stat().st_size
    if size < MIN_CLIP_BYTES:
        return f"output is only {size} bytes — too small to be a real video clip"

    kind = sniff_media_kind(path)
    if kind is not None and kind != "video":
        return f"output content is a {kind}, not a video"

    try:
        probe = hidden_subprocess.run(
            ["ffmpeg", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, timeout=_FFMPEG_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"could not inspect output with ffmpeg: {exc}"

    stderr = probe.stderr or ""
    if not _VIDEO_STREAM_RE.search(stderr):
        return "output has no video stream (audio-only or unreadable)"

    m = _DURATION_RE.search(stderr)
    if not m:
        return "ffmpeg reported no duration for the output"
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    if duration < 0.3:
        return f"output duration is {duration:.2f}s — effectively empty"
    if duration > expected_duration + DURATION_SLACK + 5.0:
        # Generous upper bound — this is the "produced the whole source
        # instead of a segment" case, which must never be silently accepted.
        return (
            f"output duration is {duration:.2f}s, far longer than the "
            f"requested ~{expected_duration:.1f}s segment"
        )
    return None


# ---------- the shared low-level acquisition attempt ----------

_CLIENT_URL_RE = re.compile(r"[?&]c=([A-Za-z0-9_]+)")


def _resolved_format_clients(info: dict) -> List[str]:
    """Which player client each SELECTED format's stream URL actually came
    from. yt-dlp doesn't label a format dict with its source client, but the
    client identity is embedded in the googlevideo.com URL's own `c=` query
    parameter — confirmed empirically (every diagnostic run in this
    project's history shows e.g. c=ANDROID_VR, c=MWEB, c=WEB, c=TVHTML5).
    Returns one entry per requested format (video, audio), e.g. ["MWEB",
    "MWEB"] or ["ANDROID_VR"] for a mismatched pool."""
    clients = []
    for fmt in info.get("requested_formats") or [info]:
        if not fmt:
            continue
        m = _CLIENT_URL_RE.search(fmt.get("url") or "")
        if m:
            clients.append(m.group(1).upper())
    return clients


def _run_attempt(
    candidate: "VideoCandidate",
    start: float,
    duration: float,
    dest: Path,
    format_selector: str,
    extractor_args: Optional[dict],
    expected_client: Optional[str] = None,
) -> None:
    """One real yt-dlp + ffmpeg invocation: download_ranges + force_keyframes_
    at_cuts (never a full-video download), real stderr captured via
    _capture_fd2, classified via classify_failure(). Raises StrategyFailed on
    any failure; on success, `dest` exists. This is the one place that
    actually talks to yt-dlp/ffmpeg — every strategy below only varies
    `format_selector`/`extractor_args`, never this mechanism.

    `expected_client` (e.g. "MWEB", "WEB") is an explicit consistency check:
    when set, the resolved format(s) actually selected must have come from
    that exact client — see _resolved_format_clients. If yt-dlp's default
    multi-client pool lets a DIFFERENT client's stream win the format
    selector (the audited mismatch: a PO token minted for one client while
    another client's stream gets downloaded), that resolution is REJECTED
    rather than silently accepted. Callers that don't need this guarantee
    (DashDefaultStrategy, AlternateClientStrategy) simply omit it — unchanged
    behavior."""
    yt_dlp = _require_yt_dlp()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_out = Path(tmp) / "clip.%(ext)s"
        logger = _CapturingLogger()
        opts = {
            # NOT quiet: True — yt-dlp's FFmpegFD reads `quiet` to decide
            # ffmpeg's own -loglevel flag (independent of Python-side
            # logging), so quiet=True makes it pass "-loglevel quiet" and
            # ffmpeg's real stderr is never produced at all, not just
            # unprinted. `logger` above already keeps yt-dlp's own console
            # output silent.
            "no_warnings": True,
            "logger": logger,
            "format": format_selector,
            "merge_output_format": "mp4",
            "outtmpl": str(tmp_out),
            "download_ranges": yt_dlp.utils.download_range_func(None, [(start, start + duration)]),
            "force_keyframes_at_cuts": True,
            "socket_timeout": _PROBE_TIMEOUT,
        }
        if extractor_args:
            opts["extractor_args"] = extractor_args

        caught: List[Exception] = []
        info: Optional[dict] = None
        with _capture_fd2() as get_captured:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    # extract_info(download=True) instead of download() — same
                    # download, but returns the info dict so the format(s)
                    # actually selected can be inspected for the consistency
                    # check below. No behavior change for callers that don't
                    # pass expected_client.
                    info = ydl.extract_info(candidate.url, download=True)
            except Exception as exc:
                caught.append(exc)
        stderr_text = get_captured().decode("utf-8", "replace")

        if caught:
            kind = classify_failure(str(caught[0]), stderr_text)
            raise StrategyFailed(kind, str(caught[0]), stderr_text)

        produced = list(Path(tmp).glob("clip.*"))
        if not produced:
            raise StrategyFailed(FailureKind.INVALID_OUTPUT, "no output file produced", stderr_text)

        if expected_client is not None:
            resolved = _resolved_format_clients(info or {})
            mismatched = [c for c in resolved if c != expected_client]
            if mismatched:
                for leftover in Path(tmp).glob("*"):
                    leftover.unlink(missing_ok=True)
                raise StrategyFailed(
                    FailureKind.OTHER,
                    f"client consistency check failed: requested {expected_client}, "
                    f"resolved format(s) actually came from {resolved or 'unknown'} — rejected, not downloaded",
                    stderr_text,
                )

        # Clean up any stray partial/temp leftovers regardless of outcome —
        # spec §17: only the final canonical asset may ever remain.
        produced[0].replace(dest)
        for leftover in Path(tmp).glob("*"):
            leftover.unlink(missing_ok=True)


# ---------- strategies ----------

class AcquisitionStrategy:
    name: str = "base"

    def can_handle(self, candidate: "VideoCandidate") -> bool:
        """Cheap, no-network check for whether this strategy is worth trying
        at all for this candidate (e.g. PoTokenStrategy skips itself when no
        provider is installed). Default: always worth trying — most
        strategies' real availability can only be known by attempting them
        (yt-dlp already fails cleanly/classifiably when a format family
        doesn't exist for a video, so a separate probe call would just be a
        second network round trip for the same answer)."""
        return True

    def download_segment(self, candidate: "VideoCandidate", start: float, duration: float, dest: Path) -> None:
        """Raise StrategyFailed on any failure. Must not leave partial files
        behind (handled by the shared _run_attempt helper)."""
        raise NotImplementedError


class DashDefaultStrategy(AcquisitionStrategy):
    """The current/default acquisition: yt-dlp's own default player-client
    resolution (no override), DASH video+audio merged by ffmpeg. This is the
    strategy that already worked in the majority of prior real-world tests."""

    name = "dash_default"

    def __init__(self, format_selector: str):
        self.format_selector = format_selector

    def download_segment(self, candidate, start, duration, dest) -> None:
        _run_attempt(candidate, start, duration, dest, self.format_selector, extractor_args=None)


class AlternateClientStrategy(AcquisitionStrategy):
    """Same DASH format family, different yt-dlp player-client identity.
    Client names must be real entries in the installed yt-dlp version's own
    INNERTUBE_CLIENTS registry — verified (not guessed) against
    yt_dlp/extractor/youtube/_base.py: `tv` and `web_embedded` are the two
    that do not declare a required Proof-of-Origin token, unlike web/
    web_safari/android/ios/mweb (confirmed empirically unusable without one)."""

    def __init__(self, client: str, format_selector: str):
        self.client = client
        self.name = f"client_{client}"
        self.format_selector = format_selector

    def download_segment(self, candidate, start, duration, dest) -> None:
        _run_attempt(
            candidate, start, duration, dest, self.format_selector,
            extractor_args={"youtube": {"player_client": [self.client]}},
        )


class HlsStrategy(AcquisitionStrategy):
    """Prefer an HLS (m3u8) stream via the web_safari client — the client
    confirmed (audit + real testing) to actually expose HLS formats, and a
    structurally different delivery path from the DASH GVS requests that hit
    the 403/PO-token wall, so it can succeed independently of that problem.

    Explicitly forces player_client=web_safari via extractor_args (fixes the
    audited mismatch: with no override, yt-dlp queries android_vr AND
    web_safari together, and the format selector could silently pick an
    android_vr stream instead of the HLS one this strategy exists for) and
    verifies (expected_client="WEB" — web_safari's own INNERTUBE clientName
    is "WEB", shared with the plain "web" client) that the resolved stream
    really did come from that client, not android_vr. yt-dlp's own
    format-selector syntax already fails cleanly (classified as
    FORMAT_MISSING) when no HLS format exists for a video."""

    name = "hls"

    def download_segment(self, candidate, start, duration, dest) -> None:
        _run_attempt(
            candidate, start, duration, dest,
            format_selector="best[protocol*=m3u8]/bestvideo[protocol*=m3u8]+bestaudio[protocol*=m3u8]",
            extractor_args={"youtube": {"player_client": ["web_safari"]}},
            expected_client="WEB",
        )


def _po_token_provider_available() -> bool:
    """Detect whether a real yt-dlp PO-Token provider PLUGIN is installed and
    registered — using yt-dlp's own supported plugin-registry mechanism
    (yt_dlp.extractor.youtube.pot._registry), not a homemade token
    implementation (spec explicitly forbids inventing one). Returns False
    (clean skip) if none is registered, if yt-dlp isn't installed, or if this
    internal API differs in some future yt-dlp version — never raises."""
    try:
        from yt_dlp.extractor.youtube.pot._registry import _pot_providers
        return bool(_pot_providers.value)
    except Exception:
        return False


class PoTokenStrategy(AcquisitionStrategy):
    """Only viable when the user has separately installed a real yt-dlp
    PO-Token provider plugin (e.g. bgutil-ytdlp-pot-provider) — this project
    does not bundle, install, or implement one itself, and does not store or
    hardcode any token.

    Explicitly forces player_client=mweb via extractor_args (fixes the
    audited mismatch: with no override, yt-dlp's default resolution queries
    android_vr AND web_safari together — a PO token gets minted for
    web_safari, but the format selector can pick android_vr's stream
    instead, so the token goes completely unused) and verifies
    (expected_client="MWEB") that the resolved stream really did come from
    mweb, not android_vr. mweb is one of the clients that HARD-requires a PO
    token per yt-dlp's own client policy, so a successful download here
    means the installed bgutil provider's token was genuinely necessary and
    used — not incidental."""

    name = "po_token"

    def can_handle(self, candidate) -> bool:
        return _po_token_provider_available()

    def download_segment(self, candidate, start, duration, dest) -> None:
        _run_attempt(
            candidate, start, duration, dest,
            format_selector="bestvideo+bestaudio/best",
            extractor_args={"youtube": {"player_client": ["mweb"]}},
            expected_client="MWEB",
        )


_WORKER_KIND_TO_FAILURE = {
    "unavailable": FailureKind.UNAVAILABLE,
    "age_restricted": FailureKind.AGE_RESTRICTED,
    "bot_blocked": FailureKind.BOT_BLOCKED,
    "consent_failed": FailureKind.CONSENT_FAILED,
    "playback_failed": FailureKind.PLAYBACK_FAILED,
    "capture_failed": FailureKind.CAPTURE_FAILED,
    "timeout": FailureKind.TIMEOUT,
    "browser_crashed": FailureKind.BROWSER_CRASHED,
    "conversion_failed": FailureKind.CONVERSION_FAILED,
    "drm": FailureKind.DRM,
}


def map_browser_kind(kind: Optional[str]) -> FailureKind:
    if not kind:
        return FailureKind.PLAYBACK_FAILED
    return _WORKER_KIND_TO_FAILURE.get(kind, FailureKind.PLAYBACK_FAILED)


class BrowserPlaybackStrategy(AcquisitionStrategy):
    """PRIMARY acquisition: real Chrome YouTube playback + captureStream().

    Does not extract googlevideo URLs. Legacy yt-dlp strategies run only when
    this strategy cannot start on the machine (no Chrome/Node/playwright-core).
    """

    name = "browser_playback"

    def can_handle(self, candidate: "VideoCandidate") -> bool:
        from .acquisition.browser_client import browser_available

        return browser_available()

    def download_segment(self, candidate, start, duration, dest) -> None:
        from .acquisition.browser_client import get_client

        dest = Path(dest)
        client = get_client()
        result = client.acquire(candidate.video_id, start, duration, dest)
        if result.get("ok"):
            return
        kind = map_browser_kind(result.get("kind"))
        message = result.get("error") or kind.value
        raise StrategyFailed(kind, message, message)


def _legacy_yt_dlp_chain(format_selector: str) -> List[AcquisitionStrategy]:
    return [
        DashDefaultStrategy(format_selector),
        AlternateClientStrategy("tv", format_selector),
        AlternateClientStrategy("web_embedded", format_selector),
        HlsStrategy(),
        PoTokenStrategy(),
    ]


def build_strategy_chain(format_selector: str) -> List[AcquisitionStrategy]:
    """Browser playback is the only per-candidate strategy when the worker can
    run. The yt-dlp chain is legacy and is used only if Chrome/Node are missing."""
    browser = BrowserPlaybackStrategy()
    if browser.can_handle(None):  # type: ignore[arg-type]
        return [browser]
    return _legacy_yt_dlp_chain(format_selector)


@dataclasses.dataclass
class StrategyAttempt:
    strategy: str
    kind: str  # FailureKind value, or "success"


@dataclasses.dataclass
class AcquisitionOutcome:
    ok: bool
    strategy: Optional[str] = None
    attempts: List[StrategyAttempt] = dataclasses.field(default_factory=list)
    last_message: Optional[str] = None


class AllStrategiesFailed(RuntimeError):
    """Raised by YtDlpBackend.download_segment() when every strategy in the
    chain failed for one candidate. Carries the full AcquisitionOutcome (not
    just a message) so callers that want structured diagnostics — see
    providers/youtube/base.py's exhaustion summary — can use it; callers that
    only care about `str(exc)` (or the AssetProvider abstract interface,
    which just says "raises on failure") work unchanged either way."""

    def __init__(self, outcome: "AcquisitionOutcome"):
        self.outcome = outcome
        kinds = ", ".join(f"{a.strategy}={a.kind}" for a in outcome.attempts) or "no strategy was applicable"
        super().__init__(f"All acquisition strategies failed ({kinds}). Last reason: {outcome.last_message}")


def run_strategy_chain(
    strategies: List[AcquisitionStrategy],
    candidate: "VideoCandidate",
    start: float,
    duration: float,
    dest: Path,
    log: LogFn,
    validate=validate_clip,
) -> AcquisitionOutcome:
    """Try each strategy in order for ONE candidate; stop at the first one
    that produces a real, validated clip. A DRM/UNAVAILABLE classification
    stops trying further strategies for this candidate immediately (spec
    §9 — never repeatedly retry an unusable video); any other failure moves
    on to the next strategy. Never repeats the same (candidate, strategy)
    pair (each strategy runs at most once here, satisfying spec §15).

    `validate` is injectable (defaults to the real ffmpeg-based validate_clip)
    so tests can exercise this function's orchestration/classification logic
    in isolation from real media validation, which has its own focused tests."""
    outcome = AcquisitionOutcome(ok=False)
    dest = Path(dest)
    for strategy in strategies:
        if not strategy.can_handle(candidate):
            continue
        log(f"[YOUTUBE] Strategy: {strategy.name}")
        if strategy.name == "browser_playback":
            log("[YOUTUBE] -> browser acquisition")
        try:
            strategy.download_segment(candidate, start, duration, dest)
        except StrategyFailed as fail:
            log(f"[YOUTUBE] Strategy: {strategy.name} -> Result: {fail.kind.value}")
            outcome.attempts.append(StrategyAttempt(strategy.name, fail.kind.value))
            outcome.last_message = fail.message
            if fail.kind.is_candidate_fatal:
                log(f"[YOUTUBE] {fail.kind.value.upper()} — not retrying this candidate with another strategy")
                break
            continue

        reject_reason = validate(dest, expected_duration=duration, log=log)
        if reject_reason is not None:
            log(f"[YOUTUBE] Strategy: {strategy.name} -> Result: rejected ({reject_reason})")
            dest.unlink(missing_ok=True)
            outcome.attempts.append(StrategyAttempt(strategy.name, FailureKind.INVALID_OUTPUT.value))
            outcome.last_message = reject_reason
            continue

        log(f"[YOUTUBE] Strategy: {strategy.name} -> Result: SUCCESS")
        if strategy.name == "browser_playback":
            log(f"[BROWSER] validated: {duration:.1f}s")
        outcome.ok = True
        outcome.strategy = strategy.name
        outcome.attempts.append(StrategyAttempt(strategy.name, "success"))
        return outcome

    return outcome
