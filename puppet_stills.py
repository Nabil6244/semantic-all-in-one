"""Paper-cutout puppet for the Normal style's still pictures, without editing video_generator.py (a protected file).

prepare(...) plans which scenes get a character move and renders one clip per planned scene (cached); applied(vg, mapping) is a context manager around
vg.render_video that makes those scenes use the clip instead of the still. A failed scene keeps its still, so the render never stops. Off unless the
"puppet_stills" setting is on."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence


def settings_from(raw: dict) -> dict:
    return {"enabled": bool(raw.get("puppet_stills", False)), "intensity": str(raw.get("puppet_intensity") or "medium"),
            "character": str(raw.get("puppet_character") or "auto"), "mode": str(raw.get("puppet_mode") or "story").strip().lower()}


def prepare(aligned: Sequence[dict], durations: Sequence[float], images_dir: "str | Path", state_dir: "str | Path", settings: dict,
            log: Callable[[str], None] = print, cancel: Optional[Callable[[], bool]] = None, words: Any = None,
            motion_renderer: Optional[Callable[..., Any]] = None) -> Dict[str, str]:
    """-> {scene_number (str, as in the rows): path of the puppet clip}. Empty when off, and on any failure of one scene that scene is simply left out.
    words: the narration's Whisper words [[w, start, end], ...] (story mode follows them; without them the words are spread evenly over each scene).
    motion_renderer(still_path, out_path, duration, fps, size, seed, params): when given (or settings["puppet_motion"] is on and health_cinema.puppet.motion
    exists), every scene WITHOUT a character gets a motion clip so no still stays static."""
    st = settings_from(settings)
    if not st["enabled"]:
        return {}
    if st["mode"] == "story":
        return prepare_story(aligned, durations, images_dir, state_dir, settings, log, cancel, words, motion_renderer)
    try:
        import video_generator as vg
        from health_cinema import puppet, puppet_plan
    except Exception as exc:
        log(f"[PUPPET] unavailable ({exc}); stills are used as they are")
        return {}
    images_dir, out_dir = Path(images_dir), Path(state_dir) / "puppet_stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    index = vg.build_scene_media_index(images_dir)
    scenes, t = [], 0.0
    for row, dur in zip(aligned, durations):
        src = vg.find_image_for_scene(images_dir, row["scene_number"], ext_cache=index)
        still = str(src) if src is not None and not vg.is_video_file(src) else None
        text = f'{row.get("script_segment", "")} {row.get("prompt", "")}'
        scenes.append({"scene_no": int(str(row["scene_number"]).strip()), "text": text, "start": t, "end": t + float(dur), "kind": "footage",
                       "visual": {"still": still} if still else {}, "_row": row["scene_number"]})
        t += float(dur)
    plan = puppet_plan.plan_puppet(scenes, {"enabled": True, "intensity": st["intensity"], "character": st["character"]}, None,
                                   has_still=lambda s: bool(s["visual"].get("still")), log=log, module=puppet)
    by_no = {s["scene_no"]: s for s in scenes}
    out: Dict[str, str] = {}
    for no, entry in plan.items():
        if cancel and cancel():
            break
        sc = by_no[no]
        try:
            h = puppet_plan.file_hash(sc["visual"]["still"])
            dur = sc["end"] - sc["start"] + 0.5
            key = puppet_plan.cache_key("shot", [h], entry["character"], entry["action"], entry["direction"], entry.get("params"),
                                        int(round(dur * 30)), 30, (1920, 1080), getattr(puppet, "VERSION", ""))
            dest = out_dir / f"{key}.mp4"
            if not dest.is_file():
                puppet.render_shot(sc["visual"]["still"], entry["character"], entry["action"], str(dest), duration=dur, fps=30,
                                   direction=entry["direction"], size=(1920, 1080), params=entry.get("params"))
            out[str(sc["_row"]).strip()] = str(dest)
            log(f"[PUPPET] scene {no}: {entry['character']} {entry['action']} ({entry['direction']})")
        except Exception as exc:
            log(f"[PUPPET] scene {no}: skipped ({exc}); its still is used")
    return out


@contextmanager
def applied(vg: Any, mapping: Dict[str, str]):
    """Around vg.render_video: find_image_for_scene returns the puppet clip for the mapped scenes. Restored on exit."""
    if not mapping:
        yield
        return
    orig = vg.find_image_for_scene
    keys = {}
    for k, v in mapping.items():
        try:
            keys[int(str(k).strip())] = Path(v)
        except ValueError:
            pass

    def find(images_dir, scene_number, ext_cache=None):
        try:
            hit = keys.get(int(str(scene_number).strip()))
        except ValueError:
            hit = None
        return hit if hit is not None and hit.is_file() else orig(images_dir, scene_number, ext_cache=ext_cache)

    vg.find_image_for_scene = find
    try:
        yield
    finally:
        vg.find_image_for_scene = orig


# ---- story mode: one protagonist who follows the narration and walks from picture to picture ------------------------------------------------------

def _scenes_from(aligned, durations, images_dir):
    import video_generator as vg
    index = vg.build_scene_media_index(Path(images_dir))
    scenes, t = [], 0.0
    for row, dur in zip(aligned, durations):
        src = vg.find_image_for_scene(Path(images_dir), row["scene_number"], ext_cache=index)
        still = str(src) if src is not None and not vg.is_video_file(src) else None
        scenes.append({"scene_no": int(str(row["scene_number"]).strip()), "start": t, "end": t + float(dur), "script_segment": row.get("script_segment", ""),
                       "prompt": row.get("prompt", ""), "still": still, "_row": row["scene_number"], "_video": bool(src is not None and still is None)})
        t += float(dur)
    return scenes


def _project_of(images_dir) -> Optional[str]:
    """The project folder (the one holding state/) above the pictures folder, for the hand-curated lanes sidecar."""
    try:
        for par in [Path(images_dir).resolve()] + list(Path(images_dir).resolve().parents)[:2]:
            if (par / "state").is_dir():
                return str(par)
    except Exception:       # noqa: BLE001
        pass
    return None


def _motion_fn(settings: dict, motion_renderer):
    if motion_renderer is not None:
        return motion_renderer
    if not (settings or {}).get("puppet_motion"):
        return None
    try:
        from health_cinema.puppet import motion
        return motion.render_motion
    except Exception:       # noqa: BLE001 - optional module
        return None


def prepare_story(aligned, durations, images_dir, state_dir, settings, log=print, cancel=None, words=None, motion_renderer=None) -> Dict[str, str]:
    st = settings_from(settings)
    try:
        import puppet_story
        import video_generator as vg
        from health_cinema import puppet, puppet_plan
        scenes = _scenes_from(aligned, durations, images_dir)
    except Exception as exc:
        log(f"[PUPPET] unavailable ({exc}); stills are used as they are")
        return {}
    out_dir = Path(state_dir) / "puppet_stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = puppet_story.plan_story([s for s in scenes if s["still"]], words if words is not None else (settings or {}).get("puppet_words"),
                                   {"intensity": st["intensity"], "character": st["character"], "seed": (settings or {}).get("puppet_seed"), "rows": list(aligned),
                                    "lane_fn": (settings or {}).get("puppet_lane_fn"), "lane_overrides": (settings or {}).get("puppet_lane_overrides"),
                                    "project_dir": (settings or {}).get("puppet_project_dir") or _project_of(images_dir)}, log)
    try:
        for line in puppet_story.explain(plan, scenes).splitlines():
            log("[STORY] " + line)
    except Exception:       # noqa: BLE001
        pass
    by_no = {s["scene_no"]: s for s in scenes}
    out: Dict[str, str] = {}
    for no, entry in (plan.get("scenes") or {}).items():
        if cancel and cancel():
            return out
        sc = by_no[no]
        try:
            dur = sc["end"] - sc["start"] + 0.5
            params = {"beats": [{k: b[k] for k in ("t0", "t1", "action", "x0", "x1", "params") if k in b} for b in entry["beats"]], "char_h": entry["char_h"]}
            if entry.get("y") is not None:
                params["y"] = entry["y"]
            if entry.get("lane"):
                params["lane"] = entry["lane"]
            if entry.get("prop"):
                params["prop"] = entry["prop"]
            h = puppet_plan.file_hash(sc["still"])
            key = puppet_plan.cache_key("story", [h], entry["character"], entry["action"], entry["direction"], params, int(round(dur * 30)), 30, (1920, 1080),
                                        getattr(puppet, "VERSION", "") + ":" + puppet_story.STORY_VERSION)
            dest = out_dir / f"{key}.mp4"
            if not dest.is_file():
                puppet.render_shot(sc["still"], entry["character"], entry["action"], str(dest), duration=dur, fps=30, direction=entry["direction"],
                                   size=(1920, 1080), params=params)
            out[str(sc["_row"]).strip()] = str(dest)
            log(f"[PUPPET] scene {no}: {entry['character']} {len(entry['beats'])} beats ({entry['role']})")
        except Exception as exc:
            log(f"[PUPPET] scene {no}: skipped ({exc}); its still is used")
    motion = _motion_fn(settings, motion_renderer)
    if motion is not None:
        for sc in scenes:
            key = str(sc["_row"]).strip()
            if key in out or not sc["still"]:
                continue
            if cancel and cancel():
                break
            try:
                dur = sc["end"] - sc["start"] + 0.5
                seed = int(puppet_plan.file_hash(sc["still"])[:6], 16)
                h = puppet_plan.file_hash(sc["still"])
                ck = puppet_plan.cache_key("motion", [h], None, "motion", "right", None, int(round(dur * 30)), 30, (1920, 1080), getattr(puppet, "VERSION", ""))
                dest = out_dir / f"{ck}.mp4"
                if not dest.is_file():
                    motion(sc["still"], str(dest), dur, 30, (1920, 1080), seed, None)
                if dest.is_file():
                    out[key] = str(dest)
            except Exception as exc:
                log(f"[PUPPET] scene {sc['scene_no']}: motion skipped ({exc}); its still is used")
    return out
