"""Health Cinema engine: narration sentences -> plan -> per-scene clips (cached) -> one 16:9 video with the voiceover.

Own compositor (not War Documentary's): that renderer is fixed at 1280x720 @ 25 fps, Health Cinema is 1920x1080 @ 24 landscape. It reuses the
shared pieces: the project workspace/state folder, ffmpeg resolution, the app's word timings (via app_section), and the segment-style
principles (bounded memory: one ffmpeg per clip, concat with -c copy, audio muxed once at the end, exact frame counts, nothing left behind on cancel)."""
from __future__ import annotations
import json, os, shutil, subprocess, tempfile, threading, time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import acquire as ACQ, assets, clips, direction, planner, profiles as P, relevance as RL

REVIEW_NOTE = ("Review flags come from keyword rules that point at wording needing a human check (unsourced statistics, causal or absolute wording, medication or "
               "supplement advice, preliminary research). They do not verify any medical claim and an empty list is not a clearance.")
NOT_IMPLEMENTED = ["sound design and music (narration only)", "word-level caption timing (captions are phrase-level, timed within each spoken sentence)"]
CREDIT_Z = "3D anatomy: Z-Anatomy (CC BY-SA 4.0) built on BodyParts3D (CC BY-SA 2.1 Japan); kidneys, ureters and adrenal glands: BodyParts3D, (c) The Database Center for Life Science, licensed under CC Attribution 4.0 International. 3D illustration, not clinical imagery."

NOT_IMPLEMENTED_HIGH_END = ["word-level caption timing (phrase boundaries snap to detected pauses; word times inside a phrase are estimated)", "tracking-style callouts exist only for the 3D labels (projected from the camera); footage is not object-tracked", "footage depth is simulated with layered plates and motes, not a depth map"]

from .render_journey import Cancelled, run_cancellable   # one cancellation type for the whole style (the app catches engine.Cancelled)

