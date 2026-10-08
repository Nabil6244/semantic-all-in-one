"""Recurring figures (style_engine/entities.py): the same figure gets the same canonical description in every AI prompt
of a CSV scene that names it; the CSV stays the production contract (no scene created, removed, reordered or retyped,
real-source searches untouched, unnamed scenes unchanged); only a style that defines entities (Book of Enoch) uses it."""

import copy
import csv
import tempfile
import unittest
from pathlib import Path

from style_engine.entities import MARK, enrich_plan, enrich_prompt, referenced
from style_engine.loader import list_builtin_styles, load_style
from visual_director.schema import parse_visual_plan

ENTITIES = load_style("book_of_enoch").entities

SCENES = [  # (narration, asset_type, prompt)
    ("Genesis says only that Enoch walked with God.", "image", "A Romantic oil painting of a lone patriarch in a misty valley"),
    ("Enoch was carried beyond the ends of the earth.", "video", "A small traveller at the edge of a cosmic abyss"),
    ("Two hundred angels called the Watchers descended on Mount Hermon.", "image", "Winged figures descending on a snowy summit"),
    ("Their leader, Semjaza, made them swear an oath together.", "image", "Shadowy figures on a mountain crag under lightning"),
    ("The Watcher Azazel taught men to forge swords and shields.", "video", "An ancient blacksmith beating glowing iron"),
    ("Their children were the Nephilim, giants who devoured the labour of mankind.", "video", "Giant shadows over ruins"),
    ("It is called the Book of Enoch.", "image", "Ethiopic Ge'ez script on darkened parchment"),
    ("The sea rose over the land.", "image", "A storm over a dark sea"),
    ("Semjaza stood on the summit of Hermon.", "stock_image", "mount hermon summit snow"),
]


def plan():
    return parse_visual_plan({"title": "t", "scenes": [
        {"scene_id": i + 1, "narration": n, "visual_goal": n, "visual_description": p, "asset_type": a,
         "provider_preference": {"image": "flow_image", "video": "flow_video"}.get(a, a),
         **({"search_queries": [p]} if a == "stock_image" else {})}
        for i, (n, a, p) in enumerate(SCENES)]})


def block_for(prompt, name):
    """The canonical text for one figure inside an enriched prompt."""
    tail = prompt.split(MARK, 1)[1]
    start = tail.index(f"{name}:")
    return tail[start:].split(").", 1)[0]


class RecurringFigures(unittest.TestCase):
    def setUp(self):
        self.before = plan()
        self.after = plan()
        self.n = enrich_plan(self.after, ENTITIES)
        self.by = {s.scene_id: s for s in self.after.scenes}

    def test_1_the_same_figure_reads_the_same_in_every_prompt(self):
        a = block_for(self.by[1].visual_description, "Enoch")
        b = block_for(self.by[2].visual_description, "Enoch")
        self.assertEqual(a, b)
        self.assertIn("long grey beard", a)
        self.assertEqual(block_for(self.by[3].visual_description, "The Watchers"), block_for(self.by[5].visual_description, "The Watchers"))

    def test_2_figures_are_found_from_the_csv_scene_itself(self):
        self.assertEqual([e["id"] for e in referenced(SCENES[3][0], ENTITIES)], ["semjaza"], "named in the narration")
        self.assertEqual([e["id"] for e in referenced("A painting of Azazel at the anvil", ENTITIES)], ["azazel"], "or in the prompt")

    def test_3_no_scene_is_created_removed_reordered_or_retyped(self):
        fields = lambda p: [(s.scene_id, s.narration, s.asset_type, s.provider_preference) for s in p.scenes]  # noqa: E731
        self.assertEqual(fields(self.after), fields(self.before))
        for b, a in zip(self.before.scenes, self.after.scenes):
            if a.visual_description != b.visual_description:
                self.assertTrue(a.visual_description.startswith(b.visual_description), "only appended to")

    def test_4_the_csv_is_still_the_contract_and_carries_the_final_prompt(self):
        out = Path(tempfile.mkdtemp()) / "p.csv"
        self.after.write_csv(out)
        rows = list(csv.DictReader(out.open()))
        self.assertEqual(list(rows[0]), ["scene_number", "script_segment", "asset_type", "prompt"])
        self.assertEqual(len(rows), len(SCENES))
        self.assertEqual(rows[3]["prompt"], self.by[4].visual_description, "what generation receives is what the CSV says")
        again = copy.deepcopy(self.after)
        self.assertEqual(enrich_plan(again, ENTITIES), 0, "running it twice changes nothing")

    def test_5_semjaza_is_distinct_from_the_watchers(self):
        s = block_for(self.by[4].visual_description, "Semjaza")
        w = next(e for e in ENTITIES if e["id"] == "watchers")["canonical_description"]
        self.assertIn("tallest", s)
        self.assertIn("circlet", s)
        self.assertNotIn("circlet", w)

    def test_6_azazel_keeps_his_forge(self):
        a = block_for(self.by[5].visual_description, "Azazel")
        self.assertIn("forge", a)
        self.assertIn("molten metal", a)

    def test_7_only_scenes_that_name_a_figure_are_enriched(self):
        self.assertNotIn(MARK, self.by[7].visual_description, "'the Book of Enoch' is the book, not the man")
        self.assertNotIn(MARK, self.by[8].visual_description, "names no figure")
        self.assertEqual(self.n, 6)

    def test_8_prompts_without_figures_are_unchanged(self):
        for i in (7, 8):
            self.assertEqual(self.by[i].visual_description, SCENES[i - 1][2])
        self.assertEqual(enrich_prompt("A storm over a dark sea", "The sea rose.", ENTITIES), "A storm over a dark sea")

    def test_9_other_styles_have_no_figures_and_change_nothing(self):
        for st in list_builtin_styles():
            if st.id == "book_of_enoch":
                continue
            self.assertEqual(st.entities, [], st.id)
            p = plan()
            self.assertEqual(enrich_plan(p, st.entities), 0)
            self.assertEqual([s.visual_description for s in p.scenes], [s.visual_description for s in self.before.scenes])

    def test_10_the_csv_of_a_plan_without_figures_is_byte_identical(self):
        d = Path(tempfile.mkdtemp())
        p = plan()
        p.write_csv(d / "a.csv")
        enrich_plan(p, [])
        p.write_csv(d / "b.csv")
        self.assertEqual((d / "a.csv").read_bytes(), (d / "b.csv").read_bytes())

    def test_11_real_sources_are_never_touched_and_flow_is_not_involved(self):
        self.assertEqual(self.by[9].visual_description, "mount hermon summit snow", "a stock search names Semjaza but is a real search")
        import style_engine.entities as E
        self.assertNotIn("providers", Path(E.__file__).read_text(), "the enrichment knows nothing about Flow or providers")


if __name__ == "__main__":
    unittest.main()
