"""Plain-assert tests for puppet_story and the story mode of puppet_stills (fake puppet module, no rendering)."""
import sys
import types
import tempfile
from pathlib import Path

import puppet_story as ps


def S(no, a, b, text, prompt):
    return {"scene_no": no, "start": a, "end": b, "script_segment": text, "prompt": prompt}


def W(text, a, b):
    toks = text.split()
    step = (b - a) / len(toks)
    return [[t, a + i * step, a + (i + 1) * step] for i, t in enumerate(toks)]


SC = [S(1, 0, 6, "यह एक बड़ा गोदाम है।", "wide aerial view of a skyline"),
      S(2, 6, 12, "वह गोदाम से बाहर निकलता है और सड़क पर चलता है।", "warehouse door opening onto a street, paper collage"),
      S(3, 12, 18, "फिर वह घर पहुँचता है और डिब्बा उठाता है।", "front porch of a house with a doorstep"),
      S(4, 18, 21, "लाखों लोग।", "endless crowd of people"),
      S(5, 21, 24, "अब देखिए।", "a room")]
WORDS = sum([W(s["script_segment"], s["start"], s["end"]) for s in SC], [])


def test_norm_and_triggers():
    assert ps.norm("पहुँचता,") == ps.norm("पहुंचता") == "पहुचता"
    kinds = {t["kind"] for t in ps.triggers([("निकलता", 0, 1), ("उठाता", 1, 2)], 0)}
    assert {"move", "pick"} <= kinds
    k = [t["kind"] for t in ps.triggers([("हो", 0, 1), ("गई", 1, 2)], 0)]
    assert "move" not in k                       # auxiliary "ho gayi" is not a movement
    k = [t["kind"] for t in ps.triggers([("चार्जर", 0, 1), ("पहुँचा", 1, 2), ("सकती", 2, 3)], 0)]
    assert "put" in k and "move" not in k       # delivered, not "arrived"


def test_journey_continuity_and_skips():
    plan = ps.plan_story(SC, WORDS, {"intensity": "high", "seed": 3, "lane_fn": False}, characters=["worker", "woman"])
    assert plan["scenes"], plan
    assert plan["protagonist"]["character"] == "worker"
    assert 1 not in plan["scenes"] and 4 not in plan["scenes"]          # aerial/crowd skipped
    assert (2, 3) in plan["links"]
    a, b = plan["scenes"][2], plan["scenes"][3]
    assert a["exit"] == "right" and b["enter"] == "left"
    assert a["beats"][-1]["x1"] > 1.0 and b["beats"][0]["x0"] < 0.0       # leaves one side, arrives from the opposite side
    assert a["char_h"] == b["char_h"] and a["y"] == b["y"] and a["direction"] == b["direction"]
    assert b["beats"][0]["t0"] == 0.0
    for e in plan["scenes"].values():                                    # beats are ordered, inside the scene, and explained
        prev = 0.0
        for bt in e["beats"]:
            assert bt["t0"] >= prev - 1e-6 and bt["t1"] > bt["t0"]
            prev = bt["t1"]
        assert len(e["why"]) == len(e["beats"])
    assert any(bt["action"] == "pick_up" for bt in b["beats"])           # "डिब्बा उठाता" drives a pick-up
    txt = ps.explain(plan, SC)
    assert "scene 2" in txt and "<-" in txt


def test_deterministic_and_safe():
    p1 = ps.plan_story(SC, WORDS, {"seed": 5, "lane_fn": False}, characters=["worker"])
    p2 = ps.plan_story(SC, WORDS, {"seed": 5, "lane_fn": False}, characters=["worker"])
    assert p1 == p2
    assert ps.plan_story(None, None, None)["scenes"] == {}
    assert ps.plan_story([{"bad": 1}], "garbage", {"intensity": 7})["scenes"] == {}
    assert ps.plan_story(SC, None, {"lane_fn": False}, characters=["worker"])["scenes"] is not None     # no words: spread evenly


def test_budget_and_csv():
    many = [S(i, i * 6, i * 6 + 6, "वह चलता है और घर पहुँचता है।", "a street with a door") for i in range(1, 41)]
    lo = ps.plan_story(many, None, {"intensity": "low", "seed": 1, "lane_fn": False}, characters=["worker"])
    hi = ps.plan_story(many, None, {"intensity": "high", "seed": 1, "lane_fn": False}, characters=["worker"])
    minutes = 40 * 6 / 60.0
    assert len(lo["scenes"]) <= round(minutes * 0.6) + 2 and len(hi["scenes"]) > len(lo["scenes"])
    rows = [{"scene_number": "1", "character_action": "none"}, {"scene_number": "2", "character": "woman", "character_action": "walk"}]
    p = ps.plan_story(many, None, {"intensity": "high", "seed": 1, "rows": rows, "lane_fn": False}, characters=["worker", "woman"])
    assert 1 not in p["scenes"] and p["scenes"][2]["character"] == "woman"


