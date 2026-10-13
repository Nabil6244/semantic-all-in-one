"""Phase 5 broadcast compositions: the lower-third headline (words only) and place labels (a known city or a lat,lon with a name),
and Weather maps without pakMap's camera drift."""

import unittest
from types import SimpleNamespace

from weather.layers import REGISTRY, discover
from weather.layers.broadcast import build_headline, build_place, check_headline, check_place


def row(place="", **extra):
    return SimpleNamespace(id="x", place=place, extra=extra, data_source=None)


class Out:
    def __init__(self):
        self.events = []


W = SimpleNamespace(t_in=1.0, t_out=9.0)


class Broadcast(unittest.TestCase):
    def test_both_types_are_registered(self):
        discover()
        self.assertIn("headline", REGISTRY)
        self.assertIn("place_label", REGISTRY)

    def test_a_headline_is_words_only_and_upper_case(self):
        check_headline(row(kicker="Hurricane Ian", title="Landfall on the Gulf Coast", sub="September 28, 2022"))
        out = Out()
        build_headline(row(kicker="Hurricane Ian", title="Landfall  on the Gulf Coast", sub="Sep 28, 2022", tone="news"), None, W, out)
        e = out.events[0]
        self.assertEqual((e["type"], e["kicker"], e["title"], e["sub"], e["tone"]),
                         ("headline", "HURRICANE IAN", "LANDFALL ON THE GULF COAST", "SEP 28, 2022", "news"))
        self.assertEqual((e["t_in"], e["t_out"]), (1.0, 9.0))

    def test_a_headline_refuses_typed_numbers_a_missing_title_and_unknown_tones(self):
        for bad, words in [(row(title="Category 4 landfall"), "may not hold a number"), (row(kicker="Ian 2022", title="Landfall"), "kicker"),
                           (row(sub="Sep 28"), "needs extra"), (row(title="Landfall", tone="breaking"), "tone")]:
            with self.assertRaisesRegex(ValueError, words):
                check_headline(bad)

    def test_a_place_label_is_a_known_city_or_a_named_point(self):
        out = Out()
        build_place(row("Houston, TX"), None, W, out)
        build_place(row("26.64,-81.87", text="Fort Myers"), None, W, out)
        self.assertEqual(out.events[0]["text"], "HOUSTON")
        self.assertAlmostEqual(out.events[0]["lat"], 29.76, delta=0.2)
        self.assertEqual((out.events[1]["lon"], out.events[1]["lat"], out.events[1]["text"]), (-81.87, 26.64, "FORT MYERS"))
        for bad, words in [(row("Gotham, NY"), "not a known city"), (row("26.6,-81.8"), "needs extra"), (row("126.6,-81.8", text="X"), "not a latitude")]:
            with self.assertRaisesRegex(ValueError, words):
                check_place(bad)

    def test_weather_plans_have_no_camera_drift(self):
        import inspect

        from weather import generate

        self.assertIn('plan.settings.setdefault("drift_pct_per_s", 0.0)', inspect.getsource(generate.plan_layers))


if __name__ == "__main__":
    unittest.main()
