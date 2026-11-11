"""The picture library is read once and kept until index.json changes (render speed 2026-11-12); a new or removed picture is still seen at once."""
from __future__ import annotations
import os, tempfile, unittest
from pathlib import Path
from unittest import mock
from PIL import Image

from reptheory import library as L


class Cache(unittest.TestCase):
    def test_register_and_removed_file_are_seen(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"REP_THEORY_ASSET_DIR": d}):
            src = Path(d) / "src.png"; Image.new("RGB", (8, 8)).save(src)
            self.assertIsNone(L.find("t_one"))
            L.register(src, id="t_one", kind="prop", subject="x", prompt="x", source="supplied")
            got = L.find("t_one"); self.assertTrue(got and Path(got["path"]).is_file())
            L.register(src, id="t_two", kind="prop", subject="y", prompt="y", source="supplied")
            self.assertIsNotNone(L.find("t_two")); self.assertIn("t_two", [e["id"] for e in L.load()])
            Path(got["path"]).unlink()
            self.assertIsNone(L.find("t_one"))      # its file went away: not handed out
            L.load()[0]["id"] = "changed"; self.assertIsNotNone(L.find("t_two"))      # callers get copies


if __name__ == "__main__":
    unittest.main()
