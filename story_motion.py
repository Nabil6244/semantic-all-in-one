"""Story motion planner: turns Agent B's shot list + the stills into moving clips and picture-to-picture link clips.

    jobs = plan_clips(shots, images, settings)               -> list[dict]   (cheap, no rendering; every job has est_seconds)
    paths = render_clips(jobs, out_dir, log, cancel, workers=1) -> {shot_id: mp4, "<shot_id>+link": mp4}
    segs = assemble_timeline(shots, paths, settings)         -> contiguous segments covering exactly shots[0].start .. shots[-1].end
    estimate_total(jobs) -> seconds;  ai_video_jobs(jobs) -> the records for the later Flow step

SHOT (Agent B): {"shot_id","scene_no","start","end","text","subject","prompt_en","picture","character","motion_tier","camera","transition_in","link_to_next"}.
images: {shot_id | scene_no | str(scene_no): still path} (a list aligned with shots also works).

settings (all optional): size (1920,1080), fps 30, seed 0, margin 0.5 (extra seconds rendered after each shot), intensity 'medium', link_seconds 1.2 (clamped 1.0..1.6),
  link_split 0.5 (share of the link taken from the END of shot N; the rest from the START of shot N+1), transitions_as_links True (a transition_in other than 'cut' on shot N+1
  also gets a link clip), time_budget_s None (drop the least valuable links when the estimated render time is over it), puppet_renderer None (callable(job) -> mp4 for
  motion_tier 'puppet'; without it the shot gets the still_motion fallback), cache hints are inherited from motion/links (their own cache dirs).

TIERS: still_motion / hold_alive-camera -> motion.render_motion;  link -> the shot's motion clip + a link clip between it and the next shot;  ai_video -> an 'ai_video_job' record
(first_picture, last_picture, prompt, seconds) AND the still_motion fallback so the timeline is never empty;  puppet -> injected callable or fallback;  graphic -> skipped (the app draws it).

TIMELINE RULE. A link of L seconds (rounded to whole frames) is taken from the tail of shot N and the head of shot N+1, never added:
  link occupies [end_N - tail, end_N + head] with tail = round(L*split) frames and head = L - tail frames.
  shot N plays its own clip for [start_N + head_prev, end_N - tail]; shot N+1 starts at clip time `head` (clip_in), so it carries on from where the link left it.
  Every boundary is a whole frame (round(t*fps)), so segments tile the span exactly and the sum of durations equals shots[-1].end - shots[0].start (= the audio length).
  A link is dropped (hard cut, reported in `skipped`) when it would leave a shot shorter than 0.4 s of its own picture."""
from __future__ import annotations
import os, sys, threading, time, zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_cinema.puppet import links, motion

CAMERA_MODE = {"push_in": "push_in", "pull_out": "pull_out", "drift_l": "drift_l", "drift_r": "drift_r", "diag": "diag_in", "hold_alive": "push_in"}
LINK_FOR = {"match_cut": "match_cut", "walk_through": "push_through", "push_through": "push_through", "torn_wipe": "torn_wipe", "doorway_push": "push_through",
            "dissolve": "dissolve_alive", "whip": "whip"}
MOTION_MS_1080 = 150           # measured ms/frame of motion.render_motion at 1080p (see docs/story/links.md); estimate only
MIN_OWN = 0.4                  # seconds of its own picture a shot must keep when links eat its head/tail
Cancelled = motion.Cancelled

def _seed(base, shot_id) -> int: return int(base) * 1000 + (zlib.crc32(str(shot_id).encode()) % 997)

def _image(images, shot, i):
    if isinstance(images, (list, tuple)): return images[i] if i < len(images) else None
    for k in (shot.get("shot_id"), shot.get("scene_no"), str(shot.get("scene_no"))):
        if k is not None and k in images and images[k]: return str(images[k])
    return None

def _motion_ms(size): return MOTION_MS_1080 * (size[0] * size[1]) / (1920 * 1080)

def _est_motion(dur, fps, size): return round(dur * fps * (_motion_ms(size) + links.ENCODE_MS_1080 * (size[0] * size[1]) / (1920 * 1080)) / 1000.0 + .8, 2)

