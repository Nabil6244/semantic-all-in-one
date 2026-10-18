"""Local CSV Generator: schemas, validation, learning isolation, offline guarantees, scale, cancellation."""
import csv
import io
import re
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from csv_generator import GenerationOptions, SUPPORTED_STYLES, UNSUPPORTED_STYLES, generate, to_csv_text, validate_rows
from csv_generator.engine import COLUMNS, group_narrations
from learning import packages as pk
from providers.base import SceneRow

ROOT = Path(__file__).resolve().parent
BASE = ("The Aurora Bridge was built in 1932 and carried thousands of cars every day. Engineers imagined a future of freedom and speed. "
        "But the river was far too strong for the old design. Last night a rocket passed the moon on its way to Mars. "
        "Crews ran across the deck as the steel began to fall. ")


def rule(i, kind="note", text="Advice.", **kw):
    return {"id": i, "kind": kind, "text": text, "confidence": 0.8, "evidence_count": 12, "status": "approved", **kw}


class SchemaTests(unittest.TestCase):
    def test_every_supported_style_matches_its_real_parsers(self):
        for style in SUPPORTED_STYLES:
            r = generate(BASE * 6, style)
            self.assertTrue(r.ok, (style, [str(i) for i in r.issues]))
            self.assertEqual(tuple(r.columns), COLUMNS)
            parsed = list(csv.DictReader(io.StringIO(r.csv_text)))
            self.assertEqual(len(parsed), len(r.rows))
            self.assertEqual(list(parsed[0].keys()), list(COLUMNS))
            for row in parsed:
                sr = SceneRow.from_csv_row(row)                # the renderer-side parser accepts every row
                self.assertTrue(sr.script_segment and sr.asset_type)
        from scene_graph.overscaled_csv import compile_overscaled_csv
        from scene_graph.exp_solar_csv import validate_exp_solar_csv
        rows = generate(BASE * 6, "overscaled").rows
        self.assertEqual(compile_overscaled_csv(rows, segment_id="t").errors, [])
        self.assertEqual(validate_exp_solar_csv(generate(BASE * 6, "exp_solar").rows), [])

    def test_default_plan_uses_only_free_enabled_types(self):
        r = generate(BASE * 10, "normal")
        self.assertTrue({x["asset_type"] for x in r.rows} <= {"stock_video", "stock_image"})
        r2 = generate(BASE * 10, "normal", GenerationOptions(enabled_types=("stock_video", "stock_image", "image", "video", "nasa_video", "archive_video")))
        kinds = {x["asset_type"] for x in r2.rows}
        self.assertIn("nasa_video", kinds)                 # 'rocket ... moon ... Mars'
        self.assertIn("archive_video", kinds)              # '1932'
        self.assertTrue(r2.ok)

    def test_unsupported_and_unknown_styles_say_why(self):
        for s, why in UNSUPPORTED_STYLES.items():
            r = generate(BASE, s)
            self.assertFalse(r.ok)
            self.assertEqual(r.rows, [])
            self.assertIn(why, str(r.issues[0]))
        self.assertFalse(generate(BASE, "nope").ok)
        self.assertFalse(generate("   ", "normal").ok)


