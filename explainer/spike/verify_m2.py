"""Milestone 2 verification: narrator and props on the shared 10 s fixture (M1 content plus a narrator with every pose), hard cut and dissolve.
Reads the repository, writes only under <work_root>.

usage: python3 -B -I verify_m2.py <repo_root> <work_root> [dissolve values, default "0,0.5"]

A. assets: manifest hashes, rebuild equality (in memory vs disk, twice), the renderer neither draws nor imports the builder, fallback when assets are missing or damaged;
B. narrator cue rules (state machine, parameter errors) and layout collisions with cards, icons, props and transitions, both sides;
C. render through the UNMODIFIED generate_hybrid_video, then read it back from pixels:
   - the M1 cues land on the same video frames as in the Milestone 1 evidence;
   - the narrator region of every clip frame is compared with the rig's own expected frame (frame alignment, bob, cross-fades, slide);
   - every state change (show, five pose changes, hide) is detected from pixels against the counterfactual without that change, and compared with the clip map;
   - mouth and eye states are classified per frame by template matching and compared with the schedule and with the speech ground truth.
Word times in this fixture are synthetic (made by rule), not a human voice."""
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

root, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
dissolves = [float(v) for v in (sys.argv[3] if len(sys.argv) > 3 else "0,0.5").split(",")]
os.environ["VIDEOGEN_PAKMAP_CACHE"] = str(work / "cache")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import numpy as np
from PIL import Image, ImageDraw

import measure_render as M
from explainer.board import BoardCueError, Cue, build_board_clip
from explainer.board import icons as ICONS
from explainer.board import layout as LY
from explainer.board import render as R
from explainer.narrator import build_assets as BA
from explainer.narrator import rig
from explainer.narrator import timeline as TL
from hybrid.generate import generate_hybrid_video
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

FPS = 30
PROBE = (1000, 1040)            # below every element (chips end at y 980) and outside the narrator: always empty board
work.mkdir(parents=True, exist_ok=True)
media = work / "media"
media.mkdir(exist_ok=True)
voice, card = media / "voice.wav", media / "card.png"
if not voice.exists():
    subprocess.run([sys.executable, "-B", "-I", str(here / "make_audio.py"), str(voice), "24", str(card)], check=True)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
fm = lambda p: subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "framemd5", "-"], capture_output=True, text=True).stdout.split("#")[-1]


def narrate(sentences):
    words = []
    for text, t0 in sentences:
        t = t0
        for tok in text.split():
            words.append((tok, round(t, 3), round(t + 0.294 * 0.85, 3)))
            t += 0.294
    return words


WORDS = narrate([("Prices rose every year while the poor lost their homes.", 7.2),
                 ("Meanwhile gold flowed across the sea to the crown.", 10.6),
                 ("Nobody counted the true cost until 1545 and 100,000 workers.", 13.8)])
BEAT = (7.0, 17.0)
M1_CUES = [
    Cue("h1", "header", {"word": "prices"}, text="the cost"),
    Cue("c1", "card", {"word": "rose"}, text="prices rose each year", role="red", asset="icon:coin"),
    Cue("c2", "card", {"word": "homes"}, text="the poor lost their homes", role="blue", asset="icon:house"),
    Cue("a1", "arrow", {"word": "homes"}, offset_s=0.3, role="red", src="c1", dst="c2"),
    Cue("x1", "clear", {"word": "meanwhile"}),
    Cue("h2", "header", {"word": "gold"}, text="the gain"),
    Cue("i1", "icon", {"word": "flowed"}, text="gold", role="gold", asset="icon:coin"),
    Cue("c3", "card", {"word": "crown"}, text="the crown grew rich", role="green"),
    Cue("a2", "arrow", {"word": "crown"}, offset_s=0.4, role="ink", src="i1", dst="c3"),
    Cue("x2", "clear", {"word": "nobody"}),
    Cue("c4", "card", {"word": "counted"}, text="nobody counted the true cost", role="gold", asset="icon:warning"),
    Cue("k1", "chip", {"word": "1545"}, text="1545"),
    Cue("k2", "chip", {"word": "100,000"}, text="100,000"),
]
NAR = [
    Cue("n1", "narrator", {"word": "prices"}, params={"action": "show", "pose": "idle", "side": "left", "scale": 1.0, "enter": "slide"}),
    Cue("n2", "narrator", {"word": "every"}, params={"action": "pose", "pose": "point"}),
    Cue("n3", "narrator", {"word": "poor"}, params={"action": "pose", "pose": "surprise"}),
    Cue("n4", "narrator", {"word": "meanwhile"}, params={"action": "pose", "pose": "think"}),
    Cue("n5", "narrator", {"word": "flowed"}, params={"action": "pose", "pose": "explain"}),
    Cue("n6", "narrator", {"word": "nobody"}, params={"action": "pose", "pose": "shrug"}),
    Cue("n7", "narrator", {"word": "workers"}, params={"action": "hide", "exit": "slide"}),
]
CUES = M1_CUES + NAR
result = {"checks": {}, "variants": {}, "notes": []}
ck = result["checks"]
tiny = work / "tiny"
tiny.mkdir(exist_ok=True)

