"""Phase 2 local learning ledger: storage, scope, imports, render outcomes, ratings, fail-open, privacy."""
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from learning import events as ev
from learning import ledger as lg
from learning.scope import build_scope, resolve_scope

ROOT = Path(__file__).resolve().parent


class FakeWs:
    project_id = "proj-1"

    def __init__(self, meta=None):
        self.meta = meta or {}

    def read_meta(self):
        return self.meta


def fake_app(mode="normal", meta=None, **kw):
    return SimpleNamespace(generation_mode=mode, _workspace=FakeWs(meta), **kw)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.led = lg.Ledger(Path(self.tmp.name) / "learning.sqlite")

    def csv(self, name, text):
        p = Path(self.tmp.name) / name
        p.write_bytes(text.encode("utf-8"))
        return p


class StorageTests(Base):
    def test_create_reopen_schema_and_local_only(self):
        self.assertTrue(ev.record_event("t", style_scope="normal/x", ledger=self.led))
        again = lg.Ledger(self.led.path)
        self.assertEqual(again.schema_version(), lg.SCHEMA_VERSION)
        rows = again.events()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sync_state"], "local_only")

    def test_default_path_is_store_dir(self):
        with mock.patch("licensing.session_store.store_dir", return_value=Path(self.tmp.name)):
            self.assertEqual(lg.default_db_path(), Path(self.tmp.name) / "learning.sqlite")

    def test_concurrent_inserts(self):
        def work(i):
            for j in range(10):
                ev.record_event("t", style_scope="normal/x", event_id=f"{i}-{j}", ledger=self.led)
        threads = [threading.Thread(target=work, args=(i,)) for i in range(6)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(self.led.events(limit=1000)), 60)

    def test_same_event_id_is_not_duplicated(self):
        self.assertTrue(ev.record_event("t", style_scope="a/b", event_id="e1", ledger=self.led))
        self.assertFalse(ev.record_event("t", style_scope="a/b", event_id="e1", ledger=self.led))

    def test_payload_scrubbed_and_bounded(self):
        ev.record_event("t", style_scope="a/b", ledger=self.led,
                        payload={"api_key": "x", "file_path": "/u/me", "prompt": "p", "narration": "n", "ok": 1})
        self.assertEqual(self.led.events()[0]["payload"], {"ok": 1})
        ev.record_event("t", style_scope="a/b", ledger=self.led, payload={"big": "x" * 20000})
        self.assertEqual(self.led.events(newest_first=True)[0]["payload"], {"truncated": True})


class ScopeTests(unittest.TestCase):
    def test_modes_and_presets_are_distinct_and_stable(self):
        scopes = {
            resolve_scope(fake_app("normal", {"video_style": {"style_id": "history"}})),
            resolve_scope(fake_app("normal", {"video_style": {"style_id": "news"}})),
            resolve_scope(fake_app("normal", {"video_style": {"style_id": "news"}, "editing_system": "modern_tech"})),
            resolve_scope(fake_app("overscaled", _overscaled_style_preset_id="overscaled")),
            resolve_scope(fake_app("overscaled", _overscaled_style_preset_id="exp_solar")),
            resolve_scope(fake_app("pakmap")), resolve_scope(fake_app("hybrid")), resolve_scope(fake_app("starmap")),
            resolve_scope(fake_app("whatif")), resolve_scope(fake_app("normal")),
        }
        self.assertEqual(len(scopes), 10)
        a = fake_app("normal", {"video_style": {"style_id": "history"}})
        self.assertEqual(resolve_scope(a), resolve_scope(a))
        self.assertEqual(resolve_scope(a), "normal/history")
        self.assertEqual(resolve_scope(fake_app("normal")), "normal/default")

    def test_mode_override_wins_and_never_raises(self):
        self.assertEqual(resolve_scope(fake_app("normal"), "pakmap"), "pakmap/default")
        self.assertEqual(resolve_scope(None, "hybrid"), "hybrid/default")
        self.assertEqual(build_scope("Weird Mode!", "A/B"), "weird_mode/a_b")


