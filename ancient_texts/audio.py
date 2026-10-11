"""Opt-in loudness finishing for a finished Enoch Template video (no other style ever calls this).

Measure the real output with ffmpeg's EBU R128 meter (`ebur128=peak=true`), normalise the AUDIO ONLY with two-pass
`loudnorm` (linear when possible) plus a true-peak ceiling, copy the video stream bit for bit (`-c:v copy`), then measure
the result again. The file is replaced only when the re-measurement meets the Required ceiling (true peak ≤ −1 dBTP);
otherwise the original stays and the result says why. A file without audio is left untouched. Nothing here guesses:
every number reported comes from a measurement of an actual file.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

TARGET_LUFS = -16.0
TOLERANCE_LU = 1.5
TRUE_PEAK_CEILING = -1.0           # Required
LOUDNORM_TP = -1.5                 # headroom under the ceiling for the encoder's inter-sample peaks
DURATION_TOLERANCE_S = 0.06


class AudioToolError(RuntimeError):
    """ffmpeg/ffprobe or a needed filter is missing: says exactly what."""


@dataclasses.dataclass(frozen=True)
class Loudness:
    integrated_lufs: float
    loudness_range_lu: float
    true_peak_dbtp: float

    def within_target(self) -> bool:
        return abs(self.integrated_lufs - TARGET_LUFS) <= TOLERANCE_LU

    def peak_ok(self) -> bool:
        return self.true_peak_dbtp <= TRUE_PEAK_CEILING


@dataclasses.dataclass
class FinishResult:
    status: str                    # finished | no_audio | failed | skipped
    before: Optional[Loudness] = None
    after: Optional[Loudness] = None
    video_stream_identical: Optional[bool] = None
    duration_delta_s: Optional[float] = None
    message: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def ffmpeg_bin() -> str:
    here = Path(__file__).resolve().parent.parent / "bin"
    for name in ("ffmpeg.exe", "ffmpeg"):
        if (here / name).is_file():
            return str(here / name)
    found = shutil.which("ffmpeg")
    if not found:
        raise AudioToolError("ffmpeg was not found (bin/ffmpeg or PATH); loudness cannot be measured or finished")
    return found


def ffprobe_bin() -> str:
    here = Path(__file__).resolve().parent.parent / "bin"
    for name in ("ffprobe.exe", "ffprobe"):
        if (here / name).is_file():
            return str(here / name)
    found = shutil.which("ffprobe")
    if not found:
        raise AudioToolError("ffprobe was not found (bin/ffprobe or PATH)")
    return found


def _run(cmd, timeout: float = 1800.0) -> subprocess.CompletedProcess:
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, **kwargs)


def check_filters(ffmpeg: Optional[str] = None) -> None:
    ff = ffmpeg or ffmpeg_bin()
    out = _run([ff, "-hide_banner", "-filters"], timeout=60).stdout
    missing = [f for f in ("ebur128", "loudnorm", "alimiter") if not re.search(rf"\s{f}\s", out)]
    if missing:
        raise AudioToolError(f"this ffmpeg lacks the filter(s) {', '.join(missing)}; loudness finishing is unavailable")


def has_audio(path: Path) -> bool:
    out = _run([ffprobe_bin(), "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
               timeout=60).stdout
    return bool(out.strip())


def _stream_duration(path: Path, kind: str) -> float:
    out = _run([ffprobe_bin(), "-v", "error", "-select_streams", f"{kind}:0", "-show_entries", "stream=duration:format=duration",
                "-of", "json", str(path)], timeout=60).stdout
    try:
        data = json.loads(out or "{}")
        d = (data.get("streams") or [{}])[0].get("duration") or (data.get("format") or {}).get("duration")
        return float(d)
    except (ValueError, TypeError, IndexError):
        return float("nan")


def video_stream_md5(path: Path) -> str:
    """md5 of the video stream's packets (identical when the stream was copied)."""
    r = _run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy", "-f", "md5", "-"], timeout=600)
    return r.stdout.strip()


