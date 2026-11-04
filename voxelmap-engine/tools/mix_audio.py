"""Voice + music bed for a voxel map video: the music ducks under the voice and swells in the silences, and rises
steadily over the film (the reference's bed climbs ~6-7 dB from first chapter to last). Two-pass loudnorm to -14 LUFS.

    python3 tools/mix_audio.py voiceover.wav music.wav out/mix.wav [--duck -9] [--build 6] [--stems DIR]
                                [--sfx stem.wav | --sfx-plan plan.json | --timeline timeline.json]

The ducking is the app's own health_cinema.edit.audio.speech_duck (reused unchanged); only the build ramp is new.
Pass 1 measures, pass 2 applies loudnorm in linear mode with the measured values. If ffmpeg falls back to dynamic mode
or the result misses the target, a final gain correction (and an alimiter only when the peak needs it) lands the mix
within +-0.5 LU of -14 and at or below -1.0 dBTP.
--stems DIR writes music_ducked.wav and voice.wav (mono, 48 kHz, same length as the mix) with the final gain applied.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from health_cinema.edit.audio import SR, speech_duck  # noqa: E402

TARGET_I = -14.0
TARGET_TP = -1.5  # leaves room for AAC encoding, which lifts the true peak a few tenths (QC still checks <= -1.0)
TARGET_LRA = 11.0
I_TOL = 0.5
_FLOAT_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "output_i", "output_tp", "output_lra",
               "output_thresh", "normalization_type", "target_offset")


def decode(path: str) -> np.ndarray:
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True, timeout=1800).stdout
    return np.frombuffer(out, dtype=np.float32)


def build_ramp(n: int, build_db: float, music_db: float) -> np.ndarray:
    """Music gain per sample: starts `build_db` under its final level and climbs linearly in dB to it."""
    db = np.linspace(music_db - build_db, music_db, n, dtype=np.float32)
    return (10 ** (db / 20)).astype(np.float32)


def speech_rms(voice: np.ndarray) -> float:
    """RMS of the voice over its active 10 ms frames (frames above 7 % of the 95th-percentile frame RMS, like speech_duck)."""
    hop = SR // 100; k = len(voice) // hop
    f = np.sqrt(np.mean(voice[: k * hop].reshape(k, hop).astype(np.float64) ** 2, axis=1)) if k else np.zeros(1)
    act = f > 0.07 * np.percentile(f, 95)
    return float(np.sqrt(np.mean(f[act] ** 2))) if act.any() else 1e-4


def mix_parts(voice: np.ndarray, music: np.ndarray, duck_db: float = -9.0, build_db: float = 6.0, music_db: float = -8.0):
    """music_db is the bed's final level (before ducking) relative to the voice's speech RMS; the bed is first
    normalised to that reference, so a quiet or loud source file lands at the same place under the voice."""
    n = len(voice)
    if len(music) < n:
        music = np.resize(music, n)  # loop a short bed
    music = music[:n] * (speech_rms(voice) / max(1e-6, float(np.sqrt(np.mean(music[:n].astype(np.float64) ** 2)))))
    bed = (music[:n] * speech_duck(voice, floor_db=duck_db) * build_ramp(n, build_db, music_db)).astype(np.float32)
    return voice.astype(np.float32), bed


def mix(voice, music, duck_db: float = -9.0, build_db: float = 6.0, music_db: float = -8.0) -> np.ndarray:
    v, b = mix_parts(voice, music, duck_db, build_db, music_db)
    return v + b


# ---- pure helpers -------------------------------------------------------------------------------------------------

def parse_loudnorm_json(text: str) -> dict:
    """Last {...} block of ffmpeg's loudnorm print_format=json output -> dict of floats (normalization_type stays str)."""
    blocks = re.findall(r"\{[^{}]*\}", text, flags=re.S)
    if not blocks:
        raise ValueError("no loudnorm JSON in ffmpeg output")
    raw = json.loads(blocks[-1])
    out = {}
    for k, v in raw.items():
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            out[k] = v
    return out


def pass2_filter(m: dict, i=TARGET_I, tp=TARGET_TP, lra=TARGET_LRA) -> str:
    """Second-pass loudnorm filter string from pass-1 measurements (linear mode)."""
    return (f"loudnorm=I={i:g}:TP={tp:g}:LRA={lra:g}:measured_I={m['input_i']:.2f}:measured_TP={m['input_tp']:.2f}"
            f":measured_LRA={m['input_lra']:.2f}:measured_thresh={m['input_thresh']:.2f}:offset={m['target_offset']:.2f}:linear=true")


