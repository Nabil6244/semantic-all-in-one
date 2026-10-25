"""StarMap Cinema: more of the video is drawn in 3D -- a world named in the narration becomes a globe with its real map (Saturn with rings),
a map beat that names a craft or world cuts to a short 3D shot of it, and every 3D shot gets its name and a source line."""
import unittest
from types import SimpleNamespace as NS

from starmap import cinema


def beat(i, a, z, text, mode="map"):
    return NS(id=f"b{i}", mode=mode, start=a, end=z, text=text, place="", extra={}, layers=[])


def words(plan_beats):
    out = []
    for b in plan_beats:
        toks = b.text.split()
        step = (b.end - b.start) / max(1, len(toks))
        out += [(w.strip(".,"), b.start + k * step, b.start + (k + 1) * step) for k, w in enumerate(toks)]
    return out


class Globes(unittest.TestCase):
    def test_a_named_world_gets_its_texture_and_saturn_its_rings(self):
        self.assertEqual(cinema._globe_for("Mars orbits at about one and a half units")[:2], ("2k_mars.jpg", "MARS"))
        tex, name, rim, rings = cinema._globe_for("Saturn follows at nearly ten units")
        self.assertEqual((tex, name, rings), ("2k_saturn.jpg", "SATURN", True))
        self.assertIsNone(cinema._globe_for("Zoom out and the dark gets deeper"))

    def test_a_map_beat_naming_a_world_cuts_to_a_globe_where_it_is_named(self):
        bs = [beat(1, 0, 4, "It begins."), beat(2, 4, 16, "Then the map crosses the belt and Jupiter appears near the middle of the screen today.")]
        plan = NS(beats=bs, words=words(bs), duration=16)
        spec = {"duration": 16, "layers": [], "footage": [], "camera": {"moves": []}}
        notes = []
        cinema.variety(spec, plan, notes)
        globes = [L for L in spec["layers"] if L["type"] == "cinema_globe"]
        self.assertEqual(len(globes), 1)
        g = globes[0]
        self.assertEqual(g["texture"], "jupiter_cassini_pia07782.jpg")
        self.assertTrue(4 < g["start"] < g["end"] <= 16 and g["end"] - g["start"] >= 3.0)
        self.assertTrue(any(L["type"] == "tm_caption" and L["text"] == "JUPITER" for L in spec["layers"]))
        self.assertTrue(any("3D" in n for n in notes))

    def test_a_photograph_stays_a_photograph(self):
        bs = [beat(1, 0, 14, "The photo showed Jupiter and its great spot for the first time in colour for everyone.")]
        plan = NS(beats=bs, words=words(bs), duration=14)
        spec = {"duration": 14, "layers": [], "footage": [], "camera": {"moves": []}}
        cinema.variety(spec, plan, [])
        self.assertFalse([L for L in spec["layers"] if L["type"] == "cinema_globe"])

    def test_no_two_3d_shots_overlap_and_the_share_is_capped(self):
        bs = [beat(i, i * 10, i * 10 + 10, f"Beat {i} the map shows Mars and then Venus close by on the screen right now ok.") for i in range(12)]
        plan = NS(beats=bs, words=words(bs), duration=120)
        spec = {"duration": 120, "layers": [], "footage": [], "camera": {"moves": []}}
        cinema.variety(spec, plan, [])
        shots = sorted((L["start"], L["end"]) for L in spec["layers"] if L["type"] in ("cinema_globe", "cinema_craft"))
        for (a, z), (a2, z2) in zip(shots, shots[1:]):
            self.assertLessEqual(z, a2)
        self.assertLessEqual(sum(z - a for a, z in shots), cinema.SHOT_3D_TIME_MAX * 120 + 5)


if __name__ == "__main__":
    unittest.main()
