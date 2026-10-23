"""Content-quality gate for the director (after Milestone 4a): runs the five synthetic topics, renders each through the unchanged Hybrid renderer, writes a contact sheet per topic
and the objective phrase and pacing numbers used in the before/after comparison. Reads the repository, writes only under <work>/<label>.

usage: python3 -B -I quality_gate.py <repo_root> <work_root> <label>

Objective proxies (they are NOT a human judgement of meaning): per phrase, words, whether it starts or ends on a function or weak word, whether it is a single non-number word;
per sentence, how many of its content words appear in some card, header or caption anchored inside it ("coverage"); distinct phrases per sentence; font size and slot of every card.
No reviewer ratings are produced or claimed. Word times are synthetic and the offline map has no imagery."""
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

root, work, label = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]
LOOK = sys.argv[4] if len(sys.argv) > 4 else "reference"
os.environ["VIDEOGEN_PAKMAP_CACHE"] = str(work / "cache")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import numpy as np
from PIL import Image, ImageDraw

import measure_render as M
from m4_topics import TOPICS, words_from_script
from explainer.director import DirectorOptions, direct
from explainer.director import lexicon as LX
from explainer.director.segment import norm
from hybrid.generate import generate_hybrid_video
from hybrid.narration import build_sentences
from hybrid.plan import HybridPlan
from pakmap.engine_runner import render_spec

FPS = 30
out = work / label
out.mkdir(parents=True, exist_ok=True)
(work / "media").mkdir(exist_ok=True)
adir = work / "archive_lib"
adir.mkdir(exist_ok=True)
if not (adir / "press.png").exists():
    rs = np.random.RandomState(5)
    pa = np.zeros((450, 800, 3), np.uint8)
    for _ in range(40):
        x0, y0 = rs.randint(0, 700), rs.randint(0, 380)
        pa[y0:y0 + rs.randint(30, 120), x0:x0 + rs.randint(40, 200)] = rs.randint(0, 255, 3)
    Image.fromarray(pa).save(adir / "press.png")
    (adir / "archive.json").write_text(json.dumps([{"file": "press.png", "subjects": ["printing press", "movable metal letters"], "reason": "a picture of a press: what the map cannot show"}]))