class ValidationTests(unittest.TestCase):
    def check(self, rows, **kw):
        return [str(i) for i in validate_rows(rows, columns=COLUMNS, style="normal", **kw)]

    def row(self, n=1, seg="Hello world.", at="stock_video", pr="hello"):
        return {"scene_number": str(n), "script_segment": seg, "asset_type": at, "prompt": pr}

    def test_problems_are_caught(self):
        self.assertTrue(self.check([]))
        self.assertTrue(any("Empty narration" in m for m in self.check([self.row(seg=" ")])))
        self.assertTrue(any("not one the renderer understands" in m for m in self.check([self.row(at="hologram")])))
        self.assertTrue(any("needs a prompt" in m for m in self.check([self.row(pr="")])))
        self.assertTrue(any("run 1..n" in m for m in self.check([self.row(1), self.row(3)])))
        self.assertTrue(any("not enabled" in m for m in self.check([self.row(at="image")], allowed_asset_types=["stock_video"])))
        self.assertTrue(any("do not reproduce the script" in m for m in self.check([self.row(seg="Different words")], script="Hello world.")))
        self.assertEqual([m for m in self.check([self.row()], script="Hello world.") if "[error]" in m], [])
        bad_cols = validate_rows([self.row()], columns=("scene_number",), style="normal")
        self.assertTrue(bad_cols)

    def test_bad_exp_solar_beat_is_reported_by_the_real_parser(self):
        rows = [dict(self.row(), beat="not_a_beat")]
        out = validate_rows(rows, columns=COLUMNS + ("beat",), style="exp_solar")
        self.assertTrue(any("beat" in str(i) for i in out))


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_empty_learning_data_works(self):
        r = generate(BASE * 8, "normal", scope="normal/history", knowledge_root=self.root)
        self.assertTrue(r.ok)
        self.assertEqual(r.applied_knowledge, [])

    def test_approved_rules_of_the_same_scope_change_the_plan(self):
        pk.install(pk.build_package("normal/history", [rule("fail-stock_video", "asset_type_failure", asset_type="stock_video"),
                                                       rule("tag-repetitive_scenes")], version=1), root=self.root)
        opts = GenerationOptions(enabled_types=("stock_video", "stock_image"))
        plain = generate(BASE * 20, "normal", opts)
        tuned = generate(BASE * 20, "normal", opts, scope="normal/history", knowledge_root=self.root)
        self.assertIn("stock_video", {x["asset_type"] for x in plain.rows})
        self.assertNotIn("stock_video", {x["asset_type"] for x in tuned.rows})
        self.assertEqual(len(tuned.applied_knowledge), 2)
        self.assertTrue(tuned.ok)

    def test_other_styles_rules_are_never_applied(self):
        pk.install(pk.build_package("weather/classic", [rule("fail-stock_video", "asset_type_failure", asset_type="stock_video")], version=1), root=self.root)
        pk.install(pk.build_package("normal/news", [rule("fail-stock_video", "asset_type_failure", asset_type="stock_video")], version=1), root=self.root)
        r = generate(BASE * 20, "normal", scope="normal/history", knowledge_root=self.root)
        self.assertEqual(r.applied_knowledge, [])
        self.assertIn("stock_video", {x["asset_type"] for x in r.rows})
        self.assertEqual(generate(BASE * 20, "normal", scope="normal/news", knowledge_root=self.root).applied_knowledge, ["fail-stock_video: avoid stock_video"])

    def test_candidates_and_invalid_packages_never_influence_output(self):
        cand = pk.build_package("normal/history", [rule("fail-stock_video", "asset_type_failure", asset_type="stock_video")], version=1)
        cand["rules"][0]["status"] = "candidate"                 # not approved (and hash no longer matches)
        self.assertFalse(pk.install(cand, root=self.root).ok)
        r = generate(BASE * 20, "normal", scope="normal/history", knowledge_root=self.root)
        self.assertEqual(r.applied_knowledge, [])

    def test_broken_knowledge_store_falls_back_to_plain_plan(self):
        with mock.patch("learning.packages.active_package", side_effect=RuntimeError("db")):
            r = generate(BASE * 4, "normal", scope="normal/history")
        self.assertTrue(r.ok)