def _link_kind(shot, nxt, settings):
    l = shot.get("link_to_next")
    if isinstance(l, dict) and l.get("kind") in LINK_FOR: return LINK_FOR[l["kind"]], l.get("note")
    if shot.get("motion_tier") == "link" or settings.get("transitions_as_links", True):
        k = LINK_FOR.get((nxt or {}).get("transition_in"))
        if k and (shot.get("motion_tier") == "link" or settings.get("transitions_as_links", True)): return k, None
    if shot.get("motion_tier") == "link": return "dissolve_alive", None
    return None, None

def _link_len(settings, fps) -> int:
    L = min(max(float(settings.get("link_seconds", 1.2)), 1.0), 1.6); return max(2, int(round(L * fps)))

def plan_clips(shots, images, settings=None) -> list:
    """Jobs in timeline order. type: 'motion' | 'ai_video_job' (also renders a motion fallback: job['fallback_motion']) | 'puppet' | 'link' | 'skip'."""
    st = dict(settings or {}); size = tuple(st.get("size", (1920, 1080))); fps = int(st.get("fps", 30)); base = int(st.get("seed", 0)); margin = float(st.get("margin", .5))
    inten = st.get("intensity", "medium"); jobs = []; shots = list(shots)
    for i, sh in enumerate(shots):
        sid = sh["shot_id"]; dur = max(float(sh["end"]) - float(sh["start"]), 0.2); tier = sh.get("motion_tier") or "still_motion"; still = _image(images, sh, i)
        cam = sh.get("camera") or "push_in"; mode = CAMERA_MODE.get(cam, "push_in")
        if mode == "push_in" and cam == "diag": mode = "diag_in"
        if cam == "diag" and zlib.crc32(str(sid).encode()) % 2: mode = "diag_out"
        base_job = dict(shot_id=sid, scene_no=sh.get("scene_no"), still=still, duration=round(dur + margin, 3), shot_seconds=round(dur, 3), fps=fps, size=size, seed=_seed(base, sid),
                        camera=cam, tier=tier, params={"mode": mode, "intensity": "low" if cam == "hold_alive" else inten})
        if tier == "graphic": jobs.append(dict(base_job, type="skip", reason="graphic (drawn by the app)", est_seconds=0.0)); continue
        if not still or not os.path.isfile(str(still)): jobs.append(dict(base_job, type="skip", reason="no still found", est_seconds=0.0)); continue
        est = _est_motion(base_job["duration"], fps, size)
        if tier == "puppet":
            j = dict(base_job, type="puppet", est_seconds=est, fallback="still_motion"); jobs.append(j)
        elif tier == "ai_video":
            nxt = shots[i + 1] if i + 1 < len(shots) else None; last = _image(images, nxt, i + 1) if nxt else None
            jobs.append(dict(base_job, type="ai_video_job", first_picture=still, last_picture=last or still, prompt=sh.get("prompt_en") or sh.get("text") or "",
                             seconds=round(dur, 2), est_seconds=est, fallback="still_motion"))
        else: jobs.append(dict(base_job, type="motion", est_seconds=est))
    # link clips between consecutive renderable shots
    by_id = {j["shot_id"]: j for j in jobs}; L = _link_len(st, fps); split = float(st.get("link_split", .5)); links_planned = []
    for i in range(len(shots) - 1):
        a, b = shots[i], shots[i + 1]; ja, jb = by_id.get(a["shot_id"]), by_id.get(b["shot_id"])
        if not ja or not jb or ja["type"] == "skip" or jb["type"] == "skip": continue
        kind, note = _link_kind(a, b, st)
        if not kind or ja["still"] == jb["still"]: continue
        tail = int(round(L * split)); head = L - tail
        la = float(a["end"]) - float(a["start"]); lb = float(b["end"]) - float(b["start"])
        if la - tail / fps < MIN_OWN or lb - head / fps < MIN_OWN: continue
        info = links.resolve_link(ja["still"], jb["still"], kind) if st.get("resolve", True) else {"kind": kind, "fallback": False}
        links_planned.append(dict(type="link", shot_id=a["shot_id"] + "+link", from_shot=a["shot_id"], to_shot=b["shot_id"], kind=info["kind"], asked=kind, fallback=info.get("fallback", False),
                                  still_a=ja["still"], still_b=jb["still"], frames=L, tail_frames=tail, head_frames=head, duration=L / fps, fps=fps, size=size,
                                  seed=_seed(base, a["shot_id"] + ">" + b["shot_id"]), params={"intensity": inten}, note=note, est_seconds=links.estimate_seconds(info["kind"], L / fps, fps, size),
                                  resolved=info))
    budget = st.get("time_budget_s")
    if budget:
        total = sum(j["est_seconds"] for j in jobs) + sum(l["est_seconds"] for l in links_planned)
        order = sorted(range(len(links_planned)), key=lambda x: (links_planned[x]["kind"] in ("push_through", "torn_wipe"), -links_planned[x]["est_seconds"]))   # drop plain ones first
        dropped = set()
        for x in order:
            if total <= budget: break
            total -= links_planned[x]["est_seconds"]; dropped.add(x)
        links_planned = [dict(l, type="skip", reason="time budget") if x in dropped else l for x, l in enumerate(links_planned)]
    # interleave in timeline order
    out = []; lk = {l["from_shot"]: l for l in links_planned}
    for j in jobs:
        out.append(j)
        if j["shot_id"] in lk: out.append(lk[j["shot_id"]])
    return out

