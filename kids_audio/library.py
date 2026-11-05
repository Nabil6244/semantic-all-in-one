"""The preschool audio library: one musical identity, a few seamless beds and reusable sound effects.

Everything is synthesised deterministically from this file, written once to kids_audio/library/ (git-ignored) and
rebuilt only when this file or synth.py changes. Lessons pick beds and effects by name; nothing is random per lesson.
"""
import hashlib
import json
import os
import subprocess

import numpy as np

from . import synth as S
from .synth import SR, hz

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "library")
BED_LUFS = -20.0          # beds are stored at this loudness; the mixer sets the final level
SFX_PEAK_DB = -3.0

# ---- musical identity: C major, a bright I-V-vi-IV world, one signature motif every bed quotes
CHORDS = {"C": ["C4", "E4", "G4", "C5"], "G": ["B3", "D4", "G4", "B4"], "Am": ["C4", "E4", "A4", "C5"], "F": ["C4", "F4", "A4", "C5"],
          "Dm": ["D4", "F4", "A4", "D5"], "Em": ["B3", "E4", "G4", "B4"]}
ROOT = {"C": "C3", "G": "G2", "Am": "A2", "F": "F2", "Dm": "D3", "Em": "E3"}
MOTIF = [("E5", 0, 0.5), ("G5", 0.5, 0.5), ("A5", 1, 0.5), ("G5", 1.5, 1.5)]            # (note, beat, length): the "hello" motif
ANSWER = [("E5", 0, 0.5), ("D5", 0.5, 0.5), ("C5", 1, 0.5), ("D5", 1.5, 1.5)]


def _bed(name, bpm, prog, *, uke=True, drums=True, glock_arp=False, melody=True, bars=8):
    beat = 60 / bpm; L = S.Loop(bars * 4 * beat)
    for bar in range(bars):
        ch = prog[bar % len(prog)]; t0 = bar * 4 * beat
        L.add(S.bass(hz(ROOT[ch]), 0.55, dur=beat * 1.8), t0, pan=0)
        L.add(S.bass(hz(ROOT[ch]), 0.4, dur=beat * 1.6), t0 + 2 * beat, pan=0)
        if uke:                                                                  # down on 1, 2&, 3, 4: a happy strum
            for k, b in enumerate((0, 1.5, 2, 3)):
                for s, nt in enumerate(CHORDS[ch]):
                    L.add(S.pluck(hz(nt), 0.22 if k else 0.3, dur=beat * 1.5, bright=0.55, seed=bar * 17 + k), t0 + b * beat + s * 0.012, pan=-0.35)
        if glock_arp:
            for k in range(8):
                nt = CHORDS[ch][k % 4]; L.add(S.glock(hz(nt[:-1] + str(int(nt[-1]) + 1)), 0.12), t0 + k * beat / 2, pan=0.4)
        if drums:
            for b in (0, 2):
                L.add(S.kick(0.5), t0 + b * beat)
            for b in (1, 3):
                L.add(S.snap(0.25, seed=bar), t0 + b * beat, pan=0.1)
            for k in range(8):
                L.add(S.shaker(0.12 if k % 2 else 0.07, seed=bar * 8 + k), t0 + k * beat / 2, pan=0.45)
        if melody and bar % 2 == 0:                                              # the motif on odd phrases, its answer on even ones
            for nt, b, ln in (MOTIF if bar % 4 == 0 else ANSWER):
                L.add(S.marimba(hz(nt), 0.42, dur=max(0.6, ln * beat * 1.4)), t0 + b * beat, pan=0.25)
    L.reverb(0.16)
    return L.buf


BPM = {"playroom": 104, "calm": 84, "sunny": 112}
BEDS = {
    "playroom": lambda: _bed("playroom", 104, ["C", "G", "Am", "F"]),
    "calm": lambda: _bed("calm", 84, ["C", "Am", "F", "G"], uke=False, drums=False, glock_arp=True),
    "sunny": lambda: _bed("sunny", 112, ["C", "F", "G", "C", "Am", "F", "G", "C"]),
}


