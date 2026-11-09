"""War Documentary: three render faults seen in a real film, each pinned by a synthetic check.

1. A card that crosses a segment join re-faded its dark backdrop from clear footage: 2-5 frames of the bare clip flashed at the join.
2. The round picture on a map flipped left/right of its pin every frame while the camera drifted the pin across the middle.
3. The sound layer took any file in a folder: a harsh -16.7 dB noise burst, and 5-12 s sounds chopped at 2.5 s.
"""

import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np

from cinematic_explainer import look as L
from cinematic_explainer.render import Layer
from cinematic_explainer.war import audio as A
from cinematic_explainer.war import maps_tactical as MT
from cinematic_explainer.war import segments as SG


class DimAcrossJoin(unittest.TestCase):
    def test_spans_stay_open_across_pieces(self):
        layers = [Layer("no_such_card", 0.5, 3.5, {}, dim=True)]
        first = SG.Piece(0, "clip.mp4", 0, 50, 0.0)           # 0 - 2 s
        second = SG.Piece(1, "clip.mp4", 50, 100, 2.0)        # 2 - 4 s
        self.assertEqual(SG._spans_local(first, layers), [(0.5, 3.5)])
        self.assertEqual(SG._spans_local(second, layers), [(-1.5, 1.5)])     # began earlier: no fade-in at this piece's first frame

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed")
    def test_second_piece_is_dimmed_from_its_first_frame(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            clip = tmp / "white.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=white:s={SG.W}x{SG.H}:r={SG.FPS}:d=5",
                            "-pix_fmt", "yuv420p", str(clip)], check=True)
            layers = [Layer("no_such_card", 0.5, 3.5, {}, dim=True)]
            piece = SG.Piece(1, str(clip), 50, 75, 2.0)
            out = tmp / "p.mp4"
            SG._render_piece(piece, layers, out, "h264", {}, lambda: False, [], set(), threading.Lock(), {})
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-frames:v", "3", "-vf", "scale=64:36", "-f", "rawvideo",
                                  "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
            frames = np.frombuffer(raw, np.uint8).reshape(-1, 36, 64)
            for f in frames:
                self.assertLess(float(f.mean()), 200, "bare clip flashed at the start of a piece inside a dimmed card")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _View:
    def __init__(self, x):
        self.x = x

    def pt(self, lat, lon):
        return (self.x, 300)


class InsetSide(unittest.TestCase):
    def test_side_is_fixed_while_pin_drifts_across_middle(self):
        pl = {"lat": 0, "lon": 0}

        def view_at(tt):          # the pin wobbles over the centre line
            return _View(MT.W / 2 + (8 if int(tt * 25) % 2 else -8) + 30)

        sides = {MT.inset_side(pl, 1.0, 5.0, view_at) for _ in range(5)}
        self.assertEqual(len(sides), 1)
        self.assertEqual(MT.inset_side(pl, 1.0, 5.0, lambda tt: _View(200)), 1)
        self.assertEqual(MT.inset_side(pl, 1.0, 5.0, lambda tt: _View(MT.W - 200)), -1)


class SfxChoice(unittest.TestCase):
    def test_rejects_harsh_long_and_unknown(self):
        base = {"duration": 1.0, "loudness_db": -25.0, "intensity": "medium", "spectral_character": "warm/body", "transient_character": "percussive"}
        self.assertTrue(A.sfx_ok(base))
        self.assertFalse(A.sfx_ok(dict(base, intensity="high")))
        self.assertFalse(A.sfx_ok(dict(base, spectral_character="bright/noisy", transient_character="articulated")))
        self.assertFalse(A.sfx_ok(dict(base, duration=7.3)))
        self.assertFalse(A.sfx_ok(dict(base, loudness_db=None)))
        self.assertFalse(A.sfx_ok(None))

    def test_bundled_whooshes_are_levelled_and_short(self):
        files = A._sfx_files("whoosh")
        self.assertTrue(files)
        self.assertNotIn("whoosh_010.opus", [f.name for f in files])
        cat = A._catalog()
        for f in files:
            e = cat[f"whoosh/{f.name}"]
            self.assertLessEqual(e["duration"], A.SFX_MAX_S)
            self.assertAlmostEqual(float(e["loudness_db"]) + 20 * np.log10(A.level_gain("whoosh", f)), A.SFX_TARGET_DB["whoosh"], delta=1.0)


if __name__ == "__main__":
    unittest.main()


class CardsDroppedByFfmpeg(unittest.TestCase):
    """Seen on another Mac: ffmpeg encoded a backdrop piece without its card layer and reported nothing. The render must notice and
    paint the cards on itself. Simulated by moving ffmpeg's card overlay off-screen."""

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed")
    def test_missing_card_is_found_and_painted_on(self):
        tmp = Path(tempfile.mkdtemp())
        orig = SG.piece_graph
        try:
            clip = tmp / "grey.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x404858:s={SG.W}x{SG.H}:r={SG.FPS}:d=4",
                            "-pix_fmt", "yuv420p", str(clip)], check=True)
            layers = [Layer("kit_title", 0.0, 3.0, {"text": "Subscribe to the channel"}, dim=True)]
            shots = [SG.Shot(str(clip), 0.0, 3.0, 0.0)]
            cards = SG.all_cards()
            piece = SG.plan_pieces(shots, layers)[0]

            def dropped(pc, spans):
                return orig(pc, spans).replace("overlay=format=auto", f"overlay=x={SG.W}:y={SG.H}:format=auto")

            SG.piece_graph = dropped
            out = tmp / "p.mp4"
            SG._render_piece(piece, layers, out, "x264", cards, lambda: False, [], set(), threading.Lock(), {})
            self.assertEqual(SG.verify_cards(piece, layers, out, cards), ["kit_title"])

            res = SG.render_segmented(shots, layers, str(tmp / "film.mp4"), workers=1)
            self.assertEqual(len(res["cards_repainted"]), 1)
            self.assertTrue(res["cards_repainted"][0]["fixed"])
            SG.piece_graph = orig
            self.assertEqual(SG.verify_cards(piece, layers, tmp / "film.mp4", cards), [])
        finally:
            SG.piece_graph = orig
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed")
    def test_a_good_piece_passes_the_check(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            clip = tmp / "grey.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x404858:s={SG.W}x{SG.H}:r={SG.FPS}:d=4",
                            "-pix_fmt", "yuv420p", str(clip)], check=True)
            layers = [Layer("lay_stat_split", 0.0, 3.0, {"value": 25, "suffix": "%", "sub": "Reported by Reuters"}, dim=True),
                      Layer("kit_title", 3.0, 3.9, {"text": "Next"}, dim=False)]
            res = SG.render_segmented([SG.Shot(str(clip), 0.0, 3.9, 0.0)], layers, str(tmp / "film.mp4"), workers=1)
            self.assertEqual(res["cards_repainted"], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
