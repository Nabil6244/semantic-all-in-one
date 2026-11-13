"""Aviation bible + Flow prompt builder v2 (aviation/bible.py, aviation/flow_prompts.py): offline, rules only."""
import json
import unittest

from aviation import bible as B
from aviation import flow_prompts as P

SCRIPT = [
    "In 1947 Malayan Airways was founded, and its first propeller planes carried cash and cargo between Singapore and Kuala Lumpur.",
    "In 1963 it was renamed Malaysian Airways as the new federation took shape.",
    "In 1966 the two governments formed Malaysia-Singapore Airlines, which flew Boeing 707s out of Singapore.",
    "The captain on those first jets said the airline was held up by cash and cargo, and by two borrowed planes.",
    "But the two partners could not agree on routes, and the argument over the borrowed planes grew into a crisis.",
    "The Prime Minister said the airline had to be split, and in 1972 the split gave birth to Singapore Airlines and Malaysia Airlines.",
    "Through the 1970s Singapore Airlines flew Boeing 747s from Changi, while the cabin crew became famous for service.",
    "Malaysia Airlines rebuilt around Kuala Lumpur and recovered with its own fleet.",
    "In 2007 Singapore Airlines flew the first Airbus A380 to Sydney.",
    "Today the story is still about cash and cargo, and the split that made two airlines.",
]
BIB = B.read(SCRIPT)


class BibleTests(unittest.TestCase):
    def test_eras_found(self):
        self.assertEqual([e["key"] for e in BIB.eras], ["pre1960", "1960s", "1970s", "modern"])
        e60 = BIB.eras[1]
        self.assertEqual((e60["y0"], e60["y1"]), (1963, 1966))
        self.assertEqual(e60["lines"], [1, 2, 3, 4])
        self.assertIn("sepia", BIB.eras[0]["look"])
        self.assertIn("Kodachrome", e60["look"])
        self.assertEqual(BIB.lines[3]["year"], 1966)                  # carried forward
        self.assertEqual(BIB.lines[6]["year_kind"], "decade")         # "the 1970s"

    def test_fleet_by_era(self):
        f = BIB.fleet
        self.assertIn("b707", f["msa"]["1960s"]["types"])
        self.assertFalse(f["msa"]["1960s"]["assumed"])
        self.assertEqual(f["malayan_airways"]["pre1960"], {"types": ["dc3"], "assumed": True, "lines": [0]})
        self.assertTrue(f["malaysia_airlines"]["1970s"]["assumed"])
        self.assertEqual(f["singapore_airlines"]["1970s"]["types"], ["b747"])
        self.assertEqual(f["singapore_airlines"]["modern"]["types"], ["a380"])
        self.assertEqual(f["singapore_airlines"]["1970s"]["lines"], [5, 6])

    def test_livery_uses_the_historic_entry(self):
        lv = BIB.livery
        self.assertEqual(lv["malaysian_airways"]["1960s"]["name"], "Malaysian Airways")
        self.assertEqual(lv["msa"]["1960s"]["name"], "Malaysia-Singapore Airlines")
        self.assertIn("yellow", lv["msa"]["1960s"]["color_words"])
        self.assertIn("dark blue tail", lv["singapore_airlines"]["1970s"]["notes"])
        self.assertNotIn("singapore_airlines", [a for a in lv if "pre1960" in lv[a]])

    def test_historic_name_mapped_by_explicit_year(self):
        b = B.read(["In 1966 Singapore Airlines already flew Boeing 707s."])      # that airline was MSA in 1966
        self.assertEqual(b.lines[0]["airlines"], ["msa"])

    def test_places_and_landmarks(self):
        self.assertEqual(list(BIB.places), ["SIN", "KUL", "SYD"])
        self.assertIn("Kallang", BIB.places["SIN"]["landmark"])       # 1947
        self.assertIn("Changi", B.landmark("SIN", 2007))
        self.assertIn("Petronas", BIB.places["KUL"]["landmark"])
        self.assertIn("Opera House", BIB.places["SYD"]["landmark"])
        self.assertEqual(BIB.lines[3]["place"], "SIN")                # carried
        self.assertNotIn("SIN", BIB.lines[8]["airports"])             # "Singapore Airlines" is not the place

    def test_cast_roles_never_names(self):
        self.assertEqual(set(BIB.cast), {"captain", "official", "cabin_crew"})
        self.assertEqual(BIB.cast["captain"]["lines"], [3])
        self.assertEqual(BIB.cast["official"]["label"], "government official")
        blob = json.dumps(BIB.cast)
        for bad in ("Lee", "Kuan", "Yew", "Tunku"):
            self.assertNotIn(bad, blob)
        b = B.read(["Prime Minister Lee Kuan Yew met the minister and the engineer."])
        self.assertEqual(set(b.cast), {"official", "engineer"})
        self.assertNotIn("Lee", json.dumps(b.cast))

    def test_motifs(self):
        ph = {m["phrase"]: m for m in BIB.motifs}
        self.assertEqual(ph["cash and cargo"]["lines"], [0, 3, 9])
        self.assertIn("borrowed planes", ph)
        self.assertIn("split", ph)
        for bad in ("singapore", "airways", "malaysia", "boeing"):
            self.assertFalse(any(bad in m["phrase"] for m in BIB.motifs))

    def test_moods(self):
        by_line = {r["no"]: r["mood"] for r in BIB.lines}
        self.assertEqual(by_line[0], "rise")
        self.assertEqual(by_line[4], "crisis")
        self.assertEqual(by_line[5], "split")
        self.assertEqual(by_line[7], "recovery")
        m = next(x for x in BIB.moods if x["mood"] == "crisis")
        self.assertIn("storm", m["weather"])
        self.assertTrue(m["light"] and m["palette"])

    def test_json_round_trip(self):
        d = json.loads(json.dumps(BIB.to_dict()))
        again = B.Bible.from_dict(d)
        self.assertEqual(again.to_dict(), BIB.to_dict())
        self.assertEqual(B.Bible.from_dict(None).lines, [])

    def test_no_years_script(self):
        b = B.read(["The airline flies at night.", "It carries cargo."])
        self.assertEqual({r["era"] for r in b.lines}, {"modern"})
        self.assertEqual(B.read([]).lines, [])


