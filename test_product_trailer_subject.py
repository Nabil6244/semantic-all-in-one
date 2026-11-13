"""The film's phone drawn with its own camera on the flat graphics (product_trailer/subject.py); compared phones keep theirs."""
import unittest

from product_trailer import subject as SJ


class Camera(unittest.TestCase):
    def test_layouts_follow_the_3d_engine(self):
        self.assertEqual(SJ.camera_of("iPhone Duo"), ("iphone", 2))           # no preset: an iPhone that is not a Pro has two lenses
        self.assertEqual(SJ.camera_of("iPhone 17 Pro"), ("iphone", 3))
        self.assertEqual(SJ.camera_of("Galaxy S27 Ultra")[1], 3)               # its preset: the S27 camera bar, three lenses
        self.assertEqual(SJ.camera_of("Pixel 10 Pro")[0], "pixel")

    def test_only_the_films_phone_changes(self):
        L = [{"type": "pt_flatphones", "phones": [{"label": "iPhone Duo", "cams": 3, "design": "x"}, {"label": "iPhone 18 Pro", "cams": 3}]},
             {"type": "pt_lenses", "phones": [{"label": "iPhone Duo"}]}]
        SJ.fix_phones(L, "iphone duo")
        self.assertEqual((L[0]["phones"][0]["cams"], L[0]["phones"][0]["design"]), (2, "iphone"))
        self.assertEqual(L[0]["phones"][1], {"label": "iPhone 18 Pro", "cams": 3})
        self.assertEqual(L[1]["phones"][0]["cams"], 2)


class Planner(unittest.TestCase):
    def test_timed_review_draws_the_films_phone_right(self):
        import inspect
        from product_trailer import review
        self.assertIn("fix_phones(layers", inspect.getsource(review.plan_review_timed))


if __name__ == "__main__":
    unittest.main()


def test_compared_phones_get_their_own_preset_camera():
    """iPhone Air 2 film: the iPhone 18 card has the base iPhone's vertical pill, the Air the one-lens plateau, the Air 2 two lenses."""
    from product_trailer import subject as S
    L = [{"type": "pt_flatphones", "phones": [{"label": "iPhone Air 2"}, {"label": "iPhone 18"}, {"label": "iPhone Air"}, {"label": "Earlier leak"}]}]
    S.fix_phones(L, "iPhone Air 2")
    got = [(p.get("design"), p.get("cams")) for p in L[0]["phones"]]
    assert got[:3] == [("air", 2), ("pill", 2), ("air", 1)]
    assert got[3] == (None, None)                     # a label that is not a phone is left as written


def test_3d_phone_follows_the_sentence_subject():
    from product_trailer import subject as S
    lines = ["Apple's next iPhone Air may fix its biggest problem.", "The original iPhone Air has one camera.", "Leak number two: the iPhone 18.",
             "This dummy looks almost identical to the iPhone 17.", "Samsung's Galaxy S27 Pro is the competition.", "It has a big camera."]
    names = [(p or {}).get("name") for p in S.subjects(lines, "iPhone Air 2")]
    assert names == ["iPhone Air 2", "iPhone Air", "iPhone 18", "iPhone 18", "Galaxy S27 Pro", "Galaxy S27 Pro"]
    spec = {"shots": [{"kind": "product", "object": "phone", "phone": "iPhone Air 2", "color": "Sky Blue", "start": t, "end": t + 1.0} for t in range(6)]}
    assert S.follow(spec, lines, [float(t) for t in range(6)], "iPhone Air 2") == 5
    assert [s["phone"] for s in spec["shots"]] == ["iPhone Air 2", "iPhone Air", "iPhone 18", "iPhone 18", "Galaxy S27 Pro", "Galaxy S27 Pro"]
    assert "color" not in spec["shots"][2]               # "Sky Blue" is not an iPhone 18 colour: its own default is used
