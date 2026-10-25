"""Run the word-timed board builder and the splice helper on REAL word timings (a transcription of a voice-over), and measure how real
Whisper punctuation and word-time error change cue landing. Reads the repository, writes only under <work_root>.

usage: python3 -B -I verify_real_voiceover.py <repo_root> <work_root> <audio> <words.json> [window_start_s]

The cues are derived from the transcript itself (no wording is invented): a typed phrase on the 2nd word of the first sentence of the window, a
pop on the longest word of the second sentence, a clear at the next sentence start, a title on the longest word of the third sentence, and a
typed phrase that finishes with the last sentence. The window is about 3 sentences (at most 14 s), starting at a sentence start.
What is measured:
  * do the sentence-boundary sources agree on real words (Hybrid's pause rule, Hybrid's build_sentences, Whisper's punctuation)?
  * where does every cue land in a real render, against the clip map and against the transcribed word time (as in the synthetic tests)?
  * how good are the transcribed word times themselves? For every word in the window, the first rise of the audio's energy envelope near the
    word's start is compared with Whisper's start. This is a rough proxy (word-initial sounds and coarticulation differ), reported as such.
"""
import copy
import json
import math
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

root, work, audio, words_json = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve(), Path(sys.argv[4]).resolve()
win_arg = float(sys.argv[5]) if len(sys.argv) > 5 else None
os.environ["VIDEOGEN_PAKMAP_CACHE"] = str(work / "cache")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image, ImageDraw

import measure_render as M
from explainer.board import Cue, resolve_cues, splice_board_beats
from hybrid.generate import generate_hybrid_video
from hybrid.narration import build_sentences
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

FPS = 30
work.mkdir(parents=True, exist_ok=True)
data = json.loads(words_json.read_text())
RAW = [tuple(w) for w in data["raw_words"]]
APP = [tuple(w) for w in data["app_style_words"]]
total = float(data["duration_s"])
sents = build_sentences(APP, duration=total)                      # Hybrid's own sentence builder (pause rule: no script text)
S = [(s.start, s.end) for s in sents]

# ---- choose the window: 3 consecutive Hybrid sentences, at most 14 s, starting near window_start ----
def pick():
    want = win_arg if win_arg is not None else total * 0.25
    best = None
    for k in range(0, len(sents) - 2):
        a, c = sents[k], sents[k + 2]
        if c.end - a.start <= 14.0 and a.start >= 2.5:
            if best is None or abs(a.start - want) < abs(sents[best].start - want):
                best = k
    return best

k = pick()
if k is None:
    sys.exit("no window of three Hybrid sentences within 14 s was found in this transcript")
s1, s2, s3 = sents[k], sents[k + 1], sents[k + 2]
t_lo, t_hi = s1.start - 2.0, s3.end + 2.5
frame = lambda s: round(s * FPS) / FPS
B_START, B_END = frame(s1.start - 0.25), frame(s3.end + 0.3)
print(f"window: sentences {k}..{k + 2}, beat {B_START:.2f}-{B_END:.2f} s (of {total:.1f} s)")

def words_in(sent, wlist):
    return [w for w in wlist if sent.start - 0.01 <= w[1] <= sent.end + 0.01]

w1, w2, w3 = words_in(s1, APP), words_in(s2, APP), words_in(s3, APP)
longest = lambda ws: max(ws, key=lambda w: len(w[0]))
anchor_type = w1[1] if len(w1) > 1 else w1[0]
pop_w, title_w = longest(w2), longest(w3)
fin_anchor = w3[-3] if len(w3) >= 3 else w3[0]
fin_text = " ".join(w[0] for w in w3[-3:])
CUES = [Cue("r1_type", "type", {"word": anchor_type[0], "occurrence": 1}, text=f"{anchor_type[0]} {w1[w1.index(anchor_type) + 1][0] if w1.index(anchor_type) + 1 < len(w1) else ''}".strip()),
        Cue("r2_pop", "pop", {"word": pop_w[0]}, text=pop_w[0], role="blue"),
        Cue("r3_clear", "clear", {"word": pop_w[0]}, at="next_sentence"),
        Cue("r4_title", "title", {"word": title_w[0]}, text=title_w[0].upper()),
        Cue("r5_type_end", "type", {"word": fin_anchor[0]}, text=fin_text, finish_with="sentence_end")]

