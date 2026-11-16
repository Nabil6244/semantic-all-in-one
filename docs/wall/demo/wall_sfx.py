"""DEMO ONLY: synthesise every sound cue the wall items asked for (no sample files). Usage: wall_sfx.py <work_dir> <dur>"""
import json, sys, wave
import numpy as np

WD, DUR, SR = sys.argv[1], float(sys.argv[2]), 48000
rng = np.random.default_rng(3)
n = lambda s: int(s * SR)


def band(x, lo, hi):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def env(m, att, dec):
    t = np.arange(m) / SR
    return np.minimum(1, t / max(att, 1e-4)) * np.exp(-np.maximum(0, t - att) / dec)


def norm(x, p):
    return x / (np.abs(x).max() + 1e-9) * p


def whoosh():
    m = n(0.6); t = np.linspace(0, 1, m); x = band(rng.standard_normal(m), 300, 4000)
    return norm(x * np.sin(np.pi * t) ** 3, 0.35)


def drop():          # a print landing on the board: soft paper slap + low thump
    m = n(0.35); slap = band(rng.standard_normal(m), 900, 6000) * env(m, 0.001, 0.025)
    t = np.arange(m) / SR; th = np.sin(2 * np.pi * 110 * t) * env(m, 0.002, 0.07)
    return norm(slap * 0.7 + th, 0.4)


def pop():
    m = n(0.12); t = np.arange(m) / SR
    return norm(np.sin(2 * np.pi * np.cumsum(500 + 900 * np.exp(-t * 40)) / SR) * env(m, 0.002, 0.03), 0.25)


def slide():         # string pulled taut
    m = n(0.7); t = np.linspace(0, 1, m); x = band(rng.standard_normal(m), 1500, 7000)
    return norm(x * np.sin(np.pi * t) ** 2, 0.16)


def marker():
    m = n(0.4); t = np.arange(m) / SR; f = 1800 + 500 * np.sin(2 * np.pi * 8 * t)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25 + band(rng.standard_normal(m), 3000, 8000) * 0.75
    return norm(x * np.sin(np.pi * t / 0.4), 0.18)


def pencil():
    m = n(0.7); x = band(rng.standard_normal(m), 2500, 9000)
    mod = (np.sin(2 * np.pi * 11 * np.arange(m) / SR) > 0).astype(float) * 0.7 + 0.3
    return norm(x * mod * np.sin(np.pi * np.arange(m) / m), 0.12)


def tick(p=0.3):
    m = n(0.04); return norm(band(rng.standard_normal(m), 2500, 9000) * env(m, 0.0005, 0.005), p)


def ticks(d):
    out = np.zeros(n(d) + n(0.05))
    for u in np.linspace(0, 1, max(4, int(d * 14))):
        at = n(d * (1 - (1 - u) ** 1.7)); tk = tick(0.22); out[at:at + len(tk)] += tk
    return out


def typing(d=1.2):
    out = np.zeros(n(d) + n(0.05))
    for at in np.linspace(0, d, 14):
        tk = tick(0.28); i = n(at); out[i:i + len(tk)] += tk
    return out


def impact():
    m = n(0.6); t = np.arange(m) / SR
    body = np.sin(2 * np.pi * np.cumsum(80 * np.exp(-t * 6) + 42) / SR) * env(m, 0.002, 0.16)
    return norm(body + 0.4 * band(rng.standard_normal(m), 600, 4000) * env(m, 0.001, 0.025), 0.45)


def stamp():
    m = n(0.45); t = np.arange(m) / SR
    body = np.sin(2 * np.pi * 70 * t) * env(m, 0.001, 0.09)
    clack = band(rng.standard_normal(m), 400, 3500) * env(m, 0.0005, 0.02)
    return norm(body + clack, 0.55)


def boom():
    m = n(2.2); t = np.arange(m) / SR
    sub = np.sin(2 * np.pi * np.cumsum(55 * np.exp(-t * 1.2) + 30) / SR) * env(m, 0.005, 0.7)
    air = band(rng.standard_normal(m), 60, 600) * env(m, 0.01, 0.5)
    return norm(sub + 0.5 * air, 0.6)


SOUND = dict(whoosh=whoosh, drop=drop, pop=pop, slide=slide, marker=marker, pencil=pencil, impact=impact, stamp=stamp,
             boom=boom, type=typing)
mix = np.zeros(n(DUR) + n(3))
# quiet room tone so silence never sounds dead
rt = band(np.cumsum(rng.standard_normal(len(mix))) * 0.01, 40, 300); mix += norm(rt, 0.025)
last = {}
for t, name in json.loads(open(f"{WD}/sfx_events.json").read()):
    if t < 0 or t > DUR:
        continue
    if name.startswith("ticks:"):
        sig = ticks(float(name[6:]))
    else:
        if t - last.get(name, -9) < 0.25:
            continue
        last[name] = t
        sig = SOUND[name]()
    i = n(t); mix[i:i + len(sig)] += sig
mix = np.tanh(mix * 1.1) * 0.85
with wave.open(f"{WD}/sfx.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(mix[:n(DUR)], -1, 1) * 32767).astype(np.int16).tobytes())
print("ok")
