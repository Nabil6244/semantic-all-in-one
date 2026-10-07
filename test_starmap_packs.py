"""StarMap phase 6: every mission pack is complete and consistent, and its shipped sample (script, beat CSV, media) passes
Check plan and compiles. A new pack is covered by these tests as soon as it and its sample are added."""

import csv
import io
import json
import unittest
from datetime import datetime
from pathlib import Path

from pakmap.words import estimate_words
from starmap import Catalog, check_csv, compile_plan, read_plan
from starmap.catalog import available_packs
from starmap.compile import strip_private
from starmap.prompt import build_prompt

HERE = Path(__file__).resolve().parent
PACKS = HERE / "starmap" / "packs"
SAMPLES = HERE / "starmap" / "samples"
MEDIA_DIR = HERE / "starmap-engine" / "samples" / "media"
EXPECTED = {"apollo8", "apollo11", "apollo13", "artemis1", "chandrayaan3", "change4"}   # the Moon Missions pack


def iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class EveryPack(unittest.TestCase):
    def test_the_moon_missions_are_all_there(self):
        self.assertTrue(EXPECTED <= set(available_packs()), sorted(EXPECTED - set(available_packs())))

    def test_each_pack_is_consistent(self):
        for pid in available_packs():
            with self.subTest(pack=pid):
                p = json.loads((PACKS / f"{pid}.json").read_text(encoding="utf-8"))
                cat = Catalog(pid)
                self.assertEqual(p["id"], pid)
                self.assertIn("illustrated", p["_about"].lower(), "the pack says its trajectories are illustrated")
                events = p["events"]
                self.assertEqual(p["met_zero"], events["launch"], "mission time starts at launch")
                times = [iso(t) for t in events.values()]
                self.assertEqual(times, sorted(times), "events are listed in time order")
                ids = {t["id"] for t in p["trajectories"]}
                for t in p["trajectories"]:
                    self.assertEqual(t.get("source"), "illustrated")
                    for g in t["generate"]:
                        for k in ("from_utc", "to_utc"):
                            if k in g:
                                iso(g[k])
                for name, c in p["craft"].items():
                    self.assertIn(c["trajectory"], ids, f"craft {name}")
                for name, a in p.get("craft_aliases", {}).items():
                    self.assertIn(a, p["craft"], f"alias {name}")
                for name, path in p["paths"].items():
                    self.assertIn(path["of"], ids, f"path {name}")
                    self.assertLess(iso(cat.date(path["from"])), iso(cat.date(path["to"])), f"path {name} runs forwards")
                for name, o in p["orbits"].items():
                    self.assertIn(o["trajectory"], ids, f"orbit {name}")
                    cat.date(o["at"])
                for name, s in p["sites"].items():
                    self.assertIn(s["body"], cat.body_ids, name)
                    self.assertTrue(-180 <= s["lon"] <= 180 and -90 <= s["lat"] <= 90, name)
                    self.assertTrue(s.get("label"), name)

    def test_each_pack_fills_the_prompt(self):
        for pid in available_packs():
            with self.subTest(pack=pid):
                p = build_prompt(pid, "My script.")
                self.assertNotIn("<<<", p)
                self.assertIn(f"\n{pid} = ", p, "the dataset is listed in full")
                self.assertIn(f"{pid}.launch (", p, "its events, qualified")


class EverySample(unittest.TestCase):
    def files(self, pid):
        return (SAMPLES / f"{pid}_script.txt", SAMPLES / f"{pid}_beats.csv", SAMPLES / f"{pid}_media.json")

    def test_each_pack_has_a_sample(self):
        for pid in available_packs():
            with self.subTest(pack=pid):
                for f in self.files(pid):
                    self.assertTrue(f.exists(), f.name)

    def test_each_sample_obeys_the_prompt_rules(self):
        """Joined beat texts are the script word for word; each beat's vo_anchor is its first words; every row's anchor is in
        its own beat's text; the plan row's id is empty (datasets are found) or the dataset id as a starting context."""
        for pid in available_packs():
            with self.subTest(pack=pid):
                script, beats_csv, _ = self.files(pid)
                rows = list(csv.DictReader(io.StringIO(beats_csv.read_text(encoding="utf-8"))))
                self.assertEqual(rows[0]["row"], "plan")
                self.assertIn(rows[0]["id"], ("", pid), "the plan row's id is empty or an optional starting context")
                beats = [r for r in rows if r["row"] == "beat"]
                self.assertEqual(" ".join(r["text"] for r in beats).split(), script.read_text(encoding="utf-8").split())
                text = {r["beat"]: r["text"] for r in beats}
                for r in beats:
                    self.assertTrue(r["text"].startswith(r["vo_anchor"]), r["beat"])
                for r in rows:
                    if r["row"] in ("layer", "card") and r["vo_anchor"]:
                        self.assertIn(r["vo_anchor"], text[r["beat"]], f"{r['beat']} {r['type']}")

    def test_each_sample_passes_check_plan_and_compiles(self):
        for pid in available_packs():
            with self.subTest(pack=pid):
                script, beats_csv, media_json = self.files(pid)
                words = estimate_words(script.read_text(encoding="utf-8"), words_per_second=2.5)
                text = beats_csv.read_text(encoding="utf-8")
                media = json.loads(media_json.read_text(encoding="utf-8"))
                rep = check_csv(text, words, None, media=media)
                self.assertTrue(rep.ok, rep.to_text())
                self.assertFalse([p for p in rep.to_text().splitlines() if p.startswith("NOTE")], rep.to_text())
                spec = strip_private(compile_plan(read_plan(text, words), Catalog(pid), media=media).spec)
                self.assertTrue(any(L["type"] == "spacecraft" for L in spec["layers"]), "the sample shows its craft")
                self.assertTrue(any(L["type"] == "trajectory" for L in spec["layers"]), "and its path")

    def test_each_sample_picture_is_shipped_and_credited(self):
        credits = (MEDIA_DIR / "CREDITS.txt").read_text(encoding="utf-8")
        for pid in available_packs():
            with self.subTest(pack=pid):
                media = json.loads(self.files(pid)[2].read_text(encoding="utf-8"))
                for desc, m in media.items():
                    if desc.startswith("_"):
                        continue
                    self.assertTrue(desc.startswith("nasa_image:"), desc)
                    self.assertTrue((MEDIA_DIR / m["file"]).exists(), m["file"])
                    self.assertIn(m["file"], credits)
                    self.assertTrue(m.get("credit"), desc)


if __name__ == "__main__":
    unittest.main()