def correction_plan(i_meas: float, tp_meas: float, i=TARGET_I, tp=TARGET_TP, tol=I_TOL):
    """-> (gain_db, needs_limiter). Gain moves loudness to the target; a limiter is wanted only if the peak would still exceed tp."""
    if abs(i_meas - i) <= tol and tp_meas <= tp:
        return 0.0, False
    gain = i - i_meas
    return gain, (tp_meas + gain) > tp


def parse_ebur128(text: str) -> dict:
    """Summary block of ffmpeg ebur128=peak=true -> {'I': LUFS, 'LRA': LU, 'TP': dBTP}."""
    tail = text[text.rfind("Summary:"):] if "Summary:" in text else text
    mi = re.search(r"\bI:\s+(-?[\d.]+|-inf)\s+LUFS", tail)
    ml = re.search(r"\bLRA:\s+(-?[\d.]+)\s+LU\b", tail)
    mp = re.search(r"True peak:.*?Peak:\s+(-?[\d.]+|-inf)\s+dBFS", tail, flags=re.S)
    f = lambda x: float(x.group(1)) if x else None  # noqa: E731
    return {"I": f(mi), "LRA": f(ml), "TP": f(mp)}


def measure_ebur128(path: str) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, check=True, timeout=1800)
    return parse_ebur128(r.stderr)


def _ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-y"] + args, capture_output=True, text=True, check=True, timeout=1800)


def _write_wav(path: Path, mono: np.ndarray, channels: int = 2):
    raw = path.with_suffix(".raw.f32")
    raw.write_bytes(mono.astype(np.float32).tobytes())
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", str(raw),
                        "-ar", str(SR), "-ac", str(channels), "-c:a", "pcm_s16le", str(path)], check=True, timeout=1800)
    finally:
        raw.unlink(missing_ok=True)


