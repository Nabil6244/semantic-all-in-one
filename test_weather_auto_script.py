"""Phase 2: the script is written from the data and says nothing the data does not (real snapshot of 2026-10-12, no network)."""

import copy
import re
import unittest
from datetime import date

from weather.automation import spoken as sp
from weather.automation.coverage import metro
from weather.automation.fetch import NATIONAL, day_date
from weather.automation.script import day_of, write_script
from weather.automation.story import pick_story

from test_weather_auto_story import alert, snapshot, with_alerts

TODAY = date(2026, 10, 12)   # the prep's Central date (evening): the forecast is for Tuesday the 13th
DATE_WORDS = re.compile(r"\b(?:[a-z]+-)?(?:" + "|".join(sorted(sp.ORDINALS.values(), key=len, reverse=True)) + r")\b")


def values(snap):
    """Every number the snapshot holds (highs, lows, chances of rain, temperatures now)."""
    out = set()
    for f in snap.forecasts.values():
        for d in f["days"]:
            for k in ("high", "low", "pop", "pop_night"):
                if d.get(k):
                    out.add(d[k]["value"])
    for o in snap.observations.values():
        out.add(o["temp"]["value"])
    return out


def value_at(snap, ref):
    if ref["field"] == "now":
        return snap.observations[ref["city"]]["temp"]["value"]
    for d in snap.forecasts[ref["city"]]["days"]:
        if day_date(d).isoformat() == ref["date"]:
            return d[ref["field"]]["value"]
    raise AssertionError(f"no day {ref['date']} for {ref['city']}")


def scripts():
    """The real day, and a few other stories built from the same data."""
    base = snapshot()
    routine = copy.deepcopy(base)
    routine.extra[NATIONAL]["alerts"] = []
    out = []
    for s in (base, routine, with_alerts(base, alert("Hurricane Warning", ["FL"], ["Miami, FL"], (25.8, -80.2))),
              with_alerts(base, *[alert("Tornado Warning", ["OK"], [], (35.5, -97.5), i) for i in range(3)])):
        st = pick_story(s)
        for seed in ("", "other-day"):
            out.append((s, st, write_script(s, st, today=TODAY, seed=seed)))
    return out


class Truth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = scripts()

    def test_every_number_said_is_in_the_snapshot_and_in_the_sentences_own_data(self):
        for snap, st, sc in self.cases:
            have = values(snap)
            for ln in sc.lines():
                text = DATE_WORDS.sub("", sp.strip_hints(ln["text"]).lower())
                refs = {r["value"] for r in ln["refs"]}
                for word, v in sp.spoken_numbers(text):
                    self.assertIn(v, have, f"{word!r} is not a number of the snapshot: {ln['text']}")
                    self.assertIn(v, refs, f"{word!r} is said without its data: {ln['text']}")
                for phrase in sp.spoken_bands(text):
                    self.assertTrue(any(sp.band(v) == phrase for v in refs), f"{phrase!r} matches none of {refs}: {ln['text']}")

    def test_each_ref_is_the_snapshot_value_and_is_said_as_written(self):
        for snap, st, sc in self.cases:
            for ln in sc.lines():
                for r in ln["refs"]:
                    self.assertEqual(r["value"], value_at(snap, r), ln["text"])
                    self.assertIn(r["said"], ln["text"])
                    self.assertTrue(r["said"] == sp.words(r["value"]) or r["said"] == f"near {sp.words(r['value'])}"
                                    or r["said"] == sp.band(r["value"]) or r["said"] == f"{sp.words(r['value'])} percent", r)

    def test_each_city_line_says_the_weather_words_of_its_own_forecast(self):
        for snap, st, sc in self.cases:
            n = 0
            for ln in sc.lines():
                highs = [r for r in ln["refs"] if r["field"] == "high" and r["said"].startswith(("near", "in the"))]
                if len(highs) != 1 or "warmest" in ln["text"]:
                    continue
                d = day_of(snap, highs[0]["city"], date.fromisoformat(highs[0]["date"]))
                self.assertIn(sp.condition_clause(d["short"]), ln["text"])
                n += 1
            self.assertGreaterEqual(n, 10)

    def test_comparisons_only_within_a_citys_own_days(self):
        for snap, st, sc in self.cases:
            text = sc.text.lower()
            for w in ("cooler", "warmer", "hotter", "colder", "than yesterday", "than normal", "above average", "below average"):
                self.assertNotIn(w, text)
            for ln in sc.lines():
                m = re.match(r"Highs (climb|drop) to ([a-z-]+(?: hundred [a-z-]+)?) by (\w+)\.", ln["text"])
                if m:
                    (r,) = ln["refs"]
                    today_hi = day_of(snap, r["city"], st.on)["high"]["value"]
                    self.assertTrue(r["value"] >= today_hi + 5 if m.group(1) == "climb" else r["value"] <= today_hi - 5, ln["text"])
                    self.assertEqual(date.fromisoformat(r["date"]).strftime("%A"), m.group(3))


