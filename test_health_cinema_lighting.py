"""Health Cinema's 3D look (threejs/page.js): the tissue lighting is opt-in per spec, so other users of the same page (Rep Theory's muscle clips) keep the
classic look, and everything it loads ships with the app."""
import unittest
from pathlib import Path

from health_cinema import assets, clips

PAGE = (Path(__file__).resolve().parent / "health_cinema" / "threejs" / "page.js").read_text(encoding="utf-8")
ATMO = (Path(__file__).resolve().parent / "health_cinema" / "threejs" / "atmosphere.js").read_text(encoding="utf-8")


class TissueLook(unittest.TestCase):
    def test_tissue_is_switched_on_by_the_spec_only(self):
        self.assertIn("const tissue = spec.lighting === 'tissue';", PAGE)
        self.assertEqual(clips.LIGHTING, "tissue")

    def test_the_classic_look_is_kept_for_specs_without_it(self):
        # the classic material and light rig are the else-branches of the switch, unchanged
        self.assertIn("else { o.material.envMapIntensity = 0; o.material.roughness = Math.max(o.material.roughness, 0.62); }", PAGE)
        self.assertIn("[['key', 3.0, [0.9, 0.7, 0.9], 0xffffff], ['fill', 0.9, [-1, 0.2, 0.7], 0xffffff], ['rim', 2.2, [0, 0.5, -1], 0xffffff]]", PAGE)
        self.assertIn("atmo?.update(f, lk, tissue ? cam.position : null)", PAGE)

    def test_room_light_strength_is_set_on_the_scene(self):
        # scene.environment ignores a material's envMapIntensity: the strength must be the scene's, or the picture blows out
        self.assertIn("scene.environmentIntensity = spec.env_intensity ??", PAGE)

    def test_motes_near_the_lens_fade_out(self):
        self.assertIn("update(f, look, cam = null)", ATMO); self.assertIn("vertexColors: true", ATMO)

    def test_the_room_environment_ships(self):
        self.assertIn("environments/RoomEnvironment.js", assets.THREE_ADDONS)
        self.assertNotIn("three/examples/jsm/environments/RoomEnvironment.js", assets.missing_threejs_files())


if __name__ == "__main__":
    unittest.main()
