"""Weather: Generate scenes fetches the footage and stops; the button says Render once every clip is ready."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from weather import app_section as ws


class Button(unittest.TestCase):
    def _text(self, ready):
        calls = {}
        app = SimpleNamespace(
            _weather_busy=False, _weather_running=False, _workspace=object(), _weather_ok=None, _scene_rows=[1, 2],
            stage_var=SimpleNamespace(set=lambda v: None), hint_var=SimpleNamespace(set=lambda v: None),
            _current_voiceover_path=lambda: Path("v.wav"), _set_generate_btn=lambda **k: calls.update(k),
            _scenes_all_ready=lambda owner: ready and owner == "weather")
        with mock.patch.object(ws, "has_plan", return_value=True), mock.patch.object(ws, "is_auto", return_value=True), \
                mock.patch.object(ws, "project", return_value=SimpleNamespace()):
            ws.sync_cta(app)
        return calls["text"]

    def test_generate_scenes_until_ready_then_render(self):
        self.assertEqual(self._text(False), "Generate scenes")
        self.assertEqual(self._text(True), "Render")


class MediaReady(unittest.TestCase):
    def test_the_forecast_numbers_file_is_not_written_for_a_scenes_only_run(self):
        import inspect

        from weather import generate

        src = inspect.getsource(generate.generate_forecast_video)
        self.assertIn('not getattr(result, "media_ready", 0)', src)

    def test_news_doc_draws_nothing_when_only_the_clips_were_fetched(self):
        import inspect

        from weather.newsdoc import generate

        self.assertIn('getattr(result, "media_ready", 0)', inspect.getsource(generate.generate_newsdoc_video))


if __name__ == "__main__":
    unittest.main()
