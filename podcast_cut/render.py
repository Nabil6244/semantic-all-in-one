"""Podcast Cut renderer: the director's timeline -> the mp4.

1. audio   the kept stretches of the podcast cut on pauses (20 ms fades), silence under the "presents" card, levelled
           to -15 LUFS and otherwise untouched (no pitch, speed or EQ change: the reference channel changes none, measured
           2026-11-23); a dark music bed from assets/music (a new track every ~7 min, 4 s crossfades) about 12 dB under
           the voice, as the reference sits (music alone -26..-28 LUFS against speech -14..-16), dipping only ~2-3 dB
           while he talks; a limiter on top
2. video   pieces of about a minute drawn in parallel: every shot filled to the frame and graded (the camera and any
           ungraded clip get the Podcast Cut grade; library clips are graded already), exact frame counts so nothing
           drifts, then the caption strips, the watermark and the "presents" card laid over (PIL pictures)
3. join    the pieces are joined without re-encoding and the audio is muxed in

Size (1920, 1080) for the main video, (1280, 720) for previews, (1080, 1920) for Shorts.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import look

ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "assets" / "music"
MUSIC_ORDER = ["dark_fog", "echoes_of_time_v2", "ascending_the_vale", "lost_frontier", "despair_and_triumph", "interloper",
               "stormfront"]
FPS = 25
PIECE = 60.0
MUSIC_SWITCH = 7 * 60.0
VOICE_LUFS = -15.0
MUSIC_UNDER_DB = 12.0       # the bed's loudness below the voice (reference channel: ~12 dB)


class Stopped(Exception):
    pass


def _ff():
    from providers.media_clip.ffmpeg_clip import _ffmpeg
    return _ffmpeg()


def _run(cmd: List[str], timeout: float = 3600) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {(r.stderr or '').strip()[-600:]}")


_ENC: Dict[str, List[str]] = {}


def encoder(preview: bool = False) -> List[str]:
    """h264_videotoolbox on a Mac (fast), libx264 elsewhere; the same settings for every piece so they join by copy."""
    key = "p" if preview else "f"
    if key not in _ENC:
        out = subprocess.run([_ff(), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        if sys.platform == "darwin" and "h264_videotoolbox" in out:
            _ENC[key] = ["-c:v", "h264_videotoolbox", "-b:v", "5M" if preview else "9M", "-maxrate", "12M", "-profile:v", "high",
                         "-allow_sw", "1"]
        else:
            _ENC[key] = ["-c:v", "libx264", "-preset", "veryfast" if preview else "medium", "-crf", "21" if preview else "19"]
        _ENC[key] += ["-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 2)]
    return _ENC[key]


# ---------------------------------------------------------------------------------------------------------------- audio

def music_tracks() -> List[Path]:
    have = {p.stem: p for p in MUSIC.glob("*.opus")} | {p.stem: p for p in MUSIC.glob("*.mp3")}
    return [have[n] for n in MUSIC_ORDER if n in have] + [p for n, p in sorted(have.items()) if n not in MUSIC_ORDER]


def build_audio(source_audio: Path, segments: Sequence[Dict], card: Optional[Dict], length: float, out: Path,
                music: bool = True, music_under_db: float = MUSIC_UNDER_DB) -> Path:
    """The film's sound as one m4a (voice cut + music bed)."""
    parts, labels = [], []
    for k, s in enumerate(segments):
        a, b = float(s["src_start"]), float(s["src_end"])
        d = b - a
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"afade=t=in:d=0.02,afade=t=out:st={max(0.0, d - 0.03):.3f}:d=0.03[s{k}]")
        labels.append(f"[s{k}]")
        if card and s.get("role") == "hook" and k == 0:
            cd = float(card["out_end"]) - float(card["out_start"])
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={cd:.3f}[gap]")
            labels.append("[gap]")
    parts.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1,"
                 "highpass=f=70,acompressor=threshold=0.09:ratio=2.5:attack=15:release=250,"
                 f"loudnorm=I={VOICE_LUFS:g}:TP=-1.5:LRA=11,aresample=48000[voice]")
    inputs = ["-i", str(source_audio)]
    tracks = music_tracks() if music else []
    if tracks:
        n = max(1, int(length // MUSIC_SWITCH) + 1)
        seg = length / n + 4.0
        for k in range(n):
            inputs += ["-stream_loop", "-1", "-i", str(tracks[k % len(tracks)])]
            parts.append(f"[{k + 1}:a]atrim=duration={seg:.2f},aformat=sample_rates=48000:channel_layouts=stereo,"
                         f"loudnorm=I={VOICE_LUFS - music_under_db:g}:TP=-6:LRA=11[m{k}]")
        cur = "[m0]"
        for k in range(1, n):
            parts.append(f"{cur}[m{k}]acrossfade=d=4:c1=tri:c2=tri[x{k}]")
            cur = f"[x{k}]"
        parts.append(f"{cur}atrim=duration={length:.3f},afade=t=in:d=2,"
                     f"afade=t=out:st={max(0.0, length - 4):.2f}:d=4[bed]")
        parts.append("[voice]asplit=2[v1][vkey]")
        # a light dip under the voice only (about 2-3 dB): the reference's bed stays clearly audible while he talks
        parts.append("[bed][vkey]sidechaincompress=threshold=0.06:ratio=1.6:attack=60:release=900:makeup=1[duck]")
        parts.append("[v1][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]")
        last = "[mix]"
    else:
        last = "[voice]"
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([_ff(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *inputs, "-filter_complex", ";".join(parts),
          "-map", last, "-t", f"{length:.3f}", "-c:a", "aac", "-b:a", "192k", str(out)])
    return out


# ---------------------------------------------------------------------------------------------------------------- video

def shot_source(shot: Dict, sections: Dict, lib_dir: Path, found: Dict[int, str]) -> Tuple[Optional[Path], float, bool]:
    """(file, seek seconds, already graded) for one shot; (None, 0, False) when nothing is there (drawn black)."""
    if shot["kind"] == "camera":
        t = float(shot["src_t"])
        for (a, b), (f, f0) in sections.items():
            if a - 0.05 <= t <= b:
                return Path(f), max(0.0, t - f0), False
        return None, 0.0, False
    if shot.get("row") and found.get(int(shot["row"])):
        return Path(found[int(shot["row"])]), 0.0, False
    if shot.get("file"):
        p = Path(shot["file"])
        p = p if p.is_absolute() else lib_dir / p
        if p.is_file():
            return p, 0.0, "/mine/" not in str(p).replace("\\", "/")
    return None, 0.0, False


def _pieces(shots: Sequence[Dict], length: float) -> List[Tuple[float, float, List[Dict]]]:
    out, cur, t0 = [], [], 0.0
    for s in shots:
        if cur and float(s["out_start"]) - t0 >= PIECE:
            out.append((t0, float(s["out_start"]), cur))
            cur, t0 = [], float(s["out_start"])
        cur.append(s)
    if cur:
        out.append((t0, length, cur))
    return out


def render_piece(k: int, t0: float, t1: float, shots: List[Dict], captions: List[Dict], card: Optional[Dict],
                 sections: Dict, lib_dir: Path, found: Dict[int, str], tmp: Path, size: Tuple[int, int], preview: bool,
                 channel: str, short: bool = False) -> Path:
    w, h = size
    f0, f1 = round(t0 * FPS), round(t1 * FPS)
    inputs: List[str] = []
    chains: List[str] = []
    labels: List[str] = []
    for j, s in enumerate(shots):
        a = round(float(s["out_start"]) * FPS)
        b = round(min(t1, float(s["out_start"]) + float(s["dur"])) * FPS) if j == len(shots) - 1 else round(float(shots[j + 1]["out_start"]) * FPS)
        if j == len(shots) - 1:
            b = f1
        n = max(1, b - a)
        d = n / FPS
        src, seek, graded = shot_source(s, sections, lib_dir, found)
        if src is None:
            inputs += ["-f", "lavfi", "-t", f"{d + 0.2:.3f}", "-i", f"color=c=0x0b0b0d:s={w}x{h}:r={FPS}"]
            vf = "null"
        else:
            if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                inputs += ["-loop", "1", "-t", f"{d + 0.2:.3f}", "-i", str(src)]
            else:
                inputs += ["-ss", f"{seek:.3f}", "-t", f"{d + 0.5:.3f}", "-i", str(src)]
            vf = look.fit_filter(w, h) + ("" if graded else "," + look.grade(preview))
        i = sum(1 for x in inputs if x == "-i") - 1
        chains.append(f"[{i}:v]{vf},fps={FPS},format=yuv420p,tpad=stop_mode=clone:stop_duration=2,"
                      f"trim=end_frame={n},setpts=PTS-STARTPTS[v{j}]")
        labels.append(f"[v{j}]")
    chains.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[base]")
    cur = "[base]"
    over: List[Tuple[str, int, float, float]] = []
    cap_dir = tmp / "caps"
    cap_dir.mkdir(parents=True, exist_ok=True)
    for c_i, c in enumerate(captions):
        if c["out_end"] <= t0 or c["out_start"] >= t1:
            continue
        p = cap_dir / f"c{k:03d}_{c_i:05d}.png"
        y = look.caption_png(c["text"], p, w, h, short=short)
        over.append((str(p), y, max(0.0, c["out_start"] - t0), min(t1, c["out_end"]) - t0))
    if card and card["out_start"] < t1 and card["out_end"] > t0:
        p = tmp / f"presents_{w}x{h}.png"
        if not p.is_file():
            look.presents_png(card.get("channel") or channel, p, w, h)
        over.append((str(p), 0, max(0.0, card["out_start"] - t0 + 0.3), card["out_end"] - t0 - 0.2))
    wm = tmp / f"wm_{w}x{h}.png"
    if channel and not wm.is_file():
        look.watermark_png(channel, wm, w, h)
    for p, y, a, b in over:
        inputs += ["-i", p]
        i = sum(1 for x in inputs if x == "-i") - 1
        chains.append(f"{cur}[{i}:v]overlay=0:{y}:enable='between(t,{a:.3f},{b:.3f})'[o{i}]")
        cur = f"[o{i}]"
    if channel:
        inputs += ["-i", str(wm)]
        i = sum(1 for x in inputs if x == "-i") - 1
        chains.append(f"{cur}[{i}:v]overlay=0:0[o{i}]")
        cur = f"[o{i}]"
    out = tmp / f"piece_{k:03d}.mp4"
    graph = ";".join(chains)      # inline: -filter_complex_script is gone in ffmpeg 8; a 1-min piece is a few kB
    _run([_ff(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *inputs, "-filter_complex", graph,
          "-map", cur, "-frames:v", str(f1 - f0), *encoder(preview), "-an", str(out)])
    return out


def render(plan: Dict, source_audio: Path, sections: Dict, out_path: Path, *, channel: str = "", lib_dir: Optional[Path] = None,
           found: Optional[Dict[int, str]] = None, size: Tuple[int, int] = (look.W, look.H), preview: bool = False,
           short: bool = False, music: bool = True, workers: int = 0, progress: Optional[Callable] = None,
           cancel=None, log: Callable = print) -> Dict:
    from . import library as LIB
    lib_dir = Path(lib_dir or LIB.library_dir())
    found = found or {}
    out_path = Path(out_path).resolve()      # absolute: the concat list's paths are read relative to the list's folder
    tmp = out_path.parent / (out_path.stem + "_parts")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    length = float(plan["length"])
    prog = progress or (lambda f, m="": None)

    def stop():
        if cancel and cancel():
            raise Stopped("stopped")

    prog(0.02, "Mixing the sound")
    log("Mixing the voice and the music bed …")
    audio = build_audio(Path(source_audio), plan["segments"], plan.get("card"), length, tmp / "audio.m4a", music=music)
    stop()
    w, h = size        # the shared pictures are made once here: pieces drawn in parallel must never race to write them
    if channel:
        look.watermark_png(channel, tmp / f"wm_{w}x{h}.png", w, h)
    if plan.get("card"):
        look.presents_png(plan["card"].get("channel") or channel, tmp / f"presents_{w}x{h}.png", w, h)
    pieces = _pieces(plan["shots"], length)
    log(f"Drawing {len(pieces)} piece(s) of about {PIECE:.0f} s …")
    workers = workers or max(2, min(4, (os.cpu_count() or 4) // 2))
    done = [0]
    files: List[Optional[Path]] = [None] * len(pieces)

    def job(k):
        stop()
        t0, t1, shots = pieces[k]
        files[k] = render_piece(k, t0, t1, shots, plan["captions"], plan.get("card"), sections, lib_dir, found, tmp, size,
                                preview, channel, short=short)
        done[0] += 1
        prog(0.05 + 0.9 * done[0] / len(pieces), f"Drew piece {done[0]} of {len(pieces)}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in [ex.submit(job, k) for k in range(len(pieces))]:
            f.result()
    stop()
    lst = tmp / "pieces.txt"
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in files))
    prog(0.97, "Joining")
    _run([_ff(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
          "-map", "0:v", "-map", "1:a", "-c", "copy", "-shortest", "-movflags", "+faststart", str(out_path)])
    shutil.rmtree(tmp, ignore_errors=True)
    prog(1.0, "Done")
    return {"path": out_path, "seconds": length, "pieces": len(pieces)}
