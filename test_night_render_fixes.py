"""Fixes from the 2026-11-17 overnight renders (Elder sound, Aviation clip repeats, War blank wall / maps / dates, Baby Talk)."""
import subprocess
from pathlib import Path


def test_elder_sounds_are_calm():
    from reptheory import sound as S, theme as T
    scenes = [{"start": float(i * 4), "end": float(i * 4 + 4), "kind": "illus", "text": "drink water", "chapter_card": {"title": "Part two"} if i == 3 else None} for i in range(12)]
    T.set_theme("elder")
    try:
        cs = S.cues(scenes)
        assert all(c["sfx"] not in S.CALM_DROP for c in cs)
        assert all(c["t"] in (12.0,) for c in cs if c["sfx"] == "soft_transition")      # a transition only where a chapter starts
        assert S._mood() == "wonder"
        assert S._quiet("subtle_pop").startswith("rtq_calm_")
    finally:
        T.set_theme("")


def test_aviation_clipless_lines_go_on_the_stage_at_render():
    from aviation import planner as P

    class C:
        def __init__(self, t):
            self.text, self.values, self.airlines, self.airports = t, {}, [], []
    scenes = [{"has_clip": False}, {"has_clip": True}, {"has_clip": False}, {"has_clip": False}]
    rows = [{"mode": "news"}, {"mode": "news"}, {"mode": "map"}, {"mode": "people", "article": {"headline": "x"}}]
    modes = P._clipless_to_story(scenes, [C("a"), C("b"), C("c"), C("d")], rows, ["news", "news", "flight", "people"], [True] * 4)
    assert modes == ["story", "news", "flight", "people"]
    assert P._clipless_to_story([{}], [C("a")], [{}], ["news"], [False]) == ["news"]        # Generate: unchanged


def test_wall_camera_waits_for_the_next_item():
    from wall import planner as WP
    keys = [{"t": 1.6, "x": 1014.0, "y": 0.0, "z": 0.74}, {"t": 3.24, "x": 1968.0, "y": 30.0, "z": 1.1, "_ready": 2.84}]
    out = WP._wait_for_items(keys)
    assert len(out) == 3 and out[1]["x"] == 1014.0 and abs(out[1]["t"] - 2.59) < 1e-6
    assert all("_ready" not in k for k in out)


def test_wall_window_past_the_clip_end_slides_back(tmp_path):
    from wall import frames as FR
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x36:d=2", "-pix_fmt", "yuv420p", str(clip)], check=True)
    f = FR.window(str(clip), 2.0, 8.0, (64, 36), str(tmp_path / "w"))
    assert f.hold_end and f.b <= 2.0 and len(f) > 0
    im = f.at(5.0)
    assert im is not None and im.getpixel((10, 10))[0] > 200


def test_war_world_places_and_spoken_dates():
    from cinematic_explainer.war import catalog as C, direction as D
    names = {m.entry["name"] for m in C.find_place("The flag of Argentina was flying over Port Stanley, and they retook South Georgia.")}
    assert {"Argentina", "Stanley"} <= names and "Georgia" not in names
    assert not C.find_place("HMS Sheffield was hit. Most of the crew survived in March.")
    assert [m.entry["name"] for m in C.find_place("Drones hit Kupiansk.")] == ["Kupiansk"]
    assert D._date_of("On the twenty fifth of April, British forces retook the island") == "25 April"
    assert D._after_date("On the twenty fifth of April, British forces retook the island", "25 April") == "British forces retook the island"
    assert D._date_of("In February 2022, Russian columns advanced") == "February 2022"


def test_baby_backdrop_shapes_stay_low():
    src = Path(__file__).with_name("cartoon2d").joinpath("baby_sets.py").read_text()
    assert "rnd.uniform(0.55, 0.6) * H" in src
