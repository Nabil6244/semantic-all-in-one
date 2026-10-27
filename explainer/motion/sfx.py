"""Explainer sound layer (opt-in, standalone). Reads the pre-built assets in explainer/assets/sfx/ (built once by build_sfx.py, never during a render) and produces:

    events_from_report(report, fps)                       -> [{"t", "kind", ...}]   effect events from a director plan report
    build_sfx_track(report_or_events, total_duration, fps) -> wav path               sparse effects track, exactly total_duration long
    duck_bed_under_voice(bed, windows, ...)                -> ducked bed samples
    voice_windows_from_words(words)                        -> [(start, end)]
    mix_explainer_audio(voice, sfx_track, bed_wav, out)    -> out path (ffmpeg, time-limited) or None
    build_explainer_sound(report, words, total, ...)       -> one call that does all of it

Never stops a render: a missing or altered asset gives a silent track plus a note in `notes`. Designed from scratch (the reference's sound is unverified, see
docs/explainer/explainer_reference2_analysis.md); placement follows explainer.motion.presets: a stamp lands on frame 4 (0.133 s after its cue frame)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "sfx"
SR = 44100
GRID_FPS = 30
IMPACT_FRAME = 4
FFMPEG_TIMEOUT_S = 180

# kind -> (asset, level in dB relative to the asset's -6 dBFS peak, offset from the cue time in seconds, priority: lower wins when the density limit bites)
KINDS: Dict[str, Tuple[str, float, float, int]] = {
    "stamp": ("stamp_thump", 0.0, IMPACT_FRAME / GRID_FPS, 0),
    "reveal": ("reveal_riser", -4.0, 0.0, 1),            # onset = where the riser starts; it swells for 1.1 s
    "cross": ("cross_scratch", -3.0, 0.0, 2),
    "slide": ("slide_whoosh", -3.0, 0.0, 3),
    "pop": ("pop", -2.0, 0.0, 4),
    "rustle": ("paper_rustle", -5.0, 0.0, 5),
    "tick": ("count_tick", -6.0, 0.0, 6),
}
MAX_PER_WINDOW, WINDOW_S, SAME_KIND_GAP_S = 4, 2.0, 0.25
SFX_GAIN_DB = -9.0                     # the effects bus under speech (each effect leaves the assets at -6 dBFS peak, so about -15 dBFS peak in the track)
COUNT_TICKS = 8
BED_SPEECH_DB, BED_GAP_DB, ATTACK_S, RELEASE_S = -22.0, -16.0, 0.25, 0.6

_cache: Dict[str, Any] = {}


# ---------------------------------------------------------------- assets
def _manifest() -> Dict[str, Any]:
    if "man" not in _cache:
        try:
            _cache["man"] = json.loads((ASSETS / "manifest.json").read_text())
        except Exception:
            _cache["man"] = {}
    return _cache["man"]


def read_wav(path: Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError("only 16-bit WAV")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def load_asset(name: str, notes: Optional[List[str]] = None) -> Optional[Tuple[np.ndarray, int]]:
    """The asset as (samples, rate), or None with a note when missing or when its SHA-256 differs from the manifest."""
    fn = name if name.endswith(".wav") else name + ".wav"
    key = "a:" + fn
    if key in _cache:
        hit = _cache[key]
    else:
        hit = None
        p = ASSETS / fn
        try:
            want = _manifest().get("files", {}).get(fn, {}).get("sha256")
            raw = p.read_bytes()
            if not want or hashlib.sha256(raw).hexdigest() != want:
                raise ValueError("hash differs from manifest.json")
            hit = read_wav(p)
        except Exception as exc:
            hit = "%s: %s" % (fn, exc)
        _cache[key] = hit
    if isinstance(hit, str):
        if notes is not None and hit not in notes:
            notes.append("sound asset unavailable (" + hit + ")")
        return None
    return hit


def verify_assets() -> List[str]:
    """Problems with the shipped assets (empty = all present and matching their hashes)."""
    out: List[str] = []
    for fn in _manifest().get("files", {}):
        load_asset(fn, out)
    if not _manifest():
        out.append("manifest.json missing")
    return out


def _resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return x
    n = int(round(len(x) * sr_to / sr_from))
    return np.interp(np.arange(n) * (sr_from / sr_to), np.arange(len(x)), x)


# ---------------------------------------------------------------- events from a plan report
def _count_ticks(t0: float, frames: int, fps: float = GRID_FPS) -> List[float]:
    """Tick times of a count-up rolling for `frames` frames with an ease-out cubic: one tick each time the shown value has covered another 1/COUNT_TICKS of its way (dense at the start, slowing to the end)."""
    n = max(1, int(frames)) / float(GRID_FPS)
    return [t0 + n * (1.0 - (1.0 - k / COUNT_TICKS) ** (1.0 / 3.0)) for k in range(1, COUNT_TICKS)] + []


def _kind_for_cue(spec: Dict[str, Any]) -> List[str]:
    k = spec.get("kind")
    p = spec.get("params") or {}
    style = p.get("style") if isinstance(p, dict) else None
    out: List[str] = []
    if k == "visual":
        if style == "stamp":
            out.append("stamp")
        elif style == "plate":
            out.append("slide")
        elif style == "cross":
            out.append("cross")
        elif style in ("tile", "circle", "box", "lite", "tag", "figure", "crowd", "prop"):
            out.append("pop")
        elif style in ("scroll", "set"):
            out.append("rustle")
        if isinstance(p, dict) and p.get("count"):
            out.append("count")
    elif k in ("pop", "icon", "chip"):
        out.append("pop")
    elif k in ("card", "header"):
        out.append("rustle")
    elif k == "title":
        out.append("reveal")
    return out


def events_from_report(report: Dict[str, Any], fps: float = GRID_FPS) -> List[Dict[str, Any]]:
    """Walk report["beat_details"][beat]["cue_specs"] and ["layout"] (first_frame, clip-relative) with the beat starts in report["selection"]["beats"]. A cue with no first_frame is skipped.
    Returns events {"t": absolute seconds of the cue frame, "kind", "cue", ["frames"]}: the placement offset (stamp +4 frames) is applied by the track builder, not here."""
    starts = {b["id"]: float(b["start"]) for b in (report.get("selection", {}) or {}).get("beats", [])}
    ev: List[Dict[str, Any]] = []
    for bid, det in (report.get("beat_details") or {}).items():
        if bid not in starts or not isinstance(det, dict):
            continue
        ff = {r["cue"]: r.get("first_frame") for r in det.get("layout", []) or []}
        for spec in det.get("cue_specs", []) or []:
            f = ff.get(spec.get("id"))
            if f is None:
                f = spec.get("first_frame")
            if f is None:
                continue
            t = starts[bid] + float(f) / fps
            for kind in _kind_for_cue(spec):
                e = {"t": t, "kind": kind, "cue": spec.get("id"), "beat": bid}
                if kind == "count":
                    c = (spec.get("params") or {}).get("count")
                    e["frames"] = int(c.get("frames", 30)) if isinstance(c, dict) else 30
                ev.append(e)
    return sorted(ev, key=lambda e: (e["t"], str(e.get("cue"))))


# ---------------------------------------------------------------- the effects track
def select_events(events: Iterable[Dict[str, Any]], max_per_window: int = MAX_PER_WINDOW, window_s: float = WINDOW_S, same_kind_gap_s: float = SAME_KIND_GAP_S) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Expand count events into tick sequences, apply the density limits, return (kept, dropped). Each event gets "at" = the time its sound starts. A tick sequence counts as ONE effect
    for the window limit and the same-kind gap (its ticks keep their own rhythm). Limits: at most `max_per_window` effects start in any `window_s`, and never two of the same kind within
    `same_kind_gap_s`. When the limit bites, the higher-priority kind (stamp first) wins."""
    items: List[Dict[str, Any]] = []
    for e in events:
        k = e["kind"]
        if k == "count":
            at = float(e["t"])
            items.append({**e, "kind": "tick", "at": at, "seq": [at + 0.0] + _count_ticks(at, e.get("frames", 30))})
        elif k in KINDS:
            items.append({**e, "at": float(e["t"]) + KINDS[k][2]})
    order = sorted(items, key=lambda e: (KINDS[e["kind"]][3], e["at"]))
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for e in order:
        near = [x for x in kept if abs(x["at"] - e["at"]) < window_s]
        same = any(x["kind"] == e["kind"] and abs(x["at"] - e["at"]) < same_kind_gap_s for x in kept)
        # any window of length window_s containing e.at: check the densest one
        pts = sorted([x["at"] for x in near] + [e["at"]])
        dense = any(pts[i + max_per_window] - pts[i] < window_s - 1e-9 for i in range(len(pts) - max_per_window)) if len(pts) > max_per_window else False
        (dropped if (same or dense) else kept).append(e)
    kept.sort(key=lambda e: e["at"])
    return kept, dropped


