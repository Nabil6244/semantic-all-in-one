"""War Footage Director: footage that shows what the narrator says, or War graphics when no such footage can be verified.

docs/war/FOOTAGE_DIRECTOR_PLAN.md (Stages 1-9). For each YouTube row of a War scenes CSV:

  1 read the sentence (narration_read)            -> types, places, actor, date; claims / figures / questions / transitions want no footage
  2 search (director_search)                      -> 3-5 entity-first queries, results pooled
  3 rules (director_rules)                        -> hard rejections with reasons, then rank
  4 frames (director_frames)                      -> storyboard check of the shortlist, best cut-free 3-8 s window
  5 authenticity (director_authenticity)          -> verified_event / corroborated / unverified; events take only the first two
  6 no repeats (director_rules.Used)              -> same seconds, same picture under another URL, max 2 moments per video
  7 capture + verify (director_capture)           -> the shared capture pool records it; the file is matched against the storyboard
  9 report                                        -> state/war/discovery_report.json + director_decisions.json

A scene left without verified footage is handed to the graphics: no_footage, and (when its CSV row names no graphic) the existing War
graphic that fits the sentence (graphic_for). A clip the user picked in the Visuals tab is never touched. No Gemini, no API keys.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import director_authenticity as A
from . import director_capture as C
from . import director_frames as F
from . import director_rules as R
from . import director_search as S
from . import narration_read as N

SHORTLIST = 4
CAPTURE_TRIES = 3
PREFETCH_THREADS = 4
CAPTURE_LIMIT_S = 45.0          # War's own limit per capture (+3 s per clip second); the shared browser's own limit is 180 s


def bounded(acquire: Callable[..., Dict[str, Any]], seconds_fn: Callable[[float], float]) -> Callable[..., Dict[str, Any]]:
    """acquire() with a War-side time limit: a capture that hangs is given up (its browser finishes on its own), the next candidate goes on."""
    import threading

    def run(video_id, start, seconds, dest):
        box: Dict[str, Any] = {}
        th = threading.Thread(target=lambda: box.update(res=acquire(video_id, start, seconds, dest)), daemon=True, name="war-capture")
        th.start()
        limit = seconds_fn(seconds)
        th.join(limit)
        if th.is_alive():
            return {"ok": False, "kind": "timeout", "error": f"timed out after {limit:.0f} s (War limit)"}
        return box.get("res") or {"ok": False, "error": "no result"}
    return run
REPORT = "discovery_report.json"
DECISIONS = "director_decisions.json"
SETTING = "war_footage_director"


BLOCKLIST = Path(__file__).resolve().parent / "data" / "footage_blocklist.json"
PROJECT_BLOCKLIST = "director_blocklist.json"
# capture failures that will fail again for the same video and window: never retried; a timeout or a browser hiccup may be retried once
LASTING = ("picture:", "moment:", "file:", "capture: no video tracks", "capture: age restricted", "capture: age_restricted")


def load_blocklist(state_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in [BLOCKLIST] + ([Path(state_dir) / PROJECT_BLOCKLIST] if state_dir else []):
        try:
            out += list(json.loads(Path(p).read_text(encoding="utf-8")).get("entries") or [])
        except (OSError, ValueError):
            continue
    return out


def blocked_for(entries: Sequence[Dict[str, Any]], video_id: str, text: str, start: Optional[float] = None) -> str:
    """The reason this video may not be used for this narration ('' = allowed). A lasting capture failure blocks only its own window."""
    for e in entries:
        if e.get("video_id") != video_id:
            continue
        if e.get("scope") == "text" and str(e.get("text") or "").lower() not in (text or "").lower():
            continue
        if e.get("scope") == "window" and start is not None and abs(float(e.get("start") or -99) - float(start)) > 4.0:
            continue
        return str(e.get("reason") or "blocklisted")
    return ""


def _remember_failure(state_dir: Path, video_id: str, start: float, reasons: Sequence[str]) -> None:
    """A capture that failed for a lasting reason is written to the project's blocklist (that window only), so no later run retries it."""
    why = "; ".join(reasons)
    if not any(why.startswith(x) or x in why for x in LASTING):
        return
    p = Path(state_dir) / PROJECT_BLOCKLIST
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"note": "this project's War Footage Director failures and rejections (merged with data/footage_blocklist.json)", "entries": []}
    data["entries"].append({"video_id": video_id, "scope": "window", "start": round(float(start), 2), "reason": f"capture failed: {why[:160]}"})
    _write(p, data)


