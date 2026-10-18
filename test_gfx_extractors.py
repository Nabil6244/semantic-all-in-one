"""The automatic graphics that come from what the narration says besides a number (gfx_extractors): quotes, named people, places, numbered facts,
records, timelines and comparisons. Nothing is ever invented: a missing piece means no graphic. Run: python -m unittest test_gfx_extractors"""
import unittest

import gfx_templates as G
from pakmap.compile import compile_csv
from pakmap.words import estimate_words

LEAD = "Canada is a vast country with many surprises waiting for anyone who looks at it closely. "
TAIL = " Then the story moves on to other things entirely."
PLACES = {"Halifax": (-63.6, 44.6), "Nova Scotia": (-63.0, 45.0), "Canada": (-98.0, 60.0), "Alberta": (-114.0, 54.0)}
resolve = lambda name: PLACES.get(name)


def auto(text, **kw):
    kw.setdefault("niche", "map")
    return G.auto_events(estimate_words(text), **kw)


def ids(evs):
    return [e["template"]["id"] for e in evs]


class TestSentences(unittest.TestCase):
    def test_a_title_does_not_end_a_sentence(self):
        s = G.sentences(estimate_words("Dr. Santos said it. Mr. Lee agreed. It ended."))
        self.assertEqual([t for t, _a, _b in s], ["Dr. Santos said it.", "Mr. Lee agreed.", "It ended."])


class TestQuotes(unittest.TestCase):
    def test_a_long_attributed_quote_is_a_card_with_the_exact_words_and_the_speaker(self):
        evs = auto(LEAD + '"The ice here moves faster than anyone expected it to move," said Dr. Maria Santos, and the camp fell silent.' + TAIL)
        self.assertEqual(ids(evs), ["quote_card"])
        self.assertEqual(evs[0]["slots"]["text"].replace("|", " "), "The ice here moves faster than anyone expected it to move")
        self.assertEqual(evs[0]["slots"]["by"], "DR. MARIA SANTOS")

    def test_the_speaker_before_the_quote_and_according_to_are_found(self):
        a = auto(LEAD + 'Smith wrote: "A place where the ice never really goes away at all."' + TAIL)
        self.assertEqual(a[0]["slots"]["by"], "SMITH")
        b = auto(LEAD + 'According to Brooks, "the river has never run this low in living memory".' + TAIL)
        self.assertEqual(b[0]["slots"]["by"], "BROOKS")

    def test_a_pronoun_names_nobody(self):
        evs = auto(LEAD + '"We did not think the ice would ever break apart so quickly," he said quietly.' + TAIL)
        self.assertEqual((ids(evs), evs[0]["slots"]["by"]), (["quote_card"], ""))

    def test_a_short_unattributed_quote_is_the_boxed_heavy_one_in_capitals(self):
        evs = auto(LEAD + 'Locals call it "the land that forgot time" and they mean it.' + TAIL)
        self.assertEqual(ids(evs), ["quote_boxed"])
        self.assertEqual(evs[0]["slots"]["text"], "THE LAND THAT FORGOT TIME")

    def test_a_short_attributed_quote_keeps_its_speaker_on_the_card(self):
        evs = auto(LEAD + '"It was never going to last," said Brooks quietly.' + TAIL)
        self.assertEqual((ids(evs), evs[0]["slots"]["by"]), (["quote_card"], "BROOKS"))

    def test_nothing_is_cut_short_and_a_fragment_is_not_a_quote(self):
        self.assertEqual(auto(LEAD + '"' + " ".join(["word"] * 40) + '" said Smith.' + TAIL), [])
        self.assertEqual(auto(LEAD + 'He called it "home" for years.' + TAIL, enabled=("quote_card", "quote_boxed")), [])
        self.assertEqual(auto(LEAD + "Smith said the ice was never going to last at all." + TAIL), [])      # reported speech has no quotation marks

    def test_the_card_is_timed_to_the_quoted_words(self):
        evs = auto(LEAD + 'Then the weather turned. "The ice here moves faster than anyone expected it to move," said Dr. Maria Santos.' + TAIL)
        words = estimate_words(LEAD + 'Then the weather turned. "The ice here moves faster than anyone expected it to move," said Dr. Maria Santos.' + TAIL)
        start = next(a for w, a, _b in words if w.startswith('"The'))
        self.assertLessEqual(abs(evs[0]["t_in"] - start), 0.25)

    def test_the_same_quote_is_not_shown_twice(self):
        q = '"The ice here moves faster than anyone expected it to move," said Dr. Maria Santos.'
        self.assertEqual(len(auto(LEAD + q + " Time passed and the story moved on to other places and other people entirely. " + q + TAIL)), 1)

    def test_a_quote_over_covering_footage_is_flagged_and_backed_where_its_text_is(self):
        text = LEAD + '"The ice here moves faster than anyone expected it to move," said Dr. Maria Santos.' + TAIL
        evs = auto(text, footage=[(0, 40)])
        self.assertTrue(evs[0]["over_footage"])
        self.assertNotIn("dim", evs[0]["template"])
        self.assertGreater(evs[0]["template"]["shade"]["at"][0], 0.3)           # not at the left edge: the text block is there


