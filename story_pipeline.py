"""Story pipeline: turns a static-image story video into a video made of per-SHOT clips, without editing video_generator.py.

    build_story(project_dir, settings, log, cancel, dry_run=True) -> StoryRun
        align (story_align) -> shots (shot_director) -> generation plan (story_character, dry run only)
        -> clip jobs / timeline (story_motion) -> audit (story_audit)
        Every step is cached under <project>/state/story/ keyed by its inputs (a re-run skips what did not change = resumable),
        cancellable between steps, and a missing module only turns its step into "skipped" - the pipeline never raises.
    applied_story(vg, run) -> context manager around vg.render_video: the render gets one synthetic row per timeline unit (shot or link clip), see "REMAP" below.
    StoryRun.report() -> human summary: what would be generated, counts, time estimates, risks.

Off unless settings["story_video"] is true (is_on(settings)). Nothing here calls a generator, the network or Whisper.

REMAP - what render_video keys by scene, and what is done when scenes become shots
  The render loops over aligned_rows; clip i = row i, window = [start_time_i, start_time_{i+1}) (row 0 starts at 0, last ends at audio_end).
  The unit of the new render is a "unit": one per timeline SEGMENT of story_motion.assemble_timeline (a shot's own clip, or a link clip between
  two shots), or one per shot when there is no timeline. A unit row is {scene_number: SHOT_BASE + index (integer, so find_image_for_scene's
  int() works and no real scene number can collide), script_segment: the shot's text (captions; a link unit keeps the text of the shot it leaves),
  start_time/end_time}. A segment that starts INSIDE its clip (clip_in > 0, the shot after a link) is played from a trimmed copy of the clip,
  because render_video always plays a clip from its first frame. Per input:
    aligned_rows            -> unit rows (build_units), tiled with no gaps: the first starts at 0, each starts where the last ends.
    find_image_for_scene    -> patched: synthetic number -> that shot's mp4 (or still); anything else -> the previous finder.
    scene_text_effects      -> list per row INDEX: re-sliced by absolute time (expand_text_effects), local_start/local_end rebased.
    transition_by_scene     -> dict by str(scene_number): scene's value goes to its FIRST shot; later shots get their own transition_in.
    camera_by_scene         -> dict by str(scene_number): every shot of a scene inherits it unless the shot names a camera.
    edit_decisions_by_scene -> dict by str(scene_number), times local to the scene: B-roll entries re-assigned by absolute time and rebased;
                               multi-shot / strategy decisions are dropped (the shots ARE the editing now); each clip shot gets HOLD_TAIL
                               so a clip shorter than its shot freezes its last frame instead of looping a walk cycle.
    editorial_timeline      -> time-native (graphics overlap-test by absolute time): works unchanged because shots tile 0..audio_end.
    .asset_manifest.json    -> coverage flags by real scene number: never match a synthetic number (no accidental avoid_blind_loop).
    render cache            -> keyed by synthetic number + clip content: a shot re-renders only when its clip, text or window changed.
  NOT remapped (still scene-based, and harmless): production graph / progress counts (clips_total), the Hybrid sound hook's per-scene starts
  and transition indexes (they are absolute times of the ORIGINAL scenes, which stay valid), Doc Style extras (take the shot rows).
"""
from __future__ import annotations

import contextlib
import copy
import csv
import hashlib
import inspect
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SETTING_KEY = "story_video"
SHOT_BASE = 100000
MAX_SHOT_S = 6.0
VERSION = 1

# B's transition names -> the styles render_video's transition_by_scene understands (None = hard cut)
TRANSITION_STYLE: Dict[str, Optional[str]] = {
    "": None, "cut": None, "hard_cut": None, "match_cut": None, "jump_cut": None,
    "dissolve": "dissolve", "crossfade": "dissolve", "cross_dissolve": "dissolve", "fade": "fade", "dip_black": "fade", "dip": "fade",
    "soft": "soft", "flash": "flash", "dip_white": "flash", "zoom_blur": "zoom_blur", "whip": "zoom_blur", "whip_pan": "zoom_blur",
}


def is_on(settings: Optional[dict]) -> bool:
    return bool((settings or {}).get(SETTING_KEY, False))


# =============================================================== remap helpers (pure functions, tested on fake data)

def synthetic_id(k: int) -> int:
    """Shot index k (0-based) -> the integer scene_number its row carries."""
    return SHOT_BASE + int(k) + 1


def is_synthetic(scene_number: Any) -> bool:
    try:
        return int(str(scene_number).strip()) > SHOT_BASE
    except (TypeError, ValueError):
        return False


