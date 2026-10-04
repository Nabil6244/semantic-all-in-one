"""The Hybrid beat CSV: a plan written as one row per beat / camera step / layer / clip / card, read back without losing anything."""

import tempfile
import unittest
from pathlib import Path

from hybrid.beat_csv import COLUMNS, import_beats, is_beat_csv, needs_words, plan_from_csv, plan_to_csv
from hybrid.plan import Beat, CameraStep, Clip, HybridPlan, Layer, PlanError, Support, validate_plan

HERE = Path(__file__).resolve().parent
HEAD = ",".join(COLUMNS) + "\n"


def R(**kw):
    """One CSV line from named columns (so tests never miscount commas)."""
    import csv
    import io

    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow([kw.get(c, "") for c in COLUMNS])
    return buf.getvalue()


def rich_plan() -> HybridPlan:
    """Every field the plan can hold, set to something other than its default."""
    b1 = Beat(id="b1", mode="map", start=0, end=12.5, purpose="where it is", narration="Lesotho sits, inside South Africa, entirely.",
              camera=[CameraStep("start", "Lesotho", "country", 0), CameraStep("push_in", "", "", 3.0, 6.0, 0.4)],
              layers=[Layer("t1", "hud_title", 0.2, label="PART 1", sub="THE KINGDOM, IN THE SKY"),
                      Layer("r1", "line", 2.0, places=["Maseru", "Leribe", "-29.3,27.5"], kind="flow", until="after_footage", params={"width": 7}),
                      Layer("s1", "stat", 4.0, value_from=0, value_to=30355.5, format="#,##0 KM²", sub="AREA", anchor="br", hold=4.5),
                      Layer("c1", "caption", 6.0, text="A country \"inside\" another", anchor="bc", until=11.25),
                      Layer("f1", "fill", 1.0, place="Lesotho", role="subject", until="end")],
              geo_intent="locate it", overlay_intent="title, route, area", confidence=0.72, findings=["map is dense"], validation="warnings",
              cam_place="Lesotho", cam_frame="country", cam_move="push_in", chapter=1)
    b2 = Beat(id="b2", mode="footage", start=12.5, end=20, purpose="what it looks like",
              clips=[Clip("stock_video:Lesotho highlands, snow", 4.0, reason="the highlands"), Clip("media/hut.jpg", kenburns=True, loop=True)],
              footage_intent="cold and high", keep_overlays=True, transition_sound="whoosh_soft", chapter=1)
    b3 = Beat(id="b3", mode="map_footage", start=20, end=30, purpose="the capital",
              layers=[Layer("m1", "marker", 21, place="Maseru", label="MASERU", role="featured")],
              support=Support("stock_image:Maseru city view", 22.0, "Maseru", "MASERU", 6.0), chapter=2)
    return HybridPlan(duration=30, beats=[b1, b2, b3], settings={"dissolve_s": 0.6, "globe_opening": False}, version=2,
                      chapters=[{"id": 1, "title": "Part one", "start": 0, "end": 20}, {"id": 2, "title": "Part two", "start": 20, "end": 30, "note": "x"}])


class TestRoundTrip(unittest.TestCase):
    def test_every_field_survives(self):
        plan = rich_plan()
        back = plan_from_csv(plan_to_csv(plan))
        self.assertEqual(back.to_dict(), plan.to_dict())

    def test_the_saved_app_fixture_survives(self):
        plan = HybridPlan.load(HERE / "test_hybrid_app_plan.json")
        self.assertEqual(plan_from_csv(plan_to_csv(plan)).to_dict(), plan.to_dict())

    def test_twice_is_stable_and_validation_agrees(self):
        plan = rich_plan()
        once = plan_to_csv(plan)
        self.assertEqual(plan_to_csv(plan_from_csv(once)), once)
        self.assertEqual(validate_plan(plan_from_csv(once)), validate_plan(plan))

    def test_a_spreadsheet_save_with_a_bom_and_blank_rows_still_loads(self):
        text = "﻿" + plan_to_csv(rich_plan()) + ",,,,\n\n"
        self.assertEqual(plan_from_csv(text).to_dict(), rich_plan().to_dict())


