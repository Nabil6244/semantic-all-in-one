"""Original synthesized sound effects (numpy only, deterministic). Nothing here is sampled or downloaded.
    render(cue, dur, seed) -> mono float32 at 48 kHz.   CLI: python3 tools/sfx_synth.py out/sfx   writes one wav per cue.
These are procedural stand-ins (filtered noise + envelopes): good enough to carry a mix, not studio recordings."""
import sys
import zlib
import numpy as np

SR = 48000


def _rng(seed): return np.random.default_rng(zlib.crc32(str(seed).encode()))


def _lp(x, fc):
    """FFT low-pass (brick-wall softened) -- fine for noise shaping."""
    n = len(x); X = np.fft.rfft(x); f = np.fft.rfftfreq(n, 1 / SR); X *= 1 / (1 + (f / max(fc, 1)) ** 4); return np.fft.irfft(X, n)


def _hp(x, fc): return x - _lp(x, fc)


def _bp(x, lo, hi): return _lp(_hp(x, lo), hi)


def _env(n, attack, decay):
    t = np.arange(n) / SR; e = np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / max(decay, 1e-4)); return e


def _noise(n, r): return r.standard_normal(n)


def _norm(x, peak=0.9): m = np.max(np.abs(x)) or 1; return (x / m * peak).astype(np.float32)


def shot(r, n=int(0.5 * SR), body=1.0):
    nz = _noise(n, r); crack = _hp(nz, 1800) * _env(n, 0.0004, 0.012); thump = _lp(nz, 260) * _env(n, 0.001, 0.07); tail = _bp(nz, 400, 3000) * _env(n, 0.002, 0.16) * 0.35
    return crack + thump * body + tail


def place(buf, snd, t, gain=1.0):
    i = max(0, int(t * SR))
    if i >= len(buf): return
    j = min(len(buf), i + len(snd)); buf[i:j] += snd[: j - i] * gain


def gunfire(dur, seed, density=1.0, far=False):
    r = _rng(seed); out = np.zeros(int(dur * SR)); t = 0.0
    while t < dur:
        burst = r.integers(3, 9) if r.random() < 0.6 else 1
        for k in range(burst):
            s = shot(r, body=r.uniform(0.6, 1.2)); place(out, s, t + k * r.uniform(0.07, 0.11), r.uniform(0.4, 1.0))
        t += r.exponential(1.0 / max(0.15, density)) * 1.4 + 0.3
    if far: out = _lp(out, 1400) * 0.7
    return out


def explosion(dur, seed, wet=False):
    r = _rng(seed); n = int(max(dur, 3.2) * SR); nz = _noise(n, r)
    boom = _lp(nz, 120) * _env(n, 0.004, 0.55) * 2.2; mid = _bp(nz, 150, 1200) * _env(n, 0.002, 0.28); crackle = _hp(nz, 2500) * _env(n, 0.001, 0.05) * 0.8
    rumble = _lp(_noise(n, r), 70) * _env(n, 0.05, 1.3) * 1.2
    x = boom + mid + crackle + rumble
    if wet: x = _lp(x, 900) + _hp(_noise(n, r), 1500) * _env(n, 0.05, 0.6) * 0.3
    return x


def engine(dur, seed, f0=70, prop=True):
    r = _rng(seed); n = int(dur * SR); t = np.arange(n) / SR
    base = np.zeros(n)
    for h, a in [(1, 1), (2, 0.6), (3, 0.4), (4, 0.25), (6, 0.15)]:
        base += a * np.sin(2 * np.pi * (f0 * h * (1 + 0.012 * np.sin(2 * np.pi * 0.7 * t))) * t + r.uniform(0, 6.28))
    if prop: base *= 0.7 + 0.3 * np.sin(2 * np.pi * (f0 / 3.0) * t) ** 2
    return base * 0.6 + _lp(_noise(n, r), 400) * 0.4


def planes_pass(dur, seed): n = int(dur * SR); t = np.arange(n) / SR; sw = np.sin(np.pi * t / max(dur, 1e-3)) ** 1.5; return engine(dur, seed, 62) * sw + engine(dur, str(seed) + 'b', 66) * sw * 0.7


def tanks(dur, seed):
    r = _rng(seed); n = int(dur * SR); x = engine(dur, seed, 38, prop=False) * 0.7
    for k in range(int(dur * 7)): place(x, _bp(_noise(int(0.06 * SR), r), 800, 4000) * _env(int(0.06 * SR), 0.001, 0.02), k / 7 + r.uniform(0, 0.03), 0.25)
    return x


def marching(dur, seed):
    r = _rng(seed); n = int(dur * SR); x = np.zeros(n)
    for k in range(int(dur * 2.0)):
        s = _lp(_noise(int(0.12 * SR), r), 500) * _env(int(0.12 * SR), 0.003, 0.04); place(x, s, k / 2.0 + r.uniform(-0.01, 0.01), 0.8)
        place(x, _bp(_noise(int(0.04 * SR), r), 1500, 5000) * _env(int(0.04 * SR), 0.001, 0.01), k / 2.0 + 0.02, 0.15)
    return x


