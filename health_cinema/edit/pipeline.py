"""High-end render pipeline: director -> (3D journeys, cached shots) -> audio mix -> one compositing pass with transitions, captions and finish -> QC.
Caching: a shot clip is keyed by its own spec (durations, not absolute times), its source files and the edit code, so editing one scene re-renders only that
shot (plus its neighbours' timing windows are recomputed in the cheap assembly pass). 3D journeys keep their own cache (render_journey)."""
from __future__ import annotations
import hashlib, json, os, shutil, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional
from PIL import Image

from . import audio, director, gfx, grade, media, qc, shots as S, typo, transitions as T
from . import VERSION

JOURNEY_TIMEOUT_S = 900   # a 3D journey that takes longer than this is treated as failed (statement card + flag), never as a success
HANDLE = 12   # frames of extra picture on each side of a shot (half of the longest transition)
HERE = Path(__file__).resolve().parent
CODE = sorted(HERE.glob("*.py"))

def code_hash() -> str:
    h = hashlib.sha256(VERSION.encode())
    for p in CODE: h.update(p.read_bytes())
    return h.hexdigest()[:16]

def _sig(path: Optional[str]) -> str:
    if not path: return ""
    try: st = os.stat(path); return f"{path}|{st.st_size}|{int(st.st_mtime)}"
    except OSError: return str(path)

def shot_key(spec: dict, W: int, H: int, code: str) -> str:
    s = {k: v for k, v in spec.items() if k not in ("t0", "t1", "why", "scene_no", "role", "journey_cache_hit")}; s["dur"] = round(spec["t1"] - spec["t0"], 4)
    for k in ("src", "plate", "clip"):
        if s.get(k): s[k] = _sig(s[k])
    return hashlib.sha256(json.dumps([s, W, H, HANDLE, code], sort_keys=True, default=str).encode()).hexdigest()[:24]

class _ClipReader:
    def __init__(self, path, start, count, W, H, cancel): self.it = media.read_frames_exact(path, W, H, start, count, cancel)
    def next(self): return next(self.it)