class TestReadable(unittest.TestCase):
    def test_one_row_per_thing_under_its_beat(self):
        lines = plan_to_csv(rich_plan()).splitlines()
        self.assertEqual(lines[0], ",".join(COLUMNS))
        kinds = [ln.split(",")[1] for ln in lines[1:]]
        self.assertEqual(kinds, ["plan", "chapter", "chapter", "beat", "camera", "camera", "layer", "layer", "layer", "layer", "layer",
                                 "beat", "clip", "clip", "beat", "layer", "card"])
        self.assertIn(R(beat="b1", row="layer", t="2", id="r1", type="line", place="Maseru;Leribe;-29.3,27.5", kind="flow", until="after_footage",
                        extra='{"params": {"width": 7}}'), plan_to_csv(rich_plan()))

    def test_an_edit_in_the_spreadsheet_is_what_loads(self):
        text = plan_to_csv(rich_plan()).replace("m1,marker,Maseru,,MASERU,", "m1,marker,Maseru,,MASERU CITY,", 1).replace("media/hut.jpg", "stock_image:a round thatched hut")
        back = plan_from_csv(text)
        self.assertEqual(back.beats[2].layers[0].label, "MASERU CITY")
        self.assertEqual(back.beats[1].clips[1].asset, "stock_image:a round thatched hut")
        self.assertTrue(back.beats[1].clips[1].kenburns)

    def test_it_is_told_apart_from_a_hybrid_import_csv(self):
        self.assertTrue(is_beat_csv(plan_to_csv(rich_plan())))
        self.assertFalse(is_beat_csv("item_no,vo_anchor,layer_type,layer_id\n1,Kenya,hud_title,t\n"))
        from app import VideoGeneratorApp as App

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"
            p.write_text(plan_to_csv(rich_plan()), encoding="utf-8")
            self.assertTrue(App._hybrid_is_beat_csv(str(p)))
            p.write_text("item_no,vo_anchor,layer_type\n", encoding="utf-8")
            self.assertFalse(App._hybrid_is_beat_csv(str(p)))


class TestProblemsNameTheRow(unittest.TestCase):
    def problems(self, text, **kw):
        with self.assertRaises(PlanError) as cm:
            plan_from_csv(text, **kw)
        return " | ".join(cm.exception.problems)

    def test_row_numbered_errors(self):
        p = self.problems(HEAD
                          + R(row="layer", t="1", id="m", type="marker", place="Maseru")                    # row 2: before any beat
                          + R(beat="b1", row="beat", mode="mapp", start="0", end="5")                       # row 3: bad mode
                          + R(beat="b2", row="beat", mode="map", start="5", end="abc")                      # row 4: bad number
                          + R(beat="b3", row="beat", mode="map", start="5", end="9", extra="{oops")         # row 5: bad JSON
                          + R(beat="b4", row="beat", mode="map", start="9", end="12", extra='{"colour": 1}')  # row 6: unknown extra
                          + R(beat="b5", row="widget", mode="map", start="12", end="14")                   # row 7: unknown row type
                          + R(beat="b5", row="beat", mode="map_footage", start="14", end="20")
                          + R(beat="b5", row="card", t="15", asset="stock_image:a")
                          + R(beat="b5", row="card", t="16", asset="stock_image:b", anchor="ml")
                          + R(beat="b5", row="card", t="17", asset="stock_image:c", anchor="br")
                          + R(beat="b5", row="card", t="18", asset="stock_image:d")                        # row 12: a fourth card
                          + R(beat="b9", row="layer", t="17", id="x", type="marker", place="Maseru", label="M"))  # row 13: wrong beat
        for want in ("row 2: a layer row must come after", "row 3: mode must be one of", "row 4: end must be a number", "row 5: the extra cell is not valid JSON",
                     "row 6: the extra cell has colour", "row 7: row must be one of", "row 12: beat b5 already has 3 photo cards", "row 13: says beat 'b9' but follows beat 'b5'"):
            self.assertIn(want, p)

    def test_not_a_beat_csv(self):
        self.assertIn("not a Hybrid beat CSV", self.problems("item_no,vo_anchor\n1,x\n"))