# ---- the audio for the render: a cut around the window, times shifted so the cut starts at 0 ----
shift = max(0.0, frame(t_lo))
cut = work / "voice_cut.wav"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{shift}", "-t", f"{t_hi - shift:.3f}", "-i", str(audio), "-vn", "-ac", "1", "-ar", "48000", str(cut)], check=True, timeout=1800)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(cut)], capture_output=True, text=True, timeout=1800).stdout)
dur = math.floor(dur * FPS) / FPS
sh = lambda ws: [(w[0], round(w[1] - shift, 3), round(w[2] - shift, 3)) for w in ws if w[2] - shift > 0 and w[1] - shift < dur]
RAWc, APPc = sh(RAW), sh(APP)
Sc = [(a - shift, b - shift) for a, b in S if b - shift > 0 and a - shift < dur]
bs, be = round(B_START - shift, 4), round(B_END - shift, 4)
card = work / "card.png"
Image.new("RGB", (800, 500), (230, 225, 210)).save(card)

# ---- 1. do the sentence sources agree on real words? ----
fx = json.loads((root / "test_hybrid_app_plan.json").read_text())
b1 = copy.deepcopy(next(b for b in fx["beats"] if b["id"] == "b1")); b1.update(start=0, end=bs); b1["layers"][1]["until"] = "beat_end"
PLAN = {"version": 1, "duration": dur, "settings": {"dissolve_s": 0.0, "return_grace_s": 0.8, "drift_pct_per_s": 0.5}, "beats": [
    b1, {"id": "b2", "mode": "footage", "start": bs, "end": be, "purpose": "placeholder", "footage": {"clips": [{"asset": str(card)}]}},
    {"id": "b3", "mode": "map", "start": be, "end": dur, "purpose": "close", "camera": [], "layers": []}]}
variants = {"raw_punctuated": (RAWc, None), "app_words_pause_fallback": (APPc, None), "app_words_hybrid_sentences": (APPc, Sc)}
onsets, src = {}, {}
for name, (w, sn) in variants.items():
    row = {}
    for r in resolve_cues(CUES, w, bs, be, bs, FPS, be - bs, sn):
        row[r.cue.id] = (None if r.onset_abs is None else round(r.onset_abs, 4), r.sentence_source, r.problems)
    onsets[name] = row
base = {k2: v[0] for k2, v in onsets["app_words_hybrid_sentences"].items()}
agree = {n: {"source": sorted({v[1] for v in row.values()}), "equal_to_hybrid_sentences": {k2: v[0] for k2, v in row.items()} == base,
             "differences_ms": {k2: (None if v[0] is None or base[k2] is None else round((v[0] - base[k2]) * 1000)) for k2, v in row.items() if v[0] != base[k2]},
             "problems": [p for v in row.values() for p in v[2]]} for n, row in onsets.items()}

# ---- 2. word-time quality: audio energy onset near each word start ----
with wave.open(str(cut)) as wf:
    sig = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(float) / 32768
    sr = wf.getframerate()
hop = int(0.005 * sr)
env = np.array([np.sqrt(np.mean(sig[i:i + hop * 2] ** 2)) for i in range(0, len(sig) - hop * 2, hop)])
noise = np.percentile(env, 10)
def energy_onset(t0):
    a, b = max(0, int((t0 - 0.25) / 0.005)), min(len(env) - 1, int((t0 + 0.25) / 0.005))
    seg = env[a:b]
    if len(seg) < 4:
        return None
    thr = max(3 * noise, 0.2 * seg.max())
    for i, v in enumerate(seg):
        if v >= thr and (i == 0 or seg[i - 1] < thr):
            return (a + i) * 0.005
    return None
errs = []
for w, st, en in APPc:
    if bs <= st <= be:
        o = energy_onset(st)
        if o is not None and abs(o - st) < 0.25:
            errs.append((o - st) * 1000)
quality = {"words_compared": len(errs), "mean_ms": round(float(np.mean(errs))), "median_ms": round(float(np.median(errs))), "std_ms": round(float(np.std(errs))),
           "p90_abs_ms": round(float(np.percentile(np.abs(errs), 90))), "max_abs_ms": round(float(np.max(np.abs(errs)))),
           "note": "audio energy onset minus Whisper start, a rough proxy; positive = the audio rises after the transcribed start"} if errs else {"words_compared": 0}

# ---- 3. splice + render + read back, both dissolve modes ----
validate_fn = lambda p: validate_plan(HybridPlan.from_dict(p))
R = {"window": {"hybrid_sentence_index": k, "beat_in_cut_s": [bs, be], "cut_offset_s": shift, "cut_duration_s": dur, "hybrid_sentences_in_total": len(sents)},
     "cues": [{"id": c.id, "kind": c.kind, "anchor": c.anchor, "text": c.text} for c in CUES], "sentence_sources": agree, "word_time_quality": quality, "variants": {}}
