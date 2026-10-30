"""Score an Explainer plan (and optionally its render) against the five-reference targets.

See docs/explainer/reference_targets.md for where the ranges come from.
"""
import argparse
import json
import statistics as st
import subprocess


def beat_kind(b):
    p = b.get("purpose", "")
    sup = b.get("support") or {}
    clips = [c.get("asset", "") for c in (b.get("footage") or {}).get("clips", [])]
    if "picture" in p or "archiv" in p or (p.startswith("explainer footage") and any(a.startswith("stock_image") for a in clips)):
        return "archival"
    if "cartoon" in p:
        return "cartoon"
    if "board" in p:
        return "board"
    if b.get("mode", "").startswith("map"):
        return "map"
    return "archival" if str(sup.get("asset", "")).startswith("stock_image") else b.get("mode", "other")


def sentence_starts(words, offset):
    """Clause starts: after end punctuation, or after a pause of 0.3 s or more (timings carry no punctuation)."""
    starts, prev = [], None
    for w in words:
        if prev is None or prev[0].rstrip().endswith((".", "?", "!")) or w[1] - prev[2] >= 0.3:
            starts.append(w[1] - offset)
        prev = w
    return starts


def video_change(path):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "fps=5,scale=160:90,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=900)
    a = np.frombuffer(r.stdout, np.uint8).reshape(-1, 90, 160).astype(float)
    d = np.abs(np.diff(a, axis=0)).mean((1, 2))
    n = len(d) // 10
    changed = sum(d[i * 10:(i + 1) * 10].max() > 1.0 for i in range(n))
    run = best = 0
    for x in d:
        run = run + 1 if x < 0.25 else 0
        best = max(best, run)
    return changed / max(n, 1), best / 5


def score(plan, words=None, offset=0.0, video=None):
    beats = plan["beats"]
    total = beats[-1]["end"]
    lens = [b["end"] - b["start"] for b in beats]
    share = {}
    for b in beats:
        k = beat_kind(b)
        share[k] = share.get(k, 0) + (b["end"] - b["start"]) / total * 100
    caps = [l["text"] for b in beats for l in b.get("layers", []) if l.get("type") == "caption"]
    out = []

    def add(cid, name, val, ok, note=""):
        out.append((cid, name, val, "PASS" if ok else "FAIL", note))

    med = st.median(lens)
    add("R01", "median shot s", round(med, 2), 4.0 <= med <= 5.9)
    cpm = len(beats) / total * 60
    add("R02", "cuts per minute", round(cpm, 1), 7.8 <= cpm <= 12.6)
    add("R03", "longest shot s", round(max(lens), 1), max(lens) <= 20)
    add("R04", "map share %", round(share.get("map", 0)), 20 <= share.get("map", 0) <= 30)
    add("R05", "board share %", round(share.get("board", 0)), 25 <= share.get("board", 0) <= 45)
    sc = share.get("cartoon", 0)
    add("R06", "scene share %", round(sc), 25 <= sc <= 35)
    ar = share.get("archival", 0)
    add("R07", "archival share %", round(ar), 8 <= ar <= 12)
    if caps:
        short = sum(len(c.split()) <= 8 for c in caps) / len(caps)
        add("R11", "captions <= 8 words", f"{short:.0%}", short >= 0.8)
    if words:
        ss = sentence_starts(words, offset)
        near = sum(any(abs(b["start"] - s) <= 0.5 for s in ss) for b in beats[1:]) / max(len(beats) - 1, 1)
        add("R10", "cuts near a sentence start", f"{near:.0%}", near >= 0.5)
    if video:
        frac, static = video_change(video)
        add("R08", "2 s windows with change", f"{frac:.0%}", frac >= 0.95, "loose: camera drift counts")
        add("R09", "longest static s", static, static <= 3)
    return out, share


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--video")
    ap.add_argument("--words")
    ap.add_argument("--offset", type=float, default=0.0)
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    words = json.load(open(a.words))["words"] if a.words else None
    rows, share = score(plan, words, a.offset, a.video)
    for r in rows:
        print("%-4s %-28s %-8s %s %s" % r)
    print("share:", {k: round(v) for k, v in share.items()})
    p = sum(r[3] == "PASS" for r in rows)
    print(f"{p}/{len(rows)} measured checks pass")
