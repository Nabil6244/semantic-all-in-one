"""Doc Style (the app-wide switch in Audio & Effects > Smart editing): graphics drawn in the News Doc look; off, nothing changes."""

import inspect
import tempfile
import unittest
from pathlib import Path

from graphics.doc_style import pick_look, render_doc_style
from graphics.render import render_graphic_overlay
from graphics.schema import GraphicSpec, TextOverlaySpec


def _spec(role, text, sub="", decision="TEXT", **meta):
    return GraphicSpec(graphic_id="g", decision=decision, role=role,
                       text=TextOverlaySpec(role=role, text=text, secondary_text=sub, metadata=meta))


class PickLook(unittest.TestCase):
    def test_roles(self):
        self.assertEqual(pick_look(_spec("STATISTIC", "150 mph", "wind", "STATISTIC"))[0], "number")
        self.assertEqual(pick_look(_spec("STATISTIC", "70%", "rain", "STATISTIC"))[0], "ring")
        self.assertFalse(pick_look(_spec("STATISTIC", "2,000", "years", "STATISTIC", big_number=True))[1]["corner"])
        self.assertEqual(pick_look(_spec("LOWER_THIRD", "Maria Lopez", "manager", "LOWER_THIRD"))[0], "nametag")
        self.assertEqual(pick_look(_spec("LOCATION", "Mount Hermon"))[0], "place")
        self.assertEqual(pick_look(_spec("CALLOUT", "The fallen angels", decision="CALLOUT"))[0], "ytag")
        self.assertEqual(pick_look(_spec("QUOTE", "They taught charms", "Enoch 7:1"))[0], "pullquote")
        self.assertEqual(pick_look(_spec("CHAPTER", "The Watchers"))[0], "chapter")
        self.assertEqual(pick_look(_spec("TITLE", "1947"))[0], "year")
        self.assertEqual(pick_look(_spec("CAPTION", "A text older than the Bible"))[0], "caption")

    def test_chart_and_countdown(self):
        dv = {"kind": "comparison", "title": "Rain", "points": [{"label": "A", "value": 3, "display": "3"},
                                                               {"label": "B", "value": 5, "display": "5"}]}
        s = GraphicSpec(graphic_id="d", role="DATA", text=TextOverlaySpec(text="Rain"),
                        payload={"template": "dataviz_comparison", "dataviz": dv})
        self.assertEqual(pick_look(s)[0], "chart")
        dv["kind"] = "change"
        self.assertEqual(pick_look(s)[0], "line")
        s.payload["template"] = "countdown_tag"
        self.assertIsNone(pick_look(s))   # a style's own reference look stays


