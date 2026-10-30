"""Paper-cutout puppet pipeline side: CSV columns, the shot plan, cache keys and the never-stop fallback, against a fake puppet module. Run: python3 test_health_cinema_puppet_plan.py"""
import os, sys, tempfile, threading, types
from pathlib import Path

from health_cinema import planner, puppet_plan as PP, scenes_csv

ACTIONS = ["walk", "run", "stand_idle", "look_around", "point", "turn", "pick_up", "put_down", "wave", "stop"]


def fake_module(fail=False, calls=None):
    m = types.ModuleType("health_cinema.puppet")
    m.VERSION = "t1"
    m.TRANSITIONS = ("tear_seam", "door_walk", "page_flip", "behind_object")
    m.list_characters = lambda: ["fox", "owl", "bear"]
    m.list_actions = lambda: list(ACTIONS)
    def render_shot(still, character, action, out, duration=5.0, fps=30, direction="right", size=(1920, 1080), params=None):
        calls is not None and calls.append(("shot", still, character, action, round(duration, 3)))
        if fail: raise RuntimeError("boom")
        Path(out).write_bytes(b"shot")
        return out
    def render_transition(a, b, character, transition, out, duration, fps=30, size=(1920, 1080), direction="right"):
        calls is not None and calls.append(("trans", transition))
        if fail: raise RuntimeError("boom")
        Path(out).write_bytes(b"trans")
        return out
    m.render_shot, m.render_transition = render_shot, render_transition
    return m


CSV_PLAIN = "text,chapter\nA woman walks to the door.,\nThe heart pumps blood.,\n"
CSV_PUP = ("text,character_action,character\nA woman walks to the door.,walk_in_from_left,fox\nThe heart pumps blood.,none,\n"
           "He looks around the room.,stand_and_look,\nHe picks up the box.,pick_up_box,dragon\nAnd then he rests.,dance wildly,\nPlain row.,,\n")


def test_csv():
    old = scenes_csv.parse_csv_text(CSV_PLAIN)
    assert all("character_action" not in r and "character" not in r for r in old)
    assert not scenes_csv.has_direction(scenes_csv.parse_csv_text(CSV_PUP))      # puppet cells alone never switch the CSV into "directed" mode
    sys.modules["health_cinema.puppet"] = fake_module()
    notes = []
    rows = scenes_csv.parse_csv_text(CSV_PUP, notes)
    assert (rows[0]["character_action"], rows[0]["character_direction"], rows[0]["character"]) == ("walk", "right", "fox")
    assert rows[1]["character_action"] == "none"
    assert rows[2]["character_action"] == "look_around" and "character_direction" not in rows[2]
    assert rows[3]["character_action"] == "pick_up" and "character" not in rows[3]
    assert "character_action" not in rows[4] and "character_action" not in rows[5]
    assert any("dragon" in n for n in notes) and any("dance wildly" in n for n in notes), notes
    assert PP.parse_action("walk_out_to_left")[:2] == ("walk", "left")
    assert PP.parse_action("")[0] is None and PP.parse_action("NONE")[0] == "none"
    assert PP.parse_character("Auto") == (None, "")


def scenes(n=20):
    texts = ["A woman walks up the stairs.", "The pancreas makes insulin.", "He picks up the heavy box.", "Millions of people worldwide have this.",
             "She stops and looks around the kitchen.", "Forty percent of adults are affected.", "The patient waves to the nurse."]
    out = []
    for i in range(n):
        out.append({"scene_no": i + 1, "start": i * 4.0, "end": i * 4.0 + 4.0, "text": texts[i % len(texts)] + f" {i}", "kind": "footage" if i % 3 else "text_card"})
    return out


def test_plan():
    sys.modules["health_cinema.puppet"] = fake_module()
    sc = scenes(30)
    on = {"enabled": True, "intensity": "medium", "seed": 7}
    assert PP.plan_puppet(sc, {"enabled": False}, has_still=lambda s: True) == {}
    p1 = PP.plan_puppet(sc, on, has_still=lambda s: True)
    p2 = PP.plan_puppet(sc, dict(on), has_still=lambda s: True)
    assert p1 == p2 and p1, "deterministic for a seed"
    assert PP.plan_puppet(sc, dict(on, seed=8), has_still=lambda s: True) != p1
    assert 0.2 <= len(p1) / len(sc) <= 0.4, len(p1)
    for no, e in p1.items():
        text = sc[no - 1]["text"]
        assert "worldwide" not in text and "percent" not in text and "insulin" not in text, text      # crowds, figures and diagrams stay plain
        assert e["action"] in ACTIONS and e["character"] in ("fox", "owl", "bear") and e["direction"] in ("left", "right")
    order = sorted(p1)
    for a, b in zip(order, order[1:]):
        assert p1[a]["action"] != p1[b]["action"], (a, b)
        if b == a + 1:
            assert p1[b]["transition"] in ("tear_seam", "door_walk", "page_flip", "behind_object") and p1[b]["transition_from"] == a
            assert p1[b]["character"] == p1[a]["character"]
    low = PP.plan_puppet(sc, dict(on, intensity="low"), has_still=lambda s: True)
    high = PP.plan_puppet(sc, dict(on, intensity="high"), has_still=lambda s: True)
    assert len(low) < len(p1) <= len(high)
    assert PP.plan_puppet(sc, on, has_still=lambda s: False) == {}      # no stills, nothing planned
    assert all(e["character"] == "owl" for e in PP.plan_puppet(sc, dict(on, character="owl"), has_still=lambda s: True).values())


