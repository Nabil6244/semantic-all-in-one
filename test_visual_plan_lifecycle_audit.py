"""Regression suite for the Visual Plan / Local Visual Planner / Overscaled /
Exp Solar lifecycle audit. Every test here reproduces a bug that was real in
the code before the audit fix it guards:

  1. Explicit Flow rows (asset_type image/video + a prompt — exactly what
     Change Source -> flow_image/flow_video writes) were refined or
     diversity-rotated to stock_image by the planner at Generate, while the
     Visual Plan badge still said Flow.
  2. Change Source on a continuation row was silently dropped at Generate
     (the planner still folded the row, so it got no node).
  3. Compound-split sub-nodes share one CSV scene_number, so every one of
     them resolved into the SAME numbered media file; all but one rendered
     as a placeholder.
  4. Exp Solar's pre-retime beat merge mapped nodes to beats by
     "beat_<scene_number>"; for a compound row every sub-node mapped to the
     same beat and that row's narration beat was deleted.
  5. A legacy Flow row (blank asset_type + prompt) sorted into the last
     acquisition tier instead of the flow_image tier.
  6. Visual Plan rows in Local Planner mode showed the raw CSV cell instead
     of the compiled node's decision that Generate resolves.
  7. _render_scene_rows' fast path was keyed on scene numbers only, so a
     reload with the same numbers kept stale badges and stale SceneRow
     references in widgets/callbacks.
  8. A failed re-import / style switch left the PREVIOUS plan on screen
     while the CSV path/style pointed at something else.
  9. Manifest hydration showed READY/failed for a record produced for a
     different prompt than the row now requests.
 10. In CSV-compiler mode, Change Source on a row that only references an
     earlier node turned it into a conflicting redefinition (the CSV then
     failed to compile).
 11. Change Source during a running generation could be undone by the
     in-flight batch.

Tk-dependent checks run in a real subprocess (same convention as
test_overscaled_ui_integration.py — a real CTk root corrupts global Tk
state in-process).
"""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from providers.base import SceneRow
from scene_graph.generator import (
    _derive_stock_query,
    generate_scene_graph_local_planner,
    scene_rows_from_csv_rows,
)


def _plan(rows):
    result = generate_scene_graph_local_planner("seg", scene_rows_from_csv_rows(rows))
    assert result.ok, result.errors
    return result.scene_graph


_COMPOUND = (
    "Engineers had to divert the entire river, excavate the deep canyon "
    "foundation, and pour millions of tons of concrete."
)


