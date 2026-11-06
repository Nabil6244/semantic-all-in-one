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