def test_plan_csv_wins():
    sys.modules["health_cinema.puppet"] = fake_module()
    sc = scenes(6)
    rows = [{"text": "x", "start": 0.0, "end": 4.0, "character_action": "wave", "character_direction": "left", "character": "bear"},
            {"text": "y", "start": 4.0, "end": 8.0, "character_action": "none"}]
    p = PP.plan_puppet(sc, {"enabled": True, "intensity": "high", "seed": 1}, rows, has_still=lambda s: True)
    assert p[1]["action"] == "wave" and p[1]["direction"] == "left" and p[1]["character"] == "bear" and p[1]["source"] == "csv"
    assert 2 not in p


def test_cache_key():
    k = lambda **kw: PP.cache_key("shot", ["abc"], kw.get("c", "fox"), kw.get("a", "walk"), "right", kw.get("p", {"motion": 1.0, "intensity": "medium"}), kw.get("n", 120), 24, (1920, 1080), kw.get("v", "t1"))
    assert k() == k() == k(p={"intensity": "medium", "motion": 1.0})
    assert len({k(), k(c="owl"), k(a="run"), k(p={"motion": 1.4}), k(n=121), k(v="t2")}) == 6
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "a.png"; f.write_bytes(b"1"); h1 = PP.file_hash(str(f)); f.write_bytes(b"2")
        assert h1 != PP.file_hash(str(f))


def runner_case(fail=False, cancel=None):
    d = Path(tempfile.mkdtemp())
    stills = []
    for i in range(2):
        p = d / f"s{i}.png"; p.write_bytes(b"png%d" % i); stills.append(str(p))
    sc = [{"scene_no": i + 1, "start": i * 4.0, "end": i * 4.0 + 4.0, "text": "She walks.", "kind": "footage", "visual": {"still": stills[i]}} for i in range(2)]
    calls = []
    def conform(src, dst, frames, captions, skip):
        Path(dst).write_bytes(Path(src).read_bytes() + b"|%d|%d" % (frames, skip))
    r = PP.Runner(d / "cache", 1920, 1080, 24, cancel, lambda m: calls.append(("log", m)), module=fake_module(fail, calls), conform=conform)
    return sc, r, calls


def test_runner_and_fallback():
    sc, r, calls = runner_case()
    e1 = {"character": "fox", "action": "walk", "direction": "right", "params": {"motion": 1.0}}
    e2 = dict(e1, action="run", transition="page_flip", transition_s=1.0, transition_from=1)
    a = r.render(sc[0], e1, None, [], 96)
    b = r.render(sc[1], e2, sc[0], [], 96)
    assert a and not a["pre"] and Path(a["path"]).is_file()
    assert b and len(b["pre"]) == 1 and b["puppet"]["transition"] == "page_flip"
    assert Path(b["path"]).read_bytes().endswith(b"|72|24")      # the shot borrows the transition's frames: scene length stays exact
    n_calls = len([c for c in calls if c[0] != "log"])
    a2 = r.render(sc[0], e1, None, [], 96)      # same inputs: cached, the engine is not called again
    assert a2["cache_hit"] and len([c for c in calls if c[0] != "log"]) == n_calls
    sc[1]["visual"]["still"] = sc[0]["visual"]["still"]      # edit scene 2 only: scene 1 stays cached
    r.render(sc[0], e1, None, [], 96)
    assert len([c for c in calls if c[0] != "log"]) == n_calls
    # failure -> None (engine falls back to the normal render), logged, never raises
    sc, r, calls = runner_case(fail=True)
    assert r.render(sc[0], e1, None, [], 96) is None
    assert any(c[0] == "log" and "normal render used" in c[1] for c in calls) and r.stats["fallbacks"] == 1
    # no still -> None
    sc, r, calls = runner_case()
    sc[0]["visual"] = {}
    assert r.render(sc[0], e1, None, [], 96) is None
    # missing engine -> disabled for the run, None
    sc, r, calls = runner_case()
    r._module_arg = None
    r._mod = None
    sys.modules["health_cinema.puppet"] = None
    try:
        assert r.render(sc[0], e1, None, [], 96) is None and r.disabled
    finally:
        sys.modules.pop("health_cinema.puppet", None)


def test_cancel():
    ev = threading.Event(); ev.set()
    sc, r, calls = runner_case(cancel=ev)
    try:
        r.render(sc[0], {"character": "fox", "action": "walk", "direction": "right"}, None, [], 96)
    except PP.PuppetCancelled:
        return
    raise AssertionError("cancel must propagate")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)


from unittest_adopt import adopt
adopt(globals())