SCRIPT = ("Lesotho is a kingdom inside South Africa. Its capital Maseru sits on the western border. "
          "Up in the highlands, snow falls every winter and shepherds wrap themselves in blankets. "
          "Back on the map, the Orange River starts here and runs two thousand kilometres to the Atlantic.")


def words_for(text, gap=0.4):
    out, t = [], 0.0
    for w in text.split():
        out.append((w.strip(".,"), round(t, 2), round(t + 0.3, 2)))
        t += gap
    return out


WORDS = words_for(SCRIPT)
DURATION = WORDS[-1][2] + 0.5


def at(word):
    return next(s for w, s, _e in WORDS if w == word)


AI_CSV = (HEAD
          + R(beat="b1", row="beat", vo_anchor="Lesotho is", mode="map", place="Lesotho", frame="country", why="where it is")
          + R(beat="b1", row="layer", vo_anchor="Lesotho is", type="hud_title", label="PART 1", sub="THE KINGDOM IN THE SKY")
          + R(beat="b1", row="layer", vo_anchor="inside South Africa", type="fill", place="Lesotho", role="subject", until="after_footage")
          + R(beat="b2", row="beat", vo_anchor="Its capital", mode="map_footage", place="Maseru", frame="region")
          + R(beat="b2", row="layer", vo_anchor="Maseru", type="marker", place="Maseru", label="MASERU")
          + R(beat="b2", row="card", vo_anchor="western border", asset="stock_image:Maseru city view", place="Maseru", label="MASERU")
          + R(beat="b3", row="beat", vo_anchor="Up in the highlands", mode="footage", why="feel the cold")
          + R(beat="b3", row="clip", asset="stock_video:snow falling on Lesotho highlands", why="the winter")
          + R(beat="b3", row="clip", asset="stock_video:Basotho shepherd in a blanket", why="the people")
          + R(beat="b4", row="beat", vo_anchor="Back on the map", mode="map", place="Lesotho", frame="country")
          + R(beat="b4", row="layer", vo_anchor="the Orange River", type="line", place="Lesotho;-28.6,16.5", kind="river")
          + R(beat="b4", row="layer", vo_anchor="two thousand kilometres", type="stat", value_to="2000", format="#,##0 KM"))


