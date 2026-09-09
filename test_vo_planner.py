"""Unit tests for Option 3 VO-Aware Visual Planner (no Whisper / no LLM)."""

from __future__ import annotations

import unittest

from visual_director.schema import VisualPlan, VisualScene

from vo_planner.beat_align import align_beats_to_vo
from vo_planner.bridge import merge_vo_aware_into_payload, to_visual_plan
from vo_planner.coverage import plan_coverage
from vo_planner.engine import build_vo_aware_plan, compact_handoff_json, format_plan_preview
from vo_planner.memory import VisualMemory, entry_from_unit
from vo_planner.preferences import allocation_settings_from_mix, apply_asset_mix_to_plan
from vo_planner.progression import next_distinct_stage, plan_progression
from vo_planner.qc import validate_plan
from vo_planner.quality import (
    detect_opportunity_tags,
    narrative_importance,
    quality_requirements,
    strip_generic_stock_language,
    visual_opportunity,
)
from vo_planner.schema import (
    AssetMixPreferences,
    AlignedBeat,
    CoverageUnit,
    VOAnalysis,
    VOWord,
)
from vo_planner.vo_analyzer import _detect_pauses, _split_sentences


def _words_from_script(segments, wps: float = 2.5, pause: float = 0.4):
    """Build fake whisper words with deterministic timing."""
    words = []
    t = 0.1
    dt = 1.0 / wps
    for seg in segments:
        for tok in seg.split():
            words.append((tok.lower().strip(".,!?"), t, t + dt * 0.85))
            t += dt
        t += pause
    return words


def _words_timed(phrases_with_gaps):
    """phrases_with_gaps: list of (text, pause_after)."""
    words = []
    t = 0.1
    dt = 0.35
    for text, gap in phrases_with_gaps:
        for tok in text.split():
            words.append((tok.lower().strip(".,!?"), t, t + dt * 0.85))
            t += dt
        t += gap
    return words


def _scene(i: int, narration: str, **kwargs) -> VisualScene:
    return VisualScene(
        scene_id=i,
        narration=narration,
        visual_goal=kwargs.get("visual_goal", "show the idea"),
        visual_description=kwargs.get(
            "visual_description", "specific documentary footage of the subject"
        ),
        asset_type=kwargs.get("asset_type", "stock_video"),
        provider_preference=kwargs.get("provider_preference", "stock_video"),
        search_queries=kwargs.get("search_queries", ["subject documentary"]),
        timestamp_needed=False,
        timestamp_hint="",
        duration=float(kwargs.get("duration", 3.0)),
        importance=kwargs.get("importance", "medium"),
        fallbacks=kwargs.get("fallbacks", ["stock_image"]),
        visual_treatment="",
        transition="cut",
        minimum_quality="1080p",
    )


def _vo_from_words(words, audio_duration=None) -> VOAnalysis:
    sentences = _split_sentences(words)
    duration = audio_duration if audio_duration is not None else words[-1][2]
    pauses = _detect_pauses(words, duration)
    dens = [s.speech_density for s in sentences if s.speech_density > 0]
    return VOAnalysis(
        audio_path="/tmp/test.wav",
        audio_duration=float(duration),
        words=[VOWord(w, s, e) for w, s, e in words],
        sentences=sentences,
        pauses=pauses,
        mean_speech_density=(sum(dens) / len(dens)) if dens else 0.0,
        whisper_model="test",
    )


def _beat(**kwargs) -> AlignedBeat:
    defaults = dict(
        beat_id=1,
        narration="Narration",
        start=0.0,
        end=4.0,
        align_confidence=1.0,
        visual_goal="goal",
        visual_description="specific documentary detail",
        importance="medium",
        narrative_importance=0.5,
        visual_opportunity=0.5,
        speech_density=2.0,
        idea_count=1,
        opportunity_tags=[],
        internal_pauses=[],
    )
    defaults.update(kwargs)
    return AlignedBeat(**defaults)


