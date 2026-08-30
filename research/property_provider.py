"""Subprocess/CLI implementation of ResearchProvider — talks to the
standalone semantic-research-engine as an external tool over its existing
CLI. Semantic YT Studio never imports the engine's Python package; the only
contract is its `research.json` / `metadata/media_manifest.json` output
shape (see package_importer.py).

Writes directly into the caller-supplied `output_dir` (the project's
research/ folder) — the engine downloads media there directly, so no
separate copy step is needed to "store research media in the project."
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional

from providers import hidden_subprocess
from research.models import ResearchResult
from research.package_importer import empty_result, load_research_result

DEFAULT_TIMEOUT_SECONDS = 180.0


class PropertyResearchProvider:
    def __init__(self, engine_root: str, engine_python: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        self.engine_root = (engine_root or "").strip()
        self.engine_python = (engine_python or "").strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.engine_root and self.engine_python and Path(self.engine_root).is_dir())

    def research(
        self,
        topic: str,
        script: Optional[str] = None,
        urls: Optional[List[str]] = None,
        domain: str = "auto",
        max_media_per_property: int = 20,
        output_dir: Optional[Path] = None,
    ) -> ResearchResult:
        if not self.is_configured():
            return empty_result(error="Research engine path not configured (see Manual Research settings).")
        if not (topic or "").strip() and not (script or "").strip() and not (urls or []):
            return empty_result(error="Research needs at least a topic, script, or URL.")
        if output_dir is None:
            return empty_result(error="No output directory given for research results.")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        script_file_ctx = tempfile.TemporaryDirectory(prefix="research_script_") if (script or "").strip() else None
        try:
            cmd = [self.engine_python, "-m", "app.cli.main", "research"]
            if (topic or "").strip():
                cmd += ["--topic", topic.strip()]
            if script_file_ctx is not None:
                script_path = Path(script_file_ctx.name) / "script.txt"
                script_path.write_text(script, encoding="utf-8")
                cmd += ["--script", str(script_path)]
            for url in (urls or []):
                if url.strip():
                    cmd += ["--url", url.strip()]
            cmd += [
                "--domain", (domain or "auto").strip() or "auto",
                "--download",
                "--max-media-per-property", str(max(1, int(max_media_per_property or 20))),
                "--output", str(output_dir),
            ]

            try:
                proc = hidden_subprocess.run(
                    cmd, cwd=self.engine_root, capture_output=True, text=True, timeout=self.timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - a failed research run must never raise into the caller
                return empty_result(error=f"Research engine failed to run: {exc}")

            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip()[-800:]
                return empty_result(error=f"Research engine exited with code {proc.returncode}: {tail}")

            return load_research_result(output_dir)
        finally:
            if script_file_ctx is not None:
                script_file_ctx.cleanup()
