"""Milestone 1 verification: the new board cue kinds (header, card, icon, chip, arrow) on one shared 10 s fixture, in hard-cut and dissolve modes.
Reads the repository, writes only under <work_root>.

usage: python3 -B -I verify_m1.py <repo_root> <work_root> [dissolve values, default "0,0.5"]

1. unit checks: every new problem path (reserved kind, unknown asset, no free slot, text too long, arrow before its endpoint, bad explicit position),
   strict vs non-strict, legacy default positions untouched, slot reuse after a clear, deterministic builds (manifest, frames, clip bytes);
2. for each dissolve value: build the 10 s clip, put it in the fixture's footage beat, render through the UNMODIFIED generate_hybrid_video, then
   read it back: frame map of the clip, and for every cue the video frame on which it really appears against the clip map and the builder's plan.
"""
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

root, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
dissolves = [float(v) for v in (sys.argv[3] if len(sys.argv) > 3 else "0,0.5").split(",")]
os.environ["VIDEOGEN_PAKMAP_CACHE"] = str(work / "cache")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import numpy as np
from PIL import Image, ImageDraw

import measure_render as M
from explainer.board import BoardCueError, Cue, build_board_clip
from explainer.board import layout as LY
from hybrid.generate import generate_hybrid_video
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

FPS = 30
PROBE = (300, 500)                     # a pixel the clip never draws on (the left 544 px are reserved for the narrator in Milestone 2)
work.mkdir(parents=True, exist_ok=True)
media = work / "media"
media.mkdir(exist_ok=True)
voice, card = media / "voice.wav", media / "card.png"
if not voice.exists():
    subprocess.run([sys.executable, "-B", "-I", str(here / "make_audio.py"), str(voice), "24", str(card)], check=True, timeout=1800)


def narrate(sentences):
    words = []
    for text, t0 in sentences:
        t = t0
        for tok in text.split():
            words.append((tok, round(t, 3), round(t + 0.294 * 0.85, 3)))
            t += 0.294
    return words


WORDS = narrate([("Prices rose every year while the poor lost their homes.", 7.2),
                 ("Meanwhile gold flowed across the sea to the crown.", 10.6),
                 ("Nobody counted the true cost until 1545 and 100,000 workers.", 13.8)])
BEAT = (7.0, 17.0)
CUES = [
    Cue("h1", "header", {"word": "prices"}, text="the cost"),
    Cue("c1", "card", {"word": "rose"}, text="prices rose each year", role="red", asset="icon:coin"),
    Cue("c2", "card", {"word": "homes"}, text="the poor lost their homes", role="blue", asset="icon:house"),
    Cue("a1", "arrow", {"word": "homes"}, offset_s=0.3, role="red", src="c1", dst="c2"),
    Cue("x1", "clear", {"word": "meanwhile"}),
    Cue("h2", "header", {"word": "gold"}, text="the gain"),
    Cue("i1", "icon", {"word": "flowed"}, text="gold", role="gold", asset="icon:coin"),
    Cue("c3", "card", {"word": "crown"}, text="the crown grew rich", role="green"),
    Cue("a2", "arrow", {"word": "crown"}, offset_s=0.4, role="ink", src="i1", dst="c3"),
    Cue("x2", "clear", {"word": "nobody"}),
    Cue("c4", "card", {"word": "counted"}, text="nobody counted the true cost", role="gold", asset="icon:warning"),
    Cue("k1", "chip", {"word": "1545"}, text="1545"),
    Cue("k2", "chip", {"word": "100,000"}, text="100,000"),
]
result = {"checks": {}, "variants": {}}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
fm = lambda p: subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "framemd5", "-"], capture_output=True, text=True, timeout=1800).stdout.split("#")[-1]

# ---- 1. unit checks ----
tiny = work / "tiny"
tiny.mkdir(exist_ok=True)


def problems_of(cues, strict=False, beat=(7.0, 17.0)):
    try:
        b = build_board_clip(cues, WORDS, *beat, tiny / "u.mp4", strict=strict)
    except BoardCueError as e:
        return e.problems, None
    return b.problems, b


