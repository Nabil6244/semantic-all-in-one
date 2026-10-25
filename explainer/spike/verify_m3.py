"""Milestone 3 verification: board captions (four-rung ladder), map beats and archive beats as plan data. Reads the repository, writes only under <work_root>.

usage: python3 -B -I verify_m3.py <repo_root> <work_root> [dissolve values, default "0,0.5"]

A. caption timing unit tests (each rung, repeated words, matches before the anchor, sentence boundary, zero-length window, out-of-order times, phrase past the beat);
B. caption cue rules and layout collisions (narrator, chips, cards, margins, entering and leaving elements);
C. caption render: every rung has its own cue, rendered through the UNMODIFIED generate_hybrid_video and read back from pixels in hard cut and dissolve, per word:
   plan frame (manifest) vs an independent recomputation from the narration words vs the frame the pixels change on;
D. layout render: captions together with the M1 elements and the M2 narrator, per-frame geometry;
E. map and archive plan: builders, relevance checks, negative tests, real validate_plan, render through the unchanged Hybrid renderer with a network guard, and the layer
   timing that can be measured offline (counterfactual renders without one layer);
F. determinism (same process, separate process).
Word times in every fixture are synthetic (made by rule), not a human voice. The offline test map has no satellite imagery: nothing here says a map looks right."""
import hashlib
import json
import math
import os
import shutil
import socket
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
from explainer.beats import PlanBuildError, assemble_plan, check_plan, make_archive_beat, make_map_beat
from explainer.beats import relevance as REL
from explainer.board import BoardCueError, Cue, build_board_clip
from explainer.board import layout as LY
from explainer.captions.timing import resolve_caption
from hybrid.generate import generate_hybrid_video
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

FPS = 30
PROBE = (1000, 1040)
work.mkdir(parents=True, exist_ok=True)
media = work / "media"
media.mkdir(exist_ok=True)
voice, card = media / "voice.wav", media / "card.png"
if not voice.exists():
    subprocess.run([sys.executable, "-B", "-I", str(here / "make_audio.py"), str(voice), "24", str(card)], check=True, timeout=1800)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
fm = lambda p: subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "framemd5", "-"], capture_output=True, text=True, timeout=1800).stdout.split("#")[-1]


# ---- no-network guard: every connection attempt to a non-local address is recorded and refused ----
class NetGuard:
    attempts = []

    def __enter__(self):
        self._c, self._cc = socket.socket.connect, socket.create_connection

        def deny(addr):
            host = addr[0] if isinstance(addr, (tuple, list)) else addr
            return str(host) not in ("127.0.0.1", "::1", "localhost", "0.0.0.0") and not str(host).startswith("127.") and not str(addr).startswith("/")

        def conn(sock, addr, *a, **k):
            if deny(addr):
                NetGuard.attempts.append(str(addr)[:80])
                raise OSError("network is disabled during verification")
            return self._c(sock, addr, *a, **k)

        def cc(addr, *a, **k):
            if deny(addr):
                NetGuard.attempts.append(str(addr)[:80])
                raise OSError("network is disabled during verification")
            return self._cc(addr, *a, **k)
        socket.socket.connect, socket.create_connection = conn, cc
        return self

    def __exit__(self, *e):
        socket.socket.connect, socket.create_connection = self._c, self._cc


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
result = {"checks": {}, "variants": {}, "notes": []}
ck = result["checks"]
tiny = work / "tiny"
tiny.mkdir(exist_ok=True)

# ================= A. caption timing unit tests =================
TW = [("prices", 7.2, 7.4), ("rose", 7.5, 7.7), ("every", 7.8, 8.0), ("year", 8.1, 8.3), ("while", 8.4, 8.6), ("the", 8.7, 8.9), ("poor", 9.0, 9.2), ("lost", 9.3, 9.5),
      ("the", 9.6, 9.8), ("poor", 9.9, 10.1), ("homes", 10.2, 10.4), ("meanwhile", 10.6, 10.9)]
ALL = list(range(len(TW)))


def rc(text, anchor=7.2, window=ALL, send=10.5, mode="words", beat_end=17.0, clip_end=17.0):
    return resolve_caption("t", text, mode, anchor, TW, window, 0, send, beat_end, clip_end, 30)


