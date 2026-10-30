"""story_fast.animate: runs the ai_video_job entries of a clip plan (real image-to-video), safely and selectively.

    report = dry_run_report(jobs, settings)                          # nothing is sent; "would animate N shots, ~S seconds"
    out    = animate_jobs(jobs, clips, out_dir, settings, animator=None, log=None, cancel=None)   # -> {"clips": {...}, "report": {...}}

Rules
  * story_ai_video_live must be True to submit anything (default False: jobs are only recorded and a dry-run report is made).
  * Jobs are ranked by need (real character action > object action > environment) and capped by story_ai_video_live_max
    (default: story_ai_video_max, else 6). Every other job keeps its local camera clip.
  * One request per distinct (picture bytes + prompt + duration); the answer is cached in <out_dir>/ai_video/ so a rerun or a crash costs nothing more.
    A request that was sent but never answered (crash/cancel) is NOT sent again by itself: it is recorded "unknown" (it may have billed) and
    the local clip is kept; set story_ai_video_resubmit=True to send it again.
  * The returned mp4 is fitted to the shot exactly (30 fps, 1920x1080, libx264 -crf 18 like story_fast's own clips).
  * ANY failure (timeout, quota, anti-abuse hold, unsupported engine, bad file) keeps the local clip and writes the reason into ai_video_jobs.json.
    A quota or hold stops further submissions for this run (they would fail the same way).

The animator is any object with  animate(image, prompt, seconds, out_path, should_stop) -> path  (raise on failure; cancel() optional).
FlowAnimator is the real one (providers.flow video path); it refuses to run unless the engine can take a start picture (see its docstring)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

FPS, SIZE = 30, (1920, 1080)
FLOW_DURATIONS = (4, 6, 8)                     # seconds Flow video can make (config.js videoDurations)
DEFAULT_MAX, DEFAULT_TIMEOUT = 6, 600.0
CONTINUITY = "Same character, same outfit, same place and lighting as the picture. One continuous shot, no cuts, no text, no new people."
_PERSON = re.compile(r"\b(he|she|man|woman|men|women|boy|girl|child|children|soldier|people|crowd|king|queen|doctor|worker|farmer|driver|rider|runner|"
                     r"character|hero|villain|someone|person|player|dancer|fighter)\b", re.I)
_OBJECT = re.compile(r"\b(car|truck|train|plane|ship|boat|door|wheel|flag|machine|engine|rocket|bridge|gate|sword|ball|lamp|candle|clock|gear|horse|dog|bird)\b", re.I)


class AnimateError(Exception):
    reason = "error"
class AnimateTimeout(AnimateError): reason = "timeout"
class AnimateQuota(AnimateError): reason = "quota"
class AnimateHold(AnimateError): reason = "hold"
class AnimateUnsupported(AnimateError): reason = "unsupported"
class AnimateCancelled(AnimateError): reason = "cancelled"
class AnimateBadFile(AnimateError): reason = "bad_file"


def classify(exc: BaseException) -> AnimateError:
    """Any exception -> one of the classes above (by type, then by words in the message)."""
    if isinstance(exc, AnimateError):
        return exc
    m = str(exc).lower()
    if any(w in m for w in ("quota", "credit", "rate limit", "too many", "limit reached", "resource_exhausted", "429")):
        return AnimateQuota(str(exc))
    if any(w in m for w in ("unusual activity", "anti-abuse", "abuse", "hold", "blocked", "suspended", "not allowed", "policy")):
        return AnimateHold(str(exc))
    if "timed out" in m or "timeout" in m:
        return AnimateTimeout(str(exc))
    if "cancel" in m:
        return AnimateCancelled(str(exc))
    return AnimateError(f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ settings, ranking, prompt
def live(settings) -> bool:
    return bool((settings or {}).get("story_ai_video_live", False))


def _cap(settings) -> int:
    st = settings or {}
    for k in ("story_ai_video_live_max", "story_ai_video_max"):
        try:
            v = int(st.get(k))
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return DEFAULT_MAX


def need_score(job: dict) -> float:
    """Higher = the shot gains more from real movement. character action 3, object action 2, environment 1, plus the planner's own priority."""
    ai = job.get("ai_video") or {}
    blob = " ".join(str(ai.get(k) or "") for k in ("prompt", "reason"))
    kind = 3.0 if _PERSON.search(blob) else (2.0 if _OBJECT.search(blob) else 1.0)
    try:
        pr = float(ai.get("priority") or 0.0)
    except (TypeError, ValueError):
        pr = 0.0
    return kind * 10.0 + pr


