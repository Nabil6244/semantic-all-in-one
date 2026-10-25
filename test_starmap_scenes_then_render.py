"""StarMap: Generate gets the scenes and stops, Render draws; the table decides which button shows. No network, no renderer."""

import struct
import tempfile
import unittest
import wave
from pathlib import Path

from starmap.app_integration import generate_starmap_video
from starmap.media import Fetched

from test_starmap_media import S, WORDS


class ScenesThenRender(unittest.TestCase):
    def _vo(self, tmp):
        vo = tmp / "vo.wav"
        with wave.open(str(vo), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(struct.pack("<h", 0) * 16000 * 55)
        return vo

    def test_media_only_fetches_and_draws_nothing(self):
        tmp = Path(tempfile.mkdtemp())
        drawn = []
        res = generate_starmap_video(S / "apollo11_beats.csv", self._vo(tmp), tmp / "final.mp4", work_dir=tmp / "work", whisper_words=WORDS,
                                     images_dir=tmp / "media", fetch=lambda plan, d, **kw: Fetched(), render=lambda *a, **k: drawn.append(1),
                                     log=lambda m: None, media_only=True)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(drawn, [], "nothing is drawn until the author clicks Render")
        self.assertIsNone(res.output_path)
        self.assertFalse((tmp / "final.mp4").exists())

    def test_the_table_decides_render_or_generate_scenes(self):
        import app

        class Row:
            def __init__(self, n): self.scene_number = n

        class Fake:
            _scene_rows_owner = "starmap"
            _scene_rows = [Row("1"), Row("2")]
            statuses = {"1": "ready", "2": "skipped"}

            def _row_status_from_result(self, r): return self.statuses[r.scene_number]

        f = Fake()
        ready = lambda: app.VideoGeneratorApp._scenes_all_ready(f, "starmap")
        self.assertTrue(ready())
        for bad in ("queued", "needs_action", "cancelled", "failed"):
            f.statuses["2"] = bad
            self.assertFalse(ready(), bad)
        f.statuses["2"] = "ready"
        f._scene_rows_owner = "hybrid"
        self.assertFalse(ready(), "another style's table is not this style's scenes")
        f._scene_rows_owner, f._scene_rows = "starmap", []
        self.assertFalse(ready(), "an empty table is not 'every scene ready'")


if __name__ == "__main__":
    unittest.main()
