"""A stat chip draws its number at 86 px, and the engine sizes the box to number + format text: '4.5 MILLION YEARS AGO' made a 1200 px chip (project 21, 98 s).
Long words after the number now go to the small line under it; short units (KM, %, M) stay beside the number."""

from __future__ import annotations

import unittest

from hybrid.compile import plan_to_rows
from hybrid.plan import Beat, CameraStep, HybridPlan, Layer


def _stat(fmt, sub=""):
    b = Beat(id="b1", mode="map", start=0.0, end=20.0, geo_intent="x", camera=[CameraStep(action="start", place="Victoria", frame="region", t=0.0)],
             layers=[Layer(id="s", type="stat", t=5.0, value_from=0, value_to=4.5, format=fmt, sub=sub, anchor="br", hold=4.5)])
    rows, _, _ = plan_to_rows(HybridPlan(duration=20, beats=[b], settings={"ambience": False}))
    return next(r for r in rows if r.layer_type == "stat")


class TestStatSize(unittest.TestCase):
    def test_long_words_move_to_the_small_line(self):
        r = _stat("0.0 MILLION YEARS AGO", "FIRST ERUPTIONS")
        self.assertEqual(r.value_format, "0.0")
        self.assertEqual(r.sub_text, "MILLION YEARS AGO · FIRST ERUPTIONS")

    def test_long_words_with_no_sub_become_the_sub(self):
        r = _stat("0 MILLION PEOPLE")
        self.assertEqual((r.value_format, r.sub_text), ("0", "MILLION PEOPLE"))

    def test_short_units_stay_beside_the_number(self):
        for fmt in ("#,##0 KM", "0.0M", "0%", "#,##0 KM²", "0.0 °C"):
            r = _stat(fmt, "AREA")
            self.assertEqual((r.value_format, r.sub_text), (fmt, "AREA"), fmt)

    def test_a_prefix_is_left_alone(self):
        r = _stat("M0.0", "MAGNITUDE")
        self.assertEqual(r.value_format, "M0.0")


if __name__ == "__main__":
    unittest.main()