def _probe_duration(path: str) -> float:
    try: r = subprocess.run([assets.ffprobe_path() or "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired: return 0.0
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

def _judge(rec: dict, sc, d: dict, settings: Optional[dict], ff: str, log: Callable[[str], None]) -> dict:
    """Relevance check (health_cinema/relevance.py) for scenes about a named body part: title first, then frames when a vision key exists."""
    organ = sc.visual.get("anatomy_wanted")      # only scenes whose visual IS the body part (a person with knee pain is judged by the app's own QA)
    return RL.check(rec, sc.text, d.get("query") or sc.visual.get("query") or (d.get("queries") or [""])[0], organ, settings, ff, log)

def _retry_footage(sc, d: dict, acquirer: Callable, allow_youtube: bool, allow_flow: bool, settings: Optional[dict], log: Callable[[str], None], acquisition: dict, rounds: int = 2, better_than: Optional[dict] = None) -> bool:
    """A scene's footage was not found: ask the visual direction for other searches and try again (scene numbers 1000+ keep the retry apart from the
    failed manifest entry). True when a clip was found. Only when every retry fails does the caller fall back to a card."""
    import dataclasses
    tried = [sc.visual.get("query", "") or (d.get("queries") or [""])[0]]
    for rnd in range(1, rounds + 1):
        alts = direction.alternative_queries(d, tried, settings, log)
        if not alts: return False
        q = alts[0]; tried.append(q); no = int(sc.dscene_ids[0]); key = 1000 * rnd + no
        scn = dataclasses.replace(d["scene"], search_queries=[q]) if d.get("scene") is not None else None
        if scn is None: return False
        d2 = dict(d, queries=[q], scene=scn, query=q)
        if rnd == rounds and allow_youtube: d2["asset_type"] = "youtube_video"
        acquisition["requested"] += 1
        res = _judge(acquirer(ACQ.rows_for({key: d2}, allow_youtube, allow_flow)).get(key, {}), sc, d2, settings, assets.ffmpeg_path() or "ffmpeg", log)
        log(f"scene {sc.scene_no}: footage retry {rnd} with '{q[:60]}': {'found' if res.get('ok') else 'nothing'}")
        if res.get("ok") and better_than is not None and (ACQ.is_weak(res) or float((res.get("qa") or {}).get("semantic_match") or 0) <= float((better_than.get("qa") or {}).get("semantic_match") or 0)): continue
        if res.get("ok"):
            res["scene_key"] = key      # Generate scenes moves this clip to the scene's own row in the Visuals table
            sc.asset = res; sc.visual["path"] = res["path"]; sc.visual["query"] = q; acquisition["ok"] += 1; acquisition["retried_ok"] = acquisition.get("retried_ok", 0) + 1
            src = res.get("provider") or res.get("source") or "?"; acquisition["sources"][src] = acquisition["sources"].get(src, 0) + 1
            sc.decisions.append(f"first footage search found nothing; alternative search '{q[:50]}' succeeded")
            return True
    return False

def _kind_counts(scenes) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for sc in scenes: out[sc.kind] = out.get(sc.kind, 0) + 1
    return out

def timeline(sentences: List[dict], total_s: float) -> List[dict]:
    """Make the scenes contiguous from 0 to the voiceover length (gaps are absorbed by the previous scene, the last scene runs to the end)."""
    ss = sorted((dict(s) for s in sentences), key=lambda s: float(s["start"]))
    for i, s in enumerate(ss):
        s["start"] = 0.0 if i == 0 else float(ss[i - 1]["end"]); s["end"] = float(ss[i + 1]["start"]) if i + 1 < len(ss) else max(float(s["end"]), total_s or float(s["end"]))
        s["scene_no"] = s.get("scene_no") or i + 1
    return ss

def illustrations_wanted(scenes) -> List[dict]:
    """Every illustration card the plan pins on a 3D scene (organ cards and body-map beats), once per id: [{ref, prompt, type, topic, narration}].
    Generate scenes lists them in the Visuals tab; the ones the library already holds are shown there as done."""
    from . import illustrations as ILL
    out: Dict[str, dict] = {}
    for sc in scenes:
        if sc.kind != "anatomy_3d": continue
        want = list(sc.visual.get("cards") or []) + [{"type": r["hint"].get("card_type"), "ref": r["hint"].get("card_ref") or "", "prompt": r["hint"].get("card_prompt") or "", "topic": r["hint"].get("body_label") or r["hint"].get("body_region") or ""}
                                                     for r in sc.visual.get("body_rows") or [] if (r.get("hint") or {}).get("card_type") not in (None, "", "none")]
        for c in want:
            ref = c.get("ref") or ""
            if not ref or ref in out or not (c.get("prompt") or ILL.find(ref)): continue
            out[ref] = {"ref": ref, "prompt": c.get("prompt") or "", "type": c.get("type") or "mechanism", "topic": c.get("topic") or sc.visual.get("organ") or "", "narration": sc.text[:120]}
    return list(out.values())


def csv_directs(sentences: List[dict]) -> bool:
    """True when the scenes CSV picks the visuals itself: then nothing in the run calls Gemini."""
    return any(any(s.get(k) for k in ("visual", "organ", "shot", "footage", "footage_alt", "source", "overlay", "items")) for s in sentences)

def run_health_cinema(project_dir, sentences: List[dict], voiceover_path: str, out_path: str, *, profile: str = P.DEFAULT_PROFILE, quality: str = "final",
                      title: str = "", cancel_check: Optional[Callable[[], bool]] = None, progress_cb: Optional[Callable[[float, str], None]] = None,
                      log: Callable[[str], None] = lambda m: None, frame_renderer: Optional[Callable] = None, write_report: bool = True,
                      script_text: Optional[str] = None, settings: Optional[dict] = None, acquirer: Optional[Callable] = None, allow_youtube: bool = False,
                      allow_flow: bool = False, use_director: Optional[bool] = None, edit: str = "classic", music: bool = True, use_gemini: bool = True,
                      puppet: Optional[dict] = None, puppet_module=None, media_only: bool = False, table: Optional[Dict[int, dict]] = None) -> Dict:
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
    anatomy = assets.anatomy_status()
    if not anatomy["usable"]:      # never silent: without the 3D path every anatomy scene is footage or a card
        log("3D anatomy is NOT available (" + ("no model found in " + ", ".join(anatomy["dirs"]) if not any(anatomy["ready"].values()) else "Node/three.js/browser missing: " + ", ".join(anatomy["threejs_missing"] or ["browser"])) + "): anatomy scenes will use footage instead")
    acquisition: Dict = {"requested": 0, "ok": 0, "failed": 0, "sources": {}, "flow_used": False, "youtube_allowed": allow_youtube}
    dscenes: List[dict] = []; table_rows: List = []
    if not use_gemini: settings = dict(settings or {}, gemini_enabled=False)      # one switch: the director, footage retries and everything else stay on the built-in planner
    if director_on:
        prog(0.0, "planning scenes from the narration (the app's visual director)")
        script = script_text or " ".join(s["text"] for s in sents)
        csv_directed = csv_directs(sents)
        if csv_directed:      # the scenes CSV decides the visuals: no Gemini call anywhere in this run (planning, footage retries, frame checks)
            settings = dict(settings or {}, gemini_enabled=False)
            log("visuals planned from the scenes CSV (Gemini is not used for this run)"); dscenes = direction.dscenes_from_rows(sents)
        else: dscenes = direction.plan_visuals(script, settings, str(project_dir / "state"), log, cancel=lambda: cancel.is_set() or cancelled())
        if dscenes and dscenes[0].get("plan_source") not in ("gemini", "csv") and (settings or {}).get("gemini_enabled", True):
            settings = dict(settings or {}, gemini_enabled=False)                  # Gemini just failed: do not wait on it again for every footage retry
            log("Gemini was unavailable for planning: the rest of this run uses the built-in planner")
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
            if sc.kind == "footage": want[int(sc.dscene_ids[0])] = dict(by_id[sc.dscene_ids[0]], query=sc.visual.get("query") or "")
        def _same(a, b): return " ".join(str(a or "").split()).lower() == " ".join(str(b or "").split()).lower()
        chosen = {no: rec for no, rec in (table or {}).items() if no in want and rec.get("ok") and _same(rec.get("narration"), want[no].get("narration"))}      # the clips the Visuals tab holds
        table_rows = ACQ.rows_for(want, allow_youtube, allow_flow) if media_only else []
        if want:
            prog(0.0, f"getting footage for {len(want) - len(chosen)} scenes through the app's asset sources" + (f" ({len(chosen)} chosen in the Visuals tab)" if chosen else ""))
            rows = ACQ.rows_for({no: d for no, d in want.items() if no not in chosen}, allow_youtube, allow_flow); acquisition["requested"] = len(rows) + len(chosen)
            got = acquirer(rows) if rows else {}
            for sc in scenes:
                if sc.kind != "footage": continue
                rec = chosen.get(int(sc.dscene_ids[0]))
                if rec is not None:      # the Visuals tab's clip is the user's (or the last Generate's) choice: used as it is, never judged or replaced
                    sc.asset = rec; sc.visual["path"] = rec["path"]; acquisition["ok"] += 1; src = rec.get("provider") or rec.get("source") or "?"
                    acquisition["sources"][src] = acquisition["sources"].get(src, 0) + 1; acquisition["flow_used"] = acquisition["flow_used"] or "flow" in str(rec.get("source", "")).lower()
                    sc.decisions.append("clip taken from the Visuals tab")
                    if ACQ.is_weak(rec) and not rec.get("user_override"): sc.flags.append({"code": "footage_weak_match", "severity": "review", "message": "The footage matches the narration poorly; replace it in the Visuals tab before publishing."})
                    continue
                r = got.get(int(sc.dscene_ids[0]), {})
                r = _judge(r, sc, by_id[sc.dscene_ids[0]], settings, ff, log)
                retried = False
                if r.get("ok") and ACQ.is_weak(r):
                    if _retry_footage(sc, by_id[sc.dscene_ids[0]], acquirer, allow_youtube, allow_flow, settings, log, acquisition, better_than=r): continue      # a better clip was found
                    retried = True
                    if sc.visual.get("anatomy_wanted"):      # a clip of the wrong body part is worse than no clip: never show it as if it explained the narration
                        r = dict(r, ok=False, error=f"the only clips found show a different subject (QA {r['qa']['semantic_match']:.2f})")
                if r.get("ok"):
                    if ACQ.is_weak(r): sc.flags.append({"code": "footage_weak_match", "severity": "review", "message": f"The footage matches the narration poorly (visual QA {r['qa']['semantic_match']:.2f}) and no better clip was found; replace it before publishing."})
                    sc.asset = r; sc.visual["path"] = r["path"]; acquisition["ok"] += 1; acquisition["sources"][r.get("provider") or r.get("source") or "?"] = acquisition["sources"].get(r.get("provider") or r.get("source") or "?", 0) + 1
                    acquisition["flow_used"] = acquisition["flow_used"] or "flow" in str(r.get("source", "")).lower()
                else:
                    got_alt = (not retried) and _retry_footage(sc, by_id[sc.dscene_ids[0]], acquirer, allow_youtube, allow_flow, settings, log, acquisition)
                    if got_alt: continue
                    acquisition["failed"] += 1; why = r.get("error") or "no result"
                    sc.flags.append({"code": "footage_unavailable", "severity": "note", "message": f"Footage could not be acquired ({str(why)[:120]}); a typographic card is shown instead."})
                    sc.kind = "text_card"; sc.visual = {"text": sc.text, "beats": [{"text": x["text"], "t0": round(x["start"] - sc.start, 3)} for x in sc.sentences]}
                    log(f"scene {sc.scene_no}: footage failed ({str(why)[:100]}): typographic fallback")
    if media_only:      # Generate scenes: the footage is fetched and listed for the Visuals tab; Render makes the video from what the tab holds
        stop_watch.set()
        folder = getattr(acquirer, "images_dir", None)
        if folder is not None:
            from asset_manager import AssetManifest
            man = AssetManifest(Path(folder))
            for sc in scenes:
                key = (sc.asset or {}).get("scene_key")
                if sc.kind == "footage" and key and man.get(str(key)):      # a retry found the clip: it becomes the scene's own row
                    man.set(str(int(sc.dscene_ids[0])), dict(man.get(str(key)), scene_number=str(int(sc.dscene_ids[0]))))
        return {"ok": True, "media_only": True, "rows": table_rows, "acquisition": acquisition, "scenes": [s.as_dict() for s in scenes], "illustrations": illustrations_wanted(scenes),
                "visual_director": (dscenes[0]["plan_source"] if dscenes else "off")}
    if not (puppet and puppet.get("enabled")) and any(x.get("character_action") for x in sents): log("puppet: the scenes file has character_action cells but the paper-cutout switch is off, so they are ignored")
    if puppet and puppet.get("enabled") and edit == "high_end": log("puppet: the paper-cutout character is used by the Classic edit only; this High-end render has none")
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
               "scenes": [s.as_dict() for s in scenes], "plan_log": plan["log"], "review_flags": [dict(f, scene=s.scene_no) for s in scenes for f in s.flags] + er["flags"], "acquisition": acquisition, "anatomy": anatomy, "kind_counts": _kind_counts(scenes),
               "visual_director": (dscenes[0]["plan_source"] if dscenes else "off"), "review_note": REVIEW_NOTE, "not_implemented": NOT_IMPLEMENTED_HIGH_END, "credits": credits,
               "rights_not_established": bool(credits and credits[0] == CREDIT_Z), "rights_note": "3D anatomy is a CC BY-SA derivative evaluated locally; do not distribute until the licence review clears commercial use." if credits and credits[0] == CREDIT_Z else "",
               "high_end": er}
        if write_report: Path(str(out_path) + ".health_cinema.json").write_text(json.dumps(rep, indent=1, default=str))
        prog(1.0, "done"); return rep
    cache_dir = project_dir / "state" / "health_cinema" / quality; cache_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="hc_", dir=str(cache_dir)))
    pplan: Dict[int, dict] = {}; prunner = None; by_no = {sc.scene_no: sc for sc in scenes}
    if puppet and puppet.get("enabled"):      # opt-in paper-cutout character on some stills (health_cinema/puppet_plan.py); any problem there falls back to the normal scene render
        try:
            from . import puppet_plan as PP
            pplan = planner.puppet_plan(scenes, puppet, sents, PP.still_for, log, puppet_module)
            if pplan: prunner = PP.Runner(cache_dir, W, H, clips.FPS, cancel, log, module=puppet_module, cancel_exc=Cancelled)
        except Exception as exc: pplan = {}; log(f"puppet: planning failed ({type(exc).__name__}: {str(exc)[:120]}); no character in this run")
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
            r = None
            if prunner is not None and sc.scene_no in pplan:
                ent = pplan[sc.scene_no]
                r = prunner.render(sc, ent, by_no.get(ent.get("transition_from")), clips.captions_for(sc), round(sc.end * clips.FPS) - round(sc.start * clips.FPS))
                if r is None: sc.flags.append({"code": "puppet_fallback", "severity": "note", "message": "The character move could not be rendered; the scene is shown without it."})
            if r is None: r = clips.render_scene(sc, prof, cache_dir, quality=quality, cancel=cancel, log=log, frame_renderer=frame_renderer)
            if r["fallback"]: sc.flags.append({"code": "3d_fallback", "severity": "note", "message": r["fallback"]}); sc.kind = r["used_kind"]
            results.append(r)
        if cancelled(): raise Cancelled("cancelled")
        lst = work / "list.txt"; lst.write_text("".join(f"file '{Path(p).as_posix()}'\n" for r in results for p in list(r.get("pre") or []) + [r["path"]]))      # a puppet scene may open with its transition clip
        joined = work / "joined.mp4"
        _run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], "joining the scene clips")
        if voiceover_path:
            _run(["-i", str(joined), "-i", voiceover_path, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                  "-af", "apad", "-t", f"{sum(round(s.end * clips.FPS) - round(s.start * clips.FPS) for s in scenes) / clips.FPS:.3f}", str(tmp_out)], "adding the voiceover")
        else: shutil.copy2(joined, tmp_out)
        os.replace(tmp_out, out_path)
    except BaseException:
        try: tmp_out.unlink(missing_ok=True)      # never leave a half-written video behind
        except OSError: pass                        # (a file Windows still holds must not hide why it stopped)
        raise
    finally:
        stop_watch.set(); shutil.rmtree(work, ignore_errors=True)
    used3d = any(r["used_kind"] == "anatomy_3d" for r in results); credits = [CREDIT_Z] if used3d else []
    for s in scenes:
        a = s.asset or {}
        if a.get("path"): credits.append(f"Footage (scene {s.scene_no}): {a.get('provider') or a.get('source')} - {a.get('author') or 'unknown author'} {a.get('source_url') or ''} [query: {a.get('query', '')[:60]}]".strip())
    flags = [dict(f, scene=s.scene_no) for s in scenes for f in s.flags]
    rep = {"ok": True, "out": str(out_path), "profile": prof.id, "quality": quality, "size": [W, H], "fps": clips.FPS, "seconds": round(time.time() - t0, 2),
           "scenes": [dict(s.as_dict(), clip=r["path"], cache_hit=r["cache_hit"], fallback=r["fallback"], **({"puppet": r["puppet"]} if r.get("puppet") else {})) for s, r in zip(scenes, results)], "plan_log": plan["log"],
           "review_flags": flags, "acquisition": acquisition, "anatomy": anatomy, "kind_counts": _kind_counts(scenes), "visual_director": (dscenes[0]["plan_source"] if dscenes else "off"), "review_note": REVIEW_NOTE, "not_implemented": NOT_IMPLEMENTED, "credits": credits, "rights_not_established": used3d,
           "rights_note": "3D anatomy is a CC BY-SA derivative evaluated locally; do not distribute until the licence review clears commercial use." if used3d else ""}
    if prunner is not None: rep["puppet"] = dict(prunner.stats, planned_scenes=sorted(pplan))
    if write_report: Path(str(out_path) + ".health_cinema.json").write_text(json.dumps(rep, indent=1))
    prog(1.0, "done"); return rep
