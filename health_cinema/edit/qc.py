"""Editorial QC. Plan checks run on the edit decision list before rendering; output checks run on the finished MP4. They find LIKELY defects with simple
measurements (repetition, reading speed, black frames, frame-to-frame jumps away from planned cuts, loudness/peaks, silent gaps). They do not judge
whether footage matches the narration or whether a medical visual is appropriate: those stay on the human review list."""
from __future__ import annotations
import re, subprocess
from typing import Dict, List
import numpy as np

from . import media, motion as M
from .transitions import Transition

HUMAN_REVIEW = ["Does each stock clip fit its line and avoid implying the person is a real patient? (not automated)",
                "Is every statistic's source, population and year attached before publishing? (flagged, not verified)",
                "Is each caption/graphic accurate to the narration and medically appropriate? (not automated)",
                "Overall pacing, taste and emotional fit of transitions and sound. (not automated)"]

QC_TIMEOUT_S = 900   # one full-video ffmpeg analysis pass; killed (and raised) past this


def plan_checks(plan: dict) -> List[dict]:
    out: List[dict] = []; shots, trans, phrases = plan["shots"], plan["transitions"], plan["phrases"]
    def add(code, sev, where, msg): out.append({"code": code, "severity": sev, "where": where, "message": msg})
    for a, b in zip(shots, shots[1:]):
        if a["kind"] == "footage" and b["kind"] == "footage" and a.get("camera", {}).get("move") == b.get("camera", {}).get("move") and a["scene_no"] != b["scene_no"]:
            add("repeated_camera_move", "note", f"scenes {a['scene_no']}->{b['scene_no']}", f"same camera move ({a['camera']['move']}) on consecutive shots")
        if a["kind"] == "footage" and b["kind"] == "footage" and a["scene_no"] == b["scene_no"] and a["src"] == b["src"]:
            da = a["t1"] - a["t0"]; za = M.camera_path(a["camera"]["move"], da, a["camera"]["amount"], tuple(a["camera"]["focus"]), 0.5)(da)[0] * a["camera"].get("base", 1.0); zb = M.camera_path(b["camera"]["move"], 1.0, b["camera"]["amount"], tuple(b["camera"]["focus"]), 0.5)(0.0)[0] * b["camera"].get("base", 1.0)
            if abs(za - zb) / max(za, zb) < 0.10: add("jump_cut_similar_framing", "review", f"scene {a['scene_no']}", f"split shots frame the subject within {abs(za - zb) / max(za, zb):.0%} of each other: reads as a jump cut")
    run = 0
    for k, t in enumerate(trans):
        run = run + 1 if t.name not in ("cut", "dissolve") else 0
        if run >= 3: add("transition_run", "review", f"shot {k + 1}", "three styled transitions in a row")
    for s in shots:
        d = s["t1"] - s["t0"]
        if s["kind"] == "statement" and d > 9 and len(s["gfx"]["beats"]) == 1: add("long_static", "review", f"scene {s['scene_no']}", f"one text beat held {d:.1f}s")
        if s["kind"] == "footage" and d > 8.5: add("long_static", "note", f"scene {s['scene_no']}", f"single footage shot {d:.1f}s")
        for o in s.get("overlays", []):
            if o["type"] in ("chip",) and o["t1"] - o["t0"] < 1.8: add("short_lived_text", "review", f"scene {s['scene_no']}", f"chip '{o['text']}' on screen {o['t1'] - o['t0']:.1f}s")
            if o["type"] == "title" and (o.get("t_out", d) - o["t0"]) < 1.5: add("short_lived_text", "review", f"scene {s['scene_no']}", f"title '{o['text']}' on screen {(o.get('t_out', d) - o['t0']):.1f}s")
        if s["kind"] in ("counter", "bar", "stat") and not s["gfx"].get("source_line"): add("figure_without_source", "review", f"scene {s['scene_no']}", "figure shown with a 'Source needed' label: attach the source before publishing")
        if s["kind"] == "anatomy" and not s.get("illustrative"): add("missing_disclaimer", "high", f"scene {s['scene_no']}", "3D scene without the illustration disclaimer")
    for p in phrases:
        d = p.t1 - p.t0; cps = len(p.text) / max(0.1, d)
        if d < 0.9: add("short_caption", "review", f"{p.t0:.1f}s", f"caption '{p.text[:30]}' lasts {d:.2f}s")
        if cps > 22: add("fast_caption", "review", f"{p.t0:.1f}s", f"caption reads at {cps:.0f} characters/second")
    for k, t in enumerate(trans):
        if t.frames <= 0: continue
        cut = shots[k + 1]["t0"]; w0, w1 = cut - t.frames / 48.0, cut + t.frames / 48.0
        for p in phrases:
            for i in p.emph:
                _, a, b = p.words[i]
                if a < w1 and b > w0: add("transition_over_key_word", "note", f"{cut:.1f}s", f"{t.name} overlaps the (estimated) timing of '{p.words[i][0]}'")
    return out