def build_sfx_track(plan_report_or_events: Any, total_duration: float, fps: float = GRID_FPS, out: Optional[str] = None, *, notes: Optional[List[str]] = None, sr: int = SR,
                    sfx_gain_db: float = SFX_GAIN_DB) -> str:
    """Write a mono 16-bit WAV of exactly round(total_duration * sr) samples with every kept effect placed at its time and return its path. Accepts a director report (dict) or a list of
    events. Missing assets give silence in their place and a note in `notes`; this never raises for audio reasons."""
    notes = notes if notes is not None else []
    n = max(1, int(round(float(total_duration) * sr)))
    track = np.zeros(n)
    try:
        events = events_from_report(plan_report_or_events, fps) if isinstance(plan_report_or_events, dict) else list(plan_report_or_events or [])
        kept, dropped = select_events(events)
        if dropped:
            notes.append("sound: %d effect(s) dropped by the density limits (%s)" % (len(dropped), ", ".join(sorted({d['kind'] for d in dropped}))))
        gain0 = 10 ** (sfx_gain_db / 20.0)
        for e in kept:
            asset, level_db, _off, _pr = KINDS[e["kind"]]
            a = load_asset(asset, notes)
            if a is None:
                continue
            x = _resample(a[0], a[1], sr) * gain0 * 10 ** (level_db / 20.0)
            lead = int(np.argmax(np.abs(x))) if e["kind"] == "stamp" else 0       # the stamp's loudest sample (not the file's first) is what lands on the impact time
            for t in (e["seq"] if e["kind"] == "tick" else [e["at"]]):
                i = int(round(t * sr)) - lead
                if i >= n or i + len(x) <= 0:
                    continue
                lo = max(0, i)
                seg = x[lo - i:lo - i + (n - lo)]
                track[lo:lo + len(seg)] += seg
        peak = float(np.max(np.abs(track)))
        if peak > 0.8:                                           # overlapping effects: soft-limit so the sum can never clip
            track = np.tanh(track / 0.8) * 0.8
    except Exception as exc:                                     # never stop a render for sound
        notes.append("sound: the effects track could not be built (%r); it is silent" % (exc,))
        track = np.zeros(n)
    if out is None:
        fd = tempfile.NamedTemporaryFile(suffix="_sfx.wav", delete=False)
        fd.close()
        out = fd.name
    _write_wav(out, track, sr)
    return str(out)


