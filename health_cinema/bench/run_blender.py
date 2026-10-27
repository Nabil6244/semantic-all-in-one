"""Driver: sample the journey, run Blender in the background, composite labels, encode. Usage: run_blender.py OUTNAME W H ENGINE SAMPLES FPS [first last]"""
import json, os, subprocess, sys, time, resource
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from health_cinema import journey
BL = os.path.expanduser("~/HealthCinemaTools/blender/Blender.app/Contents/MacOS/Blender"); B = Path(os.path.expanduser("~/HealthCinemaTools/bench"))
name, W, H, eng, samples, fps = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), int(sys.argv[6])
rng = sys.argv[7:9]
spec, A, frames = journey.sample(Path(__file__).parent / "journey_chest_heart.json", B / "anchors.json", fps, W, H)
out = B / f"out_{name}"; out.mkdir(exist_ok=True)
(out / "frames.json").write_text(json.dumps({"spec": spec, "anchors": A, "frames": frames}))
cmd = [BL, "-b", str(B / "chest.blend"), "--python", str(Path(__file__).parent / "render_blender.py"), "--", str(out / "frames.json"), str(out), str(W), str(H), eng, str(samples)] + rng
t = time.time(); p = subprocess.run(cmd, capture_output=True, text=True); dt = time.time() - t
print("\n".join(l for l in p.stdout.splitlines() if "RENDER" in l or "Error" in l or "Traceback" in l), p.stderr[-500:])
print("wall", round(dt, 1), "peak MB (children)", resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // (1024 * 1024))
