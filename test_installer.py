"""Unit tests for the optional online installer stub (mocked; no multi-GB downloads)."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from installer.download import DownloadError, sha256_file, verify_sha256
from installer.extract import extract_archive, should_skip_archive_member
from installer.manifest import (
    RELEASE_NOT_PUBLISHED,
    ManifestError,
    FileSpec,
    ModelSpec,
    PlatformSpec,
    is_published,
    load_manifest,
    platform_spec,
    require_published,
)
from installer.pipeline import aggregate_progress
from installer.platform import UnsupportedPlatformError, detect_platform, try_detect_platform


class TestPlatformDetect(unittest.TestCase):
    def test_win_amd64(self):
        with patch("installer.platform.sys.platform", "win32"):
            with patch("installer.platform.platform.machine", return_value="AMD64"):
                self.assertEqual(detect_platform(), "win-amd64")

    def test_darwin_arm64(self):
        with patch("installer.platform.sys.platform", "darwin"):
            with patch("installer.platform.platform.machine", return_value="arm64"):
                self.assertEqual(detect_platform(), "darwin-arm64")

    def test_rejects_intel_mac(self):
        with patch("installer.platform.sys.platform", "darwin"):
            with patch("installer.platform.platform.machine", return_value="x86_64"):
                with self.assertRaises(UnsupportedPlatformError) as ctx:
                    detect_platform()
                self.assertIn("Apple Silicon", str(ctx.exception))

    def test_try_detect_none_on_linux(self):
        with patch("installer.platform.sys.platform", "linux"):
            with patch("installer.platform.platform.machine", return_value="x86_64"):
                self.assertIsNone(try_detect_platform())


class TestBundledManifest(unittest.TestCase):
    def test_bundled_manifest_loads_and_is_published(self):
        data = load_manifest()
        self.assertEqual(data.get("schema_version"), 1)
        for pid in ("win-amd64", "darwin-arm64"):
            spec = platform_spec(data, pid)
            self.assertTrue(is_published(spec), pid)
            require_published(spec)

    def test_empty_urls_are_unpublished(self):
        spec = PlatformSpec(
            platform_id="win-amd64",
            app=[],
            runtime=[FileSpec("", "", "r.zip", 0)],
            model=ModelSpec(source="huggingface", repo_id="x", revision="main", files=[]),
        )
        self.assertFalse(is_published(spec))
        with self.assertRaises(ManifestError) as ctx:
            require_published(spec)
        self.assertIn("not published", str(ctx.exception).lower())
        self.assertEqual(str(ctx.exception), RELEASE_NOT_PUBLISHED)

    def test_published_when_urls_and_model_files_filled(self):
        spec = PlatformSpec(
            platform_id="win-amd64",
            app=[],
            runtime=[FileSpec("https://example/r.zip", "def", "r.zip", 20)],
            model=ModelSpec(
                source="huggingface",
                repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                revision="main",
                files=[FileSpec("", "aaa", "config.json", 1, path="config.json")],
            ),
        )
        self.assertTrue(is_published(spec))


class TestShaMismatch(unittest.TestCase):
    def test_verify_rejects_bad_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blob.bin"
            path.write_bytes(b"hello")
            with self.assertRaises(DownloadError) as ctx:
                verify_sha256(path, "0" * 64)
            self.assertIn("mismatch", str(ctx.exception).lower())

    def test_sha256_file_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blob.bin"
            data = b"abcdef"
            path.write_bytes(data)
            expected = hashlib.sha256(data).hexdigest()
            self.assertEqual(sha256_file(path), expected)
            verify_sha256(path, expected)


class TestAggregateProgress(unittest.TestCase):
    def test_halfway_first_of_two_equal(self):
        sizes = [100, 100]
        self.assertAlmostEqual(aggregate_progress(0, 50, 100, sizes), 0.25)

    def test_complete_first_file(self):
        sizes = [100, 100]
        self.assertAlmostEqual(aggregate_progress(1, 0, 100, sizes), 0.5)

    def test_all_done(self):
        sizes = [100, 100, 100]
        self.assertAlmostEqual(aggregate_progress(2, 100, 100, sizes), 1.0)


class TestFindQwenPythonProvisioned(unittest.TestCase):
    def test_prefers_provisioned_over_venv(self):
        from tts import client as client_mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / ".videogen" / "runtime" / "qwen" / "darwin-arm64" / "bin"
            root.mkdir(parents=True)
            py = root / "python"
            py.write_text("#!/bin/sh\n", encoding="utf-8")
            py.chmod(0o755)

            venv_py = Path(tmp) / "project" / ".venv-qwen" / "bin" / "python"
            venv_py.parent.mkdir(parents=True)
            venv_py.write_text("#!/bin/sh\n", encoding="utf-8")
            venv_py.chmod(0o755)

            with patch.object(client_mod, "_ROOT", Path(tmp) / "project"):
                with patch("tts.client.Path.home", return_value=home):
                    with patch("tts.client.sys.platform", "darwin"):
                        with patch("tts.client.platform.machine", return_value="arm64"):
                            with patch.dict("os.environ", {}, clear=False):
                                # Ensure env override is not set
                                import os

                                os.environ.pop("QWEN_TTS_PYTHON", None)
                                found = client_mod.find_qwen_python()
            self.assertEqual(found, py)

    def test_env_override_wins(self):
        from tts import client as client_mod

        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom-python"
            custom.write_text("x", encoding="utf-8")
            with patch.dict("os.environ", {"QWEN_TTS_PYTHON": str(custom)}):
                found = client_mod.find_qwen_python()
            self.assertEqual(found, custom)


class TestManifestTempFile(unittest.TestCase):
    def test_load_custom_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "platforms": {
                            "win-amd64": {
                                "app": [],
                                "runtime": [],
                                "model": {
                                    "source": "huggingface",
                                    "repo_id": "x",
                                    "revision": "main",
                                    "files": [],
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            data = load_manifest(path)
            self.assertEqual(data["schema_version"], 1)


class TestDownloadResume(unittest.TestCase):
    def test_http_416_clears_stale_part_and_retries_fresh(self) -> None:
        from unittest.mock import MagicMock, patch

        from installer.download import download_file

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "runtime.zip"
            part = dest.with_name(dest.name + ".part")
            part.write_bytes(b"x" * 100)

            body416 = MagicMock()
            body416.status_code = 416
            body416.__enter__ = lambda s: s
            body416.__exit__ = lambda *a: None

            body200 = MagicMock()
            body200.status_code = 200
            body200.headers = {"Content-Length": "5"}
            body200.iter_content = lambda **k: [b"hello"]
            body200.__enter__ = lambda s: s
            body200.__exit__ = lambda *a: None

            sess = MagicMock()
            sess.get.side_effect = [body416, body200]

            out = download_file(
                "https://example.com/file.zip",
                dest,
                session=sess,
            )
            self.assertTrue(out.is_file())
            self.assertEqual(out.read_bytes(), b"hello")
            self.assertFalse(part.is_file())


class TestSkipDistInfoLicenses(unittest.TestCase):
    def test_skip_predicate(self):
        deep = (
            "python/Lib/site-packages/torch-2.13.0.dist-info/licenses/third_party/"
            "kineto/libkineto/third_party/dynolog/third_party/prometheus-cpp/"
            "3rdparty/googletest/googlemock/scripts/generator/gmock_gen.py"
        )
        self.assertTrue(should_skip_archive_member(deep))
        self.assertTrue(
            should_skip_archive_member(
                r"python\Lib\site-packages\torch-2.13.0.dist-info\licenses\NOTICE"
            )
        )
        self.assertFalse(
            should_skip_archive_member("python/Lib/site-packages/torch/__init__.py")
        )
        self.assertFalse(
            should_skip_archive_member(
                "python/Lib/site-packages/torch-2.13.0.dist-info/METADATA"
            )
        )

    def test_extract_skips_license_trees_keeps_runtime_files(self):
        import zipfile

        deep = (
            "python/Lib/site-packages/torch-2.13.0.dist-info/licenses/third_party/"
            "kineto/libkineto/third_party/dynolog/third_party/prometheus-cpp/"
            "3rdparty/googletest/googlemock/scripts/generator/gmock_gen.py"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "runtime.zip"
            dest = root / "out"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("python/python.exe", b"MZ")
                zf.writestr(
                    "python/Lib/site-packages/torch-2.13.0.dist-info/METADATA",
                    b"Name: torch\n",
                )
                zf.writestr(deep, b"# unused license junk\n")

            extract_archive(archive, dest, clear_dest=True)
            # Single top-level "python/" is unwrapped into dest.
            self.assertTrue((dest / "python.exe").is_file())
            self.assertTrue(
                (
                    dest
                    / "Lib"
                    / "site-packages"
                    / "torch-2.13.0.dist-info"
                    / "METADATA"
                ).is_file()
            )
            self.assertFalse(
                any("licenses" in p.parts for p in dest.rglob("*") if p.is_file())
            )


if __name__ == "__main__":
    unittest.main()
