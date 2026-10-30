"""Honest QA for a rendered Story Motion film. It MEASURES and it SHOWS; it never says the film is good.

    rep = analyze(mp4, shots, out_dir, start=0, dur=180, voice="voiceover.wav")
    -> out_dir/report.json, out_dir/report.md, out_dir/sheet_joins_NN.png, out_dir/sheet_mid_NN.png

What is measured (all numbers are in the report, every flag names its threshold):
  audio   integrated loudness (LUFS), loudness range, true peak, 1 s short-term curve; with `voice` (the untouched narration): the fitted voice gain
          and lag inside the mix, the bed (everything that is not the voice) level while the voice speaks vs in its gaps = ducking depth, and the
          bed-to-voice ratio. A narration-only film shows "no bed detected".
  video   luma/colour per frame at 30 fps on 48x27 thumbnails: scene-change density vs the planned joins, joins that show no visible change, shots held
          too long (planned length and measured motion), grade drift between shots (white point + exposure, robust z-scores), luma flashes / dips at
          joins (and whether the plan asked for a flash/fade there), sustained dark dips anywhere, near-duplicate pictures within a few shots.
  sheets  contact sheets of the frames before|after every join and of the middle of every shot (strided when there are many), labelled with shot id,
          time, treatment and transition, for a person (or a model that can read images) to look at.
The report's "verdict" is always "not assessed": numbers can raise flags, only looking at the sheets can clear them."""
from __future__ import annotations

import json, math, os, re, subprocess, tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

THUMB_W, THUMB_H = 48, 27
FPS_ANALYSIS = 30
TH = {
    "hold_plan_s": 8.0,            # a shot planned longer than this is "long"
    "hold_motion": 0.35,           # median |frame diff| (0-255 grey, 48x27) below this inside a shot = visually static
    "hold_static_s": 4.0,          # ... and static for at least this long
    "join_min_change": 3.0,        # mean |grey diff| between 0.2 s before and 0.2 s after a join below this = no visible change
    "flash_luma": 0.08,            # luma excursion (0-1) at a join beyond both neighbours
    "flash_max_s": 0.4,
    "dip_ratio": 0.55,             # luma below this fraction of the +-2 s median for >= dip_min_frames
    "dip_min_frames": 3,
    "drift_z": 3.5,                # robust z of a shot's white point / exposure vs the film
    "dup_dist": 4.0,               # mean abs diff (0-255) of 24x14 grey thumbnails of two mid-shot frames
    "dup_window": 8,               # shots
    "duck_active_margin_db": 25.0, "duck_gap_margin_db": 40.0,
}


def _run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    try:
        from providers import hidden_subprocess
        return hidden_subprocess.run(cmd, **kw)
    except ImportError:
        return subprocess.run(cmd, **kw)


def probe(path: str) -> dict:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate,duration:format=duration", "-of", "json", path], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    return {"duration": float(d.get("format", {}).get("duration") or 0), "w": int(v.get("width") or 0), "h": int(v.get("height") or 0),
            "fps": float(num) / max(1.0, float(den)), "has_audio": a is not None}


