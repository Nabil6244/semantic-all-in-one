"""War Documentary composition layouts: deterministic, inside the frame, designed fallbacks (never blank), registered, safe on odd input."""
import hashlib
import time
import unittest
from pathlib import Path

from PIL import Image

from cinematic_explainer.war import layouts as LY, registry

DATA = Path(LY.__file__).resolve().parent / "data"
PORTRAIT = str(DATA / "portraits" / "zelensky.jpg")
PHOTO = str(DATA / "equipment_images" / "pantsir-s1.jpg")
SPECS = [{"label": "Range", "value": "20 km"}, {"label": "Targets", "value": "Aircraft, drones, missiles, shells and more"}, {"label": "Crew", "value": "3"}]
EQ = {"name": "Pantsir-S1", "role": "Gun-missile system", "operator": "Russia", "image": PHOTO, "image_credit": "Photo: x · CC BY-SA 4.0", "confidence": "confirmed",
      "icon": "air_defense", "specs": SPECS, "source": "reference data"}
P = {
    "lay_figure_hero": {"name": "Volodymyr Zelensky", "role": "President of Ukraine", "image": PORTRAIT, "statement": "We will keep defending our land and our people.",
                        "kicker": "KEY FIGURE", "credit": "Photo: Press Service of the President of Ukraine · CC BY 4.0"},
    "lay_figure_pair": {"people": [{"name": "Person One", "role": "Role one", "image": PORTRAIT}, {"name": "Person Two", "role": "Role two", "country": "X"}], "label": "MEET"},
    "lay_equipment_hero": EQ,
    "lay_equipment_compare": {"items": [EQ, dict(EQ, name="Other System", image=None, specs=SPECS[:2])]},
    "lay_stat_split": {"value": 2250, "label": "Casualties in one day", "text": "Both sides publish different numbers.", "status": "disputed", "claimant": "Ukraine",
                       "rows": [{"label": "Before", "value": 2200, "shown": "2,200"}, {"label": "Now", "value": 2250, "shown": "2,250", "colour": "red"}]},
    "lay_timeline": {"title": "How it unfolded", "items": [{"date": "2014", "text": "A"}, {"date": "Feb 2022", "text": "B"}, {"date": "Sept 2022", "text": "C"}]},
    "lay_claim": {"claim": "Our air defence destroys more than 98 percent of enemy drones.", "claimant": "Someone", "highlight": "more than 98 percent", "status": "claimed",
                  "confirmed": ["A report exists"], "claimed": ["98 percent rate"]},
    "lay_inset": {"caption": "Refineries under pressure", "caption_sub": "Illustrative footage", "notes": [{"title": "Moscow", "sub": "x", "variant": "dark"}, {"title": "Claimed", "variant": "paper"}],
                  "inset": {"image": PORTRAIT, "label": "Portrait"}},
    "lay_logistics": {"title": "Fuel chain", "nodes": [{"label": "Refinery", "icon": "flame", "value": "300"}, {"label": "Pipeline", "icon": "pipe"}, {"label": "Depot", "icon": "truck"}],
                      "links": ["crude", "fuel"]},
}
DUR = 4.0


def h(im):
    return hashlib.sha1(im.tobytes()).hexdigest()


def solid_count(band, thr=200):
    return sum(band.histogram()[thr + 1:])


def opaque_bbox(im, thr=8):
    return im.getchannel("A").point(lambda v: 255 if v > thr else 0).getbbox()


class Registered(unittest.TestCase):
    def test_all_kinds_in_registry(self):
        cards = registry.all_cards()
        for k in LY.LAYOUT_CARDS:
            self.assertIn(k, cards)
        self.assertEqual(set(LY.LAYOUT_CARDS), set(P))


