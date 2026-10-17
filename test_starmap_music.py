"""StarMap's music bed: the story's mood, the whole length covered, ducked under the narrator, credited."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from starmap import music


@unittest.skipUnless(shutil.which("ffmpeg") and music.music_dir().is_dir(), "ffmpeg and assets/music are needed")
class MusicBed(unittest.TestCase):
    def test_mood_and_coverage_are_fixed_by_the_story(self):
        self.assertEqual(music.mood_of("The first launch, a record journey, the fastest craft ever"), "epic")
        self.assertEqual(music.mood_of("Nobody knows what waits in the dark silence at the edge"), "mystery")
        a, b = music.choose("a quiet story", 1200, seed="Voyager"), music.choose("a quiet story", 1200, seed="Voyager")
        self.assertEqual(a, b, "the same video always gets the same music")
        self.assertGreaterEqual(sum(music._length(music.music_dir() / f"{s}.opus") - music.CROSSFADE_S for s in a), 1200)

    def test_the_bed_dips_while_the_narrator_speaks(self):
        with tempfile.TemporaryDirectory() as d:
            voice = Path(d) / "voice.wav"
            # 4 s of "voice" (a loud tone), 4 s of silence
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=4", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                            "-filter_complex", "[0:a]volume=0.5,aresample=48000[a];[1:a]atrim=0:4[b];[a][b]concat=n=2:v=0:a=1", str(voice)], check=True)
            out, credits = music.add_music(voice, Path(d) / "out.wav", 8.0, "a quiet story", seed="t")
            self.assertTrue(out and out.is_file())
            self.assertTrue(credits and "Kevin MacLeod" in credits[0] and "Attribution 4.0" in credits[0])

            def rms(a, z):
                r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(a), "-t", str(z - a), "-i", str(out), "-f", "s16le", "-ac", "1", "-"],
                                   capture_output=True, check=True).stdout
                import array
                x = array.array("h", r)
                return (sum(v * v for v in x) / max(1, len(x))) ** 0.5
            # in the gap the music alone is heard; it is clearly present there
            self.assertGreater(rms(5.5, 7.0), 100)
