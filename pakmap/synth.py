"""Deterministic, original sound generators for pakMap sound effects the library has no recording of (Phase 8).

Nothing here is sampled or copied: each sound is built from sine/noise/envelope maths with a fixed seed, so the same
call always returns the same samples. They are simple approximations of the named sound, labelled "synthesized" in the
sound plan so the author knows what they are hearing. Output: float32 stereo (n, 2) at SR, peak below 1.
"""

from __future__ import annotations

from typing import Callable, Dict

import numpy as np

SR = 48000


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """FFT band-pass (lo=0 -> low-pass, hi>=SR/2 -> high-pass) with soft edges."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    gain = np.ones_like(f)
    if lo > 0:
        gain *= 1 / (1 + (lo / np.maximum(f, 1e-9)) ** 4)
    if hi < SR / 2:
        gain *= 1 / (1 + (f / hi) ** 4)
    return np.fft.irfft(spec * gain, n=len(x))


def _decay(t: np.ndarray, tau: float, attack: float = 0.002) -> np.ndarray:
    return np.exp(-t / tau) * np.minimum(1.0, t / max(attack, 1e-6))


def _stereo(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.abs(x).max())
    x = x * (peak / m) if m > 0 else x
    return np.stack([x, x], axis=1).astype(np.float32)


def _place(out: np.ndarray, hit: np.ndarray, at: float) -> None:
    i = int(at * SR)
    j = min(len(out), i + len(hit))
    if i < len(out):
        out[i:j] += hit[:j - i]


def _bell(freq: float, dur: float, tau: float, partials=(1.0, 2.76, 5.4, 8.9), amps=(1.0, 0.5, 0.25, 0.12)) -> np.ndarray:
    t = _t(dur)
    return sum(a * np.sin(2 * np.pi * freq * p * t) * _decay(t, tau / (1 + 0.6 * k)) for k, (p, a) in enumerate(zip(partials, amps)))


def deep_thud() -> np.ndarray:
    t = _t(0.9)
    f = 45 + 50 * np.exp(-t / 0.12)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * _decay(t, 0.22, 0.004)
    knock = _band(_rng(1).standard_normal(len(t)), 0, 220) * _decay(t, 0.05, 0.001)
    return _stereo(body + 0.5 * knock / (np.abs(knock).max() + 1e-9))


def draw_zap() -> np.ndarray:
    t = _t(0.9)
    f = 2400 + 3200 * (t / 0.9) ** 0.7
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.6 + 0.4 * np.sin(2 * np.pi * 55 * t))
    hiss = _band(_rng(2).standard_normal(len(t)), 4000, 9000) * 0.25
    env = np.minimum(1.0, t / 0.04) * np.clip((0.9 - t) / 0.25, 0, 1)
    return _stereo((tone + hiss) * env)


def bubble_pluck() -> np.ndarray:
    t = _t(0.28)
    f = 380 + 900 * (1 - np.exp(-t / 0.03))
    return _stereo(np.sin(2 * np.pi * np.cumsum(f) / SR) * _decay(t, 0.06, 0.002))


def paper_slide() -> np.ndarray:
    t = _t(0.85)
    n = _band(_rng(3).standard_normal(len(t)), 1500, 7500)
    wobble = 0.65 + 0.35 * np.abs(_band(_rng(4).standard_normal(len(t)), 0, 40))
    wobble = wobble / wobble.max()
    env = np.minimum(1.0, t / 0.12) * np.clip((0.85 - t) / 0.3, 0, 1)
    return _stereo(n * wobble * env)


def cash_register() -> np.ndarray:
    out = np.zeros(int(1.5 * SR))
    rng = _rng(5)
    for k in range(7):  # the ratchet
        click = _band(rng.standard_normal(int(0.012 * SR)), 1800, 9000) * np.exp(-np.arange(int(0.012 * SR)) / (0.003 * SR))
        _place(out, click, 0.02 + 0.035 * k)
    _place(out, 0.8 * _bell(2093, 1.1, 0.35), 0.32)
    _place(out, 0.55 * _bell(3136, 0.9, 0.28), 0.40)
    return _stereo(out)


def clock_chime() -> np.ndarray:
    return _stereo(_bell(880, 1.8, 0.6, partials=(1.0, 2.0, 3.01, 4.16), amps=(1.0, 0.45, 0.2, 0.1)))


def metal_clang() -> np.ndarray:
    t = _t(1.3)
    body = sum(a * np.sin(2 * np.pi * 640 * p * t) * _decay(t, 0.42 / (1 + 0.5 * k)) for k, (p, a) in enumerate(zip((1, 1.59, 2.14, 2.65, 3.5), (1, .7, .5, .35, .2))))
    hit = _band(_rng(6).standard_normal(len(t)), 1500, 9000) * _decay(t, 0.012, 0.0005)
    return _stereo(body + 0.8 * hit / (np.abs(hit).max() + 1e-9))


def muffled_explosion() -> np.ndarray:
    t = _t(2.4)
    n = _rng(7).standard_normal(len(t))
    low = _band(n, 0, 160) * _decay(t, 0.7, 0.01)
    mid = _band(n, 0, 700) * _decay(t, 0.25, 0.004)
    thump = np.sin(2 * np.pi * (38 + 40 * np.exp(-t / 0.2)) * t) * _decay(t, 0.5, 0.004)
    x = low / (np.abs(low).max() + 1e-9) + 0.6 * mid / (np.abs(mid).max() + 1e-9) + 0.9 * thump
    return _stereo(_band(x, 0, 500) * np.clip((2.4 - t) / 0.6, 0, 1))


def boil_sizzle() -> np.ndarray:
    t = _t(2.2)
    rng = _rng(8)
    fizz = _band(rng.standard_normal(len(t)), 3500, 14000) * (0.5 + 0.5 * (rng.random(len(t)) > 0.7))
    out = fizz * 0.5
    for at in np.sort(rng.uniform(0.05, 1.9, 14)):  # bubbles
        f0 = rng.uniform(250, 700); d = _t(0.08)
        _place(out, np.sin(2 * np.pi * np.cumsum(f0 + 600 * (1 - np.exp(-d / 0.02))) / SR) * _decay(d, 0.025, 0.001) * 0.5, at)
    return _stereo(out * np.minimum(1.0, t / 0.1) * np.clip((2.2 - t) / 0.5, 0, 1))


def wood_splinter() -> np.ndarray:
    out = np.zeros(int(1.4 * SR))
    rng = _rng(9)
    for at in np.sort(rng.uniform(0.0, 1.0, 11)):
        d = int(rng.uniform(0.012, 0.035) * SR)
        burst = _band(rng.standard_normal(d), rng.uniform(900, 2000), rng.uniform(3500, 7000)) * np.exp(-np.arange(d) / (0.006 * SR))
        _place(out, burst / (np.abs(burst).max() + 1e-9) * rng.uniform(0.4, 1.0), at)
    return _stereo(out)


def ice_crack() -> np.ndarray:
    out = np.zeros(int(1.2 * SR))
    rng = _rng(10)
    for at, amp in ((0.0, 1.0), (0.11, 0.55), (0.3, 0.8)):
        d = _t(0.18)
        ping = np.sin(2 * np.pi * np.cumsum(3200 * np.exp(-d / 0.05) + 700) / SR) * _decay(d, 0.05, 0.0005)
        snap = _band(rng.standard_normal(len(d)), 2500, 12000) * _decay(d, 0.006, 0.0002)
        _place(out, amp * (0.6 * ping + snap / (np.abs(snap).max() + 1e-9)), at)
    return _stereo(out)


def steam_chug() -> np.ndarray:
    out = np.zeros(int(3.2 * SR))
    rng = _rng(11)
    for k in range(11):
        at = 0.05 + k * 0.28
        d = _t(0.22)
        chuff = _band(rng.standard_normal(len(d)), 250, 2600) * _decay(d, 0.07, 0.006)
        thump = np.sin(2 * np.pi * 62 * d) * _decay(d, 0.1, 0.004)
        _place(out, chuff / (np.abs(chuff).max() + 1e-9) * 0.8 + 0.5 * thump, at)
    return _stereo(out * np.clip((3.2 - np.arange(len(out)) / SR) / 0.8, 0, 1))


def car_gravel() -> np.ndarray:
    t = _t(3.2)
    rng = _rng(12)
    crunch = np.zeros(len(t))
    idx = rng.integers(0, len(t), 900)
    crunch[idx] = rng.uniform(0.3, 1.0, 900)
    crunch = _band(np.convolve(crunch, np.exp(-np.arange(300) / 40.0), mode="same"), 900, 7000)
    engine = _band(rng.standard_normal(len(t)), 0, 120) * 0.6
    env = np.minimum(1.0, t / 0.4) * np.clip((3.2 - t) / 0.6, 0, 1)
    return _stereo((crunch / (np.abs(crunch).max() + 1e-9) + engine / (np.abs(engine).max() + 1e-9) * 0.5) * env)


def birds_chirping() -> np.ndarray:
    out = np.zeros(int(3.6 * SR))
    rng = _rng(13)
    for at in (0.1, 0.55, 0.9, 1.7, 2.05, 2.8):
        for k in range(int(rng.integers(2, 4))):
            d = _t(0.09)
            up = rng.random() > 0.5
            f = (3200 + 1800 * (d / 0.09)) if up else (5200 - 1800 * (d / 0.09))
            chirp = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * d / 0.09) ** 2
            _place(out, chirp * rng.uniform(0.5, 1.0), at + k * 0.13)
    return _stereo(out)


def industrial_hum() -> np.ndarray:
    n = int(12 * SR)
    t = np.arange(n) / SR
    base = sum(a * np.sin(2 * np.pi * 50 * k * t + k) for k, a in ((1, 1.0), (2, 0.6), (3, 0.35), (4, 0.2), (6, 0.1)))
    mod = 0.85 + 0.15 * np.sin(2 * np.pi * 0.25 * t)
    rumble = _band(_rng(14).standard_normal(n), 60, 380) * 0.35
    return _stereo(base * mod + rumble)


def airplane_hum() -> np.ndarray:
    n = int(8 * SR)
    t = np.arange(n) / SR
    saw = sum(np.sin(2 * np.pi * 78 * k * t) / k for k in range(1, 9))
    wash = _band(_rng(15).standard_normal(n), 180, 1400)
    mod = 0.9 + 0.1 * np.sin(2 * np.pi * 0.4 * t)
    return _stereo(_band(saw * 0.6 + wash * 0.5, 0, 900) * mod)


GENERATORS: Dict[str, Callable[[], np.ndarray]] = {
    "deep_thud": deep_thud, "draw_zap": draw_zap, "bubble_pluck": bubble_pluck, "paper_slide": paper_slide,
    "cash_register": cash_register, "clock_chime": clock_chime, "metal_clang": metal_clang, "muffled_explosion": muffled_explosion,
    "boil_sizzle": boil_sizzle, "wood_splinter": wood_splinter, "ice_crack": ice_crack, "steam_chug": steam_chug,
    "car_gravel": car_gravel, "birds_chirping": birds_chirping, "industrial_hum": industrial_hum, "airplane_hum": airplane_hum,
}

_cache: Dict[str, np.ndarray] = {}


def render(name: str) -> np.ndarray:
    if name not in GENERATORS:
        raise KeyError(f"no synthesizer named {name!r}")
    if name not in _cache:
        _cache[name] = GENERATORS[name]()
    return _cache[name].copy()
