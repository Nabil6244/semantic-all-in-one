"""Semantic Intelligence Engine: deterministic ambience (English + Hindi), AI only for conflicts, SFX events, offline operation."""
import tempfile, unittest
from pathlib import Path

import smart_editing as se
from semantic_intel import ambience as A, sfx as S, lexicon as L, core

FREE = {"ai_planning": "auto"}   # no key: the AI can never be asked


def make_catalog(entries):
    root = Path(tempfile.mkdtemp())
    out = []
    for e in entries:
        (root / e["file"]).parent.mkdir(parents=True, exist_ok=True); (root / e["file"]).write_bytes(b"x")
        out.append(se.SfxEntry.from_dict(e))
    return se.SfxCatalog(root, out)


AMB = [{"id": f"amb_{p}", "file": f"ambience/amb_{p}.opus", "category": "ambience", "tags": list(se._AMBIENCE_PROFILES[p]), "duration": 60.0}
       for p in se._AMBIENCE_PROFILES if p != "none"]


def scenes(items):
    rows = [{"scene_number": str(i + 1), "script_segment": t, "prompt": p} for i, (t, p) in enumerate(items)]
    return rows, [dict(r, start_time=i * 5.0, end_time=i * 5.0 + 5.0) for i, r in enumerate(rows)]


def profiles(items, **kw):
    rows, aligned = scenes(items)
    out, rep = A.plan_profiles(rows, aligned, settings=kw.pop("settings", FREE), catalog=kw.pop("catalog", make_catalog(AMB)), **kw)
    return [o["profile"] for o in out], out, rep


class AmbienceRelevance(unittest.TestCase):
    def test_environment_from_narration_and_picture_english_and_hindi(self):
        got, *_ = profiles([
            ("Rain hammered the windows all night.", "a harbor town under storm clouds"),
            ("समुद्र की लहरें किनारे से टकराईं।", "waves breaking on a rocky shore"),
            ("ट्रेन स्टेशन पर रुकी।", "a steam train beside a platform"),
            ("The stadium roared.", "a packed stadium crowd with raised arms"),
            ("उन्होंने जंगल पार किया।", "a dense forest at dawn"),
            ("Engineers watched the servers.", "a server room with blinking racks"),
        ])
        self.assertEqual(got, ["rain", "water", "transport", "crowd", "nature", "technology"])

    def test_abstract_narration_stays_on_the_quiet_room_bed(self):
        got, *_ = profiles([("He believed it would change everything.", "a man at a window"), ("और फिर सब कुछ बदल गया।", "an empty chair")])
        self.assertEqual(got, ["room", "room"])

    def test_bed_continues_then_fades_to_room(self):
        got, *_ = profiles([("They crossed the forest.", "deep forest")] + [("He thought about it.", "a thinker")] * 5)
        self.assertEqual(got[:3], ["nature"] * 3)   # kept for HOLD scenes without evidence
        self.assertEqual(got[-1], "room")           # then the quiet bed takes over

    def test_picture_outweighs_a_figure_of_speech(self):
        got, *_ = profiles([("The city never sleeps, he wrote.", "a quiet library reading room with long desks")])
        self.assertEqual(got, ["room"])

    def test_no_flapping_on_weak_evidence(self):
        got, *_ = profiles([("Ocean waves rolled in.", "a beach"), ("It was a quiet moment.", "a seagull"), ("The machine hummed.", "a gear")])
        self.assertEqual(got[0], "water"); self.assertEqual(got[1], "water")   # one weak scene does not switch the bed

    def test_unavailable_profiles_are_never_chosen(self):
        only = make_catalog([e for e in AMB if e["id"] in ("amb_room", "amb_city")])
        got, *_ = profiles([("Ocean waves rolled in.", "a beach")], catalog=only)
        self.assertEqual(got, ["room"])

    def test_deterministic(self):
        items = [("Rain on the city streets.", "wet street"), ("Silence.", "")] * 5
        self.assertEqual(profiles(items)[0], profiles(items)[0])

    def test_missing_prompt_uses_narration_fully(self):
        got, *_ = profiles([("Cars rush through wet city streets.", ""), ("Rocket engines ignite at the launch pad.", "")])
        self.assertEqual(got, ["city", "technology"])