ck = result["checks"]
p, _ = problems_of([Cue("n", "map", {"word": "rose"}, text="x")])   # Milestone 2 implemented "narrator" and Milestone 3 "caption"; "map" is still reserved
ck["reserved_kind_reports_problem"] = any("reserved" in x for x in p)
p, _ = problems_of([Cue("i", "icon", {"word": "rose"}, asset="icon:nope")])
ck["unknown_asset_lists_available"] = any("unknown asset" in x and "icon:drop" in x for x in p)
p, _ = problems_of([Cue("i", "icon", {"word": "rose"})])
ck["icon_needs_asset"] = any("needs an asset" in x for x in p)
p, _ = problems_of([Cue("c", "card", {"word": "rose"}, text="word " * 60)])
ck["text_too_long_reports_problem"] = any("does not fit" in x for x in p)
p, _ = problems_of([Cue(f"c{k}", "card", {"word": "rose"}, text=f"card {k}") for k in range(5)])
ck["fifth_card_gets_no_slot"] = sum("no free card slot" in x for x in p) == 1
p, _ = problems_of([Cue("c", "card", {"word": "homes"}, text="a"), Cue("a", "arrow", {"word": "rose"}, src="c", dst="c2"), Cue("c2", "card", {"word": "crown"}, text="b")])
ck["arrow_before_endpoint_reports_problem"] = any("appears at frame" in x or "not a drawable" in x for x in p)
p, _ = problems_of([Cue("c", "card", {"word": "rose"}, text="a", pos=(10, 10))])
ck["position_outside_margins_reports_problem"] = any("margins" in x for x in p)
p, _ = problems_of([Cue("c", "card", {"word": "rose"}, text="a", slot="C1"), Cue("d", "card", {"word": "rose"}, text="b", slot="C1")])
ck["named_slot_taken_reports_problem"] = any("slot C1 is taken" in x for x in p)
p, _ = problems_of([Cue("c", "card", {"word": "rose"}, text="a", slot="K1")])
ck["wrong_class_slot_reports_problem"] = any("not a card slot" in x for x in p)
try:
    build_board_clip([Cue("c", "card", {"word": "rose"}, text="word " * 60)], WORDS, 7.0, 8.0, tiny / "s.mp4", strict=True)
    ck["strict_raises_on_layout_problem"] = False
except BoardCueError:
    ck["strict_raises_on_layout_problem"] = not (tiny / "s.mp4").exists()
p, b = problems_of([Cue("bad", "card", {"word": "rose"}, text="word " * 60), Cue("ok", "card", {"word": "rose"}, text="fine")])
ck["non_strict_skips_bad_and_builds_good"] = bool(p) and b is not None and [i.cue_id for i in b.items] == ["ok"] and b.items[0].slot == "C1"
# legacy cues keep their default positions even when new cues are present
leg = [Cue("t", "type", {"word": "rose"}, text="legacy line"), Cue("p", "pop", {"word": "homes"}, text="pop", role="blue")]
bl = build_board_clip(leg, WORDS, 7.0, 12.0, tiny / "leg.mp4")
bm = build_board_clip(leg + [Cue("c", "card", {"word": "rose"}, text="new card")], WORDS, 7.0, 12.0, tiny / "leg2.mp4")
pos_l = {i.cue_id: (i.pos, i.bbox) for i in bl.items}
pos_m = {i.cue_id: (i.pos, i.bbox) for i in bm.items if i.cue_id in pos_l}
ck["legacy_positions_unchanged_by_new_cues"] = pos_l == pos_m
ck["new_card_avoids_legacy_items"] = all(not LY.intersects(i.rect, o.bbox) for i in bm.items if i.cue_id == "c" for o in bm.items if o.cue_id in pos_l)
# slot reuse after a clear: the same slot twice, separated by a clear
b = build_board_clip([Cue("a", "card", {"word": "rose"}, text="first", slot="C1"), Cue("x", "clear", {"word": "meanwhile"}), Cue("b", "card", {"word": "gold"}, text="second", slot="C1")],
                     WORDS, 7.0, 17.0, tiny / "reuse.mp4")