class TestVOSentenceSplit(unittest.TestCase):
    def test_pause_splits_sentences(self):
        words = [
            ("hello", 0.0, 0.3),
            ("world", 0.35, 0.6),
            ("this", 1.5, 1.7),
            ("continues", 1.75, 2.1),
        ]
        sentences = _split_sentences(words)
        self.assertGreaterEqual(len(sentences), 2)
        self.assertIn("hello", sentences[0].text)


class TestAlignmentAndCoverage(unittest.TestCase):
    def test_align_uses_vo_duration_not_scene_estimate(self):
        segs = [
            "Ancient forests covered the northern continent for centuries.",
            "Then factories rose beside the river and smoke filled the sky.",
            "Workers built machines that changed every street overnight.",
        ]
        words = _words_from_script(segs, wps=2.2)
        vo = _vo_from_words(words)
        scenes = [_scene(i + 1, s, duration=2.0) for i, s in enumerate(segs)]
        beats = align_beats_to_vo(scenes, vo)
        self.assertEqual(len(beats), 3)
        total = sum(b.duration for b in beats)
        self.assertGreater(total, 5.0)
        self.assertNotEqual(round(beats[0].duration, 1), 2.0)
        self.assertAlmostEqual(beats[-1].end, vo.audio_duration, delta=0.5)

    def test_coverage_fills_timeline_without_gaps(self):
        segs = [
            "Look at the vast ocean surrounding the city skyline at dawn.",
            "Scientists reveal how the mechanism actually works under pressure.",
            "The final consequence reshapes the entire coastline forever.",
        ]
        words = _words_from_script(segs, wps=2.0)
        vo = _vo_from_words(words)
        scenes = [
            _scene(1, segs[0], importance="high", visual_goal="establish ocean city"),
            _scene(2, segs[1], importance="high", visual_goal="explain mechanism"),
            _scene(3, segs[2], importance="high", visual_goal="show consequence"),
        ]
        beats = align_beats_to_vo(scenes, vo)
        units, contracts, memory, stages = plan_coverage(beats)
        self.assertEqual(len(contracts), 3)
        self.assertGreaterEqual(len(units), 3)
        issues = validate_plan(beats, units, audio_duration=vo.audio_duration)
        gap_errors = [i for i in issues if i.code == "coverage_gap" and i.severity == "error"]
        self.assertEqual(gap_errors, [])
        self.assertEqual(memory.summary()["units_recorded"], len(units))


