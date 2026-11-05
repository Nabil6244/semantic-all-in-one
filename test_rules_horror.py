"""Rules Horror Stage 2: CSV reader, planner (timing on the voice, cuts, carry-over), compile, sound cues. Synthetic data only; no render."""
import io
import unittest

from product_trailer.voiceover import align_lines
from rules_horror import assets
from rules_horror.check import check_screen, check_story
from rules_horror.compile import compile_spec, stage_media
from rules_horror.csv_io import parse_csv_text
from rules_horror.planner import MAX_BEAT_S, plan
from rules_horror.sound import plan_cues

CSV = """﻿#subject,deer,"tall deer, long legs"
order,section,line,set,shot,subject,pose,action,tag,value,prompt
2,hook,and see a deer standing in your yard,window,push_in,deer,stand_side,figure_look,YOU,,
1,hook,If you ever wake up at three,bedroom,wide,,,figure_sleep,,3:00 AM,

3,rule,Do not turn on the lights,card,,,,rule_card,,1,
4,scare,it was grinning at me,closeup,push_in,deer,close_up_face,glitch,,,"a white face"
5,turn,then it spoke,yard,PUSH,,,figure_walk+sight_line,,,
"""


def words_for(lines, wps=2.5, gap=0.3, t0=0.4):
    out, t = [], t0
    for ln in lines:
        for w in ln.split():
            out.append((w.lower().strip(".,"), t, t + 1 / wps - 0.05)); t += 1 / wps
        t += gap
    return out, t


def built():
    data = parse_csv_text(CSV)
    lines = [r["line"] for r in data["rows"]]
    words, end = words_for(lines)
    al = align_lines(lines, words, end)
    return data, al, words, end, plan(data, al, words, end)


class CsvTests(unittest.TestCase):
    def test_lenient_reader(self):
        d = parse_csv_text(CSV)
        self.assertEqual([r["order"] for r in d["rows"]], [1, 2, 3, 4, 5])          # sorted by order
        self.assertEqual(d["rows"][1]["shot"], "push_in")
        self.assertEqual(d["rows"][4]["shot"], "push_in")                            # "PUSH" alias
        self.assertEqual(d["meta"]["subject"][0], "deer")
        self.assertEqual(d["rows"][0]["value"], "3:00 AM")

    def test_missing_header_and_bad_values(self):
        d = parse_csv_text("1,hook,hello there,bedroom,zoomzoom,,,,,,\nx,hook,again,house,wide,,,,,,\n")
        self.assertTrue(any("no header" in n for n in d["notes"]))
        self.assertTrue(any("shot" in n for n in d["notes"]))
        self.assertEqual(d["rows"][1]["set"], "house_section")                       # alias
        self.assertEqual(parse_csv_text("")["rows"], [])