def _assemble(shots_: List[dict], trans: List[T.Transition], clips: List[Path], phrases, W: int, H: int, out: Path, audio_wav: Optional[Path], accent, cancel, progress) -> int:
    U = gfx.Units(W, H); caps = typo.CaptionTrack(phrases, U, accent); starts = [round(s["t0"] * media.FPS) for s in shots_]; ends = starts[1:] + [round(shots_[-1]["t1"] * media.FPS)]; total = ends[-1]
    nin = [0] + [t.frames // 2 for t in trans]; nout = [t.frames // 2 for t in trans] + [0]
    readers: Dict[int, object] = {}
    def reader(i):
        if i not in readers:
            first = HANDLE - nin[i]; count = (ends[i] - starts[i]) + nin[i] + nout[i]; readers[i] = media.read_frames_exact(str(clips[i]), W, H, first, count, cancel)
        return readers[i]
    enc = media.Encoder(out.with_suffix(".part.mp4"), W, H, 16, "medium", audio=str(audio_wav) if audio_wav else None)
    try:
        for g in range(total):
            if cancel is not None and cancel.is_set(): raise media.Cancelled("cancelled")
            i = max(k for k in range(len(shots_)) if starts[k] <= g); tr_i = None
            for k, t in enumerate(trans):
                if t.frames and starts[k + 1] - t.frames // 2 <= g < starts[k + 1] + t.frames // 2: tr_i = k; break
            if tr_i is None: im = next(reader(i))
            else:
                t = trans[tr_i]; p = (g - (starts[tr_i + 1] - t.frames // 2) + 0.5) / t.frames; a = next(reader(tr_i)); b = next(reader(tr_i + 1)); im = T.apply(t, a, b, p)
                if g == starts[tr_i + 1] + t.frames // 2 - 1:
                    for j in (tr_i,): readers.pop(j, None)
            caps.draw(im, g / media.FPS); im = grade.grain(im, g, 0.45); enc.write(im)
            if g % 48 == 0: progress(g / total)
        enc.close(); out.with_suffix(".part.mp4").replace(out)
    except BaseException:
        enc.abort(); out.with_suffix(".part.mp4").unlink(missing_ok=True); raise
    return total

def render_high_end(scenes, voiceover: str, out_path: str, project_dir: Path, *, prof, quality: str, W: int, H: int, cancel: Optional[threading.Event] = None, log: Callable[[str], None] = lambda m: None,
                    progress: Callable[[float, str], None] = lambda k, m: None, journey_renderer: Optional[Callable] = None, music: bool = True, frame_renderer=None, workers: int = 4) -> dict:
    """-> report dict (timings, cache hits, plan, QC). Raises media.Cancelled on cancel; leaves no partial video."""
    from .. import clips as C, render_journey as RJ, assets
    t_start = time.time(); project_dir = Path(project_dir); cancel = cancel or threading.Event(); out_path = Path(out_path); code = code_hash()
    cache = project_dir / "state" / "health_cinema" / quality / "edit"; cache.mkdir(parents=True, exist_ok=True)
    total_s = sum(round(s.end * C.FPS) - round(s.start * C.FPS) for s in scenes) / C.FPS
    progress(0.02, "reading the narration's pauses")
    silences = media.detect_pauses(voiceover) if voiceover else []
    plan = director.build(scenes, prof.accent, silences); shots_ = plan["shots"]; flags: List[dict] = []
    # 3D journeys: through the app's cached Three.js renderer; labels stay baked (they track the anatomy), captions are drawn by this pipeline
    t_j = time.time()
    for k, sh in enumerate(list(shots_)):
        if sh["kind"] != "anatomy": continue
        a = assets.anatomy_assets(assets.TEMPLATE_ASSET.get(sh["template"], "chest")); ok = bool(a and (frame_renderer is not None or assets.threejs_ready()))
        if ok:
            try:
                spec = C.scale_spec(C.template_spec(sh["template"]), sh["t1"] - sh["t0"]); spec["footer"] = ""; spec["captions"] = []
                sp = cache / f"spec_{hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]}.json"; sp.write_text(json.dumps(spec))
                progress(0.05 + 0.1 * k / len(shots_), f"3D journey for scene {sh['scene_no']}")
                r = RJ.render_journey(sp, a["anchors"], a["model"], W, H, C.FPS, cache.parent / "journeys", cancel=cancel, frame_renderer=frame_renderer or (lambda *a, **k: RJ.threejs_frames(*a, **dict(k, timeout=JOURNEY_TIMEOUT_S)))); log(f"3D journey scene {sh['scene_no']}: {'cache hit' if r['cache_hit'] else 'rendered in %.0fs' % r['seconds']}"); sh["clip"] = r["path"]; sh["journey_cache_hit"] = r["cache_hit"]; continue
            except RJ.Cancelled: raise
            except Exception as exc: flags.append({"code": "3d_fallback", "scene": sh["scene_no"], "message": f"3D render failed ({str(exc)[:140]}): statement card instead"}); log(f"3D scene {sh['scene_no']} failed: {str(exc)[:120]}")
        else: flags.append({"code": "3d_fallback", "scene": sh["scene_no"], "message": "3D assets or Node/three.js not available: statement card instead"})
        sh.update(kind="statement", gfx={"beats": [{"text": next((s.text for s in scenes if s.scene_no == sh["scene_no"]), ""), "t0": 0.0}]}, overlays=[]); sh.pop("template", None)
    journeys_s = time.time() - t_j
    # shot clips (cached by their own content); uncached ones render in a small thread pool (Pillow and ffmpeg release the GIL)
    clips: List[Path] = []; hits = 0; todo = []; keys = []
    for sh in shots_:
        key = shot_key(sh, W, H, code); keys.append(key); p = cache / f"shot_{sh['kind']}_{key}.mp4"; clips.append(p)
        if p.exists() and p.stat().st_size > 0: hits += 1
        else: todo.append((sh, p))
    t_s = time.time(); done = [0]
    def job(sh, p):
        S.render_shot(sh, W, H, p, HANDLE, cancel); done[0] += 1; progress(0.15 + 0.5 * done[0] / max(1, len(todo)), f"shot {done[0]}/{len(todo)} rendered")
    if todo:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(todo)))) as ex:
            futs = [ex.submit(job, sh, p) for sh, p in todo]
            try:
                for f_ in futs: f_.result()
            except BaseException:
                cancel.set(); [f_.cancel() for f_ in futs]; raise
    shots_s = time.time() - t_s
    # audio
    progress(0.66, "mixing audio"); t_a = time.time(); arep: dict = {}; wav = None
    if voiceover:
        wav = cache / f"mix_{hashlib.sha256((_sig(voiceover) + json.dumps(plan['cues']) + json.dumps([[s['t0'], s['t1'], s['role']] for s in shots_]) + str(music) + code).encode()).hexdigest()[:16]}.wav"
        if wav.exists(): arep = {"cached": True}
        else:
            try: arep = audio.mix(voiceover, plan, total_s, wav, " ".join(s.text for s in scenes), hashlib.sha1(" ".join(s.text for s in scenes).encode()).hexdigest()[:8], music=music, log=log)
            except Exception as exc: arep = {"notes": [f"audio finishing failed ({type(exc).__name__}: {str(exc)[:120]}); plain narration used"]}; wav = None; log(arep["notes"][0])
    audio_s = time.time() - t_a
    progress(0.7, "compositing transitions, captions and finish"); t_c = time.time()
    out_path.parent.mkdir(parents=True, exist_ok=True); tmp_out = out_path.with_name(out_path.name + ".rendering.mp4")
    audio_for_mux = wav
    if voiceover and wav is None:   # audio finishing failed: mux the plain narration so the video is never silent
        audio_for_mux = Path(voiceover)
    total = _assemble(shots_, plan["transitions"], clips, plan["phrases"], W, H, tmp_out, audio_for_mux, tuple(prof.accent), cancel, lambda k: progress(0.7 + 0.25 * k, "compositing"))
    os.replace(tmp_out, out_path); comp_s = time.time() - t_c
    progress(0.96, "quality checks")
    pc = qc.plan_checks(plan); oc = qc.output_checks(str(out_path), shots_, plan["transitions"], total)
    rep = {"edit_version": VERSION, "frames": total, "seconds_total": round(time.time() - t_start, 2), "timing": {"journeys_s": round(journeys_s, 2), "shots_s": round(shots_s, 2), "audio_s": round(audio_s, 2), "composite_s": round(comp_s, 2)},
           "shots_total": len(shots_), "shots_cache_hits": hits, "shots_rendered": len(todo), "shot_keys": keys, "plan": {"analysis": plan["analysis"], "shots": [{k: v for k, v in s.items() if k != "profile"} for s in shots_],
           "transitions": [t.as_json() for t in plan["transitions"]], "cues": plan["cues"], "phrases": [p.as_json() for p in plan["phrases"]]}, "audio": arep, "plan_qc": pc, "output_qc": oc,
           "flags": flags, "human_review": qc.HUMAN_REVIEW}
    return rep
