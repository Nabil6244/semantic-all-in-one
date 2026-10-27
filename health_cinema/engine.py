"""Health Cinema engine: narration sentences -> plan -> per-scene clips (cached) -> one 16:9 video with the voiceover.

Own compositor (not War Documentary's): that renderer is fixed at 1280x720 @ 25 fps, Health Cinema is 1920x1080 @ 24 landscape. It reuses the
shared pieces: the project workspace/state folder, ffmpeg resolution, the app's word timings (via app_section), and the segment-style
principles (bounded memory: one ffmpeg per clip, concat with -c copy, audio muxed once at the end, exact frame counts, nothing left behind on cancel)."""
from __future__ import annotations
import json, os, shutil, subprocess, tempfile, threading, time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import acquire as ACQ, assets, clips, direction, planner, profiles as P

REVIEW_NOTE = ("Review flags come from keyword rules that point at wording needing a human check (unsourced statistics, causal or absolute wording, medication or "
               "supplement advice, preliminary research). They do not verify any medical claim and an empty list is not a clearance.")
NOT_IMPLEMENTED = ["sound design and music (narration only)", "word-level caption timing (captions are phrase-level, timed within each spoken sentence)"]
CREDIT_Z = "3D anatomy: Z-Anatomy (CC BY-SA 4.0) built on BodyParts3D (CC BY-SA 2.1 Japan). 3D illustration, not clinical imagery."

NOT_IMPLEMENTED_HIGH_END = ["word-level caption timing (phrase boundaries snap to detected pauses; word times inside a phrase are estimated)", "tracking-style callouts exist only for the 3D labels (projected from the camera); footage is not object-tracked", "footage depth is simulated with layered plates and motes, not a depth map"]

from .render_journey import Cancelled, run_cancellable   # one cancellation type for the whole style (the app catches engine.Cancelled)

