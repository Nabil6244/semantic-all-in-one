"""Survival: the Rep Theory engine with the field-guide theme (reptheory/theme.py "survival"), its own script and CSV prompts, and the rules from the 10 s test (2026-11-10)."""
import unittest

from reptheory import app_section as A, art as AR, beat_art as BA, direction as DR, gate as G, packaging as PK, picture as P, theme as T
from ui import style_registry as R


class SurvivalTheme(unittest.TestCase):
    def tearDown(self):
        T.set_theme("")

    def test_switch_and_back(self):
        base = (T.BG_TOP, T.WHITE, T.HEAD_FONT)
        self.assertEqual(T.set_theme("survival"), "survival")
        self.assertIn("survival", T.NO_GYM); self.assertIn("survival", T.LIGHT)
        self.assertGreater(sum(T.BG_TOP), 700); self.assertLess(sum(T.WHITE), 200)      # paper canvas, dark ink type
        T.set_theme("")
        self.assertEqual((T.BG_TOP, T.WHITE, T.HEAD_FONT), base)

    def test_picture_prompts_use_the_field_guide_style(self):
        T.set_theme("survival")
        self.assertIn(AR.SURVIVAL_STYLE, BA.prompt_for("A blaze is a cut through the bark."))
        self.assertIn(AR.SURVIVAL_STYLE, BA.own_prompt("a long hunter cutting a blaze"))
        self.assertIn("drawn large", AR.SURVIVAL_STYLE)      # the detail the sentence is about must be unmistakable (test 1: blazes too faint)
        T.set_theme("cat")
        self.assertNotIn(AR.SURVIVAL_STYLE, BA.prompt_for("A blaze is a cut through the bark."))

    def test_close_up_is_a_real_close_up_only_in_survival(self):
        self.assertGreater(P.SURVIVAL_PUSH["close"][0], P.SURVIVAL_PUSH["medium"][1] * 1.25)
        self.assertEqual(P.PUSH["close"], (1.12, 1.22))      # Rep Theory / Cat / Jung / Elder keep their framing

    def test_no_repeated_words_on_screen(self):
        self.assertTrue(G.repeats("THAT'S NUMBER TWENTY-TWO", {"NUMBER TWENTY-TWO"}))
        self.assertTrue(G.repeats("THAT'S NUMBER TWENTY-TWO", {"#22"}))
        self.assertFalse(G.repeats("PALE WOOD", {"EYE LEVEL", "#22"}))
        self.assertFalse(G.repeats("", {"#22"}))

    def test_spoken_number_may_show_as_digits(self):
        self.assertEqual(DR.on_screen_ok("#22", "That's number twenty-two."), "#22")
        self.assertEqual(DR.on_screen_ok("$20", "There's a way to hide for about twenty dollars."), "$20")
        self.assertEqual(DR.on_screen_ok("22 DAYS", "It took days."), "")

    def test_picker_and_prompts(self):
        self.assertEqual(R.BUILT_ON[R.SURVIVAL], "Rep Theory")
        out = R.with_extras(("Rep Theory", "Health Cinema"))
        self.assertEqual(out[out.index("Elder Health Theory") + 1], "Survival")
        txt = A.prompt_text("That's number 22.", cat="survival")
        self.assertIn("Survival video", txt); self.assertTrue(txt.rstrip().endswith("That's number 22.")); self.assertNotIn("<<<PASTE", txt)
        script = A.SURVIVAL_SCRIPT_PROMPT_FILE.read_text(encoding="utf-8")
        for must in ("ONE SECRET, MANY MYTHS", "THE ONE RULE", "THE BRIDGE", "FORCED-CHOICE", "Never invent", "TOPIC:"):
            self.assertIn(must, script)
        names = {p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for p, _ in PK.prompt_files(".")}
        self.assertTrue({"survival_scenes_csv_prompt.txt", "survival_script_prompt.txt"} <= names)

    def test_csv_example_is_valid(self):
        import csv, io
        txt = A.SURVIVAL_PROMPT_FILE.read_text(encoding="utf-8")
        block = txt.split("CSV:\n", 1)[1].split("\n\nSCRIPT", 1)[0]
        rows = list(csv.reader(io.StringIO(block)))
        self.assertEqual(rows[0], ["text", "chapter", "look", "prompt", "muscle", "camera", "on_screen", "section", "graphic"])
        T.set_theme("survival")
        for r in rows[1:]:
            self.assertEqual(len(r), 9, r)
            if r[2]: self.assertTrue(DR.norm_look(r[2]), r[2])
            if r[6]: self.assertTrue(DR.on_screen_ok(r[6], r[0]), (r[6], r[0]))


