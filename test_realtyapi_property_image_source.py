"""Focused tests for Phase 2: the Property Image Source switch and the
RealtyAPI photo supplement.

No real network calls anywhere in this file — httpx clients are mocked.
No real API key anywhere — only placeholder strings.

research/engine/app/... uses absolute `app.*` imports internally (it's
designed to run with research/engine itself as sys.path root, via the CLI
subprocess). `_load_engine_symbols()` below imports it under that required
top-level name "app", but saves and restores any pre-existing
sys.path/sys.modules["app"*] state around the import so this file never
leaves the engine's `app` package shadowing this repo's own top-level
app.py module for the rest of the pytest session (that shadowing is exactly
what broke unrelated test files the first time this was tried).
"""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from research.property_provider import PropertyResearchProvider
from research.settings import (
    DEFAULT_PROPERTY_IMAGE_SOURCE,
    load_property_image_source,
    with_property_image_source,
)

_ENGINE_ROOT = Path(__file__).resolve().parent / "research" / "engine"


def _load_engine_symbols():
    saved_path = list(sys.path)
    saved_modules = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    for key in saved_modules:
        del sys.modules[key]
    sys.path.insert(0, str(_ENGINE_ROOT))
    try:
        return (
            importlib.import_module("app.media.realtyapi_supplement"),
            importlib.import_module("app.models.media"),
            importlib.import_module("app.research.property_researcher"),
            importlib.import_module("app.media.variants"),
        )
    finally:
        sys.path[:] = saved_path
        for key in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
            del sys.modules[key]
        sys.modules.update(saved_modules)


_realtyapi_supplement, _media_models, _property_researcher, _variants = _load_engine_symbols()

_select_largest_jpeg = _realtyapi_supplement._select_largest_jpeg
_photos_to_media_assets = _realtyapi_supplement._photos_to_media_assets
fetch_realtyapi_photos = _realtyapi_supplement.fetch_realtyapi_photos
MediaType = _media_models.MediaType
MediaAsset = _media_models.MediaAsset
apply_image_source_mode = _property_researcher.apply_image_source_mode
group_variants = _variants.group_variants


# ---------------------------------------------------------------------------
# Settings / persistence
# ---------------------------------------------------------------------------

class PropertyImageSourceSettingsTests(unittest.TestCase):
    def test_default_is_existing(self):
        self.assertEqual(DEFAULT_PROPERTY_IMAGE_SOURCE, "existing")
        self.assertEqual(load_property_image_source({}), "existing")

    def test_can_select_realtyapi(self):
        settings = with_property_image_source({}, "realtyapi")
        self.assertEqual(load_property_image_source(settings), "realtyapi")

    def test_can_select_both(self):
        settings = with_property_image_source({}, "both")
        self.assertEqual(load_property_image_source(settings), "both")

    def test_selection_survives_a_settings_reload_roundtrip(self):
        import json

        saved = with_property_image_source({}, "realtyapi")
        reloaded = json.loads(json.dumps(saved))
        self.assertEqual(load_property_image_source(reloaded), "realtyapi")

    def test_invalid_value_normalizes_to_default(self):
        settings = with_property_image_source({}, "not-a-real-mode")
        self.assertEqual(load_property_image_source(settings), "existing")

    def test_case_and_whitespace_insensitive(self):
        settings = with_property_image_source({}, "  BOTH  ")
        self.assertEqual(load_property_image_source(settings), "both")

    def test_unrelated_settings_preserved(self):
        settings = with_property_image_source(
            {"pexels_api_key": "unrelated", "realtyapi_api_key": "unrelated2"}, "realtyapi",
        )
        self.assertEqual(settings["pexels_api_key"], "unrelated")
        self.assertEqual(settings["realtyapi_api_key"], "unrelated2")


# ---------------------------------------------------------------------------
# PropertyResearchProvider: CLI arg + env var wiring, Existing mode = today
# ---------------------------------------------------------------------------

def _write_research_package(output_dir: Path) -> None:
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "research.json").write_text(json.dumps({
        "property": {"identity": {"property_name": "Test", "canonical_address": "1 Test St"}, "confidence": 0.9},
        "media": [], "sources": [], "statistics": {},
    }), encoding="utf-8")


class PropertyResearchProviderImageSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_existing_mode_passes_no_realtyapi_env_var(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            _write_research_package(Path(cmd[cmd.index("--output") + 1]))

            class FakeProc:
                returncode = 0
                stdout = ""
                stderr = ""
            return FakeProc()

        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        with patch("research.property_provider.hidden_subprocess.run", side_effect=fake_run):
            provider.research(
                "Test", urls=["https://example.test/listing"], output_dir=self.tmp / "out",
                image_source="existing", realtyapi_key="placeholder-should-be-unused",
            )
        self.assertIn("--property-image-source", captured["cmd"])
        idx = captured["cmd"].index("--property-image-source")
        self.assertEqual(captured["cmd"][idx + 1], "existing")
        # No env override at all in Existing mode -> subprocess inherits the
        # parent environment untouched, exactly as before this feature.
        self.assertIsNone(captured["env"])

    def test_realtyapi_mode_sets_env_var_not_cli_arg(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            _write_research_package(Path(cmd[cmd.index("--output") + 1]))

            class FakeProc:
                returncode = 0
                stdout = ""
                stderr = ""
            return FakeProc()

        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        with patch("research.property_provider.hidden_subprocess.run", side_effect=fake_run):
            provider.research(
                "Test", urls=["https://example.test/listing"], output_dir=self.tmp / "out",
                image_source="realtyapi", realtyapi_key="placeholder-secret-key",
            )
        idx = captured["cmd"].index("--property-image-source")
        self.assertEqual(captured["cmd"][idx + 1], "realtyapi")
        # The key is NEVER a CLI argument.
        self.assertNotIn("placeholder-secret-key", captured["cmd"])
        # It IS passed via the REALTYAPI_API_KEY environment variable.
        self.assertEqual(captured["env"]["REALTYAPI_API_KEY"], "placeholder-secret-key")

    def test_both_mode_sets_env_var(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            _write_research_package(Path(cmd[cmd.index("--output") + 1]))

            class FakeProc:
                returncode = 0
                stdout = ""
                stderr = ""
            return FakeProc()

        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        with patch("research.property_provider.hidden_subprocess.run", side_effect=fake_run):
            provider.research(
                "Test", urls=["https://example.test/listing"], output_dir=self.tmp / "out",
                image_source="both", realtyapi_key="placeholder-secret-key-2",
            )
        self.assertEqual(captured["env"]["REALTYAPI_API_KEY"], "placeholder-secret-key-2")

    def test_realtyapi_mode_with_no_key_sets_no_env_var(self):
        """Missing key: the CLI still runs (facts/research must not be
        blocked), just with no key available to the engine — which itself
        must then make zero RealtyAPI calls (see supplement tests below)."""
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            _write_research_package(Path(cmd[cmd.index("--output") + 1]))

            class FakeProc:
                returncode = 0
                stdout = ""
                stderr = ""
            return FakeProc()

        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        with patch("research.property_provider.hidden_subprocess.run", side_effect=fake_run):
            result = provider.research(
                "Test", urls=["https://example.test/listing"], output_dir=self.tmp / "out",
                image_source="realtyapi", realtyapi_key="",
            )
        self.assertIsNone(captured["env"])
        self.assertTrue(result.ok)  # research must not fail merely for lacking a key

    def test_invalid_image_source_normalizes_to_existing(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            _write_research_package(Path(cmd[cmd.index("--output") + 1]))

            class FakeProc:
                returncode = 0
                stdout = ""
                stderr = ""
            return FakeProc()

        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        with patch("research.property_provider.hidden_subprocess.run", side_effect=fake_run):
            provider.research(
                "Test", urls=["https://example.test/listing"], output_dir=self.tmp / "out",
                image_source="not-a-mode",
            )
        idx = captured["cmd"].index("--property-image-source")
        self.assertEqual(captured["cmd"][idx + 1], "existing")


# ---------------------------------------------------------------------------
# RealtyAPI photo supplement — pure parsing + network-failure behavior
# ---------------------------------------------------------------------------

def _jpeg_sources(*widths):
    return {"jpeg": [{"url": f"https://cdn.realtyapi.example/photo-{w}.jpg", "width": w} for w in widths]}


class SelectLargestJpegTests(unittest.TestCase):
    def test_picks_highest_of_800_1024_1344_1536(self):
        chosen = _select_largest_jpeg(_jpeg_sources(800, 1024, 1344, 1536))
        self.assertEqual(chosen["width"], 1536)
        self.assertIn("1536", chosen["url"])

    def test_1920_beats_1536(self):
        chosen = _select_largest_jpeg(_jpeg_sources(800, 1024, 1344, 1536, 1920))
        self.assertEqual(chosen["width"], 1920)

    def test_1536_beats_1344(self):
        chosen = _select_largest_jpeg(_jpeg_sources(800, 1024, 1344, 1536))
        self.assertGreater(chosen["width"], 1344)

    def test_1344_beats_1024(self):
        chosen = _select_largest_jpeg(_jpeg_sources(800, 1024, 1344))
        self.assertGreater(chosen["width"], 1024)

    def test_1024_beats_800(self):
        chosen = _select_largest_jpeg(_jpeg_sources(800, 1024))
        self.assertGreater(chosen["width"], 800)

    def test_only_800_uses_800(self):
        chosen = _select_largest_jpeg(_jpeg_sources(800))
        self.assertEqual(chosen["width"], 800)

    def test_never_invents_a_url(self):
        sources = _jpeg_sources(800, 1536)
        chosen = _select_largest_jpeg(sources)
        real_urls = {e["url"] for e in sources["jpeg"]}
        self.assertIn(chosen["url"], real_urls)

    def test_missing_mixed_sources_returns_none(self):
        self.assertIsNone(_select_largest_jpeg(None))
        self.assertIsNone(_select_largest_jpeg({}))
        self.assertIsNone(_select_largest_jpeg({"jpeg": "not-a-list"}))

    def test_malformed_entries_are_skipped_not_fatal(self):
        malformed = {"jpeg": [
            "not-a-dict", {"width": 1536},  # missing url
            {"url": ""}, {"url": "https://x/y.jpg", "width": "not-a-number"},
            {"url": "https://x/real.jpg", "width": 1024},
        ]}
        chosen = _select_largest_jpeg(malformed)
        self.assertEqual(chosen["url"], "https://x/real.jpg")
        self.assertEqual(chosen["width"], 1024)


class PhotosToMediaAssetsTests(unittest.TestCase):
    def test_produces_candidates_from_valid_response(self):
        photos = [{"mixedSources": _jpeg_sources(800, 1536)}]
        assets = _photos_to_media_assets(photos, source_page="https://example.test/listing", source_id="realtyapi")
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].media_type, MediaType.IMAGE)
        self.assertEqual(assets[0].width, 1536)
        self.assertEqual(assets[0].provider, "realtyapi")

    def test_missing_photo_data_returns_empty(self):
        self.assertEqual(_photos_to_media_assets(None, source_page="", source_id=""), [])
        self.assertEqual(_photos_to_media_assets("not-a-list", source_page="", source_id=""), [])
        self.assertEqual(_photos_to_media_assets([], source_page="", source_id=""), [])

    def test_malformed_photo_entries_are_skipped(self):
        photos = [
            "not-a-dict",
            {"mixedSources": None},
            {"mixedSources": _jpeg_sources(1024)},
        ]
        assets = _photos_to_media_assets(photos, source_page="", source_id="")
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].width, 1024)

    def test_original_order_is_preserved(self):
        photos = [
            {"mixedSources": _jpeg_sources(800)},
            {"mixedSources": _jpeg_sources(1536)},
            {"mixedSources": _jpeg_sources(1024)},
        ]
        assets = _photos_to_media_assets(photos, source_page="", source_id="")
        self.assertEqual([a.width for a in assets], [800, 1536, 1024])
        self.assertEqual([a.page_position for a in assets], [0, 1, 2])


class FetchRealtyapiPhotosTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_key_configured_makes_zero_network_calls(self):
        mock_client = MagicMock()
        mock_client.get = AsyncMock()
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("REALTYAPI_API_KEY", None)
            result = await fetch_realtyapi_photos(listing_url="https://example.test/x", http_client=mock_client)
        self.assertEqual(result, [])
        mock_client.get.assert_not_called()

    async def test_no_listing_url_or_address_makes_zero_network_calls(self):
        mock_client = MagicMock()
        mock_client.get = AsyncMock()
        with patch.dict("os.environ", {"REALTYAPI_API_KEY": "placeholder"}):
            result = await fetch_realtyapi_photos(http_client=mock_client)
        self.assertEqual(result, [])
        mock_client.get.assert_not_called()

    async def test_address_only_makes_zero_network_calls(self):
        """/pro/byurl (the only documented endpoint this module calls)
        accepts a Zillow URL only, not an address — address-only input must
        not produce a request to it."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock()
        with patch.dict("os.environ", {"REALTYAPI_API_KEY": "placeholder"}):
            result = await fetch_realtyapi_photos(address="1 Test St, Testville, TS", http_client=mock_client)
        self.assertEqual(result, [])
        mock_client.get.assert_not_called()

    async def _fetch_with_mock_response(self, *, status_code=200, json_data=None, raise_exc=None):
        mock_client = MagicMock()
        if raise_exc is not None:
            mock_client.get = AsyncMock(side_effect=raise_exc)
        else:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            if json_data is _MALFORMED:
                mock_response.json = MagicMock(side_effect=ValueError("bad json"))
            else:
                mock_response.json = MagicMock(return_value=json_data)
            mock_client.get = AsyncMock(return_value=mock_response)
        with patch.dict("os.environ", {"REALTYAPI_API_KEY": "placeholder-test-key"}):
            return await fetch_realtyapi_photos(listing_url="https://example.test/x", http_client=mock_client), mock_client

    async def test_valid_response_produces_candidates(self):
        data = {"originalPhotos": [{"mixedSources": _jpeg_sources(800, 1536)}]}
        result, _client = await self._fetch_with_mock_response(json_data=data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].width, 1536)

    async def test_401_yields_no_candidates_no_raise(self):
        result, _ = await self._fetch_with_mock_response(status_code=401, json_data={})
        self.assertEqual(result, [])

    async def test_403_yields_no_candidates_no_raise(self):
        result, _ = await self._fetch_with_mock_response(status_code=403, json_data={})
        self.assertEqual(result, [])

    async def test_404_yields_no_candidates_no_raise(self):
        result, _ = await self._fetch_with_mock_response(status_code=404, json_data={})
        self.assertEqual(result, [])

    async def test_429_yields_no_candidates_no_raise(self):
        result, _ = await self._fetch_with_mock_response(status_code=429, json_data={})
        self.assertEqual(result, [])

    async def test_500_yields_no_candidates_no_raise(self):
        result, _ = await self._fetch_with_mock_response(status_code=500, json_data={})
        self.assertEqual(result, [])

    async def test_timeout_yields_no_candidates_no_raise(self):
        import httpx
        result, _ = await self._fetch_with_mock_response(raise_exc=httpx.TimeoutException("timed out"))
        self.assertEqual(result, [])

    async def test_connection_error_yields_no_candidates_no_raise(self):
        import httpx
        result, _ = await self._fetch_with_mock_response(raise_exc=httpx.ConnectError("refused"))
        self.assertEqual(result, [])

    async def test_malformed_json_yields_no_candidates_no_raise(self):
        result, _ = await self._fetch_with_mock_response(json_data=_MALFORMED)
        self.assertEqual(result, [])

    async def test_missing_photos_field_yields_no_candidates(self):
        result, _ = await self._fetch_with_mock_response(json_data={"someOtherField": True})
        self.assertEqual(result, [])

    async def test_response_not_a_dict_yields_no_candidates(self):
        result, _ = await self._fetch_with_mock_response(json_data=["not", "a", "dict"])
        self.assertEqual(result, [])

    async def test_key_never_appears_in_request_url(self):
        """The key must travel only as a header, never a query param/URL —
        so it can never leak via URL logging."""
        data = {"originalPhotos": []}
        _result, client = await self._fetch_with_mock_response(json_data=data)
        call_args = client.get.call_args
        url_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        params = call_args.kwargs.get("params", {})
        self.assertNotIn("placeholder-test-key", url_arg)
        self.assertNotIn("placeholder-test-key", str(params))
        headers = call_args.kwargs.get("headers", {})
        self.assertEqual(headers.get("x-realtyapi-key"), "placeholder-test-key")

    async def test_request_matches_the_documented_pro_byurl_endpoint(self):
        """Verified 2026-09 against https://zillow.realtyapi.io/openapi.json
        — GET /pro/byurl on the zillow.realtyapi.io subdomain, `url` query
        param, x-realtyapi-key header."""
        self.assertEqual(_realtyapi_supplement.REALTYAPI_BASE_URL, "https://zillow.realtyapi.io")
        self.assertEqual(_realtyapi_supplement.REALTYAPI_PROPERTY_ENDPOINT, "/pro/byurl")

        data = {"originalPhotos": []}
        _result, client = await self._fetch_with_mock_response(json_data=data)
        call_args = client.get.call_args
        url_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        self.assertEqual(url_arg, "https://zillow.realtyapi.io/pro/byurl")
        params = call_args.kwargs.get("params", {})
        self.assertEqual(params, {"url": "https://example.test/x"})


_MALFORMED = object()  # sentinel: response.json() raises ValueError


# ---------------------------------------------------------------------------
# Property Image Source mode dispatch (Both mode's additive-only guarantee,
# resolution-driven winner selection) — property_researcher.py
# ---------------------------------------------------------------------------

from uuid import uuid4


def _asset(url, media_type=MediaType.IMAGE, **kw):
    defaults = dict(
        media_id=f"m_{uuid4().hex[:8]}", media_type=media_type, source_url=url,
        source_page="https://example.test/listing",
    )
    defaults.update(kw)
    return MediaAsset(**defaults)


class ApplyImageSourceModeTests(unittest.TestCase):
    def test_existing_mode_is_unchanged_and_ignores_any_realtyapi_media(self):
        existing = [_asset("https://a.example/1.jpg"), _asset("https://a.example/2.jpg")]
        result = apply_image_source_mode(existing, [], "existing")
        self.assertEqual(result, existing)

    def test_realtyapi_mode_drops_existing_images_keeps_video(self):
        existing_image = _asset("https://a.example/1.jpg", media_type=MediaType.IMAGE)
        existing_video = _asset("https://a.example/1.mp4", media_type=MediaType.VIDEO)
        realty = [_asset("https://realtyapi.example/1.jpg")]
        result = apply_image_source_mode([existing_image, existing_video], realty, "realtyapi")
        self.assertNotIn(existing_image, result)
        self.assertIn(existing_video, result)
        self.assertIn(realty[0], result)

    def test_both_mode_keeps_existing_and_adds_realtyapi(self):
        existing = [_asset("https://a.example/1.jpg")]
        realty = [_asset("https://realtyapi.example/1.jpg")]
        result = apply_image_source_mode(existing, realty, "both")
        self.assertIn(existing[0], result)
        self.assertIn(realty[0], result)
        self.assertEqual(len(result), 2)

    def test_both_mode_existing_higher_resolution_still_wins(self):
        """Existing 1920px vs RealtyAPI 1536px -> existing wins. No source-
        preference score anywhere: this is decided purely by
        group_variants()'s existing measured-pixel election, unmodified."""
        existing = _asset(
            "https://a.example/photo.jpg",
            actual_width=1920, actual_height=1080,
        )
        realty = _asset(
            "https://realtyapi.example/photo-b.jpg",
            actual_width=1536, actual_height=864,
        )
        combined = apply_image_source_mode([existing], [realty], "both")
        elected = group_variants(combined)
        # Different URLs won't URL-pattern-group, so both remain as separate
        # "photos" here (variant grouping is URL-based) — the property
        # under test is that the higher-resolution asset from EITHER source
        # is never discarded or demoted; ranking downstream (unmodified)
        # will prefer it. Assert both survive and the higher-res one is
        # measurably still the better candidate.
        self.assertEqual(len(elected), 2)
        best = max(elected, key=lambda a: (a.actual_width or 0) * (a.actual_height or 0))
        self.assertEqual(best.source_url, existing.source_url)

    def test_both_mode_realtyapi_higher_resolution_naturally_wins(self):
        existing = _asset("https://a.example/photo.jpg", actual_width=800, actual_height=600)
        realty = _asset("https://realtyapi.example/photo-b.jpg", actual_width=1536, actual_height=1152)
        combined = apply_image_source_mode([existing], [realty], "both")
        elected = group_variants(combined)
        best = max(elected, key=lambda a: (a.actual_width or 0) * (a.actual_height or 0))
        self.assertEqual(best.source_url, realty.source_url)

    def test_realtyapi_media_carries_property_match_score_for_ranking(self):
        realty = _asset("https://realtyapi.example/1.jpg", property_match_score=1.0)
        self.assertEqual(realty.property_match_score, 1.0)


if __name__ == "__main__":
    unittest.main()