def output_checks(mp4: str, shots: List[dict], trans: List[Transition], total_frames: int) -> dict:
    ff = media.ffmpeg(); rep: Dict = {}
    r = subprocess.run([ff, "-hide_banner", "-i", mp4, "-vf", "blackdetect=d=0.06:pix_th=0.08", "-an", "-f", "null", "-"], capture_output=True, timeout=QC_TIMEOUT_S, text=True)
    rep["black_intervals"] = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)]
    r = subprocess.run([ff, "-v", "error", "-i", mp4, "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-"], capture_output=True, timeout=QC_TIMEOUT_S); a = np.frombuffer(r.stdout, np.uint8).reshape(-1, 36, 64).astype(np.float32)
    rep["frames_decoded"] = int(len(a)); d = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2)); lum = a.mean(axis=(1, 2))
    cuts = [round(s["t0"] * media.FPS) for s in shots[1:]]; hard = [c for c, t in zip(cuts, trans) if t.frames == 0]
    thr = max(10.0, float(np.median(d)) * 6); spikes = [int(i) + 1 for i in np.where(d > thr)[0]]
    windows = [(c - t.frames // 2 - 1, c + t.frames // 2 + 1) for c, t in zip(cuts, trans) if t.frames]
    panel = [(c, c + 14) for c, s in zip(cuts, shots[1:]) if s.get("layout") == "split"]   # the split-screen panel opening is an animated reveal
    unexplained = [s for s in spikes if not any(abs(s - c) <= 2 for c in hard) and not any(a <= s <= b for a, b in windows + panel)]
    rep["frame_jump_threshold"] = round(thr, 2); rep["jumps_at_planned_transitions"] = [s for s in spikes if s not in unexplained]; rep["unexplained_jumps"] = [{"frame": s, "t": round(s / media.FPS, 2), "delta": round(float(d[s - 1]), 1)} for s in unexplained]
    rep["median_frame_delta"] = round(float(np.median(d)), 2); rep["min_mean_luma"] = round(float(lum.min()), 1)
    fz = subprocess.run([ff, "-hide_banner", "-i", mp4, "-vf", "freezedetect=n=-55dB:d=2.5", "-an", "-f", "null", "-"], capture_output=True, timeout=QC_TIMEOUT_S, text=True)
    rep["frozen_intervals"] = [(float(x)) for x in re.findall(r"freeze_start: ([\d.]+)", fz.stderr)]
    au = subprocess.run([ff, "-hide_banner", "-i", mp4, "-vn", "-af", "ebur128=peak=true,silencedetect=noise=-60dB:d=0.4", "-f", "null", "-"], capture_output=True, timeout=QC_TIMEOUT_S, text=True).stderr
    m = re.search(r"Integrated loudness:\s+I:\s+(-?[\d.]+) LUFS.*?Loudness range:\s+LRA:\s+([\d.]+) LU.*?True peak:\s+Peak:\s+(-?[\d.]+) dBFS", au, re.S)
    rep["audio"] = {"integrated_lufs": float(m.group(1)), "lra": float(m.group(2)), "true_peak_dbfs": float(m.group(3))} if m else {}
    rep["audio_silent_gaps"] = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", au)]
    return rep
