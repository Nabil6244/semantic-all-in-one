"""ONE-TIME asset builder for the explainer sound layer. Run by hand, never during a render:

    python3 -B explainer/motion/build_sfx.py            # writes explainer/assets/sfx/ (WAV files + manifest.json with SHA-256)
    python3 -B explainer/motion/build_sfx.py --check    # rebuilds in memory, compares bytes with the files on disk, writes nothing

Everything is synthesised with numpy from fixed seeds and closed-form maths: no outside audio, no network, no speech engine. Effects are mono 16-bit 44.1 kHz, peak -6 dBFS each (the
track builder lowers them to sit under speech). Beds are mono 16-bit 22.05 kHz, 30 s, every partial is a whole number of cycles in 30 s so the last sample runs straight into the first
(a seamless loop), RMS -18 dBFS. Nobody has listened to these; they are checked by measurement (explainer/spike/test_motion_sfx.py)."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import wave
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "assets" / "sfx"
ASSET_ID = "explainer_sfx_v1"
SR = 44100
BED_SR = 22050
BED_SECONDS = 30
PEAK = 0.5012          # -6 dBFS
BED_RMS = 0.1259       # -18 dBFS

# ---------------------------------------------------------------- helpers


def _t(dur: float, sr: int = SR) -> np.ndarray:
    return np.arange(int(round(dur * sr))) / sr


def _shape(x: np.ndarray, gain_fn, sr: int = SR) -> np.ndarray:
    """Zero-phase spectral shaping: multiply the spectrum by gain_fn(freqs_hz)."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    return np.fft.irfft(spec * gain_fn(f), n=len(x))


def _lowpass(x, fc, sr: int = SR, width=0.35):
    return _shape(x, lambda f: 1.0 / (1.0 + (f / fc) ** 4), sr)


def _highpass(x, fc, sr: int = SR):
    return _shape(x, lambda f: 1.0 / (1.0 + (fc / np.maximum(f, 1e-3)) ** 4), sr)


def _bandpass(x, lo, hi, sr: int = SR):
    return _shape(x, lambda f: (1.0 / (1.0 + (f / hi) ** 4)) * (1.0 / (1.0 + (lo / np.maximum(f, 1e-3)) ** 4)), sr)


def _swept_noise(rng, dur, f0, f1, ratio=1.8, segs=24):
    """Noise whose band (centre f0 -> f1 on a log scale, width = ratio) moves over time: overlapped Hann segments, each band-passed at its own centre."""
    n = int(round(dur * SR))
    seg = 2 * n // (segs + 1)
    hop = seg // 2
    out = np.zeros(n + seg)
    win = np.hanning(seg + 1)[:seg]
    for i in range(segs):
        c = f0 * (f1 / f0) ** (i / max(1, segs - 1))
        z = rng.standard_normal(seg)
        z = _bandpass(z, c / ratio, c * ratio)
        out[i * hop:i * hop + seg] += z * win
    return out[:n]


def _fade(x, fin=0.002, fout=0.01):
    a, b = int(fin * SR), int(fout * SR)
    x = x.copy()
    if a:
        x[:a] *= np.linspace(0, 1, a)
    if b:
        x[-b:] *= np.linspace(1, 0, b)
    return x


def _norm(x, peak=PEAK):
    m = float(np.max(np.abs(x)))
    return x * (peak / m) if m > 0 else x


# ---------------------------------------------------------------- effects


def stamp_thump():
    """Low body (cosine phase, so the peak is in the first millisecond) + a short soft noise burst. The file's first millisecond IS the impact."""
    rng = np.random.default_rng(1101)
    t = _t(0.38)
    f = 46 + 70 * np.exp(-t / 0.035)
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.cos(phase) * np.exp(-t / 0.10)
    burst = _lowpass(rng.standard_normal(len(t)), 1800) * np.exp(-t / 0.012)
    click = np.exp(-t / 0.0015) * 0.0
    x = body + 0.35 * burst / max(1e-9, np.max(np.abs(burst))) + click
    x[:14] *= np.linspace(0.0, 1.0, 14)
    return _norm(_fade(x, 0, 0.04))


def slide_whoosh():
    rng = np.random.default_rng(1102)
    d = 0.42
    t = _t(d)
    x = _swept_noise(rng, d, 380, 2300)
    env = np.sin(np.pi * np.minimum(1.0, t / d) ** 0.8) ** 2
    return _norm(_fade(_lowpass(x, 5500) * env, 0.01, 0.05))


def count_tick():
    rng = np.random.default_rng(1103)
    t = _t(0.05)
    x = np.sin(2 * np.pi * 1650 * t) * np.exp(-t / 0.006) + 0.25 * _lowpass(rng.standard_normal(len(t)), 5000) * np.exp(-t / 0.003)
    return _norm(_fade(x, 0.0004, 0.01))


def pop():
    t = _t(0.16)
    f = 340 + 760 * np.exp(-t / 0.025)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.04)
    return _norm(_fade(x, 0.0006, 0.03))


def paper_rustle():
    rng = np.random.default_rng(1105)
    d = 0.36
    t = _t(d)
    n = _bandpass(rng.standard_normal(len(t)), 1400, 5500)
    slow = np.abs(_lowpass(rng.standard_normal(len(t)), 38))
    slow = (slow / slow.max()) ** 1.6
    env = slow * np.sin(np.pi * t / d) ** 0.7
    return _norm(_fade(n * env, 0.01, 0.05))


