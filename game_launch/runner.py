"""Game Launch ("Game vs Real") engine: a game's official trailers side by side with the real places they copy.

    check(csv, trailers_dir)                         -> {"errors", "warnings", "lines", "shots", ...}   reads only
    prepare(csv, trailers_dir, work, voice, ...)     -> summary; writes work/plan.json (voice lines + trailer cuts)
    render(work, out, found, ...)                    -> {"seconds", "shorts", "thumbnail"}

Game footage = trailer files the user keeps in one folder (muted; their music is licensed). Real footage = the Visuals tab's clips
(`found`: {scene_no: file}). Voice = free Edge voices, one file per line. Music = a synthwave bed made in code. No Gemini.
A trailer shot never crosses one of the trailer's own cuts: cuts are detected once per file (scene change + fade to black) and a
shot that would run past one plays slower (down to 0.45x) and then holds its last frame.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PIL import Image, ImageDraw

from . import look as L
from . import plan as P

PLAN_FILE = "game_launch_plan.json"
DEFAULT_VOICE = "en-US-AndrewNeural"
_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WHOOSH = _ROOT / "assets/bundled-sfx/wall/whoosh.wav"
IMPACT = _ROOT / "assets/bundled-sfx/impact/impact_001.opus"


class Cancelled(Exception):
    pass


def _whisper_backend():
    """The repo's whisper_backend.py (Apple-GPU Whisper with a CPU fallback), or None where it can't be imported."""
    try:
        import sys as _sys
        from pathlib import Path as _P
        root = str(_P(__file__).resolve().parents[1])
        if root not in _sys.path:
            _sys.path.append(root)
        import whisper_backend
        return whisper_backend
    except Exception:  # noqa: BLE001
        return None


def _run(cmd: List[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg failed: {(r.stderr or '').strip()[-400:]}")


def duration(path) -> float:
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                      text=True)
        return float(out.strip())
    except Exception:  # noqa: BLE001
        return 0.0


def trailer_path(trailers_dir: str, name: str) -> Optional[Path]:
    """The trailer file the CSV names: exact, then any case, then by name without extension."""
    d = Path(trailers_dir or ".")
    if not name or not d.is_dir():
        return None
    p = d / name
    if p.is_file():
        return p
    low = name.lower()
    stem = Path(low).stem
    for f in d.iterdir():
        if f.is_file() and f.suffix.lower() in P.VIDEO_EXT and (f.name.lower() == low or f.stem.lower() == stem):
            return f
    return None


# ---------------------------------------------------------------------------------------------------------------- check

def words_seconds(text: str) -> float:
    return len(re.findall(r"\w+", text)) / 2.75 + 0.35


def check(csv_path: str, trailers_dir: str) -> Dict[str, Any]:
    plan = P.read(csv_path)
    errors, warnings = list(plan["errors"]), list(plan["warnings"])
    if not trailers_dir or not Path(trailers_dir).is_dir():
        errors.append("choose the folder with the game's trailer files")
    else:
        lengths: Dict[str, float] = {}
        for ln in plan["lines"]:
            for s in ln["shots"]:
                if not s["game"]:
                    continue
                f = trailer_path(trailers_dir, s["game"])
                if f is None:
                    errors.append(f"row {s['row']}: no trailer file '{s['game']}' in {Path(trailers_dir).name}")
                    continue
                if f.name not in lengths:
                    lengths[f.name] = duration(f)
                if lengths[f.name] and s["game_at"] >= lengths[f.name] - 0.2:
                    errors.append(f"row {s['row']}: game_at {s['game_at']:.1f} s is past the end of {f.name} ({lengths[f.name]:.0f} s)")
    shots = [s for ln in plan["lines"] for s in ln["shots"]]
    used = {}
    for s in shots:
        if s["game"] and s["kind"] in ("game", "split"):
            key = (s["game"].lower(), round(s["game_at"]))
            if key in used:
                warnings.append(f"row {s['row']}: the same trailer moment as row {used[key]} (a repeated shot)")
            used[key] = s["row"]
    return {"errors": errors, "warnings": warnings, "lines": len(plan["lines"]), "shots": len(shots),
            "splits": sum(1 for s in shots if s["kind"] == "split"), "maps": sum(1 for s in shots if s["kind"] == "map"),
            "chapters": sum(1 for s in shots if s["kind"] == "chapter"), "real": sum(1 for s in shots if s.get("scene_no")),
            "seconds": sum(words_seconds(ln["text"]) for ln in plan["lines"]) + 2.5, "plan": plan}


# ---------------------------------------------------------------------------------------------------------------- cuts

def detect_cuts(path: Path, cache_dir: Path) -> List[float]:
    """The trailer's cut times (scene changes and starts of fades to black), cached per file."""
    st = path.stat()
    key = hashlib.sha1(f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]
    f = Path(cache_dir) / f"cuts_{key}.json"
    if f.is_file():
        try:
            return json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            pass
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-an", "-vf",
                        "blackdetect=d=0.08:pix_th=0.12,select='gt(scene,0.28)',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True)
    log = r.stderr or ""
    cuts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", log)]
    cuts += [float(m) for m in re.findall(r"black_start:([0-9.]+)", log)]
    cuts = sorted({round(c, 2) for c in cuts if c > 0.05})
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(cuts))
    except OSError:
        pass
    return cuts


# ---------------------------------------------------------------------------------------------------------------- voice

_DIGITS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight",
           "9": "nine"}


def _speakable(text: str, attempt: int) -> str:
    """Edge sometimes returns no audio for a line (seen with 'GTA 6.' at a sentence end): later attempts reword it."""
    if attempt >= 2:
        text = text.replace("?", ",").replace(":", ",")
    if attempt >= 3:
        text = re.sub(r"\b(\d)\b", lambda m: _DIGITS[m.group(1)], text)
    return text


async def _tts(text: str, voice: str, path: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, voice, rate="+6%").save(str(path))


VOICE_PARALLEL = 10   # Edge lines fetched at once (fresh text: 15 at once had no failures)


def voice_line(text: str, voice: str, folder: Path, log=lambda m: None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / (hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16] + ".mp3")
    import time

    for attempt in range(7):                       # Edge throttles bursts for a short while: wait longer between tries
        if f.is_file() and f.stat().st_size > 0:
            return f
        try:
            asyncio.run(_tts(_speakable(text, attempt), voice, f))
        except Exception as exc:  # noqa: BLE001
            log(f"voice retry {attempt + 1}: {exc}")
            f.unlink(missing_ok=True)
            time.sleep(min(20.0, 1.5 * 2 ** attempt))
    raise RuntimeError(f"the Edge voice made no audio for: {text[:60]}")


# ---------------------------------------------------------------------------------------------------------------- prepare

# ---------------------------------------------------------------------------------------------------------------- own voiceover

_NUM = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
        "nine": "9", "ten": "10", "nineteenth": "19th", "first": "1st", "second": "2nd", "third": "3rd"}


def _tok(text: str) -> List[str]:
    return [_NUM.get(w, w) for w in re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))]


def vo_words(audio: str, cache_dir: Path, log=lambda m: None) -> List[Dict[str, Any]]:
    """[{w, s, e}] word timings of a recorded voiceover (faster-whisper, cached by file size + time)."""
    f = Path(audio)
    st = f.stat()
    key = hashlib.sha1(f"{f.name}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:16]
    cache = cache_dir / f"vo_words_{key}.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    from faster_whisper import WhisperModel

    log("listening to the voiceover (word timings)")
    wb = _whisper_backend()
    if wb is not None:   # Apple GPU when it can (whisper_backend.py), else the same CPU model
        segs, _info = wb.transcribe(str(f), "small", language="en", word_timestamps=True)
    else:
        m = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _info = m.transcribe(str(f), language="en", word_timestamps=True)
    words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for sg in segs for w in sg.words]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(words), encoding="utf-8")
    return words