r = rc("prices rose every year")
ck["rung1_every_word_at_its_own_start"] = r.rung == 1 and r.reveal_times == [7.2, 7.5, 7.8, 8.1] and not r.spread
r = rc("prices soared every year")
ck["rung2_unmatched_word_spread_between_neighbours"] = r.rung == 2 and abs(r.reveal_times[1] - (7.2 + (7.8 - 7.2) / 2)) < 1e-9 and r.spread[0]["words"] == ["soared"]
r = rc("prices rose every year zebra")
ck["rung2_trailing_word_spread_to_sentence_end"] = r.rung == 2 and abs(r.reveal_times[4] - (8.1 + (10.5 - 8.1) / 2)) < 1e-9
r = rc("zebra giraffe")
ck["rung3_nothing_matched_types_from_anchor"] = r.rung == 3 and r.reveal_times == [7.2, 7.2]
r = rc("prices rose", mode="typed")
ck["rung3_typed_mode_is_requested_not_fallback"] = r.rung == 3 and any("requested" in n for n in r.notes)
r = rc("   ")
ck["rung4_empty_phrase"] = r.rung == 4 and bool(r.problems)
r = rc("one two three four five six seven eight nine ten eleven twelve thirteen")
ck["rung4_more_than_12_words"] = r.rung == 4 and bool(r.problems)
r = rc("one two three four five six seven eight nine", mode="typed")
ck["over_policy_recorded_above_8_words"] = r.over_policy
r = rc("the poor lost the poor homes", anchor=8.7, window=ALL[5:])
ck["repeated_words_match_the_nearest_after_the_previous"] = [m["narration_index"] for m in r.matched] == [5, 6, 7, 8, 9, 10] and r.rung == 1
r = rc("while lost", anchor=8.7, window=ALL[5:])
ck["word_before_the_anchor_is_never_matched"] = r.rung == 2 and r.matched[0]["narration_word"] == "lost" and r.reveal_times[0] <= r.reveal_times[1]
r = rc("rose", anchor=8.7, window=ALL[5:])
ck["word_only_before_anchor_gives_rung3"] = r.rung == 3
r = rc("prices homes", window=ALL[:8])
ck["match_further_than_6_words_is_ignored"] = r.rung == 2 and [m["narration_word"] for m in r.matched] == ["prices"]
r = rc("lost meanwhile", anchor=9.3, window=ALL[7:11], send=10.5)
ck["sentence_boundary_words_outside_window_unmatched"] = r.rung == 2 and [m["narration_word"] for m in r.matched] == ["lost"]
r = rc("prices zebra rose", anchor=7.2, window=ALL)
r0 = resolve_caption("t", "zebra rose", "words", 7.5, TW, ALL[1:], 0, 10.5, 17.0, 17.0, 30)
ck["zero_length_window_stacks_on_the_matched_word"] = r0.rung == 2 and r0.stacked == 1 and r0.reveal_times[0] == r0.reveal_times[1] == 7.5 and r0.spread[0]["stacked"]
TWO = [("a", 5.0, 5.2), ("b", 4.0, 4.2), ("c", 3.0, 3.2), ("d", 2.0, 2.2), ("e", 6.0, 6.2)]
r = resolve_caption("t", "a b c d e", "words", 5.0, TWO, list(range(5)), 0, 7.0, 17.0, 17.0, 30)
ck["out_of_order_times_clamped_then_distrusted_beyond_2"] = r.clamped == 3 and r.rung == 3 and any("not trusted" in n for n in r.notes)
TWO2 = [("a", 5.0, 5.2), ("b", 4.0, 4.2), ("c", 5.5, 5.7)]
r = resolve_caption("t", "a b c", "words", 5.0, TWO2, [0, 1, 2], 0, 7.0, 17.0, 17.0, 30)
ck["one_out_of_order_time_clamped_and_noted"] = r.rung == 1 and r.clamped == 1 and r.reveal_times == [5.0, 5.0, 5.5]
r = resolve_caption("t", "prices rose zebra", "words", 16.0, [("prices", 16.0, 16.2), ("rose", 16.4, 16.6)], [0, 1], 0, None, 17.0, 17.0, 30)
ck["phrase_past_the_beat_spread_ends_before_the_clip_end"] = r.rung == 2 and r.reveal_times[2] < 17.0 - 1 / 30 + 1e-9
r = resolve_caption("t", "x - y", "words", 7.2, [("x", 7.2, 7.4), ("y", 7.5, 7.7)], [0, 1], 0, 9.0, 17.0, 17.0, 30)
ck["display_only_dash_shares_the_previous_time"] = r.rung == 1 and r.reveal_times[1] == r.reveal_times[0] == 7.2 and r.reveal_times[2] == 7.5

# ================= B. caption cue rules and layout =================
def probs(cues, strict=False, beat=BEAT, name="u.mp4", words=WORDS):
    try:
        b = build_board_clip(cues, words, *beat, tiny / name, strict=strict)
    except BoardCueError as e:
        return e.problems, None
    return b.problems, b


def narr(i, word, **params):
    return Cue(i, "narrator", {"word": word}, params=params)


def cap(i, word, text, **kw):
    params = kw.pop("params", None) or {}
    return Cue(i, "caption", {"word": word}, text=text, params=params, **kw)


p, b = probs([cap("a", "prices", "prices rose every year")])
cr = [c for c in json.loads(json.dumps(b.manifest()))["cues"] if c["id"] == "a"][0]
ck["caption_manifest_records_rung_and_inputs"] = (not p and cr["caption"]["rung"] == 1 and len(cr["caption"]["matched"]) == 4 and len(cr["caption"]["reveal_frames"]) == 4
                                                   and len(cr["caption"]["word_boxes"]) == 4 and cr["caption"]["window"]["sentence_end"] is not None and cr["slot"] == "B")
