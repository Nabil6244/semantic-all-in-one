"""Horror story sounds (Step 2): every horror bed the director can name exists in the mixer, and every horror sound synthesizes."""
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'tools'))


class HorrorAudio(unittest.TestCase):
    def test_beds_exist(self):
        import mix_audio as M
        for bed in ('horror_street', 'horror_rain', 'horror_room', 'horror_room_rain'):
            self.assertIn(bed, M.BEDS)
            self.assertEqual(M.BEDS[bed][1], 'drone')

    def test_sounds_render(self):
        import sfx_synth as S
        for cue in ('drone', 'phone_ring', 'paper_rustle', 'door_chime', 'footsteps_slow', 'whisper_name'):
            x = S.render(cue, 4.0, 3)
            self.assertIsNotNone(x, cue)
            self.assertTrue(np.isfinite(x).all() and 0.5 < float(np.max(np.abs(x))) <= 0.91, cue)


if __name__ == '__main__':
    unittest.main()