def test_prepare_story_with_fake_engine():
    import puppet_stills
    import health_cinema
    calls, motions = [], []
    fake = types.ModuleType("health_cinema.puppet")
    fake.VERSION = "t"
    fake.list_characters = lambda: ["worker", "woman"]
    fake.list_actions = lambda: ["walk", "stand_idle"]

    def render_shot(still, ch, action, out, duration, fps, direction, size, params=None):
        calls.append((ch, action, duration, params))
        Path(out).write_bytes(b"x")
    fake.render_shot = render_shot
    saved = sys.modules.get("health_cinema.puppet"), getattr(health_cinema, "puppet", None)
    sys.modules["health_cinema.puppet"] = fake
    health_cinema.puppet = fake
    import video_generator as vg
    with tempfile.TemporaryDirectory() as d:
        imgs = Path(d) / "img"
        imgs.mkdir()
        for s in SC:
            (imgs / f"scene_{s['scene_no']}.png").write_bytes(b"png%d" % s["scene_no"])
        aligned = [{"scene_number": str(s["scene_no"]), "script_segment": s["script_segment"], "prompt": s["prompt"]} for s in SC]
        orig = (vg.build_scene_media_index, vg.find_image_for_scene, vg.is_video_file)
        vg.build_scene_media_index = lambda p: {}
        vg.find_image_for_scene = lambda p, n, ext_cache=None: imgs / f"scene_{str(n).strip()}.png"
        vg.is_video_file = lambda p: False
        try:
            out = puppet_stills.prepare(aligned, [s["end"] - s["start"] for s in SC], imgs, d, {"puppet_stills": True, "puppet_intensity": "high", "puppet_lane_fn": lambda still, **kw: {"x0": 0.0, "x1": 1.0, "y": 0.86, "h_hint": 0.4, "avoid": [], "conf": 0.9}}, lambda m: None, words=WORDS,
                                        motion_renderer=lambda still, o, dur, fps, size, seed, params: (motions.append((still, dur)), Path(o).write_bytes(b"m")))
        finally:
            vg.build_scene_media_index, vg.find_image_for_scene, vg.is_video_file = orig
            if saved[0] is None:
                sys.modules.pop("health_cinema.puppet", None)
            else:
                sys.modules["health_cinema.puppet"] = saved[0]
            if saved[1] is not None:
                health_cinema.puppet = saved[1]
    assert set(out) == {"1", "2", "3", "4", "5"}, out            # characters on the journey, motion clips on the rest: nothing static
    assert calls and all(abs(c[2] - 6.5) < 1e-6 for c in calls)        # scene length + 0.5 s margin
    assert "beats" in calls[0][3] and calls[0][3].get("lane", {}).get("x1") == 1.0 and motions and all(m[1] in (6.5, 3.5, 6.5) or m[1] > 3 for m in motions)
    assert len(calls) + len(motions) == 5


def LN(x0=0.0, x1=1.0, y=0.86, avoid=None, h=0.4):
    return {"x0": x0, "x1": x1, "y": y, "h_hint": h, "avoid": avoid or [], "conf": 0.9, "source": "fake"}


def test_phonetic_alignment_finds_real_speech():
    assert ps.phon_key("अमेजन") == ps.phon_key("आमीजन") == ps.phon_key("Amazon") or ps.phon_key("Amazon")[1:] == ps.phon_key("अमेजन")[1:]
    assert ps.phon_key("पहुँचता") == ps.phon_key("पहुंचता")
    # the app cut scene 2 and 3 one scene too late: scene 2's words are really spoken in 6-12, scene 3's in 12-18
    sc = [S(1, 0, 6, "यह एक बड़ा गोदाम है", "x"), S(2, 12, 18, "वह गोदाम से बाहर निकलता है और सड़क पर चलता है", "x"),
          S(3, 18, 24, "फिर वह घर पहुँचता है और डिब्बा उठाता है", "x")]
    words = [["यह", 0, .5], ["एक", .5, 1], ["बडा", 1, 2], ["गोदाम", 2, 3], ["है", 3, 4], ["वो", 6, 6.5], ["गुदाम", 6.5, 7.5], ["से", 7.5, 8], ["बाहर", 8, 9], ["निकलता", 9, 10],
             ["है", 10, 10.5], ["और", 10.5, 11], ["सडक", 11, 11.5], ["पर", 11.5, 12], ["चलता", 12, 12.5], ["है", 12.5, 13]]
    tm = ps.realign(ps._prep(sc), ps.normalize_words(words))
    assert tm[1]["timing_ok"] and tm[2]["speech_start"] < 7 and tm[2]["speech_end"] <= 13.1
    assert not tm[2]["timing_ok"] and "clip" in tm[2]["reason"]       # its speech is before its clip: skipped
    assert not tm[3]["timing_ok"]                                     # nothing of scene 3 was said at all
    assert "MISALIGNED" in ps.timing_report(sc, words)


