"""Render 050 production slice (6:43-9:44): keyword cards only for real lists, real figures only, the dated strike campaign timeline,
strike-map places from the previous line only, grounded gap fills / flagged gaps, one text layer at a time. No network, no render."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from cinematic_explainer.render import Layer
from cinematic_explainer.war import direction as D, footage_director as FD, narration_read as N, semantics as S

CAMPAIGN = [
    "Then, on the thirtieth of October, the strikes came back.",
    "On the thirtieth of October, drones hit Rosneft's Novokuybyshevsk refinery in the Samara region.",
    "On the thirty-first, the Novoil refinery in Ufa, owned by Bashneft.",
    "On the first of November, Lukoil's NORSI refinery in the Nizhny Novgorod region.",
    "On the second of November, a Transneft oil pumping station in Samara.",
    "That fire burned for several days.",
    "On the fifth of November, the Ryazan refinery, south-east of Moscow.",
    "That is seven targets in nine days, spread across thousands of kilometres of Russian territory.",
]


def rows_of(lines, dur=5.0, graphic=None):
    out, t = [], 0.0
    for i, x in enumerate(lines, 1):
        out.append({"_no": str(i), "text": x, "_start": t, "_end": t + dur, "words": None, "graphic": (graphic or {}).get(i, "")})
        t += dur
    return out


def nums(text):
    from cinematic_explainer.war import planner as P

    A = S.analyze_scene(text, P._default_catalog(), None, 0, 6)
    return [(n.raw, n.unit) for s in A.sentences for n in s.numbers]


class NoLooseKeywords(unittest.TestCase):
    def test_keyword_card_only_for_a_real_list(self):
        from cinematic_explainer.war import planner as P

        cat = P._default_catalog()
        sent = S.analyze_scene("Ukraine withdrew its forces as the Russian army entered the country.", cat, None, 0, 5).sentences[0]
        self.assertNotIn("kit_keywords", [k for k, _p in D._motion_options(sent, "Ukraine withdrew")])
        lst = S.analyze_scene("The targets include refineries, depots and factories.", cat, None, 0, 5).sentences[0]
        self.assertIn("kit_keywords", [k for k, _p in D._motion_options(lst, "Spread across the country")])

    def test_csv_keywords_without_a_list_makes_no_card(self):
        from cinematic_explainer.war import planner as P

        r = rows_of(["Then came the biggest strike of the campaign."])[0]
        ly, why = D._csv_layer("keywords", r, dict(P.DEFAULTS), P._default_catalog())
        self.assertTrue(ly is None or ly.kind != "kit_keywords", (ly, why))

    def test_no_sentence_falls_back_to_keywords(self):
        self.assertNotEqual(FD.graphic_for(N.read("Then came the biggest strike of the campaign.")), "keywords")


class RealFigures(unittest.TestCase):
    def test_figures(self):
        self.assertEqual(nums("The governor said air defences had shot down 113 drones over the region."), [("113", "drones")])
        self.assertEqual(nums("Its capacity is up to 21 million tonnes of crude oil a year."), [("21 million", "tonnes")])
        self.assertEqual(nums("And this one matters even more for the war."), [])
        self.assertEqual(nums("Every Pantsir or S-400 battery moved to protect a refinery."), [])
        self.assertEqual(nums("For almost two weeks in October, the strikes paused."), [])
        self.assertEqual(nums("That is seven targets in nine days."), [("seven", "targets")])


class CampaignTimeline(unittest.TestCase):
    def test_dated_strike_lines(self):
        self.assertEqual(D.dated_strike(CAMPAIGN[2], "October")["date"], "31 OCT")
        self.assertEqual(D.dated_strike("And on the night of the sixth to the seventh of November, the Saratov refinery on the Volga.", "")["date"],
                         "6-7 NOV")
        self.assertIsNone(D.dated_strike("That fire burned for several days.", "November"))
        self.assertIsNone(D.dated_strike("On the fifth of November, ministers met in Brussels.", ""))     # no target: not a strike line

    def test_summary_line_gets_the_campaign_timeline(self):
        plan = NS(layers=[Layer("institution_card", 35.0, 40.0, {}, dim=False)], shots=[])
        counts = {}
        D._campaign_timeline(plan, rows_of(CAMPAIGN, graphic={8: "timeline"}), counts)
        tl = [ly for ly in plan.layers if ly.kind == "lay_timeline"]
        self.assertEqual(len(tl), 1)
        self.assertEqual([i["date"] for i in tl[0].params["items"]], ["30 OCT", "31 OCT", "1 NOV", "2 NOV", "5 NOV"])
        self.assertEqual(tl[0].start, 35.0)
        self.assertNotIn("institution_card", [ly.kind for ly in plan.layers])

    def test_never_forced(self):
        plan = NS(layers=[], shots=[])
        D._campaign_timeline(plan, rows_of(["Part two. The oil war.", "On the fifth of November, the Ryazan refinery.",
                                            "That is seven targets in nine days."]), {})
        self.assertFalse(plan.layers)                                  # one dated strike line is not a campaign
        plan = NS(layers=[], shots=[])
        D._campaign_timeline(plan, rows_of(CAMPAIGN[:-1] + ["Russia's air defence is stretched."]), {})
        self.assertFalse(plan.layers)                                  # no summary line and no CSV ask: no timeline
        plan = NS(layers=[], shots=[])
        D._campaign_timeline(plan, rows_of(CAMPAIGN[1:5] + ["Part three. The cities.", "That is seven targets in nine days."]), {})
        self.assertFalse(plan.layers)                                  # a section break between them


class StrikeMapPlaces(unittest.TestCase):
    def test_no_place_from_two_lines_back(self):
        from cinematic_explainer.war import planner as P

        rows = rows_of(["Ukrainian drones attacked the Kirishi oil refinery in the Leningrad region.",
                        "The plant is one of the largest in Russia.",
                        "Overnight, a major combined attack hit the port."], dur=6.0)
        d = Path(tempfile.mkdtemp())
        from cinematic_explainer.war import integration as I

        sc = I.load_scenes(d, [{"scene_no": int(r["_no"]), "text": r["text"], "start": r["_start"], "end": r["_end"], "no_footage": True}
                               for r in rows])
        plan = P.plan(sc)
        late = [ly for ly in plan.layers if ly.kind == "tac_map" and (ly.params or {}).get("strike_map") and ly.start >= 12.0]
        for ly in late:
            self.assertNotIn("Kirishi", str(ly.params.get("places")))


class TextAndGaps(unittest.TestCase):
    def test_two_text_cards_never_overlap(self):
        plan = NS(layers=[Layer("kit_dossier", 0.0, 6.0, {}, dim=False), Layer("kit_bignum", 4.0, 9.0, {}, dim=False),
                          Layer("kit_tag", 1.0, 3.0, {}, dim=False)], shots=[])
        D._text_layers_clear(plan, {})
        full = sorted([(ly.start, ly.end) for ly in plan.layers if ly.kind in D.TEXT_FULL])
        for (a0, a1), (b0, b1) in zip(full, full[1:]):
            self.assertLessEqual(a1, b0 + 1e-6)
        self.assertNotIn("kit_tag", [ly.kind for ly in plan.layers])

    def test_gap_with_nothing_relevant_is_flagged_not_filled_by_a_neighbour(self):
        from cinematic_explainer.war import planner as P

        rows = rows_of(["And it was not enough."], dur=5.0)
        self.assertIsNone(D._grounded_fill(rows, P._default_catalog(), 0.0, 5.0))
        rows = rows_of(["Drones struck the Kirishi oil refinery in the Leningrad region."], dur=5.0)
        g = D._grounded_fill(rows, P._default_catalog(), 0.0, 5.0)
        self.assertIsNotNone(g)
        self.assertEqual(g.kind, "tac_map")


if __name__ == "__main__":
    unittest.main()
