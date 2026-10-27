"""Motion kit tests (reference-2 plan, "Phase 9"; the file is named test_motion_kit because test_phase9_* is the footage phase): presets, verdict stamps, year plates, assets, packaging,
never-stop fallback, and the proof that motion=False changes nothing.

Offline and deterministic; nothing is encoded (plans are built with materialize=False, frames are drawn in memory).
usage: python3 -B explainer/spike/test_motion_kit.py   (from the repository root)"""
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import synth, run, SCRIPT as KOREA_SCRIPT, WORDS as KOREA_WORDS, DUR as KOREA_DUR      # noqa: E402
from explainer.board import render as R                                       # noqa: E402
from explainer.board import layout as LY                                      # noqa: E402
from explainer.board.cues import Cue                                          # noqa: E402
from explainer.board.dry import dry_build                                     # noqa: E402
from explainer.director import DirectorOptions                                # noqa: E402
from explainer.director.segment import norm                                   # noqa: E402
from explainer.motion import presets as P                                     # noqa: E402
from explainer.motion import sprites as MS                                    # noqa: E402
from explainer.motion import build_assets as BA                               # noqa: E402

STAMPS = ROOT / "explainer" / "assets" / "stamps"
EVIDENCE = ROOT / "docs" / "explainer" / "phase_motion_evidence"
FPS = 30
SCRIPT = ("The old fortress had stood for centuries above the river. Its walls were thick and its guards were proud. "
          "Then the army arrived and the garrison was surrounded within a single week. The commander wrote that the situation was hopeless. "
          "In 1944 the siege entered its final winter and the supplies ran out. Every officer knew the plan was worthless and the orders were wrong. "
          "The soldiers who stayed were caught between the river and the guns. Nobody expected help from the north. "
          "By 1945 the survivors were freed and the fortress was silent again. The long road home began that summer.")
VERDICTS = ("The plan was worthless. " * 1)