class TestRealisticScenarios(unittest.TestCase):
    """Scenarios A–H from the Option 3 quality audit."""

    def test_A_short_simple_stays_simple(self):
        beat = _beat(
            narration="The river bends quietly toward the sea.",
            start=0.0,
            end=4.0,
            narrative_importance=0.35,
            visual_opportunity=0.4,
            speech_density=2.0,
            idea_count=1,
        )
        units, contracts, _, _ = plan_coverage([beat])
        self.assertEqual(contracts[0].required_units, 1)
        self.assertEqual(len(units), 1)
        self.assertIn(units[0].strategy, {"single_shot", "hold"})

    def test_B_long_multi_idea_gets_multiple_units(self):
        narr = (
            "The factory assembles engines on one line. "
            "Meanwhile workers inspect every seal. "
            "And then the finished motors roll toward shipping."
        )
        beat = _beat(
            narration=narr,
            start=0.0,
            end=13.5,
            narrative_importance=0.7,
            visual_opportunity=0.72,
            speech_density=2.4,
            idea_count=3,
            opportunity_tags=["dramatic_action", "important_object"],
            visual_goal="factory assembly process",
            visual_description="robotic arms assembling engine blocks on the line",
        )
        units, contracts, _, _ = plan_coverage([beat])
        self.assertGreaterEqual(contracts[0].required_units, 2)
        self.assertGreaterEqual(len(units), 2)
        for u in units:
            self.assertGreater(u.duration, 1.2)
            self.assertTrue(u.visual_purpose)
            self.assertTrue(u.subject)
            self.assertTrue(u.change_trigger)

    def test_C_pauses_create_change_opportunities(self):
        beat = _beat(
            narration="First the dam holds. Then the gates open and the valley floods.",
            start=0.0,
            end=12.0,
            narrative_importance=0.7,
            visual_opportunity=0.7,
            speech_density=2.0,
            idea_count=2,
            internal_pauses=[4.5, 8.0],
            opportunity_tags=["dramatic_action"],
        )
        units, contracts, _, _ = plan_coverage([beat])
        self.assertGreaterEqual(len(units), 2)
        triggers = [u.change_trigger for u in units]
        self.assertTrue(
            any(t == "mid_pause_shift" for t in triggers[1:])
            or any(abs(u.start - p) < 0.5 for u in units[1:] for p in beat.internal_pauses)
        )

    def test_D_repeated_subject_evolves_grammar(self):
        beats = [
            _beat(
                beat_id=i,
                narration=f"The factory line keeps moving through stage {i}.",
                start=float(i * 4),
                end=float(i * 4 + 3.8),
                visual_goal="factory line",
                visual_description="factory conveyor with engines",
                narrative_importance=0.6,
                visual_opportunity=0.6,
            )
            for i in range(1, 5)
        ]
        # Force same subject extraction path via goal/description
        units, _, memory, _ = plan_coverage(beats)
        factory_units = [u for u in units if u.subject == "factory"]
        self.assertGreaterEqual(len(factory_units), 2)
        grammars = {(u.shot_scale, u.camera, u.motion) for u in factory_units}
        self.assertGreaterEqual(len(grammars), 2, "repeated subject should evolve look")
        avoids = memory.avoid_list()
        self.assertTrue(any("subject" in a or "scale" in a or "factory" in a for a in avoids) or len(units) >= 4)

    def test_E_major_reveal_stronger_treatment(self):
        beat = _beat(
            narration="And finally the hidden truth is revealed beneath the archive documents.",
            start=0.0,
            end=7.0,
            narrative_importance=0.9,
            visual_opportunity=0.85,
            opportunity_tags=["reveal", "historical_evidence"],
            visual_goal="reveal archive truth",
            visual_description="close archival documents exposed under lamp light",
            idea_count=1,
        )
        units, _, _, stages = plan_coverage([beat])
        self.assertGreaterEqual(len(units), 2)
        self.assertTrue(any(u.strong_opportunity or "reveal" in u.visual_purpose for u in units))
        self.assertTrue(any(u.quality_requirements for u in units))
        handoff_quality = units[-1].quality_target
        self.assertIn(handoff_quality, {"must_be_specific_evidence", "prefer_specific_over_decorative"})

    def test_F_dense_narration_enough_but_not_chaotic(self):
        beat = _beat(
            narration="Rapid claims stack: borders shift, markets crash, leaders resign, cities empty.",
            start=0.0,
            end=9.5,
            narrative_importance=0.7,
            visual_opportunity=0.65,
            speech_density=3.8,
            idea_count=3,
            opportunity_tags=["dramatic_action", "important_location"],
        )
        units, _, _, _ = plan_coverage([beat])
        self.assertGreaterEqual(len(units), 2)
        self.assertLessEqual(len(units), 3)
        self.assertTrue(all(u.duration >= 1.3 for u in units))

    def test_G_low_density_allows_hold(self):
        beat = _beat(
            narration="The valley rests under slow clouds.",
            start=0.0,
            end=6.0,
            narrative_importance=0.35,
            visual_opportunity=0.4,
            speech_density=1.1,
            idea_count=1,
        )
        units, contracts, _, _ = plan_coverage([beat])
        self.assertEqual(len(units), 1)
        self.assertIn(contracts[0].strategy, {"hold", "single_shot"})

    def test_H_full_video_memory_and_callbacks(self):
        segs = [
            "Wide city skyline over the harbor at dawn.",
            "Inside the factory machines assemble the engines.",
            "Workers face the human consequence of the collapse.",
            "The city skyline returns as smoke clears after the reveal.",
        ]
        words = _words_from_script(segs, wps=2.0, pause=0.55)
        vo = _vo_from_words(words)
        scenes = [
            _scene(1, segs[0], importance="medium", visual_goal="city harbor skyline",
                   visual_description="wide harbor skyline at dawn"),
            _scene(2, segs[1], importance="high", visual_goal="factory engines",
                   visual_description="factory machines assembling engines"),
            _scene(3, segs[2], importance="high", visual_goal="workers consequence",
                   visual_description="workers facing collapse aftermath"),
            _scene(4, segs[3], importance="high", visual_goal="city skyline reveal",
                   visual_description="city skyline returning after smoke clears"),
        ]
        beats = align_beats_to_vo(scenes, vo)
        units, _, memory, stages = plan_coverage(beats)
        summary = memory.summary()
        self.assertGreaterEqual(summary["units_recorded"], 4)
        self.assertTrue(summary.get("subjects"))
        # Progression should not be all identical
        self.assertGreaterEqual(len(set(stages)), 2)
        # Coverage spans full VO
        self.assertAlmostEqual(units[0].start, beats[0].start, delta=0.2)
        self.assertAlmostEqual(units[-1].end, beats[-1].end, delta=0.35)
        issues = validate_plan(beats, units, audio_duration=vo.audio_duration)
        self.assertFalse(any(i.code == "coverage_gap" and i.severity == "error" for i in issues))