def _write_wav(path: str, x: np.ndarray, sr: int) -> None:
    pcm = np.clip(np.round(x * 32767.0), -32767, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- bed and ducking
def voice_windows_from_words(words: Sequence[Sequence[Any]], gap_s: float = 0.35) -> List[Tuple[float, float]]:
    """Speech windows from word tuples (text, start, end): words closer than gap_s are one window."""
    out: List[List[float]] = []
    for w in sorted(words, key=lambda w: w[1]):
        s, e = float(w[1]), float(w[2])
        if out and s - out[-1][1] <= gap_s:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(a, b) for a, b in out]


def load_bed(mood: str = "neutral", notes: Optional[List[str]] = None) -> Optional[Tuple[np.ndarray, int]]:
    return load_asset("bed_%s" % mood, notes)


def duck_curve_db(windows: Sequence[Tuple[float, float]], total_s: float, rate: int = 200, speech_db: float = BED_SPEECH_DB, gap_db: float = BED_GAP_DB,
                  attack_s: float = ATTACK_S, release_s: float = RELEASE_S) -> np.ndarray:
    """Bed gain in dB at `rate` points per second: gap_db in silence, speech_db inside speech; falling takes attack_s and rising release_s (exponential, time constant = one third of
    that, so ~95% of the move is done in the stated time)."""
    n = int(round(total_s * rate)) + 1
    tgt = np.full(n, gap_db)
    for a, b in windows:
        tgt[max(0, int(a * rate)):min(n, int(np.ceil(b * rate)) + 1)] = speech_db
    out = np.empty(n)
    cur = gap_db
    ka, kr = 1 - np.exp(-3.0 / (attack_s * rate)), 1 - np.exp(-3.0 / (release_s * rate))
    for i in range(n):
        k = ka if tgt[i] < cur else kr
        cur += (tgt[i] - cur) * k
        out[i] = cur
    return out