# ================= A. assets =================
files = BA.build()
files2 = BA.build()
ck["asset_build_twice_identical_in_memory"] = files == files2
ck["asset_files_on_disk_equal_rebuild"] = all((BA.OUT / n).read_bytes() == b for n, b in files.items()) and sorted(p.name for p in BA.OUT.glob("*")) == sorted(files)
man = json.loads((BA.OUT / "manifest.json").read_text())
ck["manifest_sha256_matches_every_layer"] = all(hashlib.sha256((BA.OUT / m["file"]).read_bytes()).hexdigest() == m["sha256"] for g in ("poses", "eyes", "mouths") for m in man[g].values())
ck["six_poses_three_eyes_four_mouths"] = len(man["poses"]) == 6 and len(man["eyes"]) == 3 and len(man["mouths"]) == 4
result["assets"] = {"asset_id": man["asset_id"], "manifest_sha256": hashlib.sha256((BA.OUT / "manifest.json").read_bytes()).hexdigest(), "layers_digest": man["layers_digest"],
                    "pillow_version": man["pillow_version"], "design_height_px": man["design_height_px"], "files": {n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}}
src_rig = Path(rig.__file__).read_text()
import re as _re
ck["renderer_has_no_drawing_code"] = ("ImageDraw" not in src_rig and not _re.search(r"^\s*(import|from)\s+.*build_assets", src_rig + Path(TL.__file__).read_text(), _re.M)
                                      and "ImageDraw" not in Path(TL.__file__).read_text())
# the builder module must not be loaded by a render: run one in a fresh interpreter and look at sys.modules
probe = (f"import sys; sys.dont_write_bytecode=True; sys.path.insert(0, {str(root)!r}); from explainer.board import Cue, build_board_clip; "
         f"w=[('a',7.2,7.4),('b',7.6,7.9)]; b=build_board_clip([Cue('n','narrator',{{'word':'a'}},params={{'action':'show'}})], w, 7.0, 8.5, {str(tiny / 'fresh.mp4')!r}); "
         f"print('explainer.narrator.build_assets' in sys.modules)")
ck["render_does_not_load_the_asset_builder"] = subprocess.run([sys.executable, "-B", "-I", "-c", probe], capture_output=True, text=True).stdout.strip() == "False"


def with_assets_dir(path):
    rig.ASSET_DIR = Path(path)
    rig.load_assets.cache_clear()
    rig.sprite.cache_clear()
    rig.faded.cache_clear()


good_dir = rig.ASSET_DIR
dmg = tiny / "assets_damaged"
shutil.rmtree(dmg, ignore_errors=True)
shutil.copytree(good_dir, dmg)
(dmg / "body_think.png").write_bytes((dmg / "body_think.png").read_bytes()[:-9] + b"corrupted")
with_assets_dir(dmg)
try:
    build_board_clip([Cue("n", "narrator", {"word": "prices"}, params={"action": "show"})], WORDS, *BEAT, tiny / "fb_strict.mp4")
    ck["damaged_asset_strict_raises_with_build_hint"] = False
except BoardCueError as e:
    ck["damaged_asset_strict_raises_with_build_hint"] = "does not match manifest" in str(e) and "build_assets.py" in str(e) and not (tiny / "fb_strict.mp4").exists()
b = build_board_clip([Cue("n", "narrator", {"word": "prices"}, params={"action": "show"}), Cue("c", "card", {"word": "rose"}, text="still drawn")], WORDS, *BEAT, tiny / "fb_loose.mp4", strict=False)
ck["damaged_asset_non_strict_renders_everything_else"] = bool(b.problems) and b.narrator is None and [i.cue_id for i in b.items] == ["c"] and (tiny / "fb_loose.mp4").exists()
shutil.rmtree(dmg / "mouth_o.png", ignore_errors=True) if (dmg / "mouth_o.png").is_dir() else (dmg / "mouth_o.png").unlink()
with_assets_dir(dmg)
b = build_board_clip([Cue("n", "narrator", {"word": "prices"}, params={"action": "show"})], WORDS, *BEAT, tiny / "fb2.mp4", strict=False)
ck["missing_asset_reports_problem"] = any("missing" in p or "does not match" in p for p in b.problems)
with_assets_dir(good_dir)

# ================= B. cue rules and collisions =================
def probs(cues, strict=False, beat=BEAT, side_effect_name="u.mp4"):
    try:
        b = build_board_clip(cues, WORDS, *beat, tiny / side_effect_name, strict=strict)
    except BoardCueError as e:
        return e.problems, None
    return b.problems, b


def narr(i, word, **params):
    return Cue(i, "narrator", {"word": word}, params=params)