def align_lines(texts: List[str], words: List[Dict[str, Any]], total: float) -> List[tuple]:
    """(start, end) in the recording for each script line: script and heard words are matched in order (difflib), a line runs
    from the gap before its first heard word to the gap before the next line's. Lines nobody matched share time evenly."""
    import difflib

    heard = [(t, w) for w in words for t in _tok(w["w"])]
    htok = [t for t, _w in heard]
    stok, owner = [], []
    for i, tx in enumerate(texts):
        for t in _tok(tx):
            stok.append(t)
            owner.append(i)
    first: Dict[int, float] = {}
    last: Dict[int, float] = {}
    sm = difflib.SequenceMatcher(None, stok, htok, autojunk=False)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            i, w = owner[a + k], heard[b + k][1]
            first.setdefault(i, w["s"])
            first[i] = min(first[i], w["s"])
            last[i] = max(last.get(i, 0.0), w["e"])
    n = len(texts)
    starts: List[Optional[float]] = [first.get(i) for i in range(n)]
    starts[0] = 0.0
    for i in range(1, n):                              # a line with no heard word: halfway between its neighbours
        if starts[i] is None or starts[i] <= (starts[i - 1] or 0.0):
            nxt = next((starts[j] for j in range(i + 1, n) if starts[j] is not None and starts[j] > (starts[i - 1] or 0)), total)
            starts[i] = (starts[i - 1] + nxt) / 2
    cuts = [0.0]
    for i in range(1, n):
        prev_end = last.get(i - 1, starts[i])
        cuts.append(max(cuts[-1] + 0.2, (min(prev_end, starts[i]) + starts[i]) / 2))
    cuts.append(total)
    return [(round(cuts[i], 3), round(cuts[i + 1], 3)) for i in range(n)]


def cut_voiceover(audio: str, spans: List[tuple], folder: Path) -> List[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i, (a, b) in enumerate(spans):
        f = folder / f"line{i:03d}.wav"
        _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(audio), "-ac", "1", "-ar", "48000",
              str(f)])
        out.append(f)
    return out


def prepare(csv_path: str, trailers_dir: str, work: str, voice: str = DEFAULT_VOICE, log=lambda m: None,
            cancel: Callable[[], bool] = lambda: False, progress=lambda f, m="": None, voiceover: str = "") -> Dict[str, Any]:
    """voiceover = a recorded mp3/wav of the whole script: it is cut into the CSV's lines (no Edge voice is made)."""
    c = check(csv_path, trailers_dir)
    if c["errors"]:
        raise ValueError("The scenes CSV has problems:\n" + "\n".join(c["errors"][:10]))
    plan = c["plan"]
    work_d = Path(work)
    work_d.mkdir(parents=True, exist_ok=True)
    trailers: Dict[str, Dict[str, Any]] = {}
    for ln in plan["lines"]:
        for s in ln["shots"]:
            if s["game"] and s["game"] not in trailers:
                f = trailer_path(trailers_dir, s["game"])
                log(f"reading the cuts of {f.name}")
                trailers[s["game"]] = {"path": str(f), "cuts": detect_cuts(f, work_d / "cache"), "seconds": duration(f)}
                if cancel():
                    raise Cancelled()
    if voiceover:
        words = vo_words(voiceover, work_d / "cache", log)
        spans = align_lines([ln["text"] for ln in plan["lines"]], words, duration(voiceover))
        files = cut_voiceover(voiceover, spans, work_d / "own_voice")
        for ln, f, (a, b) in zip(plan["lines"], files, spans):
            ln["vo"], ln["vo_dur"], ln["vo_span"] = str(f), round(b - a, 3), [a, b]
        plan["vo_gap"] = 0.0                              # the recording's own pauses are kept
    if not voiceover:
        # Edge makes each line at about real time (5-8 s for a short line, 2026-11-17), so ask for many at once
        from concurrent.futures import ThreadPoolExecutor, as_completed

        lines = plan["lines"]
        with ThreadPoolExecutor(VOICE_PARALLEL) as ex:
            futs = {ex.submit(voice_line, ln["text"], voice, work_d / "voice", log): ln for ln in lines}
            for n, fut in enumerate(as_completed(futs), 1):
                if cancel():
                    for x in futs:
                        x.cancel()
                    raise Cancelled()
                progress(0.3 + 0.7 * n / max(1, len(lines)), f"voice {n}/{len(lines)}")
                f = fut.result()
                futs[fut]["vo"], futs[fut]["vo_dur"] = str(f), duration(f)
    data = {"csv": str(csv_path), "trailers_dir": str(trailers_dir), "voice": voice, "plan": plan, "trailers": trailers}
    (work_d / PLAN_FILE).write_text(json.dumps(data, indent=1), encoding="utf-8")
    shots, _vo, total = timeline(plan)
    return {"lines": c["lines"], "shots": c["shots"], "splits": c["splits"], "maps": c["maps"], "chapters": c["chapters"],
            "real": c["real"], "seconds": total, "warnings": c["warnings"]}


def load(work: str) -> Optional[Dict[str, Any]]:
    f = Path(work) / PLAN_FILE
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except Exception:  # noqa: BLE001
        return None


def timeline(plan: Dict[str, Any]):
    """Shots with start/len: each line's shots share its voice time (a map shot a little less); a breath before chapters."""
    t, shots, vo = 0.35, [], []
    for i, ln in enumerate(plan["lines"]):
        sh = ln["shots"]
        is_chap = sh[0]["kind"] == "chapter"
        if is_chap and i:
            t += 0.45
        d = float(ln.get("vo_dur") or words_seconds(ln["text"]))
        vo.append((ln.get("vo"), t))
        start = 0.0 if i == 0 else t - 0.15
        span_end = t + d + float(plan.get("vo_gap", 0.32))
        weights = [0.75 if s["kind"] == "map" and len(sh) > 1 else 1.0 for s in sh]
        a = start
        for s, w in zip(sh, weights):
            shots.append(dict(s, start=a, line=i, chapter=is_chap))
            a += (span_end - start) * w / sum(weights)
        t = span_end
    total = t + 2.2
    for k, s in enumerate(shots):
        nxt = shots[k + 1]["start"] if k + 1 < len(shots) else total
        s["len"] = round(nxt - s["start"], 3)
    return shots, vo, total


# ---------------------------------------------------------------------------------------------------------------- shots

def usable_end(cuts: Optional[List[float]], seconds: float) -> float:
    """Where a trailer's own footage stops: the last cut in its final quarter (the logo / date card after it is never used)."""
    late = [c for c in (cuts or []) if c >= seconds * 0.75]
    return late[-1] if late else seconds


_AVOID: Dict[str, List[List[float]]] = {}


def avoid_ranges(path: str) -> List[List[float]]:
    """Title / logo / rating cards of a trailer, from '<name>.avoid.json' beside it ({"text_cards": [[start, end], ...]})."""
    key = str(path)
    if key not in _AVOID:
        f = Path(path).with_suffix("").with_name(Path(path).stem + ".avoid.json")
        try:
            _AVOID[key] = [list(map(float, r)) for r in json.loads(f.read_text(encoding="utf-8")).get("text_cards", [])]
        except Exception:  # noqa: BLE001 - no file: nothing to avoid
            _AVOID[key] = []
    return _AVOID[key]


def _dodge(t_in: float, span: float, ranges: List[List[float]]) -> float:
    """Start earlier when a shot starting outside a text card would play into one ahead of it (a shot placed on a card on
    purpose is left alone)."""
    for r0, r1 in sorted(ranges):
        if t_in < r0 < t_in + span:
            return max(0.0, r0 - span - 0.05)
    return t_in


