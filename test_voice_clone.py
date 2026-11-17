"""voice_clone: sample checks, window splitting, saved voices, the synthesize(convert=...) hook. No network, no model download."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

import edge_voiceover as ev
from voice_clone import engine

FFMPEG = shutil.which("ffmpeg")


def _speechlike(seconds: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * engine.SR)) / engine.SR
    return (amp * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)


class AudioHelperTests(unittest.TestCase):
    def test_speech_seconds_ignores_silence(self):
        a = np.concatenate([_speechlike(5), np.zeros(engine.SR * 10, np.float32), _speechlike(3)])
        self.assertAlmostEqual(engine.speech_seconds(a), 8.0, delta=0.6)
        self.assertEqual(engine.speech_seconds(np.zeros(100, np.float32)), 0.0)

    def test_windows_cover_everything_and_stay_short(self):
        a = _speechlike(100)
        a[int(31 * engine.SR): int(31.4 * engine.SR)] = 0   # a quiet gap the cut should pick
        wins = engine.split_windows(a, 30.0)
        self.assertEqual(sum(w.size for w in wins), a.size)
        self.assertTrue(all(w.size <= 30 * engine.SR for w in wins))
        self.assertGreaterEqual(len(wins), 4)
        self.assertEqual(len(engine.split_windows(_speechlike(10), 30.0)), 1)


class VoiceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.old = os.environ.get("VIDEOGEN_VOICE_CLONE")
        os.environ["VIDEOGEN_VOICE_CLONE"] = self.tmp
        self.addCleanup(lambda: os.environ.pop("VIDEOGEN_VOICE_CLONE", None) if self.old is None else os.environ.__setitem__("VIDEOGEN_VOICE_CLONE", self.old))

    def test_list_and_delete(self):
        d = Path(self.tmp) / "voices" / "Mine"
        d.mkdir(parents=True)
        (d / "voice.json").write_text('{"name": "Mine"}')
        self.assertEqual(engine.list_voices(), [])        # no embedding yet
        (d / "se.pt").write_bytes(b"x")
        self.assertEqual(engine.list_voices(), [("Mine", str(d / "se.pt"))])
        engine.delete_voice("Mine")
        self.assertEqual(engine.list_voices(), [])

    def test_models_not_ready_when_empty(self):
        self.assertFalse(engine.models_ready())


@unittest.skipUnless(FFMPEG, "ffmpeg not installed")
class SampleCheckTests(unittest.TestCase):
    def _wav(self, tmp, seconds):
        p = os.path.join(tmp, f"s{seconds}.wav")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f=200:d={seconds}", p], check=True)
        return p

    def test_short_sample_rejected_and_long_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, msg, _ = engine.check_sample(self._wav(tmp, 2), FFMPEG)
            self.assertFalse(ok)
            self.assertIn("at least", msg)
            ok, msg, audio = engine.check_sample(self._wav(tmp, 25), FFMPEG)
            self.assertTrue(ok, msg)
            self.assertGreater(audio.size, 20 * engine.SR)
            ok, msg, _ = engine.check_sample(os.path.join(tmp, "nope.wav"), FFMPEG)
            self.assertFalse(ok)


@unittest.skipUnless(FFMPEG, "ffmpeg not installed")
class ConvertHookTests(unittest.TestCase):
    def test_every_piece_goes_through_convert_and_timings_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tone = os.path.join(tmp, "tone.mp3")
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=300:d=1", "-c:a", "libmp3lame", tone], check=True)
            data = Path(tone).read_bytes()

            class Comm:
                def __init__(self, text, voice, **kw):
                    pass

                async def stream(self):
                    yield {"type": "audio", "data": data}
                    yield {"type": "WordBoundary", "text": "hi", "offset": 0, "duration": 5_000_000}

            import types
            fake = types.SimpleNamespace(Communicate=Comm)
            import sys
            sys.modules["edge_tts"] = fake
            self.addCleanup(sys.modules.pop, "edge_tts", None)
            seen, ticks = [], []

            def convert(src, dst):
                seen.append(src)
                shutil.copy(src, dst)

            text = " ".join(f"Sentence {i} is here." for i in range(300))
            out = os.path.join(tmp, "out.mp3")
            res = ev.synthesize(text, out, ffmpeg=FFMPEG, ffprobe=shutil.which("ffprobe"), convert=convert,
                                convert_progress=lambda d, t: ticks.append((d, t)))
            self.assertEqual(len(seen), res["pieces"])
            self.assertGreaterEqual(res["pieces"], 2)
            self.assertEqual(ticks[-1], (res["pieces"], res["pieces"]))
            self.assertTrue(os.path.getsize(out) > 0)
            words = __import__("json").loads(Path(res["words_path"]).read_text())
            self.assertEqual(len(words), res["pieces"])

    def test_empty_conversion_is_an_error(self):
        with self.assertRaises(RuntimeError):
            ev._convert_pieces([("a.mp3", [])], lambda s, d: None, tempfile.gettempdir(), None)


FAKE_WORKER = """
import json, sys, wave, math
job = json.load(open(sys.argv[1]))
print(json.dumps({"ready": "cpu", "model": "fake"}), flush=True)
for i, p in enumerate(job["pieces"]):
    with wave.open(p["out"], "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"".join(int(8000 * math.sin(i + n / 20)).to_bytes(2, "little", signed=True) for n in range(12000)))
    print(json.dumps({"done": i, "seconds": 0.5}), flush=True)
"""


@unittest.skipUnless(FFMPEG, "ffmpeg not installed")
class ChatterboxTests(unittest.TestCase):
    def setUp(self):
        from voice_clone import chatterbox_engine as cbx
        self.cbx = cbx
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _patch_worker(self, body):
        import sys
        w = Path(self.tmp) / "worker.py"
        w.write_text(body)
        old = (self.cbx.env_python, self.cbx.worker_path)
        self.cbx.env_python, self.cbx.worker_path = (lambda: Path(sys.executable)), (lambda: w)
        self.addCleanup(lambda: setattr(self.cbx, "env_python", old[0]) or setattr(self.cbx, "worker_path", old[1]))

    def test_reference_drops_leading_silence_and_is_capped(self):
        src = os.path.join(self.tmp, "s.wav")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=3", "-f", "lavfi",
                        "-i", "sine=f=200:d=40:sample_rate=24000", "-filter_complex", "[0][1]concat=n=2:v=0:a=1", src], check=True)
        dest = self.cbx.save_reference(src, Path(self.tmp) / "ref.wav", FFMPEG)
        import wave
        with wave.open(str(dest)) as w:
            sec = w.getnframes() / w.getframerate()
        self.assertLessEqual(sec, self.cbx.REF_SECONDS + 0.01)
        self.assertGreater(sec, 11)          # a pure tone has no pause, so the cut lands at the earliest allowed point
        a = engine.read_audio(str(dest), FFMPEG, seconds=0.2)
        self.assertGreater(float(np.abs(a).max()), 0.1)     # starts on the voice, not on silence

    def test_every_piece_is_made_and_joined(self):
        self._patch_worker(FAKE_WORKER)
        ref = Path(self.tmp) / "ref.wav"
        engine.write_wav(_speechlike(6), str(ref))
        ticks = []
        text = " ".join(f"Sentence number {i} is right here." for i in range(40))
        out = os.path.join(self.tmp, "out.mp3")
        res = self.cbx.synthesize(text, out, str(ref), speed=1.1, ffmpeg=FFMPEG, ffprobe=shutil.which("ffprobe"),
                                  progress=lambda d, t: ticks.append((d, t)))
        self.assertGreaterEqual(res["pieces"], 4)
        self.assertEqual(ticks[-1], (res["pieces"], res["pieces"]))
        self.assertGreater(res["duration"], 0.4 * res["pieces"])
        self.assertEqual(__import__("json").loads(Path(res["words_path"]).read_text()), [])

    def test_worker_failure_and_missing_sample_are_errors(self):
        self._patch_worker('import json; print(json.dumps({"error": "boom"}))')
        ref = Path(self.tmp) / "ref.wav"
        engine.write_wav(_speechlike(6), str(ref))
        with self.assertRaisesRegex(RuntimeError, "boom"):
            self.cbx.synthesize("Hello there.", os.path.join(self.tmp, "o.mp3"), str(ref), ffmpeg=FFMPEG)
        with self.assertRaisesRegex(RuntimeError, "add the voice again"):
            self.cbx.synthesize("Hello there.", os.path.join(self.tmp, "o.mp3"), os.path.join(self.tmp, "none.wav"), ffmpeg=FFMPEG)


if __name__ == "__main__":
    unittest.main()
