"""Voxel Map photo cards: planned from the narration, CSV wins, pictures through the Visuals tab, the story the renderer reads."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "voxelmap-engine"
spec = importlib.util.spec_from_file_location("vme_cards_test", ENGINE / "cards.py")
cards = importlib.util.module_from_spec(spec)
sys.modules["vme_cards_test"] = cards
spec.loader.exec_module(cards)

HEAD = "row,id,date,place,lon,lat,rung,alt,heading,site,gap,text,extra\n"
LONG = ("Romulus founded the city on the Palatine Hill after he killed his brother Remus. " * 3).strip()


def story(beats: str, extra_rows: str = "") -> str:
    return (HEAD + 'plan,T,,,,,,,,,,,"{""world"":""x"",""wpm"":150}"\nchapter,c1,,,,,,,,,,One,\n' + beats + extra_rows)


def beat(i, rung, text, place="Rome"):
    return f'beat,b{i},-0753-04,{place},12.5,41.9,{rung},,,,,"{text}",\n'


class Cards(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def csv(self, text):
        p = self.d / "s.csv"
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_a_long_scene_gets_a_card_named_from_its_narration(self):
        reqs = cards.requests(self.csv(story(beat(1, "map", LONG))))
        self.assertTrue(reqs)
        self.assertEqual(reqs[0]["beat"], "b1")
        self.assertIn("Romulus", reqs[0]["query"])
        self.assertTrue(reqs[0]["words"].startswith("Romulus"))
        self.assertEqual([c["n"] for c in reqs], list(range(1, len(reqs) + 1)))

    def test_no_card_on_a_globe_opening_or_a_very_short_scene(self):
        reqs = cards.requests(self.csv(story(beat(1, "globe", LONG) + beat(2, "map", "Romulus fled.") )))
        self.assertEqual(reqs, [])

    def test_pacing_one_card_per_twelve_seconds(self):
        sent = "Julius Caesar crossed the Rubicon with his army and marched south. "
        beats = "".join(beat(i, "map", sent) for i in range(1, 9))      # ~4 s each at 150 wpm: eight scenes ~ 32 s
        reqs = cards.requests(self.csv(story(beats.replace("Julius Caesar", "Julius Caesar", 1))))
        self.assertLessEqual(len(reqs), 4)

    def test_a_name_is_not_used_twice(self):
        t = "Romulus founded the city and ruled it for many long years of peace and war. "
        reqs = cards.requests(self.csv(story(beat(1, "map", t * 2) + beat(2, "map", t * 2))))
        self.assertEqual(len({c["label"].lower() for c in reqs}), len(reqs))

    def test_csv_wins_card_rows_in_the_story_mean_nothing_is_planned(self):
        rows = 'card,b1,,,12.5,41.9,,,,,,The wolf,"{""asset"":""Capitoline wolf bronze"",""words"":""founded the city""}"\n'
        reqs = cards.requests(self.csv(story(beat(1, "map", LONG) + beat(2, "map", LONG), rows)))
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["source"], "csv")
        self.assertEqual(reqs[0]["query"], "Capitoline wolf bronze")

    def test_a_picture_file_named_by_the_csv_is_used_as_is_not_searched(self):
        (self.d / "wolf.png").write_bytes(b"x")
        rows = 'card,b1,,,,,,,,,,The wolf,"{""asset"":""wolf.png""}"\n'
        reqs = cards.requests(self.csv(story(beat(1, "map", LONG), rows)))
        self.assertEqual(Path(reqs[0]["local"]).resolve(), (self.d / "wolf.png").resolve())
        self.assertEqual(cards.table_rows(reqs), [])

    def test_table_rows_are_searches_numbered_like_the_cards(self):
        reqs = cards.requests(self.csv(story(beat(1, "map", LONG))))
        rows = cards.table_rows(reqs)
        self.assertEqual([str(r.scene_number) for r in rows], [str(c["n"]) for c in reqs])
        self.assertTrue(all(r.stock for r in rows))

    def test_written_story_has_a_card_row_only_for_cards_with_a_picture(self):
        pic = self.d / "a.png"
        pic.write_bytes(b"x")
        reqs = cards.requests(self.csv(story(beat(1, "map", LONG) + beat(2, "map", LONG))))
        self.assertGreaterEqual(len(reqs), 2)
        out = cards.write_story(self.d / "s.csv", self.d / "w" / "story_cards.csv", reqs, {1: str(pic)}, ["Picture: x - y (z)"])
        rows, _ = cards.read_rows(out)
        crow = [r for r in rows if r["row"] == "card"]
        self.assertEqual(len(crow), 1)
        self.assertEqual(Path(json.loads(crow[0]["extra"])["asset"]), pic.resolve())      # absolute, so the renderer finds it from any folder
        plan = next(r for r in rows if r["row"] == "plan")
        self.assertIn("Picture: x - y (z)", json.loads(plan["extra"])["credits_lines"])

    def test_the_engine_reads_the_written_story_and_times_the_card_on_its_words(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        pic = self.d / "a.png"
        pic.write_bytes(b"\x89PNG\r\n\x1a\n")
        src = self.csv(story(beat(1, "map", LONG)))
        reqs = cards.requests(src)
        out = cards.write_story(src, self.d / "story_cards.csv", reqs, {1: str(pic)})
        r = subprocess.run([node, str(ENGINE / "render.mjs"), out, "--plan", "--out", str(self.d / "o")], capture_output=True, text=True, cwd=str(ENGINE), timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        tl = json.loads((self.d / "o" / "timeline.json").read_text(encoding="utf-8"))
        self.assertEqual(len(tl["cards"]), 1)
        self.assertTrue(tl["cards"][0]["url"].startswith("/card/"))

    def test_voxel_map_owns_a_visuals_folder(self):
        import visual_bridge
        from types import SimpleNamespace

        app = SimpleNamespace(_scene_rows_owner="voxel_map", _vm_active=True, _workspace=SimpleNamespace(root=str(self.d)))
        self.assertTrue(visual_bridge.owns(app))
        self.assertEqual(visual_bridge.images_dir(app), self.d / "state" / "voxel_map" / "assets")




class Queries(unittest.TestCase):
    def test_classify_and_query(self):
        self.assertEqual(cards.classify("Hannibal", "The general Hannibal marched an army."), "person")
        self.assertEqual(cards.classify("Carthage", "Across the sea lay Carthage, a wealthy city in Tunisia."), "place")
        self.assertEqual(cards.classify("Battle of Zama", "The Battle of Zama ended it."), "event")
        self.assertEqual(cards.classify("Theodosius", "After the death of Theodosius, the empire split."), "thing")
        self.assertEqual(cards.query_for("Scipio", "person"), "Scipio portrait painting")
        self.assertEqual(cards.query_for("Carthage", "place"), "Carthage ruins")
        self.assertEqual(cards.query_for("Senate", "thing", "rome"), "Senate rome painting")

    def test_an_adjective_before_a_title_is_not_the_subject(self):
        t = story(beat(1, "map", "Around 390 BC, a Gallic chieftain named Brennus beat the Romans at the river and then he marched on the city itself."))
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (d / "s.csv").write_text(t, encoding="utf-8")
        reqs = cards.requests(str(d / "s.csv"))
        self.assertTrue(reqs and reqs[0]["label"] == "Brennus", reqs)


class Wikipedia(unittest.TestCase):
    def fake(self, pages, images):
        def get(url, params):
            if "rest.php" in url:
                return {"pages": pages}
            return {"query": {"pages": images}}
        return get

    def test_the_matching_articles_commons_picture_is_taken(self):
        get = self.fake([{"title": "Hannibal", "description": "Carthaginian general"}],
                        [{"title": "Hannibal", "thumbnail": {"source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Hannibal.jpg/1280px-Hannibal.jpg"}}])
        hit = cards.wiki_picture("Hannibal", "Hannibal rome painting", get)
        self.assertTrue(hit["url"].endswith("1280px-Hannibal.jpg"))
        self.assertEqual(hit["page"], "https://en.wikipedia.org/wiki/Hannibal")

    def test_unrelated_or_disambiguation_hits_and_non_commons_pictures_are_refused(self):
        img = [{"title": "X", "thumbnail": {"source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/1280px-X.jpg"}}]
        self.assertIsNone(cards.wiki_picture("Senate", "Senate", self.fake([{"title": "Houses of Parliament", "description": "building"}], img)))
        self.assertIsNone(cards.wiki_picture("Senate", "Senate", self.fake([{"title": "Senate", "description": "Wikimedia disambiguation page"}], img)))
        local = [{"title": "Senate", "thumbnail": {"source": "https://upload.wikimedia.org/wikipedia/en/thumb/a/ab/Senate.jpg/1280px-Senate.jpg"}}]
        self.assertIsNone(cards.wiki_picture("Senate", "Senate", self.fake([{"title": "Senate", "description": "legislature"}], local)))

    def test_the_article_about_the_person_beats_one_that_only_mentions_them(self):
        img = [{"title": "X", "thumbnail": {"source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/1280px-X.jpg"}}]
        pages = [{"title": "Curia of Pompey", "description": "building in Rome"}, {"title": "Pompey", "description": "Roman general"}]
        hit = cards.wiki_picture("Pompey", "Pompey portrait painting", self.fake(pages, img))
        self.assertTrue(hit["page"].endswith("/Pompey") or hit["title"] == "X")
        self.assertEqual(cards._hit_rank("Pompey", "Pompey", True), 0)
        self.assertEqual(cards._hit_rank("Baths of Diocletian", "Diocletian", False), 2)
        self.assertEqual(cards._hit_rank("Roman Senate", "Senate", False), 1)

    def test_a_network_error_is_not_an_error(self):
        def boom(url, params):
            raise OSError("offline")
        self.assertIsNone(cards.wiki_picture("Hannibal", "Hannibal", boom))

    def test_seeded_picture_lands_in_the_visuals_manifest_with_its_credit(self):
        import visual_bridge

        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        get = self.fake([{"title": "Scipio Africanus", "description": "Roman general"}],
                        [{"title": "Scipio Africanus", "thumbnail": {"source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/S.jpg/1280px-S.jpg"}}])
        reqs = [{"n": 1, "label": "Scipio", "query": "Scipio portrait painting", "local": ""}]
        n = cards.seed_from_wikipedia(reqs, d, get=get, download=lambda u: b"jpgdata")
        self.assertEqual(n, 1)
        rows = cards.table_rows(reqs)
        rec = visual_bridge.records(d, rows)[1]
        self.assertTrue(rec["ok"])
        self.assertIn("Wikimedia", cards.credits(reqs, {1: rec})[0])
        self.assertEqual(cards.seed_from_wikipedia(reqs, d, get=get, download=lambda u: b"x"), 0)      # already held: never replaced

    def test_a_planned_card_without_a_wikipedia_picture_is_dropped_but_a_csv_card_is_searched(self):
        class Mgr:
            settings: dict = {}

            def __init__(self):
                self.got = []

            def resolve_all(self, rows):
                self.got = [r.stock for r in rows]

            def request_cancel(self):
                pass

        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        reqs = [{"n": 1, "label": "Vandals", "query": "Vandals rome painting", "local": "", "source": "auto"},
                {"n": 2, "label": "Wolf", "query": "Capitoline wolf bronze", "local": "", "source": "csv"}]
        old = cards.wiki_picture
        cards.wiki_picture = lambda *a, **k: None
        self.addCleanup(setattr, cards, "wiki_picture", old)
        m = Mgr()
        rows = cards.fetch(reqs, m, d)
        self.assertEqual([str(r.scene_number) for r in rows], ["2"])
        self.assertEqual(m.got, ["Capitoline wolf bronze"])


if __name__ == "__main__":
    unittest.main()