def _clip(path: str, t_in: float, L_: float, cuts: Optional[List[float]] = None, seconds: float = 0.0):
    """Input args + filter giving exactly L_ s of moving footage from path at t_in. A shot that fits before the next cut stays
    inside it (at most 15% slower); a longer one plays on at normal speed through the trailer's own next shots, as the trailer
    is edited, instead of slowing down and freezing. It never runs into the end logo: it starts earlier when it would."""
    seconds = seconds or duration(path)
    stop = usable_end(cuts, seconds) if cuts else seconds
    nxt = [c for c in (cuts or []) if c > t_in + 0.05]
    end = min(nxt[0] if nxt else stop, stop)
    avail = max(0.2, end - t_in - 0.06)
    if avail >= L_ * 0.85:
        slow = min(1.0, avail / L_)
        take = min(avail, L_ * slow)
    else:
        slow = 1.0
        if t_in + L_ > stop - 0.06:
            t_in = max(0.0, stop - 0.06 - L_)
        t_in = _dodge(t_in, L_, avoid_ranges(path))
        take = min(L_, max(0.2, seconds - t_in))
    hold = max(0.0, L_ - take / slow)
    inp = ["-ss", f"{t_in:.3f}", "-t", f"{take:.3f}", "-i", str(path)]
    f = f"setpts=(PTS-STARTPTS)/{slow:.4f},fps={L.FPS}"
    if hold > 0.01:
        f += f",tpad=stop_mode=clone:stop_duration={hold + 0.1:.3f}"
    return inp, f


def _encode(inputs: List[str], fc: str, L_: float, out: Path) -> None:
    _run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-t", f"{L_:.3f}", "-r", str(L.FPS),
          "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p", "-an", str(out)])


class _Ctx:
    def __init__(self, data: Dict[str, Any], found: Dict[int, str], work: Path, log):
        self.trailers = data["trailers"]
        self.found = {int(k): v for k, v in (found or {}).items() if v and Path(v).is_file()}
        self.work = work
        self.log = log
        self.pins = data["plan"]["pins"]
        self.map_base = None

    def game(self, s):
        tr = self.trailers.get(s["game"]) or {}
        return tr.get("path"), s["game_at"], tr.get("cuts"), tr.get("seconds", 0.0)

    def real(self, s):
        p = self.found.get(int(s.get("scene_no") or 0))
        if not p:
            return None, 0.0
        at = s["real_at"] if s.get("real_is_file") else (s["real_at"] or 1.0)
        return p, max(0.0, min(at, duration(p) - 3.0))


def render_shot(ctx: _Ctx, i: int, s: Dict[str, Any], out: Path) -> Path:
    kind, L_ = s["kind"], s["len"]
    png = ctx.work / f"ov{i:03d}.png"
    cover = f"scale={L.W}:{L.H}:force_original_aspect_ratio=increase,crop={L.W}:{L.H}"
    push = f"scale=w='trunc({L.W}*(1+0.06*t/{L_})/2)*2':h=-2:eval=frame,crop={L.W}:{L.H},setsar=1"
    if kind == "map":
        return render_map(ctx, s, L_, out)
    if kind == "storms":
        return render_storms(ctx, s, L_, out)
    if kind in ("board", "timeline"):
        return render_cards(ctx, i, s, L_, out)
    if kind == "dossier":
        return render_dossier(ctx, i, s, L_, out)
    if kind == "hud":
        return render_hud(ctx, i, s, L_, out)
    if kind == "tracker":
        return render_tracker(ctx, s, L_, out)
    if kind == "route":
        return render_route(ctx, s, L_, out)
    if kind in ("steps", "payout"):
        return render_states(ctx, i, s, L_, out)
    if kind in ("rank", "spot"):
        return render_marked(ctx, i, s, L_, out)
    real_p, real_at = ctx.real(s) if s.get("scene_no") else (None, 0.0)
    if kind == "versus":
        vf = s.get("vs_file", "")
        if not vf or not Path(vf).is_file():
            ctx.log(f"row {s['row']}: older-game clip missing ({s['real']}) - the new trailer plays full screen")
            return render_shot(ctx, i, dict(s, kind="game"), out)
        real_p, real_at = vf, max(0.0, min(float(s["real_at"] or 0.0), duration(vf) - 1.0))
    if kind in ("split", "versus"):
        if not real_p:
            ctx.log(f"row {s['row']}: no real clip in the Visuals tab - the game shot plays full screen")
            return render_shot(ctx, i, dict(s, kind="game"), out)
        pills = ("GTA VI", "GTA V") if kind == "versus" else ("IN GAME", "REAL LIFE")
        L.split_png(s["left"], s["right"], png, L.receipt(s["game"], s["game_at"]), pills)
        gp, gt, gc, gs = ctx.game(s)
        gi, gf = _clip(gp, gt, L_, gc, gs)
        ri, rf = _clip(real_p, real_at, L_)
        half = f"scale=-2:{L.H},crop={L.W // 2}:{L.H},setsar=1"
        fc = (f"[0:v]{gf},{half}[g];[2:v]{rf},{half}[r];color=c=black:s={L.W}x{L.H}:r={L.FPS}:d={L_}[base];"
              f"[base][g]overlay=0:0[b1];[b1][r]overlay=x='{L.W // 2}+{L.W // 2}*pow(max(0,1-(t-0.25)/0.45),3)':y=0[b2];"
              f"[1:v]format=rgba,fade=in:st=0.3:d=0.3:alpha=1[ov];[b2][ov]overlay=0:0,{L.GLITCH}[v]")
        _encode([*gi, "-loop", "1", "-t", f"{L_:.3f}", "-i", str(png), *ri], fc, L_, out)
        return out
    # one source full screen: game, real, title, chapter
    if kind == "game" or (kind in ("title", "chapter") and s["game"]):
        src, t_in, cuts, secs = ctx.game(s)
    elif real_p:
        src, t_in, cuts, secs = real_p, real_at, None, 0.0
    else:
        ctx.log(f"row {s['row']}: no real clip in the Visuals tab - a title card stands in")
        src = None
    if src is None:
        L.title_png((s["real"] or s["title"] or "REAL LIFE").upper()[:28], "", "REAL LIFE", png)
        fc = f"color=c=0x0c1028:s={L.W}x{L.H}:r={L.FPS}:d={L_}[bg];[0:v]format=rgba[ov];[bg][ov]overlay=0:0,{L.GLITCH}[v]"
        _encode(["-loop", "1", "-t", f"{L_:.3f}", "-i", str(png)], fc, L_, out)
        return out
    if kind in ("game", "real"):
        if kind == "game" and L.is_ai_clip(s["game"]):
            L.chip_png(False, png, "", "AI RECREATION")
        else:
            L.chip_png(kind == "real", png, L.receipt(s["game"], s["game_at"]) if kind == "game" else "")
        delay, yoff = 0.1, "0"
    elif kind == "title":
        L.title_png(s["title"].upper(), s["subtitle"].upper(), "", png)
        delay, yoff = 0.15, "60*pow(max(0,1-(t-0.15)/0.4),2)"
    else:
        L.chapter_png(s.get("number", ""), s["title"].upper(), s["subtitle"].upper(), png)
        delay, yoff = 0.05, "60*pow(max(0,1-(t-0.05)/0.4),2)"
    ci, cf = _clip(src, t_in, L_, cuts, secs)
    fc = (f"[0:v]{cf},{cover},{push}[bg];[1:v]format=rgba,fade=in:st={delay}:d=0.35:alpha=1[ov];"
          f"[bg][ov]overlay=x=0:y='{yoff}',{L.GLITCH}[v]")
    _encode([*ci, "-loop", "1", "-t", f"{L_:.3f}", "-i", str(png)], fc, L_, out)
    return out


# ---------------------------------------------------------------------------------------------------------------- map

MW, MH = 3840, 2160