ck["slot_reused_after_clear"] = not b.problems and [i.slot for i in b.items] == ["C1", "C1"]
ck["manifest_has_schema_version_1"] = build_board_clip(CUES, WORDS, *BEAT, tiny / "m.mp4", manifest_path=tiny / "m.json").manifest()["schema_version"] == 1
# deterministic builds
for tag, inst in (("plain", False), ("instr", True)):
    for k in (1, 2):
        build_board_clip(CUES, WORDS, *BEAT, tiny / f"{tag}{k}.mp4", instrument=inst, manifest_path=tiny / f"{tag}{k}.json")
    ck[f"deterministic_{tag}_clip_bytes"] = sha(tiny / f"{tag}1.mp4") == sha(tiny / f"{tag}2.mp4")
    ck[f"deterministic_{tag}_frames"] = fm(tiny / f"{tag}1.mp4") == fm(tiny / f"{tag}2.mp4")
    ck[f"deterministic_{tag}_manifest"] = (tiny / f"{tag}1.json").read_text().replace(f"{tag}1", "X") == (tiny / f"{tag}2.json").read_text().replace(f"{tag}2", "X")
result["clip_sha256"] = {"plain": sha(tiny / "plain1.mp4"), "instrumented": sha(tiny / "instr1.mp4")}
result["clip_bytes"] = (tiny / "plain1.mp4").stat().st_size


