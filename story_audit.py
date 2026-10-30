"""Quality gates for story videos: works on a rendered mp4 and on a plan.

    still_stretches(video, thresh, min_len)   spans where the picture barely changes (grain/dust ignored)
    flash_frames(video)                       abrupt full-frame luminance flashes (not slow fades, not dips)
    variety_report(plan_or_shots)             shot count / lengths / transitions / tier mix / character continuity
    sync_report(aligned, words)               how many of each scene's words fall inside its window
    contact_sheet(video, every_s, out)        one image, a frame every N seconds
    cut_sheets(video, cuts, out)              frames just before / on / after each cut
    audit_all(...)                            pass/fail summary with the thresholds in THRESHOLDS

Only numpy, Pillow and ffmpeg. Nothing here renders or generates; it only reads.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

THRESHOLDS: Dict[str, float] = {
    "still_max_s": 3.0,        # no stretch of near-identical picture longer than this
    "shot_max_s": 6.0,         # no shot longer than this
    "sync_min_pct": 90.0,      # share of matched words that fall inside their scene window
    "flash_max": 0,            # flash frames at cuts tolerated
    "repeat_transition_max": 3,  # the same transition this many times in a row is a failure
    "tier_idle_max_pct": 35.0,  # share of shots with no real motion (tier 0/"still")
}

# Calibrated on the old static hrt video (stills with a 10% Ken Burns zoom): mean grey diff per 0.5 s on a 64x36 blurred frame has median 0.85
# and p90 1.9 there (cuts are 50+). A picture that really moves (character, camera, live clip) is expected well above 1.5, so the zoom drift
# of a still counts as still. Raise/lower via still_stretches(thresh=...).
STILL_DIFF = 1.5
_W, _H = 64, 36


# ------------------------------------------------------------------ ffmpeg helpers

def _probe_duration(video: "str | Path") -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip() or 0.0)
    except Exception:       # noqa: BLE001
        return 0.0


def _gray_frames(video: "str | Path", fps: float, w: int = _W, h: int = _H, start: float = 0.0,
                 end: Optional[float] = None) -> Iterable[np.ndarray]:
    """Yields float32 (h, w) grey frames at `fps`, already area-downscaled (that is the blur that hides grain and dust)."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(video)]
    if end is not None:
        cmd += ["-t", f"{max(end - start, 0.05):.3f}"]
    cmd += ["-vf", f"fps={fps},scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = w * h
    try:
        while True:
            buf = p.stdout.read(size)
            if not buf or len(buf) < size:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(h, w).astype(np.float32)
    finally:
        try:
            p.stdout.close()
        except Exception:       # noqa: BLE001
            pass
        p.kill()
        p.wait(timeout=7200)


def _blur(a: np.ndarray) -> np.ndarray:
    """3x3 box blur (edge-replicated): grain and dust specks vanish, shapes stay."""
    p = np.pad(a, 1, mode="edge")
    return sum(p[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3)) / 9.0


# ------------------------------------------------------------------ one decode for both video checks

def scan_video(video: "str | Path", fps: float = 30.0, sample_fps: float = 4.0, step: int = 2) -> dict:
    """ONE ffmpeg decode at `fps` (small grey frames) feeding both frame_diffs and flash_frames: {"diffs": [(t, d)], "lums": [mean grey per frame]}."""
    every = max(int(round(fps / sample_fps)), 1)
    lums: List[float] = []
    diffs: List[Tuple[float, float]] = []
    buf: List[np.ndarray] = []
    for i, f in enumerate(_gray_frames(video, fps)):
        lums.append(float(f.mean()))
        if i % every == 0:
            b = _blur(f)
            buf.append(b)
            if len(buf) > step:
                diffs.append((i / fps, float(np.abs(b - buf.pop(0)).mean())))
    return {"diffs": diffs, "lums": lums, "fps": fps}


# ------------------------------------------------------------------ (a) still stretches

def frame_diffs(video: "str | Path", sample_fps: float = 4.0, step: int = 2) -> List[Tuple[float, float]]:
    """[(t, mean abs grey difference between the frame at t and the one `step` samples earlier)], t in seconds. step=2 at 4 fps = 0.5 s apart."""
    out: List[Tuple[float, float]] = []
    buf: List[np.ndarray] = []
    for i, f in enumerate(_gray_frames(video, sample_fps)):
        b = _blur(f)
        buf.append(b)
        if len(buf) > step:
            out.append((i / sample_fps, float(np.abs(b - buf.pop(0)).mean())))
    return out


def still_stretches(video: "str | Path", thresh: float = STILL_DIFF, min_len: float = 3.0, sample_fps: float = 4.0,
                    diffs: Optional[List[Tuple[float, float]]] = None) -> List[dict]:
    """Spans [{start, end, length, mean_diff}] where the picture barely changes for at least min_len seconds. A slow Ken Burns zoom on a
    still counts as still (it is the thing being hunted); a hard cut between two stills ends one stretch and starts the next.
    `diffs` lets a caller reuse frame_diffs() output."""
    d = diffs if diffs is not None else frame_diffs(video, sample_fps)
    half = 0.5            # a diff at t compares t-0.5 .. t: the quiet span starts half a second earlier
    spans: List[dict] = []
    cur: List[Tuple[float, float]] = []

    def close():
        if cur:
            a, b = cur[0][0] - half, cur[-1][0]
            if b - a >= min_len:
                spans.append({"start": round(max(a, 0.0), 2), "end": round(b, 2), "length": round(b - a, 2),
                              "mean_diff": round(float(np.mean([x[1] for x in cur])), 3)})
        cur.clear()

    gap = 1.5 / sample_fps
    last_t = None
    for t, v in d:
        if v < thresh and (last_t is None or t - last_t <= gap or not cur):
            cur.append((t, v))
        else:
            close()
            if v < thresh:
                cur.append((t, v))
        last_t = t
    close()
    return spans


# ------------------------------------------------------------------ flash frames

def flash_frames(video: "str | Path", fps: float = 30.0, jump: float = 40.0, back_within: int = 6, settle: float = 18.0,
                 max_frames: Optional[int] = None, lums: Optional[List[float]] = None) -> List[dict]:
    """Abrupt full-frame luminance flashes: the mean grey jumps by >= `jump` in ONE frame and falls back to within `settle` of the level it
    came from inside `back_within` frames (0.2 s at 30 fps). A hard cut to a different picture does not return, a slow fade is not one frame,
    so neither counts. -> [{t, delta, kind: "white"|"black"}]."""
    if lums is None:
        lums = []
        for i, f in enumerate(_gray_frames(video, fps, 32, 18)):
            lums.append(float(f.mean()))
            if max_frames and i >= max_frames:
                break
    out: List[dict] = []
    i = 1
    n = len(lums)
    while i < n:
        d = lums[i] - lums[i - 1]
        if abs(d) >= jump:
            base = lums[i - 1]
            for k in range(i + 1, min(i + 1 + back_within, n)):
                if abs(lums[k] - base) <= settle:
                    out.append({"t": round(i / fps, 3), "delta": round(d, 1), "kind": "white" if d > 0 else "black"})
                    i = k
                    break
        i += 1
    return out


# ------------------------------------------------------------------ (b) variety (plan side)

def _shots_of(plan_or_shots: Any) -> List[dict]:
    if isinstance(plan_or_shots, dict):
        for key in ("shots", "rows", "scenes"):
            if isinstance(plan_or_shots.get(key), list):
                return [s for s in plan_or_shots[key] if isinstance(s, dict)]
        return []
    return [s for s in (plan_or_shots or []) if isinstance(s, dict)]


def _f(d: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        try:
            if d.get(k) not in (None, ""):
                return float(d[k])
        except (TypeError, ValueError):
            pass
    return default


def variety_report(plan_or_shots: Any) -> dict:
    """Shots count / average / max length, repeated transitions, tier mix, character continuity. Pure data, no files."""
    shots = _shots_of(plan_or_shots)
    lens = [max(_f(s, "end", "end_time") - _f(s, "start", "start_time"), 0.0) for s in shots]
    trans = [str(s.get("transition_in") or "cut").lower() for s in shots]
    run, worst, worst_name = 1, 1 if shots else 0, ""
    for i in range(1, len(trans)):
        run = run + 1 if trans[i] == trans[i - 1] and trans[i] != "cut" else 1
        if run > worst:
            worst, worst_name = run, trans[i]
    tiers: Dict[str, int] = {}
    for s in shots:
        k = str(s.get("motion_tier", "") if s.get("motion_tier") is not None else "")
        tiers[k or "?"] = tiers.get(k or "?", 0) + 1
    idle = sum(v for k, v in tiers.items() if k.lower() in ("0", "still", "static", "none"))
    chars = [str(s.get("character") or "") for s in shots]
    named = [c for c in chars if c and c.lower() not in ("none", "no", "false")]
    protagonist = ""
    if isinstance(plan_or_shots, dict):
        protagonist = str(plan_or_shots.get("protagonist") or "")
    switches = sum(1 for a, b in zip(chars, chars[1:]) if a and b and a != b and a.lower() != "none" and b.lower() != "none")
    return {
        "shots": len(shots),
        "total_s": round(sum(lens), 2),
        "avg_len_s": round(sum(lens) / len(lens), 2) if lens else 0.0,
        "max_len_s": round(max(lens), 2) if lens else 0.0,
        "over_max": [(s.get("shot_id"), round(l, 2)) for s, l in zip(shots, lens) if l > THRESHOLDS["shot_max_s"]],
        "transitions": {t: trans.count(t) for t in sorted(set(trans))},
        "max_transition_run": worst, "max_transition_run_name": worst_name,
        "tier_mix": tiers, "idle_pct": round(100.0 * idle / len(shots), 1) if shots else 0.0,
        "with_character": len(named), "character_pct": round(100.0 * len(named) / len(shots), 1) if shots else 0.0,
        "protagonist": protagonist,
        "character_switches": switches,
        "characters": sorted(set(named)),
    }


# ------------------------------------------------------------------ (c) sync

_STRIP = re.compile(r"[़ँंःा-्‌‍]")   # nukta, chandrabindu, anusvara, visarga, matras, virama, joiners
_NONWORD = re.compile(r"[^\w]+", re.UNICODE)


def phon_key(word: str) -> str:
    """A spelling-tolerant key: NFKD-fold Latin, drop Devanagari vowel signs/nasal marks/virama, lowercase. Whisper spells Hindi differently
    from the script (ट्रैकिंग / ट्रकिन), so only the consonant skeleton is compared."""
    w = unicodedata.normalize("NFC", str(word)).lower()
    w = _STRIP.sub("", w)
    w = unicodedata.normalize("NFKD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return _NONWORD.sub("", w)


def _tokens(text: str) -> List[str]:
    return [t for t in (_NONWORD.sub(" ", str(text or "")).split()) if t]


def sync_report(aligned: Sequence[dict], words: Sequence[Sequence[Any]], tol: float = 0.35, min_ratio: float = 0.6) -> dict:
    """aligned: rows with script_segment + start_time/end_time (or start/end); words: [[w, start, end], ...].
    The script words of all scenes are matched in order against the transcript on a phonetic key; a matched word is 'inside' when its time lies in
    its own scene's window (+-tol s). -> {pct_inside, matched, inside, scenes: [{scene, words, matched, inside, pct}], worst}. Uses story_align's
    own report when that module offers one (story_align.sync_report), so both agree."""
    try:        # prefer the alignment module's own report when it has one
        import story_align
        fn = getattr(story_align, "sync_report", None)
        if callable(fn):
            return fn(aligned, words)
    except Exception:       # noqa: BLE001
        pass
    key_fn, akey_fn, sim_fn = phon_key, None, None
    try:        # Agent A's richer phonetic key + similarity (maps Latin spellings onto Devanagari) rate the fuzzy pairs; exact blocks use my key
        import story_align as _sa
        akey_fn, sim_fn = _sa.phon_key, getattr(_sa, "_key_sim", None)
    except Exception:       # noqa: BLE001
        pass
    rows = []
    for r in aligned:      # one sentence over several pictures (the CSV repeats its text on each row): one scene spanning those rows, not several short ones each owed all the words
        key = " ".join(str(r.get("script_segment", "")).lower().split())
        if rows and key and key == rows[-1][0]:
            rows[-1][1]["end_time"] = _f(r, "end_time", "end", default=_f(r, "start_time", "start"))
            rows[-1][1].pop("end", None)
            rows[-1][1]["scene_number"] = f"{rows[-1][2]}-{r.get('scene_number', '')}"
        else:
            rows.append([key, dict(r), r.get("scene_number", len(rows) + 1)])
    rows = [x[1] for x in rows]
    wins = []
    for i, r in enumerate(rows):
        s = _f(r, "start_time", "start")
        e = _f(r, "end_time", "end", default=s)
        if i + 1 < len(rows):         # a scene ends where the next begins (pauses belong to the scene before)
            e = max(e, _f(rows[i + 1], "start_time", "start"))
        wins.append((s, e))
    stoks: List[Tuple[int, str]] = []
    for i, r in enumerate(rows):
        for t in _tokens(r.get("script_segment", "")):
            stoks.append((i, key_fn(t)))
    wkeys = [key_fn(w[0]) for w in words]
    a = [k for _, k in stoks]
    sm = difflib.SequenceMatcher(None, a, wkeys, autojunk=False)
    pairs: List[Tuple[int, int]] = []
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            pairs.append((blk.a + k, blk.b + k))
    # fuzzy fill: unmatched script tokens between two matched anchors may pair with the unmatched word at the same relative place
    matched_a = {x for x, _ in pairs}
    pairs_sorted = sorted(pairs)
    atoks = [t for r in rows for t in _tokens(r.get("script_segment", ""))]
    for ia, (sc, key) in enumerate(stoks):
        if ia in matched_a:
            continue
        lo = max([p for p in pairs_sorted if p[0] < ia], default=(-1, -1))[1] + 1
        hi = min([p for p in pairs_sorted if p[0] > ia], default=(0, len(wkeys)))[1]
        best, bj = 0.0, -1
        for j in range(lo, min(hi, len(wkeys))):
            r_ = difflib.SequenceMatcher(None, key, wkeys[j]).ratio() if key and wkeys[j] else 0.0
            if akey_fn and sim_fn:
                try:
                    r_ = max(r_, float(sim_fn(akey_fn(atoks[ia]), akey_fn(words[j][0]))))
                except Exception:       # noqa: BLE001
                    pass
            if r_ > best:
                best, bj = r_, j
        if bj >= 0 and best >= min_ratio:
            pairs.append((ia, bj))
    per = [{"scene": rows[i].get("scene_number", i + 1), "words": 0, "matched": 0, "inside": 0} for i in range(len(rows))]
    for sc, _ in stoks:
        per[sc]["words"] += 1
    for ia, jb in pairs:
        sc = stoks[ia][0]
        t = (float(words[jb][1]) + float(words[jb][2])) / 2.0
        per[sc]["matched"] += 1
        if wins[sc][0] - tol <= t <= wins[sc][1] + tol:
            per[sc]["inside"] += 1
    for p in per:
        p["pct"] = round(100.0 * p["inside"] / p["matched"], 1) if p["matched"] else None
    m, ins = sum(p["matched"] for p in per), sum(p["inside"] for p in per)
    worst = sorted([p for p in per if p["pct"] is not None], key=lambda p: p["pct"])[:5]
    return {"pct_inside": round(100.0 * ins / m, 1) if m else 0.0, "matched": m, "inside": ins,
            "script_words": len(stoks), "match_pct": round(100.0 * m / len(stoks), 1) if stoks else 0.0, "scenes": per, "worst": worst}


# ------------------------------------------------------------------ (d) sheets

def _grab(video: "str | Path", t: float, w: int) -> Optional["Image.Image"]:       # noqa: F821
    from PIL import Image
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={w}:-2",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        return None
    import io
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def _sheet(frames: List[Tuple[str, Any]], cols: int, out: "str | Path", cell_w: int) -> str:
    from PIL import Image, ImageDraw
    frames = [(l, im) for l, im in frames if im is not None]
    if not frames:
        raise ValueError("no frames could be read")
    ch = frames[0][1].height
    rows_n = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows_n * (ch + 16)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(frames):
        x, y = (i % cols) * cell_w, (i // cols) * (ch + 16)
        sheet.paste(im.resize((cell_w, ch)), (x, y + 16))
        d.text((x + 3, y + 2), label, fill=(240, 240, 240))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(out))
    return str(out)


def contact_sheet(video: "str | Path", every_s: float = 6.0, out: "str | Path" = "contact_sheet.png", cols: int = 6, cell_w: int = 320) -> str:
    dur = _probe_duration(video)
    ts = [t for t in np.arange(0.0, max(dur - 0.05, 0.1), every_s)]
    return _sheet([(f"{t:6.1f}s", _grab(video, float(t), cell_w)) for t in ts], cols, out, cell_w)


def cut_sheets(video: "str | Path", cuts: Sequence[float], out: "str | Path" = "cut_sheets.png", around: float = 0.2, cell_w: int = 240) -> str:
    """One row per cut: [cut-around, cut, cut+around]."""
    frames: List[Tuple[str, Any]] = []
    for c in cuts:
        for dt in (-around, 0.0, around):
            frames.append((f"cut {c:.1f}s {dt:+.1f}", _grab(video, c + dt, cell_w)))
    return _sheet(frames, 3, out, cell_w)


# ------------------------------------------------------------------ (e) audit_all

def _row(name: str, ok: bool, detail: str, limit: str) -> dict:
    return {"check": name, "ok": bool(ok), "detail": detail, "limit": limit}


def audit_all(video: "str | Path | None" = None, plan: Any = None, aligned: Optional[Sequence[dict]] = None,
              words: Optional[Sequence[Sequence[Any]]] = None, thresholds: Optional[dict] = None,
              print_fn: Optional[Callable[[str], None]] = print, sheets_dir: "str | Path | None" = None,
              flash_check: bool = True) -> dict:
    """Runs every check the inputs allow (video -> stills, flashes, sheets; plan -> variety; aligned+words -> sync) and prints one pass/fail table.
    -> {"ok": bool, "checks": [...], "still_spans": [...], "flashes": [...], "variety": {...}, "sync": {...}}."""
    th = dict(THRESHOLDS)
    th.update(thresholds or {})
    checks: List[dict] = []
    res: Dict[str, Any] = {}
    if video is not None and Path(video).is_file():
        scan = scan_video(video)
        diffs = scan["diffs"]
        spans = still_stretches(video, min_len=min(th["still_max_s"], 3.0), diffs=diffs)
        over = [s for s in spans if s["length"] > th["still_max_s"]]
        dur = _probe_duration(video)
        still_total = sum(s["length"] for s in spans)
        res["still_spans"], res["duration"] = spans, dur
        longest = max((s["length"] for s in spans), default=0.0)
        checks.append(_row("still stretches", not over, f"{len(over)} over limit, longest {longest:.1f}s, {still_total:.0f}s of {dur:.0f}s still",
                           f"none > {th['still_max_s']:.0f}s"))
        if flash_check:
            fl = flash_frames(video, fps=scan["fps"], lums=scan["lums"])
            res["flashes"] = fl
            checks.append(_row("flash frames", len(fl) <= th["flash_max"], f"{len(fl)} flash(es)" + (f" at {[f['t'] for f in fl[:6]]}" if fl else ""),
                               f"<= {th['flash_max']}"))
        if sheets_dir:
            try:
                res["contact_sheet"] = contact_sheet(video, 6.0, Path(sheets_dir) / "contact_sheet.png")
            except Exception as exc:        # noqa: BLE001
                res["contact_sheet_error"] = str(exc)
    if plan is not None:
        v = variety_report(plan)
        res["variety"] = v
        checks.append(_row("shot length", not v["over_max"] and v["shots"] > 0,
                           f"{v['shots']} shots, avg {v['avg_len_s']}s, max {v['max_len_s']}s" + (f", too long: {v['over_max'][:5]}" if v["over_max"] else ""),
                           f"each <= {th['shot_max_s']:.0f}s"))
        checks.append(_row("transition variety", v["max_transition_run"] <= th["repeat_transition_max"],
                           f"longest run of one transition: {v['max_transition_run']} ({v['max_transition_run_name'] or '-'})", f"<= {th['repeat_transition_max']:.0f} in a row"))
        if v["tier_mix"] and "?" not in v["tier_mix"]:
            checks.append(_row("idle shots", v["idle_pct"] <= th["tier_idle_max_pct"], f"{v['idle_pct']}% of shots with no motion; mix {v['tier_mix']}",
                               f"<= {th['tier_idle_max_pct']:.0f}%"))
    if aligned is not None and words is not None:
        s = sync_report(aligned, words)
        res["sync"] = s
        checks.append(_row("timing", s["pct_inside"] >= th["sync_min_pct"], f"{s['pct_inside']}% of {s['matched']} matched words inside their scene window",
                           f">= {th['sync_min_pct']:.0f}%"))
    ok = all(c["ok"] for c in checks) and bool(checks)
    res.update({"ok": ok, "checks": checks})
    if print_fn:
        print_fn("STORY AUDIT")
        for c in checks:
            print_fn(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['check']:<18} {c['detail']}   (limit: {c['limit']})")
        print_fn(f"  RESULT: {'PASS' if ok else 'FAIL'}" if checks else "  nothing to check (no video, plan or timing given)")
    return res


if __name__ == "__main__":      # python3 story_audit.py video.mp4 [plan.json]
    import sys
    vid = sys.argv[1] if len(sys.argv) > 1 else None
    pl = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else None
    audit_all(vid, pl)
