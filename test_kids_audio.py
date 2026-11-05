"""Preschool audio engine (kids_audio): seamless beds, event-placed effects, voice-first mixing, off switches."""
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from kids_audio import library as L
from kids_audio import mixer
from kids_audio.synth import SR


# plain unittest (CI runs unittest and has no pytest): one library build for the module, a fresh temp folder per test
_MAN = None


def _man():
    global _MAN
    if _MAN is None:
        _MAN = L.build()
    return _MAN


def _check_library_has_every_bed_and_effect(man):
    assert set(man["beds"]) >= {"playroom", "calm", "sunny"}
    assert set(man["sfx"]) >= {"pop", "sparkle", "chime", "success", "drumroll"} | {f"ding_{i}" for i in range(1, 11)}
    for e in list(man["beds"].values()) + list(man["sfx"].values()):
        assert os.path.exists(os.path.join(L.LIB, e["file"]))


def _check_beds_loop_without_a_click(man, bed):
    x = L.read_audio(os.path.join(L.LIB, man["beds"][bed]["file"]))
    jump = np.abs(x[:, 0] - x[:, -1]).max()                     # end -> start, as the loop repeats
    steps = np.abs(np.diff(x, axis=1)).max(0)
    assert jump <= np.percentile(steps, 99.9), f"{bed}: boundary step {jump:.4f} is unusually large"
    assert np.abs(x).max() < 0.99


def _voice(tmp_path, n_sec=8.0):
    """Synthetic 'speech': 300 Hz bursts from 2-4 s and 5-7 s, silence elsewhere."""
    t = np.arange(int(n_sec * SR)) / SR; on = ((t > 2) & (t < 4)) | ((t > 5) & (t < 7))
    v = 0.3 * np.sin(2 * np.pi * 300 * t) * on; x = np.stack([v, v])
    p = str(tmp_path / "voice.wav"); L.write_wav(p, x)
    return p, x


def _rms_db(a):
    return 20 * np.log10(np.sqrt((a ** 2).mean()) + 1e-12)


def _check_music_ducks_under_speech_and_voice_stays_untouched(tmp_path, man):
    vp, v = _voice(tmp_path); out = str(tmp_path / "mix.wav")
    rep = mixer.mix({"voice": vp, "out": out, "duration": 8.0, "voice_lufs": -14, "target_lufs": None, "music": {"bed": "playroom", "fade_in": 0.1, "fade_out": 0.1}, "sfx": []})
    m = L.read_audio(out)[:, : v.shape[1]]; music = m - v                     # with no mastering gain the voice bus is passed through as-is
    gap, speech = music[:, int(0.5 * SR):int(1.8 * SR)], music[:, int(2.5 * SR):int(3.8 * SR)]
    assert _rms_db(gap) - _rms_db(speech) > 7, "music should dip clearly while she speaks"
    assert rep["voice_over_music_db"]["worst_5pct"] > 12
    assert rep["peak_dbfs"] <= -0.99


def _check_effects_land_on_their_events(tmp_path, man):
    out = str(tmp_path / "fx.wav")
    mixer.mix({"voice": None, "out": out, "duration": 4.0, "target_lufs": None, "music": None, "sfx": [{"t": 1.5, "name": "pop"}, {"t": 3.0, "name": "ding_3"}]})
    x = np.abs(L.read_audio(out)).max(0); onset = lambda a, b: np.argmax(x[int(a * SR):int(b * SR)] > 0.02) / SR + a
    assert abs(onset(1.0, 2.0) - 1.5) < 0.01 and abs(onset(2.5, 3.5) - 3.0) < 0.01
    assert x[: int(1.4 * SR)].max() < 1e-4, "nothing plays before the first event"


def _check_music_and_effects_off_return_the_voice(tmp_path, man):
    vp, v = _voice(tmp_path); out = str(tmp_path / "off.wav")
    rep = mixer.mix({"voice": vp, "out": out, "duration": 8.0, "music": None, "sfx": []})
    assert rep["music"] is None and rep["sfx"] == 0
    assert np.abs(L.read_audio(out)[:, : v.shape[1]] - v).max() < 1e-6


def _bursts(tmp_path, starts, lens):
    """A fake TTS line: 220 Hz 'words' at irregular times."""
    n = int((max(s + l for s, l in zip(starts, lens)) + 0.3) * SR); x = np.zeros(n); t = np.arange(n) / SR
    for s, l in zip(starts, lens):
        on = (t >= s) & (t < s + l); x[on] = 0.4 * np.sin(2 * np.pi * 220 * t[on])
    p = str(tmp_path / "line.wav"); L.write_wav(p, np.stack([x, x]))
    return p


def _check_chant_puts_every_word_on_the_beat(tmp_path, man):
    from kids_audio.chant import chant
    starts, lens = [0.10, 0.47, 0.73, 1.21, 1.60, 1.83], [0.25, 0.2, 0.3, 0.9, 0.15, 0.2]       # "four" is too long for its beat
    words = [{"text": w, "t0": s, "t1": s + l} for w, s, l in zip(["One,", "two,", "three,", "four!", "with", "me!"], starts, lens)]
    r = chant({"voice": _bursts(tmp_path, starts, lens), "words": words, "bpm": 120, "out": str(tmp_path / "c.wav")})
    beat = 0.5; assert [w["t0"] / beat for w in r["words"]] == [0, 1, 2, 3, 4, 4.5]   # "with me" share a beat
    assert r["beats"] == 8 and abs(r["dur"] - (8 * beat + 0.4)) < 1e-6                # each sentence fills its bar
    x = np.abs(L.read_audio(r["file"])).max(0)
    ws = r["words"]
    for k, w in enumerate(ws):                                                        # the audible onset sits on the beat
        if k and ws[k - 1]["t1"] > w["t0"] - 0.05:
            continue                                                                  # no silence before it to measure from
        i = int(w["t0"] * SR); lo = max(0, i - int(0.05 * SR)); seg = x[lo:i + int(0.05 * SR)]
        assert abs((lo + np.argmax(seg > 0.04)) / SR - w["t0"]) < 0.012, w
    four = x[int(1.5 * SR):int(2.0 * SR)]; assert four.max() > 0.1 and x[int(1.995 * SR):int(2.0 * SR)].max() < 0.05, "a long word is fitted into its beat"


class KidsAudio(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_library_has_every_bed_and_effect(self):
        _check_library_has_every_bed_and_effect(_man())

    def test_beds_loop_without_a_click(self):
        for bed in ("playroom", "calm", "sunny"):
            with self.subTest(bed):
                _check_beds_loop_without_a_click(_man(), bed)

    def test_music_ducks_under_speech_and_voice_stays_untouched(self):
        _check_music_ducks_under_speech_and_voice_stays_untouched(self.tmp, _man())

    def test_effects_land_on_their_events(self):
        _check_effects_land_on_their_events(self.tmp, _man())

    def test_music_and_effects_off_return_the_voice(self):
        _check_music_and_effects_off_return_the_voice(self.tmp, _man())

    def test_chant_puts_every_word_on_the_beat(self):
        _check_chant_puts_every_word_on_the_beat(self.tmp, _man())


if __name__ == "__main__":
    unittest.main()