class TestNames(unittest.TestCase):
    def test_a_person_introduced_with_a_role_gets_a_name_bar(self):
        evs = auto(LEAD + "Then Jane Smith, a glaciologist at the University of Alberta, measured the ice every single morning." + TAIL, resolve=resolve)
        self.assertEqual(ids(evs), ["name_bar"])
        self.assertEqual(evs[0]["slots"], {"label": "JANE SMITH", "sub": "GLACIOLOGIST AT THE UNIVERSITY OF ALBERTA"})

    def test_a_title_and_a_verb_is_enough(self):
        evs = auto(LEAD + "Dr. Alan Brooks said the lake had never been this low in his lifetime, and nobody argued." + TAIL, resolve=resolve)
        self.assertEqual((ids(evs), evs[0]["slots"]["label"]), (["name_bar"], "ALAN BROOKS"))

    def test_a_bare_name_or_a_place_or_a_role_nobody_has_gets_nothing(self):
        who = dict(resolve=resolve, enabled=("name_bar", "place_lowerthird"))      # (a superlative like "the highest tides" has its own tag_fact rule)
        self.assertEqual(auto(LEAD + "Then Jane Smith walked across the ice every single morning for years." + TAIL, **who), [])
        self.assertEqual(auto(LEAD + "Nova Scotia, a province on the Atlantic coast, has the highest tides on Earth." + TAIL, **who), [])
        self.assertEqual(auto(LEAD + "Then Jane Smith, a neighbour of the camp, brought the news every single morning." + TAIL, **who), [])

    def test_the_same_person_is_introduced_once(self):
        s = "Then Jane Smith, a glaciologist at the University of Alberta, measured the ice every single morning."
        self.assertEqual(len(auto(LEAD + s + " Weeks went by and the story moved on to other places and people entirely. " + s + TAIL, resolve=resolve)), 1)

    def test_a_different_person_soon_after_is_not_a_repeat_of_a_look(self):
        a = "Then Jane Smith, a glaciologist at the University of Alberta, measured the ice every single morning."
        b = "Later Tom Reyes, a ranger at the park, counted the birds along the shore every single evening."
        evs = auto(LEAD + a + " Weeks went by and the story moved on to other places and people entirely, while the seasons changed and the rivers froze over and thawed again. " + b + TAIL, resolve=resolve)
        self.assertEqual(ids(evs), ["name_bar", "lower_kicker"])      # a different person is shown again, in the other lower-third layout (variety)

    def test_over_footage_a_name_bar_is_flagged_and_not_dimmed(self):
        evs = auto(LEAD + "Then Jane Smith, a glaciologist at the University of Alberta, measured the ice every single morning." + TAIL, resolve=resolve, footage=[(0, 40)])
        self.assertTrue(evs[0]["over_footage"])
        self.assertNotIn("dim", evs[0]["template"])                              # the footage is not dimmed
        self.assertLessEqual(evs[0]["template"]["shade"]["rx"], 0.3)             # only a small soft backing behind the bar


class TestPlaces(unittest.TestCase):
    def test_a_place_the_narration_introduces_and_the_map_finds_gets_a_lower_third(self):
        evs = auto(LEAD + "In Halifax, a busy port on the Atlantic, the tides rise higher than anyone expects." + TAIL, resolve=resolve)
        self.assertEqual((ids(evs), evs[0]["slots"]), (["place_lowerthird"], {"label": "HALIFAX", "sub": ""}))

    def test_the_second_line_is_another_place_the_sentence_names(self):
        evs = auto(LEAD + "Halifax, Nova Scotia, is a harbour city where the tides rise higher than anyone expects." + TAIL, resolve=resolve)
        self.assertEqual(evs[0]["slots"], {"label": "HALIFAX", "sub": "NOVA SCOTIA"})

    def test_an_unknown_place_or_no_place_finder_means_no_graphic(self):
        self.assertEqual(auto(LEAD + "In Gorbleton, a busy port on the Atlantic, the tides rise higher than anyone expects." + TAIL, resolve=resolve), [])
        self.assertEqual(auto(LEAD + "In Halifax, a busy port on the Atlantic, the tides rise higher than anyone expects." + TAIL), [])

    def test_the_subject_of_the_whole_video_and_incidental_mentions_get_nothing(self):
        self.assertEqual(auto(LEAD + "In Canada, the tides rise higher. Canada is huge. Canada again and again." + TAIL, resolve=resolve), [])
        self.assertEqual(auto(LEAD + "Many people travel to Halifax every year to see the tides rise higher than anyone expects." + TAIL, resolve=resolve), [])

    def test_a_place_is_introduced_once(self):
        s = "In Halifax, a busy port on the Atlantic, the tides rise higher than anyone expects."
        self.assertEqual(len(auto(LEAD + s + " Weeks went by and the story moved on to other places and people entirely. " + s + TAIL, resolve=resolve)), 1)

    def test_over_footage_the_lower_third_is_flagged(self):
        evs = auto(LEAD + "In Halifax, a busy port on the Atlantic, the tides rise higher than anyone expects." + TAIL, resolve=resolve, footage=[(0, 40)])
        self.assertTrue(evs[0]["over_footage"])


