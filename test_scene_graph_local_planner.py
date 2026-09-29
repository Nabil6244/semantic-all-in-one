"""Regression tests for scene_graph/generator.py's Local Visual Planner MVP
(generate_scene_graph_local_planner).

Pure data-transform logic — no network, no LLM, no CSV. Mirrors the style of
test_scene_graph_generator.py (which covers the existing heuristic/LLM paths,
both left untouched by this feature).
"""

from __future__ import annotations

import unittest
from collections import defaultdict

from providers.base import SceneRow

from scene_graph.generator import _planner_first_sentence, generate_scene_graph_local_planner


def _rows(*segments):
    """segments: plain narration strings, or (script_segment, prompt) tuples."""

    rows = []
    for i, seg in enumerate(segments, start=1):
        if isinstance(seg, tuple):
            script_segment, prompt = seg
        else:
            script_segment, prompt = seg, ""
        rows.append(
            SceneRow.from_csv_row(
                {"scene_number": str(i), "script_segment": script_segment, "prompt": prompt}
            )
        )
    return rows


class TestBasicHero(unittest.TestCase):
    def test_single_subject_produces_one_node_and_no_edges(self):
        rows = _rows("A quiet frozen world sits at the edge of the solar system.")
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.scene_graph.nodes), 1)
        self.assertEqual(result.scene_graph.edges, [])


