"""Toon Tales sound kit: every SFX name the plan may use, plus the folk/banjo music bed.

Made once and cached in toontales/build/sfx (no downloads, no per-video assets): cartoon effects are
synthesised with numpy (kids_audio.synth), a few reuse the bundled CC0 library (whoosh, pop, ding).

Library: sfx.path("bonk") -> wav path;  sfx.music_bed(seconds) -> wav path (seamless banjo loop, 48 kHz stereo)
"""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kids_audio import synth as Y  # noqa: E402

SR = Y.SR
OUT = ROOT / "toontales" / "build" / "sfx"
VERSION = "v1"


def _rng(seed):
    return np.random.default_rng(seed)


def _norm(x, peak=0.9):
    return x / (np.abs(x).max() + 1e-9) * peak


def _env(n, a, d):
    return Y._env(n, a, d)


def _sweep(f0, f1, dur, shape=0.15):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / shape)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _noise(n, lo, hi, seed):
    return _norm(Y._noise_band(n, lo, hi, seed), 1.0)


def _mix(total, parts):
    out = np.zeros(int(total * SR))
    for x, at, g in parts:
        i = int(at * SR)
        m = min(len(x), len(out) - i)
        if m > 0:
            out[i:i + m] += x[:m] * g
    return out


def bonk():
    x = _sweep(950, 420, 0.45, 0.06) * _env(int(0.45 * SR), 0.001, 0.12)
    x += Y._modal(620, 0.45, [(1, 0.6, 0.08), (2.4, 0.3, 0.04)])
    return _norm(x)


def pick():
    n = int(0.5 * SR)
    clink = Y._modal(1850, 0.5, [(1, 1.0, 0.18), (2.71, 0.6, 0.1), (5.15, 0.35, 0.05)], attack=0.0005)
    crumble = _noise(n, 200, 2500, 4) * _env(n, 0.004, 0.09) * 0.5
    return _norm(clink + crumble)


def coins():
    r = _rng(5)
    parts = [(Y._modal(r.uniform(2800, 5200), 0.4, [(1, 1, 0.09), (2.3, 0.4, 0.05)], attack=0.0003), r.uniform(0, 0.35),
              r.uniform(0.5, 1.0)) for _ in range(9)]
    return _norm(_mix(0.8, parts))


def cash():
    bell = Y._modal(2093, 1.2, [(1, 1, 0.5), (2.0, 0.5, 0.3), (3.01, 0.3, 0.15)], attack=0.0005)
    n = int(0.3 * SR)
    drawer = _noise(n, 400, 3000, 6) * _env(n, 0.03, 0.08) * 0.4
    return _norm(_mix(1.3, [(drawer, 0.0, 1.0), (bell, 0.08, 0.9), (coins(), 0.25, 0.5)]))


def glass():
    r = _rng(7)
    parts = [(Y._modal(r.uniform(3000, 8000), 0.3, [(1, 1, 0.05), (2.6, 0.5, 0.03)], attack=0.0002),
              r.uniform(0, 0.25), r.uniform(0.3, 1.0)) for _ in range(28)]
    n = int(0.25 * SR)
    burst = _noise(n, 2500, 12000, 8) * _env(n, 0.0005, 0.04)
    return _norm(_mix(0.7, parts + [(burst, 0, 0.8)]))


def thud():
    x = _sweep(95, 42, 0.5, 0.05) * _env(int(0.5 * SR), 0.002, 0.12)
    n = int(0.2 * SR)
    return _norm(_mix(0.5, [(x, 0, 1.0), (_noise(n, 60, 900, 9) * _env(n, 0.001, 0.04), 0, 0.5)]))


def boom():
    n = int(2.2 * SR)
    rumble = _noise(n, 20, 400, 10) * _env(n, 0.004, 0.55)
    low = _sweep(70, 30, 2.2, 0.3) * _env(n, 0.003, 0.6)
    crack = _noise(int(0.08 * SR), 500, 9000, 11) * _env(int(0.08 * SR), 0.0005, 0.02)
    return _norm(_mix(2.2, [(rumble, 0, 1.0), (low, 0, 0.9), (crack, 0, 0.6)]))


def gunshot():
    crack = _noise(int(0.05 * SR), 300, 14000, 12) * _env(int(0.05 * SR), 0.0002, 0.008)
    body = boom()[: int(0.9 * SR)] * np.linspace(1, 0, int(0.9 * SR))
    return _norm(Y.reverb_tail(np.stack([_mix(1.0, [(crack, 0, 1.0), (body, 0, 0.45)])] * 2), 0.3, 1.2)[0])


