"""story_fast runner: plans clip jobs from shots and renders them in parallel, resumably. Drop-in for story_motion.plan_clips / render_clips / assemble_timeline.

    jobs  = plan_clips(shots, images, settings)
    clips = render_clips(jobs, out_dir, log, cancel, workers, progress=cb, state_path=None)   -> {shot_id: mp4}
    segs  = assemble_timeline(shots, clips, settings)

Joins (continuity.py): the camera of the outgoing and incoming shot are adjusted per edit (tparams['join'], no extra encode); a true cross-dissolve (time/lighting moves
on, near-identical pictures) is a short link clip '<id>+link_<k>f.mp4' (bridge.py) that REPLACES the first k frames of the next shot, so the timeline length never changes.
Everything else is a hard cut; the app only dips (transition_in) at a true scene break. Any failure falls back to plain cuts.
ai_video shots get a local fallback clip and a record in <out_dir>/ai_video_jobs.json."""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, threading, time, zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEED_PATH = ROOT / "out" / "story_fast_cache" / "speed.json"
DEFAULT_MS_1080 = 12.0            # ms per frame of 1080p until real renders are measured
MB_PER_SHOT_1080 = 700
FALLBACK_TREATMENTS = ("hold_alive", "push_in")
ROTATION = ("push_in", "drift_l", "pull_out", "drift_r", "hold_alive")
RETRIES = 2
CONTINUITY_STAMP = "cont-4+bridge-2+compose-join-5+grade-1"      # bump with continuity.py / bridge.py / the join code in compose.py: the app keys its clip cache on this file


class Cancelled(Exception): pass


_TIMER = None
_COMPOSE = None                   # injected stub (tests) or lazily imported module


def set_timer(timer): global _TIMER; _TIMER = timer
def set_compose(mod): global _COMPOSE; _COMPOSE = mod


def _compose():
    if _COMPOSE is not None: return _COMPOSE
    try:
        sys.path.insert(0, str(ROOT)); from story_fast import compose; return compose
    except Exception: return None


def _is_cancel(e): return type(e).__name__ == "Cancelled"


def _seed(base, shot_id): return int(base) * 1000 + (zlib.crc32(str(shot_id).encode()) % 997)


def _image(images, shot, i):
    if isinstance(images, (list, tuple)): return str(images[i]) if i < len(images) and images[i] else None
    for k in (shot.get("shot_id"), shot.get("scene_no"), str(shot.get("scene_no"))):
        if k is not None and k in images and images[k]: return str(images[k])
    return None


# ---------------------------------------------------------------- speed store / estimate
def _load_speed():
    try: return float(json.loads(Path(SPEED_PATH).read_text())["ms_per_frame_1080"])
    except Exception: return DEFAULT_MS_1080


def _save_speed(ms):
    try:
        Path(SPEED_PATH).parent.mkdir(parents=True, exist_ok=True); tmp = str(SPEED_PATH) + ".tmp"
        Path(tmp).write_text(json.dumps({"ms_per_frame_1080": round(ms, 3), "updated": time.time()})); os.replace(tmp, SPEED_PATH)
    except Exception: pass


def _est(dur, fps, size, ms1080): return round(dur * fps * ms1080 * (size[0] * size[1]) / (1920 * 1080) / 1000.0 + 0.2, 3)


def estimate_total(jobs, workers=1) -> float:
    return round(sum(j.get("est_seconds", 0.0) for j in jobs if j.get("type") != "skip") / max(1, workers), 2)


# ---------------------------------------------------------------- planning
def _direct(shots, st):
    if all(s.get("treatment") for s in shots): return list(shots)
    try:
        sys.path.insert(0, str(ROOT)); from story_fast import direct
        out = direct.direct(list(shots), st, int(st.get("seed", 0)))
        return list(out["shots"] if isinstance(out, dict) else out)
    except Exception:
        res = []
        for i, s in enumerate(shots):
            s = dict(s)
            if not s.get("treatment"): s["treatment"] = ROTATION[i % len(ROTATION)]
            res.append(s)
        return res