def measure(path) -> Loudness:
    """Integrated loudness, loudness range and true peak of the file's first audio stream (ffmpeg ebur128, peak=true)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    ff = ffmpeg_bin()
    r = _run([ff, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    text = r.stderr
    summary = text[text.rfind("Summary:"):] if "Summary:" in text else ""
    if not summary:
        raise AudioToolError(f"ebur128 gave no summary for {path.name}: {text.strip()[-300:]}")
    i = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", summary)
    lra = re.search(r"LRA:\s*(-?[\d.]+)\s*LU", summary)
    peak = re.search(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS", summary)
    if not (i and lra and peak):
        raise AudioToolError(f"could not read the ebur128 summary for {path.name}")
    f = lambda s: float("-inf") if s == "-inf" else float(s)  # noqa: E731
    return Loudness(integrated_lufs=f(i.group(1)), loudness_range_lu=f(lra.group(1)), true_peak_dbtp=f(peak.group(1)))


def _loudnorm_pass1(path: Path) -> dict:
    r = _run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
              "-af", f"loudnorm=I={TARGET_LUFS}:TP={LOUDNORM_TP}:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise AudioToolError(f"loudnorm measurement failed: {r.stderr.strip()[-300:]}")
    return json.loads(m.group(0))


def _render(src: Path, dst: Path, m: dict, sample_rate: int, extra_gain_db: float) -> None:
    af = (f"loudnorm=I={TARGET_LUFS}:TP={LOUDNORM_TP}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
          f"aresample={sample_rate}")
    if extra_gain_db:
        af += f",volume={extra_gain_db:.2f}dB"
    af += f",alimiter=limit={10 ** (LOUDNORM_TP / 20):.4f}:level=disabled:attack=5:release=50"
    r = _run([ffmpeg_bin(), "-y", "-hide_banner", "-nostats", "-i", str(src), "-map", "0:v?", "-map", "0:a:0",
              "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate),
              "-movflags", "+faststart", str(dst)])
    if r.returncode != 0 or not dst.is_file():
        raise AudioToolError(f"finishing pass failed: {r.stderr.strip()[-400:]}")


def _sample_rate(path: Path) -> int:
    out = _run([ffprobe_bin(), "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate", "-of", "csv=p=0",
                str(path)], timeout=60).stdout.strip()
    try:
        return int(out) or 48000
    except ValueError:
        return 48000


def finish(path, *, keep_original: bool = False) -> FinishResult:
    """Finish `path` in place (audio only). keep_original=True keeps `<name>.before_finishing<ext>` next to it."""
    path = Path(path)
    try:
        check_filters()
        if not has_audio(path):
            return FinishResult(status="no_audio", message="no audio stream: nothing to finish, file untouched")
        before = measure(path)
        if before.within_target() and before.peak_ok():
            return FinishResult(status="finished", before=before, after=before, video_stream_identical=True, duration_delta_s=0.0,
                                message="already within target; file untouched")
        m = _loudnorm_pass1(path)
        sr = _sample_rate(path)
        v_md5 = video_stream_md5(path) if _has_video(path) else ""
        with tempfile.TemporaryDirectory(dir=str(path.parent)) as tmp:
            out = Path(tmp) / f"finished{path.suffix}"
            after, gain = None, 0.0
            for _attempt in range(3):                   # re-measure; trim gain if the encoder pushed a peak over
                _render(path, out, m, sr, gain)
                after = measure(out)
                if after.peak_ok():
                    break
                gain -= (after.true_peak_dbtp - TRUE_PEAK_CEILING) + 0.3
            identical = (video_stream_md5(out) == v_md5) if v_md5 else None
            delta = abs(_stream_duration(out, "a") - _stream_duration(path, "a"))
            if after is None or not after.peak_ok():
                return FinishResult(status="failed", before=before, after=after, video_stream_identical=identical,
                                    duration_delta_s=delta, message=f"true peak {after.true_peak_dbtp if after else '?'} dBTP "
                                    f"still above {TRUE_PEAK_CEILING}; original kept")
            if identical is False:
                return FinishResult(status="failed", before=before, after=after, video_stream_identical=False,
                                    duration_delta_s=delta, message="video stream changed; original kept")
            if not (delta <= DURATION_TOLERANCE_S):
                return FinishResult(status="failed", before=before, after=after, video_stream_identical=identical,
                                    duration_delta_s=delta, message=f"audio duration changed by {delta:.3f}s; original kept")
            if keep_original:
                shutil.copy2(path, path.with_name(f"{path.stem}.before_finishing{path.suffix}"))
            os.replace(out, path)
        msg = "finished" if after.within_target() else (f"finished; integrated loudness {after.integrated_lufs:.1f} LUFS is "
                                                         f"outside {TARGET_LUFS}±{TOLERANCE_LU} (soft deviation)")
        return FinishResult(status="finished", before=before, after=after, video_stream_identical=identical,
                            duration_delta_s=delta, message=msg)
    except AudioToolError as exc:
        return FinishResult(status="failed", message=str(exc))


def _has_video(path: Path) -> bool:
    out = _run([ffprobe_bin(), "-v", "error", "-select_streams", "v", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
               timeout=60).stdout
    return bool(out.strip())
