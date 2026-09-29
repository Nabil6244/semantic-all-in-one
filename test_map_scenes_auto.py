"""Automatic map scenes (step 3): the place detector, normal mode's AI-plan
map pass (full-screen style), the Local Visual Planner, full-screen map
nodes in Overscaled/Exp Solar layout + render, and name-safe chapter titles."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from map_scene.clip import MAP_CLIP_MARKER
from map_scene.detect import detect_map_place
from scene_graph.generator import _chapter_title, generate_scene_graph_local_planner, scene_rows_from_csv_rows
from scene_graph.layout import compute_layout, find_overlaps
from scene_graph.map_nodes import prepare_map_nodes, subtract_windows
from scene_graph.schema import CaptionSpec, SceneGraph, SceneNode, TitleCue
from visual_director.map_pass import add_map_scenes
from visual_director.schema import VisualPlan, VisualScene, parse_visual_plan


def _rows(*lines, extra_by_index=None):
    extra_by_index = extra_by_index or {}
    rows = []
    for i, text in enumerate(lines, start=1):
        row = {"scene_number": str(i), "script_segment": text}
        row.update(extra_by_index.get(i, {}))
        rows.append(row)
    return scene_rows_from_csv_rows(rows)


class TestPlaceDetector(unittest.TestCase):
    def test_places_used_as_places_become_maps(self):
        cases = {
            "Our story begins in the Florida Panhandle.": "Florida > Florida Panhandle",
            "Across Egypt, the Nile feeds millions.": "Egypt",
            "Oil was found in Texas in 1901.": "United States of America > Texas",
            "Nevada's desert heat was brutal.": "United States of America > Nevada",
            "Hoover Dam stands between Arizona and Nevada.": "United States of America > Arizona",
            "Workers moved to Ontario for the job.": "Canada > Ontario",
        }
        for text, prompt in cases.items():
            pick = detect_map_place(text)
            self.assertIsNotNone(pick, text)
            self.assertEqual(pick.prompt, prompt, text)

    def test_names_that_are_not_used_as_places_are_ignored(self):
        for text in ("Chad said the plan would never work.",            # a person, no location word
                     "He studied at Florida State University.",          # a longer name containing a state
                     "The Colorado River carved the canyon.",            # a river, not the state
                     "Florida has a strange shape.",                     # named, but not placed
                     "Turbines power homes across the Southwest.",       # a direction, not a place
                     "Crews arrived in Black Canyon in 1931."):          # not in the bundled data
            self.assertIsNone(detect_map_place(text), text)


def _scene(i, text, asset_type="stock_video", duration=5.0):
    return VisualScene(scene_id=i, narration=text, visual_goal="g", visual_description="d", asset_type=asset_type,
                       provider_preference=asset_type, search_queries=["q"], timestamp_needed=False,
                       timestamp_hint="", duration=duration, importance="medium", fallbacks=["youtube"],
                       visual_treatment="", transition="cut")


class TestNormalModeAiPlan(unittest.TestCase):
    def test_place_lines_become_full_screen_maps_with_spacing(self):
        plan = VisualPlan(topic="t", scenes=[
            _scene(1, "Our story begins in the Florida Panhandle."),
            _scene(2, "Beaches stretch along the water."),
            _scene(3, "Soldiers trained in Florida too."),          # 10 s after a map: too soon
            _scene(4, "Far away, across Egypt, crews worked.", duration=30),  # 15 s: too soon
            _scene(5, "Then they moved to Texas."),                 # 45 s: allowed
        ])
        self.assertEqual(add_map_scenes(plan), 2)
        rows = plan.to_scene_rows()
        self.assertEqual([r.asset_type for r in rows], ["map", "stock_video", "stock_video", "stock_video", "map"])
        self.assertEqual((rows[0].prompt, rows[4].prompt), ("Florida > Florida Panhandle", "United States of America > Texas"))
        again = parse_visual_plan(plan.to_dict())  # saved with the project and loaded back
        self.assertEqual((again.scenes[0].asset_type, again.scenes[0].to_scene_row().prompt), ("map", "Florida > Florida Panhandle"))
        csv_row = plan.to_csv_dicts()[0]
        self.assertEqual((csv_row["asset_type"], csv_row["prompt"]), ("map", "Florida > Florida Panhandle"))

    def test_never_two_maps_in_a_row(self):
        plan = VisualPlan(topic="t", scenes=[
            _scene(1, "It began in Egypt.", duration=40), _scene(2, "Then it spread to Texas.", duration=40)])
        self.assertEqual(add_map_scenes(plan), 1)

    def test_local_and_property_plans_are_left_alone(self):
        local = VisualPlan(topic="t", scenes=[_scene(1, "It began in Egypt.", asset_type="local")])
        self.assertEqual(add_map_scenes(local), 0)
        prop = VisualPlan(topic="t", scenes=[_scene(1, "A home in Texas.", asset_type="research"),
                                             _scene(2, "It sits in Florida.")])
        self.assertEqual(add_map_scenes(prop), 0)


class TestLocalPlannerMaps(unittest.TestCase):
    def test_bare_narration_place_line_becomes_one_map_node(self):
        graph = generate_scene_graph_local_planner("s", _rows(
            "Our story begins in the Florida Panhandle, a thin strip of land along the Gulf coast and far from Miami.",
            "White sand beaches stretch for miles.")).scene_graph
        maps = [n for n in graph.nodes if n.asset_source == "map"]
        self.assertEqual([n.asset_reference for n in maps], ["Florida > Florida Panhandle"])
        self.assertEqual(maps[0].id, "n1")  # one node, not split into several cards
        self.assertTrue(all(e.from_node != "n1" and e.to_node != "n1" for e in graph.edges))

    def test_author_asset_choices_are_never_replaced(self):
        graph = generate_scene_graph_local_planner("s", _rows(
            "Our story begins in the Florida Panhandle.",
            extra_by_index={1: {"asset_type": "stock_video", "prompt": "beach"}},
        )).scene_graph
        self.assertEqual(graph.nodes[0].asset_source, "stock_video")

    def test_chapter_titles_never_cut_a_name_in_half(self):
        self.assertEqual(_chapter_title("Our story begins in the Florida Panhandle, a thin strip of land."),
                         "Our Story Begins in the Florida Panhandle")
        self.assertEqual(_chapter_title("For nearly a century, Hoover Dam has stood between Arizona and Nevada."),
                         "For Nearly a Century")


def _graph_with_map():
    nodes = [
        SceneNode(id="a", type="image", asset_source="stock_image", asset_reference="x", appear_at=0.0,
                  caption=CaptionSpec(text="first card")),
        SceneNode(id="m", type="image", asset_source="map", asset_reference="Egypt", appear_at=4.0,
                  caption=CaptionSpec(text="The Nile Country")),
        SceneNode(id="b", type="image", asset_source="stock_image", asset_reference="y", appear_at=9.0),
    ]
    from scene_graph.schema import SceneEdge

    edges = [SceneEdge(id="e_a_m", from_node="a", to_node="m", kind="sequential", draw_at=4.0)]
    return SceneGraph(segment_id="s", duration=14.0, nodes=nodes, edges=edges,
                      title_cues=[TitleCue(text="Chapter One", at=0.0)])


class TestFullScreenMapNodes(unittest.TestCase):
    def test_prepare_turns_the_caption_into_the_map_label_and_drops_arrows(self):
        graph = prepare_map_nodes(_graph_with_map())
        m = next(n for n in graph.nodes if n.id == "m")
        self.assertEqual((m.type, m.border, m.shadow, m.caption), ("video_loop", False, False, None))
        self.assertEqual(m.asset_reference, "Egypt | label: The Nile Country")
        self.assertEqual(graph.edges, [])
        long = SceneNode(id="z", asset_source="map", asset_reference="Egypt",
                         caption=CaptionSpec(text="Engineers redirected the river into four huge tunnels"))
        prepare_map_nodes(SceneGraph(segment_id="s", duration=5.0, nodes=[long]))
        self.assertEqual(long.asset_reference, "Egypt")  # a sentence is no label; the map names the place

    def test_layout_gives_the_map_the_whole_frame_and_the_screen_to_itself(self):
        graph = prepare_map_nodes(_graph_with_map())
        layout = compute_layout(graph)
        rect = layout.node_rects["m"]
        self.assertEqual((rect.x, rect.y, rect.width, rect.height), (0.0, 0.0, float(layout.canvas_width), float(layout.canvas_height)))
        self.assertEqual(layout.active_windows["m"], (4.0, 9.0))
        self.assertEqual(find_overlaps(layout), [])
        self.assertLessEqual(layout.active_windows["a"][1], 4.0)
        # The chapter title band is not drawn over the map and returns after it.
        self.assertEqual([(s, e) for _t, s, e in layout.title_windows], [(0.0, 4.0), (9.0, 14.0)])
        self.assertNotIn("m", layout.caption_positions)

    def test_window_subtraction(self):
        self.assertEqual(subtract_windows((0, 10), [(3, 5)]), [(0, 3), (5, 10)])
        self.assertEqual(subtract_windows((0, 10), [(0, 9.8)]), [])


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
class TestMapHoldInOverscaledRender(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _clip(self, name, tag):
        path = self.tmp / name
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=1",
               "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if tag:
            cmd += ["-metadata", f"comment={MAP_CLIP_MARKER}"]
        subprocess.run(cmd + [str(path)], check=True)
        return str(path)

    def test_a_short_map_clip_holds_for_its_whole_window_other_clips_do_not(self):
        from scene_graph.render import _node_video_layer

        graph = prepare_map_nodes(_graph_with_map())
        layout = compute_layout(graph)
        m = next(n for n in graph.nodes if n.id == "m")
        layer = _node_video_layer(m, layout=layout, resolved_media={"m": self._clip("m.mp4", True)})
        self.assertAlmostEqual(layer.duration, 5.0, places=2)  # the whole 4 s -> 9 s window
        self.assertIn("tpad=stop_mode=clone", layer.pre_filter)
        b = next(n for n in graph.nodes if n.id == "b")
        plain = _node_video_layer(b, layout=layout, resolved_media={"b": self._clip("b.mp4", False)})
        self.assertNotIn("tpad", plain.pre_filter)


if __name__ == "__main__":
    unittest.main()
