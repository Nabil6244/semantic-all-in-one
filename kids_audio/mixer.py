"""Voice-first bus mixer: the voice bus is passed through untouched; the music bed loops under it and ducks while
she speaks; sound effects land on lesson events. A final peak guard keeps the sum under -1 dBFS.

python3 -m kids_audio.mixer job.json
job = {"voice": "voice_processed.wav", "out": "mix.wav", "duration": 54.0,
       "music": {"bed": "playroom", "gap_db": -12, "duck_db": -10, "fade_in": 1.5, "fade_out": 2.5} | null,
       "sfx": [{"t": 5.0, "name": "pop", "gain_db": 0}, ...] | [],
       "voice_lufs": -14, "target_lufs": -14, "duck_regions": [{"t0", "t1", "duck_db"}] (optional)}
Prints a JSON report (levels, ducking, the quietest voice-over-music margin during speech).
"""
import json
import os
import sys

import numpy as np

from . import library as L
from .synth import SR

SFX_PEAK = -13.0              # effect peaks in dBFS when the voice is at -14 LUFS (voice peaks sit near -4 dBFS)


def _smooth_gain(target, attack, release, lookahead):
    """One-pole follower per sample (attack when the gain falls, release when it rises), shifted earlier by `lookahead` s."""
    k = int(lookahead * SR); tg = np.concatenate([target[k:], np.full(k, target[-1])]) if k else target
    a, r = 1 - np.exp(-1 / (attack * SR)), 1 - np.exp(-1 / (release * SR))
    out = np.empty_like(tg); g = tg[0]
    # coarse 1 ms steps keep this fast; gains change slowly anyway
    step = SR // 1000
    for i in range(0, len(tg), step):
        x = tg[i:i + step].min(); c = a if x < g else r; g += (x - g) * (1 - (1 - c) ** step); out[i:i + step] = g
    return out


def voice_activity(voice, floor_db=-42.0):
    """0..1 per sample: how much she is speaking (10 ms RMS, gated at floor_db)."""
    m = voice.mean(0); w = SR // 100; n = len(m) // w * w
    rms = np.sqrt((m[:n].reshape(-1, w) ** 2).mean(1) + 1e-12); db = 20 * np.log10(rms)
    act = np.clip((db - floor_db) / 12, 0, 1)
    return np.repeat(act, w)[: len(m)] if n else np.zeros(len(m)), np.repeat(db, w)


def mix(job):
    man = L.build(); dur = float(job["duration"]); N = int(round(dur * SR))
    voice = L.read_audio(job["voice"]) if job.get("voice") else np.zeros((2, N))
    voice = np.pad(voice, ((0, 0), (0, max(0, N - voice.shape[1]))))[:, :N]
    out = voice.copy(); rep = {"duration": dur, "music": None, "sfx": 0}
    vlufs = float(job.get("voice_lufs", -14.0))
    act, vdb = voice_activity(voice); act = np.pad(act, (0, N - len(act)), constant_values=0)[:N]
    mus = np.zeros_like(out)
    m = job.get("music")
    if m:
        bed = man["beds"][m.get("bed", "playroom")]; x = L.read_audio(os.path.join(L.LIB, bed["file"]))
        reps = int(np.ceil(N / x.shape[1])); x = np.tile(x, (1, reps))[:, :N]
        gap = vlufs + float(m.get("gap_db", -12)) - bed["lufs"]                    # level in the gaps, relative to the voice
        duck = float(m.get("duck_db", -10))
        dk = np.full(N, duck)                                                    # regions (chants) can duck less: the music carries the beat
        for r in job.get("duck_regions") or []:
            dk[max(0, int(r["t0"] * SR)):max(0, int(r["t1"] * SR))] = float(r["duck_db"])
        target = 10 ** ((gap + dk * act) / 20)
        g = _smooth_gain(target, attack=0.06, release=0.45, lookahead=0.05)
        fi, fo = float(m.get("fade_in", 1.5)), float(m.get("fade_out", 2.5)); t = np.arange(N) / SR
        g *= np.clip(t / max(fi, 1e-3), 0, 1) * np.clip((dur - t) / max(fo, 1e-3), 0, 1)
        mus = x * g; out += mus
        rep["music"] = {"bed": m.get("bed", "playroom"), "gap_db": m.get("gap_db", -12), "duck_db": duck}
    fx = np.zeros_like(out)
    for e in job.get("sfx") or []:
        s = man["sfx"].get(e["name"])
        if not s:
            continue
        y = L.read_audio(os.path.join(L.LIB, s["file"]))         # short sounds: level by peak (loudness meters gate them out)
        gdb = (vlufs + 14.0) + SFX_PEAK + float(e.get("gain_db", 0)) - s["peak_db"]
        i0 = int(round(float(e["t"]) * SR)); n = max(0, min(y.shape[1], N - i0))
        if n > 0 and i0 >= 0:
            fx[:, i0:i0 + n] += y[:, :n] * 10 ** (gdb / 20); rep["sfx"] += 1
    out += fx
    # master to the target loudness with one overall gain (the music gaps lower the gated average a little)
    tgt = job.get("target_lufs", -14.0)
    if tgt is not None and (m or rep["sfx"]):
        g = 10 ** (float(np.clip(float(tgt) - L.lufs(out), -3, 3)) / 20); voice, mus, fx = voice * g, mus * g, fx * g; out = voice + mus + fx
    # peak guard on the music + effects only, so the voice is never squashed
    limit = 10 ** (-1.0 / 20); peak = np.abs(out).max(0)
    over = peak > limit
    if over.any():
        bg = mus + fx; need = np.ones(N)
        bgp = np.abs(bg).max(0) + 1e-12; room = np.clip((limit - np.abs(voice).max(0)) / bgp, 0, 1)
        need[over] = room[over]
        k = int(0.005 * SR)                                                   # hold the reduction 5 ms either side: no clicks
        need = np.lib.stride_tricks.sliding_window_view(np.pad(need, (k, k), constant_values=1), 2 * k + 1).min(1)
        out = voice + bg * need
    # report: how far the voice stays above the music while she speaks (100 ms windows)
    w = SR // 10; n = N // w * w
    if m and n:
        e = lambda a: 10 * np.log10((a.mean(0)[:n].reshape(-1, w) ** 2).mean(1) + 1e-12)
        ve, me, sp = e(voice), e(mus), act[:n].reshape(-1, w).mean(1) > 0.8
        if sp.any():
            margin = (ve - me)[sp]; rep["voice_over_music_db"] = {"median": round(float(np.median(margin)), 1), "worst_5pct": round(float(np.percentile(margin, 5)), 1)}
    rep["peak_dbfs"] = round(20 * np.log10(np.abs(out).max() + 1e-12), 2)
    L.write_wav(job["out"], out)
    rep["lufs"] = round(L.lufs(out), 1)
    return rep


if __name__ == "__main__":
    print(json.dumps(mix(json.load(open(sys.argv[1])))))