def _scenes(text: str, per_scene: int = 2):
    """Scenes of `per_scene` sentences each, every word 0.4 s long."""
    import re
    sents = re.findall(r"[^.!?]+[.!?]", text); t = 0.0; out = []
    for k in range(0, len(sents), per_scene):
        ws = []
        for s in sents[k:k + per_scene]:
            toks = s.split()
            for j, w in enumerate(toks):
                core = w.rstrip(".,!?:;"); ws.append({"w": core, "t0": round(t, 2), "t1": round(t + 0.35, 2), "p": w[len(core):]}); t += 0.4
            t += 0.3
        out.append({"start": ws[0]["t0"], "end": round(t, 2), "words": ws, "text": " ".join(sents[k:k + per_scene]).strip(), "kind": "illus", "look": "flow", "pages": [], "decisions": []})
    for a, b in zip(out, out[1:]): a["end"] = b["start"]
    return out


class SurvivalCards(unittest.TestCase):
    """Every card from the narration's own words, on the word that says it (reptheory/survival.py)."""
    def setUp(self):
        T.set_theme("survival")

    def tearDown(self):
        T.set_theme("")

    SCRIPT = ("Most advice says three days. And number one is a sickness that shows up in the third month. "
              "Number seven costs a lot if you get it wrong. "
              "They burned dried dung on the plains. That's number five. It costs nothing and a child can gather it. "
              "The one rule that matters: only dung from animals that eat grass. "
              "Hold on to that sickness for later. Number four takes about a minute to learn. Hold your hand to the sun. "
              "Number three is butter. Number two is a blaze. Remember the sickness? Number one is scurvy. Sprouts take three days to grow.")

    def test_only_the_real_countdown_counts(self):
        from reptheory import survival as SV
        sc = _scenes(self.SCRIPT); SV.plan(sc)
        nums = [(c["n"], c["at"]) for x in sc for c in x.get("sv", {}).get("numbers", [])]
        self.assertEqual([n for n, _ in nums], [5, 4, 3, 2, 1])      # the opening teases of one and seven are not items
        words = {round(w["t0"], 2): w["w"] for x in sc for w in x["words"]}
        self.assertEqual([words[round(t, 2)].lower() for _, t in nums], ["five", "four", "three", "two", "one"])      # on the number word itself
        badge = next(x["sv"]["badge"] for x in sc if x.get("sv", {}).get("badge"))
        self.assertEqual(badge["total"], 5)

    def test_strip_only_says_what_was_said(self):
        from reptheory import survival as SV
        sc = _scenes(self.SCRIPT); SV.plan(sc)
        strips = {id(x["sv"]["strip"]): x["sv"]["strip"] for x in sc if x.get("sv", {}).get("strip")}.values()
        got = [[(f["kind"], f["text"]) for f in s["facts"]] for s in strips]
        self.assertIn([("cost", "FREE"), ("level", "EASY")], got)      # number five: "costs nothing and a child can gather it"
        self.assertIn([("time", "1 MINUTE")], got)                      # number four: "takes about a minute to learn"
        self.assertTrue(all(f["text"] for s in got for f in [dict(kind=k, text=v) for k, v in s]))
        self.assertFalse(any("BUTTER" in v for s in got for _, v in s))      # number three says nothing about cost or time: no chip invented

    def test_tracker_and_rule(self):
        from reptheory import survival as SV
        sc = _scenes(self.SCRIPT); r = SV.plan(sc)
        self.assertGreaterEqual(r["teases"], 2); self.assertEqual(r["rules"], 1)
        unlock = next(x["sv"]["unlock"] for x in sc if x.get("sv", {}).get("unlock"))
        one = next(c["at"] for x in sc for c in x.get("sv", {}).get("numbers", []) if c["n"] == 1)
        self.assertEqual(unlock["at"], one)
        rule = next(x["sv"]["rule"] for x in sc if x.get("sv", {}).get("rule"))
        self.assertEqual(" ".join(w["w"] for w in rule["words"]), "only dung from animals that eat grass.")
        self.assertTrue(all(a["t0"] < b["t0"] for a, b in zip(rule["words"], rule["words"][1:])))      # written in word by word

    def test_no_countdown_no_numbers(self):
        from reptheory import survival as SV
        sc = _scenes("A drone can find you in minutes. There is a trick for twenty dollars. A bush will not hide you. A tarp warms up. "
                     "Glass blocks the camera. The ground keeps a print. Remember that thing in the first aid kit? It is the emergency blanket.")
        r = SV.plan(sc)
        self.assertEqual(r["numbers"], 0)
        self.assertFalse(any(x.get("sv", {}).get("badge") for x in sc))

    def test_cards_draw(self):
        from reptheory import survival as SV
        from reptheory import draw as D
        from PIL import Image
        sc = _scenes(self.SCRIPT); SV.plan(sc); ctx = D.Ctx(1280, 720)
        for x in sc:
            for t in (x["start"] + 0.1, (x["start"] + x["end"]) / 2, x["end"] - 0.1):
                cv = Image.new("RGB", (1280, 720), T.BG_TOP); SV.draw(cv, ctx, x, t)
        x = next(x for x in sc if x.get("sv", {}).get("numbers"))
        cv = Image.new("RGB", (1280, 720), T.BG_TOP); SV.draw(cv, ctx, x, x["sv"]["numbers"][0]["at"] + 0.8)
        self.assertLess(cv.convert("L").getextrema()[0], 120)      # the big number is drawn in dark ink