class FakeLLM:
    def __init__(self, answers=None, fail=False):
        self.calls, self.answers, self.fail = [], answers or {}, fail

    def complete(self, system, user, **kw):
        import json
        if self.fail:
            raise RuntimeError("rate limit")
        ids = [l.split(":")[0].replace("scene ", "") for l in user.splitlines() if l.startswith("scene ")]
        self.calls.append(ids)
        return json.dumps({"scenes": [{"scene_number": i, "profile": self.answers.get(i, "room")} for i in ids]})


CONFLICT = [("The ocean and the city met here.", "a harbor city skyline over the sea")]   # water vs city: named about equally


class AmbienceAI(unittest.TestCase):
    def ask(self, llm, settings, items=None, cache=None):
        rows, aligned = scenes(items or CONFLICT + [("Quiet.", "")])
        return A.plan_profiles(rows, aligned, settings=settings, catalog=make_catalog(AMB), cache_dir=cache, llm_factory=lambda: llm, sleep=lambda s: None)

    def test_ai_asked_only_about_the_conflict_and_cached(self):
        d = Path(tempfile.mkdtemp()); llm = FakeLLM({"1": "water"})
        out, rep = self.ask(llm, {"ai_planning": "auto"}, cache=d)
        self.assertEqual(llm.calls, [["1"]]); self.assertEqual(out[0]["profile"], "water"); self.assertEqual(out[0]["source"], "ai")
        llm2 = FakeLLM(); out2, rep2 = self.ask(llm2, {"ai_planning": "auto"}, cache=d)
        self.assertEqual(llm2.calls, []); self.assertEqual(out2[0]["profile"], "water"); self.assertEqual(out2[0]["provenance"], "cache")

    def test_an_unrelated_ai_answer_cannot_override_the_picture(self):
        out, _ = self.ask(FakeLLM({"1": "traffic"}), {"ai_planning": "auto"})
        self.assertIn(out[0]["profile"], ("water", "city")); self.assertEqual(out[0]["provenance"], "rules")

    def test_full_mode_asks_about_every_scene_and_takes_the_answer(self):
        llm = FakeLLM({"1": "traffic", "2": "atmospheric"})
        out, _ = self.ask(llm, {"ai_planning": "full"})
        self.assertEqual(sorted(llm.calls[0]), ["1", "2"]); self.assertEqual([o["profile"] for o in out], ["traffic", "atmospheric"])

    def test_a_failing_ai_falls_back_to_the_rules(self):
        out, rep = self.ask(FakeLLM(fail=True), {"ai_planning": "auto"})
        self.assertEqual(rep["failed"], 1); self.assertIn(out[0]["profile"], ("water", "city"))

    def test_off_never_asks(self):
        llm = FakeLLM(); out, _ = self.ask(llm, {"ai_planning": "off"}); self.assertEqual(llm.calls, [])

    def test_no_key_never_asks_and_still_plans(self):
        import os
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            rows, aligned = scenes(CONFLICT)
            out, rep = A.plan_profiles(rows, aligned, settings={}, catalog=make_catalog(AMB))
            self.assertEqual(rep["asked"], 0); self.assertEqual(len(out), 1)
        finally:
            if old: os.environ["GEMINI_API_KEY"] = old

    def test_plan_scene_ambience_end_to_end_offline(self):
        rows, aligned = scenes([("Rain on the glass.", "rainy window"), ("A crowd gathered.", "crowd in a square")])
        s = se.SmartEditingSettings(scene_ambience=True, sound_effects=False)
        beds = se.plan_scene_ambience(rows, aligned, s, catalog=make_catalog(AMB), gemini_settings={}, audio_end=10.0)
        self.assertEqual([b["profile"] for b in beds], ["rain", "crowd"])


class EditorialHints(unittest.TestCase):
    class Plan:
        def __init__(self, m): self.m = m
        def ambience_profile_map(self): return self.m

    def test_builder_default_does_not_override_but_a_deliberate_hint_does(self):
        # "cards" contains "car" and the editorial builder's substring check calls that traffic; that is a default, not a decision
        rows, aligned = scenes([("Ten small paper cards lay in a row.", "cards on a table"), ("A quiet moment.", "a chair")])
        base = [{"scene_number": "1", "profile": "room", "source": "heuristic"}, {"scene_number": "2", "profile": "room", "source": "heuristic"}]
        out = se._apply_editorial_ambience_hints(base, self.Plan({"1": "traffic", "2": "fire"}), rows, aligned)
        self.assertEqual([p["profile"] for p in out], ["room", "fire"])
        self.assertEqual(out[1]["source"], "editorial")