ck["caption_schema_version_is_1_2"] = b.manifest()["schema_version"] == "1.2"
p, _ = probs([cap("a", "prices", "")])
ck["caption_needs_text"] = any("needs text" in x for x in p)
p, _ = probs([cap("a", "nonexistent", "x y")])
ck["caption_anchor_not_in_beat_is_rung4_problem"] = any("not spoken inside this beat" in x for x in p)
p, _ = probs([cap("a", "prices", "x", params={"mode": "sing"})])
ck["caption_bad_mode_is_a_problem"] = any("params.mode" in x for x in p)
p, _ = probs([cap("a", "prices", "word " * 13)])
ck["caption_over_12_words_is_a_problem"] = any("at most 12 words" in x for x in p)
p, _ = probs([cap("a", "prices", "supercalifragilisticexpialidocious " * 10, slot="BL")])
ck["caption_text_too_wide_for_slot_is_a_problem"] = any("does not fit" in x or "no place" in x for x in p)
p, _ = probs([cap("a", "prices", "x", pos=(10, 10))])
ck["caption_position_outside_margins_is_a_problem"] = any("margins" in x for x in p)
p, _ = probs([cap("a", "prices", "x", slot="C1")])
ck["caption_wrong_class_slot_is_a_problem"] = any("not a caption slot" in x for x in p)
p, _ = probs([cap("a", "prices", "x", offset_s=-3.0)])
ck["caption_before_clip_start_is_a_problem"] = any("outside the clip" in x for x in p)
p, _ = probs([cap("a", "prices", "prices rose every year"), Cue("k", "chip", {"word": "rose"}, text="1545", slot="K2")])
ck["named_chip_slot_under_the_caption_text_is_refused"] = any("slot K2 is taken" in x or "collides" in x for x in p)
p, b = probs([cap("a", "prices", "prices rose every year"), Cue("k", "chip", {"word": "rose"}, text="1545")])
ck["automatic_chip_goes_beside_the_caption_not_under_it"] = not p and [i.slot for i in b.items if i.kind == "chip"] == ["K1"]
p, b = probs([cap("a", "prices", "prices rose every year", slot="BL"), Cue("k", "chip", {"word": "rose"}, text="1545", slot="K3")])
ck["chip_beside_left_half_caption_is_allowed"] = not p
p, _ = probs([Cue("k", "chip", {"word": "prices"}, text="1545", slot="K2"), cap("a", "rose", "rose every year", slot="B")])
ck["caption_named_slot_under_a_visible_chip_is_refused"] = any("slot B is taken" in x for x in p)
p, b = probs([Cue("k", "chip", {"word": "prices"}, text="1545", slot="K2"), cap("a", "rose", "rose every year")])
ck["caption_moves_to_a_free_slot_when_a_chip_blocks"] = not p and [i.slot for i in b.items if i.kind == "caption"] == ["BR"]
p, _ = probs([cap("a", "prices", "x", pos=(700, 880), role="red"), Cue("c", "card", {"word": "rose"}, text="y", pos=(700, 700))])
ck["explicit_card_over_caption_is_a_problem"] = any("collides" in x for x in p)
p, _ = probs([Cue("c", "card", {"word": "prices"}, text="y", slot="C3"), cap("a", "rose", "x", pos=(700, 880))])
ck["caption_explicit_box_over_card_is_a_problem"] = any("collides" in x for x in p)
p, _ = probs([Cue("i", "icon", {"word": "prices"}, asset="prop:book", slot="C3"), cap("a", "rose", "prices rose", pos=(700, 880))])
ck["caption_explicit_box_over_prop_icon_is_a_problem"] = any("collides" in x for x in p)
RIGHT = narr("n1", "prices", action="show", side="right")
LONG = "rose every year while the poor lost"
p, b = probs([RIGHT, cap("a", "rose", LONG)])
ck["right_narrator_long_caption_takes_the_left_half"] = not p and any(i.slot == "BL" for i in b.items)
p, b = probs([RIGHT, cap("a", "rose", "rose every year")])
ck["right_narrator_short_caption_stays_in_the_full_band_beside_it"] = not p and any(i.slot == "B" for i in b.items)
p, _ = probs([RIGHT, cap("a", "rose", "rose every year", slot="BR")])
ck["right_narrator_named_BR_blocked"] = any("collides with 'n1'" in x or "taken by 'n1'" in x for x in p)
HIDE = narr("n9", "homes", action="hide", exit="slide")
p, _ = probs([RIGHT, HIDE, cap("a", "their", "their homes", slot="BR")])
ck["caption_while_narrator_present_or_sliding_collides"] = any("n1" in x for x in p)
p, b = probs([RIGHT, HIDE, cap("a", "meanwhile", "meanwhile gold", slot="BR")])
ck["caption_after_narrator_exit_finished_is_allowed"] = not p
p, _ = probs([narr("n1", "prices", action="show"), Cue("a", "caption", {"word": "rose"}, text="rose every year", pos=(300, 900))])
ck["caption_box_over_left_narrator_is_a_problem"] = any("collides" in x or "margins" in x for x in p)
ck["strict_raises_on_caption_problem"] = False
try:
    build_board_clip([cap("a", "nonexistent", "x y")], WORDS, *BEAT, tiny / "strict.mp4", strict=True)
except BoardCueError:
    ck["strict_raises_on_caption_problem"] = not (tiny / "strict.mp4").exists()
p, b = probs([cap("bad", "nonexistent", "x y"), cap("ok", "prices", "prices rose")])
ck["non_strict_skips_bad_caption_and_builds_good"] = bool(p) and [i.cue_id for i in b.items] == ["ok"]

# ================= C. caption render fixtures (one cue per rung / edge case) =================
CAP = [
    Cue("k1", "caption", {"word": "prices"}, text="prices rose every year"),                                              # rung 1
    Cue("x1", "clear", {"word": "while"}),
    Cue("k2", "caption", {"word": "the"}, text="the poor lost their domes", role="red"),                                  # rung 2, trailing word spread to the sentence end
    Cue("x2", "clear", {"word": "meanwhile"}),
    Cue("k3", "caption", {"word": "gold"}, text="a completely different thought", role="green"),                         # rung 3 by fallback (nothing matches)
    Cue("x3", "clear", {"word": "to"}),
    Cue("k4", "caption", {"word": "crown"}, text="the crown grew rich", params={"mode": "typed"}),                        # rung 3 requested
    Cue("x4", "clear", {"word": "nobody"}),
    Cue("k5", "caption", {"word": "counted"}, text="nobody counted the cost", role="blue"),                              # rung 2: first word spoken BEFORE the anchor, zero-length window
]
LAYOUT = [c for c in (
    Cue("h1", "header", {"word": "prices"}, text="the cost"),
    Cue("c1", "card", {"word": "rose"}, text="prices rose each year", role="red", asset="icon:coin"),
    Cue("c2", "card", {"word": "homes"}, text="the poor lost their homes", role="blue", asset="prop:house" if False else "icon:house"),
    Cue("a1", "arrow", {"word": "homes"}, offset_s=0.3, role="red", src="c1", dst="c2"),
    Cue("x1", "clear", {"word": "meanwhile"}),
    Cue("h2", "header", {"word": "gold"}, text="the gain"),
    Cue("i1", "icon", {"word": "flowed"}, text="gold", role="gold", asset="prop:chest"),
    Cue("c3", "card", {"word": "crown"}, text="the crown grew rich", role="green", asset="prop:note"),
    Cue("a2", "arrow", {"word": "crown"}, offset_s=0.4, role="ink", src="i1", dst="c3"),
    Cue("x2", "clear", {"word": "nobody"}),
    Cue("c4", "card", {"word": "counted"}, text="nobody counted the true cost", role="gold", asset="icon:warning"),
    Cue("k1x", "chip", {"word": "1545"}, text="1545", slot="K3"),
    Cue("n1", "narrator", {"word": "prices"}, params={"action": "show", "pose": "idle"}),
    Cue("n2", "narrator", {"word": "every"}, params={"action": "pose", "pose": "point"}),
    Cue("n3", "narrator", {"word": "meanwhile"}, params={"action": "pose", "pose": "think"}),
    Cue("n4", "narrator", {"word": "workers"}, params={"action": "hide", "exit": "slide"}),
    Cue("ca1", "caption", {"word": "prices"}, text="prices rose every year", slot="BL", role="blue"),
    Cue("ca2", "caption", {"word": "gold"}, text="gold flowed across the sea", slot="BL", role="red"),
    Cue("ca3", "caption", {"word": "counted"}, text="nobody counted the true cost", slot="BL", role="green"),
)]
# a caption must be cleared before the next one takes its slot; the M1 clears already do this (x1, x2)