class PlannerTests(unittest.TestCase):
    def test_cuts_follow_the_voice(self):
        data, al, words, end, pl = built()
        firsts = {}
        for b in pl["beats"]:
            firsts.setdefault(b["row"], b)
        for i, sp in enumerate(al["spans"]):
            if i:
                self.assertAlmostEqual(firsts[i]["start"], sp[0], delta=0.36, msg=f"row {i}")      # at most the minimum-gap nudge
        self.assertEqual(pl["beats"][0]["start"], 0.0)
        self.assertAlmostEqual(pl["beats"][-1]["end"], end, places=2)

    def test_beats_are_contiguous_and_short(self):
        _, _, _, _, pl = built()
        for a, b in zip(pl["beats"], pl["beats"][1:]):
            self.assertAlmostEqual(a["end"], b["start"], places=2)
        for b in pl["beats"]:
            self.assertGreater(b["end"] - b["start"], 0.2)
            self.assertLessEqual(b["end"] - b["start"], MAX_BEAT_S + 0.01)

    def test_long_row_is_cut_with_alternating_camera(self):
        data = parse_csv_text("order,line,set,shot,action\n1,one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty,yard,push_in,figure_stand\n")
        words, end = words_for([data["rows"][0]["line"]], wps=1.0)
        pl = plan(data, align_lines([data["rows"][0]["line"]], words, end), words, end)
        self.assertGreaterEqual(len(pl["beats"]), 3)
        pushes = [b["cam"]["push"] for b in pl["beats"]]
        self.assertTrue(pushes[0] > 0 > pushes[1])

    def test_captions_sit_inside_their_beat_and_card_has_none(self):
        _, _, _, _, pl = built()
        for b in pl["beats"]:
            for c in b["captions"]:
                self.assertGreaterEqual(c["start"], b["start"] - 1e-6)
                self.assertLessEqual(c["end"], b["end"] + 1e-6)
                self.assertLessEqual(len(c["text"].split()), 7)
            if b["card"]:
                self.assertEqual(b["captions"], [])
        card = next(b for b in pl["beats"] if b["card"])
        self.assertEqual(card["card"], {"number": 1, "text": "Do not turn on the lights"})

    def test_state_carries_inside_a_set_and_resets_in_a_new_one(self):
        data = parse_csv_text("order,line,set,action,subject,pose\n1,a b c,yard,figure_walk,deer,walk\n2,d e f,yard,,,\n3,g h i,bedroom,,,\n")
        words, end = words_for([r["line"] for r in data["rows"]])
        pl = plan(data, align_lines([r["line"] for r in data["rows"]], words, end), words, end)
        by = {b["row"]: b for b in pl["beats"]}
        self.assertEqual(len(by[0]["figures"]), 2)
        self.assertEqual(len(by[1]["figures"]), 2)                                   # carried
        self.assertEqual(by[2]["figures"], [])                                       # a new room starts empty

    def test_deer_without_a_picture_is_a_code_drawn_animal(self):
        _, _, _, _, pl = built()
        subj = [f for b in pl["beats"] for f in b["figures"] if f.get("subject") and not f.get("hollow")]
        self.assertTrue(subj and all(f.get("animal") == "deer" for f in subj))

    def test_unknown_subject_is_reported_and_drawn_as_red_eyed_figure(self):
        data = parse_csv_text("order,line,set,subject,pose\n1,a b c,yard,shade,stand\n")
        words, end = words_for(["a b c"])
        pl = plan(data, align_lines(["a b c"], words, end), words, end)
        self.assertTrue(any("shade" in n for n in pl["notes"]))
        subj = [f for b in pl["beats"] for f in b["figures"] if f.get("subject")]
        self.assertTrue(subj and all(f["eyes"] == "red" and f["hollow"] for f in subj))

    def test_grinning_and_mannequin_characters_are_drawn_in_code(self):
        data = parse_csv_text("order,line,set,subject,pose\n1,a b c,yard,smiling usher,stand\n2,d e f,street,mannequin,stand\n")
        words, end = words_for(["a b c", "d e f"])
        pl = plan(data, align_lines(["a b c", "d e f"], words, end), words, end)
        looks = [f.get("look") for b in pl["beats"] for f in b["figures"] if f.get("subject")]
        self.assertEqual(sorted(set(looks)), ["grin", "mannequin"])
        self.assertFalse(any("not available" in n for n in pl["notes"]))
        lay = [L for L in compile_spec(pl)["layers"] if L["type"] == "rh_figure" and L.get("look")]
        self.assertTrue(lay and all(not L.get("hollow") for L in lay))

    def test_colour_schemes_add_a_backdrop_and_a_hazmat_character_and_keep_mono_unchanged(self):
        data = parse_csv_text("order,line,set,subject,pose,action,value\n1,a b c,store,hazmat inspector,stand,figure_stand,\n2,d e f,card,,,rule_card,3\n")
        words, end = words_for(["a b c", "d e f"])
        pl = plan(data, align_lines(["a b c", "d e f"], words, end), words, end)
        mono, col = compile_spec(pl), compile_spec(pl, scheme="colour")
        self.assertEqual(mono["rh"]["scheme"], "mono")
        self.assertFalse(any(L["type"] == "rh_bg" for L in mono["layers"]))
        self.assertEqual(col["rh"]["scheme"], "colour")
        self.assertEqual(sum(L["type"] == "rh_bg" for L in col["layers"]), 1)           # the card beat has its own backdrop
        self.assertTrue(any(L["type"] == "rh_figure" and L.get("look") == "hazmat" for L in col["layers"]))
        self.assertEqual(compile_spec(pl, scheme="nonsense")["rh"]["scheme"], "mono")

    def test_mirror_actions_make_a_reflection_layer_and_refuse_other_sets(self):
        csv = ("order,line,set,action\n1,you look up,bathroom,figure_stand+mirror_early+water\n2,it smiles,bathroom,mirror_early+mirror_smile\n"
               "3,it presses on the glass,bathroom,mirror_early+mirror_press\n4,at the end of the hall,hall_mirror,figure_walk+mirror\n5,not here,kitchen,figure_stand+mirror\n")
        data = parse_csv_text(csv)
        lines = [r["line"] for r in data["rows"]]
        words, end = words_for(lines)
        pl = plan(data, align_lines(lines, words, end), words, end)
        spec = compile_spec(pl)
        mir = [L for L in spec["layers"] if L["type"] == "rh_mirror"]
        self.assertEqual({L["set"] for L in mir}, {"bathroom", "hall_mirror"})
        self.assertTrue(any(L.get("lead") == 0.5 and L.get("water") for L in mir))
        self.assertTrue(any("smile_at" in L for L in mir) and any("press_at" in L for L in mir))
        self.assertTrue(any("kitchen" in n and "mirror" in n for n in pl["notes"]))
        self.assertTrue({"bathroom", "kitchen", "hall_mirror"} <= {L["set"] for L in spec["layers"] if L["type"] == "rh_set"})

    def test_colour_follows_the_narration_and_a_mood_cell_wins(self):
        from rules_horror.mood import moods_for
        rows = [{"line": "It is 3:12 in the morning, you stand there", "set": "bathroom", "action": ""}, {"line": "and the tap runs", "set": "bathroom", "action": ""},
                {"line": "the reflection smiles", "set": "bathroom", "action": "mirror_smile"}, {"line": "somebody has been home all night in a warm yellow room", "set": "bathroom", "action": ""},
                {"line": "you walk on", "set": "yard", "action": ""}, {"line": "and it screams", "set": "yard", "action": ""},
                {"line": "you see the sun come up", "set": "yard", "action": ""}, {"line": "plain words", "set": "yard", "action": "", "mood": "red"}]
        self.assertEqual(moods_for(rows), ["cold", "cold", "cold", "red" if False else "warm", "warm", "red", "dawn", "red"])
        data = parse_csv_text("order,line,set,mood\n1,a quiet street,street,\n2,they scream and run,street,\n3,plain words here,street,warm\n")
        words, end = words_for([r["line"] for r in data["rows"]])
        pl = plan(data, align_lines([r["line"] for r in data["rows"]], words, end), words, end)
        self.assertEqual([b["mood"] for b in pl["beats"]][:1], ["night"])
        self.assertIn("red", pl["stats"]["moods"])
        story, fixed = compile_spec(pl, scheme="story"), compile_spec(pl, scheme="dark")
        self.assertTrue({"night", "red", "warm"} <= {L.get("mood") for L in story["layers"] if L["type"] == "rh_bg"})
        self.assertFalse(any("mood" in L for L in fixed["layers"]))

    def test_ring_hand_handprint_phone_floorboards_and_hair_part_props(self):
        csv = ("order,line,set,action,value\n1,the ring,prop,prop_ring_hand,left>right\n2,the parting,prop,prop_hair_part,right\n3,fog,prop,prop_handprint,\n"
               "4,dark phone,prop,prop_phone_black+mirror_smile,I am up\n5,count them,prop,prop_floorboards,11>12\n6,plain count,prop,prop_floorboards,9\n")
        data = parse_csv_text(csv)
        lines = [r["line"] for r in data["rows"]]
        words, end = words_for(lines)
        pl = plan(data, align_lines(lines, words, end), words, end)
        props = {L["kind"]: L for L in compile_spec(pl)["layers"] if L["type"] == "rh_prop"}
        self.assertEqual(props["ring_hand"]["side"], "left")
        self.assertIn("flip_at", props["ring_hand"])
        self.assertEqual(props["hair_part"]["side"], "right")
        self.assertNotIn("flip_at", props["hair_part"])
        self.assertIn("smile_at", props["phone_black"])
        self.assertEqual(props["phone_black"]["text"], "I am up")
        floors = [L for L in compile_spec(pl)["layers"] if L["type"] == "rh_prop" and L["kind"] == "floorboards"]
        self.assertEqual([(L["count"], L["extra"]) for L in floors], [(11, True), (9, False)])

    def test_prompts_document_every_set_prop_and_action_the_planner_knows(self):
        from rules_horror import prompts
        from rules_horror.mood import MOODS
        from rules_horror.planner import PROPS, SETS
        for text in (prompts.story_prompt(), prompts.convert_prompt()):
            for name in SETS + PROPS:
                self.assertIn(name, text, name)
            for act in ("mirror_early", "mirror_smile", "mirror_press", "water", "bubble", "banner", "red_eyes", "crowd_turn", "rule_card", "glitch"):
                self.assertIn(act, text, act)
            for m in MOODS:
                self.assertIn(m, text, m)
        conv = prompts.convert_prompt()
        self.assertNotIn("{{CSV_SPEC}}", conv)
        self.assertIn("order,section,line,set,shot,subject,pose,action,tag,value,prompt,mood", conv)
        self.assertIn("exactly", conv)

    def test_props_crowd_bubble_banner_and_new_sets(self):
        csv = ("order,line,set,action,value,prompt\n1,test paper,prop,prop_paper,UNIT 4,1. one|2. two\n2,the crowd,crowd,crowd_turn,NORMAL,\n"
               "3,a bubble,stairs,figure_stand+bubble,STAY.,\n4,banner,street,figure_walk+banner,DO NOT PET IT,\n5,cctv,yard,prop_cctv,CAM 02,\n6,phone,prop,prop_phone,,them:hi|me:yo\n")
        data = parse_csv_text(csv)
        lines = [r["line"] for r in data["rows"]]
        words, end = words_for(lines)
        pl = plan(data, align_lines(lines, words, end), words, end)
        spec = compile_spec(pl)
        types = {(L["type"], L.get("kind")) for L in spec["layers"]}
        for want in (("rh_prop", "paper"), ("rh_crowd", "classroom"), ("rh_mark", "bubble"), ("rh_mark", "banner"), ("rh_prop", "cctv"), ("rh_prop", "phone"), ("rh_set", None)):
            self.assertTrue(want in types or (want[1] is None and any(t[0] == want[0] for t in types)), want)
        self.assertEqual({L["set"] for L in spec["layers"] if L["type"] == "rh_set"}, {"stairs", "street", "yard"})
        paper = next(L for L in spec["layers"] if L["type"] == "rh_prop" and L["kind"] == "paper")
        self.assertEqual(paper["lines"], ["1. one", "2. two"])
        self.assertEqual(next(L for L in spec["layers"] if L["type"] == "rh_prop" and L["kind"] == "phone")["messages"], [["them", "hi"], ["me", "yo"]])

    def test_repeated_picture_gets_a_new_angle(self):
        rows = "".join(f"{i},line number {i} goes here,yard,figure_stand,\n" for i in range(1, 6))
        data = parse_csv_text("order,line,set,action,subject\n" + "".join(f"{i},line number {i} goes here,yard,figure_stand,deer\n" for i in range(1, 6)))
        lines = [r["line"] for r in data["rows"]]
        words, end = words_for(lines)
        pl = plan(data, align_lines(lines, words, end), words, end)
        focus = [b["cam"].get("focus") for b in pl["beats"]]
        self.assertIsNone(focus[0])
        self.assertTrue(all(f is not None for f in focus[1:]))
        self.assertGreaterEqual(len({tuple(f) for f in focus[1:]}), 2)       # not the same zoom twice in a row
        self.assertEqual(check_screen(pl).count("x"), 0)

    def test_combined_actions(self):
        _, _, _, _, pl = built()
        last = [b for b in pl["beats"] if b["row"] == 4]
        self.assertTrue(any(f["pose"] == "walk" and "walk_to" in f for f in last[0]["figures"]))
        self.assertTrue(any(m["kind"] == "sight" for m in last[0]["marks"]) or not any(f.get("subject") for f in last[0]["figures"]))

    def test_unknown_set_keeps_the_previous_one_and_says_so(self):
        data = parse_csv_text("order,line,set\n1,a b,yard\n2,c d,spaceship\n")
        words, end = words_for(["a b", "c d"])
        pl = plan(data, align_lines(["a b", "c d"], words, end), words, end)
        self.assertTrue(any("spaceship" in n for n in pl["notes"]))
        self.assertEqual({b["set"] for b in pl["beats"]}, {"yard"})


