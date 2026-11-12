"""The job file and its status file (plain JSON, so Claude, a script or a person can read them)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]

def _s(pick: str, csv: str, prompt: str, voice: str = "required", fields: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """pick: the style card's name in the app. csv/voice: required | optional. prompt: the file Claude follows to write the CSV.
    fields: the style page's own file fields (kind -> app attribute), filled as its Browse buttons would."""
    return {"pick": pick, "csv": csv, "csv_prompt": prompt, "voice": voice, "fields": fields or {}}


_RT = "reptheory/"
# command-line name -> the style. Every card of the app's style picker (ui/style_registry.py).
STYLES: Dict[str, Dict[str, Any]] = {
    "normal": _s("Normal video", "required", "composition_styles/normal_csv_prompt.txt"),
    "story-motion": _s("Story Motion", "required", "composition_styles/normal_csv_prompt.txt"),
    "modern-tech-news": _s("Modern Tech News", "required", "composition_styles/normal_csv_prompt.txt"),
    "overscaled": _s("Overscaled", "required", "composition_styles/overscaled_csv_prompt.txt"),
    "exp-solar": _s("Exp Solar", "required", "composition_styles/exp_solar_csv_prompt.txt"),
    "pakmap": _s("pakMap", "required", "composition_styles/pakmap_csv_prompt.txt"),
    "hybrid": _s("Hybrid Map", "required", "composition_styles/hybrid_csv_prompt.txt"),
    "explainer": _s("Explainer", "optional", "composition_styles/explainer_scene_csv_prompt.txt"),
    "voxel-map": _s("Voxel Map", "required", "voxelmap-engine/tools/story_prompt.md", fields={"csv": "_vm_csv_var", "voice": "_vm_voice_var"}),
    "city-timelapse": _s("City Timelapse", "required", "citygrow-engine/tools/story_prompt.md", voice="optional",
                         fields={"csv": "_ct_csv_var", "voice": "_ct_voice_var", "music": "_ct_music_var"}),
    "starmap": _s("StarMap", "required", "composition_styles/starmap_beats_prompt.txt"),
    "starmap-cinema": _s("StarMap Cinema", "required", "composition_styles/starmap_beats_prompt.txt"),
    "what-if": _s("What If", "required", "composition_styles/whatif_csv_prompt.txt"),
    "rep-theory": _s("Rep Theory", "optional", _RT + "scenes_csv_prompt.txt", fields={"csv": "_rt_scenes_var"}),
    "cat-theory": _s("Cat Theory", "optional", _RT + "cat_scenes_csv_prompt.txt", fields={"csv": "_rt_scenes_var"}),
    "carl-jung-theory": _s("Carl Jung Theory", "optional", _RT + "jung_scenes_csv_prompt.txt", fields={"csv": "_rt_scenes_var"}),
    "elder-health-theory": _s("Elder Health Theory", "optional", _RT + "elder_scenes_csv_prompt.txt", fields={"csv": "_rt_scenes_var"}),
    "survival": _s("Survival", "optional", _RT + "survival_scenes_csv_prompt.txt", fields={"csv": "_rt_scenes_var"}),
    "product-trailer": _s("Product Trailer", "required", "docs/product_trailer/CSV_prompt.txt", voice="optional",
                          fields={"csv": "_pt_csv_var", "voice": "_pt_voice_var", "music": "_pt_music_var"}),
    "war": _s("War Documentary", "optional", "cinematic_explainer/war/data/war_csv_prompt.txt", fields={"csv": "_war_scenes_var"}),
    "enoch-template": _s("Enoch Template", "required", "composition_styles/enoch_template_csv_prompt.txt"),
    "roblox-cinema": _s("Roblox Cinema", "optional", "roblox-cinema-engine/docs/story_prompt.md",
                        fields={"csv": "_rc_csv_var", "voice": "_rc_voice_var", "music": "_rc_music_var"}),
    "health-cinema": _s("Health Cinema", "optional", "composition_styles/health_cinema_csv_prompt.txt",
                        fields={"csv": "_health_scenes_var", "music": "_health_music_var"}),
    "weather": _s("Weather", "required", "weather/prompts/forecast_csv_prompt.txt"),
    "rules-horror": _s("Rules Horror", "required", "rules_horror/prompt.txt", fields={"csv": "_rh_csv_var", "voice": "_rh_voice_var"}),
    "kids-learn": _s("Kids Learn", "required", "cartoon3d-engine/samples/chant_lesson.csv", voice="optional",
                     fields={"csv": "_kl_csv_var", "voice": "_kl_voice_var", "music": "_kl_music_var"}),
    "aviation": _s("Aviation", "optional", "aviation/data/aviation_csv_prompt.txt", fields={"csv": "_av_csv_var", "voice": "_av_voice_var"}),
}
VOICE_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")


