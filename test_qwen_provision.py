"""Unit tests for in-app Qwen provision (mocked; no multi-GB downloads)."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from installer.manifest import FileSpec, ModelSpec, PlatformSpec, resolve_model_downloads
from tts.qwen_provision import (
    ProvisionCancelled,
    ProvisionError,
    build_qwen_plan,
    friendly_provision_error,
    is_qwen_locally_ready,
    provision_qwen,
    runtime_and_model_ready,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


class TestRuntimeAndModelReady(unittest.TestCase):
    def test_ignores_empty_app(self):
        spec = PlatformSpec(
            platform_id="darwin-arm64",
            app=[],  # app ignored for in-app flow
            runtime=[FileSpec("https://example/r.zip", "abc", "r.zip", 10)],
            model=ModelSpec(
                source="huggingface",
                repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                revision="main",
                files=[FileSpec("", "def", "config.json", 1, path="config.json")],
            ),
        )
        self.assertTrue(runtime_and_model_ready(spec))

    def test_rejects_missing_runtime_url(self):
        spec = PlatformSpec(
            platform_id="win-amd64",
            app=[],
            runtime=[FileSpec("", "abc", "r.zip", 10)],
            model=ModelSpec(
                source="huggingface",
                repo_id="x",
                revision="main",
                files=[FileSpec("", "def", "config.json", 1, path="config.json")],
            ),
        )
        self.assertFalse(runtime_and_model_ready(spec))


class TestBuildQwenPlan(unittest.TestCase):
    def test_plan_excludes_app_includes_runtime_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "m.json"
            runtime_url = "https://example.test/runtime.zip"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "platforms": {
                            "darwin-arm64": {
                                "app": [
                                    {
                                        "url": "https://example.test/app.zip",
                                        "sha256": "a" * 64,
                                        "filename": "app.zip",
                                        "size": 1,
                                    }
                                ],
                                "runtime": [
                                    {
                                        "url": runtime_url,
                                        "sha256": "b" * 64,
                                        "filename": "runtime.zip",
                                        "size": 100,
                                    }
                                ],
                                "model": {
                                    "source": "huggingface",
                                    "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                                    "revision": "main",
                                    "files": [
                                        {
                                            "path": "config.json",
                                            "filename": "config.json",
                                            "url": "",
                                            "sha256": "c" * 64,
                                            "size": 10,
                                        }
                                    ],
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            plan = build_qwen_plan(manifest_path=manifest, platform_id="darwin-arm64")
            phases = [p for p, _ in plan.downloads]
            self.assertEqual(phases, ["runtime", "model"])
            self.assertEqual(plan.downloads[0][1].url, runtime_url)
            self.assertIn("huggingface.co", plan.downloads[1][1].url)


class TestProvisionQwen(unittest.TestCase):
    def test_idempotent_when_ready(self):
        statuses: list[str] = []
        with patch("tts.qwen_provision.is_qwen_locally_ready", return_value=True):
            with patch("tts.qwen_provision.build_qwen_plan") as build:
                build.return_value = MagicMock(platform_id="darwin-arm64", downloads=[], sizes=[])
                plan = provision_qwen(status=statuses.append, progress=lambda _: None)
        self.assertTrue(statuses)
        self.assertIn("already", statuses[-1].lower())
        self.assertIs(plan, build.return_value)

    def test_downloads_runtime_and_model_with_mocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cache = home / ".videogen" / "installer-cache"
            model_dest = home / ".videogen" / "qwen3-tts" / "Qwen3-TTS-12Hz-1.7B-Base"
            runtime_dest = home / ".videogen" / "runtime" / "qwen" / "darwin-arm64"

            config_bytes = b'{"ok": true}\n'
            config_sha = _sha(config_bytes)

            zip_path = Path(tmp) / "runtime.zip"
            with tempfile.TemporaryDirectory() as ztmp:
                root = Path(ztmp) / "payload"
                bin_dir = root / "bin"
                bin_dir.mkdir(parents=True)
                py = bin_dir / "python3"
                py.write_bytes(b"#!/bin/sh\necho ok\n")
                py.chmod(0o755)
                _write_zip(
                    zip_path,
                    {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()},
                )
            runtime_archive_bytes = zip_path.read_bytes()
            runtime_sha = _sha(runtime_archive_bytes)

            manifest = Path(tmp) / "m.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "platforms": {
                            "darwin-arm64": {
                                "app": [],
                                "runtime": [
                                    {
                                        "url": "https://example.test/runtime.zip",
                                        "sha256": runtime_sha,
                                        "filename": "runtime.zip",
                                        "size": len(runtime_archive_bytes),
                                    }
                                ],
                                "model": {
                                    "source": "huggingface",
                                    "repo_id": "local/test",
                                    "revision": "main",
                                    "files": [
                                        {
                                            "path": "config.json",
                                            "filename": "config.json",
                                            "url": "https://example.test/config.json",
                                            "sha256": config_sha,
                                            "size": len(config_bytes),
                                        }
                                    ],
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            def fake_download(url, dest, **kwargs):
                dest = Path(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if str(url).endswith("runtime.zip"):
                    dest.write_bytes(runtime_archive_bytes)
                else:
                    dest.write_bytes(config_bytes)
                if kwargs.get("progress"):
                    size = dest.stat().st_size
                    kwargs["progress"](size, size)
                return dest

            progress_vals: list[float] = []
            with patch("tts.qwen_provision.is_qwen_locally_ready", return_value=False):
                with patch("tts.qwen_provision.download_cache_dir", return_value=cache):
                    with patch("tts.qwen_provision.model_root", return_value=model_dest):
                        with patch("tts.qwen_provision.runtime_root", return_value=runtime_dest):
                            with patch("tts.qwen_provision.download_file", side_effect=fake_download):
                                with patch(
                                    "tts.qwen_provision.model_is_installed",
                                    side_effect=[False, True],
                                ):
                                    with patch(
                                        "tts.qwen_provision.provisioned_python",
                                        side_effect=[None, runtime_dest / "bin" / "python3"],
                                    ):
                                        with patch(
                                            "tts.qwen_provision.estimate_totals",
                                            side_effect=lambda plan, session=None: plan.sizes,
                                        ):
                                            provision_qwen(
                                                manifest_path=manifest,
                                                platform_id="darwin-arm64",
                                                progress=progress_vals.append,
                                            )

            self.assertTrue(
                (runtime_dest / "bin" / "python3").is_file()
                or (runtime_dest / "python3").is_file()
            )
            self.assertTrue((model_dest / "config.json").is_file())
            self.assertTrue(progress_vals)
            self.assertAlmostEqual(progress_vals[-1], 1.0)


    def test_cancel_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "m.json"
            blob = b"x" * 20
            sha = _sha(blob)
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "platforms": {
                            "darwin-arm64": {
                                "app": [],
                                "runtime": [
                                    {
                                        "url": "https://example.test/runtime.zip",
                                        "sha256": sha,
                                        "filename": "runtime.zip",
                                        "size": len(blob),
                                    }
                                ],
                                "model": {
                                    "source": "huggingface",
                                    "repo_id": "local/test",
                                    "revision": "main",
                                    "files": [
                                        {
                                            "path": "config.json",
                                            "filename": "config.json",
                                            "url": "https://example.test/config.json",
                                            "sha256": sha,
                                            "size": len(blob),
                                        }
                                    ],
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("tts.qwen_provision.is_qwen_locally_ready", return_value=False):
                with patch("tts.qwen_provision.provisioned_python", return_value=None):
                    with patch("tts.qwen_provision.model_is_installed", return_value=False):
                        with patch("tts.qwen_provision.estimate_totals", side_effect=lambda plan, session=None: plan.sizes):
                            with self.assertRaises(ProvisionCancelled):
                                provision_qwen(
                                    manifest_path=manifest,
                                    platform_id="darwin-arm64",
                                    should_stop=lambda: True,
                                )


class TestFriendlyError(unittest.TestCase):
    def test_cancelled(self):
        self.assertIn("cancelled", friendly_provision_error(ProvisionCancelled("stop")).lower())

    def test_provision_error(self):
        self.assertEqual(friendly_provision_error(ProvisionError("boom")), "boom")


class TestResolveModelUrls(unittest.TestCase):
    def test_fills_hf_url(self):
        spec = PlatformSpec(
            platform_id="win-amd64",
            app=[],
            runtime=[],
            model=ModelSpec(
                source="huggingface",
                repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                revision="main",
                files=[FileSpec("", "aaa", "config.json", 1, path="config.json")],
            ),
        )
        files = resolve_model_downloads(spec)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].url.startswith("https://huggingface.co/"))


class TestIsLocallyReady(unittest.TestCase):
    def test_false_without_python(self):
        with patch("tts.qwen_provision.detect_platform", return_value="darwin-arm64"):
            with patch("tts.qwen_provision.provisioned_python", return_value=None):
                self.assertFalse(is_qwen_locally_ready())


if __name__ == "__main__":
    unittest.main()