class TestProgressionMemoryOpportunity(unittest.TestCase):
    def test_progression_avoids_identical_consecutive_stages(self):
        beats = [
            _beat(beat_id=i, narration=text, start=float(i), end=float(i + 2), visual_goal=text)
            for i, text in enumerate(
                [
                    "The city skyline rises over the bay.",
                    "Another wide view of the city streets and sky.",
                    "A worker opens the machine housing.",
                ]
            )
        ]
        stages = plan_progression(beats)
        self.assertEqual(len(stages), 3)
        self.assertNotEqual(stages[0], stages[1])

    def test_next_distinct_stage(self):
        self.assertEqual(next_distinct_stage("environment", "environment"), "scale")
        self.assertEqual(next_distinct_stage("reveal", None), "reveal")

    def test_memory_flags_visual_repetition(self):
        mem = VisualMemory()
        for i in range(3):
            u = CoverageUnit(
                unit_id=f"u{i}",
                beat_id=i,
                start=float(i),
                end=float(i + 2),
                strategy="single_shot",
                visual_purpose="establish_world",
                evidence_type="establishing",
                subject="city",
                shot_scale="wide",
                camera="eye_level",
                motion="slow_pan",
                specificity=0.5,
                visual_importance=0.5,
                novelty=0.5,
                repetition_risk=0.0,
                generic_risk=0.3,
                strong_opportunity=False,
                quality_target="1080p",
                change_trigger="beat_start",
                progression_stage="environment",
                location="city",
            )
            mem.remember(entry_from_unit(u, location="city"), strategy="single_shot")
        self.assertGreaterEqual(
            mem.visual_repetition("wide", "eye_level", "slow_pan", "environment", strategy="single_shot"),
            0.5,
        )
        evolved = mem.evolve_grammar("wide", "eye_level", "slow_pan", strategy="single_shot", force=True)
        self.assertNotEqual(evolved[0], "wide")
        self.assertTrue(any("location" in a or "subject" in a for a in mem.avoid_list()))

    def test_opportunity_tags_and_quality_req(self):
        tags = detect_opportunity_tags("Finally the secret is revealed as markets crash 40 percent")
        self.assertIn("reveal", tags)
        self.assertTrue("statistic" in tags or "dramatic_action" in tags)
        scene = _scene(
            1,
            "Watch the rocket launch into the sky.",
            importance="medium",
            visual_goal="rocket launch",
            visual_description="close footage of rocket engines igniting on the launch pad",
        )
        critical = _scene(
            2,
            "This is the critical truth about the discovery.",
            importance="high",
            visual_goal="abstract idea",
            visual_description="cinematic footage of something",
        )
        self.assertGreater(narrative_importance(critical), 0.7)
        self.assertGreater(
            visual_opportunity(scene, duration=6.0),
            visual_opportunity(critical, duration=3.0),
        )
        cleaned = strip_generic_stock_language("cinematic footage of the dam gates")
        self.assertNotIn("cinematic footage", cleaned.lower())
        req = quality_requirements(
            subject="dam",
            action="open",
            evidence="process",
            motion="push_in",
            specificity=0.7,
            generic_risk=0.3,
            repetition_risk=0.2,
            strong=True,
            tags=["reveal"],
            editability="high",
        )
        self.assertTrue(req["forbid_generic_phrasing"])
        self.assertEqual(req["editability"], "high")


