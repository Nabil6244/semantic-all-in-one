import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio_qc import SR, gaps, quiet_runs  # noqa: E402
from make_test_vo import plan_placement  # noqa: E402
from mix_audio import correction_plan, parse_ebur128, parse_loudnorm_json, pass2_filter  # noqa: E402

LN = """[Parsed_loudnorm_0 @ 0x1] \n{\n\t"input_i" : "-20.50",\n\t"input_tp" : "-3.10",\n\t"input_lra" : "5.20",\n\t"input_thresh" : "-31.00",\n\t"output_i" : "-14.10",\n\t"output_tp" : "-1.50",\n\t"output_lra" : "4.00",\n\t"output_thresh" : "-24.30",\n\t"normalization_type" : "dynamic",\n\t"target_offset" : "0.10"\n}\n"""
EB = "  Summary:\n\n  Integrated loudness:\n    I:         -14.2 LUFS\n    Threshold: -24.3 LUFS\n\n  Loudness range:\n    LRA:         5.1 LU\n\n  True peak:\n    Peak:       -1.3 dBFS\n"


class Tests(unittest.TestCase):
    def test_loudnorm_json(self):
        m = parse_loudnorm_json(LN)
        self.assertEqual(m["input_i"], -20.5); self.assertEqual(m["normalization_type"], "dynamic")
        f = pass2_filter(m)
        for frag in ("measured_I=-20.50", "measured_TP=-3.10", "measured_LRA=5.20", "measured_thresh=-31.00", "offset=0.10", "linear=true"):
            self.assertIn(frag, f)

    def test_ebur128(self):
        self.assertEqual(parse_ebur128(EB), {"I": -14.2, "LRA": 5.1, "TP": -1.3})

    def test_correction(self):
        self.assertEqual(correction_plan(-14.2, -1.3, tp=-1.0), (0.0, False))   # within an explicit -1.0 ceiling: untouched
        self.assertEqual(correction_plan(-14.2, -1.7), (0.0, False))            # within the default -1.5 (AAC headroom)
        self.assertTrue(correction_plan(-14.2, -1.3)[1])                        # over the default: limited
        g, lim = correction_plan(-15.8, -3.5); self.assertAlmostEqual(g, 1.8); self.assertFalse(lim)
        g, lim = correction_plan(-18.0, -2.0); self.assertTrue(lim)

    def test_placement(self):
        pl = plan_placement([0.0, 5.0, 10.0], [4.0, 5.2, 3.0], 20.0)
        self.assertFalse(pl[0]["sped_up"])
        self.assertTrue(pl[1]["sped_up"]); self.assertFalse(pl[1]["overlap"]); self.assertAlmostEqual(pl[1]["tempo"], 5.2 / 4.9, places=3)
        pl = plan_placement([0.0, 3.0], [4.0, 2.0], 10.0)
        self.assertEqual(pl[0]["tempo"], 1.15); self.assertTrue(pl[0]["overlap"])

    def test_gaps_and_quiet(self):
        s = [{"start": 1.0, "end": 2.0}, {"start": 2.3, "end": 3.0}, {"start": 4.0, "end": 5.0}]
        self.assertEqual(gaps(s, 6.0, 0.6), [(0.0, 1.0), (3.0, 4.0), (5.0, 6.0)])
        x = np.full(SR * 4, 0.1, np.float32); x[SR: int(2.0 * SR)] = 0.0; x[int(3.0 * SR): int(3.3 * SR)] = 0.0
        r = quiet_runs(x)
        self.assertEqual(len(r), 1); self.assertAlmostEqual(r[0][0], 1.0, places=1); self.assertAlmostEqual(r[0][1], 2.0, places=1)


if __name__ == "__main__":
    unittest.main()