class PromptTests(unittest.TestCase):
    def test_every_prompt_has_era_livery_place_mood_and_the_clause(self):
        p = P.image_prompt(BIB, 2, "era_plate")
        self.assertIn(B.era_look("1960s"), p["prompt"])
        self.assertIn("yellow", p["prompt"])
        self.assertIn("Boeing 707", p["prompt"])
        self.assertIn("Singapore", p["prompt"])
        self.assertIn(BIB.moods[0]["light"], p["prompt"])
        self.assertTrue(p["prompt"].endswith(P.END))
        self.assertEqual(p["chip"], "AI ILLUSTRATION")
        self.assertEqual(p["look"], B.era_look("1960s"))

    def test_all_uses_build_and_end_with_the_clause(self):
        for use in P.IMAGE_USES:
            r = P.image_prompt(BIB, 6, use)
            self.assertIsNotNone(r, use)
            self.assertTrue(r["prompt"].endswith("no logos, no watermark."), use)
            self.assertLessEqual(len(r["refs"]), 3)
            self.assertIn("1970s", r["prompt"] if use != "future_aircraft" else "1970s")
        for use in P.VIDEO_USES:
            r = P.video_prompt(BIB, 6, use)
            self.assertIsNotNone(r, use)
            self.assertTrue(r["prompt"].endswith("no logos, no watermark."), use)
            self.assertEqual(r["chip"], "AI ILLUSTRATION")

    def test_sticker_is_a_black_background_die_cut(self):
        p = P.image_prompt(BIB, 2, "sticker")["prompt"]
        for w in ("die-cut", "black", "side view", "Boeing 707", "yellow"):
            self.assertIn(w, p)
        prop = P.image_prompt(BIB, 2, "sticker", "ticket")["prompt"]
        self.assertIn("ticket", prop)
        self.assertNotIn("Boeing", prop)

    def test_sticker_for_other_type_and_assumed_era_type(self):
        self.assertIn("Airbus A380", P.image_prompt(BIB, 8, "sticker")["prompt"])
        self.assertIn("Douglas DC-3", P.image_prompt(BIB, 0, "sticker")["prompt"])        # assumed from the era
        self.assertIn("Boeing 747", P.image_prompt(BIB, 5, "sticker", "b747")["prompt"])

    def test_explainer_has_no_labels_and_no_numbers(self):
        p = P.image_prompt(BIB, 8, "explainer_plate", "an engine cutaway")["prompt"]
        self.assertIn("without any labels", p)
        self.assertIn("engine cutaway", p)

    def test_metaphor_uses_a_motif(self):
        p = P.image_prompt(BIB, 3, "metaphor")["prompt"]
        self.assertIn("cash and cargo", p)
        self.assertIsNone(P.image_prompt(B.read(["The airline flies at night."]), 0, "metaphor"))

    def test_place_plate(self):
        p = P.image_prompt(BIB, 8, "place_plate", "SYD")["prompt"]
        self.assertIn("Opera House", p)
        self.assertIsNone(P.image_prompt(B.read(["In 1990 an airline began."]), 0, "place_plate"))
        self.assertIn("place:SYD", P.image_prompt(BIB, 8, "place_plate", "SYD")["refs"])

    def test_refs_are_few_specific_and_known(self):
        self.assertEqual(P.references(BIB, 2), ["hero:msa:1960s", "place:SIN"])
        self.assertEqual(P.references(BIB, 3), ["hero:msa:1960s", "cast:captain", "place:SIN"])
        self.assertEqual(P.references(BIB, 3, "captain")[0], "cast:captain")
        self.assertEqual(P.references(BIB, 8, "SYD")[0], "place:SYD")
        for n in range(len(SCRIPT)):
            refs = P.references(BIB, n)
            self.assertLessEqual(len(refs), 3)
            self.assertEqual(len(refs), len(set(refs)))
            for r in refs:
                self.assertTrue(P._known(BIB, r), r)
        self.assertEqual(P.references(BIB, 99), [])
        self.assertEqual(P.references(B.read(["The airline flies at night."]), 0), [])

    def test_real_person_gets_no_face_picture(self):
        b = B.read(["In 1965 Lee Kuan Yew spoke about Malaysia-Singapore Airlines and the captain listened."])
        self.assertIn("Lee Kuan Yew", P.real_people(b.lines[0]["text"]))
        for use in ("cast_moment", "card_picture", "cabin", "thumbnail"):
            self.assertIsNone(P.image_prompt(b, 0, use) or P.video_prompt(b, 0, use), use)
        self.assertIn("real person", P.why_not(b, 0, "cast_moment"))
        self.assertIsNotNone(P.image_prompt(b, 0, "sticker"))                   # an aircraft sticker has no face
        self.assertEqual(P.real_people("Prime Minister Tunku Abdul Rahman said no."), ["Tunku Abdul Rahman"])

    def test_script_lines_name_no_one(self):
        for r in BIB.lines:
            self.assertEqual(P.real_people(r["text"]), [], r["text"])

    def test_named_event_never_staged(self):
        b = B.read(["In 2014 flight MH370 disappeared over the sea.", "In 1998 a Boeing 747 crashed on landing."])
        for n in (0, 1):
            self.assertTrue(P.named_event(b.lines[n]["text"]))
            for use in ("cast_moment", "place_reconstruction", "image_to_video", "era_plate", "card_picture"):
                self.assertIsNone(P.image_prompt(b, n, use) or P.video_prompt(b, n, use), use)
            self.assertIn("event", P.why_not(b, n, "place_reconstruction"))
            self.assertIsNotNone(P.image_prompt(b, n, "sticker"))
        self.assertFalse(P.named_event(SCRIPT[4]))

    def test_unknown_use_and_line(self):
        self.assertIsNone(P.image_prompt(BIB, 0, "nonsense"))
        self.assertIsNone(P.video_prompt(BIB, 99, "ops_broll"))
        self.assertIsNone(P.video_prompt(BIB, 0, "sticker"))

    def test_library_lists(self):
        heroes = {h["id"]: h for h in P.hero_list(BIB)}
        self.assertIn("hero:msa:1960s", heroes)
        self.assertIn("hero:singapore_airlines:modern", heroes)
        self.assertEqual(len(heroes), sum(len(v) for v in BIB.fleet.values()))
        self.assertIn("Boeing 707", heroes["hero:msa:1960s"]["prompt"])
        self.assertIn("Airbus A380", heroes["hero:singapore_airlines:modern"]["prompt"])
        self.assertTrue(heroes["hero:malayan_airways:pre1960"]["assumed"])
        cast = {c["id"]: c for c in P.cast_list(BIB)}
        self.assertEqual(set(cast), {"cast:captain", "cast:official", "cast:cabin_crew"})
        self.assertIn("not any real person", cast["cast:captain"]["prompt"])
        self.assertIn("yellow", cast["cast:captain"]["prompt"])
        places = {p["id"]: p for p in P.place_list(BIB)}
        self.assertEqual(set(places), {"place:SIN", "place:KUL", "place:SYD"})
        self.assertIn("Kallang", places["place:SIN"]["prompt"])
        for item in list(heroes.values()) + list(cast.values()) + list(places.values()):
            self.assertTrue(item["prompt"].endswith(P.END))
            self.assertEqual(item["refs"], [])
        json.dumps(P.hero_list(BIB) + P.cast_list(BIB) + P.place_list(BIB))

    def test_cast_moment_uses_the_sheet(self):
        r = P.video_prompt(BIB, 3, "cast_moment")
        self.assertEqual(r["refs"][0], "cast:captain")
        self.assertIn("captain", r["prompt"])


if __name__ == "__main__":
    unittest.main()


def test_bible_reads_a_long_business_script_without_crashing():
    # the TAP / Lufthansa script crashed here: a mood flag was removed from earlier lines while later lines still read it
    from aviation import bible as BB
    lines = ["Here is the strange part.", "TAP lost 99.2 million euros in the first half of this year.", "Now the airport.",
             "Tourism is booming, and the capital's airport is full.", "Then the story flips.", "The airline is seasonal, not sinking."]
    b = BB.read(lines)
    assert len(b.lines) == len(lines) and all("_mood_own" not in r for r in b.lines)