class CsvWordsHold(unittest.TestCase):
    def test_on_screen_on_its_word_and_kept_for_the_row(self):
        s = {"text": "The pale wood shows up even in bad light.", "start": 5.0, "end": 8.0,
             "words": [{"w": w, "t0": 5.0 + 0.3 * i} for i, w in enumerate("The pale wood shows up even in bad light.".split())]}
        self.assertAlmostEqual(DR.word_time("PALE WOOD", s), 5.3)
        self.assertAlmostEqual(DR.word_time("#22", {"start": 1.0, "words": [{"w": "That's", "t0": 1.0}, {"w": "number", "t0": 1.3}, {"w": "twenty-two.", "t0": 1.7}]}), 1.7)
        sc = {"on_screen": "PALE WOOD", "on_screen_span": (5.0, 8.0), "pages": [
            {"at": 5.0, "headline": "PALE WOOD", "chips": []}, {"at": 6.5, "headline": "BAD LIGHT", "chips": [{"text": "EVEN", "at": 6.6}]}, {"at": 8.2, "headline": "NEXT", "chips": []}]}
        self.assertEqual(G.keep_csv_words([sc]), 1)
        self.assertEqual([p["headline"] for p in sc["pages"]], ["PALE WOOD", "NEXT"])      # the next row's page stays
        self.assertEqual([c["text"] for c in sc["pages"][0]["chips"]], ["EVEN"])