class Reading(unittest.TestCase):
    def test_two_to_four_minutes_short_sentences_none_starting_with_a_number(self):
        for snap, st, sc in scripts():
            self.assertTrue(300 <= sc.word_count <= 600, sc.word_count)
            for ln in sc.lines():
                first = re.findall(r"[A-Za-z-]+", ln["text"])[0].lower()
                self.assertNotIn(first.split("-")[0], set(sp.ONES) | set(sp.TENS.values()), ln["text"])
                self.assertLessEqual(len(ln["text"].split()), 34, ln["text"])

    def test_it_opens_on_the_date_leads_with_the_story_and_ends_with_the_local_nws_office(self):
        snap = snapshot()
        st = pick_story(snap)
        sc = write_script(snap, st, today=TODAY)
        self.assertIn("Tuesday, October thirteenth", sc.sections[0].text)
        self.assertIn("heavy rain and flooding, in Utah and Arizona", sc.sections[0].text)
        self.assertIn("flood watches in effect for parts of Utah and Arizona", sc.sections[1].text)
        self.assertIn("local National Weather Service office", sc.sections[-1].text)
        self.assertIn(f"the National Weather Service {metro(st.lead_city).office_spoken} office, at weather dot gov", sc.sections[-1].text)
        self.assertEqual([s.kind for s in sc.sections][:3], ["intro", "lead", "now"])
        self.assertEqual(sum(s.kind == "footage" for s in sc.sections), 3)
        self.assertEqual({s.kind for s in sc.sections} >= {"region", "week", "trend", "warnings", "close"}, True)

    def test_the_same_day_always_reads_the_same_and_another_seed_reads_differently(self):
        snap = snapshot()
        st = pick_story(snap)
        a, b = write_script(snap, st, today=TODAY), write_script(snap, st, today=TODAY)
        c = write_script(snap, st, today=TODAY, seed="2026-10-14")
        self.assertEqual(a.text, b.text)
        self.assertNotEqual(a.text, c.text)

    def test_today_is_said_only_on_the_day_itself(self):
        snap = snapshot()
        st = pick_story(snap)
        self.assertNotIn(" today ", write_script(snap, st, today=TODAY).text)

    def test_a_pronunciation_hint_only_for_a_listed_name(self):
        base = snapshot()
        s = with_alerts(base, *[alert("Excessive Heat Warning", ["AZ"], ["Phoenix, AZ"], (33.4, -112.0), i) for i in range(3)])
        sc = write_script(s, pick_story(s), today=TODAY)
        self.assertIn("Maricopa [mair-ih-KOH-puh] County", sc.text)
        self.assertEqual(re.findall(r"\[[^\]]+\]", sc.text), ["[mair-ih-KOH-puh]"])
        self.assertNotIn("[", sp.strip_hints(sc.text))


class Spoken(unittest.TestCase):
    def test_numbers_and_bands(self):
        self.assertEqual([sp.words(n) for n in (0, 7, 40, 92, 100, 104, -5)],
                         ["zero", "seven", "forty", "ninety-two", "one hundred", "one hundred four", "five below zero"])
        self.assertEqual([sp.band(n) for n in (60, 63, 64, 66, 67, 69, 15, 100, 5)],
                         ["in the low sixties", "in the low sixties", "in the mid sixties", "in the mid sixties", "in the upper sixties",
                          "in the upper sixties", "in the mid teens", None, None])
        self.assertEqual(sp.temp(104, False), "near one hundred four")
        self.assertEqual(sp.ordinal(13), "thirteenth")
        self.assertEqual(sp.ordinal(31), "thirty-first")

    def test_certainty_words_come_from_the_nws_wording(self):
        self.assertEqual(sp.condition_clause("Slight Chance Showers And Thunderstorms"), "there is a slight chance of showers and thunderstorms")
        self.assertEqual(sp.condition_clause("Chance Rain Showers"), "there is a chance of showers")
        self.assertEqual(sp.condition_clause("Rain Showers Likely"), "showers are likely")
        self.assertEqual(sp.condition_clause("Rain"), "expect rain")
        self.assertEqual(sp.condition_clause("Patchy Fog then Mostly Sunny"), "there is patchy fog around, turning mostly sunny")
        self.assertEqual(sp.condition_clause("Sunny"), "it stays sunny")

    def test_footage_condition_of_a_day(self):
        self.assertEqual(sp.category("Chance Showers And Thunderstorms", 90, 52), "storm")
        self.assertEqual(sp.category("Chance Showers And Thunderstorms", 90, 20), "heat")       # a small chance: the heat is the story
        self.assertEqual(sp.category("Slight Chance Rain Showers then Mostly Sunny", 78, 15), "sun")
        self.assertEqual(sp.category("Snow Likely", 30, 70), "snow")
        self.assertEqual(sp.category("Patchy Fog then Sunny", 72, 0), "fog")
        self.assertEqual(sp.category("Mostly Cloudy", 62, 3), "cloud")
        self.assertEqual(sp.category("Partly Sunny", 61, 12), "cloud")
        self.assertEqual(sp.category("Sunny", 35, 0), "cold")


if __name__ == "__main__":
    unittest.main()