def run_board(name, cues, d, narrator_frames=False):
    tag = f"{name}_d{str(d).replace('.', '_')}"
    out = work / f"variant_{tag}"
    out.mkdir(exist_ok=True)
    build = build_board_clip(cues, WORDS, *BEAT, out / "board.mp4", dissolve_s=d, instrument=True, beat_id="b2", manifest_path=out / "board_manifest.json")
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
    with NetGuard():
        res = generate_hybrid_video(hp, voice, video, work_dir=out / "work", whisper_words=WORDS, render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw),
                                    sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    info = {"name": name, "dissolve_s": d, "validate_problems": problems, "render_ok": bool(res.ok), "render_errors": list(res.errors or []), "render_seconds": round(time.time() - t0, 1),
            "clip_origin_s": build.clip_origin_s, "clip_frames": build.n_frames, "builder_problems": build.problems, "schema_version": build.manifest()["schema_version"]}
    if not res.ok:
        return info
    runs, nb = M.board_runs(video, PROBE)
    run = max(runs, key=lambda r: r["frames"])
    f0 = run["offset"]
    info.update({"video_frames": nb, "pure_board_frames": run["frames"], "clip_frame0_at_video_frame": f0, "held_frames": run["held_frames"], "skipped_frames": run["skipped_frames"]})
    man = json.loads((out / "board_manifest.json").read_text())
    rows = []
    origin = build.clip_origin_s
    for c in man["cues"]:
        if c["kind"] != "caption" or c["problems"]:
            continue
        cp = c["caption"]
        wb = cp["word_boxes"]
        rec = {"id": c["id"], "rung": cp["rung"], "rung_name": cp["rung_name"], "mode": cp["mode"], "slot": c["slot"], "phrase": cp["phrase_words"], "notes": cp["notes"], "spread": cp["spread"],
               "stacked": cp["stacked"], "words": []}
        mt = {m["phrase_word"]: m for m in cp["matched"]}
        if cp["rung"] == 3:                       # typed: first character and completion
            box = [min(b[0] for b in wb) if wb else 0, 0, 0, 0]
            x0 = min(b[0] for b in wb)
            y0, x1, y1 = min(b[1] for b in wb), max(b[2] for b in wb), max(b[3] for b in wb)
            exp0 = f0 + c["first_frame"]
            first_box = (wb[0][0] - 3, y0 - 3, wb[0][0] + 26, y1 + 3)
            found, _ = M.onset_frame(video, first_box, exp0, nb, run["last"], dev=50, thr=6)
            n_chars = len(" ".join(cp["phrase_words"]))
            x0i, y0i, x1i, y1i = [v // 2 * 2 for v in (x0 - 3, y0 - 3, x1 + 4, y1 + 4)]
            w_, h_ = x1i - x0i, y1i - y0i
            reg = M.raw(video, f"crop={w_}:{h_}:{x0i}:{y0i},format=gray", "gray", w_ * h_)
            cnt = (np.abs(reg.astype(int) - 192) > 50).sum(axis=1)
            onset_t = c["onset_clip"]
            exp_done = next(i for i in range(0, 10 ** 4) if i / FPS - onset_t >= (n_chars - 1) / cp["cps"] - 1e-9)
            final = cnt[min(run["last"], f0 + exp_done + 2)]          # the count two frames after the expected completion (the caption is still on screen then)
            done = next((i for i in range(found or exp0, min(run["last"], f0 + exp_done + 12)) if final and cnt[i] >= 0.97 * final), None)
            rec["typed"] = {"first_char": {"expected_video_frame": exp0, "detected_video_frame": found, "error_frames": None if found is None else found - exp0},
                            "completion": {"expected_video_frame": f0 + exp_done, "detected_video_frame": done, "error_frames": None if done is None else done - (f0 + exp_done)},
                            "note": "completion = first frame whose changed-pixel count reaches 97% of the final count; antialiasing and the 30 cps step make +-1 frame expected"}
        else:
            for k, (w, b) in enumerate(zip(cp["phrase_words"], wb)):
                frame = cp["reveal_frames"][k]
                exp = f0 + frame
                found, _ = M.onset_frame(video, (b[0] - 3, b[1] - 3, b[2] + 3, b[3] + 3), exp, nb, run["last"], dev=50, thr=6)
                indep = None
                m = next((mm for mm in cp["matched"] if mm["phrase_word"] == w and mm["narration_index"] is not None), None)
                if m is not None:
                    indep = int(math.ceil((m["start"] + (cp.get("offset_s") or 0.0) - origin) * FPS - 1e-9))   # recomputed from the narration word, not from the manifest
                rec["words"].append({"word": w, "reveal_time_abs": cp["reveal_times_abs"][k], "plan_clip_frame": frame, "independent_clip_frame_from_narration": indep,
                                     "plan_equals_independent": None if indep is None else indep == frame, "expected_video_frame": exp, "detected_video_frame": found,
                                     "error_frames": None if found is None else found - exp})
        rows.append(rec)
    info["captions"] = rows
    errs = [w["error_frames"] for r in rows for w in r["words"] if w["error_frames"] is not None]
    typed = [r["typed"] for r in rows if "typed" in r]
    info["caption_summary"] = {"words_measured": len(errs), "undetected": [(r["id"], w["word"]) for r in rows for w in r["words"] if w["detected_video_frame"] is None],
                               "max_abs_error_frames": max([abs(e) for e in errs] or [None]),
                               "plan_vs_independent_mismatches": [(r["id"], w["word"]) for r in rows for w in r["words"] if w["plan_equals_independent"] is False],
                               "typed_first_char_errors": [t["first_char"]["error_frames"] for t in typed], "typed_completion_errors": [t["completion"]["error_frames"] for t in typed]}
    # ---- geometry per frame: caption word boxes vs every other visible element and the narrator's exact pixels ----
    trk = build.narrator
    items = build.items
    coll = []
    from explainer.narrator import rig
    for n in range(build.n_frames):
        vis = [it for it in items if it.kind != "narrator" and it.first_frame <= n and (it.hide_at is None or n < int(math.ceil(it.hide_at * FPS - 1e-9)))]
        caps = [it for it in vis if it.kind == "caption"]
        nb_ = None
        if trk is not None and trk.state(n) is not None:
            st = trk.state(n)
            bx = []
            for ly in st.layers:
                sp = rig.sprite(ly.pose, st.eyes, st.mouth, ly.scale_pct, trk.flip)
                a = np.asarray(sp.getchannel("A")) > 0
                ys, xs = np.where(a)
                bx.append((ly.x + xs.min(), ly.y + ys.min(), ly.x + xs.max() + 1, ly.y + ys.max() + 1))
            nb_ = (min(b[0] for b in bx), min(b[1] for b in bx), max(b[2] for b in bx), max(b[3] for b in bx))
        for c in caps:
            shown = [bb for bb, fr in zip(c.word_boxes, c.reveal_frames) if fr <= n] if c.rung != 3 else [c.rect]
            rc_ = (min(b[0] for b in shown), min(b[1] for b in shown), max(b[2] for b in shown), max(b[3] for b in shown)) if shown else None
            if rc_ is None:
                continue
            if not (96 <= rc_[0] and 96 <= rc_[1] and rc_[2] <= 1824 and rc_[3] <= 984):
                coll.append({"frame": n, "caption": c.cue_id, "problem": "outside the margins", "box": list(rc_)})
            for o in vis:
                if o is c:
                    continue
                ob = o.bbox
                if rc_[0] < ob[2] and ob[0] < rc_[2] and rc_[1] < ob[3] and ob[1] < rc_[3]:
                    coll.append({"frame": n, "caption": c.cue_id, "element": o.cue_id, "kind": o.kind, "box": list(rc_), "element_box": list(ob)})
            if nb_ and rc_[0] < nb_[2] and nb_[0] < rc_[2] and rc_[1] < nb_[3] and nb_[1] < rc_[3]:
                coll.append({"frame": n, "caption": c.cue_id, "element": "narrator(exact pixels)", "box": list(rc_), "narrator_box": [int(v) for v in nb_]})
    info["geometry"] = {"frames_checked": build.n_frames, "caption_collisions_or_margin_violations": len(coll), "examples": coll[:6]}
    # evidence sheet: before / at / after each caption's first word
    sel = [(r["id"], r["words"][0]["detected_video_frame"] if r["words"] else r["typed"]["first_char"]["detected_video_frame"]) for r in rows]
    sel = [(a, b) for a, b in sel if b is not None]
    tw, th = 640, 130
    sh = Image.new("RGB", (tw * 3, th * len(sel)), (0, 0, 0))
    dd = ImageDraw.Draw(sh)
    for ri, (cid, vf) in enumerate(sel):
        for ci, n in enumerate((vf - 1, vf, vf + 8)):
            fr = M.frame_png(video, n).crop((600, 880, 1860, 1000)).resize((tw, th))
            sh.paste(fr, (ci * tw, ri * th))
            dd.rectangle([ci * tw, 0 + ri * th, ci * tw + 260, ri * th + 14], fill=(0, 0, 0))
            dd.text((ci * tw + 3, ri * th + 1), f"{cid} frame {n}", fill=(255, 255, 0))
    sh.save(out / "caption_onsets.jpg", quality=85)
    return info


with NetGuard():
    pass
for d in dissolves:
    for nm, cues in (("captions", CAP), ("layout", LAYOUT)):
        info = run_board(nm, cues, d)
        result["variants"][f"{nm}_dissolve_{d}"] = info
        print(json.dumps({k: v for k, v in info.items() if k in ("name", "dissolve_s", "render_ok", "render_errors", "validate_problems", "schema_version", "pure_board_frames", "caption_summary", "geometry")}, indent=1, default=str))

# ================= E. map and archive beats =================
MW = narrate([("Pakistan is built around a single river system.", 0.5), ("It begins in the mountains near Gilgit, far to the north.", 4.8),
              ("Then it runs south past Lahore to Karachi.", 9.4), ("Farmers wait for the water each spring.", 13.0), ("Then the story returns to the map.", 19.4)])
mdir = work / "map"
mdir.mkdir(exist_ok=True)
pic = mdir / "farm_market.png"
rs = np.random.RandomState(7)
pa = np.zeros((450, 800, 3), np.uint8)
for _ in range(60):
    x0, y0 = rs.randint(0, 700), rs.randint(0, 380)
    pa[y0:y0 + rs.randint(30, 120), x0:x0 + rs.randint(40, 200)] = rs.randint(0, 255, 3)
Image.fromarray(pa).save(pic)
b1, e1, p1 = make_map_beat("b1", 0.0, 9.2, MW, camera_start={"place": "Pakistan", "frame": "country"}, fills=[{"place": "Pakistan"}], markers=[{"place": "Gilgit"}],
                           captions=[{"text": "single river system", "anchor_word": "single"}], fly_to=[{"place": "Gilgit", "dur": 2.0, "t": 5.5}],
                           purpose="where the river begins", geo_intent="the river system of Pakistan")
b2, e2, p2 = make_map_beat("b2", 9.2, 12.6, MW, markers=[{"place": "Lahore"}, {"place": "Karachi"}], lines=[{"places": ["Lahore", "Karachi"], "kind": "river"}],
                           fly_to=[{"place": "Pakistan", "frame": "country", "t": 9.4, "dur": 2.0}],
                           purpose="where it flows", geo_intent="the river runs south")
b3, e3, p3 = make_archive_beat("b3", 12.6, 19.0, MW, [{"asset": str(pic), "reason": "a picture of the farming this river feeds: what the map cannot show", "subject": ["farmers", "water"], "kenburns": True}],
                               purpose="farmers and water")
b4, e4, p4 = make_map_beat("b4", 19.0, 24.0, MW, captions=[{"text": "the story returns to the map", "anchor_word": "story"}], purpose="back to the map", geo_intent="return to the map")
plan = assemble_plan(24.0, [b1, b2, b3, b4], {"dissolve_s": 0.5})
subjects = {**e3["subjects"]}
rep = check_plan(plan, MW, subjects=subjects, base_dir=mdir)
(work / "map_plan.json").write_text(json.dumps(plan, indent=1, sort_keys=True))
result["map_plan"] = {"validate_plan_problems": rep.validate_plan_problems, "relevance_problems": rep.problems, "warnings": rep.warnings, "layers_checked": len([r for r in rep.records if "layer" in r]),
                      "clips_checked": len([r for r in rep.records if "clip" in r]), "plan_sha256": sha(work / "map_plan.json")}
ck["map_plan_passes_validate_plan_and_relevance"] = rep.ok and not rep.validate_plan_problems
ck["every_map_layer_has_its_word_match_recorded"] = all(r.get("matches") or r.get("caption") for r in rep.records if r.get("type") in ("marker", "fill", "line", "caption"))
ck["markers_and_fills_start_at_the_spoken_word"] = all(abs(r["t_minus_word_start"]) <= 0.6 for r in rep.records if "t_minus_word_start" in r)
ck["sample_plan_has_no_camera_framing_warnings"] = not any("may be off screen" in w for w in rep.warnings)
b2_nocam, _, _ = make_map_beat("b2", 9.2, 12.6, MW, markers=[{"place": "Lahore"}, {"place": "Karachi"}], purpose="where it flows", geo_intent="the river runs south")
rep_nc = check_plan(assemble_plan(24.0, [b1, b2_nocam, b3, b4], {"dissolve_s": 0.5}), MW, subjects=subjects, base_dir=mdir)
ck["layers_at_places_outside_the_camera_area_get_a_framing_warning"] = any("may be off screen" in w and "Lahore" in w for w in rep_nc.warnings) and rep_nc.ok
ck["places_resolve_with_the_offline_lookup"] = all(all(v.values()) for r in rep.records for v in [r.get("resolvable_offline", {})])
result["map_evidence"] = {"beats": [e1, e2, e3, e4]}
# negative tests -------------------------------------------------------------------------
def neg(label, plan_mut, expect, subjects_=None, words=MW):
    pl = json.loads(json.dumps(plan))
    plan_mut(pl)
    r = check_plan(pl, words, subjects=subjects_ if subjects_ is not None else subjects, base_dir=mdir)
    hit = any(expect in x for x in r.problems)
    ck[f"negative_{label}"] = hit
    return r


def set_layer(pl, bid, lid, **kw):
    for b in pl["beats"]:
        if b["id"] == bid:
            for l in b["layers"]:
                if l["id"] == lid:
                    l.update(kw)


r = neg("marker_for_place_spoken_only_in_another_beat", lambda pl: pl["beats"][0]["layers"].append({"id": "bad1", "type": "marker", "t": 6.0, "place": "Lahore", "label": "LAHORE"}),
        "not spoken inside this beat")
ck["negative_that_plan_passes_validate_plan"] = r.validate_plan_problems == []
neg("marker_placed_too_early", lambda pl: set_layer(pl, "b1", "b1_marker1", t=4.0), "starts at 4 s but")
neg("marker_placed_too_late", lambda pl: set_layer(pl, "b1", "b1_marker1", t=8.5), "starts at 8.5 s but")
neg("marker_label_not_spoken", lambda pl: set_layer(pl, "b1", "b1_marker1", label="THE ZEBRA CAPITAL"), "neither the place nor words spoken")
neg("unresolvable_place_offline", lambda pl: pl["beats"][0]["layers"].append({"id": "bad2", "type": "fill", "t": 0.5, "place": "Pakistan"}) or set_layer(pl, "b1", "bad2", place="Atlantis"),
    "not spoken inside this beat")
AW = narrate([("Atlantis sank beneath the sea long ago.", 0.5)])
rr = check_plan({"version": 1, "duration": 5.0, "settings": {}, "beats": [{"id": "z", "mode": "map", "start": 0.0, "end": 5.0, "geo_intent": "x", "camera": [{"action": "start", "place": "Pakistan", "frame": "country"}],
                                                                      "layers": [{"id": "z1", "type": "fill", "t": 0.5, "place": "Atlantis"}]}]}, AW)
ck["negative_place_spoken_but_unknown_to_the_offline_lookup"] = any("offline place lookup cannot find" in x for x in rr.problems)
neg("caption_layer_not_in_narration", lambda pl: set_layer(pl, "b1", "b1_caption3", text="completely unrelated words"), "the caption 'completely unrelated words'")
neg("caption_layer_starting_word_spoken_but_phrase_not", lambda pl: set_layer(pl, "b1", "b1_caption3", text="zebra giraffe single"), "the caption 'zebra giraffe single'")
neg("map_layer_outside_its_beat_is_caught_by_validate_plan", lambda pl: set_layer(pl, "b1", "b1_marker1", t=9.5), "outside its map beat")
neg("archive_clip_without_reason", lambda pl: pl["beats"][2]["footage"]["clips"][0].update(reason=""), "non-empty reason")
neg("archive_clip_blank_reason", lambda pl: pl["beats"][2]["footage"]["clips"][0].update(reason="   "), "non-empty reason")
neg("archive_subject_not_spoken_in_window", lambda pl: None, "none of its subjects", subjects_={"b3": {"0": ["zebras", "volcano"]}})
neg("archive_no_subject_given", lambda pl: None, "no subject phrase was given", subjects_={})
empty = mdir / "empty.png"
empty.write_bytes(b"")
adir = mdir / "a_directory.png"
adir.mkdir(exist_ok=True)
txt = mdir / "notes.txt"
txt.write_text("not a picture")
for lab, path, expect in (("missing_file", str(mdir / "nope.png"), "file not found"), ("directory", str(adir), "not a regular file"), ("empty_file", str(empty), "empty file"),
                          ("unsupported_extension", str(txt), "unsupported file type")):
    neg(f"invalid_local_file_{lab}", lambda pl, path=path: pl["beats"][2]["footage"]["clips"][0].update(asset=path), expect)
noread = mdir / "noread.png"
shutil.copy(pic, noread)
os.chmod(noread, 0)
if os.access(noread, os.R_OK):
    ck["negative_invalid_local_file_unreadable"] = None
    result["notes"].append("unreadable-file test skipped: this process can read a mode-000 file")
else:
    neg("invalid_local_file_unreadable", lambda pl: pl["beats"][2]["footage"]["clips"][0].update(asset=str(noread)), "unreadable file")
os.chmod(noread, 0o600)
REMOTE = ["stock_image:a market", "stock_video:farmers", "flow_image:a river at dawn", "flow_video:farmers walking", "youtube_video:farmers documentary", "https://example.com/p.jpg",
          "http://example.com/p.jpg", "ftp://example.com/p.jpg", "file:///etc/passwd.jpg", "//host/share/p.jpg", "www.example.com/p.jpg", "data:image/png;base64,AAAA", "a.png|b.png"]
accepted = []
for k, ref in enumerate(REMOTE):
    r = neg(f"remote_reference_{k}", lambda pl, ref=ref: pl["beats"][2]["footage"]["clips"][0].update(asset=ref), "(local files only)" if ref.split(":")[0] not in ("a.png|b.png",) else "not a single local file")
    accepted.append({"ref": ref, "validate_plan_accepts": not any(ref[:30] in x for x in r.validate_plan_problems) and not r.validate_plan_problems})
    # builder refuses before anything
    try:
        make_archive_beat("zz", 12.6, 19.0, MW, [{"asset": ref, "reason": "x", "subject": ["farmers"]}], base_dir=mdir)
        ck[f"builder_refuses_remote_reference_{k}"] = False
    except PlanBuildError as e:
        ck[f"builder_refuses_remote_reference_{k}"] = any("local files only" in x or "single local file" in x or "not a local file" in x for x in e.problems)
result["remote_references"] = accepted
ck["validate_plan_alone_accepts_most_remote_references"] = sum(1 for a in accepted if a["validate_plan_accepts"]) >= 8
neg("map_footage_card_with_remote_asset", lambda pl: pl["beats"].__setitem__(3, {"id": "b4", "mode": "map_footage", "start": 19.0, "end": 24.0, "geo_intent": "x", "camera": [],
                                                                                    "layers": [], "support": {"asset": "stock_image:glacier", "t": 20.0}}), "local files only")
for fn, args, expect in (
        (lambda: make_map_beat("q", 0, 9, MW, markers=[{"place": "Lahore"}]), None, "not spoken inside"),
        (lambda: make_map_beat("q", 0, 9, MW, fills=[{"place": "Atlantis"}]), None, "not spoken inside"),
        (lambda: make_map_beat("q", 0, 9, MW, captions=[{"text": "zebra giraffe", "anchor_word": "single"}]), None, "not supported by the narration"),
        (lambda: make_archive_beat("q", 12.6, 19.0, MW, [{"asset": str(pic), "reason": "", "subject": ["farmers"]}], base_dir=mdir), None, "non-empty reason"),
        (lambda: make_archive_beat("q", 12.6, 19.0, MW, [{"asset": str(pic), "reason": "r", "subject": ["volcano"]}], base_dir=mdir), None, "none of its subjects")):
    try:
        fn()
        ck[f"builder_strict_{expect[:12]}"] = False
    except PlanBuildError as e:
        ck[f"builder_strict_{expect[:12]}_{len([k for k in ck if k.startswith('builder_strict_')])}"] = any(expect in x for x in e.problems)
_, _, probs_loose = make_map_beat("q", 0, 9, MW, fills=[{"place": "Atlantis"}], markers=[{"place": "Gilgit"}], strict=False)
b_loose, _, _ = make_map_beat("q", 0, 9, MW, fills=[{"place": "Atlantis"}], markers=[{"place": "Gilgit"}], strict=False)
ck["builder_non_strict_returns_problems_and_the_good_layers"] = bool(probs_loose) and [l["id"] for l in b_loose["layers"]] == ["q_marker1"]


# render the positive plan through the unchanged renderer, network guarded -----------------
def render_plan(pl, out, label):
    out.mkdir(exist_ok=True)
    (out / "plan.json").write_text(json.dumps(pl, indent=1, sort_keys=True))
    hp = HybridPlan.load(out / "plan.json")
    vp = validate_plan(hp)
    video = out / "render.mp4"
    NetGuard.attempts = []
    t0 = time.time()
    with NetGuard():
        res = generate_hybrid_video(hp, voice, video, work_dir=out / "work", whisper_words=MW, render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw),
                                    sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    return {"label": label, "validate_plan_problems": vp, "render_ok": bool(res.ok), "render_errors": list(res.errors or []), "render_seconds": round(time.time() - t0, 1),
            "network_attempts_refused": list(NetGuard.attempts), "video": str(video)}


base = render_plan(plan, work / "map_render_base", "base")
result["map_render"] = {k: v for k, v in base.items() if k != "video"}
ck["map_plan_renders_through_unchanged_hybrid"] = base["render_ok"] and not base["validate_plan_problems"]
ck["no_network_attempts_while_rendering_map_and_archive"] = base["network_attempts_refused"] == []
if base["render_ok"]:
    V = Path(base["video"])
    nbv = M.n_frames(V)
    result["map_render"]["video_frames"] = nbv
    # archive beat: the local picture is on screen in the middle of its beat (correlation of the downscaled frame with the picture)
    def small(img):
        return np.asarray(img.convert("L").resize((64, 36), Image.LANCZOS), dtype=np.float32)

    def corr(a, b):
        a, b = a - a.mean(), b - b.mean()
        return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))

    ref = small(Image.open(pic))
    mid = M.frame_png(V, int(15.8 * FPS))
    map_t = M.frame_png(V, int(10.0 * FPS))
    result["map_render"]["archive_picture_correlation_mid_beat"] = round(corr(small(mid), ref), 3)
    result["map_render"]["map_frame_correlation_with_picture_at_10s"] = round(corr(small(map_t), ref), 3)
    ck["archive_picture_is_on_screen_mid_beat"] = result["map_render"]["archive_picture_correlation_mid_beat"] > 0.8 and result["map_render"]["map_frame_correlation_with_picture_at_10s"] < 0.5
    mid.save(work / "map_render_base" / "archive_mid_beat.png")
    # layer timing that can be measured offline: counterfactual renders without one layer, first frame that differs from the base render
    def decoded_small(path, frames):
        p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", str(frames), "-vf", "scale=480:270,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True, timeout=1800)
        return np.frombuffer(p.stdout, np.uint8).reshape(-1, 270 * 480).astype(np.int16)

    nwatch = int(9.0 * FPS)
    Bd = decoded_small(V, nwatch)
    timing = []
    for lid, bi in (("b1_fill2", 0), ("b1_marker1", 0), ("b1_caption3", 0)):
        pl2 = json.loads(json.dumps(plan))
        pl2["beats"][bi]["layers"] = [l for l in pl2["beats"][bi]["layers"] if l["id"] != lid]
        r2 = render_plan(pl2, work / f"map_render_without_{lid}", f"without {lid}")
        lay = next(l for l in plan["beats"][bi]["layers"] if l["id"] == lid)
        row = {"layer": lid, "type": lay["type"], "plan_t": lay["t"], "plan_frame": int(math.ceil(lay["t"] * FPS - 1e-9)), "render_ok": r2["render_ok"]}
        if r2["render_ok"]:
            Cd = decoded_small(r2["video"], nwatch)
            diff = np.abs(Bd - Cd).sum(axis=1)
            pf = row["plan_frame"]
            plateau = int(diff[pf:pf + 60].max()) if pf < len(diff) else int(diff.max())
            nz = next((i for i, v in enumerate(diff) if v > 0), None)
            ge5 = next((i for i, v in enumerate(diff) if v >= 0.05 * plateau and v > 0), None)
            jump = next((i for i in range(3, len(diff)) if diff[i] >= 0.01 * plateau and diff[i] >= 1.5 * max(1, int(diff[i - 3:i].max()))), None)
            row.update({"diff_plateau": plateau, "first_nonzero_frame": nz, "first_5pct_of_plateau_frame": ge5, "first_big_jump_frame": jump,
                        "offsets_vs_plan_frame": {"first_nonzero": None if nz is None else nz - pf, "5pct_of_plateau": None if ge5 is None else ge5 - pf, "big_jump": None if jump is None else jump - pf},
                        "diff_series_around_plan_frame": {str(i): int(diff[i]) for i in range(max(0, pf - 6), min(len(diff), pf + 8))},
                        "network_attempts_refused": r2["network_attempts_refused"]})
        timing.append(row)
    result["map_layer_render_timing"] = timing
    ck["no_network_attempts_in_counterfactual_renders"] = all(not t.get("network_attempts_refused") for t in timing)

