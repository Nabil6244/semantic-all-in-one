"""'A post-event report is ready to make' (weather.post.suggest): warnings over, reports in, big enough, not offered before."""

import unittest
from datetime import datetime, timedelta, timezone

from weather.post.suggest import Alert, Report, episodes, suggest

UTC = timezone.utc


def T(day, hour=0, month=8):
    return datetime(2017, month, day, hour, tzinfo=UTC)


def warn(event, state, start, end):
    return {"event": event, "states": [state], "onset": start.isoformat(), "ends": end.isoformat()}


HARVEY = [warn("Hurricane Warning", "TX", T(24, 15), T(26, 21)), warn("Flash Flood Warning", "TX", T(26, 22), T(27, 10)),
          warn("Flash Flood Emergency", "TX", T(27, 4), T(28, 4)), warn("Flood Warning", "TX", T(28, 0), T(31, 18))]


class SuggestTest(unittest.TestCase):
    def test_hurricane_flooding_is_offered_once_it_is_over(self):
        s = suggest(HARVEY, [], T(2, 0, month=9))
        self.assertEqual(len(s), 1)
        x = s[0]
        self.assertEqual((x.kind, x.state, x.warnings), ("hurricane", "TX", 4))
        self.assertEqual(x.title, "Hurricane aftermath in Texas, Aug 24–31, 2017: what happened")
        self.assertEqual((x.start, x.end), (T(24, 15), T(31, 18)))
        self.assertIn("no warning in force in the state now", x.why)

    def test_not_while_a_warning_is_in_force_or_too_soon(self):
        self.assertEqual(suggest(HARVEY, [], T(31, 12)), [])                    # the flood warning is still in force
        self.assertEqual(suggest(HARVEY, [], T(31, 18) + timedelta(hours=6)), [])   # ended, but the data is not in yet
        self.assertEqual(len(suggest(HARVEY, [], T(31, 18) + timedelta(hours=24))), 1)

    def test_not_twice_and_not_stale(self):
        first = suggest(HARVEY, [], T(2, 0, month=9))[0]
        self.assertEqual(suggest(HARVEY, [], T(2, 0, month=9), already=[first.id]), [])
        self.assertEqual(suggest(HARVEY, [], T(15, 0, month=10)), [])

    def test_a_lone_warning_is_too_small(self):
        one = [warn("Flash Flood Warning", "OK", T(10, 1), T(10, 4))]
        self.assertEqual(suggest(one, [], T(12)), [])

    def test_tornado_outbreak_waits_for_storm_reports(self):
        alerts = [warn("Tornado Warning", "MS", T(5, 18, 4) + timedelta(minutes=20 * k), T(5, 19, 4) + timedelta(minutes=20 * k)) for k in range(6)]
        reps = [{"kind": "tornado", "state": "MS", "time": (T(5, 19, 4) + timedelta(minutes=10 * k)).isoformat()} for k in range(12)]
        self.assertEqual(suggest(alerts, [], T(7, 0, 4)), [])                     # no reports in yet
        self.assertEqual(suggest(alerts, reps, T(6, 12, 4)), [])                  # the last report is not a day old
        s = suggest(alerts, reps, T(7, 0, 4))
        self.assertEqual((s[0].kind, s[0].reports), ("tornado", 12))
        self.assertTrue(s[0].title.startswith("Tornado outbreak in Mississippi"))
        self.assertIn("12 storm report(s) in (preliminary)", s[0].why)

    def test_states_and_episodes_are_separate(self):
        alerts = HARVEY + [warn("Flash Flood Warning", "LA", T(29, 0), T(30, 12)), warn("Flood Warning", "LA", T(30, 0), T(31, 0)),
                           warn("Flash Flood Warning", "LA", T(30, 6), T(30, 18)),
                           warn("Hurricane Warning", "TX", T(20, 0, 9), T(21, 0, 9))]   # a later, separate episode
        eps = episodes([a for d in alerts for a in Alert.from_dict(d)])
        self.assertEqual(len(eps["TX"]), 2)
        s = suggest(alerts, [], T(3, 0, month=9))
        self.assertEqual(sorted(x.state for x in s), ["LA", "TX"])
        self.assertEqual([x.kind for x in s if x.state == "LA"], ["flood"])

    def test_input_checks(self):
        with self.assertRaisesRegex(ValueError, "needs event"):
            suggest([{"event": "Flood Warning", "states": ["TX"]}], [], T(1))
        self.assertEqual(Report.from_dict({"type": "hail", "state": "ks", "time": "2024-05-06T21:00:00Z"}).state, "KS")


if __name__ == "__main__":
    unittest.main()