def _base_map(ctx: _Ctx):
    """Satellite imagery of all the pins (free tiles, cached by the Aviation basemap), tinted night-blue; a grid if offline."""
    if ctx.map_base is not None:
        return ctx.map_base
    pts = [(p["lat"], p["lon"]) for p in ctx.pins] or [(0.0, 0.0)]
    bb = None
    img = None
    try:
        import numpy as np
        from aviation import basemap as B

        bb = B.fit_bbox(pts, pad=0.22, aspect=16 / 9, min_km=120.0)
        a = B.imagery(bb, (MW, MH), B.sat_tile)
        if a is not None:
            rgb = a[..., :3]
            rgb = rgb * 0.55 + np.array(L.NAVY, dtype=np.float32) * 0.45
            img = Image.fromarray(np.clip(rgb, 0, 255).astype("uint8"), "RGB")
    except Exception as exc:  # noqa: BLE001 - the map still draws without imagery
        ctx.log(f"satellite map not available ({type(exc).__name__}); a plain map is used")
    if img is None:
        img = Image.new("RGB", (MW, MH), (10, 16, 40))
        d = ImageDraw.Draw(img)
        for gx in range(0, MW, 160):
            d.line([(gx, 0), (gx, MH)], fill=(22, 34, 66), width=2)
        for gy in range(0, MH, 160):
            d.line([(0, gy), (MW, gy)], fill=(22, 34, 66), width=2)

    def px(lat, lon):
        if bb is not None:
            from aviation import basemap as B
            return B.to_px(bb, lat, lon, MW, MH)
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        x0, x1 = min(lons) - 1, max(lons) + 1
        y0, y1 = min(lats) - 1, max(lats) + 1
        return (lon - x0) / (x1 - x0) * MW, (y1 - lat) / (y1 - y0) * MH

    ctx.map_base = (img, px)
    return ctx.map_base


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def render_map(ctx: _Ctx, s: Dict[str, Any], L_: float, out: Path) -> Path:
    if s.get("game") and s.get("kind") == "map":
        tmp = out.with_name(out.stem + "_map.mp4")
        _draw_map(ctx, s, L_, tmp)
        return _map_inset(ctx, s, L_, tmp, out)
    return _draw_map(ctx, s, L_, out)


