"""Stage B.3 (render 050 repair, live slice 2026-11-12): wrong-event rejection, narration-first subjects, separate place/event/subject
levels, unread on-screen location labels. Titles are the real ones the live run picked. No network."""

from __future__ import annotations

import unittest
from types import SimpleNamespace as NS

import numpy as np

from cinematic_explainer.war import director_rules as R, footage_director as FD, narration_read as N


def clip(title, up="20261111", channel="Reuters", dur=90.0, desc=""):
    return NS(video_id="x", title=title, channel=channel, duration=dur, description=desc, details={"upload_date": up}, blocked=False,
              content_warning="", level_hint="")


def read(lines, no):
    """Readings of a little script (section dates, subjects), with the CSV prompts applied: {scene_no: prompt}."""
    sc = [{"scene_no": i + 1, "text": t} for i, (t, _p) in enumerate(lines)]
    rd = N.read_scenes(sc)
    FD.widen_to_section(rd)
    FD._prompt_subjects(rd, sc, [NS(scene_number=str(i + 1), prompt=p or "") for i, (_t, p) in enumerate(lines)])
    return rd[str(no)]


TALKS = [("Part one. The talks in Abu Dhabi.", ""),
         ("On the tenth and eleventh of November 2026, the United States hosted a new round of three-way talks in Abu Dhabi.",
          "Abu Dhabi Russia Ukraine US talks || trilateral talks Abu Dhabi delegations"),
         ("In January and February, the first three-way talks took place in Abu Dhabi.",
          "Abu Dhabi Russia Ukraine US talks || trilateral talks Abu Dhabi delegations")]
OIL = [("Part two. The oil war.", ""),
       ("On the night of the ninth of November 2026, Ukrainian drones attacked the Kirishi oil refinery in the Leningrad region.",
        "Kirishi refinery drone attack fire"),
       ("On the fifth of November, the Ryazan refinery, south-east of Moscow.", "Putin meeting Kremlin || Kremlin Moscow"),
       ("It supplies petrol, diesel and jet fuel to the whole of north-western Russia, including Saint Petersburg and its main airport, Pulkovo.",
        "Saint Petersburg city aerial || Pulkovo airport"),
       ("But he also admitted that several drones had hit industrial sites in Kirishi.", "Kirishi refinery drone attack fire")]


