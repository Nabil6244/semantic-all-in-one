"""A canvas that keeps building (product_trailer/canvas.py, REVIEW_REFERENCE_4 gap 2): consecutive flat scenes of the same phones become one
scene on screen; the new facts are added, facts no longer named stay dimmed, nothing re-enters. Scenes with nothing new still cut."""
import unittest

from product_trailer import canvas as K


def scene(a, b, phones, title=None):
    shot = {"id": f"s{int(a)}", "kind": "black", "start": a, "end": b}
    flat = {"type": "pt_flatphones", "phones": phones, "start": a + 0.05, "end": b - 0.05}
    if title:
        flat["title"] = title
    return shot, [{"type": "pt_paper", "start": a, "end": b, "fade_in": 0, "fade_out": 0}, flat]


def film(*scenes):
    shots, layers = [], []
    for s, ls in scenes:
        shots.append(s)
        layers.extend(ls)
    return shots, layers


def flats(layers):
    return [L for L in layers if L["type"] == "pt_flatphones"]


FOUR = ["Galaxy S27", "Galaxy S27+", "Galaxy S27 Pro", "Galaxy S27 Ultra"]


class Build(unittest.TestCase):
    def test_same_phones_with_new_facts_continue_the_canvas(self):
        a = scene(0, 5, [{"label": n, "badge": c} for n, c in zip(FOUR, ["Exynos", "Exynos", "Snapdragon", "Snapdragon"])], "Chips")
        b = scene(5, 10, [{"label": n, "top": "12GB RAM"} for n in FOUR])
        shots, layers = film(a, b)
        K.build(shots, layers)
        f1, f2 = flats(layers)
        self.assertTrue(f1.get("keep"), "the first scene does not fade out")
        self.assertAlmostEqual(f1["end"], 5.0)
        self.assertTrue(f2.get("cont"), "the second scene does not re-enter")
        self.assertEqual((f1["fade_out"], f2["fade_in"]), (0, 0), "no fade dip at the join")
        self.assertAlmostEqual(f2["start"], 5.0)
        self.assertEqual(f2["t0"], f1["start"], "one slow push across the whole canvas")
        p = f2["phones"][0]
        self.assertEqual(p["badge"], "Exynos")
        self.assertIn("badge", p["dim"])
        self.assertIn("top", p["fresh"])
        self.assertEqual(f2["title"], "Chips")

    def test_a_replaced_value_is_fresh_not_dimmed(self):
        a = scene(0, 4, [{"label": "S27", "text": "??MP"}, {"label": "S27 Plus", "text": "??MP"}])
        b = scene(4, 8, [{"label": "S27", "text": "10MP"}, {"label": "S27 Plus", "text": "10MP"}])
        shots, layers = film(a, b)
        K.build(shots, layers)
        p = flats(layers)[1]["phones"][0]
        self.assertEqual(p["text"], "10MP")
        self.assertEqual(p["fresh"], ["text"])
        self.assertNotIn("text", p.get("dim", []))
        self.assertEqual(p["was"], {"text": "??MP"}, "the old value shows until the new one is said")

    def test_different_phones_still_cut(self):
        a = scene(0, 4, [{"label": "Galaxy S27 Ultra", "text": "5000mAh"}])
        b = scene(4, 8, [{"label": "iPhone 18 Pro Max", "text": "4800mAh"}])
        shots, layers = film(a, b)
        K.build(shots, layers)
        self.assertFalse(any(L.get("cont") or L.get("keep") for L in flats(layers)))

    def test_nothing_new_still_cuts(self):
        ph = [{"label": "Galaxy S27 Ultra", "text": "60W"}]
        shots, layers = film(scene(0, 4, ph), scene(4, 8, [dict(x) for x in ph]))
        K.build(shots, layers)
        self.assertFalse(any(L.get("cont") for L in flats(layers)))

    def test_a_gap_between_scenes_breaks_the_canvas(self):
        a = scene(0, 4, [{"label": "S27", "text": "A"}])
        mid = ({"id": "x", "kind": "product", "start": 4, "end": 6}, [])
        b = scene(6, 9, [{"label": "S27", "text": "B"}])
        shots, layers = film(a, mid, b)
        K.build(shots, layers)
        self.assertFalse(any(L.get("cont") for L in flats(layers)))

    def test_a_canvas_is_capped(self):
        scs = [scene(4 * i, 4 * i + 4, [{"label": "S27", "text": str(i)}]) for i in range(K.MAX_CHAIN + 2)]
        shots, layers = film(*scs)
        K.build(shots, layers)
        conts = [bool(L.get("cont")) for L in flats(layers)]
        self.assertEqual(conts[:K.MAX_CHAIN], [False] + [True] * (K.MAX_CHAIN - 1))
        self.assertFalse(conts[K.MAX_CHAIN], "a new canvas starts after the cap")

    def test_held_copies_are_left_alone(self):
        a = scene(0, 4, [{"label": "S27", "text": "A"}])
        b = scene(4, 8, [{"label": "S27", "text": "A"}])
        b[1][1]["hold"] = True
        shots, layers = film(a, b)
        K.build(shots, layers)
        self.assertFalse(flats(layers)[1].get("cont"))