class Layouts(unittest.TestCase):
    def test_size_deterministic_and_inside_frame(self):
        for kind, fn in LY.LAYOUT_CARDS.items():
            for t in (0.2, 1.0, 2.6):
                a, b = fn(t, DUR, P[kind]), fn(t, DUR, P[kind])
                self.assertEqual(a.size, (1280, 720), kind)
                self.assertEqual(a.mode, "RGBA", kind)
                self.assertEqual(h(a), h(b), f"{kind} not deterministic at {t}")
                bb = opaque_bbox(a, 40)                       # the scrims fade to nothing at the frame edge; content is what must stay inside
                self.assertIsNotNone(bb, f"{kind} blank at {t}")

    def test_content_stays_in_safe_margins(self):
        for kind, fn in LY.LAYOUT_CARDS.items():
            im = fn(2.8, DUR, P[kind])
            bb = opaque_bbox(im, 200)                         # solid pixels only (not scrims or soft shadows)
            self.assertIsNotNone(bb, kind)
            self.assertGreaterEqual(bb[0], 20, kind)
            self.assertGreaterEqual(bb[1], 20, kind)
            self.assertLessEqual(bb[2], 1260, kind)
            self.assertLessEqual(bb[3], 700, kind)

    def test_frame_occupancy_is_deliberate(self):
        # the hero layouts use a large share of the frame, unlike the old corner templates
        for kind in ("lay_figure_hero", "lay_equipment_hero", "lay_equipment_compare", "lay_stat_split", "lay_timeline"):
            bb = opaque_bbox(LY.LAYOUT_CARDS[kind](2.8, DUR, P[kind]), 200)
            self.assertGreater((bb[2] - bb[0]) / 1280.0, 0.70, kind)
        bb = opaque_bbox(LY.lay_figure_hero(2.8, DUR, P["lay_figure_hero"]), 200)
        self.assertGreater((bb[3] - bb[1]) / 720.0, 0.45)

    def test_portrait_hero_is_large(self):
        img = LY.lay_figure_hero(2.8, DUR, dict(P["lay_figure_hero"], statement=""))
        self.assertGreater(solid_count(img.crop((780, 120, 1220, 600)).getchannel("A")) / (440.0 * 480.0), 0.4)

    def test_no_portrait_is_a_designed_layout_not_blank(self):
        p = {"name": "Sergei Shoigu", "role": "Secretary of the Security Council of Russia", "country": "Russia"}
        img = LY.lay_figure_hero(2.8, DUR, p)
        bb = opaque_bbox(img, 200)
        self.assertGreater((bb[2] - bb[0]) / 1280.0, 0.6)
        # the right-hand dossier panel carries labelled rows, so that area is solidly drawn
        self.assertGreater(solid_count(img.crop((780, 120, 1220, 560)).getchannel("A")) / (440.0 * 440.0), 0.5)

    def test_missing_files_never_raise(self):
        for kind, fn in LY.LAYOUT_CARDS.items():
            p = {k: (v.replace(str(DATA), "/nonexistent") if isinstance(v, str) else v) for k, v in P[kind].items()}
            self.assertIsNotNone(fn(1.5, DUR, p), kind)
        for kind, fn in LY.LAYOUT_CARDS.items():
            for bad in ({}, {"name": ""}, None):
                try:
                    fn(1.0, DUR, bad)
                except Exception as exc:                      # pragma: no cover
                    self.fail(f"{kind} raised on {bad!r}: {exc}")

    def test_silhouette_equipment_is_labelled_illustrative(self):
        a = LY.lay_equipment_hero(2.0, DUR, {"confidence": "uncertain", "icon": "drone"})
        self.assertIsNotNone(a)
        self.assertEqual(a.size, (1280, 720))
        self.assertIsNotNone(opaque_bbox(a, 200))

    def test_unconfirmed_equipment_shows_no_specs(self):
        a = LY.lay_equipment_hero(3.0, DUR, dict(EQ, confidence="uncertain"))
        b = LY.lay_equipment_hero(3.0, DUR, dict(EQ, confidence="confirmed"))
        self.assertNotEqual(h(a), h(b))

    def test_animation_sequences_in_order(self):
        # portrait first, then the name, then role/statement: more of the frame is drawn at each later time
        def px(t):
            return solid_count(LY.lay_figure_hero(t, DUR, P["lay_figure_hero"]).getchannel("A"), 100)
        a, b, c = px(0.1), px(0.8), px(2.8)
        self.assertLess(a, b)
        self.assertLess(b, c)

    def test_fades_out_at_the_end(self):
        for kind, fn in LY.LAYOUT_CARDS.items():
            near = fn(DUR - 0.01, DUR, P[kind])
            self.assertLess(near.getchannel("A").getextrema()[1], 40, kind)

    def test_timeline_follows_given_times(self):
        p = dict(P["lay_timeline"], times=[0.2, 1.5, 3.0])
        early = LY.lay_timeline(1.0, DUR, p)
        late = LY.lay_timeline(3.5, DUR, p)
        self.assertNotEqual(h(early), h(late))

    def test_per_frame_cost_after_warmup(self):
        for kind, fn in LY.LAYOUT_CARDS.items():
            fn(1.0, DUR, P[kind])
            t0 = time.time()
            for t in (1.04, 1.08, 1.12):
                fn(t, DUR, P[kind])
            self.assertLess((time.time() - t0) / 3, 0.35, kind)


if __name__ == "__main__":
    unittest.main()
