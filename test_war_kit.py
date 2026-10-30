"""War Documentary kit cards: deterministic, inside the frame, transparent where they must be, registered, safe on odd input."""
import hashlib
import time
import unittest

from PIL import Image

from cinematic_explainer.war import cards_kit as K, registry, stickers as S

P = {
    "kit_tag": {"text": "Satellites and AI", "sub": "A war on hands and knees", "pos": "top-centre"},
    "kit_stamp": {"status": "claimed", "text": "Claimed by Moscow", "sub": "no independent confirmation"},
    "kit_chips": {"chips": [{"title": "Kupiansk", "sub": "Illustrative position", "variant": "dark"}, {"title": "Taken", "variant": "red"},
                            {"title": "Liberated", "variant": "blue"}, {"title": "Note", "sub": "x " * 30, "variant": "paper"}]},
    "kit_recap": {"title": "Put those together", "items": ["Record casualties", {"text": "A front barely moving", "sub": "fixture"}, "A transparent battlefield"]},
    "kit_sticker": {"name": "tank", "label": "Frozen ground"},
    "kit_ribbon": {"text": "Section two"},
    "kit_bignum": {"value": "46,000+", "label": "Worst month", "sub": "fixture"},
    "kit_scale": {"n": 10, "label": "10 soldiers single file", "bar_label": "A pipe"},
    "kit_badge": {"kind": "ai", "channel": "Channel"},
    "kit_grain": {},
    "kit_chapter": {"label": "Chapter two", "sub": "The Black Sea"},
    "kit_speaker": {"name": "Michel Hofman", "role": "Belgian analyst"},
    "kit_versus": {"a": "18", "a_label": "this year", "b": "6", "b_label": "the year before"},
    "kit_icons": {"icons": [{"name": "drone", "label": "drones"}, {"name": "crate", "label": "ammunition"}], "link": "arrow", "title": "Small, slow, cheap"},
    "kit_flag": {"iso3": "UKR"},
}
DUR = 3.2


def h(im):
    return hashlib.sha1(im.tobytes()).hexdigest()


class Registered(unittest.TestCase):
    def test_all_kinds_in_registry(self):
        cards = registry.all_cards()
        for k in K.KIT_CARDS:
            self.assertIn(k, cards)
        self.assertEqual(set(K.KIT_CARDS), set(P))


class Cards(unittest.TestCase):
    def test_size_deterministic_and_inside_frame(self):
        for kind, fn in K.KIT_CARDS.items():
            d = 2.0 if kind == "kit_ribbon" else DUR
            for t in (0.15, 0.6, 1.2):
                a, b = fn(t, d, P[kind]), fn(t, d, P[kind])
                self.assertEqual(a.size, (1280, 720), kind)
                self.assertEqual(a.mode, "RGBA", kind)
                self.assertEqual(h(a), h(b), f"{kind} not deterministic at {t}")
                if kind in ("kit_ribbon", "kit_grain", "kit_bignum", "kit_versus", "kit_icons", "kit_flag"):   # bignum and versus have a full-height scrim that bleeds off the left edge by design
                    continue
                bb = a.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
                if bb:
                    self.assertGreaterEqual(bb[0], 2, kind)
                    self.assertGreaterEqual(bb[1], 2, kind)
                    self.assertLessEqual(bb[2], 1278, kind)
                    self.assertLessEqual(bb[3], 718, kind)

    def test_ribbon_transparent_at_start_and_end(self):
        for t in (0.0, 2.0):
            self.assertIsNone(K.kit_ribbon(t, 2.0, P["kit_ribbon"]).getchannel("A").getbbox())
        self.assertIsNotNone(K.kit_ribbon(1.0, 2.0, P["kit_ribbon"]).getchannel("A").getbbox())

    def test_fade_out_at_end(self):
        for kind in ("kit_tag", "kit_chips", "kit_sticker", "kit_scale", "kit_bignum", "kit_recap"):
            late = K.KIT_CARDS[kind](DUR, DUR, P[kind])
            self.assertIsNone(late.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox(), kind)

    def test_chips_are_revealed_one_by_one(self):
        def n_visible(t):
            im = K.kit_chips(t, DUR, P["kit_chips"])
            col = im.crop((900, 0, 1280, 720)).getchannel("A").point(lambda v: 255 if v > 200 else 0)
            return sum(1 for y in range(0, 720, 4) if col.getpixel((200, y)) == 255)
        self.assertLess(n_visible(0.4), n_visible(2.4))

    def test_bignum_counts_up_and_formats(self):
        a, b = K.kit_bignum(0.3, DUR, P["kit_bignum"]), K.kit_bignum(1.5, DUR, P["kit_bignum"])
        self.assertNotEqual(h(a), h(b))
        self.assertEqual(K._parse_value("46,000+")[:3], ("", 46000.0, "+"))
        self.assertEqual(K._parse_value("≈26,000")[:3], ("≈", 26000.0, ""))
        self.assertEqual(K._parse_value(2200)[3], True)

    def test_scale_carries_illustrative_chip_and_caps_count(self):
        self.assertIsNotNone(K.kit_scale(1.5, DUR, {"n": 500}))
        self.assertIsNone(K.kit_scale(1.5, DUR, {"n": 0}))

    def test_grain_is_deterministic_per_frame_and_varies(self):
        g0, g1 = K.kit_grain(0.0, 10, {}), K.kit_grain(0.04, 10, {})
        self.assertNotEqual(h(K.kit_grain(1.0, 10, {})), h(g1))
        self.assertEqual(h(K.kit_grain(2.0, 10, {})), h(K.kit_grain(2.0, 10, {})))

    def test_odd_input_never_raises(self):
        for kind, fn in K.KIT_CARDS.items():
            for bad in (None, {}, {"text": None, "items": "x", "chips": [None, 3], "n": "ten", "name": 5, "value": None}):
                for t in (0.0, 1.0, 99.0):
                    out = fn(t, DUR, bad)
                    self.assertTrue(out is None or out.size == (1280, 720), kind)

    def test_empty_text_gives_nothing(self):
        for kind in ("kit_tag", "kit_chips", "kit_recap", "kit_bignum"):
            self.assertIsNone(K.KIT_CARDS[kind](1.0, DUR, {}))

    def test_frame_cost_is_small_after_warmup(self):
        for kind, fn in K.KIT_CARDS.items():
            fn(1.0, DUR, P[kind])
            t0 = time.time()
            for i in range(6):
                fn(1.0 + i * 0.04, DUR, P[kind])
            self.assertLess((time.time() - t0) / 6, 0.25, kind)


class Stickers(unittest.TestCase):
    def test_every_name_draws(self):
        for n in S.NAMES:
            im = S.draw_sticker(n, 96)
            self.assertEqual(im.size, (96, 96))
            self.assertIsNotNone(im.getchannel("A").getbbox(), n)

    def test_unknown_name_is_a_question_mark_and_never_raises(self):
        self.assertEqual(h(S.draw_sticker("nope", 64)), h(S.draw_sticker("question", 64)))
        S.draw_sticker(None, 64)

    def test_soldiers_row(self):
        im = S.soldiers(5, 100)
        self.assertEqual(im.height, 100)
        self.assertGreater(im.width, 200)

    def test_colour_override(self):
        self.assertNotEqual(h(S.draw_sticker("tank", 64)), h(S.draw_sticker("tank", 64, (255, 0, 0))))


if __name__ == "__main__":
    unittest.main()
