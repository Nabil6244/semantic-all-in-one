"""Audio Director library: selection, quality gate, catalog and packaging.

The build-time generator is pure/deterministic, so these run without the
Sonniss source except where a real decode is explicitly required.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import build_audio_library as B  # noqa: E402


def _asset(name, *, dur=2.0, mean=-20.0, peak=-3.0, sil=0.0, cen=3000.0,
           flat=0.2, trans=0.01, ch=2, sr=48000, crest=8.0, rel=None):
    a = B.Asset(path=Path(f"/src/{name}"), rel=rel or name)
    a.size = int(dur * 200_000); a.duration = dur; a.sample_rate = sr; a.channels = ch
    a.mean_db = mean; a.peak_db = peak; a.silence_ratio = sil
    a.centroid_hz = cen; a.flatness = flat; a.transient_density = trans
    a.crest = crest; a.ok = True
    return B.classify(a)


class TestQualityGate(unittest.TestCase):
    def test_healthy_asset_passes(self):
        self.assertTrue(B.passes_quality(_asset("impact_good.wav")))

    def test_near_silent_rejected(self):
        self.assertFalse(B.passes_quality(_asset("x.wav", sil=0.95, mean=-55, peak=-45)))

    def test_too_quiet_rejected(self):
        self.assertFalse(B.passes_quality(_asset("x.wav", mean=-70, peak=-50)))

    def test_unusual_but_healthy_sound_survives(self):
        """A rare sound must NOT be discarded merely for being unmatched."""
        odd = _asset("zzz_unknown_recording.wav", cen=11000, flat=0.8)
        self.assertEqual(odd.cats, [], "precondition: no category keyword")
        self.assertTrue(B.passes_quality(odd), "unusual != unusable")

    def test_clipping_is_penalised_not_auto_rejected(self):
        clipped = _asset("impact_clip.wav", peak=-0.0)
        clean = _asset("impact_clean.wav", peak=-3.0)
        self.assertLess(clipped.quality, clean.quality)


class TestClassification(unittest.TestCase):
    def test_long_sustained_is_ambience(self):
        self.assertEqual(_asset("rain_long.wav", dur=90, trans=0.005).audio_type, "ambience")

    def test_short_percussive_is_sfx(self):
        self.assertEqual(_asset("impact_hit.wav", dur=1.2, trans=0.2).audio_type, "sfx")

    def test_signal_overrides_missing_filename_hint(self):
        """The 27 ambience files regex cannot reach must still classify."""
        a = _asset("XYZ_take_04.wav", dur=120, trans=0.004)
        self.assertEqual(a.cats, [])
        self.assertEqual(a.audio_type, "ambience")

    def test_transient_and_spectral_characters(self):
        self.assertEqual(_asset("a.wav", trans=0.2).transient_character, "percussive")
        self.assertEqual(_asset("a.wav", trans=0.005).transient_character, "sustained")
        self.assertEqual(_asset("a.wav", cen=500).spectral_character, "low/rumble")
        self.assertEqual(_asset("a.wav", cen=9000, flat=0.5).spectral_character, "bright/noisy")


class TestSelection(unittest.TestCase):
    def _pool(self):
        pool = []
        # 6 interchangeable whooshes + genuinely different material
        for i in range(6):
            pool.append(_asset(f"whoosh_{i}.wav", dur=1.5, cen=4000, flat=0.30,
                               trans=0.05, mean=-20 - i * 0.05))
        pool.append(_asset("impact_heavy.wav", dur=2.0, cen=400, flat=0.1, trans=0.25, mean=-14))
        pool.append(_asset("ui_click.wav", dur=0.4, cen=7000, flat=0.5, trans=0.3, mean=-24))
        pool.append(_asset("rain_amb.wav", dur=120, cen=2200, flat=0.7, trans=0.004, mean=-26))
        pool.append(_asset("city_amb.wav", dur=90, cen=1200, flat=0.6, trans=0.006, mean=-25))
        return pool

    def test_deterministic(self):
        p1, p2 = self._pool(), self._pool()
        a = [x.rel for x in B.select(p1, 8, 0.25, 0.20, log=lambda *_: None)[0]]
        b = [x.rel for x in B.select(p2, 8, 0.25, 0.20, log=lambda *_: None)[0]]
        self.assertEqual(a, b, "selection must be reproducible for the build")

    def test_interchangeable_variants_are_not_all_selected(self):
        chosen, _, _, _ = B.select(self._pool(), 10, 0.25, 0.20, log=lambda *_: None)
        whooshes = [x for x in chosen if x.rel.startswith("whoosh_")]
        self.assertLess(len(whooshes), 6, "must not select all 6 near-identical whooshes")

    def test_distinct_material_is_preferred(self):
        chosen, _, _, _ = B.select(self._pool(), 5, 0.25, 0.20, log=lambda *_: None)
        rels = {x.rel for x in chosen}
        self.assertTrue({"rain_amb.wav", "city_amb.wav"} & rels)
        self.assertIn("impact_heavy.wav", rels)

    def test_coverage_stage_runs_before_variety(self):
        chosen, covered, universe, saturated = B.select(self._pool(), 10, 0.25, 0.20, log=lambda *_: None)
        self.assertGreater(saturated, 0)
        self.assertLessEqual(saturated, len(chosen))
        self.assertTrue(all(c.reason for c in chosen), "every asset needs a reason")
        self.assertTrue(any(c.reason.startswith("coverage:") for c in chosen))

    def test_target_is_an_upper_bound_not_a_quota(self):
        chosen, _, _, _ = B.select(self._pool(), 100, 0.25, 0.20, log=lambda *_: None)
        self.assertLessEqual(len(chosen), len(self._pool()))

    def test_similarity_grouping_is_feature_based_not_pack_based(self):
        pool = self._pool()
        n = B.group_similar(pool, 0.22)
        self.assertGreater(n, 0)
        wg = {x.similarity_group for x in pool if x.rel.startswith("whoosh_")}
        self.assertEqual(len(wg), 1, "near-identical whooshes must share a group")
        self.assertNotIn(next(x for x in pool if x.rel == "rain_amb.wav").similarity_group, wg)


class TestCatalogValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "impact").mkdir(parents=True)
        self.wav = self.tmp / "impact" / "impact_001.wav"
        self.wav.write_bytes(b"RIFF" + b"\x00" * 64)
        self.cat = {"version": 2, "sfx": [{"id": "impact_001", "file": "impact/impact_001.wav",
                                           "format": "wav", "sample_rate": 48000, "channels": 2}]}
        self._write()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self):
        (self.tmp / "catalog.json").write_text(json.dumps(self.cat), encoding="utf-8")

    def test_valid_library_reports_no_problems(self):
        self.assertEqual(B.validate_bundled_audio_library(self.tmp, deep=False), [])

    def test_missing_file_detected(self):
        self.wav.unlink()
        p = B.validate_bundled_audio_library(self.tmp, deep=False)
        self.assertTrue(any("missing file" in x for x in p))

    def test_orphan_file_detected(self):
        (self.tmp / "impact" / "orphan_002.wav").write_bytes(b"RIFF")
        p = B.validate_bundled_audio_library(self.tmp, deep=False)
        self.assertTrue(any("orphan" in x for x in p))

    def test_absolute_path_rejected(self):
        self.cat["sfx"][0]["file"] = "/etc/passwd"; self._write()
        p = B.validate_bundled_audio_library(self.tmp, deep=False)
        self.assertTrue(any("non-relative" in x for x in p))

    def test_escaping_path_rejected(self):
        self.cat["sfx"][0]["file"] = "../../secrets.wav"; self._write()
        p = B.validate_bundled_audio_library(self.tmp, deep=False)
        self.assertTrue(any("escaping" in x or "non-relative" in x for x in p))

    def test_source_path_leak_rejected(self):
        """The app must never depend on the Sonniss source after install."""
        self.cat["sfx"][0]["source_path"] = "/Users/x/Downloads/videogen-sfx-source/a.wav"
        self._write()
        p = B.validate_bundled_audio_library(self.tmp, deep=False)
        self.assertTrue(any("leaks source path" in x for x in p))

    def test_missing_catalog_detected(self):
        (self.tmp / "catalog.json").unlink()
        self.assertTrue(B.validate_bundled_audio_library(self.tmp, deep=False))

    def test_unparseable_catalog_detected(self):
        (self.tmp / "catalog.json").write_text("{not json", encoding="utf-8")
        p = B.validate_bundled_audio_library(self.tmp, deep=False)
        self.assertTrue(any("does not parse" in x for x in p))


class TestFormatProfiles(unittest.TestCase):
    def test_wav_remains_supported(self):
        """WAV must not be removed until the pipeline has passed end to end."""
        self.assertIn("wav48", B.FORMATS)
        self.assertEqual(B.FORMATS["wav48"]["codec"], "pcm_s16le")

    def test_all_profiles_target_48k(self):
        for name, spec in B.FORMATS.items():
            self.assertIn("48000", spec["args"], name)

    def test_format_is_a_parameter_not_a_constant(self):
        self.assertGreaterEqual(len(B.FORMATS), 4)
        self.assertTrue({"wav48", "flac48", "opus96", "opus128"} <= set(B.FORMATS))


@unittest.skipUnless((Path(__file__).parent / "bin" / "ffprobe").is_file(),
                     "bundled ffprobe required")
class TestGeneratedLibraryIfPresent(unittest.TestCase):
    """Deep validation of a real generated library, when one has been built."""

    def _roots(self):
        return [p for p in (Path("/tmp/bundled-sfx-v2"), Path("/tmp/bundled-sfx-opus128"),) if (p / "catalog.json").is_file()]

    def test_generated_library_validates(self):
        roots = self._roots()
        if not roots:
            self.skipTest("no generated library present")
        ffprobe = str(Path(__file__).parent / "bin" / "ffprobe")
        for r in roots:
            self.assertEqual(B.validate_bundled_audio_library(r, ffprobe=ffprobe, deep=True), [], str(r))

    def test_every_entry_has_required_metadata(self):
        roots = self._roots()
        if not roots:
            self.skipTest("no generated library present")
        need = {"id", "file", "format", "category", "audio_type", "duration", "duration_band",
                "sample_rate", "channels", "quality_score", "intensity", "transient_character",
                "spectral_character", "similarity_group", "selection_reason", "source", "license"}
        cat = json.loads((roots[0] / "catalog.json").read_text())
        for e in cat["sfx"]:
            self.assertTrue(need <= set(e), f"{e.get('id')} missing {need - set(e)}")
            self.assertTrue(e["selection_reason"], f"{e['id']} has no reason")


if __name__ == "__main__":
    unittest.main()


class TestPlatformIndependentPathChecks(unittest.TestCase):
    """Regression for a Windows CI failure.

    validate_bundled_audio_library relied on pathlib for two things that are
    OS-dependent, so it behaved differently on Windows than on macOS:

      * Path("/etc/passwd").is_absolute() is False on Windows, so a
        POSIX-absolute catalog path was ACCEPTED there.
      * str(Path) yields "impact\\x.opus" on Windows while the catalog stores
        "impact/x.opus", so the orphan check reported EVERY bundled file as an
        orphan and the packaged build failed validation.

    These assert the behaviour directly, so the bug is caught on any host.
    """

    def test_absolute_and_escaping_paths_rejected_on_every_platform(self):
        for bad in ("/etc/passwd", "C:/Windows/x", "c:\\x", "../../secret",
                    "\\\\server\\share", "impact\\a.opus", ""):
            self.assertTrue(B._is_unsafe_relpath(bad), f"{bad!r} must be rejected")

    def test_normal_posix_relative_path_accepted(self):
        for good in ("impact/impact_001.opus", "ambience/ambience_001.wav", "a.wav"):
            self.assertFalse(B._is_unsafe_relpath(good), f"{good!r} must be accepted")

    def test_orphan_check_compares_in_posix_form(self):
        """A correct library must report zero orphans regardless of host."""
        import inspect
        src = inspect.getsource(B.validate_bundled_audio_library)
        self.assertIn("as_posix()", src)
        self.assertNotIn("str(p.relative_to(root))", src)
