"""The template inventory is computed from the registry, never from a remembered count. Run: python -m unittest test_gfx_inventory"""

from __future__ import annotations

import unittest

import gfx_inventory as I
import gfx_templates as G

RULE_KEYS = {"weight", "where", "requires", "eligible", "placement", "timing", "fallback"}


class TestInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = G.load_library()
        cls.rows = I.inventory(render_check=False)
        cls.by = {r["id"]: r for r in cls.rows}

    def test_one_row_per_template_in_the_registry(self):
        self.assertEqual(sorted(self.by), sorted(self.lib))
        self.assertEqual(I.summary(self.rows)["templates_in_library"], len(self.lib))

    def test_every_automatic_rule_is_defined_in_words_and_names_a_real_template(self):
        for tid, _pat, _fn in G.AUTO:
            self.assertIn(tid, self.lib)
            self.assertIn(tid, G.RULES, f"{tid} has an extractor but no definition of what it requires")
            self.assertTrue(RULE_KEYS <= set(G.RULES[tid]), tid)
            self.assertTrue(all(str(G.RULES[tid][k]).strip() for k in RULE_KEYS - {"weight", "where"}), tid)
        self.assertEqual(set(G.RULES), {tid for tid, _p, _f in G.AUTO})

    def test_a_template_without_a_rule_says_exactly_why(self):
        for r in self.rows:
            if r["auto_rule"]:
                self.assertEqual(r["why_not_auto"], "")
            else:
                self.assertGreater(len(r["why_not_auto"]), 20, r["id"])

    def test_map_only_graphics_are_kept_off_footage(self):
        for r in self.rows:
            t = self.lib[r["id"]]
            self.assertEqual(r["map_bound"], G.map_bound(t))
            if r["map_bound"]:
                self.assertFalse(r["context_over_footage"], r["id"])
                self.assertFalse(r["plan_layer_on_footage_beat"], r["id"])
        for tid in ("route_travel", "location_card", "region_spotlight", "distance_ruler", "flow_route", "place_pulse"):
            self.assertTrue(self.by[tid]["map_bound"], tid)
        for tid in ("big_number", "name_bar", "typed_caption", "ring_percent", "checklist_card"):
            self.assertFalse(self.by[tid]["map_bound"], tid)

    def test_the_doc_style_looks_are_placed_by_doc_style_not_by_narration_rules(self):
        for tid in G.DOC_STYLE_TWINS:
            if self.by[tid]["auto_rule"]:
                continue                       # (counter_corner is also a narration rule: a number in the corner)
            self.assertIn("Doc Style", self.by[tid]["why_not_auto"])
        self.assertFalse(self.by["yellow_tag"]["auto_rule"])
        self.assertFalse(self.by["typed_caption"]["auto_rule"])

    def test_the_counts_add_up(self):
        s = I.summary(self.rows)
        self.assertEqual(s["eligible_over_footage"] + s["map_only"] + sum(1 for r in self.rows if r["needs_picture"] and not r["map_bound"]), s["templates_in_library"])
        self.assertEqual(s["with_an_automatic_rule"], len(G.RULES))
        self.assertEqual(s["full_screen_plates"], sum(1 for t in self.lib.values() if t.get("plate")))

    def test_nothing_with_a_rule_needs_a_picture_or_the_map_unless_it_says_map_only(self):
        for tid, rule in G.RULES.items():
            t = self.lib[tid]
            self.assertFalse(G.needs_picture(t), tid)
            if G.map_bound(t):
                self.assertEqual(tuple(rule["where"]), ("map",), tid)
            else:
                self.assertEqual(tuple(rule["where"]), ("map", "footage"), tid)

    def test_every_template_draws_on_the_mock_canvas_where_node_is_available(self):
        rows = I.inventory(render_check=True)
        if rows[0]["renders_on_map"] is None:
            self.skipTest("node is not available")
        broken = [(r["id"], r["render_problem"]) for r in rows if r["renders_on_map"] is not True or r["renders_over_footage"] is False]
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
