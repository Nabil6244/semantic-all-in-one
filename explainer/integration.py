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
    return {"sound": _flag(settings, "explainer_sound"), "dialogue": _flag(settings, "explainer_dialogue"), "scenes2": _flag(settings, "explainer_scenes2"),
            "mapoverlay": _flag(settings, "explainer_mapoverlay"), "texture": _flag(settings, "explainer_texture"), "camera": cam if cam in ("push", "drift", "reframe") else "off"}


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
FULL_LOOK = {"explainer_motion": True, "explainer_numbers": True, "explainer_maplines": True, "explainer_variety": True, "explainer_budget": True,
             "explainer_fill": True, "explainer_scenes2": True, "explainer_mapoverlay": True, "explainer_texture": True, "explainer_dialogue": True,
             "explainer_camera": "drift", "explainer_cartoon_share": 0.25, "explainer_footage_share": 0.2}


def full_look(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The application's settings with the full-look defaults under them (a saved choice always wins)."""
    return {**FULL_LOOK, **(settings if isinstance(settings, dict) else {})}


def direct_plan(words: Sequence, script: Optional[str], settings: Dict[str, Any], *, work_dir: str, duration: Optional[float] = None, places: Sequence[str] = (),
                archive_dir: Optional[str] = None, dissolve_s: float = 0.0, log: Callable[[str], None] = lambda m: None) -> Dict[str, Any]:
    """Returns {"plan": dict | None, "problems": [...], "warnings": [...], "report": {...}}. `settings` is the application's settings dict (read only; the one key read is `explainer_cartoon_share`, default 0)."""
    opt = DirectorOptions(work_dir=work_dir, places=list(places), archive_dir=archive_dir, dissolve_s=float(dissolve_s), cartoon_share=cartoon_share(settings),
                          footage_share=footage_settings(settings)[0], footage_source=footage_settings(settings)[1],
                          background=look_settings(settings)[0], narrator_style=look_settings(settings)[1], motion=motion_enabled(settings), fill=fill_enabled(settings), **motion_pack(settings), **extras(settings), max_map_share=map_share(settings))
    r = direct(words, script, opt, duration=duration, log=log)
    return {"plan": r.plan, "problems": r.problems, "warnings": r.warnings, "report": r.report}
