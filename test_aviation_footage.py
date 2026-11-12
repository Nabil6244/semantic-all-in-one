"""Aviation style step 5: footage search words, clip match rules, livery check, cut lengths, CSV rows."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from aviation import csv_rows as V
from aviation import footage as FT
from aviation import router as R


class QueryTests(unittest.TestCase):
    def q(self, text):
        return FT.queries_for(R.classify(text))

    def test_news_names_airline_event_and_year(self):
        qs = self.q("On the 5th of October 2015, Air France workers went on strike over 2,900 job cuts.")
        self.assertIn("Air France strike 2015", qs)
        self.assertLessEqual(len(qs), 3)

    def test_news_launch(self):
        qs = self.q("Then on December 1st, 2017, Air France launched a new airline.")
        self.assertEqual(qs[0], "Air France launch 2017")

    def test_fleet_names_the_type(self):
        qs = self.q("The A350 seats 292 passengers in a three-class cabin.")
        self.assertTrue(any("Airbus A350" in q for q in qs), qs)
        self.assertTrue(any("cabin" in q for q in qs), qs)

    def test_fleet_with_airline(self):
        qs = self.q("Emirates rejected brand new 777X jets.")
        self.assertEqual(qs[0], "Emirates Boeing 777X")

    def test_flight_uses_airport_and_phase(self):
        qs = self.q("They take off from Srinagar and climb towards Jammu.")
        self.assertTrue(any("Srinagar airport" in q for q in qs), qs)
        self.assertTrue(any("takeoff" in q for q in qs), qs)

    def test_weather(self):
        qs = self.q("Monsoon storm clouds with heavy hail were building over the airport.")
        self.assertTrue(any("storm" in q for q in qs), qs)

    def test_news_without_event_uses_the_sentence_words(self):
        qs = self.q("Air France described Joon as a fashion brand and a rooftop bar.")
        self.assertTrue(any("fashion" in q or "rooftop" in q for q in qs), qs)
        self.assertTrue(all(q != "Air France aircraft" for q in qs[:1]), qs)

    def test_evidence_wants_graphics_not_footage(self):
        self.assertEqual(self.q("The investigation report found the crew had not checked the latest weather."), [])


class MatchTests(unittest.TestCase):
    def test_named_type_must_be_in_the_clip(self):
        c = R.classify("The A350 seats 292 passengers in a three-class cabin.")
        self.assertTrue(FT.clip_ok("Air France Airbus A350-900 takeoff Paris CDG", c)[0])
        ok, _, why = FT.clip_ok("Boeing 737 landing at Paris", c)
        self.assertFalse(ok)
        self.assertIn("A350", why)

    def test_airline_livery_preferred(self):
        c = R.classify("Air France flies the 787 to Asia.")
        own = FT.clip_ok("Air France Boeing 787-9 landing", c)
        other = FT.clip_ok("United Boeing 787 landing", c)
        self.assertTrue(own[0] and other[0])
        self.assertGreater(own[1], other[1])

    def test_news_event_needs_the_airline(self):
        c = R.classify("In 2015 Air France workers went on strike over job cuts.")
        self.assertFalse(FT.clip_ok("Lufthansa pilots strike Frankfurt", c)[0])
        self.assertTrue(FT.clip_ok("Air France strike Paris 2015 workers", c)[0])

    def test_unnamed_sentence_takes_any_relevant_clip(self):
        c = R.classify("The airport was busy that morning.")
        self.assertTrue(FT.clip_ok("busy airport terminal passengers", c)[0])


class LiveryTests(unittest.TestCase):
    def test_livery_colours_score(self):
        navy = Image.new("RGB", (100, 60), (0, 33, 87))           # Air France navy
        grey = Image.new("RGB", (100, 60), (128, 128, 128))
        self.assertGreater(FT.livery_score(navy, "air_france"), 0.5)
        self.assertLess(FT.livery_score(grey, "air_france"), 0.05)

    def test_white_is_not_a_livery_signal(self):
        white = Image.new("RGB", (100, 60), (255, 255, 255))
        self.assertLess(FT.livery_score(white, "air_france"), 0.05)


class PacingTests(unittest.TestCase):
    def test_cut_lengths_by_mode(self):
        self.assertEqual(FT.cut_range("news"), (1.0, 2.0))
        lo, hi = FT.cut_range("fleet")
        self.assertGreaterEqual(lo, 4.0)
        self.assertGreater(FT.cut_range("flight")[1], FT.cut_range("news")[1])


class CsvTests(unittest.TestCase):
    HEADER = "scene_number,script_segment,asset_type,prompt,graphic,mode,airline,aircraft,from,to,time,fuel,altitude,article,radio\n"

    def write(self, body):
        d = tempfile.mkdtemp()
        p = Path(d) / "s.csv"
        p.write_text(self.HEADER + body, encoding="utf-8")
        return p

    def test_reads_aviation_columns(self):
        p = self.write('1,"Vistara 611 takes off from Srinagar.",youtube_video,"Vistara A320 takeoff || Srinagar airport",,flight,Vistara,A320,SXR,Jammu,13:24,4900,,,\n'
                       '2,"Air France launched Joon.",none,,,news,Air France,,,,,,,"Travel Weekly | Air France launches Joon from Paris | December 1, 2017",\n'
                       '3,"They asked to climb.",none,,,flight,,,,,,,10000,,"FIRST OFFICER: Jammu, Vistara 611, request climb || JAMMU ATC: Vistara 611, climb 7,000 feet"\n')
        rows = V.read_rows(p)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["mode"], "flight")
        self.assertEqual(rows[0]["from"], "SXR")
        self.assertEqual(rows[0]["to"], "IXJ")                     # a city name resolves to its airport
        self.assertEqual(rows[0]["aircraft"], "a320")
        self.assertEqual(rows[0]["fuel"], 4900)
        self.assertEqual(rows[0]["queries"], ["Vistara A320 takeoff", "Srinagar airport"])
        self.assertEqual(rows[1]["article"], {"outlet": "Travel Weekly", "headline": "Air France launches Joon from Paris", "date": "December 1, 2017"})
        self.assertEqual(rows[2]["radio"], [{"speaker": "FIRST OFFICER", "text": "Jammu, Vistara 611, request climb"},
                                            {"speaker": "JAMMU ATC", "text": "Vistara 611, climb 7,000 feet"}])
        self.assertEqual(rows[2]["altitude"], 10000)

    def test_bad_mode_falls_back_to_the_router(self):
        p = self.write('1,"Storm clouds and hail over the field.",none,,,banana,,,,,,,,,\n')
        r = V.read_rows(p)[0]
        self.assertEqual(r["mode"], "weather")
        self.assertIn("router", r["mode_source"])

    def test_plain_war_csv_still_reads(self):
        d = tempfile.mkdtemp()
        p = Path(d) / "w.csv"
        p.write_text('scene_number,script_segment,asset_type,prompt\n1,"Emirates ordered 777X jets.",youtube_video,"Emirates 777X"\n', encoding="utf-8")
        r = V.read_rows(p)[0]
        self.assertEqual(r["mode"], R.classify("Emirates ordered 777X jets.").mode)
        self.assertEqual(r["mode_source"], "router")
        self.assertEqual(r["aircraft"], "b777x")
        self.assertEqual(r["queries"], ["Emirates 777X"])

    def test_prompt_file_lists_every_column(self):
        txt = V.prompt_text()
        for col in V.COLUMNS:
            self.assertIn(col, txt)
        self.assertIn("SCRIPT", txt)


if __name__ == "__main__":
    unittest.main()
