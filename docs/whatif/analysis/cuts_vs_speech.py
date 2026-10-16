"""Do the reference's cuts land in pauses or inside speech? Uses the per-50 ms RMS of the mixed audio: the 'bed' is the quiet floor (music
and ambience, 5th percentile); a frame within `margin` dB of the bed is a pause. Cut times come from ref<N>.json (measure_reference.py)."""
import json, subprocess, sys
import numpy as np
vid, j = sys.argv[1], sys.argv[2]
r = json.load(open(j))
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", vid, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
x = np.frombuffer(pcm, np.float32); hop = 800
n = len(x) // hop
rms = np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
db = 20 * np.log10(rms)
bed = np.percentile(db, 5); speech = np.percentile(db, 70)
# smooth over 100 ms, so a plosive gap inside a word is not a pause
sm = np.convolve(db, np.ones(3) / 3, mode="same")
pause = sm < bed + 7
# pause runs
runs, s = [], None
for i, p in enumerate(pause):
    if p and s is None: s = i
    if not p and s is not None:
        runs.append((s * 0.05, i * 0.05)); s = None
runs = [(a, b) for a, b in runs if b - a >= 0.2]
def at(t): return int(min(n - 1, max(0, t / 0.05)))
def in_pause(t): return bool(pause[at(t)]) or any(a - 0.1 <= t <= b + 0.1 for a, b in runs)
def frac(ts): return round(sum(in_pause(t) for t in ts) / max(1, len(ts)), 2)
# a random baseline: how often a RANDOM moment is in a pause
rng = np.random.default_rng(1); base = round(float(np.mean([in_pause(t) for t in rng.uniform(5, n * 0.05 - 5, 400)])), 2)
out = {"bed_db": round(float(bed), 1), "speech_db_p70": round(float(speech), 1), "bed_to_speech_db": round(float(speech - bed), 1),
       "pauses_ge_0.2s": {"n": len(runs), "median_len": round(float(np.median([b - a for a, b in runs])), 2) if runs else 0, "per_min": round(len(runs) / (n * 0.05) * 60, 1)},
       "hard_cuts_in_pause": frac(r["hard_cut_times"][1:]), "visual_changes_in_pause": frac(r["visual_change_times"][1:]), "baseline_random_in_pause": base}
print(json.dumps(out)); json.dump(out, open(j.replace(".json", "_cuts_vs_speech.json"), "w"))