def select(jobs: List[dict], settings) -> List[dict]:
    """The jobs that will be animated: ai_video_job only, best need first, at most the cap; returned in timeline (plan) order."""
    ai = [j for j in jobs if j.get("type") == "ai_video_job" and j.get("ai_video")]
    ranked = sorted(ai, key=lambda j: -need_score(j))[:_cap(settings)]
    ids = {j["shot_id"] for j in ranked}
    return [j for j in ai if j["shot_id"] in ids]


_CAMERA = {"push_in": "slow push-in", "pull_out": "slow pull-back", "drift_l": "gentle camera drift to the left", "drift_r": "gentle camera drift to the right",
           "hold_alive": "locked-off camera", "track_l": "tracking shot to the left", "track_r": "tracking shot to the right"}


def motion_prompt(job: dict) -> str:
    """action (the planner's prompt) + camera + continuity suffix."""
    ai = job.get("ai_video") or {}
    action = str(ai.get("prompt") or "").strip().rstrip(".")
    cam = _CAMERA.get(str(job.get("treatment") or ""), "steady cinematic camera")
    return f"{action}. Camera: {cam}. {CONTINUITY}".strip(". ").strip() + "."


def request_seconds(shot_seconds: float) -> int:
    """Smallest Flow duration that covers the shot (the clip is then trimmed); longer shots use the longest and are slowed a little / held."""
    for d in FLOW_DURATIONS:
        if d >= shot_seconds - 1e-6:
            return d
    return FLOW_DURATIONS[-1]


