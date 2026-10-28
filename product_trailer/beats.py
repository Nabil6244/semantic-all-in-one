"""Beat / onset detection for cutting on the music. librosa when importable; otherwise ffmpeg -> mono PCM, numpy spectral-flux onsets
and a tempo from the onset envelope's autocorrelation. No music -> a 110 bpm grid."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

SR = 22050
HOP = 512
NO_MUSIC_BPM = 110.0
MAX_LEN_S = 95.0
DEFAULT_LEN_S = 60.0


@dataclass
class BeatInfo:
    duration: float
    tempo: float
    beats: List[float] = field(default_factory=list)       # regular beat grid locked to the onsets
    onsets: List[float] = field(default_factory=list)
    source: str = "grid"


def _ffmpeg() -> str:
    try:
        from map_scene.render import _ffmpeg as f

        return f()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg") or "ffmpeg"


def decode_mono(path, sr: int = SR) -> np.ndarray:
    cmd = [_ffmpeg(), "-v", "error", "-nostdin", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"reading the audio {path} took too long") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"could not read audio {path}: {proc.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def onset_envelope(y: np.ndarray, sr: int = SR, hop: int = HOP, n_fft: int = 2048) -> np.ndarray:
    y = np.pad(y, (n_fft // 2, n_fft // 2))          # centred frames: frame i is time i * hop
    if len(y) < n_fft:
        y = np.pad(y, (0, n_fft - len(y)))
    n = 1 + (len(y) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n)[:, None]
    frames = y[idx] * np.hanning(n_fft)[None, :]
    mag = np.log1p(10.0 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")    # remove the slow loudness trend
    flux = np.maximum(flux, 0.0)
    return flux / (flux.max() or 1.0)


def pick_onsets(env: np.ndarray, sr: int = SR, hop: int = HOP, thresh: float = 0.15, min_gap_s: float = 0.1) -> List[float]:
    out, last = [], -1e9
    gap = min_gap_s * sr / hop
    for i in range(1, len(env) - 1):
        if env[i] >= thresh and env[i] >= env[i - 1] and env[i] > env[i + 1] and i - last >= gap:
            out.append(i * hop / sr)
            last = i
    return out


def estimate_tempo(env: np.ndarray, sr: int = SR, hop: int = HOP, lo: float = 70.0, hi: float = 180.0) -> float:
    e = env - env.mean()
    ac = np.correlate(e, e, mode="full")[len(e) - 1:]
    fps = sr / hop
    lags = np.arange(len(ac))
    lmin, lmax = int(fps * 60 / hi), int(min(len(ac) - 1, fps * 60 / lo))
    if lmax <= lmin:
        return NO_MUSIC_BPM
    seg = ac[lmin:lmax + 1]
    k = int(np.argmax(seg)) + lmin
    if 0 < k < len(ac) - 1:                                    # parabolic refinement
        a, b, c = ac[k - 1], ac[k], ac[k + 1]
        d = (a - 2 * b + c)
        k = k + (0.5 * (a - c) / d if d else 0.0)
    return float(60.0 * fps / k) if k else NO_MUSIC_BPM
    _ = lags


def beat_grid(onsets: List[float], tempo: float, duration: float) -> List[float]:
    """A regular grid at the tempo whose phase best matches the onsets."""
    period = 60.0 / tempo
    if onsets:
        best, best_score = 0.0, -1.0
        for ph in np.linspace(0, period, 48, endpoint=False):
            o = np.asarray(onsets)
            d = np.abs(((o - ph + period / 2) % period) - period / 2)
            score = float(np.sum(np.exp(-(d / 0.04) ** 2)))
            if score > best_score:
                best, best_score = float(ph), score
        phase = best
    else:
        phase = 0.0
    return [round(float(t), 3) for t in np.arange(phase, duration + 1e-6, period)]


def grid(duration: float = DEFAULT_LEN_S, bpm: float = NO_MUSIC_BPM) -> BeatInfo:
    p = 60.0 / bpm
    return BeatInfo(duration=duration, tempo=bpm, beats=[round(i * p, 3) for i in range(int(duration / p) + 1)], source="grid")


def detect(music_path: Optional[str] = None, max_len: float = MAX_LEN_S) -> BeatInfo:
    if not music_path:
        return grid()
    try:
        import librosa  # type: ignore

        y, sr = librosa.load(str(music_path), sr=SR, mono=True)
        dur = len(y) / sr
        tempo, frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=HOP)
        on = librosa.onset.onset_detect(y=y, sr=sr, hop_length=HOP, units="time")
        beats = [round(float(t), 3) for t in librosa.frames_to_time(frames, sr=sr, hop_length=HOP)]
        tempo = float(np.atleast_1d(tempo)[0]) or NO_MUSIC_BPM
        if len(beats) < 4:
            beats = beat_grid(list(on), tempo, dur)
        info = BeatInfo(duration=dur, tempo=tempo, beats=beats, onsets=[float(t) for t in on], source="librosa")
    except Exception:  # noqa: BLE001 -- librosa missing or failed: numpy path
        y = decode_mono(music_path)
        dur = len(y) / SR
        if dur < 1.0:
            return grid()
        env = onset_envelope(y)
        on = pick_onsets(env)
        tempo = estimate_tempo(env)
        info = BeatInfo(duration=dur, tempo=tempo, beats=beat_grid(on, tempo, dur), onsets=on, source="numpy")
    info.duration = min(info.duration, max_len)
    info.beats = [b for b in info.beats if b <= info.duration + 1e-6]
    info.onsets = [o for o in info.onsets if o <= info.duration + 1e-6]
    if len(info.beats) < 4:
        g = grid(info.duration, info.tempo or NO_MUSIC_BPM)
        info.beats = g.beats
    return info
