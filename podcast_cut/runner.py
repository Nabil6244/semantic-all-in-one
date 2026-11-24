"""Podcast Cut runner: what the app page, make_video and the command line call.

plan(...)    = Generate: get the episode (audio download, cached), its word times (Whisper, or YouTube captions with
               captions=True), pick the clips (or read the user's clip CSV), check them, then the footage director lays
               out the film (film.json). Writes clips.csv, plan_report.txt and film.json into the episode's work folder.
               The film's literal stock searches come back as `rows` for the app's Visuals tab.
fetch_broll  = the command line's stand-in for the Visuals tab: the first good stock clip for each literal row.
render(...)  = Render: download only the video sections the camera shots use, mix the sound, draw the pieces in
               parallel, join, then the title choices, chapters, thumbnail and (optional) 9:16 Shorts next to the mp4.
No Gemini, ever: with a clip CSV the CSV is the plan; without one the picker is local scoring.

  python -m podcast_cut.runner <link | file> [--minutes 35] [--clips my.csv] [--captions] [--channel NAME]
                               [--render] [--preview] [--shorts 3] [--out video.mp4]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from podcast_cut import check as _check, clipcsv, director, fetch, picker  # noqa: E402

Stopped = fetch.Stopped
FILM = "film.json"
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v")


def report_text(meta: dict, clips, errors, warns, notes, target_min: float) -> str:
    tot = _check.total_length(clips)
    lines = [f"Podcast Cut plan: {meta.get('title') or meta.get('id')}",
             f"Episode {meta.get('duration', 0) / 60:.0f} min  ->  cut {tot / 60:.1f} min (target {target_min:g})  "
             f"in {len(clips)} clips", ""]
    lines += [f"NOTE  {n}" for n in notes]
    lines += [f"ERROR {e}" for e in errors]
    lines += [f"WARN  {w}" for w in warns]
    lines.append("")
    for k, c in enumerate(clips, 1):
        txt = c.text if len(c.text) <= 150 else c.text[:110] + " … " + c.text[-35:]
        lines.append(f"{k:>3} {c.role:<8} {clipcsv.fmt_time(c.start)} -> {clipcsv.fmt_time(c.end)} "
                     f"({c.length:5.1f}s) {c.score:5.2f}  {txt}")
    return "\n".join(lines) + "\n"


def has_video(src: str) -> bool:
    return fetch.is_url(src) or Path(src).suffix.lower() in VIDEO_EXT


def plan(src: str, target_min: float = 35.0, clip_csv: Optional[str] = None, captions: bool = False,
         model_size: str = "small", workdir: Optional[Path] = None, channel: str = "", speaker: str = "", shorts: int = 0,
         log: Callable[[str], None] = print, cancel=None) -> dict:
    """Returns {'ok', 'workdir', 'clips_csv', 'report', 'clips', 'errors', 'warnings', 'notes', 'meta', 'length', 'rows',
    'film'}."""
    wd = Path(workdir) if workdir else fetch.workdir_for(src)
    wd.mkdir(parents=True, exist_ok=True)
    media, meta = fetch.get_source(src, wd, video=False, captions=captions, log=log, cancel=cancel)
    words = fetch.get_words(src, media, wd, captions=captions, model_size=model_size, log=log, cancel=cancel)
    if not meta.get("duration"):
        meta["duration"] = words[-1][2] if words else 0.0
    notes = []
    if clip_csv:
        log(f"Using your clip CSV {Path(clip_csv).name} (the picker is skipped)")
        clips = clipcsv.read(Path(clip_csv))
    else:
        fetch._check(cancel)
        log(f"Picking about {target_min:g} min from {meta['duration'] / 60:.0f} min of talk …")
        res = picker.pick(words, target_min=target_min, sponsor=meta.get("sponsor") or ())
        clips, notes = res["clips"], res["notes"]
    errors, warns = _check.check(clips, duration=meta.get("duration", 0.0), target_min=target_min, words=words)
    out_csv = clipcsv.write(clips, wd / "clips.csv")
    rep = report_text(meta, clips, errors, warns, notes, target_min)
    (wd / "plan_report.txt").write_text(rep, encoding="utf-8")
    log(f"Plan: {len(clips)} clips, {_check.total_length(clips) / 60:.1f} min -> {out_csv}")
    for e in errors:
        log(f"ERROR {e}")
    for w in warns[:12]:
        log(f"WARN  {w}")
    film = None
    if not errors:
        vid = has_video(src)
        film = director.build(clips, words, has_video=vid, channel=channel)
        short_clips = picker.shorts(words, n=shorts, sponsor=meta.get("sponsor") or ()) if shorts else []
        film.update({"source": src, "workdir": str(wd), "media": str(media), "channel": channel, "speaker": speaker,
                     "target_min": target_min, "clips": [c.__dict__ for c in clips], "meta": meta,
                     "shorts": [c.__dict__ for c in short_clips]})
        (wd / FILM).write_text(json.dumps(film, indent=1), encoding="utf-8")
        lib_n = len({s["file"] for s in film["shots"] if s.get("file")})
        log(f"Film: {len(film['shots'])} shots, camera {film['camera_share'] * 100:.0f}% of the time, {len(film['rows'])} "
            f"stock searches for the Visuals tab, {lib_n} mood-library clips"
            + ("" if vid else " (audio-only source: b-roll the whole way)"))
    return {"ok": not errors, "workdir": wd, "clips_csv": out_csv, "report": wd / "plan_report.txt", "clips": clips,
            "errors": errors, "warnings": warns, "notes": notes, "meta": meta, "length": _check.total_length(clips),
            "rows": (film or {}).get("rows", []), "film": film}


def load_film(wd: Path) -> Optional[dict]:
    try:
        return json.loads((Path(wd) / FILM).read_text(encoding="utf-8"))
    except Exception:
        return None


def fetch_broll(film: dict, wd: Path, log: Callable = print, cancel=None) -> Dict[int, str]:
    """The command line's Visuals tab: for each literal row, the first landscape stock clip (6 s, ungraded)."""
    from podcast_cut import library as LIB
    from providers.stock.pexels import PexelsBackend
    from providers.stock.pixabay import PixabayBackend
    keys = LIB._keys()
    bes = ([PexelsBackend(keys["pexels"])] if keys["pexels"] else []) + ([PixabayBackend(keys["pixabay"])] if keys["pixabay"] else [])
    found: Dict[int, str] = {}
    if not bes:
        log("No stock keys: literal shots use their mood-library stand-ins.")
        return found
    used = set()
    for r in film.get("rows", []):
        fetch._check(cancel)
        dest = Path(wd) / "broll" / f"row_{int(r['scene_no']):03d}.mp4"
        if dest.is_file():
            found[int(r["scene_no"])] = str(dest)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        for be in bes:
            try:
                cands = [c for c in be.search(r["stock"], media_type="video", per_page=8)
                         if c.width >= c.height and (be.name, c.asset_id) not in used]
            except Exception as exc:
                log(f"  {be.name} '{r['stock']}': {exc}")
                continue
            for c in cands[:3]:
                try:
                    LIB.grab(c.url, dest, start=0.5, seconds=7.0, graded=False)
                    found[int(r["scene_no"])] = str(dest)
                    used.add((be.name, c.asset_id))
                    break
                except Exception as exc:
                    log(f"  skipped {be.name} {c.asset_id}: {str(exc)[-100:]}")
            if int(r["scene_no"]) in found:
                break
        log(f"  row {r['scene_no']} '{r['stock']}': {'ok' if int(r['scene_no']) in found else 'not found (mood clip stands in)'}")
    return found


