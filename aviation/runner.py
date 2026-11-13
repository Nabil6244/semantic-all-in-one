"""Aviation style runner: the Tk-free work behind the app page (ui/aviation_section.py).

    scenes_from_csv(path) -> (untimed scene dicts, aviation csv rows)      the CSV is the plan: no Gemini anywhere in a CSV run
    request_footage(scenes, plan)            asset_type / prompt per scene: the CSV's own, else youtube_video + the narration's searches
                                             for the scenes whose footage slots (or card pictures) need a clip; 'none' for the rest
    prefetch_maps(plan, log)                 downloads the elevation tiles the flight maps need (once per area, cached), before Render
    clip_picker(scenes, plan) -> pick(slot)  the clip for a planner footage slot: the scene's own clip (from the Visuals tab), sliced
                                             from a different point each time; a clip whose title shows another aircraft type is not used;
                                             a scene without a clip borrows the nearest clip of its own stretch
    split_timeline(shots, layers, chunk_s)   the film in chunks; shots crossing a cut go on with the right seek, layers keep their clock
    render_film(plan, scenes, voice, out)    chunks rendered in parallel through the shared renderer, joined, the voice-over laid on
                                             at -14 LUFS. Cancel is checked between chunks; nothing is written to `out` when stopped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import bridge as BR
from . import csv_rows as V
from . import footage as FT
from . import router as R

FOOTAGE_TYPES = ("youtube_video", "stock_video", "archive_video", "flow_video", "local", "local_video")


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------- scenes

def scenes_from_csv(path: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = V.read_rows(path)
    scenes = []
    for i, r in enumerate(rows, 1):
        try:
            no = int(str(r["scene_number"]).strip())
        except ValueError:
            no = i
        scenes.append({"scene_no": no, "text": r["text"], "asset_type": r["asset_type"] or "",
                       "prompt": " || ".join(r["queries"])})
    return scenes, rows


def request_footage(scenes: List[Dict[str, Any]], plan: Any) -> None:
    need = {s.get("scene") for s in plan.shots if s.get("kind") == "footage"}
    need |= {s.get("scene") for s in plan.shots if (s.get("params") or {}).get("image_from") == "footage"}
    for sc in scenes:
        if str(sc.get("asset_type") or "").strip():
            continue                                       # the CSV decided
        if sc["scene_no"] in need:
            q = FT.queries_for(R.classify(sc["text"]))
            sc["asset_type"] = "youtube_video" if q else "none"
            sc["prompt"] = " || ".join(q[:2])
        else:
            sc["asset_type"] = "none"


def prepare_pages(rows: Optional[Sequence[Dict[str, Any]]], cache_dir: Any, log: Callable[[str], None] = lambda m: None,
                  shot: Optional[Callable[[str, Any], Dict[str, Any]]] = None) -> int:
    """For every CSV row with a `url`: the page's screenshot (once, cached) on the row's article card. The CSV's own outlet / headline /
    date win; the page's tags fill what the CSV left empty. A page that cannot be had leaves the typeset card."""
    if not rows:
        return 0
    if shot is None:
        from .webshot import shot
    n = 0
    for r in rows:
        url = (r or {}).get("url") or ""
        if not url:
            continue
        got = shot(url, cache_dir)
        if not got.get("ok"):
            log(f"page not captured ({got.get('reason', '')[:80]}): {url}")
            continue
        art = dict(r.get("article") or {})
        art.setdefault("outlet", got.get("site", ""))
        art.setdefault("headline", got.get("title", ""))
        art.setdefault("date", got.get("date", ""))
        for k in ("outlet", "headline", "date"):
            art[k] = art.get(k) or got.get({"outlet": "site", "headline": "title", "date": "date"}[k], "")
        art["page"] = got["path"]
        art["headline_box"] = got.get("headline_box")
        r["article"] = art
        n += 1
    return n