STRIP_MIN, STRIP_MAX = 3, 6

def strip_groups(shots, images, settings=None) -> dict:
    """{shot_id: (group id, index)} for runs of 3..6 consecutive shots with DIFFERENT pictures that are glued into one torn-paper strip the camera travels along.
    story_strip: "off" (default) | "auto" (travel / history / documentary runs, at most 40% of the shots) | "all" (every possible run)."""
    st = dict(settings or {}); mode = str(st.get("story_strip", st.get("strip", "off"))).lower()
    if mode in ("off", "false", "0", "none", ""): return {}
    ok = []
    for i, sh in enumerate(shots):
        still = _image(images, sh, i)
        good = sh.get("motion_tier") != "graphic" and still and os.path.isfile(str(still)) and not sh.get("ai_video")
        if mode == "auto": good = good and (sh.get("genre") in ("travel", "history", "documentary"))
        ok.append(still if good else None)
    # panels: consecutive shots on the SAME picture are one panel of the strip; a run is a chain of touching panels
    panels, cur = [], None
    for i, still in enumerate(ok):
        if not still: cur = None; continue
        if cur is not None and cur["still"] == still and abs(float(shots[i]["start"]) - float(shots[cur["idx"][-1]]["end"])) < 0.6: cur["idx"].append(i)
        else: cur = {"still": still, "idx": [i]}; panels.append(cur)
    runs, run = [], []
    for pn in panels:
        if run and abs(float(shots[pn["idx"][0]]["start"]) - float(shots[run[-1]["idx"][-1]]["end"])) < 0.6 and all(pn["still"] != q["still"] for q in run[-1:]): run.append(pn)
        else:
            if run: runs.append(run)
            run = [pn]
    if run: runs.append(run)
    cap = len(shots) if mode == "all" else int(0.4 * len(shots)); out = {}; used = 0; gid = 0
    for r in runs:
        while len(r) >= STRIP_MIN and used < cap:
            part = r[:STRIP_MAX]; r = r[STRIP_MAX:]
            if len(r) and len(r) < STRIP_MIN: part, r = part + r, []                 # never leave a 1-2 panel stub behind
            if len(part) < STRIP_MIN: break
            gid += 1
            for k, pn in enumerate(part):
                used += len(pn["idx"])
                for i in pn["idx"]: out[shots[i]["shot_id"]] = (f"g{gid:03d}", k)
    return out



def _bounds(shots, fps):
    b = [int(round(float(shots[0]["start"]) * fps))] + [int(round(float(s["end"]) * fps)) for s in shots]
    for i in range(1, len(b)): b[i] = max(b[i], b[i - 1])
    return b


def _continuity_on(st):
    return str(st.get("story_continuity", True)).lower() not in ("false", "0", "off", "no", "none")


def _plan_joins(shots, images, st, fps, usable):
    """(camera joins {shot_id: spec}, links {A id: {to, frames}}). usable[i] = shot i is a plain clip shot (not graphic / ai / strip / picture-less). Never raises."""
    if not _continuity_on(st) or len(shots) < 2: return {}, {}
    try:
        sys.path.insert(0, str(ROOT)); from story_fast import continuity as C
        edits = C.plan_edits(shots, st, images if isinstance(images, dict) else None)
        for i, e in enumerate(edits):
            if e.get("realize") in ("camera", "link") and not (i and usable[i] and usable[i - 1]):
                e.update(type="simple_cut", realize="none", strength=0.0, reason=e.get("reason", "") + " - kept a plain cut (a neighbouring shot is not a plain clip)")
        C.apply(shots, edits, st)
        return C.camera_joins(shots, edits, fps), C.link_pairs(shots, edits, fps)
    except Exception:
        return {}, {}