WEAK = LX.STOP | {"almost", "simply", "really", "just", "very", "many", "some", "other", "also", "even", "still", "quite", "rather", "thing", "things", "way", "one", "two"}
summary = {}
for name, script in TOPICS.items():
    words, dur = words_from_script(script)
    t0 = time.time()
    r = direct(words, script, DirectorOptions(work_dir=str(out / f"work_{name}"), archive_dir=str(adir) if name == "printing" else None, look=LOOK), duration=dur)
    rep = r.report
    row = {"topic": name, "plan_ok": r.plan is not None, "problems": r.problems, "warnings": r.warnings, "seconds": round(time.time() - t0, 1), "duration_s": dur}
    if r.plan is None:
        summary[name] = row
        continue
    (out / f"plan_{name}.json").write_text(json.dumps(r.plan, indent=1, sort_keys=True).replace(str(out), "<WORK>"))
    (out / f"report_{name}.json").write_text(json.dumps(rep, indent=1, default=str).replace(str(out), "<WORK>"))
    # ---- phrase metrics (objective proxies) ----
    raw_sents = build_sentences(words, script, dur)
    sent_spans = [(s.start, s.end + 0.5) for s in raw_sents]
    texts = []                                    # (beat id, kind, text, anchor time)
    layout_px = []
    for b in rep["selection"]["beats"]:
        det = rep["beat_details"].get(b["id"], {})
        for spec in det.get("cue_specs", []):
            if spec["kind"] in ("card", "header", "caption", "visual", "title") and spec["text"]:
                bw = [w for w in words if b["start"] - 1e-6 <= w[1] < b["end"] - 1e-6]
                a = spec["anchor"]
                t = bw[a["index"]][1] if "index" in a and a["index"] < len(bw) else b["start"]
                texts.append((b["id"], spec["kind"], spec["text"], t, spec["id"]))
        for l in det.get("layout", []):
            if l["kind"] in ("card", "header", "caption", "chip", "visual") and l["font_px"]:
                layout_px.append(l["font_px"])
    cards = [x for x in texts if x[1] == "card"]
    def toks(t):
        return [norm(w) for w in t.split() if norm(w)]
    frag, single, wcount = 0, 0, []
    for _b, _k, text, _t, _i in texts:
        tk = toks(text)
        wcount.append(len(tk))
        if not tk or tk[0] in WEAK or tk[-1] in WEAK:
            frag += 1
        elif len(tk) == 1 and not any(c.isdigit() for c in tk[0]):
            single += 1
    cover = []
    per_sentence = []
    for k, (a, b) in enumerate(sent_spans):
        sw = [norm(w[0]) for w in words if a - 1e-6 <= w[1] < b and norm(w[0])]
        content = {t for t in sw if t not in WEAK and len(t) > 1}
        got = set()
        mine = [x for x in texts if a - 1e-6 <= x[3] < b]
        for x in mine:
            got |= set(toks(x[2]))
        cover.append(len(content & got) / len(content) if content else 1.0)
        per_sentence.append({"sentence": k, "text": raw_sents[k].text[:120], "texts": [f"{x[1]}: {x[2]}" for x in mine]})
    row["phrase_metrics"] = {"texts": len(texts), "cards": len(cards), "mean_words": round(float(np.mean(wcount)), 2) if wcount else 0, "share_3_or_more_words": round(sum(1 for c in wcount if c >= 3) / max(1, len(wcount)), 3),
                             "fragment_rate_edge_function_or_weak_word": round(frag / max(1, len(texts)), 3), "single_non_number_word_rate": round(single / max(1, len(texts)), 3),
                             "content_coverage_mean": round(float(np.mean(cover)), 3), "sentences_with_no_text": sum(1 for p in per_sentence if not p["texts"]), "sentences": len(per_sentence),
                             "distinct_phrases_share": round(len({x[2].lower() for x in texts}) / max(1, len(texts)), 3),
                             "font_px_min": min(layout_px) if layout_px else None, "font_px_mean": round(float(np.mean(layout_px)), 1) if layout_px else None}
    row["per_sentence"] = per_sentence
    # ---- scorecard numbers ----
    P = rep["pacing"]
    starts = [b["start"] for b in rep["selection"]["beats"][1:]]
    at_sentence = [any(abs(s - a) <= 0.3 for a, _b in sent_spans) for s in starts]
    caps = [x for x in texts if x[1] == "caption"]
    kw = rep["metaphors"]["keywords"]
    row["scorecard"] = {"T01_layer_mix_share": P["layer_mix_share"], "T02_median_shot_s": P["shot_length"]["median_s"], "T02_share_2_to_8_s": P["shot_length"]["share_between_2_and_8_s"],
                        "T03_change_windows": P["change_density"], "T03_meaningful_change_windows": P.get("meaningful_change_density"),
                        "peak_occupancy_share": [v.get("peak_occupancy_share") for v in rep["beat_details"].values() if isinstance(v, dict) and "peak_occupancy_share" in v], "T04_longest_still_all_s": max([v.get("still_gap_all_s", 0) for v in rep["beat_details"].values() if isinstance(v, dict)] or [0]), "T04_longest_still_strict_s": max([v.get("still_gap_strict_s", 0) for v in rep["beat_details"].values() if isinstance(v, dict)] or [0]), "T04_longest_still_s": max([v["still_gap_s"] for v in rep["beat_details"].values() if isinstance(v, dict) and "still_gap_s" in v] or [0]),
                        "T05_narrator": P["narrator"], "T07_cuts_at_sentence_start_share": round(sum(at_sentence) / max(1, len(at_sentence)), 3),
                        "T09_captions": {"n": len(caps), "share_8_words_or_fewer": round(sum(1 for c in caps if len(toks(c[2])) <= 8) / max(1, len(caps)), 3)},
                        "T12_metaphor_consistent": rep["metaphors"]["asset_consistent"], "T12_recurrences_per_10min": round(sum(v["count"] for v in kw.values() if v["count"] >= 2) * 600.0 / dur, 1),
                        "T13_story": {k: (v if not isinstance(v, dict) else {x: v.get(x) for x in ("present", "at_s", "trigger", "explicit")}) for k, v in rep["story"].items()}}
    # ---- render and contact sheet ----
    voice = work / "media" / f"voice_{int(math.ceil(dur))}.wav"
    if not voice.exists():
        subprocess.run([sys.executable, "-B", "-I", str(here / "make_audio.py"), str(voice), str(int(math.ceil(dur))), str(work / "media" / "card.png")], check=True)
    (out / f"plan_{name}_abs.json").write_text(json.dumps(r.plan, indent=1, sort_keys=True))
    hp = HybridPlan.load(out / f"plan_{name}_abs.json")
    video = out / f"render_{name}.mp4"
    res = generate_hybrid_video(hp, voice, video, work_dir=out / f"hy_{name}", whisper_words=words, render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw),
                                sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    row["render_ok"] = bool(res.ok)
    if res.ok:
        nb = M.n_frames(video)
        beats = rep["selection"]["beats"]
        tw, th = 640, 360
        ncol = 4
        sh = Image.new("RGB", (tw * ncol, th * math.ceil(len(beats) / ncol)), (0, 0, 0))
        dd = ImageDraw.Draw(sh)
        for k, b in enumerate(beats):
            t = b["start"] + (b["end"] - b["start"]) * 0.85
            im = M.frame_png(video, min(nb - 1, int(t * FPS))).resize((tw, th))
            x, y = (k % ncol) * tw, (k // ncol) * th
            sh.paste(im, (x, y))
            dd.rectangle([x, y, x + 250, y + 14], fill=(0, 0, 0))
            dd.text((x + 3, y + 1), f"{name} {b['id']} t={t:.1f}s {b['kind']}", fill=(255, 255, 0))
        sh.save(out / f"sheet_{name}.jpg", quality=88)
    (out / f"phrases_{name}.txt").write_text("\n".join(f"[{p['sentence']}] {p['text']}\n    " + "\n    ".join(p["texts"] or ["(nothing)"]) for p in per_sentence))
    summary[name] = row
    print(name, "plan", row["plan_ok"], "frag", row["phrase_metrics"]["fragment_rate_edge_function_or_weak_word"], "cov", row["phrase_metrics"]["content_coverage_mean"], "chg", P["change_density"]["share"], "narr", P["narrator"]["share"], flush=True)
(out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
