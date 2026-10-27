"""The War Documentary direction pass (cinematic_explainer/war/direction.py): restrained, narration-driven additions on top of the planner."""
import unittest

from cinematic_explainer.war import backdrop, planner as P

KIT = {"kit_stamp", "kit_tag", "kit_chips", "kit_recap", "kit_sticker", "kit_scale", "kit_ribbon", "kit_bignum", "tac_map"}


def sc(no, text, start, end, footage=None, meta=None):
    d = {"scene_no": no, "text": text, "start": float(start), "end": float(end)}
    if footage:
        d["footage"] = footage
        d["footage_meta"] = meta or {"user_supplied": True}
    return d


def kinds(plan):
    return [ly.kind for ly in plan.layers]


class Treatment(unittest.TestCase):
    def test_off_reproduces_the_old_plan(self):
        scenes = [sc(1, "Some claims cannot be verified.", 0, 8, "a.mp4"), sc(2, "Drones struck Moscow and Ryazan.", 8, 16, "b.mp4")]
        old = P.plan(scenes, config={"direction": False})
        self.assertFalse(KIT & set(kinds(old)))
        self.assertTrue(all(s.treat is None and s.dissolve_in == 0 for s in old.shots))

    def test_motion_varies_and_dissolve_only_between_different_clips(self):
        scenes = [sc(i + 1, "Engineers rebuilt the bridge near the port.", i * 8, i * 8 + 8, f"{i}.mp4") for i in range(4)]
        p = P.plan(scenes)
        moves = [s.treat["motion"] for s in p.shots]
        self.assertTrue(all(a != b for a, b in zip(moves, moves[1:])))
        self.assertTrue(all(s.dissolve_in in (0.0, 0.4) for s in p.shots))
        same = P.plan([sc(1, "Engineers rebuilt the bridge.", 0, 8, "x.mp4"), sc(2, "Engineers rebuilt the road.", 8, 16, "x.mp4")])
        self.assertTrue(all(s.dissolve_in == 0 for s in same.shots))

    def test_cold_grade_for_generic_neutral_for_user(self):
        p = P.plan([sc(1, "Engineers rebuilt the bridge.", 0, 8, "g.mp4", {"generic": True, "mismatch": True}), sc(2, "Engineers rebuilt the road.", 8, 16, "u.mp4")])
        self.assertEqual([s.treat["grade"] for s in p.shots], ["cold", "neutral"])

    def test_no_footage_scene_gets_the_plate_not_the_previous_clip(self):
        p = P.plan([sc(1, "Engineers rebuilt the bridge.", 0, 8, "a.mp4"), sc(2, "Winter makes it harder because drones watch every road.", 8, 16)])
        self.assertEqual([s.path for s in p.shots], ["a.mp4"])
        self.assertIn("no_footage", p.log[1].flags)


class Rules(unittest.TestCase):
    def test_claim_gets_a_status_stamp(self):
        p = P.plan([sc(1, "Some of these claims cannot be verified independently.", 0, 9, "a.mp4")])
        st = [ly for ly in p.layers if ly.kind == "kit_stamp"]
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0].params["status"], "unverified")

    def test_sticker_only_over_missing_or_generic_footage(self):
        none = P.plan([sc(1, "Drones watch every road in winter.", 0, 9)])
        own = P.plan([sc(1, "Drones watch every road in winter.", 0, 9, "a.mp4")])
        self.assertIn("kit_sticker", kinds(none))
        self.assertNotIn("kit_sticker", kinds(own))

    def test_scale_needs_a_stated_number(self):
        p = P.plan([sc(1, "Reports describe ten soldiers moving in single file through a narrow pipe.", 0, 9)])
        self.assertEqual([ly.params["n"] for ly in p.layers if ly.kind == "kit_scale"], [10])
        self.assertNotIn("kit_scale", kinds(P.plan([sc(1, "Soldiers moved through a narrow pipe.", 0, 9)])))

    def test_big_number_swaps_only_without_a_claimant(self):
        p = P.plan([sc(1, "The front line runs for more than 1,000 kilometers.", 0, 9, "a.mp4")])
        self.assertIn("kit_bignum", kinds(p))
        self.assertNotIn("stat_number", kinds(p))
        c = P.plan([sc(1, "Russia's defense ministry said it shot down 1,398 drones in one day.", 0, 9, "a.mp4")])
        self.assertNotIn("kit_bignum", kinds(c))

    def test_ribbon_on_topic_change_once_per_minute(self):
        scenes = [sc(1, "Engineers rebuilt the bridge near the port.", 0, 10, "a.mp4"), sc(2, "Now the winter war on the ground begins.", 10, 20, "b.mp4"),
                  sc(3, "Now the story moves on again.", 20, 30, "c.mp4")]
        self.assertEqual(kinds(P.plan(scenes)).count("kit_ribbon"), 1)

    def test_tactical_map_names_only_resolvable_places(self):
        p = P.plan([sc(1, "Strikes have been reported near Moscow and in Ryazan.", 0, 10, "a.mp4")])
        m = [ly for ly in p.layers if ly.kind == "tac_map"]
        self.assertEqual(len(m), 1)
        self.assertEqual({x["name"].lower() for x in m[0].params["places"]}, {"moscow", "ryazan"})
        self.assertEqual(m[0].params["theme"], "tactical")

    def test_decorations_never_overlap_each_other(self):
        p = P.plan([sc(1, "Drones watch every road in winter.", 0, 9), sc(2, "Winter makes it harder because the cold slows drones.", 9, 18)])
        deco = [ly for ly in p.layers if ly.kind in KIT]
        for i, a in enumerate(deco):
            for b in deco[i + 1:]:
                self.assertFalse(a.start < b.end - 0.01 and b.start < a.end - 0.01, (a.kind, b.kind))
        self.assertLessEqual(kinds(p).count("kit_sticker"), 1)

    def test_empty_plate_stretch_gets_something_truthful(self):
        p = P.plan([sc(1, "Winter makes the roads harder, because the cold slows everything down.", 0, 14)])
        self.assertTrue({"kit_tag", "kit_sticker"} & set(kinds(p)))

    def test_illustrative_chip_is_replaced_by_the_badge(self):
        p = P.plan([sc(1, "Engineers rebuilt the bridge near the port.", 0, 9, "g.mp4", {"generic": True, "mismatch": True})])
        self.assertIn("kit_badge", kinds(p))
        self.assertFalse([ly for ly in p.layers if ly.kind == "status_chip" and "ILLUSTRATIVE" in str(ly.params.get("text", "")).upper()])


class Plate(unittest.TestCase):
    def test_long_gap_never_runs_past_the_loop(self):
        shots = backdrop.fill_gaps([], 40.0, "plate.mp4")
        self.assertAlmostEqual(sum(s.end - s.start for s in shots), 40.0, places=1)
        for s in shots:
            self.assertLessEqual(s.seek + (s.end - s.start), backdrop.LENGTH_S + 1e-6)


if __name__ == "__main__":
    unittest.main()