def _load_grade(st):
    """The project grade: settings['story_grade'] (a ProjectGrade or its dict) or the JSON at settings['story_grade_path']. None = the fixed look (old behaviour)."""
    try:
        from story_fast import grade as G
        g = st.get("story_grade")
        if isinstance(g, G.ProjectGrade): return g
        if isinstance(g, dict) and g.get("ref"): return G.ProjectGrade.from_dict(g)
        gp = st.get("story_grade_path") or st.get("grade_path")
        if gp: return G.load(str(gp))
    except Exception: pass
    return None


def plan_clips(shots, images, settings=None) -> list:
    st = dict(settings or {}); size = tuple(st.get("size", (1920, 1080))); fps = int(st.get("fps", 30)); base = int(st.get("seed", 0))
    margin = float(st.get("margin", 0.3)); inten = st.get("intensity", "medium"); ms = _load_speed(); shots = _direct(list(shots), st); jobs = []
    groups = strip_groups(shots, images, st)
    bnd = _bounds(shots, fps) if shots else [0]
    usable = []
    for i, sh in enumerate(shots):
        stl = _image(images, sh, i)
        usable.append(sh.get("motion_tier") != "graphic" and bool(stl) and os.path.isfile(str(stl)) and not sh.get("ai_video") and sh["shot_id"] not in groups)
    joins, links = _plan_joins(shots, images, st, fps, usable)
    grade = _load_grade(st)
    for i, sh in enumerate(shots):
        sid = sh["shot_id"]; dur = max(float(sh["end"]) - float(sh["start"]), 0.2); tier = sh.get("motion_tier") or "still_motion"; still = _image(images, sh, i)
        job = dict(shot_id=sid, scene_no=sh.get("scene_no"), still=still, duration=round(dur + margin, 3), shot_seconds=round(dur, 3), fps=fps, size=size, seed=_seed(base, sid),
                   treatment=sh.get("treatment") or "push_in", tparams=dict(sh.get("tparams") or {}), env=sh.get("env"), intensity=sh.get("intensity") or inten)
        if tier == "graphic": jobs.append(dict(job, type="skip", reason="graphic (drawn by the app)", est_seconds=0.0)); continue
        if not still or not os.path.isfile(str(still)): jobs.append(dict(job, type="skip", reason="no picture found", est_seconds=0.0)); continue
        job["est_seconds"] = _est(job["duration"], fps, size, ms)
        if grade is not None:
            try: job["grade_vf"] = grade.filter_for(still)
            except Exception: pass
        ai = sh.get("ai_video")
        if ai:
            job["type"] = "ai_video_job"; job["ai_video"] = ai if isinstance(ai, dict) else {"requested": True}
            job["ai_video"] = dict(job["ai_video"], shot_id=sid, first_picture=still, seconds=round(dur, 2), prompt=sh.get("prompt_en") or sh.get("text") or "")
        else: job["type"] = "shot"
        if job["type"] == "shot":
            job["frames"] = bnd[i + 1] - bnd[i]
            jn = joins.get(str(sid))
            if jn and sid not in groups:
                job["tparams"] = dict(job["tparams"], join=jn)
                job["join"] = {"in": jn.get("edit_in"), "out": jn.get("edit_out")}
            lk = links.get(str(sid))
            if lk: job["link_next"] = dict(lk)
        if job["type"] == "shot" and sid in groups:
            job["strip"] = groups[sid][0]; job["strip_index"] = groups[sid][1]; job["start"] = round(float(sh["start"]), 4); job["end"] = round(float(sh["end"]), 4)
            job["strip_walker"] = (st.get("story_strip_walker", st.get("strip_walker", "")) or None); job["strip_seam"] = st.get("story_strip_seam", st.get("strip_seam", "torn"))
            job["est_seconds"] = round(dur * 0.12 + 0.3, 3)
        jobs.append(job)
    return jobs


# ---------------------------------------------------------------- resources
def _available_ram():
    try:
        import psutil; return int(psutil.virtual_memory().available)
    except Exception: pass
    try: return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except Exception: return 4 << 30


