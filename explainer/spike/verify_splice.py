"""Verification of the plan-level splice helper on a five-beat plan with TWO board beats. Reads the repository, writes only under <work_root>.

usage: python3 -B -I verify_splice.py <repo_root> <work_root>

1. sentence-boundary sources agree (punctuated words / normalised tokens with Hybrid's own build_sentences, script-aligned and pause-based);
2. splice rules (unknown beat, map beat, duplicate, strict stops before drawing, non-strict records, input not mutated, other beats unchanged);
3. both dissolve modes: splice, validate with the real validate_plan, render through the unmodified generate_hybrid_video, read the render back
   (both board runs: frame numbers, offsets; every cue's landing frame against the clip map and the word time).
"""
import copy
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

root, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
os.environ["VIDEOGEN_PAKMAP_CACHE"] = str(work / "cache")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageDraw

import measure_render as M
from explainer.board import BoardCueError, Cue, resolve_cues, splice_board_beats
from hybrid.generate import generate_hybrid_video
from hybrid.narration import build_sentences
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

FPS = 30
work.mkdir(parents=True, exist_ok=True)
media = work / "media"
media.mkdir(exist_ok=True)
voice, card = media / "voice.wav", media / "card.png"
if not voice.exists():
    subprocess.run([sys.executable, "-B", "-I", str(Path(__file__).resolve().parent / "make_audio.py"), str(voice), "28", str(card)], check=True)

# ---- narration: our own sentences, 0.7 s between sentences, Whisper-shaped words with punctuation ----
SENT = ["Pakistan is built around a single river system.", "It begins in the high mountains, far to the north.",
        "This river feeds the whole valley.", "Farmers wait for the water each spring.", "But the glaciers are melting and nobody knows.",
        "The mountains feed the river all year.",
        "The first steps matter most here.", "Everything depends on the next decade.", "That is the whole story."]
t, words, starts = 0.4, [], []
for text in SENT:
    starts.append(round(t, 3))
    for tok in text.split():
        words.append((tok, round(t, 3), round(t + 0.294 * 0.85, 3)))
        t += 0.294
    t += 0.7
ends = [words[[i for i, w in enumerate(words) if w[1] >= starts[k]][0] + len(SENT[k].split()) - 1][2] for k in range(len(SENT))]
frame = lambda s: round(s * FPS) / FPS
B2 = (frame(starts[2] - 0.3), frame(starts[5] - 0.3))     # board 1: sentences 2, 3, 4
B4 = (frame(starts[6] - 0.3), frame(ends[8] + 0.35))      # board 2: sentences 6, 7, 8
assert B2[1] <= starts[5] and B4[1] <= 28.0, (B2, B4, ends)
norm = lambda w: re.sub(r"[^a-z0-9']", "", w.lower())
nwords = [(norm(w), s, e) for w, s, e in words]

CUES_1 = [Cue("a1", "type", {"word": "river"}, text="one river"), Cue("a2", "pop", {"word": "farmers"}, text="farmers", role="blue"),
          Cue("a3", "pop", {"word": "water"}, text="water", role="green"), Cue("a4", "clear", {"word": "water"}, at="next_sentence"),
          Cue("a5", "title", {"word": "glaciers"}, text="THE TWIST")]
CUES_2 = [Cue("b1", "type", {"word": "steps"}, text="first steps"), Cue("b2", "pop", {"word": "depends"}, text="depends", role="gold"),
          Cue("b3", "type", {"word": "whole"}, text="the whole story", finish_with="sentence_end")]
SPECS = [{"beat_id": "b2", "cues": CUES_1}, {"beat_id": "b4", "cues": CUES_2}]
fx = json.loads((root / "test_hybrid_app_plan.json").read_text())
b1 = copy.deepcopy(next(b for b in fx["beats"] if b["id"] == "b1"))
mk = copy.deepcopy(next(b for b in fx["beats"] if b["id"] == "b3"))
b1.update(start=0, end=B2[0])
b1["layers"][1]["until"] = "beat_end"
mk.pop("support", None); mk["mode"] = "map"
mk.update(id="b3", start=B2[1], end=B4[0])
mk["layers"][0]["t"] = round(B2[1] + 0.6, 3)
PLAN = {"version": 1, "duration": 28.0, "settings": {"dissolve_s": 0.5, "return_grace_s": 0.8, "drift_pct_per_s": 0.5}, "beats": [
    b1,
    {"id": "b2", "mode": "footage", "start": B2[0], "end": B2[1], "purpose": "placeholder", "footage": {"clips": [{"asset": str(card)}]}},
    mk,
    {"id": "b4", "mode": "footage", "start": B4[0], "end": B4[1], "purpose": "placeholder", "footage": {"clips": [{"asset": str(card)}]}},
    {"id": "b5", "mode": "map", "start": B4[1], "end": 28.0, "purpose": "close", "camera": [], "layers": []}]}
