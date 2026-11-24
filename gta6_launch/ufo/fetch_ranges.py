"""Step 3 of the brief, per the manifest's source_clip_rule: download ONLY each beat's exact source_clips ranges
(video_id + start -> end) with yt-dlp --download-sections. No caption scraping. Files land in footage/library/raw/yt_ufo
as <video_id>_<start>_<end>.mp4 (seconds). Run: python3 fetch_ranges.py"""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "footage/library/raw/yt_ufo"
FMT = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/bv*[height<=1080]+ba"


def secs(t):
    s = 0.0
    for part in str(t).split(":"):
        s = s * 60 + float(part)
    return s


def name(c):
    return f"{c['video_id']}_{int(secs(c['start']))}_{int(secs(c['end']))}"


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    m = json.loads((HERE / "manifest.json").read_text())
    for b in m["beats"]:
        for c in b["source_clips"]:
            out = RAW / f"{name(c)}.mp4"
            if out.is_file() and out.stat().st_size > 100_000:
                print("have", out.name)
                continue
            a, e = secs(c["start"]), secs(c["end"])
            r = subprocess.run(["yt-dlp", "-q", "--no-progress", "--no-warnings", "-f", FMT, "--merge-output-format", "mp4",
                                "--download-sections", f"*{a}-{e}", "--force-keyframes-at-cuts", "-o", str(RAW / f"{name(c)}.%(ext)s"),
                                f"https://www.youtube.com/watch?v={c['video_id']}"], capture_output=True, text=True)
            print("ok  " if out.is_file() else "FAIL", out.name, r.stderr.strip()[-150:])
