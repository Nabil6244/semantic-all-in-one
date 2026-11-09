"""Regressions found in the Moskva 1-minute render (2026-11-09) and fixed in the audit pass: general rules, synthetic inputs."""

import unittest
from types import SimpleNamespace as NS

from cinematic_explainer.render import Layer
from cinematic_explainer.war import direction as D
from cinematic_explainer.war import director_rules as R
from cinematic_explainer.war import director_search as DS
from cinematic_explainer.war import footage_director as FD
from cinematic_explainer.war import narration_read as N
from cinematic_explainer.war import semantics as S


class BackingFieldDrawnUnder(unittest.TestCase):
    def test_a_longer_field_that_starts_with_the_cards_is_drawn_first(self):
        layers = [Layer("stat_number", 20.24, 21.84, {}), Layer("lay_document", 20.24, 26.48, {}), Layer("kit_field", 20.24, 30.56, {}),
                  Layer("kit_field", 20.2, 30.56, {})]
        layers.sort(key=D.draw_order)
        kinds = [ly.kind for ly in layers]
        self.assertEqual(kinds[:2], ["kit_field", "kit_field"])
        self.assertEqual(set(kinds[2:]), {"stat_number", "lay_document"})


class SpokenNumbers(unittest.TestCase):
    def nums(self, text):
        return [(n.value, n.raw) for n in S.find_numbers(text)[0]]

    def test_whole_spoken_numbers(self):
        self.assertEqual(self.nums("a cruiser more than one hundred eighty metres long")[0], (180.0, "one hundred eighty"))
        self.assertEqual(self.nums("About five hundred sailors were on board.")[0], (500.0, "five hundred"))
        self.assertIn((27.0, "twenty seven"), self.nums("one dead and twenty seven missing"))
        self.assertEqual(self.nums("four thousand kilometres away")[0][0], 4000.0)
        self.assertEqual(S.words_value("two thousand three hundred"), 2300)
        self.assertEqual(S.words_value("twenty-seven"), 27)


class CountriesThatOnlySpeakAreNoMap(unittest.TestCase):
    def test_actor_country_is_not_a_map_place(self):
        sent = NS(text="Later, United States officials confirmed it was a Ukrainian missile strike.",
                  entities=[NS(kind="place", country=True, name="United States")])
        self.assertEqual(D._countries(sent, as_place=True), [])
        self.assertEqual(len(D._countries(sent)), 1)          # flags and stickers still see it

    def test_country_as_place_stays(self):
        sent = NS(text="Russian forces crossed into Ukraine.", entities=[NS(kind="place", country=True, name="Ukraine")])
        self.assertEqual(len(D._countries(sent, as_place=True)), 1)


class FootageRules(unittest.TestCase):
    def test_reference_place(self):
        self.assertTrue(N.reference_only("Two missiles struck the ship south of Odesa.", "Odesa"))
        self.assertTrue(N.reference_only("Russia pulled its ships back from the coast near Odesa.", "Odesa"))
        self.assertFalse(N.reference_only("Russian missiles hit Odesa overnight.", "Odesa"))

    def test_clip_naming_only_the_reference_place_is_rejected(self):
        r = N.read("Ukraine said two Neptune missiles struck the ship south of Odesa.")
        c = NS(video_id="x", title="Ukraine's Odesa hit by deadly Russian missile attack", channel="Reuters", duration=90.0, description="",
               details={}, upload_date="20240315", blocked=False, content_warning="")
        self.assertTrue(any("reference point" in w for w in R.reject(c, r)))

    def test_comparison_year_is_not_the_story_date(self):
        self.assertEqual(N.read("It was the largest warship lost in combat since 1982.").date, "")
        self.assertTrue(N.read("Fighting has gone on since 2014.").date)

    def test_csv_prompt_searched_first(self):
        r = N.read("On April 14, 2022, the flagship of Russia's Black Sea Fleet sank.")
        self.assertEqual(DS.build_queries(r, "Moskva cruiser sinking || Moskva burning")[0], "Moskva cruiser sinking")

    def test_csv_prompt_names_lead_the_key_terms(self):
        rd = {"1": N.read("On April 14, 2022, the flagship of Russia's Black Sea Fleet sank.")}
        FD._prompt_subjects(rd, [{"scene_no": "1"}], [NS(scene_number="1", prompt="Moskva cruiser sinking April 2022 || x")])
        self.assertEqual(rd["1"].key_terms[0], "Moskva")
        rd = {"1": N.read("Weeks earlier, she had demanded the surrender of Snake Island.")}
        FD._prompt_subjects(rd, [{"scene_no": "1"}], [NS(scene_number="1", prompt="Reuters Snake Island Moskva radio")])
        self.assertEqual(rd["1"].key_terms[:2], ["Snake Island", "Moskva"])


