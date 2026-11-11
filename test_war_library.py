"""War footage library (cinematic_explainer/war/library.py): every footage row asks the reviewed library first, only what it lacks is searched
live. A synthetic library in a temp folder; no network, no rendering (the import test makes two 4 s clips with ffmpeg)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from cinematic_explainer.war import library as L

CLIPS = {
    "moskva/moskva_001.mp4": ("moskva", "Moskva cruiser warship Black Sea Fleet flagship"),
    "refinery_fire/refinery_fire_001.mp4": ("refinery_fire", "refinery fire black smoke oil plant"),
    "harbour/harbour_001.mp4": ("harbour", "hazy bay coast sea"),
    "russian_soldiers/russian_soldiers_001.mp4": ("russian_soldiers", "Russian soldiers marching column"),
    "sea_drone/sea_drone_001.mp4": ("sea_drone", "sea drone water thermal camera"),
    "drone_strike_aerial/drone_strike_aerial_001.mp4": ("drone_strike_aerial", "drone aerial strike smoke village"),
    "missile_launch/missile_launch_001.mp4": ("missile_launch", "rocket launcher salvo firing"),
    "black_sea_coast/black_sea_coast_001.mp4": ("black_sea_coast", "hazy bay harbour coast sea"),
    "russian_submarine/russian_submarine_001.mp4": ("russian_submarine", "Kilo submarine in port"),
    "money/money_001.mp4": ("money_economy", "counting rubles money hands"),
}


def make_library(clips=CLIPS, ai=()) -> Path:
    lib = Path(tempfile.mkdtemp())
    index = []
    for f, (subject, words) in clips.items():
        (lib / f).parent.mkdir(parents=True, exist_ok=True)
        (lib / f).write_bytes(f.encode())
        index.append({"file": f, "subject": subject, "words": words, "usable_s": 6.0, "url": f"https://www.youtube.com/watch?v={subject[:11]:x<11}",
                      "title": subject, "channel": "test", "ai_generated": f in ai})
    (lib / "index.json").write_text(json.dumps({"version": 1, "clips": index}), encoding="utf-8")
    cache = {}                       # the fake files are bytes, not videos: their visual check is recorded as already passed
    for f in clips:
        st = (lib / f).stat()
        cache[f] = {"sig": f"{st.st_size}:{int(st.st_mtime)}", "why": ""}
    (lib / L.USABILITY).write_text(json.dumps(cache), encoding="utf-8")
    return lib


def _line(prompt):
    """A narration line about what its prompt asks for (render 050 rule: a library clip must fit the LINE, not only the CSV prompt; a real
    CSV's prompt is written from its line, so a line says what its prompt searches for)."""
    words = [w for w in prompt.split() if w.lower() not in ("footage", "video")]
    return "The story here is the " + " ".join(words) + "."


def scenes_for(prompts, step=20.0, asset_type="youtube_video"):
    return [{"scene_no": i + 1, "text": _line(p), "start": i * step, "end": (i + 1) * step, "asset_type": asset_type,
             "prompt": p} for i, p in enumerate(prompts)]


def rows_for(scenes):
    from cinematic_explainer.war.app_section import csv_rows

    return csv_rows(scenes)


def files(prompt, clips):
    return [clips[i]["file"].split("/")[0] for _s, _p, i in L.candidates(prompt, clips)]


class TestMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = make_library()
        cls.clips = L.load(cls.lib)

    def test_a_named_search_takes_only_a_clip_carrying_the_name(self):
        self.assertEqual(files("Moskva cruiser sinking footage", self.clips), ["moskva"])
        self.assertEqual(files("Admiral Makarov frigate footage", self.clips), [])         # named, not held: live search
        self.assertEqual(files("Storm Shadow missile footage", self.clips), [])

    def test_a_plain_search_needs_two_shared_words_or_one_in_the_subject_name(self):
        self.assertEqual(files("big fire at night", self.clips)[:1], ["refinery_fire"])  # 'fire' is in the subject name
        self.assertIn("harbour", files("calm bay coast", self.clips))                     # two shared words
        self.assertEqual(files("bay", self.clips), [])                                    # one word, not in a subject name
        self.assertEqual(files("Russian rubles money", self.clips), ["money"])

    def test_a_clip_of_the_other_side_is_never_taken(self):
        self.assertEqual(files("Ukrainian soldiers marching footage", self.clips), [])
        self.assertEqual(files("Russian soldiers marching footage", self.clips), ["russian_soldiers"])
        self.assertEqual(files("soldiers marching footage", self.clips), ["russian_soldiers"])

    def test_an_underwater_drone_is_never_an_aerial_clip_and_a_launch_is_no_rocket_salvo(self):
        self.assertEqual(files("Ukrainian underwater drone footage", self.clips), ["sea_drone"])
        self.assertNotIn("missile_launch", files("Ukrainian long range drone launch footage", self.clips))
        self.assertNotIn("sea_drone", files("Ukrainian long range drone launch footage", self.clips))

    def test_black_sea_fleet_says_where_not_what(self):
        self.assertEqual(files("Russian submarine Black Sea Fleet footage", self.clips), ["russian_submarine"])

    def test_a_stock_row_is_matched_by_its_stock_query(self):
        rows = rows_for(scenes_for(["Russian rubles money"], asset_type="stock_video"))
        got = L.plan(scenes_for(["Russian rubles money"], asset_type="stock_video"), rows, self.clips)
        self.assertEqual(got["1"]["source"], "library")


class TestNamesAndAi(unittest.TestCase):
    def test_a_name_must_appear_as_one_phrase_and_military_alone_is_not_a_match(self):
        clips = L.load(make_library({"ai_black_sea_storm/a_01.mp4": ("ai_black_sea_storm", "rough storm sea, ships in shadow"),
                                     "ai_factory_military/b_01.mp4": ("ai_factory_military", "artillery shells on a factory line")}))
        self.assertEqual(files("Storm Shadow missile footage", clips), [])
        self.assertEqual(files("Russian army military vehicles footage", clips), [])
        self.assertEqual(files("Russian military factory production footage", clips), ["ai_factory_military"])

    def test_at_the_same_fit_real_footage_comes_before_an_ai_clip(self):
        clips = L.load(make_library({"a_steel/steel_mill_001.mp4": ("steel_mill", "molten steel sparks"),
                                     "z_steel/steel_mill_002.mp4": ("steel_mill", "molten steel sparks")}, ai={"a_steel/steel_mill_001.mp4"}))
        sc = scenes_for(["steel mill footage"])
        self.assertEqual(L.plan(sc, rows_for(sc), clips)["1"]["clip"]["file"], "z_steel/steel_mill_002.mp4")


class TestLiveCap(unittest.TestCase):
    def test_past_the_live_limit_a_named_row_takes_the_same_kind_of_clip_or_war_graphics(self):
        clips = L.load(make_library({"warship_port/warship_port_001.mp4": ("warship_port", "Russian warship moored in port"),
                                     "warship_port/warship_port_002.mp4": ("warship_port", "warships moored at a naval base pier")}))
        prompts = ["Russian warships Novorossiysk footage"] * 3 + ["Storm Shadow missile footage", "Pletenchuk navy spokesman footage"]
        sc = scenes_for(prompts, step=70.0)
        got = L.plan(sc, rows_for(sc), clips, cap=2)
        self.assertEqual(sorted(no for no, d in got.items() if d["source"] == "live"), ["1", "4"])   # each different search first
        self.assertEqual((got["2"]["source"], got["2"]["relaxed"]), ("library", True))
        self.assertEqual(got["5"]["source"], "graphics")                                          # nothing like it: map / cards
        self.assertEqual(sum(d["source"] == "live" for d in L.plan(sc, rows_for(sc), clips).values()), 5)   # no limit: all live
        self.assertEqual(L.live_cap({}), 10)
        self.assertIsNone(L.live_cap({"war_live_searches": -1}))


class TestPlan(unittest.TestCase):
    def test_reuse_gap_and_max_uses_then_war_graphics(self):
        clips = L.load(make_library({"refinery_fire/refinery_fire_001.mp4": ("refinery_fire", "refinery fire black smoke")}))
        sc = scenes_for(["refinery fire footage"] * 8, step=20.0)
        got = L.plan(sc, rows_for(sc), clips)
        # MAX_USES is 2 per source video since render 050 (one road clip on 3 unrelated lines, one Kremlin clip on 5)
        self.assertEqual([got[str(i)]["source"] for i in range(1, 9)],
                         ["library", "graphics", "graphics", "library", "graphics", "graphics", "graphics", "graphics"])
        rep = L.summary(got)
        self.assertEqual(rep["need_more"], [{"subject": "refinery_fire", "rows": 8, "short": 6}])

    def test_same_csv_and_library_give_the_same_plan_and_unmatched_rows_go_live(self):
        clips = L.load(make_library())
        sc = scenes_for(["refinery fire footage", "Kalibr cruise missile footage", "Russian soldiers marching", "calm bay coast",
                         "refinery fire footage", "Moskva cruiser"] * 4, step=12.0)
        a, b = L.plan(sc, rows_for(sc), clips), L.plan(sc, rows_for(sc), clips)
        key = lambda p: {k: (v["source"], (v.get("clip") or {}).get("file")) for k, v in p.items()}
        self.assertEqual(key(a), key(b))
        self.assertEqual(a["2"], {"source": "live"})


class TestApply(unittest.TestCase):
    def test_apply_files_clips_writes_records_and_the_report(self):
        from asset_manager import AssetManifest

        lib = make_library(ai={"sea_drone/sea_drone_001.mp4"})
        proj = Path(tempfile.mkdtemp())
        images, state = proj / "assets", proj
        sc = scenes_for(["refinery fire footage", "Kalibr cruise missile footage", "Ukrainian underwater drone footage"])
        got = L.apply(sc, rows_for(sc), images, state, lib=lib)
        self.assertEqual([got[n]["source"] for n in "123"], ["library", "live", "library"])
        self.assertEqual((images / "001.mp4").read_bytes(), b"refinery_fire/refinery_fire_001.mp4")
        man = AssetManifest(images)
        rec = man.get("1")
        self.assertEqual((rec["status"], rec["selection_method"], rec["library_file"]), ("complete", "war_library", "refinery_fire/refinery_fire_001.mp4"))
        self.assertTrue(man.get("3")["ai_generated"])
        self.assertIsNone(man.get("2"))
        rep = json.loads((state / L.REPORT).read_text(encoding="utf-8"))
        self.assertEqual(rep["counts"], {"library": 2, "clips": 2, "relaxed": 0, "graphics": 0, "live": 1})
        self.assertEqual(L.library_nos(images, rows_for(sc)), {"1", "3"})

    def test_fetch_asks_the_library_first_and_keeps_user_picks_and_earlier_live_clips(self):
        from asset_manager import AssetManifest
        from cinematic_explainer.war.app_section import fetch_csv_footage
        from test_war_app_section import _FakeManager

        lib = make_library({"refinery_fire/refinery_fire_001.mp4": ("refinery_fire", "refinery fire black smoke"),
                            "sea_drone/sea_drone_001.mp4": ("sea_drone", "sea drone water")}, ai={"sea_drone/sea_drone_001.mp4"})
        proj = Path(tempfile.mkdtemp())
        images = proj / "assets"
        images.mkdir()
        sc = scenes_for(["refinery fire footage", "refinery fire footage", "Kalibr cruise missile footage", "refinery fire footage",
                         "refinery fire footage", "Ukrainian underwater drone footage"], step=10.0)
        mine, earlier = images / "mine.mp4", images / "earlier.mp4"
        mine.write_bytes(b"m")
        earlier.write_bytes(b"e")
        man = AssetManifest(images)
        man.set("4", {"scene_number": "4", "status": "complete", "source": "manual", "type": "video", "local_path": str(mine), "user_override": True})
        man.set("5", {"scene_number": "5", "status": "complete", "source": "youtube_video", "type": "video", "local_path": str(earlier)})
        mgr = _FakeManager(images)
        out, _rows = fetch_csv_footage(sc, mgr, images, director=False, library=lib)
        self.assertEqual([a[0] for a in mgr.asked], ["3"])                    # only the row the library has nothing for is searched
        self.assertTrue(out[0]["footage"].endswith("001.mp4"))
        self.assertTrue(out[1].get("no_footage") and not out[1].get("footage"))  # subject used (gap): War graphics, no search
        self.assertNotEqual(out[1].get("graphic"), "keywords")             # 2026-11-12 owner: never a keyword card from loose words; War graphics choose
        self.assertEqual(out[3]["footage"], str(mine))
        self.assertEqual(out[4]["footage"], str(earlier))
        self.assertTrue(out[5]["footage_meta"].get("ai_generated"))
        out2, _ = fetch_csv_footage(sc, None, images, fetch=False)             # Render after Generate scenes: same graphics row
        self.assertTrue(out2[1].get("no_footage"))
        mgr2 = _FakeManager(images)
        fetch_csv_footage(sc, mgr2, images, director=False, library=False)     # library off: the library's own rows stay as filed
        self.assertEqual([a[0] for a in mgr2.asked], ["2"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg needed")
class TestImport(unittest.TestCase):
    def test_import_checks_pictures_and_approve_adds_the_reviewed_clips(self):
        work = Path(tempfile.mkdtemp())
        lib = make_library({})
        for name, size in (("001", "1280x720"), ("002", "1280x720"), ("003", "640x360")):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25:duration=4", "-c:v", "libx264",
                            "-preset", "ultrafast", str(work / f"{name}.mp4")], check=True)
        (work / "batch.csv").write_text("scene_number,library_name\n1,steel_mill_01\n2,steel_mill_02\n3,steel_mill_03\n", encoding="utf-8")
        z = work / "friend_a.zip"
        with zipfile.ZipFile(z, "w") as zf:
            for n in ("001.mp4", "002.mp4", "003.mp4", "batch.csv"):
                zf.write(work / n, f"batch/{n}")
        box = L.import_batch(z, lib=lib, log=lambda m: None)
        pend = json.loads((box / "pending.json").read_text(encoding="utf-8"))
        self.assertEqual([(c["name"], c["ok"]) for c in pend["clips"]], [("steel_mill_01", True), ("steel_mill_02", True), ("steel_mill_03", False)])
        self.assertTrue(list(box.glob("sheet_*.jpg")))
        self.assertEqual(L.load(lib), [])                                       # nothing enters the library before approve
        self.assertEqual(L.approve(box.name, ["steel_mill_02"], lib=lib, log=lambda m: None), 1)
        self.assertEqual([c["file"] for c in L.load(lib)], ["steel_mill/steel_mill_001.mp4"])

    def test_a_flow_batch_folder_with_scene_names_is_named_marked_ai_and_described_by_its_prompt(self):
        work = Path(tempfile.mkdtemp())
        lib = make_library({})
        (work / "clips").mkdir()
        for name in ("scene_001", "scene_002"):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=4", "-c:v", "libx264",
                            "-preset", "ultrafast", str(work / "clips" / f"{name}.mp4")], check=True)
        (work / "flow_batch.csv").write_text(
            "scene_number,start,end,script_segment,asset_type,prompt,graphic,library_name\n"
            '1,0,8,x,flow_video,"a grey warship in a foggy harbour at dawn, slow push-in",,ai_dry_dock_2_01\n'
            '2,8,16,x,flow_video,"molten steel pouring in a mill, sparks",,ai_steel_mill_02\n', encoding="utf-8")
        box = L.import_batch(work, lib=lib, log=lambda m: None)
        pend = {c["name"]: c for c in json.loads((box / "pending.json").read_text(encoding="utf-8"))["clips"]}
        self.assertEqual(set(pend), {"ai_dry_dock_2_01", "ai_steel_mill_02"})
        self.assertEqual(pend["ai_dry_dock_2_01"]["subject"], "ai_dry_dock")               # the batch marker '_2' joins the subject
        self.assertTrue(all(c["ai_generated"] for c in pend.values()))
        self.assertEqual(pend["ai_steel_mill_02"]["words"], "molten steel pouring in a mill")  # camera / light notes left out


if __name__ == "__main__":
    unittest.main()