def cross_scratch():
    """Two pen strokes of 5 frames (1/6 s) each, matching presets.CROSS_STROKE_FRAMES."""
    rng = np.random.default_rng(1106)
    d = 0.36
    t = _t(d)
    n = _bandpass(rng.standard_normal(len(t)), 1800, 4200)
    grain = 0.65 + 0.35 * np.sin(2 * np.pi * 85 * t)
    s = 1.0 / 6.0
    env = np.where(t < s, np.sin(np.pi * np.clip(t / s, 0, 1)) ** 0.8, 0.0) + np.where((t >= s + 0.02) & (t < 2 * s + 0.02), np.sin(np.pi * np.clip((t - s - 0.02) / s, 0, 1)) ** 0.8, 0.0)
    return _norm(_fade(n * grain * env, 0.004, 0.03))


def reveal_riser():
    rng = np.random.default_rng(1107)
    d = 1.1
    t = _t(d)
    n = _swept_noise(rng, d, 300, 2800, ratio=1.6)
    glide = np.sin(2 * np.pi * np.cumsum(220 * (2.0 ** (t / d))) / SR) * 0.5
    env = (t / d) ** 2
    x = _lowpass(n / max(1e-9, np.max(np.abs(n))) * 0.8 + glide, 4500) * env
    return _norm(_fade(x, 0.01, 0.07))


EFFECTS = {"stamp_thump": stamp_thump, "slide_whoosh": slide_whoosh, "count_tick": count_tick, "pop": pop, "paper_rustle": paper_rustle, "cross_scratch": cross_scratch, "reveal_riser": reveal_riser}

# ---------------------------------------------------------------- beds
# chords as MIDI notes, four per bed (7.5 s each, cross-faded with cos^2 so the sum is flat)
MOODS = {
    "neutral": ((45, 52, 57, 60, 64), (41, 48, 57, 60, 65), (48, 55, 60, 64, 67), (43, 50, 59, 62, 67)),          # Am9-ish, Fmaj7, Cmaj, G6
    "tense": ((38, 45, 50, 53, 57), (37, 44, 50, 53, 56), (34, 41, 46, 50, 53), (38, 45, 51, 53, 57)),          # Dm, Db-ish cluster, Bb, Dm(b5)
    "warm": ((48, 55, 59, 64, 67), (45, 52, 55, 60, 64), (41, 48, 53, 57, 64), (43, 50, 55, 59, 62)),            # Cmaj7, Am7, Fmaj7, G
}


def _q(freq: float) -> float:
    """Snap a frequency to a whole number of cycles in BED_SECONDS."""
    return round(freq * BED_SECONDS) / BED_SECONDS


def bed(mood: str) -> np.ndarray:
    n = BED_SR * BED_SECONDS
    t = np.arange(n) / BED_SR
    period = BED_SECONDS / 4.0
    out = np.zeros(n)
    for ci, chord in enumerate(MOODS[mood]):
        d = (t - ci * period + BED_SECONDS / 2) % BED_SECONDS - BED_SECONDS / 2          # circular distance to the chord's centre
        w = np.where(np.abs(d) < period, np.cos(np.pi * d / (2 * period)) ** 2, 0.0)
        c = np.zeros(n)
        for ni, midi in enumerate(chord):
            f0 = 440.0 * 2 ** ((midi - 69) / 12)
            trem = 1.0 + 0.12 * np.sin(2 * np.pi * (1 + ni % 3) * t / BED_SECONDS + ni)
            for h, a in ((1, 1.0), (2, 0.32), (3, 0.10)):
                for det in (-0.1, 0.1):
                    f = _q(f0 * h) + det * h
                    f = round(f * BED_SECONDS) / BED_SECONDS
                    c += a * trem * np.sin(2 * np.pi * f * t + ni * 1.3 + h)
        out += w * c
    out = _shape(out, lambda f: 1.0 / (1.0 + (f / 1800.0) ** 4), BED_SR)
    out -= out.mean()
    out *= BED_RMS / float(np.sqrt(np.mean(out ** 2)))
    return out


# ---------------------------------------------------------------- writing


def to_wav_bytes(x: np.ndarray, sr: int) -> bytes:
    pcm = np.clip(np.round(x * 32767.0), -32768, 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def build_all() -> Tuple[Dict[str, bytes], dict]:
    files: Dict[str, bytes] = {}
    meta: Dict[str, dict] = {}
    for name, fn in EFFECTS.items():
        x = fn()
        files[name + ".wav"] = to_wav_bytes(x, SR)
        meta[name + ".wav"] = {"kind": "effect", "sr": SR, "seconds": round(len(x) / SR, 4)}
    for mood in MOODS:
        x = bed(mood)
        files[f"bed_{mood}.wav"] = to_wav_bytes(x, BED_SR)
        meta[f"bed_{mood}.wav"] = {"kind": "bed", "sr": BED_SR, "seconds": BED_SECONDS, "loop": True, "mood": mood}
    for k, b in files.items():
        meta[k].update({"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)})
    man = {"asset_id": ASSET_ID, "numpy": np.__version__.split(".")[0], "total_bytes": sum(len(b) for b in files.values()), "files": meta,
           "note": "synthesised; peak -6 dBFS effects, -18 dBFS RMS beds; not listened to"}
    return files, man


def main(argv) -> int:
    files, man = build_all()
    mbytes = (json.dumps(man, indent=1, sort_keys=True) + "\n").encode()
    if "--check" in argv:
        bad = [k for k, b in files.items() if not (OUT / k).exists() or (OUT / k).read_bytes() != b]
        if not (OUT / "manifest.json").exists() or (OUT / "manifest.json").read_bytes() != mbytes:
            bad.append("manifest.json")
        print("sfx assets OK (%d files, %d bytes)" % (len(files), man["total_bytes"]) if not bad else "sfx assets DIFFER: " + ", ".join(bad))
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for k, b in files.items():
        (OUT / k).write_bytes(b)
    (OUT / "manifest.json").write_bytes(mbytes)
    print("wrote %d files, %d bytes to %s" % (len(files), man["total_bytes"], OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