class CompileAndSoundTests(unittest.TestCase):
    def test_spec_shape(self):
        _, _, _, end, pl = built()
        spec = compile_spec(pl)
        self.assertEqual(len(spec["shots"]), len(pl["beats"]))
        self.assertTrue(all(s["kind"] == "black" for s in spec["shots"]))
        known = {"rh_set", "rh_figure", "rh_mark", "rh_rulecard", "rh_caption", "rh_glitch", "rh_animal", "rh_prop", "rh_crowd"}
        self.assertTrue(all(L["type"] in known for L in spec["layers"]))
        self.assertTrue(all(L["fade_in"] == 0 and L["fade_out"] == 0 for L in spec["layers"]))        # hard cuts
        types = [L["type"] for L in spec["layers"]]
        first_glitch = types.index("rh_glitch") if "rh_glitch" in types else len(types)
        self.assertTrue(all(t == "rh_glitch" for t in types[first_glitch:]))          # the glitch tears everything drawn before it
        self.assertEqual(spec["look"]["lift"], "#000000")
        self.assertAlmostEqual(spec["duration"], end, places=3)

    def test_sound_cues_are_spaced_and_never_before_zero(self):
        _, _, _, _, pl = built()
        cues = plan_cues(pl["beats"])
        self.assertTrue(cues)
        for a, b in zip(cues, cues[1:]):
            self.assertGreaterEqual(b["t"] - a["t"], 0.5)
        self.assertTrue(all(c["t"] >= 0 for c in cues))
        card = next(b for b in pl["beats"] if b["card"])
        self.assertTrue(any(abs(c["t"] - card["start"]) < 0.01 and c["kind"] == "impact" for c in cues))