def _f(x, d=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


# ------------------------------------------------------------------------------------------------ audio
def _decode_mono(path: str, start: float, dur: Optional[float], sr: int = 16000) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + ["-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    r = _run(cmd, capture_output=True)
    return np.frombuffer(r.stdout, dtype="<f4").copy()


def loudness(path: str, start: float, dur: Optional[float]) -> dict:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + ["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]
    r = _run(cmd, capture_output=True, text=True)
    tail = (r.stderr or "").split("Summary:")[-1]
    g = lambda rx: (lambda m: float(m[-1]) if m else None)(re.findall(rx, tail))
    return {"integrated_lufs": g(r"I:\s*(-?[\d.]+) LUFS"), "lra_lu": g(r"LRA:\s*(-?[\d.]+) LU"), "true_peak_dbfs": g(r"Peak:\s*(-?[\d.]+) dBFS")}


def level_curve(x: np.ndarray, sr: int, win_s: float = 1.0) -> List[float]:
    n = int(sr * win_s)
    return [round(float(10 * math.log10(max(1e-12, float(np.mean(x[i:i + n] ** 2))))), 2) for i in range(0, max(0, len(x) - n + 1), n)]


def _align(mix: np.ndarray, voice: np.ndarray, sr: int, max_lag_s: float = 1.0):
    """Lag (samples, + = mix is later) and LS gain of voice inside mix, from the loudest 20 s of the voice."""
    n = min(len(mix), len(voice))
    if n < sr * 4:
        return 0, 0.0
    hop = sr
    e = [float(np.sum(voice[i:i + 20 * sr] ** 2)) for i in range(0, max(1, n - 20 * sr), hop)] or [0.0]
    i0 = int(np.argmax(e)) * hop
    seg = slice(i0, min(n, i0 + 20 * sr))
    v, m = voice[seg], mix[seg]
    L = int(max_lag_s * sr)
    best, lag = -1e30, 0
    F = 1 << int(math.ceil(math.log2(len(v) + len(m) + 1)))
    cc = np.fft.irfft(np.fft.rfft(m, F) * np.conj(np.fft.rfft(v, F)), F)
    cands = np.concatenate([cc[:L + 1], cc[-L:]]) if L else cc[:1]
    idx = np.concatenate([np.arange(0, L + 1), np.arange(-L, 0)])
    lag = int(idx[int(np.argmax(cands))])
    return lag, 0.0


def audio_report(mix_path: str, start: float, dur: Optional[float], voice_path: Optional[str]) -> dict:
    out = {"loudness": loudness(mix_path, start, dur)}
    sr = 16000
    mix = _decode_mono(mix_path, start, dur, sr)
    out["short_term_rms_db_1s"] = level_curve(mix, sr)
    if not voice_path:
        return out
    voice = _decode_mono(voice_path, start, dur, sr)
    lag, _ = _align(mix, voice, sr)
    if lag > 0:
        mix_a, voice_a = mix[lag:], voice
    else:
        mix_a, voice_a = mix, voice[-lag:]
    n = min(len(mix_a), len(voice_a))
    mix_a, voice_a = mix_a[:n], voice_a[:n]
    den = float(np.dot(voice_a, voice_a)) or 1e-12
    gain = float(np.dot(mix_a, voice_a) / den)
    res = mix_a - gain * voice_a
    w = int(0.2 * sr)
    k = n // w
    vr = np.array([10 * math.log10(max(1e-12, float(np.mean(voice_a[i * w:(i + 1) * w] ** 2)))) for i in range(k)])
    rr = np.array([10 * math.log10(max(1e-12, float(np.mean(res[i * w:(i + 1) * w] ** 2)))) for i in range(k)])
    top = float(np.percentile(vr, 90)) if k else -90
    active = vr > top - TH["duck_active_margin_db"] + 10   # clearly speaking (within 15 dB of the loud speech)
    gap = vr < top - TH["duck_gap_margin_db"] + 8          # voice (almost) absent (> 32 dB under loud speech)
    # lag/gain sanity: how much of the mix is explained by the voice alone
    explained = 1.0 - float(np.dot(res, res)) / max(1e-12, float(np.dot(mix_a, mix_a)))
    bed_present = bool(rr.size and float(np.median(rr)) > -60.0)
    d = {"voice_lag_ms": round(1000.0 * lag / sr, 2), "voice_gain_in_mix": round(gain, 4), "voice_gain_db": round(20 * math.log10(max(1e-6, abs(gain))), 2),
         "mix_explained_by_voice": round(explained, 4), "bed_present": bed_present, "voice_windows": int(active.sum()), "gap_windows": int(gap.sum()),
         "bed_median_db_while_speaking": round(float(np.median(rr[active])), 2) if active.any() else None,
         "bed_median_db_in_gaps": round(float(np.median(rr[gap])), 2) if gap.any() else None,
         "bed_to_voice_db": round(float(np.median(rr[active] - vr[active])), 2) if active.any() else None}
    d["ducking_depth_db"] = round(d["bed_median_db_in_gaps"] - d["bed_median_db_while_speaking"], 2) if bed_present and d["bed_median_db_in_gaps"] is not None and d["bed_median_db_while_speaking"] is not None else None
    d["note"] = ("no bed detected: the film's audio is the narration alone" if not bed_present else
                 "ducking depth needs voice gaps; none found" if d["ducking_depth_db"] is None else "bed level measured as mix minus the fitted voice")
    out["voice_vs_mix"] = d
    return out


# ------------------------------------------------------------------------------------------------ video pass
def video_pass(path: str, start: float, dur: float) -> dict:
    """Stream the video once at 30 fps -> per-frame: mean rgb, white point rgb (p90), grey 16x9 thumbnail, diff to the previous frame."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", path, "-an", "-vf", f"fps={FPS_ANALYSIS},scale={THUMB_W}:{THUMB_H}:flags=area,format=rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    fs = THUMB_W * THUMB_H * 3
    rgb, wp, diff, grey = [], [], [], []
    prev = None
    while True:
        buf = p.stdout.read(fs * 300)
        if not buf:
            break
        n = len(buf) // fs
        a = np.frombuffer(buf[:n * fs], dtype=np.uint8).reshape(n, THUMB_H, THUMB_W, 3).astype(np.float32) / 255.0
        px = a.reshape(n, -1, 3)
        rgb.append(px.mean(1))
        wp.append(np.percentile(px, 90, axis=1))
        g = (a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)) * 255.0
        gg = np.concatenate([prev[None], g]) if prev is not None else np.concatenate([g[:1], g])
        diff.append(np.abs(gg[1:] - gg[:-1]).mean((1, 2)))
        prev = g[-1]
    p.stdout.close()
    try: p.wait(timeout=120)
    except subprocess.TimeoutExpired: p.kill()
    if not rgb:
        return {"n": 0}
    rgb, wp, diff = np.concatenate(rgb), np.concatenate(wp), np.concatenate(diff)
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return {"n": len(luma), "rgb": rgb, "wp": wp, "luma": luma, "diff": diff}


def _rz(v: np.ndarray) -> np.ndarray:
    med = np.median(v, 0)
    mad = np.median(np.abs(v - med), 0) * 1.4826 + 1e-4
    return (v - med) / mad


def video_report(vp: dict, shots: Sequence[dict], start: float, dur: float) -> dict:
    out: dict = {"frames": vp.get("n", 0)}
    if not vp.get("n"):
        return out
    fps = FPS_ANALYSIS
    N = vp["n"]
    luma, rgb, wp, diff = vp["luma"], vp["rgb"], vp["wp"], vp["diff"]
    sel = [s for s in shots if _f(s["end"]) > start and _f(s["start"]) < start + dur]
    joins = [s for s in sel if _f(s["start"]) > start + 0.05]
    minutes = max(1e-6, dur / 60.0)
    # ---- scene changes: measured vs planned
    thr = max(12.0, 6.0 * float(np.median(diff)))
    ch = np.where(diff > thr)[0]
    det = [int(c) for i, c in enumerate(ch) if i == 0 or c - ch[i - 1] > 3]
    out["scene_change"] = {"detected_hard_changes": len(det), "per_min": round(len(det) / minutes, 2), "planned_joins": len(joins), "planned_per_min": round(len(joins) / minutes, 2),
                           "threshold_grey_diff": round(thr, 1)}
    # ---- joins: visible change, flashes
    jr, flashes, invisible = [], [], []
    for s in joins:
        k = int(round((_f(s["start"]) - start) * fps))
        if k < 8 or k > N - 8:
            continue
        pre, post = luma[max(0, k - 12):k - 5], luma[k + 5:k + 13]
        a_pre, a_post = float(np.median(pre)), float(np.median(post))
        near = luma[k - 4:k + 5]
        up = float(near.max() - max(a_pre, a_post))
        dn = float(min(a_pre, a_post) - near.min())
        change = float(np.abs(rgb[k + 6] - rgb[k - 6]).mean() * 255.0)
        dmax = float(diff[max(0, k - 4):k + 5].max())
        row = {"shot_id": s.get("shot_id"), "t": round(_f(s["start"]), 2), "transition": s.get("transition_in"), "luma_up": round(up, 3), "luma_down": round(dn, 3),
               "max_frame_diff": round(dmax, 1), "colour_change": round(change, 2)}
        jr.append(row)
        if max(up, dn) > TH["flash_luma"]:
            flashes.append(dict(row, kind="flash" if up > dn else "dip", planned=s.get("transition_in") in ("flash", "fade", "dissolve", "soft")))
        if dmax < TH["join_min_change"] and change < 1.0:
            invisible.append(row)
    out["joins"] = {"count": len(jr), "luma_flashes_or_dips": flashes, "unplanned_flashes_or_dips": [f for f in flashes if not f["planned"]], "joins_with_no_visible_change": invisible,
                    "median_max_frame_diff": round(float(np.median([r["max_frame_diff"] for r in jr])), 1) if jr else None}
    # ---- shots: length, held too long, motion, grade
    rows = []
    for s in sel:
        a = max(0, int(round((_f(s["start"]) - start) * fps)) + 6)
        b = min(N, int(round((_f(s["end"]) - start) * fps)) - 6)
        if b - a < 6:
            continue
        mot = float(np.median(diff[a:b]))
        rows.append({"shot_id": s.get("shot_id"), "start": round(_f(s["start"]), 2), "dur": round(_f(s["end"]) - _f(s["start"]), 2), "treatment": s.get("treatment"),
                     "motion": round(mot, 3), "luma": float(np.median(luma[a:b])), "wp": [float(x) for x in np.median(wp[a:b], 0)], "rgb": [float(x) for x in np.median(rgb[a:b], 0)]})
    durs = np.array([r["dur"] for r in rows]) if rows else np.array([0.0])
    held = [{k: r[k] for k in ("shot_id", "start", "dur", "treatment", "motion")} for r in rows if r["dur"] >= TH["hold_static_s"] and r["motion"] < TH["hold_motion"]]
    long_plan = [{k: r[k] for k in ("shot_id", "start", "dur", "treatment", "motion")} for r in rows if r["dur"] > TH["hold_plan_s"]]
    out["shots"] = {"count": len(rows), "dur_mean": round(float(durs.mean()), 2), "dur_median": round(float(np.median(durs)), 2), "dur_p90": round(float(np.percentile(durs, 90)), 2),
                    "dur_max": round(float(durs.max()), 2), "planned_longer_than_%gs" % TH["hold_plan_s"]: long_plan, "visually_static_>=%gs" % TH["hold_static_s"]: held,
                    "motion_median": round(float(np.median([r["motion"] for r in rows])), 3) if rows else None}
    if len(rows) >= 6:
        L = np.array([r["luma"] for r in rows])
        W = np.array([r["wp"] for r in rows])
        zL, zW = _rz(L[:, None])[:, 0], _rz(W)
        adj = np.abs(np.diff(L))
        outl = [{"shot_id": rows[i]["shot_id"], "t": rows[i]["start"], "luma": round(float(L[i]), 3), "wp": [round(x, 3) for x in W[i]], "z_luma": round(float(zL[i]), 1),
                 "z_whitepoint": round(float(np.abs(zW[i]).max()), 1)} for i in range(len(rows)) if abs(zL[i]) > TH["drift_z"] or np.abs(zW[i]).max() > TH["drift_z"]]
        out["grade_drift"] = {"luma_median": round(float(np.median(L)), 3), "luma_mad": round(float(np.median(np.abs(L - np.median(L)))), 3),
                              "whitepoint_median": [round(float(x), 3) for x in np.median(W, 0)], "whitepoint_spread_p95_minus_p5": [round(float(np.percentile(W[:, c], 95) - np.percentile(W[:, c], 5)), 3) for c in range(3)],
                              "adjacent_luma_jump_median": round(float(np.median(adj)), 3), "adjacent_luma_jump_p95": round(float(np.percentile(adj, 95)), 3), "outlier_shots": outl}
    # ---- sustained dark dips anywhere
    dips, k = [], 0
    win = 2 * fps
    while k < N:
        lo, hi = max(0, k - win), min(N, k + win)
        if luma[k] < TH["dip_ratio"] * float(np.median(luma[lo:hi])):
            j = k
            while j < N and luma[j] < TH["dip_ratio"] * float(np.median(luma[max(0, j - win):min(N, j + win)])):
                j += 1
            if j - k >= TH["dip_min_frames"]:
                t = start + k / fps
                near = [s for s in sel if abs(_f(s["start"]) - t) < 0.7]
                dips.append({"t": round(t, 2), "frames": j - k, "min_luma": round(float(luma[k:j].min()), 3), "at_join": near[0].get("shot_id") if near else None,
                             "planned_transition": near[0].get("transition_in") if near else None})
            k = j + 1
        else:
            k += 1
    out["dark_dips"] = dips
    out["_rows"] = rows
    return out


# ------------------------------------------------------------------------------------------------ frames + sheets
def extract_frames(path: str, times: Sequence[float], start: float, w: int = 320, h: int = 180, fps: float = 30.0) -> Dict[float, np.ndarray]:
    """{time: HxWx3 uint8}. Frames are picked by number with `select`, in chunks of <= 24 frames (a long select expression overflows ffmpeg's parser)
    and each chunk seeks to its own start, so a 45-minute film costs only the decoded stretches."""
    idx = sorted({max(0, int(round((t - start) * fps))) for t in times})
    if not idx:
        return {}
    by_idx: Dict[int, np.ndarray] = {}
    fs = w * h * 3
    chunks, cur = [], []
    for i in idx:
        if cur and (len(cur) >= 24 or i - cur[0] > 40 * fps):
            chunks.append(cur); cur = []
        cur.append(i)
    if cur:
        chunks.append(cur)
    for ch in chunks:
        base = max(0, ch[0] - 15)
        expr = "+".join(f"eq(n\\,{i - base})" for i in ch)
        r = _run(["ffmpeg", "-v", "error", "-ss", f"{start + base / fps:.4f}", "-t", f"{(ch[-1] - base + 3) / fps:.4f}", "-i", path, "-an", "-vf",
                  f"fps={fps:g},select='{expr}',scale={w}:{h}:flags=bicubic,format=rgb24", "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True)
        n = len(r.stdout) // fs
        frames = np.frombuffer(r.stdout[:n * fs], dtype=np.uint8).reshape(n, h, w, 3)
        for k, i in enumerate(ch[:n]):
            by_idx[i] = frames[k]
    return {t: by_idx.get(max(0, int(round((t - start) * fps)))) for t in times}


def _label(im, text: str):
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, 13], fill=(0, 0, 0))
    d.text((3, 1), text, fill=(255, 255, 0))


def make_sheets(path: str, shots: Sequence[dict], start: float, dur: float, out_dir: Path, flagged: Sequence[str] = (), max_cells: int = 96) -> dict:
    from PIL import Image
    sel = [s for s in shots if _f(s["end"]) > start and _f(s["start"]) < start + dur]
    if len(sel) > max_cells:                                    # stride, but always keep the flagged shots
        stride = int(math.ceil(len(sel) / max_cells))
        sel = [s for i, s in enumerate(sel) if i % stride == 0 or str(s.get("shot_id")) in set(map(str, flagged))]
    cw, ch = 240, 135
    times = []
    for s in sel:
        a, b = max(_f(s["start"]), start), min(_f(s["end"]), start + dur)
        times += [(a + b) / 2, max(start, a - 0.12), min(start + dur - 0.05, a + 0.12)]
    fr = extract_frames(path, times, start, cw, ch)
    mid_tiles, join_tiles = [], []
    for s in sel:
        a, b = max(_f(s["start"]), start), min(_f(s["end"]), start + dur)
        tag = f"{s.get('shot_id')} {a:.1f}s {s.get('treatment', '')[:12]}"
        m = fr.get((a + b) / 2)
        if m is not None:
            im = Image.fromarray(m); _label(im, tag); mid_tiles.append(im)
        pre, post = fr.get(max(start, a - 0.12)), fr.get(min(start + dur - 0.05, a + 0.12))
        if pre is not None and post is not None and a > start + 0.05:
            pair = Image.new("RGB", (cw * 2 + 2, ch), (255, 0, 255))
            pair.paste(Image.fromarray(pre), (0, 0)); pair.paste(Image.fromarray(post), (cw + 2, 0))
            _label(pair, f"JOIN {s.get('shot_id')} {a:.1f}s <{s.get('transition_in')}>")
            join_tiles.append(pair)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {"mid": [], "joins": []}

    def pack(tiles, cols, per_sheet, prefix, key):
        for si in range(0, len(tiles), per_sheet):
            chunk = tiles[si:si + per_sheet]
            tw, th = chunk[0].size
            rows = int(math.ceil(len(chunk) / cols))
            sheet = Image.new("RGB", (cols * (tw + 4), rows * (th + 4)), (40, 40, 40))
            for i, t in enumerate(chunk):
                sheet.paste(t, ((i % cols) * (tw + 4), (i // cols) * (th + 4)))
            p = out_dir / f"{prefix}_{si // per_sheet + 1:02d}.png"
            sheet.save(p)
            files[key].append(str(p))
    pack(mid_tiles, 6, 36, "sheet_mid", "mid")
    pack(join_tiles, 3, 18, "sheet_joins", "joins")
    return {"files": files, "shots_shown": len(sel), "mid_frames": {f"{s.get('shot_id')}": m for s, m in zip(sel, [fr.get((max(_f(s['start']), start) + min(_f(s['end']), start + dur)) / 2) for s in sel])}}


def near_duplicates(mid_frames: Dict[str, np.ndarray], order: Sequence[str], window: int, thr: float) -> List[dict]:
    from PIL import Image
    th = {}
    for sid, fr in mid_frames.items():
        if fr is not None:
            th[sid] = np.asarray(Image.fromarray(fr).convert("L").resize((24, 14), Image.BILINEAR), dtype=np.float32)
    ids = [s for s in order if s in th]
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:i + 1 + window]:
            d = float(np.abs(th[a] - th[b]).mean())
            if d < thr:
                out.append({"a": a, "b": b, "distance": round(d, 2)})
    return out


# ------------------------------------------------------------------------------------------------ main
def analyze(mp4: str, shots: Sequence[dict], out_dir: str, start: float = 0.0, dur: Optional[float] = None, voice: Optional[str] = None, sheets: bool = True) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pr = probe(mp4)
    dur = min(float(dur) if dur else pr["duration"] - start, pr["duration"] - start)
    rep: dict = {"file": mp4, "window": {"start": start, "dur": round(dur, 2)}, "probe": pr,
                 "verdict": "NOT ASSESSED: numbers raise flags, only looking at the contact sheets can clear them. This tool never reports success."}
    rep["audio"] = audio_report(mp4, start, dur, voice) if pr["has_audio"] else {"error": "no audio stream"}
    vp = video_pass(mp4, start, dur)
    vr = video_report(vp, shots, start, dur)
    rows = vr.pop("_rows", [])
    rep["video"] = vr
    flagged = [str(f.get("shot_id")) for f in vr.get("joins", {}).get("unplanned_flashes_or_dips", [])] + [str(o["shot_id"]) for o in vr.get("grade_drift", {}).get("outlier_shots", [])]
    flagged += [str(h["shot_id"]) for h in vr.get("shots", {}).get("visually_static_>=%gs" % TH["hold_static_s"], [])]
    if sheets:
        sh = make_sheets(mp4, shots, start, dur, out, flagged)
        mids = sh.pop("mid_frames")
        sel_ids = [str(s.get("shot_id")) for s in shots if _f(s["end"]) > start and _f(s["start"]) < start + dur]
        rep["sheets"] = sh
        rep["video"]["near_duplicate_pictures"] = near_duplicates(mids, sel_ids, TH["dup_window"], TH["dup_dist"])
    rep["flags"] = flags_of(rep)
    rep["thresholds"] = TH
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=float), encoding="utf-8")
    (out / "report.md").write_text(to_markdown(rep), encoding="utf-8")
    return rep


def flags_of(rep: dict) -> List[str]:
    f = []
    a, v = rep.get("audio", {}), rep.get("video", {})
    lo = a.get("loudness", {})
    if lo.get("integrated_lufs") is not None and not (-20.5 <= lo["integrated_lufs"] <= -13.0):
        f.append(f"integrated loudness {lo['integrated_lufs']} LUFS outside -20.5..-13 (YouTube-style target about -14..-16 for a voice film)")
    if lo.get("true_peak_dbfs") is not None and lo["true_peak_dbfs"] > -1.0:
        f.append(f"true peak {lo['true_peak_dbfs']} dBFS above -1")
    vm = a.get("voice_vs_mix")
    if vm:
        if not vm["bed_present"]:
            f.append("audio is narration only: no music / ambience / effects detected")
        else:
            if abs(vm["voice_gain_db"]) > 0.5:
                f.append(f"voice level in the mix is {vm['voice_gain_db']} dB vs the original narration (should be about 0)")
            if vm["ducking_depth_db"] is not None and vm["ducking_depth_db"] < 4:
                f.append(f"ducking depth only {vm['ducking_depth_db']} dB")
            if vm["bed_to_voice_db"] is not None and vm["bed_to_voice_db"] > -14:
                f.append(f"bed only {vm['bed_to_voice_db']} dB under the voice while it speaks (want <= -14)")
    j = v.get("joins", {})
    if j.get("unplanned_flashes_or_dips"):
        f.append(f"{len(j['unplanned_flashes_or_dips'])} luma flashes/dips at joins the plan did not ask for")
    if j.get("joins_with_no_visible_change"):
        f.append(f"{len(j['joins_with_no_visible_change'])} joins show no visible change")
    s = v.get("shots", {})
    for k, val in s.items():
        if k.startswith("visually_static") and val:
            f.append(f"{len(val)} shots look static for >= {TH['hold_static_s']} s")
        if k.startswith("planned_longer") and val:
            f.append(f"{len(val)} shots planned longer than {TH['hold_plan_s']} s")
    if v.get("grade_drift", {}).get("outlier_shots"):
        f.append(f"{len(v['grade_drift']['outlier_shots'])} shots are grade outliers (|z|>{TH['drift_z']})")
    dips = v.get("dark_dips") or []
    if dips:
        black = [d for d in dips if d["min_luma"] < 0.1]
        soft_black = [d for d in black if d.get("planned_transition") in ("dissolve", "soft")]
        cut_black = [d for d in black if d.get("planned_transition") in ("cut", None)]
        f.append(f"{len(dips)} sustained dark dips ({len(black)} reach near-black, luma<0.1; {len(soft_black)} of those at joins planned as dissolve/soft; "
                 f"{len(cut_black)} at cuts or away from any join)")
    if v.get("near_duplicate_pictures"):
        f.append(f"{len(v['near_duplicate_pictures'])} near-duplicate picture pairs within {TH['dup_window']} shots")
    return f


def to_markdown(rep: dict) -> str:
    L = ["# Film QA (numbers + sheets; not a verdict)", "", f"**{rep['verdict']}**", "", f"- file: {rep['file']}", f"- window: {rep['window']}", "", "## Flags"]
    L += [f"- {x}" for x in rep["flags"]] or ["- none raised (this does NOT mean the film is fine)"]
    L += ["", "## Audio", "```", json.dumps({k: v for k, v in rep["audio"].items() if k != "short_term_rms_db_1s"}, indent=1), "```", "", "## Video", "```",
          json.dumps(rep["video"], indent=1, default=float)[:12000], "```", "", "## Sheets"]
    L += [f"- {p}" for k in ("joins", "mid") for p in rep.get("sheets", {}).get("files", {}).get(k, [])]
    return "\n".join(L)


if __name__ == "__main__":      # python -m story_fast.film_qa film.mp4 direct.json out_dir [--start S --dur D --voice narration.wav]
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("mp4"); ap.add_argument("direct"); ap.add_argument("out")
    ap.add_argument("--start", type=float, default=0.0); ap.add_argument("--dur", type=float, default=None); ap.add_argument("--voice", default=None)
    a = ap.parse_args()
    d = json.loads(Path(a.direct).read_text(encoding="utf-8")); d = d.get("data", d)
    r = analyze(a.mp4, d["shots"] if isinstance(d, dict) else d, a.out, a.start, a.dur, a.voice)
    print(json.dumps({"flags": r["flags"], "verdict": r["verdict"], "sheets": r.get("sheets", {}).get("files")}, indent=1))
