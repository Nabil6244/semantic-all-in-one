"""What If's sound: every graphic sounds like what it does -- a line draws (zap), a number counts (ticks), a dot lands (pop), a title
or statement lands (thud), a section opens (riser) -- a change of shot kind gets a soft transition, and the ambience bed follows the
story (water, wind, cold, the space drone). The sounds, the no-stacking rule and
the mix (narration first, everything ducked under the voice) are pakMap's, used as they are (as StarMap does)."""

from __future__ import annotations

from typing import Any, Dict, List

LAYER_SFX = {"tm_metric": "data_tick", "tm_caption": "ui_click", "tm_title": "deep_thud", "tm_fade": "deep_thud", "tm_survival": "ui_click",
             "tm_clock": "clock_ticking", "tm_gauge": "data_tick", "tm_composition": "counter_ticks", "tm_logaxis": "directional_whoosh",
             "tm_compare": "bubble_pluck", "tm_bars": "counter_ticks", "tm_timeline": "marker_pop", "tm_discmap": "shimmer_riser",
             "tm_annotate": "marker_pop", "tm_curve": "draw_zap", "tm_dial": "data_tick", "tm_wave": "draw_zap", "tm_section": "bubble_pluck",
             "tm_grid": "data_tick", "tm_orbitmap": "marker_pop", "tm_phase": "draw_zap", "tm_mission": "data_tick"}
# a template's own entrance: by its id, else by its family
TEMPLATE_SFX = {"stage_header": "shimmer_riser", "mission_intro": "shimmer_riser", "statement": "deep_thud", "question_card": "deep_thud",
                "end_question": "final_chime", "recap_strip": "fast_whoosh", "dated_caption": "paper_slide", "quote_card": "paper_slide",
                "theories_split": "paper_slide", "big_number_lower": "counter_ticks", "bar_race": "counter_ticks", "odds_dial": "data_tick",
                "eht_pair": "camera_shutter", "before_after": "camera_shutter", "annotated_photo_rings": "marker_pop", "two_clocks_ratio": "clock_ticking",
                "hourglass_pair": "clock_ticking", "cosmic_calendar": "clock_ticking", "seconds_left": "clock_ticking", "info_letter": "boil_sizzle"}
FAMILY_SFX = {"story": "deep_thud", "scale": "counter_ticks", "distance": "directional_whoosh", "time": "clock_ticking", "physics": "draw_zap",
              "forces": "draw_zap", "structure": "bubble_pluck", "data": "data_tick", "space": "marker_pop", "survival": "deep_thud", "blackhole": "shimmer_riser"}
# a build inside a template (a line drawing, a number counting, a dot landing)
ITEM_SFX = {"path": "draw_zap", "line": "draw_zap", "arrow": "draw_zap", "axis": "draw_zap", "wave": "draw_zap", "ring": "marker_pop", "dot": "marker_pop",
            "number": "data_tick", "bar": "data_tick", "icon": "subtle_pop", "image": "camera_shutter", "callout": "marker_pop", "text": "ui_click",
            "donut": "counter_ticks", "disc": "bubble_pluck"}
MAJOR = ("deep_thud", "final_chime", "shimmer_riser", "fast_whoosh")
SAME_SOUND_GAP_S, MIN_GAP_S, MAX_PER_WINDOW, WINDOW_S = 0.6, 0.4, 8, 10.0
AMBIENCE = (("water_ambience", r"\b(water|rivers?|oceans?|lakes?|rain|seas?|flood\w*)\b"), ("desert_wind", r"\b(wind|dust|desert|sand|storms?|dunes?)\b"),
            ("cold_wind", r"\b(ice|icy|frozen|polar|glaciers?|snow|cold)\b"))


def _when(v, length: float, cues: Dict[str, float], fallback: float) -> float:
    """A template time (seconds, "40%", "end-1", "@word") -> seconds from the layer start (the engine's lib/tpl.mjs rule)."""
    import re

    if v is None or v == "":
        return fallback
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s.startswith("="):
        return fallback
    m = re.match(r"^(-?[\d.]+)%$", s)
    if m:
        return length * float(m.group(1)) / 100
    m = re.match(r"^end\s*([+-]\s*[\d.]+)?$", s)
    if m:
        return length + (float(m.group(1).replace(" ", "")) if m.group(1) else 0.0)
    m = re.match(r"^@([\w'-]+)\s*([+-]\s*[\d.]+)?$", s)
    if m:
        c = cues.get(m.group(1).lower())
        return fallback if c is None else c + (float(m.group(2).replace(" ", "")) if m.group(2) else 0.0)
    try:
        return float(s)
    except ValueError:
        return fallback


def _template_cues(L: Dict[str, Any]) -> List[Dict[str, Any]]:
    t = L.get("template") or {}
    t0, t1 = float(L.get("start", 0)), float(L.get("end", 0))
    length, cues = max(0.5, t1 - t0), L.get("cues") or {}
    first = TEMPLATE_SFX.get(t.get("id")) or FAMILY_SFX.get(t.get("family"), "ui_click")
    out = [{"t": t0 + 0.05, "sfx": first, "source": f"template {t.get('id')}"}]
    items = t.get("items") or []
    for k, it in enumerate(items):
        sfx = ITEM_SFX.get(it.get("p"))
        if not sfx or it.get("p") == "particles":
            continue
        if it.get("m") == "count":
            sfx = "counter_ticks"
        elif it.get("m") == "draw":
            sfx = "draw_zap"
        at = _when(it.get("in"), length, cues, _when(it.get("or"), length, cues, length * (0.12 + 0.6 * k / max(1, len(items)))))
        if 0.4 <= at < length - 0.2:
            out.append({"t": t0 + at, "sfx": sfx, "source": f"template {t.get('id')}: {it.get('p')} builds"})
    return out


