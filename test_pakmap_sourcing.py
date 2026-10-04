"""pakMap pictures through the existing Visual Plan (Phase 8).

Each stock / Flow / YouTube reference in the script is one row of the app's Visual Plan table, resolved by the existing
asset machinery into one images folder and read back by scene number. Every provider here is a fake that writes a small
file and a manifest record: nothing is downloaded and no Flow credit is spent."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pakmap import sourcing as sc
from pakmap.compile import CompileError, compile_csv
from pakmap.schema import CsvError, parse_csv

HEAD = "item_no,vo_anchor,layer_type,layer_id,label_text,geo_ref,asset_path,anchor,params\n"
WORDS = [("Kenya", 0.5, 0.9), ("has", 0.9, 1.1), ("Nairobi", 3.0, 3.5), ("rain", 7.0, 7.4)] + [("w%d" % i, 8 + i * 0.5, 8.3 + i * 0.5) for i in range(8)]


def rows_of(text):
    return parse_csv("x.csv", text=text)[0]


class FakeManifest:
    """Stands in for asset_manager.AssetManifest: one shared dict per images folder."""
    store: dict = {}

    def __init__(self, images_dir):
        self.records = FakeManifest.store.setdefault(str(images_dir), {})

    def get(self, n):
        return self.records.get(str(n))


class FakeProviders:
    """Stands in for video_generator.resolve_scene_assets (+ the AssetManager cache) and find_image_for_scene."""

    def __init__(self, fail=(), skip=(), exit_with=None, raise_with=None):
        self.calls, self.fail, self.skip, self.exit_with, self.raise_with = [], set(fail), set(skip), exit_with, raise_with
        self.kwargs = {}

    def resolve(self, rows, images_dir, **kw):
        self.kwargs = kw
        recs = FakeManifest.store.setdefault(str(images_dir), {})
        todo = [dict(r) for r in rows if recs.get(str(r["scene_number"]), {}).get("status") != "complete"]  # the AssetManager cache
        self.calls.append(todo)
        if self.raise_with:
            raise self.raise_with
        for r in todo:
            n = str(r["scene_number"])
            if r["prompt"] in self.skip:
                recs[n] = {"status": "failed", "error": "Skipped (placeholder only)"}
            elif r["prompt"] in self.fail:
                recs[n] = {"status": "failed", "error": f"no result for {r['prompt']!r}"}
            else:
                ext = "mp4" if r["asset_type"].endswith("video") else "jpg"
                (Path(images_dir) / f"{int(n):03d}.{ext}").write_bytes(b"x" * 20)
                recs[n] = {"status": "complete", "source": r["asset_type"], "prompt": r["prompt"]}
        if self.exit_with:
            raise SystemExit(self.exit_with)

    def find(self, images_dir, scene_number):
        for f in Path(images_dir).glob(f"{int(scene_number):03d}.*"):
            return f
        return None


class Row:
    """A Visual Plan row (providers.base.SceneRow has more fields; these are the ones the fetch uses)."""

    def __init__(self, n, asset_type, prompt, script_segment=""):
        self.scene_number, self.asset_type, self.prompt, self.stock, self.script_segment = str(n), asset_type, prompt, "", script_segment


class TestParsing(unittest.TestCase):
    def test_a_source_reference_is_recognised_and_a_file_is_not(self):
        self.assertEqual(sc.parse_spec("stock_image:Nairobi skyline"), ("stock_image", "Nairobi skyline"))
        self.assertEqual(sc.parse_spec("  flow_video: aerial of the lake "), ("flow_video", "aerial of the lake"))
        for plain in ("media/city.jpg", "C:\\pics\\a.jpg", "C:/pics/a.jpg", "city.jpg", "https://x.org/a.jpg"):
            self.assertIsNone(sc.parse_spec(plain), plain)

    def test_every_use_is_its_own_numbered_row_even_when_the_text_repeats(self):
        occ = sc.find_occurrences(rows_of(HEAD + "1,Kenya,pip,a,NAIROBI,,stock_image:Nairobi  skyline,tr,\n1,Nairobi,pip,b,,,stock_image:Nairobi skyline,tl,\n1,rain,pip,c,,,flow_image:Nairobi skyline,tl,\n"))
        self.assertEqual([(o.scene_number, o.line, o.kind) for o in occ], [(1, 2, "stock_image"), (2, 3, "stock_image"), (3, 4, "flow_image")])
        self.assertEqual(occ[0].prompt, "Nairobi skyline")  # whitespace tidied
        self.assertTrue(occ[2].uses_flow and not occ[0].uses_flow)

    def test_crossfade_parts_are_numbered_and_local_files_are_not_rows(self):
        occ = sc.find_occurrences(rows_of(HEAD + '1,Kenya,pip,a,,,"stock_image:one|local/two.jpg|flow_image:three",tr,\n'))
        self.assertEqual([(o.scene_number, o.part, o.prompt) for o in occ], [(1, 0, "one"), (2, 2, "three")])
        self.assertEqual(sc.find_occurrences(rows_of(HEAD + "1,Kenya,pip,a,,,media/city.jpg,tr,\n")), [])

    def test_the_visual_plan_row_says_what_and_where(self):
        occ = sc.find_occurrences(rows_of(HEAD + "1,Nairobi,pip,a,NAIROBI,,stock_image:skyline,tr,\n1,rain,media_full,v,,,flow_video:rain,,\n"))
        rows = sc.scene_row_dicts(occ)
        self.assertEqual(rows[0], {"scene_number": "1", "script_segment": "photo card · NAIROBI — “Nairobi”", "asset_type": "stock_image", "prompt": "skyline"})
        self.assertEqual(rows[1]["script_segment"], "full-screen — “rain”")
        self.assertEqual(rows[1]["asset_type"], "flow_video")

    def test_a_misspelled_source_is_a_row_numbered_error_with_a_hint(self):
        with self.assertRaises(CsvError) as cm:
            parse_csv("x.csv", text=HEAD + "1,Kenya,pip,a,,,stok_image:Nairobi,tr,\n")
        self.assertIn("row 2", cm.exception.problems[0])
        self.assertIn("stock_image", cm.exception.problems[0])

    def test_media_for_swaps_skips_and_leaves_files_alone(self):
        row = rows_of(HEAD + '1,Kenya,pip,a,,,"stock_image:one|local.jpg|flow_image:three",tr,\n')[0]
        self.assertEqual(sc.media_for(row, {(2, 0): "/m/1.jpg", (2, 2): "/m/3.jpg"}), "/m/1.jpg|local.jpg|/m/3.jpg")
        self.assertEqual(sc.media_for(row, {(2, 0): None, (2, 2): None}), "local.jpg")
        self.assertEqual(sc.media_for(row, None), row.asset_path)
        self.assertEqual(sc.media_for(row, {(99, 0): "/x"}), row.asset_path)


class TestFetching(unittest.TestCase):
    def setUp(self):
        FakeManifest.store = {}
        self.tmp = tempfile.TemporaryDirectory()
        self.media = Path(self.tmp.name) / "media"

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, fake, rows, **kw):
        return sc.fetch_scenes(rows, self.media, resolver=fake.resolve, find_file=fake.find, manifest_cls=FakeManifest, log=lambda m: None, **kw)

    def test_each_row_is_resolved_through_the_providers_and_its_file_returned(self):
        fake = FakeProviders()
        r = self.fetch(fake, [Row(1, "stock_image", "Nairobi"), Row(2, "flow_video", "lake at dawn")])
        self.assertEqual((r.fetched, r.reused, r.missing, r.skipped), (2, 0, {}, []))
        self.assertEqual(len(fake.calls), 1)
        self.assertTrue(r.paths["1"].endswith("001.jpg") and r.paths["2"].endswith("002.mp4"))

    def test_a_second_run_reuses_what_is_saved_and_the_provider_has_nothing_to_do(self):
        rows = [Row(1, "flow_image", "a map of Kenya")]
        self.fetch(FakeProviders(), rows)
        fake = FakeProviders()
        r = self.fetch(fake, rows)
        self.assertEqual((r.fetched, r.reused), (0, 1))
        self.assertEqual(fake.calls, [[]])  # the existing cache short-circuits: no scene needed Flow

    def test_the_row_as_the_table_holds_it_is_what_the_provider_gets(self):
        # the user changed scene 1 from stock to Flow in the Visual tab: that is the row generation uses
        fake = FakeProviders()
        self.fetch(fake, [Row(1, "flow_image", "Nairobi at dusk"), Row(2, "stock_video", "rain")])
        self.assertEqual([(x["asset_type"], x["prompt"]) for x in fake.calls[0]], [("flow_image", "Nairobi at dusk"), ("stock_video", "rain")])

    def test_what_could_not_be_found_is_reported_and_the_rest_kept(self):
        fake = FakeProviders(fail={"B"})
        r = self.fetch(fake, [Row(1, "stock_image", "A"), Row(2, "stock_image", "B")])
        self.assertEqual(list(r.paths), ["1"])
        self.assertIn("no result for", r.missing["2"])
        again = FakeProviders()
        r2 = self.fetch(again, [Row(1, "stock_image", "A"), Row(2, "stock_image", "B")])
        self.assertEqual([x["prompt"] for x in again.calls[0]], ["B"])  # only the missing one is retried
        self.assertEqual(r2.reused, 1)

    def test_a_scene_the_author_skipped_is_reported_as_skipped_not_missing(self):
        r = self.fetch(FakeProviders(skip={"B"}), [Row(1, "stock_image", "A"), Row(2, "stock_image", "B")])
        self.assertEqual((list(r.paths), r.skipped, r.missing), (["1"], ["2"], {}))

    def test_a_provider_that_exits_or_raises_never_escapes_and_its_reason_is_kept(self):
        def exits(rows, images_dir, **kw):
            raise SystemExit("No Pexels API key")

        r = sc.fetch_scenes([Row(1, "stock_image", "A")], self.media, resolver=exits, find_file=lambda d, n: None, manifest_cls=FakeManifest, log=lambda m: None)
        self.assertEqual(r.missing, {"1": "No Pexels API key"})
        r = self.fetch(FakeProviders(raise_with=RuntimeError("boom")), [Row(1, "stock_image", "Z")])
        self.assertIn("boom", r.missing["1"])

    def test_provider_settings_are_passed_through_untouched(self):
        fake = FakeProviders()
        self.fetch(fake, [Row(1, "flow_image", "x")], pexels_api_key="K", flow_engine_manager="M", flow_video_account_ids=["1"])
        self.assertEqual((fake.kwargs["pexels_api_key"], fake.kwargs["flow_engine_manager"], fake.kwargs["flow_video_account_ids"]), ("K", "M", ["1"]))

    def test_every_setting_we_pass_exists_on_the_real_resolver(self):
        import inspect
        import video_generator as vg

        params = set(inspect.signature(vg.resolve_scene_assets).parameters)
        for name in ("pexels_api_key", "flow_engine_manager", "flow_settings", "flow_video_account_ids", "log", "on_scene_start", "on_scene_complete", "on_scene_generating", "on_manager_ready"):
            self.assertIn(name, params)

    def test_the_real_scene_row_converts_back_to_provider_input(self):
        from providers.base import SceneRow

        for d in ({"scene_number": "1", "script_segment": "s", "asset_type": "stock_image", "prompt": "skyline"},
                  {"scene_number": "2", "script_segment": "s", "asset_type": "flow_video", "prompt": "lake"}):
            row = SceneRow.from_csv_row(d)
            back = sc._row_dict(row)
            again = SceneRow.from_csv_row(back)
            self.assertEqual((again.asset_type, again.prompt, again.stock), (row.asset_type, row.prompt, row.stock))


class TestCompile(unittest.TestCase):
    def build(self, body, media_map=None):
        return compile_csv(text=HEAD + body, words=WORDS, validate=False, media_map=media_map)

    def test_fetched_files_replace_the_references_in_the_spec(self):
        body = ('1,Kenya,hud_title,t,PART 1,,,,\n1,Nairobi,pip,p,,Nairobi,stock_image:Nairobi skyline,tr,\n1,rain,media_full,v,,,flow_video:rain over Kenya,,\n')
        ev = {e["id"]: e for e in self.build(body, {(3, 0): "/m/001.jpg", (4, 0): "/m/002.mp4"}).spec["events"]}
        self.assertEqual((ev["p"]["media"], ev["v"]["media"]), ("/m/001.jpg", "/m/002.mp4"))

    def test_a_crossfade_and_a_filmstrip_are_substituted_too(self):
        body = ('1,Kenya,hud_title,t,PART 1,,,,\n1,Nairobi,pip,p,,Nairobi,"stock_image:a|local.jpg",tr,\n'
                '1,rain,filmstrip,f,ONE,,stock_image:c1,center,\n1,rain,filmstrip,f,TWO,,stock_image:c2,center,\n1,rain,filmstrip,f,THREE,,local3.jpg,center,\n')
        ev = {e["id"]: e for e in self.build(body, {(3, 0): "/m/a.jpg", (4, 0): "/m/c1.jpg", (5, 0): "/m/c2.jpg"}).spec["events"]}
        self.assertEqual(ev["p"]["images"], ["/m/a.jpg", "local.jpg"])
        self.assertEqual([c["media"] for c in ev["f"]["cards"]], ["/m/c1.jpg", "/m/c2.jpg", "local3.jpg"])

    def test_a_skipped_picture_leaves_its_layer_out_with_a_warning(self):
        body = '1,Kenya,hud_title,t,PART 1,,,,\n1,Nairobi,pip,p,,Nairobi,stock_image:x,tr,\n'
        res = self.build(body, {(3, 0): None})
        self.assertNotIn("p", {e["id"] for e in res.spec["events"]})
        self.assertIn("picture was skipped", " ".join(res.report.warnings))

    def test_a_plan_check_without_pictures_still_compiles_and_leaves_the_reference(self):
        spec = self.build('1,Kenya,hud_title,t,PART 1,,,,\n1,Nairobi,pip,p,,Nairobi,stock_image:Nairobi skyline,tr,\n').spec
        self.assertEqual({e["id"]: e for e in spec["events"]}["p"]["media"], "stock_image:Nairobi skyline")

    def test_a_sticker_cannot_be_fetched(self):
        with self.assertRaises(CompileError) as cm:
            self.build('1,Kenya,hud_title,t,PART 1,,,,\n1,Nairobi,sticker,s,,Nairobi,stock_image:lion,,\n')
        self.assertIn("row 3", " ".join(cm.exception.report.errors))
        self.assertIn("PNG with transparency", " ".join(cm.exception.report.errors))

    def test_local_files_are_unchanged_by_the_map(self):
        spec = self.build('1,Kenya,hud_title,t,PART 1,,,,\n1,Nairobi,pip,p,,Nairobi,media/city.jpg,tr,\n', {(99, 0): "/m/x.jpg"}).spec
        self.assertEqual({e["id"]: e for e in spec["events"]}["p"]["media"], "media/city.jpg")


CSV = ("item_no,vo_anchor,layer_type,layer_id,label_text,geo_ref,asset_path,anchor\n"
       "1,Kenya has,hud_title,t,PART 1,,,\n1,Nairobi,pip,p,NAIROBI,Nairobi,stock_image:Nairobi skyline,tr\n1,rain,media_full,v,,,flow_video:rain over Kenya,\n")


class TestGenerateRun(unittest.TestCase):
    def setUp(self):
        import wave, struct
        FakeManifest.store = {}
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "s.csv").write_text(CSV, encoding="utf-8")
        with wave.open(str(self.d / "vo.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * 8000 * 12)
        self.specs = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_gen(self, fake, **kw):
        from pakmap import app_integration as ai

        def fake_render(spec_, out, progress=None, cancel_check=None, log=print):
            self.specs.append(spec_)
            Path(out).write_bytes(b"x")
            return type("O", (), {"sidecar": {}})()

        with mock.patch("scene_graph.app_integration._export_via_existing_renderer", lambda g, s, *, voiceover_path, output_path, **k: Path(output_path).write_bytes(b"x")), \
             mock.patch("scene_graph.app_integration.validate_rendered_output", lambda *a, **k: None), \
             mock.patch.object(ai, "voiceover_duration", lambda p: 12.0), \
             mock.patch("pakmap.compile.check_with_engine", lambda s: ([], [], True)):
            return ai.generate_pakmap_video(self.d / "s.csv", self.d / "vo.wav", self.d / "out.mp4", work_dir=self.d / "w", whisper_words=WORDS, render=fake_render,
                                            media_resolver=fake.resolve, media_find_file=fake.find, media_manifest_cls=FakeManifest, sound_design=False, **kw)

    def test_the_pictures_are_fetched_into_the_images_folder_and_rendered_from_their_files(self):
        r = self.run_gen(FakeProviders(), pexels_api_key="K")
        self.assertTrue(r.ok, r.errors)
        ev = {e["id"]: e for e in self.specs[0]["events"]}
        self.assertTrue(ev["p"]["media"].endswith("001.jpg") and ev["v"]["media"].endswith("002.mp4"))
        self.assertIn(str(self.d / "w" / "media"), ev["p"]["media"])

    def test_a_replacement_made_in_the_visual_tab_is_what_gets_rendered(self):
        # scene 1 was a stock image; the user's Change source / Local clip left a complete user_override record and their own file
        media = self.d / "w" / "media"
        media.mkdir(parents=True)
        (media / "001.png").write_bytes(b"mine")
        FakeManifest.store[str(media)] = {"1": {"status": "complete", "source": "manual", "user_override": True}}
        fake = FakeProviders()
        r = self.run_gen(fake)
        self.assertTrue(r.ok, r.errors)
        self.assertEqual([x["scene_number"] for x in fake.calls[0]], ["2"])  # scene 1 was not fetched again
        ev = {e["id"]: e for e in self.specs[0]["events"]}
        self.assertTrue(ev["p"]["media"].endswith("001.png"))

    def test_the_table_as_the_user_left_it_drives_generation(self):
        fake = FakeProviders()
        rows = [Row(1, "flow_image", "Nairobi at dusk"), Row(2, "youtube_video", "Kenya rain")]
        r = self.run_gen(fake, scene_rows=rows)
        self.assertTrue(r.ok, r.errors)
        self.assertEqual([(x["asset_type"], x["prompt"]) for x in fake.calls[0]], [("flow_image", "Nairobi at dusk"), ("youtube_video", "Kenya rain")])

    def test_a_second_generate_does_not_fetch_again(self):
        self.run_gen(FakeProviders())
        fake = FakeProviders()
        self.assertTrue(self.run_gen(fake).ok)
        self.assertEqual(fake.calls, [[]])

    def test_a_missing_picture_stops_before_rendering_and_points_at_the_visual_tab(self):
        r = self.run_gen(FakeProviders(fail={"rain over Kenya"}))
        self.assertFalse(r.ok)
        self.assertEqual(r.unresolved, ["2"])
        self.assertIn("Picture 2", r.errors[0])
        self.assertIn("full-screen", r.errors[0])
        self.assertIn("Visual Plan", r.errors[-1])
        self.assertEqual(self.specs, [])  # nothing was drawn

    def test_a_skipped_picture_drops_that_layer_and_the_video_still_renders(self):
        r = self.run_gen(FakeProviders(skip={"rain over Kenya"}))
        self.assertTrue(r.ok, r.errors)
        self.assertNotIn("v", {e["id"] for e in self.specs[0]["events"]})
        self.assertTrue(any("picture was skipped" in w for w in r.warnings))

    def test_a_script_with_only_local_pictures_never_touches_the_providers(self):
        (self.d / "s.csv").write_text(CSV.replace("stock_image:Nairobi skyline", "a.jpg").replace("flow_video:rain over Kenya", "b.mp4"), encoding="utf-8")
        fake = FakeProviders()
        self.assertTrue(self.run_gen(fake).ok)
        self.assertEqual(fake.calls, [])

    def test_the_plan_check_and_the_table_rows(self):
        from pakmap import app_integration as ai

        self.assertEqual([d["asset_type"] for d in ai.visual_plan_dicts(self.d / "s.csv")], ["stock_image", "flow_video"])
        before = ai.describe_sourced(self.d / "s.csv", self.d / "w" / "media")
        self.assertIn("will be fetched", before[0])
        self.assertIn("GENERATED with Flow", before[1])
        self.assertIn("Visual Plan tab", before[0])
        self.run_gen(FakeProviders())
        import asset_manager
        with mock.patch.object(asset_manager, "AssetManifest", FakeManifest):
            self.assertTrue(all("already saved" in l for l in ai.describe_sourced(self.d / "s.csv", self.d / "w" / "media")))

    def test_row_times_come_from_the_compiled_plan(self):
        from pakmap import app_integration as ai

        res, rep, problems = ai.check_pakmap_plan(self.d / "s.csv", WORDS, duration=12.0, base_dir=self.d)
        self.assertEqual(problems, [])
        t = ai.row_times(rep)
        self.assertAlmostEqual(t[3], 3.0, delta=0.2)  # the "Nairobi" pip


class TestRealAssetManager(unittest.TestCase):
    """The real asset machinery (no network): what the Visual tab writes is what pakMap reads."""

    def test_a_replacement_saved_by_the_visual_tab_is_used_without_any_provider(self):
        from asset_manager import AssetManifest
        from providers.base import SceneRow

        with tempfile.TemporaryDirectory() as d:
            media = Path(d) / "media"
            media.mkdir()
            mine = media / "001.png"
            mine.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
            AssetManifest(media).set("1", {"status": "complete", "source": "manual", "local_path": str(mine), "user_override": True})
            # scene 1 is still "stock_image: Nairobi skyline" in the script; no Pexels key, no network, no Flow
            r = sc.fetch_scenes([SceneRow.from_csv_row({"scene_number": "1", "asset_type": "stock_image", "prompt": "Nairobi skyline"})], media, log=lambda m: None)
            self.assertEqual(r.missing, {})
            self.assertTrue(r.paths["1"].endswith("001.png"))
            self.assertEqual(r.reused, 1)


class TestEndToEndWithTheRealAssetMachinery(unittest.TestCase):
    """generate_pakmap_video with the REAL fetch (AssetManager, manifest, find_image_for_scene), a fake renderer and no network."""

    def test_a_replacement_made_in_the_visual_tab_reaches_the_render(self):
        import struct, wave
        from asset_manager import AssetManifest
        from pakmap import app_integration as ai

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "s.csv").write_text(CSV.replace("1,rain,media_full,v,,,flow_video:rain over Kenya,\n", ""), encoding="utf-8")
            with wave.open(str(d / "vo.wav"), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * 8000 * 12)
            media = d / "w" / "media"
            media.mkdir(parents=True)
            mine = media / "001.png"
            mine.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
            AssetManifest(media).set("1", {"status": "complete", "source": "manual", "user_override": True, "local_path": str(mine)})
            specs = []

            def fake_render(spec_, out, progress=None, cancel_check=None, log=print):
                specs.append(spec_)
                Path(out).write_bytes(b"x")
                return type("O", (), {"sidecar": {}})()

            with mock.patch("scene_graph.app_integration._export_via_existing_renderer", lambda g, s, *, voiceover_path, output_path, **k: Path(output_path).write_bytes(b"x")), \
                 mock.patch("scene_graph.app_integration.validate_rendered_output", lambda *a, **k: None), \
                 mock.patch.object(ai, "voiceover_duration", lambda p: 12.0), mock.patch("pakmap.compile.check_with_engine", lambda s: ([], [], True)):
                r = ai.generate_pakmap_video(d / "s.csv", d / "vo.wav", d / "out.mp4", work_dir=d / "w", whisper_words=WORDS, render=fake_render, sound_design=False)
            self.assertTrue(r.ok, r.errors)
            self.assertEqual({e["id"]: e for e in specs[0]["events"]}["p"]["media"], str(mine))  # no provider was contacted: none is configured


class TestVisualTabActionsReachTheRender(unittest.TestCase):
    """The Visual tab's own actions (Change source, Local clip, Retry) are the real AssetManager's; whatever they leave in the
    pakMap images folder is what pakMap renders. Providers are stubs that write a small file: no network, no Flow."""

    def setUp(self):
        from providers.base import AssetProvider, AssetResult, AssetSource, MediaType, SceneStatus

        outer = self

        class Stub(AssetProvider):
            def __init__(self, source, ext, media, name, fail_first=False):
                self.source, self.ext, self.media, self.name, self.fail_first, self.calls = source, ext, media, name, fail_first, 0
                self.should_stop_scene = None

            def resolve(self, scene, images_dir, log=print):
                self.calls += 1
                if self.fail_first and self.calls == 1:
                    return AssetResult(scene.scene_number, None, None, self.source, SceneStatus.FAILED, error="the provider found nothing")
                path = Path(images_dir) / f"{int(scene.scene_number):03d}.{self.ext}"
                for old in Path(images_dir).glob(f"{int(scene.scene_number):03d}.*"):
                    old.unlink()
                path.write_bytes(b"\x89PNG\r\n\x1a\n" + self.name.encode() + b"x" * 40)
                return AssetResult(scene.scene_number, path, self.media, self.source, SceneStatus.READY)

        from asset_manager import AssetManager

        self.tmp = tempfile.TemporaryDirectory()
        self.media = Path(self.tmp.name) / "media"
        self.stock = Stub(AssetSource.STOCK_IMAGE, "jpg", MediaType.IMAGE, "stock")
        self.flow = Stub(AssetSource.FLOW_IMAGE, "png", MediaType.IMAGE, "flow")
        self.yt = Stub(AssetSource.YOUTUBE_VIDEO, "mp4", MediaType.VIDEO, "youtube")
        self.mgr = AssetManager(self.media, stock_provider=self.stock, flow_image_provider=self.flow, youtube_provider=self.yt, log=lambda m: None)
        from providers.base import SceneRow
        self.row = SceneRow.from_csv_row({"scene_number": "1", "script_segment": "photo card · NAIROBI", "asset_type": "stock_image", "prompt": "Nairobi skyline"})

    def tearDown(self):
        self.tmp.cleanup()

    def rendered_path(self):
        """What the next pakMap generate would use for scene 1 (real fetch, no provider configured: only the cache can answer)."""
        r = sc.fetch_scenes([self.row], self.media, log=lambda m: None)
        self.assertEqual(r.missing, {})
        return Path(r.paths["1"])

    def test_the_first_fetch_is_the_stock_picture(self):
        self.mgr.resolve_all([self.row])
        self.assertEqual(self.rendered_path().suffix, ".jpg")

    def test_changing_source_to_flow_youtube_or_local_replaces_what_is_rendered(self):
        self.mgr.resolve_all([self.row])
        self.mgr.change_source(self.row, "flow_image")
        self.assertEqual(self.rendered_path().suffix, ".png")
        self.assertIn(b"flow", self.rendered_path().read_bytes())
        self.mgr.change_source(self.row, "youtube")
        self.assertEqual(self.rendered_path().suffix, ".mp4")
        mine = Path(self.tmp.name) / "mine.png"
        mine.write_bytes(b"\x89PNG\r\n\x1a\n" + b"local" + b"x" * 40)
        self.mgr.attach_manual_clip(self.row, mine)
        self.assertIn(b"local", self.rendered_path().read_bytes())

    def test_a_replacement_is_not_undone_by_generating_again(self):
        self.mgr.resolve_all([self.row])
        self.mgr.change_source(self.row, "flow_image")
        flow_calls = self.flow.calls
        before = self.rendered_path()
        again = sc.fetch_scenes([self.row], self.media, log=lambda m: None)  # the script still says stock_image
        self.assertEqual(Path(again.paths["1"]), before)
        self.assertEqual((self.stock.calls, self.flow.calls), (1, flow_calls))  # nothing was fetched again

    def test_a_failed_picture_can_be_retried_and_then_renders(self):
        self.stock.fail_first = True
        first = self.mgr.resolve_all([self.row])
        self.assertFalse(first.results[self.row.scene_number].ok)
        failed = sc.fetch_scenes([self.row], self.media, log=lambda m: None)
        self.assertIn("1", failed.missing)  # it is reported, not rendered
        self.mgr.retry_scene(self.row)
        self.assertEqual(self.rendered_path().suffix, ".jpg")


class TestFriendlyProblems(unittest.TestCase):
    def test_a_problem_names_the_layer_it_is_about_and_unknown_messages_pass_through(self):
        from pakmap import app_integration as ai

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.csv"
            p.write_text(HEAD + "1,Kenya,hud_title,t,PART 1,,,,\n1,Nairobi,marker,m,NAIROBI,Nairobi,,,\n", encoding="utf-8")
            out = ai.friendly_problems(p, ["row 3: can't find 'Nairobi' in the narration", "renderer rule: row 2: too many text layers", "something else", "row 99: nope"])
            self.assertEqual(out[0], "Row 3 (marker NAIROBI): can't find 'Nairobi' in the narration")
            self.assertEqual(out[1], "Row 2 (hud_title PART 1): too many text layers")
            self.assertEqual(out[2:], ["something else", "row 99: nope"])


if __name__ == "__main__":
    unittest.main()