def cap_workers(requested, size=(1920, 1080)):
    per = MB_PER_SHOT_1080 * (1 << 20) * max(0.25, (size[0] * size[1]) / (1920 * 1080))
    return max(1, min(int(requested or 1), int(_available_ram() * 0.8 // per)))


# ---------------------------------------------------------------- state
class _State:
    def __init__(self, path):
        self.path = str(path); self.lock = threading.Lock(); self.data = {}
        try: self.data = json.loads(Path(self.path).read_text()).get("shots", {})
        except Exception: self.data = {}

    def get(self, sid):
        with self.lock: return dict(self.data.get(sid, {}))

    def set(self, sid, **kw):
        with self.lock:
            self.data.setdefault(sid, {}).update(kw)
            try:
                tmp = self.path + ".tmp"; Path(tmp).write_text(json.dumps({"shots": self.data})); os.replace(tmp, self.path)
            except Exception: pass


class _LinkState:
    """dict-like view of the shot state for '<id>+link' records (bridge.build_links wants state.get(key) / state[key] = rec)."""
    def __init__(self, st): self.st = st
    def get(self, k, d=None): return self.st.get(k) or d
    def __setitem__(self, k, v): self.st.set(k, **v)


def _key(job):
    try:
        c = _compose(); ck = c.job_key(job) if c and hasattr(c, "job_key") else ""
    except Exception: ck = ""
    try: st = os.stat(job["still"]); fs = f"{st.st_size}:{int(st.st_mtime)}"
    except Exception: fs = "?"
    own = json.dumps([job["still"], fs, job["duration"], job["fps"], list(job["size"]), job["seed"], job["treatment"], job["tparams"], job["env"], job["intensity"], job.get("grade_vf", "")], sort_keys=True, default=str)
    return hashlib.sha1((str(ck) + own).encode()).hexdigest()[:24]


def _cut(src, out, offset, dur, fps, size):
    """A shot's own clip out of its panel's slice (re-encoded: exact frames, any start)."""
    ff = shutil.which("ffmpeg") or "ffmpeg"; tmp = str(out) + ".part.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{max(0.0, offset):.4f}", "-i", src, "-t", f"{dur:.4f}", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                    "-pix_fmt", "yuv420p", "-an", tmp], check=True, capture_output=True, timeout=300)
    os.replace(tmp, out); return str(out)


def _strip_key(grp):
    return hashlib.sha1(json.dumps([[j["still"], os.path.getsize(j["still"]) if os.path.isfile(j["still"]) else 0, j["start"], j["end"], list(j["size"]), j["fps"], j.get("strip_walker"), j.get("strip_seam"), j["seed"], "strip-2"] for j in grp], default=str).encode()).hexdigest()[:24]


def _ok_file(p):
    try: return bool(p) and os.path.isfile(p) and os.path.getsize(p) > 0
    except OSError: return False


def _still_clip(job, out):
    ff = shutil.which("ffmpeg") or "ffmpeg"; w, h = job["size"]; tmp = str(out) + ".part.mp4"
    cmd = [ff, "-y", "-loglevel", "error", "-loop", "1", "-i", job["still"], "-t", f"{job['duration']:.3f}", "-r", str(job["fps"]),
           "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-an", tmp]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300); os.replace(tmp, out); return str(out)