def still_to_clip(image: str, out: str, seconds: float = 8.0) -> str:
    """A still (a Flow image) as a short moving clip: a slow push-in, so it can sit in the timeline like footage. Made once."""
    o = Path(out)
    if o.is_file() and o.stat().st_size > 1000:
        return str(o)
    frames = int(round(seconds * 30))
    vf = (f"scale=2560:-2,zoompan=z='min(zoom+0.0006,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1280x720:fps=30,"
          "format=yuv420p")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(image), "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast",
                    str(o)], check=True, timeout=300)
    return str(o)


def attach_images(scenes: List[Dict[str, Any]], images_dir: Any) -> int:
    """flow_image scenes: their finished picture (from the Visuals tab's manifest) as a moving clip, set as the scene's footage."""
    from asset_manager import AssetManifest

    man = AssetManifest(Path(images_dir))
    n = 0
    for sc in scenes:
        if str(sc.get("asset_type") or "") != "flow_image":
            continue
        rec = man.get(str(sc["scene_no"])) or man.get(f"{int(sc['scene_no']):03d}") or {}
        img = rec.get("local_path") or ""
        if str(rec.get("status")).lower() != "complete" or not img or not Path(img).is_file():
            continue
        sc["footage"] = still_to_clip(img, str(Path(img).with_suffix(".still.mp4")))
        sc["footage_meta"] = {"duration": 8.0, "user_supplied": True, "ai_generated": True}
        n += 1
    return n


def mark_clips(scenes: List[Dict[str, Any]]) -> int:
    """At Render: which scenes really have a clip (from the Visuals tab). The planner shows a graphic or a text card on the others,
    never a picture borrowed from another scene."""
    n = 0
    for sc in scenes:
        f = sc.get("footage")
        sc["has_clip"] = bool(f and Path(str(f)).is_file())
        n += sc["has_clip"]
    return n


def prefetch_maps(plan: Any, log: Callable[[str], None] = lambda m: None, cancel: Callable[[], bool] = lambda: False) -> int:
    """Draw the first frame of every flight map once: that downloads (or reads from the cache) the elevation it needs."""
    from . import flightmap

    n = 0
    seen = set()
    for s in plan.shots:
        if s.get("layer") != "flightmap.lay_flight_map":
            continue
        key = json.dumps(sorted(s["params"].get("airports") or []))
        if key in seen:
            continue
        seen.add(key)
        if cancel():
            raise Cancelled()
        log(f"map terrain for {', '.join(s['params'].get('airports') or [])}")
        flightmap.lay_flight_map(0.0, float(s["end"] - s["start"]), dict(s["params"]))
        n += 1
    return n


# ---------------------------------------------------------------------------------------------------------------- clips

def _duration(path: str) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                             timeout=30).strip())
    except Exception:
        return 0.0


