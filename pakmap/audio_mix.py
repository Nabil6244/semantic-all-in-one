"""Phase 7: turn an AudioPlan into one audio file = the narration (untouched) + the pakMap sound bed.

This is pakMap's own mixer; the generic mixers in smart_editing are not used or changed. Everything is deterministic
(no randomness, fixed filters, fixed envelope maths). Decoding goes through ffmpeg; the mixing itself is plain numpy.

Levels and ducking (priority: narration > major sfx > normal sfx > ambience):
  * effects sit at their vocabulary volume (all well below speech) and dip DUCK_SFX while the narrator speaks
  * ambience dips DUCK_AMBIENCE while the narrator speaks, and a further DUCK_AMBIENCE_BY_MAJOR under a major effect
  * the narration is never gain-changed; where the sum would clip, only the sound bed dips, only around that moment
    (a short ramp down and back up, so no click; the rest of the video keeps its full effects and ambience)

The mix is streamed in CHUNK_S windows (see "rendering"), so a 60-minute video needs no more memory than a 1-minute one.
"""

from __future__ import annotations

import subprocess
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .audio_plan import AudioPlan, Bed, Cue, expand, sound_for
from . import synth as _synth
from .sounds import CLOSE, PRIORITY_MAJOR, SYNTHESIZED, Sound

SR = 48000
DUCK_SFX = 0.35
DUCK_AMBIENCE = 0.60
DUCK_AMBIENCE_BY_MAJOR = 0.50
SPEECH_RMS = 0.04  # RMS at which the narrator counts as fully speaking
ATTACK_S, RELEASE_S = 0.05, 0.35
CLIP_DIP_ATTACK_S, CLIP_DIP_RELEASE_S = 0.02, 0.25  # the bed's dip under a moment that would clip: down in 20 ms, back in 250 ms
HOP = 480  # 10 ms envelope step
PEAK_LIMIT = 0.97
SFX_REF_PEAK = 1.0     # every effect is normalised to this peak before its vocabulary volume is applied
AMBIENCE_REF_RMS = 0.2  # every ambience bed is normalised to this RMS (about -14 dBFS) before its vocabulary volume
MAX_NORMALISE_GAIN = 100.0  # never boost a near-silent file by more than 40 dB (it would only be noise)
LOOP_FADE_S = 1.0


class AudioMixError(RuntimeError):
    pass


@dataclass
class ResolvedAsset:
    sound: str
    catalog_id: str
    path: Optional[Path]  # None for a synthesized sound
    fidelity: str
    duration: float
    license: str = ""