class TestNumberedFactsAndRecords(unittest.TestCase):
    RECORD = ("In Delhi, the hottest day on record reached 49.2 degrees Celsius in May 2024, beating the previous record of 48.4 degrees Celsius set in "
              "June 1998.")

    def test_a_numbered_fact_gets_its_card_with_the_headline_the_narrator_gives(self):
        evs = auto(LEAD + "Number seven, the highest tides on Earth." + TAIL)
        self.assertEqual(ids(evs), ["fact_card"])
        self.assertEqual(evs[0]["slots"], {"n": 7, "kicker": "NUMBER", "title": "THE HIGHEST TIDES ON EARTH", "body": ""})

    def test_a_headline_too_long_for_the_bar_is_not_cut_it_gets_no_card(self):
        self.assertEqual(auto(LEAD + "Fact 3: Canada holds more lakes than any other country on Earth." + TAIL), [])
        self.assertEqual(auto(LEAD + "Fact 3:" + TAIL), [])                    # nothing after the number: no headline to show

    def test_the_word_fact_without_a_number_is_not_a_numbered_fact(self):
        self.assertEqual(auto(LEAD + "That fact surprised almost everybody who visited the camp that year." + TAIL), [])

    def test_a_record_with_everything_the_badge_needs_gets_the_badge(self):
        evs = auto(LEAD + self.RECORD + TAIL, resolve=resolve if False else (lambda n: {"Delhi": (77, 28)}.get(n)))
        self.assertEqual(ids(evs), ["record_badge"])
        self.assertEqual(evs[0]["slots"], {"headline": "HOTTEST DAY ON RECORD", "place": "DELHI", "value": "49.2 °C", "date": "MAY 2024",
                                           "prev_value": "48.4 °C", "prev_date": "JUNE 1998"})

    def test_a_record_missing_any_part_is_never_filled_in(self):
        no_prev = "In Delhi, the hottest day on record reached 49.2 degrees Celsius in May 2024."
        no_date = "In Delhi, the hottest day on record reached 49.2 degrees Celsius, beating the previous record of 48.4 degrees Celsius set in June 1998."
        no_place = "The hottest day on record reached 49.2 degrees Celsius in May 2024, beating the previous record of 48.4 degrees Celsius set in June 1998."
        for text in (no_prev, no_date, no_place):
            self.assertNotIn("record_badge", ids(auto(LEAD + text + TAIL, resolve=lambda n: {"Delhi": (77, 28)}.get(n))), text)

    def test_an_unknown_place_gets_no_badge(self):
        self.assertNotIn("record_badge", ids(auto(LEAD + self.RECORD + TAIL, resolve=lambda n: None)))

    def test_a_card_over_covering_footage_is_flagged(self):
        evs = auto(LEAD + "Number seven, the highest tides on Earth." + TAIL, footage=[(0, 40)])
        self.assertTrue(evs[0]["over_footage"])