def _draw_map(ctx: _Ctx, s: Dict[str, Any], L_: float, out: Path) -> Path:
    base, px = _base_map(ctx)
    n = int(round(L_ * L.FPS))
    focus = s.get("pin")
    tc = px(focus["lat"], focus["lon"]) if focus else (MW / 2, MH / 2)
    tz = 2.6 if focus else 1.0
    pins = [focus] if focus else ctx.pins
    sides: Dict[str, int] = {}
    placed: List[tuple] = []
    for p in pins:                                  # label to the left near the right edge or when it would sit on another label
        x, y = px(p["lat"], p["lon"])
        side = -1 if x > MW * 0.62 else 1
        for (qx, qy, qs) in placed:
            if abs(qy - y) < 110 and abs(qx - x) < 700 and qs == side:
                side = -side
        sides[p["name"]] = side
        placed.append((x, y, side))
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L.W}x{L.H}",
                             "-r", str(L.FPS), "-i", "-", "-vf", L.GLITCH, "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                             "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    big, small = (L.font(L.F_HEAD, 64), L.font(L.F_TAG, 30)) if focus else (L.font(L.F_HEAD, 46), L.font(L.F_TAG, 24))
    try:
        for f in range(n):
            t = f / L.FPS
            k = _ease((t - 0.2) / 1.6)
            z = 1.0 + (tz - 1.0) * k if focus else 1.0 + 0.05 * t / L_
            cx = MW / 2 + (tc[0] - MW / 2) * k
            cy = MH / 2 + (tc[1] - MH / 2) * k
            cw, ch = MW / z, MH / z
            x0 = min(max(0, cx - cw / 2), MW - cw)
            y0 = min(max(0, cy - ch / 2), MH - ch)
            frame = base.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((L.W, L.H), Image.BILINEAR).convert("RGBA")
            d = ImageDraw.Draw(frame)
            sc = L.W / cw
            for j, p in enumerate(pins):
                appear = 1.2 if focus else 0.5 + j * 0.55
                if t < appear:
                    continue
                q = _ease((t - appear) / 0.35)
                bx, by = px(p["lat"], p["lon"])
                x, y = (bx - x0) * sc, (by - y0) * sc
                r = 16 * q + 5 * math.sin(t * 5) * q
                d.ellipse((x - r - 10, y - r - 10, x + r + 10, y + r + 10), outline=L.PINK + (int(150 * q),), width=4)
                d.ellipse((x - r, y - r, x + r, y + r), fill=L.PINK + (255,), outline=L.WHITE, width=4)
                side = sides.get(p["name"], 1)
                tx = x + side * 34
                a = int(255 * q)
                d.text((tx + 3, y + 5), p["name"].upper(), font=big, fill=(0, 0, 0, a // 2), anchor="ls" if side > 0 else "rs")
                d.text((tx, y + 2), p["name"].upper(), font=big, fill=L.WHITE + (a,), anchor="ls" if side > 0 else "rs")
                if p.get("real"):
                    d.text((tx, y + (34 if focus else 26)), "= " + p["real"].upper(), font=small, fill=L.TEAL + (a,),
                           anchor="lt" if side > 0 else "rt")
            if s.get("title") and t > 0.6:
                ov = Image.new("RGBA", (L.W, L.H), (0, 0, 0, 0))
                L.shadow_text(ov, (L.W // 2, 200), s["title"].upper(), L.fit(s["title"].upper(), L.F_HEAD, 130, L.W - 200))
                if s.get("subtitle"):
                    L.shadow_text(ov, (L.W // 2, 300), s["subtitle"].upper(), L.font(L.F_TAG, 40), fill=L.TEAL)
                q = _ease((t - 0.6) / 0.4)
                ov.putalpha(ov.getchannel("A").point(lambda v, q=q: int(v * q)))
                frame.alpha_composite(ov)
            proc.stdin.write(frame.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        proc.wait()
    if proc.returncode:
        raise RuntimeError(f"map encode failed: {err[-300:]}")
    return out



def _bg_input(ctx: _Ctx, s: Dict[str, Any], L_: float, blur: bool = True):
    """Inputs + filter for a card's moving background: the row's trailer shot, darkened (blurred), or plain navy."""
    if s.get("game"):
        gp, gt, gc, gs = ctx.game(s)
        if gp:
            gi, gf = _clip(gp, gt, L_, gc, gs)
            soft = ",boxblur=18:2" if blur else ""
            return gi, (f"[0:v]{gf},scale={L.W}:{L.H}:force_original_aspect_ratio=increase,crop={L.W}:{L.H},setsar=1{soft},"
                        f"eq=brightness=-0.12[bg]")
    return [], f"color=c=0x0c1028:s={L.W}x{L.H}:r={L.FPS}:d={L_:.3f}[bg]"


def render_cards(ctx: _Ctx, i: int, s: Dict[str, Any], L_: float, out: Path) -> Path:
    """Scoreboard or timeline: the frame first, then each item fades in on its own beat (board: old items are there at once)."""
    items = s["items"]
    stem = f"c{i:03d}"
    if s["kind"] == "board":
        pngs = L.board_pngs((s["title"] or "CONFIRMED OR NOT?").upper(), items, ctx.work, stem)
    else:
        pngs = L.timeline_pngs((s["title"] or "THE ROAD TO LAUNCH").upper(), items, ctx.work, stem)
    animate = [k for k in range(len(items)) if s["kind"] == "timeline" or items[k]["new"]]
    if s["kind"] == "board" and not animate:          # nothing marked new: tick them all in
        animate = list(range(len(items)))
    t0, t1 = 0.45, max(0.9, L_ - 0.9)
    step = (t1 - t0) / max(1, len(animate))
    at = {k: t0 + n * step for n, k in enumerate(animate)}
    inputs, fc_bits = [], []
    gi, bg = _bg_input(ctx, s, L_)
    inputs += gi
    n0 = 1 if gi else 0
    last = "bg"
    for j, (png, k) in enumerate(pngs):
        idx = n0 + j
        inputs += ["-loop", "1", "-t", f"{L_:.3f}", "-i", str(png)]
        st = 0.1 if k < 0 else at.get(k, 0.1)
        fc_bits.append(f"[{idx}:v]format=rgba,fade=in:st={st:.3f}:d=0.3:alpha=1[o{j}]")
        nxt = f"b{j}"
        fc_bits.append(f"[{last}][o{j}]overlay=0:0[{nxt}]")
        last = nxt
    fc = ";".join([bg] + fc_bits) + f";[{last}]{L.GLITCH}[v]"
    _encode(inputs, fc, L_, out)
    return out


def render_states(ctx: _Ctx, i: int, s: Dict[str, Any], L_: float, out: Path) -> Path:
    """Walkthrough steps (sharp gameplay, a panel lighting one step at a time) or a payout board (blurred gameplay, money ticking
    in with the total): one full picture per state, each shown in its own window of the shot."""
    stem = f"g{i:03d}"
    items = s["items"]
    if s["kind"] == "steps":
        pngs = L.steps_pngs(s["title"] or "HOW TO DO IT", items, ctx.work, stem)
        step = L_ / max(1, len(pngs))
        starts = [k * step for k in range(len(pngs))]
        gi, bg = _bg_input(ctx, s, L_, blur=False)
    else:
        pngs = L.payout_pngs(s["title"] or "HOW MUCH YOU MAKE", items, ctx.work, stem)
        t0, t1 = 0.45, max(0.9, L_ - 0.9)
        step = (t1 - t0) / max(1, len(items))
        starts = [0.0] + [t0 + k * step for k in range(len(items))]
        gi, bg = _bg_input(ctx, s, L_)
    inputs, bits, last = list(gi), [], "bg"
    n0 = 1 if gi else 0
    for j, png in enumerate(pngs):
        inputs += ["-loop", "1", "-t", f"{L_:.3f}", "-i", str(png)]
        a = starts[j]
        b = starts[j + 1] if j + 1 < len(pngs) else L_ + 1
        fade = ",fade=in:st=0.1:d=0.3:alpha=1" if j == 0 else ""
        bits.append(f"[{n0 + j}:v]format=rgba{fade}[o{j}]")
        bits.append(f"[{last}][o{j}]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[b{j}]")
        last = f"b{j}"
    fc = ";".join([bg] + bits) + f";[{last}]{L.GLITCH}[v]"
    _encode(inputs, fc, L_, out)
    return out


def render_marked(ctx: _Ctx, i: int, s: Dict[str, Any], L_: float, out: Path) -> Path:
    """Gameplay full screen with a mark on it: a countdown entry (#N + name, slow push in) or a spot (a pulsing ring on the
    place and its tag; no push, so the ring stays on the place)."""
    gp, gt, gc, gs = ctx.game(s)
    if not gp:
        return render_shot(ctx, i, dict(s, kind="title", game=""), out)
    gi, gf = _clip(gp, gt, L_, gc, gs)
    cover = f"scale={L.W}:{L.H}:force_original_aspect_ratio=increase,crop={L.W}:{L.H},setsar=1"
    if s["kind"] == "rank":
        png = ctx.work / f"ov{i:03d}.png"
        L.rank_png(s.get("number", "#1"), s["title"], s["subtitle"], png)
        push = f"scale=w='trunc({L.W}*(1+0.06*t/{L_})/2)*2':h=-2:eval=frame,crop={L.W}:{L.H},setsar=1"
        fc = (f"[0:v]{gf},{cover},{push}[bg];[1:v]format=rgba,fade=in:st=0.12:d=0.35:alpha=1[ov];"
              f"[bg][ov]overlay=x=0:y='50*pow(max(0,1-(t-0.12)/0.4),2)',{L.GLITCH}[v]")
        _encode([*gi, "-loop", "1", "-t", f"{L_:.3f}", "-i", str(png)], fc, L_, out)
        return out
    ring, pulse, label = L.spot_pngs(s["title"] or "IT'S HERE", s["subtitle"], s.get("spot") or (0.5, 0.5), ctx.work, f"s{i:03d}")
    ins = [*gi]
    for f in (ring, pulse, label):
        ins += ["-loop", "1", "-t", f"{L_:.3f}", "-i", str(f)]
    fc = (f"[0:v]{gf},{cover}[bg];[1:v]format=rgba,fade=in:st=0.35:d=0.25:alpha=1[r];[2:v]format=rgba[p];"
          f"[3:v]format=rgba,fade=in:st=0.6:d=0.3:alpha=1[l];[bg][r]overlay=0:0[b1];"
          f"[b1][p]overlay=0:0:enable='gte(t,0.6)*lt(mod(t-0.6,0.8),0.4)'[b2];[b2][l]overlay=0:0,{L.GLITCH}[v]")
    _encode(ins, fc, L_, out)
    return out


def render_dossier(ctx: _Ctx, i: int, s: Dict[str, Any], L_: float, out: Path) -> Path:
    """Character file: the trailer shot blurred behind, the same shot sharp in a framed box, name / role / line / first seen."""
    png = ctx.work / f"ov{i:03d}.png"
    L.dossier_png(s["title"], s.get("role", ""), s.get("line_text", ""), L.receipt(s["game"], s["game_at"]), png)
    gp, gt, gc, gs = ctx.game(s)
    if not gp:
        return render_shot(ctx, i, dict(s, kind="title", game=""), out)
    gi, gf = _clip(gp, gt, L_, gc, gs)
    x0, y0, x1, y1 = L.DOSSIER_BOX
    bw, bh = x1 - x0, y1 - y0
    fc = (f"[0:v]{gf},split[a][b];[a]scale={L.W}:{L.H}:force_original_aspect_ratio=increase,crop={L.W}:{L.H},setsar=1,"
          f"boxblur=24:2,eq=brightness=-0.22[bg];[b]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},setsar=1[fg];"
          f"[bg][fg]overlay={x0}:{y0}[b1];[1:v]format=rgba,fade=in:st=0.1:d=0.35:alpha=1[ov];"
          f"[b1][ov]overlay=0:0,{L.GLITCH}[v]")
    _encode([*gi, "-loop", "1", "-t", f"{L_:.3f}", "-i", str(png)], fc, L_, out)
    return out


def render_hud(ctx: _Ctx, i: int, s: Dict[str, Any], L_: float, out: Path) -> Path:
    """An ILLUSTRATION card (game_launch/hud.py) over the row's trailer shot (blurred) or navy: layers fade in on their beats,
    some flash."""
    from . import hud as HUD

    lay = HUD.layers(s["title"], s["subtitle"], ctx.work, f"h{i:03d}")
    inputs, bits = [], []
    gi, bg = _bg_input(ctx, s, L_, blur=s["title"].strip().lower() != "waink")
    inputs += gi
    n0 = 1 if gi else 0
    last = "bg"
    for j, l_ in enumerate(lay):
        inputs += ["-loop", "1", "-t", f"{L_:.3f}", "-i", l_["png"]]
        st = max(0.05, float(l_.get("at") or 0.0) * L_)
        bits.append(f"[{n0 + j}:v]format=rgba,fade=in:st={st:.3f}:d=0.3:alpha=1[o{j}]")
        en = ""
        if l_.get("blink") is not None:
            en = f":enable='{'lt' if l_['blink'] == 0 else 'gte'}(mod(t,0.5),0.25)'"
        bits.append(f"[{last}][o{j}]overlay=0:0{en}[b{j}]")
        last = f"b{j}"
    fc = ";".join([bg] + bits) + f";[{last}]{L.GLITCH}[v]"
    _encode(inputs, fc, L_, out)
    return out


def render_tracker(ctx: _Ctx, s: Dict[str, Any], L_: float, out: Path) -> Path:
    """The speed-tracker story drawn frame by frame on the satellite map, zoomed onto the Keys road."""
    from . import hud as HUD

    base, px = _base_map(ctx)
    pts = [px(la, lo) for la, lo in HUD.ROUTE]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), (max(ys) - min(ys)) * 16 / 9) * 1.7
    cw = min(MW, max(span, MW / 4))
    ch = cw * 9 / 16
    x0 = min(max(0, cx - cw / 2), MW - cw)
    y0 = min(max(0, cy - ch / 2), MH - ch)
    small = base.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((L.W, L.H), Image.BILINEAR).convert("RGBA")
    sc = L.W / cw

    def to_px(la, lo):
        bx, by = px(la, lo)
        return (bx - x0) * sc, (by - y0) * sc

    n = int(round(L_ * L.FPS))
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L.W}x{L.H}",
                             "-r", str(L.FPS), "-i", "-", "-vf", L.GLITCH, "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                             "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for fno in range(n):
            proc.stdin.write(HUD.tracker_frame(small, to_px, fno / L.FPS, L_, s.get("title", "").upper()).convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        proc.wait()
    if proc.returncode:
        raise RuntimeError(f"tracker encode failed: {err[-300:]}")
    return out


def render_route(ctx: _Ctx, s: Dict[str, Any], L_: float, out: Path) -> Path:
    """Fog-of-war route: the satellite map starts under dark fog; a glowing green route draws stop to stop and clears the fog
    around it, each stop pins and names itself as the route reaches it."""
    from PIL import ImageFilter

    base, px = _base_map(ctx)
    stops = s["stops"]
    pts = [px(q["lat"], q["lon"]) for q in stops]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    cw = min(MW, max((max(xs) - min(xs)) * 1.6, (max(ys) - min(ys)) * 1.9 * 16 / 9, MW / 3))
    ch = cw * 9 / 16
    cy -= ch * 0.08                                  # room at the top for the heading
    x0 = min(max(0, cx - cw / 2), MW - cw)
    y0 = min(max(0, cy - ch / 2), MH - ch)
    sc = L.W / cw
    small = base.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((L.W, L.H), Image.BILINEAR).convert("RGBA")
    P2 = [((x - x0) * sc, (y - y0) * sc) for x, y in pts]
    seglen = [math.dist(P2[k], P2[k + 1]) for k in range(len(P2) - 1)]
    total_len = sum(seglen) or 1.0
    reveal = Image.new("L", (L.W, L.H), 0)
    rd = ImageDraw.Draw(reveal)
    fog_col = Image.new("RGBA", (L.W, L.H), (6, 8, 18, 255))
    n = int(round(L_ * L.FPS))
    t0, t1 = 0.4, max(0.8, L_ - 1.0)
    big, small_f = L.font(L.F_HEAD, 54), L.font(L.F_TAG, 26)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L.W}x{L.H}",
                             "-r", str(L.FPS), "-i", "-", "-vf", L.GLITCH, "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                             "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    rd.ellipse((P2[0][0] - 170, P2[0][1] - 170, P2[0][0] + 170, P2[0][1] + 170), fill=255)
    try:
        for fno in range(n):
            t = fno / L.FPS
            q = _ease((t - t0) / (t1 - t0))
            dist = q * total_len
            path, acc = [P2[0]], 0.0
            for k, sl in enumerate(seglen):
                if acc + sl <= dist:
                    path.append(P2[k + 1])
                    acc += sl
                else:
                    f = (dist - acc) / sl if sl else 0
                    path.append((P2[k][0] + (P2[k + 1][0] - P2[k][0]) * f, P2[k][1] + (P2[k + 1][1] - P2[k][1]) * f))
                    break
            hx, hy = path[-1]
            rd.ellipse((hx - 190, hy - 190, hx + 190, hy + 190), fill=255)
            soft = reveal.filter(ImageFilter.GaussianBlur(40))
            fog = fog_col.copy()
            fog.putalpha(soft.point(lambda v: int(225 * (1 - v / 255))))
            frame = small.copy()
            frame.alpha_composite(fog)
            d = ImageDraw.Draw(frame)
            if len(path) >= 2:
                d.line(path, fill=(0, 255, 140, 90), width=26, joint="curve")
                d.line(path, fill=(120, 255, 180, 255), width=9, joint="curve")
            d.ellipse((hx - 14, hy - 14, hx + 14, hy + 14), fill=L.WHITE + (255,), outline=(0, 200, 120, 255), width=5)
            for k, (q_, (x, y)) in enumerate(zip(stops, P2)):
                reached = k == 0 or sum(seglen[:k]) <= dist + 1
                if not reached:
                    continue
                d.ellipse((x - 16, y - 16, x + 16, y + 16), fill=L.PINK + (255,), outline=L.WHITE, width=4)
                side = -1 if x > L.W * 0.62 else 1
                anc = "ls" if side > 0 else "rs"
                d.text((x + side * 30 + 3, y + 5), q_["name"].upper(), font=big, fill=(0, 0, 0, 160), anchor=anc)
                d.text((x + side * 30, y + 2), q_["name"].upper(), font=big, fill=L.WHITE, anchor=anc)
                if q_.get("real"):
                    d.text((x + side * 30, y + 34), q_["real"].upper(), font=small_f, fill=L.TEAL + (255,),
                           anchor="lt" if side > 0 else "rt")
            if s.get("title"):
                L.shadow_text(frame, (L.W // 2, 100), s["title"].upper(), L.fit(s["title"].upper(), L.F_HEAD, 96, L.W - 300))
            L.pill(frame, (60, 56), "ILLUSTRATION", (90, 90, 110), 30)
            proc.stdin.write(frame.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        proc.wait()
    if proc.returncode:
        raise RuntimeError(f"route encode failed: {err[-300:]}")
    return out


INSET = (90, 600, 650, 915)                       # map corner box for the region's trailer shot (560x315)


def _map_inset(ctx: _Ctx, s: Dict[str, Any], L_: float, map_mp4: Path, out: Path) -> Path:
    gp, gt, gc, gs = ctx.game(s)
    if not gp:
        map_mp4.replace(out)
        return out
    png = ctx.work / f"inset_{out.stem}.png"
    L.inset_png(L.receipt(s["game"], s["game_at"]), png, INSET)
    x0, y0, x1, y1 = INSET
    bw, bh = x1 - x0, y1 - y0
    st = min(1.5, L_ * 0.35)
    gi, gf = _clip(gp, gt, L_, gc, gs)
    fc = (f"[1:v]{gf},scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},setsar=1,format=yuva420p,"
          f"fade=in:st={st:.2f}:d=0.35:alpha=1[g];[0:v][g]overlay={x0}:{y0}[b1];"
          f"[2:v]format=rgba,fade=in:st={st:.2f}:d=0.35:alpha=1[ov];[b1][ov]overlay=0:0[v]")
    _encode(["-i", str(map_mp4), *gi, "-loop", "1", "-t", f"{L_:.3f}", "-i", str(png)], fc, L_, out)
    return out


# ---------------------------------------------------------------------------------------------------------------- storms

HURDAT_INDEX = "https://www.nhc.noaa.gov/data/hurdat/"
STORM_COLORS = [(255, 46, 136), (0, 214, 201), (255, 196, 0), (160, 120, 255), (255, 120, 60), (120, 220, 90)]


def hurdat_text(cache_dir: Path, log=lambda m: None) -> str:
    """NOAA's Atlantic best track (HURDAT2), downloaded once and kept; '' when offline."""
    f = cache_dir / "hurdat2_atlantic.txt"
    if f.is_file() and f.stat().st_size > 1_000_000:
        return f.read_text(encoding="utf-8", errors="replace")
    try:
        import urllib.request

        from weather.post.besttrack import latest_file

        def get(url):
            req = urllib.request.Request(url, headers={"User-Agent": "video-generator/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", errors="replace")

        text = get(latest_file(get(HURDAT_INDEX), "AL"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return text
    except Exception as exc:  # noqa: BLE001
        log(f"hurricane tracks not available ({type(exc).__name__}: {exc})")
        return ""


def storm_tracks(text: str, ids: List[str], log=lambda m: None) -> List[Dict[str, Any]]:
    """[{id, name, year, label, points [(lat, lon)], peak, landfall (lat, lon) or None}] from HURDAT2; unknown ids are skipped."""
    from weather.post.besttrack import category, landfalls, parse_block, storm_block

    out = []
    for sid in ids:
        try:
            name, fixes = parse_block(storm_block(text, sid))
        except Exception as exc:  # noqa: BLE001
            log(f"storm {sid} skipped: {exc}")
            continue
        if not fixes:
            continue
        peak = max(fixes, key=lambda f: f.wind_kt)
        fl = [f for f in landfalls(fixes) if 24.0 <= f.lat <= 31.2 and -88.0 <= f.lon <= -79.8]
        cat = category(peak.wind_kt, peak.status).replace("CATEGORY ", "CAT ").replace(" HURRICANE", "")
        out.append({"id": sid, "name": name.title(), "year": fixes[0].time.year, "points": [(f.lat, f.lon) for f in fixes],
                    "landfall": (fl[0].lat, fl[0].lon) if fl else None,
                    "label": f"{name.upper()} {fixes[0].time.year}  ·  PEAK {cat}"})
    return out


def render_storms(ctx: _Ctx, s: Dict[str, Any], L_: float, out: Path) -> Path:
    """Real hurricane tracks drawn one after another on the satellite map (NOAA best track), each named at its Florida landfall."""
    base, px = _base_map(ctx)
    tracks = storm_tracks(hurdat_text(ctx.work.parent / "cache", ctx.log), s.get("storms", []), ctx.log)
    if not tracks:
        ctx.log(f"row {s['row']}: no storm track could be drawn - the plain map is shown")
        return render_map(ctx, dict(s, kind="map", pin=None), L_, out)
    n = int(round(L_ * L.FPS))
    big, small = L.font(L.F_HEAD, 44), L.font(L.F_TAG, 22)
    t0, t1 = 0.5, max(1.0, L_ - 0.8)
    each = (t1 - t0) / len(tracks)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L.W}x{L.H}",
                             "-r", str(L.FPS), "-i", "-", "-vf", L.GLITCH, "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                             "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    sc = L.W / MW
    small_base = base.resize((L.W, L.H), Image.BILINEAR).convert("RGBA")
    try:
        for fno in range(n):
            t = fno / L.FPS
            frame = small_base.copy()
            d = ImageDraw.Draw(frame)
            for k, tr in enumerate(tracks):
                a = t0 + k * each
                if t < a:
                    continue
                q = _ease((t - a) / (each * 0.85))
                pts = [tuple(c * sc for c in px(la, lo)) for la, lo in tr["points"]]
                upto = max(2, int(len(pts) * q))
                col = STORM_COLORS[k % len(STORM_COLORS)]
                d.line(pts[:upto], fill=(0, 0, 0, 150), width=11, joint="curve")
                d.line(pts[:upto], fill=col + (255,), width=6, joint="curve")
                hx, hy = pts[upto - 1]
                d.ellipse((hx - 11, hy - 11, hx + 11, hy + 11), fill=col + (255,), outline=L.WHITE, width=3)
                if q >= 1.0 or upto == len(pts):
                    lx, ly = (tuple(c * sc for c in px(*tr["landfall"])) if tr["landfall"] else pts[-1])
                    d.ellipse((lx - 9, ly - 9, lx + 9, ly + 9), fill=L.WHITE, outline=col, width=4)
                    side = -1 if lx > L.W * 0.6 else 1
                    anchor = "ls" if side > 0 else "rs"
                    d.text((lx + side * 22 + 2, ly + 4), tr["label"], font=small, fill=(0, 0, 0, 200), anchor=anchor)
                    d.text((lx + side * 22, ly + 2), tr["label"], font=small, fill=L.WHITE, anchor=anchor)
            if s.get("title"):
                L.shadow_text(frame, (L.W // 2, 110), s["title"].upper(), L.fit(s["title"].upper(), L.F_HEAD, 96, L.W - 300))
            d.text((L.W - 40, L.H - 30), "TRACKS: NOAA NATIONAL HURRICANE CENTER (HURDAT2)", font=small,
                   fill=(255, 255, 255, 170), anchor="rs")
            proc.stdin.write(frame.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        proc.wait()
    if proc.returncode:
        raise RuntimeError(f"storm map encode failed: {err[-300:]}")
    return out

# ---------------------------------------------------------------------------------------------------------------- render

def _mix(shots, vo, total, work: Path, out_wav: Path) -> None:
    ins, parts = [], []
    for j, (p, at) in enumerate(vo):
        ins += ["-i", str(p)]
        parts.append(f"[{j}:a]aresample=48000,adelay={int(at * 1000)}:all=1,volume=1.6[v{j}]")
    parts.append("".join(f"[v{j}]" for j in range(len(vo))) + f"amix=inputs={len(vo)}:normalize=0,apad=whole_dur={total}[vo]")
    voice = work / "voice_track.wav"
    _run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(parts), "-map", "[vo]", "-ac", "1", "-ar", "48000",
          str(voice)])
    mus = work / "music.wav"
    L.music(total, mus, cache=work / "cache")
    ins = ["-i", str(voice), "-i", str(mus)]
    parts, tags = [], []
    k = 2
    if WHOOSH.is_file():
        for h in [s["start"] for s in shots if s["chapter"] or s["kind"] == "map"]:
            ins += ["-i", str(WHOOSH)]
            parts.append(f"[{k}:a]aresample=48000,adelay={max(0, int(h * 1000) - 150)}:all=1,volume=0.32[x{k}]")
            tags.append(f"[x{k}]")
            k += 1
    if IMPACT.is_file():
        for h in [s["start"] for s in shots if s["kind"] == "chapter"]:
            ins += ["-i", str(IMPACT)]
            parts.append(f"[{k}:a]aresample=48000,adelay={int(h * 1000) + 60}:all=1,volume=0.4[x{k}]")
            tags.append(f"[x{k}]")
            k += 1
    parts += ["[0:a]asplit=2[vo][sc]", "[1:a]aresample=48000,volume=0.5[m]",
              "[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck]",
              f"[vo][duck]{''.join(tags)}amix=inputs={len(tags) + 2}:normalize=0,alimiter=limit=0.9,atrim=0:{total}[a]"]
    _run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(parts), "-map", "[a]", "-ar", "48000", "-ac", "2",
          str(out_wav)])


def render(work: str, out_path: str, found: Dict[int, str], *, shorts: bool = True, thumbnail: bool = True,
           thumb_text: str = "", short_foot: str = "", progress=lambda f, m="": None, cancel: Callable[[], bool] = lambda: False,
           log=lambda m: None) -> Dict[str, Any]:
    data = load(work)
    if not data:
        raise ValueError("Click Generate first: there is no prepared plan.")
    wd = Path(work) / "render"
    wd.mkdir(parents=True, exist_ok=True)
    shots, vo, total = timeline(data["plan"])
    ctx = _Ctx(data, found, wd, log)
    files = []
    for i, s in enumerate(shots):
        if cancel():
            raise Cancelled()
        progress(0.85 * i / len(shots), f"shot {i + 1}/{len(shots)}")
        files.append(render_shot(ctx, i, s, wd / f"shot{i:03d}.mp4"))
    progress(0.86, "joining and grading")
    lst = wd / "concat.txt"
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in files), encoding="utf-8")
    silent = wd / "video.mp4"
    bar_in, bar_fc = progress_overlay(shots, total, wd)
    vf = ["-vf", L.GRADE] if not bar_in else ["-filter_complex", f"[0:v]{L.GRADE}[g0];{bar_fc}", "-map", "[v]"]
    _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), *bar_in, *vf, "-c:v", "libx264",
          "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
          "-colorspace", "bt709", str(silent)])
    if cancel():
        raise Cancelled()
    progress(0.92, "mixing voice, music and sound")
    mix = wd / "mix.wav"
    _mix(shots, vo, total, wd, mix)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
          "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    result: Dict[str, Any] = {"seconds": total, "shorts": [], "thumbnail": "", "shots": len(shots)}
    if shorts and not cancel():
        progress(0.95, "Shorts")
        result["shorts"] = make_shorts(out, shots, vo, total, short_foot, wd, log)
    if thumbnail and not cancel():
        try:
            result["thumbnail"] = make_thumbnail(ctx, shots, out.with_name(out.stem + "_thumbnail.jpg"), thumb_text, wd)
        except Exception as exc:  # noqa: BLE001 - the video is done; a thumbnail problem is only reported
            log(f"thumbnail not made: {exc}")
    progress(1.0, "done")
    return result


# ---------------------------------------------------------------------------------------------------------------- extras

def chapter_spans(shots, total) -> List[Dict[str, Any]]:
    """[{idx, title, start, end}] for each chapter: from its card to the next one; the last ends at the first scoreboard after it
    with no new (+) items (the recap) or at the end. Needs two chapters or more."""
    chap = [s for s in shots if s["kind"] == "chapter"]
    if len(chap) < 2:
        return []
    out = []
    for k, c in enumerate(chap):
        if k + 1 < len(chap):
            end = chap[k + 1]["start"]
        else:
            end = next((s["start"] for s in shots if s["start"] > c["start"] and s["kind"] == "board"
                        and not any(it.get("new") for it in s.get("items", []))), total)
        out.append({"idx": k, "title": c["title"], "start": c["start"] + c["len"], "end": end})
    return out


CARD_KINDS = {"chapter", "hud", "board", "timeline", "tracker", "dossier", "storms", "route", "steps", "payout"}   # full-frame cards with their own heading


def _bar_windows(shots, a: float, b: float) -> List[tuple]:
    """Parts of [a, b] not covered by a full-frame card (the bar would sit on the card's heading)."""
    out, cur = [], a
    for s in shots:
        if s["kind"] not in CARD_KINDS:
            continue
        s0, s1 = s["start"], s["start"] + s["len"]
        if s1 <= cur or s0 >= b:
            continue
        if s0 > cur:
            out.append((cur, s0))
        cur = max(cur, s1)
    if cur < b:
        out.append((cur, b))
    return [(x, y) for x, y in out if y - x > 0.05]


def progress_overlay(shots, total, wd: Path):
    """(ffmpeg inputs, filter) laying the chapter bar over [g0] -> [v] during each chapter (not over its own card)."""
    spans = chapter_spans(shots, total)
    if not spans:
        return [], ""
    ins, bits, last = [], [], "g0"
    for j, sp in enumerate(spans):
        png = wd / f"bar{j}.png"
        L.progress_png(len(spans), sp["idx"], sp["title"], png)
        ins += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(png)]
        nxt = "v" if j == len(spans) - 1 else f"g{j + 1}"
        on = _bar_windows(shots, sp["start"], sp["end"])
        en = "+".join(f"between(t,{x:.3f},{y:.3f})" for x, y in on) or "0"
        bits.append(f"[{j + 1}:v]format=rgba[p{j}];[{last}][p{j}]overlay=0:0:shortest=0:eof_action=pass:"
                    f"enable='{en}'[{nxt}]")
        last = nxt
    return ins, ";".join(bits)


def short_spans(shots, vo, total) -> List[Dict[str, Any]]:
    """One Short per chapter: from its chapter card to the next one, cut at a line end to stay under 59 s; 10 s at least."""
    starts = [at - 0.15 for _p, at in vo]
    ends = starts[1:] + [total]
    chap = [s for s in shots if s["kind"] == "chapter"]
    if not chap:                                      # a countdown video: one Short per top-5 entry, from its rank card
        chap = [s for s in shots if s["kind"] == "rank"][-5:]
    spans = []
    for k, c in enumerate(chap):
        first = c["line"]
        last = (chap[k + 1]["line"] - 1) if k + 1 < len(chap) else len(vo) - 1
        while last > first and ends[last] - starts[first] > 58.5:
            last -= 1
        a, b = starts[first], ends[last]
        if b - a < 10.0:
            continue
        sub = next((s["right"] for s in shots if first <= s["line"] <= last and s["kind"] == "split" and s["right"]), "")
        head = (f"{c['number']}  {c['title']}" if c["kind"] == "rank" and c.get("number") else c["title"]).upper()
        sub = sub or (c.get("subtitle", "") if c["kind"] == "rank" else "")
        spans.append({"start": max(0.0, a), "end": b, "title": head, "second": ("= " + sub) if sub and c["kind"] != "rank" else sub})
    return spans


def make_shorts(video: Path, shots, vo, total, foot: str, wd: Path, log) -> List[str]:
    outs = []
    for k, sp in enumerate(short_spans(shots, vo, total), start=1):
        ov = wd / f"short{k}.png"
        L.short_png(sp["title"], sp["second"], foot.upper(), ov)
        L_ = sp["end"] - sp["start"]
        out = video.with_name(f"{video.stem}_short{k}.mp4")
        fc = ("[0:v]split[x][y];[x]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:2,"
              "eq=brightness=-0.15[bg];[y]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2[v1];"
              f"[v1][1:v]overlay=0:0,fade=out:st={L_ - 0.6:.2f}:d=0.6[v];[0:a]afade=out:st={L_ - 0.8:.2f}:d=0.8[a]")
        try:
            _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{sp['start']:.3f}", "-t", f"{L_:.3f}", "-i", str(video), "-i", str(ov),
                  "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "19",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
            outs.append(str(out))
        except Exception as exc:  # noqa: BLE001
            log(f"Short {k} not made: {exc}")
    return outs


def _frame(path: str, at: float, dst: Path) -> Image.Image:
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, at):.2f}", "-i", str(path), "-frames:v", "1", str(dst)])
    return Image.open(dst)