# ================= F. determinism =================
for k in (1, 2):
    b1_, _, _ = make_map_beat("b1", 0.0, 9.2, MW, camera_start={"place": "Pakistan", "frame": "country"}, fills=[{"place": "Pakistan"}], markers=[{"place": "Gilgit"}],
                              captions=[{"text": "single river system", "anchor_word": "single"}], fly_to=[{"place": "Gilgit", "dur": 2.0, "t": 5.5}], purpose="where the river begins",
                              geo_intent="the river system of Pakistan")
    pl_ = assemble_plan(24.0, [b1_, b2, b3, b4], {"dissolve_s": 0.5})
    (tiny / f"plan{k}.json").write_text(json.dumps(pl_, indent=1, sort_keys=True))
ck["plan_builds_identical_same_process"] = sha(tiny / "plan1.json") == sha(tiny / "plan2.json") == result["map_plan"]["plan_sha256"]
for tag, inst in (("plain", False), ("instr", True)):
    for k in (1, 2):
        build_board_clip(CAP, WORDS, *BEAT, tiny / f"cap_{tag}{k}.mp4", instrument=inst, beat_id="b2", manifest_path=tiny / f"cap_{tag}{k}.json")
    ck[f"caption_clip_{tag}_bytes_identical"] = sha(tiny / f"cap_{tag}1.mp4") == sha(tiny / f"cap_{tag}2.mp4")
    ck[f"caption_clip_{tag}_frames_identical"] = fm(tiny / f"cap_{tag}1.mp4") == fm(tiny / f"cap_{tag}2.mp4")
    ck[f"caption_clip_{tag}_manifest_identical"] = (tiny / f"cap_{tag}1.json").read_text().replace(f"{tag}1", "X") == (tiny / f"cap_{tag}2.json").read_text().replace(f"{tag}2", "X")