def _probe_duration(path: str) -> float:
    r = subprocess.run([assets.ffprobe_path() or "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0

def footage_lookup(project_dir: Path) -> Callable[[dict], Optional[str]]:
    """Footage convention (no manifest coupling): <project>/Health Cinema footage/<n>.mp4 where n is the 1-based sentence number; or `footage` in the scenes file."""
    folder = Path(project_dir) / "Health Cinema footage"
    def find(s: dict) -> Optional[str]:
        n = s.get("scene_no")
        if n is None or not folder.is_dir(): return None
        for ext in (".mp4", ".mov", ".mkv", ".webm"):
            p = folder / f"{n}{ext}"
            if p.is_file(): return str(p)
        return None
    return find

def timeline(sentences: List[dict], total_s: float) -> List[dict]:
    """Make the scenes contiguous from 0 to the voiceover length (gaps are absorbed by the previous scene, the last scene runs to the end)."""
    ss = sorted((dict(s) for s in sentences), key=lambda s: float(s["start"]))
    for i, s in enumerate(ss):
        s["start"] = 0.0 if i == 0 else float(ss[i - 1]["end"]); s["end"] = float(ss[i + 1]["start"]) if i + 1 < len(ss) else max(float(s["end"]), total_s or float(s["end"]))
        s["scene_no"] = s.get("scene_no") or i + 1
    return ss

def run_health_cinema(project_dir, sentences: List[dict], voiceover_path: str, out_path: str, *, profile: str = P.DEFAULT_PROFILE, quality: str = "final",
                      title: str = "", cancel_check: Optional[Callable[[], bool]] = None, progress_cb: Optional[Callable[[float, str], None]] = None,
                      log: Callable[[str], None] = lambda m: None, frame_renderer: Optional[Callable] = None, write_report: bool = True,
                      script_text: Optional[str] = None, settings: Optional[dict] = None, acquirer: Optional[Callable] = None, allow_youtube: bool = False,
                      allow_flow: bool = False, use_director: Optional[bool] = None, edit: str = "classic", music: bool = True) -> Dict:
    t0 = time.time(); project_dir = Path(project_dir); cancel = threading.Event(); cancelled = cancel_check or (lambda: False)
    stop_watch = threading.Event()
    def _watch():   # the caller's cancel flag also stops a render that is in the middle of a scene (kills the node/Chromium/ffmpeg children)
        while not stop_watch.wait(0.2):
            if cancelled(): cancel.set(); return
    threading.Thread(target=_watch, name="hc-cancel-watch", daemon=True).start()
    if quality not in clips.SIZES: raise ValueError(f"quality must be one of {list(clips.SIZES)} (16:9 landscape only)")
    W, H = clips.SIZES[quality]; prof = P.get_profile(profile); ff = assets.ffmpeg_path() or "ffmpeg"
    prog = progress_cb or (lambda k, m: None)
    total = _probe_duration(voiceover_path) if voiceover_path else 0.0
    sents = timeline(sentences, total)
    ready = assets.anatomy_ready() if frame_renderer is None else assets.anatomy_assets() is not None
    director_on = (acquirer is not None or settings is not None) if use_director is None else use_director
    acquisition: Dict = {"requested": 0, "ok": 0, "failed": 0, "sources": {}, "flow_used": False, "youtube_allowed": allow_youtube}
    dscenes: List[dict] = []
    if director_on:
        prog(0.0, "planning scenes from the narration (the app's visual director)")
        script = script_text or " ".join(s["text"] for s in sents)
        dscenes = direction.plan_visuals(script, settings, str(project_dir / "state"), log)
        tpl_ok = (lambda t: assets.template_ready(t)) if frame_renderer is not None else (lambda t: assets.template_ready(t) and assets.threejs_ready())
        plan = planner.plan_directed(sents, profile, dscenes, tpl_ok, allow_footage=acquirer is not None, title=title)
    else:
        plan = planner.plan(sents, profile, assets_ok=ready, footage_for=footage_lookup(project_dir), title=title)
    scenes = plan["scenes"]
    if not scenes: raise ValueError("no scenes to render")
    scenes[0].start = 0.0; scenes[-1].end = max(scenes[-1].end, total)
    for a, b in zip(scenes, scenes[1:]): b.start = a.end        # contiguous, exact frame boundaries
    if acquirer is not None and dscenes:
        by_id = {d["scene_id"]: d for d in dscenes}; want = {}
        for sc in scenes:
            if sc.kind == "footage": want[int(sc.dscene_ids[0])] = by_id[sc.dscene_ids[0]]
        if want:
            prog(0.0, f"getting footage for {len(want)} scenes through the app's asset sources")
            rows = ACQ.rows_for(want, allow_youtube, allow_flow); acquisition["requested"] = len(rows)
            got = acquirer(rows)
            for sc in scenes:
                if sc.kind != "footage": continue
                r = got.get(int(sc.dscene_ids[0]), {})
                if r.get("ok"):
                    sc.asset = r; sc.visual["path"] = r["path"]; acquisition["ok"] += 1; acquisition["sources"][r.get("provider") or r.get("source") or "?"] = acquisition["sources"].get(r.get("provider") or r.get("source") or "?", 0) + 1
                    acquisition["flow_used"] = acquisition["flow_used"] or "flow" in str(r.get("source", "")).lower()
                else:
                    acquisition["failed"] += 1; why = r.get("error") or "no result"
                    sc.flags.append({"code": "footage_unavailable", "severity": "note", "message": f"Footage could not be acquired ({str(why)[:120]}); a typographic card is shown instead."})
                    sc.kind = "text_card"; sc.visual = {"text": sc.text, "beats": [{"text": x["text"], "t0": round(x["start"] - sc.start, 3)} for x in sc.sentences]}
                    log(f"scene {sc.scene_no}: footage failed ({str(why)[:100]}): typographic fallback")
    if edit == "high_end":   # opt-in: the layered compositing / editorial pipeline (health_cinema/edit); the classic path below is unchanged
        from .edit import pipeline, media as EM
        try:
            er = pipeline.render_high_end(scenes, voiceover_path, str(out_path), project_dir, prof=prof, quality=quality, W=W, H=H, cancel=cancel, log=log, progress=prog, frame_renderer=frame_renderer, music=music)
        except EM.Cancelled as exc: raise Cancelled(str(exc))
        finally: stop_watch.set()
        credits = [CREDIT_Z] if any(x["kind"] == "anatomy" for x in er["plan"]["shots"]) else []
        for s in scenes:
            a = s.asset or {}
            if a.get("path"): credits.append(f"Footage (scene {s.scene_no}): {a.get('provider') or a.get('source')} - {a.get('author') or 'unknown author'} {a.get('source_url') or ''} [query: {a.get('query', '')[:60]}]".strip())
        if er["audio"].get("credit"): credits.append(er["audio"]["credit"])
        rep = {"ok": True, "out": str(out_path), "profile": prof.id, "quality": quality, "size": [W, H], "fps": clips.FPS, "seconds": round(time.time() - t0, 2), "edit": "high_end",
               "scenes": [s.as_dict() for s in scenes], "plan_log": plan["log"], "review_flags": [dict(f, scene=s.scene_no) for s in scenes for f in s.flags] + er["flags"], "acquisition": acquisition,
               "visual_director": (dscenes[0]["plan_source"] if dscenes else "off"), "review_note": REVIEW_NOTE, "not_implemented": NOT_IMPLEMENTED_HIGH_END, "credits": credits,
               "rights_not_established": bool(credits and credits[0] == CREDIT_Z), "rights_note": "3D anatomy is a CC BY-SA derivative evaluated locally; do not distribute until the licence review clears commercial use." if credits and credits[0] == CREDIT_Z else "",
               "high_end": er}
        if write_report: Path(str(out_path) + ".health_cinema.json").write_text(json.dumps(rep, indent=1, default=str))
        prog(1.0, "done"); return rep
    cache_dir = project_dir / "state" / "health_cinema" / quality; cache_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="hc_", dir=str(cache_dir)))
    def _run(args, what):
        try: run_cancellable([ff, "-y", "-v", "error"] + args, cancel, 1800)
        except Cancelled: raise
        except Exception as exc: raise RuntimeError(f"ffmpeg failed while {what}: {str(exc)[-300:]}") from exc
    results: List[dict] = []; out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_name(out_path.name + ".rendering.mp4")
    try:
        for i, sc in enumerate(scenes):
            if cancelled() or cancel.is_set(): cancel.set(); raise Cancelled("cancelled")
            prog(i / len(scenes), f"scene {sc.scene_no}/{len(scenes)}: {sc.kind}")
            r = clips.render_scene(sc, prof, cache_dir, quality=quality, cancel=cancel, log=log, frame_renderer=frame_renderer)
            if r["fallback"]: sc.flags.append({"code": "3d_fallback", "severity": "note", "message": r["fallback"]}); sc.kind = r["used_kind"]
            results.append(r)
        if cancelled(): raise Cancelled("cancelled")
        lst = work / "list.txt"; lst.write_text("".join(f"file '{Path(r['path']).as_posix()}'\n" for r in results))
        joined = work / "joined.mp4"
        _run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], "joining the scene clips")
        if voiceover_path:
            _run(["-i", str(joined), "-i", voiceover_path, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                  "-af", "apad", "-t", f"{sum(round(s.end * clips.FPS) - round(s.start * clips.FPS) for s in scenes) / clips.FPS:.3f}", str(tmp_out)], "adding the voiceover")
        else: shutil.copy2(joined, tmp_out)
        os.replace(tmp_out, out_path)
    except BaseException:
        tmp_out.unlink(missing_ok=True); raise      # never leave a half-written video behind
    finally:
        stop_watch.set(); shutil.rmtree(work, ignore_errors=True)
    used3d = any(r["used_kind"] == "anatomy_3d" for r in results); credits = [CREDIT_Z] if used3d else []
    for s in scenes:
        a = s.asset or {}
        if a.get("path"): credits.append(f"Footage (scene {s.scene_no}): {a.get('provider') or a.get('source')} - {a.get('author') or 'unknown author'} {a.get('source_url') or ''} [query: {a.get('query', '')[:60]}]".strip())
    flags = [dict(f, scene=s.scene_no) for s in scenes for f in s.flags]
    rep = {"ok": True, "out": str(out_path), "profile": prof.id, "quality": quality, "size": [W, H], "fps": clips.FPS, "seconds": round(time.time() - t0, 2),
           "scenes": [dict(s.as_dict(), clip=r["path"], cache_hit=r["cache_hit"], fallback=r["fallback"]) for s, r in zip(scenes, results)], "plan_log": plan["log"],
           "review_flags": flags, "acquisition": acquisition, "visual_director": (dscenes[0]["plan_source"] if dscenes else "off"), "review_note": REVIEW_NOTE, "not_implemented": NOT_IMPLEMENTED, "credits": credits, "rights_not_established": used3d,
           "rights_note": "3D anatomy is a CC BY-SA derivative evaluated locally; do not distribute until the licence review clears commercial use." if used3d else ""}
    if write_report: Path(str(out_path) + ".health_cinema.json").write_text(json.dumps(rep, indent=1))
    prog(1.0, "done"); return rep