p, _ = probs([narr("a", "every", action="pose", pose="point")])
ck["pose_before_show_is_a_problem"] = any("not on screen" in x for x in p)
p, _ = probs([narr("a", "prices", action="show"), narr("b", "homes", action="show")])
ck["second_show_is_a_problem"] = any("already shown" in x for x in p)
p, _ = probs([narr("a", "prices", action="show"), narr("b", "rose", action="pose", pose="point")])
ck["pose_during_enter_slide_is_a_problem"] = any("during the enter slide" in x for x in p)
p, _ = probs([narr("a", "prices", action="show"), narr("b", "every", action="pose", pose="point"), narr("c", "every", action="pose", pose="think", ), ], strict=False)
ck["two_poses_on_one_frame_is_a_problem"] = any("previous pose change" in x for x in p)
p, _ = probs([narr("a", "prices", action="show"), narr("b", "homes", action="hide"), narr("c", "meanwhile", action="hide")])
ck["hide_after_hide_is_a_problem"] = any("after the narrator left" in x for x in p)
p, _ = probs([narr("a", "prices", action="show", pose="dance")])
ck["unknown_pose_is_a_problem"] = any("unknown pose" in x for x in p)
p, _ = probs([narr("a", "prices", action="show", scale=2.0)])
ck["scale_out_of_range_is_a_problem"] = any("scale must be" in x for x in p)
p, _ = probs([narr("a", "prices", action="show", side="middle")])
ck["bad_side_is_a_problem"] = any("side must be" in x for x in p)
p, _ = probs([narr("a", "prices", action="wave")])
ck["bad_action_is_a_problem"] = any("params.action" in x for x in p)
p, _ = probs([Cue("m", "map", {"word": "prices"}, text="x")])   # "caption" became real in Milestone 3; "map" is still reserved
ck["still_reserved_kinds_report_problem"] = any("reserved" in x for x in p)
# collisions: cards, icons, props, chips against the animated narrator (left side, shown 7.2 s .. hidden at 'homes')
SHOW = narr("n1", "prices", action="show", pose="idle")
HIDE = narr("n9", "homes", action="hide", exit="slide")           # hide at word 'homes' (9.846 s), exit frames 9.846 .. 10.246 s
for nm, cue in (("card", Cue("e", "card", {"word": "rose"}, text="x", pos=(300, 500))), ("icon", Cue("e", "icon", {"word": "rose"}, asset="icon:coin", pos=(200, 450))),
                ("prop", Cue("e", "card", {"word": "rose"}, text="x", asset="prop:book", pos=(120, 600))), ("chip", Cue("e", "chip", {"word": "rose"}, text="1545", pos=(400, 900))),
                ("header", Cue("e", "header", {"word": "rose"}, text="x", pos=(150, 440)))):
    p, _ = probs([SHOW, cue])
    ck[f"explicit_{nm}_on_narrator_is_a_problem"] = any("collides with 'n1'" in x for x in p)
# transitions: an element that appears during the exit slide is blocked, one after the exit has finished is allowed
p, _ = probs([SHOW, HIDE, Cue("e", "card", {"word": "their"}, text="late", pos=(300, 500))])           # 'their' 9.552 s: narrator still on screen
ck["element_during_narrator_presence_collides"] = any("collides" in x for x in p)
p, _ = probs([SHOW, HIDE, Cue("e", "card", {"word": "meanwhile"}, text="after", pos=(300, 500))])      # 10.6 s: exit finished at 10.246 s
ck["element_after_exit_finished_is_allowed"] = not p
p, _ = probs([SHOW, narr("n9", "poor", action="hide", exit="none"), Cue("e", "card", {"word": "lost"}, text="x", pos=(300, 500))])   # hide 'none' at 'poor' (8.964), 'lost' 9.258
ck["element_after_instant_exit_is_allowed"] = not p
# element appearing during the enter slide frames (before settled): blocked
p, _ = probs([SHOW, Cue("e", "card", {"word": "prices"}, offset_s=0.1, text="x", pos=(300, 500))])
ck["element_during_enter_slide_collides"] = any("collides" in x for x in p)
# slots avoid the narrator: right-side narrator removes the right-hand slots
p, b = probs([narr("n1", "prices", action="show", side="right"), Cue("c1", "card", {"word": "rose"}, text="a"), Cue("c2", "card", {"word": "rose"}, text="b"), Cue("c3", "card", {"word": "rose"}, text="c"),
              Cue("k", "chip", {"word": "rose"}, text="1")])