def _ambience(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The bed follows the story: water where it talks about water, wind over dust and storms, cold over ice, the space drone otherwise
    (a section lasts at least 20 s, so the bed never flickers)."""
    import re

    marks: List[Dict[str, Any]] = []
    for s in spec.get("shots") or []:
        txt = " ".join(str(s.get(k, "")) for k in ("text", "title", "sub"))
        name = next((a for a, pat in AMBIENCE if re.search(pat, txt, re.I)), "space_drone")
        if not marks or (marks[-1]["ambience"] != name and float(s["start"]) - marks[-1]["t"] >= 20.0):
            marks.append({"t": 0.0 if not marks else float(s["start"]), "ambience": name})
    return marks or [{"t": 0.0, "ambience": "space_drone"}]


def sound_hints(spec: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Every graphic the viewer sees gets the sound of what it does (a line draws, a number counts, a title lands); a change of shot kind
    gets a soft transition; the bed follows the story. Restraint is applied here (the mixer plays these cues as given)."""
    cues: List[Dict[str, Any]] = []
    prev = None
    for s in spec.get("shots") or []:
        k = s.get("kind")
        if k == "plate":
            cues.append({"t": float(s["start"]), "sfx": "soft_transition", "source": "diagram plate"})
        elif k in ("globe", "craft", "hero") and prev != k:
            cues.append({"t": float(s["start"]), "sfx": "map_slide_whoosh", "source": f"{k} shot"})
        elif prev is not None and k != prev and k in ("image", "video"):
            cues.append({"t": float(s["start"]), "sfx": "soft_transition", "source": "a new kind of shot"})
        prev = k
    for L in spec.get("layers") or []:
        ty = L.get("type")
        if "start" not in L:
            continue
        if ty == "tm_template":
            cues += _template_cues(L)
            continue
        sfx = LAYER_SFX.get(ty)
        if sfx:
            cues.append({"t": float(L["start"]), "sfx": "deep_thud" if ty == "tm_metric" and L.get("size") == "hero" else sfx, "source": f"{ty} layer"})
        if ty == "tm_survival":
            cues += [{"t": float(x["t"]), "sfx": "ui_click", "source": "survival clock change"} for x in (L.get("states") or [])[1:]]
        if ty == "tm_mission":
            cues += [{"t": float(x["t"]), "sfx": "data_tick", "source": "mission card beat"} for x in (L.get("keys") or [])[1:]]
        if ty == "tm_timeline":
            cues += [{"t": float(x["t"]), "sfx": "marker_pop", "source": "timeline event"} for x in (L.get("events") or []) if "t" in x]
    kept: List[Dict[str, Any]] = []
    for c in sorted(cues, key=lambda c: (c["t"], 0 if c["sfx"] in MAJOR else 1)):
        if any(k["sfx"] == c["sfx"] and c["t"] - k["t"] < SAME_SOUND_GAP_S for k in kept[-6:]):
            continue
        if kept and c["t"] - kept[-1]["t"] < MIN_GAP_S and not (c["sfx"] in MAJOR and kept[-1]["sfx"] not in MAJOR):
            continue
        if kept and c["t"] - kept[-1]["t"] < MIN_GAP_S:
            kept.pop()                      # a major sound replaces a small one just before it
        if sum(1 for k in kept if c["t"] - k["t"] < WINDOW_S) >= MAX_PER_WINDOW and c["sfx"] not in MAJOR:
            continue
        kept.append(c)
    return {"cues": kept, "ambience": _ambience(spec)}


def plan_sound(spec: Dict[str, Any], *, enabled: bool = True, catalog: Any = None):
    from pakmap.audio_mix import resolve_assets
    from pakmap.audio_plan import plan_audio

    plan = plan_audio({"duration": spec.get("duration", 0)}, sound_hints(spec), enabled=enabled, duration=spec.get("duration"))
    return resolve_assets(plan, catalog)


# ---- loudness: the references are all normalised to -14 LUFS integrated, loudness range about 4 LU, true peak about -1.5 dBFS
TARGET_LUFS, TARGET_TP, TARGET_LRA = -14.0, -1.5, 4.0


def measure_loudness(path: Any, ffmpeg: str = "ffmpeg") -> Dict[str, float]:
    """Integrated loudness (LUFS), loudness range (LU) and true peak (dBFS) of an audio file."""
    import re
    import subprocess

    r = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    summ = r.stderr[r.stderr.rfind("Summary:"):]
    pick = lambda pat: float(re.search(pat, summ).group(1))  # noqa: E731
    return {"lufs": pick(r"I:\s+(-?[0-9.]+) LUFS"), "lra": pick(r"LRA:\s+([0-9.]+) LU"), "peak": pick(r"Peak:\s+(-?[0-9.]+) dBFS")}


def normalize_loudness(src: Any, dst: Any, ffmpeg: str = "ffmpeg", *, lufs: float = TARGET_LUFS, tp: float = TARGET_TP, lra: float = TARGET_LRA) -> Any:
    """The final audio at the references' loudness (two-pass loudnorm: measured, then applied linearly so the dynamics are kept). Returns
    dst; if anything fails the source is returned untouched, so a normalisation problem never stops a video."""
    import json
    import re
    import subprocess
    from pathlib import Path

    try:
        a = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(src), "-af", f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
        m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", a.stderr, re.S).group(0))
        flt = (f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
               f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        b = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-af", flt, "-ar", "48000", str(dst)], capture_output=True, text=True)
        if b.returncode != 0 or not Path(dst).is_file():
            return src
        return dst
    except Exception:
        return src
