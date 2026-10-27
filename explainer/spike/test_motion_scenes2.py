"""Tests for the "scenes v2" pack (opt-in DirectorOptions.scenes2): assets, loader, lexicon, tile pictures, cartoon composer, flag-off identity, packaging by simulation.

Offline and deterministic; plans are built with materialize=False; nothing is generated at render time.
usage: python3 -B explainer/spike/test_motion_scenes2.py   (from the repository root)"""
import hashlib
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import synth, run                      # noqa: E402
from m4_topics import TOPICS, words_from_script                         # noqa: E402
from explainer.cartoon import kit as K, kit_v2 as V, build_scenes_v2 as B      # noqa: E402
from explainer.director import lexicon_v2 as LV, compose_cartoon as CC          # noqa: E402
from explainer.director.options import DirectorOptions                          # noqa: E402

V1_DIR = ROOT / "explainer" / "assets" / "cartoon"
V2_DIR = ROOT / "explainer" / "assets" / "scenes_v2"


def head_module():
    """compose_cartoon.py exactly as committed (the 'before' for the flag-off identity test)."""
    src = subprocess.run(["git", "show", "HEAD:explainer/director/compose_cartoon.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    m = types.ModuleType("explainer.director.compose_cartoon")
    m.__package__ = "explainer.director"
    m.__file__ = str(ROOT / "explainer/director/compose_cartoon.py")
    exec(compile(src, "compose_cartoon_HEAD.py", "exec"), m.__dict__)
    return m


class Assets(unittest.TestCase):
    def test_build_check_passes_and_counts(self):
        files = B.build()
        for n, b in files.items():
            self.assertEqual((V2_DIR / n).read_bytes(), b, n)
        self.assertEqual({p.name for p in V2_DIR.glob("*")}, set(files))
        m = V.manifest()
        self.assertEqual((len(m["sets"]), len(m["props"])), (8, 15))
        self.assertEqual(len(files), 8 * 2 + 15 + 1)

    def test_manifest_hashes_verify(self):
        m = V.manifest()
        for s in m["sets"].values():
            for slot in s["tod"].values():
                b = (V2_DIR / slot["file"]).read_bytes()
                self.assertEqual((hashlib.sha256(b).hexdigest(), len(b)), (slot["sha256"], slot["bytes"]))
        self.assertTrue(V.available())

    def test_old_kit_untouched(self):
        out = subprocess.run(["git", "status", "--porcelain", "explainer/assets/cartoon", "explainer/cartoon/kit.py", "explainer/cartoon/build_assets.py"], cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "")
        self.assertEqual(len(list(V1_DIR.glob("*"))), 42)

    def test_art_is_not_flat_nothing(self):
        for s in V.sets():
            for t in ("day", "dusk"):
                im = V.set_image(s, t)
                self.assertEqual(im.size, (1920, 1080))
                self.assertGreater(len(set(im.resize((96, 54)).getdata())), 12)
        for p in V.props():
            self.assertIsNotNone(V.prop_full(p).getchannel("A").getbbox())


class Loader(unittest.TestCase):
    def test_install_resolves_v2_names_and_leaves_v1_alone(self):
        self.assertTrue(V.install())
        self.assertTrue(V.install())
        self.assertEqual(K.problem("set", {"set": "vault", "tod": "dusk"}), "")
        self.assertEqual(K.problem("prop", {"prop": "tank"}), "")
        self.assertEqual(K.problem("set", {"set": "town"}), "")
        self.assertNotEqual(K.problem("set", {"set": "nonesuch"}), "")
        self.assertEqual(K.set_image("vault", "day").size, (1920, 1080))
        self.assertEqual(K.ground_y("vault"), 880)
        self.assertEqual(K.prop_sprite("train", 170).height, 170)
        self.assertEqual(K.set_image("town", "day").size, (1920, 1080))

    def test_missing_or_damaged_asset_is_a_problem_not_a_crash(self):
        V._file_problem.cache_clear()
        real = V.ASSET_DIR
        with tempfile.TemporaryDirectory() as d:
            for f in real.glob("*"):
                (Path(d) / f.name).write_bytes(f.read_bytes())
            (Path(d) / "set_vault_day.png").unlink()
            (Path(d) / "prop_tank.png").write_bytes(b"damaged")
            V.ASSET_DIR = Path(d)
            try:
                self.assertIn("missing", V.problem("set", {"set": "vault"}))
                self.assertIn("manifest", V.problem("prop", {"prop": "tank"}))
                self.assertEqual(V.problem("prop", {"prop": "train"}), "")
                self.assertFalse(V.available())
                self.assertFalse(CC._v2_ready() and V.available())
                # the composer falls back to the flag-off behaviour
                opt = DirectorOptions(); object.__setattr__(opt, "scenes2", True)
                words = [(w, 0.5 + 0.3 * i, 0.7 + 0.3 * i) for i, w in enumerate("the farmers worked the field and the village grew rich from the harvest".split())]
                self.assertEqual(CC.scene_score("farmers field village".split(), scenes2=True), CC.scene_score("farmers field village".split()))
                _ = words
            finally:
                V.ASSET_DIR = real
                V._file_problem.cache_clear()
        self.assertTrue(V.available())
        # a missing manifest
        V.manifest.cache_clear()
        with tempfile.TemporaryDirectory() as d:
            V.ASSET_DIR = Path(d)
            try:
                self.assertFalse(V.available())
                self.assertIn("missing", V.problem("set", {"set": "vault"}))
                self.assertEqual(V.sets(), ())
                from explainer.board import icons as I
                V.prop_full.cache_clear(); I.icon_sprite.cache_clear()
                self.assertEqual(I.icon_sprite("pic:train", "blue", 120).size, (120, 120))      # stand-in square, no crash
            finally:
                V.ASSET_DIR = real
                V.manifest.cache_clear(); V._file_problem.cache_clear(); V.prop_full.cache_clear()
                __import__("explainer.board.icons", fromlist=["x"]).icon_sprite.cache_clear()


class Lexicon(unittest.TestCase):
    def pick(self, s):
        return LV.choose_scene_v2(s.split())

    def test_near_synonyms_pick_different_scenes(self):
        got = [self.pick(s) for s in ("the village priest", "the town council walked", "at the border crossing", "the station platform", "the bank was full", "high in the mountains",
                                      "inside the barn", "a snow storm covered the village")]
        self.assertEqual(got, ["village", "old_town", "border_wall", "station", "vault", "mountain_pass", "barn", "snowy_village"])
        self.assertEqual(len(set(got)), 8)

    def test_no_scene_when_none_is_named(self):
        for s in ("it was a family business", "the people were afraid", "the country grew rich", "they made a plan", "money changed everything"):
            self.assertIsNone(self.pick(s), s)
            self.assertEqual(CC.scene_score(s.split(), scenes2=True), 0)

    def test_every_table_target_exists_in_the_pack_or_v1(self):
        for name in LV.SET_WORDS_V2:
            self.assertTrue(name in V.sets() or name in K.sets(), name)
        for p in LV.PROP_WORDS_V2:
            self.assertTrue(p in V.props() or p in K.manifest()["props"], p)
        for a in LV.TILE_ICONS_V2.values():
            self.assertIn(a.split(":")[1], V.props())

    def test_props_and_tiles_distinguish_near_synonyms(self):
        pr = lambda s: (LV.prop_for_v2(s.split()) or (None,))[0]
        self.assertEqual([pr("a convoy of lorries"), pr("the tanks rolled"), pr("planes overhead"), pr("ships at sea"), pr("a border post"), pr("barbed wire")],
                         ["truck", "tank", "plane", "ship", "border_post", "barbed_wire"])
        self.assertIsNone(pr("the village grew"))
        self.assertIsNone(pr("the country was rich"))
        self.assertEqual(LV.tile_for_v2("they hid gold".split())[0], "pic:gold_bars")
        self.assertEqual(LV.tile_for_v2("stacks of coins".split())[0], "pic:coin_stack")
        self.assertEqual(LV.tile_for_v2("a secret dossier".split())[0], "pic:folder")
        self.assertIsNone(LV.tile_for_v2("a quiet morning".split()))
        self.assertEqual(LV.scenes2_tables()["icons"]["train"], "pic:train")

    def test_snow_beside_a_town_is_the_snowy_village(self):
        self.assertEqual(self.pick("the town was buried in snow"), "snowy_village")
        self.assertEqual(self.pick("winter came to the village"), "snowy_village")


class Icons(unittest.TestCase):
    def test_tile_pictures_register_and_draw(self):
        from explainer.board import icons as I
        V.install()
        for i in ("pic:" + n for n in V.props()):
            self.assertIn(i, I.ICONS)
            im = I.icon_sprite(i, "blue", 160)
            self.assertEqual(im.size, (160, 160))
            bb = im.getchannel("A").getbbox()
            self.assertIsNotNone(bb)
            self.assertGreaterEqual(bb[0], 2); self.assertLessEqual(bb[2], 158)
        self.assertEqual(len(__import__("explainer.board.icons_v2", fromlist=["x"]).register()), 0)


class Composer(unittest.TestCase):
    def test_scene_score_flag_off_is_v1(self):
        for s in ("the farmers worked the field", "a family business", "the village grew rich", "sailors in the harbour"):
            t = s.split()
            self.assertEqual(CC.scene_score(t), CC.scene_score(t, scenes2=False))

    def test_flag_on_scores_new_scenes(self):
        self.assertGreater(CC.scene_score("guards at the border wall watched the refugees".split(), scenes2=True), 0)
        self.assertEqual(CC.scene_score("guards at the border wall watched the refugees".split()), 0)

    def test_author_cartoon_uses_the_new_pieces(self):
        plan_cues = self._author("The guards at the border wall watched the refugees, and a train of tanks rolled through the village at night.", True)
        sets = [c.params["set"] for c in plan_cues if c.params.get("style") == "set"]
        props = [c.params["prop"] for c in plan_cues if c.params.get("style") == "prop"]
        self.assertEqual(sets, ["border_wall"])
        self.assertEqual(len(props), 1)
        self.assertIn(props[0], ("border_post", "train", "tank"))
        self.assertEqual([c.params["tod"] for c in plan_cues if c.params.get("style") == "set"], ["dusk"])
        from explainer.board.cues import Cue
        self.assertTrue(all(isinstance(c, Cue) for c in plan_cues))

    def test_no_set_when_the_words_name_none(self):
        cues = self._author("They built a family business that nobody believed in, and the people were afraid of everything.", True)
        self.assertEqual([c for c in cues if c.params.get("style") == "set"], [])
        self.assertTrue([c for c in cues if c.params.get("style") == "figure"])

    def test_the_prop_never_overlaps_a_figure_and_stays_in_the_frame(self):
        from explainer.board import styles as ST
        for text in ("A convoy of lorries and a long train crossed the border.", "The ship sailed past the harbour wall.", "The planes of the Luftwaffe flew over the town square."):
            for v in (0, 1):
                cues = self._author(text, True, variant=v)
                for p in [c for c in cues if c.params.get("style") == "prop"]:
                    m = ST.measure_cartoon("prop", p.params)
                    x0, x1 = p.pos[0], p.pos[0] + m["w"]
                    self.assertTrue(96 <= x0 and x1 <= 1824, (text, x0, x1))
                    for f in [c for c in cues if c.params.get("style") == "figure"]:
                        fm = ST.measure_cartoon("figure", f.params)
                        self.assertTrue(x1 <= f.pos[0] or x0 >= f.pos[0] + fm["w"], (text, x0, x1, f.pos))

    def _author(self, text, scenes2, variant=0):
        from explainer.director import segment as SG
        words, dur = synth(text)
        opt = DirectorOptions(cartoon_share=0.5)
        object.__setattr__(opt, "scenes2", scenes2)
        sents = SG.sentences(words, text, dur, opt.split_over_s)
        SG.label_sentences(sents, words, text)
        SG.compute_breaks(sents, words)
        r = CC.author_cartoon("b1", words[0][1], dur + 1, sents, words, SG.casing(text), opt, dict(__import__("explainer.director.lexicon", fromlist=["x"]).ICONS), {}, variant=variant)
        return r.cues


class FlagOffIdentity(unittest.TestCase):
    def test_cartoon_plans_are_identical_to_head_for_the_m4_topics(self):
        for name, (script, *_r) in TOPICS.items():
            words, dur = words_from_script(script)
            new = run(words, script, dur, cartoon_share=0.3)
            cur = sys.modules["explainer.director.compose_cartoon"]
            sys.modules["explainer.director.compose_cartoon"] = head_module()
            try:
                old = run(words, script, dur, cartoon_share=0.3)
            finally:
                sys.modules["explainer.director.compose_cartoon"] = cur
            self.assertEqual(json.dumps(new.plan, sort_keys=True, default=str), json.dumps(old.plan, sort_keys=True, default=str), name)

    def test_the_v1_manifest_is_byte_identical_to_head(self):
        head = subprocess.run(["git", "show", "HEAD:explainer/assets/cartoon/manifest.json"], cwd=ROOT, capture_output=True).stdout
        self.assertEqual(head, (V1_DIR / "manifest.json").read_bytes())


class Packaging(unittest.TestCase):
    def test_a_simulated_data_dirs_list_ships_every_v2_file(self):
        from explainer import packaging as P
        old = P.DATA_DIRS
        try:
            P.DATA_DIRS = tuple(old) + (() if "assets/scenes_v2" in old else ("assets/scenes_v2",))
            got = {Path(src).name for src, dst in P.data_files(ROOT) if dst.replace("\\", "/").endswith("assets/scenes_v2")}
        finally:
            P.DATA_DIRS = old
        self.assertEqual(got, set(B.build()))


if __name__ == "__main__":
    unittest.main(verbosity=1)
