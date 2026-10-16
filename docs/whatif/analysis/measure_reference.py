"""Measures the three reference videos (read-only): shot lengths by class, audio loudness, silences, ducking depth and the timing of
transient 'sound effect' events against visual changes. Usage: python3 measure_reference.py <video.mp4> <out.json>
Cut times come from ffmpeg scene detection (threshold 0.12 = hard cuts, 0.025 at 6 fps = any visual change)."""
import json, subprocess, sys, re
import numpy as np
from PIL import Image
import io

vid, out = sys.argv[1], sys.argv[2]

def run(cmd):
    return subprocess.run(cmd, capture_output=True)

dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", vid]).stdout)

def times(vf):
    r = run(["ffmpeg", "-v", "info", "-i", vid, "-vf", vf + ",showinfo", "-f", "null", "-"])
    return [float(x) for x in re.findall(r"pts_time:([0-9.]+)", r.stderr.decode(errors="ignore"))]

hard = [0.0] + times("scale=320:-1,select='gt(scene,0.12)'")
hard = [t for i, t in enumerate(hard) if i == 0 or t - hard[i - 1] > 0.3]
change = [0.0] + times("fps=6,scale=160:-1,select='gt(scene,0.025)'")
ch = [change[0]]
for t in change[1:]:
    if t - ch[-1] > 1.0:
        ch.append(t)

# classify every shot by its middle frame: a diagram plate is dark and unsaturated; a picture is lit or coloured
def frame_at(t):
    r = run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", vid, "-frames:v", "1", "-vf", "scale=160:90", "-f", "image2pipe", "-vcodec", "png", "-"])
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")
shots = []
bounds = hard + [dur]
for a, b in zip(bounds, bounds[1:]):
    im = np.asarray(frame_at((a + b) / 2), dtype=float) / 255
    lum = im.mean()
    sat = (im.max(2) - im.min(2)).mean()
    cls = "plate" if lum < 0.16 and sat < 0.12 else "picture"
    shots.append({"t0": round(a, 2), "t1": round(b, 2), "len": round(b - a, 2), "lum": round(float(lum), 3), "sat": round(float(sat), 3), "class": cls})

def dist(xs):
    if not xs: return {}
    xs = sorted(xs)
    q = lambda p: round(xs[min(len(xs) - 1, int(p * len(xs)))], 2)
    return {"n": len(xs), "mean": round(sum(xs) / len(xs), 2), "p10": q(.1), "p25": q(.25), "median": q(.5), "p75": q(.75), "p90": q(.9), "max": round(max(xs), 2)}

# audio
pcm = run(["ffmpeg", "-v", "error", "-i", vid, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]).stdout
x = np.frombuffer(pcm, np.float32)
loud = run(["ffmpeg", "-v", "info", "-i", vid, "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr.decode(errors="ignore")
summ = loud[loud.rfind("Summary:"):]
lufs = float(re.search(r"I:\s+(-?[0-9.]+) LUFS", summ).group(1)); lra = float(re.search(r"LRA:\s+([0-9.]+) LU", summ).group(1))
peak = float(re.search(r"Peak:\s+(-?[0-9.]+) dBFS", summ).group(1))
sil = run(["ffmpeg", "-v", "info", "-i", vid, "-af", "silencedetect=noise=-55dB:d=0.4", "-f", "null", "-"]).stderr.decode(errors="ignore")
silences = list(zip([float(v) for v in re.findall(r"silence_start: ([0-9.]+)", sil)], [float(v) for v in re.findall(r"silence_end: ([0-9.]+)", sil)]))

hop, n = 800, 1024            # 50 ms hop at 16 kHz
win = np.hanning(n)
frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * win
spec = np.abs(np.fft.rfft(frames, axis=1))
fr = np.fft.rfftfreq(n, 1 / 16000)
band = lambda lo, hi: spec[:, (fr >= lo) & (fr < hi)].sum(1)
low, voice, high = band(20, 120), band(200, 3000), band(3000, 8000)
db = lambda v: 20 * np.log10(v + 1e-9)
rms = np.sqrt((frames ** 2).mean(1) + 1e-12)
# speech frames: voice band energy far above its own 10th percentile; gaps are the rest
v = db(voice)
speech = v > np.percentile(v, 10) + 22
music_in_gaps = float(np.median(db(rms)[~speech])) if (~speech).any() else None
speech_level = float(np.median(db(rms)[speech])) if speech.any() else None
# transient events: a sudden rise in the 3-8 kHz band (clicks, whooshes' attack) that is NOT sustained speech sibilance
flux = np.maximum(0, np.diff(db(high), prepend=db(high)[0]))
thr = np.median(flux) + 6 * (np.median(np.abs(flux - np.median(flux))) + 1e-6)
ev = [i * hop / 16000 for i in range(1, len(flux) - 1) if flux[i] > max(thr, 9) and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
ev2 = []
for t in ev:
    if not ev2 or t - ev2[-1] > 0.3: ev2.append(t)
lowflux = np.maximum(0, np.diff(db(low), prepend=db(low)[0]))
lthr = np.median(lowflux) + 6 * (np.median(np.abs(lowflux - np.median(lowflux))) + 1e-6)
thuds = [i * hop / 16000 for i in range(1, len(lowflux) - 1) if lowflux[i] > max(lthr, 10) and lowflux[i] >= lowflux[i - 1] and lowflux[i] >= lowflux[i + 1]]
th2 = []
for t in thuds:
    if not th2 or t - th2[-1] > 0.5: th2.append(t)

def near(ts, refs, w=0.25):
    return round(sum(any(0 <= e - r <= w for e in ts) for r in refs) / max(1, len(refs)), 2)

res = {"video": vid.split("/")[-1], "duration": round(dur, 1),
       "hard_cuts": {"n": len(hard), "per_min": round(len(hard) / dur * 60, 1), "shot_len": dist([s["len"] for s in shots])},
       "by_class": {c: dist([s["len"] for s in shots if s["class"] == c]) | {"share_of_runtime": round(sum(s["len"] for s in shots if s["class"] == c) / dur, 2)} for c in ("plate", "picture")},
       "visual_changes": {"n": len(ch), "per_min": round(len(ch) / dur * 60, 1), "gap": dist([b - a for a, b in zip(ch, ch[1:])])},
       "audio": {"integrated_lufs": lufs, "lra_lu": lra, "true_peak_dbfs": peak, "silences_over_0.4s": [(round(a, 1), round(b, 1)) for a, b in silences][:40],
                 "n_silences": len(silences), "speech_frame_share": round(float(speech.mean()), 2), "level_in_speech_db": round(speech_level, 1) if speech_level is not None else None,
                 "level_in_gaps_db": round(music_in_gaps, 1) if music_in_gaps is not None else None,
                 "duck_depth_db": round(speech_level - music_in_gaps, 1) if None not in (speech_level, music_in_gaps) else None,
                 "high_transients": {"n": len(ev2), "per_min": round(len(ev2) / dur * 60, 1), "within_250ms_after_a_visual_change": near(ev2, ch), "within_250ms_after_a_hard_cut": near(ev2, hard)},
                 "low_thuds": {"n": len(th2), "per_min": round(len(th2) / dur * 60, 1), "times_first_20": [round(t, 1) for t in th2[:20]]}},
       "hard_cut_times": [round(t, 2) for t in hard], "visual_change_times": [round(t, 2) for t in ch], "shots": shots}
json.dump(res, open(out, "w"))
print(json.dumps({k: v for k, v in res.items() if k not in ("hard_cut_times", "visual_change_times", "shots")}, indent=1)[:3500])