def _camera_spans(film: dict, segs: List[dict]) -> List[tuple]:
    """The source spans whose segment shows the camera at least once (only those are downloaded)."""
    cams = [s for s in film["shots"] if s["kind"] == "camera"]
    out = []
    for g in segs:
        if any(g["src_start"] - 0.05 <= s["src_t"] <= g["src_end"] for s in cams):
            out.append((g["src_start"], g["src_end"]))
    return out


def render(wd: Path, out_path: Path, *, channel: Optional[str] = None, preview: bool = False, found: Optional[Dict[int, str]] = None,
           shorts: bool = True, music: bool = True, progress: Optional[Callable] = None, cancel=None,
           log: Callable = print) -> dict:
    from podcast_cut import render as R, titles as TT
    film = load_film(wd)
    if not film:
        raise RuntimeError("Generate first: there is no planned film in this folder.")
    channel = film.get("channel", "") if channel is None else channel
    src, wd, out_path = film["source"], Path(wd), Path(out_path)
    prog = progress or (lambda f, m="": None)
    if found is None:
        found = fetch_broll(film, wd, log=log, cancel=cancel)
    found = {int(k): v for k, v in (found or {}).items()}
    spans = _camera_spans(film, film["segments"]) if film.get("has_video") else []
    prog(0.01, "Getting the video sections")
    sections = fetch.fetch_sections(src, wd, spans, log=log, cancel=cancel) if spans else {}
    size = (1280, 720) if preview else (1920, 1080)

    def sub(a, b):
        return lambda f, m="": prog(a + (b - a) * f, m)

    has_shorts = shorts and film.get("shorts")
    res = R.render(film, Path(film["media"]), sections, out_path, channel=channel, found=found, size=size, preview=preview,
                   music=music, progress=sub(0.03, 0.85 if has_shorts else 0.95), cancel=cancel, log=log)
    clips = [picker.Clip(**{k: v for k, v in c.items() if k in ("role", "start", "end", "text", "score")}) for c in film["clips"]]
    speaker = film.get("speaker") or TT.speaker_from(film.get("meta") or {})
    tl = TT.titles(film.get("meta") or {}, clips, res["seconds"], speaker)
    chs = TT.chapters(film, clips)
    stem = out_path.with_suffix("")
    Path(str(stem) + "_titles.txt").write_text("\n".join(tl) + "\n\nChapters:\n" + TT.chapters_text(chs), encoding="utf-8")
    frames = []
    for s in [x for x in film["shots"] if x["kind"] == "camera"][::3][:16]:
        for (a, b), (f, f0) in sections.items():
            if a - 0.05 <= s["src_t"] <= b:
                frames.append((f, s["src_t"] - f0 + min(1.0, s["dur"] / 2)))
                break
    words = TT.theme(" ".join(c.text for c in clips)).replace("Your ", "").replace("Of ", "")
    thumb = TT.thumbnail(frames, words, speaker, Path(str(stem) + "_thumbnail.jpg"), wd / "thumb_frames") if frames else None
    shorts_out = []
    if has_shorts:
        words_all = [tuple(w) for w in json.loads((wd / "words.json").read_text())]
        sc = [picker.Clip(**{k: v for k, v in c.items() if k in ("role", "start", "end", "text", "score")}) for c in film["shorts"]]
        sec_s = fetch.fetch_sections(src, wd, [(c.start, c.end) for c in sc], log=log, cancel=cancel) if film.get("has_video") else {}
        for k, c in enumerate(sc, 1):
            sf = director.build([c], words_all, has_video=film.get("has_video", False), seed=100 + k, channel=channel)
            p = Path(f"{stem}_short{k}.mp4")
            R.render(sf, Path(film["media"]), sec_s, p, channel=channel, size=(1080, 1920), preview=preview, short=True,
                     music=music, progress=sub(0.85 + 0.15 * (k - 1) / len(sc), 0.85 + 0.15 * k / len(sc)), cancel=cancel, log=log)
            shorts_out.append(p)
    prog(1.0, "Done")
    log(f"Done: {out_path.name} ({res['seconds'] / 60:.1f} min)" + (f" + {len(shorts_out)} Short(s)" if shorts_out else ""))
    return {"path": out_path, "seconds": res["seconds"], "titles": tl, "chapters": chs, "thumbnail": thumb, "shorts": shorts_out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Podcast Cut: a long podcast -> a 30-38 min motivation cut over mood b-roll.")
    ap.add_argument("source", help="YouTube link or a local video/audio file")
    ap.add_argument("--minutes", type=float, default=35.0)
    ap.add_argument("--clips", help="your own clip CSV (then nothing is picked)")
    ap.add_argument("--captions", action="store_true", help="use YouTube's automatic captions instead of Whisper (faster)")
    ap.add_argument("--model", default="small", help="Whisper model size")
    ap.add_argument("--workdir", help="work folder (default out/podcast_cut/<video id>)")
    ap.add_argument("--channel", default="", help="channel name for the 'presents' card and the watermark")
    ap.add_argument("--speaker", default="", help="speaker name for the titles (default: from the video title)")
    ap.add_argument("--render", action="store_true", help="render the video after planning")
    ap.add_argument("--preview", action="store_true", help="720p fast render")
    ap.add_argument("--shorts", type=int, default=0, help="also make this many 9:16 Shorts")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--out", help="output mp4")
    a = ap.parse_args(argv)
    res = plan(a.source, target_min=a.minutes, clip_csv=a.clips, captions=a.captions, model_size=a.model,
               workdir=Path(a.workdir) if a.workdir else None, channel=a.channel, speaker=a.speaker, shorts=a.shorts)
    print(Path(res["report"]).read_text(encoding="utf-8"))
    if not res["ok"]:
        return 1
    if a.render:
        out = Path(a.out) if a.out else res["workdir"] / "podcast_cut.mp4"
        render(res["workdir"], out, preview=a.preview, shorts=bool(a.shorts), music=not a.no_music)
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