class TestQualityAndPrefs(unittest.TestCase):
    def test_mix_maps_to_allocation_softly(self):
        mix = AssetMixPreferences(video_pct=80, image_pct=20, flow_video_pct=30)
        settings = allocation_settings_from_mix(mix)
        self.assertEqual(settings.visual_strategy, "video_heavy")
        img = AssetMixPreferences(video_pct=20, image_pct=80)
        self.assertEqual(allocation_settings_from_mix(img).visual_strategy, "image_heavy")

    def test_flow_image_pct_assigns_flow_image_providers(self):
        """PLAN tab Flow Image % must rewrite scene providers (was ignored before)."""
        scenes = [
            _scene(i + 1, narr, importance="medium")
            for i, narr in enumerate(
                [
                    "A conceptual diagram explains the hidden mechanism.",
                    "Workers load steel containers at the busy harbor.",
                    "An abstract comparison shows two biological clocks colliding.",
                    "Ships cross the ocean under storm clouds at night.",
                    "A metaphor of social jet lag appears as misaligned schedules.",
                    "Cranes lift cargo while traffic rushes through the port.",
                    "The idea of time debt is visualized as stacked calendars.",
                    "Factories hum across the industrial skyline at dawn.",
                    "An illustration of circadian rhythm glows inside the body.",
                    "Trains roll inland carrying goods from the coast.",
                ]
            )
        ]
        plan = VisualPlan(topic="Mix", scenes=scenes)
        mix = AssetMixPreferences(
            video_pct=50,
            image_pct=50,
            stock_video_pct=80,
            flow_video_pct=20,
            youtube_video_pct=0,
            flow_image_pct=100,
            stock_image_pct=0,
        )
        out = apply_asset_mix_to_plan(plan, mix)
        flow_imgs = [s for s in out.scenes if s.provider_preference == "flow_image"]
        self.assertGreaterEqual(len(flow_imgs), 4)
        self.assertTrue(all(s.asset_type == "image" for s in flow_imgs))
        self.assertTrue(any("asset_mix_applied" in w for w in out.warnings))
        # Preferred providers appear in Claude handoff
        words = _words_from_script([s.narration for s in out.scenes])
        vo = _vo_from_words(words)
        vo_plan = build_vo_aware_plan(
            "\n".join(s.narration for s in out.scenes),
            "/tmp/test.wav",
            semantic_plan=out,
            vo=vo,
            asset_mix=mix,
        )
        handoff = vo_plan.compact_handoff()
        prefs = [b.get("pref") for b in handoff["beats"]]
        self.assertIn("flow_image", prefs)
        self.assertEqual(handoff["mix"]["flow_image_pct"], 100.0)


