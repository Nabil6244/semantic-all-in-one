"""Decode a finished journey clip and check it: size, frame count, blank frames, temporal pop detection (frame-to-frame change spikes against a
local median), and label presence against frames.json. Usage: validate_video.py MP4 FRAMES_JSON [WORKDIR]"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

def run(mp4, frames_json, work=None):
    work = Path(work or tempfile.mkdtemp()); shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True)
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=width,height,nb_read_frames,r_frame_rate", "-of", "json", str(mp4)], capture_output=True, text=True)
    st = json.loads(pr.stdout)["streams"][0]
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), str(work / "f%05d.png")], check=True)
    fr = json.load(open(frames_json))["frames"]; files = sorted(work.glob("f*.png")); prev = None; diffs = []; blank = []; lab_ok = lab_bad = 0
    for k, p in enumerate(files):
        im = Image.open(p).convert("RGB"); a = np.asarray(im.convert("L").resize((480, 270))).astype(np.int16)
        diffs.append(0.0 if prev is None else float(np.abs(a - prev).mean())); prev = a
        if a.std() < 2: blank.append(k)
        arr = np.asarray(im); cyan = int(((np.abs(arr[:, :, 0].astype(int) - 120) < 50) & (np.abs(arr[:, :, 1].astype(int) - 200) < 50) & (arr[:, :, 2] > 200)).sum())
        want = bool(fr[k]["labels"]) and min(l["a"] for l in fr[k]["labels"]) > 0.9
        if want: lab_ok += cyan > 10; lab_bad += cyan <= 10
        elif not fr[k]["labels"] and cyan > 400: lab_bad += 1
    x = np.array(diffs); med = float(np.median(x[1:])); dd = np.abs(np.diff(x))
    shutil.rmtree(work, ignore_errors=True)
    return {"size": f'{st["width"]}x{st["height"]}', "fps": st["r_frame_rate"], "frames_decoded": len(files), "frames_expected": len(fr), "blank_frames": blank,
            "diff_median": round(med, 3), "diff_max": round(float(x.max()), 3), "diff_max_at": int(x.argmax()),
            "frames_over_5x_median": int((x > 5 * med).sum()), "max_isolated_spike_ratio": round(float(max(x[i] / max(1e-6, (x[i - 1] + x[i + 1]) / 2) for i in range(1, len(x) - 1))), 2),
            "label_frames_ok": int(lab_ok), "label_mismatches": int(lab_bad)}

if __name__ == "__main__":
    print(json.dumps(run(*sys.argv[1:]), indent=1))
