"""Verification of the word-timed board-clip builder on the 24 s fixture. Reads the repository, writes only under <work_root>.

usage: python3 -B -I verify_builder.py <repo_root> <work_root> [dissolve values, default "0,0.5"]

1. unit-level checks of cue resolution (missing word, strict vs not strict, determinism of the build);
2. for each dissolve value: build the clip from word-timed cues, put it in the fixture's footage beat, render through the UNMODIFIED
   generate_hybrid_video (offline imagery, synthetic narration), then read the render back:
     - frame-number check (where the clip's frames land in the video, contiguous, +1 per frame, constant offset);
     - for every cue, the video frame on which it really appears (detected from pixels), against the word's time, the builder's plan, and the clip map.
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
import numpy as np
from PIL import Image, ImageDraw

from explainer.board import BoardCueError, Cue, build_board_clip
from hybrid.generate import generate_hybrid_video
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

FPS = 30
work.mkdir(parents=True, exist_ok=True)
media = work / "media"
media.mkdir(exist_ok=True)
voice, card = media / "voice.wav", media / "card.png"
if not voice.exists():
    subprocess.run([sys.executable, "-B", "-I", str(here / "make_audio.py"), str(voice), "24", str(card)], check=True)


# ---- the test narration: our own sentences, Whisper-shaped words (text with punctuation, start, end) ----
def narrate(sentences):
    words = []
    for text, t0 in sentences:
        t = t0
        for tok in text.split():
            words.append((tok, round(t, 3), round(t + 0.294 * 0.85, 3)))
            t += 0.294
    return words


WORDS = narrate([("Pakistan is built around a single river system.", 0.5),
                 ("It begins in the high mountains, far to the north.", 4.8),
                 ("This river feeds the whole valley.", 9.2),
                 ("Farmers wait for the water each spring.", 11.4),
                 ("But the glaciers are melting, nobody knows how long.", 14.15),
                 ("The story continues on the map.", 17.6)])
CUES = [
    Cue("c1_type", "type", {"word": "river"}, text="one river"),
    Cue("c2_pop", "pop", {"word": "farmers"}, text="farmers", role="blue"),
    Cue("c3_pop", "pop", {"word": "water"}, text="water", role="green"),
    Cue("c4_clear", "clear", {"word": "water"}, at="next_sentence"),
    Cue("c5_title", "title", {"word": "glaciers"}, text="THE TWIST"),
    Cue("c6_type_end", "type", {"word": "nobody"}, text="nobody knows how long", finish_with="sentence_end"),
]
BEAT = (9.0, 17.0)
result = {"checks": {}, "variants": {}}

# ---- 1. unit-level checks ----
tiny = work / "tiny"
tiny.mkdir(exist_ok=True)
try:
    build_board_clip([Cue("x", "type", {"word": "nonexistent"}, text="x")], WORDS, 9.0, 10.0, tiny / "strict.mp4")
    result["checks"]["strict_raises_on_missing_word"] = False
except BoardCueError as e:
    result["checks"]["strict_raises_on_missing_word"] = "not spoken inside this beat" in str(e)
b = build_board_clip([Cue("x", "type", {"word": "nonexistent"}, text="x"), Cue("y", "type", {"word": "river"}, text="ok")], WORDS, 9.0, 10.0, tiny / "loose.mp4", strict=False)
result["checks"]["non_strict_skips_bad_cue_and_still_builds"] = bool(b.problems) and b.n_frames == 30 and [i.cue_id for i in b.items] == ["y"]
for bad in (Cue("k", "wobble", {"word": "river"}, text="x"), Cue("e", "type", {"word": "river"}, text=""), Cue("w", "type", {}, text="x"),
            Cue("l", "clear", {"word": "river"}, at="sideways"), Cue("o", "type", {"word": "river"}, text="x", offset_s=30.0)):
    r = build_board_clip([bad], WORDS, 9.0, 10.0, tiny / "bad.mp4", strict=False)
    result["checks"][f"problem_reported_for_{bad.id}"] = bool(r.problems)
h1 = build_board_clip(CUES, WORDS, *BEAT, tiny / "d1.mp4", instrument=True, manifest_path=tiny / "d1.json")
h2 = build_board_clip(CUES, WORDS, *BEAT, tiny / "d2.mp4", instrument=True, manifest_path=tiny / "d2.json")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
result["checks"]["build_is_deterministic_manifest"] = json.loads((tiny / "d1.json").read_text())["cues"] == json.loads((tiny / "d2.json").read_text())["cues"]
fm = lambda p: subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "framemd5", "-"], capture_output=True, text=True).stdout.split("#")[-1]
result["checks"]["build_is_deterministic_frames"] = fm(tiny / "d1.mp4") == fm(tiny / "d2.mp4")
result["checks"]["clip_bytes_identical_between_builds"] = sha(tiny / "d1.mp4") == sha(tiny / "d2.mp4")


# ---- 2. render and read back ----
def raw(path, vf, pix, size_bytes):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo", "-pix_fmt", pix, "-"], capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(-1, size_bytes)


def frame_png(path, n):
    import io
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", "-f", "image2pipe", "-c:v", "png", "-"], capture_output=True, check=True)
    return Image.open(io.BytesIO(p.stdout)).convert("RGB")


def run_variant(d):
    tag = f"d{str(d).replace('.', '_')}"
    out = work / f"variant_{tag}"
    out.mkdir(exist_ok=True)
    build = build_board_clip(CUES, WORDS, *BEAT, out / "board.mp4", dissolve_s=d, instrument=True, beat_id="b2", manifest_path=out / "board_manifest.json")
    plan = json.loads((root / "test_hybrid_app_plan.json").read_text())
    plan["settings"]["dissolve_s"] = build.plan_fragment["settings"]["dissolve_s"]
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
            "clip_origin_s": build.clip_origin_s, "clip_length_s": build.clip_length_s, "clip_frames": build.n_frames}
    if not res.ok:
        return info
    nb = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(video)],
                            capture_output=True, text=True).stdout.strip().strip(","))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip())
    info.update({"video_frames": nb, "video_duration_s": dur})
    # frame-number read-back
    p_int = raw(video, "crop=2:2:1700:300", "rgb24", 12)[:, :3].astype(int)
    p_top = raw(video, "crop=2:2:960:22", "rgb24", 12)[:, :3].astype(int)
    code = raw(video, "crop=320:20:0:0,format=gray", "gray", 320 * 20).reshape(-1, 20, 320)
    board, codes = [], {}
    for i in range(nb):
        cells = code[i][10, 10::20][:16]
        if np.all((cells < 40) | (cells > 215)) and np.abs(p_int[i] - 192).max() <= 8 and p_top[i][0] > 190 and p_top[i][1] < 40:
            board.append(i)
            codes[i] = int("".join("1" if c > 128 else "0" for c in cells), 2)
    seq = [codes[i] for i in board]
    offs = sorted({i - codes[i] for i in board})
    info["frame_number_check"] = {"board_frames": len(board), "first_video_frame": board[0], "last_video_frame": board[-1],
                                  "contiguous": board[-1] - board[0] + 1 == len(board), "code_steps": sorted({seq[j + 1] - seq[j] for j in range(len(seq) - 1)}),
                                  "first_code": seq[0], "last_code": seq[-1], "video_frame_minus_clip_frame_values": offs[:5],
                                  "constant_offset": len(offs) == 1, "clip_frame0_at_video_frame": offs[0] if len(offs) == 1 else None,
                                  "clip_frame0_time_s": (offs[0] / FPS) if len(offs) == 1 else None, "ideal_origin_s": build.clip_origin_s}
    f0 = offs[0] if len(offs) == 1 else None
    # per-cue onset detection from pixels
    man = json.loads((out / "board_manifest.json").read_text())
    THR, DEV = 12, 50
    rows = []
    for c in man["cues"]:
        row = {"id": c["id"], "kind": c["kind"], "word": c["word"], "word_start_abs": c["word_start_abs"], "planned_onset_abs": c["onset_abs"], "first_clip_frame": c["first_frame"],
               "planned_video_frame_builder": c["planned_video_frame"], "problems": c["problems"]}
        if c["kind"] == "clear" or not c.get("bbox") or f0 is None:
            rows.append(row)
            continue
        x0, y0, x1, y1 = c["bbox"]
        x0, y0, x1, y1 = x0 // 2 * 2, y0 // 2 * 2, (x1 + 1) // 2 * 2, (y1 + 1) // 2 * 2
        w, h = x1 - x0, y1 - y0
        reg = raw(video, f"crop={w}:{h}:{x0}:{y0},format=gray", "gray", w * h)
        cnt = (np.abs(reg.astype(int) - 192) > DEV).sum(axis=1)
        exp_map = f0 + c["first_frame"]
        found = None
        for i in range(max(1, exp_map - 8), min(nb, exp_map + 10)):
            if cnt[i] >= THR and cnt[i - 1] < THR:
                found = i
                break
        row.update({"expected_video_frame_clip_map": exp_map, "detected_video_frame": found, "region_px": [w, h]})
        if found is not None:
            row["detected_time_s"] = found / FPS
            row["latency_vs_word_s"] = round(found / FPS - c["word_start_abs"], 4)
            row["detected_minus_builder_plan_frames"] = found - c["planned_video_frame"]
            row["detected_minus_clip_map_frames"] = found - exp_map
            if c["kind"] == "type" and c["finish_with"] == "sentence_end":
                final = cnt[min(board[-1], found + math.ceil(c["type_duration_s"] * FPS) + 3)]   # just after the planned end, still inside the board run
                done = next((i for i in range(found, min(nb, found + 60)) if cnt[i] >= 0.97 * final), None)
                row["typing_complete_frame"] = done
                row["typing_complete_time_s"] = None if done is None else done / FPS
                row["sentence_end_abs"] = c["sentence_end_abs"]
                row["complete_minus_sentence_end_s"] = None if done is None else round(done / FPS - c["sentence_end_abs"], 4)
        rows.append(row)
    # the clear: the first frame where the pop c3's region is empty again
    clear = next((c for c in man["cues"] if c["kind"] == "clear" and not c["problems"]), None)
    pop = next((c for c in man["cues"] if c["id"] == "c3_pop"), None)
    if clear and pop and f0 is not None:
        x0, y0, x1, y1 = [v // 2 * 2 for v in pop["bbox"]]
        w, h = (x1 - x0) or 2, (y1 - y0) or 2
        reg = raw(video, f"crop={w}:{h}:{x0}:{y0},format=gray", "gray", w * h)
        cnt = (np.abs(reg.astype(int) - 192) > DEV).sum(axis=1)
        exp = f0 + math.ceil(clear["onset_clip"] * FPS - 1e-9)
        gone = next((i for i in range(max(1, exp - 8), min(nb, exp + 10)) if cnt[i] < THR <= cnt[i - 1]), None)
        rows.append({"id": clear["id"], "kind": "clear", "word": clear["word"], "planned_onset_abs": clear["onset_abs"], "next_sentence_start_abs": clear["onset_abs"],
                     "expected_video_frame_clip_map": exp, "detected_video_frame": gone, "detected_minus_clip_map_frames": None if gone is None else gone - exp,
                     "latency_vs_sentence_start_s": None if gone is None else round(gone / FPS - clear["onset_abs"], 4)})
    info["cues"] = rows
    lat = [r["latency_vs_word_s"] for r in rows if "latency_vs_word_s" in r and r["kind"] in ("pop", "title", "type") and r["id"] != "c6_type_end"]
    info["latency_summary"] = {"n": len(lat), "min_s": min(lat) if lat else None, "max_s": max(lat) if lat else None,
                               "share_in_0_to_0.4s": (sum(1 for v in lat if 0 <= v <= 0.4) / len(lat)) if lat else None,
                               "max_abs_frame_error_vs_clip_map": max([abs(r.get("detected_minus_clip_map_frames", 0)) for r in rows if r.get("detected_video_frame")] or [None]),
                               "undetected": [r["id"] for r in rows if r["kind"] != "clear" and r.get("detected_video_frame") is None and not r.get("problems")]}
    # evidence sheet: before / at / after each cue's onset
    sel = [r for r in rows if r.get("detected_video_frame")]
    tw, th = 480, 270
    sh = Image.new("RGB", (tw * 3, th * len(sel)), (0, 0, 0))
    dd = ImageDraw.Draw(sh)
    for ri, r in enumerate(sel):
        for ci, n in enumerate((r["detected_video_frame"] - 1, r["detected_video_frame"], r["detected_video_frame"] + 3)):
            sh.paste(frame_png(video, n).resize((tw, th)), (ci * tw, ri * th))
            dd.rectangle([ci * tw, ri * th + th - 24, ci * tw + 330, ri * th + th], fill=(0, 0, 0))
            dd.text((ci * tw + 4, ri * th + th - 20), f"{r['id']} frame {n} t={n / FPS:.3f}s", fill=(255, 255, 0))
    sh.save(out / "cue_onsets.jpg", quality=88)
    return info


for d in dissolves:
    info = run_variant(d)
    result["variants"][f"dissolve_{d}"] = info
    print(json.dumps({k: v for k, v in info.items() if k != "cues"}, indent=1))
(work / "verify_builder.json").write_text(json.dumps(result, indent=1))
print(json.dumps(result["checks"], indent=1))