for d, tail in ((0.0, 0), (0.5, 0), (0.0, 2)):
    tag = f"d{str(d).replace('.', '_')}_tail{tail}"
    out = work / f"variant_{tag}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    res = splice_board_beats(PLAN, [{"beat_id": "b2", "cues": CUES}], APPc, out, sentences=Sc, dissolve_s=d, instrument=True, validate=validate_fn, tail_frames=tail)
    (out / "spliced_plan.json").write_text(json.dumps(res.plan, indent=1))
    hp = HybridPlan.load(out / "spliced_plan.json")
    video = out / "render.mp4"
    t0 = time.time()
    g = generate_hybrid_video(hp, cut, video, work_dir=out / "work", whisper_words=APPc, render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw),
                              sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    info = {"dissolve_s": d, "tail_frames": tail, "notes": res.notes, "render_ok": bool(g.ok), "render_errors": list(g.errors or []), "render_seconds": round(time.time() - t0, 1)}
    if g.ok:
        runs, nb = M.board_runs(video)
        info.update({"video_frames": nb, "board_runs": [{k: v for k, v in r.items() if k != "frame_of_code"} for r in runs]})
        b = res.builds[0]
        rn = runs[0] if runs else None
        rows = []
        for c in b.manifest()["cues"]:
            row = {"id": c["id"], "kind": c["kind"], "word": c["word"], "word_start_abs": c["word_start_abs"], "planned_onset_abs": c["onset_abs"], "first_clip_frame": c["first_frame"],
                   "sentence_source": c["sentence_source"], "problems": c["problems"]}
            if rn and c["kind"] != "clear" and c.get("bbox") and c["first_frame"] in rn["frame_of_code"]:
                want = rn["frame_of_code"][c["first_frame"]]
                got, cnt = M.onset_frame(video, c["bbox"], want, nb, rn["last"])
                row.update({"expected_video_frame_clip_map": want, "detected_video_frame": got})
                if got is not None:
                    row["latency_vs_word_s"] = round(got / FPS - c["word_start_abs"], 4)
                    row["detected_minus_clip_map_frames"] = got - want
                    row["detected_minus_builder_plan_frames"] = got - c["planned_video_frame"]
                    if c["kind"] == "type" and c["finish_with"] == "sentence_end":
                        fin = cnt[min(rn["last"], got + math.ceil(c["type_duration_s"] * FPS) + 3)]
                        done = next((i for i in range(got, min(nb, got + 90)) if cnt[i] >= 0.97 * fin), None)
                        row["complete_minus_sentence_end_s"] = None if done is None else round(done / FPS - c["sentence_end_abs"], 4)
            rows.append(row)
        info["cues_measured"] = rows
        lat = [r["latency_vs_word_s"] for r in rows if "latency_vs_word_s" in r and "complete_minus_sentence_end_s" not in r]
        info["summary"] = {"runs": len(runs), "run_held_frames": [r["held_frames"] for r in runs], "run_held_at": [r["held_at"] for r in runs], "run_skipped_frames": [r["skipped_frames"] for r in runs],
                           "undetected": [r["id"] for r in rows if r["kind"] != "clear" and r.get("detected_video_frame") is None and not r["problems"]],
                           "max_abs_frame_error_vs_clip_map": max([abs(r["detected_minus_clip_map_frames"]) for r in rows if "detected_minus_clip_map_frames" in r] or [None]),
                           "max_abs_frame_error_vs_builder_plan": max([abs(r["detected_minus_builder_plan_frames"]) for r in rows if "detected_minus_builder_plan_frames" in r] or [None]),
                           "latency_min_s": min(lat) if lat else None, "latency_max_s": max(lat) if lat else None}
        sel = [r for r in rows if r.get("detected_video_frame")]
        tw, th = 480, 270
        sheet = Image.new("RGB", (tw * 3, th * len(sel)), (0, 0, 0))
        dd = ImageDraw.Draw(sheet)
        for ri, r in enumerate(sel):
            for ci, n in enumerate((r["detected_video_frame"] - 1, r["detected_video_frame"], r["detected_video_frame"] + 3)):
                sheet.paste(M.frame_png(video, n).resize((tw, th)), (ci * tw, ri * th))
                dd.rectangle([ci * tw, ri * th + th - 24, ci * tw + 330, ri * th + th], fill=(0, 0, 0))
                dd.text((ci * tw + 4, ri * th + th - 20), f"{r['id']} frame {n} t={n / FPS:.3f}s", fill=(255, 255, 0))
        sheet.save(out / "cue_onsets.jpg", quality=88)
    R["variants"][f"dissolve_{d}_tail_{tail}"] = info
    print(json.dumps({k2: v for k2, v in info.items() if k2 not in ("cues_measured", "board_runs")}, indent=1)[:1800])
(work / "verify_real_voiceover.json").write_text(json.dumps(R, indent=1))
print(json.dumps({"sentence_sources": agree, "word_time_quality": quality}, indent=1))
