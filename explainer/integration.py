"""The one entry point the application would call (Milestone 4b, after approval): never raises, returns the plan or the reasons it could not make one."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence

from .director import DirectorOptions, direct


def cartoon_share(settings: Optional[Dict[str, Any]]) -> float:
    """The only setting read: `explainer_cartoon_share`, the largest share of the runtime the director may turn into cartoon beats. Missing, unreadable or negative means 0 (none); at most 0.5."""
    try:
        v = float((settings or {}).get("explainer_cartoon_share", 0.0) or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0
    return 0.0 if v != v or v <= 0 else min(v, 0.5)


def _flag(settings: Optional[Dict[str, Any]], key: str) -> bool:
    """A switch from the application's settings: only a real True (or "true"/"1"/"yes"/"on", or the number 1) turns it on; missing or any bad value means False."""
    v = settings.get(key, False) if isinstance(settings, dict) else False
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "on")
    return v is True or (isinstance(v, int) and not isinstance(v, bool) and v == 1)


def motion_enabled(settings: Optional[Dict[str, Any]]) -> bool:
    """`explainer_motion` (the opt-in motion kit: verdict stamps and year plates)."""
    return _flag(settings, "explainer_motion")


def motion_pack(settings: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    """The upgrade phases, each its own opt-in: `explainer_numbers` (count-up numbers, cross-outs), `explainer_maplines` (map relation lines), `explainer_variety` (layout variety, dossier backdrop),
    `explainer_budget` (per-video effect windows and rotating variants). All default False."""
    return {"numbers": _flag(settings, "explainer_numbers"), "maplines": _flag(settings, "explainer_maplines"), "variety": _flag(settings, "explainer_variety"), "budget": _flag(settings, "explainer_budget")}


def fill_enabled(settings: Optional[Dict[str, Any]]) -> bool:
    """`explainer_fill` (the opt-in fill pass: near-empty board beats get a staged build from their own narration). Default False."""
    return _flag(settings, "explainer_fill")


def extras(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The engaging-upgrade switches, each its own opt-in, default off, a bad value means off: `explainer_sound`, `explainer_dialogue`, `explainer_scenes2`, `explainer_mapoverlay`, `explainer_texture`
    (booleans) and `explainer_camera` ("push", "drift" or "reframe"; anything else is "off")."""
    cam = settings.get("explainer_camera", "off") if isinstance(settings, dict) else "off"
    cam = cam.strip().lower() if isinstance(cam, str) else "off"
    return {"sound": _flag(settings, "explainer_sound"), "dialogue": _flag(settings, "explainer_dialogue"), "scenes2": _flag(settings, "explainer_scenes2"), "meaning": _flag(settings, "explainer_meaning"), "recipes": _flag(settings, "explainer_recipes"), "continuity": _flag(settings, "explainer_continuity"), "animate": _flag(settings, "explainer_animate"), "pictures": _flag(settings, "explainer_pictures"),
            "mapoverlay": _flag(settings, "explainer_mapoverlay"), "alive": _flag(settings, "explainer_alive"), "texture": _flag(settings, "explainer_texture"), "camera": cam if cam in ("push", "drift", "reframe") else "off"}


def map_share(settings: Optional[Dict[str, Any]]) -> float:
    """`explainer_map_share`: the largest share of the runtime that map beats may take (0.30 to 0.6; missing, lower or bad values keep the default 0.30)."""
    try:
        v = float(settings.get("explainer_map_share", 0.30)) if isinstance(settings, dict) else 0.30
    except (TypeError, ValueError):
        return 0.30
    return 0.30 if v != v or v < 0.30 else min(v, 0.6)


def build_sound(report: Dict[str, Any], words: Sequence, total: float, out: str, *, mood: str = "neutral", voice_path: Optional[str] = None) -> Optional[str]:
    """Only when the report says `options.sound` is on: the effects track and ducked bed (mixed with the voice when given) as one WAV. Returns its path, or None (never raises)."""
    try:
        if not (report.get("options") or {}).get("sound"):
            return None
        from .motion.sfx import build_explainer_sound
        return build_explainer_sound(report, words, total, out, mood=mood, voice_path=voice_path)
    except Exception:
        return None


def composite_map_overlays(report: Dict[str, Any], map_clips: Dict[str, str], out_dir: str) -> Dict[str, str]:
    """Only for beats whose report entry carries an `overlay` plan (options.mapoverlay): renders the alpha clip and lays it over the map clip `map_clips[beat_id]`. Returns {beat_id: new clip path};
    a beat that fails keeps its original clip (never raises)."""
    done: Dict[str, str] = {}
    try:
        from pathlib import Path as _P
        from .beats import overlay as OV
        for bid, info in (report.get("beat_details") or {}).items():
            plan, src = (info or {}).get("overlay"), map_clips.get(bid)
            if not plan or not plan.get("cues") or not src:
                continue
            try:
                d = _P(out_dir)
                d.mkdir(parents=True, exist_ok=True)
                mov, outp = d / f"{bid}_overlay.mov", d / f"{bid}_with_overlay.mp4"
                if OV.render_overlay(plan, mov)["returncode"] == 0 and OV.composite_over(src, mov, outp, start_s=0.0) == 0:
                    done[bid] = str(outp)
            except Exception:
                continue
    except Exception:
        pass
    return done


def post_render(video: Any, work: Any, voice_path: Any, log: Callable[[str], None] = lambda m: None) -> Dict[str, Any]:
    """After the whole video is drawn (map, board clips, presenter): lays each map beat's overlay (outlines, arrows, stamps, plates) over it at the beat's time, and builds the sound track
    (effects + ducked bed + the voice) from the plan the director left in <work>/explainer/render_report.json (or beside work). Returns {"video": path, "audio": path or None}; anything that
    fails keeps the video / the voice as they were and says so in the log (never raises)."""
    from pathlib import Path as _P
    out: Dict[str, Any] = {"video": video, "audio": None}
    try:
        rr = next((p for p in (_P(work) / "explainer" / "render_report.json", _P(work).parent / "explainer" / "render_report.json") if p.is_file()), None)
        if rr is None:
            return out
        import json
        data = json.loads(rr.read_text(encoding="utf-8"))
        report, words, total = data["report"], data["words"], float(data["total"])
        cur = _P(video)
        from .beats import overlay as OV
        n = 0
        for bid, info in sorted((report.get("beat_details") or {}).items()):
            plan = (info or {}).get("overlay")
            if not plan or not plan.get("cues"):
                continue
            try:
                mov, nxt = rr.parent / f"{bid}_overlay.mov", rr.parent / f"{cur.stem.split('__ov')[0]}__ov{n}.mp4"
                if OV.render_overlay(plan, mov)["returncode"] == 0 and OV.composite_over(cur, mov, nxt, start_s=float(plan["start"])) == 0 and nxt.is_file():
                    cur, n = nxt, n + 1
            except Exception as exc:
                log(f"[Explainer] the map overlay of {bid} could not be laid on ({str(exc)[:100]}); the map is used as it is")
        if n:
            log(f"[Explainer] {n} map overlay(s) laid on the video")
            out["video"] = cur
        if (report.get("options") or {}).get("sound") and voice_path:
            snd = build_sound(report, words, total, str(rr.parent / "explainer_audio.wav"), voice_path=str(voice_path))
            if snd:
                out["audio"] = snd
                log("[Explainer] sound effects and a quiet bed are mixed under the narration")
    except Exception as exc:
        log(f"[Explainer] the finishing step could not run ({str(exc)[:100]}); the video is used as it is")
    return out


def footage_settings(settings: Optional[Dict[str, Any]]):
    """(share, source) from `explainer_footage_share` (0 to 0.6, default 0: none) and `explainer_footage_source` (one of the application's footage sources, default stock_video)."""
    from .director.lexicon import FOOTAGE_SOURCES
    s = settings if isinstance(settings, dict) else {}
    try:
        v = float(s.get("explainer_footage_share", 0.0) or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    share = 0.0 if v != v or v <= 0 else min(v, 0.6)
    src = s.get("explainer_footage_source")
    return share, (src if src in FOOTAGE_SOURCES else "stock_video")


def look_settings(settings: Optional[Dict[str, Any]]):
    """(background, narrator style) from `explainer_background` (grey, paper, grid, warm; default paper) and `explainer_narrator` (serious or cartoon; default serious)."""
    from .board.backdrops import STYLES
    s = settings if isinstance(settings, dict) else {}
    bg, nar = s.get("explainer_background"), s.get("explainer_narrator")
    return (bg if bg in STYLES else "paper"), (nar if nar in ("serious", "cartoon") else "serious")


# The Explainer is meant to be full: every visual option is on unless the user saved a choice for it (the library defaults stay off).
FULL_LOOK = {"explainer_sound": True, "explainer_motion": True, "explainer_numbers": True, "explainer_maplines": True, "explainer_variety": True, "explainer_budget": True,
             "explainer_fill": True, "explainer_scenes2": True, "explainer_mapoverlay": True, "explainer_texture": True, "explainer_dialogue": True,
             "explainer_meaning": True, "explainer_recipes": True, "explainer_continuity": True, "explainer_animate": True, "explainer_alive": True, "explainer_pictures": True,
             "explainer_camera": "drift", "explainer_cartoon_share": 0.33, "explainer_footage_share": 0.0}


def full_look(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The application's settings with the full-look defaults under them (a saved choice always wins)."""
    return {**FULL_LOOK, **(settings if isinstance(settings, dict) else {})}


def direct_plan(words: Sequence, script: Optional[str], settings: Dict[str, Any], *, work_dir: str, duration: Optional[float] = None, places: Sequence[str] = (),
                archive_dir: Optional[str] = None, dissolve_s: float = 0.0, log: Callable[[str], None] = lambda m: None) -> Dict[str, Any]:
    """Returns {"plan": dict | None, "problems": [...], "warnings": [...], "report": {...}}. `settings` is the application's settings dict (read only; the one key read is `explainer_cartoon_share`, default 0)."""
    if archive_dir is None and _flag(settings, "explainer_pictures"):     # the people the narration names get a vetted portrait (Wikimedia Commons, public domain), kept in the work folder; none found = none shown
        try:
            from .director.portraits import build_library
            archive_dir = build_library(script, places, work_dir, log)
        except Exception:
            archive_dir = None
    opt = DirectorOptions(work_dir=work_dir, places=list(places), archive_dir=archive_dir, dissolve_s=float(dissolve_s), cartoon_share=cartoon_share(settings),
                          footage_share=footage_settings(settings)[0], footage_source=footage_settings(settings)[1],
                          background=look_settings(settings)[0], narrator_style=look_settings(settings)[1], motion=motion_enabled(settings), fill=fill_enabled(settings), **motion_pack(settings), **extras(settings), max_map_share=map_share(settings))
    r = direct(words, script, opt, duration=duration, log=log)
    return {"plan": r.plan, "problems": r.problems, "warnings": r.warnings, "report": r.report}