class FairTestFixes(unittest.TestCase):
    """The 2-minute fair test (2026-11-10): rules, not patches."""
    def test_negation_breaks_a_key_phrase(self):
        from reptheory import narrative as N
        self.assertNotIn("WEREN'T", N.key_phrase("Most people who get lost in the woods weren't lost on the way out.")[0])
        self.assertNotIn("NEVER", N.key_phrase("Never cut a living tree.")[0])

    def test_tidy_kickers_values_tints(self):
        from reptheory import survival as SV
        sc = [{"text": "Most people who get lost in the woods weren't lost.", "tint": {"at": 1.0}, "pages": [{"kicker": "MISTAKE", "headline": "WOODS", "value": ""}]},
              {"text": "And number one takes two seconds.", "pages": [{"kicker": "KEY", "headline": "", "value": "2 S"}, {"kicker": "", "value": "1 MIN"}]},
              {"text": "The most common mistake is driving.", "pages": [{"kicker": "MISTAKE", "headline": "DRIVING", "value": ""}]}]
        r = SV.tidy(sc)
        self.assertEqual(r, {"kickers": 2, "values": 2, "tints": 1})
        self.assertNotIn("tint", sc[0]); self.assertEqual(sc[0]["pages"][0]["kicker"], "")
        self.assertEqual([p["value"] for p in sc[1]["pages"]], ["2 SECONDS", "1 MINUTE"])
        self.assertEqual(sc[2]["pages"][0]["kicker"], "MISTAKE")      # said, so kept

    def test_number_card_replaces_chapter_card(self):
        from reptheory import survival as SV
        T.set_theme("survival")
        try:
            sc = _scenes(SurvivalCards.SCRIPT)
            for x in sc: x["chapter_card"] = {"n": 1, "of": 3, "title": "X"}
            SV.plan(sc)
            for x in sc:
                if x.get("sv", {}).get("numbers"): self.assertNotIn("chapter_card", x)
        finally:
            T.set_theme("")


class SurvivalFormats(unittest.TestCase):
    """Phase 3-5 (2026-11-10): each format's extra, from the narration's own words."""
    def setUp(self):
        T.set_theme("survival")

    def tearDown(self):
        T.set_theme("")

    def _plan(self, text, per_scene=2):
        from reptheory import survival as SV
        sc = _scenes(text, per_scene); r = SV.plan(sc); return sc, r

    def test_thermal_starts_on_its_word_and_follows_heat_talk(self):
        sc, r = self._plan("A drone flies over the field at night. To a thermal camera you glow like a lamp. Your warm body stands out against the cold ground. "
                           "The tarp warms up within minutes. Now let us talk about food. Beans keep for years.", 1)
        self.assertEqual(r["thermal"], 1)
        on = [x["text"] for x in sc if x.get("sv", {}).get("thermal")]
        self.assertEqual(on[0], "To a thermal camera you glow like a lamp.")
        self.assertIn("The tarp warms up within minutes.", on)
        self.assertNotIn("Beans keep for years.", on)
        word = next(w for w in sc[1]["words"] if w["w"] == "thermal")
        self.assertEqual(sc[1]["sv"]["thermal"]["at"], word["t0"])

    def test_state_map_needs_a_ranking(self):
        _, r = self._plan("Hawaii has no neighbour to lean on. Texas runs its own grid.")
        self.assertEqual(r["states"], 0)      # two states named is a mention
        sc, r = self._plan("That's number fifty. Hawaii goes dark first. That's number forty-nine. Alaska is next. That's number forty-eight. Maine follows.")
        self.assertEqual(r["states"], 3)
        st = [x["sv"]["state"] for x in sc if x.get("sv", {}).get("state")]
        self.assertEqual(st[0]["name"], "Hawaii"); self.assertEqual(st[0]["rank"], 50)
        self.assertIn("Hawaii", st[-1]["done"])
        self.assertEqual([x["rank"] for x in st], [50, 49, 48])      # each state takes the latest announcement before it

    def test_timeline_from_spoken_times(self):
        sc, r = self._plan("In the first hour the lights go out. By the first night the house is cold. On day three the water runs short. A week later the stores are empty.")
        self.assertEqual(r["timeline"], 3)
        tl = next(x["sv"]["timeline"] for x in sc if x.get("sv", {}).get("timeline"))
        self.assertEqual([m["label"] for m in tl["marks"]], ["HOUR 1", "NIGHT 1", "DAY 3"])
        _, r = self._plan("Number three is salt. Number two is a pot. Number one is a blanket. In the first hour the lights go out. By the first night it is cold. On day three it runs short.")
        self.assertEqual(r["timeline"], 0)      # a countdown has its progress dots

    def test_persona_and_prices(self):
        sc, r = self._plan("The man who owns it is named Ray. Ray, 81, has lived through four blizzards. A tactical flashlight costs $120. A headlamp does the job for $4.")
        self.assertEqual(r["persona"], 1)
        p = next(x["sv"]["persona"] for x in sc if x.get("sv", {}).get("persona")); self.assertEqual(p["name"], "RAY")
        self.assertEqual(r["prices"], 1)
        pr = next(x["sv"]["prices"] for x in sc if x.get("sv", {}).get("prices")); self.assertEqual([g["v"] for g in pr["tags"]], [120.0, 4.0])
        _, r = self._plan("A bag costs $20. A better bag costs $25.")
        self.assertEqual(r["prices"], 0)      # no real gap, no compare

    def test_all_extras_draw(self):
        from reptheory import survival as SV, draw as D
        from PIL import Image
        sc, _ = self._plan("That's number fifty. Hawaii goes dark first. That's number forty-nine. Alaska is next. That's number forty-eight. Maine follows. "
                           "To a thermal camera you glow. Ray, 81, says a $120 light loses to a $4 headlamp.")
        ctx = D.Ctx(640, 360)
        for x in sc:
            x["_shown"] = ((0, 0, 1, 1), (0, 0, 400, 360))
            for t in (x["start"] + 0.2, (x["start"] + x["end"]) / 2, x["end"] - 0.05):
                cv = Image.new("RGB", (640, 360), T.BG_TOP); SV.draw(cv, ctx, x, t)

    def test_thermal_palette(self):
        from reptheory import survival_formats as SF
        from PIL import Image
        im = Image.new("RGB", (60, 40), (250, 250, 248)); im.paste((20, 20, 20), (20, 10, 40, 30))
        th = SF.thermal_image(im)
        self.assertLess(sum(th.getpixel((2, 2))), 120)      # paper reads cold (dark)
        self.assertGreater(sum(th.getpixel((30, 20))), 500)      # ink reads hot (bright)