class JobError(ValueError):
    pass


def make_job(style: str, voice: str = "", script: str = "", csv: str = "", title: str = "", out: str = "", music: str = "") -> Dict[str, Any]:
    """A checked job (absolute paths). Raises JobError with a plain message."""
    style = (style or "").strip().lower().replace("_", "-").replace(" ", "-")
    if style not in STYLES:
        raise JobError(f"unknown style {style!r}; styles: {', '.join(STYLES)}")
    v = Path(voice).expanduser().resolve() if voice else None
    if v is None and STYLES[style]["voice"] == "required":
        raise JobError(f"the {style} style needs the voiceover (--voice)")
    if v is not None and (not v.is_file() or v.suffix.lower() not in VOICE_EXT):
        raise JobError(f"the voiceover must be an audio file ({', '.join(VOICE_EXT)}): {voice!r}")
    m = Path(music).expanduser().resolve() if music else None
    if m is not None and (not m.is_file() or m.suffix.lower() not in VOICE_EXT):
        raise JobError(f"the music must be an audio file: {music!r}")
    s = Path(script).expanduser().resolve() if script else None
    if s is not None and not s.is_file():
        raise JobError(f"script file not found: {script}")
    c = Path(csv).expanduser().resolve() if csv else None
    if c is not None and not c.is_file():
        raise JobError(f"CSV file not found: {csv}")
    if c is None and STYLES[style]["csv"] == "required":
        raise JobError(f"the {style} style needs a CSV (--csv); write it with: make_video.py prompt --style {style}")
    o = Path(out).expanduser().resolve() if out else None
    if o is not None and o.suffix.lower() != ".mp4":
        raise JobError("--out must end in .mp4")
    stem = (v or c or s or Path(style)).stem
    return {"style": style, "voice": str(v) if v else "", "script": str(s) if s else "", "csv": str(c) if c else "",
            "music": str(m) if m else "", "title": (title or stem)[:60], "out": str(o) if o else ""}


def read_job(path: "str | Path") -> Dict[str, Any]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return make_job(d.get("style", ""), d.get("voice", ""), d.get("script", ""), d.get("csv", ""), d.get("title", ""), d.get("out", ""), d.get("music", ""))


def status_path(job_path: "str | Path") -> Path:
    p = Path(job_path)
    return p.with_name(p.stem + ".status.json")


def log_path(job_path: "str | Path") -> Path:
    p = Path(job_path)
    return p.with_name(p.stem + ".log")


class Status:
    """state: starting | waiting_for_sign_in | running | done | failed. Written atomically on every change."""

    def __init__(self, job_path: "str | Path"):
        self.path = status_path(job_path)
        self.data: Dict[str, Any] = {"state": "starting", "step": "", "message": "", "video": "", "project": "", "questions": [], "errors": [], "started": time.time()}
        self.write()

    def set(self, **kw: Any) -> None:
        self.data.update(kw)
        self.write()

    def add(self, key: str, value: str) -> None:
        lst: List[str] = self.data.setdefault(key, [])
        lst.append(value)
        self.write()

    def write(self) -> None:
        self.data["updated"] = time.time()
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass


def read_status(job_path: "str | Path") -> Optional[Dict[str, Any]]:
    try:
        return json.loads(status_path(job_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
