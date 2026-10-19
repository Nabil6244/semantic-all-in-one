"""transcribe_audio keeps the loaded Whisper model for the next call (it was loaded from disk on every call)."""
import sys
import threading
import types
import unittest
from unittest import mock

import video_generator as vg


class _Word:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class _Seg:
    def __init__(self, words, end):
        self.words, self.end = words, end


class _FakeModel:
    built = []

    def __init__(self, size, **kw):
        _FakeModel.built.append((size, kw))
        self.size = size

    def transcribe(self, source, **kw):
        return iter([_Seg([_Word(" hello", 0.0, 0.4), _Word(" world", 0.5, 0.9)], 0.9)]), types.SimpleNamespace(duration=1.0)


class ModelReuse(unittest.TestCase):
    def setUp(self):
        _FakeModel.built = []
        vg._WHISPER_CACHE.clear()
        self.addCleanup(vg._WHISPER_CACHE.clear)
        fake_mod = types.ModuleType("faster_whisper")
        fake_mod.WhisperModel = _FakeModel
        p = mock.patch.dict(sys.modules, {"faster_whisper": fake_mod})
        p.start()
        self.addCleanup(p.stop)
        # no real ffmpeg decode: Whisper "reads the file itself"
        q = mock.patch.object(vg.hidden_subprocess, "run", side_effect=OSError("no ffmpeg in this test"))
        q.start()
        self.addCleanup(q.stop)

    def test_second_call_reuses_the_model_and_gives_the_same_words(self):
        a = vg.transcribe_audio("x.mp3", "small")
        b = vg.transcribe_audio("y.mp3", "small")
        self.assertEqual(len(_FakeModel.built), 1)
        self.assertEqual(a, b)
        self.assertEqual(a, [("hello", 0.0, 0.4), ("world", 0.5, 0.9)])

    def test_same_settings_as_before(self):
        vg.transcribe_audio("x.mp3", "base")
        size, kw = _FakeModel.built[0]
        self.assertEqual(size, "base")
        self.assertEqual(kw["device"], "cpu")
        self.assertEqual(kw["compute_type"], "int8")
        self.assertEqual(kw["num_workers"], 1)

    def test_other_size_replaces_the_model(self):
        vg.transcribe_audio("x.mp3", "small")
        vg.transcribe_audio("x.mp3", "base")
        vg.transcribe_audio("x.mp3", "base")
        self.assertEqual([s for s, _ in _FakeModel.built], ["small", "base"])

    def test_concurrent_calls_build_one_model(self):
        errors = []

        def run():
            try:
                vg.transcribe_audio("x.mp3", "small")
            except Exception as exc:   # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(len(_FakeModel.built), 1)

    def test_no_words_still_exits_and_releases_the_lock(self):
        with mock.patch.object(_FakeModel, "transcribe", return_value=(iter([]), types.SimpleNamespace(duration=1.0))):
            with self.assertRaises(SystemExit):
                vg.transcribe_audio("x.mp3", "small")
        self.assertFalse(vg._WHISPER_LOCK.locked())


if __name__ == "__main__":
    unittest.main()
