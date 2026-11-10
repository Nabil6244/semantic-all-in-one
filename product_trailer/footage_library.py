"""Local footage intelligence for Product Trailer films: index a folder of the user's own videos once, find the moments that show what a sentence says,
and cut them out for the film. The originals are only ever read.

    index_folder(folder, cache_dir, log)  -> {"files": [...]}  metadata, shots, motion and quality per shot, thumbnails; cached per file (path+size+mtime), so
                                             unchanged footage is never analysed again
    contact_sheets(index, out_dir)         -> sheets of every shot's frame, to label shots by eye (or by a caption backend)
    labels(...)                            -> the shot descriptions (footage_labels.json next to the cache): what a shot shows, its subject, its concepts
    match_sentence(...)                    -> segments (source, in, out) that show what the narration says, or [] when nothing in the library does
    cut_segment(seg, dest)                 -> a trimmed 30 fps clip (ffmpeg, no audio); the source is never touched

Meaning comes from shot descriptions + the sentence's concepts + the subject (a clip of another phone is never used for the film's phone), not from
file names. The pixels themselves are described by a caption backend: today the labels file (written by eye from the contact sheets); the library
reports every shot still without a description, and a vision model can fill them in without any change here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
INDEX_VERSION = "ptlib-1"
SAMPLE_FPS = 5.0
CUT_DIFF = 26.0           # mean grey difference (0-255) between samples 0.2 s apart that counts as a cut
MIN_SHOT_S = 0.6
THUMB_W = 320


# ----------------------------------------------------------------------------- index

def _sig(p: Path) -> str:
    st = p.stat()
    return hashlib.sha1(f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}|{INDEX_VERSION}".encode()).hexdigest()[:16]


def discover(folder: Any) -> List[Path]:
    """Every video under the folder (sorted). Hidden files and our own output folders are skipped."""
    root = Path(folder)
    if not root.is_dir():
        return []
    out = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT and not any(x.startswith(".") for x in p.relative_to(root).parts)]
    return sorted(out, key=lambda p: str(p).lower())


def _analyse(path: Path, thumbs_dir: Path) -> Dict[str, Any]:
    import av
    import numpy as np
    from PIL import Image

    meta: Dict[str, Any] = {}
    with av.open(str(path)) as c:
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"
        fps = float(vs.average_rate or 30)
        meta = {"width": vs.codec_context.width, "height": vs.codec_context.height, "fps": round(fps, 3), "codec": vs.codec_context.name,
                "has_audio": bool(c.streams.audio), "duration": float(c.duration / 1_000_000) if c.duration else 0.0}
        step = max(1, int(round(fps / SAMPLE_FPS)))
        grey, luma, colour, times = [], [], [], []
        for i, fr in enumerate(c.decode(vs)):
            if i % step:
                continue
            im = fr.to_ndarray(width=160, height=90, format="rgb24")
            g = im.mean(axis=2)
            grey.append(g)
            luma.append(float(g.mean()))
            colour.append(float(np.abs(im[..., 0].astype(float) - im[..., 1]).mean() + np.abs(im[..., 1].astype(float) - im[..., 2]).mean()))
            times.append(float(fr.time if fr.time is not None else i / fps))
    if not grey:
        return {**meta, "shots": []}
    diffs = [0.0] + [float(np.abs(grey[k] - grey[k - 1]).mean()) for k in range(1, len(grey))]
    meta["duration"] = max(meta["duration"], times[-1] + 1.0 / SAMPLE_FPS)
    cuts = [0] + [k for k in range(1, len(grey)) if diffs[k] > CUT_DIFF]
    bounds = []
    for n, k in enumerate(cuts):
        a = times[k]
        b = times[cuts[n + 1]] if n + 1 < len(cuts) else meta["duration"]
        if bounds and b - a < MIN_SHOT_S:           # a flash or a dissolve frame: part of the shot before
            bounds[-1][1] = b
        else:
            bounds.append([a, b])
    shots = []
    for n, (a, b) in enumerate(bounds):
        idx = [k for k, t in enumerate(times) if a - 1e-6 <= t < b - 1e-6] or [0]
        mot = [diffs[k] for k in idx[1:]] or [0.0]
        curve = [round(diffs[k], 1) for k in idx]
        shots.append({"n": n, "start": round(a, 3), "end": round(b, 3), "motion": round(float(np.mean(mot)), 2), "motion_curve": curve,
                      "luma": round(float(np.mean([luma[k] for k in idx])), 1), "colour": round(float(np.mean([colour[k] for k in idx])), 1),
                      "dark": bool(np.mean([luma[k] for k in idx]) < 14)})
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    with av.open(str(path)) as c:
        vs = c.streams.video[0]
        for s in shots:
            mid = (s["start"] + s["end"]) / 2
            try:
                c.seek(int(mid / vs.time_base), stream=vs, backward=True, any_frame=False)
                for fr in c.decode(vs):
                    if fr.time is None or fr.time >= mid - 0.05:
                        h = int(THUMB_W * meta["height"] / meta["width"])
                        Image.fromarray(fr.to_ndarray(width=THUMB_W, height=h, format="rgb24")).save(thumbs_dir / f"shot_{s['n']:03d}.jpg", quality=80)
                        s["thumb"] = f"shot_{s['n']:03d}.jpg"
                        break
            except Exception:  # noqa: BLE001 -- a missing thumbnail is not a failed index
                pass
    return {**meta, "shots": shots}


def index_folder(folder: Any, cache_dir: Any, log: Callable[[str], None] = print) -> Dict[str, Any]:
    """Index every video in `folder`; a file whose path, size and modification time are unchanged is read from the cache, not analysed again."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    files, fresh, reused = [], 0, 0
    for p in discover(folder):
        sig = _sig(p)
        rec_path = cache / f"{sig}.json"
        rec = None
        if rec_path.is_file():
            try:
                rec = json.loads(rec_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                rec = None
        if rec and rec.get("sig") == sig:
            reused += 1
        else:
            t0 = time.monotonic()
            try:
                info = _analyse(p, cache / sig)
            except Exception as exc:  # noqa: BLE001 -- one unreadable file never stops the library
                log(f"footage library: could not read {p.name}: {type(exc).__name__}")
                continue
            rec = {"sig": sig, "path": str(p), "name": p.name, "folder": p.parent.name, "size": p.stat().st_size, **info}
            rec_path.write_text(json.dumps(rec), encoding="utf-8")
            fresh += 1
            log(f"footage library: indexed {p.name} ({rec['duration']:.1f} s, {len(rec['shots'])} shots) in {time.monotonic() - t0:.1f} s")
        rec["thumb_dir"] = str(cache / sig)
        files.append(rec)
    log(f"footage library: {len(files)} file(s), {fresh} analysed, {reused} from the cache")
    return {"files": files, "cache": str(cache), "fresh": fresh, "reused": reused}


def contact_sheets(index: Dict[str, Any], out_dir: Any, per_sheet: int = 24, cols: int = 6) -> List[str]:
    """JPG sheets of every shot's middle frame, captioned `file#shot`, so shots can be described by eye or by a caption backend."""
    from PIL import Image, ImageDraw

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cells = []
    for f in index["files"]:
        for s in f["shots"]:
            if s.get("thumb"):
                cells.append((f"{f['folder'][:2]}/{Path(f['name']).stem[-7:]}#{s['n']}", Path(f["thumb_dir"]) / s["thumb"]))
    sheets = []
    tw, th = 240, 135
    for k in range(0, len(cells), per_sheet):
        chunk = cells[k:k + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sh = Image.new("RGB", (cols * tw, rows * (th + 16)), "white")
        d = ImageDraw.Draw(sh)
        for n, (cap, tp) in enumerate(chunk):
            x, y = (n % cols) * tw, (n // cols) * (th + 16)
            try:
                sh.paste(Image.open(tp).convert("RGB").resize((tw, th)), (x, y + 16))
            except OSError:
                pass
            d.text((x + 3, y + 2), cap, fill="black")
        dest = out / f"sheet_{k // per_sheet + 1:02d}.jpg"
        sh.save(dest, quality=82)
        sheets.append(str(dest))
    return sheets


# ----------------------------------------------------------------------------- shot descriptions

def load_labels(path: Any) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def label_key(f: Dict[str, Any]) -> str:
    return f"{f['folder']}/{f['name']}"


def attach_labels(index: Dict[str, Any], labels: Dict[str, Any]) -> Dict[str, Any]:
    """Put each described shot's `shows`, `subject`, `concepts`, `usage` on the index; return {"described": n, "undescribed": [file#shot, ...]}."""
    ok, missing = 0, []
    for f in index["files"]:
        lab = labels.get(label_key(f)) or {}
        subj = lab.get("subject", "")
        per = {int(k): v for k, v in (lab.get("shots") or {}).items()}
        for s in f["shots"]:
            d = per.get(s["n"]) or per.get(-1)
            if d:
                s.update({"shows": d.get("shows", ""), "concepts": list(d.get("concepts", [])), "usage": d.get("usage", ""), "state": d.get("state", ""),
                          "subject": d.get("subject", subj), "keep": d.get("keep", True), "onscreen": list(d.get("onscreen", [])), "third_party": bool(d.get("third_party", False))})
                ok += 1
            else:
                missing.append(f"{f['folder']}/{f['name']}#{s['n']}")
    return {"described": ok, "undescribed": missing}


# ----------------------------------------------------------------------------- what a sentence asks for

# concept -> the words in narration that name it. A shot is matched on these concepts, never on its file name.
CONCEPT_WORDS: Dict[str, str] = {
    "foldable_form": r"foldable|folds?\b|folding|book-style|unfold|\bopen(?:s|ed|ing)?\b|closed|fold line",
    "hinge": r"hinge",
    "inner_display": r"inner (?:screen|display)|7\.6|large display|inner",
    "outer_display": r"outer (?:screen|display)|5\.4|cover screen|outer",
    "apps_ui": r"\bapps?\b|multitask|split[- ]screen|interface|software|ios|screen real estate|awkward",
    "camera": r"camera|lens|selfie|telephoto|photo|video quality|low light|main camera",
    "pencil": r"pencil",
    "chip": r"a20|chip|processor|performance|thermal|vapor",
    "battery": r"battery|batteries|hours of video|charging",
    "price": r"\$\s?\d|dollars|price|costs?\b|expensive",
    "launch": r"launch(?:ed)?|announc|event|unveil|in people.s hands|first foldable|first-gen|first generation",
    "display_quality": r"nano-texture|oled|brightness|nits|refresh|120 hertz|glare|crease",
    "design": r"design|thin|thinnest|titanium|colou?r|finish|hands|pocket",
}

SPECIFIC = {"battery", "chip", "price", "pencil", "camera", "hinge"}

# Concepts that no promotional footage can honestly show: they need the real evidence, a document, or a graphic.
EVIDENCE_KINDS = {"reported_problem", "signoff", "test"}
EVIDENCE_WORDS = r"respon\w*|crack|damage|owners? (?:report|said)|broke|hasn.t (?:given|confirmed)|acknowledged|statement|appleCare|replacement|teardown|ifixit|reported|according to|failure rate|small number|supply|quoting|diagnostic"


def concepts_of(text: str) -> Dict[str, float]:
    """The concepts a sentence talks about, with weights (more hits, higher weight)."""
    t = text.lower()
    out: Dict[str, float] = {}
    if re.search(r"\bwhat is (?:the )?(?:new )?iphone duo\b|\bmeet (?:the )?iphone duo\b|\bintroducing\b", t):     # a line that introduces the product itself: the product on screen
        out.update({"foldable_form": 1.0, "design": 1.0})
    for k, pat in CONCEPT_WORDS.items():
        n = len(re.findall(pat, t))
        if n:
            out[k] = min(2.0, 0.8 + 0.4 * n)
    return out


def _norm(x: str) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", x.lower())


def _onscreen_ok(text: str, tokens: Sequence[str]) -> bool:
    n = _norm(text)
    return all(_norm(tok) in n for tok in tokens)


def is_evidence_sentence(text: str) -> bool:
    return bool(re.search(EVIDENCE_WORDS, text, re.I))


# usage a sentence kind is happy to take from footage (a number-heavy line is drawn as a graphic instead)
KIND_USAGE = {"date": {"promo", "product", "hands"}, "price": {"promo", "product", "hands"}, "product": {"product", "hands", "promo", "mood"}, "hook": {"product", "hands", "promo", "mood"}, "lead_in": {"product", "hands", "promo", "mood"},
              "explanation": {"product", "hands", "ui", "promo"}, "criticism": {"hands", "ui", "product", "promo"}, "advice": {"hands", "product", "mood"},
              "question": {"product", "hands", "mood"}, "spec": {"product", "promo", "ui"}}


def match_sentence(text: str, kind: str, slot_s: float, phone: str, index: Dict[str, Any], used: Dict[Tuple[str, int], float], *, min_score: float = 1.0,
                   seg_s: Tuple[float, float] = (1.2, 3.6), max_units: int = 6, flex: bool = False, cap: Optional[float] = None, fresh: bool = False) -> Dict[str, Any]:
    """Segments that show what `text` says. Returns {"segments": [...], "score": x, "reason": "..."}; segments is [] when nothing honestly fits.
    A segment is {"file", "path", "in", "out", "shot", "shows", "score"}. `used` records the seconds already taken from each (file, shot), so
    one source gives several clips but the same moment is never shown twice."""
    want = concepts_of(text)
    if kind in EVIDENCE_KINDS:
        return {"segments": [], "score": 0.0, "reason": "evidence sentence: promotional footage would not show what is said"}
    if re.match(rf"^\W*(?:\w+\W+){{0,4}}?(?:{EVIDENCE_WORDS})", text, re.I):    # a line that opens on a statement or a report is about that, not about the launch
        for c in ("launch", "price"):
            want.pop(c, None)
    if not want:
        return {"segments": [], "score": 0.0, "reason": "no visual concept in the sentence"}
    phone_key = re.sub(r"[^a-z0-9]+", "_", (phone or "").lower()).strip("_")
    allowed = KIND_USAGE.get(kind, {"product", "hands", "promo", "ui", "mood"})
    cands = []
    for f in index["files"]:
        for s in f["shots"]:
            if not s.get("shows") or s.get("keep") is False or s.get("dark") or s.get("third_party"):      # content that is not the manufacturer's (a game, a film clip on screen) needs its own clearance
                continue
            if s.get("subject") != phone_key:                # a clip of another phone is never the film's phone
                continue
            if s.get("usage") and s["usage"] not in allowed:
                continue
            if flex and s.get("usage") == "ui" and not (set(want) & SPECIFIC & set(s.get("concepts", []))):
                continue                                     # screen-capture footage under figures only when the line is about what it shows (the chip, an app)
            if not _onscreen_ok(text, s.get("onscreen") or []):    # words or figures printed in the shot are only shown when the narration says them
                continue
            have = set(s.get("concepts", []))
            need = set(want) & SPECIFIC                      # a line about the battery, the chip, the price, the Pencil... needs a shot that shows that, not just the phone's screen
            if need and not (need & have):
                continue
            hit = sum(w for c, w in want.items() if c in have)
            if hit <= 0:
                continue
            miss = sum(w for c, w in want.items() if c not in have) * 0.15
            taken = used.get((f["path"], s["n"]), 0.0)
            room = (s["end"] - s["start"]) - taken
            if room < seg_s[0]:
                continue
            score = hit - miss + min(1.0, s["motion"] / 12.0) * 0.4 - (0.5 if taken else 0.0)
            cands.append((score, f, s, room))
    cands.sort(key=lambda x: -x[0])
    if not cands or cands[0][0] < min_score:
        return {"segments": [], "score": cands[0][0] if cands else 0.0, "reason": "no shot in the library shows this"}
    if flex:
        picked, full = _cover_flex(cands, slot_s, used, seg_s, min_score, cap=cap, fresh=fresh)
    else:
        picked, full = _cover(cands, slot_s, used, seg_s, min_score, max_units)
    if not picked:
        return {"segments": [], "score": cands[0][0], "reason": "matching shots are used up or too short"}
    return {"segments": picked, "score": picked[0]["score"], "reason": "matched on " + ", ".join(sorted(want)[:4]), "covers_slot": full}


def _cover_flex(cands, slot_s: float, used: Dict[Tuple[str, int], float], seg_s: Tuple[float, float], min_score: float, each: float = 3.6, cap: Optional[float] = None, fresh: bool = False):
    """For a line whose figures stay on screen: take each matching moment at its own length (up to `each` s, never looped or stretched), one per shot, until the line
    is covered or the library has no more. What is left of the line is the director's scene. Returns (segments, covered)."""
    taken, total = [], 0.0
    goal = slot_s if cap is None else min(slot_s, cap)
    for score, fl, s, _room in cands:
        if score < min_score or any(x["path"] == fl["path"] and x["shot"] == s["n"] for x in taken):
            continue
        prev = used.get((fl["path"], s["n"]), 0.0)
        if fresh and prev:                                  # a lead-in is a picture the film has not shown yet
            continue
        start = s["start"] + 0.12 + prev + (0.45 if prev else 0.0)
        room = s["end"] - 0.08 - start
        length = min(each, room, goal - total)
        left = slot_s - total - length
        if cap is None and 0 < left < 2.0:                  # a sliver of line would be left: this clip runs to the end of it, or stops early enough for a scene that can be read
            length = slot_s - total if room >= slot_s - total else length - (2.0 - left)
        if length < max(1.5, seg_s[0]):
            continue
        start = _calm_start(s, start, length)
        taken.append({"file": fl["name"], "path": fl["path"], "in": round(start, 3), "out": round(start + length, 3), "shot": s["n"], "shows": s["shows"],
                      "score": round(score, 2), "room": round(s["end"] - 0.05 - start, 3), "onscreen": list(s.get("onscreen") or [])})
        used[(fl["path"], s["n"])] = start - s["start"] + length
        total += length
        if total >= goal - 0.6:
            break
    return taken, bool(taken) and total >= slot_s - 0.6


def _cover(cands, slot_s: float, used: Dict[Tuple[str, int], float], seg_s: Tuple[float, float], min_score: float, max_units: int = 6):
    """Pick segments that fill the slot without a clip being looped or stretched: u units each slot/u long (the planner splits a line's time evenly);
    every footage unit needs a real moment at least that long. When the library cannot give all u, one unit is left for a phrase card (full = False)."""
    lo = max(1, int(-(-slot_s // 4.5)))
    order = list(range(lo, max(lo, max_units) + 1)) + list(range(lo - 1, max(0, int(-(-slot_s // 7.0)) - 1), -1))      # first shares up to 4.5 s, then longer ones
    for u in order:
        share = slot_s / u
        if share < seg_s[0]:
            continue
        for p in (0, 1):
            f = u - p
            if f < 1:
                continue
            taken, tmp = [], dict(used)
            for score, fl, s, _room in cands:
                if any(x["path"] == fl["path"] and x["shot"] == s["n"] for x in taken):    # one moment per shot in a line: the same picture twice running reads as a stall
                    continue
                while len(taken) < f:
                    prev = tmp.get((fl["path"], s["n"]), 0.0)
                    start = s["start"] + 0.12 + prev + (0.45 if prev else 0.0)        # a second moment from one shot starts well after the first
                    room = s["end"] - 0.08 - start
                    if room < share + 0.1 or score < min_score * 0.8:
                        break
                    start = _calm_start(s, start, share)
                    taken.append({"file": fl["name"], "path": fl["path"], "in": round(start, 3), "out": round(start + share, 3), "shot": s["n"], "shows": s["shows"],
                                  "score": round(score, 2), "room": round(s["end"] - 0.05 - start, 3), "onscreen": list(s.get("onscreen") or [])})
                    tmp[(fl["path"], s["n"])] = start - s["start"] + share
                    break
                if len(taken) >= f:
                    break
            if len(taken) == f:
                used.update(tmp)
                return taken, p == 0
    return [], False


def _calm_start(shot: Dict[str, Any], start: float, length: float) -> float:
    """Inside the shot, the window of that length with the most movement (the shot's own action) that still starts at or after `start`."""
    curve = shot.get("motion_curve") or []
    if len(curve) < 3:
        return start
    step = 1.0 / SAMPLE_FPS
    w = max(1, int(length / step))
    best, best_i = -1.0, 0
    for i in range(0, max(1, len(curve) - w)):
        t = shot["start"] + i * step
        if t < start - 1e-6 or t + length > shot["end"] - 0.05:
            continue
        v = sum(curve[i:i + w]) / w
        if v > best:
            best, best_i = v, i
    return shot["start"] + best_i * step if best >= 0 else start


# ----------------------------------------------------------------------------- cutting

def _ffmpeg() -> str:
    from map_scene.render import _ffmpeg as f

    return f()


def cut_segment(seg: Dict[str, Any], dest: Any, *, width: int = 1920, height: int = 1080, fps: int = 30, pad_s: float = 0.0) -> Path:
    """Trim `seg` out of its source into `dest` (H.264, no audio, scaled to the film's size). The source file is only read."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dur = float(seg["out"]) - float(seg["in"]) + pad_s
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},format=yuv420p"
    cmd = [_ffmpeg(), "-y", "-v", "error", "-nostdin", "-ss", f"{float(seg['in']):.3f}", "-i", str(seg["path"]), "-t", f"{dur:.3f}", "-an", "-vf", vf,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-movflags", "+faststart", str(dest)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("cutting a footage clip took too long") from exc
    if r.returncode != 0 or not dest.is_file():
        raise RuntimeError(f"could not cut a footage clip: {r.stderr[-300:]}")
    return dest


# ----------------------------------------------------------------------------- the planner step

GENERIC_3D = {"fold", "macro", "lineup", "intro", "outro", "bigtype", "xray"}     # the same generic phone shot whatever the sentence says: real footage replaces it, or a plain phrase card
KEEP_3D: set = set()                                                # labelled inside-the-phone illustrations are explanatory, not a stand-in for a clip


def clause_label(text: str, max_words: int = 6) -> str:
    """The line's first clause when it is short enough to read beside a picture (2 to max_words words), else nothing: never a sentence cut in the middle."""
    first = re.split(r"[,;:.!?\u2014]", str(text).strip(), maxsplit=1)[0].strip()
    n = len(first.split())
    return first if 2 <= n <= max_words else ""


def key_phrase(text: str, max_words: int = 11) -> str:
    """The narration's own opening clause (up to the first comma or full stop), at most `max_words` words: shown as written, nothing added."""
    clause = re.split(r"[,;:.?!]", text.strip(), maxsplit=1)[0].strip() or text.strip()
    if len(clause.split()) < 3:                       # "First, what is the iPhone Duo?": the whole line is the phrase
        clause = re.sub(r"[.?!]+$", "", text.strip())
    words = clause.split()
    return " ".join(words[:max_words])


def clauses(text: str, slot: float, max_each: float = 4.6) -> List[str]:
    """The line split at its commas into as many cards as its length needs (one per ~4.6 s at most), each shown as spoken: a long line never holds one still card."""
    parts = [x.strip() for x in re.split(r"(?<=[,;:])\s+|\s+(?=(?:and|but|then|so)\s)", text.strip()) if x.strip()]
    parts = [re.sub(r"[,;:.]+$", "", x) for x in parts]
    n = max(1, int(-(-slot // max_each)))
    if len(parts) <= 1 or n == 1:
        return [key_phrase(text)] if n == 1 or len(parts) <= 1 else parts
    while len(parts) > n:                              # merge the shortest neighbours until the count fits
        i = min(range(len(parts) - 1), key=lambda k: len(parts[k].split()) + len(parts[k + 1].split()))
        parts[i:i + 2] = [parts[i] + ", " + parts[i + 1]]
    return [" ".join(x.split()[:14]) for x in parts]


HL_PATTERNS = [
    r"(?:about |around |roughly |fewer than |more than |over |under |only )?(?:\d[\d,\.]*|one|two|three|four|five|six|seven|eight|nine|ten|twenty)\s+(?:hours?|days?|minutes?|weeks?|times?|openings?|dollars?|percent|%)",
    r"no software fix|cracks?|bright lines|won.t open or close|strange noises|loose|damaged hinges?|crease|not what you.d expect|statement|acknowledged",
]


def hl_of(text: str) -> str:
    """The words in a clause that carry its key fact (a figure with its unit, or the named fault): they are picked out in colour and underlined on their word."""
    for pat in HL_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(0).strip()
    return ""


def kicker_of(text: str, cls: Dict[str, Any]) -> str:
    """The label a source-bearing line carries: who said it, from the sentence's own words (never a source the line does not name)."""
    if re.search(r"\bApple\b.*\b(?:respon\w+|said|says|statement|acknowledged)\b|\b(?:respon\w+|statement)\b.*\bApple\b", text, re.I):
        return "Apple's response"
    src = (cls.get("secondary") or {}).get("source")
    if src and src.lower() not in ("owner", "owners", "user", "users", "customer", "customers"):
        return f"Source: {src}"
    if re.search(r"\bowners?\b|\busers?\b|\bcustomers?\b", text, re.I):
        return "Owner reports"
    if re.search(r"\bApple\b.*\b(?:respon\w+|said|says|statement|acknowledged)\b|\b(?:respon\w+|statement)\b.*\bApple\b", text, re.I):
        return "Apple's response"
    if (cls.get("secondary") or {}).get("reported") or cls.get("primary") in ("reported_problem", "test"):
        return "Reported"
    return ""


def split_beats(text: str, span_s: float, max_each: float = 4.2, max_words: int = 16) -> List[str]:
    """The line cut at its commas / 'and' / 'but' / 'then' into beats of at most ~4 s and 16 words, every word kept (so the words map one to one onto the narrator's)."""
    parts = [x.strip() for x in re.split(r"(?<=[,;:])\s+|\s+(?=(?:and|but|then|so)\s)", text.strip()) if x.strip()]
    n = max(1, int(-(-span_s // max_each)), int(-(-len(text.split()) // max_words)))
    while len(parts) > n:
        i = min(range(len(parts) - 1), key=lambda k: len(parts[k].split()) + len(parts[k + 1].split()))
        parts[i:i + 2] = [parts[i] + " " + parts[i + 1]]
    k = 0
    while k < len(parts) and len(parts) > 1:           # a beat of one or two words (a lone "and") joins its neighbour
        if len(parts[k].split()) < 3:
            j = k + 1 if k + 1 < len(parts) else k - 1
            lo, hi = sorted((k, j))
            parts[lo:hi + 1] = [parts[lo] + " " + parts[hi]]
            k = 0
        else:
            k += 1
    out = []
    for x in parts:
        w = x.split()
        while len(w) > max_words:
            h = len(w) // 2
            out.append(" ".join(w[:h])); w = w[h:]
        out.append(" ".join(w))
    return out


def make_beats(text: str, W: Sequence[Any], rng: Tuple[int, int], span: Tuple[float, float], ok: bool, *, from_t: Optional[float] = None) -> List[Dict[str, Any]]:
    """Beats with their word times (absolute seconds). `from_t` keeps only the words spoken from that moment (a card that covers the tail of a line)."""
    words = text.split()
    s0, e0 = rng
    if ok and W and len(words) == e0 - s0 + 1:
        times = [float(W[s0 + j][1]) for j in range(len(words))]
    else:                                              # the narrator's words do not line up one to one: spread over the line's span
        a, b = span
        times = [a + (b - a) * j / max(1, len(words)) for j in range(len(words))]
    if from_t is not None:
        keep = [j for j, t in enumerate(times) if t >= from_t - 0.05]
        if not keep:
            return []
        words, times = [words[j] for j in keep], [times[j] for j in keep]
        text = " ".join(words)
    beats, j = [], 0
    for part in split_beats(text, (times[-1] - times[0]) + 1.0 if times else 3.0):
        n = len(part.split())
        tt = times[j:j + n]
        if not tt:
            break
        beats.append({"text": part, "from": round(tt[0], 3), "to": round(tt[-1] + 0.5, 3), "times": [round(x, 3) for x in tt], "hl": hl_of(part)})
        j += n
    return beats


def apply_library(parsed: Dict[str, Any], phone: str, folder: Any, work_dir: Any, words: Sequence[Any], voice_seconds: float,
                  log: Callable[[str], None] = print, labels_path: Optional[Any] = None, hero_renders: bool = True) -> Dict[str, Any]:
    """Choose, for every narration line, what carries it: footage from the user's library (the moment that shows what is said), a graphic the director
    already wrote for it (figures, dates, quotes), or a plain phrase card; never a generic phone shot. Inserts `footage` items (with `seg`) and `phrase`
    items into `parsed` and returns {"decisions": [...], "index": {...}, "undescribed": [...]} (also written to work_dir/footage_plan.json)."""
    from . import voiceover as vo
    from .diagnostic import classify

    hero_ok = hero_renders
    work = Path(work_dir)
    cache = work / "index"
    idx = index_folder(folder, cache, log)
    lab_path = Path(labels_path) if labels_path else cache / "footage_labels.json"
    info = attach_labels(idx, load_labels(lab_path))
    flat = []
    for ci, ch in enumerate(parsed["chapters"]):
        for k, it in enumerate(ch["items"]):
            if it["kind"] == "line":
                flat.append((ci, k, it))
    lines = [it["text"] for _c, _k, it in flat]
    voice = vo.align_lines(lines, list(words), float(voice_seconds))
    spans, D = voice["spans"], float(voice["duration"])
    ranges, vok = voice["ranges"], bool(voice.get("ok", False))
    Wt = vo._wtimes(list(words))
    used: Dict[Tuple[str, int], float] = {}
    decisions: List[Dict[str, Any]] = []
    plan: Dict[int, Dict[str, Any]] = {}
    for i, (ci, k, it) in enumerate(flat):
        text = it["text"]
        a = 0.0 if i == 0 else spans[i][0]
        b = D if i + 1 >= len(flat) else spans[i + 1][0]
        slot = max(1.0, b - a)
        cls = classify(text, i + 1, len(flat))
        kind = cls["primary"]
        items = parsed["chapters"][ci]["items"]
        before = []
        j = k - 1
        while j >= 0 and items[j]["kind"] != "line":
            before.append(items[j])
            j -= 1
        graphics = [d for d in before if d["kind"] not in GENERIC_3D and d["kind"] not in KEEP_3D]
        dec = {"line": i + 1, "text": text, "kind": kind, "slot": round(slot, 2), "treatment": "", "reason": "", "segments": []}
        dropped: List[Dict[str, Any]] = []
        if graphics and os.environ.get("PT_LIBRARY_OVERLAY", "1") != "0":
            try:                                            # a footage moment that already prints the figure (the launch slide says $1,999) needs no second copy of it
                from .review import flat_facts as _ff
                fx = [_ff(d, phone) for d in graphics]
                if all(fx):
                    probe = match_sentence(text, "figure", slot, phone, idx, dict(used), flex=True)
                    dig = [re.sub(r"\D", "", x["value"]) for ft in fx for x in ft["items"]]
                    shown = "".join(re.sub(r"\D", "", "".join(sg.get("onscreen") or [])) + "|" for sg in probe["segments"])
                    if probe["segments"] and dig and all(dg and dg in shown for dg in dig):
                        dropped, graphics = list(graphics), []
            except Exception:
                pass
        if graphics:
            over_m = None
            if os.environ.get("PT_LIBRARY_OVERLAY", "1") != "0":     # figures over matching footage: the picture shows the thing, the figures state it
                try:
                    from .review import flat_facts
                    facts = [flat_facts(d, phone) for d in graphics]
                except Exception:
                    facts = [None]
                if all(facts):
                    mm = match_sentence(text, "figure", slot, phone, idx, used, flex=True)
                    if mm["segments"]:
                        over_m = (mm, facts)
            if over_m:
                mm, facts = over_m
                tail = []
                for d, ft in zip(graphics, facts):
                    if not mm.get("covers_slot", True):      # the library's matching moments end before the line does: the rest is the director's own scene, its figures settled at once
                        t2 = copy.deepcopy(d)
                        t2["_stay"], t2["flat"] = True, True
                        n_at = [0]
                        def _settle(o):
                            if isinstance(o, dict):
                                if "at" in o and isinstance(o["at"], (int, float)):
                                    o["at"] = 0.12 * n_at[0]; n_at[0] += 1
                                for v in o.values():
                                    _settle(v)
                            elif isinstance(o, list):
                                for v in o:
                                    _settle(v)
                        _settle(t2)
                        tail.append(t2)
                    d["_over"], d["_facts"], d["_stay"] = True, ft, True
                dec.update(treatment="footage+figures", reason="figures over matched footage: " + mm["reason"], segments=mm["segments"])
                if tail:
                    dec["tail"] = "the director's scene, figures settled"
                add = [{"kind": "footage", "query": "", "topic": None, "text": "", "path": sg["path"], "seg": sg, "_own": True} for sg in mm["segments"]] + tail
                plan[i] = {"drop": [], "add": add}
            else:
                lead = None
                cap = slot - 5.0
                s0, e0 = ranges[i]
                said = {re.sub(r"\D", "", x) for d in graphics for x in re.findall(r"\d[\d,.]*", json.dumps(d, default=str))} - {""}      # the figures the chart shows, as the narrator says them
                fig_t = next((Wt[q][1] for q in range(s0, min(e0 + 1, len(Wt))) if re.sub(r"\D", "", Wt[q][0]) in said and re.fullmatch(r"[\d.,]+", Wt[q][0])), None)      # the chart starts where its first figure is said
                if fig_t is not None:
                    cap = min(cap, fig_t - a - 0.4)
                if cap >= 2.0 and all(d["kind"] in ("bars", "compare", "gauge", "scene", "thermal", "curve") for d in graphics):
                    ml = match_sentence(text, "figure", slot, phone, idx, used, flex=True, cap=cap, fresh=True)       # the thing first, then the chart that states it
                    if ml["segments"]:
                        lead = ml
                for d in graphics:
                    d["_stay"] = True
                    if d["kind"] in ("sides", "feature", "callout"):
                        d["flat"] = True                      # drawn on the paper with the film's own phone: no generic 3D phone behind a figure
                chip = re.search(r"\b(A\d{2}(?:\s+(?:Pro|Max|Bionic))?|Snapdragon[\w ]{0,18}?|Exynos[\w ]{0,8}?|Tensor[\w ]{0,6}?|Dimensity[\w ]{0,6}?)\s+chip\b", text)
                if not lead and chip and fig_t is not None and fig_t - a > 3.0 and all(d["kind"] in ("bars", "compare") for d in graphics):
                    same = re.search(r"\b(?:same|as|than)\b[^,.]*?\b((?:iPhone|Galaxy|Pixel)[\w ]{0,14}?)(?=[,.]|$| and)", text[chip.end():])
                    plan[i] = {"drop": [], "add": [{"kind": "chip", "label": chip.group(1).upper(), "text": ("Same chip as " + same.group(1).strip()) if same else "", "flat": True, "_first": True, "_stay": True, "_own": True}]}
                    dec.update(treatment="chip badge + graphic", reason="the named chip first, then the director's " + "/".join(d["kind"] for d in graphics))
                elif lead:
                    dec.update(treatment="footage+graphic", reason="footage first (" + lead["reason"] + "), then the director's " + "/".join(d["kind"] for d in graphics), segments=lead["segments"])
                    plan[i] = {"drop": [], "add": [{"kind": "footage", "query": "", "topic": None, "text": "", "path": sg["path"], "seg": sg, "_own": True, "_lead": True} for sg in lead["segments"]]}
                else:
                    dec.update(treatment="graphic", reason="the director's " + "/".join(d["kind"] for d in graphics) + " carries it (figures, dates, quotes, charts); no matching footage in the library")
        else:
            m = match_sentence(text, kind, slot, phone, idx, used, min_score=1.8 if cls["secondary"].get("source") else 1.0)   # a line that credits a source needs a strong visual match, not one word
            if m["segments"]:
                dec.update(treatment="footage", reason=m["reason"], segments=m["segments"])
                add = [{"kind": "footage", "query": "", "topic": None, "text": "", "path": s["path"], "seg": s, "_own": True} for s in m["segments"]]
                if not m.get("covers_slot", True):         # the library has fewer matching moments than the line is long: the rest is the line's own words, not a loop
                    share = slot / (len(m["segments"]) + 1)
                    bt = make_beats(text, Wt, ranges[i], spans[i], vok, from_t=b - share + 0.25)
                    add.append({"kind": "evidence", "text": text, "kicker": kicker_of(text, cls), "beats": bt, "_own": True, "_stay": True} if bt else {"kind": "phrase", "text": key_phrase(text), "_own": True})
                    dec["tail"] = "evidence card"
                plan[i] = {"drop": [d for d in before if d["kind"] in GENERIC_3D] + dropped, "add": add}
            elif any(d["kind"] in KEEP_3D for d in before):
                dec.update(treatment="3d_illustration", reason="inside-the-phone illustration kept: " + m["reason"])
            else:
                dec.update(treatment="phrase", reason=m["reason"])
                bt = make_beats(text, Wt, ranges[i], spans[i], vok)
                lead_in = cls["primary"] in ("lead_in", "criticism") and len(text.split()) <= 6 and not (cls["secondary"] or {}).get("source")
                sourced = bool(cls["secondary"].get("source") or cls["secondary"].get("reported") or kind in EVIDENCE_KINDS)
                if not sourced and not lead_in and hero_ok:
                    plan[i] = {"drop": [d for d in before if d["kind"] in GENERIC_3D], "add": [{"kind": "hero", "text": clause_label(text), "_own": True}]}
                    dec["treatment"] = "hero render"
                    decisions.append(dec)
                    continue
                card = {"kind": "bigtype", "text": text.strip().rstrip("."), "_plate": True, "_own": True, "_stay": True} if lead_in else {"kind": "evidence", "text": text, "kicker": kicker_of(text, cls), "beats": bt, "_own": True, "_stay": True} if bt else None
                plan[i] = {"drop": [d for d in before if d["kind"] in GENERIC_3D], "add": [card] if card else [{"kind": "phrase", "text": c, "_own": True} for c in clauses(text, slot)]}
                if kind in EVIDENCE_KINDS or cls["secondary"].get("physical_problem") or cls["secondary"].get("reported"):
                    dec["missing_asset"] = "genuine evidence (owner photo or video, an original report, or Apple's own page) for: " + key_phrase(text, 14)
        decisions.append(dec)
    for i in sorted(plan, reverse=True):          # edit from the back so earlier positions stay valid
        ci, k, it = flat[i]
        items = parsed["chapters"][ci]["items"]
        drop = {id(d) for d in plan[i]["drop"]}
        pos = k
        for d in plan[i]["drop"]:
            idx_d = next(n for n, x in enumerate(items) if x is d)
            items.pop(idx_d)
            if idx_d < pos:
                pos -= 1
        for add in reversed(plan[i]["add"]):
            items.insert(pos, add)
    if hero_ok:                                  # text cards are for sourced claims only, and few: the rest of the evidence / tweet cards become renders of the phone with the line's key words
        cards = [(ci, k, it) for ci, ch in enumerate(parsed["chapters"]) for k, it in enumerate(ch["items"]) if it["kind"] in ("evidence", "tweet")]
        keep_n = max(2, int(0.12 * len(flat)))
        step = max(1, len(cards) // keep_n)
        keep = {id(c[2]) for n, c in enumerate(cards) if n % step == 0 and (c[2].get("kicker") or c[2]["kind"] == "tweet")}
        for ci, k, it in cards:
            if id(it) in keep:
                continue
            txt = it.get("text") or " ".join(str(b.get("text", "")) for b in it.get("beats") or [])
            parsed["chapters"][ci]["items"][k] = {"kind": "hero", "text": clause_label(str(txt)), "_own": True}
        log(f"text cards kept {len(keep)}, turned into phone renders {len(cards) - len(keep)}")
    out = {"decisions": decisions, "undescribed": info["undescribed"], "described": info["described"],
           "files": len(idx["files"]), "shots": sum(len(f["shots"]) for f in idx["files"]), "fresh": idx["fresh"], "reused": idx["reused"]}
    work.mkdir(parents=True, exist_ok=True)
    (work / "footage_plan.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    n_f = sum(1 for d in decisions if d["treatment"] == "footage")
    log(f"footage library: {n_f} of {len(decisions)} lines carried by footage, {sum(1 for d in decisions if d['treatment'] == 'graphic')} by graphics, "
        f"{sum(1 for d in decisions if d['treatment'] == 'phrase')} by phrase cards; {len(info['undescribed'])} shot(s) still without a description")
    return out