class Render(unittest.TestCase):
    def test_doc_differs_and_off_is_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _spec("LOWER_THIRD", "Maria Lopez", "manager", "LOWER_THIRD")
            a = render_graphic_overlay(sp, Path(d) / "a.png", 1920, 1080)
            b = render_graphic_overlay(sp, Path(d) / "b.png", 1920, 1080, look="")
            c = render_graphic_overlay(sp, Path(d) / "c.png", 1920, 1080, look="doc")
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertNotEqual(a.read_bytes(), c.read_bytes())

    def test_not_16_9_keeps_usual_graphics(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(render_doc_style(_spec("LOCATION", "X"), Path(d) / "v.png", 1080, 1920))

    def test_render_video_default_off(self):
        import video_generator as vg

        self.assertEqual(inspect.signature(vg.render_video).parameters["graphics_look"].default, "")



class Extras(unittest.TestCase):
    """The News Doc looks a normal plan never asks for, placed from the narration, one graphic at a time."""

    SEGS = ["Hurricane Ian struck Florida in 2022. Hurricane Ian was one of the strongest storms the state had seen.",
            "It came ashore near Fort Myers with winds of 150 mph.", "For days the sky stayed dark over the gulf.",
            "Residents had to choose between staying and leaving.",
            "Many stayed because the warnings came late and the roads were already full of traffic.",
            "The wind tore roofs off.", "Families waited for news.",
            "Crews checked Sanibel, Captiva, Naples, Punta Gorda and Fort Myers Beach.", "Power lines lay across roads.",
            "Some neighborhoods had no water.", "Three threats came at once: wind, water, power.", "Shelters filled up.",
            "The river rose Monday 14 feet, Tuesday 18 feet and Wednesday 16 feet.", "Volunteers came.",
            "Nobody had ever seen water rise this fast in the city.", "Teams worked through the night."] * 2

    def _plan(self, existing=(), channel=""):
        from graphics.doc_plan import plan_doc_extras

        rows, tl, t = [], [], 0.0
        for i, s in enumerate(self.SEGS):
            rows.append({"scene_number": str(i + 1), "script_segment": s, "start_time": t})
            tl.append((t, t + 8.0))
            t += 8.0
        return plan_doc_extras(rows, tl, list(existing), lambda k: "still.jpg", channel=channel), tl

    def test_detects_each_look(self):
        from graphics.doc_plan import _detect

        self.assertEqual(_detect("Crews checked Sanibel, Captiva, Naples, Punta Gorda and Fort Myers Beach.", True),
                         ("checklist", {"title": "CREWS CHECKED", "items": ["Sanibel", "Captiva", "Naples", "Punta Gorda", "Fort Myers Beach"]}))
        self.assertEqual(_detect("Three threats came at once: wind, water, power.", True)[0], "rings")
        self.assertEqual(_detect("He was tired, hungry and cold, but he kept going.", True)[1]["items"], ["TIRED", "HUNGRY", "COLD"])
        self.assertEqual(_detect("The river rose Monday 14 feet, Tuesday 18 feet and Wednesday 16 feet.", True)[1]["values"], ["14", "18", "16"])
        self.assertEqual(_detect("Residents had to choose between staying and leaving.", True)[0], "polaroids")
        self.assertNotEqual((_detect("Residents had to choose between staying and leaving.", False) or ("",))[0], "polaroids")
        self.assertEqual(_detect("Many stayed because the warnings came late and the roads were full.", True)[0], "panel")
        self.assertEqual(_detect("Nobody had ever seen water rise this fast.", True)[0], "quote")
        self.assertEqual(_detect("Rescue teams worked in Lee County all day.", True), ("framed", {"caption": "LEE COUNTY"}))
        self.assertIsNone(_detect("I went home.", True))

    def test_one_graphic_at_a_time(self):
        existing = [GraphicSpec(graphic_id="s", role="STATISTIC", decision="STATISTIC", start=9.0, end=12.0,
                                text=TextOverlaySpec(text="150 mph"))]
        extras, _ = self._plan(existing, channel="My Channel")
        looks = {e.payload["doc_look"] for e in extras}
        for want in ("dossier", "checklist", "forecast", "quote", "glitch", "watermark"):
            self.assertIn(want, looks)
        shown = sorted([e for e in extras if e.decision != "WATERMARK"] + existing, key=lambda e: e.start)
        for a, b in zip(shown, shown[1:]):
            self.assertLessEqual(a.end, b.start, f"{a.graphic_id} overlaps {b.graphic_id}")
        full = [e.start for e in extras if e.payload["doc_look"] in ("checklist", "rings", "forecast", "polaroids", "quote_card", "framed", "dossier")]
        self.assertTrue(all(b - a >= 25.0 for a, b in zip(full, full[1:])))

    def test_smart_text_never_draws_over_a_doc_graphic(self):
        from graphics.conflicts import filter_smart_text_for_graphics

        extras, tl = self._plan(channel="My Channel")
        card = next(e for e in extras if e.payload["doc_look"] == "checklist")
        wm = next(e for e in extras if e.payload["doc_look"] == "watermark")
        a = tl[int(card.scene_number) - 1][0]
        over = {"text": "something else entirely", "local_start": card.start - a + 0.5, "local_end": card.start - a + 1.5}
        clear = {"text": "something else entirely", "local_start": 0.0, "local_end": 0.0001}
        kept = filter_smart_text_for_graphics([over], [card, wm], scene_start=a, scene_end=a + 8.0)
        self.assertEqual(kept, [])
        # the corner watermark alone never stops Smart Text
        self.assertEqual(filter_smart_text_for_graphics([clear], [wm], scene_start=a, scene_end=a + 8.0), [clear])

    def test_extras_draw(self):
        extras, _ = self._plan(channel="My Channel")
        with tempfile.TemporaryDirectory() as d:
            for e in extras:
                if e.payload["doc_look"] in ("polaroids", "framed"):
                    continue   # need real stills
                self.assertIsNotNone(render_graphic_overlay(e, Path(d) / f"{e.graphic_id}.png", 1920, 1080, look="doc"), e.graphic_id)


if __name__ == "__main__":
    unittest.main()