class RoundTwo(unittest.TestCase):
    """Found in render 044 (2026-11-10)."""

    def test_sea_name_in_prompt_is_not_a_subject(self):
        rd = {"9": N.read("After that, Russia pulled its ships back from the coast near Odesa.")}
        FD._prompt_subjects(rd, [{"scene_no": "9"}], [NS(scene_number="9", prompt="Black Sea Fleet Sevastopol ships || x")])
        self.assertNotIn("Black Sea", rd["9"].key_terms)
        self.assertEqual(rd["9"].key_terms[0], "Sevastopol")
        c = NS(video_id="x", title="Ukraine's Odesa hit by deadly Russian missile attack", channel="Reuters", duration=90.0,
               description="Black Sea port city", details={}, upload_date="20240315", blocked=False, content_warning="")
        self.assertTrue(R.reject(c, rd["9"]))

    def test_one_moment_per_video(self):
        u = R.Used()
        u.add("003", "vid", 47.0, 52.9)
        self.assertTrue(u.conflict("vid", 52.9, 58.8))

    def test_no_date_card_for_a_comparison_year(self):
        self.assertEqual(D._date_of("It was the largest warship lost in combat since 1982."), "")
        self.assertEqual(D._date_of("Ukraine has held since 2014."), "2014")

    def test_quote_never_cut_mid_phrase(self):
        from cinematic_explainer.war.graphics_lib import whole_quote

        self.assertEqual(whole_quote("a fire had set off ammunition, and that she sank in a storm while under tow"), "a fire had set off ammunition")
        q = whole_quote("the strike destroyed three launchers and killed at least twelve soldiers near the border crossing")
        self.assertTrue(q.endswith("…") and not q.lower().rstrip("…").endswith((" the", " near", " a")))

    def test_kicker_lives_only_with_its_card(self):
        plan = NS(layers=[Layer("lay_stat_split", 33.4, 36.4, {}), Layer("kicker", 33.76, 37.0, {"text": "Key figure"}),
                          Layer("kit_radar", 17.0, 20.0, {}), Layer("kicker", 17.5, 21.8, {"text": "Key figure"})], shots=[])
        D._fit_kickers(plan, {})
        kick = [(ly.start, ly.end) for ly in plan.layers if ly.kind == "kicker"]
        self.assertEqual(kick, [(33.76, 36.4)])


class AccurateFootageAndLivelierGraphics(unittest.TestCase):
    """2026-11-10 owner: footage accurate, graphics and maps more engaging, no major coding."""

    def clip(self, title, up="20220418"):
        return NS(video_id="x", title=title, channel="Reuters", duration=90.0, description="", details={}, upload_date=up,
                  blocked=False, content_warning="")

    def reading(self, text, prompt):
        rd = {"1": N.read(text)}
        FD._prompt_subjects(rd, [{"scene_no": "1"}], [NS(scene_number="1", prompt=prompt)])
        return rd["1"]

    def test_clip_must_show_what_the_prompt_asks(self):
        r = self.reading("Ukraine printed the Snake Island moment on a postage stamp, and people queued for hours to buy it.",
                         "Ukraine Snake Island postage stamp queue || Snake Island February 2022")
        self.assertTrue(R.reject(self.clip("Strikes on Odesa after Russia quits Snake Island"), r))
        self.assertFalse(R.reject(self.clip("Timelapse shows hundreds of Ukrainians queuing to buy stamp honouring Snake Island"), r))

    def test_word_forms_match(self):
        r = self.reading("Ukraine said two Neptune missiles struck the ship south of Odesa.", "Neptune missile launch Ukraine")
        self.assertFalse(R.reject(self.clip("Ukraine Launches Neptune Cruise Missiles At Russian Targets"), r))

    def test_generic_prompt_has_no_date_and_takes_illustrative_clips(self):
        from cinematic_explainer.war import director_authenticity as AU

        r = self.reading("Ukrainian soldiers held the trenches through the winter.", "Ukrainian soldiers trench winter")
        old = self.clip("Ukrainian soldiers in a winter trench near the front", up="20190101")
        self.assertFalse(R.reject(old, r, None, None))                      # no date rule for a generic picture
        self.assertTrue(AU.allowed("unverified", r, "atmospheric", reasons=[]))
        self.assertFalse(AU.allowed("unverified", r, "exact", reasons=["red flag: 'simulation'"]))

    def test_small_overlay_alone_gets_a_motion_card_not_a_bare_field(self):
        self.assertIn("kit_flyover", D.LIGHT_OVER)

    def test_no_dark_night_map_in_rotation(self):
        import inspect

        self.assertNotIn('"night"', inspect.getsource(D).split("looks = (", 1)[1].split(")", 1)[0])


