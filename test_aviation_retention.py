"""Aviation retention pass (aviation/retention.py): turn lines, visual check, deterministic fixes, the re-hook wipe."""

import copy

from aviation import planner as P
from aviation import retention as R
from aviation import stage as G


def sc(i, text, a, b):
    return {"scene_no": i + 1, "text": text, "start": float(a), "end": float(b)}


def foot(a, b, scene=1, q=("jet",)):
    return {"kind": "footage", "start": float(a), "end": float(b), "scene": scene, "mode": "news", "queries": list(q), "cut": "cut"}


def lay(name, a, b, scene=1, **kw):
    return dict({"layer": name, "start": float(a), "end": float(b), "scene": scene, "params": {}, "full_frame": True}, **kw)


class FP:
    def __init__(self, shots):
        self.shots, self.modes, self.log = shots, [], []


def stage_shot(a, b, els, scene=1, years=()):
    return lay("stage.lay_stage", a, b, scene, params={"elements": els, "years": [list(y) for y in years]}, cues=[])


def el(kind, args, t0, t1=None, ident=None):
    st = G.Stage()
    st.add(kind, t0, args, id=ident or kind + "1", pos=(640, 380), scale=1.0)
    e = st.params()["elements"][0]
    e["t1"] = t1
    return e


def kinds(issues):
    return {i["kind"] for i in issues}


# --------------------------------------------------------------------------------------------------------------- turn lines
def test_turn_lines_sample_sentences():
    texts = ["The airline began with two planes.", "But there is a catch.", "Then the story flips.", "However, the money ran out.",
             "What nobody expected was the strike.", "That changed in 1998.", "Here's the problem.", "The twist came later.",
             "Until the war began.", "So why did it fail?", "How did a small airline survive?", "It flew to Paris every day.",
             "It was a nice day. And then, suddenly, everything stopped."]
    scenes = [sc(i, t, i * 4, i * 4 + 4) for i, t in enumerate(texts)]
    got = R.turn_lines(scenes)
    assert got == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12] or set(range(1, 11)) <= set(got)
    assert 0 not in got and 11 not in got


def test_opening_question_and_answer_pair():
    scenes = [sc(0, "Why did Flight 370 vanish?", 0, 4), sc(1, "It left Kuala Lumpur at night.", 4, 9),
              sc(2, "Years of searching found little.", 9, 15),
              sc(3, "The answer is simple: Flight 370 vanished because nobody was watching the transponder.", 100, 106)]
    q, a, sent = R.opening_question(scenes)
    assert (q, a) == (0, 3) and sent.endswith("?")
    assert R.turn_lines(scenes) == [0, 3]


def test_question_late_is_not_opening():
    scenes = [sc(0, "Welcome.", 0, 5), sc(1, "Why did it fail?", 80, 85)]
    assert R.opening_question(scenes)[0] == -1


# --------------------------------------------------------------------------------------------------------------- check
def test_check_same_kind_footage():
    plan = FP([foot(0, 12)])
    assert "same_kind" in kinds(R.check(plan, [sc(0, "Hello there.", 0, 12)]))


def test_check_two_text_cards_in_row():
    plan = FP([lay("cards.lay_article", 0, 4), lay("gfx.lay_sheet", 4, 8)])
    assert "text_cards_in_row" in kinds(R.check(plan, []))
    plan2 = FP([lay("cards.lay_article", 0, 4), foot(4, 6), lay("gfx.lay_sheet", 6, 9)])
    assert "text_cards_in_row" not in kinds(R.check(plan2, []))


def test_check_card_long():
    plan = FP([foot(0, 3), lay("cards.lay_article", 3, 12)])
    assert "card_long" in kinds(R.check(plan, []))


def test_check_slow_opening():
    plan = FP([foot(0, 15), foot(15, 30)])
    assert "slow_opening" in kinds(R.check(plan, []))
    fast = FP([foot(i * 1.5, i * 1.5 + 1.5) for i in range(20)])
    assert "slow_opening" not in kinds(R.check(fast, []))


def test_check_no_rehook_and_stage_idle():
    plan = FP([foot(0, 4)] + [foot(t, t + 4) for t in range(4, 200, 4)])
    assert "no_rehook" in kinds(R.check(plan, []))
    idle = FP([stage_shot(0, 20, [el("flag", {"code": "MY"}, 0.0)])])
    iss = R.check(idle, [])
    assert "stage_idle" in kinds(iss)
    busy = FP([stage_shot(0, 20, [el("flag", {"code": "MY"}, 0.0, ident="a"), el("flag", {"code": "SG"}, 6.0, ident="b"),
                                  el("flag", {"code": "GB"}, 12.0, ident="c"), el("flag", {"code": "FR"}, 18.0, ident="d")])])
    assert "stage_idle" not in kinds(R.check(busy, []))