class TestBridgeAndEngine(unittest.TestCase):
    def test_build_plan_and_compact_handoff(self):
        segs = [
            "Mountains surround the valley at sunrise.",
            "Engineers explain how the dam mechanism holds the flood.",
            "The reveal shows what happens when the gates finally open.",
        ]
        words = _words_from_script(segs)
        vo = _vo_from_words(words)
        scenes = [_scene(i + 1, s, importance="high") for i, s in enumerate(segs)]
        semantic = VisualPlan(topic="Test", scenes=scenes)
        vo_plan = build_vo_aware_plan(
            "\n".join(segs),
            "/tmp/test.wav",
            semantic_plan=semantic,
            vo=vo,
        )
        visual = to_visual_plan(vo_plan, source_scenes=scenes)
        self.assertEqual(len(visual.scenes), 3)
        for scene in visual.scenes:
            self.assertGreater(scene.duration, 1.5)
            self.assertNotIn("cinematic footage of", (scene.visual_description or "").lower())
        handoff = vo_plan.compact_handoff()
        self.assertEqual(handoff["planner"], "vo_aware")
        self.assertTrue(handoff["mix"]["targets_only"])
        self.assertTrue(handoff["mix"]["quality_protection"])
        self.assertIn("shown", handoff)
        self.assertIn("req", handoff["units"][0])
        self.assertIn("what", handoff["units"][0])
        payload = merge_vo_aware_into_payload(visual, visual.to_dict())
        self.assertEqual(payload.get("planner"), "vo_aware")
        preview = format_plan_preview(vo_plan)
        self.assertIn("Claude Visual Production Plan", preview)
        raw = compact_handoff_json(vo_plan)
        self.assertIn('"planner": "vo_aware"', raw)

    def test_build_vo_aware_plan_signature(self):
        segs = ["The ocean city skyline glows at night."]
        words = _words_from_script(segs)
        vo = _vo_from_words(words)
        scenes = [_scene(1, segs[0])]
        plan = build_vo_aware_plan(
            segs[0],
            "/tmp/x.wav",
            semantic_plan=VisualPlan(topic="t", scenes=scenes),
            vo=vo,
        )
        self.assertGreaterEqual(len(plan.units), 1)


