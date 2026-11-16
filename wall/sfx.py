"""The wall's item sounds, synthesised (no sample files, no licences) and written once to assets/bundled-sfx/wall/.

    python -m wall.sfx            (re)write every file
    ensure() -> folder            writes only the missing files; called before a mix
    file_for(cue) -> Path         'drop', 'pop', 'slide', 'marker', 'pencil', 'impact', 'stamp', 'boom', 'type', 'whoosh', 'ticks:<s>'
                                  (a counter's roll uses the closest of the pre-made tick runs)
    GAIN_DB / KIND                level below each sample's own peak, and the mixer kind (aviation.sound's MIN_GAP rule picks by kind)
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Callable, Dict

import numpy as np

SR = 48000
DIR = Path(__file__).resolve().parents[1] / "assets" / "bundled-sfx" / "wall"
TICK_RUNS = (0.6, 1.0, 1.5, 2.2, 3.0)

GAIN_DB = {"drop": -20.0, "pop": -22.0, "slide": -27.0, "marker": -26.0, "pencil": -28.0, "impact": -17.0, "stamp": -15.0,
           "boom": -14.0, "type": -24.0, "whoosh": -22.0, "ticks": -24.0}
KIND = {"drop": "thud", "pop": "pop", "slide": "write", "marker": "write", "pencil": "write", "impact": "hit", "stamp": "hit",
        "boom": "hit", "type": "tick", "whoosh": "whoosh", "ticks": "tick"}


def _n(s: float) -> int:
    return int(s * SR)


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def _env(m: int, att: float, dec: float) -> np.ndarray:
    t = np.arange(m) / SR
    return np.minimum(1, t / max(att, 1e-4)) * np.exp(-np.maximum(0, t - att) / dec)


def _norm(x: np.ndarray) -> np.ndarray:
    return x / (np.abs(x).max() + 1e-9)


def whoosh() -> np.ndarray:
    m = _n(0.6)
    t = np.linspace(0, 1, m)
    return _norm(_band(_rng(1).standard_normal(m), 300, 4000) * np.sin(np.pi * t) ** 3)


def drop() -> np.ndarray:            # a print landing: paper slap + low thump
    m = _n(0.35)
    slap = _band(_rng(2).standard_normal(m), 900, 6000) * _env(m, 0.001, 0.025)
    t = np.arange(m) / SR
    return _norm(slap * 0.7 + np.sin(2 * np.pi * 110 * t) * _env(m, 0.002, 0.07))


def pop() -> np.ndarray:
    m = _n(0.12)
    t = np.arange(m) / SR
    return _norm(np.sin(2 * np.pi * np.cumsum(500 + 900 * np.exp(-t * 40)) / SR) * _env(m, 0.002, 0.03))


def slide() -> np.ndarray:           # string pulled taut
    m = _n(0.7)
    t = np.linspace(0, 1, m)
    return _norm(_band(_rng(3).standard_normal(m), 1500, 7000) * np.sin(np.pi * t) ** 2)


def marker() -> np.ndarray:
    m = _n(0.4)
    t = np.arange(m) / SR
    f = 1800 + 500 * np.sin(2 * np.pi * 8 * t)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25 + _band(_rng(4).standard_normal(m), 3000, 8000) * 0.75
    return _norm(x * np.sin(np.pi * t / 0.4))


def pencil() -> np.ndarray:
    m = _n(0.7)
    x = _band(_rng(5).standard_normal(m), 2500, 9000)
    mod = (np.sin(2 * np.pi * 11 * np.arange(m) / SR) > 0).astype(float) * 0.7 + 0.3
    return _norm(x * mod * np.sin(np.pi * np.arange(m) / m))


def _tick(seed: int) -> np.ndarray:
    m = _n(0.04)
    return _norm(_band(_rng(seed).standard_normal(m), 2500, 9000) * _env(m, 0.0005, 0.005))


def ticks(d: float) -> np.ndarray:   # a counter rolling: ticks that slow down as the number lands
    out = np.zeros(_n(d) + _n(0.05))
    for k, u in enumerate(np.linspace(0, 1, max(4, int(d * 14)))):
        at = _n(d * (1 - (1 - u) ** 1.7))
        tk = _tick(100 + k) * 0.8
        out[at:at + len(tk)] += tk[: len(out) - at]
    return _norm(out)


def typing(d: float = 1.0) -> np.ndarray:
    out = np.zeros(_n(d) + _n(0.05))
    for k, at in enumerate(np.linspace(0, d, 12)):
        tk = _tick(200 + k)
        i = _n(at)
        out[i:i + len(tk)] += tk[: len(out) - i]
    return _norm(out)


def impact() -> np.ndarray:
    m = _n(0.6)
    t = np.arange(m) / SR
    body = np.sin(2 * np.pi * np.cumsum(80 * np.exp(-t * 6) + 42) / SR) * _env(m, 0.002, 0.16)
    return _norm(body + 0.4 * _band(_rng(6).standard_normal(m), 600, 4000) * _env(m, 0.001, 0.025))


def stamp() -> np.ndarray:
    m = _n(0.45)
    t = np.arange(m) / SR
    return _norm(np.sin(2 * np.pi * 70 * t) * _env(m, 0.001, 0.09) + _band(_rng(7).standard_normal(m), 400, 3500) * _env(m, 0.0005, 0.02))


def boom() -> np.ndarray:
    m = _n(2.2)
    t = np.arange(m) / SR
    sub = np.sin(2 * np.pi * np.cumsum(55 * np.exp(-t * 1.2) + 30) / SR) * _env(m, 0.005, 0.7)
    return _norm(sub + 0.5 * _band(_rng(8).standard_normal(m), 60, 600) * _env(m, 0.01, 0.5))


MAKERS: Dict[str, Callable[[], np.ndarray]] = {"whoosh": whoosh, "drop": drop, "pop": pop, "slide": slide, "marker": marker,
                                               "pencil": pencil, "impact": impact, "stamp": stamp, "boom": boom, "type": typing}
MAKERS.update({f"ticks_{int(d * 10):02d}": (lambda d=d: ticks(d)) for d in TICK_RUNS})


def _write(path: Path, x: np.ndarray) -> None:
    pcm = (np.clip(x * 0.98, -1, 1) * 32767).astype(np.int16)
    tmp = path.with_suffix(".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    tmp.replace(path)


def ensure(force: bool = False) -> Path:
    DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in MAKERS.items():
        p = DIR / f"{name}.wav"
        if force or not p.is_file():
            _write(p, fn())
    return DIR


def base(cue: str) -> str:
    return "ticks" if cue.startswith("ticks") else cue


def file_for(cue: str) -> Path:
    if cue.startswith("ticks"):
        try:
            d = float(cue.split(":", 1)[1])
        except (IndexError, ValueError):
            d = 1.0
        best = min(TICK_RUNS, key=lambda r: abs(r - d))
        return DIR / f"ticks_{int(best * 10):02d}.wav"
    return DIR / f"{cue}.wav"


PRIORITY = {"hit": 0, "tick": 1, "pop": 2, "write": 3, "thud": 4, "whoosh": 5}


def events(cues, min_gap: float = 0.25):
    """[(t, cue)] -> [{t, file, gain_db, kind}]: two sounds never closer than min_gap (the stronger kind keeps its slot)."""
    ensure()
    raw = []
    for t, cue in cues:
        name = base(cue)
        if name in KIND:
            raw.append({"t": round(float(t), 3), "file": str(file_for(cue)), "gain_db": GAIN_DB[name], "kind": KIND[name]})
    raw.sort(key=lambda e: (PRIORITY.get(e["kind"], 9), e["t"]))
    kept = []
    for e in raw:
        if all(abs(e["t"] - k["t"]) >= min_gap for k in kept):
            kept.append(e)
    return sorted(kept, key=lambda e: e["t"])


def track(total_s: float, cues, sr: int = SR) -> np.ndarray:
    """The wall's item sounds as one mono float32 track (for a style whose mixer takes a ready track, like War's)."""
    out = np.zeros(int(total_s * sr) + sr, dtype=np.float32)
    cache = {}
    for e in events(cues):
        f = e["file"]
        if f not in cache:
            with wave.open(f, "rb") as w:
                a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
                if w.getframerate() != sr and a.size:
                    a = np.interp(np.linspace(0, a.size - 1, int(a.size * sr / w.getframerate())), np.arange(a.size), a).astype(np.float32)
            cache[f] = a
        a = cache[f] * (10 ** (e["gain_db"] / 20.0))
        i = int(e["t"] * sr)
        if 0 <= i < out.size:
            n = min(a.size, out.size - i)
            out[i:i + n] += a[:n]
    return out


if __name__ == "__main__":
    print(ensure(force=True))