# ---------------------------------------------------------------- render
def render_clips(jobs, out_dir, log=None, cancel=None, workers=1, puppet_renderer=None, progress=None, state_path=None) -> dict:
    log = log or (lambda *a, **k: None); os.makedirs(out_dir, exist_ok=True); jobs = list(jobs)
    todo = [j for j in jobs if j.get("type") != "skip"]; total = len(todo); all_todo = list(todo)
    for j in jobs:
        if j.get("type") == "skip": log(f"skip {j['shot_id']}: {j.get('reason')}")
    ai = [j["ai_video"] for j in jobs if j.get("type") == "ai_video_job" and j.get("ai_video")]
    if ai:
        tmp = os.path.join(out_dir, "ai_video_jobs.json.tmp"); Path(tmp).write_text(json.dumps(ai, indent=1, default=str)); os.replace(tmp, os.path.join(out_dir, "ai_video_jobs.json"))
    size = tuple(todo[0]["size"]) if todo else (1920, 1080); nw = cap_workers(workers, size)
    if nw < int(workers or 1): log(f"workers lowered {workers} -> {nw} (memory)")
    comp = _compose()
    if comp is not None:
        try: log(f"encoder: {comp.available_encoder()}")
        except Exception: pass
    state = _State(state_path or os.path.join(out_dir, "story_fast_state.json")); res = {}; lock = threading.Lock()
    prog = {"done": 0, "times": [], "frames": 0, "secs": 0.0}; ms1080 = _load_speed(); t_start = time.time()
    def report(msg=""):
        if not progress: return
        with lock:
            d = prog["done"]; rem = total - d
            if prog["times"]: eta = sum(prog["times"]) / len(prog["times"]) * rem / nw
            else: eta = sum(j["est_seconds"] for j in todo[d:]) / nw
        try: progress("clips", d, total, round(eta, 1), msg)
        except Exception: pass
    def finish(j, path, dt, real):
        with lock:
            res[j["shot_id"]] = path; prog["done"] += 1
            if real:
                prog["times"].append(dt); prog["frames"] += int(j["duration"] * j["fps"]); prog["secs"] += dt
        report(f"{j['shot_id']} done")
    def attempt(j, treat, out):
        c = _compose()
        if c is None: raise RuntimeError("compose module unavailable")
        job = dict(j, treatment=treat)
        t0 = time.time()
        try:
            if hasattr(c, "prepare"):
                if hasattr(c, "needs_depth"): c.prepare(j["still"], tuple(j["size"]), need_depth=c.needs_depth(treat, j["still"]))
                else: c.prepare(j["still"], tuple(j["size"]))
        except Exception as e:
            if _is_cancel(e): raise
        if _TIMER: _TIMER.add("image_prep", time.time() - t0)
        t1 = time.time()
        try: return c.render_shot(job, out, cancel=cancel)
        finally:
            if _TIMER: _TIMER.add("scene_render", time.time() - t1)
    def one(j):
        sid = j["shot_id"]; out = os.path.join(out_dir, f"{sid}.mp4")
        if cancel and cancel(): raise Cancelled("clip render cancelled")
        key = _key(j); s = state.get(sid)
        if s.get("status") == "done" and s.get("key") == key and _ok_file(s.get("path")) and s["path"] == out:
            finish(j, out, 0, False); return
        t = time.time(); att = 0; err = None; path = None; used = j["treatment"]
        state.set(sid, key=key, status="running", path=out, error=None, attempts=0)
        for treat, tries in [(j["treatment"], 1 + RETRIES)] + [(x, 1) for x in FALLBACK_TREATMENTS if x != j["treatment"]]:
            for _ in range(tries):
                if cancel and cancel(): state.set(sid, status="failed", error="cancelled"); raise Cancelled("clip render cancelled")
                att += 1
                try:
                    r = attempt(j, treat, out)
                    if _ok_file(str(r)): path = str(r); used = treat; break
                    err = "empty output"
                except Exception as e:
                    if _is_cancel(e): state.set(sid, status="failed", error="cancelled", attempts=att); raise Cancelled("clip render cancelled")
                    err = f"{type(e).__name__}: {e}"; log(f"{sid}: {treat} failed ({err})")
            if path: break
        real = True
        if not path:
            log(f"{sid}: all treatments failed; making a still-frame clip")
            try: path = _still_clip(j, out); used = "still"
            except Exception as e: err = f"still clip failed: {e}"
        dt = time.time() - t
        if path:
            state.set(sid, key=key, status="done", path=path, seconds=round(dt, 3), error=None, attempts=att, treatment=used)
            if used != "still": log(f"{sid} done in {dt:.1f}s (est {j.get('est_seconds')}s)" + ("" if used == j["treatment"] else f" with fallback {used}"))
            finish(j, path, dt, real)
        else:
            state.set(sid, key=key, status="failed", error=err, attempts=att); log(f"{sid}: no clip ({err})"); finish(j, None, dt, False)
            with lock: res.pop(sid, None)
    def render_strips():
        by = {}
        for j in todo:
            if j.get("strip"): by.setdefault(j["strip"], []).append(j)
        def one_strip(gid, grp):
            grp.sort(key=lambda j: j["strip_index"])
            if all(_ok_file(state.get(j["shot_id"]).get("path")) and state.get(j["shot_id"]).get("status") == "done" and state.get(j["shot_id"]).get("key") == _strip_key(grp) for j in grp):
                for j in grp: finish(j, state.get(j["shot_id"])["path"], 0.0, False)
                return
            if cancel and cancel(): raise Cancelled("clip render cancelled")
            t = time.time(); key = _strip_key(grp)
            try:
                from health_cinema.puppet import travel
                t0 = grp[0]["start"]; fps = grp[0]["fps"]; pan = {}
                for j in grp: pan.setdefault(j["strip_index"], []).append(j)
                windows = {f"p{k}": (min(j["start"] for j in v) - t0, max(j["end"] for j in v) - t0) for k, v in pan.items()}
                stills = {f"p{k}": v[0]["still"] for k, v in pan.items()}
                sl = travel.render_travel_slices(stills, windows, os.path.join(out_dir, "strips"), margin=0.0, fps=fps, size=tuple(grp[0]["size"]), walker=grp[0].get("strip_walker"),
                                                 seed=grp[0]["seed"], seam_style=grp[0].get("strip_seam") or "torn", cancel=cancel, zoom=(1.0, 1.0))      # whole picture visible: nothing cropped
                paths = {}
                for k, v in pan.items():
                    src = sl[f"p{k}"]; p0 = min(x["start"] for x in v)
                    for j in v:
                        paths[j["shot_id"]] = src if len(v) == 1 else _cut(src, os.path.join(out_dir, f"{j['shot_id']}.mp4"), j["start"] - p0, j["duration"], fps, tuple(j["size"]))
                if not all(_ok_file(paths.get(j["shot_id"])) for j in grp): raise RuntimeError("strip slices missing")
            except Exception as e:
                if _is_cancel(e) or type(e).__name__ == "TravelCancelled": raise Cancelled("clip render cancelled")
                log(f"strip {gid} failed ({type(e).__name__}: {e}); its shots use their own camera moves")
                for j in grp: j.pop("strip", None)
                return
            dt = time.time() - t
            for j in grp:
                state.set(j["shot_id"], key=key, status="done", path=paths[j["shot_id"]], seconds=round(dt / len(grp), 3), error=None, attempts=1, treatment="strip")
                finish(j, paths[j["shot_id"]], dt / len(grp), False)
            log(f"strip {gid}: {len(grp)} pictures glued, rendered in {dt:.1f}s")
        sw = max(1, min(nw, len(by)))
        if sw <= 1:
            for gid, grp in by.items(): one_strip(gid, grp)
        else:
            with ThreadPoolExecutor(max_workers=sw) as ex:
                for f in [ex.submit(one_strip, g, grp) for g, grp in by.items()]: f.result()
    report("start")
    try:
        render_strips()
        todo = [j for j in todo if not (j.get("strip") and res.get(j["shot_id"]))]
        if nw <= 1:
            for j in todo: one(j)
        else:
            with ThreadPoolExecutor(max_workers=nw) as ex:
                it = iter(todo); pend = set(); err = None
                import concurrent.futures as cf
                while True:
                    while len(pend) < nw and err is None:
                        j = next(it, None)
                        if j is None: break
                        pend.add(ex.submit(one, j))
                    if not pend: break
                    dn, pend = cf.wait(pend, return_when=cf.FIRST_COMPLETED)
                    for f in dn:
                        e = f.exception()
                        if e and err is None: err = e
                if err: raise err
    finally:
        if prog["frames"] and prog["secs"] > 0:
            px = size[0] * size[1] / (1920 * 1080)
            _save_speed((prog["secs"] * nw / prog["frames"]) * 1000.0 / px if nw > 1 else prog["secs"] / prog["frames"] * 1000.0 / px)
    done = {k: res[k] for k in [j["shot_id"] for j in all_todo if res.get(j["shot_id"])]}
    try:
        pairs = {j["shot_id"]: j["link_next"] for j in all_todo if j.get("link_next") and not j.get("strip") and j["shot_id"] in done and j["link_next"]["to"] in done}
        if pairs:
            sys.path.insert(0, str(ROOT)); from story_fast import bridge
            t_l = time.time(); fps0 = all_todo[0]["fps"]
            lk = bridge.build_links(pairs, done, out_dir, fps0, size, {j["shot_id"]: j["frames"] for j in all_todo if j.get("frames")}, state=_LinkState(state), save_state=None,
                                    log=log, cancel=cancel, workers=min(nw, 3))
            done.update(lk)
            log(f"dissolve links: {len(lk)}/{len(pairs)} in {time.time() - t_l:.1f}s")
    except Exception as e:
        if _is_cancel(e) or type(e).__name__ == "BridgeCancelled": raise Cancelled("clip render cancelled")
        log(f"dissolve links skipped ({type(e).__name__}: {e}); plain cuts")
    log(f"clips: {sum(1 for v in res.values() if v)}/{total} ready in {time.time() - t_start:.1f}s")
    return done