def _file_sha(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def cache_key(picture: str, prompt: str, seconds: int) -> str:
    return hashlib.sha1(json.dumps([_file_sha(picture), prompt, int(seconds), "i2v-1"]).encode()).hexdigest()[:24]


# ------------------------------------------------------------------ dry run
def dry_run_report(jobs: List[dict], settings) -> dict:
    sel = select(jobs, settings)
    secs = sum(request_seconds(float(j.get("shot_seconds") or (j.get("ai_video") or {}).get("seconds") or 0)) for j in sel)
    total = sum(1 for j in jobs if j.get("type") == "ai_video_job")
    return {"live": live(settings), "candidates": total, "would_animate": len(sel), "estimated_seconds": secs, "cap": _cap(settings),
            "shots": [j["shot_id"] for j in sel],
            "text": f"would animate {len(sel)} shot{'s' if len(sel) != 1 else ''}, ~{secs}s of Flow video "
                    f"({len(sel)} generations of Flow video credits; {total - len(sel)} other flagged shot(s) keep their camera clip). Not sent: story_ai_video_live is off."}


# ------------------------------------------------------------------ ffmpeg
def _ff(name: str) -> str:
    return shutil.which(name) or name


def probe_seconds(path: str) -> float:
    r = subprocess.run([_ff("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise AnimateBadFile("returned file has no readable duration")


def fit_clip(src: str, out: str, seconds: float, fps: int = FPS, size=SIZE) -> str:
    """Exactly round(seconds*fps) frames at size. Longer source: trimmed. Slightly shorter: slowed (up to 1.5x), then the last frame is held."""
    n = max(1, int(round(seconds * fps))); have = probe_seconds(src); w, h = size
    slow = 1.0
    if have > 0 and have < seconds:
        slow = min(1.5, seconds / have)
    vf = (f"setpts={slow:.5f}*PTS,fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
          f"tpad=stop_mode=clone:stop={n},format=yuv420p")
    tmp = out + ".part.mp4"
    subprocess.run([_ff("ffmpeg"), "-y", "-loglevel", "error", "-i", src, "-vf", vf, "-frames:v", str(n), "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-an", tmp], check=True, capture_output=True, timeout=600)
    os.replace(tmp, out)
    return out


def frame_count(path: str) -> int:
    r = subprocess.run([_ff("ffprobe"), "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True, timeout=120)
    return int(r.stdout.strip() or 0)


def last_frame(src: str, out_png: str) -> Optional[str]:
    try:
        subprocess.run([_ff("ffmpeg"), "-y", "-loglevel", "error", "-sseof", "-0.1", "-i", src, "-frames:v", "1", "-update", "1", out_png], check=True, capture_output=True, timeout=60)
        return out_png if os.path.isfile(out_png) else None
    except Exception:
        return None


# ------------------------------------------------------------------ records
def _load_records(path: str) -> Dict[str, dict]:
    try:
        d = json.loads(Path(path).read_text())
        return {str(r.get("shot_id")): r for r in d if isinstance(r, dict)}
    except Exception:
        return {}


def _save_records(path: str, recs: Dict[str, dict]) -> None:
    tmp = path + ".tmp"
    Path(tmp).write_text(json.dumps(list(recs.values()), indent=1, default=str))
    os.replace(tmp, path)


def _run_bounded(animator, picture, prompt, seconds, raw_out, cancel, timeout) -> str:
    """animator.animate in a daemon thread; we poll for cancel and the deadline so a stuck call can never hang the render."""
    box: Dict[str, Any] = {}
    stop = threading.Event()

    def should_stop() -> bool:
        return stop.is_set() or bool(cancel and cancel())

    def work():
        try:
            box["path"] = animator.animate(picture, prompt, seconds, raw_out, should_stop)
        except BaseException as e:           # noqa: BLE001 - reported, classified by the caller
            box["err"] = e
    t = threading.Thread(target=work, daemon=True); t.start()
    end = time.monotonic() + timeout
    while t.is_alive():
        t.join(0.1)
        if cancel and cancel():
            stop.set(); _try_cancel(animator); t.join(2.0)
            raise AnimateCancelled("cancelled while waiting for the video")
        if time.monotonic() > end:
            stop.set(); _try_cancel(animator)
            raise AnimateTimeout(f"no video after {int(timeout)}s")
    if "err" in box:
        raise classify(box["err"])
    return str(box.get("path") or raw_out)


def _try_cancel(animator):
    try:
        c = getattr(animator, "cancel", None)
        if callable(c):
            c()
    except Exception:
        pass


# ------------------------------------------------------------------ main
def animate_jobs(jobs: List[dict], clips: Dict[str, str], out_dir: str, settings=None, animator=None, log: Optional[Callable] = None,
                 cancel: Optional[Callable[[], bool]] = None) -> dict:
    """Returns {"clips": clips with animated shots replaced, "report": dict}. Never raises for an animation problem; local clips stay."""
    st = dict(settings or {}); log = log or (lambda *a, **k: None); clips = dict(clips or {})
    os.makedirs(out_dir, exist_ok=True); cdir = os.path.join(out_dir, "ai_video"); os.makedirs(cdir, exist_ok=True)
    rec_path = os.path.join(out_dir, "ai_video_jobs.json"); recs = _load_records(rec_path)
    report = dry_run_report(jobs, st); report.update(animated=0, cached=0, failed=0, cancelled=False, stopped_early=None)
    sel = select(jobs, st); picked = {j["shot_id"] for j in sel}
    for j in jobs:                                      # make sure every flagged job has a record, with its status
        if j.get("type") != "ai_video_job":
            continue
        r = recs.setdefault(str(j["shot_id"]), dict(j.get("ai_video") or {}, shot_id=j["shot_id"]))
        r.update(selected=j["shot_id"] in picked, need=round(need_score(j), 2))
        if j["shot_id"] not in picked and r.get("status") not in ("animated", "cached"):
            r["status"] = "not_selected"; r["fallback"] = "local camera clip"
    if not live(st) or not sel:
        for j in sel:
            recs[str(j["shot_id"])].update(status="dry_run" if not live(st) else recs[str(j["shot_id"])].get("status"), fallback="local camera clip",
                                         note="story_ai_video_live is off: nothing was sent" if not live(st) else None)
        _save_records(rec_path, recs); log("[STORY] ai video: " + report["text"] if not live(st) else "[STORY] ai video: nothing selected")
        report["recorded"] = rec_path
        return {"clips": clips, "report": report}
    if animator is None:
        animator = st.get("story_ai_video_animator") or FlowAnimator(st)       # an object in settings: the app's Flow provider wrapper, or a test stub
    timeout = float(st.get("story_ai_video_timeout") or DEFAULT_TIMEOUT); stop_reason = None; prev: Optional[dict] = None
    for j in sel:
        sid = str(j["shot_id"]); r = recs[sid]
        if cancel and cancel():
            report["cancelled"] = True; r.update(status="cancelled", fallback="local camera clip"); break
        if stop_reason:
            r.update(status="skipped", fallback="local camera clip", note=f"not sent: {stop_reason}"); continue
        ai = j["ai_video"]; pic = str(ai.get("first_picture") or j.get("still") or "")
        if prev and prev.get("seed_next") and prev.get("last_frame") and os.path.isfile(prev["last_frame"]) and prev.get("shot_id_next") == sid:
            pic = prev["last_frame"]                 # continuity: the previous animated clip ended here
        if not pic or not os.path.isfile(pic):
            r.update(status="failed", reason="bad_file", error="no picture to animate", fallback="local camera clip"); report["failed"] += 1; continue
        prompt = motion_prompt(j); rs = request_seconds(float(j.get("shot_seconds") or ai.get("seconds") or 4.0)); key = cache_key(pic, prompt, rs)
        raw = os.path.join(cdir, f"{key}.mp4"); fitted = os.path.join(cdir, f"{sid}_{key}_{int(round(float(j['duration']) * FPS))}f.mp4"); pend = os.path.join(cdir, f"{key}.pending")
        r.update(key=key, prompt=prompt, requested_seconds=rs, picture=pic)
        try:
            if os.path.isfile(raw) and os.path.getsize(raw) > 0:
                status = "cached"
            elif os.path.isfile(pend) and not st.get("story_ai_video_resubmit"):
                r.update(status="unknown", fallback="local camera clip",
                         note="a request for this shot was sent earlier and never came back; it may have billed. Not sent again (set story_ai_video_resubmit to send it).")
                _save_records(rec_path, recs); continue
            else:
                Path(pend).write_text(json.dumps({"shot_id": sid, "sent": time.time()}))
                r.update(status="submitted"); _save_records(rec_path, recs); log(f"[STORY] ai video: sending {sid} ({rs}s)")
                part = raw + ".dl.mp4"
                got = _run_bounded(animator, pic, prompt, rs, part, cancel, timeout)
                if not os.path.isfile(got) or os.path.getsize(got) == 0:
                    raise AnimateBadFile("animator returned no file")
                probe_seconds(got)                                   # readable video, else AnimateBadFile
                os.replace(got, raw); status = "animated"
                try:
                    os.remove(pend)
                except OSError:
                    pass
            if not (os.path.isfile(fitted) and frame_count(fitted) == int(round(float(j["duration"]) * FPS))):
                fit_clip(raw, fitted, float(j["duration"]))
            clips[sid] = fitted
            r.update(status=status, clip=fitted, error=None, reason=None, fallback=None, frames=int(round(float(j["duration"]) * FPS)))
            report["cached" if status == "cached" else "animated"] += 1
            lf = last_frame(raw, os.path.join(cdir, f"{key}_last.png")) if ai.get("seed_next") else None
            prev = dict(seed_next=bool(ai.get("seed_next")), last_frame=lf, shot_id_next=ai.get("next_shot_id"), shot_id=sid)
            r["last_frame"] = lf
        except AnimateCancelled as e:
            report["cancelled"] = True; r.update(status="cancelled", reason="cancelled", error=str(e), fallback="local camera clip"); break
        except Exception as e:                                       # noqa: BLE001
            ce = classify(e); r.update(status="failed", reason=ce.reason, error=str(ce), fallback="local camera clip"); report["failed"] += 1
            if isinstance(ce, (AnimateQuota, AnimateHold, AnimateUnsupported)):
                try:
                    os.remove(pend)                                  # refused before generating: nothing billed, safe to try later
                except OSError:
                    pass
            log(f"[STORY] ai video: {sid} failed ({ce.reason}: {ce}); local camera clip kept")
            prev = None
            if isinstance(ce, (AnimateQuota, AnimateHold, AnimateUnsupported)):
                stop_reason = f"{ce.reason} on an earlier shot"; report["stopped_early"] = ce.reason
        _save_records(rec_path, recs)
    _save_records(rec_path, recs); report["recorded"] = rec_path
    log(f"[STORY] ai video: {report['animated']} animated, {report['cached']} from cache, {report['failed']} failed (those keep the camera clip)")
    return {"clips": clips, "report": report}


# ------------------------------------------------------------------ the real animator (Flow)
class FlowAnimator:
    """Sends one picture + motion prompt through the app's existing Flow VIDEO path (providers.flow.provider.FlowProvider, media_kind='video').

    HONEST STATUS: the Flow engine in this repo has only a text-to-video path (flow-engine/lib/flow-api.js generateOneVideo takes a prompt, no start
    picture), and referenceImages work only for IMAGE runs in UI mode. A text-only video would not match the still, so this class refuses
    (AnimateUnsupported) unless settings say the engine can take a start picture: story_ai_video_start_image=True (the engine then must read
    settings['startImage']). Nothing here was run against live Flow."""

    def __init__(self, settings=None, provider=None, images_dir: Optional[str] = None):
        self.settings = dict(settings or {}); self.provider = provider; self._cancelled = threading.Event()
        self.images_dir = images_dir or self.settings.get("story_ai_video_dir") or os.path.join(os.getcwd(), "out", "story_ai_video")

    def cancel(self):
        self._cancelled.set()

    def animate(self, image, prompt, seconds, out_path, should_stop):
        if not self.settings.get("story_ai_video_start_image"):
            raise AnimateUnsupported("the Flow engine has no start-picture video mode yet (text-to-video would not match the picture)")
        if self.provider is None:
            raise AnimateUnsupported("no Flow video provider was given (build FlowAnimator(settings, provider=app's flow video provider))")
        from providers.base import SceneRow
        prov = self.provider
        fs = dict(getattr(prov, "flow_settings", {}) or {}); fs.update(startImage=str(Path(image).resolve()), videoDuration=int(seconds))
        prov.flow_settings = fs
        scene = SceneRow(scene_number="ai_" + hashlib.sha1(prompt.encode()).hexdigest()[:8], script_segment=prompt, asset_type="video", prompt=prompt)
        Path(self.images_dir).mkdir(parents=True, exist_ok=True)
        res = prov.resolve_batch([scene], Path(self.images_dir), log=lambda *a, **k: None,
                                 should_stop=lambda: self._cancelled.is_set() or bool(should_stop()))[scene.scene_number]
        if not res.ok:
            raise classify(RuntimeError(res.error or "Flow returned no video"))
        shutil.copyfile(str(res.path), out_path)
        return out_path
