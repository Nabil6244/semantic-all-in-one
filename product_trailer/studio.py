"""The page's back end (no UI): one entry point per film type, the AI scene steps, and a saved record of what was made.

    plan_film(...)      -> {"spec_path", "summary", "pack", "notes"}   Trailer, Reveal (with or without AI scenes) or Review
    ensure_references() -> the five reference pictures of the phone (rendered once, reused)
    make_scenes()       -> generate the pack's AI pictures in Flow (images only; clips are counted, never generated here)
    load_results()      -> what make_scenes() saved, so a later Generate uses the pictures

Nothing here starts on its own; the page calls these from its buttons, off the UI thread.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

FILM_TYPES = ("Trailer", "Reveal", "Review")
RESULTS_FILE = "scene_results.json"


def scene_dir(out_dir) -> Path:
    return Path(out_dir) / "scene_pack"


def refs_dir(out_dir) -> Path:
    return scene_dir(out_dir) / "refs"


def _colours(phone: str, colour: str = "") -> List[str]:
    from .references import preset_colours

    return preset_colours(phone)


def load_results(out_dir) -> Dict[Any, Any]:
    """{scene n (int): {"status", "path"?}} saved by make_scenes(); {} when nothing was made yet."""
    f = scene_dir(out_dir) / RESULTS_FILE
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[Any, Any] = {}
    for k, v in raw.items():
        if isinstance(v, dict) and (v.get("status") != "done" or Path(str(v.get("path", ""))).is_file()):
            out[int(k) if str(k).isdigit() else k] = v
    return out


def save_results(out_dir, results: Dict[Any, Any]) -> Path:
    d = scene_dir(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    f = d / RESULTS_FILE
    f.write_text(json.dumps({str(k): v for k, v in results.items()}, indent=1), encoding="utf-8")
    return f


def _read_features(csv_path: str, phone: str, colour: str, disclaimer: Optional[str], disclaimer_on: bool) -> Dict[str, Any]:
    from .csv_io import read_csv

    data = read_csv(csv_path)
    prod = data.setdefault("product", {})
    if phone:
        prod["phone"] = phone
        prod.setdefault("name", phone)
    if colour:
        prod["colour"] = colour
    if disclaimer:
        prod["disclaimer"] = disclaimer
    if not disclaimer_on:
        prod["disclaimer"] = ""
    return data


def plan_pack(film_type: str, *, csv: Optional[str] = None, script: Optional[str] = None, phone: str = "", colour: str = "", disclaimer: Optional[str] = None,
              disclaimer_on: bool = True, max_clips: int = 3):
    """The AI scene pack for a film (Reveal from the CSV, Review from the script) and its parsed source; (pack, data_or_parsed)."""
    from . import review, scenepack

    cols = _colours(phone, colour)
    if film_type == "Review":
        parsed = review.parse_script(review.review_source(script, csv))
        return review.plan_review_scenes(parsed, phone or "phone", cols), parsed
    data = _read_features(csv or "", phone, colour, disclaimer, disclaimer_on)
    p = phone or data["product"].get("phone") or data["product"].get("name") or "phone"
    return scenepack.plan_scene_pack(data["features"], p, _colours(p, colour), max_clips=max_clips), data


def plan_film(film_type: str, *, out_dir, csv: Optional[str] = None, script: Optional[str] = None, phone: str = "", colour: str = "", music: Optional[str] = None,
              disclaimer: Optional[str] = None, disclaimer_on: bool = True, width: int = 1920, height: int = 1080, fps: int = 30, use_ai: bool = False,
              max_clips: int = 3, voiceover: Optional[str] = None, words: Optional[Sequence[Any]] = None, voice_seconds: Optional[float] = None, style: str = "mixed", llm_run: Optional[Callable[[str, str], str]] = None,
              stock_settings: Optional[Dict[str, Any]] = None, log: Callable[[str], None] = print) -> Dict[str, Any]:
    """Write the film's spec and return {"spec_path", "summary", "pack", "notes"}. use_ai uses the pictures make_scenes() saved (a missing one is 3D)."""
    from . import mixed, review, scenepack
    from .planner import build_spec

    if film_type not in FILM_TYPES:
        raise ValueError(f"unknown film type {film_type!r}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pack, notes, summary = None, [], ""
    media = out / "media"
    if film_type == "Review":
        script = review.review_source(script, csv)
        if not script.strip():
            raise ValueError("Paste the review script, or choose a review CSV, first.")
        if style not in review.STYLES:
            raise ValueError(f"unknown review style {style!r}")
        pack, parsed = plan_pack("Review", script=script, phone=phone, colour=colour)
        if style == "infographic":
            use_ai = False      # flat paper shots need no AI picture
        if style == "mixed":    # the auto director picks a fitting visual for each plain line, then the film is planned as the cinematic one
            from . import director

            from . import footage, llm_director

            new = llm_director.llm_direct(parsed, phone, llm_run, log) if llm_run else None
            parsed = new or director.auto_direct(parsed, phone)          # the AI's scenes, or the built-in rules when it is not available
            if stock_settings:
                got = footage.resolve_footage(parsed, out, stock_settings, log)
                log(f"Stock footage: {got['found']} clip(s) found, {got['missing']} not found")
            style = "follow"
        results = load_results(out) if use_ai else {}
        prod = {"name": phone, "phone": phone, "disclaimer": (disclaimer or "") if disclaimer_on else ""}
        if voiceover and Path(voiceover).is_file():   # timed to the narrator: every line owns its stretch of the film
            from . import voiceover as vo

            ws = list(words or [])
            dur = float(voice_seconds or 0.0) or vo.audio_seconds(voiceover) or (float(ws[-1][2]) if ws else 0.0)
            if dur <= 0:
                raise ValueError("The voice-over's length could not be read.")
            lines = [i["text"] for c in parsed["chapters"] for i in c["items"] if i["kind"] == "line"]
            spec = review.plan_review_timed(parsed, pack, results, vo.align_lines(lines, ws, dur), ws, media_dir=media, width=width, height=height, fps=fps, product=prod, style=style)
        else:
            spec = review.plan_review(parsed, pack, results, media_dir=media, width=width, height=height, fps=fps, product=prod, style=style)
        notes = spec.get("whatif", {}).get("notes", [])
    elif use_ai:
        if not csv or not Path(csv).is_file():
            raise ValueError("Choose the feature CSV first.")
        pack, data = plan_pack(film_type, csv=csv, phone=phone, colour=colour, disclaimer=disclaimer, disclaimer_on=disclaimer_on, max_clips=max_clips)
        spec = mixed.plan_mixed(data, pack, load_results(out), media_dir=media, width=width, height=height, fps=fps)
        notes = spec.get("whatif", {}).get("notes", [])
    else:
        if not csv or not Path(csv).is_file():
            raise ValueError("Choose the feature CSV first.")
        path = build_spec(csv, music_path=music or None, out_dir=str(out), width=width, height=height, fps=fps, seed=None, phone=phone or None,
                          colour=colour or None, disclaimer=disclaimer if disclaimer_on else None, disclaimer_on=disclaimer_on,
                          pace="reveal" if film_type == "Reveal" else "trailer")
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
        if voiceover and Path(voiceover).is_file():   # a music-first film can still carry a voice-over on top
            spec.setdefault("product_trailer", {})["voiceover"] = str(voiceover)
            Path(path).write_text(json.dumps(spec, indent=1), encoding="utf-8")
        return {"spec_path": path, "summary": f"{film_type}: {len(spec['shots'])} shots, {spec['duration']:.0f} s", "pack": None, "notes": []}
    if music:
        spec.setdefault("product_trailer", {})["music"] = music
    if voiceover and Path(voiceover).is_file():
        spec.setdefault("product_trailer", {})["voiceover"] = str(voiceover)
    path = out / "product_trailer_spec.json"
    path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    e = pack["estimate"]
    summary = (f"{film_type}: {len(spec['shots'])} shots, {spec['duration']:.0f} s; {e['ai_images']} AI scenes, {e['three_d_shots']} 3D"
               + (f", {len(notes)} fell back to 3D" if notes else ""))
    return {"spec_path": str(path), "summary": summary, "pack": pack, "notes": notes}


def estimate_text(pack: Dict[str, Any]) -> str:
    e = pack["estimate"]
    clip = f" {e['ai_clips']} clip(s) are planned but not made here ({e['clip_credits']} credits)." if e["ai_clips"] else ""
    return f"{e['ai_images']} AI images, 0 credits.{clip} {e['three_d_shots']} shots stay 3D."


def ensure_references(phone: str, out_dir, *, log: Callable[[str], None] = print, runner: Optional[Callable] = None) -> Path:
    """The five reference pictures in <out_dir>/scene_pack/refs (rendered once; reused while all five exist)."""
    from . import references

    d = refs_dir(out_dir)
    if all(f.is_file() for f in references.reference_files(d)):
        return d
    references.render_references(phone or "galaxy s27 ultra", d, log=log, runner=runner)
    return d


def make_scenes(pack: Dict[str, Any], out_dir, client, *, phone: str = "", log: Callable[[str], None] = print, ref_runner: Optional[Callable] = None,
                timeout_s: float = 900.0) -> Dict[Any, Any]:
    """Render the references if needed, make every AI scene's picture in Flow, save and return the results. Images only: 0 credits."""
    from . import scenepack

    d = ensure_references(phone or pack.get("phone", ""), out_dir, log=log, runner=ref_runner)
    results = scenepack.generate_scene_pack(pack, d, scene_dir(out_dir) / "run", client, log=log, timeout_s=timeout_s)
    save_results(out_dir, results)
    ok = sum(1 for r in results.values() if r["status"] == "done")
    log(f"AI scenes: {ok} of {len(results)} made; the rest become 3D shots")
    return results