# ---------------------------------------------------------------- timeline
def assemble_timeline(shots, clips, settings=None) -> dict:
    st = dict(settings or {}); fps = int(st.get("fps", 30)); shots = list(shots)
    if not shots: return {"segments": [], "skipped": [], "fps": fps, "frames": 0, "seconds": 0.0}
    bound = [int(round(float(shots[0]["start"]) * fps))] + [int(round(float(s["end"]) * fps)) for s in shots]
    for i in range(1, len(bound)): bound[i] = max(bound[i], bound[i - 1])
    segs = []; pending = {}
    try: from story_fast.bridge import link_frames
    except Exception: link_frames = lambda p: 0
    for i, s in enumerate(shots):
        f0, f1 = bound[i], bound[i + 1]
        if f1 <= f0: continue
        sid = s["shot_id"]; p = clips.get(sid)
        kind = "shot" if p else ("graphic" if s.get("motion_tier") == "graphic" else "gap")
        clip_in = 0.0
        lk = pending.pop(sid, None)
        if lk and p and f1 - f0 >= lk[0] + 2:
            # a real cross-dissolve: the link takes this shot's first k frames (A's tail dissolving into B's head), B plays on from its frame k
            k, lp, _a = lk
            segs.append(dict(kind="link", shot_id=lk[2] + "+link", path=lp, start_frame=f0, end_frame=f0 + k, frames=k, start=f0 / fps, end=(f0 + k) / fps, duration=k / fps, clip_in=0.0))
            f0 += k; clip_in = k / fps
        segs.append(dict(kind=kind, shot_id=sid, path=p or None, start_frame=f0, end_frame=f1, frames=f1 - f0, start=f0 / fps, end=f1 / fps, duration=(f1 - f0) / fps, clip_in=clip_in))
        lp = clips.get(f"{sid}+link")
        if lp and p and os.path.isfile(str(lp)) and link_frames(lp) > 0 and i + 1 < len(shots) and clips.get(shots[i + 1]["shot_id"]):
            pending[shots[i + 1]["shot_id"]] = (link_frames(lp), lp, sid)
    total = sum(g["frames"] for g in segs)
    return {"segments": segs, "skipped": [], "fps": fps, "frames": total, "seconds": total / fps}