class ImportTests(Base):
    def test_raw_vs_final_hash_and_structure(self):
        text = "scene_number,script_segment,asset_type,prompt\n1,hello,video,x\n2,bye,image,y\n"
        src = self.csv("src.csv", text)
        final = self.csv("final.csv", text.replace("video", "image"))
        before = src.read_bytes()
        self.assertTrue(ev.note_import(fake_app(), "normal", path=src, final_path=final, ledger=self.led))
        row = self.led.events(event_type="csv_import")[0]
        self.assertEqual(row["csv_sha256"], ev.sha256_bytes(before))
        self.assertNotEqual(row["payload"]["final_csv_sha256"], row["csv_sha256"])
        self.assertEqual(row["payload"]["rows"], 2)
        self.assertEqual(row["payload"]["asset_types"], {"video": 1, "image": 1})
        self.assertNotIn("hello", str(row))            # no narration stored
        self.assertEqual(src.read_bytes(), before)      # file untouched
        self.assertEqual(row["project_id"], "proj-1")

    def test_pasted_text_hashes_exact_text(self):
        text = "scene_number,script_segment\r\n1,a\r\n"
        ev.note_import(fake_app(), "normal", text=text, ledger=self.led)
        self.assertEqual(self.led.events()[0]["csv_sha256"], ev.sha256_bytes(text.encode()))

    def test_reimport_new_row_but_redelivery_deduped(self):
        src = self.csv("a.csv", "scene_number,script_segment\n1,a\n")
        app = fake_app()
        ev.note_import(app, "normal", path=src, ledger=self.led)
        ev.note_import(app, "normal", path=src, ledger=self.led)                     # deliberate re-import
        ev.note_import(app, "normal", path=src, op_id="same", ledger=self.led)
        ev.note_import(app, "normal", path=src, op_id="same", ledger=self.led)       # duplicate callback
        self.assertEqual(len(self.led.events(event_type="csv_import")), 3)

    def test_changed_content_has_new_hash_and_missing_file_still_records(self):
        app = fake_app()
        ev.note_import(app, "normal", path=self.csv("a.csv", "scene_number\n1\n"), ledger=self.led)
        ev.note_import(app, "normal", path=self.csv("a.csv", "scene_number\n1\n2\n"), ledger=self.led)
        a, b = [r["csv_sha256"] for r in self.led.events()]
        self.assertNotEqual(a, b)
        self.assertTrue(ev.note_import(app, "normal", path=Path(self.tmp.name) / "gone.csv", ledger=self.led))
        self.assertIsNone(self.led.events(newest_first=True)[0]["csv_sha256"])

    def test_every_style_is_recorded_in_its_own_scope(self):
        src = self.csv("a.csv", "scene_number\n1\n")
        for mode in ("normal", "overscaled", "pakmap", "hybrid", "starmap", "whatif", "weather"):
            ev.note_import(fake_app(mode), mode, path=src, ledger=self.led)
        scopes = [r["style_scope"] for r in self.led.events()]
        self.assertEqual(len(set(scopes)), 7)

    def test_hooks_exist_at_user_import_points_only(self):
        app_src = (ROOT / "app.py").read_text(encoding="utf-8")
        for mode in ("normal", "overscaled", "pakmap", "hybrid", "starmap"):
            self.assertIn(f'_lrn(self, "{mode}"', app_src)
        self.assertIn('_lrn(app, "whatif"', (ROOT / "whatif/app_section.py").read_text(encoding="utf-8"))
        self.assertIn('_lrn(app, "weather"', (ROOT / "weather/app_section.py").read_text(encoding="utf-8"))
        # reopen paths must not record
        start = app_src.index("def _bind_workspace_paths")
        end = app_src.index("\n    def ", start + 10)
        self.assertNotIn("_lrn(", app_src[start:end])
        start = app_src.index("def _load_overscaled_csv")
        self.assertNotIn("_lrn(", app_src[start:app_src.index("\n    def ", start + 10)])
        start = app_src.index("def _load_pakmap_csv")
        self.assertNotIn("_lrn(", app_src[start:app_src.index("\n    def ", start + 10)])