def make_thumbnail(ctx: _Ctx, shots, out: Path, head: str, wd: Path) -> str:
    """The first split shot with a real clip: its game frame | real frame, the CSV's first title (or the page's text) in big letters."""
    for s in shots:
        if s["kind"] != "split":
            continue
        rp, rt = ctx.real(s)
        gp, gt, _c, _s = ctx.game(s)
        if not rp or not gp:
            continue
        left = _frame(gp, gt + 0.8, wd / "thumb_game.png")
        right = _frame(rp, rt + 1.5, wd / "thumb_real.png")
        title = head or next((x["title"] for x in shots if x["kind"] == "title" and x["title"]), "") or "IT'S REAL"
        sub = f"{s['left']} = {s['right']}" if s["left"] and s["right"] else ""
        L.thumbnail(left, right, title.upper(), sub, "IN GAME", out)
        return str(out)
    guide = [s for s in shots if s["kind"] in P.GUIDE_KINDS and ctx.game(s)[0]]   # a guide video: two of its gameplay frames
    if not guide:                                     # no splits, no guide shots: two plain gameplay shots instead
        guide = [s for s in shots if s["kind"] == "game" and ctx.game(s)[0]][2:]
    if guide:
        a, b = guide[0], guide[min(len(guide) - 1, max(1, len(guide) // 2))]
        left = _frame(ctx.game(a)[0], a["game_at"] + 0.8, wd / "thumb_game.png")
        right = _frame(ctx.game(b)[0], b["game_at"] + 0.8, wd / "thumb_real.png")
        title = head or next((x["title"] for x in shots if x["kind"] in ("title", "chapter") and x["title"]), "") or "FULL GUIDE"
        L.thumbnail(left, right, title.upper(), "", "GUIDE", out, right_tag="")
        return str(out)
    return ""