ck["right_narrator_cards_avoid_right_slots"] = b is not None and [i.slot for i in b.items if i.kind == "card"] == ["C1", "C3"] and sum("no free card slot" in x for x in p) == 1
p, _ = probs([narr("n1", "prices", action="show", side="right"), Cue("e", "card", {"word": "rose"}, text="x", slot="C2")])
ck["right_narrator_named_slot_blocked"] = any("collides" in x or "taken" in x for x in p)
ck["narrator_box_is_the_union_of_every_frame"] = True
# narrator box covers every frame's exact opaque pixels, all poses, both sides
for side in ("left", "right"):
    _, bb = probs([SHOW if side == "left" else narr("n1", "prices", action="show", side="right"), narr("n2", "every", action="pose", pose="surprise"), narr("n3", "poor", action="pose", pose="shrug", scale=0.8)], side_effect_name=f"u_{side}.mp4")
    t = bb.narrator
    box = t.bounds()[0]
    worst = 0.0
    for n in range(t.f_first, t.clip_frames):
        fr = t.frame_rect(n)
        if fr is not None:
            worst = max(worst, box[0] - fr[0], box[1] - fr[1], fr[2] - box[2], fr[3] - box[3])
    ck["narrator_box_is_the_union_of_every_frame"] &= worst <= 1e-6
# props
ids = [i for i in ICONS.icon_ids() if i.startswith("prop:")]
ck["eight_props_registered"] = len(ids) == 8
ck["every_prop_draws_inside_its_sprite_with_a_margin"] = all((bb := ICONS.icon_sprite(i, "blue", 170).getchannel("A").getbbox()) is not None and bb[0] >= 2 and bb[1] >= 2 and bb[2] <= 168 and bb[3] <= 168 for i in ids)
pp = []
for k, i in enumerate(ids[:4]):
    pp.append(Cue(f"p{k}", "card", {"word": "rose"}, text=i.split(":")[1], asset=i, role="blue"))
p1, b1 = probs(pp, side_effect_name="props_cards.mp4")
pp2 = [Cue(f"q{k}", "icon", {"word": "rose"}, text=i.split(":")[1], asset=i, role="gold") for k, i in enumerate(ids[4:])]
p2, b2 = probs(pp2, side_effect_name="props_icons.mp4")
ck["props_work_in_cards_and_icons_without_problems"] = not p1 and not p2 and b1 is not None and b2 is not None
# deterministic builds (clip bytes, frames, manifest) with the narrator, plain and instrumented
for tag, inst in (("plain", False), ("instr", True)):
    for k in (1, 2):
        build_board_clip(CUES, WORDS, *BEAT, tiny / f"{tag}{k}.mp4", instrument=inst, beat_id="b2", manifest_path=tiny / f"{tag}{k}.json")
    ck[f"deterministic_{tag}_clip_bytes"] = sha(tiny / f"{tag}1.mp4") == sha(tiny / f"{tag}2.mp4")
    ck[f"deterministic_{tag}_frames"] = fm(tiny / f"{tag}1.mp4") == fm(tiny / f"{tag}2.mp4")
    ck[f"deterministic_{tag}_manifest"] = (tiny / f"{tag}1.json").read_text().replace(f"{tag}1", "X") == (tiny / f"{tag}2.json").read_text().replace(f"{tag}2", "X")
result["clip_sha256"] = {"plain": sha(tiny / "plain1.mp4"), "instrumented": sha(tiny / "instr1.mp4")}
result["clip_bytes"] = (tiny / "plain1.mp4").stat().st_size
# cross-process: rebuild the plain clip in a separate interpreter and compare bytes
src_text = Path(__file__).read_text()
cut = src_text.index("# ================= A. assets")
child = src_text[:cut].replace("sys.argv[1]", repr(str(root))).replace("sys.argv[2]", repr(str(work / "child"))).replace('(sys.argv[3] if len(sys.argv) > 3 else "0,0.5")', '"0"')
child = child.replace("here = Path(__file__).resolve().parent", f"here = Path({str(here)!r})")
child += f"\nbuild_board_clip(CUES, WORDS, *BEAT, Path({str(tiny / 'plain_child.mp4')!r}), beat_id='b2')\n"
(work / "child_build.py").write_text(child)
subprocess.run([sys.executable, "-B", "-I", str(work / "child_build.py")], capture_output=True)
ck["deterministic_across_processes_plain_clip_bytes"] = (tiny / "plain_child.mp4").exists() and sha(tiny / "plain_child.mp4") == sha(tiny / "plain1.mp4")