def tree_hash(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in d.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(d)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


class Cache:
    _r = {}

    @classmethod
    def plan(cls, motion=True, script=SCRIPT):
        k = (motion, script)
        if k not in cls._r:
            w, d = synth(script)
            cls._r[k] = (run(w, script, d, motion=motion), w, d)
        return cls._r[k]


def motion_records(rep):
    return {b: v["motion"] for b, v in rep["beat_details"].items() if isinstance(v, dict) and v.get("motion")}


def beat_cues(rep, bid):
    return [Cue(**c) for c in rep["beat_details"][bid]["cue_specs"]]


def beat_span(plan, bid):
    b = next(b for b in plan["beats"] if b["id"] == bid)
    return b["start"], b["end"]


def build(rep, plan, words, bid, cues=None):
    s, e = beat_span(plan, bid)
    return dry_build(cues if cues is not None else beat_cues(rep, bid), words, s, e, beat_id=bid)


def all_stamps(rep):
    return [(bid, s) for bid, m in motion_records(rep).items() for s in m["stamps"]]


def all_plates(rep):
    return [(bid, s) for bid, m in motion_records(rep).items() for s in m["plates"]]


class Presets(unittest.TestCase):
    def test_pure_and_deterministic(self):
        ages = [i / 120.0 for i in range(0, 60)]
        a = [(P.slam(x), P.slide_in(x), P.slam_settled(x)) for x in ages]
        b = [(P.slam(x), P.slide_in(x), P.slam_settled(x)) for x in ages]
        self.assertEqual(a, b)
        self.assertEqual(P.slam(0.1), P.slam(0.1 + 0.0001))             # a frame depends only on the 30 fps frame the age falls in
        self.assertEqual(P.slam(0.1), P.slam(0.1 + 1 / 30 - 0.0005))

    def test_slam_settles_within_8_frames_with_overshoot(self):
        self.assertLessEqual(P.SLAM_FRAMES, 8)
        self.assertTrue(P.slam_settled((P.SLAM_FRAMES - 1) / FPS))
        self.assertFalse(P.slam_settled((P.SLAM_FRAMES - 2) / FPS))
        self.assertEqual(P.slam(7 / FPS), (1.0, 1.0, 0.0, 0, 0))
        self.assertEqual(P.slam(5.0), (1.0, 1.0, 0.0, 0, 0))              # and stays there
        scales = [P.SLAM[i][0] for i in range(P.SLAM_FRAMES)]
        self.assertGreater(scales[0], 1.3)                                # starts large
        self.assertLess(min(scales), 1.0)                                 # undershoots (the impact) ...
        self.assertGreater(max(scales[P.IMPACT_FRAME + 1:]), 1.0)         # ... and overshoots back
        self.assertEqual([P.SLAM[i][1] for i in range(P.IMPACT_FRAME, P.SLAM_FRAMES)], [1.0] * (P.SLAM_FRAMES - P.IMPACT_FRAME))

    def test_slide_in_is_monotonic_and_lands(self):
        offs = [P.slide_in(i / FPS)[0] for i in range(0, 14)]
        self.assertEqual(offs, sorted(offs, reverse=True))
        self.assertEqual(P.slide_in(P.SLIDE_FRAMES / FPS), (0, 1.0))
        self.assertGreater(offs[0], 0)


class Stamps(unittest.TestCase):
    def test_a_stamp_is_added_on_a_spoken_verdict_word_and_only_when_motion_is_on(self):
        r, _w, _d = Cache.plan()
        self.assertIsNotNone(r.plan, r.problems)
        self.assertEqual(r.problems, [])
        words = {s["text"] for _b, s in all_stamps(r.report)}
        self.assertTrue(words & {"SURROUNDED", "CAUGHT"}, words)
        off, _w2, _d2 = Cache.plan(False)
        self.assertEqual(all_stamps(off.report), [])
        self.assertFalse(any(c["params"] and c["params"].get("style") in ("stamp", "plate") for v in off.report["beat_details"].values() if isinstance(v, dict) for c in v.get("cue_specs", [])))

    def test_first_visible_frame_is_on_the_verdict_word_and_absent_the_frame_before(self):
        r, w, _d = Cache.plan()
        n = 0
        for bid, s in all_stamps(r.report):
            n += 1
            _p, res, items = build(r.report, r.plan, w, bid)
            st = next(x for x in items if x.cue_id == s["cue"])
            bs0, _be0 = beat_span(r.plan, bid)
            lag = st.onset - (s["t"] - bs0)                              # item onsets are clip seconds (from the beat's start); the word time is absolute
            self.assertGreaterEqual(lag, -1e-6, "the stamp may not land before the word")
            self.assertLessEqual(lag, 0.3 + 1e-6)
            self.assertAlmostEqual(st.first_frame / FPS, st.onset, delta=1 / FPS + 1e-6)
            bs, _be = beat_span(r.plan, bid)
            without = [x for x in items if x.cue_id != s["cue"]]
            before = (st.first_frame - 1) / FPS
            a = R.draw_frame(items, before, (1920, 1080), None, st.first_frame - 1, False)
            b = R.draw_frame(without, before, (1920, 1080), None, st.first_frame - 1, False)
            self.assertEqual(a.tobytes(), b.tobytes(), "the stamp is visible a frame before its first frame")
            c = R.draw_frame(items, st.onset, (1920, 1080), None, st.first_frame, False)
            d = R.draw_frame(without, st.onset, (1920, 1080), None, st.first_frame, False)
            self.assertNotEqual(c.tobytes(), d.tobytes(), "the stamp is not visible on its first frame")
        self.assertGreaterEqual(n, 2)

    def test_stamp_text_is_a_contiguous_quote_of_the_beat_narration(self):
        r, w, _d = Cache.plan()
        for bid, s in all_stamps(r.report):
            bs, be = beat_span(r.plan, bid)
            said = [re.sub(r"[^\w'-]", "", x[0]).upper() for x in w if bs - 1e-6 <= x[1] < be - 1e-6]
            parts = s["text"].split()
            self.assertTrue(any(said[i:i + len(parts)] == parts for i in range(len(said))), f"{s['text']!r} is not a contiguous quote of {said}")
            self.assertIn(norm(s["text"].lower()), P_VERDICTS())

    def test_no_two_stamps_within_15_seconds_and_at_most_one_per_beat(self):
        many = " ".join(f"The plan was worthless and the army was caught in the field and nobody was saved {i}." for i in range(1, 9)) + " The end was banned."
        r, _w, _d = Cache.plan(True, many)
        self.assertIsNotNone(r.plan, r.problems)
        times = sorted(s["t"] for _b, s in all_stamps(r.report))
        for a, b in zip(times, times[1:]):
            self.assertGreaterEqual(b - a, 15.0 - 1e-6)
        for m in motion_records(r.report).values():
            self.assertLessEqual(len(m["stamps"]), 1)
        skipped = [x for m in motion_records(r.report).values() for x in m["skipped"]]
        self.assertTrue(any("minimum 15 s" in x for x in skipped), skipped)

    def test_a_stamp_fits_the_frame_and_collides_with_nothing(self):
        r, w, _d = Cache.plan()
        for bid, s in all_stamps(r.report):
            self.assertEqual(r.report["beat_details"][bid]["problems"], [])
            _p, res, items = build(r.report, r.plan, w, bid)
            self.assertEqual(_p, [], _p)                                  # the layout gate (collision, margins, narrator zone) passes with the stamp in
            st = next(x for x in items if x.cue_id == s["cue"])
            x0, y0, x1, y1 = st.rect
            sx0, sy0, sx1, sy1 = LY.SAFE
            self.assertTrue(sx0 <= x0 and sy0 <= y0 and x1 <= sx1 and y1 <= sy1, (st.rect, LY.SAFE))
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            for f in range(P.IMPACT_FRAME, P.SLAM_FRAMES):               # impact, shake and the settled stamp, with the tilt: inside the safe area
                sp, (dx, dy) = MS.stamp_frame(st.lines[0], st.role, x1 - x0, y1 - y0, st.px, MS.variant_for(st.cue_id), MS.available_cached(), MS.tilt_for(st.cue_id), f)
                bx0, by0 = cx - sp.width // 2 + dx, cy - sp.height // 2 + dy
                self.assertTrue(sx0 <= bx0 and sy0 <= by0 and bx0 + sp.width <= sx1 and by0 + sp.height <= sy1, (f, bx0, by0, sp.size))

    def test_a_stamp_never_takes_another_elements_place(self):
        r, w, _d = Cache.plan()
        off, _w, _d2 = Cache.plan(False)
        for bid, s in all_stamps(r.report):
            on_ids = [c["id"] for c in r.report["beat_details"][bid]["cue_specs"]]
            off_ids = [c["id"] for c in off.report["beat_details"][bid]["cue_specs"]]
            self.assertEqual([i for i in on_ids if i != s["cue"]], off_ids)        # everything else is exactly what it was


def P_VERDICTS():
    from explainer.director import compose_motion as CM
    return CM.VERDICT | CM.VERDICT_GREEN


PLATE_SCRIPT = ("The old fortress had stood for centuries above the river. Its walls were thick and its guards were proud. Then the army arrived and the garrison was surrounded within a single week. "
                "The siege began in 1944. Every officer knew the plan was worthless and the orders were wrong. The soldiers who stayed were caught between the river and the guns. Nobody expected help from the north. "
                "A visitor in 1962 wrote about the quiet ruins and the tall grass. The war ended in 1945 and the survivors went home. The long road home began that summer.")


def r_opt():
    return DirectorOptions(look="reference", motion=True)


def pass_on(script, bid, extra=(), drop=(), state=None):
    """Run the real motion pass on a beat's motion-off cues (optionally with extra cues added or cues dropped). Returns (br, record, words, plan, off_report)."""
    from types import SimpleNamespace
    from explainer.director import segment as SG
    from explainer.director.compose_motion import motion_pass, new_state
    r, w, d = Cache.plan(False, script)
    s0, e0 = beat_span(r.plan, bid)
    cues = [Cue(**c) for c in r.report["beat_details"][bid]["cue_specs"] if c["id"] not in drop] + list(extra)
    br = SimpleNamespace(cues=cues, repairs=[])
    rec = motion_pass(br, bid, s0, e0, SG.sentences(w, script, d, 8.0), w, r_opt(), state or new_state())
    return br, rec, w, r.plan, r.report


def spec_texts(rep, bid):
    return [(c["id"], " ".join((c["text"] or "").split())) for c in rep["beat_details"][bid]["cue_specs"]]


class DateRule(unittest.TestCase):
    def test_the_importance_rule_is_deterministic_and_ordinary_years_score_below_the_bar(self):
        from explainer.director import compose_motion as CM
        from explainer.director import segment as SG
        w, d = synth(PLATE_SCRIPT)
        ss = SG.sentences(w, PLATE_SCRIPT, d, 8.0)
        first = next(g for g, x in enumerate(w) if CM._year_of(x[0]))
        got = {}
        for s in ss:
            for g in s.widx:
                y = CM._year_of(w[g][0])
                if y:
                    got[y] = CM.date_score(s, g, w, first)
        self.assertEqual(got, {y: CM.date_score(next(s for s in ss if any(w[g][0] == y for g in s.widx)), next(g for s in ss for g in s.widx if w[g][0] == y), w, first) for y in got})
        self.assertGreaterEqual(got["1944"][0], CM.DATE_MIN_SCORE)       # "The siege began in 1944": an event word, and the first year
        self.assertGreaterEqual(got["1945"][0], CM.DATE_MIN_SCORE)       # "The war ended in 1945"
        self.assertLess(got["1962"][0], CM.DATE_MIN_SCORE)               # "A visitor in 1962 wrote about the quiet ruins": ordinary
        self.assertEqual(CM.DATE_MIN_SCORE, 2)

    def test_an_ordinary_year_never_becomes_a_plate_and_says_why(self):
        r, w, _d = Cache.plan(True, PLATE_SCRIPT)
        self.assertNotIn("1962", [p["text"] for _b, p in all_plates(r.report)])
        skipped = [x for m in motion_records(r.report).values() for x in m["skipped"]]
        self.assertTrue(any("1962" in x and "ordinary year" in x for x in skipped), skipped)
        r2, _w, _d = Cache.plan(True, SCRIPT)                              # "the siege entered its final winter" in 1944 is the first year only: ordinary
        self.assertTrue(any("1944" in x and "ordinary year" in x for m in motion_records(r2.report).values() for x in m["skipped"]))

    def test_plates_are_at_least_15_seconds_apart(self):
        r, _w, _d = Cache.plan(True, PLATE_SCRIPT)
        ts = sorted(p["t"] for _b, p in all_plates(r.report))
        self.assertGreaterEqual(len(ts), 2)
        for a, b in zip(ts, ts[1:]):
            self.assertGreaterEqual(b - a, 15.0 - 1e-6)
        r3, _w, _d = Cache.plan(True, PLATE_SCRIPT.replace("The war ended in 1945", "The war ended in 1945") )
        self.assertEqual(ts, sorted(p["t"] for _b, p in all_plates(r3.report)))


class Plates(unittest.TestCase):
    def test_an_important_date_replaces_the_boards_own_year_tag_or_chip(self):
        r, w, _d = Cache.plan(True, PLATE_SCRIPT)
        off, _w, _d2 = Cache.plan(False, PLATE_SCRIPT)
        plates = dict(all_plates(r.report))
        self.assertEqual({b: p["text"] for b, p in plates.items()}, {"e4": "1944", "e7": "1945"})
        kinds = set()
        for bid, p in plates.items():
            self.assertEqual(len(p["replaced"]), 1, p)
            old = next(c for c in off.report["beat_details"][bid]["cue_specs"] if c["id"] == p["replaced"][0])
            kinds.add((old["kind"], (old["params"] or {}).get("style")))
            self.assertEqual(" ".join(old["text"].split()), p["text"])                    # only a bare year is ever replaced
            new_specs = {c["id"]: c for c in r.report["beat_details"][bid]["cue_specs"]}
            self.assertNotIn(old["id"], new_specs)                                         # the tag/chip is gone ...
            self.assertEqual(new_specs[p["cue"]]["anchor"], old["anchor"])                  # ... and the plate is on the same word
        self.assertEqual(kinds, {("visual", "tag"), ("chip", None)})                       # both ways the planner shows a year
        self.assertEqual(r.problems, [])

    def test_no_year_is_shown_twice_by_separate_elements(self):
        r, w, _d = Cache.plan(True, PLATE_SCRIPT)
        for bid, p in all_plates(r.report):
            texts = spec_texts(r.report, bid)
            standalone = [i for i, t in texts if t == p["text"]]
            self.assertEqual(standalone, [p["cue"]], texts)                               # exactly one element is the year itself
            for c in r.report["beat_details"][bid]["cue_specs"]:
                if c["id"] != p["cue"] and p["text"] in re.findall(r"\d+", c["text"] or ""):
                    self.assertNotIn(c["kind"], ("chip", "title", "header"))
                    self.assertNotIn((c["params"] or {}).get("style"), ("tag", "plate"))

    def test_the_duplicate_guard_still_rejects_a_genuinely_repeated_year(self):
        title = Cue("e4_ttl", "title", {"index": 0}, text="THE YEAR 1944", pos=(1100, 150))
        br, rec, w, plan, rep = pass_on(PLATE_SCRIPT, "e4", extra=[title])
        self.assertEqual(rec["plates"], [])
        self.assertTrue(any("would repeat the year" in x for x in rec["skipped"]), rec)
        self.assertTrue(any(c.id == "e4_tag1" for c in br.cues), "the board's own year is untouched when the plate is refused")
        br2, rec2, *_ = pass_on(SCRIPT, "e7")                                              # no tag to replace and a running phrase already carries 1945
        self.assertEqual(rec2["plates"], [])
        self.assertTrue(any("would repeat the year" in x for x in rec2["skipped"]), rec2)
        br3, rec3, *_ = pass_on(PLATE_SCRIPT, "e4", extra=[Cue("e4_tag9", "visual", {"index": 0}, text="1944 army", role="blue", pos=(1000, 120), params={"style": "tag"})])
        self.assertEqual(rec3["plates"], [])                                                # a second tag with the number: not replaceable, so it blocks

    def test_a_plate_is_a_spoken_year_lands_on_the_word_and_is_absent_the_frame_before(self):
        r, w, _d = Cache.plan(True, PLATE_SCRIPT)
        for bid, p in all_plates(r.report):
            bs, be = beat_span(r.plan, bid)
            self.assertIn(p["text"], [re.sub(r"[^\w]", "", x[0]) for x in w if bs - 1e-6 <= x[1] < be - 1e-6])
            self.assertRegex(p["text"], r"^(1[0-9]{3}|20[0-9]{2})$")
            _p, _r, items = build(r.report, r.plan, w, bid)
            it = next(x for x in items if x.cue_id == p["cue"])
            lag = it.onset - (p["t"] - bs)
            self.assertTrue(-1e-6 <= lag <= 0.3 + 1e-6, lag)
            without = [x for x in items if x.cue_id != p["cue"]]
            tb = it.onset - 1 / FPS
            self.assertEqual(R.draw_frame(items, tb, (1920, 1080), None, it.first_frame - 1, False).tobytes(), R.draw_frame(without, tb, (1920, 1080), None, it.first_frame - 1, False).tobytes())
            self.assertNotEqual(R.draw_frame(items, it.onset, (1920, 1080), None, it.first_frame, False).tobytes(), R.draw_frame(without, it.onset, (1920, 1080), None, it.first_frame, False).tobytes())

    def test_a_plate_keeps_the_safe_margins_and_collides_with_nothing(self):
        r, w, _d = Cache.plan(True, PLATE_SCRIPT)
        for bid, p in all_plates(r.report):
            self.assertEqual(r.report["beat_details"][bid]["problems"], [])
            probs, _res, items = build(r.report, r.plan, w, bid)
            self.assertEqual(probs, [])
            it = next(x for x in items if x.cue_id == p["cue"])
            sx0, sy0, sx1, sy1 = LY.SAFE
            x0, y0, x1, y1 = it.rect
            self.assertTrue(sx0 <= x0 and sy0 <= y0 - 60 + 60 and x1 <= sx1 and y1 <= sy1, it.rect)
            self.assertGreaterEqual(y0 - 60 + 60, sy0)
            for o in items:
                if o.cue_id != it.cue_id and o.kind != "narrator" and o.rect != (0, 0, 0, 0):
                    self.assertTrue(x1 <= o.rect[0] or o.rect[2] <= x0 or y1 <= o.rect[1] or o.rect[3] <= y0, f"plate overlaps {o.cue_id}")

    def test_a_stamp_and_a_plate_in_one_beat_never_overlap(self):
        br, rec, w, plan, rep = pass_on(PLATE_SCRIPT, "e4")                              # fresh state: "worthless" and the 1944 plate land in the same beat
        self.assertEqual(len(rec["plates"]), 1, rec)
        self.assertEqual(len(rec["stamps"]), 1, rec)
        s0, e0 = beat_span(plan, "e4")
        probs, _res, items = dry_build(br.cues, w, s0, e0, beat_id="e4")
        self.assertEqual(probs, [])
        two = [x for x in items if x.style in ("stamp", "plate")]
        self.assertEqual(len(two), 2)
        a, b = two
        end = lambda x: 1e9 if x.hide_at is None else x.hide_at
        concurrent = a.onset < end(b) and b.onset < end(a)                                 # the board clears between sentences: only elements on screen together can collide (H07)
        self.assertFalse(concurrent and not (a.rect[2] <= b.rect[0] or b.rect[2] <= a.rect[0] or a.rect[3] <= b.rect[1] or b.rect[3] <= a.rect[1]), (a.rect, b.rect))

    def test_a_plate_slides_in_and_then_holds_still(self):
        r, w, _d = Cache.plan(True, PLATE_SCRIPT)
        bid, p = all_plates(r.report)[0]
        _p, _r, items = build(r.report, r.plan, w, bid)
        it = next(x for x in items if x.cue_id == p["cue"])
        f = [R.draw_frame(items, it.onset + k / FPS, (1920, 1080), None, it.first_frame + k, False) for k in (0, 3, 9)]
        self.assertEqual(len({x.tobytes() for x in f}), 3)
        self.assertTrue(it.hide_at is None or it.hide_at > it.onset + 0.5, (it.onset, it.hide_at))      # the board's own clear (it replaces the tag's lifetime) keeps the plate on for at least this long
        later = R.draw_frame(items, it.onset + 0.4, (1920, 1080), None, it.first_frame + 12, False)
        self.assertEqual(f[2].crop(it.rect).tobytes(), later.crop(it.rect).tobytes())


class Assets(unittest.TestCase):
    def test_build_check_passes_and_masks_verify(self):
        self.assertEqual(BA.main(["--check"]), 0)
        m = json.loads((STAMPS / "manifest.json").read_text())
        self.assertEqual(sorted(m["masks"]), ["a", "b"])
        for slot in m["masks"].values():
            b = (STAMPS / slot["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(b).hexdigest(), slot["sha256"])
            self.assertEqual(len(b), slot["bytes"])
        self.assertTrue(MS.available())

    def test_packaging_lists_the_stamps_folder(self):
        from explainer import packaging as PK
        self.assertIn("assets/stamps", PK.DATA_DIRS)
        shipped = {Path(src).name for src, _dst in PK.data_files(ROOT)}
        self.assertTrue({"grunge_a.png", "grunge_b.png"} <= shipped)
        self.assertEqual(sorted(p.name for p in STAMPS.iterdir()), ["grunge_a.png", "grunge_b.png", "manifest.json"])

    def test_nothing_is_written_under_assets_during_a_render(self):
        before = tree_hash(ROOT / "explainer" / "assets")
        w, d = synth(SCRIPT)
        r = run(w, SCRIPT, d, motion=True)
        bid, s = all_stamps(r.report)[0]
        _p, _r, items = build(r.report, r.plan, w, bid)
        for t in (0.0, 5.0, 12.0):
            R.draw_frame(items, t, (1920, 1080), None, int(t * 30), False)
        self.assertEqual(tree_hash(ROOT / "explainer" / "assets"), before)

    def test_a_missing_or_damaged_texture_gives_a_plain_stamp_and_a_note_never_a_failure(self):
        saved = (MS.ASSET_DIR, dict(MS._AVAILABLE))
        try:
            for how in ("missing", "damaged", "no_manifest"):
                with tempfile.TemporaryDirectory() as td:
                    d = Path(td) / "stamps"
                    shutil.copytree(STAMPS, d)
                    if how == "missing":
                        (d / "grunge_a.png").unlink()
                    elif how == "damaged":
                        (d / "grunge_b.png").write_bytes(b"not a png")
                    else:
                        (d / "manifest.json").unlink()
                    MS.ASSET_DIR = d
                    MS.manifest.cache_clear()
                    MS._mask.cache_clear()
                    MS.stamp_frame.cache_clear()
                    MS.stamp_base.cache_clear()
                    MS._AVAILABLE.clear()
                    self.assertFalse(MS.available(), how)
                    w, dur = synth(SCRIPT)
                    r = run(w, SCRIPT, dur, motion=True)
                    self.assertIsNotNone(r.plan, (how, r.problems))
                    self.assertEqual(r.problems, [], how)
                    stamps = all_stamps(r.report)
                    self.assertTrue(stamps, how)
                    notes = [x for v in r.report["beat_details"].values() if isinstance(v, dict) for x in v.get("repairs", [])]
                    self.assertTrue(any("stamp texture" in x and "plain" in x for x in notes), (how, notes))
                    specs = [c for v in r.report["beat_details"].values() if isinstance(v, dict) for c in v.get("cue_specs", []) if (c.get("params") or {}).get("style") == "stamp"]
                    self.assertTrue(all(c["params"]["texture"] is False for c in specs))
                    bid, s = stamps[0]
                    _p, _r, items = build(r.report, r.plan, w, bid)
                    st = next(x for x in items if x.cue_id == s["cue"])
                    im = R.draw_frame(items, st.onset + 0.3, (1920, 1080), None, st.first_frame + 9, False)       # drawing works without the texture
                    self.assertEqual(im.size, (1920, 1080))
        finally:
            MS.ASSET_DIR = saved[0]
            MS.manifest.cache_clear()
            MS._mask.cache_clear()
            MS.stamp_frame.cache_clear()
            MS.stamp_base.cache_clear()
            MS._AVAILABLE.clear()
            MS._AVAILABLE.update(saved[1])
        self.assertTrue(MS.available())


class OffByDefault(unittest.TestCase):
    def test_motion_is_off_by_default_and_absent_from_the_disabled_report(self):
        self.assertIs(DirectorOptions().motion, False)
        r, _w, _d = Cache.plan(False)
        self.assertNotIn("motion", r.report["options"])
        on, _w2, _d2 = Cache.plan(True)
        self.assertIs(on.report["options"]["motion"], True)

    def test_motion_false_equals_the_recorded_head_plan_cue_keys_and_clip_hashes(self):
        """The baseline JSON was recorded from HEAD's explainer/ (a copy outside the working tree), before any motion edit: plan, options, cue specs and clip names of two scripts, both looks."""
        base = json.loads((EVIDENCE / "disabled_path_baseline_HEAD.json").read_text())

        def sha(o):
            return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()
        cases = {"korea": (KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR)}
        w, d = synth(SCRIPT)
        cases["verdicts"] = (w, SCRIPT, d)
        seen = 0
        for k, (ww, ss, dd) in cases.items():
            for look in ("reference", "classic"):
                r = run(ww, ss, dd, look=look)
                bd = r.report["beat_details"]
                got = {"plan_sha": sha(r.plan), "options_sha": sha(r.report["options"]), "problems": r.problems,
                       "cue_specs_sha": sha({b: v["cue_specs"] for b, v in bd.items() if isinstance(v, dict) and "cue_specs" in v}),
                       "clips": {b: v["clip"] for b, v in bd.items() if isinstance(v, dict) and "clip" in v}, "beats": len(r.plan["beats"])}
                self.assertEqual(got, base[f"{k}/{look}"], f"{k}/{look}")
                seen += 1
        self.assertEqual(seen, 4)

    def test_the_integration_setting_is_off_unless_clearly_on(self):
        from explainer.integration import motion_enabled
        for bad in (None, {}, {"explainer_motion": None}, {"explainer_motion": "no"}, {"explainer_motion": 0}, {"explainer_motion": 2}, {"explainer_motion": [1]}, {"explainer_motion": "maybe"}, "x", 5):
            self.assertFalse(motion_enabled(bad), bad)
        for good in ({"explainer_motion": True}, {"explainer_motion": "true"}, {"explainer_motion": 1}, {"explainer_motion": "On"}):
            self.assertTrue(motion_enabled(good), good)


class Determinism(unittest.TestCase):
    def test_the_same_plan_twice_gives_identical_bytes(self):
        w, d = synth(SCRIPT)
        a = run(w, SCRIPT, d, motion=True)
        b = run(w, SCRIPT, d, motion=True)
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))
        self.assertEqual(json.dumps(a.report["beat_details"], sort_keys=True, default=str), json.dumps(b.report["beat_details"], sort_keys=True, default=str))
        bid, s = all_stamps(a.report)[0]
        _p, _r, ia = build(a.report, a.plan, w, bid)
        _p, _r, ib = build(b.report, b.plan, w, bid)
        st = next(x for x in ia if x.cue_id == s["cue"])
        for k in range(0, 12):
            t = st.onset + k / FPS
            fa = R.draw_frame(ia, t, (1920, 1080), None, st.first_frame + k, False)
            fb = R.draw_frame(ib, t, (1920, 1080), None, st.first_frame + k, False)
            self.assertEqual(hashlib.sha256(fa.tobytes()).hexdigest(), hashlib.sha256(fb.tobytes()).hexdigest())

    def test_the_motion_clip_name_differs_only_for_beats_that_gained_a_cue(self):
        on, _w, _d = Cache.plan(True)
        off, _w2, _d2 = Cache.plan(False)
        added = set(motion_records_with_cues(on.report))
        for bid, v in off.report["beat_details"].items():
            if isinstance(v, dict) and "clip" in v:
                same = on.report["beat_details"][bid]["clip"] == v["clip"]
                self.assertEqual(same, bid not in added, bid)


def motion_records_with_cues(rep):
    return [b for b, m in motion_records(rep).items() if m["stamps"] or m["plates"]]


if __name__ == "__main__":
    unittest.main(verbosity=2)
