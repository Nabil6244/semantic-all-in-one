"""War render 048 (Novorossiysk, 2026-11-10) review fixes, as general rules with synthetic inputs (no render, no network):
fragment text cards, cut captions, rich panels first, corner CSV cards over maps, strike maps, maps that point at the story's place,
dossier typing, library real-before-AI + spare clips, interview clips."""
from __future__ import annotations

import unittest

from cinematic_explainer.war import direction as D
from cinematic_explainer.war import library as L
from cinematic_explainer.war import planner
from test_war_library import make_library, rows_for, scenes_for


def plan_rows(rows, step=6.0, footage=None):
    t, sc = 0.0, []
    for i, (g, txt) in enumerate(rows):
        sc.append({"text": txt, "start": t, "end": t + step, "scene_no": i + 1, "graphic": g, "footage": footage, "footage_meta": {}})
        t += step
    return planner.plan(sc, config={}), sc


class FragmentText(unittest.TestCase):
    def test_no_screen_shows_the_first_words_of_a_long_sentence(self):
        for s in ("This is what makes Ukraine's changing strategy so significant for the rest of the war.",
                  "And its access to the sea is now threatened by drones every day.",
                  "It is not simply trying to destroy random targets across Russia.",
                  "So here is the question.", "It is the connection between all of them."):
            self.assertEqual(D._phrase_or_lead(s), "", s)

    def test_a_fragment_never_stops_on_an_open_word(self):
        for s in ("The importance of NLMK extends beyond the steel industry for many years.",
                  "The supposed safe haven has become a place where ships are trapped by drones."):
            h = D._phrase_or_lead(s)
            self.assertNotIn(h.split()[-1].lower() if h else "", ("beyond", "become", "has", "extends"), s)

    def test_good_lines_are_kept(self):
        self.assertEqual(D._phrase_or_lead("The war is far from over."), "The war is far from over")
        self.assertEqual(D._phrase_or_lead("Losses rose from 2,000 in March to 46,000 by December."), "Losses rose from 2,000 in March")
        self.assertEqual(D._phrase_or_lead("Cheap drones are emptying the stocks of air defence missiles."), "Cheap drones are emptying the stocks")

    def test_big_word_and_caption_need_their_figure_or_reported_words(self):
        p, sc = plan_rows([("big word", "Every damaged industrial facility requires resources to repair."),
                           ("caption", "The importance of NLMK extends beyond the steel industry and into the wider economy.")])
        self.assertFalse([ly for ly in p.layers if ly.kind in ("bc_bigword", "bc_caption") and (ly.params or {}).get("csv_graphic")])


class RichFirst(unittest.TestCase):
    def test_a_light_ask_on_a_weapon_type_line_is_the_type_panel(self):
        p, _sc = plan_rows([("kinetic", "Russian warships were the backbone of the fleet for decades.")])
        kinds = [ly.kind for ly in p.layers if (ly.params or {}).get("csv_graphic")]
        self.assertIn("lay_equipment_hero", kinds)

    def test_an_attack_word_no_longer_hides_the_type_panel(self):
        p, _sc = plan_rows([("", "Ukrainian drones attacked again and again through the summer.")] * 1, step=8.0)
        self.assertTrue(any(ly.kind == "lay_equipment_hero" for ly in p.layers))


class StrikeMaps(unittest.TestCase):
    def test_a_stated_strike_on_a_named_place_flies_on_the_map(self):
        p, _sc = plan_rows([("", "Ukrainian sea drones struck Novorossiysk overnight.")], step=7.0)
        m = [ly for ly in p.layers if ly.kind == "tac_map" and (ly.params or {}).get("routes")]
        self.assertTrue(m)
        self.assertEqual(m[0].params["routes"][0]["to"]["name"] if isinstance(m[0].params["routes"][0]["to"], dict)
                         else m[0].params["routes"][0]["to"], "Novorossiysk")

    def test_the_port_further_on_means_the_place_just_named(self):
        p, _sc = plan_rows([("", "Russia moved its warships to Novorossiysk."),
                            ("", "Then Ukraine launched a major combined attack against the port.")], step=6.0)
        self.assertTrue(any(ly.kind == "tac_map" and (ly.params or {}).get("strike_map") for ly in p.layers))
        # 2026-11-12 owner (render 050 slice): only the line just before; two lines back is another subject (Kirishi pinned for Ust-Luga)
        p, _sc = plan_rows([("", "Russia moved its warships to Novorossiysk."), ("", "Calm returned for a while."),
                            ("", "Then Ukraine launched a major combined attack against the port.")], step=6.0)
        self.assertFalse(any(ly.kind == "tac_map" and (ly.params or {}).get("strike_map") and "Novorossiysk" in str(ly.params.get("places"))
                             for ly in p.layers))

    def test_no_strike_is_drawn_when_who_fires_is_not_stated(self):
        p, _sc = plan_rows([("", "For years Moscow believed attacks on its capital were impossible.")], step=7.0)
        self.assertFalse(any((ly.params or {}).get("strike_map") for ly in p.layers))

    def test_a_ukrainian_missile_never_leaves_a_town_russia_holds(self):
        names = {str(e.get("name", "")).lower() for e in D._side_cities("ua")}
        self.assertNotIn("berdiansk", names)
        self.assertNotIn("mariupol", names)

    def test_the_weapons_side_decides_the_attacker(self):
        self.assertEqual(D._attacker("While Russia's ships are trapped in Novorossiysk, Ukrainian missiles and drones are reaching deeper."), "ua")


