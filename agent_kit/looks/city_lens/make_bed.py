"""Make city_lens's music bed once: a calm, modern documentary underscore (warm pads, soft piano, a gentle pulse, light
shaker), built from plain synthesis so it needs no download and no licence. It changes every 8 bars so it never feels like
a short loop, sits under a voice at about -20 dB, and loops cleanly (join loops it for long videos).

    python3 agent_kit/looks/city_lens/make_bed.py            -> agent_kit/looks/city_lens/sound/bed.opus
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 90
BEAT = 60 / BPM
BAR = 4 * BEAT
# A minor, thoughtful: Am9 - Fmaj7 - Cmaj7 - G6sus, two bars each
CHORDS = [[57, 60, 64, 67, 71], [53, 57, 60, 64, 67], [48, 55, 59, 64, 67], [55, 59, 62, 64, 69]]
ROOTS = [45, 41, 48, 43]
SECTIONS = ["pad", "pad+keys", "pad+keys+pulse", "full", "pad+keys+pulse", "full", "pad+keys", "pad"]   # 8 bars each

hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)   # noqa: E731


def lp(x, cut, passes=2):
    from scipy.signal import lfilter
    a = np.exp(-2 * np.pi * cut / SR)
    for _ in range(passes):
        x = lfilter([1 - a], [1, -a], x)
    return x


def pad_note(f, dur, rng):
    t = np.arange(int(dur * SR)) / SR
    v = sum(np.sign(np.sin(2 * np.pi * f * (1 + d) * t + rng.uniform(0, 6))) * 0.5 + np.sin(2 * np.pi * f * (1 + d) * t) * 0.5
            for d in (-0.004, 0.0, 0.0045))
    env = np.minimum(1, t / 1.6) * np.minimum(1, (dur - t) / 1.4).clip(0)
    return v * env / 3


def keys_note(f, dur):
    t = np.arange(int(dur * SR)) / SR
    v = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) * np.exp(-t * 3) + 0.12 * np.sin(6 * np.pi * f * t) * np.exp(-t * 5)
    return v * np.exp(-t * 1.1) * np.minimum(1, t / 0.006)


def pluck(f, dur):
    t = np.arange(int(dur * SR)) / SR
    return (np.sin(2 * np.pi * f * t) + 0.2 * np.sin(2 * np.pi * 2 * f * t)) * np.exp(-t * 7) * np.minimum(1, t / 0.004)


def main(out: Path) -> Path:
    rng = np.random.default_rng(7)
    bars = 8 * len(SECTIONS)
    n = int(bars * BAR * SR) + SR * 4
    pad, keys, arp, bass, perc = (np.zeros(n) for _ in range(5))
    for b in range(bars):
        sec = SECTIONS[b // 8]
        ci = (b // 2) % 4
        t0 = int(b * BAR * SR)
        if b % 2 == 0:                                            # pad + bass hold for two bars
            for m in CHORDS[ci][:4]:
                x = pad_note(hz(m), 2 * BAR + 1.2, rng)
                pad[t0:t0 + len(x)] += x
            tb = np.arange(int(2 * BAR * SR)) / SR
            bx = np.sin(2 * np.pi * hz(ROOTS[ci] - 12) * tb) * np.minimum(1, tb / 0.3) * np.minimum(1, (2 * BAR - tb) / 0.4)
            bass[t0:t0 + len(bx)] += bx
        if "keys" in sec or sec == "full":                        # soft piano: a broken chord, varied per bar
            pat = [(0, 4), (1.5, 2), (2.5, 3), (3, 1)] if b % 2 == 0 else [(0, 3), (1, 4), (2.5, 2)]
            for beat, ni in pat:
                x = keys_note(hz(CHORDS[ci][ni] + 12), 3.0) * (0.9 if beat == 0 else 0.6)
                s = t0 + int(beat * BEAT * SR)
                keys[s:s + len(x)] += x[: max(0, n - s)]
        if "pulse" in sec or sec == "full":                       # gentle 8th-note pulse on chord tones
            for e in range(8):
                f = hz(CHORDS[ci][[0, 2, 3, 2, 1, 2, 3, 4][e]] + 12)
                x = pluck(f, BEAT) * (0.8 if e % 2 == 0 else 0.55)
                s = t0 + int(e * BEAT / 2 * SR)
                arp[s:s + len(x)] += x
        if sec == "full":                                         # light shaker on the off-beats, a soft low thump on 1
            for e in range(8):
                s = t0 + int(e * BEAT / 2 * SR)
                ln = int(0.09 * SR)
                nz = rng.standard_normal(ln) * np.exp(-np.arange(ln) / SR * 45) * (1.0 if e % 2 else 0.45)
                perc[s:s + ln] += nz
            tk = np.arange(int(0.35 * SR)) / SR
            kick = np.sin(2 * np.pi * (48 + 60 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 9)
            perc[t0:t0 + len(kick)] += kick * 6
    pad = lp(pad, 1400)
    keys = lp(keys, 3200, 1)
    arp = lp(arp, 2400, 1)
    shaker = lp(perc - lp(perc, 5000, 1), 9000, 1)   # keep the kick low and the shaker soft and airy
    mix = 0.22 * pad + 0.18 * keys + 0.10 * arp + 0.20 * bass + 0.012 * shaker + 0.012 * lp(perc, 200, 1)
    # stereo width: delay the pluck and keys a little on the right
    d = int(0.011 * SR)
    left = mix
    right = 0.22 * pad + 0.18 * np.roll(keys, d) + 0.10 * np.roll(arp, int(BEAT * 0.75 * SR)) * 0.8 + 0.20 * bass + 0.012 * shaker + 0.012 * lp(perc, 200, 1)
    st = np.stack([left, right], 1)
    st /= np.abs(st).max() * 1.12
    with tempfile.TemporaryDirectory() as td:
        w = Path(td) / "bed.wav"
        with wave.open(str(w), "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(SR)
            f.writeframes((st * 32767).astype(np.int16).tobytes())
        out.parent.mkdir(parents=True, exist_ok=True)
        # a room around it (two soft echoes), then a loudness close to other beds so music_db means the same
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w), "-af",
                        "aecho=0.8:0.55:90|210:0.25|0.15,highpass=f=40,loudnorm=I=-20:TP=-2:LRA=8,"
                        f"atrim=0:{bars * BAR:.2f}",          # no fades: join fades the ends and loops it
                        "-c:a", "libopus", "-b:a", "160k", str(out)], check=True)
    return out


if __name__ == "__main__":
    print(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "sound" / "bed.opus"))
