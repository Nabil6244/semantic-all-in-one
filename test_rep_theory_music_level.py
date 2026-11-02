"""The music bed sits MUSIC_UNDER_VOICE_LU under the narration whatever the voiceover's own loudness (2026-11-02: a fixed volume left it as loud as a
quiet voice in every pause, 0.9 dB apart, and the final loudness pass turned both up)."""
import tempfile, unittest
from pathlib import Path
from unittest import mock

from reptheory import sound as SND


class MusicFollowsTheVoice(unittest.TestCase):
    def gain(self, voice, bed):
        with tempfile.TemporaryDirectory() as d, mock.patch("subprocess.run"), \
             mock.patch("starmap.music.add_music", return_value=(Path(d) / "bed.wav", [])), \
             mock.patch("whatif.sound.measure_loudness", side_effect=[{"lufs": voice}, {"lufs": bed}]):
            return SND.music_gain("vo.wav", Path(d), 60.0, "text", "seed")

    def test_bed_lands_18_lu_under_the_voice(self):
        g, v, b = self.gain(-26.7, -29.9)
        import math
        self.assertAlmostEqual(b + 20 * math.log10(g / SND.MUSIC_GAIN), v - SND.MUSIC_UNDER_VOICE_LU, places=3)

    def test_a_quieter_voice_gets_quieter_music(self):
        self.assertLess(self.gain(-30.0, -29.9)[0], self.gain(-20.0, -29.9)[0])

    def test_gain_stays_in_range(self):
        self.assertGreaterEqual(self.gain(-70.0 + 1, -5.0)[0], SND.MUSIC_GAIN_RANGE[0])
