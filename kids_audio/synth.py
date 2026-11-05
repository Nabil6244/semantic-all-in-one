"""Toy-instrument synthesis for the preschool audio library (numpy only, 48 kHz).

Every voice is written into a *circular* buffer (`Loop`): a note's tail that runs past the loop end wraps to the start,
and the reverb is a circular convolution, so a rendered bed repeats with no gap and no click by construction.
"""
import numpy as np

SR = 48000
A4 = 440.0
NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(name):
    """'C4', 'F#5' -> frequency."""
    n, o = (name[:-1], int(name[-1]))
    return A4 * 2 ** ((NOTE[n] + 12 * (o + 1) - 69) / 12)


def _env(n, attack, decay):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / decay)


def _modal(f, dur, partials, attack=0.002, vel=1.0):
    """Sum of decaying sine partials: [(ratio, gain, decay_s), ...]."""
    n = int(dur * SR); t = np.arange(n) / SR; out = np.zeros(n)
    for r, g, d in partials:
        if f * r < SR / 2.2:
            out += g * np.sin(2 * np.pi * f * r * t) * _env(n, attack, d)
    return out * vel


def marimba(f, vel=1.0, dur=1.6):
    x = _modal(f, dur, [(1, 1.0, 0.45), (3.93, 0.32, 0.12), (9.2, 0.08, 0.035)], attack=0.0015, vel=vel)
    rng = np.random.default_rng(int(f * 10)); m = int(0.006 * SR)
    x[:m] += rng.standard_normal(m) * np.linspace(0.05, 0, m) * vel          # soft mallet
    return x


def glock(f, vel=1.0, dur=2.4):
    return _modal(f, dur, [(1, 1.0, 0.9), (2.76, 0.42, 0.35), (5.4, 0.2, 0.15), (8.93, 0.08, 0.07)], attack=0.0008, vel=vel)


def pluck(f, vel=1.0, dur=1.4, bright=0.5, seed=0):
    """Karplus-Strong string with a little body resonance (ukulele-like)."""
    n = int(dur * SR); p = max(2, int(round(SR / f)))
    rng = np.random.default_rng(seed + int(f))
    buf = rng.uniform(-1, 1, p); buf = np.convolve(buf, np.ones(3) / 3, "same") * (0.6 + 0.4 * bright)
    out = np.zeros(n + p); damp = 0.996 - 0.004 * (1 - bright)
    for k in range(0, n, p):                                               # one string period per step (vectorised)
        out[k:k + p] = buf; buf = damp * 0.5 * (buf + np.roll(buf, -1))
    out = out[:n]
    body = np.exp(-np.arange(int(0.012 * SR)) / (0.003 * SR)) * np.sin(2 * np.pi * 220 * np.arange(int(0.012 * SR)) / SR)
    return np.convolve(out, body / np.abs(body).sum() * 6, "full")[:n] * vel


def bass(f, vel=1.0, dur=0.6):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.18 * np.sin(4 * np.pi * f * t)
    return x * _env(n, 0.006, dur * 0.45) * vel


def kick(vel=1.0):
    n = int(0.28 * SR); t = np.arange(n) / SR
    f = 50 + 70 * np.exp(-t / 0.03); ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * _env(n, 0.002, 0.09) * vel


def _noise_band(n, lo, hi, seed):
    x = np.random.default_rng(seed).standard_normal(n); X = np.fft.rfft(x); fr = np.fft.rfftfreq(n, 1 / SR)
    X[(fr < lo) | (fr > hi)] = 0
    return np.fft.irfft(X, n)


def shaker(vel=1.0, seed=1):
    n = int(0.09 * SR); x = _noise_band(n, 4000, 12000, seed)
    return x / (np.abs(x).max() + 1e-9) * _env(n, 0.01, 0.025) * vel


def snap(vel=1.0, seed=2):
    n = int(0.18 * SR); x = _noise_band(n, 900, 3500, seed); x /= np.abs(x).max() + 1e-9
    e = np.zeros(n)
    for d in (0, 0.008, 0.017):                                           # a few quick slaps = soft clap
        k = int(d * SR); e[k:] += _env(n - k, 0.001, 0.02)
    return x * e * vel * 0.6


def reverb_ir(seconds=0.9, seed=7, damp=0.5):
    n = int(seconds * SR); t = np.arange(n) / SR
    ir = np.random.default_rng(seed).standard_normal(n) * np.exp(-t / (seconds / 5))
    ir = np.convolve(ir, np.ones(int(2 + damp * 10)) / (2 + damp * 10), "same"); ir[0] = 0
    return ir / np.sqrt((ir ** 2).sum())


class Loop:
    """A circular stereo buffer for one seamless loop."""

    def __init__(self, seconds):
        self.n = int(round(seconds * SR)); self.buf = np.zeros((2, self.n))

    def add(self, x, at, gain=1.0, pan=0.0):
        """Mix mono `x` starting at `at` seconds; whatever runs past the end wraps to the start."""
        i0 = int(round(at * SR)) % self.n; idx = (i0 + np.arange(len(x))) % self.n
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        np.add.at(self.buf[0], idx, x * gain * l * 1.4142); np.add.at(self.buf[1], idx, x * gain * r * 1.4142)

    def reverb(self, mix=0.18, seconds=0.9):
        ir = reverb_ir(seconds); H = np.fft.rfft(np.pad(ir, (0, max(0, self.n - len(ir))))[: self.n])
        wet = np.stack([np.fft.irfft(np.fft.rfft(c) * H, self.n) for c in self.buf])     # circular convolution keeps the loop seamless
        self.buf = self.buf * (1 - mix) + wet * mix * 1.6


def one_shot(seconds):
    """A plain (non-wrapping) stereo buffer for sound effects."""
    return np.zeros((2, int(round(seconds * SR))))


def place(buf, x, at, gain=1.0, pan=0.0):
    i0 = int(round(at * SR)); m = max(0, min(len(x), buf.shape[1] - i0))
    if m <= 0:
        return
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[0, i0:i0 + m] += x[:m] * gain * l * 1.4142; buf[1, i0:i0 + m] += x[:m] * gain * r * 1.4142


def reverb_tail(buf, mix=0.2, seconds=0.8):
    ir = reverb_ir(seconds); n = buf.shape[1] + len(ir)
    wet = np.stack([np.fft.irfft(np.fft.rfft(c, n) * np.fft.rfft(ir, n), n)[: buf.shape[1]] for c in buf])
    return buf * (1 - mix) + wet * mix * 1.6