def enabled(settings: Optional[Dict[str, Any]]) -> bool:
    return bool((settings or {}).get(SETTING, True))


def graphic_for(r: N.Reading) -> str:
    """The existing War graphic (a CSV `graphic` value, direction.CSV_GRAPHIC) for a sentence shown without footage."""
    t = set(r.types)
    low = r.text.lower()
    if "TRANSITION" in t and not ({"EVENT", "MOVEMENT", "STATISTIC"} & t):
        return "title" if any(w in low for w in ("subscribe", "comments", "tell me")) else "chapter"
    if "QUESTION" in t:
        return "kinetic"
    if "STATISTIC" in t:
        return "number"
    if "CLAIM" in t and r.speaker:
        return "speaker"
    if "MOVEMENT" in t and r.places:
        return "route"
    if ("LOCATION" in t or "EVENT" in t) and r.places:
        return "map"
    if "EVENT" in t and any(w in low for w in ("drone", "missile", "from the air", "air strike")):
        return "flyover"
    if "CLAIM" in t:
        return "source" if r.outlet else "claim"
    if "SUBJECT" in t and r.equipment:
        return "equipment"
    return "keywords"


def _clip_dict(rec: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("video_id", "source", "source_url", "clip_start", "title", "channel", "description", "upload_date", "authenticity",
            "moment_verified", "frame_flags", "tile_hashes")
    d = {k: rec.get(k) for k in keys}
    d["title"] = rec.get("video_title") or rec.get("title") or ""
    d["clip_end"] = rec.get("timestamp_end")
    d["reused"] = bool(rec.get("reused"))
    return d


def run(scenes: Sequence[Dict[str, Any]], rows: Sequence[Any], images_dir: Path, state_dir: Path, log: Callable[[str], None] = lambda m: None,
        cancel: Callable[[], bool] = lambda: False, film_date: Optional[_dt.date] = None, searcher: Optional[S.Searcher] = None,
        acquire: Optional[Callable[..., Dict[str, Any]]] = None, validate: Optional[Callable[..., Optional[str]]] = None,
        fetch_sheet: Optional[Callable[[str], bytes]] = None, render_id: str = "") -> Dict[str, Any]:
    """Decide footage or graphics for every YouTube row; capture what is chosen. Returns the report (also written to state_dir)."""
    from asset_manager import AssetManifest

    images_dir, state_dir = Path(images_dir), Path(state_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    film_date = film_date or _dt.date.today()
    searcher = searcher or S.Searcher(state_dir / "director_cache", log=log)
    fetch_sheet = fetch_sheet or F._fetch
    readings = N.read_scenes(scenes)
    topic = S.topic_of(list(readings.values()))
    story = R.story_period(list(readings.values()))
    man = AssetManifest(images_dir)
    used = R.Used()
    blocklist = load_blocklist(state_dir)
    by_no = {str(sc.get("scene_no")): sc for sc in scenes}
    yt_rows = [r for r in rows if getattr(r, "asset_type", "") == "youtube_video"]
    report_scenes: List[Dict[str, Any]] = []
    decisions: Dict[str, Dict[str, Any]] = {}

    # clips already decided (the user's own picks, or an earlier director run) keep their place and block repeats
    for r in yt_rows:
        rec = man.get(str(r.scene_number)) or {}
        if str(rec.get("status") or "").lower() == "complete" and rec.get("video_id") and \
                (rec.get("user_override") or rec.get("source") == "manual" or rec.get("selection_method") == "war_director"):
            if Path(str(rec.get("local_path") or "")).is_file():
                used.add(str(r.scene_number), rec["video_id"], float(rec.get("clip_start") or 0), float(rec.get("timestamp_end") or 0),
                         rec.get("tile_hashes") or [])

    t_start = time.time()
    timing = {"prefetch_s": 0.0, "capture_ok_s": 0.0, "capture_fail_s": 0.0, "captures_ok": 0, "captures_failed": 0}
    if acquire is None:
        from providers.youtube.acquisition.browser_client import get_client
        acquire = get_client().acquire
    acquire = bounded(acquire, lambda sec: CAPTURE_LIMIT_S + 3.0 * float(sec))

    # 1 discovery for every footage scene at once (search, rules, metadata, storyboards): network waits overlap; picking stays in order
    pre_scene: Dict[str, Any] = {}
    tiles_of: Dict[str, Any] = {}

    def discover(r: Any) -> None:
        no_ = str(r.scene_number)
        sc_ = by_no.get(no_) or (by_no.get(str(int(no_))) if no_.isdigit() else None) or {}
        rd = readings.get(str(sc_.get("scene_no", no_))) or N.read(r.script_segment)
        rec_ = man.get(no_) or {}
        if not rd.footage_wanted or rec_.get("user_override") or rec_.get("source") == "manual":
            return
        qs = S.build_queries(rd, getattr(r, "prompt", "") or "", topic=topic)
        pl = searcher.pool(qs, cancel=cancel)
        ok_, _bad = R.rank([c for c in pl if not blocked_for(blocklist, c.video_id, rd.text)], rd, film_date, story)
        for _s, c in ok_[:SHORTLIST + 2]:
            d_ = searcher.details(c)
            if c.video_id in tiles_of:
                continue
            sb_ = d_.get("storyboard") or {}
            try:
                tiles_of[c.video_id] = (F.inspect(F.tiles_from_storyboard(sb_, fetch=fetch_sheet)) if sb_ else
                                        F.inspect(F.tiles_from_thumbnails(c.video_id, c.duration, fetch=fetch_sheet)), bool(sb_))
            except Exception:  # noqa: BLE001 - frames are fetched again in the pick loop
                pass
        pre_scene[no_] = (qs, pl)

    t0 = time.time()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=PREFETCH_THREADS) as ex:
        list(ex.map(lambda r: (None if cancel() else discover(r)), yt_rows))
    timing["prefetch_s"] = round(time.time() - t0, 1)

    for r in yt_rows:
        if cancel():
            log("Footage Director stopped")
            break
        no = str(r.scene_number)
        sc = by_no.get(no) or by_no.get(str(int(no))) if no.isdigit() else by_no.get(no)
        sc = sc or {}
        reading = readings.get(str(sc.get("scene_no", no))) or N.read(r.script_segment)
        entry: Dict[str, Any] = {"scene": f"{int(no):03d}" if no.isdigit() else no, "types": reading.types, "actor": reading.actor,
                                 "key_terms": reading.key_terms, "graphic_intent": graphic_for(reading), "reasons": reading.reasons,
                                 "queries": [], "candidates": [], "rejected": [], "decision": "graphics", "clip": {}}
        rec = man.get(no) or {}
        if rec.get("user_override") or rec.get("source") == "manual":
            entry.update(decision="footage", clip=_clip_dict(rec), note="the user's own pick: kept")
            report_scenes.append(entry)
            decisions[no] = {"decision": "footage", "graphic": ""}
            continue
        if rec.get("selection_method") == "war_director" and str(rec.get("status")).lower() == "complete" and \
                Path(str(rec.get("local_path") or "")).is_file():
            entry.update(decision="footage", clip=_clip_dict(rec), note="chosen by an earlier run: kept")
            report_scenes.append(entry)
            decisions[no] = {"decision": "footage", "graphic": ""}
            continue
        if not reading.footage_wanted:
            why = f"{'/'.join(reading.types)} sentence: shown with War graphics, not footage"
            entry["note"] = why
            log(f"scene {no}: {why}")
            _mark_graphics(man, no, rec, why)
            decisions[no] = {"decision": "graphics", "graphic": entry["graphic_intent"], "why": why}
            report_scenes.append(entry)
            continue
        queries, pool = pre_scene.get(no) or (S.build_queries(reading, getattr(r, "prompt", "") or "", topic=topic), None)
        entry["queries"] = queries
        if pool is None:
            pool = searcher.pool(queries, cancel=cancel)
        pre = [c for c in pool if blocked_for(blocklist, c.video_id, reading.text) and
               not any(e.get("scope") == "window" for e in blocklist if e.get("video_id") == c.video_id)]
        if pre:
            pool = [c for c in pool if c not in pre]
        ok, bad = R.rank(pool, reading, film_date, story)
        bad += [(c, [f"blocklist: {blocked_for(blocklist, c.video_id, reading.text)}"]) for c in pre]
        entry["rejected"] = [{"video_id": c.video_id, "title": c.title, "channel": c.channel, "why": w} for c, w in bad]
        picked = None
        tries = 0
        shortlist = ok[:SHORTLIST + 2]
        for _sc, c in shortlist:
            searcher.details(c)
        # an age-restricted upload cannot be recorded by the capture browser (no sign-in): it stays a candidate, tried last
        shortlist = sorted(shortlist, key=lambda x: (x[1].blocked, -x[0]))[:SHORTLIST + 1]
        others: List[Any] = []
        for score, c in shortlist:
            if cancel() or tries >= CAPTURE_TRIES:
                break
            d = searcher.details(c)
            cand = {"video_id": c.video_id, "title": c.title, "channel": c.channel, "tier": R.channel_tier(c.channel), "score": score,
                    "duration": c.duration, "upload_date": d.get("upload_date", ""), "queries": c.queries}
            late = R.reject(c, reading, film_date, story)          # the upload date is known now
            if late:
                cand["why"] = late
                entry["candidates"].append(cand)
                continue
            level = R.match_level(c, reading)
            cand["level"] = level
            sb = d.get("storyboard") or {}
            if c.video_id in tiles_of:
                tiles, _has_sb = tiles_of[c.video_id]
                win = (F.choose_window(tiles, c.duration, usable=lambda a, b, h, vid=c.video_id: not used.conflict(vid, a, b, h)) if sb else
                       F.window_from_thumbnails(tiles, c.duration, usable=lambda a, b, h, vid=c.video_id: not used.conflict(vid, a, b, h)))
                if not sb:
                    cand["inspection"] = "thumbnails" + (" (metadata needs sign-in)" if c.blocked else "")
            elif sb:
                tiles = F.inspect(F.tiles_from_storyboard(sb, fetch=fetch_sheet))
                win = F.choose_window(tiles, c.duration, usable=lambda a, b, h, vid=c.video_id: not used.conflict(vid, a, b, h))
            else:
                # no storyboard (age-restricted / sign-in): preview from YouTube's thumbnails, capture is then judged on its own frames
                tiles = F.inspect(F.tiles_from_thumbnails(c.video_id, c.duration, fetch=fetch_sheet))
                win = F.window_from_thumbnails(tiles, c.duration, usable=lambda a, b, h, vid=c.video_id: not used.conflict(vid, a, b, h))
                cand["inspection"] = "thumbnails" + (" (metadata needs sign-in)" if c.blocked else "")
                if c.content_warning:
                    cand["content_warning"] = c.content_warning
            cand["frames"] = F.summary(tiles)
            if not win:
                cand["why"] = ["frames: no cut-free stretch of filmed footage (talking heads, graphics, phone video in bars, or repeats)"]
                entry["candidates"].append(cand)
                continue
            stop = blocked_for([e for e in blocklist if e.get("scope") == "window"], c.video_id, reading.text, win["start"])
            if stop:
                cand["why"] = [f"blocklist: {stop} (not retried)"]
                entry["candidates"].append(cand)
                continue
            others.append((c.video_id, c.channel, win["hashes"]))
            cls, why_cls = A.classify(c, reading, film_date, win["hashes"], others, story=story, level=level)
            cand.update(window=win, authenticity=cls, authenticity_reasons=why_cls)
            if not A.allowed(cls, reading, level, cand["tier"], c.blocked):
                cand["why"] = [f"authenticity: {cls} ({'; '.join(why_cls)}): an event scene takes only verified or corroborated footage"]
                entry["candidates"].append(cand)
                continue
            tries += 1
            dest = images_dir / (f"{int(no):03d}.mp4" if no.isdigit() else f"{no}.mp4")
            got = C.capture(c.video_id, win["start"], win["end"] - win["start"], dest, tiles, acquire=acquire, validate=validate, log=log,
                            storyboard=bool(sb))
            timing["capture_ok_s" if got["ok"] else "capture_fail_s"] += float(got.get("seconds") or 0)
            timing["captures_ok" if got["ok"] else "captures_failed"] += 1
            cand["capture"] = {k: got.get(k) for k in ("ok", "reasons", "seconds")}
            entry["candidates"].append(cand)
            if not got["ok"]:
                log(f"scene {no}: {c.title[:50]} not used: {'; '.join(got['reasons'])}")
                _remember_failure(state_dir, c.video_id, win["start"], got["reasons"])
                blocklist = load_blocklist(state_dir)
                continue
            picked = {"candidate": c, "window": win, "path": got["path"], "verify": got.get("verify"), "authenticity": cls,
                      "authenticity_reasons": why_cls, "score": score, "tier": cand["tier"], "queries": queries, "level": level,
                      "frame_flags": sorted({fl for t in tiles if win["start"] <= t.t < win["end"] for fl in t.flags})}
            break
        if picked:
            rec = C.write_record(man, no, getattr(r, "script_segment", ""), getattr(r, "prompt", ""), picked)
            used.add(no, picked["candidate"].video_id, picked["window"]["start"], picked["window"]["end"], picked["window"]["hashes"])
            entry.update(decision="footage", clip=_clip_dict(rec), match_level=level)
            decisions[no] = {"decision": "footage", "graphic": "", "label": A.label(picked["authenticity"])}
            log(f"scene {no}: {picked['candidate'].channel} '{picked['candidate'].title[:60]}' {picked['window']['start']:.1f}-"
                f"{picked['window']['end']:.1f}s ({picked['authenticity']})")
        else:
            why = "no candidate passed the checks: shown with War graphics"
            entry["note"] = why
            _mark_graphics(man, no, rec, why)
            decisions[no] = {"decision": "graphics", "graphic": entry["graphic_intent"], "why": why}
            log(f"scene {no}: {why} ({len(pool)} found, {len(bad)} rejected by the rules)")
        report_scenes.append(entry)

    levels = {k: sum(1 for x in report_scenes if x.get("decision") == "footage" and x.get("match_level") == k)
              for k in ("exact", "contextual", "atmospheric")}
    report = {"version": 1, "render": render_id, "film_date": str(film_date), "topic": topic, "seconds": round(time.time() - t_start, 1),
              "story_period": [str(story[0]), str(story[1])] if story else None, "levels": levels,
              "graphics": sum(1 for x in report_scenes if x.get("decision") == "graphics"),
              "calls": dict(searcher.calls), "timing": {**{k: round(v, 1) if isinstance(v, float) else v for k, v in timing.items()},
                                                         "other_s": round(time.time() - t_start - timing["prefetch_s"] - timing["capture_ok_s"]
                                                                          - timing["capture_fail_s"], 1)},
              "scenes": report_scenes}
    _write(state_dir / REPORT, report)
    _write(state_dir / DECISIONS, decisions)
    placed = sum(1 for s in report_scenes if s["decision"] == "footage")
    log(f"Footage Director: {placed} of {len(report_scenes)} YouTube scenes have verified footage, the rest use War graphics "
        f"({report['seconds']:.0f} s; report in {state_dir / REPORT})")
    return report


def _mark_graphics(man: Any, no: str, rec: Dict[str, Any], why: str) -> None:
    """A clip an older run left for this scene is not used: the record says why (the Visuals tab shows it)."""
    if rec and str(rec.get("status") or "").lower() == "complete" and not (rec.get("user_override") or rec.get("source") == "manual"):
        man.set(no, dict(rec, status="failed", error=f"War Footage Director: {why}"))


def _write(p: Path, data: Any) -> None:
    try:
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def load_decisions(state_dir: Path) -> Dict[str, Dict[str, Any]]:
    try:
        return json.loads((Path(state_dir) / DECISIONS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apply_decisions(scenes: List[Dict[str, Any]], decisions: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scenes handed to the graphics get no_footage and, when their CSV row names no graphic, the War graphic that fits the sentence."""
    out = []
    for sc in scenes:
        sc = dict(sc)
        d = decisions.get(str(sc.get("scene_no"))) or decisions.get(f"{sc.get('scene_no')}".zfill(3)) or {}
        if d.get("decision") == "graphics" and not (sc.get("footage_meta") or {}).get("user_supplied"):
            sc["no_footage"] = True
            sc.pop("footage", None)
            sc.pop("footage_meta", None)
            if not str(sc.get("graphic") or "").strip() and d.get("graphic"):
                sc["graphic"] = d["graphic"]
                sc["graphic_by"] = "footage_director"
        elif d.get("label") and sc.get("footage_meta") is not None:
            sc["footage_meta"] = dict(sc["footage_meta"], label=d["label"])
        out.append(sc)
    return out
