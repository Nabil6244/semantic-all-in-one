"""Before/after comparison for the content-quality gate. Recomputes every metric from the stored plans and reports of two quality_gate runs with ONE function (so the numbers are
comparable), writes a markdown summary, a JSON file and stacked before/after contact sheets.

usage: python3 -B -I quality_compare.py <repo_root> <work_root> <out_dir> [labelA labelB]      (reads <work_root>/<labelA> and <labelB>; default before and after)
Objective proxies only: they are not a judgement of meaning and no reviewer ratings are produced."""
import json
import re
import sys
from pathlib import Path

root, work, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
import numpy as np
from PIL import Image, ImageDraw

from m4_topics import TOPICS, words_from_script
from explainer.director import lexicon as LX
from explainer.director.segment import norm
from hybrid.narration import build_sentences

out.mkdir(parents=True, exist_ok=True)
WEAK = LX.STOP | LX.WEAK
ALLOWED_LEAD = LX.LEADING_OK | LX.CLAUSE_START_OK


def toks(t):
    return [norm(w) for w in t.split() if norm(w)]


def metrics(label, name):
    d = work / label
    plan = json.loads((d / f"plan_{name}.json").read_text())
    rep = json.loads((d / f"report_{name}.json").read_text())
    script = TOPICS[name]
    words, dur = words_from_script(script)
    raw = build_sentences(words, script, dur)
    spans = [(s.start, s.end + 0.5) for s in raw]
    texts = []                              # (kind, text, time, beat)
    px = []
    for b in rep["selection"]["beats"]:
        det = rep["beat_details"].get(b["id"], {})
        bw = [w for w in words if b["start"] - 1e-6 <= w[1] < b["end"] - 1e-6]
        for spec in det.get("cue_specs", []):
            if spec["kind"] in ("card", "header", "caption", "visual", "title") and spec["text"]:
                a = spec["anchor"]
                t = bw[a["index"]][1] if "index" in a and a["index"] < len(bw) else b["start"]
                texts.append((spec["kind"], spec["text"], t, b["id"]))
        for l in det.get("layout", []):
            if l["kind"] in ("card", "header", "caption", "chip", "visual") and l["font_px"]:
                px.append(l["font_px"])
    for pb in plan["beats"]:                # map beats: marker labels, place fills and whole-phrase captions count as text too
        for l in pb.get("layers", []):
            txt = l.get("label") or l.get("text") or l.get("place")
            if txt:
                texts.append(("map_" + l["type"], txt, l["t"], pb["id"]))
    for pb in plan["beats"]:                # archive beats: the picture's reason is not narration text; only its subject counts as covered
        pass
    shown = [x for x in texts if x[0] in ("card", "header", "caption", "visual", "title")]
    n = len(shown)
    trailing = sum(1 for x in shown if toks(x[1]) and toks(x[1])[-1] in WEAK)
    leading = sum(1 for x in shown if toks(x[1]) and toks(x[1])[0] in WEAK and toks(x[1])[0] not in ALLOWED_LEAD)
    single = sum(1 for x in shown if len(toks(x[1])) == 1)
    wc = [len(toks(x[1])) for x in shown]
    cover, none = [], 0
    for a, b in spans:
        sw = [norm(w[0]) for w in words if a - 1e-6 <= w[1] < b and norm(w[0])]
        content = {t for t in sw if t not in WEAK and len(t) > 1}
        got = set()
        mine = [x for x in texts if a - 1e-6 <= x[2] < b]
        for x in mine:
            got |= set(toks(x[1]))
        cover.append(len(content & got) / len(content) if content else 1.0)
        none += 0 if mine else 1
    sc = json.loads((d / "summary.json").read_text())[name]["scorecard"]
    return {"texts": n, "mean_words": round(float(np.mean(wc)), 2) if wc else 0, "share_3_plus_words": round(sum(1 for c in wc if c >= 3) / max(1, n), 3),
            "trailing_function_or_weak_word": trailing, "leading_function_word_not_allowlisted": leading, "single_word": single,
            "content_coverage_mean": round(float(np.mean(cover)), 3), "sentences_without_any_text": none, "sentences": len(spans),
            "distinct_share": round(len({x[1].lower() for x in shown}) / max(1, n), 3), "font_px_min": min(px) if px else None, "font_px_mean": round(float(np.mean(px)), 1) if px else None,
            "scorecard": sc, "hybrid_validate_warnings": len(rep.get("hybrid_validate", {}).get("warnings", [])), "cards": sum(1 for x in shown if x[0] == "card"),
            "captions": sum(1 for x in shown if x[0] == "caption"), "headers": sum(1 for x in shown if x[0] == "header"), "events": len(rep.get("change_events_s", [])) or None}


res = {}
LA, LB = (sys.argv[4], sys.argv[5]) if len(sys.argv) > 5 else ("before", "after")
lines = ["| Topic | | texts | mean words | trailing function word | leading function word (not allow-listed) | single word | content coverage | sentences with no text | change windows (all cues) | meaningful change windows | peak occupancy mean / min | narrator share / longest absence | min / mean px |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for name in TOPICS:
    res[name] = {}
    for label in (LA, LB):
        m = metrics(label, name)
        res[name][label] = m
        sc = m["scorecard"]
        lines.append(f"| {name} | {label} | {m['texts']} | {m['mean_words']} | {m['trailing_function_or_weak_word']} | {m['leading_function_word_not_allowlisted']} | {m['single_word']} | {m['content_coverage_mean']} | {m['sentences_without_any_text']}/{m['sentences']} | "
                     f"{sc['T03_change_windows']['share']} ({sc['T03_change_windows']['windows_with_a_change']}/{sc['T03_change_windows']['windows_2s']}) | " + (f"{sc['T03_meaningful_change_windows']['share']} ({sc['T03_meaningful_change_windows']['windows_with_a_change']}/{sc['T03_meaningful_change_windows']['windows_2s']})" if sc.get('T03_meaningful_change_windows') else "n/a") + f" | {round(float(np.mean(sc['peak_occupancy_share'])),3) if sc.get('peak_occupancy_share') else 'n/a'} / {min(sc['peak_occupancy_share']) if sc.get('peak_occupancy_share') else 'n/a'} | {sc['T05_narrator']['share']} / {sc['T05_narrator']['longest_absence_s']} s | {m['font_px_min']} / {m['font_px_mean']} |")
(out / "quality_before_after.json").write_text(json.dumps(res, indent=1))
(out / "quality_before_after.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
# phrase listings
for name in TOPICS:
    for label in (LA, LB):
        src = work / label / f"phrases_{name}.txt"
        if src.exists():
            (out / f"phrases_{name}_{label}.txt").write_text(src.read_text())
# stacked sheets
for name in TOPICS:
    a, b = work / LA / f"sheet_{name}.jpg", work / LB / f"sheet_{name}.jpg"
    if a.exists() and b.exists():
        ia, ib = Image.open(a), Image.open(b)
        W = max(ia.width, ib.width)
        sh = Image.new("RGB", (W, ia.height + ib.height + 40), (30, 30, 30))
        d = ImageDraw.Draw(sh)
        d.text((8, 4), f"{name}: {LA}", fill=(255, 255, 0))
        sh.paste(ia, (0, 20))
        d.text((8, ia.height + 24), f"{name}: {LB}", fill=(0, 255, 255))
        sh.paste(ib, (0, ia.height + 40))
        sh.save(out / f"sheet_{name}_before_after.jpg", quality=86)
