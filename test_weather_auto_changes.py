"""Phase 2: what changed since the prep, in plain words, and the script lines that say the changed numbers."""

import copy
import unittest
from datetime import datetime, timezone

from weather.automation.changes import ChangeReport, diff, diff_alerts, lines_to_rerecord
from weather.automation.fetch import NATIONAL
from weather.automation.script import write_script
from weather.automation.story import pick_story

from test_weather_auto_script import TODAY
from test_weather_auto_story import alert, snapshot

UTC = timezone.utc


def day(snap, key, iso):
    return next(d for d in snap.forecasts[key]["days"] if d["start"][:10] == iso)


def area(i, event, counties=("48201",), ends=""):
    return {"id": i, "event": event, "severity": "Severe", "headline": "", "sent": "2026-10-12T20:00:00+00:00",
            "expires": "2026-10-13T20:00:00+00:00", "ends": ends, "sender": "", "how": "counties", "polys": [], "counties": list(counties)}


class Diff(unittest.TestCase):
    def setUp(self):
        self.old = snapshot()
        self.new = copy.deepcopy(self.old)

    def test_no_change_says_so(self):
        self.assertEqual(diff(self.old, self.new), [])
        self.assertIn("No changes since the prep", ChangeReport([]).text)

    def test_changed_numbers_and_weather_words_are_named_by_city_and_day(self):
        day(self.new, "Dallas, TX", "2026-10-13")["high"]["value"] = 94
        day(self.new, "Boston, MA", "2026-10-13")["pop"]["value"] = 70
        day(self.new, "Houston, TX", "2026-10-14")["short"] = "Chance Showers And Thunderstorms"
        day(self.new, "Seattle, WA", "2026-10-13")["pop"]["value"] = 15   # 12% -> 15%: both too small to be said or shown
        self.new.observations["Phoenix, AZ"]["temp"]["value"] += 2
        texts = [c.text for c in diff(self.old, self.new)]
        self.assertIn("Dallas Tuesday high 92° → 94°", texts)
        self.assertIn("Boston Tuesday chance of rain 54% → 70%", texts)
        self.assertIn("Houston Wednesday: Sunny → Chance Showers And Thunderstorms", texts)
        self.assertIn("Phoenix now 81° → 83° (observed)", texts)
        self.assertFalse([t for t in texts if t.startswith("Seattle")])

    def test_new_and_ended_alerts(self):
        old = {"TX": {"areas": [area("a", "Flood Warning", ends="2026-10-13T03:00:00+00:00"), area("b", "Flood Watch")]}}
        new = {"TX": {"areas": [area("a", "Flood Warning", ends="2026-10-13T03:00:00+00:00"), area("c", "Flash Flood Warning", ("48113",))]}}
        out = []
        diff_alerts(old, new, out, now=datetime(2026, 10, 13, 4, 0, tzinfo=UTC))
        texts = [c.text for c in out]
        self.assertIn("new: Flash Flood Warning for Dallas County, Texas", texts)
        self.assertIn("ended: Flood Watch for Harris County, Texas", texts)
        self.assertIn("ended: Flood Warning for Harris County, Texas", texts)   # still listed, but past its end time

    def test_national_warnings_that_came_or_went(self):
        self.new.extra[NATIONAL]["alerts"] = [a for a in self.new.extra[NATIONAL]["alerts"] if a["event"] != "Flood Watch"] + [
            alert("Tornado Watch", ["OK"])]
        texts = [c.text for c in diff(self.old, self.new)]
        self.assertIn("new: Tornado Watch for test area", texts)
        self.assertEqual(sum(t.startswith("ended: Flood Watch") for t in texts), 3)


class Lines(unittest.TestCase):
    def test_the_lines_to_rerecord_are_the_ones_that_say_the_changed_numbers(self):
        old = snapshot()
        st = pick_story(old)
        sc = write_script(old, st, today=TODAY)
        new = copy.deepcopy(old)
        day(new, "Dallas, TX", "2026-10-13")["high"]["value"] = 95   # said in the intro (warmest city) and the Texas line
        new.extra[NATIONAL]["alerts"] = [a for a in new.extra[NATIONAL]["alerts"] if a["event"] != "Flood Watch"]
        changes = diff(old, new)
        lines = lines_to_rerecord(changes, sc.lines())
        said = [ln["text"] for ln in lines]
        self.assertTrue(any(t.startswith("The warmest of our big cities is Dallas") for t in said), said)
        self.assertTrue(any(t.startswith("In Dallas,") for t in said), said)
        self.assertTrue(any("flood watches in effect" in t for t in said), said)
        self.assertFalse(any("Seattle" in t and "Dallas" not in t for t in said))
        rep = ChangeReport(changes, lines)
        self.assertIn("Script lines to re-record:", rep.text)
        self.assertIn("Dallas Tuesday high 92° → 95°", rep.text)


if __name__ == "__main__":
    unittest.main()