class TestComparison(unittest.TestCase):
    def test_comparison_language_creates_a_relationship_edge(self):
        rows = _rows(
            "The Vasa was a massive Swedish warship.",
            "Unlike smaller ships, it carried two full gun decks.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        self.assertEqual(len(sg.edges), 1)
        self.assertEqual(sg.edges[0].from_node, sg.nodes[0].id)
        self.assertEqual(sg.edges[0].to_node, sg.nodes[1].id)
        self.assertEqual(sg.edges[0].metadata.get("relationship"), "comparison")


class TestCauseEffect(unittest.TestCase):
    def test_causal_language_creates_a_causal_relationship(self):
        rows = _rows(
            "The engine overheated during the test flight.",
            "This caused a fire in the cargo bay.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        self.assertEqual(len(sg.edges), 1)
        self.assertEqual(sg.edges[0].metadata.get("relationship"), "causal")
        self.assertEqual(sg.nodes[1].semantic_role, "consequence")


class TestMechanism(unittest.TestCase):
    def test_mechanism_language_is_tagged_as_mechanism(self):
        rows = _rows(
            "The engine converts fuel into thrust.",
            "Here's how it works: fuel ignites and expands rapidly.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        self.assertEqual(sg.nodes[1].semantic_role, "mechanism")
        self.assertEqual(len(sg.edges), 1)
        self.assertEqual(sg.edges[0].metadata.get("relationship"), "mechanism")


class TestConservativeFallback(unittest.TestCase):
    def test_ambiguous_narration_produces_simple_graph_with_no_hallucinated_edges(self):
        rows = _rows(
            "The town square was quiet that morning.",
            "A few people walked past the old fountain.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.scene_graph.nodes), 2)
        self.assertEqual(result.scene_graph.edges, [])

    def test_weak_sequential_cue_alone_does_not_create_an_edge(self):
        # "another" is a sequential-list cue, but with no independent
        # opportunity signal it must NOT be enough on its own.
        rows = _rows(
            "The house had a small garden.",
            "Another room was down the hall.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.edges, [])


class TestMissingPrompt(unittest.TestCase):
    def test_missing_prompt_is_derived_from_script_segment(self):
        rows = _rows("A tall glass skyscraper reflects the sunset.")
        result = generate_scene_graph_local_planner("seg", rows)
        node = result.scene_graph.nodes[0]
        self.assertTrue(node.asset_reference)
        self.assertIn("skyscraper", node.asset_reference.lower())


class TestExistingPromptPreserved(unittest.TestCase):
    def test_supplied_prompt_is_used_verbatim(self):
        rows = _rows(("Some narration text.", "a golden retriever puppy"))
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_reference, "a golden retriever puppy")


class TestDeterminism(unittest.TestCase):
    def test_same_input_produces_identical_output(self):
        rows = _rows(
            "A test sentence about a bridge.",
            "Because of the flood, the bridge collapsed.",
        )
        r1 = generate_scene_graph_local_planner("seg", rows)
        r2 = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(r1.scene_graph.to_dict(), r2.scene_graph.to_dict())


class TestValidation(unittest.TestCase):
    def test_result_always_passes_scene_graph_validate(self):
        rows = _rows(
            "A quiet town.",
            "Unlike the city, it never sleeps... wait, it does.",
            "Because the factory closed, everyone left.",
            "Here's how the new plant works.",
            "Finally, subscribe for more stories like this.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.validate(), [])

    def test_last_row_with_cta_language_gets_cta_role(self):
        rows = _rows(
            "This is the story of the bridge.",
            "If you enjoyed this, please subscribe for more.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[-1].semantic_role, "cta")


class TestEmptyInput(unittest.TestCase):
    def test_empty_rows_produce_a_safe_valid_empty_graph(self):
        result = generate_scene_graph_local_planner("seg", [])
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.nodes, [])
        self.assertEqual(result.scene_graph.edges, [])

    def test_row_with_no_segment_and_no_prompt_yields_no_node(self):
        rows = [SceneRow.from_csv_row({"scene_number": "1", "script_segment": "", "prompt": ""})]
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.nodes, [])


class TestPositionalNodeIds(unittest.TestCase):
    def test_node_ids_come_from_row_position_not_csv_scene_number(self):
        rows = [
            SceneRow.from_csv_row({"scene_number": "47", "script_segment": "First thing."}),
            SceneRow.from_csv_row({"scene_number": "12", "script_segment": "Second thing."}),
        ]
        result = generate_scene_graph_local_planner("seg", rows)
        ids = [n.id for n in result.scene_graph.nodes]
        self.assertEqual(ids, ["n1", "n2"])


# --- PART 6: hardening-pass tests --------------------------------------------


class TestAbbreviationSafeFallbackPrompt(unittest.TestCase):
    def test_us_abbreviation_does_not_truncate_the_sentence(self):
        text = "In 1959, the U.S. Army began building Camp Century in Greenland."
        self.assertEqual(
            _planner_first_sentence(text),
            "In 1959, the U.S. Army began building Camp Century in Greenland.",
        )

    def test_multiple_abbreviations_in_one_sentence(self):
        text = "Dr. Smith and Prof. Lee, e.g. two scientists, led the project. It failed later."
        result = _planner_first_sentence(text)
        self.assertTrue(result.startswith("Dr. Smith and Prof. Lee, e.g. two scientists, led the project."))
        self.assertNotIn("It failed later", result)

    def test_uk_and_un_abbreviations(self):
        text = "The U.N. and U.K. issued a joint statement. They condemned it."
        result = _planner_first_sentence(text)
        self.assertEqual(result, "The U.N. and U.K. issued a joint statement.")

    def test_planner_uses_the_abbreviation_safe_prompt(self):
        # (No place named "in X" here: a line that places the story somewhere
        # real becomes a map scene instead — see the Greenland check below.)
        rows = _rows("In 1959, the U.S. Army began building Camp Century under the ice.")
        result = generate_scene_graph_local_planner("seg", rows)
        prompt = result.scene_graph.nodes[0].asset_reference
        self.assertIn("U.S. Army began building Camp Century", prompt)
        located = generate_scene_graph_local_planner(
            "seg", _rows("In 1959, the U.S. Army began building Camp Century in Greenland.")
        ).scene_graph.nodes[0]
        self.assertEqual((located.asset_source, located.asset_reference), ("map", "Greenland"))


class TestSmallCollection(unittest.TestCase):
    def test_three_to_four_item_collection_forms_one_group(self):
        rows = _rows(
            "The system has three main components: power, control, and sensing.",
            "The power component supplies energy to the whole system.",
            "The control component makes real-time decisions.",
            "The sensing component gathers data from the environment.",
            "The weather that day was calm and clear.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        group_edges = [e for e in sg.edges if e.metadata.get("relationship") == "collection_small"]
        # 3 members chained m1->m2->m3. The intro is the chapter's titled
        # card, not a group member (chaining it in made announced four-item
        # groups five cards and overflowed Exp Solar's layout).
        self.assertEqual(len(group_edges), 2)
        self.assertNotIn(sg.nodes[0].id, {e.from_node for e in group_edges} | {e.to_node for e in group_edges})
        for e in group_edges:
            self.assertEqual(e.kind, "group")
        # The unrelated trailing sentence must never be pulled into the group.
        involved = {e.from_node for e in group_edges} | {e.to_node for e in group_edges}
        self.assertNotIn(sg.nodes[-1].id, involved)

    def test_wrapup_sentence_referring_back_does_not_start_a_second_group(self):
        # Regression: "Together these four components..." matched the same
        # number+noun pattern as a genuine intro and, before this fix,
        # falsely re-triggered a second group that swallowed unrelated
        # trailing narration.
        rows = _rows(
            "The dam has four main structural components that visitors can see.",
            "The dam wall holds back the reservoir.",
            "The power plant houses the generators.",
            "The spillways route floodwater around the dam.",
            "The intake towers control water flow to the turbines.",
            "Together these four components allow the dam to work as one system.",
            "It also created thousands of jobs during the Great Depression.",
            "That employment boost helped stabilize the region.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        collection_edges = [e for e in sg.edges if e.metadata.get("relationship") == "collection_small"]
        # Exactly one group (4 members -> 3 edges: m1->m2->m3->m4; the
        # intro is the chapter's titled card, not a member).
        self.assertEqual(len(collection_edges), 3)
        self.assertNotIn(sg.nodes[0].id, {e.from_node for e in collection_edges} | {e.to_node for e in collection_edges})
        group_ids = {e.metadata.get("relationship") for e in sg.edges}
        # The trailing jobs/economy sentences must not have been swept into
        # any group at all.
        jobs_node = sg.nodes[6]
        self.assertNotIn(jobs_node.id, {e.from_node for e in collection_edges} | {e.to_node for e in collection_edges})


class TestLargeCollection(unittest.TestCase):
    def test_five_to_fifteen_item_collection_uses_group_grid(self):
        segments = ["Here are the seven wonders of the ancient world."]
        segments += [f"Wonder number {i} is a famous ancient structure." for i in range(1, 8)]
        segments.append("That concludes the list of wonders.")
        rows = _rows(*segments)
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        grid_edges = [e for e in sg.edges if e.metadata.get("relationship") == "collection_large"]
        self.assertEqual(len(grid_edges), 6)  # 7 members chained; the intro is its own titled card
        self.assertNotIn(sg.nodes[0].id, {e.from_node for e in grid_edges} | {e.to_node for e in grid_edges})
        for e in grid_edges:
            self.assertEqual(e.kind, "group_grid")


class TestGenuineOrderedSequence(unittest.TestCase):
    def test_contiguous_ordinal_markers_form_a_sequence_group(self):
        rows = _rows(
            "Building a rocket engine requires careful engineering.",
            "First, engineers design the combustion chamber.",
            "Next, they select propellant materials.",
            "Then, they run static fire tests.",
            "Finally, the engine is cleared for flight.",
            "The rocket later launched successfully.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        seq_edges = [e for e in sg.edges if e.metadata.get("relationship") == "sequential_list"]
        self.assertEqual(len(seq_edges), 3)
        for e in seq_edges:
            self.assertEqual(e.kind, "group")


class TestWeakSequentialCueNoGrouping(unittest.TestCase):
    def test_isolated_transition_words_never_group_on_their_own(self):
        rows = _rows(
            "The house had a small garden.",
            "Another room was down the hall.",
            "Next to it was a kitchen.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.edges, [])

    def test_a_single_first_with_no_follow_through_creates_no_group(self):
        rows = _rows(
            "First, let's look at the overall design.",
            "The design itself was fairly conventional.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.edges, [])


class TestVisualPersistenceContinuation(unittest.TestCase):
    def test_short_pronoun_led_low_opportunity_row_gets_no_new_node(self):
        rows = _rows(
            "A massive dam holds back the river.",
            "It was built in 1936.",
            "The turbines generate electricity for the region.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        sg = result.scene_graph
        self.assertEqual(len(sg.nodes), 2)
        self.assertEqual(len(sg.beats), 3)  # timing/narration preserved for all 3 rows
        self.assertEqual(sg.validate(), [])

    def test_long_pronoun_led_row_still_gets_its_own_node(self):
        rows = _rows(
            "A massive dam holds back the river.",
            "It was one of the largest engineering projects of its era and took years to finish.",
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(len(result.scene_graph.nodes), 2)


class TestContinuationAdversarialFalsePositives(unittest.TestCase):
    """A pronoun/connector opening + short length is NOT enough on its own —
    each of these SHOULD get its own new visual because it introduces a new
    subject/event/entity, even though it looks like a continuation on the
    surface (all realistic documentary-narration phrasing)."""

    def _new_node_count(self, second_sentence: str) -> int:
        rows = _rows(
            "Deep beneath the site, engineers built the original station in secrecy.",
            second_sentence,
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        return len(result.scene_graph.nodes)

    def test_it_introduces_a_new_discovery_event(self):
        self.assertEqual(self._new_node_count("It was discovered decades later."), 2)

    def test_this_introduces_a_new_discovery_fact(self):
        self.assertEqual(self._new_node_count("This discovery changed the project."), 2)

    def test_they_introduces_a_new_entity(self):
        self.assertEqual(self._new_node_count("They built a second tunnel nearby."), 2)

    def test_also_introduces_a_new_structure_with_different_design(self):
        self.assertEqual(
            self._new_node_count("Also, the eastern structure used a different design."), 2
        )

    def test_meanwhile_introduces_a_new_site(self):
        self.assertEqual(self._new_node_count("Meanwhile, engineers moved to a new site."), 2)

    def test_then_introduces_a_new_abandonment_event(self):
        self.assertEqual(self._new_node_count("Then the military abandoned the station."), 2)


class TestContinuationAdversarialTruePositives(unittest.TestCase):
    """Genuine continuations — a short, low-opportunity, pronoun-led
    supporting detail about the SAME subject already on screen — must still
    fold into the previous visual after the false-positive fix above."""

    def _new_node_count(self, second_sentence: str) -> int:
        rows = _rows(
            "Deep beneath the site, engineers built the original station in secrecy.",
            second_sentence,
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        return len(result.scene_graph.nodes)

    def test_it_remained_is_a_continuation(self):
        self.assertEqual(self._new_node_count("It remained there for decades."), 1)

    def test_this_made_is_a_continuation(self):
        self.assertEqual(self._new_node_count("This made the system unstable."), 1)

    def test_they_later_returned_is_a_continuation(self):
        self.assertEqual(self._new_node_count("They later returned to the site."), 1)

    def test_meanwhile_it_continued_is_a_continuation(self):
        self.assertEqual(self._new_node_count("Meanwhile, it continued operating."), 1)

    def test_also_it_became_expensive_is_a_continuation(self):
        self.assertEqual(self._new_node_count("Also, it became increasingly expensive."), 1)


class TestDeterminismOnComplexStructures(unittest.TestCase):
    def test_same_input_with_groups_and_continuations_is_byte_identical(self):
        rows = _rows(
            "There are three stages to this process.",
            "First, raw material is collected.",
            "Second, it is refined into usable form.",
            "Third, it is shipped to market.",
            "It happened quickly.",
            "Unlike older methods, this one is fully automated.",
        )
        r1 = generate_scene_graph_local_planner("seg", rows)
        r2 = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(r1.scene_graph.to_dict(), r2.scene_graph.to_dict())


class TestRealisticLongFormScript(unittest.TestCase):
    """~15 minutes of realistic documentary-style narration (see the final
    report for full statistics). Bounds only — no invented target numbers,
    just a check that the planner avoids "one complex visual per sentence"
    and "hundreds of unnecessary edges" on long-form input."""

    SCRIPT = (
        "Deep in the Black Canyon of the Colorado River sits one of the greatest "
        "engineering achievements of the twentieth century. "
        "In the early 1900s, the Colorado River flooded farmland every spring. "
        "Unlike earlier dams built from simple gravity masonry, Hoover Dam used a "
        "curved arch-gravity design. "
        "Because the heat was so extreme, several workers died from heat exhaustion. "
        "It offered little relief from the heat. "
        "The construction process had five major stages. "
        "First, engineers diverted the Colorado River through four tunnels. "
        "Second, crews cleared the canyon floor down to bedrock. "
        "Third, workers built the dam in a honeycomb of concrete columns. "
        "Fourth, cooling pipes carried refrigerated water through the concrete. "
        "Finally, engineers filled the remaining gaps with grout. "
        "The dam has four main structural components that visitors can see today. "
        "The dam wall holds back the reservoir known as Lake Mead. "
        "The power plant houses the electrical generators. "
        "The spillways route floodwater around the dam. "
        "The intake towers control water flow to the turbines. "
        "Here are the ten technologies that made a project like this possible. "
        "Large-scale electric power tools allowed crews to work faster. "
        "High-strength structural steel supported the massive penstock pipes. "
        "Industrial-scale concrete mixing plants produced material continuously. "
        "Aerial cableways carried workers across the canyon. "
        "Diesel-powered trucks moved excavated rock out of the canyon. "
        "Refrigeration technology enabled the cooling-pipe system. "
        "Pneumatic drills bored the diversion tunnels through solid rock. "
        "Electric arc welding sealed the massive steel penstocks. "
        "Hydraulic-powered cranes lifted concrete buckets into place. "
        "Precision surveying instruments kept the structure aligned. "
        "Because the dam blocks the natural flow of sediment, the delta has eroded. "
        "This surprised even the dam's own planners. "
        "Compared with earlier flood-control projects, it set a new standard. "
        "If you found this story interesting, subscribe for more deep dives."
    )

    def test_long_form_script_does_not_explode_into_one_node_per_sentence_or_hundreds_of_edges(self):
        segments = [s.strip() for s in self.SCRIPT.strip().split(". ") if s.strip()]
        rows = _rows(*segments)
        result = generate_scene_graph_local_planner("hoover_dam", rows, title="Hoover Dam")
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        self.assertEqual(sg.validate(), [])

        total_rows = len(rows)
        total_nodes = len(sg.nodes)
        total_edges = len(sg.edges)

        # The planner must not create a node for every single row (some
        # continuation rows should be folded into the previous visual)...
        self.assertLess(total_nodes, total_rows)
        # ...and must not create anywhere close to a fully-connected or even
        # densely-connected graph — most rows should remain isolated heroes,
        # with only strong-evidence relationships/groups creating edges.
        self.assertLess(total_edges, total_rows)

        relationships = {e.metadata.get("relationship") for e in sg.edges}
        self.assertIn("comparison", relationships)
        self.assertIn("causal", relationships)
        self.assertIn("collection_small", relationships)
        self.assertIn("collection_large", relationships)
        self.assertIn("sequential_list", relationships)

        self.assertEqual(sg.nodes[-1].semantic_role, "cta")

    def test_long_form_script_is_deterministic(self):
        segments = [s.strip() for s in self.SCRIPT.strip().split(". ") if s.strip()]
        rows = _rows(*segments)
        r1 = generate_scene_graph_local_planner("hoover_dam", rows, title="Hoover Dam")
        r2 = generate_scene_graph_local_planner("hoover_dam", rows, title="Hoover Dam")
        self.assertEqual(r1.scene_graph.to_dict(), r2.scene_graph.to_dict())


# --- Visual Intelligence pass: visual_hint, prompt intelligence, diversity ---


def _csv_rows(*dicts):
    return [SceneRow.from_csv_row({"scene_number": str(i), **d}) for i, d in enumerate(dicts, start=1)]


class TestVisualHintColumn(unittest.TestCase):
    def test_visual_hint_is_used_verbatim_as_the_prompt(self):
        rows = _csv_rows({
            "script_segment": "A quiet dam sits in the canyon.",
            "visual_hint": "aerial drone shot of a massive concrete dam at golden hour",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(
            result.scene_graph.nodes[0].asset_reference,
            "aerial drone shot of a massive concrete dam at golden hour",
        )

    def test_visual_hint_absent_falls_back_to_derived_prompt(self):
        rows = _csv_rows({"script_segment": "A quiet dam sits in the canyon."})
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertIn("dam", result.scene_graph.nodes[0].asset_reference.lower())

    def test_visual_hint_with_motion_verb_prefers_video(self):
        rows = _csv_rows({
            "script_segment": "The dam sits quietly in the canyon.",
            "visual_hint": "water spinning through the turbine housing",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        # "video" is now further refined by source intelligence into the
        # specific stock_video/flow_video choice (see TestSourceIntelligence)
        # — a plain hint with no other stock-suitable keyword defaults to
        # flow_video, the same safe default the old generic "video" implied.
        self.assertIn(result.scene_graph.nodes[0].asset_source, ("stock_video", "video"))

    def test_visual_hint_disables_compound_split_for_that_row(self):
        # Long, comma-and-"and" narration that WOULD split without a hint —
        # a visual_hint expresses one specific intended shot, so it must not.
        rows = _csv_rows({
            "script_segment": (
                "Engineers had to divert the Colorado River, excavate the "
                "foundation, and manage enormous amounts of concrete."
            ),
            "visual_hint": "wide shot of the entire Hoover Dam construction site",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(len(result.scene_graph.nodes), 1)
        self.assertEqual(
            result.scene_graph.nodes[0].asset_reference,
            "wide shot of the entire Hoover Dam construction site",
        )


class TestExplicitCsvOverridesStillRespected(unittest.TestCase):
    def test_explicit_asset_type_and_prompt_are_never_overridden(self):
        rows = _csv_rows({
            "script_segment": "Explicit override here.",
            "asset_type": "stock_video",
            "prompt": "explicit user prompt",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        node = result.scene_graph.nodes[0]
        self.assertEqual(node.asset_source, "stock_video")
        self.assertEqual(node.asset_reference, "explicit user prompt")

    def test_blank_asset_type_and_prompt_are_intelligently_inferred(self):
        rows = _csv_rows({"script_segment": "The turbine spins rapidly to generate power."})
        result = generate_scene_graph_local_planner("seg", rows)
        node = result.scene_graph.nodes[0]
        # "video" is now further refined into a specific stock_video/
        # flow_video choice by source intelligence (see TestSourceIntelligence).
        self.assertIn(node.asset_source, ("stock_video", "video"))
        self.assertTrue(node.asset_reference)


class TestPromptIntelligenceEraGrounding(unittest.TestCase):
    def test_era_token_present_in_narration_is_never_fabricated_beyond_the_text(self):
        # No motion/stock-suitable keyword here on purpose — isolates the
        # flow-style era-grounding behavior from source selection (see
        # TestSourceIntelligence for that).
        rows = _csv_rows({"script_segment": "The observatory was completed in 1931."})
        result = generate_scene_graph_local_planner("seg", rows)
        node = result.scene_graph.nodes[0]
        self.assertEqual(node.asset_source, "image")
        prompt = node.asset_reference
        self.assertIn("1931", prompt)
        # Nothing invented beyond what the narration itself stated.
        self.assertNotIn("historical engineering documentary photography", prompt)


class TestVisualDiversityMemory(unittest.TestCase):
    def test_repeated_subject_gets_a_rotating_shot_qualifier(self):
        rows = _csv_rows(
            {"script_segment": "The canyon walls rise steeply on either side."},
            {"script_segment": "The dam again dominates the canyon view."},
            {"script_segment": "The dam towers over the canyon once more."},
            {"script_segment": "The dam remains the canyon's defining structure."},
        )
        result = generate_scene_graph_local_planner("seg", rows)
        prompts = [n.asset_reference for n in result.scene_graph.nodes]
        # First "dam" mention: no qualifier yet. Later repeats: differentiated.
        self.assertNotIn("aerial view", prompts[1])
        self.assertTrue(any(q in prompts[2] for q in ("aerial view", "ground-level view", "close-up detail")))
        self.assertNotEqual(prompts[2], prompts[3])

    def test_diversity_never_touches_an_explicit_prompt(self):
        rows = _csv_rows(
            {"script_segment": "The dam again dominates the canyon view."},
            {"script_segment": "The dam towers over the canyon.", "prompt": "exact user prompt"},
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[1].asset_reference, "exact user prompt")


class TestNoGeminiDependency(unittest.TestCase):
    def test_planner_module_never_imports_visual_director_llm(self):
        import scene_graph.generator as gen_module
        # The module-level namespace must not include the Gemini client —
        # generate_scene_graph_with_llm takes an injected LLMProvider, but
        # the Local Visual Planner path never touches it, imports it, or
        # calls it.
        self.assertFalse(hasattr(gen_module, "GeminiLLM"))
        self.assertFalse(hasattr(gen_module, "gemini_configured"))

    def test_planner_produces_a_valid_plan_with_no_llm_argument_at_all(self):
        rows = _rows("A calm narration line with no AI involved at all.")
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.source, "local_planner")


class TestExpSolarAndOverscaledSharedOutput(unittest.TestCase):
    def test_same_planner_output_feeds_both_style_presets(self):
        rows = _rows(
            "Unlike older telescopes, this one uses adaptive optics.",
            "The system has four main components: power, control, sensing, and cooling.",
        )
        overscaled = generate_scene_graph_local_planner("seg", rows, style_preset="overscaled")
        exp_solar = generate_scene_graph_local_planner("seg", rows, style_preset="exp_solar")
        self.assertTrue(overscaled.ok and exp_solar.ok)
        # Identical structure — style is a presentation label only.
        self.assertEqual(len(overscaled.scene_graph.nodes), len(exp_solar.scene_graph.nodes))
        self.assertEqual(len(overscaled.scene_graph.edges), len(exp_solar.scene_graph.edges))


# --- Source intelligence: stock vs Flow, source-aware prompts, diversity ---


class TestSourceIntelligenceSelection(unittest.TestCase):
    def test_stock_video_preferred_for_suitable_real_world_motion(self):
        rows = _csv_rows({
            "script_segment": "Workers drove heavy machinery through the muddy construction site.",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_source, "stock_video")

    def test_flow_image_preferred_for_specific_conceptual_visuals(self):
        rows = _csv_rows({
            "script_segment": "An engineer explains the internal mechanism of the turbine in cross section.",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_source, "image")

    def test_stock_image_preferred_over_flow_video_when_a_still_suffices(self):
        rows = _csv_rows({
            "script_segment": (
                "An archival photograph shows the observatory shortly after "
                "it was built in 1931."
            ),
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_source, "stock_image")

    def test_flow_video_selected_for_highly_specific_motion_stock_cannot_represent(self):
        rows = _csv_rows({
            "script_segment": (
                "The reactor core explodes in a conceptual visualization of "
                "a scenario that never actually happened."
            ),
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_source, "video")

    def test_explicit_fully_specific_csv_asset_type_is_never_overridden(self):
        # "stock_image" is fully explicit — must survive even when the text
        # strongly suggests stock_video (a real-world action scene).
        rows = _csv_rows({
            "script_segment": "Workers drove heavy machinery through the muddy construction site.",
            "asset_type": "stock_image",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_source, "stock_image")

    def test_generic_video_hint_is_refined_into_a_specific_source(self):
        # "video" only states the VISUAL TYPE — the intelligence layer may
        # still pick stock_video vs flow_video, refining an underspecified
        # hint rather than overriding an explicit one.
        rows = _csv_rows({
            "script_segment": "Workers drove heavy machinery through the muddy construction site.",
            "asset_type": "video",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_source, "stock_video")

    def test_generic_image_hint_is_refined_into_flow_image_for_a_technical_visual(self):
        rows = _csv_rows({
            "script_segment": "An engineer explains the internal mechanism of the turbine in cross section.",
            "asset_type": "image",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_source, "image")


class TestSourceAwarePrompts(unittest.TestCase):
    def test_stock_prompts_are_search_oriented_not_cinematic(self):
        rows = _csv_rows({
            "script_segment": "Workers drove heavy machinery through the muddy construction site.",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        node = result.scene_graph.nodes[0]
        self.assertEqual(node.asset_source, "stock_video")
        prompt = node.asset_reference
        self.assertNotIn("cinematic", prompt.lower())
        self.assertLessEqual(len(prompt.split()), 8)

    def test_flow_prompts_remain_generation_oriented(self):
        rows = _csv_rows({
            "script_segment": "An engineer explains the internal mechanism of the turbine in cross section.",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        node = result.scene_graph.nodes[0]
        self.assertEqual(node.asset_source, "image")
        # The full-sentence, era-aware derivation — not a keyword search query.
        self.assertIn("cross section", node.asset_reference.lower())

    def test_visual_hint_used_verbatim_regardless_of_source(self):
        rows = _csv_rows({
            "script_segment": "Workers drove heavy machinery through the muddy construction site.",
            "visual_hint": "muddy construction site excavator",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(result.scene_graph.nodes[0].asset_reference, "muddy construction site excavator")


class TestSourceDiversityMemory(unittest.TestCase):
    def test_repeated_weak_default_source_rotates_after_three_in_a_row(self):
        # Four plain, signal-free sentences in a row all fall to the same
        # weak/default flow_image — the 4th must rotate to the alternate.
        rows = _csv_rows(
            {"script_segment": "A quiet valley stretches into the distance."},
            {"script_segment": "The old house stood near the river bend."},
            {"script_segment": "A narrow path wound through the tall grass."},
            {"script_segment": "Somewhere beyond the hill a bell rang softly."},
        )
        result = generate_scene_graph_local_planner("seg", rows)
        sources = [n.asset_source for n in result.scene_graph.nodes]
        self.assertEqual(sources[:3], ["image", "image", "image"])
        self.assertEqual(sources[3], "stock_image")

    def test_strong_signal_is_never_overridden_for_diversity(self):
        # Four genuinely stock-video-suitable sentences in a row must ALL
        # stay stock_video — diversity never overrides a real signal.
        rows = _csv_rows(
            {"script_segment": "Workers drove heavy machinery across the construction site."},
            {"script_segment": "More workers operated machinery near the factory gate."},
            {"script_segment": "Crowds walked past the construction machinery every morning."},
            {"script_segment": "Trucks and machinery operated across the busy factory yard."},
        )
        result = generate_scene_graph_local_planner("seg", rows)
        sources = [n.asset_source for n in result.scene_graph.nodes]
        self.assertEqual(sources, ["stock_video"] * 4)

    def test_shot_framing_diversity_still_works_alongside_source_diversity(self):
        rows = _csv_rows(
            {"script_segment": "The dam again dominates the canyon view."},
            {"script_segment": "The dam towers over the canyon once more."},
            {"script_segment": "The dam remains the canyon's defining structure."},
        )
        result = generate_scene_graph_local_planner("seg", rows)
        prompts = [n.asset_reference for n in result.scene_graph.nodes]
        self.assertTrue(any(q in prompts[1] for q in ("aerial view", "ground-level view", "close-up detail")))


class TestSourceIntelligenceDeterminismAndSafety(unittest.TestCase):
    def test_source_selection_is_fully_deterministic(self):
        rows = _rows(
            "Workers drove heavy machinery through the muddy construction site.",
            "An engineer explains the internal mechanism of the turbine in cross section.",
            "An archival photograph shows the observatory built in 1931.",
        )
        r1 = generate_scene_graph_local_planner("seg", rows)
        r2 = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(r1.scene_graph.to_dict(), r2.scene_graph.to_dict())

    def test_planner_module_performs_no_network_or_provider_calls(self):
        import scene_graph.generator as gen_module
        for name in ("resolve_scene_assets", "resolve_scene_graph_media", "requests", "urllib"):
            self.assertFalse(hasattr(gen_module, name))

    def test_overscaled_and_exp_solar_share_identical_source_decisions(self):
        rows = _rows(
            "Workers drove heavy machinery through the muddy construction site.",
            "An engineer explains the internal mechanism of the turbine in cross section.",
        )
        overscaled = generate_scene_graph_local_planner("seg", rows, style_preset="overscaled")
        exp_solar = generate_scene_graph_local_planner("seg", rows, style_preset="exp_solar")
        self.assertEqual(
            [n.asset_source for n in overscaled.scene_graph.nodes],
            [n.asset_source for n in exp_solar.scene_graph.nodes],
        )

    def test_visual_hint_behavior_remains_intact_alongside_source_intelligence(self):
        rows = _csv_rows({
            "script_segment": "A quiet dam sits in the canyon.",
            "visual_hint": "aerial drone shot of a massive concrete dam at golden hour",
        })
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertEqual(
            result.scene_graph.nodes[0].asset_reference,
            "aerial drone shot of a massive concrete dam at golden hour",
        )

    def test_compound_splitting_still_works_alongside_source_intelligence(self):
        rows = _rows(
            "Engineers had to divert the Colorado River, excavate the "
            "foundation, and manage enormous amounts of concrete."
        )
        result = generate_scene_graph_local_planner("seg", rows)
        self.assertGreaterEqual(len(result.scene_graph.nodes), 3)


if __name__ == "__main__":
    unittest.main()


class TestGroupsFitTheStylesChapterCapacity(unittest.TestCase):
    """Real project: "The tunnel project happened in four stages:" + four
    stages became ONE five-card group (intro chained in), overflowing Exp
    Solar's four-cards-per-chapter layout -> "layout produced overlapping
    nodes" on every render of that script."""

    def _graph(self, texts, style="exp_solar"):
        rows = [SceneRow(scene_number=str(i + 1), script_segment=t) for i, t in enumerate(texts)]
        result = generate_scene_graph_local_planner("s", rows, style_preset=style)
        self.assertTrue(result.ok, result.errors)
        return result.scene_graph

    def test_collection_intro_is_its_titled_card_not_a_fifth_group_member(self):
        graph = self._graph([
            "The tunnel project happened in four stages:",
            "First, surveyors mapped the canyon and marked the routes.",
            "Second, drilling crews blasted through the canyon walls.",
            "Then, workers enlarged the tunnels and lined them with concrete.",
            "Finally, engineers redirected the river into the tunnels.",
        ])
        group_edges = [e for e in graph.edges if e.kind in ("group", "group_grid")]
        members = {e.from_node for e in group_edges} | {e.to_node for e in group_edges}
        self.assertNotIn("n1", members)
        self.assertEqual(len(members), 4)
        self.assertTrue(any("four stages" in t.text.lower() for t in graph.title_cues))

    def test_sequence_longer_than_four_steps_uses_the_grid_group(self):
        graph = self._graph([
            "First, the site was surveyed across the whole canyon.",
            "Second, the access roads were cut into the rock.",
            "Third, the diversion tunnels were drilled through.",
            "Fourth, the cofferdams were built across the river.",
            "Finally, the foundation was excavated down to bedrock.",
        ])
        kinds = {e.kind for e in graph.edges if e.kind in ("group", "group_grid")}
        self.assertEqual(kinds, {"group_grid"})

    def test_exp_solar_layout_of_both_shapes_has_no_overlaps(self):
        from scene_graph.layout import compute_layout, find_overlaps
        from scene_graph.pipeline import _sync_grouped_node_timing
        from scene_graph.style_presets import load_style_preset

        cap = (load_style_preset("exp_solar").metadata or {}).get("max_active_per_chapter")
        for texts in (
            ["The project happened in four stages:", "First, a survey was made of the site.",
             "Second, the drilling crews started work.", "Then, the tunnels were lined.",
             "Finally, the river was diverted."],
            ["First, a survey was made of the site.", "Second, the roads were cut.",
             "Third, tunnels were drilled.", "Fourth, cofferdams were built.",
             "Finally, the foundation was dug."],
        ):
            graph = _sync_grouped_node_timing(self._graph(texts))
            self.assertEqual(find_overlaps(compute_layout(graph, max_active_per_chapter=cap)), [])


class TestEngagementIntelligence(unittest.TestCase):
    """Planner-built videos used to have almost no chapter titles, no caption
    highlights, no name tags, unlabeled arrows and no reaction beats — all
    features the renderer/audio already support when a hand-written CSV sets
    them. Real script: test_fixtures/voiceover_check/hoover_plan.csv."""

    @classmethod
    def setUpClass(cls):
        import csv
        from pathlib import Path

        path = Path(__file__).resolve().parent / "test_fixtures" / "voiceover_check" / "hoover_plan.csv"
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        cls.graph = generate_scene_graph_local_planner(
            "s", [SceneRow.from_csv_row(r) for r in rows], style_preset="exp_solar").scene_graph
        # Content cards only (the chapter strip's tabs are checklist_item
        # nodes: a label, no caption — covered by TestChapterProgressStrip).
        cls.cards = [n for n in cls.graph.nodes if n.type != "checklist_item"]

    def test_chapters_follow_the_scripts_sections(self):
        titles = [t.text for t in self.graph.title_cues]
        self.assertEqual(titles[0], "Hoover Dam")  # the subject the opening line introduces
        self.assertIn("Before Construction Began", titles)
        # ("Here's How It Works" opens row 18, but the list intro on row 19
        # titles that chapter — two bands seconds apart would just flash.)
        self.assertNotIn("Here's How It Works", titles)
        self.assertIn("The Tunnel Project: Four Stages", titles)
        self.assertIn("Black Canyon: Three Major Challenges", titles)
        # A list chapter's title must not stay over the next section: the
        # sections after each list get their own titles.
        self.assertIn("Changing the River's Path", titles)
        self.assertIn("Diverting the River", titles)
        self.assertGreaterEqual(len(titles), 6)

    def test_chapters_are_neither_every_scene_nor_absent_for_long_stretches(self):
        from scene_graph import generator as G

        starts = [t.at for t in self.graph.title_cues]
        beats = sorted(b.start for b in self.graph.beats)
        for a, b in zip(starts, starts[1:]):
            between = [s for s in beats if a <= s < b]
            self.assertGreaterEqual(len(between), 2, "title bands too close together")
            self.assertLessEqual(len(between), G._MAX_ROWS_PER_CHAPTER + 2)

    def test_most_captions_highlight_a_real_word_of_the_caption(self):
        highlighted = [n for n in self.cards if n.caption and n.caption.highlight]
        self.assertGreaterEqual(len(highlighted), int(0.8 * len(self.cards)))
        for node in highlighted:
            self.assertIn(node.caption.highlight.lower(), node.caption.text.lower())
            self.assertFalse(node.caption.highlight.lower().endswith(("ly", "ed")), node.caption.highlight)
        for a, b in zip(self.cards, self.cards[1:]):
            if a.caption and b.caption and a.caption.highlight and b.caption.highlight:
                self.assertNotEqual(a.caption.highlight.lower(), b.caption.highlight.lower())

    def test_name_tags_are_real_names_introduced_once(self):
        labels = [n.label for n in self.cards if n.label]
        self.assertIn("Hoover Dam", labels)
        self.assertIn("Colorado River", labels)
        self.assertEqual(len(labels), len(set(labels)))
        for bad in ("Giant", "Engineers", "Here's", "Diverting", "Surveyors", "Workers"):
            self.assertNotIn(bad, labels)

    def test_no_arrow_bridges_out_of_a_finished_list(self):
        # "Unlike a modern construction site" was linked to the last card of
        # the "Three Major Challenges" list, so layout kept that finished list
        # on screen during the next chapter.
        members = {e.from_node for e in self.graph.edges if e.kind in ("group", "group_grid")}
        members |= {e.to_node for e in self.graph.edges if e.kind in ("group", "group_grid")}
        for e in self.graph.edges:
            if e.kind == "sequential":
                self.assertNotIn(e.from_node, members, e.id)

    def test_name_tags_only_name_what_the_card_shows_and_never_the_cta(self):
        for node in self.cards:
            if node.label:
                self.assertIn(node.label.lower(), node.caption.text.lower())
                self.assertNotEqual(node.semantic_role, "cta")

    def test_arrows_carry_a_relationship_label(self):
        arrows = [e for e in self.graph.edges if e.kind == "sequential"]
        self.assertTrue(arrows)
        self.assertTrue(all(e.metadata.get("label") for e in arrows))

    def test_captions_are_short_clean_clauses(self):
        from scene_graph import generator as G

        members = {e.to_node for e in self.graph.edges if e.kind in ("group", "group_grid")}
        members |= {e.from_node for e in self.graph.edges if e.kind in ("group", "group_grid")}
        for node in self.cards:
            if node.caption:
                text = node.caption.text
                limit = G._GROUP_CAPTION_MAX_WORDS if node.id in members else G._CAPTION_MAX_WORDS
                self.assertLessEqual(len(text.split()), limit, text)
                self.assertFalse(text.endswith(("...", "…", ":", ",")), text)
                last = text.split()[-1].lower()
                self.assertNotIn(last, G._DANGLING_END_WORDS, text)
                self.assertFalse(last.endswith("ing"), text)

    def test_reaction_lines_become_reaction_beats(self):
        rows = [SceneRow(scene_number=str(i + 1), script_segment=t) for i, t in enumerate([
            "The dam took five years to build across the canyon.",
            "Imagine standing at the bottom of that canyon!",
            "Workers poured concrete around the clock in shifts.",
        ])]
        graph = generate_scene_graph_local_planner("s", rows, style_preset="exp_solar").scene_graph
        self.assertEqual(graph.nodes[1].semantic_role, "reaction")

    def test_full_exp_solar_layout_with_all_features_has_no_overlaps(self):
        from scene_graph.layout import compute_layout, find_overlaps
        from scene_graph.pipeline import _sync_grouped_node_timing

        for style, cap in (("exp_solar", 4), ("overscaled", None)):
            graph = _sync_grouped_node_timing(self.graph) if style == "exp_solar" else self.graph
            self.assertEqual(find_overlaps(compute_layout(graph, max_active_per_chapter=cap)), [], style)


class TestChapterProgressStrip(unittest.TestCase):
    """Exp Solar's numbered chapter strip (current chapter highlighted) was
    never produced by the planner — every planner video lacked it."""

    def _graph(self, style):
        import csv
        from pathlib import Path

        path = Path(__file__).resolve().parent / "test_fixtures" / "voiceover_check" / "hoover_plan.csv"
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = [SceneRow.from_csv_row(r) for r in csv.DictReader(f)]
        return generate_scene_graph_local_planner("s", rows, style_preset=style).scene_graph

    def test_one_tab_per_chapter_starting_with_its_chapter(self):
        graph = self._graph("exp_solar")
        tabs = [n for n in graph.nodes if n.type == "checklist_item"]
        self.assertEqual([t.appear_at for t in tabs], [c.at for c in graph.title_cues])
        self.assertEqual([t.label for t in tabs][:4], ["Hoover Dam", "Construction", "Black Canyon", "River's Path"])
        for tab in tabs:
            self.assertLessEqual(len(tab.label.split()), 3)

    def test_strip_is_laid_out_without_overlaps(self):
        from scene_graph.layout import compute_layout, find_overlaps
        from scene_graph.pipeline import _sync_grouped_node_timing

        layout = compute_layout(_sync_grouped_node_timing(self._graph("exp_solar")), max_active_per_chapter=4)
        self.assertGreater(layout.checklist_band_px, 0)
        self.assertEqual(len(layout.checklist_windows), len(self._graph("exp_solar").title_cues))
        self.assertEqual(find_overlaps(layout), [])

    def test_tabs_never_request_media(self):
        from unittest import mock
        from scene_graph import media_resolution

        captured = []
        with mock.patch("video_generator.resolve_scene_assets", lambda rows, d, **k: captured.extend(rows)):
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as tmp:
                media_resolution.resolve_scene_graph_media(self._graph("exp_solar"), images_dir=Path(tmp))
        self.assertEqual(len(captured), 26)

    def test_overscaled_style_has_no_strip(self):
        self.assertFalse([n for n in self._graph("overscaled").nodes if n.type == "checklist_item"])

    def test_short_videos_with_few_chapters_have_no_strip(self):
        rows = [SceneRow(scene_number=str(i + 1), script_segment=f"Scene {i} of a very short video about dams.")
                for i in range(3)]
        graph = generate_scene_graph_local_planner("s", rows, style_preset="exp_solar").scene_graph
        self.assertFalse([n for n in graph.nodes if n.type == "checklist_item"])