class SurvivalSoundAndPackage(unittest.TestCase):
    def test_scene_beds_follow_the_subject(self):
        from reptheory import survival_sound as SS
        sc = [{"start": 0.0, "text": "We lit the woodstove before dark. The fire crackled and the coals glowed."},
              {"start": 15.0, "text": "Smoke drifted up the chimney. Kindling was stacked by the door."},
              {"start": 30.0, "text": "Then we talked about money. Prices went up again."},
              {"start": 45.0, "text": "Banks closed early. Nobody knew why."}]
        self.assertEqual(SS.beds(sc), [{"t": 0.0, "ambience": "sv_fire"}, {"t": 30.0, "ambience": "none"}])
        self.assertEqual(SS.beds([{"start": 0.0, "text": "There was a fire once. Then we moved on to taxes."}]), [])      # one passing word is not the subject
        from pakmap import sounds as PS
        self.assertTrue({"sv_fire", "sv_rain", "sv_water", "sv_cold", "sv_wind", "sv_forest"} <= set(PS.SOUNDS))

    def test_chapters_and_titles(self):
        from reptheory import survival_package as SP
        sc = [{"start": 0.0, "text": "Most people get lost on the way back.", "section": "INTRO"},
              {"start": 20.0, "text": "We still say somebody blazed a trail.", "section": "NUMBER 3 · THE BLAZE"},
              {"start": 26.0, "text": "That's number three.", "section": "NUMBER 3 · THE BLAZE", "sv": {"numbers": [{"n": 3, "at": 26.5}]}},
              {"start": 60.0, "text": "That's number two.", "section": "NUMBER 2 · THE SUN", "sv": {"numbers": [{"n": 2, "at": 60.4}]}},
              {"start": 80.0, "text": "When the grid goes down, number one is looking back.", "section": "NUMBER 1 · LOOK BACK", "sv": {"numbers": [{"n": 1, "at": 80.2}]}}]
        self.assertEqual(SP.chapters(sc), [(0.0, "Intro"), (20.0, "Number 3 · The Blaze"), (60.0, "Number 2 · The Sun"), (80.0, "Number 1 · Look Back")])
        ts = SP.titles(sc, "3 Frontier Tricks")
        self.assertEqual(len(ts), 5); self.assertTrue(all("When the Grid Goes Down" in t or "WRONG" in t for t in ts))
        self.assertTrue(ts[0].startswith("3 Forgotten Frontier Tricks"))


if __name__ == "__main__":
    unittest.main()