def _num(d: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        try:
            if d.get(k) not in (None, ""):
                return float(d[k])
        except (TypeError, ValueError):
            pass
    return default


def tile_shots(shots: Sequence[dict], audio_end: float, min_len: float = 0.2) -> List[dict]:
    """Copies of the shots made contiguous: first starts at 0, each starts where the previous ended, the last ends at audio_end; a shot that would
    be shorter than min_len is merged into its neighbour. Shot order is kept; 'start'/'end' are set on the copies."""
    ordered = sorted((dict(s) for s in shots), key=lambda s: (_num(s, "start", "start_time"), str(s.get("shot_id", ""))))
    out: List[dict] = []
    for s in ordered:
        s["start"] = _num(s, "start", "start_time")
        s["end"] = _num(s, "end", "end_time", default=s["start"])
        if s["end"] - s["start"] < min_len and out:      # too short to be a clip: the previous shot absorbs it
            out[-1]["end"] = max(out[-1]["end"], s["end"])
            continue
        out.append(s)
    for i, s in enumerate(out):                           # contiguous: each shot starts where the previous one ended (order beats timing)
        s["start"] = 0.0 if i == 0 else out[i - 1]["end"]
        s["end"] = max(s["end"], s["start"] + 0.05)
    if out:
        out[-1]["end"] = max(float(audio_end), out[-1]["start"] + 0.05)
    return out


def _scene_of(d: dict) -> str:
    return str(d.get("scene_no", d.get("scene_number", ""))).strip()


def build_units(shots: Sequence[dict], timeline: Optional[dict], clips: Optional[Dict[str, str]], audio_end: float) -> List[dict]:
    """The render units, in order, contiguous from 0 to audio_end. From story_motion.assemble_timeline's segments when there is a timeline
    (shot segments and link segments), else one unit per (tiled) shot. A unit: {_ix, kind 'shot'|'link'|'graphic'|'gap', shot_id, scene_no,
    start, end, path (clip file or None), clip_in, text, prompt_en, transition_in, camera}."""
    shots = list(shots)
    by_id = {str(s.get("shot_id")): s for s in shots}
    clips = clips or {}
    units: List[dict] = []
    segs = (timeline or {}).get("segments") if isinstance(timeline, dict) else None
    if segs:
        for sg in segs:
            sid = str(sg.get("shot_id"))
            base = by_id.get(sid.split("+link")[0]) or {}
            kind = str(sg.get("kind") or "shot")
            prev_link = bool(units) and units[-1]["kind"] == "link"
            units.append({"kind": kind, "shot_id": sid, "scene_no": _scene_of(base), "start": float(sg["start"]), "end": float(sg["end"]),
                          "path": sg.get("path"), "clip_in": float(sg.get("clip_in") or 0.0), "text": base.get("text", ""),
                          "prompt_en": base.get("prompt_en", ""),
                          # a link IS the transition into the next shot: no extra dip there
                          "transition_in": None if (kind == "link" or prev_link) else base.get("transition_in"),
                          "camera": base.get("camera") if kind == "shot" else None})
    else:
        for sh in shots:
            units.append({"kind": "shot", "shot_id": str(sh.get("shot_id")), "scene_no": _scene_of(sh), "start": float(sh["start"]), "end": float(sh["end"]),
                          "path": clips.get(str(sh.get("shot_id"))), "clip_in": 0.0, "text": sh.get("text", ""), "prompt_en": sh.get("prompt_en", ""),
                          "transition_in": sh.get("transition_in"), "camera": sh.get("camera")})
    for i, u in enumerate(units):                         # contiguous from 0 to audio_end, whatever rounding the timeline did
        u["start"] = 0.0 if i == 0 else units[i - 1]["end"]
        u["end"] = max(u["end"], u["start"] + 0.05)
        u["_ix"] = i
    if units:
        units[-1]["end"] = max(float(audio_end), units[-1]["start"] + 0.05)
    return units


def shot_rows(units: Sequence[dict], scenes: Sequence[dict]) -> List[dict]:
    """The synthetic aligned rows render_video gets: one per unit."""
    by_no = {str(sc.get("scene_number")).strip(): sc for sc in scenes}
    rows = []
    for u in units:
        parent = by_no.get(_scene_of(u), {})
        text = str(u.get("text") or "").strip() or str(parent.get("script_segment") or "")
        rows.append({"scene_number": str(synthetic_id(u["_ix"])), "script_segment": text, "prompt": u.get("prompt_en") or parent.get("prompt", ""),
                     "start_time": float(u["start"]), "end_time": float(u["end"]), "confidence": 1.0,
                     "_shot_id": u.get("shot_id"), "_parent_scene": _scene_of(u) or str(parent.get("scene_number", ""))})
    return rows


def _first_unit_of_scene(units: Sequence[dict]) -> Dict[int, str]:
    seen: Dict[str, int] = {}
    for u in units:
        if u.get("kind") == "link":
            continue
        seen.setdefault(_scene_of(u), u["_ix"])
    return {k: sc for sc, k in seen.items()}      # unit index -> scene number, for the first (non-link) unit of each scene


def _style_of(name: Any) -> Optional[str]:
    n = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return TRANSITION_STYLE.get(n, None)


def expand_transitions(by_scene: Optional[dict], units: Sequence[dict]) -> Dict[str, str]:
    """transition_by_scene {str(scene_no): style} -> {str(synthetic): style}. The scene's style goes to the first unit of the scene (the cut INTO the
    scene); every other unit uses its own transition_in (B decides how its shots join; a link unit and the unit after it have none, the link is the
    transition). A boundary with no style is a hard cut."""
    first = _first_unit_of_scene(units)
    out: Dict[str, str] = {}
    for u in units:
        k = u["_ix"]
        style = (by_scene or {}).get(first[k]) if k in first else None
        style = style or _style_of(u.get("transition_in"))
        if style:
            out[str(synthetic_id(k))] = style
    return out


def expand_camera(by_scene: Optional[dict], units: Sequence[dict]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for u in units:
        cam = u.get("camera") or (None if u.get("kind") == "link" else (by_scene or {}).get(_scene_of(u)))
        if cam:
            out[str(synthetic_id(u["_ix"]))] = str(cam)
    return out


def expand_text_effects(per_row: Optional[Sequence[Sequence[dict]]], old_windows: Sequence[Tuple[float, float]],
                        units: Sequence[dict]) -> List[List[dict]]:
    """scene_text_effects (one list per OLD row, times local to the scene) -> one list per unit. An effect belongs to the unit that contains its
    start; its local times are rebased to that unit and cut at the unit's end. Absolute times come from fx['start'/'end'] when the effect has
    them (smart_editing's do), else old window start + local time."""
    out: List[List[dict]] = [[] for _ in units]
    if not per_row:
        return out
    for i, fxs in enumerate(per_row):
        w0 = old_windows[i][0] if i < len(old_windows) else 0.0
        for fx in fxs or []:
            a = _num(fx, "start", default=w0 + _num(fx, "local_start"))
            b = _num(fx, "end", default=w0 + _num(fx, "local_end", default=_num(fx, "local_start") + 0.3))
            for u in units:
                if u["start"] - 1e-6 <= a < u["end"] - 1e-6 or (u is units[-1] and a >= u["end"]):
                    f2 = dict(fx)
                    f2["local_start"] = max(0.0, a - u["start"])
                    f2["local_end"] = max(f2["local_start"] + 0.08, min(b, u["end"]) - u["start"])
                    f2["scene_duration"] = u["end"] - u["start"]
                    f2["scene_number"] = str(synthetic_id(u["_ix"]))
                    out[u["_ix"]].append(f2)
                    break
    return out


def expand_edit_decisions(by_scene: Optional[dict], old_windows: Dict[str, Tuple[float, float]], units: Sequence[dict],
                          clip_units: Sequence[int] = ()) -> Dict[str, dict]:
    """edit_decisions_by_scene -> per unit. B-roll overlays (scene-local times) go to the unit they start in, rebased. Units that play a clip
    get {"strategy": "HOLD_TAIL"} (freeze the last frame rather than loop). Multi-shot decisions of the old scene are dropped."""
    out: Dict[str, dict] = {}
    cu = set(clip_units)
    for u in units:
        if u["_ix"] in cu:
            out[str(synthetic_id(u["_ix"]))] = {"strategy": "HOLD_TAIL", "avoid_blind_loop": True}
    for sc, rec in (by_scene or {}).items():
        if not isinstance(rec, dict) or not rec.get("broll"):
            continue
        w0 = old_windows.get(str(sc).lstrip("0") or str(sc), old_windows.get(str(sc), (0.0, 0.0)))[0]
        for b in rec["broll"]:
            a = w0 + float(b.get("overlay_start") or 0.0)
            ln = float(b.get("overlay_duration") or 0.0)
            for u in units:
                if u["start"] <= a < u["end"]:
                    nb = dict(b)
                    nb["overlay_start"] = a - u["start"]
                    nb["overlay_duration"] = max(0.0, min(ln, u["end"] - a))
                    out.setdefault(str(synthetic_id(u["_ix"])), {}).setdefault("broll", []).append(nb)
                    break
    return out


def trim_clip(src: "str | Path", clip_in: float, dur: float, out: "str | Path") -> Optional[Path]:
    """A copy of src from clip_in on (re-encoded, near-lossless), for a unit that starts inside its clip. None if ffmpeg fails."""
    import subprocess
    out = Path(out)
    if out.is_file() and out.stat().st_size > 0:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", f"{clip_in:.4f}", "-i", str(src), "-t", f"{dur + 0.1:.3f}", "-an", "-c:v", "libx264",
                        "-crf", "12", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)], capture_output=True, timeout=600)
    return out if r.returncode == 0 and out.is_file() else None