class CaptureChecks(unittest.TestCase):
    """2026-11-10 capture investigation: the recorder landed on the right second; War's picture checks threw the clips away."""

    def test_warm_landscape_is_not_a_studio(self):
        import numpy as np
        from cinematic_explainer.war import director_frames as F

        rng = np.random.default_rng(1)
        rocks = np.clip(rng.normal([190, 120, 70], 25, (90, 160, 3)), 0, 255).astype(np.uint8)       # orange everywhere
        self.assertNotEqual(F.classify(rocks, rocks)[0], "studio")
        studio = np.clip(rng.normal([60, 70, 110], 40, (90, 160, 3)), 0, 255).astype(np.uint8)        # a busy blue studio set
        studio[20:75, 60:100] = (200, 140, 110)                                                       # a face in the middle
        self.assertEqual(F.classify(studio, studio)[0], "studio")

    def test_moving_camera_judged_by_colour(self):
        import numpy as np
        from cinematic_explainer.war import director_capture as C
        from cinematic_explainer.war import director_frames as F

        rng = np.random.default_rng(2)
        street = lambda: np.clip(rng.normal([110, 110, 120], 60, (90, 160, 3)), 0, 255).astype(np.uint8)  # noqa: E731 - every frame different
        tiles = ([F.Tile(t=float(t), img=street()) for t in range(40, 56)]
                 + [F.Tile(t=float(t), img=np.full((90, 160, 3), (20, 200, 40), np.uint8)) for t in range(100, 110)])
        v = C.verify([street() for _ in range(8)], tiles, 45.0, 4.0)
        self.assertTrue(v["ok"], v)
        ad = [np.clip(rng.normal([230, 30, 200], 60, (90, 160, 3)), 0, 255).astype(np.uint8) for _ in range(8)]
        self.assertFalse(C.verify(ad, tiles, 45.0, 4.0)["ok"])


if __name__ == "__main__":
    unittest.main()


class ReferenceFireballs(unittest.TestCase):
    """2026-11-10 reference 'GIANT FIREBALLS': missiles fly on the map; generic b-roll; earned clips stay visible."""

    def test_strike_with_only_the_target_named_flies_from_the_attacker(self):
        routes, extra = D._one_sided_strike("Ukraine said two Neptune missiles struck the ship south of Odesa.", [{"name": "Odesa"}])
        self.assertEqual(len(routes), 2)                                     # two missiles, one after another
        self.assertEqual(routes[0]["from"]["name"], "Odesa")
        self.assertLess(routes[0]["to"]["lat"], 46.4)                         # south of Odesa, at sea
        self.assertEqual(extra["label"], "SHIP")
        routes, _ = D._one_sided_strike("Drones struck the Ryazan refinery overnight.", [{"name": "Ryazan"}])
        self.assertEqual(len(routes), 1)                                     # the side opposite the target's country fires
        self.assertNotEqual(routes[0]["from"]["name"], "Ryazan")
        self.assertEqual(D._one_sided_strike("The strike hit something.", [{"name": "Nowhereville"}])[0], [])

    def test_dimming_layout_card_counts_as_cover(self):
        self.assertTrue(D._covers(Layer("lay_claim", 21.3, 30.3, {}, dim=True)))
        self.assertFalse(D._covers(Layer("lay_claim", 21.3, 30.3, {"over": True}, dim=True)))

    def test_generic_prompt_prefers_broll_over_talk(self):
        r = AccurateFootageAndLivelierGraphics.reading(None, "Russian tanks moved through the snow.", "Russian tanks snow")
        mk = lambda t: NS(video_id="x", title=t, channel="Some Channel", duration=60.0, description="", details={}, upload_date="20240101",  # noqa: E731
                          blocked=False, content_warning="", queries=[], rank=1)
        self.assertGreater(R.score(mk("Russian tanks in snow combat footage"), r), R.score(mk("Russian tanks in snow: news analysis live"), r))