def estimate_total(jobs, workers=1) -> float:
    return round(sum(j.get("est_seconds", 0.0) for j in jobs) / max(1, workers), 2)

def ai_video_jobs(jobs) -> list:
    return [{"type": "ai_video_job", "shot_id": j["shot_id"], "first_picture": j["first_picture"], "last_picture": j["last_picture"], "prompt": j["prompt"], "seconds": j["seconds"]}
            for j in jobs if j["type"] == "ai_video_job"]

# ---------------------------------------------------------------- continuity: where the neighbouring motion clips are at the link ends
_CAM_LOCK = threading.Lock(); _RIGS: dict = {}

def _cam(job, t):
    """(z, fx, fy) of the motion clip of `job` at clip time t (extrapolated outside 0..duration), as fractions of the frame."""
    key = (job["still"], job["duration"], job["fps"], tuple(job["size"]), job["seed"], tuple(sorted(job["params"].items())))
    with _CAM_LOCK:
        rig = _RIGS.get(key)
        if rig is None:
            if len(_RIGS) > 6: _RIGS.clear()
            rig = _RIGS[key] = motion._Rig(job["still"], job["size"], job["fps"], job["duration"], job["seed"], dict(job["params"]))
        z, px, py, _, _ = rig.cam(t); return (float(z), float(px / rig.size[0]), float(py / rig.size[1]))

def _link_params(lj, by_id):
    ja, jb = by_id.get(lj["from_shot"]), by_id.get(lj["to_shot"]); p = dict(lj["params"])
    if not ja or not jb or ja["type"] == "skip" or jb["type"] == "skip": return p
    Lt = lj["frames"] / lj["fps"]; tail = lj["tail_frames"] / lj["fps"]; head = lj["head_frames"] / lj["fps"]
    try:
        ta = ja["shot_seconds"] - tail                    # A's clip time at the link start; the link then runs on for Lt
        tb = head                                         # B's clip time at the link end
        p["cam_a"] = [list(_cam(ja, ta)), list(_cam(ja, ta + Lt))]; p["cam_b"] = [list(_cam(jb, tb - Lt)), list(_cam(jb, tb))]
    except Exception:
        pass                                              # continuity is an improvement, never a reason to fail
    return p

# ---------------------------------------------------------------- rendering
def _run_motion(j, out_dir, cancel):
    out = Path(out_dir) / f"{j['shot_id']}.mp4"
    return str(motion.render_motion(j["still"], out, j["duration"], fps=j["fps"], size=j["size"], seed=j["seed"], params=dict(j["params"]), cancel=cancel))

