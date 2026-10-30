"""Tests for story_fast.continuity / bridge and the runner integration (stub compose). Run: python3 test_story_continuity.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from story_fast import bridge, continuity as C, direct, runner

FAILS = []


def ok(name, cond, extra=""):
    if cond:
        print("ok  ", name)
    else:
        print("FAIL", name, extra)
        FAILS.append(name)


def S(i, text, en="", dur=3.0, loc=None, same=False, **kw):
    d = {"shot_id": "s%03d" % i, "scene_no": i, "start": i * dur, "end": (i + 1) * dur, "text": text, "prompt_en": en, "subject": "",
         "picture": "p%d" % i, "motion_tier": "still_motion", "treatment": "push_in", "transition_in": "cut",
         "continuity": {"location": loc or "room", "characters": [], "same_location_as_prev": same, "carry_dir": None}}
    d.update(kw)
    return d


def edit(a, b, **kw):
    return C.plan_edits([a, b], kw.get("settings"), kw.get("images"))[1]


# ---------------------------------------------------------------- one pair at a time: English
e = edit(S(0, "He sat alone in the dark apartment."), S(1, "He picked up his phone and stared at the screen.", same=True))
ok("screen cue -> screen_or_chart_focus", e["type"] == "screen_or_chart_focus" and e["realize"] == "camera" and e["strength"] >= 0.55, e)
ok("reason is recorded", isinstance(e["reason"], str) and "screen" in e["reason"], e)

e = edit(S(0, "She ran down the alley, chased by two men."), S(1, "He sprinted after her across the rooftops.", same=True))
ok("both shots running -> action_continues", e["type"] == "action_continues" and e["dir"] in ("l", "r"), e)

e = edit(S(0, "The old merchant walked toward the harbour.", loc="market"), S(1, "At the dock he stepped aboard the ship.", loc="ship", same=False))
ok("walks into another place -> follow_into_location", e["type"] == "follow_into_location", e)

e = edit(S(0, "Hands trembling, he opened the box.", en="Close-up of hands on a wooden box"), S(1, "Inside the old study, dust covered everything.", en="Interior of a study", same=True))
ok("close-up then context -> object_closeup_to_context", e["type"] == "object_closeup_to_context", e)

e = edit(S(0, "The city sprawled to the horizon.", en="Wide establishing aerial shot of the city skyline"),
         S(1, "Anna watched it from her window.", en="Anna at a window, face in profile", same=True))
ok("wide then person -> wide_to_close", e["type"] == "wide_to_close", e)

e = edit(S(0, "A single coin rolled across the table.", same=True), S(1, "Another coin dropped into the jar.", same=True))
ok("same object -> match_cut", e["type"] == "match_cut" and "coin" in e["reason"], e)

e = edit(S(0, "Nothing moved in the quiet room.", same=True), S(1, "The clock kept ticking.", same=True))
ok("no cue -> simple_cut, strength 0", e["type"] == "simple_cut" and e["strength"] == 0.0 and e["realize"] == "none", e)

e = edit(S(0, "The village slept under the stars."), S(1, "Years later, the village was a city.", same=True))
ok("time jump -> scene_break (the only dip)", e["type"] == "scene_break" and e["realize"] == "dip", e)

e = edit(S(0, "The kitchen was bright and warm this morning.", same=True), S(1, "By evening, the same kitchen was quiet.", same=True))
ok("time of day moves on -> real dissolve", e["type"] == "dissolve" and e["realize"] == "link", e)

# ---------------------------------------------------------------- Hindi (Devanagari + romanised)
e = edit(S(0, "वह अँधेरे कमरे में अकेला बैठा था।"), S(1, "उसने अपने फोन की स्क्रीन देखी।", same=True))
ok("hindi screen cue", e["type"] == "screen_or_chart_focus", e)
e = edit(S(0, "वह जंगल में दौड़ता गया।", loc="forest"), S(1, "घुड़सवार भागता हुआ आगे निकला।", loc="forest", same=True))
ok("hindi action continues", e["type"] == "action_continues", e)
e = edit(S(0, "राजा किले की ओर चला।", loc="castle"), S(1, "वह दरवाज़े से महल के अंदर पहुँचा।", loc="palace", same=False))
ok("hindi follow into location", e["type"] == "follow_into_location", e)
e = edit(S(0, "सालों बाद भी गाँव वैसा ही था।"), S(1, "कुछ सालों बाद वहाँ शहर बस गया।", same=True))
ok("hindi time jump -> scene_break", e["type"] == "scene_break", e)
e = edit(S(0, "सुबह रसोई में रोशनी थी।", same=True), S(1, "शाम तक रसोई शांत हो गई।", same=True))
ok("hindi morning -> evening dissolve", e["type"] == "dissolve", e)
e = edit(S(0, "Raju ne phone uthaya.", same=True), S(1, "Phir usne mobile ki screen dekhi.", same=True))
ok("romanised hindi screen cue", e["type"] == "screen_or_chart_focus", e)
e = edit(S(0, "शामिल होने की बात थी।", same=True), S(1, "उसने कुछ कहा नहीं।", same=True))
ok("'शामिल' is not 'शाम' (no false time of day)", e["type"] == "simple_cut", e)

# ---------------------------------------------------------------- the whole film: pacing, determinism, contract
TEXTS = ["He picked up the phone and looked at the screen.", "Nothing moved in the room.", "A coin rolled across the table.", "Another coin fell.",
         "They ran through the market, chased by guards.", "He sprinted across the square.", "At the gate he stepped inside.", "The hall was silent.",
         "Years later, the city had grown.", "वह स्क्रीन देखता रहा।", "उसने दरवाज़े से अंदर कदम रखा।", "सुबह धूप थी।", "शाम को सब शांत था।"] * 8
shots = [S(i, TEXTS[i % len(TEXTS)], dur=2.0 + (i % 4) * 0.7, same=bool(i % 3)) for i in range(len(TEXTS))]
t = 0.0
for s in shots:
    d = s["end"] - s["start"]
    s["start"], s["end"] = t, t + d
    t += d
ed = C.plan_edits(shots, {})
ed2 = C.plan_edits(shots, {})
ok("deterministic", json.dumps(ed, sort_keys=True) == json.dumps(ed2, sort_keys=True))
ok("one edit per shot", len(ed) == len(shots) and ed[0]["type"] == "simple_cut")
ok("every edit has type / reason / strength", all(x["type"] in C.EDITS and x["reason"] and isinstance(x["strength"], float) for x in ed))
cam = [x for x in ed if x["realize"] == "camera"]
ok("camera joins stay a share of the cuts (<= %.0f%%)" % (C.MAX_CAMERA_SHARE * 100 + 2), len(cam) <= C.MAX_CAMERA_SHARE * len(ed) + 3, len(cam))
run = worst = 0
for x in ed:
    run = run + 1 if x["realize"] == "camera" else 0
    worst = max(worst, run)
ok("never more than %d camera joins in a row" % C.MAX_CAMERA_RUN, worst <= C.MAX_CAMERA_RUN, worst)
lk = [i for i, x in enumerate(ed) if x["realize"] == "link"]
ok("dissolves rare and spaced", len(lk) <= max(1, int(C.MAX_LINK_SHARE * len(ed))) and all(b - a >= C.MIN_LINK_GAP for a, b in zip(lk, lk[1:])), lk)

orig = [dict(x) for x in shots]
src = json.dumps(shots, sort_keys=True)
C.plan_edits(shots, {})
ok("plan_edits does not mutate", json.dumps(shots, sort_keys=True) == src)
# a plain dip becomes a cut unless it is a true scene break
for s in shots:
    s["transition_in"] = "dissolve"
C.apply(shots, ed, {})
dips = [s for s in shots if s["transition_in"] in ("dissolve", "soft", "fade")]
ok("no dip through black except at scene breaks", all(s["continuity_edit"]["type"] == "scene_break" for s in dips) and len(dips) == sum(1 for x in ed if x["type"] == "scene_break"))
ok("shot['continuity_edit'] = {type, reason, strength}", all({"type", "reason", "strength"} <= set(s["continuity_edit"]) for s in shots))

# camera spec: out/in pairs belong to ONE edit, bounded, and match the cut times
cj = C.camera_joins(shots, ed, 30)
ok("every realised camera edit has an out on A and an in on B", all(("out" in cj[str(shots[i - 1]['shot_id'])]) and ("in" in cj[str(shots[i]['shot_id'])]) for i, x in enumerate(ed) if x["realize"] == "camera"))
ok("D is the shot length", all(abs(cj[s["shot_id"]]["D"] - (s["end"] - s["start"])) < 1e-3 for s in shots if s["shot_id"] in cj))
lp = C.link_pairs(shots, ed, 30)
ok("link pairs name the next shot", all(v["to"] and v["frames"] >= 2 for v in lp.values()) and len(lp) == len(lk))

# ---------------------------------------------------------------- direct(): continuity is part of the director (and can be switched off)
dr = direct.direct([dict(s, transition_in="cut") for s in shots], {}, 3)
ok("direct() writes continuity_edit on every shot", all("continuity_edit" in s for s in dr["shots"]))
ok("direct() stats carry the continuity summary", dr["stats"].get("continuity", {}).get("types"))
dips = [s for s in dr["shots"] if s["transition_in"] in ("dissolve", "soft", "fade")]
ok("direct(): dips only at scene breaks", all(s["continuity_edit"]["type"] == "scene_break" for s in dips))
off = direct.direct([{k: v for k, v in s.items() if k != "continuity_edit"} for s in shots], {"story_continuity": "off"}, 3)
ok("story_continuity off: no continuity_edit", all("continuity_edit" not in s for s in off["shots"]))

# ---------------------------------------------------------------- runner integration with a stub compose + real ffmpeg for the link
TMP = tempfile.mkdtemp(prefix="sfc_")
runner.SPEED_PATH = os.path.join(TMP, "speed.json")
ff = shutil.which("ffmpeg")


def mk_clip(path, dur, color, fps=30, size="320x180"):
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:r={fps}:d={dur}", "-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True)


class Stub:
    def __init__(self): self.calls = []
    def job_key(self, job): return "k" + json.dumps(job.get("tparams"), sort_keys=True, default=str)
    def available_encoder(self): return "stub"
    def prepare(self, still, size, cache_dir=None, need_depth=True): pass
    def render_shot(self, job, out, cancel=None, progress=None):
        self.calls.append(job)
        mk_clip(out, job["duration"], "red" if len(self.calls) % 2 else "blue", job["fps"], "%dx%d" % tuple(job["size"]))
        return str(out)


def story(n=8, d=3.0):
    imgs, sh = {}, []
    for i in range(n):
        p = os.path.join(TMP, f"img{i}.png")
        open(p, "wb").write(b"png%d" % i)
        sid = f"s{i:03d}"
        imgs[sid] = p
        sh.append(S(i, "", dur=d, treatment="push_in", tparams={"amount": .5, "ease": "smooth"}))
    return sh, imgs


sh, imgs = story()
texts = ["He opened the laptop and stared at the screen.", "The screen glowed.", "The room was warm and bright this morning.", "By evening the same room was dim and quiet.",
         "He walked out of the house.", "Outside, the street was empty.", "A coin rolled.", "Another coin fell."]
for s, t_ in zip(sh, texts):
    s["text"] = t_
    s["continuity"]["same_location_as_prev"] = True
sh[5]["continuity"]["same_location_as_prev"] = False
runner.set_compose(Stub())
runner._still_clip = lambda j, out: (open(out, "wb").write(b"s"), str(out))[1]
jobs = runner.plan_clips(sh, imgs, {"fps": 30, "size": (320, 180)})
joined = [j for j in jobs if (j.get("tparams") or {}).get("join")]
ok("plan_clips: join specs on the shots of realised edits", len(joined) >= 2, [j["shot_id"] for j in joined])
ok("every shot job knows its timeline frames", all(j["frames"] == 90 for j in jobs if j["type"] == "shot"))
dis = [j for j in jobs if j.get("link_next")]
ok("plan_clips: the time-of-day dissolve is planned as a link", len(dis) == 1 and dis[0]["link_next"]["to"] == "s003", [(j["shot_id"], j.get("link_next")) for j in jobs])
ok("shots after a dissolve are plain cuts (no dip on top)", sh[3]["transition_in"] == "cut")
off_jobs = runner.plan_clips(sh, imgs, {"fps": 30, "size": (320, 180), "story_continuity": "off"})
ok("story_continuity off: no joins, no links", not any((j.get("tparams") or {}).get("join") or j.get("link_next") for j in off_jobs))

od = os.path.join(TMP, "out")
clips = runner.render_clips(jobs, od, workers=2)
ok("link clip delivered next to the shot clips", "s002+link" in clips and os.path.isfile(clips["s002+link"]) and bridge.link_frames(clips["s002+link"]) == 8, sorted(clips))
tl = runner.assemble_timeline(sh, clips, {"fps": 30})
ok("timeline total frames == narration frames (no drift)", tl["frames"] == 8 * 90 and tl["segments"][-1]["end_frame"] == 720, tl["frames"])
segs = tl["segments"]
ok("segments are contiguous", all(a["end_frame"] == b["start_frame"] for a, b in zip(segs, segs[1:])) and segs[0]["start_frame"] == 0)
li = [i for i, s_ in enumerate(segs) if s_["kind"] == "link"]
ok("one link segment, right after A and at B's cut", len(li) == 1 and segs[li[0] - 1]["shot_id"] == "s002" and segs[li[0] + 1]["shot_id"] == "s003", [s_["shot_id"] for s_ in segs])
if li:
    L, B = segs[li[0]], segs[li[0] + 1]
    ok("link starts exactly where B's sentence starts (frame 270)", L["start_frame"] == 270 and L["frames"] == 8 and L["shot_id"] == "s002+link")
    ok("B plays on from its frame 8 and ends where it always did", B["start_frame"] == 278 and B["end_frame"] == 360 and abs(B["clip_in"] - 8 / 30.0) < 1e-6)
pr = subprocess.run([ff, "-v", "error", "-i", clips["s002+link"], "-f", "null", "-"], capture_output=True)
ok("link clip decodes", pr.returncode == 0)
n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", clips["s002+link"]], capture_output=True, text=True).stdout.strip()
ok("link has exactly 8 frames", n == "8", n)

# resume: nothing re-made, same files
n_calls = len(runner._compose().calls)
clips2 = runner.render_clips(jobs, od, workers=2)
ok("resume: shots and link reused (no new compose calls)", len(runner._compose().calls) == n_calls and clips2.get("s002+link") == clips.get("s002+link"))

# fallback: a failing link never fails the run, the timeline keeps the plain cut
orig_make = bridge.make_link
bridge.make_link = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
od2 = os.path.join(TMP, "out2")
clips3 = runner.render_clips(jobs, od2, workers=2)
tl3 = runner.assemble_timeline(sh, clips3, {"fps": 30})
ok("failing link -> no link clip, timeline falls back to the plain cut with identical length", "s002+link" not in clips3 and tl3["frames"] == 720 and not any(s_["kind"] == "link" for s_ in tl3["segments"]))
bridge.make_link = orig_make

# cancel
class Stop(Exception): pass
cancel_after = {"n": 0}
def cancel():
    cancel_after["n"] += 1
    return cancel_after["n"] > 3
try:
    runner.render_clips(jobs, os.path.join(TMP, "out3"), cancel=cancel, workers=1)
    ok("cancel raises Cancelled", False)
except Exception as ex:
    ok("cancel raises Cancelled", type(ex).__name__ == "Cancelled", repr(ex))

# an ai_video / graphic neighbour: no join on either side
sh2, imgs2 = story(4)
for s, t_ in zip(sh2, ["He stared at the screen.", "The screen glowed.", "A coin.", "Another coin."]):
    s["text"] = t_
    s["continuity"]["same_location_as_prev"] = True
sh2[1]["ai_video"] = {"requested": True}
j2 = runner.plan_clips(sh2, imgs2, {"fps": 30, "size": (320, 180)})
ok("no join into / out of an ai_video shot", not any((j.get("tparams") or {}).get("join") for j in j2[:3]), [(j["shot_id"], (j.get("tparams") or {}).get("join")) for j in j2])

# missing continuity module -> plan_clips still works
real = sys.modules.get("story_fast.continuity")
sys.modules["story_fast.continuity"] = None
j3 = runner.plan_clips(sh2, imgs2, {"fps": 30, "size": (320, 180)})
ok("continuity import failure -> plain jobs", len(j3) == 4 and not any((j.get("tparams") or {}).get("join") for j in j3))
if real is not None:
    sys.modules["story_fast.continuity"] = real
else:
    del sys.modules["story_fast.continuity"]

# ---------------------------------------------------------------- compose: the join really changes the camera ends (real ffmpeg, tiny)
try:
    from PIL import Image
    from story_fast import compose
    pic = os.path.join(TMP, "pic.png")
    im = Image.new("RGB", (640, 360), (235, 235, 235))
    for x in range(0, 640, 40):
        for y in range(0, 360, 40):
            if (x // 40 + y // 40) % 2:
                im.paste((30 + x % 200, 60 + y % 150, 120), (x, y, x + 40, y + 40))
    im.save(pic)
    base = dict(still=pic, duration=1.6, fps=30, size=(320, 180), seed=1, treatment="hold_alive", env=[], intensity="medium", shot_id="t")
    tp0 = {"amount": .3, "ease": "smooth", "auto_focus": False}
    jn = {"out": {"pt": [.3, .4], "z": 1.5, "k": 1.0}, "in": {"pt": [.7, .6], "z": 1.5, "k": 1.0}, "D": 1.3, "w": .4}
    j1 = dict(base, tparams=dict(tp0, join=jn))
    j0 = dict(base, tparams=tp0)
    ok("join changes the cache key", compose.job_key(j1) != compose.job_key(j0))
    ok("no join: key does not depend on the join code", compose.job_key(j0) == compose.job_key(dict(j0, tparams=dict(tp0))))
    o0, o1 = os.path.join(TMP, "j0.mp4"), os.path.join(TMP, "j1.mp4")
    compose.render_shot(j0, o0)
    compose.render_shot(j1, o1)
    def frame(path, n):
        r = subprocess.run([ff, "-v", "error", "-i", path, "-vf", f"select=eq(n\\,{n})", "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
        import numpy as np
        return np.frombuffer(r.stdout, np.uint8).astype(float)
    import numpy as np
    first0, first1 = frame(o0, 0), frame(o1, 0)
    cut0, cut1 = frame(o0, 38), frame(o1, 38)             # D = 1.3 s -> frame 39 is the cut; 38 is the last frame of the shot
    ok("the incoming state differs from the plain shot at frame 0", np.abs(first0 - first1).mean() > 3.0, np.abs(first0 - first1).mean())
    ok("the outgoing state differs from the plain shot at the last frame", np.abs(cut0 - cut1).mean() > 3.0, np.abs(cut0 - cut1).mean())
    ok("a join never changes the frame count", subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", o1], capture_output=True, text=True).stdout.strip() ==
       subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", o0], capture_output=True, text=True).stdout.strip())
    # whip with blur renders
    jw = dict(base, tparams=dict(tp0, join={"out": {"dx": .08, "dy": 0.0, "zb": .2, "k": 1.0}, "in": {"dx": -.08, "dy": 0.0, "zb": .2, "k": 1.0}, "D": 1.3, "w": .28, "blur": {"out": 1, "in_": 1}}))
    ow = os.path.join(TMP, "jw.mp4")
    compose.render_shot(jw, ow)
    ok("whip with motion blur renders", os.path.getsize(ow) > 1000)
    # a join that cannot fit falls back to the shot's own camera instead of failing
    jb = dict(base, tparams=dict(tp0, join={"out": {"dx": 9.0, "dy": 9.0, "zb": 0.0, "k": 1.0}, "D": 1.3, "w": .3}))
    ob = os.path.join(TMP, "jb.mp4")
    compose.render_shot(jb, ob)
    ok("an impossible join leaves a valid clip", os.path.getsize(ob) > 1000)
except Exception as ex:      # noqa: BLE001
    import traceback
    traceback.print_exc()
    ok("compose join tests ran", False, repr(ex))

shutil.rmtree(TMP, ignore_errors=True)
print("ALL OK" if not FAILS else "FAILED: %s" % FAILS)
sys.exit(1 if FAILS else 0)
