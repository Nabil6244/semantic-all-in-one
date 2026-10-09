"""The packaged app carries everything StarMap loads at run time, and nothing it does not (tests, samples, the rest of node_modules)."""

import re
import unittest
from pathlib import Path

from starmap.packaging import engine_data_files

ROOT = Path(__file__).resolve().parent


class StarmapPackaging(unittest.TestCase):
    def setUp(self):
        self.files = {Path(src).relative_to(ROOT).as_posix(): dest for src, dest in engine_data_files(ROOT)}

    def test_every_module_the_page_imports_ships(self):
        page = (ROOT / "starmap-engine" / "page.js").read_text(encoding="utf-8")
        mods = re.findall(r"from '/((?:lib|layers)/[\w-]+\.mjs)'", page)
        self.assertGreaterEqual(len(mods), 8, mods)
        for mod in mods:
            self.assertIn(f"starmap-engine/{mod}", self.files, mod)
        for mod in (ROOT / "starmap-engine" / "layers").glob("*.mjs"):
            self.assertIn(f"starmap-engine/layers/{mod.name}", self.files)

    def test_every_texture_and_font_a_sample_or_catalog_names_ships(self):
        import json

        bodies = json.loads((ROOT / "starmap" / "catalog" / "bodies.json").read_text(encoding="utf-8"))
        for b in bodies["world"]:
            for key in ("texture", "bump"):
                if b.get(key):
                    self.assertIn(f"starmap-engine/assets/textures/{b[key]}", self.files, b[key])
            if b.get("rings"):
                self.assertIn(f"starmap-engine/assets/textures/{b['rings']['texture']}", self.files)
        self.assertIn("starmap-engine/assets/catalogs/bright_stars.json", self.files)
        self.assertIn("starmap-engine/assets/fonts/Montserrat-VF.ttf", self.files)

    def test_the_runtime_node_files_ship_and_nothing_else_from_node_modules(self):
        nm = [f for f in self.files if "/node_modules/" in f]
        self.assertEqual(len(nm), 7, nm)
        self.assertIn("starmap-engine/node_modules/three/build/three.module.min.js", self.files)
        self.assertIn("starmap-engine/node_modules/astronomy-engine/astronomy.browser.min.js", self.files)
        self.assertIn("starmap-engine/node_modules/astronomy-engine/esm/astronomy.js", self.files, "Node imports it (ERR_MODULE_NOT_FOUND)")

    def test_tests_and_samples_stay_out_and_the_python_data_ships(self):
        self.assertFalse(any("/test/" in f or "/samples/" in f for f in self.files))
        self.assertIn("starmap/packs/apollo11.json", self.files)
        self.assertIn("starmap/catalog/bodies.json", self.files)
        self.assertEqual(Path(self.files["starmap/packs/apollo11.json"]), Path("starmap/packs"))   # the OS separator either way

    def test_the_build_spec_uses_it(self):
        self.assertIn("starmap_data_files(ROOT)", (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