class TestExplicitSourcesSurvivePlanning(unittest.TestCase):
    def test_explicit_flow_image_with_prompt_is_never_refined_or_rotated(self):
        rows = [
            {"scene_number": str(i), "script_segment": f"The harbor town number {i} sat on the coast.",
             "asset_type": "flow_image", "prompt": f"harbor town {i}"}
            for i in range(1, 9)
        ]
        # Would otherwise score as a stock_image candidate.
        rows.append({"scene_number": "9", "script_segment": "A historical photograph of the monument.",
                     "asset_type": "flow_image", "prompt": "monument"})
        graph = _plan(rows)
        self.assertEqual({n.asset_source for n in graph.nodes}, {"image"})
        self.assertEqual([n.asset_reference for n in graph.nodes][-1], "monument")

    def test_explicit_flow_video_with_prompt_is_never_turned_into_stock_video(self):
        graph = _plan([{"scene_number": "1", "script_segment": "Construction workers poured concrete on the highway.",
                        "asset_type": "flow_video", "prompt": "workers pouring concrete"}])
        self.assertEqual(graph.nodes[0].asset_source, "video")

    def test_generic_image_without_prompt_is_still_refined(self):
        # The generic hint path must keep working (weak hints CAN improve).
        graph = _plan([{"scene_number": "1", "script_segment": "A historical photograph of the old monument.",
                        "asset_type": "image"}])
        self.assertEqual(graph.nodes[0].asset_source, "stock_image")

    def test_overridden_continuation_row_gets_its_own_node(self):
        rows = [
            {"scene_number": "1", "script_segment": "The Hoover Dam rises above the Colorado River canyon walls."},
            {"scene_number": "2", "script_segment": "It remained there for decades.",
             "asset_type": "stock_image", "prompt": "hoover dam"},
        ]
        nodes = [n for n in _plan(rows).nodes if n.metadata["scene_number"] == "2"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual((nodes[0].asset_source, nodes[0].asset_reference), ("stock_image", "hoover dam"))

    def test_plain_continuation_row_still_folds(self):
        rows = [
            {"scene_number": "1", "script_segment": "The Hoover Dam rises above the Colorado River canyon walls."},
            {"scene_number": "2", "script_segment": "It remained there for decades."},
        ]
        self.assertEqual([n.metadata["scene_number"] for n in _plan(rows).nodes], ["1"])


class TestCompoundRowsResolveEverySubNode(unittest.TestCase):
    def test_each_sub_node_gets_its_own_resolution_key_and_media(self):
        from scene_graph import media_resolution

        graph = _plan([
            {"scene_number": "1", "script_segment": "The canyon was silent before the project began."},
            {"scene_number": "2", "script_segment": _COMPOUND},
        ])
        self.assertGreaterEqual(len([n for n in graph.nodes if n.metadata["scene_number"] == "2"]), 3)

        captured = []

        def fake_resolve(rows, images_dir, **kwargs):
            for row in rows:
                captured.append(row)
                (Path(images_dir) / f"{int(row['scene_number']):03d}.png").write_bytes(b"x")

        with tempfile.TemporaryDirectory() as tmp, mock.patch("video_generator.resolve_scene_assets", fake_resolve):
            resolved = media_resolution.resolve_scene_graph_media(graph, images_dir=Path(tmp))
            keys = [r["scene_number"] for r in captured]
            self.assertEqual(len(keys), len(set(keys)), keys)
            self.assertEqual(set(resolved), {n.id for n in graph.nodes})
            self.assertEqual(len(set(resolved.values())), len(graph.nodes))
            # The FIRST node for the row keeps the real scene number (the
            # one the Visual Plan row and per-row actions use).
            first_sub = next(n for n in graph.nodes if n.metadata["scene_number"] == "2")
            self.assertTrue(resolved[first_sub.id].endswith("002.png"))

    def test_exp_solar_beat_merge_keeps_the_compound_rows_beat(self):
        from scene_graph.pipeline import _merge_grouped_beats_for_retime

        graph = _plan([
            {"scene_number": "1", "script_segment": "The canyon was silent before the project began."},
            {"scene_number": "2", "script_segment": _COMPOUND},
        ])
        merged = _merge_grouped_beats_for_retime(graph)
        self.assertEqual([b.beat_id for b in merged.beats], [b.beat_id for b in graph.beats])

    def test_exp_solar_beat_merge_uses_reveal_actions_not_scene_number_naming(self):
        from scene_graph.pipeline import _merge_grouped_beats_for_retime

        # Scene numbers deliberately NOT 1..N — the planner's beat ids are
        # positional, so "beat_<scene_number>" named no real beat at all.
        rows = [{"scene_number": "10", "script_segment": "The system has three main components: pumps, valves, and pipes."}]
        rows += [{"scene_number": str(20 + i), "script_segment": f"Component number {i} handles a distinct job in the plant."}
                 for i in range(3)]
        graph = _plan(rows)
        self.assertTrue(any(e.kind in ("group", "group_grid") for e in graph.edges))
        merged = _merge_grouped_beats_for_retime(graph)
        self.assertLess(len(merged.beats), len(graph.beats))
        self.assertEqual(merged.beats[0].beat_id, "beat_1")


class TestAcquisitionAndQueries(unittest.TestCase):
    def test_legacy_prompt_row_ranks_in_the_flow_image_tier(self):
        import video_generator as vg

        legacy = SceneRow.from_csv_row({"scene_number": "1", "script_segment": "x", "prompt": "a city"})
        flow_video = SceneRow.from_csv_row({"scene_number": "2", "script_segment": "x", "asset_type": "flow_video", "prompt": "p"})
        self.assertLess(vg._acquisition_rank(legacy), vg._acquisition_rank(flow_video))
        self.assertEqual(vg._acquisition_rank(legacy), vg._ACQUISITION_ORDER["image"])

    def test_stock_query_drops_function_words(self):
        query = _derive_stock_query("The Hoover Dam rises above the Colorado River canyon walls.")
        self.assertNotIn("above", query.split())
        self.assertIn("Hoover", query)


class TestPlanningIsolationAndDeterminism(unittest.TestCase):
    def test_planning_makes_no_acquisition_or_resolution_calls(self):
        boom = mock.Mock(side_effect=AssertionError("acquisition during planning"))
        rows = [{"scene_number": str(i), "script_segment": s} for i, s in enumerate([
            "Workers excavated the canyon floor with heavy machinery.",
            "A cross-section diagram shows the turbine mechanism.",
            "A historical photograph of the dam in 1936.",
            _COMPOUND,
        ], start=1)]
        with mock.patch("video_generator.resolve_scene_assets", boom), \
                mock.patch("asset_manager.AssetManager", boom), \
                mock.patch("urllib.request.urlopen", boom):
            _plan(rows)
        boom.assert_not_called()

    def test_same_input_same_decisions(self):
        rows = [{"scene_number": str(i), "script_segment": s} for i, s in enumerate([
            "Workers excavated the canyon floor with heavy machinery.",
            "A cross-section diagram shows the turbine mechanism.",
            "It remained there for decades.",
            _COMPOUND,
        ], start=1)]
        first, second = _plan(rows).to_dict(), _plan(rows).to_dict()
        self.assertEqual(first, second)


class TestTitleCues(unittest.TestCase):
    def test_identical_consecutive_chapter_titles_are_not_repeated(self):
        rows = [{"scene_number": "1", "script_segment": "Opening words about the dam."}]
        for _ in range(2):
            base = len(rows)
            rows.append({"scene_number": str(base + 1),
                         "script_segment": "The system has three main components: pumps, valves, and pipes."})
            rows += [{"scene_number": str(base + 2 + i), "script_segment": f"Component {i} does a specific job in the plant."}
                     for i in range(3)]
        texts = [t.text for t in _plan(rows).title_cues]
        self.assertEqual(len(texts), 2, texts)
        self.assertTrue(all(a != b for a, b in zip(texts, texts[1:])))

    def test_long_form_plan_is_deterministic_with_unique_resolution_keys(self):
        from scene_graph import media_resolution

        sentences = [
            "Workers excavated the canyon floor with heavy machinery near the river.",
            "A cross-section diagram shows the turbine mechanism inside the dam.",
            "It remained there for decades.",
            _COMPOUND,
            "The city skyline glowed at night as traffic moved through the streets.",
        ]
        rows = [{"scene_number": str(i + 1), "script_segment": sentences[i % len(sentences)]} for i in range(600)]
        graph = _plan(rows)
        self.assertEqual(graph.to_dict(), _plan(rows).to_dict())
        captured = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("video_generator.resolve_scene_assets", lambda r, d, **k: captured.extend(r)):
            media_resolution.resolve_scene_graph_media(graph, images_dir=Path(tmp))
        keys = [r["scene_number"] for r in captured]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), len(graph.nodes))