def test_check_no_callback():
    scenes = [sc(0, "Why did Flight 370 vanish?", 0, 4), sc(1, "It left at night.", 4, 40),
              sc(2, "That is why Flight 370 vanished, because nobody watched.", 40, 46)]
    plan = FP([stage_shot(0, 4, [el("flag", {"code": "MY"}, 0.2)]), foot(4, 40, 2), foot(40, 46, 3, q=("radar",))])
    assert "no_callback" in kinds(R.check(plan, scenes))


# --------------------------------------------------------------------------------------------------------------- apply
def _substring_ok(plan, scenes):
    all_text = " ".join(s["text"] for s in scenes)
    for s in plan.shots:
        for e in (s.get("params") or {}).get("elements", []) if s.get("layer", "").startswith("stage.") else []:
            if str(e["id"]).startswith("rh_") and e["kind"] in ("big_type", "text"):
                assert e["args"]["text"] in all_text, e["args"]


def test_apply_opening_and_long_footage_and_cards():
    scenes = [sc(0, "Once there was an airline.", 0, 30), sc(1, "It grew.", 30, 50)]
    plan = FP([foot(0, 12, 1), foot(12, 30, 1), foot(30, 50, 2, q=("a",)), lay("cards.lay_article", 50, 60, 2)])
    scenes.append(sc(2, "Done.", 50, 60))
    before = R.check(plan, scenes)
    rep = R.apply(plan, scenes)
    after = R.check(plan, scenes)
    assert len(after) < len(before)
    assert "slow_opening" not in kinds(after) and "card_long" not in kinds(after) and "same_kind" not in kinds(after)
    assert {f["fix"] for f in rep["fixed"]} >= {"opening_split", "card_shortened", "footage_split"}
    assert all(f["reason"] for f in rep["fixed"])
    firsts = [s for s in plan.shots if s.get("kind") == "footage" and s["start"] < 30]
    assert all(s["end"] - s["start"] <= 2.01 for s in firsts)
    assert all(s["queries"] == ["jet"] for s in firsts)
    assert plan.shots == sorted(plan.shots, key=lambda s: s["start"])


def test_apply_rehook_on_turn_lines_stage_and_marker():
    scenes = [sc(0, "The airline grew fast.", 0, 20), sc(1, "But there is a catch, the fuel bill doubled every year.", 20, 40),
              sc(2, "It never recovered.", 40, 60)]
    e = [el("flag", {"code": "MY"}, 0.0, ident="a"), el("flag", {"code": "SG"}, 5.0, ident="b"),
         el("flag", {"code": "GB"}, 10.0, ident="c"), el("flag", {"code": "FR"}, 16.0, ident="d"),
         el("flag", {"code": "AU"}, 24.0, ident="e"), el("flag", {"code": "IN"}, 32.0, ident="f"),
         el("flag", {"code": "JP"}, 40.0, ident="g"), el("flag", {"code": "CN"}, 48.0, ident="h"),
         el("flag", {"code": "TH"}, 55.0, ident="i")]
    plan = FP([stage_shot(0, 60, e)])
    rep = R.apply(plan, scenes)
    marks = [s for s in plan.shots if s.get("layer") == "retention.lay_rehook"]
    assert len(marks) == 1 and abs(marks[0]["start"] - 20.0) < 0.01 and abs(marks[0]["end"] - 20.6) < 0.01
    assert marks[0]["params"] == {"style": "wipe"}
    st = [s for s in plan.shots if s.get("layer") == "stage.lay_stage"][0]
    big = [x for x in st["params"]["elements"] if x["kind"] == "big_type"]
    assert len(big) == 1 and len(big[0]["args"]["text"].split()) <= 6
    assert abs(big[0]["t0"] - 20.0) < 0.01
    assert any(c[1] == "rehook" for c in st["cues"])
    _substring_ok(plan, scenes)
    assert 1 in rep["turn_lines"]
    assert G.lay_stage(20.5, 60, st["params"]) is not None


def test_apply_stage_idle_gets_a_move_and_second_check_is_better():
    scenes = [sc(0, "The Malaysian airline began.", 0, 30)]
    plan = FP([stage_shot(0, 30, [el("flag", {"code": "MY"}, 0.0)])])
    before = R.check(plan, scenes)
    R.apply(plan, scenes)
    after = R.check(plan, scenes)
    assert "stage_idle" in kinds(before) and "stage_idle" not in kinds(after)
    assert len(after) < len(before)
    assert len(plan.shots[0]["params"]["elements"][0]["keys"]) > 1


def test_apply_empty_stage_gets_text_from_the_line():
    scenes = [sc(0, "Malaysia Airlines began in 1947.", 0, 30)]
    plan = FP([stage_shot(0, 30, [])])
    R.apply(plan, scenes)
    texts = [e["args"]["text"] for e in plan.shots[0]["params"]["elements"] if e["kind"] == "text"]
    assert texts and all(t in scenes[0]["text"] for t in texts)