def finalize(raw_wav: Path, out: Path, log=print) -> dict:
    """Two-pass loudnorm raw_wav -> out, then correct to target if needed. Returns the report dict."""
    p1 = _ff(["-i", str(raw_wav), "-af", f"loudnorm=I={TARGET_I:g}:TP={TARGET_TP:g}:LRA={TARGET_LRA:g}:print_format=json", "-f", "null", "-"])
    m = parse_loudnorm_json(p1.stderr)
    _ff(["-i", str(raw_wav), "-af", pass2_filter(m), "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(out)])
    got = measure_ebur128(str(out))
    rep = {"pass1": {k: m[k] for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}, "after_pass2": got, "correction_db": 0.0, "limiter": False}
    gain, lim = correction_plan(got["I"], got["TP"])
    if gain != 0.0 or lim:
        # ffmpeg fell back or missed: simple gain, then alimiter (ceiling just under the TP target, oversampled) only if needed.
        tmp = out.with_suffix(".pre.wav")
        out.replace(tmp)
        filt = f"volume={gain:.3f}dB"
        if lim:
            filt += f",alimiter=limit={10 ** ((TARGET_TP - 0.3) / 20):.4f}:attack=5:release=50:level=disabled"
        _ff(["-i", str(tmp), "-af", filt, "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(out)])
        got = measure_ebur128(str(out))
        # a limiter shaves loudness slightly: one trim pass if we drifted out of tolerance and the peak allows it
        if abs(got["I"] - TARGET_I) > I_TOL:
            g2 = TARGET_I - got["I"]
            if got["TP"] + g2 <= TARGET_TP:
                out.replace(tmp)
                _ff(["-i", str(tmp), "-af", f"volume={g2:.3f}dB", "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(out)])
                gain += g2
                got = measure_ebur128(str(out))
        tmp.unlink(missing_ok=True)
        rep.update(correction_db=round(gain, 3), limiter=lim)
    # a sample-peak limiter can leave inter-sample overs (loud impacts from the sfx stem): trim until the true peak fits
    for _ in range(3):
        if got["TP"] is None or got["TP"] <= TARGET_TP:
            break
        trim = TARGET_TP - got["TP"] - 0.2
        tmp = out.with_suffix(".pre.wav"); out.replace(tmp)
        _ff(["-i", str(tmp), "-af", f"volume={trim:.3f}dB", "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(out)])
        tmp.unlink(missing_ok=True)
        rep["correction_db"] = round(rep.get("correction_db", 0.0) + trim, 3)
        got = measure_ebur128(str(out))
    # if the trim pulled loudness out of tolerance, one more two-pass loudnorm in dynamic mode: its true-peak limiter holds
    # the ceiling while it brings the level back (used only when linear mode plus trims cannot satisfy both targets)
    if abs(got["I"] - TARGET_I) > I_TOL:
        tmp = out.with_suffix(".pre.wav"); out.replace(tmp)
        p1 = _ff(["-i", str(tmp), "-af", f"loudnorm=I={TARGET_I:g}:TP={TARGET_TP - 0.5:g}:LRA=20:print_format=json", "-f", "null", "-"])
        m2 = parse_loudnorm_json(p1.stderr)
        _ff(["-i", str(tmp), "-af", pass2_filter(m2, tp=TARGET_TP - 0.5, lra=20).replace(":linear=true", ":linear=false"), "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(out)])
        tmp.unlink(missing_ok=True)
        rep["dynamic_pass"] = True
        got = measure_ebur128(str(out))
    rep["final"] = got
    return rep


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("voice"); p.add_argument("music"); p.add_argument("out")
    p.add_argument("--duck", type=float, default=-9.0); p.add_argument("--build", type=float, default=6.0)
    p.add_argument("--stems", default=None, help="directory for music_ducked.wav + voice.wav (+ sfx.wav) QC stems")
    p.add_argument("--sfx", default=None, help="finished stereo sfx stem (from sfx_plan.py render), added at its own level")
    p.add_argument("--sfx-plan", default=None, help="sfx plan JSON (sfx_plan.py plan); rendered against the voice and added")
    p.add_argument("--timeline", default=None, help="timeline.json; with --sfx-plan absent, the plan is built from it")
    a = p.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    voice, bed = mix_parts(decode(a.voice), decode(a.music), a.duck, a.build)
    raw = out.with_suffix(".premix.wav")
    sfx = None  # (n, 2) float32 stem at final relative level, or None
    if a.sfx or a.sfx_plan or a.timeline:
        import sfx_plan as SP
        if a.sfx:
            sfx = SP.read_stereo(a.sfx)
        else:
            plan = json.loads(Path(a.sfx_plan).read_text()) if a.sfx_plan else SP.build_plan(json.loads(Path(a.timeline).read_text()))
            sfx = SP.render(plan, voice)
        sfx = np.pad(sfx[: len(voice)], ((0, max(0, len(voice) - len(sfx))), (0, 0)))
    # 32-bit float pre-mix so loudnorm sees the unclipped sum
    if sfx is None:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_f32le", str(raw)],
                       input=(voice + bed).astype(np.float32).tobytes(), check=True, timeout=1800)
    else:
        st = np.stack([voice + bed + sfx[:, 0], voice + bed + sfx[:, 1]], axis=1).astype(np.float32)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_f32le", str(raw)],
                       input=st.tobytes(), check=True, timeout=1800)
    try:
        rep = finalize(raw, out)
    finally:
        raw.unlink(missing_ok=True)
    if a.stems:
        sd = Path(a.stems); sd.mkdir(parents=True, exist_ok=True)
        fin = decode(str(out))  # mono downmix of the final mix
        n = min(len(fin), len(voice))
        ref = (voice + bed + (sfx.mean(axis=1) if sfx is not None else 0))[:n]
        g = float(np.dot(fin[:n], ref) / max(1e-12, np.dot(ref, ref)))  # overall linear gain loudnorm/correction applied
        full_v = np.zeros(len(fin), np.float32); full_b = np.zeros(len(fin), np.float32)
        full_v[:n] = voice[:n] * g; full_b[:n] = bed[:n] * g
        _write_wav(sd / "voice.wav", full_v, 1)
        _write_wav(sd / "music_ducked.wav", full_b, 1)
        if sfx is not None:
            full_s = np.zeros((len(fin), 2), np.float32); full_s[:n] = sfx[:n] * g
            SP.write_stereo(sd / "sfx.wav", full_s)
        rep["stem_gain_db"] = round(20 * np.log10(max(g, 1e-9)), 3)
    print(json.dumps({"event": "done", "out": str(out), **rep}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