class RenderTests(Base):
    def run_(self, gid="g1", engine="normal"):
        return SimpleNamespace(generation_id=gid, project_id="proj-1", render_engine=engine)

    def test_outcomes_and_csv_link(self):
        app = fake_app()
        ev.note_import(app, "normal", path=self.csv("a.csv", "scene_number\n1\n"), ledger=self.led)
        for gid, out in (("g1", "completed"), ("g2", "failed"), ("g3", "cancelled")):
            self.assertTrue(ev.note_render_outcome(app, self.run_(gid), out, "ffmpeg", "secret /Users/me/x", ledger=self.led))
        rows = {r["generation_id"]: r for r in self.led.events(event_type="render_outcome")}
        self.assertEqual([rows[g]["payload"]["outcome"] for g in ("g1", "g2", "g3")], ["success", "failure", "cancelled"])
        self.assertEqual(rows["g2"]["payload"]["failure_category"], "ffmpeg")
        self.assertNotIn("failure_category", rows["g1"]["payload"])
        self.assertTrue(rows["g1"]["csv_sha256"])
        self.assertNotIn("secret", str(rows))

    def test_duplicate_terminal_callback_ignored_new_render_recorded(self):
        app = fake_app()
        self.assertTrue(ev.note_render_outcome(app, self.run_("g1"), "failed", ledger=self.led))
        self.assertFalse(ev.note_render_outcome(app, self.run_("g1"), "completed", ledger=self.led))
        self.assertTrue(ev.note_render_outcome(app, self.run_("g2"), "completed", ledger=self.led))
        self.assertEqual([r["payload"]["outcome"] for r in self.led.events(event_type="render_outcome")], ["failure", "success"])

    def test_nothing_invented(self):
        app = fake_app()
        self.assertFalse(ev.note_render_outcome(app, None, "completed", ledger=self.led))
        self.assertFalse(ev.note_render_outcome(app, self.run_(), "running", ledger=self.led))
        self.assertEqual(self.led.events(), [])

    def test_unknown_category_is_sanitized_and_scope_follows_engine(self):
        ev.note_render_outcome(fake_app("overscaled", _overscaled_style_preset_id="exp_solar"),
                               self.run_("g9", "overscaled"), "failed", "weird", ledger=self.led)
        r = self.led.events()[0]
        self.assertEqual(r["payload"]["failure_category"], "unknown")
        self.assertEqual(r["style_scope"], "overscaled/exp_solar")


