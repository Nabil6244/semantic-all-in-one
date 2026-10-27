"""Optional audio finishing: narration-first mix of a music bed (the app's bundled, credited tracks) with scene-aware level automation, speech ducking,
a few rationed accents from the app's bundled SFX library, a peak limiter and two-pass loudness normalisation. Everything is local and licensed with the app;
nothing is fetched or generated. If anything is missing the video keeps the plain narration (reported, never fatal)."""
from __future__ import annotations
import json, re, subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

from . import media

SR = 48000
ROOT = Path(__file__).resolve().parent.parent.parent

def _decode(path: str, channels: int, start: float = 0.0, dur: Optional[float] = None) -> np.ndarray:
    cmd = [media.ffmpeg(), "-v", "error", "-ss", f"{start:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + ["-i", str(path), "-f", "f32le", "-ac", str(channels), "-ar", str(SR), "-"]
    r = subprocess.run(cmd, capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.float32)
    return a.reshape(-1, channels) if channels > 1 else a

def _db(x: float) -> float: return 10 ** (x / 20.0)

def speech_duck(voice: np.ndarray, floor_db: float = -6.5, attack_ms: float = 40, release_ms: float = 380) -> np.ndarray:
    """Per-sample music gain that dips while the narrator speaks (fast attack, slower release so it swells in breaths)."""
    hop = int(SR * 0.01); n = len(voice) // hop; rms = np.sqrt(np.maximum(1e-12, np.add.reduceat(voice[: n * hop] ** 2, np.arange(0, n * hop, hop)) / hop)); thr = 0.07 * np.percentile(rms, 95)
    target = np.where(rms > thr, _db(floor_db), 1.0); g = np.empty(n); cur = 1.0; a = 1 - np.exp(-10.0 / attack_ms); r = 1 - np.exp(-10.0 / release_ms)
    for i in range(n):
        k = a if target[i] < cur else r; cur += (target[i] - cur) * k; g[i] = cur
    return np.interp(np.arange(len(voice)) / hop, np.arange(n) + 0.5, g).astype(np.float32)

def scene_levels(shots: List[dict], total: int, level_db: Dict[str, float]) -> np.ndarray:
    """Scene-aware music level in dB per sample: each shot's role sets a target, joined with 1.6 s eased ramps; fade-out over the last 4 s."""
    pts = [(0.0, level_db.get(shots[0]["role"], 0.0))]
    for s in shots: pts += [(s["t0"] + 0.8, level_db.get(s["role"], 0.0)), (s["t1"] - 0.8, level_db.get(s["role"], 0.0))]
    pts = sorted(pts); tt = np.arange(total) / SR; db = np.interp(tt, [p[0] for p in pts], [p[1] for p in pts])
    end = total / SR; fo = np.clip((end - tt) / 4.0, 0, 1); return db + 20 * np.log10(np.maximum(1e-4, fo * fo * (3 - 2 * fo)))

def _music_bed(text: str, seed: str, total_s: float, log) -> Tuple[Optional[np.ndarray], List[str]]:
    from starmap import music as SM
    stems = SM.choose(text, total_s, seed, mood="ambient")
    if not stems: return None, []
    N = int((total_s + 1) * SR); cross = int(5.0 * SR); out = np.zeros((0, 2), np.float32); used = []
    for s in stems:
        a = _decode(str(SM.music_dir() / f"{s}.opus"), 2)
        if a.size == 0: continue
        used.append(s)
        if len(out) == 0: out = a
        else:
            c = min(cross, len(a), len(out)); w = np.linspace(0, 1, c)[:, None]; w1, w2 = np.cos(w * np.pi / 2), np.sin(w * np.pi / 2)
            out = np.concatenate([out[:-c], out[-c:] * w1 + a[:c] * w2, a[c:]])
        if len(out) >= N: break
    if len(out) < N: out = np.tile(out, (N // max(1, len(out)) + 1, 1))
    out = out[:N]; rms = float(np.sqrt(np.mean(out ** 2))) or 1e-4; return (out / rms * _db(-24.0)).astype(np.float32), used

def _pick_sfx(kind: str) -> Optional[Path]:
    try:
        cat = json.loads((ROOT / "assets" / "bundled-sfx" / "catalog.json").read_text())
        rows = [e for e in cat.get("sfx", []) if e.get("category") == kind and 0.8 <= float(e.get("duration", 0)) <= 2.6 and e.get("channels", 2) in (1, 2)]
        rows.sort(key=lambda e: (-float(e.get("quality_score", 0) or 0), str(e.get("id"))))
        for e in rows:
            p = ROOT / "assets" / "bundled-sfx" / e["file"]
            if p.is_file(): return p
    except Exception: pass
    return None

def _loudnorm(src: Path, dst: Path, target: float = -16.0, tp: float = -1.5) -> dict:
    ff = media.ffmpeg(); r = subprocess.run([ff, "-hide_banner", "-i", str(src), "-af", f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S); j = json.loads(m.group(0)) if m else {}
    flt = f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={j.get('input_i')}:measured_TP={j.get('input_tp')}:measured_LRA={j.get('input_lra')}:measured_thresh={j.get('input_thresh')}:offset={j.get('target_offset')}:linear=true" if j else f"loudnorm=I={target}:TP={tp}"
    subprocess.run([ff, "-y", "-v", "error", "-i", str(src), "-af", flt, "-ar", str(SR), "-ac", "2", str(dst)], check=True); return j

def mix(voiceover: str, plan: dict, total_s: float, out_wav: Path, text: str, seed: str, music: bool = True, accents: bool = True, log=lambda m: None) -> dict:
    """-> report {music: [stems], credit, accents: [...], loudnorm: {...}, notes: [...]}. Writes a 48 kHz stereo wav of exactly total_s."""
    from . import director
    N = int(round(total_s * SR)); notes: List[str] = []; rep: Dict = {"music": [], "credit": "", "accents": [], "notes": notes}
    voice = _decode(voiceover, 1)[:N]; voice = np.pad(voice, (0, N - len(voice))); mixbuf = np.stack([voice, voice], 1) * 0.9
    if music:
        try:
            bed, stems = _music_bed(text, seed, total_s, log)
            if bed is None: notes.append("no bundled music tracks found: narration only")
            else:
                bed = bed[:N]; bed = np.pad(bed, ((0, N - len(bed)), (0, 0))); gain = _db(-2.0) * speech_duck(voice) * (10 ** (scene_levels(plan["shots"], N, director.LEVEL_DB) / 20.0)).astype(np.float32)
                fi = np.clip(np.arange(N) / (2.5 * SR), 0, 1); mixbuf += bed * (gain * fi)[:, None]; rep["music"] = stems
                from starmap import music as SM; rep["credit"] = " | ".join(SM.credit(s) for s in dict.fromkeys(stems))
        except Exception as exc: notes.append(f"music skipped: {type(exc).__name__}: {str(exc)[:120]}")
    if accents:
        for c in plan.get("cues", []):
            p = _pick_sfx("whoosh" if c["kind"] == "whoosh" else "impact")
            if not p: notes.append(f"no {c['kind']} sample available"); continue
            a = _decode(str(p), 2)
            if a.size == 0: continue
            a = a[: int(2.2 * SR)]; pk = float(np.max(np.abs(a))) or 1.0; a = a / pk * _db(c["db"]); fl = int(0.06 * SR); a[:fl] *= np.linspace(0, 1, fl)[:, None]; a[-int(0.25 * SR):] *= np.linspace(1, 0, int(0.25 * SR))[:, None]
            i0 = max(0, int(c["t"] * SR)); seg = a[: max(0, N - i0)]; mixbuf[i0:i0 + len(seg)] += seg; rep["accents"].append({"kind": c["kind"], "t": c["t"], "file": p.name, "peak_db": c["db"]})
    pk = float(np.max(np.abs(mixbuf)));
    if pk > 0.89: mixbuf *= 0.89 / pk; notes.append(f"peak protection reduced the mix by {20 * np.log10(0.89 / pk):.1f} dB before normalisation")
    tmp = out_wav.with_suffix(".raw.wav"); pcm = (np.clip(mixbuf, -1, 1) * 32767).astype("<i2")
    subprocess.run([media.ffmpeg(), "-y", "-v", "error", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-", str(tmp)], input=pcm.tobytes(), check=True)
    rep["loudnorm"] = _loudnorm(tmp, out_wav); tmp.unlink(missing_ok=True); return rep
