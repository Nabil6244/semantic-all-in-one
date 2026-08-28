#!/usr/bin/env python3
"""Unit tests for the AI Visual Director — mocked LLM, no live providers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from asset_manager import AssetManager
from providers.base import AssetSource, SceneRow
from providers.router import SceneAssetRouter
from test_asset_pipeline import FakeProvider
from visual_director import SYSTEM_PROMPT, VisualDirector, parse_visual_plan
from visual_director.llm import StaticLLM
from visual_director.schema import VisualPlanError, assert_pipeline_compatible

EXAMPLE_SCRIPT = """Your brain was never designed for a nine-to-five.

Every morning the alarm rings and we force ourselves into a schedule that fights our biology.

Scientists call this social jet lag: the gap between when your body wants to sleep and when society demands you wake up.

Look at a night-shift nurse leaving the hospital at sunrise. Her circadian clock is still in the dark.

The answer is not more coffee. Treat sleep like the biological process it actually is.
"""

VALID_PLAN = {
    "topic": "Social jet lag and modern sleep",
    "scenes": [
        {
            "scene_id": 1,
            "narration": "Your brain was never designed for a nine-to-five.",
            "visual_goal": "Hook: industrial time colliding with a tired human.",
            "visual_description": "Close-up of a harsh digital alarm clock at 6:00 AM beside a person reluctantly sitting up in bed.",
            "asset_type": "stock_video",
            "provider_preference": "stock_video",
            "search_queries": [
                "person waking exhausted to alarm clock morning",
                "hand slamming digital alarm clock in bed",
            ],
            "timestamp_needed": False,
            "duration": 2.5,
            "importance": "high",
            "fallbacks": ["flow_image"],
            "visual_treatment": "quick cut-in",
            "transition": "cut",
        },
        {
            "scene_id": 2,
            "narration": "Every morning the alarm rings and we force ourselves into a schedule that fights our biology.",
            "visual_goal": "Show the grind of an imposed work schedule.",
            "visual_description": "Office workers commuting on a packed train at dawn, fluorescent lights, blank faces.",
            "asset_type": "stock_video",
            "provider_preference": "stock_video",
            "search_queries": ["crowded commuter train early morning tired workers"],
            "timestamp_needed": False,
            "duration": 4.0,
            "importance": "medium",
            "fallbacks": ["stock_image", "flow_image"],
            "visual_treatment": "slow pan",
            "transition": "cut",
        },
        {
            "scene_id": 3,
            "narration": "Scientists call this social jet lag: the gap between when your body wants to sleep and when society demands you wake up.",
            "visual_goal": "Make an abstract circadian mismatch visible.",
            "visual_description": "A split conceptual image: a glowing body clock on one side, a rigid calendar and office tower on the other, offset from each other.",
            "asset_type": "image",
            "provider_preference": "flow_image",
            "search_queries": [],
            "timestamp_needed": False,
            "duration": 2.5,
            "importance": "high",
            "fallbacks": ["stock_image"],
            "visual_treatment": "static",
            "transition": "dissolve",
        },
        {
            "scene_id": 4,
            "narration": "Look at a night-shift nurse leaving the hospital at sunrise. Her circadian clock is still in the dark.",
            "visual_goal": "Authentic real-world example of inverted sleep.",
            "visual_description": "A nurse in scrubs walking out of a hospital entrance at sunrise, exhausted, sky turning light.",
            "asset_type": "youtube_video",
            "provider_preference": "youtube",
            "search_queries": [
                "night shift nurse leaving hospital at sunrise",
                "hospital worker walking outside dawn scrubs",
                "night shift nurse hospital exit",
            ],
            "timestamp_needed": True,
            "timestamp_hint": "nurse or hospital staff exiting into morning light after a night shift",
            "duration": 3.0,
            "importance": "high",
            "fallbacks": ["stock_video", "flow_image"],
            "visual_treatment": "subtle push-in",
            "transition": "cut",
        },
        {
            "scene_id": 5,
            "narration": "The answer is not more coffee. Treat sleep like the biological process it actually is.",
            "visual_goal": "Close on recovery, not caffeine.",
            "visual_description": "A quiet bedroom at night, phone face-down on the nightstand, person actually asleep, slow breathing implied.",
            "asset_type": "stock_video",
            "provider_preference": "stock_video",
            "search_queries": ["person sleeping peacefully dark bedroom phone on nightstand"],
            "timestamp_needed": False,
            "duration": 3.5,
            "importance": "medium",
            "fallbacks": ["flow_image"],
            "visual_treatment": "slow push-in",
            "transition": "fade",
        },
    ],
}


class TestVisualPlanParsing(unittest.TestCase):
    def test_valid_plan_parses(self):
        plan = parse_visual_plan(VALID_PLAN)
        self.assertEqual(len(plan.scenes), 5)
        self.assertEqual(plan.scenes[0].duration, 2.5)
        self.assertEqual(plan.scenes[0].minimum_quality, "1080p")
        self.assertEqual(plan.scenes[3].asset_type, "youtube_video")
        self.assertTrue(plan.scenes[3].timestamp_needed)
        self.assertEqual(plan.scenes[2].provider_preference, "flow_image")
        self.assertEqual(plan.scenes[2].asset_type, "image")

    def test_json_string_and_fences(self):
        wrapped = "Here you go:\n```json\n" + json.dumps(VALID_PLAN) + "\n```"
        plan = parse_visual_plan(wrapped)
        self.assertEqual(plan.topic, "Social jet lag and modern sleep")

    def test_malformed_response(self):
        with self.assertRaises(VisualPlanError):
            parse_visual_plan("sorry, I cannot")

    def test_missing_required_fields(self):
        payload = {
            "topic": "x",
            "scenes": [
                {"scene_id": 1, "narration": "a", "visual_goal": "g", "visual_description": "d"},
                {"scene_id": 2, "narration": "b", "visual_goal": "g", "visual_description": "d",
                 "provider_preference": "stock_video", "search_queries": ["q"], "duration": 3},
            ],
        }
        with self.assertRaises(VisualPlanError) as ctx:
            parse_visual_plan(payload)
        self.assertIn("missing required field", str(ctx.exception))

    def test_invalid_asset_type(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"][0]["provider_preference"] = "tiktok"
        with self.assertRaises(VisualPlanError) as ctx:
            parse_visual_plan(payload)
        self.assertIn("invalid asset type", str(ctx.exception))

    def test_duration_validation(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"][0]["duration"] = 90
        plan = parse_visual_plan(payload)
        self.assertEqual(plan.scenes[0].duration, 6.0)

    def test_provider_duration_hard_caps(self):
        cases = [
            (0, "stock_video", 6.1),
            (2, "flow_image", 3.1),
            (3, "youtube", 3.1),
        ]
        for index, provider, duration in cases:
            payload = json.loads(json.dumps(VALID_PLAN))
            payload["scenes"][index]["provider_preference"] = provider
            if provider == "flow_image":
                payload["scenes"][index]["asset_type"] = "image"
                payload["scenes"][index]["search_queries"] = []
            payload["scenes"][index]["duration"] = duration
            plan = parse_visual_plan(payload)
            cap = {0: 6.0, 2: 3.0, 3: 3.0}[index]
            self.assertEqual(plan.scenes[index].duration, cap, msg=provider)

        stock_image = json.loads(json.dumps(VALID_PLAN))
        stock_image["scenes"][0]["provider_preference"] = "stock_image"
        stock_image["scenes"][0]["asset_type"] = "stock_image"
        stock_image["scenes"][0]["duration"] = 3.5
        plan = parse_visual_plan(stock_image)
        self.assertEqual(plan.scenes[0].duration, 3.0)

        flow_video = json.loads(json.dumps(VALID_PLAN))
        flow_video["scenes"][0]["provider_preference"] = "flow_video"
        flow_video["scenes"][0]["asset_type"] = "video"
        flow_video["scenes"][0]["search_queries"] = []
        flow_video["scenes"][0]["duration"] = 6.1
        plan = parse_visual_plan(flow_video)
        self.assertEqual(plan.scenes[0].duration, 6.0)

        for provider in ("archive", "nasa"):
            doc = json.loads(json.dumps(VALID_PLAN))
            doc["scenes"][3]["provider_preference"] = provider
            doc["scenes"][3].pop("asset_type", None)
            doc["scenes"][3]["duration"] = 3.5
            plan = parse_visual_plan(doc)
            self.assertEqual(plan.scenes[3].duration, 3.0, msg=provider)

        ok = json.loads(json.dumps(VALID_PLAN))
        ok["scenes"][2]["duration"] = 3.0
        ok["scenes"][3]["duration"] = 3.0
        ok["scenes"][0]["duration"] = 6.0
        parse_visual_plan(ok)

    def test_local_provider_remapped_to_stock(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"] = payload["scenes"][:2]
        payload["scenes"][0]["asset_type"] = "local"
        payload["scenes"][0]["provider_preference"] = "local"
        payload["scenes"][0]["search_queries"] = []
        plan = parse_visual_plan(payload)
        self.assertEqual(plan.scenes[0].asset_type, "stock_video")
        self.assertEqual(plan.scenes[0].provider_preference, "stock_video")
        self.assertTrue(plan.scenes[0].search_queries)

    def test_legacy_flow_provider_matches_video_asset_type(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"][0]["provider_preference"] = "flow"
        payload["scenes"][0]["asset_type"] = "video"
        payload["scenes"][0]["search_queries"] = []
        plan = parse_visual_plan(payload)
        self.assertEqual(plan.scenes[0].asset_type, "video")
        self.assertEqual(plan.scenes[0].provider_preference, "flow_video")

    def test_scene_ordering_renumbers_gaps(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"] = payload["scenes"][:2]
        payload["scenes"][0]["scene_id"] = 4
        payload["scenes"][1]["scene_id"] = 9
        plan = parse_visual_plan(payload)
        self.assertEqual([s.scene_id for s in plan.scenes], [1, 2])

    def test_duplicate_scene_ids_rejected(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"] = payload["scenes"][:2]
        payload["scenes"][0]["scene_id"] = 1
        payload["scenes"][1]["scene_id"] = 1
        with self.assertRaises(VisualPlanError):
            parse_visual_plan(payload)

    def test_search_query_required_for_youtube(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"][3]["search_queries"] = []
        payload["scenes"][3].pop("search_query", None)
        with self.assertRaises(VisualPlanError) as ctx:
            parse_visual_plan(payload)
        self.assertIn("search query", str(ctx.exception))

    def test_youtube_requires_multiple_distinct_queries(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"][3]["search_queries"] = [
            "night shift nurse hospital sunrise",
            "night shift nurse hospital sunrise",
        ]
        with self.assertRaises(VisualPlanError) as ctx:
            parse_visual_plan(payload)
        msg = str(ctx.exception).lower()
        self.assertTrue("distinct" in msg or "at least 2" in msg, msg)

    def test_archive_and_nasa_providers_parse_and_route(self):
        payload = {
            "topic": "Apollo and Pluto",
            "scenes": [
                {
                    "scene_id": 1,
                    "narration": "Apollo 11 lifted off in July 1969.",
                    "visual_goal": "Show the historic Saturn V launch.",
                    "visual_description": "Saturn V rocket clearing the tower with flame and smoke.",
                    "provider_preference": "archive",
                    "search_queries": [
                        "apollo 11 launch 1969",
                        "saturn v liftoff moon mission",
                    ],
                    "duration": 3.0,
                    "importance": "high",
                    "fallbacks": ["youtube", "flow_video"],
                    "visual_treatment": "static",
                    "transition": "cut",
                },
                {
                    "scene_id": 2,
                    "narration": "New Horizons revealed Pluto's heart-shaped region.",
                    "visual_goal": "Show NASA flyby imagery.",
                    "visual_description": "Pluto's pale heart-shaped Tombaugh Regio from space.",
                    "provider_preference": "nasa",
                    "search_queries": [
                        "new horizons pluto flyby",
                        "pluto heart tombaugh regio nasa",
                    ],
                    "duration": 2.5,
                    "importance": "high",
                    "fallbacks": ["archive", "flow_video"],
                    "visual_treatment": "static",
                    "transition": "cut",
                },
            ],
        }
        plan = parse_visual_plan(payload)
        self.assertEqual(plan.scenes[0].asset_type, "archive_video")
        self.assertEqual(plan.scenes[1].asset_type, "nasa_video")
        rows = plan.to_scene_rows()
        self.assertEqual(SceneAssetRouter.classify(rows[0]), AssetSource.ARCHIVE_VIDEO)
        self.assertEqual(SceneAssetRouter.classify(rows[1]), AssetSource.NASA_VIDEO)
        csv_rows = plan.to_csv_dicts()
        self.assertIn(" || ", csv_rows[0]["prompt"])
        self.assertEqual(csv_rows[0]["asset_type"], "archive_video")

    def test_duration_caps_still_apply_to_youtube(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"][3]["duration"] = 3.0
        parse_visual_plan(payload)
        payload["scenes"][3]["duration"] = 3.1
        plan = parse_visual_plan(payload)
        self.assertEqual(plan.scenes[3].duration, 3.0)

    def test_generic_query_and_unjustified_youtube_warn(self):
        payload = {
            "topic": "t",
            "scenes": [
                {
                    "scene_id": 1,
                    "narration": "They wake up tired.",
                    "visual_goal": "Show fatigue.",
                    "visual_description": "A tired person.",
                    "provider_preference": "stock_video",
                    "search_queries": ["tired person"],
                    "duration": 3.0,
                    "importance": "low",
                    "fallbacks": ["flow_image"],
                    "visual_treatment": "static",
                    "transition": "cut",
                },
                {
                    "scene_id": 2,
                    "narration": "This is called social jet lag.",
                    "visual_goal": "Name the concept.",
                    "visual_description": "People looking tired at desks.",
                    "provider_preference": "youtube",
                    "search_queries": ["people waking up tired morning", "morning commute tired workers"],
                    "timestamp_needed": False,
                    "duration": 3.0,
                    "importance": "high",
                    "fallbacks": ["stock_video"],
                    "visual_treatment": "static",
                    "transition": "cut",
                },
            ],
        }
        plan = parse_visual_plan(payload)
        blob = " ".join(plan.warnings)
        self.assertIn("generic search query", blob)
        self.assertIn("YouTube used without a unique", blob)
        self.assertIn("social jet lag", blob)

        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"] = payload["scenes"][:2]
        desc = "A person checking a smartphone in bed looking at notifications"
        payload["scenes"][0]["visual_description"] = desc
        payload["scenes"][1]["visual_description"] = desc
        payload["scenes"][0]["search_queries"] = ["person checking smartphone in bed"]
        payload["scenes"][1]["search_queries"] = ["person checking smartphone in bed"]
        plan = parse_visual_plan(payload)
        self.assertTrue(any("duplicate search query" in w for w in plan.warnings))
        self.assertTrue(any("repetitive visuals" in w for w in plan.warnings))

    def test_fallback_chain_maps_to_existing_asset_types(self):
        plan = parse_visual_plan(VALID_PLAN)
        yt = plan.scenes[3]
        self.assertEqual(yt.provider_chain(), ["youtube", "stock_video", "flow_image"])
        primary = yt.scene_row_at(0)
        stock = yt.scene_row_at(1)
        flow = yt.scene_row_at(2)
        self.assertEqual(primary.asset_type, "youtube_video")
        self.assertEqual(SceneAssetRouter.classify(primary), AssetSource.YOUTUBE_VIDEO)
        self.assertEqual(stock.asset_type, "stock_video")
        self.assertEqual(SceneAssetRouter.classify(stock), AssetSource.STOCK_VIDEO)
        self.assertEqual(flow.asset_type, "image")
        self.assertEqual(SceneAssetRouter.classify(flow), AssetSource.FLOW_IMAGE)

    def test_to_scene_rows_match_existing_csv_shape(self):
        plan = parse_visual_plan(VALID_PLAN)
        rows = plan.to_scene_rows()
        self.assertEqual(rows[0].asset_type, "stock_video")
        self.assertEqual(rows[0].stock, "person waking exhausted to alarm clock morning")
        self.assertEqual(rows[2].asset_type, "image")
        self.assertIn("split conceptual image", rows[2].prompt)
        self.assertEqual(rows[3].asset_type, "youtube_video")
        self.assertEqual(rows[3].prompt, "night shift nurse leaving hospital at sunrise")
        self.assertEqual(rows[3].script_segment, plan.scenes[3].narration)


class TestVisualDirectorMocked(unittest.TestCase):
    def test_complete_script_to_structured_plan(self):
        llm = StaticLLM(json.dumps(VALID_PLAN))
        director = VisualDirector(llm=llm)
        plan = director.plan(EXAMPLE_SCRIPT)
        self.assertEqual(len(llm.calls), 1)
        self.assertIn("nine-to-five", llm.calls[0][1])
        self.assertIn("NO required scene count", llm.calls[0][1])
        self.assertNotIn("Required scene count:", llm.calls[0][1])
        self.assertNotIn("BETWEEN", llm.calls[0][1])
        self.assertNotIn("cut that spine into 6–12 scenes", llm.calls[0][0])
        self.assertNotIn("28–40", llm.calls[0][0] + llm.calls[0][1])
        self.assertEqual([s.provider_preference for s in plan.scenes], [
            "stock_video", "stock_video", "flow_image", "youtube", "stock_video",
        ])
        preview = plan.format_preview()
        self.assertIn("SCENE 01", preview)
        self.assertIn("Type: youtube", preview)
        self.assertIn("stock_video → flow_image", preview)

    def test_empty_script_rejected(self):
        with self.assertRaises(ValueError):
            VisualDirector(llm=StaticLLM("{}")).plan("  ")

    def test_plan_feeds_existing_asset_manager(self):
        plan = parse_visual_plan(VALID_PLAN)
        rows = plan.to_scene_rows()
        self.assertEqual(assert_pipeline_compatible(plan), [])
        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp)
            stock = FakeProvider(AssetSource.STOCK_VIDEO, {str(i): "ok" for i in range(1, 6)})
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {str(i): "ok" for i in range(1, 6)})
            youtube = FakeProvider(AssetSource.YOUTUBE_VIDEO, {str(i): "ok" for i in range(1, 6)})
            mgr = AssetManager(
                images,
                stock_provider=stock,
                flow_image_provider=flow,
                youtube_provider=youtube,
                log=lambda *_: None,
            )
            summary = mgr.resolve_all(rows)
            self.assertTrue(summary.ok, [r.error for r in summary.failed])
            self.assertEqual(summary.results["1"].source, AssetSource.STOCK_VIDEO)
            self.assertEqual(summary.results["3"].source, AssetSource.FLOW_IMAGE)
            self.assertEqual(summary.results["4"].source, AssetSource.YOUTUBE_VIDEO)
            self.assertTrue((images / "001.mp4").is_file() or (images / "001.jpg").is_file())

    def test_write_csv_roundtrip(self):
        plan = parse_visual_plan(VALID_PLAN)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script.csv"
            plan.write_csv(path)
            import csv
            with path.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(list(rows[0].keys()), [
                "scene_number", "script_segment", "asset_type", "prompt",
            ])
            scene_rows = [SceneRow.from_csv_row(r) for r in rows]
            self.assertEqual(SceneAssetRouter.classify(scene_rows[3]), AssetSource.YOUTUBE_VIDEO)
            self.assertEqual(SceneAssetRouter.classify(scene_rows[2]), AssetSource.FLOW_IMAGE)


class TestGeminiProvider(unittest.TestCase):
    def test_missing_api_key_is_explicit(self):
        from visual_director.llm import GeminiLLM, LLMError, MISSING_GEMINI_KEY

        llm = GeminiLLM(api_key="")
        with self.assertRaises(LLMError) as ctx:
            llm.complete("sys", "user")
        self.assertEqual(str(ctx.exception), MISSING_GEMINI_KEY)

    def test_resolve_key_uses_settings_when_env_empty(self):
        import os
        from unittest.mock import patch
        from visual_director.llm import resolve_gemini_api_key

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            self.assertEqual(
                resolve_gemini_api_key({"gemini_api_key": "from-settings"}),
                "from-settings",
            )

    def test_extract_gemini_response_then_parse_plan(self):
        from visual_director.llm import extract_gemini_text

        payload = {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(VALID_PLAN)}]}}
            ]
        }
        plan = parse_visual_plan(extract_gemini_text(payload))
        self.assertEqual(len(plan.scenes), 5)
        self.assertEqual(plan.scenes[0].minimum_quality, "1080p")

    def test_gemini_wrapped_plan_feeds_asset_manager(self):
        from visual_director.llm import extract_gemini_text

        raw = extract_gemini_text(
            {"candidates": [{"content": {"parts": [{"text": json.dumps(VALID_PLAN)}]}}]}
        )
        director = VisualDirector(llm=StaticLLM(raw))
        plan = director.plan(EXAMPLE_SCRIPT)
        rows = plan.to_scene_rows()
        self.assertEqual(assert_pipeline_compatible(plan), [])
        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp)
            mgr = AssetManager(
                images,
                stock_provider=FakeProvider(AssetSource.STOCK_VIDEO, {str(i): "ok" for i in range(1, 6)}),
                flow_image_provider=FakeProvider(AssetSource.FLOW_IMAGE, {str(i): "ok" for i in range(1, 6)}),
                youtube_provider=FakeProvider(AssetSource.YOUTUBE_VIDEO, {str(i): "ok" for i in range(1, 6)}),
                log=lambda *_: None,
            )
            summary = mgr.resolve_all(rows)
            self.assertTrue(summary.ok, [r.error for r in summary.failed])

    def test_invalid_minimum_quality_rejected(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["scenes"] = payload["scenes"][:2]
        payload["scenes"][0]["minimum_quality"] = "potato"
        with self.assertRaises(VisualPlanError):
            parse_visual_plan(payload)

    def test_default_director_uses_gemini_backend(self):
        from visual_director.llm import GeminiLLM

        self.assertIsInstance(VisualDirector(llm=GeminiLLM(api_key="x")).llm, GeminiLLM)

    def test_default_model_is_gemini_3_6_flash(self):
        from visual_director.llm import DEFAULT_GEMINI_MODEL, GeminiLLM

        self.assertEqual(DEFAULT_GEMINI_MODEL, "gemini-3.6-flash")
        self.assertEqual(GeminiLLM(api_key="x").model, "gemini-3.6-flash")

    def test_extract_skips_thought_parts(self):
        from visual_director.llm import extract_gemini_text

        payload = {
            "candidates": [{
                "content": {
                    "parts": [
                        {"thought": True, "text": "internal reasoning, not JSON"},
                        {"text": json.dumps(VALID_PLAN)},
                    ]
                }
            }]
        }
        plan = parse_visual_plan(extract_gemini_text(payload))
        self.assertEqual(len(plan.scenes), 5)

    def test_gemini_http_error_is_useful_and_redacts_key(self):
        from visual_director.llm import format_gemini_api_error

        body = json.dumps({
            "error": {
                "code": 404,
                "message": "models/gemini-3.6-flash is no longer available AIzaSyFakeKeyForTestOnly1234567890",
                "status": "NOT_FOUND",
            }
        })
        msg = format_gemini_api_error(404, body, "gemini-3.6-flash")
        self.assertEqual(msg, "Gemini API error: model gemini-3.6-flash unavailable")
        self.assertNotIn("AIza", msg)

        quota = format_gemini_api_error(
            429,
            json.dumps({"error": {"message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}}),
            "gemini-3.6-flash",
        )
        self.assertEqual(quota, "Gemini API error: Resource exhausted")


def _stock_scene(i: int, narration: str) -> dict:
    return {
        "scene_id": i,
        "narration": narration,
        "visual_goal": f"Beat {i} of the story.",
        "visual_description": (
            f"Distinct documentary shot {i}: icy plains, variant lighting {i}, "
            f"camera height {i % 7}, no repeated framing."
        ),
        "asset_type": "stock_video",
        "provider_preference": "stock_video",
        "search_queries": [f"pluto icy terrain aerial variant {i} daylight"],
        "timestamp_needed": False,
        "duration": 3.5,
        "importance": "medium",
        "fallbacks": ["flow_image"],
        "visual_treatment": "slow pan",
        "transition": "cut",
    }


class TestCoveragePlanning(unittest.TestCase):
    def test_user_message_has_no_scene_count_target(self):
        from visual_director.director import _plan_user_message

        script = "The ice world Pluto hides a buried ocean. " * 400
        user = _plan_user_message(script)
        self.assertIn("NO required scene count", user)
        self.assertNotIn("BETWEEN", user)
        self.assertNotIn("hard maximum", user.lower())
        self.assertNotIn("28–40", user)
        self.assertNotIn("6–12 grouped", user)

    def test_prompt_forbids_sentence_and_paragraph_rules(self):
        self.assertIn("not \"one sentence = one scene\"", SYSTEM_PROMPT)
        self.assertIn("COMPLETE visual timeline", SYSTEM_PROMPT)
        self.assertIn("HARD MAX 3.0s", SYSTEM_PROMPT)
        self.assertIn("HARD MAX 6.0s", SYSTEM_PROMPT)
        self.assertNotIn("Honor it", SYSTEM_PROMPT)

    def test_under_segmented_long_script_retries_then_accepts(self):
        from visual_director.director import plan_segmentation_issue

        chunk = "Pluto is a frozen world with a buried ocean and a blue haze. "
        script = chunk * 150
        words = len(script.split())
        self.assertGreater(words, 1500)

        compressed = {
            "topic": "Pluto",
            "scenes": [_stock_scene(1, script[:200]), _stock_scene(2, script[200:400])],
        }
        n_ok = 130
        dense = {
            "topic": "Pluto",
            "scenes": [_stock_scene(i + 1, chunk) for i in range(n_ok)],
        }

        class TwoShot:
            def __init__(self):
                self.calls = []

            def complete(self, system, user):
                self.calls.append((system, user))
                if len(self.calls) == 1:
                    return json.dumps(compressed)
                return json.dumps(dense)

        llm = TwoShot()
        plan = VisualDirector(llm=llm).plan(script)
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("under-segmented", llm.calls[1][1])
        self.assertEqual(len(plan.scenes), n_ok)
        self.assertIsNone(plan_segmentation_issue(script, plan))

    def test_five_k_word_dense_plan_accepted(self):
        """~5k words / ~190 scenes must not fail the strict 8s hold rule."""
        from visual_director.director import (
            estimate_narration_seconds,
            plan_segmentation_issue,
            script_word_count,
        )
        from visual_director.schema import parse_visual_plan

        chunk = (
            "The old house stood on the hill overlooking the valley where fog "
            "gathered every morning before the sun broke through the trees. "
        )
        script = chunk * 210
        words = script_word_count(script)
        self.assertGreaterEqual(words, 4300)

        est = estimate_narration_seconds(words)
        n_scenes = 192
        # Split script into n_scenes narration slices so coverage passes.
        tokens = script.split()
        per = max(1, len(tokens) // n_scenes)
        scenes = []
        for i in range(n_scenes):
            start = i * per
            end = (i + 1) * per if i < n_scenes - 1 else len(tokens)
            narr = " ".join(tokens[start:end]) or chunk.strip()
            scenes.append(_stock_scene(i + 1, narr))
        plan = parse_visual_plan({"topic": "House documentary", "scenes": scenes})
        implied = est / len(plan.scenes)
        self.assertGreater(implied, 8.0)
        self.assertLess(implied, 12.0)
        self.assertIsNone(plan_segmentation_issue(script, plan))

    def test_compressed_plan_is_not_silently_accepted(self):
        chunk = "Pluto is a frozen world with a buried ocean and a blue haze. "
        script = chunk * 400
        tiny = {"topic": "Pluto", "scenes": [_stock_scene(1, chunk), _stock_scene(2, chunk)]}
        llm = StaticLLM(json.dumps(tiny))
        with self.assertRaises(VisualPlanError) as ctx:
            VisualDirector(llm=llm).plan(script)
        self.assertIn("under-segmented", str(ctx.exception))

    def test_many_scenes_parse_without_a_max_cap(self):
        payload = {
            "topic": "Long film",
            "scenes": [_stock_scene(i + 1, f"Narration beat {i} about Pluto's ice.") for i in range(80)],
        }
        plan = parse_visual_plan(payload)
        self.assertEqual(len(plan.scenes), 80)

    def test_duration_hard_caps_unchanged_in_prompt(self):
        self.assertIn("HARD MAX 3.0s", SYSTEM_PROMPT)
        self.assertIn("HARD MAX 6.0s", SYSTEM_PROMPT)
        self.assertIn("archive_video", SYSTEM_PROMPT)
        self.assertIn("nasa_video", SYSTEM_PROMPT)
        self.assertNotIn("commons_image", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