def render_clips(jobs, out_dir, log=None, cancel=None, workers=1, puppet_renderer=None) -> dict:
    """Render every job. Returns {shot_id: path} for shot clips and {"<shot_id>+link": path} for link clips. Skipped jobs are absent. Raises Cancelled when cancel() turns true
    (finished clips stay in the cache; nothing partial is left behind). A link that fails is logged and left out (hard cut), a shot clip that fails raises."""
    log = log or (lambda *a, **k: None); os.makedirs(out_dir, exist_ok=True); res: dict = {}; lock = threading.Lock(); by_id = {j["shot_id"]: j for j in jobs if j["type"] != "link"}
    def one(j):
        if cancel and cancel(): raise Cancelled("clip render cancelled")
        t = time.time()
        if j["type"] == "skip": log(f"skip {j['shot_id']}: {j.get('reason')}"); return
        if j["type"] == "link":
            p = _link_params(j, by_id)
            try: path = links.render_link(j["still_a"], j["still_b"], j["kind"], Path(out_dir) / f"{j['shot_id']}.mp4", duration=j["duration"], fps=j["fps"], size=j["size"], seed=j["seed"], params=p, cancel=cancel)
            except Cancelled: raise
            except Exception as e: log(f"link {j['shot_id']} failed ({e}); using a cut"); return
        elif j["type"] == "puppet" and (puppet_renderer or j.get("puppet_renderer")):
            path = (puppet_renderer or j["puppet_renderer"])(j)
        else:
            path = _run_motion(j, out_dir, cancel)
        with lock: res[j["shot_id"]] = str(path)
        log(f"{j['type']} {j['shot_id']} done in {time.time() - t:.1f}s (est {j.get('est_seconds')}s)")
    todo = [j for j in jobs if j["type"] != "link"]; lnk = [j for j in jobs if j["type"] == "link"]
    for batch in (todo, lnk):                              # shot clips first so link continuity can read their cameras without racing the cache
        if workers <= 1:
            for j in batch: one(j)
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(one, j) for j in batch]
                for f in futs: f.result(timeout=7200)
    return {k: res[k] for k in [j["shot_id"] for j in jobs if j["shot_id"] in res]}

# ---------------------------------------------------------------- timeline
def assemble_timeline(shots, clips, settings=None) -> dict:
    """-> {"segments": [...], "skipped": [...], "fps", "frames", "seconds"}. Segment: {kind 'shot'|'link'|'graphic'|'gap', shot_id, path|None, start_frame, end_frame, frames, start, end,
    duration, clip_in (seconds into that clip), link_kind (links)}. Segments tile [round(shots[0].start*fps), round(shots[-1].end*fps)) with no gap or overlap."""
    st = dict(settings or {}); fps = int(st.get("fps", 30)); split = float(st.get("link_split", .5)); shots = list(shots); n = len(shots)
    bound = [int(round(float(shots[0]["start"]) * fps))] + [int(round(float(s["end"]) * fps)) for s in shots]   # frame boundaries between shots (shot i = bound[i]..bound[i+1])
    for i in range(1, n): bound[i] = max(bound[i], bound[i - 1])
    tail = [0] * n; head = [0] * n; lk = {}; skipped = []
    for i in range(n - 1):
        a, b = shots[i], shots[i + 1]; key = a["shot_id"] + "+link"
        if key not in clips: continue
        # the frames the link spans come from the real clip file when we can read them; the plan's frame count otherwise
        frames = int(st.get("link_frames_" + key, 0)) or _link_frames(clips[key], fps) or _link_len(st, fps)
        t = int(round(frames * split)); h = frames - t
        la = bound[i + 1] - bound[i] - tail[i] - head[i]; lb = bound[i + 2] - bound[i + 1] - h
        if la - t < MIN_OWN * fps or lb < MIN_OWN * fps:
            skipped.append({"shot_id": key, "reason": "shots too short for the link"}); continue
        tail[i] = t; head[i + 1] = h; lk[i] = (frames, t, h)
    segs = []
    def seg(kind, sid, path, f0, f1, clip_in=0.0, **kw):
        if f1 > f0: segs.append(dict(kind=kind, shot_id=sid, path=path, start_frame=f0, end_frame=f1, frames=f1 - f0, start=f0 / fps, end=f1 / fps, duration=(f1 - f0) / fps, clip_in=round(clip_in, 4), **kw))
    for i, s in enumerate(shots):
        sid = s["shot_id"]; f0 = bound[i] + head[i]; f1 = bound[i + 1] - tail[i]
        p = clips.get(sid)
        kind = "shot" if p else ("graphic" if s.get("motion_tier") == "graphic" else "gap")
        seg(kind, sid, p, f0, f1, clip_in=head[i] / fps)
        if i in lk:
            frames, t, h = lk[i]; seg("link", sid + "+link", clips[sid + "+link"], bound[i + 1] - t, bound[i + 1] + h, 0.0, link_kind=None, from_shot=sid, to_shot=shots[i + 1]["shot_id"])
    total = sum(g["frames"] for g in segs)
    return {"segments": segs, "skipped": skipped, "fps": fps, "frames": total, "seconds": total / fps}

def _link_frames(path, fps):
    try:
        import subprocess, json
        o = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries", "stream=nb_read_frames", "-of", "json", str(path)], capture_output=True, text=True, timeout=30).stdout
        return int(json.loads(o)["streams"][0]["nb_read_frames"])
    except Exception: return 0
