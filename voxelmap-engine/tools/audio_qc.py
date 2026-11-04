"""Audio QC for a voxel map video. Prints one JSON report of measured values with pass/fail against stated thresholds.

    python3 tools/audio_qc.py mix.wav STEMS_DIR vo_timing.json timeline.json [video.mp4] [--out report.json]

STEMS_DIR holds music_ducked.wav + voice.wav from mix_audio.py --stems. Thresholds: LUFS -14 +-0.5, true peak <= -1.0 dBTP,
clarity >= 10 dB (voice RMS vs ducked-music RMS during speech), ducking depth >= 3 dB, music in every narration silence
>= 0.6 s above -50 dBFS, no stretch of the mix under -50 dBFS longer than 0.5 s, caption sync <= 40 ms, A/V duration gap <= 0.1 s.
When STEMS_DIR also holds sfx.wav (mix_audio.py --sfx...): voice must stay >= 10 dB above music+sfx during speech (overall and
per sentence), and sfx must be present (> -60 dBFS RMS) in every narration silence >= 0.6 s that follows the first bed start (the first beat's travelT1).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mix_audio import SR, decode, measure_ebur128  # noqa: E402

LUFS_TARGET, LUFS_TOL, TP_MAX = -14.0, 0.5, -1.0
CLARITY_MIN, DEPTH_MIN = 10.0, 3.0
SILENCE_MIN_S, DEAD_DB, DEAD_MIN_S = 0.6, -50.0, 0.5
SYNC_MAX_MS, AV_MAX_S = 40.0, 0.1
SFX_PRESENT_DB = -60.0


def rms_db(x: np.ndarray) -> float:
    return float(10 * np.log10(max(1e-12, float(np.mean(x.astype(np.float64) ** 2))))) if len(x) else float("-inf")


def seg_audio(x: np.ndarray, segs, sr: int = SR) -> np.ndarray:
    parts = [x[max(0, int(a * sr)): max(0, int(b * sr))] for a, b in segs if b > a]
    return np.concatenate(parts) if parts else x[:0]


def gaps(sentences, total: float, min_len: float = 0.0):
    """Narration silences: before the first sentence, between sentences, after the last, each >= min_len seconds."""
    edges, cur = [], 0.0
    for s in sorted(sentences, key=lambda s: s["start"]):
        if s["start"] - cur >= min_len:
            edges.append((cur, s["start"]))
        cur = max(cur, s["end"])
    if total - cur >= min_len:
        edges.append((cur, total))
    return edges


def quiet_runs(x: np.ndarray, thr_db: float = DEAD_DB, min_s: float = DEAD_MIN_S, win_s: float = 0.05, sr: int = SR):
    """Stretches where 50 ms-window RMS stays below thr_db for longer than min_s -> [(t0, t1)]."""
    hop = int(sr * win_s)
    n = len(x) // hop
    if n == 0:
        return []
    e = np.add.reduceat(x[: n * hop].astype(np.float64) ** 2, np.arange(0, n * hop, hop)) / hop
    low = 10 * np.log10(np.maximum(e, 1e-12)) < thr_db
    runs, i = [], 0
    while i < n:
        if low[i]:
            j = i
            while j < n and low[j]:
                j += 1
            if (j - i) * win_s > min_s:
                runs.append((round(i * win_s, 3), round(j * win_s, 3)))
            i = j
        else:
            i += 1
    return runs


def check(value, ok, threshold):
    return {"value": value, "pass": bool(ok), "threshold": threshold}


def stream_durations(mp4: str) -> dict:
    out = {}
    for kind, sel in (("video", "v:0"), ("audio", "a:0")):
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel, "-show_entries", "stream=duration", "-of", "csv=p=0", mp4], capture_output=True, text=True, timeout=120)
        try:
            out[kind] = float(r.stdout.strip().split()[0])
        except (ValueError, IndexError):
            out[kind] = None
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mix"); p.add_argument("stems"); p.add_argument("timing"); p.add_argument("timeline"); p.add_argument("video", nargs="?")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    sents = json.loads(Path(a.timing).read_text())["sentences"]
    tl = json.loads(Path(a.timeline).read_text())
    mix = decode(a.mix); voice = decode(str(Path(a.stems) / "voice.wav")); music = decode(str(Path(a.stems) / "music_ducked.wav"))
    total = len(mix) / SR
    rep = {"mix_seconds": round(total, 3)}

    m = measure_ebur128(a.mix)
    rep["loudness"] = check(round(m["I"], 2), abs(m["I"] - LUFS_TARGET) <= LUFS_TOL, "-14 +-0.5 LUFS")
    rep["true_peak"] = check(round(m["TP"], 2), m["TP"] <= TP_MAX, "<= -1.0 dBTP")

    speech = [(s["start"], s["end"]) for s in sents]
    per = []
    for s in sents:
        v = rms_db(seg_audio(voice, [(s["start"], s["end"])])); mu = rms_db(seg_audio(music, [(s["start"], s["end"])]))
        per.append(v - mu)
    overall = rms_db(seg_audio(voice, speech)) - rms_db(seg_audio(music, speech))
    w = int(np.argmin(per))
    rep["voice_clarity"] = {"overall_db": round(overall, 2), "worst_db": round(per[w], 2), "worst_sentence": w, "worst_text": sents[w]["text"],
                            "pass": bool(overall >= CLARITY_MIN and per[w] >= CLARITY_MIN), "threshold": ">= 10 dB (voice RMS - ducked music RMS during speech)"}

    sil = gaps(sents, total, SILENCE_MIN_S)
    music_speech = rms_db(seg_audio(music, speech))
    music_sil = rms_db(seg_audio(music, sil))
    depth = music_sil - music_speech
    rep["ducking_depth"] = check(round(depth, 2), depth >= DEPTH_MIN, ">= 3 dB (music in narration silences minus during speech)")
    rep["ducking_depth"].update(music_speech_db=round(music_speech, 2), music_silence_db=round(music_sil, 2))

    levels = [rms_db(seg_audio(music, [g])) for g in sil]
    dead = quiet_runs(mix)
    rep["silence_handling"] = {"silences_ge_0_6s": len(sil), "min_music_level_db": round(min(levels), 2) if levels else None,
                               "music_ok": bool(levels and min(levels) > DEAD_DB), "mix_dead_air_runs": dead,
                               "pass": bool(levels and min(levels) > DEAD_DB and not dead),
                               "threshold": "music > -50 dBFS in every silence >= 0.6 s; no mix stretch < -50 dBFS longer than 0.5 s"}

    sfx_path = Path(a.stems) / "sfx.wav"
    if sfx_path.exists():
        sfx = decode(str(sfx_path)); L = min(len(sfx), len(voice), len(music))
        both = (music[:L].astype(np.float64) ** 2 + sfx[:L].astype(np.float64) ** 2)  # power sum of music + sfx (uncorrelated)
        bg = np.sqrt(both).astype(np.float32)
        per2 = [rms_db(seg_audio(voice[:L], [(s["start"], s["end"])])) - rms_db(seg_audio(bg, [(s["start"], s["end"])])) for s in sents]
        ov2 = rms_db(seg_audio(voice[:L], speech)) - rms_db(seg_audio(bg, speech))
        w2 = int(np.argmin(per2))
        rep["sfx_clarity"] = {"overall_db": round(ov2, 2), "worst_db": round(per2[w2], 2), "worst_sentence": w2, "worst_text": sents[w2]["text"],
                              "voice_minus_sfx_only_db": round(rms_db(seg_audio(voice, speech)) - rms_db(seg_audio(sfx, speech)), 2),
                              "pass": bool(ov2 >= CLARITY_MIN and per2[w2] >= CLARITY_MIN), "threshold": ">= 10 dB (voice RMS - (music+sfx) RMS during speech)"}
        # beds start when the camera arrives (first beat's travelT1): judge only the silences from there on
        t_first = min((float(b["travelT1"]) for b in tl.get("beats", [])), default=0.0)
        sil_s = [(max(g0, t_first), g1) for g0, g1 in sil if g1 - max(g0, t_first) >= SILENCE_MIN_S]
        sl = [rms_db(seg_audio(sfx, [g])) for g in sil_s]
        sp_db = rms_db(seg_audio(sfx, speech)); si_db = rms_db(seg_audio(sfx, sil_s))
        rep["sfx_presence"] = {"silences_ge_0_6s": len(sil_s), "sfx_start_s": t_first, "min_sfx_level_db": round(min(sl), 2) if sl else None,
                               "sfx_speech_db": round(sp_db, 2), "sfx_silence_db": round(si_db, 2), "silence_minus_speech_db": round(si_db - sp_db, 2),
                               "pass": bool(sl and min(sl) > SFX_PRESENT_DB), "threshold": f"sfx RMS > {SFX_PRESENT_DB:g} dBFS in every silence >= 0.6 s"}

    caps = tl.get("captions", [])
    k = min(len(caps), len(sents))
    diffs = [abs(sents[i]["start"] - caps[i]["t0"]) * 1000 for i in range(k)]
    worst = max(diffs) if diffs else None
    sync = check(round(worst, 2) if worst is not None else None, worst is not None and worst <= SYNC_MAX_MS, "<= 40 ms max |vo start - caption t0|")
    sync["pairs"] = k
    if len(caps) != len(sents):
        sync["pass"] = False; sync["note"] = f"{len(sents)} sentences vs {len(caps)} captions"
    if a.video:
        d = stream_durations(a.video)
        gap = abs(d["audio"] - d["video"]) if d["audio"] is not None and d["video"] is not None else None
        sync["video"] = {**d, "gap_s": round(gap, 3) if gap is not None else None, "pass": bool(gap is not None and gap <= AV_MAX_S), "threshold": "|audio - video duration| <= 0.1 s"}
        sync["pass"] = bool(sync["pass"] and sync["video"]["pass"])
    rep["av_sync"] = sync

    keys = ["loudness", "true_peak", "voice_clarity", "ducking_depth", "silence_handling", "av_sync"] + [k for k in ("sfx_clarity", "sfx_presence") if k in rep]
    rep["all_pass"] = all(rep[k]["pass"] for k in keys)
    text = json.dumps(rep, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
