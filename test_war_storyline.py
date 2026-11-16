"""War Documentary reference phases S, B, C, D, E: storyline devices, sound mix, speaker quote card, article plate, map banner and inset,
flashes and pace. Built from docs/war/REFERENCE_AIR_DEFENSE.md sections 3 and 7."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import audio as AU
from cinematic_explainer.war import broadcast as B
from cinematic_explainer.war import catalog as C
from cinematic_explainer.war import graphics_lib as GL
from cinematic_explainer.war import maps_tactical as MT
from cinematic_explainer.war import semantics as S
from cinematic_explainer.war import storyline as SL


class P:
    def __init__(self, shots=(), layers=()):
        self.shots, self.layers, self.log = list(shots), list(layers), []


def rows_of(texts, clip=None, meta=None, d=6.0):
    out, t = [], 0.0
    for i, x in enumerate(texts):
        out.append({"_start": t, "_end": t + d, "_no": i + 1, "text": x, "footage": clip, "footage_meta": dict(meta or {})})
        t += d
    return out


class Clip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clips = []
        for i in range(3):
            c = str(Path(cls.tmp.name, f"c{i}.mp4"))
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x180:d=12", "-r", "25", c], check=True)
            cls.clips.append(c)
        cls.voice = str(Path(cls.tmp.name, "v.wav"))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=8", cls.voice], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


class StoryDevices(Clip):
    def test_roadmap_said_then_each_part_lit(self):
        rows = rows_of(["Kyiv is working on it in three ways. Borrow, find, and build.", "First, borrow. Zelensky asked for missiles.",
                        "Second, find. The Dutch pledged money.", "Third, build. A licence is not a factory."])
        plan = P()
        n = SL.roadmap(plan, rows, C)
        self.assertEqual(n, 4)
        self.assertEqual(plan.layers[0].params["words"], ["Borrow", "find", "build"])
        self.assertEqual([ly.params.get("current") for ly in plan.layers[1:]], [0, 1, 2])
        self.assertEqual(SL.fx_roadmap(1.0, 3.0, plan.layers[2].params).size, (1280, 720))

    def test_flash_on_turns_never_on_human_cost(self):
        rows = rows_of(["Fighting went on through the night.", "Then Washington made its move.", "A woman was killed and children were hurt.",
                        "The talks went on.", "So why are other countries paying?"], clip=self.clips[0], d=12.0)
        plan = P([Shot(self.clips[0], 0.0, 60.0, 0.0)])
        SL.flashes(plan, rows, C)
        starts = [round(ly.start) for ly in plan.layers]
        self.assertIn(12, starts)
        self.assertIn(48, starts)
        self.assertNotIn(24, starts)

    def test_pace_cuts_strike_lines_on_fitting_footage_only(self):
        fit = {"csv_pick": True}
        rows = rows_of(["Russia fired missiles at the grid overnight.", "The loan scheme was explained to parliament."], clip=self.clips[0], meta=fit)
        rows = rows_of(["Russia fired missiles at the grid overnight.", "The loan scheme was explained to parliament."], clip=self.clips[0], meta=fit, d=12.0)
        plan = P([Shot(self.clips[0], 0.0, 12.0, 0.0), Shot(self.clips[0], 12.0, 24.0, 0.0)])
        SL.pace(plan, rows, C)
        strike = [s for s in plan.shots if s.end <= 12.01]
        self.assertGreaterEqual(len(strike), 3)
        self.assertTrue(all(s.end - s.start >= SL.PACE_MIN_S - 0.01 for s in strike))   # never a flicker (owner, 2026-11-09)
        self.assertEqual(len([s for s in plan.shots if s.start >= 11.99]), 1)
        plan2 = P([Shot(self.clips[0], 0.0, 6.0, 0.0)])
        SL.pace(plan2, rows_of(["Russia fired missiles at the grid overnight."], clip=self.clips[0]), C)
        self.assertEqual(len(plan2.shots), 1)                         # no match data: cuts unchanged

    def test_callback_and_recap_reuse_the_films_own_pictures(self):
        fit = {"csv_pick": True}
        rows = [{"_start": 0.0, "_end": 6.0, "_no": 1, "text": "Putin praised the Kinzhal missile on stage.", "footage": self.clips[1], "footage_meta": fit},
                {"_start": 6.0, "_end": 12.0, "_no": 2, "text": "Air defence crews worked all night.", "footage": self.clips[0], "footage_meta": fit},
                {"_start": 12.0, "_end": 18.0, "_no": 3, "text": "Putin had said the Kinzhal could beat every system.", "footage": self.clips[2],
                 "footage_meta": fit}]
        plan = P([Shot(self.clips[1], 0, 6, 0), Shot(self.clips[0], 6, 12, 0), Shot(self.clips[2], 12, 18, 0)])
        res = SL.callbacks_and_recap(plan, rows, C)
        self.assertEqual(res["callbacks"], 1)
        self.assertTrue(any(s.path == self.clips[1] and s.start >= 12 for s in plan.shots))
        self.assertAlmostEqual(sum(s.end - s.start for s in plan.shots), 18.0, places=2)   # no gap, no overlap


class TextRules(unittest.TestCase):
    def test_question_box_evidence_hold_and_contrast(self):
        t = "So why are other countries paying for America's missiles?"
        self.assertTrue(t.endswith("?"))
        self.assertTrue(B._EVIDENCE.search("This is the bridge the next morning."))
        t = "In October Ukraine used 35 interceptors while only 12 arrived."
        lab = B._label_of(S.analyze_scene(t, C, None, 0, 5).sentences[0], t)
        self.assertIn("VS", lab[0])

    def test_speaker_quote_from_reported_words(self):
        t = "Zelensky said that partners had sent three times fewer air defence missiles this year."
        A = S.analyze_scene(t, C, None, 0, 6)
        sq = B._speaker_quote_of(A, A.sentences[0])
        self.assertIsNotNone(sq)
        params, _a = sq
        self.assertEqual(params["name"], "Volodymyr Zelensky")
        self.assertIn("three times fewer", params["quote"])
        self.assertEqual(len(params["words_t"]), len(params["quote"].split()))
        self.assertEqual(GL.lay_speaker_quote(2.0, 6.0, params).size, (1280, 720))
        self.assertIsNone(GL.lay_speaker_quote(1.0, 3.0, {"name": "x"}))


class Sound(Clip):
    def test_sfx_events_spaced_and_mix_normalised(self):
        ls = [Layer("tac_map", 1.0, 4.0, {}), Layer("bc_bigword", 1.5, 3.0, {}), Layer("bc_label", 5.5, 7.0, {})]
        ev = AU.sfx_events(ls)
        self.assertEqual([e[1] for e in ev], ["whoosh", "text"])        # the impact 0.65 s after the whoosh is dropped
        out = AU.build_mix(self.voice, 8.0, ls, str(Path(self.tmp.name, "mix.m4a")), {})
        self.assertTrue(out.endswith("mix.m4a"))
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", out, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
        lufs = float([l for l in r.stderr.splitlines() if l.strip().startswith("I:")][-1].split()[1])
        self.assertAlmostEqual(lufs, -14.0, delta=1.5)

    def test_transitions_and_bed_sit_well_under_the_voice(self):
        """Owner 2026-11-16: background and transitions very loud (whooshes peaked level with the voice, one every ~10 s)."""
        self.assertLessEqual(max(AU.SFX_GAIN.values()), 0.12)
        self.assertLessEqual(AU.MUSIC_DB, -22.0)
        ls = [Layer("tac_map", 1.0, 3.0, {}), Layer("lay_stat_split", 3.5, 6.0, {}), Layer("kit_chart", 6.0, 9.0, {})]
        self.assertEqual([round(e[0], 2) for e in AU.sfx_events(ls)], [0.85, 5.85])     # at most one transition sound every 4 s

    def test_no_voice_no_mix(self):
        self.assertIsNone(AU.build_mix(None, 8.0, [], str(Path(self.tmp.name, "x.m4a")), {}))


class Maps(Clip):
    def test_banner_and_inset_draw(self):
        p = {"theme": "tactical", "places": [{"name": "Kyiv"}], "banner": {"text": "1,214 drones", "sub": "29 October", "start": 0.2},
             "inset": {"place": "Kyiv", "video": self.clips[0], "at": 1.0, "start": 0.3}}
        a = MT.tac_map(2.0, 5.0, p)
        q = dict(p)
        q.pop("banner")
        q.pop("inset")
        b = MT.tac_map(2.0, 5.0, q)
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_article_plate_from_the_scenes_clip(self):
        im = GL.lay_document(2.0, 5.0, {"text": "The ministry said the plant was hit.", "outlet": "Reuters", "title": "Plant hit", "plate": self.clips[0]})
        self.assertEqual(im.size, (1280, 720))


class CleanOpening(unittest.TestCase):
    """Owner 2026-11-16: 'the opening is very very bad, no videos in the start' (cards over the opening scenes' own pictures)."""

    def test_first_seconds_show_the_scenes_own_pictures(self):
        from cinematic_explainer.war import direction as D

        shots = [Shot("/x/001.war.mp4", 0.0, 7.0, 0.0), Shot("/x/002.mp4", 7.0, 14.0, 0.0), Shot("/x/war_backdrop_v3.mp4", 14.0, 30.0, 0.0)]
        layers = [Layer("lay_document", 0.0, 5.0, {}, dim=True), Layer("institution_card", 5.0, 7.0, {}), Layer("kit_badge", 0.0, 7.0, {}),
                  Layer("kit_title", 0.5, 6.0, {"text": "Who is winning"}, dim=True), Layer("lay_stat_split", 8.0, 12.0, {}),
                  Layer("lay_stat_split", 16.0, 20.0, {}), Layer("kit_grain", 0.0, 200.0, {})]
        plan, counts = P(shots, layers), {}
        D._clean_opening(plan, counts, 15.0)
        kinds = [(l.kind, l.start) for l in plan.layers]
        self.assertNotIn(("lay_document", 0.0), kinds)
        self.assertNotIn(("institution_card", 5.0), kinds)
        self.assertNotIn(("lay_stat_split", 8.0), kinds)
        self.assertIn(("kit_badge", 0.0), kinds)                       # small marks stay
        self.assertIn(("lay_stat_split", 16.0), kinds)                 # after the opening nothing changes
        title = [l for l in plan.layers if l.kind == "kit_title"][0]
        self.assertTrue(title.params.get("over"))
        self.assertLessEqual(title.end - title.start, 3.61)

    def test_opening_cards_come_back_as_graphics_over_the_picture(self):
        """Owner 2026-11-16: 'still opening have no rich graphics': the cleared cards return as motion graphics over the playing clip."""
        from cinematic_explainer.war import direction as D

        shots = [Shot("/x/001.war.mp4", 0.0, 8.0, 0.0), Shot("/x/002.mp4", 8.0, 14.0, 0.0)]
        layers = [Layer("lay_document", 0.0, 5.0, {}, dim=True), Layer("bc_caption", 1.0, 3.0, {"text": "x"}), Layer("kit_badge", 0.0, 8.0, {}),
                  Layer("lay_stat_split", 8.5, 13.0, {"shown": "365", "label": "missiles", "value": 365}, dim=True), Layer("kit_grain", 0.0, 200.0, {})]
        rows = [{"_start": 0.0, "_end": 8.0, "_no": 1, "text": "In October 2026, Russia lost more ground in Ukraine than it gained."},
                {"_start": 8.0, "_end": 14.0, "_no": 2, "text": "Russia sent 365 missiles and drones at the grid in one night."}]
        plan = P(shots, layers)
        D._clean_opening(plan, {}, 15.0, rows)
        over = [l for l in plan.layers if (l.params or {}).get("over")]
        self.assertEqual([l.kind for l in over], ["kit_datecard", "kit_kinetic"])
        self.assertGreaterEqual(over[0].start, 0.6)                       # the first frame is the picture itself
        self.assertEqual(over[1].params["text"], "365 missiles")
        self.assertFalse(any(l.dim for l in over))
        self.assertNotIn("bc_caption", [l.kind for l in plan.layers])      # one text at a time
        self.assertIn("kit_badge", [l.kind for l in plan.layers])

    def test_cards_stay_where_the_opening_has_no_footage(self):
        from cinematic_explainer.war import direction as D

        plan = P([Shot("/x/war_backdrop_v3.mp4", 0.0, 20.0, 0.0)], [Layer("lay_document", 0.0, 5.0, {}, dim=True)])
        D._clean_opening(plan, {}, 15.0)
        self.assertEqual([l.kind for l in plan.layers], ["lay_document"])


if __name__ == "__main__":
    unittest.main()
