"""The Explainer's finishing pass: portraits of named people, the in-world echo line, places that are not places, the finishing step after the map is drawn."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from explainer.director import portraits as PO
from explainer.director import select as SL
from explainer import integration as IT

SCRIPT = ("Venice sat on a lagoon. In 1498 Portuguese explorer Vasco da Gama reached India. Later the Venetian Republic fell in the Eastern Mediterranean. "
          "In 1797 Napoleon Bonaparte entered the Ottoman Empire's old rival. The Middle East and the Adriatic Sea mattered.")


class People(unittest.TestCase):
    def test_names_of_people_only(self):
        self.assertEqual(PO.people(SCRIPT, ["Venice", "India"]), ["Vasco da Gama", "Napoleon Bonaparte"])

    def test_vet_needs_the_name_and_old_art(self):
        ok = SimpleNamespace(extra={"alt": "Portrait of Napoleon Bonaparte", "tags": "painting"}, source_url="https://commons.wikimedia.org/wiki/File:Napoleon_Bonaparte.jpg", url="x.jpg", width=900, height=1200)
        self.assertIsNotNone(PO._vet("Napoleon Bonaparte", ok))
        wrong = SimpleNamespace(extra={"alt": "Portrait of Wellington", "tags": "painting"}, source_url="https://commons.wikimedia.org/wiki/File:Wellington.jpg", url="x.jpg", width=900, height=1200)
        self.assertIsNone(PO._vet("Napoleon Bonaparte", wrong))
        modern = SimpleNamespace(extra={"alt": "Napoleon Bonaparte actor in a film", "tags": "portrait"}, source_url="", url="x.jpg", width=900, height=1200)
        self.assertIsNone(PO._vet("Napoleon Bonaparte", modern))
        photo = SimpleNamespace(extra={"alt": "Napoleon Bonaparte statue", "tags": ""}, source_url="", url="x.jpg", width=300, height=300)
        self.assertIsNone(PO._vet("Napoleon Bonaparte", photo))

    def test_offline_gives_nothing_and_never_raises(self):
        import explainer.director.portraits as P
        import providers.stock.openverse as OV

        class Dead(OV.OpenverseBackend):
            def search(self, *a, **k):
                raise RuntimeError("offline")
        old = OV.OpenverseBackend
        OV.OpenverseBackend = Dead
        try:
            with tempfile.TemporaryDirectory() as d:
                self.assertIsNone(P.build_library(SCRIPT, ["Venice"], d))
        finally:
            OV.OpenverseBackend = old


class Places(unittest.TestCase):
    def test_common_words_are_not_places(self):
        ok, ignored = SL.resolve_places(["Republic", "Empire", "Venice"])
        self.assertNotIn("Republic", ok)
        self.assertNotIn("Empire", ok)
        self.assertIn("Venice", ok)


class Finishing(unittest.TestCase):
    def test_no_report_keeps_the_video(self):
        with tempfile.TemporaryDirectory() as d:
            out = IT.post_render(Path(d) / "v.mp4", d, None)
        self.assertEqual(str(out["video"]), str(Path(d) / "v.mp4"))
        self.assertIsNone(out["audio"])

    def test_bad_report_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "explainer").mkdir()
            (Path(d) / "explainer" / "render_report.json").write_text("{not json")
            out = IT.post_render(Path(d) / "v.mp4", d, None)
        self.assertIsNone(out["audio"])

    def test_full_look_has_no_stock_footage(self):
        self.assertEqual(IT.full_look({})["explainer_footage_share"], 0.0)


if __name__ == "__main__":
    unittest.main()