class WordCueOnContinuation(unittest.TestCase):
    def test_continuation_times_fresh_facts_and_never_hides_phones(self):
        from product_trailer import wordcue as C
        W = C.wtimes([("all", 5.0, 5.2), ("four", 5.3, 5.5), ("start", 5.6, 5.8), ("with", 5.9, 6.0), ("12GB", 6.1, 6.4), ("RAM", 6.5, 6.7)])
        L = {"type": "pt_flatphones", "cont": True, "start": 5.0, "end": 9.0,
             "phones": [{"label": "Galaxy S27", "top": "12GB RAM", "fresh": ["top"]}, {"label": "Galaxy S27 Ultra", "top": "12GB RAM", "fresh": ["top"]}]}
        C.cue_layers([L], W)
        self.assertAlmostEqual(L["phones"][0]["at"], 1.1, places=1)


class PlannerHook(unittest.TestCase):
    def test_timed_review_builds_one_canvas_from_two_scene_directives(self):
        from product_trailer import review, voiceover as V
        lines = ["All four models start with twelve gigs of memory.", "The Ultra adds a sixteen gig model with one terabyte."]
        p1 = '[scene: {"title": "Memory", "phones": [{"label": "Galaxy S27", "top": "12GB RAM"}, {"label": "Galaxy S27 Ultra", "top": "12GB RAM"}]}]'
        p2 = '[scene: {"title": "Memory", "phones": [{"label": "Galaxy S27", "top": "12GB RAM"}, {"label": "Galaxy S27 Ultra", "top": "12GB RAM", "badge": "16GB / 1TB"}]}]'
        parsed = review.parse_script("# R\n" + p1 + "\n" + lines[0] + "\n" + p2 + "\n" + lines[1] + "\n")
        pack = review.plan_review_scenes(parsed, "galaxy s27 ultra", ["Black"])
        W, t = [], 0.5
        for ln in lines:
            for w in ln.split():
                W.append((w.strip(".,"), round(t, 3), round(t + 0.28, 3)))
                t += 1 / 3
            t += 0.6
        voice = V.align_lines(lines, W, W[-1][2] + 1.0)
        spec = review.plan_review_timed(parsed, pack, {}, voice, W, style="infographic")
        mine = [L for L in spec["layers"] if L["type"] == "pt_flatphones" and L["phones"][0].get("label") == "Galaxy S27"]
        self.assertEqual(len(mine), 2)
        self.assertTrue(mine[0].get("keep") and mine[1].get("cont"))
        self.assertIn("badge", mine[1]["phones"][1]["fresh"])


if __name__ == "__main__":
    unittest.main()