class TestTimelines(unittest.TestCase):
    RUN = ("In 1818 the treaty fixed the border at the forty ninth parallel. In 1846 the boundary was extended west to the coast. "
           "In 1871 the last province joined the union.")

    def test_three_dated_events_in_a_row_become_one_strip_in_the_narrators_words(self):
        evs = auto(LEAD + self.RUN + TAIL)
        self.assertEqual(ids(evs), ["timeline_strip"])
        self.assertEqual([(r["label"], r["text"]) for r in evs[0]["slots"]["rows"]],
                         [("1818", "The treaty fixed the border"), ("1846", "The boundary was extended west"), ("1871", "The last province joined")])

    def test_two_dates_are_not_a_timeline(self):
        evs = auto(LEAD + "In 1818 the treaty fixed the border. In 1846 the boundary was extended west to the coast." + TAIL)
        self.assertNotIn("timeline_strip", ids(evs))

    def test_dates_out_of_order_or_with_two_years_in_a_sentence_end_the_run(self):
        back = "In 1818 the treaty fixed the border. In 1846 the boundary was extended. In 1830 something older was found."
        self.assertNotIn("timeline_strip", ids(auto(LEAD + back + TAIL)))
        two = "In 1818 the treaty fixed the border. Between 1846 and 1871 the boundary moved. In 1900 it was done."
        self.assertNotIn("timeline_strip", ids(auto(LEAD + two + TAIL)))

    def test_a_run_too_slow_to_show_at_once_is_left_alone(self):
        slow = " ".join(f"In {1800 + 20 * i} the {'long ' * 14}story went on." for i in range(3))
        self.assertNotIn("timeline_strip", ids(auto(LEAD + slow + TAIL)))

    def test_the_strip_covers_the_run_and_is_not_repeated(self):
        words = estimate_words(LEAD + self.RUN + TAIL)
        evs = G.auto_events(words, niche="map")
        first = next(a for w, a, _b in words if w == "In")
        self.assertGreaterEqual(evs[0]["t_in"], first - 0.01)
        again = G.auto_events(words, niche="map", taken=[(evs[0]["t_in"], evs[0]["t_out"])])
        self.assertEqual(again, [])

    def test_over_covering_footage_the_plate_gives_way_to_a_backing(self):
        evs = auto(LEAD + self.RUN + TAIL, footage=[(0, 60)])
        self.assertTrue(evs[0]["over_footage"])
        self.assertFalse(evs[0]["template"]["plate"])
        self.assertIn("shade", evs[0]["template"])


class TestComparisons(unittest.TestCase):
    def test_two_named_things_with_numbers_in_the_same_unit_get_a_versus(self):
        evs = auto(LEAD + "Canada has 10 million square kilometres, Russia 17 million." + TAIL)
        self.assertEqual(ids(evs), ["versus_numbers"])
        self.assertEqual(evs[0]["slots"], {"title": "HEAD TO HEAD", "a_label": "CANADA", "a_value": 10, "b_label": "RUSSIA", "b_value": 17, "unit": "MILLION KM²"})

    def test_the_full_form_and_people_work(self):
        a = auto(LEAD + "Canada covers 10 million square kilometres, while Russia covers 17 million square kilometres." + TAIL)
        self.assertEqual((ids(a), a[0]["slots"]["b_value"]), (["versus_numbers"], 17))
        b = auto(LEAD + "Canada has 40 million people, while Kenya has 55 million people." + TAIL)
        self.assertEqual(b[0]["slots"]["unit"], "MILLION PEOPLE")

    def test_different_units_or_scales_or_bare_numbers_are_not_compared(self):
        for text in ("Canada covers 10 million square kilometres, while Russia has 140 million people.",
                     "Canada covers 10 million square kilometres, while Russia covers 17 thousand square kilometres.",
                     "Canada has 10 and Russia has 17 of them."):
            self.assertNotIn("versus_numbers", ids(auto(LEAD + text + TAIL)), text)

    def test_no_relationship_is_invented_for_a_ratio(self):
        evs = auto(LEAD + "Russia is nearly twice as large as Canada, which surprises most visitors." + TAIL)
        self.assertNotIn("versus_numbers", ids(evs))

    def test_the_same_comparison_is_shown_once_and_over_footage_it_is_flagged(self):
        s = "Canada has 10 million square kilometres, Russia 17 million."
        twice = auto(LEAD + s + " Time passed and the story moved on to other places and other people entirely for a good while longer. " + s + TAIL)
        self.assertEqual(ids(twice).count("versus_numbers"), 1)                  # the same comparison is never drawn twice
        self.assertTrue(auto(LEAD + s + TAIL, footage=[(0, 40)])[0]["over_footage"])


class TestBackwardCompatible(unittest.TestCase):
    def test_a_narration_with_none_of_this_gets_exactly_what_it_got_before(self):
        text = LEAD + "About sixty percent of its lakes are unnamed, which surprises many people. Then the story moves on to other things."
        self.assertEqual(ids(auto(text)), ["ring_percent"])

    def test_running_the_step_twice_adds_nothing(self):
        text = LEAD + '"The ice here moves faster than anyone expected it to move," said Dr. Maria Santos.' + TAIL
        first = auto(text)
        again = auto(text, taken=[(e["t_in"], e["t_out"]) for e in first])
        self.assertEqual(again, [])

    def test_the_switch_off_nothing_is_added_by_the_compiler(self):
        HEAD = "item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,sub_text,value_to,params\n"
        text = LEAD + '"The ice here moves faster than anyone expected it to move," said Dr. Maria Santos.' + TAIL
        res = compile_csv(text=HEAD + '1,Canada is,hud_title,,,PART 1,,,\n', words=estimate_words(text), validate=False)
        self.assertEqual([e["type"] for e in res.spec["events"]], ["hud_title"])


if __name__ == "__main__":
    unittest.main()
