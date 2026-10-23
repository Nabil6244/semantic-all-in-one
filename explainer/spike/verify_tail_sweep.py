"""Does the pipeline hold a frame inside a board clip when the beat length is not a whole number of frames, and do spare tail frames prevent it?
Five board beats at deliberately non-frame-aligned times, rendered with tail_frames 0 and 2 (hard cut) and with a 0.5 s dissolve.
Reads the repository, writes only under <work_root>.   usage: python3 -B -I verify_tail_sweep.py <repo_root> <work_root>"""
import json
import os
import shutil
import sys
from pathlib import Path

root, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
os.environ["VIDEOGEN_PAKMAP_CACHE"] = str(work / "cache")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import subprocess

import measure_render as M
from explainer.board import Cue, splice_board_beats
from hybrid.generate import generate_hybrid_video
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

FPS = 30
work.mkdir(parents=True, exist_ok=True)
voice, card = work / "voice.wav", work / "card.png"
if not voice.exists():
    subprocess.run([sys.executable, "-B", "-I", str(Path(__file__).resolve().parent / "make_audio.py"), str(voice), "32", str(card)], check=True)
EDGES = [0, 2.137, 6.481, 7.9, 12.263, 13.4, 17.719, 19.0, 23.541, 25.2, 29.837, 32.0]
beats, specs = [], []
for i in range(len(EDGES) - 1):
    a, b = EDGES[i], EDGES[i + 1]
    if i % 2 == 1:
        beats.append({"id": f"f{i}", "mode": "footage", "start": a, "end": b, "purpose": "placeholder", "footage": {"clips": [{"asset": str(card)}]}})
        specs.append({"beat_id": f"f{i}", "cues": [Cue(f"c{i}", "type", {"index": 3}, text=f"board {i}")]})
    else:
        beats.append({"id": f"m{i}", "mode": "map", "start": a, "end": b, "purpose": "map", "camera": [{"action": "start", "place": "Pakistan", "frame": "country"}] if i == 0 else [], "layers": []})
words = [(f"w{k}", round(0.2 + k * 0.3, 3), round(0.2 + k * 0.3 + 0.25, 3)) for k in range(105)]
PLAN = {"version": 1, "duration": 32.0, "settings": {"dissolve_s": 0.0, "return_grace_s": 0.8, "drift_pct_per_s": 0.5}, "beats": beats}
validate_fn = lambda p: validate_plan(HybridPlan.from_dict(p))
out_all = {"edges": EDGES, "variants": {}}
for name, d, tail in (("hard_tail0", 0.0, 0), ("hard_tail2", 0.0, 2), ("dissolve_tail0", 0.5, 0), ("dissolve_tail2", 0.5, 2)):
    out = work / name
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    res = splice_board_beats(PLAN, specs, words, out, dissolve_s=d, instrument=True, tail_frames=tail, validate=validate_fn)
    (out / "plan.json").write_text(json.dumps(res.plan, indent=1))
    video = out / "render.mp4"
    g = generate_hybrid_video(HybridPlan.load(out / "plan.json"), voice, video, work_dir=out / "work", whisper_words=words,
                              render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw), sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    info = {"render_ok": bool(g.ok), "errors": list(g.errors or [])}
    if g.ok:
        runs, nb = M.board_runs(video)
        info["runs_found"] = len(runs)
        rows = []
        for b, rn in zip(res.builds, runs):
            bid = b.plan_fragment["beat"]["id"]
            bs, be = b.plan_fragment["beat"]["start"], b.plan_fragment["beat"]["end"]
            c = b.manifest()["cues"][0]
            got, _ = (None, None)
            if c["first_frame"] in rn["frame_of_code"]:
                want = rn["frame_of_code"][c["first_frame"]]
                got, _ = M.onset_frame(video, c["bbox"], want, nb, rn["last"])
            rows.append({"beat": bid, "start_s": bs, "end_s": be, "start_frame_exact": round(bs * FPS, 3), "end_frame_exact": round(be * FPS, 3), "beat_frames_exact": round((be - bs) * FPS, 3),
                         "clip_frames": b.n_frames, "run_first": rn["first"], "run_last": rn["last"], "held_frames": rn["held_frames"], "held_at": rn["held_at"], "skipped_frames": rn["skipped_frames"],
                         "offset_values": rn["offset_values"], "cue_detected_minus_clip_map": None if got is None else got - rn["frame_of_code"][c["first_frame"]],
                         "cue_detected_minus_builder_plan": None if got is None else got - c["planned_video_frame"]})
        info["boards"] = rows
        info["totals"] = {"boards": len(rows), "boards_with_a_held_frame": sum(1 for r in rows if r["held_frames"]), "boards_with_skipped_frames": sum(1 for r in rows if r["skipped_frames"]),
                          "max_abs_cue_error_vs_plan_frames": max([abs(r["cue_detected_minus_builder_plan"]) for r in rows if r["cue_detected_minus_builder_plan"] is not None] or [None]),
                          "max_abs_cue_error_vs_clip_map_frames": max([abs(r["cue_detected_minus_clip_map"]) for r in rows if r["cue_detected_minus_clip_map"] is not None] or [None])}
    out_all["variants"][name] = info
    print(name, json.dumps(info.get("totals", info)))
(work / "verify_tail_sweep.json").write_text(json.dumps(out_all, indent=1))