class TestWrittenFromTheScript(unittest.TestCase):
    """A CSV an AI writes from the script (composition_styles/hybrid_beats_prompt.txt): times come from the narrator's words."""

    def test_needs_the_narration(self):
        self.assertTrue(needs_words(AI_CSV))
        self.assertFalse(needs_words(plan_to_csv(rich_plan())))
        p = TestProblemsNameTheRow.problems(self, AI_CSV)
        self.assertIn("row 2: vo_anchor needs the narration: choose the voiceover first", p)
        self.assertNotIn("must come after", p)  # the rows under a beat that failed are not reported again

    def test_beats_and_layers_land_on_their_words(self):
        got = import_beats(AI_CSV, WORDS, DURATION)
        b1, b2, b3, b4 = got.plan.beats
        self.assertEqual((b1.start, b1.end), (0.0, at("Its")))
        self.assertEqual((b2.start, b2.end, b3.start, b3.end, b4.start, b4.end), (at("Its"), at("Up"), at("Up"), at("Back"), at("Back"), DURATION))
        self.assertEqual(b2.layers[0].t, at("Maseru"))
        self.assertEqual(b2.support.t, at("western"))
        self.assertEqual(b4.layers[1].t, at("two"))  # "two thousand kilometres" found as spoken
        self.assertEqual(b4.layers[0].places, ["Lesotho", "-28.6,16.5"])
        self.assertEqual([lay.id for lay in b1.layers], ["b1_hud_title1", "b1_fill2"])
        self.assertEqual(len(b3.clips), 2)
        self.assertEqual(validate_plan(got.plan), [])

    def test_cameras_come_from_each_beats_target(self):
        plan = import_beats(AI_CSV, WORDS, DURATION).plan
        self.assertEqual([c.action for c in plan.beats[0].camera][0], "start")
        self.assertTrue(any(c.action == "fly_to" and c.place == "Maseru" for c in plan.beats[1].camera))
        self.assertEqual(plan.beats[2].camera, [])  # never under footage

    def test_exported_again_it_round_trips(self):
        plan = import_beats(AI_CSV, WORDS, DURATION).plan
        self.assertEqual(plan_from_csv(plan_to_csv(plan)).to_dict(), plan.to_dict())

    def test_anchor_problems_name_the_row(self):
        # a layer or card whose words are not found, or are spoken outside its beat, appears with its beat and says so
        bad = AI_CSV.replace('"the Orange River"', "the Zambezi River").replace("the Orange River", "the Zambezi River")
        got = import_beats(bad, WORDS, DURATION)
        self.assertTrue(any("row 12: vo_anchor 'the Zambezi River' is not in the narration" in n and "start of beat" in n for n in got.notes), got.notes)
        late = AI_CSV.replace(R(beat="b2", row="card", vo_anchor="western border", asset="stock_image:Maseru city view", place="Maseru", label="MASERU"),
                              R(beat="b2", row="card", vo_anchor="Up in the", asset="stock_image:Maseru city view", place="Maseru", label="MASERU"))
        got = import_beats(late, WORDS, DURATION)
        self.assertTrue(any("row 7: the card words are spoken at" in n for n in got.notes), got.notes)
        # a BEAT whose words come before the previous beat's still stops the import: the story order would be wrong
        back = AI_CSV.replace(R(beat="b4", row="beat", vo_anchor="Back on the map", mode="map", place="Lesotho", frame="country"),
                              R(beat="b4", row="beat", vo_anchor="Lesotho is", mode="map", place="Lesotho", frame="country"))
        self.assertIn("only spoken before the previous row", TestProblemsNameTheRow.problems(self, back, words=WORDS, duration=DURATION))

    def test_the_app_routes_it_by_header(self):
        from app import VideoGeneratorApp as App

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ai.csv"
            p.write_text(AI_CSV, encoding="utf-8")
            self.assertTrue(App._hybrid_is_beat_csv(str(p)))


class TestMapBeatWithTheSameTarget(unittest.TestCase):
    def test_a_map_beat_that_stays_where_the_camera_is_has_a_reason_to_be_on_the_map(self):
        from hybrid.validate import validate

        text = ("beat,row,start,end,mode,place,frame,type,why\n"
                "b1,beat,0,6,map,Tampa,region,,where\n"
                "b2,beat,6,12,map,Tampa,region,,still there\n")
        errors = [f for f in validate(plan_from_csv(text)) if f.severity == "error"]
        self.assertEqual([f.code for f in errors if f.code == "map_no_geography"], [])


class TestNarrationSpelling(unittest.TestCase):
    TEXT = ("beat,row,vo_anchor,mode,place,frame,type,label,format,value_to,anchor,role\n"
            "b1,beat,In Polk,map,Tampa,region,,,,,,\n"
            "b1,layer,Hardee,,\"27.49,-81.81\",,marker,HARDEE,,,,featured\n"
            "b1,layer,1.3 million acres,,,,stat,,0.0 MILLION ACRES,1.3,br,\n")

    def _words(self, text):
        from pakmap.words import estimate_words
        return estimate_words(text)

    def test_a_decimal_the_narration_wrote_as_two_numbers_and_a_name_it_spelled_its_own_way_still_match(self):
        words = self._words("In Polk and Hardy about 1 3 million acres of land and some more words after that")
        got = import_beats(self.TEXT, words, 12.0)
        self.assertEqual(len(got.plan.beats[0].layers), 2)
        self.assertTrue(any("Hardee" in n and "Hardy" in n for n in got.notes))

    def test_an_unspoken_layer_phrase_is_placed_with_its_beat_but_an_unspoken_beat_stops_the_import(self):
        words = self._words("In Polk and Marshall about 1.3 million acres of land and some more words after that")
        got = import_beats(self.TEXT.replace("Hardee", "Zanzibar"), words, 12.0)  # not stopped: the marker appears with its beat
        self.assertTrue(any("Zanzibar" in n and "start of beat" in n for n in got.notes), got.notes)
        with self.assertRaises(PlanError):  # a beat's own words must be found: they set where it starts
            import_beats(self.TEXT.replace("In Polk", "Never said"), words, 12.0)


    def test_a_beat_phrase_with_one_wrong_word_is_found_by_its_other_words(self):
        words = self._words("In Polk and Hardy about 1 3 million acres of land and some more words after that")
        text = self.TEXT.replace("In Polk", "In Polk and Harlem")
        got = import_beats(text, words, 12.0)
        self.assertTrue(any("In Polk and" in n and "found at" in n for n in got.notes), got.notes)