SFX_LIB = [
    {"id": "impact_a", "file": "impact/a.wav", "category": "impact", "tags": ["impact", "boom"], "duration": 1.2},
    {"id": "impact_b", "file": "impact/b.wav", "category": "impact", "tags": ["impact", "heavy"], "duration": 0.9},
    {"id": "mech_a", "file": "impact/m.wav", "category": "impact", "tags": ["machinery", "mechanical"], "duration": 1.5},
    {"id": "click_a", "file": "technology/c.wav", "category": "technology", "tags": ["mechanical_click"], "duration": 0.3},
]


class SfxEvents(unittest.TestCase):
    def plan(self, items, lib=SFX_LIB, existing=()):
        rows, aligned = scenes(items)
        return S.plan_event_sfx(aligned, make_catalog(lib), existing=existing)

    def test_events_are_found_in_english_and_hindi_and_not_in_abstract_lines(self):
        self.assertEqual(S.detect_events("The bridge collapsed with a huge explosion.", "")[0]["event"], "impact")
        self.assertEqual(S.detect_events("वहाँ एक ज़ोरदार धमाका हुआ।", "")[0]["event"], "impact")
        self.assertEqual(S.detect_events("He believed machines would think one day.", "a man at a desk"), [])

    def test_sound_matches_event_and_sits_where_the_word_is(self):
        ev = self.plan([("Nothing happened for a long while, and then the explosion shook the whole valley.", "")])
        self.assertEqual(len(ev), 1); self.assertIn(ev[0]["sfx_id"], ("impact_a", "impact_b"))
        self.assertGreater(ev[0]["start"], 2.0)   # late in a 5 s scene: where "explosion" is in the sentence

    def test_no_library_match_means_no_sound(self):
        self.assertEqual(self.plan([("The factory engine roared.", "")], lib=[SFX_LIB[0]]), [])   # machinery has no entry
        self.assertEqual(self.plan([("Footsteps echoed down the hall and the door creaked open.", "")]), [])   # no footsteps/doors in the library

    def test_spacing_density_and_one_per_scene(self):
        items = [("A huge explosion and a crash.", "")] * 12   # 5 s scenes: far more events than allowed
        ev = self.plan(items)
        starts = sorted(e["start"] for e in ev)
        self.assertTrue(all(b - a >= S.MIN_GAP_S for a, b in zip(starts, starts[1:])))
        self.assertEqual(len({e["scene_number"] for e in ev}), len(ev))
        self.assertLessEqual(len(ev), 4)   # 60 s of video

    def test_clear_of_other_effects(self):
        rows, aligned = scenes([("The explosion rang out.", "")])
        ev = S.plan_event_sfx(aligned, make_catalog(SFX_LIB), existing=[{"start": 1.2}])
        self.assertTrue(all(abs(e["start"] - 1.2) >= S.CLEAR_S - 1e-6 for e in ev))

    def test_levels_stay_under_the_narration(self):
        ev = self.plan([("The explosion rang out across the valley.", "")])
        self.assertTrue(0 < ev[0]["volume"] <= 0.32 * se.SFX_GAIN)

    def test_deterministic(self):
        items = [("A crash.", ""), ("Nothing.", ""), ("An explosion.", "")] * 3
        self.assertEqual(self.plan(items), self.plan(items))

    def test_plan_sfx_events_gets_event_sound_and_no_extra_total(self):
        lib = SFX_LIB + [{"id": "beat_x", "file": "cinematic/x.wav", "category": "cinematic", "tags": ["sfx"], "duration": 0.8},
                         {"id": "whoosh_x", "file": "whoosh/w.wav", "category": "whoosh", "tags": ["whoosh", "movement"], "duration": 1.0}]
        cat = make_catalog(lib)
        rows, aligned = scenes([("A huge explosion shook the valley.", "")] + [("He thought about it for a while.", "")] * 9)
        s = se.SmartEditingSettings(sound_effects=True, text_effects=False, visual_transitions=False)
        events = se.plan_sfx_events(aligned, [], s, catalog=cat)
        self.assertTrue(any(e.get("event") == "impact" for e in events))
        import semantic_intel.sfx as sem
        real = sem.plan_event_sfx
        sem.plan_event_sfx = lambda *a, **k: []
        try:
            without = se.plan_sfx_events(aligned, [], s, catalog=cat)
        finally:
            sem.plan_event_sfx = real
        generic = [e for e in events if e.get("event") is None]
        self.assertLessEqual(len(generic), len(without))   # event sounds only ever take the place of generic accents, never add to them


if __name__ == "__main__":
    unittest.main()
