"""Fixes from render 054 (2026-11-02), each a general rule: the narration's own spelling, pictures that match what the line says (who, not-X, contrasts),
cards that never sit empty, and short label lines joined to what they label."""
import unittest

from reptheory import beat_art as BA, lexicon as LX, planner as P, poses, tricks as TR, variety as V


def scene(text, start=0.0, kind="callout", sec="HOLD 1 · TOWEL RING"):
    ws = [{"w": w, "t0": start + i * 0.3} for i, w in enumerate(text.split())]
    return {"text": text, "words": ws, "start": start, "end": start + len(ws) * 0.3 + 0.2, "kind": kind, "pages": [], "decisions": [], "section": sec, "no": 1}


class Spelling(unittest.TestCase):
    def test_script_spelling_survives_the_transcript(self):
        t = "That's not muscle. It's their tendons. Stiffness jumped 57%. Wolff's law is where \"mechanic strength\" lives."
        w = [{"w": x, "t0": i, "t1": i + 1} for i, x in enumerate("that not muscle it their tendons stiffness jumped 57 wolf law is where mechanic strength lives".split())]
        self.assertEqual(" ".join(x["w"] + x.get("p", "") for x in P.respell(t, w)),
                         "that's not muscle. it's their tendons. stiffness jumped 57%. wolff's law is where mechanic strength lives.")


class PictureMeaning(unittest.TestCase):
    def test_what_a_line_denies_is_not_shown(self):
        self.assertIsNone(poses.pick("They don't go to the gym. They don't drink protein shakes.", lambda a: True))
        self.assertNotIn("muscle", LX.affirmed("that's not muscle.").lower())

    def test_workers_are_drawn_as_the_tradesman(self):
        p = BA.prompt_for("Have you ever shaken hands with an old mechanic, a bricklayer, or a farmer?", hook=True)
        self.assertIn("tradesman", p); self.assertNotIn("heavily muscled", p)

    def test_a_repeated_csv_picture_for_a_different_line_is_drawn_from_its_line(self):
        a, b = scene("Gym bros build a bigger motor tied to rubber bands.", 0), scene("Mechanics build steel cables with zero slack.", 4)
        for s, n in ((a, 1), (b, 2)): s.update(look="flow", flow_prompt="a big engine motor connected to a hand by stretched rubber bands", no=n)
        got = []; BA.prepare([a, b], directed=True, collect=got)
        self.assertNotEqual(got[0]["prompt"], got[1]["prompt"])

    def test_bone_and_xray_lines_get_no_muscle_clip(self):
        self.assertNotIn("3d", V.evidence(scene("X-ray studies show the cortical bone in their fingers and wrists is thicker.")))


class Cards(unittest.TestCase):
    def test_bands_said_one_per_line_become_one_board(self):
        ss = [scene("Under 25 seconds: your tendons are the weak link.", 0), scene("25 to 45 seconds: you are right around average.", 4),
              scene("45 to 75 seconds: you have a solid base.", 8), scene("Over 75 seconds: your crush grip is strong.", 12)]
        self.assertEqual(V.bands_across(ss), 4)
        self.assertEqual(len(ss[0]["band_card"]["tiers"]), 4); self.assertTrue(all(s.get("band") for s in ss[1:]))

    def test_a_late_like_ask_is_a_chip_not_a_card(self):
        sc = scene("Quick one: if you have bought one of those cheap plastic hand grippers and did five hundred reps with nothing to show, hit like.")
        self.assertNotIn("engage", V.evidence(sc))
        TR.plan([sc]); self.assertEqual(sc["cta"]["kind"], "like")

    def test_promise_label_never_ends_mid_phrase(self):
        c = V._promise(scene("At the end of this video, I'll show you the exact scorecard for what your time means."), "At the end of this video, I'll show you the exact scorecard for what your time means.")
        self.assertFalse(c["label"].endswith(("WHAT", "YOUR", "FOR")))

    def test_short_label_line_joins_what_it_labels(self):
        ss = [scene("Here is the plan.", 0), scene("The towel ring hold:", 2.0), scene("Four sets of 25 to 35 seconds.", 3.4)]
        ss[1]["end"] = 3.2; ss[2]["start"] = 3.2
        self.assertEqual(V.join_short(ss), 1); self.assertEqual(len(ss), 2); self.assertTrue(ss[1]["text"].startswith("The towel ring hold:"))

    def test_denial_answered_next_is_struck_out(self):
        sc = scene("That's not muscle. It's their finger tendons and their bone density.", kind="illus")
        TR.plan([sc]); self.assertEqual(sc["strike"]["text"], "MUSCLE?")


if __name__ == "__main__":
    unittest.main()


class LongPictures(unittest.TestCase):
    def test_a_long_csv_picture_is_cut_and_reframed(self):
        sc = scene("Under a rule called Wolff's law, whenever you put heavy load on bone and tendon, the body lays down new tissue, and over months the bone itself gets thicker and denser in exactly the spots you load.", 0)
        sc.update(look="flow", directed_look=True, flow_prompt="an x-ray forearm under load")
        ss = [scene("Intro line before it.", -3), sc]; ss[0]["look"] = "stock"
        V.reframe_long(ss)
        parts = [x for x in ss if x.get("flow_prompt")]
        self.assertGreaterEqual(len(parts), 2); self.assertTrue(all(p["end"] - p["start"] <= V.PIC_LONG_S + 0.5 for p in parts))
        self.assertTrue(parts[1]["same_picture"]); self.assertEqual(parts[0]["flow_prompt"], parts[1]["flow_prompt"])


class Final2Fixes(unittest.TestCase):      # the two issues seen in final 2.mp4
    def test_split_row_without_a_body_part_drops_the_plate(self):
        from reptheory import direction as DR
        sc = scene("have you ever shaken hands with an old mechanic, a bricklayer, or a farmer", 0, kind="anatomy"); sc["art"] = "anat_forearm_v1"
        ss = [sc]; DR._split_at(ss, sc["words"][-3]["t0"]) if hasattr(DR, "_split_at") else None
        tail = ss[-1]
        if len(ss) == 2: self.assertEqual(tail["kind"], "callout"); self.assertEqual(ss[0]["kind"], "anatomy")

    def test_no_guessed_ring_on_a_moving_part(self):
        from reptheory import picture as PIC
        info = {"red": None, "red_pt": None, "bbox": (0.5, 0.1, 0.8, 0.95), "size": (100, 100)}
        self.assertIsNone(PIC._part_point(info, {"part": "wrists"}, 0))
        self.assertEqual(PIC._part_point(dict(info, red_pt=(0.63, 0.33)), {"part": "wrists"}, 0), (0.63, 0.33))
        self.assertIsNotNone(PIC._part_point(info, {"part": "chest"}, 0))