class RatingTests(Base):
    def rate(self, rating=4, **kw):
        kw.setdefault("generation_id", "g1")
        return ev.record_video_rating("proj-1", "normal/history", rating, ledger=self.led, **kw)

    def test_valid_minimal_and_full(self):
        r = self.rate(5)
        self.assertEqual((r.ok, r.status, r.revision), (True, "recorded", 1))
        r2 = ev.record_video_rating("proj-1", "normal/history", 3, generation_id="g2", ledger=self.led,
                                    categories={"pacing": 2, "visual_relevance": 5}, tags=["Wrong_Visuals", "wrong_visuals", "nope"],
                                    comment="  too slow  ")
        self.assertTrue(r2.ok)
        p = self.led.latest(event_type="video_rating", generation_id="g2")["payload"]
        self.assertEqual(p["tags"], ["wrong_visuals"])
        self.assertEqual(p["categories"], {"pacing": 2, "visual_relevance": 5})
        self.assertEqual(p["comment"], "too slow")

    def test_invalid_inputs_write_nothing(self):
        for bad in (0, 6, "5", None, True, 2.5):
            self.assertEqual(self.rate(bad).status, "invalid")
        self.assertEqual(self.rate(3, categories={"pacing": 9}).status, "invalid")
        self.assertEqual(self.rate(3, categories={"bogus": 3}).status, "invalid")
        self.assertEqual(ev.record_video_rating("", "x", 3, ledger=self.led).status, "invalid")
        self.assertEqual(self.led.events(), [])

    def test_comment_bounded(self):
        self.rate(3, comment="x" * 5000)
        self.assertEqual(len(self.led.events()[0]["payload"]["comment"]), ev.MAX_COMMENT_CHARS)

    def test_repeat_is_unchanged_and_revision_is_appended(self):
        a = self.rate(4)
        self.assertEqual(self.rate(4).status, "unchanged")
        b = self.rate(2, tags=["poor_pacing"])
        self.assertEqual((b.status, b.revision), ("revised", 2))
        rows = self.led.events(event_type="video_rating")
        self.assertEqual(len(rows), 2)                                   # nothing lost
        self.assertEqual(rows[1]["payload"]["supersedes"], a.event_id)
        self.assertEqual(rows[0]["payload"]["rating"], 4)

    def test_other_render_and_other_style_are_independent(self):
        self.rate(4)
        self.assertEqual(self.rate(4, generation_id="g2").revision, 1)
        other = ev.record_video_rating("proj-1", "pakmap/default", 1, generation_id="g1", ledger=self.led)
        self.assertEqual(other.revision, 1)
        self.assertEqual(len(self.led.events(style_scope="normal/history")), 2)
        self.assertEqual(len(self.led.events(style_scope="pakmap/default")), 1)

    def test_project_level_rating_without_generation(self):
        r = ev.record_video_rating("proj-1", "normal/history", 4, ledger=self.led)
        self.assertEqual(ev.record_video_rating("proj-1", "normal/history", 4, ledger=self.led).status, "unchanged")
        self.assertTrue(r.ok)


class FailOpenAndPrivacyTests(Base):
    def test_broken_ledger_never_raises(self):
        bad = lg.Ledger(Path(self.tmp.name))                # a directory, not a file
        self.assertFalse(ev.record_event("t", style_scope="a/b", ledger=bad))
        self.assertFalse(ev.note_import(fake_app(), "normal", text="a\n", ledger=bad))
        self.assertFalse(ev.note_render_outcome(fake_app(), SimpleNamespace(generation_id="g", project_id="p", render_engine="normal"),
                                                "completed", ledger=bad))
        self.assertEqual(ev.record_video_rating("p", "s", 3, ledger=bad).status, "error")

    def test_app_hook_swallows_ledger_errors(self):
        with mock.patch("learning.events.record_event", side_effect=RuntimeError("boom")):
            self.assertFalse(ev.note_import(fake_app(), "normal", text="a\n", ledger=self.led))

    def test_no_network(self):
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network used")), \
                mock.patch("socket.getaddrinfo", side_effect=AssertionError("network used")):
            ev.note_import(fake_app(), "normal", text="scene_number\n1\n", ledger=self.led)
            ev.record_video_rating("p", "s", 3, ledger=self.led)
        self.assertEqual(len(self.led.events()), 2)
        src = "".join((ROOT / "learning" / f).read_text(encoding="utf-8") for f in ("ledger.py", "events.py", "scope.py"))
        for word in ("requests", "urllib", "http.client", "supabase", "socket"):
            self.assertNotIn("import " + word, src)

    def test_tracking_hook_does_not_replace_generation_tracking(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        i = src.index("def _track_generation_end")
        body = src[i:src.index("\n    def ", i + 10)]
        for needle in ("tracker.complete(", "tracker.cancel(", "tracker.fail("):
            self.assertIn(needle, body)


if __name__ == "__main__":
    unittest.main()