class PointedMaps(unittest.TestCase):
    def test_a_bare_country_map_points_at_the_place_the_story_named(self):
        p, _sc = plan_rows([("", "The fleet moved to Novorossiysk."), ("map", "Russia and Ukraine both claimed success.")], step=6.0)
        bare = [ly for ly in p.layers if ly.kind == "tac_map" and not (ly.params or {}).get("places")]
        pointed = [ly for ly in p.layers if ly.kind == "tac_map" and any(str(x.get("name")) == "Novorossiysk" for x in (ly.params or {}).get("places") or [])]
        self.assertFalse(bare)
        self.assertTrue(pointed)


class CornerCardsOverMaps(unittest.TestCase):
    def test_a_corner_locator_does_not_wipe_the_map_under_it(self):
        p, sc = plan_rows([("", "Russian ships sailed from Sevastopol to Novorossiysk."), ("locator", "Novorossiysk lies on the Black Sea coast.")])
        s2 = sc[1]
        full = [ly for ly in p.layers if ly.kind in D.FULL_KINDS and ly.start < s2["end"] and ly.end > s2["start"]]
        self.assertTrue(full, "the second scene is not left as an empty backdrop with a corner map")


class Dossier(unittest.TestCase):
    def test_the_dossier_text_is_typed_out_well_before_it_fades(self):
        from cinematic_explainer.war import cards_motion as CM

        p = {"title": "Its stationary position", "body": "Its stationary position creates another opportunity for drones and missiles to strike.", "seed": 1}
        a = CM.kit_dossier(4.4 * 0.62, 4.4, p)
        b = CM.kit_dossier(4.4 * 0.8, 4.4, p)
        self.assertIsNotNone(a)
        self.assertEqual(list(a.getdata())[::997], list(b.getdata())[::997])     # nothing new is typed after 62 % of the card


class LibraryChoice(unittest.TestCase):
    def test_real_footage_before_an_ai_clip_of_the_same_fit(self):
        clips = L.load(make_library({"ai_fire/ai_fire_001.mp4": ("refinery_fire", "refinery fire black smoke"),
                                     "refinery_fire/refinery_fire_001.mp4": ("refinery_fire", "refinery fire black smoke")},
                                    ai=("ai_fire/ai_fire_001.mp4",)))
        sc = scenes_for(["refinery fire footage"])
        got = L.plan(sc, rows_for(sc), clips)
        self.assertEqual(got["1"]["clip"]["file"], "refinery_fire/refinery_fire_001.mp4")

    def test_a_used_up_clip_hands_over_to_another_that_fits_before_graphics(self):
        clips = L.load(make_library({"refinery_fire/refinery_fire_001.mp4": ("refinery_fire", "refinery fire black smoke oil"),
                                     "oil_fire/oil_fire_001.mp4": ("oil_fire", "oil refinery fire night")}))
        sc = scenes_for(["refinery fire black smoke oil footage"] * 3, step=10.0)
        got = L.plan(sc, rows_for(sc), clips)
        self.assertEqual([got[str(i)]["source"] for i in (1, 2, 3)], ["library", "library", "graphics"])


class InterviewClips(unittest.TestCase):
    def test_an_interview_is_not_footage_of_a_line_without_a_person(self):
        from cinematic_explainer.war import footage_match as FM

        narr = FM.narration_profile("The importance of NLMK extends beyond steel.")
        self.assertTrue(FM._talking_head({"title": "Interview with the chairman of Udokan Copper"}, narr))
        self.assertFalse(FM._talking_head({"title": "Steel plant furnace footage"}, narr))


if __name__ == "__main__":
    unittest.main()


class NoFlash(unittest.TestCase):
    """2026-11-10 owner: "some clips just came for a mini sec ... falling back or glitching": a frame of the source's next shot showed where
    a clip's played part began or ended next to a cut inside the source file."""

    def _plan(self, shots, layers=()):
        from types import SimpleNamespace
        from cinematic_explainer.render import Shot, Layer
        return SimpleNamespace(shots=[Shot(p, a, b, seek=s) for p, a, b, s in shots], layers=[Layer(*x) for x in layers])

    def pieces(self, plan, cuts):
        return [(round(a, 2), round(b, 2)) for a, b, _p in D.visible_footage_pieces(plan, 100.0, picture=lambda p: True, cuts=cuts)]

    def test_the_played_part_moves_off_a_cut_inside_the_clip(self):
        cuts = lambda p: [4.0]
        plan = self._plan([("a.mp4", 0.0, 3.9, 0.0)])
        D.no_flash(plan, {}, cuts=cuts, probe=lambda p: 12.0, picture=lambda p: True)
        self.assertTrue(all(b - a >= D.SLIVER_S for a, b in self.pieces(plan, cuts)))
        sh = plan.shots[0]
        self.assertFalse(any(sh.seek - D.CUT_MARGIN_S < c < sh.seek + 3.9 + D.CUT_MARGIN_S for c in cuts("a")))

    def test_a_clip_too_short_to_dodge_its_cut_hands_the_sliver_to_the_next_card(self):
        cuts = lambda p: [4.1]
        plan = self._plan([("a.mp4", 0.0, 4.04, 0.44)], [("tac_map", 4.04, 8.0, {})])
        D.no_flash(plan, {}, cuts=cuts, probe=lambda p: 4.5, picture=lambda p: True)
        self.assertTrue(all(b - a >= D.SLIVER_S for a, b in self.pieces(plan, cuts)))

    def test_a_flash_cut_opening_after_a_card_stays_under_the_card(self):
        cuts = lambda p: [0.2, 0.3, 0.4]
        plan = self._plan([("a.mp4", 0.0, 7.5, 0.0)], [("tac_map", 0.0, 0.12, {})])
        D.no_flash(plan, {}, cuts=cuts, probe=lambda p: 7.6, picture=lambda p: True)
        self.assertTrue(all(b - a >= D.SLIVER_S for a, b in self.pieces(plan, cuts)))
