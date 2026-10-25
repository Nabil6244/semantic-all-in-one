"""Render the 24 s fixture offline through the UNMODIFIED Hybrid pipeline with a board clip as the footage beat.

usage: python3 -B -I run_spike.py <repo_root> <work_root> <variant: A|B|C>
  A  default settings (dissolve_s 0.5); the clip covers the dissolve padding (8.5 s)
  B  dissolve_s = 0 (hard-cut question); the clip is exactly the beat (8.0 s)
  C  control: same as B but the footage beat holds a plain local clip, no board

Nothing in the repository is edited. The only differences from the fixture are in the derived plan written under <work_root>:
the network picture sources are replaced by local files and, for A and B, the footage beat holds the board clip.
No monkeypatching: the render callable is the one generate_pakmap_video already accepts (`render=`), and it only switches the NASA imagery
off (imagery=False, the same switch the repository's own offline tests use). Cache goes to <work_root>/cache."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

root, work_root, variant = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]
os.environ["VIDEOGEN_PAKMAP_CACHE"] = str(work_root / "cache")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
here = Path(__file__).resolve().parent

from hybrid.generate import generate_hybrid_video
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

media = work_root / "media"
media.mkdir(parents=True, exist_ok=True)
out_dir = work_root / f"variant_{variant}"
out_dir.mkdir(parents=True, exist_ok=True)
fixture = json.loads((root / "test_hybrid_app_plan.json").read_text())

# --- media (all local, all made by the spike's own scripts) ---
voice, card = media / "voice.wav", media / "card.png"
if not voice.exists():
    subprocess.run([sys.executable, "-B", "-I", str(here / "make_audio.py"), str(voice), "24", str(card)], check=True, timeout=1800)
secs = {"A": 8.5, "B": 8.0, "C": 8.0}[variant]
clip = media / f"board_{secs}.mp4"
if variant in ("A", "B") and not clip.exists():
    subprocess.run([sys.executable, "-B", "-I", str(here / "make_board_clip.py"), str(clip), str(secs)], check=True, timeout=1800)
if variant == "C":
    clip = media / "plain_8.0.mp4"
    if not clip.exists():   # a plain local clip: flat blue, no code cells, no board look (it only shows where the join is)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x3060a0:s=1920x1080:r=30:d=8", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(clip)], check=True, timeout=1800)

# --- derived plan (the fixture's beats, local assets) ---
plan = json.loads(json.dumps(fixture))
plan["settings"]["dissolve_s"] = 0.5 if variant == "A" else 0.0
b2 = next(b for b in plan["beats"] if b["id"] == "b2")
b2["footage"] = {"clips": [{"asset": str(clip), "reason": "spike: placeholder clip made outside Hybrid"}]}
b3 = next(b for b in plan["beats"] if b["id"] == "b3")
b3["support"]["asset"] = str(card)
plan_path = out_dir / "derived_plan.json"
plan_path.write_text(json.dumps(plan, indent=1))
hp = HybridPlan.load(plan_path)
problems = validate_plan(hp)
print("validate_plan:", problems)

WORDS = [("pakistan", 0.5, 0.9), ("is", 0.9, 1.1)] + [("w%d" % i, 2 + i * 0.5, 2.3 + i * 0.5) for i in range(40)]
log_lines = []


def log(m):
    log_lines.append(str(m)); print(m, flush=True)


def render(spec, output, **kw):
    return render_spec(spec, output, imagery=False, **kw)


out_mp4 = out_dir / f"spike_{variant}.mp4"
t0 = time.time()
res = generate_hybrid_video(hp, voice, out_mp4, work_dir=out_dir / "work", whisper_words=WORDS, render=render, sound_design=False,
                            resolution="1920x1080", fps=30, log=log)
summary = {"variant": variant, "validate_problems": problems, "ok": bool(res.ok), "errors": list(res.errors or []), "warnings": list(res.warnings or []),
           "output": str(res.output_path or out_mp4), "seconds": round(time.time() - t0, 1), "clip": str(clip), "dissolve_s": plan["settings"]["dissolve_s"]}
(out_dir / "result.json").write_text(json.dumps(summary, indent=1))
(out_dir / "log.txt").write_text("\n".join(log_lines))
print(json.dumps(summary, indent=1))
sys.exit(0 if res.ok else 1)