# ---- 2. render and read back ----
def run_variant(d):
    tag = f"d{str(d).replace('.', '_')}"
    out = work / f"variant_{tag}"
    out.mkdir(exist_ok=True)
    build = build_board_clip(CUES, WORDS, *BEAT, out / "board.mp4", dissolve_s=d, instrument=True, beat_id="b2", manifest_path=out / "board_manifest.json")
    plan = json.loads((root / "test_hybrid_app_plan.json").read_text())
    plan["settings"]["dissolve_s"] = build.plan_fragment["settings"]["dissolve_s"]
    b1 = next(b for b in plan["beats"] if b["id"] == "b1")
    b1["end"] = BEAT[0]
    for m in b1.get("markers", []) or []:
        pass
    keep = next(b for b in plan["beats"] if b["id"] == "b2")
    keep.update({k: v for k, v in build.plan_fragment["beat"].items() if k not in ("id",)})
    keep.pop("footage_intent", None)
    next(b for b in plan["beats"] if b["id"] == "b3")["support"]["asset"] = str(card)
    (out / "derived_plan.json").write_text(json.dumps(plan, indent=1))
    hp = HybridPlan.load(out / "derived_plan.json")
    problems = validate_plan(hp)
    video = out / "render.mp4"
    t0 = time.time()
    res = generate_hybrid_video(hp, voice, video, work_dir=out / "work", whisper_words=WORDS, render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw),
                                sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    info = {"dissolve_s": d, "validate_problems": problems, "render_ok": bool(res.ok), "render_errors": list(res.errors or []), "render_seconds": round(time.time() - t0, 1),
            "clip_origin_s": build.clip_origin_s, "clip_length_s": build.clip_length_s, "clip_frames": build.n_frames, "builder_problems": build.problems}
    if not res.ok:
        return info
    runs, nb = M.board_runs(video, PROBE)
    run = max(runs, key=lambda r: r["frames"])
    f0 = run["offset"]
    info.update({"video_frames": nb, "runs": [{k: v for k, v in r.items() if k != "frame_of_code"} for r in runs], "clip_frame0_at_video_frame": f0})
    man = json.loads((out / "board_manifest.json").read_text())
    rows = []
    last_board = run["last"]
    for c in man["cues"]:
        row = {"id": c["id"], "kind": c["kind"], "slot": c["slot"], "word": c["word"], "word_start_abs": c["word_start_abs"], "planned_onset_abs": c["onset_abs"],
               "first_clip_frame": c["first_frame"], "planned_video_frame_builder": c["planned_video_frame"], "problems": c["problems"]}
        if c["kind"] == "clear" or not c.get("bbox") or f0 is None:
            rows.append(row)
            continue
        exp_map = f0 + c["first_frame"]
        found, cnt = M.onset_frame(video, c["bbox"], exp_map, nb, last_board)
        row.update({"expected_video_frame_clip_map": exp_map, "detected_video_frame": found, "bbox": c["bbox"]})
        if found is not None:
            row["latency_vs_word_s"] = round(found / FPS - c["word_start_abs"], 4)
            row["detected_minus_clip_map_frames"] = found - exp_map
            row["detected_minus_builder_plan_frames"] = found - c["planned_video_frame"]
        rows.append(row)
    # clears: the first frame on which the region of an element the clear hides is empty again
    items = {i["id"]: i for i in man["cues"]}
    for c in [c for c in man["cues"] if c["kind"] == "clear"]:
        row = {"id": c["id"], "kind": "clear", "word": c["word"], "planned_onset_abs": c["onset_abs"], "first_clip_frame": c["first_frame"]}
        target = next((r for r in rows if r["kind"] in ("card",) and r.get("bbox") and items[r["id"]]["onset_clip"] < c["onset_clip"]
                       and r["id"] in {"c1", "c3"} and ((c["id"] == "x1" and r["id"] == "c1") or (c["id"] == "x2" and r["id"] == "c3"))), None)
        if target and f0 is not None:
            x0, y0, x1, y1 = [v // 2 * 2 for v in target["bbox"]]
            w, h = max(2, x1 - x0), max(2, y1 - y0)
            reg = M.raw(video, f"crop={w}:{h}:{x0}:{y0},format=gray", "gray", w * h)
            cnt = (np.abs(reg.astype(int) - 192) > 50).sum(axis=1)
            exp = f0 + c["first_frame"]
            gone = next((i for i in range(max(1, exp - 8), min(last_board, exp + 10)) if cnt[i] < 12 <= cnt[i - 1]), None)
            row.update({"measured_on": target["id"], "expected_video_frame_clip_map": exp, "detected_video_frame": gone,
                        "detected_minus_clip_map_frames": None if gone is None else gone - exp})
        rows.append(row)
    info["cues"] = rows
    det = [r for r in rows if r.get("detected_video_frame") is not None]
    lat = [r["latency_vs_word_s"] for r in rows if "latency_vs_word_s" in r]
    info["summary"] = {"cues_total": len([r for r in rows]), "cues_measured": len(det), "undetected": [r["id"] for r in rows if r["kind"] != "clear" and r.get("detected_video_frame") is None and not r["problems"]],
                       "max_abs_frame_error_vs_clip_map": max([abs(r["detected_minus_clip_map_frames"]) for r in det if r.get("detected_minus_clip_map_frames") is not None] or [None]),
                       "max_abs_frame_error_vs_builder_plan": max([abs(r["detected_minus_builder_plan_frames"]) for r in det if "detected_minus_builder_plan_frames" in r] or [None]),
                       "latency_min_s": min(lat) if lat else None, "latency_max_s": max(lat) if lat else None,
                       "runs": len(runs), "held_frames": run["held_frames"], "skipped_frames": run["skipped_frames"]}
    sel = [r for r in det if r["kind"] != "clear"]
    tw, th = 480, 270
    sh = Image.new("RGB", (tw * 3, th * len(sel)), (0, 0, 0))
    dd = ImageDraw.Draw(sh)
    for ri, r in enumerate(sel):
        for ci, n in enumerate((r["detected_video_frame"] - 1, r["detected_video_frame"], r["detected_video_frame"] + 4)):
            sh.paste(M.frame_png(video, n).resize((tw, th)), (ci * tw, ri * th))
            dd.rectangle([ci * tw, ri * th + th - 24, ci * tw + 330, ri * th + th], fill=(0, 0, 0))
            dd.text((ci * tw + 4, ri * th + th - 20), f"{r['id']} {r['kind']} frame {n} t={n / FPS:.3f}s", fill=(255, 255, 0))
    sh.save(out / "cue_onsets.jpg", quality=85)
    # three summary frames of the real render (hard cut: just before each clear and at the end of the beat)
    keys = [int(f0 + (t - build.clip_origin_s) * FPS) for t in (10.55, 13.75, 16.9)]
    strip = Image.new("RGB", (960 * 3, 540), (0, 0, 0))
    for k, n in enumerate(keys):
        strip.paste(M.frame_png(video, n).resize((960, 540)), (k * 960, 0))
    strip.save(out / "summary_frames.jpg", quality=88)
    return info


for d in dissolves:
    info = run_variant(d)
    result["variants"][f"dissolve_{d}"] = info
    print(json.dumps({k: v for k, v in info.items() if k not in ("cues", "runs")}, indent=1))
(work / "verify_m1.json").write_text(json.dumps(result, indent=1))
print(json.dumps(result["checks"], indent=1))