class FakeClient:
    """Stands in for the Flow engine client: every request gets a picture except those whose prompt says FAIL."""
    def __init__(self, root):
        self.root, self.calls, self.sub = root, [], None

    def subscribe(self, cb):
        self.sub = cb
        return lambda: None

    def generate(self, prompts, settings=None, prompt_keys=None):
        from PIL import Image
        self.calls.append({"prompts": prompts, "refs": (settings or {}).get("referenceImages", []), "key": prompt_keys[0]})
        if "FAIL" in prompts[0]:
            self.sub({"type": "PROMPT_RESULT", "status": "failed", "error": "no picture"}); self.sub({"type": "GENERATE_DONE"}); return
        p = self.root / f"{prompt_keys[0]}.png"
        Image.new("RGB", (64, 36), (255, 255, 255)).save(p)
        self.sub({"type": "PROMPT_RESULT", "status": "done", "path": str(p)}); self.sub({"type": "GENERATE_DONE"})

    def wait_for(self, fn, timeout=0):
        return True


class AssetsAndChecksTests(unittest.TestCase):
    def test_requests_list_each_pose_once_reference_first_and_closeups(self):
        data = parse_csv_text(CSV + "6,x,more words,yard,wide,deer,walk,,,,\n7,x,again,yard,wide,deer,stand_side,,,,\n")
        reqs = assets.requests(data)
        keys = [r["key"] for r in reqs]
        self.assertEqual(keys[0], "deer:stand_side")
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("deer:walk", keys)
        self.assertTrue(any(r["kind"] == "closeup" and "white face" in r["prompt"] for r in reqs))
        self.assertTrue(all("pure black" in r["prompt"].lower() for r in reqs))
        self.assertEqual([r["n"] for r in reqs], list(range(1, len(reqs) + 1)))

    def test_make_attaches_the_reference_and_survives_a_failed_picture(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            data = parse_csv_text(CSV + "6,x,more,yard,wide,deer,walk,,,,\n")
            reqs = assets.requests(data)
            reqs[-1]["prompt"] += " FAIL"
            client = FakeClient(d)
            res = assets.make(reqs, d / "out", client)
            self.assertEqual(res[1]["status"], "done")
            self.assertEqual(client.calls[0]["refs"], [])                           # the reference pose goes alone
            self.assertTrue(all(c["refs"] == [res[1]["path"]] for c in client.calls[1:] if "closeup" not in c["key"] and "deer" in c["key"]))
            self.assertEqual(res[reqs[-1]["n"]]["status"], "failed")                # the failed one is reported, the rest are kept
            self.assertTrue(any(v["status"] == "done" for k, v in res.items() if k != reqs[-1]["n"]))
            again = assets.make(reqs, d / "out", FakeClient(d), skip={1: res[1]["path"]})
            self.assertEqual(again[1]["path"], res[1]["path"])                      # a picture already made is not made again

    def test_pictures_reach_the_plan_and_a_missing_file_falls_back(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "deer.png"
            Image.new("RGB", (64, 36), (255, 255, 255)).save(png)
            data = parse_csv_text(CSV)
            lines = [r["line"] for r in data["rows"]]
            words, end = words_for(lines)
            al = align_lines(lines, words, end)
            pl = plan(data, al, words, end, pictures={"deer:stand_side": str(png), "closeup:3": str(png)})
            self.assertFalse(any("not available" in n for n in pl["notes"]))
            media = stage_media(pl, Path(d) / "media")
            spec = compile_spec(pl, media=media, media_dir=Path(d) / "media")
            kinds = [L["type"] for L in spec["layers"]]
            self.assertIn("rh_picture", kinds)
            self.assertEqual(spec["media_dir"], str(Path(d) / "media"))
            png.unlink()
            pl2 = plan(data, al, words, end, pictures={"deer:stand_side": str(png)})
            spec2 = compile_spec(pl2, media=stage_media(pl2, Path(d) / "media2"))        # the file vanished: a code figure, no crash
            self.assertNotIn("rh_picture", [L["type"] for L in spec2["layers"]])

    def test_story_check_only_warns_and_knows_a_good_shape(self):
        data, al, words, end, pl = built()
        warn = check_story(data, al, end)
        self.assertTrue(any("rule card" in w for w in warn))                          # the short sample has 1 rule card, not 7
        self.assertIsInstance(check_screen(pl), list)
        rows = [("hook", "If you ever see a tall deer in your yard do not wave", "yard", "")]
        for i in range(7):
            rows.append(("rule", f"rule {i + 1} text", "card", "rule_card"))
        rows.append(("close", "So if you ever see a tall deer in your yard stay in bed", "bedroom", ""))
        text = "order,section,line,set,action,value\n" + "\n".join(f"{i + 1},{a},{b},{c},{d},{i if d else ''}" for i, (a, b, c, d) in enumerate(rows))
        good = parse_csv_text(text)
        al2 = {"spans": [(40.0 + i * 5, 44.0 + i * 5) for i in range(len(rows))], "ranges": [(0, 0)] * len(rows), "ok": True}
        self.assertFalse(any("closing line" in w for w in check_story(good, al2, 120.0)))
        self.assertFalse(any("7 rules" in w for w in check_story(good, al2, 120.0)))


class ReferenceProfiles(unittest.TestCase):
    """All nine references are used, not one: each story picks the look whose places it mentions; pacing and cards follow that reference."""

    def test_each_setting_picks_its_reference(self):
        from rules_horror import profiles
        cases = {"line_house": "a tall deer stands in the yard at three in the morning", "night_flight": "the flight attendant walks down the plane",
                 "night_cinema": "the usher at the movie theater", "bright_store": "the supermarket aisle after closing", "bright_mall": "the mannequin in the mall",
                 "bright_school": "your substitute teacher in the classroom", "deep_water": "the aquarium tank and the diver", "line_pet": "your dog stares at the wall",
                 "line_exam": "do not drop your pencil during the test"}
        for want, line in cases.items():
            self.assertEqual(profiles.pick({"rows": [{"line": line}]}), want, line)
        self.assertEqual(profiles.pick({"rows": [{"line": "the deer"}], "meta": {"look": "deep_water"}}), "deep_water")      # a #look line wins
        spread = {profiles.pick({"rows": [{"line": f"nothing matches here {i}"}]}) for i in range(60)}
        self.assertGreaterEqual(len(spread), 6)                                             # no-keyword stories still spread over the nine

    def test_the_animal_never_covers_the_person(self):
        from rules_horror.planner import REACH, separate
        for animal, facing in (("deer", "right"), ("deer", "left"), ("dog", "right"), ("dog", "left")):
            for px in (0.1, 0.3, 0.5, 0.6, 0.9):
                figs = [{"pose": "stand", "x": px, "size": 0.34, "walk_to": px + 0.1}, {"animal": animal, "x": 0.52, "size": 0.6, "facing": facing}]
                separate(figs)
                p, a = figs
                back, front = REACH[animal]
                f = 1 if facing == "right" else -1
                lo, hi = sorted((a["x"] - f * back * 0.6 * 9 / 16, a["x"] + f * front * 0.6 * 9 / 16))
                self.assertTrue(p["x"] + 0.04 <= lo or p["x"] - 0.04 >= hi, (animal, facing, px, p["x"], lo, hi))
                self.assertTrue(0.04 <= p["x"] <= 0.96)

    def test_pacing_and_cards_follow_the_profile(self):
        from rules_horror import profiles
        data, al, words, end, _ = built()
        fast, slow = profiles.get("bright_store"), profiles.get("line_house")
        pf, ps = plan(data, al, words, end, profile=fast), plan(data, al, words, end, profile=slow)
        self.assertGreater(pf["stats"]["cuts_per_min"], ps["stats"]["cuts_per_min"])
        self.assertGreater(pf["stats"]["punch_ins"], 0)
        self.assertTrue(all(b["end"] - b["start"] <= fast["max_beat"] + 0.05 for b in pf["beats"]))
        self.assertEqual(check_screen(ps), [w for w in check_screen(ps) if "s long" not in w])   # long line-art holds are allowed by their profile
        for style in ("dim", "tag", "paper", "sign", "hazard", "black"):
            spec = compile_spec(pf, scheme=fast["scheme"], card_style=style)
            cards = [L for L in spec["layers"] if L["type"] == "rh_rulecard"]
            self.assertTrue(cards and all(L["style"] == style for L in cards))
        dim = compile_spec(pf, scheme="dark", card_style="dim")
        i = next(k for k, L in enumerate(dim["layers"]) if L["type"] == "rh_rulecard")
        self.assertEqual(dim["layers"][i - 1]["type"], "rh_set")                            # the dim card sits over the last scene


if __name__ == "__main__":
    unittest.main()