# ================= C. render and read back =================
def run_variant(d):
    tag = f"d{str(d).replace('.', '_')}"
    out = work / f"variant_{tag}"
    out.mkdir(exist_ok=True)
    build = build_board_clip(CUES, WORDS, *BEAT, out / "board.mp4", dissolve_s=d, instrument=True, beat_id="b2", manifest_path=out / "board_manifest.json")
    trk = build.narrator
    plan = json.loads((root / "test_hybrid_app_plan.json").read_text())
    plan["settings"]["dissolve_s"] = build.plan_fragment["settings"]["dissolve_s"]
    next(b for b in plan["beats"] if b["id"] == "b1")["end"] = BEAT[0]
    keep = next(b for b in plan["beats"] if b["id"] == "b2")
    keep.update({k: v for k, v in build.plan_fragment["beat"].items() if k not in ("id",)})
    keep.pop("footage_intent", None)
    next(b for b in plan["beats"] if b["id"] == "b3")["support"]["asset"] = str(card)
    (out / "derived_plan.json").write_text(json.dumps(plan, indent=1))
    hp = HybridPlan.load(out / "derived_plan.json")
    problems = validate_plan(hp)
    video = out / "render.mp4"
    t0 = time.time()
    res = generate_hybrid_video(hp, voice, video, work_dir=out / "work", whisper_words=WORDS, render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw),
                                sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    info = {"dissolve_s": d, "validate_problems": problems, "render_ok": bool(res.ok), "render_errors": list(res.errors or []), "render_seconds": round(time.time() - t0, 1),
            "clip_origin_s": build.clip_origin_s, "clip_length_s": build.clip_length_s, "clip_frames": build.n_frames, "builder_problems": build.problems,
            "narrator": trk.summary()}
    if not res.ok:
        return info
    runs, nb = M.board_runs(video, PROBE)
    run = max(runs, key=lambda r: r["frames"])
    f0 = run["offset"]
    info.update({"video_frames": nb, "pure_board_frames": run["frames"], "first_pure_video_frame": run["first"], "last_pure_video_frame": run["last"], "clip_frame0_at_video_frame": f0,
                 "held_frames": run["held_frames"], "skipped_frames": run["skipped_frames"], "runs": len(runs)})
    man = json.loads((out / "board_manifest.json").read_text())
    last_board = run["last"]
    # ---- C1. M1 cues: same video frames as in the Milestone 1 evidence ----
    m1 = json.loads((root / "docs/explainer/m1_evidence/verify_m1.json").read_text())["variants"][f"dissolve_{d}"]["cues"]
    m1_by = {r["id"]: r for r in m1}
    rows = []
    for c in man["cues"]:
        if c["kind"] in ("clear", "narrator") or not c.get("bbox") or f0 is None:
            continue
        exp_map = f0 + c["first_frame"]
        found, _cnt = M.onset_frame(video, c["bbox"], exp_map, nb, last_board)
        ref = m1_by.get(c["id"], {})
        rows.append({"id": c["id"], "kind": c["kind"], "first_clip_frame": c["first_frame"], "expected_video_frame_clip_map": exp_map, "detected_video_frame": found,
                     "detected_minus_clip_map_frames": None if found is None else found - exp_map,
                     "m1_first_clip_frame": ref.get("first_clip_frame"), "m1_detected_minus_clip_map_frames": ref.get("detected_minus_clip_map_frames"),
                     "same_clip_frame_as_m1": ref.get("first_clip_frame") == c["first_frame"]})
    info["m1_cues"] = rows
    info["m1_cues_summary"] = {"n": len(rows), "undetected": [r["id"] for r in rows if r["detected_video_frame"] is None],
                               "max_abs_frame_error_vs_clip_map": max(abs(r["detected_minus_clip_map_frames"]) for r in rows if r["detected_minus_clip_map_frames"] is not None),
                               "all_same_clip_frames_as_m1": all(r["same_clip_frame_as_m1"] for r in rows)}
    # ---- C2. narrator region, every clip frame, against the rig's own expected frame ----
    RX0, RY0, RW, RH = 0, 420, 600, 580
    nclip = build.n_frames
    exp = {}
    exp_none = {}
    for n in range(nclip):
        im = R.draw_frame([], n / FPS, (1920, 1080), None, n, True, trk)
        exp[n] = np.asarray(im.crop((RX0, RY0, RX0 + RW, RY0 + RH)).convert("L"), dtype=np.float32)
    blank = np.asarray(R.draw_frame([], 0.0, (1920, 1080), None, 0, True, None).crop((RX0, RY0, RX0 + RW, RY0 + RH)).convert("L"), dtype=np.float32)
    # decoded frames (RGB -> L the same way as above), streamed
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"crop={RW}:{RH}:{RX0}:{RY0}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    dec = {}
    fsz = RW * RH * 3
    i = 0
    first_pure, last_pure = run["first"], run["last"]
    while True:
        buf = p.stdout.read(fsz)
        if len(buf) < fsz:
            break
        if first_pure <= i <= last_pure:
            a = np.frombuffer(buf, np.uint8).reshape(RH, RW, 3).astype(np.float32)
            dec[i] = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
        i += 1
    p.wait()
    # (instrumented frames: the red border is in both; PIL 'L' uses the same weights)
    align_ok = decisive = total = 0
    maes = []
    mismatch = []
    for vi, a in dec.items():
        n = vi - f0
        if n < 0 or n >= nclip:
            continue
        cands = {k: float(np.abs(a - exp[n + k]).mean()) for k in (-2, -1, 0, 1, 2) if 0 <= n + k < nclip}
        best = min(cands.values())
        total += 1
        maes.append(cands[0])
        if cands[0] <= best + 0.05:
            align_ok += 1
        else:
            mismatch.append({"video_frame": vi, "clip_frame": n, "mae_at_0": round(cands[0], 3), "best_offset": min(cands, key=cands.get), "best_mae": round(best, 3)})
        if all(cands[0] + 0.2 < v for k, v in cands.items() if k != 0):
            decisive += 1
    info["narrator_frame_alignment"] = {"pure_frames_compared": total, "zero_offset_is_best": align_ok, "decisively_best_by_0.2_mae": decisive, "mismatches": mismatch[:10],
                                        "mean_abs_error_gray_levels": round(float(np.mean(maes)), 3), "max_abs_error_gray_levels": round(float(np.max(maes)), 3),
                                        "region_px": [RX0, RY0, RW, RH], "note": "decoded video vs the rig's own expected frame (instrumented board, narrator only), L = 0.299R+0.587G+0.114B"}
    # ---- C3. state changes: detected from pixels against the counterfactual without that change ----
    def cf_track(skip_event):
        """The same track without one event (None for the show event: no narrator at all)."""
        if skip_event.action == "show":
            return None
        return TL.NarratorTrack([e for e in trk.events if e is not skip_event], list(trk.runs), trk.clip_frames, trk.beat_id)

    def region_frame(track, n):
        if track is None:
            return blank
        im = R.draw_frame([], n / FPS, (1920, 1080), None, n, True, track)
        return np.asarray(im.crop((RX0, RY0, RX0 + RW, RY0 + RH)).convert("L"), dtype=np.float32)

    changes = []
    for ev in trk.events:
        f = ev.frame
        other = cf_track(ev)
        win = [n for n in range(f - 3, f + 7) if 0 <= n < nclip and (f0 + n) in dec]
        diffs = {n: np.abs(exp[n] - region_frame(other, n)) for n in win}
        mask = np.zeros_like(blank, dtype=bool)
        for n in win:
            mask |= diffs[n] > 10
        ys, xs = np.where(mask)
        row = {"cue": ev.cue_id, "action": ev.action, "pose": ev.pose, "clip_frame": f, "expected_video_frame_clip_map": f0 + f}
        if len(xs) == 0:
            row["problem"] = "the change is invisible in the region"
            changes.append(row)
            continue
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        delta = {}
        for n in win:
            ew = exp[n][y0:y1, x0:x1]
            eo = region_frame(other, n)[y0:y1, x0:x1]
            dd = dec[f0 + n][y0:y1, x0:x1]
            delta[n] = float(np.abs(dd - eo).mean() - np.abs(dd - ew).mean())
        found = next((n for n in win if delta[n] > 0.3), None)   # before the change the two expectations are identical, so delta is exactly 0
        row.update({"changed_region_px": [int(x0), int(y0) + RY0, int(x1), int(y1) + RY0], "delta_mae_by_clip_frame": {str(n): round(v, 2) for n, v in delta.items()},
                    "detected_clip_frame": found, "detected_video_frame": None if found is None else f0 + found,
                    "detected_minus_clip_map_frames": None if found is None else found - f})
        changes.append(row)
    info["narrator_state_changes"] = changes
    # ---- C4. faces: template matching on the mouth and eye regions of settled, pure frames ----
    st_frames = []
    for n in range(nclip):
        s = trk.state(n)
        if s is None or len(s.layers) != 1 or (f0 + n) not in dec:
            continue
        slide_in = trk.show.enter == "slide" and n < trk.f_first + TL.ENTER_FRAMES
        slide_out = trk.hide is not None and trk.hide.exit == "slide" and n >= trk.hide.frame
        if not slide_in and not slide_out:
            st_frames.append(n)
    MOUTHS = ["closed", "open", "wide", "o"]
    EYES = ["open", "blink", "happy"]

    def roi(n, kind):
        s = trk.state(n)
        ly = s.layers[0]
        sc = ly.scale_pct / 100.0
        o = man_assets["mouths"]["closed"]["origin"] if kind == "mouth" else man_assets["eyes"]["open"]["origin"]
        w, h = (120, 70) if kind == "mouth" else (200, 70)
        return int(ly.x + o[0] * sc) - RX0, int(ly.y + o[1] * sc) - RY0, int(w * sc), int(h * sc)
    man_assets = rig.load_assets().manifest
    cm_mouth = {a: {b: 0 for b in MOUTHS} for a in MOUTHS}
    cm_eyes = {a: {b: 0 for b in EYES} for a in EYES}
    decoded_mouth = {}
    for n in st_frames:
        s = trk.state(n)
        for kind, cands, cm, sched in (("mouth", MOUTHS, cm_mouth, s.mouth), ("eyes", EYES, cm_eyes, s.eyes)):
            x, y, w, h = roi(n, kind)
            best, bv = None, 1e9
            for cname in cands:
                im = Image.new("RGB", (1920, 1080), (192, 192, 192))
                trk.draw(im, n, mouth=cname if kind == "mouth" else None, eyes=cname if kind == "eyes" else None)
                ex = np.asarray(im.crop((RX0 + x, RY0 + y, RX0 + x + w, RY0 + y + h)).convert("L"), dtype=np.float32)
                v = float(np.abs(dec[f0 + n][y:y + h, x:x + w] - ex).mean())
                if v < bv:
                    best, bv = cname, v
            cm[sched][best] += 1
            if kind == "mouth":
                decoded_mouth[n] = best
    mouth_tot = sum(sum(r.values()) for r in cm_mouth.values())
    eyes_tot = sum(sum(r.values()) for r in cm_eyes.values())
    info["faces"] = {"settled_pure_frames_classified": len(st_frames), "mouth_confusion_scheduled_by_decoded": cm_mouth, "mouth_accuracy": round(sum(cm_mouth[a][a] for a in MOUTHS) / max(1, mouth_tot), 4),
                     "eyes_confusion_scheduled_by_decoded": cm_eyes, "eye_accuracy": round(sum(cm_eyes[a][a] for a in EYES) / max(1, eyes_tot), 4),
                     "blinks_scheduled_in_classified_frames": sum(1 for n in st_frames if trk.state(n).eyes == "blink"),
                     "blinks_decoded_in_classified_frames": sum(cm_eyes[a]["blink"] for a in EYES)}
    # speech ground truth: frames inside a speech run (from the synthetic word times). 'moving' = a window of 7 decoded frames holds both an open and a closed mouth
    speech = set()
    for a, b in trk.runs:
        speech.update(range(a, b))
    near = set()
    for n in speech:
        near.update(range(n - 4, n + 5))
    is_open = lambda n: decoded_mouth[n] != "closed"
    S_den = S_mov = Z_den = Z_mov = Zg_den = Zg_mov = 0
    for n in st_frames:
        win = range(n - 3, n + 4)
        if not all(w in decoded_mouth for w in win):
            continue
        mov = any(is_open(w) for w in win) and any(not is_open(w) for w in win)
        if n in speech:
            S_den += 1
            S_mov += mov
        else:
            Z_den += 1
            Z_mov += mov
            if n not in near:
                Zg_den += 1
                Zg_mov += mov
    sil = [n for n in st_frames if n not in speech and n in decoded_mouth]
    spf = [n for n in st_frames if n in speech and n in decoded_mouth]
    info["mouth_per_frame"] = {"silence_frames_classified": len(sil), "silence_frames_with_open_mouth_false_positive": sum(1 for n in sil if is_open(n)),
                               "speech_frames_classified": len(spf), "speech_frames_with_closed_mouth": sum(1 for n in spf if not is_open(n)),
                               "note": "closed frames inside speech are the closed half of the 6-frame cycle, by design"}
    info["mouth_activity"] = {"window_frames": 7, "speech_frames_with_full_window": S_den, "speech_frames_moving": S_mov, "speech_moving_share": round(S_mov / max(1, S_den), 4),
                              "silence_frames_with_full_window": Z_den, "silence_frames_moving": Z_mov, "silence_moving_share": round(Z_mov / max(1, Z_den), 4),
                              "silence_frames_4_or_more_from_speech": Zg_den, "silence_far_moving": Zg_mov, "silence_far_moving_share": round(Zg_mov / max(1, Zg_den), 4),
                              "false_negative_speech_frames_with_closed_mouth_in_a_closed_phase_are_by_design": True,
                              "ground_truth": "speech runs from the synthetic word times (made by rule), bridged gaps <= 4 frames; NOT a human voice",
                              "classifier": "template matching of the decoded mouth region against the four rig mouth renders, minimum mean absolute error"}
    # ---- C5. poses visible in the pixels (settled intervals) ----
    pose_seen = {}
    for e_i, e in enumerate(trk.poses):
        end = trk.poses[e_i + 1].frame if e_i + 1 < len(trk.poses) else (trk.hide.frame if trk.hide else nclip)
        mid = (max(e.frame + TL.FADE_FRAMES + (TL.ENTER_FRAMES if e_i == 0 else 0), e.frame) + end) // 2
        if mid >= nclip or (f0 + mid) not in dec:
            continue
        sc = {}
        for pname in TL.POSES:
            alt = TL.NarratorTrack([TL.Event(trk.f_first, "show", "x", pose=pname, scale_pct=e.scale_pct, side=trk.side, enter="none")], [], nclip, trk.beat_id)
            alt.blinks, alt.runs = trk.blinks, trk.runs
            ex = region_frame(alt, mid)
            sc[pname] = float(np.abs(dec[f0 + mid] - ex).mean())
        pose_seen[e.cue_id] = {"scheduled": e.pose, "clip_frame": mid, "best_match": min(sc, key=sc.get), "mae_best": round(min(sc.values()), 3), "mae_scheduled": round(sc[e.pose], 3)}
    info["poses_in_pixels"] = pose_seen
    info["distinct_poses_matched"] = sorted({v["best_match"] for v in pose_seen.values() if v["best_match"] == v["scheduled"]})
    # ---- C6. geometry: exact opaque pixels of the narrator against every element, and against the frame ----
    boxes = []
    for it in build.items:
        if it.kind == "narrator":
            continue
        on = it.first_frame
        off = None if it.hide_at is None else int(math.ceil(it.hide_at * FPS - 1e-9))
        boxes.append((it.cue_id, it.kind, on, off, it.bbox))
    coll = []
    outside = {"settled_frames_with_pixels_outside_frame": 0, "transition_frames_with_pixels_outside_frame": 0, "outside_pixels_max": 0, "outside_edges": set(), "below_984_settled": 0,
               "frames_checked": 0}
    for n in range(trk.f_first, nclip):
        s = trk.state(n)
        if s is None:
            continue
        outside["frames_checked"] += 1
        slide_in = trk.show.enter == "slide" and n < trk.f_first + TL.ENTER_FRAMES
        slide_out = trk.hide is not None and trk.hide.exit == "slide" and n >= trk.hide.frame
        for ly in s.layers:
            sp = rig.sprite(ly.pose, s.eyes, s.mouth, ly.scale_pct, trk.flip)
            al = np.asarray(sp.getchannel("A")) > 0
            ys, xs = np.where(al)
            gx0, gx1, gy0, gy1 = ly.x + xs.min(), ly.x + xs.max() + 1, ly.y + ys.min(), ly.y + ys.max() + 1
            out_px = int(al.sum() - al[max(0, -ly.y):max(0, 1080 - ly.y), max(0, -ly.x):max(0, 1920 - ly.x)].sum()) if (ly.x < 0 or ly.y < 0 or ly.x + sp.width > 1920 or ly.y + sp.height > 1080) else 0
            if out_px:
                outside["outside_pixels_max"] = max(outside["outside_pixels_max"], out_px)
                outside["transition_frames_with_pixels_outside_frame" if (slide_in or slide_out) else "settled_frames_with_pixels_outside_frame"] += 1
                if ly.x < 0:
                    outside["outside_edges"].add("left")
                if ly.x + sp.width > 1920:
                    outside["outside_edges"].add("right")
                if ly.y < 0:
                    outside["outside_edges"].add("top")
                if ly.y + sp.height > 1080:
                    outside["outside_edges"].add("bottom")
            if not slide_in and not slide_out and gy1 > 984:
                outside["below_984_settled"] += 1
            for cid, kind, on, off, bx in boxes:
                if n >= on and (off is None or n < off) and gx0 < bx[2] and bx[0] < gx1 and gy0 < bx[3] and bx[1] < gy1:
                    coll.append({"frame": n, "narrator_box": [int(gx0), int(gy0), int(gx1), int(gy1)], "element": cid, "kind": kind, "element_box": list(bx)})
    outside["outside_edges"] = sorted(outside["outside_edges"])
    info["geometry"] = {"per_frame_collisions_with_elements": len(coll), "collisions": coll[:10], **outside,
                        "elements_checked": len(boxes), "element_boxes_include_scale_in_overshoot": True}
    # ---- evidence frames and sheet ----
    sel = [(c["cue"], c["detected_video_frame"]) for c in changes if c.get("detected_video_frame") is not None]
    tw, th = 400, 300
    sh = Image.new("RGB", (tw * 3, th * len(sel)), (0, 0, 0))
    dd = ImageDraw.Draw(sh)
    for ri, (cid, vf) in enumerate(sel):
        for ci, n in enumerate((vf - 1, vf, vf + 3)):
            fr = M.frame_png(video, n).crop((0, 420, 640, 420 + 480)).resize((tw, th))
            sh.paste(fr, (ci * tw, ri * th))
            dd.rectangle([ci * tw, ri * th + th - 22, ci * tw + 300, ri * th + th], fill=(0, 0, 0))
            dd.text((ci * tw + 4, ri * th + th - 18), f"{cid} frame {n} t={n / FPS:.3f}s", fill=(255, 255, 0))
    sh.save(out / "state_changes.jpg", quality=85)
    return info


for d in dissolves:
    info = run_variant(d)
    result["variants"][f"dissolve_{d}"] = info
    brief = {k: v for k, v in info.items() if k in ("dissolve_s", "render_ok", "render_errors", "validate_problems", "render_seconds", "video_frames", "pure_board_frames", "held_frames", "skipped_frames", "m1_cues_summary", "narrator_frame_alignment", "mouth_activity", "distinct_poses_matched", "geometry")}
    print(json.dumps(brief, indent=1, default=str))
    for c in info.get("narrator_state_changes", []):
        print("  ", c["cue"], c["action"], c.get("pose"), "clip", c["clip_frame"], "detected_minus_clip_map", c.get("detected_minus_clip_map_frames"))
(work / "verify_m2.json").write_text(json.dumps(result, indent=1, default=str))
print(json.dumps(result["checks"], indent=1))