class TestTheNarrationCannotBeTranscribed(unittest.TestCase):
    def test_a_transcription_that_exits_becomes_an_error_the_panel_can_show(self):
        import types
        from unittest import mock

        import app as app_module

        fake = types.SimpleNamespace(_pakmap_words=None)
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "v.wav"
            wav.write_bytes(b"x")
            with mock.patch.object(app_module.vg, "transcribe_audio", side_effect=SystemExit("ERROR: whisper returned no words")):
                with self.assertRaises(RuntimeError) as cm:
                    app_module.VideoGeneratorApp._pakmap_get_words(fake, wav, "base", None, lambda m: None)
        self.assertIn("no words", str(cm.exception))


class TestPacingOfAWrittenCsv(unittest.TestCase):
    """A CSV written by hand or by an AI: the usual layer lengths, no text on top of text, and a map that keeps moving."""
    TEXT = ("beat,row,vo_anchor,mode,place,frame,type,label,text,format,value_to,anchor,why\n"
            "b1,beat,alpha one,map,Florida,region,,,,,,,start\n"
            "b1,layer,alpha one,,,,hud_title,TITLE,,,,,\n"
            "b1,layer,delta four,,,,stat,,,0.0 MILLION ACRES,1.3,br,\n"
            "b1,layer,golden seven,,,,caption,,A CAPTION,,,bc,\n"
            "b2,beat,tango forty,map,Florida,region,,,,,,,still there\n")

    def _plan(self):
        from pakmap.words import estimate_words
        words = estimate_words(" ".join(f"{w} x{i}a x{i}b x{i}c x{i}d x{i}e" for i, w in enumerate(
            ["alpha one", "bravo two", "charlie three", "delta four", "echo five", "foxtrot six", "golden seven", "hotel eight", "india nine"]
        )) + " tango forty " + " ".join(f"z{i}" for i in range(40)))
        return import_beats(self.TEXT, words, None).plan if False else import_beats(self.TEXT, words, words[-1][2] + 1).plan

    def test_a_stat_and_a_caption_keep_their_usual_time_and_never_overlap(self):
        from hybrid.compile import plan_to_rows
        p = self._plan()
        lay = {l.type: l for l in p.beats[0].layers}
        self.assertEqual(lay["stat"].hold, 4.5)
        rows, _, notes = plan_to_rows(p)
        stat = next(r for r in rows if r.layer_type == "stat")
        cap = next(r for r in rows if r.layer_type == "caption")
        self.assertTrue(stat.t_end <= cap.t_start + 1e-6 or cap.t_end <= stat.t_start + 1e-6 or stat.anchor != "br", (stat.t_start, stat.t_end, cap.t_start))

    def test_a_long_map_beat_keeps_moving_and_the_next_eases_back(self):
        p = self._plan()
        acts = [[c.action for c in b.camera] for b in p.beats]
        self.assertIn("push_in", acts[0])
        self.assertIn("fly_to", acts[1])  # the next stretch at the same place eases back out
        self.assertEqual(p.settings.get("idle_motion_min_s"), 6.0)

    def test_a_saved_plan_keeps_its_own_settings_and_is_not_given_extra_motion(self):
        p = self._plan()
        again = plan_from_csv(plan_to_csv(p))
        self.assertEqual(again.settings, p.settings)