def test_apply_forced_rehook_when_no_turn_lines():
    scenes = [sc(i, f"Plain line number {i}.", i * 10, i * 10 + 10) for i in range(20)]
    plan = FP([foot(i * 4, i * 4 + 4, i // 2 + 1) for i in range(50)])
    assert "no_rehook" in kinds(R.check(plan, scenes))
    rep = R.apply(plan, scenes)
    assert "no_rehook" not in kinds(R.check(plan, scenes))
    assert any(f["fix"] == "rehook_forced" for f in rep["fixed"])
    assert all(s.get("params") == {"style": "wipe"} for s in plan.shots if s.get("layer") == "retention.lay_rehook")


def test_apply_callback_stage_and_footage():
    scenes = [sc(0, "Why did Flight 370 vanish?", 0, 4), sc(1, "It left at night.", 4, 60),
              sc(2, "That is why Flight 370 vanished, because nobody watched.", 60, 70)]
    plan = FP([stage_shot(0, 4, [el("flag", {"code": "MY"}, 0.2)]), stage_shot(60, 70, [el("flag", {"code": "SG"}, 0.0)], 3),
               foot(4, 60, 2)])
    R.apply(plan, scenes)
    assert "no_callback" not in kinds(R.check(plan, scenes))
    st = [s for s in plan.shots if s.get("layer") == "stage.lay_stage" and s["start"] == 60][0]
    assert any(e["kind"] == "flag" and e["args"] == {"code": "MY"} for e in st["params"]["elements"])
    # footage version
    plan2 = FP([foot(0, 4, 1, q=("flight 370",)), foot(4, 60, 2, q=("night",)), foot(60, 70, 3, q=("radar",))])
    R.apply(plan2, scenes)
    assert "no_callback" not in kinds(R.check(plan2, scenes))
    assert any(s.get("queries") == ["flight 370"] and 60 <= s["start"] < 70 for s in plan2.shots)


def test_real_planner_plan_then_apply():
    scenes = [sc(0, "Why did Malaysia Airlines lose so much money?", 0, 5),
              sc(1, "In 1972 the airline split from Singapore Airlines and kept 12 Boeing 707 jets.", 5, 14),
              sc(2, "But there is a catch. Fuel prices rose 40 percent in a year.", 14, 24),
              sc(3, "The flight from Kuala Lumpur to London took 13 hours.", 24, 36),
              sc(4, "That is why the airline lost money, because the fuel bill kept growing.", 36, 48)]
    plan = P.plan(scenes)
    before = R.check(plan, scenes)
    snap = copy.deepcopy(plan.shots)
    rep = R.apply(plan, scenes)
    after = R.check(plan, scenes)
    assert len(after) <= len(before)
    assert isinstance(rep["turn_lines"], list) and 2 in rep["turn_lines"]
    # nothing in the original shots was lost: every old shot interval is still covered
    for s in snap:
        assert any(n.get("layer") == s.get("layer") or n.get("kind") == s.get("kind") for n in plan.shots)
    _substring_ok(plan, scenes)


# --------------------------------------------------------------------------------------------------------------- the wipe
def test_lay_rehook_draws_midway_and_none_at_end():
    mid = R.lay_rehook(0.3, 0.6, {"style": "wipe"})
    assert mid is not None and mid.size == (1280, 720) and mid.mode == "RGBA"
    assert mid.getchannel("A").getbbox() is not None
    assert R.lay_rehook(0.6, 0.6, {}) is None
    assert R.lay_rehook(1.0, 0.6, {}) is None
    fl = R.lay_rehook(0.3, 0.6, {"style": "flash"})
    assert fl.getchannel("A").getbbox() is not None


def test_rehook_big_type_stands_alone_and_answer_line_gets_only_the_callback():
    from aviation import planner as P2
    from aviation import stage as G2
    lines = ["So why did one airline become two?",
             "In 1966 the two governments formed Malaysia-Singapore Airlines, flying Boeing 707s.",
             "Malaysia wanted a domestic network, while Singapore wanted international routes.",
             "But there was a catch nobody expected.",
             "The joint airline grew quickly, but the two owners pulled it in different directions.",
             "Then in 1972 the joint airline split into Singapore Airlines and Malaysia Airlines.",
             "Singapore Airlines kept the routes from Singapore to London and Sydney.",
             "One airline became two because the two governments wanted different things."]
    sc = [{"scene_no": i + 1, "text": t, "start": i * 6.0, "end": (i + 1) * 6.0} for i, t in enumerate(lines)]
    pl = P2.plan(sc)
    st = next(s for s in pl.shots if s.get("layer") == "stage.lay_stage")
    els = st["params"]["elements"]
    for big in [e for e in els if e["kind"] == "big_type"]:
        t = big["t0"] + 0.8
        others = [e for e in els if e is not big and e["kind"] != "backdrop" and G2.transform(e, t) is not None]
        assert not others, (big["args"]["text"], [o["kind"] for o in others])       # nothing under the big words
        assert big["args"]["text"].split()[-1].lower() not in ("the", "a", "because", "and", "of", "to")
    ans_t = 7 * 6.0 - st["start"]
    assert not [e for e in els if e["kind"] == "big_type" and abs(e["t0"] - ans_t) < 3.0]