def test_words_outside_the_clip_are_not_acted_on():
    sc = [S(1, 0, 8, "वह गोदाम से बाहर निकलता है और सड़क पर चलता है और घर पहुँचता है", "street with a door")]
    words = [["वह", -1.5, -1], ["गोदाम", -1, -.5], ["से", -.5, -.2], ["बाहर", .1, .6], ["निकलता", .6, 1.2], ["है", 1.2, 1.5], ["और", 1.5, 1.8], ["सडक", 2, 2.5], ["पर", 2.5, 3],
             ["चलता", 3, 3.5], ["है", 3.5, 4], ["और", 4, 4.4], ["घर", 4.4, 5], ["पहुचता", 5, 6], ["है", 6, 6.5]]
    p = ps.plan_story(sc, words, {"intensity": "high", "seed": 1, "lane_fn": False}, characters=["worker"])
    e = p["scenes"].get(1)
    assert e and all(b["t0"] >= 0 for b in e["beats"]) and all(b["t1"] <= 8.0 + 1e-6 for b in e["beats"])


def test_lanes_gate_and_clamp():
    SCS = [dict(s, still="/x/%03d.png" % s["scene_no"]) for s in SC]
    calls = []

    def lane_fn(still, scene_no=None, overrides=None, project_dir=None):
        calls.append(scene_no)
        return {2: LN(0.0, 1.0, 0.86, [[0.4, 0.6]]), 3: LN(0.0, 0.95, 0.88, h=0.3)}.get(scene_no)
    plan = ps.plan_story(SCS, WORDS, {"intensity": "high", "seed": 3, "lane_fn": lane_fn}, characters=["worker"])
    assert 4 not in plan["scenes"] and 1 not in plan["scenes"] and 5 not in plan["scenes"]       # no lane -> never a character
    assert set(plan["scenes"]) == {2, 3} and (2, 3) in plan["links"]
    a, b = plan["scenes"][2], plan["scenes"][3]
    assert a["y"] == b["y"] == 0.87 and a["char_h"] == b["char_h"] == 0.3         # one floor line and height for the whole walk
    assert a["lane"]["y"] == b["lane"]["y"] and "lane" in ps.explain(plan, SCS)
    for e in plan["scenes"].values():
        for bt in e["beats"]:
            if bt["action"] in ("stand_idle", "look_around", "pick_up"):
                assert not (0.36 <= bt["x0"] <= 0.64)                                     # never stands inside the avoid span
    # a floor that does not match across the cut: no journey, and nothing is placed on the lane-less picture
    p2 = ps.plan_story(SCS, WORDS, {"intensity": "high", "seed": 3, "lane_fn": lambda s, **k: {2: LN(y=0.6), 3: LN(y=0.9)}.get(k["scene_no"])}, characters=["worker"])
    assert not p2["links"]
    # an edge that is not open: the walker cannot leave the picture there
    p3 = ps.plan_story(SCS, WORDS, {"intensity": "high", "seed": 3, "lane_fn": lambda s, **k: {2: LN(0.0, 0.5), 3: LN(0.0, 1.0)}.get(k["scene_no"])}, characters=["worker"])
    assert not p3["links"]
    # a crashing lane module must not crash the plan
    def boom(*a, **k):
        raise RuntimeError("x")
    assert ps.plan_story(SCS, WORDS, {"lane_fn": boom}, characters=["worker"])["scenes"] == {}


def test_stand_position_avoids_zones():
    lu = ps.lane_u(LN(0.1, 0.9, avoid=[[0.2, 0.7]]), 1)
    for r in range(20):
        x = ps.pick_stand(lu, r, r)
        assert x is not None and not (0.2 - 0.04 <= x <= 0.7 + 0.04), x
    assert ps.pick_stand(ps.lane_u(LN(0.1, 0.9, avoid=[[0.12, 0.88]]), 1), 1, 1) is None


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