# =============================================================== the run record

@dataclass
class Step:
    name: str
    status: str = "pending"        # done | cached | skipped | failed | cancelled | pending
    note: str = ""
    seconds: float = 0.0


@dataclass
class StoryRun:
    project_dir: Path
    settings: dict
    dry_run: bool = True
    steps: Dict[str, Step] = field(default_factory=dict)
    rows: List[dict] = field(default_factory=list)
    words: List[list] = field(default_factory=list)
    aligned: List[dict] = field(default_factory=list)
    audio_end: float = 0.0
    align_report: dict = field(default_factory=dict)
    plan: dict = field(default_factory=dict)            # shot_director plan (shots tiled to 0..audio_end)
    gen_plan: dict = field(default_factory=dict)        # story_character.plan_generation (dry run)
    images: Dict[str, str] = field(default_factory=dict)   # {scene_no | shot_id: still path} given to story_motion
    clip_plan: Any = None                                # story_motion.plan_clips jobs
    clips: Dict[str, str] = field(default_factory=dict)  # {shot_id | "<shot_id>+link": mp4}, only after a live run
    timeline: Optional[dict] = None                      # story_motion.assemble_timeline result, only after a live run
    audit: dict = field(default_factory=dict)
    risks: List[str] = field(default_factory=list)
    cancelled: bool = False
    state_dir: Optional[Path] = None
    timer: Any = None                                    # story_fast.progress.StageTimer when the fast engine runs
    ai_video_report: dict = field(default_factory=dict)  # story_fast.animate dry-run / live report (empty when no shot was flagged)

    @property
    def shots(self) -> List[dict]:
        return self.plan.get("shots") or []

    def units(self, audio_end: Optional[float] = None) -> List[dict]:
        return build_units(self.shots, self.timeline, self.clips, float(audio_end if audio_end is not None else self.audio_end))

    def usable(self) -> bool:
        """True when applied_story has something to do: more shots than scenes, or any clip."""
        return bool(self.shots) and (len(self.shots) > len(self.aligned) or bool(self.clips))

    def report(self) -> str:
        sh = self.shots
        lines = [f"STORY RUN  {self.project_dir.name}  ({'DRY RUN - nothing generated or rendered' if self.dry_run else 'LIVE - local clips rendered, nothing sent to Flow'})"]
        for st in self.steps.values():
            lines.append(f"  {st.name:<10} {st.status:<9} {st.note}" + (f"  ({st.seconds:.1f}s)" if st.seconds >= 0.05 else ""))
        if sh:
            lens = [s["end"] - s["start"] for s in sh]
            tiers: Dict[str, int] = {}
            for s in sh:
                tiers[str(s.get("motion_tier", "?"))] = tiers.get(str(s.get("motion_tier", "?")), 0) + 1
            lines.append(f"  shots: {len(sh)} over {len(self.aligned)} scenes, avg {sum(lens) / len(lens):.1f}s, longest {max(lens):.1f}s, tiers {tiers}")
        est = self.estimates()
        if est:
            lines.append("  would generate: " + ", ".join(f"{k} {v}" for k, v in est.items()))
        if self.audit.get("checks"):
            lines.append("  plan audit: " + "; ".join(f"{c['check']} {'ok' if c['ok'] else 'FAIL'}" for c in self.audit["checks"]))
        if self.risks:
            lines.append("  risks:")
            lines += [f"    - {r}" for r in self.risks]
        return "\n".join(lines)

    def estimates(self) -> Dict[str, Any]:
        """Counts and time estimates read from the modules' own plans (story_character's counts, story_motion's jobs and est_seconds)."""
        est: Dict[str, Any] = {}
        c = (self.gen_plan or {}).get("counts") or {}
        for key, label in (("images", "new pictures (Flow, free)"), ("reference_images", "character references"), ("flow_runs", "Flow runs"),
                           ("agent_requests", "agent requests"), ("deferred", "pictures over budget")):
            if c.get(key):
                est[label] = c[key]
        jobs = [j for j in (self.clip_plan or []) if isinstance(j, dict)]
        if jobs:
            kinds: Dict[str, int] = {}
            for j in jobs:
                kinds[j.get("type", "?")] = kinds.get(j.get("type", "?"), 0) + 1
            est["clip jobs"] = {k: v for k, v in sorted(kinds.items())}
            secs = sum(float(j.get("est_seconds") or 0.0) for j in jobs)
            est["local render time (story_motion's estimate)"] = f"{secs / 60:.1f} min"
            ai = [j for j in jobs if j.get("type") == "ai_video_job"]
            if ai:
                est["AI video jobs (credits, NOT run here)"] = f"{len(ai)} for {sum(float(j.get('seconds') or 0) for j in ai):.0f}s"
            if self.ai_video_report.get("text"):
                est["AI video (story_ai_video_live)"] = self.ai_video_report["text"] if not self.ai_video_report.get("live") else (
                    f"live: {self.ai_video_report.get('animated', 0)} animated, {self.ai_video_report.get('cached', 0)} cached, {self.ai_video_report.get('failed', 0)} fell back to the camera clip")
        return est