class TestSeveralCards(unittest.TestCase):
    TEXT = ("beat,row,start,end,mode,place,frame,asset,t,label,anchor,hold\n"
            "b1,beat,0,18,map_footage,Florida,region,,,,,\n"
            "b1,card,,,,,,stock_image:phosphate rock,1,PHOSPHATE,,\n"
            "b1,card,,,,,,stock_image:a fossil shark tooth,7,SHARK TOOTH,tl,\n"
            "b1,card,,,,,,stock_image:an open pit mine,12,PIT,br,5\n")

    def test_a_beat_keeps_up_to_three_cards_and_they_round_trip(self):
        p = plan_from_csv(self.TEXT)
        b = p.beats[0]
        self.assertEqual([c.label for c in b.cards], ["PHOSPHATE", "SHARK TOOTH", "PIT"])
        self.assertEqual([c.anchor for c in b.cards], ["", "tl", "br"])
        again = plan_from_csv(plan_to_csv(p))
        self.assertEqual([(c.asset, c.t, c.anchor) for c in again.beats[0].cards], [(c.asset, c.t, c.anchor) for c in b.cards])
        from hybrid.plan import HybridPlan
        self.assertEqual(len(HybridPlan.from_dict(p.to_dict()).beats[0].cards), 3)

    def test_every_card_becomes_its_own_picture_in_its_own_corner(self):
        from hybrid.compile import plan_to_rows
        rows, _, _ = plan_to_rows(plan_from_csv(self.TEXT))
        pips = [r for r in rows if r.layer_type == "pip"]
        self.assertEqual([r.anchor for r in pips], ["tr", "tl", "br"])
        self.assertEqual([r.layer_id for r in pips], ["b1_support", "b1_support2", "b1_support3"])

    def test_every_card_is_a_row_in_the_visual_plan(self):
        from hybrid.app_integration import visual_dicts
        rows = visual_dicts(plan_from_csv(self.TEXT))
        self.assertEqual(len(rows), 3)
        self.assertIn("photo card 2/3", rows[1]["script_segment"])


if __name__ == "__main__":
    unittest.main()


class TestThePrompt(unittest.TestCase):
    """composition_styles/hybrid_beats_prompt.txt teaches by example, so its example must load and compile cleanly against its narration."""

    PROMPT = HERE / "composition_styles" / "hybrid_beats_prompt.txt"

    def parts(self):
        t = self.PROMPT.read_text(encoding="utf-8")
        script = t.split("Script:\n", 1)[1].split("\n\nCSV:", 1)[0].strip()
        csv_text = t.split("CSV:\n", 1)[1].split("\n\nNOW WRITE", 1)[0].strip() + "\n"
        return t, script, csv_text

    def test_the_header_is_the_one_demanded_and_uses_real_columns(self):
        t, _, csv_text = self.parts()
        header = csv_text.splitlines()[0]
        self.assertIn("HEADER (exactly this, in this order)\n" + header, t)
        self.assertTrue(set(header.split(",")) <= set(COLUMNS))
        self.assertTrue(is_beat_csv(csv_text))

    def test_the_example_loads_validates_and_compiles(self):
        import re

        from hybrid.compile import compile_plan
        from hybrid.validate import errors, validate

        _, script, csv_text = self.parts()
        toks = re.findall(r"[A-Za-z']+", script)
        words = [(w, round(i / 2.6, 3), round(i / 2.6 + 0.3, 3)) for i, w in enumerate(toks)]
        got = import_beats(csv_text, words, words[-1][2] + 0.5)
        plan = got.plan
        self.assertEqual([b.mode for b in plan.beats], ["map", "map_footage", "footage", "map_footage", "map"])
        self.assertEqual(validate_plan(plan), [])
        self.assertEqual([f.message for f in errors(validate(plan))], [])
        res = compile_plan(plan, validate=True)
        kinds = [e["type"] for e in res.result.spec["events"]]
        self.assertEqual(kinds.count("media_full"), 2)
        self.assertEqual(kinds.count("pip"), 5)
        self.assertIn("stat", kinds)

    def test_the_rules_that_matter_are_in_the_prompt(self):
        t = self.PROMPT.read_text(encoding="utf-8")
        for rule in ("copied EXACTLY from the script", "You do not write camera moves", "one to three card rows", "one to three clips",
                     "NEVER type the number itself", "Never use Flow sources", "Output ONLY the CSV"):
            self.assertIn(rule, t)