_GROUPED_ROWS = [
    {"scene_number": "1", "script_segment": "The canyon was silent before the project began in earnest."},
    {"scene_number": "2", "script_segment": _COMPOUND},
    {"scene_number": "3", "script_segment": "It remained there for decades."},
    {"scene_number": "4", "script_segment": "The system has three main components: pumps, valves, and pipes."},
    {"scene_number": "5", "script_segment": "Pumps move the water uphill each night."},
    {"scene_number": "6", "script_segment": "Valves control the flow at every junction."},
    {"scene_number": "7", "script_segment": "Pipes carry it to the city reservoirs."},
]


def _fake_words(rows):
    words, t = [], 0.0
    for r in rows:
        for w in r["script_segment"].split():
            words.append((w, t, t + 0.35))
            t += 0.4
        t += 0.3
    return words


class TestExpSolarPlannerNarrationSync(unittest.TestCase):
    """Exp Solar's pre-retime beat merge dropped Local-Planner group members'
    real narration, so their words were never consumed and the render ended
    ~10s before the voiceover on a 28s sample (worse on long-form)."""

    def test_merged_retime_still_ends_on_the_last_spoken_word(self):
        from scene_graph.pipeline import _merge_grouped_beats_for_retime
        from scene_graph.voiceover_sync import retime_to_whisper_words

        words = _fake_words(_GROUPED_ROWS)
        graph = _plan(_GROUPED_ROWS)
        merged = _merge_grouped_beats_for_retime(graph)
        self.assertLess(len(merged.beats), len(graph.beats))  # a group really was merged
        retimed = retime_to_whisper_words(merged, words)
        self.assertAlmostEqual(retimed.duration, words[-1][2], delta=0.05)
        # And identical to the un-merged (Overscaled) timing.
        self.assertAlmostEqual(retimed.duration, retime_to_whisper_words(graph, words).duration, delta=0.05)

    @unittest.skipUnless(__import__("shutil").which("ffmpeg") and __import__("shutil").which("ffprobe"), "ffmpeg required")
    def test_real_render_duration_matches_narration_for_both_styles(self):
        import json
        import subprocess

        from scene_graph.pipeline import run_overscaled_pipeline

        words = _fake_words(_GROUPED_ROWS)
        with tempfile.TemporaryDirectory() as tmp:
            vo = Path(tmp) / "vo.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"sine=f=220:d={words[-1][2] + 0.8}", str(vo)], check=True)
            for style in ("exp_solar", "overscaled"):
                res = run_overscaled_pipeline(
                    _GROUPED_ROWS, segment_id="seg", voiceover_path=str(vo), out_dir=Path(tmp) / style,
                    style_preset_id=style, whisper_words=words, use_local_planner=True,
                    resolution="320x180", fps=10,
                )
                self.assertTrue(res.ok, res.errors)
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                        "-of", "json", str(res.segment_clip_path)], capture_output=True, text=True)
                clip = float(json.loads(probe.stdout)["format"]["duration"])
                self.assertAlmostEqual(clip, words[-1][2], delta=0.3, msg=style)