# =============================================================== inputs and caching

def _sha(*parts: Any) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def _module_stamp(*names: str) -> List[str]:
    """Cache key part: each optional module's file size+mtime (a changed module invalidates what it produced). Missing -> 'absent'."""
    import importlib.util
    out = []
    for n in names:
        try:
            spec = importlib.util.find_spec(n)
            p = Path(spec.origin) if spec and spec.origin else None
            out.append(f"{n}:{p.stat().st_size}:{int(p.stat().st_mtime)}" if p and p.is_file() else f"{n}:absent")
        except Exception:       # noqa: BLE001
            out.append(f"{n}:absent")
    return out


def _load_cache(state_dir: Path, name: str, key: str) -> Optional[Any]:
    p = state_dir / f"{name}.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("key") == key and d.get("version") == VERSION:
            return d.get("data")
    except (OSError, ValueError):
        pass
    return None


def _save_cache(state_dir: Path, name: str, key: str, data: Any) -> None:
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        tmp = state_dir / f"{name}.json.tmp"
        tmp.write_text(json.dumps({"key": key, "version": VERSION, "data": data}, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(state_dir / f"{name}.json")
    except OSError:
        pass


def _call(fn: Callable, *args: Any, **kw: Any) -> Any:
    """Calls fn with the positional args and only those keyword args its signature accepts (modules written in parallel agree on the core
    arguments, optional ones are offered and dropped when unknown)."""
    try:
        params = inspect.signature(fn).parameters
        if not any(p.kind == p.VAR_KEYWORD for p in params.values()):
            kw = {k: v for k, v in kw.items() if k in params}
    except (TypeError, ValueError):
        pass
    return fn(*args, **kw)


def _import(name: str):
    import importlib
    try:
        return importlib.import_module(name)
    except Exception:       # noqa: BLE001
        return None


def read_rows(csv_path: Path) -> List[dict]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _find_inputs(project: Path, settings: dict) -> Tuple[Optional[Path], Optional[Path], Optional[Path], Optional[Path]]:
    csv_p = Path(settings["csv_path"]) if settings.get("csv_path") else next(iter(sorted((project / "csv").glob("*.csv"))), None)
    imgs = Path(settings["images_dir"]) if settings.get("images_dir") else next((project / n for n in ("assets", "Images", "images") if (project / n).is_dir()), None)
    audio = Path(settings["audio_path"]) if settings.get("audio_path") else next(iter(sorted(p for p in (project / "audio").glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".flac"))), None)
    timing = Path(settings["timing_json"]) if settings.get("timing_json") else None
    return csv_p, imgs, audio, timing


def _load_words(project: Path, settings: dict, audio: Optional[Path], timing: Optional[Path], log: Callable[[str], None]) -> Tuple[List[list], float]:
    """Whisper words from settings, a timing json, or the app's cache (never runs Whisper)."""
    if settings.get("words"):
        w = [list(x) for x in settings["words"]]
        return w, float(settings.get("audio_end") or w[-1][2])
    if timing and timing.is_file():
        d = json.loads(timing.read_text(encoding="utf-8"))
        return [list(x) for x in d.get("words", [])], float(d.get("audio_end") or (d["words"][-1][2] if d.get("words") else 0.0))
    if audio is not None:
        try:
            from smart_editing import get_cached_whisper_words
            w = get_cached_whisper_words(project / "state", audio)
            if w:
                return [list(x) for x in w], float(w[-1][2])
        except Exception as exc:        # noqa: BLE001
            log(f"[STORY] no cached transcript ({exc})")
    return [], 0.0


# =============================================================== build_story

def _scene_images(vg: Any, images_dir: Optional[Path], aligned: Sequence[dict]) -> Dict[str, str]:
    """{str(scene_no): still path} for the scenes whose picture is an image file (a scene whose media is a video is left out: it plays as it is)."""
    out: Dict[str, str] = {}
    if images_dir is None or not Path(images_dir).is_dir():
        return out
    index = vg.build_scene_media_index(Path(images_dir))
    for r in aligned:
        try:
            p = vg.find_image_for_scene(Path(images_dir), r["scene_number"], ext_cache=index)
        except Exception:       # noqa: BLE001
            p = None
        if p is not None and not vg.is_video_file(p):
            out[str(r["scene_number"]).strip()] = str(p)
    return out


def _generated_pictures(sd: Path, settings: dict, shots: Sequence[dict]) -> Dict[str, str]:
    """Pictures already made for 'new' shots: settings['story_pictures'] {shot_id: path} or <state>/story/pictures/<shot_id>.<ext>."""
    out: Dict[str, str] = {str(k): str(v) for k, v in (settings.get("story_pictures") or {}).items() if Path(str(v)).is_file()}
    # <state>/story/picture_map.json {shot_id: scene_number} (from story_flow_csv.export): the Flow images live in images_dir as <scene_number>.<ext>
    try:
        mp = json.loads((sd / "picture_map.json").read_text(encoding="utf-8")); idir = Path(str(settings.get("images_dir") or ""))
        for sid, num in mp.items():
            if sid in out or not idir.is_dir(): continue
            for stem in (str(num), str(num).zfill(3), str(num).zfill(4)):
                hit = next((q for ext in (".png", ".jpg", ".jpeg", ".webp") for q in (idir / f"{stem}{ext}",) if q.is_file()), None)
                if hit: out[sid] = str(hit); break
    except Exception:
        pass
    for s in shots:
        sid = str(s.get("shot_id"))
        if sid in out:
            continue
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = sd / "pictures" / f"{sid}{ext}"
            if p.is_file():
                out[sid] = str(p)
                break
    return out


def _fast_engine(settings: dict) -> bool:
    """Story Motion's engine: 'fast' (story_fast: directed treatments, ffmpeg compositor, resumable runner; the default) or 'classic' (story_motion + per-frame python)."""
    return str((settings or {}).get("story_engine") or "fast").lower() != "classic"


def _motion_settings(settings: dict) -> dict:
    st = {k[len("story_motion_"):]: v for k, v in settings.items() if k.startswith("story_motion_")}
    try:
        w, h = (int(x) for x in str(settings.get("resolution") or "1920x1080").lower().split("x"))
        st.setdefault("size", (w, h))
    except ValueError:
        pass
    st.setdefault("fps", int(settings.get("fps") or 30))
    return st


def _project_grade(run, sd: Path, settings: dict, mset: dict, log) -> None:
    """One colour grade per project, measured once from the pictures and cached in state/story/grade.json (re-measured only when the pictures change)."""
    if str(settings.get("story_grade", "on")).lower() in ("off", "false", "0", "no"):
        return
    try:
        from story_fast import grade as G
        files = sorted({str(p) for p in (run.images or {}).values() if p and Path(str(p)).is_file()})
        if not files:
            return
        sig = _sha([(f, Path(f).stat().st_size, int(Path(f).stat().st_mtime)) for f in files], "grade-1")
        gp = sd / "grade.json"
        g = G.load(str(gp))
        if g is None or _read_sig(gp) != sig:
            g = G.compute_project_grade(files)
            sd.mkdir(parents=True, exist_ok=True)
            d = g.to_dict(); d["sig"] = sig
            gp.write_text(json.dumps(d, indent=1), encoding="utf-8")
            log(f"[STORY] project grade measured from {g.stills} pictures")
        mset["grade_path"] = str(gp); mset["grade_sig"] = sig
    except Exception as exc:        # noqa: BLE001
        log(f"[STORY] project grade skipped: {exc}")


def _read_sig(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("sig")
    except (OSError, ValueError):
        return None


def build_story(project_dir: "str | Path", settings: Optional[dict] = None, log: Callable[[str], None] = print,
                cancel: Optional[Callable[[], bool]] = None, dry_run: bool = True) -> StoryRun:
    """Runs the phases in order. Never raises: a failing or missing step is recorded on the run (step status + risks) and the later steps that
    can still work run on what exists. dry_run=True never renders a clip: clip jobs are only PLANNED. dry_run=False renders the LOCAL motion and
    link clips (CPU, free). Pictures (Flow) and AI video are never generated here, in either mode: they are only planned.

    settings read: words / audio_end / rows / aligned (hand the app's own results in), csv_path / images_dir / audio_path / timing_json (else found
    in the project folder), resolution, fps, story_budget {"max_images": N}, story_pictures {shot_id: path}, story_* (passed to shot_director),
    story_motion_* (passed to story_motion as size/fps/seed/intensity/link_seconds/...), story_workers."""
    settings = dict(settings or {})
    project = Path(project_dir)
    run = StoryRun(project_dir=project, settings=settings, dry_run=bool(dry_run), state_dir=project / "state" / "story")
    sd = run.state_dir
    if _fast_engine(settings):
        try:
            from story_fast.progress import StageTimer
            run.timer = StageTimer()
        except Exception:   # noqa: BLE001
            run.timer = None
    csv_p, imgs, audio, timing = _find_inputs(project, settings)
    cancelled = lambda: bool(cancel and cancel())       # noqa: E731

    def step(name: str, fn: Callable[[], Tuple[str, str]]) -> bool:
        """Runs one step; returns False to stop the pipeline (cancelled)."""
        st = run.steps[name] = Step(name)
        if cancelled():
            st.status = "cancelled"
            run.cancelled = True
            return False
        t0 = time.time()
        try:
            st.status, st.note = fn()
        except Exception as exc:        # noqa: BLE001
            if type(exc).__name__ == "Cancelled":       # story_motion.Cancelled / motion.Cancelled
                st.status, st.note, run.cancelled = "cancelled", "stopped by the user (finished clips stay cached)", True
                return False
            st.status, st.note = "failed", f"{type(exc).__name__}: {exc}"
            run.risks.append(f"{name} failed: {exc}")
            log(f"[STORY] {name} failed: {exc}")
        st.seconds = time.time() - t0
        if run.timer is not None and name in ("inputs", "align", "shots", "direct"):
            run.timer.add("csv", st.seconds, 0)      # CSV processing = reading, aligning to the narration, shot plan and direction (local, no Flow)
        return True

    # ---- inputs
    def s_inputs():
        if settings.get("rows"):
            run.rows = [dict(r) for r in settings["rows"]]
        elif csv_p is None or not csv_p.is_file():
            raise FileNotFoundError("no scene CSV (csv/*.csv)")
        else:
            run.rows = read_rows(csv_p)
        run.words, run.audio_end = _load_words(project, settings, audio, timing, log)
        if not run.words:
            run.risks.append("no transcript words available (run the normal Generate once so Whisper's words are cached, or pass settings['words'])")
            return "skipped", "no Whisper words cached - nothing can be aligned without a transcript"
        return "done", f"{len(run.rows)} scenes, {len(run.words)} words, {run.audio_end:.1f}s"
    if not step("inputs", s_inputs):
        return run
    if not run.words:
        return _finish(run, log)

    # ---- A: align
    def s_align():
        if settings.get("aligned"):          # the app already aligned (possibly through story_align.applied): use exactly that, so shots and render agree
            run.aligned = [dict(r) for r in settings["aligned"]]
            run.audio_end = float(settings.get("audio_end") or run.audio_end)
            return "done", f"{len(run.aligned)} scenes as the app aligned them"
        key = _sha(run.rows, run.words, _module_stamp("story_align"))
        hit = _load_cache(sd, "align", key)
        if hit:
            run.aligned, run.audio_end, run.align_report = hit["aligned"], hit["audio_end"], hit["report"]
            return "cached", f"{len(run.aligned)} scenes"
        mod = _import("story_align")
        if mod is not None and hasattr(mod, "align_story"):
            import video_generator as vg
            res = _call(mod.align_story, run.rows, run.words, log=log, fallback=vg.align_rows)
            run.aligned, run.audio_end, run.align_report = res
            note = "story_align"
        else:
            import video_generator as vg
            run.aligned, run.audio_end = vg.align_rows(run.rows, [tuple(w) for w in run.words])
            note = "story_align missing -> the app's own align_rows"
            run.risks.append("story_align not available: scene windows are the app's default alignment")
        run.aligned = [dict(r) for r in run.aligned]
        _save_cache(sd, "align", key, {"aligned": run.aligned, "audio_end": run.audio_end, "report": run.align_report})
        return "done", note
    if not step("align", s_align):
        return run
    if not run.aligned:
        return _finish(run, log)

    # ---- B: shots
    def s_shots():
        scenes = [{"scene_no": int(str(r.get("scene_number")).strip()), "scene_number": str(r.get("scene_number")).strip(),
                   "script_segment": r.get("script_segment", ""), "text": r.get("script_segment", ""), "prompt": r.get("prompt", ""),
                   "start": _num(r, "start_time", "start"), "end": _num(r, "end_time", "end")} for r in run.aligned]
        key = _sha(scenes, run.words, {k: v for k, v in settings.items() if k.startswith("story_") and k not in ("story_video", "story_dry_run", "story_pictures", "story_budget")},
                   _module_stamp("shot_director"))
        hit = _load_cache(sd, "shots", key)
        if hit:
            run.plan = hit
            return "cached", f"{len(run.shots)} shots"
        mod = _import("shot_director")
        if mod is not None and hasattr(mod, "plan_shots"):
            plan = _call(mod.plan_shots, scenes, run.words, {k[len("story_"):]: v for k, v in settings.items() if k.startswith("story_shot_")}, log)
            note = "shot_director"
        else:
            plan = {"protagonist": {}, "stats": {}, "shots": [
                {"shot_id": f"{sc['scene_no']:03d}a", "scene_no": sc["scene_no"], "start": sc["start"], "end": sc["end"], "text": sc["text"],
                 "motion_tier": "still_motion", "transition_in": "cut", "character": False} for sc in scenes]}
            note = "shot_director missing -> one shot per scene (the render stays as it is)"
            run.risks.append("shot_director not available: no shot splitting")
        plan = dict(plan)
        plan["shots"] = tile_shots(plan.get("shots") or [], run.audio_end)
        run.plan = plan
        _save_cache(sd, "shots", key, plan)
        return "done", note
    if not step("shots", s_shots):
        return run

    # ---- B2: visual direction (story_fast): per shot treatment, environment, transition and continuity; the old motion engine keeps shot_director's own choices
    def s_direct():
        if not _fast_engine(settings):
            return "skipped", "story_engine is 'classic'"
        mod = _import("story_fast.direct")
        if mod is None or not hasattr(mod, "direct"):
            return "skipped", "story_fast.direct missing - the runner rotates simple treatments"
        key = _sha([(s.get("shot_id"), s.get("start"), s.get("end"), s.get("text"), s.get("prompt_en")) for s in run.shots],
                   {k: v for k, v in settings.items() if k.startswith("story_ai_video") or k == "story_seed"}, _module_stamp("story_fast.direct"))
        hit = _load_cache(sd, "direct", key)
        if hit:
            run.plan["shots"] = hit["shots"]
            run.plan["bible"] = hit.get("bible", {})
            return "cached", f"{len(run.shots)} shots directed"
        try:        # stretches of the same or near-identical picture (the director reframes them instead of repeating one move)
            from story_fast import similar
            import video_generator as _vg0
            run.plan["shots"] = similar.annotate(run.shots, _scene_images(_vg0, imgs, run.aligned))
        except Exception as exc:        # noqa: BLE001
            log(f"[STORY] picture-repeat check skipped ({exc})")
        res = _call(mod.direct, run.shots, {k: v for k, v in settings.items() if k.startswith("story_")}, int(settings.get("story_seed") or 0))
        run.plan["shots"] = res["shots"]
        run.plan["bible"] = res.get("bible", {})
        run.plan["direction_stats"] = res.get("stats", {})
        _save_cache(sd, "direct", key, {"shots": run.plan["shots"], "bible": run.plan["bible"]})
        return "done", f"{len(run.shots)} shots directed: {res.get('stats', {}).get('summary', '')}".strip()
    if _fast_engine(settings):
        step("direct", s_direct)

    import video_generator as _vg
    run.images = _scene_images(_vg, imgs, run.aligned)
    made = _generated_pictures(sd, settings, run.shots)
    run.images.update(made)
    new_total = sum(1 for s in run.shots if s.get("picture") == "new")
    if new_total and len(made) < new_total and not _fast_engine(settings):
        run.risks.append(f"{new_total - len(made)} of {new_total} 'new' pictures do not exist yet: those shots show their scene's picture until the pictures are made")

    # ---- C: generation plan (never generates, in either mode)
    def s_gen():
        if _fast_engine(settings):
            return "skipped", "pictures come from your CSV (Flow); the director reframes them, so no extra pictures are planned"
        key = _sha([(s.get("shot_id"), s.get("picture"), s.get("character"), s.get("prompt_en")) for s in run.shots], run.plan.get("protagonist"),
                   settings.get("story_budget"), sorted(made), _module_stamp("story_character"))
        hit = _load_cache(sd, "gen_plan", key)
        if hit is not None:
            run.gen_plan = hit
            return "cached", "dry-run plan"
        mod = _import("story_character")
        if mod is None or not hasattr(mod, "plan_generation"):
            return "skipped", "story_character missing - pictures stay as they are"
        prot = run.plan.get("protagonist")
        run.gen_plan = _call(mod.plan_generation, run.shots, prot if isinstance(prot, dict) else None, settings.get("story_budget"),
                             done_shot_ids=sorted(made)) or {}
        _save_cache(sd, "gen_plan", key, run.gen_plan)
        c = run.gen_plan.get("counts") or {}
        return "done", f"dry-run plan: {c.get('images', '?')} pictures, nothing generated"
    if not step("generate", s_gen):
        return run

    # ---- D: clip jobs, then (live only) the local clips and the timeline
    def s_clips():
        fast = _fast_engine(settings)
        mset = _motion_settings(settings)
        if fast:
            _project_grade(run, sd, settings, mset, log)
        stamps = ("story_fast.runner", "story_fast.compose", "story_fast.direct") if fast else ("story_motion", "health_cinema.puppet.links", "health_cinema.puppet.motion")
        key = _sha([(s.get("shot_id"), s["start"], s["end"], s.get("motion_tier"), s.get("camera"), s.get("transition_in"), s.get("link_to_next"), s.get("treatment"),
                     s.get("tparams"), s.get("env")) for s in run.shots], sorted(run.images.items()), mset, dry_run, fast, _module_stamp(*stamps),
                    *(["ai-live", settings.get("story_ai_video_max"), settings.get("story_ai_video_live_max")] if settings.get("story_ai_video_live") else []))
        hit = _load_cache(sd, "clips", key)
        if hit is not None and (dry_run or hit.get("timeline")):
            run.clip_plan, run.clips, run.timeline = hit.get("plan"), hit.get("clips", {}), hit.get("timeline")
            run.ai_video_report = hit.get("ai_video_report") or {}
            files_ok = all(Path(p).is_file() for p in run.clips.values())
            if files_ok:
                return "cached", f"{len(run.clips)} clips" if run.clips else "clip jobs (cached)"
            run.clips, run.timeline = {}, None
        mod = (_import("story_fast.runner") if fast else None) or _import("story_motion") or _import("health_cinema.puppet.story_motion")
        if mod is None or not hasattr(mod, "plan_clips"):
            return "skipped", "story_motion missing - no clip jobs"
        run.clip_plan = _call(mod.plan_clips, run.shots, run.images, mset)
        if fast:
            run.ai_video_report = _ai_video_report(run.clip_plan, settings)
        if dry_run or not hasattr(mod, "render_clips"):
            _save_cache(sd, "clips", key, {"plan": run.clip_plan, "clips": {}, "timeline": None, "ai_video_report": run.ai_video_report})
            return "done", f"{len(run.clip_plan)} clip jobs planned (nothing rendered)"
        kw = {}
        if fast:
            kw = dict(progress=settings.get("story_progress"), state_path=str(sd / "fast_state.json"))
            if run.timer is not None and hasattr(mod, "set_timer"):
                mod.set_timer(run.timer)
        workers = int(settings.get("story_workers") or (4 if fast else 1))
        run.clips = _clips_map(_call(mod.render_clips, run.clip_plan, sd / "clips", log=lambda *a, **k: log("[STORY] " + " ".join(str(x) for x in a)),
                                     cancel=cancel, workers=workers, **kw))
        if fast:
            run.clips = _animate_clips(run, sd / "clips", settings, cancel, log)
        if hasattr(mod, "assemble_timeline"):
            run.timeline = mod.assemble_timeline(run.shots, run.clips, mset)
        _save_cache(sd, "clips", key, {"plan": run.clip_plan, "clips": run.clips, "timeline": run.timeline, "ai_video_report": run.ai_video_report})
        return "done", f"{len(run.clips)} clips rendered ({'story_fast' if fast else 'classic'}), timeline {len((run.timeline or {}).get('segments', []))} segments"
    if not step("clips", s_clips):
        return run

    # ---- audit of the plan (and of the timeline when there is one)
    def s_audit():
        import story_audit
        run.audit = story_audit.audit_all(None, plan=run.plan, aligned=run.aligned, words=run.words, print_fn=None)
        failed = [c["check"] for c in run.audit["checks"] if not c["ok"]]
        if failed:
            run.risks.append("plan audit: " + ", ".join(failed))
        return "done", "pass" if run.audit.get("ok") else f"FAIL: {', '.join(failed)}"
    step("audit", s_audit)
    return _finish(run, log)


def _ai_video_report(plan: Any, settings: dict) -> dict:
    """Dry-run numbers for the flagged ai_video shots ("would animate N shots, ~S seconds"); {} when none were flagged. Sends nothing."""
    try:
        from story_fast import animate
        rep = animate.dry_run_report([j for j in (plan or []) if isinstance(j, dict)], settings)
        return rep if rep.get("candidates") else {}
    except Exception:
        return {}


def _animate_clips(run: "StoryRun", clip_dir: Path, settings: dict, cancel: Any, log: Any) -> Dict[str, str]:
    """After the local clips exist: with story_ai_video_live, real image-to-video for the selected shots (failures keep the local clip); otherwise only
    ai_video_jobs.json is completed and the dry-run report kept. Never raises."""
    try:
        from story_fast import animate
        jobs = [j for j in (run.clip_plan or []) if isinstance(j, dict)]
        if not any(j.get("type") == "ai_video_job" for j in jobs):
            return run.clips
        out = animate.animate_jobs(jobs, run.clips, str(clip_dir), settings, log=lambda *a, **k: log(" ".join(str(x) for x in a)), cancel=cancel)
        run.ai_video_report = out["report"]
        if out["report"].get("cancelled"):
            run.cancelled = True
        if out["report"].get("failed"):
            run.risks.append(f"ai video: {out['report']['failed']} shot(s) kept the camera clip (see ai_video_jobs.json)")
        return out["clips"]
    except Exception as e:
        run.risks.append(f"ai video step skipped: {type(e).__name__}: {e}")
        return run.clips


def _clips_map(out: Any) -> Dict[str, str]:
    """Accepts {shot_id: path} (story_motion's), [{shot_id, path|clip|file}] or an object with .clips; -> {shot_id: path}."""
    if hasattr(out, "clips"):
        out = out.clips
    m: Dict[str, str] = {}
    if isinstance(out, dict):
        for k, v in out.items():
            if isinstance(v, (str, Path)):
                m[str(k)] = str(v)
            elif isinstance(v, dict):
                p = v.get("path") or v.get("clip") or v.get("file")
                if p:
                    m[str(k)] = str(p)
    elif isinstance(out, (list, tuple)):
        for e in out:
            if isinstance(e, dict) and e.get("shot_id") is not None:
                p = e.get("path") or e.get("clip") or e.get("file")
                if p:
                    m[str(e["shot_id"])] = str(p)
    return m


def _finish(run: StoryRun, log: Callable[[str], None]) -> StoryRun:
    if run.timer is not None and run.state_dir is not None:
        try:
            run.timer.save(run.state_dir / "bench.json")
            log(run.timer.report())
        except Exception:   # noqa: BLE001
            pass
    sh = run.shots
    if sh:
        if not run.clips:
            run.risks.append("no clips rendered yet: a render now shows each shot's picture with the app's normal Ken Burns (split at shot cuts), not the motion/link clips")
    log(run.report())
    return run


# =============================================================== applied_story

def _sound_mix(run: StoryRun, voice: Any, audio_end: float) -> Optional[str]:
    """Music bed, ambience and effects under the narration (story_fast.sound); None = keep the narration as it is. Never raises."""
    try:
        if not voice or not Path(str(voice)).is_file() or not run.shots or not (run.settings or {}).get("story_sound", True):
            return None
        from story_fast import sound
        sd = (run.state_dir or Path(".")); sd.mkdir(parents=True, exist_ok=True)
        plan = sound.build_plan(run.shots, float(audio_end), seed=int((run.settings or {}).get("story_seed") or 0))
        res = sound.render_mix(plan, str(voice), str(sd / "mix.m4a"), work_dir=str(sd / "mix_work"))
        if res.get("ok") and not res.get("fallback"):
            run.sound_credits = res.get("credits")
            print(f"[STORY] sound: mix rendered ({len(plan.get('ambience', []) if isinstance(plan, dict) else [])} beds)")
            return str(sd / "mix.m4a")
        print(f"[STORY] sound: narration only ({res.get('reason')})")
    except Exception as exc:        # noqa: BLE001
        print(f"[STORY] sound skipped ({exc})")
    return None


@contextlib.contextmanager
def applied_story(vg: Any, run: Optional[StoryRun]):
    """Around vg.render_video: the call the app already makes is rewritten to one row per unit (see the module docstring), and
    find_image_for_scene answers the synthetic row numbers. Restored on exit. When the run has nothing to apply, or anything in the rewrite
    fails, the render is called exactly as it was (never stops the render)."""
    if run is None or not run.usable():
        yield
        return
    orig_render, orig_find = vg.render_video, vg.find_image_for_scene
    media: Dict[int, Path] = {}
    parents: Dict[int, str] = {}

    def find(images_dir, scene_number, ext_cache=None):
        try:
            n = int(str(scene_number).strip())
        except ValueError:
            return orig_find(images_dir, scene_number, ext_cache=ext_cache)
        if n > SHOT_BASE:
            hit = media.get(n)
            if hit is not None and hit.is_file():
                return hit
            return orig_find(images_dir, parents[n], ext_cache=ext_cache) if parents.get(n) else None
        return orig_find(images_dir, scene_number, ext_cache=ext_cache)

    def unit_media(u: dict, tdir: Path) -> Optional[Path]:
        """What a unit plays: its clip (trimmed when it starts inside it), else the shot's own picture, else None (= its scene's picture)."""
        p = u.get("path")
        if p and Path(str(p)).is_file():
            if u.get("clip_in", 0.0) > 0.02:
                tr = trim_clip(p, u["clip_in"], u["end"] - u["start"], tdir / f"{Path(str(p)).stem}_{int(round(u['clip_in'] * 1000))}ms_{Path(str(p)).stat().st_size}.mp4")
                return tr if tr is not None else Path(str(p))
            return Path(str(p))
        sid = str(u.get("shot_id", "")).split("+link")[0]
        for key in (sid, u.get("scene_no")):
            q = run.images.get(str(key))
            if q and Path(q).is_file():
                return Path(q)
        return None

    def render(*args, **kw):
        try:
            sig = inspect.signature(orig_render)
            bound = sig.bind(*args, **kw)
            a = bound.arguments
            old_rows, audio_end = list(a["aligned_rows"]), float(a["audio_end"])
            old_win = vg._scene_display_timeline(old_rows, audio_end)
            units = run.units(audio_end)
            rows = shot_rows(units, old_rows)
            tdir = (run.state_dir or Path(".")) / "trims"
            media.clear()
            parents.clear()
            for u in units:
                n = synthetic_id(u["_ix"])
                parents[n] = _scene_of(u)
                m = unit_media(u, tdir)
                if m is not None:
                    media[n] = m
            clip_ix = [u["_ix"] for u in units if media.get(synthetic_id(u["_ix"])) is not None and vg.is_video_file(media[synthetic_id(u["_ix"])])]
            wins = {str(r.get("scene_number")).strip(): w for r, w in zip(old_rows, old_win)}
            fx = expand_text_effects(a.get("scene_text_effects"), old_win, units)
            new = {"aligned_rows": rows,
                   "scene_text_effects": fx if any(fx) else None,
                   "transition_by_scene": expand_transitions(a.get("transition_by_scene"), units) or None,
                   "camera_by_scene": expand_camera(a.get("camera_by_scene"), units) or None,
                   "edit_decisions_by_scene": expand_edit_decisions(a.get("edit_decisions_by_scene"), wins, units, clip_ix) or None}
            a.update(new)
            mixed = _sound_mix(run, a.get("audio_path"), audio_end)
            if mixed:
                a["audio_path"] = mixed
            if "visual_transitions" in a:
                a["visual_transitions"] = bool(new["transition_by_scene"])
            print(f"[STORY] render: {len(old_rows)} scenes -> {len(rows)} units ({len(clip_ix)} clips, {len(media) - len(clip_ix)} own pictures)")
        except Exception as exc:        # noqa: BLE001
            print(f"[STORY] shot rewrite skipped ({exc}); the render uses the scenes as they are")
            return orig_render(*args, **kw)
        return orig_render(*bound.args, **bound.kwargs)

    vg.find_image_for_scene = find
    vg.render_video = render
    try:
        yield
    finally:
        vg.render_video, vg.find_image_for_scene = orig_render, orig_find