validate_fn = lambda p: validate_plan(HybridPlan.from_dict(p))
R = {"beats": {"b2": B2, "b4": B4}, "problems_of_input_plan": validate_fn(PLAN), "checks": {}, "variants": {}}

# ---- 1. sentence sources agree ----
script = " ".join(SENT)
variants = {"punctuated_words_no_sentences": (words, None),
            "normalised_words_pause_fallback": (nwords, None),
            "normalised_words_hybrid_pauses": (nwords, [(s.start, s.end) for s in build_sentences(nwords)]),
            "normalised_words_hybrid_script": (nwords, [(s.start, s.end) for s in build_sentences(nwords, script=script)])}
onsets = {}
for name, (w, sents) in variants.items():
    row = {}
    for bid, (bs, be), cues in (("b2", B2, CUES_1), ("b4", B4, CUES_2)):
        for r in resolve_cues(cues, w, bs, be, bs, FPS, be - bs, sents):
            row[f"{bid}:{r.cue.id}"] = (None if r.onset_abs is None else round(r.onset_abs, 4), r.sentence_source, r.problems)
    onsets[name] = row
base = {k: v[0] for k, v in onsets["punctuated_words_no_sentences"].items()}
R["sentence_sources"] = {n: {"source": sorted({v[1] for v in row.values()}), "all_onsets_equal_to_punctuated": {k: v[0] for k, v in row.items()} == base,
                             "problems": [p for v in row.values() for p in v[2]]} for n, row in onsets.items()}
R["checks"]["sentence_sources_agree"] = all(v["all_onsets_equal_to_punctuated"] and not v["problems"] for v in R["sentence_sources"].values())

# ---- 2. splice rules ----
import shutil
neg = work / "neg"
shutil.rmtree(neg, ignore_errors=True)    # a clean folder: the strict-stops check looks for files
neg.mkdir(exist_ok=True)
before = json.dumps(PLAN, sort_keys=True)
def raises(specs, **kw):
    try:
        splice_board_beats(PLAN, specs, words, neg, dissolve_s=0.0, **kw)
        return None
    except BoardCueError as e:
        return str(e)
e1 = raises([{"beat_id": "nope", "cues": CUES_1}])
e2 = raises([{"beat_id": "b3", "cues": CUES_1}])
e3 = raises([{"beat_id": "b2", "cues": CUES_1}, {"beat_id": "b2", "cues": CUES_1}])
e4 = raises([{"beat_id": "b2", "cues": CUES_1}, {"beat_id": "b4", "cues": [Cue("z", "type", {"word": "zzz"}, text="x")]}])
R["checks"]["unknown_beat_refused"] = bool(e1) and "not in the plan" in e1
R["checks"]["map_beat_refused"] = bool(e2) and "only a footage beat" in e2
R["checks"]["duplicate_refused"] = bool(e3) and "listed twice" in e3
R["checks"]["strict_stops_before_any_clip_is_drawn"] = bool(e4) and "zzz" in e4 and not list(neg.glob("*.mp4"))
loose = splice_board_beats(PLAN, [{"beat_id": "b2", "cues": CUES_1}, {"beat_id": "b4", "cues": [Cue("z", "type", {"word": "zzz"}, text="x"), Cue("ok", "type", {"word": "story"}, text="fine")]}],
                           words, neg, dissolve_s=0.0, strict=False)
R["checks"]["non_strict_records_problem_and_builds_both"] = len(loose.builds) == 2 and any("zzz" in p for p in loose.problems)
try:
    splice_board_beats({"beats": PLAN["beats"]}, SPECS, words, neg)
    R["checks"]["missing_dissolve_s_refused"] = False
except BoardCueError as e:
    R["checks"]["missing_dissolve_s_refused"] = "dissolve_s" in str(e)
R["checks"]["input_plan_not_mutated"] = json.dumps(PLAN, sort_keys=True) == before


