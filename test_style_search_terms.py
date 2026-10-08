"""Real-source searches that archives can answer: for a style with real_subjects (Book of Enoch), a stock scene naming one
of the style's search terms searches that short term first, and a manuscript / engraving / church is searched as a still;
named-artwork searches and AI scenes are left alone; other styles are unchanged. And Openverse candidates carry their
title and tags, so the shared ranking can judge their relevance like Pexels (alt) and Pixabay (tags)."""

import unittest
from unittest import mock

from style_engine import resolve_style
from visual_allocation.allocator import _style_search_terms
from visual_director.schema import parse_visual_plan


def plan():
    rows = [("It is called the Book of Enoch.", "stock_video", "ethiopian geez manuscript ancient manuscript fragment"),
            ("In the days of Jared, the angels descended on Mount Hermon.", "stock_video", "mount hermon summit dramatic clouds"),
            ("written in Ge'ez, the language of the Ethiopian church", "stock_video", "ethiopian orthodox church interior priest"),
            ("Their leader, Semjaza, made them swear an oath.", "stock_image", "William Blake Book of Enoch drawing"),
            ("Their children were the Nephilim.", "video", "A Gustave Doré style woodcut engraving of giant shadows"),
            ("The sea rose over the land.", "stock_video", "storm over a dark sea")]
    return parse_visual_plan({"title": "t", "scenes": [
        {"scene_id": i + 1, "narration": n, "visual_goal": n, "visual_description": q, "asset_type": a,
         "provider_preference": {"video": "flow_video"}.get(a, a), **({"search_queries": [q]} if a.startswith("stock") else {})}
        for i, (n, a, q) in enumerate(rows)]})


class StyleSearchTerms(unittest.TestCase):
    def setUp(self):
        self.p = plan()
        self.n = _style_search_terms(self.p, resolve_style(mode="manual", style_id="book_of_enoch", script=""))
        self.by = {s.scene_id: s for s in self.p.scenes}

    def test_a_real_source_scene_searches_the_style_term_first(self):
        self.assertEqual(self.by[1].search_queries[0], "Ge'ez")
        self.assertEqual(self.by[2].search_queries[0], "Mount Hermon")
        self.assertEqual(self.by[3].search_queries[0], "Ethiopian Orthodox church")

    def test_stills_are_searched_as_images_places_keep_video(self):
        self.assertEqual(self.by[1].asset_type, "stock_image", "a manuscript is a still")
        self.assertEqual(self.by[3].asset_type, "stock_image", "archives have church photographs, not video")
        self.assertEqual(self.by[2].asset_type, "stock_video", "a mountain can stay video")

    def test_named_artwork_ai_scenes_and_unnamed_scenes_are_left_alone(self):
        self.assertEqual(self.by[4].search_queries[0], "William Blake Book of Enoch drawing")
        self.assertEqual((self.by[5].asset_type, self.by[5].search_queries), ("video", []))
        self.assertEqual((self.by[6].asset_type, self.by[6].search_queries), ("stock_video", ["storm over a dark sea"]))
        self.assertEqual(self.n, 3)

    def test_other_styles_are_unchanged(self):
        p = plan()
        before = [(s.asset_type, list(s.search_queries)) for s in p.scenes]
        self.assertEqual(_style_search_terms(p, resolve_style(mode="manual", style_id="ancient_history_documentary", script="")), 0)
        self.assertEqual([(s.asset_type, list(s.search_queries)) for s in p.scenes], before)


class OpenverseText(unittest.TestCase):
    def test_candidates_carry_title_and_tags_for_ranking(self):
        from providers.stock.openverse import OpenverseBackend

        hit = {"id": "x1", "url": "https://upload.wikimedia.org/a.jpg", "width": 3496, "height": 2496, "title": "Ethiopic manuscript cover",
               "tags": [{"name": "manuscript"}, {"name": "ethiopia"}], "license": "pdm"}
        resp = mock.Mock(status_code=200, json=lambda: {"results": [hit]})
        resp.raise_for_status = lambda: None
        ob = OpenverseBackend()
        with mock.patch.object(ob, "_session") as session:
            session.get.return_value = resp
            c = ob.search("Ethiopic manuscript", media_type="image")[0]
        self.assertEqual((c.extra["alt"], c.extra["tags"]), ("Ethiopic manuscript cover", "manuscript ethiopia"))
        self.assertEqual(c.extra["license"], "pdm", "the licence is still there")


if __name__ == "__main__":
    unittest.main()


class EnochCandidateGate(unittest.TestCase):
    """Book of Enoch only: a Qur'an or Arabic page is never used, and archives win over stock when they have a picture."""

    def cand(self, provider, alt, url="https://example.org/x.jpg"):
        from providers.stock.base import Candidate, MediaType

        return Candidate(provider=provider, asset_id=f"{provider}:{alt}", media_type=MediaType.IMAGE, url=url, width=3000,
                         height=2000, extra={"alt": alt})

    def test_avoided_subjects_are_dropped_and_archives_come_first(self):
        from style_engine.visual_selection import style_candidate_gate

        enoch = resolve_style(mode="manual", style_id="book_of_enoch", script="")
        c = [self.cand("pexels", "ancient manuscript", "https://www.pexels.com/photo/ancient-manuscript-with-arabic-script-1/"),
             self.cand("pexels", "Holy Quran page"), self.cand("pixabay", "old book"), self.cand("openverse", "Ethiopic manuscript cover")]
        self.assertEqual([x.extra["alt"] for x in style_candidate_gate(c, enoch)], ["Ethiopic manuscript cover"])
        stock_only = [self.cand("pexels", "mountain at dawn")]
        self.assertEqual(style_candidate_gate(stock_only, enoch), stock_only, "with no archive picture, stock still answers")

    def test_other_styles_are_not_gated(self):
        from style_engine.visual_selection import style_candidate_gate

        c = [self.cand("pexels", "Holy Quran page"), self.cand("openverse", "x")]
        self.assertEqual(style_candidate_gate(c, resolve_style(mode="manual", style_id="ancient_history_documentary", script="")), c)
