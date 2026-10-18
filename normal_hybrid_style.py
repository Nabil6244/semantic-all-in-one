"""Hybrid Map graphics & sound for a Normal Video (the Smart editing switch "Use Hybrid Map Graphics & Sound").

Off by default; when off nothing here is imported. When on, an ordinary video (its own footage, narration and scene order) gets the
Hybrid Map template's treatment, using what the Hybrid pipeline already has and nothing it would have to invent:

  graphics  the News Doc look of Doc Style (graphics/doc_style.py, graphics/doc_plan.py), the look Hybrid Map draws its tags,
            titles, numbers and cards in, with Graphics switched on for the render. No map, outline or place boundary is added:
            a place appears only as the label the narration itself calls for.
  sound     Hybrid Map's sound design (pakmap/audio_plan.py restraint rules, pakmap/sounds.py vocabulary, pakmap/audio_mix.py
            mixer: narration first, effects ducked under it, no two effects stacked) driven by the graphics that are really on
            screen and by the stronger scene transitions. It replaces the Normal Video's own effects for this render (never
            both, so nothing plays twice); ambience beds and background music are the Normal Video's own and are untouched.

    sound_events(specs, scene_cuts)                  -> [event]            what makes a sound, and when
    plan_sound(specs, scene_cuts, duration)          -> AudioPlan          the pakMap planner's plan for those events
    finishing(vg, ...)                               -> context manager    mixes the sound design in just before render_video's mux
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SETTING_KEY = "normal_hybrid_style"

LEAD_S = 0.05              # a graphic's sound lands as its entrance starts
TRANSITION_GAP_S = 8.0     # transition effects are rare: at most one every 8 s
# Doc Style look (graphics/doc_plan.py `doc_look`) -> the pakMap vocabulary sound (the same pairs as gfx_templates.PRIM_SOUND)
LOOK_SOUND = {
    "checklist": "ui_click", "rings": "marker_pop", "forecast": "ui_click", "polaroids": "paper_slide", "panel": "paper_slide",
    "quote": "paper_slide", "quote_card": "paper_slide", "framed": "paper_slide", "dossier": "paper_slide", "glitch": "fast_whoosh",
}
# graphic role (graphics/schema.py) -> sound
ROLE_SOUND = {
    "NAME": "ui_click", "LOWER_THIRD": "ui_click", "SUBTITLE": "ui_click", "CALLOUT": "ui_click", "EMPHASIS": "ui_click", "LABEL": "ui_click",
    "LOCATION": "marker_pop", "STATISTIC": "counter_ticks", "DATA": "counter_ticks", "COUNTDOWN": "counter_ticks", "PROGRESS": "counter_ticks",
    "TITLE": "deep_thud", "CHAPTER": "deep_thud", "REVEAL": "deep_thud", "QUOTE": "paper_slide", "DOCUMENT": "paper_slide",
    "CHART": "bubble_pluck", "COMPARISON": "bubble_pluck", "RANKING": "bubble_pluck", "TIMELINE": "draw_zap", "PROCESS": "draw_zap",
    "DIAGRAM": "draw_zap",
}
NO_SOUND_LOOKS = {"watermark"}
# scene transitions that earn a sound (a plain fade, dissolve or crossfade stays quiet, as Hybrid's dissolves do)
TRANSITION_SOUND = {"zoom_blur": "fast_whoosh", "dip_black": "soft_transition", "dip_white": "soft_transition", "wipe": "soft_transition",
                    "slide": "soft_transition", "flash": "soft_transition"}
# graphic roles that are maps are never drawn by this switch (and make no sound here)
MAP_ROLES = {"MAP", "ARROW", "HIGHLIGHT"}


def is_on(settings: Optional[dict]) -> bool:
    return bool((settings or {}).get(SETTING_KEY, False))


def _event(eid: str, t_in: float, t_out: float, sound: str, why: str, at: float = LEAD_S) -> dict:
    return {"id": eid, "type": "map_template", "t_in": float(t_in), "t_out": float(t_out),
            "template": {"id": why, "sfx": [{"at": at, "sound": sound}], "items": []}}


def sound_events(specs: Sequence[Any], scene_cuts: Sequence[Tuple[float, str]] = ()) -> List[dict]:
    """The events a Hybrid sound plan is made from: one per graphic that comes on screen, one per strong scene transition.
    specs: graphics.schema.GraphicSpec (start/end/role/payload); scene_cuts: (time the new scene starts, transition style)."""
    events: List[dict] = []
    for i, s in enumerate(specs):
        try:
            payload = getattr(s, "payload", None) or {}
            look = str(payload.get("doc_look") or "")
            role = str(getattr(s, "role", "") or "").upper()
            if look in NO_SOUND_LOOKS or role in MAP_ROLES:
                continue
            sound = LOOK_SOUND.get(look) if look else ROLE_SOUND.get(role)
            if not sound:
                continue
            events.append(_event(f"gfx{i}", float(s.start), float(s.end), sound, f"normal graphic {look or role.lower()}"))
        except (TypeError, ValueError, AttributeError):
            continue    # one odd spec never stops the rest
    last = -1e9
    for t, style in sorted((float(t), str(st or "").lower()) for t, st in scene_cuts):
        sound = TRANSITION_SOUND.get(style)
        if not sound or t - last < TRANSITION_GAP_S:
            continue
        last = t
        events.append(_event(f"cut{int(t * 1000)}", t, t + 0.5, sound, f"scene transition {style}", at=0.0))
    return events


def plan_sound(specs: Sequence[Any], scene_cuts: Sequence[Tuple[float, str]], duration: float, catalog: Any = None,
               template_events: Sequence[dict] = ()):
    """The pakMap sound planner on those events (its spacing / repeat / density rules apply), library files found; no audio is read."""
    from pakmap.audio_mix import resolve_assets
    from pakmap.audio_plan import plan_audio

    # gfx-core template graphics (normal_gfx) carry their own sounds: gfx_templates.sfx_cues reads what each template draws and when its pieces come in
    spec = {"duration": float(duration), "events": sound_events(specs, scene_cuts) + [dict(e) for e in template_events], "camera": {}}
    return resolve_assets(plan_audio(spec, {}, enabled=True, duration=float(duration)), catalog)


def _finisher(narration: str, out_path: "str | Path", duration: float, log: Callable[[str], None]) -> Callable[[dict], Optional[str]]:
    """{"graphics": [...], "scene_cuts": [(t, style)]} -> the audio to mux (the narration mixed with the Hybrid sound design) or None to keep it.
    Never raises: a failed mix leaves the narration alone and says so."""
    def finish(info: dict) -> Optional[str]:
        try:
            from pakmap.audio_mix import mix_pakmap_audio
            from sfx.seed import ensure_sfx_library

            ensure_sfx_library()
            plan = plan_sound(info.get("graphics") or [], info.get("scene_cuts") or [], duration, template_events=info.get("template_events") or [])
            Path(out_path).with_name("hybrid_style_sound_plan.txt").write_text(plan.to_text(), encoding="utf-8")
            if not plan.cues:
                log("[HYBRID STYLE] No sound effects fit this video; the audio is left as it is.")
                return None
            for sid, what in sorted(plan.missing.items()):
                log(f"[HYBRID STYLE] sound {sid} skipped: {what}")
            mix = mix_pakmap_audio(plan, narration, out_path, duration=duration)
            log(f"[HYBRID STYLE] Hybrid Map sound design: {len(plan.cues)} effect(s), {len(plan.dropped)} dropped for restraint, "
                f"ducked under the narration.")
            return str(mix.path) if mix.changed else None
        except Exception as exc:
            log(f"[HYBRID STYLE] Sound design skipped ({exc}); the audio is left as it is.")
            return None
    return finish


@contextmanager
def finishing(vg: Any, narration: str, out_path: "str | Path", duration: float, scene_starts: Sequence[float],
              style_by_scene_index: Dict[int, str], log: Callable[[str], None] = print, template_events: Sequence[dict] = (),
              spec_filter: Optional[Callable[[Sequence[Any]], Sequence[Any]]] = None):
    """Around vg.render_video only, without editing video_generator.py (a protected file): collects the graphics the render really draws
    (the timeline's plus Doc Style's extras) and, right before the final mux, swaps in the narration mixed with the sound design.
    Everything is restored on exit, and a failure anywhere leaves the render exactly as it would have been.
    scene_starts: each scene's start time; style_by_scene_index: {scene index: transition style} from the Pacing Director."""
    import graphics
    import graphics.doc_plan as doc_plan

    seen: List[Any] = []
    orig_timeline, orig_extras, orig_mux = graphics.graphics_from_timeline, doc_plan.plan_doc_extras, vg.run_final_mux
    finish = _finisher(narration, out_path, duration, log)

    def timeline_specs(*a, **k):
        got = orig_timeline(*a, **k)
        if spec_filter is not None:      # e.g. the plain stats a gfx-core template replaced are not drawn twice
            got = list(spec_filter(got))
        seen.extend(got)
        return got

    def extras(*a, **k):
        got = orig_extras(*a, **k)
        seen.extend(got)
        return got

    def mux(*a, **k):
        try:
            cuts = {i: st for i, st in style_by_scene_index.items() if i >= 1}
            for i, rt in enumerate(k.get("transitions") or [], start=1):     # real cross-scene transitions from the edit decisions
                if rt and i not in cuts:
                    cuts[i] = rt[0]
            pairs = [(scene_starts[i], st) for i, st in cuts.items() if i < len(scene_starts)]
            new_audio = finish({"graphics": list(seen), "scene_cuts": pairs, "template_events": list(template_events)})
            if new_audio:
                k["audio_path"] = new_audio
        except Exception as exc:
            log(f"[HYBRID STYLE] Audio finishing skipped ({exc})")
        return orig_mux(*a, **k)

    graphics.graphics_from_timeline, doc_plan.plan_doc_extras, vg.run_final_mux = timeline_specs, extras, mux
    try:
        yield
    finally:
        graphics.graphics_from_timeline, doc_plan.plan_doc_extras, vg.run_final_mux = orig_timeline, orig_extras, orig_mux