# ---- 3. both dissolve modes ----
def run(d):
    tag = f"d{str(d).replace('.', '_')}"
    out = work / f"variant_{tag}"
    out.mkdir(exist_ok=True)
    res = splice_board_beats(PLAN, SPECS, words, out, dissolve_s=d, instrument=True, validate=validate_fn)
    info = {"dissolve_s": d, "notes": res.notes, "problems": res.problems, "clips": [str(b.clip_path) for b in res.builds],
            "other_beats_unchanged": all(copy.deepcopy(a) == b for a, b in zip(PLAN["beats"], res.plan["beats"]) if a["id"] not in ("b2", "b4")),
            "settings_dissolve": res.plan["settings"]["dissolve_s"], "board_beats_point_to_clips": [b["footage"]["clips"][0]["asset"] for b in res.plan["beats"] if b["id"] in ("b2", "b4")] == [str(b.clip_path) for b in res.builds]}
    (out / "spliced_plan.json").write_text(json.dumps(res.plan, indent=1))
    hp = HybridPlan.load(out / "spliced_plan.json")
    video = out / "render.mp4"
    t0 = time.time()
    g = generate_hybrid_video(hp, voice, video, work_dir=out / "work", whisper_words=nwords, render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw),
                              sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    info.update({"render_ok": bool(g.ok), "render_errors": list(g.errors or []), "render_seconds": round(time.time() - t0, 1)})
    if not g.ok:
        return info
    runs, nb = M.board_runs(video)
    info["video_frames"], info["board_runs"] = nb, [{k: v for k, v in r.items() if k != "frame_of_code"} for r in runs]
    exp = [(bs, be, b) for (bs, be), b in zip((B2, B4), res.builds)]
    info["runs_match_two_board_beats"] = len(runs) == 2
    cues = []
    for (bs, be, b), rn in zip(exp, runs):
        f0 = rn["offset"]
        foc = rn["frame_of_code"]
        for c in b.manifest()["cues"]:
            row = {"beat": b.plan_fragment["beat"]["id"], "id": c["id"], "kind": c["kind"], "word": c["word"], "word_start_abs": c["word_start_abs"], "planned_onset_abs": c["onset_abs"],
                   "first_clip_frame": c["first_frame"], "problems": c["problems"]}
            if c["kind"] != "clear" and c.get("bbox") and c["first_frame"] in foc:
                want = foc[c["first_frame"]]
                got, cnt = M.onset_frame(video, c["bbox"], want, nb, rn["last"])
                row.update({"expected_video_frame_clip_map": want, "detected_video_frame": got})
                if got is not None:
                    row["latency_vs_word_s"] = round(got / FPS - c["word_start_abs"], 4)
                    row["detected_minus_clip_map_frames"] = got - want
                    row["detected_minus_builder_plan_frames"] = got - c["planned_video_frame"]
                    if c["kind"] == "type" and c["finish_with"] == "sentence_end":
                        fin = cnt[min(rn["last"], got + math.ceil(c["type_duration_s"] * FPS) + 3)]
                        done = next((i for i in range(got, min(nb, got + 60)) if cnt[i] >= 0.97 * fin), None)
                        row["complete_minus_sentence_end_s"] = None if done is None else round(done / FPS - c["sentence_end_abs"], 4)
            cues.append(row)
        info.setdefault("clip_frame0", []).append({"beat": b.plan_fragment["beat"]["id"], "video_frame": f0, "time_s": None if f0 is None else f0 / FPS, "ideal_origin_s": b.clip_origin_s,
                                                    "beat_start_frame_exact": bs * FPS, "beat_end_frame_exact": be * FPS, "run_first": rn["first"], "run_last": rn["last"], "held_frames": rn["held_frames"], "skipped_frames": rn["skipped_frames"], "held_at": rn["held_at"]})
    info["cues"] = cues
    lat = [r["latency_vs_word_s"] for r in cues if "latency_vs_word_s" in r and not (r["kind"] == "type" and "complete_minus_sentence_end_s" in r)]
    info["summary"] = {"cues_measured": sum(1 for r in cues if "detected_video_frame" in r), "undetected": [r["id"] for r in cues if r["kind"] != "clear" and r.get("detected_video_frame") is None],
                       "max_abs_frame_error_vs_clip_map": max([abs(r["detected_minus_clip_map_frames"]) for r in cues if "detected_minus_clip_map_frames" in r] or [None]),
                       "latency_min_s": min(lat), "latency_max_s": max(lat), "share_latency_in_0_to_0.4s": sum(1 for v in lat if 0 <= v <= 0.4) / len(lat), "n_latency": len(lat)}
    sel = [r for r in cues if r.get("detected_video_frame")]
    tw, th = 480, 270
    sh = Image.new("RGB", (tw * 3, th * len(sel)), (0, 0, 0))
    dd = ImageDraw.Draw(sh)
    for ri, r in enumerate(sel):
        for ci, n in enumerate((r["detected_video_frame"] - 1, r["detected_video_frame"], r["detected_video_frame"] + 3)):
            sh.paste(M.frame_png(video, n).resize((tw, th)), (ci * tw, ri * th))
            dd.rectangle([ci * tw, ri * th + th - 24, ci * tw + 330, ri * th + th], fill=(0, 0, 0))
            dd.text((ci * tw + 4, ri * th + th - 20), f"{r['beat']}/{r['id']} frame {n} t={n / FPS:.3f}s", fill=(255, 255, 0))
    sh.save(out / "cue_onsets.jpg", quality=88)
    return info


for d in (0.0, 0.5):
    info = run(d)
    R["variants"][f"dissolve_{d}"] = info
    print(json.dumps({k: v for k, v in info.items() if k not in ("cues", "board_runs")}, indent=1)[:2500])
(work / "verify_splice.json").write_text(json.dumps(R, indent=1))
print(json.dumps(R["checks"], indent=1))
print(json.dumps(R["sentence_sources"], indent=1))