def splash():
    n = int(0.9 * SR)
    wash = _noise(n, 300, 7000, 13) * _env(n, 0.008, 0.18)
    r = _rng(14)
    bub = [(_sweep(r.uniform(500, 900), r.uniform(1200, 2200), 0.06, 0.02) * _env(int(0.06 * SR), 0.002, 0.02),
            r.uniform(0.1, 0.6), 0.25) for _ in range(10)]
    return _norm(_mix(0.9, [(wash, 0, 1.0)] + bub))


def fuse():
    n = int(1.4 * SR)
    hiss = _noise(n, 2500, 9000, 15) * 0.25
    r = _rng(16)
    clicks = np.zeros(n)
    for i in r.integers(0, n - 200, 140):
        clicks[i:i + 120] += r.uniform(-1, 1) * np.exp(-np.arange(120) / 25)
    return _norm((hiss + clicks) * np.minimum(1, np.arange(n) / (0.05 * SR)))


def footsteps():
    parts = []
    for k in range(4):
        n = int(0.16 * SR)
        step = _sweep(110, 60, 0.16, 0.03) * _env(n, 0.002, 0.04) + _noise(n, 800, 5000, 20 + k) * _env(n, 0.001, 0.025) * 0.5
        parts.append((step, k * 0.33, 1.0 if k % 2 == 0 else 0.8))
    return _norm(_mix(1.4, parts))


