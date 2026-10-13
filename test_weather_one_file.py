"""The one-file Weather plan: a Hybrid beat CSV with two more columns (data_source, extra) and row=weather rows, as one table.
Load plan splits it into the two files the rest of Weather reads (beats.csv, weather_layers.csv); the old two-part answer still loads.
No app, no network."""

import unittest

from hybrid.beat_csv import plan_from_csv
from weather.app_section import split_plan_text
from weather.sidecar import parse_sidecar

HEAD = "beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why,data_source,extra\n"
ONE = (HEAD
       + 'b1,beat,good morning everyone,map,hold,,Texas,region,,,"good morning everyone dallas stays hot this week",,,,,,,,,,,one,,\n'
       + "b1,weather,good morning everyone,,satellite,sat1,,,,,,,,,,,,end,,,,,gibs:geocolor@latest,\n"
       + 'b1,weather,dallas stays hot,,temp_marker,dal,"Dallas, TX",,,,,,,,,,,,,,,,"nws:forecast@Dallas,TX#day1",\n'
       + 'b1,weather,this week,,place_label,lbl,"Houston, TX",,,,,,,,,,,end,,,,,,"{""text"": ""Houston""}"\n'
       + 'b2,beat,feel the heat,footage,,,,,,,"feel the heat on the streets today",,,,,,,,,,,heat,,\n'
       + "b2,clip,,,,,,,,,,,,,,,,,,stock_video:heat haze over a busy city street,,the heat,,\n")
WORDS = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("good morning everyone dallas stays hot this week feel the heat on the streets today".split())]


class OneFile(unittest.TestCase):
    def test_it_splits_into_the_two_files(self):
        beats, layers = split_plan_text(ONE)
        self.assertIsNotNone(beats)
        self.assertIsNotNone(layers)
        rows = parse_sidecar(layers)
        self.assertEqual([r.id for r in rows], ["sat1", "dal", "lbl"])
        self.assertEqual(rows[0].until, "end")
        self.assertEqual(str(rows[1].data_source.target).replace(" ", ""), "Dallas,TX")
        self.assertEqual(rows[2].extra, {"text": "Houston"})
        plan = plan_from_csv(beats, WORDS, 8.0)
        self.assertEqual([b.id for b in plan.beats], ["b1", "b2"])
        self.assertEqual(len(plan.beats[1].clips), 1)

    def test_row_numbers_stay_those_of_the_one_file(self):
        bad = ONE.replace("temp_marker,dal", "temp_markr,dal")
        _beats, layers = split_plan_text(bad)
        with self.assertRaises(Exception) as cm:
            parse_sidecar(layers)
        self.assertIn("row 4", str(cm.exception))   # the header is row 1, the bad weather row is row 4 of the one file

    def test_claude_chat_answer_with_words_and_a_fence(self):
        answer = "Here is your Weather plan:\n\n```csv\n" + ONE + "```\n\nLet me know if you want changes."
        beats, layers = split_plan_text(answer)
        self.assertEqual(len(parse_sidecar(layers)), 3)
        self.assertEqual(len(plan_from_csv(beats, WORDS, 8.0).beats), 2)

    def test_row_kind_spellings(self):
        for kind in ("Weather", "weather_layer", "WX"):
            _b, layers = split_plan_text(ONE.replace(",weather,", f",{kind},"))
            self.assertEqual(len(parse_sidecar(layers)), 3, kind)

    def test_a_plan_without_weather_rows_has_no_layers(self):
        no_wx = "".join(ln + "\n" for ln in ONE.splitlines() if ",weather," not in ln)
        beats, layers = split_plan_text(no_wx)
        self.assertIsNotNone(beats)
        self.assertIsNone(layers)

    def test_a_file_that_only_mentions_the_markers_is_not_a_plan(self):
        code = 'x = split_plan_text("=== beats.csv ===\\n" + beats + "=== weather_layers.csv ===\\n" + layers)\nprint(x)\n'
        self.assertEqual(split_plan_text(code), (None, None))
        with open(__file__, encoding="utf-8") as f:   # this very test file (it was once picked in Load plan by mistake)
            self.assertEqual(split_plan_text(f.read()), (None, None))

    def test_the_one_file_wins_when_the_answer_also_mentions_the_markers(self):
        answer = "I did not use the old === beats.csv === / === weather_layers.csv === parts.\n```csv\n" + ONE + "```\n"
        beats, layers = split_plan_text(answer)
        self.assertEqual(len(parse_sidecar(layers)), 3)
        self.assertEqual(len(plan_from_csv(beats, WORDS, 8.0).beats), 2)

    def test_the_old_two_part_answer_still_loads(self):
        beats = HEAD.rsplit(",data_source,extra", 1)[0] + "\nb1,beat,good morning everyone,map,,,Texas,region,,,good morning everyone,,,,,,,,,,,one\n"
        layers = "beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\nb1,good morning,,sat1,satellite,,gibs:geocolor@latest,,end,\n"
        b, lay = split_plan_text("=== beats.csv ===\n" + beats + "=== weather_layers.csv ===\n" + layers)
        self.assertEqual(b.strip(), beats.strip())
        self.assertEqual(lay.strip(), layers.strip())


def one_file_from(beats: str, layers: str) -> str:
    """The two files of a plan written as the one-file plan (each weather row under its beat), as Claude answers in a chat."""
    import csv
    import io

    b = list(csv.reader(io.StringIO(beats)))
    lrows = list(csv.reader(io.StringIO(layers)))
    lay = [dict(zip(lrows[0], r)) for r in lrows[1:]]
    head = b[0] + ["data_source", "extra"]
    out = [head]
    for i, r in enumerate(b[1:], start=1):
        out.append(r + ["", ""])
        nxt = b[i + 1] if i + 1 < len(b) else None
        if nxt is None or (nxt[1] == "beat"):
            for w in (x for x in lay if x["beat"] == r[0]):
                cell = dict(w, row="weather", vo_anchor=w["vo_anchor"] or "good morning everyone")
                out.append([cell.get(h, "") for h in head])
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(out)
    return "Here is your Weather plan:\n\n```csv\n" + buf.getvalue() + "```\n"


import test_weather_render as _render   # noqa: E402


class TheRenderTestsOnAOneFilePlan(_render.Generate):
    """Every render test of test_weather_render, on the same plan loaded from one file."""

    def setUp(self):
        super().setUp()
        beats, layers = split_plan_text(one_file_from(_render.BEATS, _render.LAYERS))
        self.project.beats_csv.write_text(beats, encoding="utf-8")
        self.project.layers_csv.write_text(layers, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