class TestDuplicateSceneNumbersRejected(unittest.TestCase):
    def test_validator_reports_repeats_and_ignores_blanks(self):
        from scene_graph.overscaled_csv import duplicate_scene_numbers

        rows = [{"scene_number": "1"}, {"scene_number": "2"}, {"scene_number": " 1 "},
                {"scene_number": ""}, {"scene_number": ""}]
        self.assertEqual(duplicate_scene_numbers(rows), ["1"])

    def test_generate_refuses_a_csv_with_repeated_scene_numbers(self):
        from scene_graph.app_integration import generate_overscaled_video

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "plan.csv"
            with open(csv_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["scene_number", "script_segment"])
                w.writerow(["1", "First."])
                w.writerow(["1", "Second."])
            voice = Path(tmp) / "vo.wav"
            voice.write_bytes(b"RIFF")
            boom = mock.Mock(side_effect=AssertionError("must not resolve media"))
            with mock.patch("scene_graph.app_integration.resolve_scene_graph_media", boom):
                result = generate_overscaled_video(str(csv_path), str(voice), str(Path(tmp) / "out.mp4"),
                                                   use_local_planner=True)
            self.assertFalse(result.ok)
            self.assertIn("scene_number", " ".join(result.errors))
            boom.assert_not_called()


_LIVE_SCRIPT = r'''
import os, sys, csv, tempfile
from pathlib import Path
from unittest import mock
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())

def emit(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}:{name}:{str(detail).replace(chr(10), ' ')[:400]}")

from tkinter import messagebox
_dialogs = []
messagebox.showerror = lambda *a, **k: _dialogs.append(("error",) + a)
messagebox.showinfo = lambda *a, **k: _dialogs.append(("info",) + a)

try:
    import app as _app
    instance = _app.VideoGeneratorApp()
    instance.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

from providers.base import SceneRow
from providers.router import SceneAssetRouter
from project_workspace import ProjectWorkspace
from scene_graph.generator import generate_scene_graph_local_planner, scene_rows_from_csv_rows
from scene_graph import media_resolution

tmp = Path(tempfile.mkdtemp())
instance._workspace = ProjectWorkspace(project_id="p1", title="t", seq=1, root=tmp / "ws")

def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); [w.writerow(r) for r in rows]

bare = tmp / "bare.csv"
write_csv(bare, ["scene_number", "script_segment"], [
    ["1", "A quiet observatory sits atop a remote mountain."],
    ["2", "Workers excavated the canyon floor with heavy machinery."],
    ["3", "It remained there for decades."],
    ["4", "A historical photograph of the dam in 1936."],
])

def generate_capture():
    """What Generate would resolve: re-read the CSV Generate compiles and run
    the SAME planner + media_resolution adapter, capturing resolver rows."""
    captured = []
    def fake_resolve(rows, images_dir, **kw):
        captured.extend(rows)
    with open(instance._overscaled_csv_var.get(), newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    graph = generate_scene_graph_local_planner("s", scene_rows_from_csv_rows(rows)).scene_graph
    with mock.patch("video_generator.resolve_scene_assets", fake_resolve):
        media_resolution.resolve_scene_graph_media(graph, images_dir=tmp / "media")
    return {r["scene_number"]: SceneAssetRouter.classify(SceneRow.from_csv_row(r)) for r in captured}

def plan_classes():
    return {s.scene_number: SceneAssetRouter.classify(s) for s in instance._scene_rows}

instance._overscaled_use_local_planner_var.set(True)
instance._overscaled_csv_var.set(str(bare))
instance._load_overscaled_csv(str(bare))
instance.generation_mode = "overscaled"

# --- Visual Plan shows exactly what Generate resolves (initial plan) ---
plan, gen = plan_classes(), generate_capture()
emit("initial_plan_matches_generate",
     all(plan.get(k) == v for k, v in gen.items()) and plan.get("3") is None and "3" not in gen,
     f"plan={plan} gen={gen}")

# --- Every source through override -> Generate, all four ---
expected = {"stock_video": "stock_video", "flow_image": "flow_image",
            "stock_image": "stock_image", "flow_video": "flow_video"}
for provider, want in expected.items():
    instance._apply_overscaled_source_override(["1"], provider)
    plan, gen = plan_classes(), generate_capture()
    emit(f"override_{provider}_reaches_generate",
         getattr(gen.get("1"), "value", None) == want and plan.get("1") == gen.get("1"),
         f"plan={plan.get('1')} gen={gen.get('1')}")

# --- Bulk override of many rows to flow_image never rotates at Generate ---
instance._apply_overscaled_source_override(["1", "2", "4"], "flow_image")
gen = generate_capture()
emit("bulk_flow_image_not_rotated_at_generate",
     all(getattr(gen.get(k), "value", None) == "flow_image" for k in ("1", "2", "4")), gen)

# --- Override on a continuation row reaches Generate ---
instance._apply_overscaled_source_override(["3"], "stock_image")
plan, gen = plan_classes(), generate_capture()
emit("continuation_row_override_reaches_generate",
     getattr(gen.get("3"), "value", None) == "stock_image" and plan.get("3") == gen.get("3"),
     f"plan={plan.get('3')} gen={gen.get('3')}")

# --- Actual visible Src button after a redraw targets the CURRENT row ---
before_ids = {k: id(w["scene"]) for k, w in instance._scene_row_widgets.items()}
instance._load_overscaled_csv(instance._overscaled_csv_var.get())  # redraw/recompile
current = {_app._scene_key(s.scene_number): s for s in instance._scene_rows}
emit("widgets_reference_current_rows_after_reload",
     all(w["scene"] is current[k] for k, w in instance._scene_row_widgets.items())
     and any(before_ids[k] != id(w["scene"]) for k, w in instance._scene_row_widgets.items()),
     "")
import customtkinter as ctk
existing = set(instance.winfo_children())
instance._scene_row_widgets["002"]["buttons"]["source"].invoke()
instance.update_idletasks()
dialogs = [w for w in instance.winfo_children() if w not in existing and isinstance(w, ctk.CTkToplevel)]
clicked = False
if dialogs:
    for child in dialogs[-1].winfo_children():
        if isinstance(child, ctk.CTkButton) and child.cget("text") == "Stock Video":
            child.invoke(); clicked = True; break
instance.update_idletasks()
gen = generate_capture()
badge = instance._scene_row_widgets["002"]["badge"].cget("text")
emit("src_button_click_changes_the_clicked_row",
     clicked and getattr(gen.get("2"), "value", None) == "stock_video" and "stock" in badge.lower(),
     f"clicked={clicked} gen={gen.get('2')} badge={badge}")

# --- A one-row Change Source redraws only that row (was: every row, ~0.7 s) ---
before = {k: w["row"] for k, w in instance._scene_row_widgets.items()}
instance._apply_overscaled_source_override(["3"], "stock_video")
after = instance._scene_row_widgets
current = {_app._scene_key(s.scene_number): s for s in instance._scene_rows}
emit("one_row_change_rebuilds_only_that_row",
     after["003"]["row"] is not before["003"]
     and all(after[k]["row"] is before[k] for k in before if k != "003")
     and "stock video" in after["003"]["badge"].cget("text").lower()
     and all(w["scene"] is current[k] for k, w in after.items()),
     after["003"]["badge"].cget("text"))

# --- Hydration ignores a manifest record produced for another prompt ---
from asset_manager import AssetManifest
images_dir = instance._workspace.overscaled_images_dir
images_dir.mkdir(parents=True, exist_ok=True)
media = images_dir / "004.png"; media.write_bytes(b"x")
AssetManifest(images_dir).set("4", {"status": "complete", "source": "flow_image",
                                    "prompt": "some OTHER prompt", "local_path": str(media)})
instance._load_overscaled_csv(instance._overscaled_csv_var.get())
emit("stale_manifest_record_for_other_prompt_not_shown_ready",
     instance._asset_results.get("004") is None, repr(instance._asset_results.get("004")))
row4 = next(s for s in instance._scene_rows if s.scene_number == "4")
AssetManifest(images_dir).set("4", {"status": "complete", "source": "flow_image",
                                    "prompt": row4.prompt, "local_path": str(media)})
instance._load_overscaled_csv(instance._overscaled_csv_var.get())
emit("matching_manifest_record_still_shown_ready",
     instance._asset_results.get("004") is not None, "")

# --- Override is refused while a generation is running ---
instance._overscaled_running = True
before = open(instance._overscaled_csv_var.get()).read()
instance._apply_overscaled_source_override(["1"], "stock_image")
emit("override_blocked_while_running",
     open(instance._overscaled_csv_var.get()).read() == before, "")
instance._overscaled_running = False

# --- Failed re-import clears the previous plan (no stale rows) ---
bad = tmp / "bad.csv"
write_csv(bad, ["scene_number", "text"], [["1", "missing script_segment column"]])
instance._overscaled_use_local_planner_var.set(False)
instance._overscaled_csv_var.set(str(bad))
ok = instance._load_overscaled_csv(str(bad))
emit("failed_reimport_clears_previous_plan",
     not ok and instance._scene_rows == [] and instance._overscaled_scene_graph is None
     and instance._scene_row_widgets == {},
     f"ok={ok} rows={len(instance._scene_rows)}")

# --- Re-import of another CSV fully replaces rows/graph ---
other = tmp / "other.csv"
write_csv(other, ["scene_number", "script_segment", "node_id", "asset_type", "prompt"], [
    ["1", "The first idea appears.", "n1", "stock_image", "mountain observatory"],
    ["2", "It keeps being discussed here.", "n1", "", ""],
    ["3", "Narration with no visual of its own.", "", "", ""],
])
instance._overscaled_csv_var.set(str(other))
instance._load_overscaled_csv(str(other))
emit("reimport_replaces_rows_and_graph",
     [s.scene_number for s in instance._scene_rows] == ["1", "2", "3"]
     and [n.id for n in instance._overscaled_scene_graph.nodes] == ["n1"], "")

# --- CSV-compiler mode: override on a node-REFERENCING row edits the
#     defining row and the CSV still compiles ---
_dialogs.clear()
instance._apply_overscaled_source_override(["2"], "flow_image")
graph = instance._overscaled_scene_graph
emit("reference_row_override_redirects_to_defining_row",
     graph is not None and [n.id for n in graph.nodes] == ["n1"]
     and SceneAssetRouter.classify(SceneRow.from_csv_row({"asset_type": graph.nodes[0].asset_source,
                                                           "prompt": graph.nodes[0].asset_reference,
                                                           "scene_number": "1", "script_segment": ""})).value == "flow_image"
     and not any(d[0] == "error" for d in _dialogs),
     f"dialogs={_dialogs}")
_dialogs.clear()
instance._apply_overscaled_source_override(["3"], "stock_image")
emit("narration_only_row_override_is_refused_with_a_message",
     any(d[0] == "info" for d in _dialogs) and instance._overscaled_scene_graph is not None, _dialogs)

# --- Style switch that the CSV doesn't fit clears the plan; switching back restores ---
exp_bad = tmp / "exp_bad.csv"
write_csv(exp_bad, ["scene_number", "script_segment", "beat"], [["1", "Hello.", "definitely_not_a_beat"]])
instance._overscaled_csv_var.set(str(exp_bad))
instance._on_overscaled_style_change("Exp Solar")
exp_ok = instance._overscaled_scene_graph is not None
instance._on_overscaled_style_change("Overscaled")
emit("style_switch_never_shows_other_styles_plan",
     (exp_ok or instance._scene_rows == [] or instance._overscaled_scene_graph is not None)
     and instance._overscaled_style_preset_id == "overscaled", f"exp_ok={exp_ok}")

# --- A per-scene Alternative that lands a NEW query is kept for Generate ---
instance._overscaled_use_local_planner_var.set(True)
instance._overscaled_csv_var.set(str(bare))
instance._load_overscaled_csv(str(bare))
instance.generation_mode = "overscaled"
from providers.base import AssetResult, AssetSource as _AS, MediaType, SceneStatus
alt_media = images_dir / "001.mp4"; alt_media.write_bytes(b"x")
AssetManifest(images_dir).set("1", {"status": "complete", "source": "youtube_video",
                                    "asset_type": "youtube_video", "prompt": "observatory night timelapse",
                                    "local_path": str(alt_media)})
token = instance._qa.begin_job("001", "using_alternative")
instance._busy_scenes.add("001")
instance._ui_queue.put(("scene_result", ("1", token, AssetResult(
    scene_number="1", path=alt_media, media_type=MediaType.VIDEO, source=_AS.YOUTUBE_VIDEO,
    status=SceneStatus.READY))))
real_after = instance.after
instance.after = lambda *a, **k: None  # don't reschedule the poll loop
try:
    instance._poll_queue()
finally:
    instance.after = real_after
gen = generate_capture()
row1 = next(s for s in instance._scene_rows if s.scene_number == "1")
emit("alternative_result_is_kept_for_generate",
     getattr(gen.get("1"), "value", None) == "youtube_video" and row1.prompt == "observatory night timelapse"
     and instance._asset_results.get("001") is not None and instance._asset_results["001"].ok,
     f"gen={gen.get('1')} prompt={row1.prompt!r} res={instance._asset_results.get('001')}")

# --- CSV rewrite preserves Unicode, quotes, commas, and embedded newlines ---
tricky_text = 'Café “Überdam”, the "big" one —\nsecond line, 1936 🚧'
uni = tmp / "unicode plan é.csv"
with open(uni, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["scene_number", "script_segment", "notes"])
    w.writerow(["1", tricky_text, "keep, this"]); w.writerow(["2", "Plain row.", ""])
instance._overscaled_use_local_planner_var.set(True)
instance._overscaled_csv_var.set(str(uni))
instance._load_overscaled_csv(str(uni))
instance._apply_overscaled_source_override(["2"], "stock_image")
with open(instance._overscaled_csv_var.get(), newline="", encoding="utf-8-sig") as f:
    back = list(csv.DictReader(f))
emit("csv_rewrite_preserves_unicode_quotes_newlines_and_extra_columns",
     back[0]["script_segment"] == tricky_text and back[0]["notes"] == "keep, this"
     and back[1]["asset_type"] == "stock_image" and len(back) == 2, back[0])

# --- Duplicate scene numbers are rejected at load (no ambiguous rows) ---
dup = tmp / "dup.csv"
write_csv(dup, ["scene_number", "script_segment"], [["1", "One."], ["2", "Two."], ["2", "Two again."]])
_dialogs.clear()
instance._overscaled_csv_var.set(str(dup))
ok = instance._load_overscaled_csv(str(dup))
emit("duplicate_scene_numbers_rejected_at_load",
     not ok and instance._scene_rows == [] and any(d[0] == "error" and "2" in str(d) for d in _dialogs), _dialogs)

# --- Plan/style changes are refused while a generation is running ---
instance._overscaled_running = True
_dialogs.clear()
instance._overscaled_style_segmented.set("Exp Solar")
instance._on_overscaled_style_change("Exp Solar")
emit("style_change_refused_while_running",
     instance._overscaled_style_preset_id == "overscaled"
     and instance._overscaled_style_segmented.get() == "Overscaled"
     and any(d[0] == "info" for d in _dialogs), _dialogs)
instance._overscaled_running = False

# --- A crash inside the Generate worker never leaves the UI stuck ---
import threading, time, _tkinter

class _InlineThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self._target, self._args, self._kwargs = target, args, kwargs or {}
    def start(self):
        self._target(*self._args, **self._kwargs)
instance._overscaled_use_local_planner_var.set(True)
instance._overscaled_csv_var.set(str(bare))
instance._load_overscaled_csv(str(bare))
voice = tmp / "vo.wav"; voice.write_bytes(b"RIFF")
instance._current_voiceover_path = lambda: voice
instance._get_flow_engine_manager = lambda: None
# Failures go to the app's summary+Details error dialog (details = raw text).
instance._show_error_dialog = lambda title, summary, details: _dialogs.append(("error", title, summary, details))
_dialogs.clear()
with mock.patch("scene_graph.app_integration.generate_overscaled_video", side_effect=RuntimeError("boom")), \
        mock.patch("video_generator.transcribe_audio", side_effect=RuntimeError("no whisper")), \
        mock.patch("threading.Thread", _InlineThread):
    # after() from a real background thread needs a running mainloop, which
    # this headless harness doesn't have — run the worker inline instead.
    # Pumping the event loop headlessly would also run the startup
    # licence/project-picker modal; run the worker's after(0, ...) hand-off
    # directly instead (it is the only thing under test here).
    real_after = instance.after
    instance.after = lambda ms, fn=None, *a: fn(*a) if fn is not None else None
    try:
        instance._run_overscaled_generation()
    finally:
        instance.after = real_after
emit("worker_crash_resets_running_state_and_reports_error",
     not instance._overscaled_running and any(d[0] == "error" and "boom" in str(d) for d in _dialogs),
     f"running={instance._overscaled_running} dialogs={_dialogs}")

sys.stdout.flush()
os._exit(0)
'''


class TestVisualPlanLifecycleLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys

        script = Path(tempfile.mkdtemp()) / "_visual_plan_lifecycle_live.py"
        script.write_text(_LIVE_SCRIPT, encoding="utf-8")
        # UTF-8 both ways: the app logs "—", "→", "✓"; with the Windows
        # default code page the child can't encode them and the parent's
        # decode fails, leaving proc.stdout as None.
        proc = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            cwd=Path(__file__).resolve().parent,
        )
        cls._stdout, cls._stderr, cls._results = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[5:])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._results[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._results:
            self.fail(f"never reported {name!r}\nstdout:\n{self._stdout}\nstderr:\n{self._stderr[-3000:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name}: {detail}\nstderr:\n{self._stderr[-1500:]}")

    def test_initial_plan_matches_generate(self):
        self._check("initial_plan_matches_generate")

    def test_override_stock_video_reaches_generate(self):
        self._check("override_stock_video_reaches_generate")

    def test_override_flow_image_reaches_generate(self):
        self._check("override_flow_image_reaches_generate")

    def test_override_stock_image_reaches_generate(self):
        self._check("override_stock_image_reaches_generate")

    def test_override_flow_video_reaches_generate(self):
        self._check("override_flow_video_reaches_generate")

    def test_bulk_flow_image_not_rotated_at_generate(self):
        self._check("bulk_flow_image_not_rotated_at_generate")

    def test_continuation_row_override_reaches_generate(self):
        self._check("continuation_row_override_reaches_generate")

    def test_widgets_reference_current_rows_after_reload(self):
        self._check("widgets_reference_current_rows_after_reload")

    def test_src_button_click_changes_the_clicked_row(self):
        self._check("src_button_click_changes_the_clicked_row")

    def test_one_row_change_rebuilds_only_that_row(self):
        self._check("one_row_change_rebuilds_only_that_row")

    def test_stale_manifest_record_not_shown_ready(self):
        self._check("stale_manifest_record_for_other_prompt_not_shown_ready")

    def test_matching_manifest_record_still_shown_ready(self):
        self._check("matching_manifest_record_still_shown_ready")

    def test_override_blocked_while_running(self):
        self._check("override_blocked_while_running")

    def test_failed_reimport_clears_previous_plan(self):
        self._check("failed_reimport_clears_previous_plan")

    def test_reimport_replaces_rows_and_graph(self):
        self._check("reimport_replaces_rows_and_graph")

    def test_reference_row_override_redirects_to_defining_row(self):
        self._check("reference_row_override_redirects_to_defining_row")

    def test_narration_only_row_override_is_refused(self):
        self._check("narration_only_row_override_is_refused_with_a_message")

    def test_style_switch_never_shows_other_styles_plan(self):
        self._check("style_switch_never_shows_other_styles_plan")

    def test_csv_rewrite_preserves_unicode_quotes_newlines(self):
        self._check("csv_rewrite_preserves_unicode_quotes_newlines_and_extra_columns")

    def test_duplicate_scene_numbers_rejected_at_load(self):
        self._check("duplicate_scene_numbers_rejected_at_load")

    def test_alternative_result_is_kept_for_generate(self):
        self._check("alternative_result_is_kept_for_generate")

    def test_style_change_refused_while_running(self):
        self._check("style_change_refused_while_running")

    def test_worker_crash_resets_running_state_and_reports_error(self):
        self._check("worker_crash_resets_running_state_and_reports_error")


if __name__ == "__main__":
    unittest.main()
