"""Frame, timing and audio checks on the spike renders. Reads the renders and the source clip; writes a JSON result and join-frame evidence
under <out_dir>. Nothing in the repository is touched.

usage: python3 -B -I analyze.py <work_root> <out_dir> <variant> [clip_seconds]
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

work_root, out_dir, variant = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
out_dir.mkdir(parents=True, exist_ok=True)
clip_s = {"A": 8.5, "B": 8.0, "C": 8.0}[variant]
video = work_root / f"variant_{variant}" / f"spike_{variant}.mp4"
clip = work_root / "media" / ("plain_8.0.mp4" if variant == "C" else f"board_{clip_s}.mp4")
voice = work_root / "media" / "voice.wav"
FPS, W, H = 30, 1920, 1080


def raw(path, vf, pix, size_bytes):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo", "-pix_fmt", pix, "-"], capture_output=True, check=True, timeout=1800)
    a = np.frombuffer(p.stdout, dtype=np.uint8)
    return a.reshape(-1, size_bytes)


n_frames = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(video)],
                              capture_output=True, text=True, timeout=1800).stdout.strip().strip(","))
# per-frame probes: interior grey, top border, left border, and the 16 code cells
p_int = raw(video, "crop=2:2:1700:300", "rgb24", 12)[:, :3]
p_top = raw(video, "crop=2:2:960:22", "rgb24", 12)[:, :3]
p_left = raw(video, "crop=2:2:3:540", "rgb24", 12)[:, :3]
code = raw(video, "crop=320:20:0:0,format=gray", "gray", 320 * 20).reshape(-1, 20, 320)
assert len(p_int) == n_frames, (len(p_int), n_frames)

map_ref = p_int[100].astype(int)           # a frame inside beat 1 (map)
BOARD = np.array([192, 192, 192])
kind, codes = [], []
for i in range(n_frames):
    pi, pt, pl = p_int[i].astype(int), p_top[i].astype(int), p_left[i].astype(int)
    cells = code[i][10, 10::20][:16]
    bimodal = bool(np.all((cells < 40) | (cells > 215)))
    val = int("".join("1" if c > 128 else "0" for c in cells), 2) if bimodal else None
    board_like = np.abs(pi - BOARD).max() <= 8 and pt[0] > 190 and pt[1] < 40 and pt[2] < 40 and pl[0] > 190 and pl[1] < 40
    map_like = np.abs(pi - map_ref).max() <= 12 and not (pt[0] > 190 and pt[1] < 40)
    if board_like and bimodal:
        kind.append("board"); codes.append(val)
    elif map_like:
        kind.append("map"); codes.append(None)
    else:
        kind.append("blend/other"); codes.append(None)

# segments of equal kind
segs, s = [], 0
for i in range(1, n_frames + 1):
    if i == n_frames or kind[i] != kind[s]:
        segs.append({"kind": kind[s], "first_frame": s, "last_frame": i - 1, "start_s": round(s / FPS, 4), "end_s": round(i / FPS, 4), "frames": i - s})
        s = i
res = {"variant": variant, "video": str(video), "clip": str(clip), "n_frames": n_frames, "segments": segs}

board_idx = [i for i in range(n_frames) if kind[i] == "board"]
if board_idx:
    b0, b1 = board_idx[0], board_idx[-1]
    seq = [codes[i] for i in board_idx]
    steps = sorted({seq[j + 1] - seq[j] for j in range(len(seq) - 1)})
    res["board"] = {"first_frame": b0, "last_frame": b1, "first_s": b0 / FPS, "last_end_s": (b1 + 1) / FPS, "frames": len(board_idx), "contiguous": (b1 - b0 + 1) == len(board_idx),
                    "first_code": seq[0], "last_code": seq[-1], "code_steps_seen": steps,
                    "codes_skipped_or_repeated": [(board_idx[j], seq[j], seq[j + 1]) for j in range(len(seq) - 1) if seq[j + 1] - seq[j] != 1][:10]}
bl = [i for i in range(n_frames) if kind[i] == "blend/other"]
res["blend_or_other_frames"] = {"count": len(bl), "frames": bl[:60]}
# any fade of the board border/interior inside the board run (a fade-to-black or fade-in would change these)
if board_idx:
    inner = [i for i in board_idx]
    res["board_run_pixel_stability"] = {"interior_rgb_min": p_int[inner].min(axis=0).tolist(), "interior_rgb_max": p_int[inner].max(axis=0).tolist(),
                                        "top_border_rgb_min": p_top[inner].min(axis=0).tolist(), "top_border_rgb_max": p_top[inner].max(axis=0).tolist()}


def frame_png(path, n):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", "-f", "image2pipe", "-c:v", "png", "-"],
                       capture_output=True, check=True, timeout=1800)
    import io
    return Image.open(io.BytesIO(p.stdout)).convert("RGB")


def border_box(im):
    a = np.asarray(im).astype(int)
    m = (a[:, :, 0] > 180) & (a[:, :, 1] < 60) & (a[:, :, 2] < 60)
    m[:21, :] = False   # the code row is not border
    ys, xs = np.where(m)
    return [int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())] if len(ys) else None


# placement and fidelity: compare rendered board frames with the source frame of the same code
checks = []
if board_idx:
    for i in sorted({board_idx[0], board_idx[0] + 1, board_idx[len(board_idx) // 2], board_idx[-1]}):
        cd = codes[i]
        r, sfr = frame_png(video, i), frame_png(clip, cd)
        d = np.abs(np.asarray(r).astype(int) - np.asarray(sfr).astype(int))
        checks.append({"video_frame": i, "video_time_s": i / FPS, "clip_frame": cd, "size": list(r.size), "mean_abs_diff_rgb": round(float(d.mean()), 3),
                       "p99_abs_diff": int(np.percentile(d, 99)), "max_abs_diff": int(d.max()), "border_box_rendered_[top,bottom,left,right]": border_box(r),
                       "border_box_source_[top,bottom,left,right]": border_box(sfr)})
res["placement_fidelity"] = checks

# evidence sheets: the frames around each transition
def sheet(frames, name):
    tw, th = 480, 270
    cols = 5
    rows = (len(frames) + cols - 1) // cols
    sh = Image.new("RGB", (cols * tw, rows * th), (0, 0, 0))
    d = ImageDraw.Draw(sh)
    for k, n in enumerate(frames):
        im = frame_png(video, n).resize((tw, th))
        x, y = (k % cols) * tw, (k // cols) * th
        sh.paste(im, (x, y))
        d.rectangle([x, y + th - 26, x + 250, y + th], fill=(0, 0, 0))
        d.text((x + 4, y + th - 22), f"frame {n}  t={n / FPS:.4f}s  {kind[n]}" + (f" code={codes[n]}" if codes[n] is not None else ""), fill=(255, 255, 0))
    sh.save(out_dir / name, quality=88)

trans = [i for i in range(1, n_frames) if kind[i] != kind[i - 1]]
res["transition_frames"] = trans
join_frames = []
for t in trans:
    join_frames += list(range(max(0, t - 2), min(n_frames, t + 3)))
join_frames = sorted(set(join_frames))[:30]
if join_frames:
    sheet(join_frames, f"joins_{variant}.jpg")

# audio: continuity and timing against the synthetic narration
def pcm(path):
    if str(path).endswith(".wav"):
        with wave.open(str(path)) as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float) / 32768, w.getframerate()
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"], capture_output=True, check=True, timeout=1800)
    return np.frombuffer(p.stdout, dtype=np.int16).astype(float) / 32768, 48000


def clicks(x, sr):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    Y = np.where((f > 1500) & (f < 2500), X, 0)
    env = np.abs(np.fft.irfft(Y, len(x)))
    w = int(0.004 * sr)
    env = np.convolve(env, np.ones(w) / w, mode="same")
    out = []
    for k in range(int(len(x) / sr)):
        a, b = int(k * sr), int((k + 0.2) * sr)
        out.append((a + int(np.argmax(env[a:b]))) / sr)
    return np.array(out)


def tone_rms(x, sr):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    y = np.fft.irfft(np.where((f > 250) & (f < 420), X, 0), len(x))
    w = int(0.02 * sr)
    return np.array([np.sqrt(np.mean(y[i:i + w] ** 2)) for i in range(0, len(y) - w, w)])


xo, sro = pcm(video)
xi, sri = pcm(voice)
co, ci = clicks(xo, sro), clicks(xi, sri)
n = min(len(co), len(ci))
off = (co[:n] - ci[:n]) * 1000
tr_o, tr_i = tone_rms(xo, sro), tone_rms(xi, sri)
skip = 8   # ignore the first 160 ms (encoder priming)
res["audio"] = {"duration_out_s": len(xo) / sro, "duration_in_s": len(xi) / sri, "clicks_found_out": int(len(co)), "clicks_found_in": int(len(ci)),
                "click_offset_ms_mean": round(float(off.mean()), 2), "click_offset_ms_std": round(float(off.std()), 2),
                "click_offset_ms_min": round(float(off.min()), 2), "click_offset_ms_max": round(float(off.max()), 2),
                "tone_rms_min_over_median_out": round(float(tr_o[skip:-skip].min() / np.median(tr_o)), 3),
                "tone_rms_min_over_median_in": round(float(tr_i[skip:-skip].min() / np.median(tr_i)), 3),
                "silent_windows_out_(<0.2x median)": int((tr_o[skip:-skip] < 0.2 * np.median(tr_o)).sum())}
(out_dir / f"analysis_{variant}.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