def _sfx():
    out = {}
    b = S.one_shot(0.25); n = int(0.09 * SR); t = np.arange(n) / SR                   # pop: a quick bubble
    f = 300 + 700 * np.exp(-t / 0.02); S.place(b, np.sin(2 * np.pi * np.cumsum(f) / SR) * S._env(n, 0.001, 0.03), 0)
    out["pop"] = b
    b = S.one_shot(1.4)                                                                # sparkle: tiny glockenspiel run upward
    for k, nt in enumerate(["C6", "E6", "G6", "C7", "E7"]):
        S.place(b, S.glock(hz(nt), 0.35, dur=1.0), k * 0.035, pan=-0.3 + k * 0.15)
    out["sparkle"] = S.reverb_tail(b, 0.3)
    b = S.one_shot(1.8)                                                                # chime: "your turn"
    S.place(b, S.glock(hz("E6"), 0.6), 0); S.place(b, S.glock(hz("G6"), 0.6), 0.16)
    out["chime"] = S.reverb_tail(b, 0.25)
    scale = ["C6", "D6", "E6", "G6", "A6", "C7", "D7", "E7", "G7", "A7"]            # ding_1..ding_10 climb the pentatonic scale
    for i, nt in enumerate(scale, 1):
        b = S.one_shot(1.3); S.place(b, S.glock(hz(nt), 0.7, dur=1.2), 0); S.place(b, S.marimba(hz(nt[:-1] + "5"), 0.3), 0)
        out[f"ding_{i}"] = S.reverb_tail(b, 0.2)
    b = S.one_shot(2.2)                                                                # success: arpeggio + strum
    for k, nt in enumerate(["C5", "E5", "G5", "C6"]):
        S.place(b, S.marimba(hz(nt), 0.6), k * 0.09); S.place(b, S.glock(hz(nt[:-1] + str(int(nt[-1]) + 1)), 0.3), k * 0.09 + 0.01, pan=0.3)
    for s, nt in enumerate(CHORDS["C"]):
        S.place(b, S.pluck(hz(nt), 0.35, dur=1.6, seed=s), 0.36 + s * 0.015, pan=-0.3)
    out["success"] = S.reverb_tail(b, 0.25)
    b = S.one_shot(1.9); hits = np.cumsum(np.linspace(0.07, 0.03, 30))                 # drumroll: speeding soft snare + a cymbal tap
    for k, at in enumerate(hits[hits < 1.25]):
        S.place(b, S.snap(0.15 + 0.4 * at, seed=k), at)
    S.place(b, S.shaker(0.9, seed=99) * 1.0, 1.3); S.place(b, S.kick(0.6), 1.3)
    out["drumroll"] = S.reverb_tail(b, 0.2)
    return out


# ---- files, loudness and the cache
def _src_hash():
    h = hashlib.sha1()
    for f in ("synth.py", "library.py"):
        h.update(open(os.path.join(HERE, f), "rb").read())
    return h.hexdigest()[:12]


def write_wav(path, x):
    x = np.ascontiguousarray(np.asarray(x, np.float32).T)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_f32le", path], input=x.tobytes(), check=True, timeout=600)


def read_audio(path, channels=2):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", str(channels), "-ar", str(SR), "-"], capture_output=True, check=True, timeout=600).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, channels).T.astype(np.float64)


def lufs(x):
    """Integrated loudness (EBU R128) of a stereo array, via ffmpeg."""
    x = np.ascontiguousarray(np.asarray(x, np.float32).T)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-af", "ebur128", "-f", "null", "-"], input=x.tobytes(), capture_output=True, timeout=600)
    import re
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr.decode())
    return float(m[-1]) if m else -70.0


def build(force=False):
    """Make sure the library exists and is current. Returns the manifest."""
    man_path = os.path.join(LIB, "manifest.json"); h = _src_hash()
    if not force and os.path.exists(man_path):
        man = json.load(open(man_path))
        if man.get("hash") == h and all(os.path.exists(os.path.join(LIB, e["file"])) for e in list(man["beds"].values()) + list(man["sfx"].values())):
            return man
    os.makedirs(LIB, exist_ok=True); man = {"hash": h, "sr": SR, "bed_lufs": BED_LUFS, "beds": {}, "sfx": {}}
    for name, make in BEDS.items():
        x = make(); g = 10 ** ((BED_LUFS - lufs(np.concatenate([x, x], 1))) / 20); x = x * g
        f = f"bed_{name}.wav"; write_wav(os.path.join(LIB, f), x); man["beds"][name] = {"file": f, "seconds": round(x.shape[1] / SR, 4), "lufs": BED_LUFS, "bpm": BPM[name]}
    for name, x in _sfx().items():
        x = x * (10 ** (SFX_PEAK_DB / 20) / (np.abs(x).max() + 1e-9))
        f = f"sfx_{name}.wav"; write_wav(os.path.join(LIB, f), x); man["sfx"][name] = {"file": f, "seconds": round(x.shape[1] / SR, 4), "peak_db": SFX_PEAK_DB}
    json.dump(man, open(man_path, "w"), indent=1)
    return man