class TestClaudeWorkflowAndLongVO(unittest.TestCase):
    """Simplified Option 3 workflow + long-VO robustness."""

    def test_stage_errors_for_missing_inputs(self):
        from vo_planner import VoPlannerStageError, plan_from_voiceover

        with self.assertRaises(VoPlannerStageError) as ctx:
            plan_from_voiceover("", "/tmp/missing.wav")
        self.assertEqual(ctx.exception.stage, "script_validation")

        with self.assertRaises(VoPlannerStageError) as ctx2:
            plan_from_voiceover("Hello world narration here.", "/tmp/does_not_exist_vo.wav")
        self.assertEqual(ctx2.exception.stage, "voiceover_validation")

    def test_twenty_minute_equivalent_many_beats(self):
        # ~20 min VO as many aligned beats (no Whisper) — planner must scale.
        n = 120  # ~10s average → 20 minutes
        beats = []
        t = 0.0
        for i in range(1, n + 1):
            dur = 10.0
            beats.append(
                _beat(
                    beat_id=i,
                    narration=f"Beat {i} covers the factory and the city skyline consequence.",
                    start=t,
                    end=t + dur,
                    narrative_importance=0.55 + (0.05 if i % 17 == 0 else 0),
                    visual_opportunity=0.55 + (0.2 if i % 23 == 0 else 0),
                    speech_density=2.2,
                    idea_count=1 + (i % 3 == 0),
                    visual_goal="factory city skyline" if i % 2 == 0 else "harbor workers",
                    opportunity_tags=["reveal"] if i % 40 == 0 else [],
                )
            )
            t += dur
        self.assertAlmostEqual(t, 1200.0, delta=0.1)
        units, contracts, memory, stages = plan_coverage(beats)
        self.assertEqual(len(contracts), n)
        self.assertGreaterEqual(len(units), n)
        self.assertEqual(memory.summary()["units_recorded"], len(units))
        self.assertEqual(len(stages), n)
        # No unexplained gaps across full duration
        issues = validate_plan(beats, units, audio_duration=t)
        self.assertFalse(any(i.code == "coverage_gap" and i.severity == "error" for i in issues))
        # Preview stays compact even for long plans
        from vo_planner.schema import VoAwarePlan, AssetMixPreferences

        vo_plan = VoAwarePlan(
            topic="Long",
            planner_version=2,
            audio_duration=t,
            beats=beats,
            units=units,
            contracts=contracts,
            memory_summary=memory.summary(),
            progression=stages,
            qc_issues=issues,
            asset_mix=AssetMixPreferences(),
            vo_summary={"sentence_count": n, "mean_speech_density": 2.2},
        )
        preview = format_plan_preview(vo_plan)
        self.assertIn("Claude Visual Production Plan", preview)
        self.assertLess(len(preview), 8000)
        handoff = vo_plan.compact_handoff()
        self.assertEqual(len(handoff["beats"]), n)
        self.assertNotIn("whisper_words", handoff)

    def test_cached_plan_reuse(self):
        import tempfile
        from pathlib import Path
        from vo_planner.cache import plan_cache_key, save_cached_plan, load_cached_plan
        from vo_planner.schema import AssetMixPreferences

        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            audio = state / "vo.wav"
            audio.write_bytes(b"RIFF....")
            mix = AssetMixPreferences()
            key = plan_cache_key("script text here", audio, mix=mix, whisper_model="base")
            save_cached_plan(
                state,
                key,
                {
                    "compact": {
                        "planner": "vo_aware",
                        "v": 2,
                        "topic": "Cached",
                        "audio_s": 12.0,
                        "beats": [{"id": 1, "t": [0, 12], "dur": 12, "narr": "Hello", "goal": "g"}],
                        "units": [
                            {
                                "id": "b1_u0",
                                "beat": 1,
                                "t": [0, 12],
                                "dur": 12,
                                "strat": "single_shot",
                                "what": "harbor",
                                "why": "establish_world",
                                "scale": "wide",
                                "cam": "eye_level",
                                "motion": "slow_pan",
                                "stage": "environment",
                            }
                        ],
                        "qc": [],
                        "progression": ["environment"],
                        "memory": {"units_recorded": 1},
                        "mix": mix.to_dict(),
                    },
                    "visual_plan": {
                        "topic": "Cached",
                        "warnings": [],
                        "scenes": [
                            {
                                "scene_id": 1,
                                "narration": "Hello",
                                "visual_goal": "g",
                                "visual_description": "d",
                                "asset_type": "stock_video",
                                "provider_preference": "stock_video",
                                "search_queries": ["harbor"],
                                "timestamp_needed": False,
                                "timestamp_hint": "",
                                "duration": 12.0,
                                "importance": "medium",
                                "fallbacks": [],
                                "visual_treatment": "",
                                "transition": "cut",
                                "minimum_quality": "1080p",
                            }
                        ],
                    },
                },
            )
            loaded = load_cached_plan(state, key)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["compact"]["topic"], "Cached")

    def test_preview_title_and_handoff_are_claude_facing(self):
        beat = _beat(end=5.0)
        units, contracts, memory, stages = plan_coverage([beat])
        from vo_planner.schema import VoAwarePlan, AssetMixPreferences

        plan = VoAwarePlan(
            topic="Demo",
            planner_version=2,
            audio_duration=5.0,
            beats=[beat],
            units=units,
            contracts=contracts,
            memory_summary=memory.summary(),
            progression=stages,
            qc_issues=[],
            asset_mix=AssetMixPreferences(),
            vo_summary={},
        )
        self.assertIn("Claude Visual Production Plan", format_plan_preview(plan))
        self.assertIn("what", plan.compact_handoff()["units"][0])


if __name__ == "__main__":
    unittest.main()