def horse():
    parts = []
    for k in range(8):
        f = 1150 if k % 2 == 0 else 820
        parts.append((Y._modal(f, 0.12, [(1, 1, 0.025), (2.3, 0.4, 0.015)], attack=0.0003), (k // 2) * 0.32 + (k % 2) * 0.09, 1.0))
    return _norm(_mix(1.4, parts))


def car():
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    pulses = np.sin(2 * np.pi * 34 * t) > 0.6
    x = pulses * _noise(n, 60, 1200, 17) + 0.4 * np.sin(2 * np.pi * 68 * t)
    return _norm(x * np.minimum(1, t / 0.1) * np.minimum(1, (1.6 - t) / 0.3))


def train():
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t)
    w = sum(np.sin(2 * np.pi * f * vib * t) for f in (523, 659, 784)) * _env(n, 0.05, 1.2)
    return _norm(w)


def door():
    n = int(1.0 * SR)
    t = np.arange(n) / SR
    f = 260 + 140 * np.sin(2 * np.pi * 0.7 * t) + 25 * _rng(18).standard_normal(n).cumsum() / np.sqrt(n)
    creak = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * (0.5 + 0.5 * np.sin(2 * np.pi * 23 * t))
    return _norm(creak * _env(n, 0.08, 0.6) * 0.6)


def paper():
    n = int(0.6 * SR)
    flutter = np.abs(_rng(19).standard_normal(n // 600 + 1)).repeat(600)[:n]
    return _norm(_noise(n, 1500, 8000, 19) * flutter * _env(n, 0.01, 0.2))


def crowd():
    n = int(2.0 * SR)
    t = np.arange(n) / SR
    x = sum(_noise(n, 250 + 90 * k, 900 + 120 * k, 30 + k) * (0.5 + 0.5 * np.sin(2 * np.pi * (2 + k * 0.7) * t + k))
            for k in range(6))
    return _norm(x * np.minimum(1, t / 0.3) * np.minimum(1, (2.0 - t) / 0.4))


def scratch():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 260 + 700 * np.abs(np.sin(np.pi * 1.5 * t / 0.45 * 0.9 + 0.3)) * np.exp(-t / 0.5)
    ph = 2 * np.pi * np.cumsum(f) / SR
    saw = 2 * ((ph / (2 * np.pi)) % 1) - 1
    nz = _noise(n, 800, 7000, 21)
    x = (0.6 * saw + 0.5 * nz) * (0.6 + 0.4 * np.sin(2 * np.pi * 9 * t)) * _env(n, 0.005, 0.2)
    return _norm(x * np.minimum(1, (0.45 - t) / 0.04))


def boing():
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    f = 330 * (1 + 0.45 * np.exp(-t / 0.25) * np.sin(2 * np.pi * 14 * t)) + 60 * np.exp(-t / 0.1)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    return _norm(x * np.exp(-t / 0.2) * np.minimum(1, t / 0.004))


SYNTH = {"bonk": bonk, "pick": pick, "coins": coins, "cash": cash, "glass": glass, "thud": thud, "boom": boom,
         "gunshot": gunshot, "splash": splash, "fuse": fuse, "footsteps": footsteps, "horse": horse, "car": car,
         "train": train, "door": door, "paper": paper, "crowd": crowd, "scratch": scratch, "boing": boing}
BUNDLED = {"whoosh": ROOT / "assets" / "bundled-sfx" / "whoosh" / "whoosh_04.opus",
           "pop": ROOT / "kids_audio" / "library" / "sfx_pop.wav",
           "ding": ROOT / "kids_audio" / "library" / "sfx_ding_3.wav"}
SPOKEN = {"laugh": ("Ha ha ha ha!", "en-US-GuyNeural", "+10%", "-4Hz"),
          "gasp": ("Huh!", "en-US-ChristopherNeural", "+0%", "+10Hz")}


def _write(path, x, stereo=True):
    x = np.clip(x, -1, 1)
    data = np.stack([x, x], 1) if stereo and x.ndim == 1 else x
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2 if data.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((data * 32767).astype("<i2").tobytes())


def path(name):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}_{VERSION}.wav"
    if p.exists():
        return p
    if name in SYNTH:
        _write(p, SYNTH[name]())
    elif name in BUNDLED:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(BUNDLED[name]), "-ar", str(SR), "-ac", "2", str(p)],
                       check=True)
    elif name in SPOKEN:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import voice
        text, v, rate, pitch = SPOKEN[name]
        r = voice.line(text, v, rate, OUT, pitch)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", r["wav"], "-ar", str(SR), "-ac", "2", str(p)], check=True)
    else:
        raise KeyError(f"no sound for '{name}'")
    return p


# ---------------------------------------------------------------- music bed

PROG = [("G", ["G3", "B3", "D4", "G4"]), ("C", ["C4", "E4", "G4", "C5"]), ("G", ["G3", "B3", "D4", "G4"]),
        ("D", ["D4", "F#4", "A4", "D5"]), ("G", ["G3", "B3", "D4", "G4"]), ("C", ["C4", "E4", "G4", "C5"]),
        ("D", ["D4", "F#4", "A4", "D5"]), ("G", ["G3", "B3", "D4", "G4"])]
BASS = {"G": ("G2", "D2"), "C": ("C3", "G2"), "D": ("D2", "A2")}
ROLL = [0, 2, 3, 1, 3, 2, 0, 3]  # forward-ish roll over chord tones, 8 eighth notes per bar


def banjo(f, vel, seed):
    """Bright, short pluck with a twangy upper partial (banjo-like)."""
    x = Y.pluck(f, vel, dur=0.7, bright=1.0, seed=seed)
    n = len(x)
    twang = Y._modal(f * 2, 0.7, [(1, 0.25, 0.08), (1.5, 0.12, 0.05)], attack=0.0005, vel=vel)[:n]
    return (x + twang) * np.exp(-np.arange(n) / (0.32 * SR))


def _finish(loop, p, wet, secs):
    loop.reverb(wet, secs)
    buf = loop.buf / (np.abs(loop.buf).max() + 1e-9) * 0.8
    _write(p, buf.T, stereo=False)


def _build_upbeat(p, bpm):
    beat = 60 / bpm
    loop = Y.Loop(len(PROG) * 4 * beat)
    for b, (ch, tones) in enumerate(PROG):
        t0 = b * 4 * beat
        for i, k in enumerate(ROLL):
            v = 0.55 if i % 2 == 0 else 0.4
            loop.add(banjo(Y.hz(tones[k]), v, seed=b * 8 + i), t0 + i * beat / 2, gain=0.5, pan=0.25)
        lo, fifth = BASS[ch]
        loop.add(Y.bass(Y.hz(lo), 0.9, dur=beat * 0.9), t0, gain=0.55)
        loop.add(Y.bass(Y.hz(fifth), 0.8, dur=beat * 0.9), t0 + 2 * beat, gain=0.5)
        for q in (1, 3):  # chick: muted strum on the off beats
            for j, tone in enumerate(tones[:3]):
                loop.add(Y.pluck(Y.hz(tone), 0.25, dur=0.12, bright=0.3, seed=j), t0 + q * beat + j * 0.008, gain=0.35,
                         pan=-0.2)
            loop.add(Y.shaker(0.35, seed=b + q), t0 + q * beat, gain=0.25, pan=0.4)
    _finish(loop, p, 0.12, 0.7)


# sneaky: E minor, 8 bars. (chord tones, 4 quarter-note bass notes; last bar walks up chromatically)
SNEAKY = [(["E3", "G3", "B3"], ["E2", "G2", "A2", "B2"]), (["E3", "G3", "B3"], ["E2", "B2", "G2", "B2"]),
          (["A3", "C4", "E4"], ["A2", "C3", "E3", "C3"]), (["E3", "G3", "B3"], ["E2", "G2", "B2", "G2"]),
          (["B3", "D4", "F#4"], ["B2", "D3", "F#3", "D3"]), (["A3", "C4", "E4"], ["A2", "C3", "E3", "C3"]),
          (["E3", "G3", "B3"], ["E2", "G2", "B2", "G2"]), (["B3", "D4", "F#4"], ["B2", "C3", "C#3", "D3"])]
SNEAKY_MEL = {0: ["B4", "G4"], 2: ["C5", "E5"], 4: ["F#4", "D4"], 6: ["G4", "B4"]}


def _build_sneaky(p, bpm):
    beat = 60 / bpm
    loop = Y.Loop(len(SNEAKY) * 4 * beat)
    for b, (chord, walk) in enumerate(SNEAKY):
        t0 = b * 4 * beat
        for q, note in enumerate(walk):  # staccato walking bass on quarters
            loop.add(Y.pluck(Y.hz(note), 0.8, dur=0.22, bright=0.45, seed=b * 4 + q), t0 + q * beat, gain=0.7)
        for q in (0.5, 1.5, 2.5, 3.5):  # short muted off-beat chords
            for j, tone in enumerate(chord):
                loop.add(Y.pluck(Y.hz(tone), 0.3, dur=0.1, bright=0.35, seed=j + int(q * 2)),
                         t0 + q * beat + j * 0.006, gain=0.3, pan=-0.2)
        for e in range(8):
            loop.add(Y.shaker(0.25 if e % 2 == 0 else 0.4, seed=b * 8 + e), t0 + e * beat / 2, gain=0.18, pan=0.4)
        for k, note in enumerate(SNEAKY_MEL.get(b, [])):
            loop.add(Y.pluck(Y.hz(note), 0.5, dur=0.25, bright=0.6, seed=b + k), t0 + (2.5 + k * 0.5) * beat, gain=0.35,
                     pan=0.25)
    _finish(loop, p, 0.1, 0.6)


# sad: A minor -> F -> C -> E, two bars each, 8 bars
SAD = [(["A2", "E3", "A3", "C4"], "A2"), (["F2", "C3", "F3", "A3"], "F2"), (["C3", "G3", "C4", "E4"], "C3"),
       (["E2", "B2", "E3", "G#3"], "E2")]
SAD_MEL = {1: ("E4", 2.0), 3: ("C4", 1.0), 4: ("G4", 2.0), 6: ("B3", 1.0), 7: ("G#4", 3.0)}


def _build_sad(p, bpm):
    beat = 60 / bpm
    loop = Y.Loop(8 * 4 * beat)
    for b in range(8):
        tones, root = SAD[b // 2]
        t0 = b * 4 * beat
        for j, tone in enumerate(tones):  # soft sustained low plucks, slow arpeggio
            loop.add(Y.pluck(Y.hz(tone), 0.45, dur=3.0, bright=0.3, seed=j + b), t0 + j * beat, gain=0.4,
                     pan=-0.2 + 0.15 * j)
        if b % 2 == 0:
            loop.add(Y.pluck(Y.hz(root), 0.6, dur=4.0, bright=0.25, seed=b), t0, gain=0.5)
        if b in SAD_MEL:
            note, at = SAD_MEL[b]
            loop.add(Y.pluck(Y.hz(note), 0.35, dur=2.5, bright=0.3, seed=b), t0 + at * beat, gain=0.3, pan=0.3)
    _finish(loop, p, 0.4, 1.8)


BEDS = {"upbeat": (_build_upbeat, "bed_banjo", None), "sneaky": (_build_sneaky, "bed_sneaky", 110),
        "sad": (_build_sad, "bed_sad", 70)}


def music_bed(seconds, bpm=124, mood="upbeat"):
    """Loop tiled to `seconds`. mood: upbeat (banjo roll, default), sneaky (E-minor heist walk), sad (slow A-minor pads)."""
    OUT.mkdir(parents=True, exist_ok=True)
    build, stem, fixed = BEDS[mood]
    if fixed:
        bpm = fixed
    p = OUT / f"{stem}_{bpm}_{VERSION}.wav"
    if not p.exists():
        build(p, bpm)
    out = OUT / f"{stem}_{bpm}_{VERSION}_{int(seconds * 10)}.wav"
    if not out.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(p), "-t", f"{seconds:.2f}",
                        "-af", f"afade=t=in:d=0.4,afade=t=out:st={max(0, seconds - 1.5):.2f}:d=1.5", str(out)], check=True)
    return out