def duck_bed_under_voice(bed: Any, voice_activity_windows: Sequence[Tuple[float, float]], total_duration: Optional[float] = None, *, sr: Optional[int] = None,
                         speech_db: float = BED_SPEECH_DB, gap_db: float = BED_GAP_DB, attack_s: float = ATTACK_S, release_s: float = RELEASE_S, loop: bool = True) -> Tuple[np.ndarray, int]:
    """Return (ducked samples, rate). `bed` is a (samples, rate) pair, a bed name ("neutral") or a WAV path; it is looped (it is built to loop) to total_duration. The bed asset is
    -18 dBFS RMS, so -22 dB under speech is about -40 dBFS and -16 dB in gaps about -34 dBFS."""
    if isinstance(bed, str):
        got = load_bed(bed) if bed in ("neutral", "tense", "warm") else read_wav(Path(bed))
        if got is None:
            raise ValueError("bed unavailable")
        bed = got
    x, bsr = bed
    sr = sr or bsr
    x = _resample(x, bsr, sr)
    total = float(total_duration if total_duration is not None else len(x) / sr)
    n = int(round(total * sr))
    if loop and len(x) > 0:
        x = np.tile(x, int(np.ceil(n / len(x))))[:n]
    else:
        x = np.pad(x[:n], (0, max(0, n - len(x))))
    rate = 200
    curve = duck_curve_db(voice_activity_windows, total, rate, speech_db, gap_db, attack_s, release_s)
    g = 10 ** (np.interp(np.arange(n) / sr, np.arange(len(curve)) / rate, curve) / 20.0)
    fade = min(int(1.0 * sr), n // 4)                           # a 1 s fade in at the start and out at the end (the loop point itself is seamless)
    env = np.ones(n)
    if fade:
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
    return x * g * env, sr


def mix_explainer_audio(voice_path: Optional[str], sfx_track: Optional[str], bed: Optional[str], out: str, total_duration: float, *, notes: Optional[List[str]] = None,
                        voice_gain_db: float = 0.0) -> Optional[str]:
    """Mix voice (may be None), effects track and the (already ducked) bed WAV into `out` (48 kHz stereo WAV, exactly total_duration) with one ffmpeg call limited to FFMPEG_TIMEOUT_S.
    Returns out, or None (with a note) when ffmpeg is missing, fails or times out: the caller then keeps its own audio."""
    notes = notes if notes is not None else []
    ins = [p for p in (voice_path, sfx_track, bed) if p]
    if not ins:
        return None
    gains = []
    if voice_path:
        gains.append(voice_gain_db)
    gains += [0.0] * (len(ins) - len(gains))
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin"]
    for p in ins:
        cmd += ["-i", str(p)]
    chains = ["[%d:a]aresample=48000,aformat=channel_layouts=stereo,volume=%gdB,apad,atrim=0:%.4f[a%d]" % (i, g, total_duration, i) for i, g in enumerate(gains)]
    fc = ";".join(chains) + ";" + "".join("[a%d]" % i for i in range(len(ins))) + "amix=inputs=%d:duration=longest:normalize=0,atrim=0:%.4f,alimiter=limit=0.95[m]" % (len(ins), total_duration)
    cmd += ["-filter_complex", fc, "-map", "[m]", "-ar", "48000", "-c:a", "pcm_s16le", str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
        if r.returncode != 0:
            notes.append("sound: the mix failed (%s)" % r.stderr.decode("utf-8", "replace")[-200:])
            return None
    except Exception as exc:
        notes.append("sound: the mix could not run (%r)" % (exc,))
        return None
    return str(out)


def build_explainer_sound(report: Dict[str, Any], words: Sequence[Sequence[Any]], total_duration: float, out: str, *, fps: float = GRID_FPS, mood: str = "neutral",
                          voice_path: Optional[str] = None, notes: Optional[List[str]] = None) -> Optional[str]:
    """Everything in one call: effects track + ducked bed (+ voice) -> `out`. Returns None (with notes) if nothing could be made."""
    notes = notes if notes is not None else []
    tmp = Path(tempfile.mkdtemp(prefix="expl_sound_"))
    sfx = build_sfx_track(report, total_duration, fps, str(tmp / "sfx.wav"), notes=notes)
    bed_path = None
    got = load_bed(mood, notes)
    if got is not None:
        x, sr = duck_bed_under_voice(got, voice_windows_from_words(words), total_duration)
        bed_path = str(tmp / "bed.wav")
        _write_wav(bed_path, x, sr)
    return mix_explainer_audio(voice_path, sfx, bed_path, out, total_duration, notes=notes)