result["clip_sha256"] = {"caption_plain": sha(tiny / "cap_plain1.mp4"), "caption_instrumented": sha(tiny / "cap_instr1.mp4")}
result["clip_bytes"] = (tiny / "cap_plain1.mp4").stat().st_size
src_text = Path(__file__).read_text()
cut = src_text.index("# ================= A. caption timing unit tests")
child = src_text[:cut].replace("sys.argv[1]", repr(str(root))).replace("sys.argv[2]", repr(str(work / "child"))).replace('(sys.argv[3] if len(sys.argv) > 3 else "0,0.5")', '"0"')
child = child.replace("here = Path(__file__).resolve().parent", f"here = Path({str(here)!r})")
cap_src = src_text[src_text.index("CAP = ["):src_text.index("LAYOUT = [")]
child += "\nBEAT = (7.0, 17.0)\n" + cap_src + f"\nbuild_board_clip(CAP, WORDS, *BEAT, Path({str(tiny / 'cap_child.mp4')!r}), beat_id='b2')\n"
(work / "child_build.py").write_text(child)
subprocess.run([sys.executable, "-B", "-I", str(work / "child_build.py")], capture_output=True, timeout=1800)
ck["caption_clip_identical_across_processes"] = (tiny / "cap_child.mp4").exists() and sha(tiny / "cap_child.mp4") == sha(tiny / "cap_plain1.mp4")
(work / "verify_m3.json").write_text(json.dumps(result, indent=1, default=str))
print(json.dumps({k: v for k, v in ck.items() if v is not True}, indent=1))
print("checks:", len(ck), "true:", sum(1 for v in ck.values() if v is True))
