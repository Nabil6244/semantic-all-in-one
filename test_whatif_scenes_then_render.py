"""What If: Generate scenes fetches every picture and clip and stops (nothing drawn); once all are ready the button says Render."""
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

from test_whatif import timed
from whatif import app_section as ws
from unittest import mock

from whatif.app_integration import generate_whatif_video

SCRIPT = "Saturn waits at the edge of the dark. Its rings are made of ice and rock that circle the planet forever."


def _run(fetch_result, **kw):
    words = timed(SCRIPT)
    rendered = []
    with tempfile.TemporaryDirectory() as d, mock.patch("whatif.app_integration.wm.fetch", lambda *a, **k: fetch_result):
        vo = Path(d) / "vo.wav"
        with wave.open(str(vo), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\0\0" * 8000 * 12)
        r = generate_whatif_video(vo, Path(d) / "out.mp4", work_dir=Path(d) / "w", whisper_words=words, images_dir=Path(d) / "m",
                                  script=" ".join(x[0] for x in words), sound_design=False, log=lambda m: None,
                                  fetch=lambda *a, **k: fetch_result, render=lambda *a, **k: rendered.append(1), **kw)
    return r, rendered


class MediaOnly(unittest.TestCase):
    def test_scenes_are_fetched_and_nothing_is_drawn(self):
        r, rendered = _run(SimpleNamespace(media={}, unresolved=[], notes=[], credits=[]), media_only=True)
        self.assertTrue(r.ok, r.errors)
        self.assertGreater(r.media_ready, 0)
        self.assertEqual(rendered, [])
        self.assertIsNone(r.output_path)

    def test_a_scene_that_needs_attention_still_stops_with_it_listed(self):
        r, rendered = _run(SimpleNamespace(media={}, unresolved=["2"], notes=[], credits=[]), media_only=True)
        self.assertFalse(r.ok)
        self.assertEqual((r.unresolved, rendered), (["2"], []))


class Button(unittest.TestCase):
    def _app(self, ready):
        calls = {}
        app = SimpleNamespace(
            _whatif_busy=False, _whatif_running=False, _workspace=object(), _whatif_ok=None, _scene_rows=[1, 2], stage_var=SimpleNamespace(set=lambda v: None),
            hint_var=SimpleNamespace(set=lambda v: None), _current_voiceover_path=lambda: Path("v.wav"),
            _set_generate_btn=lambda **k: calls.update(k), _scenes_all_ready=lambda owner: ready and owner == ws.MODE,
            _scene_rows_owner=ws.MODE, _row_status_from_result=lambda r: "ready" if ready else "queued")
        return app, calls

    def test_generate_scenes_until_everything_is_ready_then_render(self):
        ws._sync_card_button = lambda app: None
        for ready, text in ((False, "Generate scenes"), (True, "Render")):
            app, calls = self._app(ready)
            ws.sync_cta(app)
            self.assertEqual(calls["text"], text)


if __name__ == "__main__":
    unittest.main()