def surf(dur, seed):
    r = _rng(seed); n = int(dur * SR); t = np.arange(n) / SR; nz = _noise(n, r)
    sw = 0.45 + 0.55 * (np.sin(2 * np.pi * t / 8.0 + 1.3) * 0.5 + 0.5) ** 2
    return (_bp(nz, 200, 2500) * sw * 0.8 + _lp(nz, 150) * 0.3)


def wind(dur, seed):
    r = _rng(seed); n = int(dur * SR); t = np.arange(n) / SR; nz = _noise(n, r)
    return _bp(nz, 120, 1000) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 11 + 0.4) * 0.5 + 0.25)


def whoosh(dur, seed):
    r = _rng(seed); n = int(max(dur, 1.4) * SR); t = np.arange(n) / SR; nz = _noise(n, r)
    f = 300 + 3500 * np.sin(np.pi * t / (n / SR)) ** 2; x = np.zeros(n)
    for lo, hi in [(200, 900), (900, 3000), (3000, 7000)]: x += _bp(nz, lo, hi) * (0.5 + 0.5 * np.sin(np.pi * t / (n / SR)))
    return x * np.sin(np.pi * t / (n / SR)) ** 1.6


def chapter_hit(dur, seed):
    r = _rng(seed); n = int(2.6 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * 52 * t * np.exp(-t * 0.25)) * np.exp(-t / 0.9) * 1.6 + _lp(_noise(n, r), 180) * _env(n, 0.003, 0.5) * 0.8


def ramp_drop(dur, seed):
    r = _rng(seed); n = int(1.8 * SR); nz = _noise(n, r)
    return _bp(nz, 150, 900) * _env(n, 0.05, 0.5) * 1.0 + _hp(nz, 2000) * _env(n, 0.0005, 0.03) * 1.4 * (np.arange(n) > int(0.55 * SR)) + _lp(nz, 120) * _env(n, 0.5, 0.3) * 0.7


def flak(dur, seed): r = _rng(seed); n = int(1.5 * SR); nz = _noise(n, r); return _lp(nz, 900) * _env(n, 0.001, 0.12) * 1.3 + _hp(nz, 3000) * _env(n, 0.0008, 0.02) * 0.6


def ship_guns(dur, seed): r = _rng(seed); n = int(3.5 * SR); nz = _noise(n, r); return _lp(nz, 90) * _env(n, 0.003, 0.9) * 2.4 + _bp(nz, 100, 700) * _env(n, 0.002, 0.3) + _hp(nz, 1500) * _env(n, 0.001, 0.03) * 0.6


def thunder(dur, seed): r = _rng(seed); n = int(max(dur, 5) * SR); nz = _lp(_noise(n, r), 140); e = _env(n, 0.3, 1.8) * (0.6 + 0.4 * np.sin(np.arange(n) / SR * 3.1) ** 2); return nz * e * 2.2


def clock(dur, seed):
    r = _rng(seed); n = int(dur * SR); x = np.zeros(n)
    for k in range(int(dur)): place(x, _bp(_noise(int(0.03 * SR), r), 1200, 5000) * _env(int(0.03 * SR), 0.0004, 0.006), k + 0.0, 0.5); place(x, _bp(_noise(int(0.03 * SR), r), 900, 3800) * _env(int(0.03 * SR), 0.0004, 0.006), k + 0.5, 0.3)
    return x


def bells(dur, seed):
    n = int(5 * SR); t = np.arange(n) / SR; x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / d) for f, a, d in [(392, 1, 2.6), (784 * 1.003, 0.5, 1.8), (1180, 0.3, 1.1), (1570, 0.2, 0.7)])
    return x


CUES = {
    'gunfire_near': lambda d, s: gunfire(d, s, 1.0), 'gunfire': lambda d, s: gunfire(d, s, 1.0), 'gunfire_far': lambda d, s: gunfire(d, s, 0.7, far=True), 'distant_gunfire': lambda d, s: gunfire(d, s, 0.5, far=True),
    'shot_single': lambda d, s: shot(_rng(s)), 'explosion': lambda d, s: explosion(d, s), 'water_explosion': lambda d, s: explosion(d, s, wet=True), 'flak': flak, 'ship_guns': ship_guns,
    'ramp_drop': ramp_drop, 'whoosh': whoosh, 'chapter_hit': chapter_hit, 'planes_pass': planes_pass, 'tanks': tanks, 'marching': marching, 'thunder': thunder, 'clock': clock, 'bells': bells, 'surf': surf, 'wind': wind,
}


def render(cue, dur=3.0, seed=1):
    if cue not in CUES: return None
    return _norm(CUES[cue](dur, seed), 0.9)


if __name__ == '__main__':
    import wave, os
    out = sys.argv[1] if len(sys.argv) > 1 else 'out/sfx'; os.makedirs(out, exist_ok=True)
    for c in CUES:
        x = render(c, 4.0, 7); w = wave.open(f'{out}/{c}.wav', 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((x * 32767).astype('<i2').tobytes()); w.close()
    print(len(CUES), 'cues ->', out)
