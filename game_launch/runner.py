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
    for attempt in range(5):
        if f.is_file() and f.stat().st_size > 0:
            return f
        try:
            asyncio.run(_tts(_speakable(text, attempt), voice, f))
        except Exception as exc:  # noqa: BLE001
            log(f"voice retry {attempt + 1}: {exc}")
            f.unlink(missing_ok=True)
    raise RuntimeError(f"the Edge voice made no audio for: {text[:60]}")


# ---------------------------------------------------------------------------------------------------------------- prepare

def prepare(csv_path: str, trailers_dir: str, work: str, voice: str = DEFAULT_VOICE, log=lambda m: None,
            cancel: Callable[[], bool] = lambda: False, progress=lambda f, m="": None) -> Dict[str, Any]:
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
        span_end = t + d + 0.32
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

def _clip(path: str, t_in: float, L_: float, cuts: Optional[List[float]] = None, seconds: float = 0.0):
    """Input args + filter giving exactly L_ s from path at t_in, never past the next cut (slower, then a held frame)."""
    seconds = seconds or duration(path)
    nxt = [c for c in (cuts or []) if c > t_in + 0.05]
    end = min(nxt[0] if nxt else seconds, seconds)
    avail = max(0.2, end - t_in - 0.06)
    slow = max(0.45, min(1.0, avail / L_))
    take = min(avail, L_ * slow)
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
    real_p, real_at = ctx.real(s) if s.get("scene_no") else (None, 0.0)
    if kind == "split":
        if not real_p:
            ctx.log(f"row {s['row']}: no real clip in the Visuals tab - the game shot plays full screen")
            return render_shot(ctx, i, dict(s, kind="game"), out)
        L.split_png(s["left"], s["right"], png)
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
        L.chip_png(kind == "real", png)
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
    _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", L.GRADE, "-c:v", "libx264",
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

def short_spans(shots, vo, total) -> List[Dict[str, Any]]:
    """One Short per chapter: from its chapter card to the next one, cut at a line end to stay under 59 s; 10 s at least."""
    starts = [at - 0.15 for _p, at in vo]
    ends = starts[1:] + [total]
    chap = [s for s in shots if s["kind"] == "chapter"]
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
        spans.append({"start": max(0.0, a), "end": b, "title": c["title"].upper(), "second": ("= " + sub) if sub else ""})
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
    return ""