class WrongEvent(unittest.TestCase):
    def test_abu_dhabi_business_panel_is_not_the_talks(self):
        r = read(TALKS, 3)
        bad = clip("Abu Dhabi's Growth Plan | The Power of Partnerships", channel="Reuters Plus")
        why = R.reject(bad, r)
        self.assertTrue(any(w.startswith("event:") for w in why), why)
        good = clip("US-mediated talks on ending Russia-Ukraine war begin in Abu Dhabi", channel="FRANCE 24 English")
        self.assertFalse(R.reject(good, read(TALKS, 2)))

    def test_putin_kushner_meeting_is_not_the_ryazan_refinery(self):
        r = read(OIL, 3)
        self.assertTrue(r.prompt_conflict)                           # the CSV prompt is about a meeting: only a late search hint
        self.assertNotIn("Putin", r.key_terms)
        self.assertNotIn("Kremlin", r.key_terms)
        self.assertTrue(FD.queries_for(r, "Putin meeting Kremlin || Kremlin Moscow")[0].lower().startswith("ryazan"))
        meet = clip("Putin meets Jared Kushner and Steve Witkoff at the Kremlin for talks", channel="Associated Press")
        self.assertTrue(R.reject(meet, r))
        fire = clip("Drones hit Ryazan oil refinery, fire breaks out", channel="Reuters")
        self.assertFalse(R.reject(fire, r))
        self.assertEqual(R.match_level(fire, r), "exact")

    def test_st_petersburg_protest_is_not_its_fuel_supply(self):
        r = read(OIL, 4)
        why = R.reject(clip("Protesters against Ukraine invasion arrested in St. Petersburg"), r)
        self.assertTrue(any(w.startswith("event:") for w in why), why)

    def test_place_name_alone_is_never_exact(self):
        r = read(TALKS, 2)
        skyline = clip("Abu Dhabi skyline at night 4K")
        self.assertNotEqual(R.match_level(skyline, r), "exact")
        talks = clip("Russia, Ukraine and US delegations hold talks in Abu Dhabi")
        self.assertEqual(R.match_level(talks, r), "exact")
        prisoners = read([("Part one. Talks.", ""), ("Russia and Ukraine agreed the largest exchange of prisoners of war since 2022.",
                                                      "Russia Ukraine prisoner exchange")], 2)
        ctx = clip("Ukraine's capital Kyiv: a day in the city")
        self.assertNotEqual(R.match_level(ctx, prisoners), "exact")

    def test_matching_prompt_but_footage_filmed_before_the_event(self):
        """Wrong place despite a matching search: an earlier strike's package (TVP, Sept 2025) on 'drones hit Kirishi' (Nov 2026)."""
        r = read(OIL, 5)
        old = clip("Ukrainian drone attack damages Russia's Kirishi oil refinery | Ukraine war", up="20250915", channel="TVP WORLD")
        self.assertTrue(R.stale(old, r))
        self.assertNotEqual(R.match_level(old, r), "exact")          # never claimed as footage of this event
        self.assertTrue(FD._location_verdict(True, old, r).get("refuse"))     # plus an unread place label: refused
        self.assertFalse(FD._location_verdict(False, old, r).get("refuse"))   # no label: contextual footage of the earlier strike
        new = clip("Ukrainian drone attack damages Russia's Kirishi oil refinery", up="20261110", channel="TVP WORLD")
        v = FD._location_verdict(True, new, r)
        self.assertTrue(v.get("unverified") and not v.get("refuse"))

    def test_right_video_wrong_moment(self):
        from cinematic_explainer.war import director_moment as M

        r = read(OIL, 2)
        segs = [{"start": float(t), "text": "other news of the day"} for t in range(0, 900, 30)]
        segs[10] = {"start": 300.0, "text": "a satellite system for the army"}
        segs.append({"start": 845.0, "text": "drones struck the Kirishi refinery overnight"})
        segs.sort(key=lambda x: x["start"])
        ok, hint, _w = M.check(900.0, segs, r)
        self.assertTrue(ok)
        self.assertFalse(M.inside(300.0, hint))                      # the satellite segment of the same programme is refused
        self.assertTrue(M.inside(850.0, hint))
        ok, _h, why = M.check(900.0, None, r, status="rate_limited")
        self.assertFalse(ok)
        self.assertIn("rate-limited", why)                            # unverified, not 'never talks about' (irrelevant)
        self.assertNotIn("never talks", why)


class Narration(unittest.TestCase):
    def test_bare_year_aside_does_not_date_the_story(self):
        rd = N.read_scenes([{"scene_no": 1, "text": "This is the war in November 2026."},
                            {"scene_no": 2, "text": "That would bring back the demands Russia made in 2021, before the invasion."},
                            {"scene_no": 3, "text": "On the fifth of November, the Ryazan refinery, south-east of Moscow."}])
        self.assertIn("2026", rd["3"].date)

    def test_moskva_prompt_still_names_the_unnamed_flagship(self):
        rd = {"1": N.read("On April 14, 2022, the flagship of Russia's Black Sea Fleet sank.")}
        FD._prompt_subjects(rd, [{"scene_no": "1"}], [NS(scene_number="1", prompt="Moskva cruiser sinking April 2022")])
        self.assertFalse(rd["1"].prompt_conflict)
        self.assertEqual(rd["1"].key_terms[0], "Moskva")


class Labels(unittest.TestCase):
    def test_real_place_label_frame_flags(self):
        from pathlib import Path

        from PIL import Image

        from cinematic_explainer.war import director_capture as C

        d = Path(__file__).parent / "test_fixtures" / "war_render050" / "frames"
        fr = lambda n: np.asarray(Image.open(d / f"{n}.jpg").convert("RGB").resize((C.TEXT_W, C.TEXT_H)))    # noqa: E731
        self.assertTrue(FD.burnt_label([fr("a089_t1"), fr("a089_t3")]))       # 'DONETSK REGION, UKRAINE' + source credit
        self.assertFalse(FD.burnt_label([fr("a004_t1"), fr("a004_t3"), fr("a011_t1"), fr("a011_t3")]))   # clean footage


if __name__ == "__main__":
    unittest.main()