@dataclass
class MixResult:
    path: Path
    changed: bool  # False when the narration file is returned untouched
    peak: float = 0.0
    bus_scale: float = 1.0  # the lowest bed level used anywhere (1.0 = the bed never had to dip to avoid clipping)
    used: List[dict] = field(default_factory=list)
    narration_duck_depth: float = 0.0
    clip_dip_s: float = 0.0  # seconds where the bed dipped below full level to keep the mix from clipping


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def decode(path: "str | Path", filters: str = "", sr: int = SR) -> np.ndarray:
    """Decode to float32 stereo (n, 2) at sr."""
    cmd = [_ffmpeg(), "-v", "error", "-nostdin", "-i", str(path)]
    if filters:
        cmd += ["-af", filters]
    cmd += ["-f", "f32le", "-ac", "2", "-ar", str(sr), "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise AudioMixError(f"could not read audio {path}: {proc.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).reshape(-1, 2).copy()


# ---- assets --------------------------------------------------------------------------------------------------

def resolve_assets(plan: AudioPlan, catalog: Any = None) -> AudioPlan:
    """Find a library file for every sound the plan uses. Cues/beds whose sound has no file are removed from the
    plan and reported in plan.missing (never replaced by something unrelated). Approximations are listed in
    plan.approximate so the author knows what they are hearing."""
    if not plan.enabled:
        return plan
    if catalog is None:
        import smart_editing as se

        catalog = se.get_sfx_catalog()
    by_id = {e.id: e for e in getattr(catalog, "entries", [])}
    root = getattr(catalog, "root", None)

    def find(sound: Sound) -> Optional[ResolvedAsset]:
        for cid, fidelity in sound.candidates:
            entry = by_id.get(cid)
            if entry is None:
                continue
            path = entry.resolved_path(root)
            if path.is_file():
                return ResolvedAsset(sound.id, cid, path, fidelity, float(entry.duration or 0.0), getattr(entry, "license", "") or "")
        if sound.synth:
            dur = len(_synth.render(sound.synth)) / SR
            return ResolvedAsset(sound.id, "synth:" + sound.synth, None, SYNTHESIZED, dur, "original, generated in code")
        return None

    def need(sound_id: str) -> Optional[ResolvedAsset]:
        if sound_id in plan.assets:
            return plan.assets[sound_id]
        sound = sound_for(sound_id, "ambience" if sound_id in _ambience_ids(plan) else "sfx")
        if sound is None:
            plan.missing[sound_id] = "not in the pakMap sound vocabulary"
            return None
        asset = find(sound)
        if asset is None:
            tried = ", ".join(c for c, _ in sound.candidates) or "no library entry is defined for it"
            plan.missing[sound_id] = f"{sound.source}: no matching file in the sound library (looked for: {tried}). {sound.note}".strip()
            return None
        plan.assets[sound_id] = asset
        if asset.fidelity != CLOSE or sound.filters:
            how = "synthesized" if asset.fidelity == SYNTHESIZED else ("processed" if sound.filters else asset.fidelity)
            plan.approximate[sound_id] = f"{sound.source} -> {asset.catalog_id} ({how}). {sound.note}".strip()
        return asset

    kept: List[Cue] = []
    for cue in plan.cues:
        parts = expand(cue)
        got = [need(p.sound) is not None for p in parts]
        if any(got):
            cue.asset = next(plan.assets[p.sound].catalog_id for p, g in zip(parts, got) if g)
            kept.append(cue)
        else:
            plan.dropped.append((cue, "no sound file in the library"))
    plan.cues = kept
    beds: List[Bed] = []
    for bed in plan.beds:
        asset = need(bed.sound)
        if asset is None:
            plan.warnings.append(f"ambience {bed.sound} at {bed.start:.1f}s has no sound file and is skipped")
            continue
        bed.asset = asset.catalog_id
        beds.append(bed)
    plan.beds = beds
    return plan


def _ambience_ids(plan: AudioPlan) -> set:
    return {b.sound for b in plan.beds}


# ---- rendering -----------------------------------------------------------------------------------------------
#
# The mix is made in CHUNK_S windows, so memory stays flat however long the video is (a full-length float buffer is
# about 0.4 GB per minute of stereo audio, and the old mixer held several of them). Nothing a window needs comes from
# another window's audio:
#   * the narration envelope is ~100 values per second: pass 1 streams the narration once and keeps only those
#     (fast attack / slow release smoothing runs over them in order, as before); a window reads its samples off them;
#   * the "a major effect is sounding" envelope is a sum of rectangles smoothed by a Hann window, so its value at
#     any sample comes straight from the window's running sum (no full-length convolution);
#   * effect hits and ambience loops are placed by sample index; a window adds just the part that falls inside it,
#     in the same order as before (so every sample is summed exactly as the full-length mixer summed it);
#   * anti-clip: pass 2 writes the mix at full bed level and keeps, per envelope step (10 ms), the highest bed level
#     that does not push the mix past PEAK_LIMIT (or past the narration's own peak, where the narration alone is already
#     louder than that). Only if some step needs less than full level is a smooth gain curve made from those ~100 values
#     per second (_clip_dip_curve) and the file written again with the bed following it (pass 3).

CHUNK_S = 30.0
CHUNK = int(CHUNK_S * SR) // HOP * HOP  # whole envelope steps per window


def _hop_targets(mono: np.ndarray) -> np.ndarray:
    """'How loud is the narrator' per HOP samples (the last step padded with silence), 0..1."""
    hops = max(1, -(-len(mono) // HOP))
    pad = np.zeros(hops * HOP, dtype=np.float32)
    pad[:len(mono)] = mono
    rms = np.sqrt((pad.reshape(hops, HOP) ** 2).mean(axis=1))
    return np.clip(rms / SPEECH_RMS, 0.0, 1.0)


def _smooth_hops(target: np.ndarray) -> np.ndarray:
    a_att = 1.0 - np.exp(-HOP / SR / ATTACK_S)
    a_rel = 1.0 - np.exp(-HOP / SR / RELEASE_S)
    env = np.zeros(len(target), dtype=np.float32)
    y = 0.0
    for i, x in enumerate(target):  # a loop over ~100 values per second, deterministic
        y += (a_att if x > y else a_rel) * (x - y)
        env[i] = y
    return env


class _NarrationEnvelope:
    """The narration envelope as ~100 values per second; samples(a, b) gives it per sample (0 past the narration)."""

    def __init__(self) -> None:
        self._targets: List[np.ndarray] = []
        self._tail = np.zeros((0, 2), dtype=np.float32)
        self.length = 0
        self.hops: Optional[np.ndarray] = None

    def feed(self, block: np.ndarray) -> None:
        self.length += len(block)
        if len(self._tail):
            block = np.concatenate([self._tail, block])
        whole = len(block) // HOP * HOP
        if whole:
            self._targets.append(_hop_targets(block[:whole].mean(axis=1)))
        self._tail = block[whole:].copy()

    def finish(self) -> "_NarrationEnvelope":
        if len(self._tail) or not self._targets:
            self._targets.append(_hop_targets(self._tail.mean(axis=1)))
        self.hops = _smooth_hops(np.concatenate(self._targets))
        self._targets, self._tail = [], np.zeros((0, 2), dtype=np.float32)
        return self

    @classmethod
    def from_array(cls, narr: np.ndarray) -> "_NarrationEnvelope":
        env = cls()
        env.feed(narr if narr.ndim == 2 else np.stack([narr, narr], axis=1))
        return env.finish()

    def samples(self, a: int, b: int) -> np.ndarray:
        out = np.zeros(max(0, b - a), dtype=np.float32)
        e = min(b, self.length)
        if e > a:
            xs = (np.arange(a, e) / HOP) - 0.5
            out[:e - a] = np.interp(xs, np.arange(len(self.hops)), self.hops).astype(np.float32)
        return out


def narration_envelope(narr: np.ndarray) -> np.ndarray:
    """0..1 'how much the narrator is speaking', one value per sample (smoothed: fast attack, slow release)."""
    env = _NarrationEnvelope.from_array(narr)
    return env.samples(0, env.length)


class _MajorEnvelope:
    """1 while a major effect sounds, edges softened by a 0.3 s Hann window (the dip of the ambience under it).
    The smoothing of a sum of rectangles is read off the window's running sum, sample by sample."""

    def __init__(self, majors: List[Tuple[float, float]], n: int) -> None:
        spans = []
        for a, b in majors:
            s, e = min(n, int(max(0, a) * SR)), min(n, int(min(n / SR, b) * SR))
            if e > s:
                spans.append((s, e))
        merged: List[List[int]] = []
        for s, e in sorted(spans):
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        self.spans = merged
        self.k = int(0.15 * SR)
        kernel = np.hanning(2 * self.k + 1).astype(np.float32)
        w = (kernel / kernel.sum()).astype(np.float64)
        self.cum = np.concatenate([[0.0], np.cumsum(w)])

    def samples(self, a: int, b: int) -> np.ndarray:
        out = np.zeros(max(0, b - a), dtype=np.float64)
        k, cum = self.k, self.cum
        for s, e in self.spans:
            lo, hi = max(a, s - k), min(b, e + k)
            if hi <= lo:
                continue
            i = np.arange(lo, hi)
            m0 = np.maximum(s, i - k)
            m1 = np.minimum(e, i + k + 1)
            out[lo - a:hi - a] += cum[i + k - m0 + 1] - cum[i + k - m1 + 1]
        return np.clip(out, 0.0, 1.0).astype(np.float32)


def _major_envelope(majors: List[Tuple[float, float]], n: int) -> np.ndarray:
    return _MajorEnvelope(majors, n).samples(0, n)


def normalise(clip: np.ndarray, kind: str) -> np.ndarray:
    """Library files are recorded at very different levels; bring each to a known reference so that the vocabulary
    volumes mean the same thing for every file. Effects by peak, ambience by RMS (peaks capped at 0.9)."""
    if len(clip) == 0:
        return clip
    if kind == "ambience":
        rms = float(np.sqrt((clip ** 2).mean()))
        if rms < 1e-6:
            return clip
        out = clip * min(MAX_NORMALISE_GAIN, AMBIENCE_REF_RMS / rms)
        peak = float(np.abs(out).max())
        return out * (0.9 / peak) if peak > 0.9 else out
    peak = float(np.abs(clip).max())
    if peak < 1e-6:
        return clip
    return clip * min(MAX_NORMALISE_GAIN, SFX_REF_PEAK / peak)


def _fade(x: np.ndarray, fin: float, fout: float) -> np.ndarray:
    n = len(x)
    a, b = min(n, int(fin * SR)), min(n, int(fout * SR))
    if a > 0:
        x[:a] *= np.linspace(0.0, 1.0, a, dtype=np.float32)[:, None]
    if b > 0:
        x[n - b:] *= np.linspace(1.0, 0.0, b, dtype=np.float32)[:, None]
    return x


def _loop_fade(clip: np.ndarray) -> int:
    return int(min(LOOP_FADE_S, len(clip) / 4) * SR)


def _loop_window(clip: np.ndarray, length: int, w0: int, w1: int) -> np.ndarray:
    """Samples w0..w1 of the clip repeated to `length` samples, each join cross-faded so the loop has no click."""
    out = np.zeros((w1 - w0, 2), dtype=np.float32)
    n = len(clip)
    if n == 0:
        return out
    if n >= length:
        return clip[w0:w1].copy()
    x = _loop_fade(clip)
    step = n - x
    if x >= n:
        raise AudioMixError(f"an ambience file of {n / SR:.2f}s is too short to loop (it needs more than {LOOP_FADE_S:.0f}s)")
    up = np.linspace(0.0, 1.0, x, dtype=np.float32)[:, None]
    down = up[::-1]
    last = -(-(length - n) // step)  # the first repeat that reaches the end
    for k in range(max(0, (w0 - n) // step + 1), min(last, (w1 - 1) // step) + 1):
        pos = k * step
        s, e = max(w0, pos), min(w1, pos + n, length)
        if e <= s:
            continue
        seg = clip[s - pos:e - pos].copy()
        if k > 0 and x:
            h0, h1 = s - pos, min(e - pos, x)
            if h1 > h0:
                seg[:h1 - h0] *= up[h0:h1]
        if k < last and x:
            t0, t1 = max(s - pos, n - x), e - pos
            if t1 > t0:
                seg[t0 - (s - pos):] *= down[t0 - (n - x):t1 - (n - x)]
        out[s - w0:e - w0] += seg
    return out


def _loop(clip: np.ndarray, length: int) -> np.ndarray:
    """Repeat the clip to `length` samples, cross-fading each join so the loop has no click."""
    return _loop_window(clip, length, 0, length)


class _Bus:
    """Effects and ambience laid out on the timeline; render(a, b, ...) makes the ducked buses for samples a..b."""

    def __init__(self, plan: AudioPlan, n: int) -> None:
        self.n = n
        self.used: List[dict] = []
        cache: Dict[Tuple[str, str], np.ndarray] = {}
        shaped: Dict[str, np.ndarray] = {}

        def clip_for(sound: Sound, asset: ResolvedAsset) -> np.ndarray:
            key = (str(asset.path or asset.catalog_id), sound.filters)
            if key not in cache:
                raw = _synth.render(sound.synth) if asset.path is None else decode(asset.path, sound.filters)
                cache[key] = normalise(raw, sound.kind)
            return cache[key]

        hits: List[Tuple[int, int, np.ndarray]] = []
        for cue in plan.cues:
            for hit in expand(cue):
                asset = plan.assets.get(hit.sound)
                sound = sound_for(hit.sound)
                if asset is None or sound is None:
                    continue
                if hit.sound not in shaped:
                    clip = clip_for(sound, asset).copy()
                    if sound.max_s:
                        clip = clip[:int(sound.max_s * SR)]
                    shaped[hit.sound] = _fade(clip, sound.fade_in, sound.fade_out) * sound.volume
                clip = shaped[hit.sound]
                i = int(round(hit.t * SR))
                if i >= n:
                    continue
                hits.append((i, min(n, i + len(clip)), clip))
                self.used.append({"t": round(hit.t, 3), "sound": hit.sound, "asset": asset.catalog_id, "fidelity": asset.fidelity, "priority": hit.priority})
        self.hits = hits
        self._hit_i = np.array([h[0] for h in hits], dtype=np.int64)
        self._hit_j = np.array([h[1] for h in hits], dtype=np.int64)
        self.beds: List[Tuple[int, int, np.ndarray, Sound]] = []
        for bed in plan.beds:
            asset = plan.assets.get(bed.sound)
            sound = sound_for(bed.sound, "ambience")
            if asset is None or sound is None:
                continue
            i, j = int(bed.start * SR), min(n, int(bed.end * SR))
            if j - i < SR // 4:
                continue
            clip = clip_for(sound, asset)
            if 0 < len(clip) < j - i and _loop_fade(clip) >= len(clip):
                raise AudioMixError(f"the ambience file for {bed.sound} is too short to loop ({len(clip) / SR:.2f}s)")
            self.beds.append((i, j, clip, sound))
            self.used.append({"t": round(bed.start, 3), "end": round(bed.end, 3), "sound": bed.sound, "asset": asset.catalog_id, "fidelity": asset.fidelity, "priority": "ambience"})

    @staticmethod
    def _bed_window(clip: np.ndarray, length: int, w0: int, w1: int, sound: Sound) -> np.ndarray:
        seg = _loop_window(clip, length, w0, w1)
        a, b = min(length, int(sound.fade_in * SR)), min(length, int(sound.fade_out * SR))
        if a > 0 and w0 < a:
            e = min(w1, a)
            seg[:e - w0] *= np.linspace(0.0, 1.0, a, dtype=np.float32)[w0:e, None]
        if b > 0 and w1 > length - b:
            s = max(w0, length - b)
            seg[s - w0:] *= np.linspace(1.0, 0.0, b, dtype=np.float32)[s - (length - b):w1 - (length - b), None]
        return seg * sound.volume

    def render(self, a: int, b: int, env: np.ndarray, major_env: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        m = b - a
        sfx = np.zeros((m, 2), dtype=np.float32)
        amb = np.zeros((m, 2), dtype=np.float32)
        if len(self.hits):
            for h in np.nonzero((self._hit_i < b) & (self._hit_j > a))[0]:  # in cue order, as before
                i, j, clip = self.hits[h]
                s, e = max(i, a), min(j, b)
                sfx[s - a:e - a] += clip[s - i:e - i]
        for i, j, clip, sound in self.beds:
            s, e = max(i, a), min(j, b)
            if e > s:
                amb[s - a:e - a] += self._bed_window(clip, j - i, s - i, e - i, sound)
        sfx *= (1.0 - DUCK_SFX * env)[:, None]
        amb *= ((1.0 - DUCK_AMBIENCE * env) * (1.0 - DUCK_AMBIENCE_BY_MAJOR * major_env))[:, None]
        return sfx, amb


def build_bus(plan: AudioPlan, narr: np.ndarray, total_s: float) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    """Returns (sfx bus, ambience bus, used) both ducked and ready to add to the narration (whole length, in memory:
    for short audio and tests; mix_pakmap_audio streams)."""
    n = int(round(total_s * SR))
    bus = _Bus(plan, n)
    sfx, amb = bus.render(0, n, _NarrationEnvelope.from_array(narr).samples(0, n), _MajorEnvelope(plan.majors(), n).samples(0, n))
    return sfx, amb, bus.used


# ---- streaming the narration in and the mix out ------------------------------------------------------------------

class _Reader:
    """The narration decoded by ffmpeg (float32 stereo at SR) and read CHUNK samples at a time."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._err = tempfile.TemporaryFile()
        self._proc = subprocess.Popen([_ffmpeg(), "-v", "error", "-nostdin", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                                      stdout=subprocess.PIPE, stderr=self._err)

    def read(self, frames: int) -> np.ndarray:
        data = self._proc.stdout.read(frames * 8)
        return np.frombuffer(data, dtype=np.float32).reshape(-1, 2) if data else np.zeros((0, 2), dtype=np.float32)

    def close(self, *, check: bool = True) -> None:
        if self._err.closed:
            return
        if self._proc.poll() is None and not check:
            self._proc.kill()
        self._proc.stdout.close()
        rc = self._proc.wait()
        self._err.seek(0)
        err = self._err.read().decode(errors="replace")
        self._err.close()
        if check and rc != 0:
            raise AudioMixError(f"could not read audio {self.path}: {err[-300:]}")


class _Writer:
    """A float32 stereo WAV written by ffmpeg from blocks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._err = tempfile.TemporaryFile()
        self._proc = subprocess.Popen([_ffmpeg(), "-y", "-v", "error", "-nostdin", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_f32le", str(path)],
                                      stdin=subprocess.PIPE, stderr=self._err)

    def write(self, block: np.ndarray) -> None:
        try:
            self._proc.stdin.write(block.astype(np.float32, copy=False).tobytes())
        except (BrokenPipeError, OSError):
            self.close()
            raise AudioMixError("could not write the mixed audio: ffmpeg stopped") from None

    def close(self) -> None:
        if self._err.closed:
            return
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        rc = self._proc.wait()
        self._err.seek(0)
        err = self._err.read().decode(errors="replace")
        self._err.close()
        if rc != 0 or not self.path.is_file():
            raise AudioMixError(f"could not write the mixed audio: {err[-300:]}")


def _step_gains(base: np.ndarray, bed: np.ndarray) -> np.ndarray:
    """Per 10 ms step (HOP samples, the window starts on a step): the highest bed level in 0..1 for which no sample of the
    step goes past PEAK_LIMIT, or past the narration itself where the narration alone is already louder than that (there
    the bed may not add to it; the narration is never changed)."""
    limit = np.maximum(PEAK_LIMIT, np.abs(base))
    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.where(bed > 0, (limit - base) / bed, np.where(bed < 0, (-limit - base) / bed, 1.0))
    g = np.clip(g, 0.0, 1.0).min(axis=1)
    steps = -(-len(g) // HOP)
    pad = np.ones(steps * HOP, dtype=np.float32)
    pad[:len(g)] = g
    return pad.reshape(steps, HOP).min(axis=1)


def _clip_dip_curve(steps: np.ndarray) -> np.ndarray:
    """The bed's level per 10 ms step: never above what each step allows, ramping down over CLIP_DIP_ATTACK_S before a
    dip and back up over CLIP_DIP_RELEASE_S after it. The neighbour minimum first means that the per-sample line drawn
    between step centres (_curve_samples) also stays under every sample's own limit."""
    y = steps.astype(np.float64).copy()
    if len(y) > 1:
        y[1:] = np.minimum(y[1:], steps[:-1])
        y[:-1] = np.minimum(y[:-1], steps[1:])
    down = HOP / SR / CLIP_DIP_ATTACK_S
    up = HOP / SR / CLIP_DIP_RELEASE_S
    for j in range(len(y) - 2, -1, -1):  # ~100 values per second
        y[j] = min(y[j], y[j + 1] + down)
    for j in range(1, len(y)):
        y[j] = min(y[j], y[j - 1] + up)
    return y


def _curve_samples(curve: np.ndarray, a: int, b: int) -> np.ndarray:
    centres = np.arange(len(curve)) * HOP + (HOP - 1) / 2
    return np.interp(np.arange(a, b), centres, curve).astype(np.float32)


def mix_pakmap_audio(plan: AudioPlan, voiceover: "str | Path", out_path: "str | Path", *, duration: Optional[float] = None) -> MixResult:
    """Write narration + sound bed to out_path (a 32-bit float WAV). With nothing to add, the narration file itself is
    returned and nothing is re-encoded. Streams in CHUNK_S windows: memory does not grow with the length of the video."""
    voiceover = Path(voiceover)
    if not plan.enabled or (not plan.cues and not plan.beds):
        return MixResult(voiceover, False)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # pass 1: the narration envelope (and the narration's length)
    env = _NarrationEnvelope()
    reader = _Reader(voiceover)
    try:
        while True:
            block = reader.read(CHUNK)
            if not len(block):
                break
            env.feed(block)
    except BaseException:
        reader.close(check=False)
        raise
    reader.close()
    env.finish()
    narr_len = env.length
    total = max(narr_len / SR, duration or 0.0)
    n = int(round(total * SR))
    bus = _Bus(plan, n)
    major = _MajorEnvelope(plan.majors(), n)

    def write_mix(curve: Optional[np.ndarray], steps: Optional[List[np.ndarray]]) -> float:
        """curve None: the bed at full level (and `steps` collects what each 10 ms step allows); else the bed follows it."""
        reader = _Reader(voiceover)
        writer = _Writer(out_path)
        peak, ok = 0.0, False
        try:
            for a in range(0, n, CHUNK):
                b = min(n, a + CHUNK)
                base = np.zeros((b - a, 2), dtype=np.float32)
                if a < min(n, narr_len):
                    want = min(b, narr_len) - a
                    got = reader.read(want)
                    if len(got) != want:
                        raise AudioMixError(f"the narration {voiceover.name} changed while it was being mixed")
                    base[:want] = got
                sfx, amb = bus.render(a, b, env.samples(a, b), major.samples(a, b))
                bed = sfx + amb
                if steps is not None:
                    steps.append(_step_gains(base, bed))
                out = base + (bed if curve is None else bed * _curve_samples(curve, a, b)[:, None])
                peak = max(peak, float(np.abs(out).max()) if len(out) else 0.0)
                writer.write(out)
            ok = True
        finally:
            reader.close(check=False)
            if ok:
                writer.close()
            else:
                try:
                    writer.close()
                except AudioMixError:
                    pass
        return peak

    # pass 2: the mix at full bed level; most mixes never come near clipping and are done here
    steps: List[np.ndarray] = []
    peak = write_mix(None, steps)
    allowed = np.concatenate(steps) if steps else np.ones(0, dtype=np.float32)
    if not len(allowed) or float(allowed.min()) >= 1.0:
        return MixResult(out_path, True, peak, 1.0, bus.used, DUCK_SFX)
    # pass 3: the bed dips only where it would clip (the narration is never turned down)
    curve = _clip_dip_curve(allowed)
    peak = write_mix(curve, None)
    return MixResult(out_path, True, peak, float(curve.min()), bus.used, DUCK_SFX, clip_dip_s=float((curve < 0.999).sum()) * HOP / SR)