class OfflineAndScaleTests(unittest.TestCase):
    def test_no_network_and_no_api_imports(self):
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network used")), \
                mock.patch("socket.getaddrinfo", side_effect=AssertionError("network used")):
            self.assertTrue(generate(BASE * 5, "normal").ok)
        for f in (ROOT / "csv_generator").glob("*.py"):
            src = f.read_text(encoding="utf-8")
            for w in ("requests", "urllib", "http.client", "socket", "genai", "openai", "anthropic", "supabase"):
                self.assertNotRegex(src, rf"^\s*(import|from)\s+{re.escape(w)}\b", f"{f.name}: {w}")

    def test_large_script_is_not_capped_and_keeps_every_word(self):
        script = " ".join(f"Sentence number {i} describes the river valley and its old bridge." for i in range(4000))   # ~40k words
        t0 = time.time()
        r = generate(script, "normal")
        self.assertLess(time.time() - t0, 30)
        self.assertGreater(len(r.rows), 600)
        self.assertTrue(r.ok, [str(i) for i in r.issues][:3])
        self.assertEqual(" ".join(x["script_segment"] for x in r.rows).split(), script.split())

    def test_single_giant_sentence_is_split_and_lossless(self):
        s = " and ".join(["the river rose, the bridge shook"] * 300) + "."
        parts = group_narrations(s, 45, 80)
        self.assertGreater(len(parts), 5)
        self.assertEqual(" ".join(parts).split(), s.split())

    def test_cancellation_returns_cleanly_and_repeat_generation_is_identical(self):
        ev = threading.Event()
        calls = []

        def prog(f, m):
            calls.append(m)
            if len(calls) >= 3:
                ev.set()
        r = generate(BASE * 400, "normal", cancel=ev, progress=prog)
        self.assertTrue(r.cancelled)
        self.assertFalse(r.ok)
        self.assertEqual(r.rows, [])
        a, b = generate(BASE * 6, "normal"), generate(BASE * 6, "normal")
        self.assertEqual(a.csv_text, b.csv_text)

    def test_generation_writes_no_files(self):
        with mock.patch("pathlib.Path.write_text", side_effect=AssertionError("wrote")), \
                mock.patch("pathlib.Path.mkdir", side_effect=AssertionError("mkdir")):
            self.assertTrue(generate(BASE * 3, "exp_solar").ok)

    def test_csv_text_roundtrip_quotes_commas_and_newlines(self):
        rows = [{"scene_number": "1", "script_segment": 'He said, "go".\nNext line', "asset_type": "stock_video", "prompt": "a, b"}]
        back = list(csv.DictReader(io.StringIO(to_csv_text(COLUMNS, rows))))
        self.assertEqual(back[0]["script_segment"], rows[0]["script_segment"])


class UiAndWiringTests(unittest.TestCase):
    def test_menu_and_module_wiring(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('label="CSV Generator…"', src)
        self.assertIn("from csv_generator.ui import open_generator", src)

    def test_window_generates_through_the_worker_thread_and_leaves_the_project_alone(self):
        try:
            import customtkinter as ctk
            root = ctk.CTk()
            root.geometry("200x80+30+30")
        except Exception as exc:
            raise unittest.SkipTest(f"no display: {exc}")
        self.addCleanup(root.destroy)
        from csv_generator import ui
        root._main_script_text = lambda: BASE * 3
        root._workspace = None
        root.generation_mode = "normal"
        root._settings = {}
        ui.open_generator(root)
        win = next(w for w in root.winfo_children() if w.winfo_class() == "Toplevel")

        def walk(w):
            yield w
            for c in w.winfo_children():
                yield from walk(c)
        widgets = list(walk(win))
        gen = next(w for w in widgets if isinstance(w, ctk.CTkButton) and w.cget("text") == "Generate")
        use = next(w for w in widgets if isinstance(w, ctk.CTkButton) and w.cget("text") == "Use in this project")
        boxes = [w for w in widgets if isinstance(w, ctk.CTkTextbox)]
        self.assertEqual(str(use.cget("state")), "disabled")                      # nothing to use before generating
        gen.invoke()
        end = time.time() + 10
        while time.time() < end and "scene_number" not in boxes[-1].get("1.0", "end"):
            root.update()
            time.sleep(0.02)
        self.assertIn("scene_number,script_segment,asset_type,prompt", boxes[-1].get("1.0", "end"))
        self.assertEqual(str(use.cget("state")), "normal")                        # valid plan -> explicit user step available
        win.destroy()


if __name__ == "__main__":
    unittest.main()