def clip_picker(scenes: Sequence[Dict[str, Any]], plan: Any, log: Callable[[str], None] = lambda m: None,
                extras: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Callable[[dict], Optional[dict]]:
    by_no = {sc["scene_no"]: sc for sc in scenes}
    order = [sc["scene_no"] for sc in scenes]
    mode_of = {sc["scene_no"]: m for sc, m in zip(scenes, plan.modes)}
    used: Dict[str, int] = {}
    durs: Dict[str, float] = {}
    usable: Dict[Any, Optional[dict]] = {}
    per_scene: Dict[Any, int] = {}
    extra_of: Dict[str, List[dict]] = {}
    for no, lst in (extras or {}).items():
        extra_of[str(no)] = [{"path": e["path"], "duration": _duration(e["path"]) or float(e.get("duration") or 0.0),
                              "source": str(e.get("channel") or "").strip()} for e in lst if e.get("path") and Path(e["path"]).is_file()]

    def own(no: Any) -> Optional[dict]:
        if no in usable:
            return usable[no]
        sc = by_no.get(no) or {}
        path = sc.get("footage")
        clip = None
        if path and Path(path).is_file():
            meta = sc.get("footage_meta") or {}
            title = " ".join(str(meta.get(k) or "") for k in ("video_title", "title"))
            ok, _score, why = FT.clip_ok(title, R.classify(sc.get("text") or "")) if title.strip() and not meta.get("user_supplied") else (True, 0, "")
            if not ok:
                log(f"scene {no}: clip not used ({why})")
            else:
                real = durs.setdefault(path, _duration(path))       # the file can be shorter than its record says (a capture
                d = min(float(meta.get("duration") or real), real) if real else float(meta.get("duration") or 0.0)  # keeps fewer seconds)
                src = str(meta.get("channel") or meta.get("author") or "").strip()
                clip = {"path": path, "duration": d, "source": src}
        usable[no] = clip
        return clip

    def pick(slot: dict) -> Optional[dict]:
        no = slot.get("scene")
        clip = own(no)
        if clip is None and no in order:                      # borrow the nearest clip of the same stretch
            i = order.index(no)
            for k in range(1, 4):
                for j in (i - k, i + k):
                    if 0 <= j < len(order) and mode_of.get(order[j]) == mode_of.get(no) and own(order[j]):
                        clip = own(order[j])
                        break
                if clip:
                    break
        if clip is None:
            return None
        alts = [clip] + (extra_of.get(str(no), []) if own(no) is clip else [])
        if len(alts) > 1:                                      # a burst cuts between different videos of the same subject
            k = per_scene.get(no, 0)
            per_scene[no] = k + 1
            clip = alts[k % len(alts)]
        length = float(slot["end"]) - float(slot["start"])
        d = float(clip.get("duration") or 0.0)
        n = used.get(clip["path"], 0)
        used[clip["path"]] = n + 1
        lead = min(1.5, 0.15 * d)                                  # the first moments of a cut are often a channel intro or a fade
        room = max(0.0, d - length - lead - 0.1)
        seek = lead + ((n * 2.3) % room if room > 0.05 else 0.0)  # each slice starts somewhere else in the clip
        if seek + length > d:
            seek = max(0.0, d - length)
        return dict(clip, seek=round(seek, 3))

    return pick


# ---------------------------------------------------------------------------------------------------------------- chunks

def split_timeline(shots: Sequence[Any], layers: Sequence[Any], chunk_s: float = 60.0) -> List[Tuple[float, List[Any], List[Any]]]:
    from cinematic_explainer.render import Layer, Shot

    total = shots[-1].end if shots else 0.0
    out = []
    c0 = 0.0
    while c0 < total - 1e-6:
        c1 = min(total, c0 + chunk_s)
        if total - c1 < 1.0:
            c1 = total                                         # no sliver of a chunk at the end
        cs = []
        for s in shots:
            a, b = max(s.start, c0), min(s.end, c1)
            if b - a > 1e-6:
                cs.append(Shot(s.path, a - c0, b - c0, s.seek + (a - s.start), s.treat, 0.0))
        cl = [Layer(ly.kind, ly.start - c0, ly.end - c0, ly.params, ly.dim) for ly in layers if ly.end > c0 and ly.start < c1]
        out.append((c0, cs, cl))
        c0 = c1
    return out


def render_film(plan: Any, scenes: Sequence[Dict[str, Any]], voice: str, out: str, *, work: str, chunk_s: float = 60.0, workers: int = 3,
                progress: Callable[[float, str], None] = lambda k, m: None, cancel: Callable[[], bool] = lambda: False,
                log: Callable[[str], None] = lambda m: None, map_extra: Optional[dict] = None,
                extras: Optional[Dict[str, List[Dict[str, Any]]]] = None, sound: bool = True) -> Dict[str, Any]:
    from cinematic_explainer import render as RD

    if cancel():
        raise Cancelled()
    wd = Path(work)
    wd.mkdir(parents=True, exist_ok=True)
    shots, layers, rep = BR.build_timeline(plan, scenes, clip_picker(scenes, plan, log, extras), black=str(wd / "black.mp4"), map_extra=map_extra)
    if rep["missing_footage"]:
        log(f"{rep['missing_footage']} footage slots had no clip: they show a fact card instead")
    chunks = split_timeline(shots, layers, chunk_s)
    table = BR.card_table()
    parts = [wd / f"part_{i:03d}.mp4" for i in range(len(chunks))]
    done = [0]
    total_s = shots[-1].end if shots else 0.0
    mixed: Dict[str, Any] = {}

    def sound_mix() -> None:
        """Sticker pops, year ticks, re-hook hits and chapter music under the voice (aviation/sound.py), mixed while the picture
        renders. Any failure leaves the plain voice-over: sound never stops a film."""
        try:
            from . import sound as SD
            ev = SD.events(plan, scenes)
            mu = SD.music_plan(plan, scenes, total_s=total_s)
            dst = wd / "voice_mix.m4a"
            SD.mix(str(voice), ev, mu, str(dst), total_s)
            if dst.is_file() and dst.stat().st_size > 0:
                mixed["path"] = str(dst)
                mixed["events"] = len(ev)
        except Exception as ex:  # noqa: BLE001
            log(f"sound design skipped ({ex}); the plain voice-over is used")

    def one(i: int) -> None:
        if cancel():
            raise Cancelled()
        _c0, cs, cl = chunks[i]
        RD.render(cs, cl, str(parts[i]), card_table=table)
        done[0] += 1
        progress(0.92 * done[0] / len(chunks), f"rendered {done[0]} of {len(chunks)} parts")

    with ThreadPoolExecutor(max_workers=1) as sx:
        sfut = sx.submit(sound_mix) if sound and total_s > 0 else None
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for f in [ex.submit(one, i) for i in range(len(chunks))]:
                f.result()
        if sfut is not None:
            sfut.result()
    if mixed.get("path"):
        log(f"sound design: {mixed['events']} effects + chapter music mixed under the voice")
        voice = mixed["path"]
    if cancel():
        raise Cancelled()
    lst = wd / "parts.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = wd / "joined.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True, timeout=3600)
    progress(0.95, "laying the voice-over")
    tmp = Path(out).with_name(Path(out).stem + ".part.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                    "-movflags", "+faststart", str(tmp)], check=True, timeout=3600)
    if cancel():
        tmp.unlink(missing_ok=True)
        raise Cancelled()
    shutil.move(str(tmp), out)
    thumbs: List[str] = []
    try:                                   # 3 thumbnail candidates from the film's own stickers and words (offered, never uploaded)
        from . import thumbs as TH
        thumbs = TH.make(plan, scenes, Path(out).with_name(Path(out).stem + "_thumbs"))
        if thumbs:
            log(f"{len(thumbs)} thumbnail candidates saved next to the video")
    except Exception as ex:  # noqa: BLE001
        log(f"thumbnails skipped: {ex}")
    for p in parts + [silent, lst]:
        Path(p).unlink(missing_ok=True)
    progress(1.0, "done")
    return {"chunks": len(chunks), "missing_footage": rep["missing_footage"], "clips": rep["clips"], "duration": shots[-1].end if shots else 0.0,
            "thumbs": thumbs}


def import_retention(csv_path: Any, scenes: Sequence[Dict[str, Any]], rows: Optional[Sequence[Dict[str, Any]]] = None,
                     web: Optional[Dict[str, Any]] = None, tune: bool = True) -> Dict[str, Any]:
    """YouTube Studio's audience-retention CSV for a published Aviation film: the film's plan is rebuilt from its scenes (the
    same plan it was rendered from), each viewer drop is matched to the picture on screen, and with tune=True the channel's
    limits move one small step (aviation/retention_import.py). Returns the report with the new limits."""
    from . import planner as P
    from . import retention_import as RI
    plan = P.plan(list(scenes), rows, web=web)
    total = max([float(s["end"]) for s in scenes] + [0.0])
    curve = RI.read_curve(csv_path, total)
    rep = RI.analyze(curve, plan)
    if tune and rep["dips"]:
        rep["limits"] = RI.tune(rep)
    else:
        rep["limits"] = RI.limits()
    return rep
