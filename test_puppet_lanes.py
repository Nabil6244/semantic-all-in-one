"""Plain-assert tests for health_cinema/puppet/lanes.py (run: python3 test_puppet_lanes.py)."""
import json, os, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from health_cinema.puppet import lanes

def _save(arr, path):
    Image.fromarray(arr.astype(np.uint8)).save(path)

def _check_lane(l):
    assert l is not None
    for k in ("x0", "x1", "y", "h_hint", "conf"):
        assert 0.0 <= l[k] <= 1.0, (k, l)
    assert l["x1"] - l["x0"] >= lanes.MIN_SPAN
    last = -1
    for a, b in l["avoid"]:
        assert 0 <= a < b <= 1 and a > last - 1e-9 or a >= last
        last = b

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    # synthetic floorless pictures -> auto None
    sky = np.zeros((200, 360, 3)); sky[...] = (150, 180, 225); _save(sky, td / "010.png")
    blank = np.full((200, 360, 3), (235, 222, 190)); _save(blank, td / "011.png")
    rng = np.random.default_rng(1)
    noise = rng.integers(0, 255, (200, 360, 3)); _save(noise, td / "012.png")
    black = np.zeros((200, 360, 3)); _save(black, td / "013.png")
    for n in (10, 11, 12, 13):
        assert lanes.auto_lane(td / f"0{n}.png") is None, n
        assert lanes.lane_for(td / f"0{n}.png") is None
    assert lanes.lane_for(td / "missing.png") is None          # unreadable -> None, no raise

    # explicit override beats everything; null override = no lane
    proj = td / "proj"; (proj / "state").mkdir(parents=True)
    (proj / "state" / "puppet_lanes.json").write_text(json.dumps({
        "10": {"x0": 0.1, "x1": 0.6, "y": 0.8, "avoid": [[0.3, 0.2], ["x", 1], [0.5, 0.55]]},
        "011": None, "012": {"x0": "bad"}, "_c": "note", "013": {"x0": 0.9, "x1": 0.2, "y": 5, "h_hint": 9}}), encoding="utf-8")
    side = lanes.lane_for(td / "010.png", project_dir=proj)
    _check_lane(side); assert side["source"] == "sidecar" and side["avoid"] == [[0.2, 0.3], [0.5, 0.55]]
    assert abs(side["h_hint"] - lanes.default_h_hint(0.8)) < 1e-6
    ov = lanes.lane_for(td / "010.png", overrides={"010": {"x0": 0.2, "x1": 0.9, "y": 0.9}}, project_dir=proj)
    assert ov["source"] == "override" and ov["x0"] == 0.2
    assert lanes.lane_for(td / "010.png", scene_no=10, overrides={"10": None}, project_dir=proj) is None
    assert lanes.lane_for(td / "011.png", project_dir=proj) is None            # sidecar null
    assert lanes.lane_for(td / "012.png", project_dir=proj) is None            # bad entry ignored -> auto None
    c = lanes.lane_for(td / "013.png", project_dir=proj)                       # swapped x, clamped y
    assert c is not None and c["x0"] == 0.2 and c["x1"] == 0.9 and c["y"] == 1.0 and c["h_hint"] <= 0.8
    assert lanes.lane_for(td / "010.png", scene_no=10, overrides={"10": {"x0": .1}}) is None  # bad override ignored, auto none

    # bad sidecar files tolerated
    for txt in ("{not json", "[1,2]", "", "null"):
        (proj / "state" / "puppet_lanes.json").write_text(txt, encoding="utf-8")
        assert lanes.load_overrides(proj) == {}
    assert lanes.load_overrides(td / "nope") == {} and lanes.load_overrides(None) == {}

    # free_spans
    l = lanes.clean_lane({"x0": 0.1, "x1": 0.9, "y": 0.8, "avoid": [[0.3, 0.5]]})
    assert lanes.free_spans(l) == [[0.1, 0.3], [0.5, 0.9]]
    assert lanes.clean_lane({"x0": 0.5, "x1": 0.52, "y": 0.8}) is None
    assert lanes.clean_lane({"x0": 0.1, "x1": float("nan"), "y": 0.8}) is None

    # a synthetic street picture (grey calm ground at the bottom under a dark building, no blue) may or may not be accepted;
    # if it is, the lane must be valid and low in the frame
    st = np.zeros((200, 360, 3)); st[:120] = (60, 50, 45); st[120:180] = (150, 145, 140); st[180:] = (235, 222, 190)
    r = lanes.auto_lane((_save(st, td / "020.png"), td / "020.png")[1])
    if r is not None:
        _check_lane(r); assert r["y"] >= 0.7
print("test_puppet_lanes OK")


import unittest


class Ran(unittest.TestCase):
    def test_the_script_above_ran_to_the_end(self):      # its checks run (and assert) when the module is imported
        self.assertTrue(True)
