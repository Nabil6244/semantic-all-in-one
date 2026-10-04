"""Phase 7: turn an AudioPlan into one audio file = the narration (untouched) + the pakMap sound bed.

This is pakMap's own mixer; the generic mixers in smart_editing are not used or changed. Everything is deterministic
(no randomness, fixed filters, fixed envelope maths). Decoding goes through ffmpeg; the mixing itself is plain numpy.

Levels and ducking (priority: narration > major sfx > normal sfx > ambience):
  * effects sit at their vocabulary volume (all well below speech) and dip DUCK_SFX while the narrator speaks
  * ambience dips DUCK_AMBIENCE while the narrator speaks, and a further DUCK_AMBIENCE_BY_MAJOR under a major effect
  * the narration is never gain-changed; if the sum would clip, only the sound bed is turned down
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
    bus_scale: float = 1.0
    used: List[dict] = field(default_factory=list)
    narration_duck_depth: float = 0.0


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

def narration_envelope(narr: np.ndarray) -> np.ndarray:
    """0..1 'how much the narrator is speaking', one value per sample (smoothed: fast attack, slow release)."""
    mono = narr.mean(axis=1) if narr.ndim == 2 else narr
    n = len(mono)
    hops = max(1, -(-n // HOP))
    pad = np.zeros(hops * HOP, dtype=np.float32)
    pad[:n] = mono
    rms = np.sqrt((pad.reshape(hops, HOP) ** 2).mean(axis=1))
    target = np.clip(rms / SPEECH_RMS, 0.0, 1.0)
    a_att = 1.0 - np.exp(-HOP / SR / ATTACK_S)
    a_rel = 1.0 - np.exp(-HOP / SR / RELEASE_S)
    env = np.zeros(hops, dtype=np.float32)
    y = 0.0
    for i, x in enumerate(target):  # a loop over ~100 values per second, deterministic
        y += (a_att if x > y else a_rel) * (x - y)
        env[i] = y
    xs = (np.arange(n) / HOP) - 0.5
    return np.interp(xs, np.arange(hops), env).astype(np.float32)


def _major_envelope(majors: List[Tuple[float, float]], n: int) -> np.ndarray:
    env = np.zeros(n, dtype=np.float32)
    for a, b in majors:
        env[int(max(0, a) * SR):int(min(n / SR, b) * SR)] = 1.0
    if not majors:
        return env
    k = int(0.15 * SR)  # soften the edges so the dip is smooth
    kernel = np.hanning(2 * k + 1).astype(np.float32)
    return np.clip(np.convolve(env, kernel / kernel.sum(), mode="same"), 0.0, 1.0)


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


def _loop(clip: np.ndarray, length: int) -> np.ndarray:
    """Repeat the clip to `length` samples, cross-fading each join so the loop has no click."""
    if len(clip) == 0:
        return np.zeros((length, 2), dtype=np.float32)
    if len(clip) >= length:
        return clip[:length].copy()
    x = int(min(LOOP_FADE_S, len(clip) / 4) * SR)
    up = np.linspace(0.0, 1.0, x, dtype=np.float32)[:, None]
    out = np.zeros((length, 2), dtype=np.float32)
    pos, first = 0, True
    while pos < length:
        seg = clip.copy()
        if not first and x:
            seg[:x] *= up
        more = pos + len(seg) < length
        if more and x:
            seg[-x:] *= up[::-1]
        end = min(length, pos + len(seg))
        out[pos:end] += seg[:end - pos]
        pos = pos + len(seg) - x if more else length
        first = False
    return out


def build_bus(plan: AudioPlan, narr: np.ndarray, total_s: float) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    """Returns (sfx bus, ambience bus, used) both ducked and ready to add to the narration."""
    n = int(round(total_s * SR))
    env = narration_envelope(narr)
    env = np.pad(env, (0, max(0, n - len(env))))[:n]
    sfx = np.zeros((n, 2), dtype=np.float32)
    amb = np.zeros((n, 2), dtype=np.float32)
    used: List[dict] = []
    cache: Dict[Tuple[str, str], np.ndarray] = {}

    def clip_for(sound: Sound, asset: ResolvedAsset) -> np.ndarray:
        key = (str(asset.path or asset.catalog_id), sound.filters)
        if key not in cache:
            raw = _synth.render(sound.synth) if asset.path is None else decode(asset.path, sound.filters)
            cache[key] = normalise(raw, sound.kind)
        return cache[key]

    for cue in plan.cues:
        for hit in expand(cue):
            asset = plan.assets.get(hit.sound)
            sound = sound_for(hit.sound)
            if asset is None or sound is None:
                continue
            clip = clip_for(sound, asset).copy()
            if sound.max_s:
                clip = clip[:int(sound.max_s * SR)]
            clip = _fade(clip, sound.fade_in, sound.fade_out) * sound.volume
            i = int(round(hit.t * SR))
            if i >= n:
                continue
            j = min(n, i + len(clip))
            sfx[i:j] += clip[:j - i]
            used.append({"t": round(hit.t, 3), "sound": hit.sound, "asset": asset.catalog_id, "fidelity": asset.fidelity, "priority": hit.priority})
    for bed in plan.beds:
        asset = plan.assets.get(bed.sound)
        sound = sound_for(bed.sound, "ambience")
        if asset is None or sound is None:
            continue
        i, j = int(bed.start * SR), min(n, int(bed.end * SR))
        if j - i < SR // 4:
            continue
        seg = _fade(_loop(clip_for(sound, asset), j - i), sound.fade_in, sound.fade_out) * sound.volume
        amb[i:j] += seg
        used.append({"t": round(bed.start, 3), "end": round(bed.end, 3), "sound": bed.sound, "asset": asset.catalog_id, "fidelity": asset.fidelity, "priority": "ambience"})
    major_env = _major_envelope(plan.majors(), n)
    sfx *= (1.0 - DUCK_SFX * env)[:, None]
    amb *= ((1.0 - DUCK_AMBIENCE * env) * (1.0 - DUCK_AMBIENCE_BY_MAJOR * major_env))[:, None]
    return sfx, amb, used


def mix_pakmap_audio(plan: AudioPlan, voiceover: "str | Path", out_path: "str | Path", *, duration: Optional[float] = None) -> MixResult:
    """Write narration + sound bed to out_path (a 32-bit float WAV). With nothing to add, the narration file itself is
    returned and nothing is re-encoded."""
    voiceover = Path(voiceover)
    if not plan.enabled or (not plan.cues and not plan.beds):
        return MixResult(voiceover, False)
    narr = decode(voiceover)
    total = max(len(narr) / SR, duration or 0.0)
    n = int(round(total * SR))
    sfx, amb, used = build_bus(plan, narr, total)
    bus = sfx + amb
    base = np.zeros((n, 2), dtype=np.float32)
    base[:len(narr)] = narr[:n]
    scale = 1.0
    peak = float(np.abs(base + bus).max())
    if peak > PEAK_LIMIT:  # turn down the bed only, never the narration
        lo, hi = 0.0, 1.0
        for _ in range(14):
            mid = (lo + hi) / 2
            if float(np.abs(base + bus * mid).max()) <= PEAK_LIMIT:
                lo = mid
            else:
                hi = mid
        scale = lo
    out = base + bus * scale
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([_ffmpeg(), "-y", "-v", "error", "-nostdin", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_f32le", str(out_path)],
                          input=out.astype(np.float32).tobytes(), capture_output=True)
    if proc.returncode != 0 or not out_path.is_file():
        raise AudioMixError(f"could not write the mixed audio: {proc.stderr.decode(errors='replace')[-300:]}")
    return MixResult(out_path, True, float(np.abs(out).max()), scale, used, DUCK_SFX)
