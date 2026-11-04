"""Video QC: frozen frames, camera/scene jumps and black frames in a rendered mp4, checked against the plan's cut times.
    python3 tools/qc_video.py out/dday_final.mp4 out/dday.mp4.plan.json
Frames are decoded at 160x90; a 'jump' is a frame-to-frame change far above its neighbours that is not at a planned cut/transition."""
import json, subprocess, sys
import numpy as np


def main():
    video, plan_f = sys.argv[1], sys.argv[2]
    plan = json.load(open(plan_f)); fps = plan['fps']
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', video, '-vf', 'scale=160:90', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'], capture_output=True, timeout=1800).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2)); n = len(fr)
    planned = sorted({round(s['t0'] * fps) for s in plan['scenes']} | {round(sh['t0'] * fps) for s in plan['scenes'] for sh in s['shots']})
    trans = [(round(s['t0'] * fps), round((s['t0'] + s['transitionIn']['dur']) * fps)) for s in plan['scenes'] if s['transitionIn']['dur']]
    near_plan = lambda i: any(abs(i - p) <= 2 for p in planned) or any(a - 2 <= i <= b + 2 for a, b in trans)
    med = np.median(d) + 1e-3
    jumps = [(int(i), float(d[i])) for i in range(1, len(d) - 1) if d[i] > max(8.0, med * 8) and d[i] > 2.5 * max(d[i - 1], d[i + 1]) and not near_plan(i)]
    # frozen: >= 2.0 s where the change stays under 0.02 (the HUD's fades still move pixels)
    still = d < 0.02; frozen = []; run = 0
    for i, s in enumerate(still):
        run = run + 1 if s else 0
        if run == int(2.0 * fps): frozen.append(round((i - run + 1) / fps, 2))
    black = [round(i / fps, 2) for i in range(n) if fr[i].mean() < 3.0]
    black_runs = []
    for t in black:
        if not black_runs or t - black_runs[-1][1] > 1.5 / fps: black_runs.append([t, t])
        else: black_runs[-1][1] = t
    out = {'frames': n, 'fps': fps, 'median_frame_delta': round(float(med), 3), 'unplanned_jumps': jumps, 'frozen_from_s': frozen,
           'black_runs_s': [r for r in black_runs if r[1] - r[0] > 0.0], 'mean_delta': round(float(d.mean()), 3), 'max_delta': round(float(d.max()), 2)}
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
