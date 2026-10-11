"""Enoch Template, Phase 0: the safety net the later phases are built on. No product code is involved.

  1. `styles/book_of_enoch.json` is byte-identical (CRLF-normalised sha256).
  2. Every file the Enoch Template work must not touch still hashes as recorded in test_fixtures/enoch_template_protected.json
     (providers, Flow, AI router, allocation, editorial, graphics, style engine, Modern Tech, the renderer, every existing style),
     and no new module appeared inside the protected packages. The guard is active until the Enoch Template work is finished.
  3. The set of styles is the baseline set (plus, later, `enoch_template` and nothing else), and no script can make auto-detection
     pick Book of Enoch or Enoch Template: both are manual-only.
  4. The zero-cost sentinel (enoch_template_testutil.NoPaidCalls) really refuses external network, Flow, AI-router and
     Node/Chrome launches, and really allows this machine.
  5. The `app.py` sites the later phases extend still exist where the specification says (so a refactor cannot move them unnoticed).
"""

from __future__ import annotations

import json
import socket
import subprocess
import unittest
from pathlib import Path

from enoch_template_testutil import NoPaidCalls, PaidCallAttempt, normalized_sha256

ROOT = Path(__file__).resolve().parent
BOOK_OF_ENOCH_SHA256 = "93e318447adbb417a4234012064f1ef844d7475cdd86d031481600f77385443a"
BASELINE_STYLE_IDS = frozenset({
    "ai_narration", "ancient_history_documentary", "biography_documentary", "book_of_enoch", "business_economics_documentary",
    "educational_explainer", "future_tech_documentary", "geopolitics_documentary", "history_documentary", "military_war_documentary",
    "mystery_documentary", "nature_wildlife_documentary", "news_current_affairs", "ocean_marine_documentary", "premium_documentary",
    "science_documentary", "space_documentary", "technology_documentary", "true_crime_documentary",
})
NEW_STYLE_IDS = frozenset({"enoch_template"})                     # the only style the Enoch Template work may add
PROTECTED_PY_PACKAGES = ("modern_tech", "style_engine", "visual_allocation", "editorial", "graphics", "typography", "providers",
                         "production", "ai_router")


def _manifest() -> dict:
    return json.loads((ROOT / "test_fixtures" / "enoch_template_protected.json").read_text(encoding="utf-8"))["files"]


class BookOfEnochUnchanged(unittest.TestCase):
    def test_byte_identical(self):
        self.assertEqual(normalized_sha256(ROOT / "styles" / "book_of_enoch.json"), BOOK_OF_ENOCH_SHA256)

    def test_its_visual_guide_is_unchanged_too(self):
        recorded = _manifest()["docs/styles/book_of_enoch_visual_guide.md"]
        self.assertEqual(normalized_sha256(ROOT / "docs" / "styles" / "book_of_enoch_visual_guide.md"), recorded)


class ProtectedFiles(unittest.TestCase):
    def test_nothing_protected_changed_or_disappeared(self):
        changed, missing = [], []
        for rel, sha in _manifest().items():
            path = ROOT / rel
            if not path.is_file():
                missing.append(rel)
            elif normalized_sha256(path) != sha:
                changed.append(rel)
        self.assertEqual((changed, missing), ([], []),
                         "protected files differ from test_fixtures/enoch_template_protected.json (a deliberate, approved change "
                         "means refreshing that manifest in the same reviewed diff)")

    def test_no_new_module_inside_a_protected_package(self):
        recorded = set(_manifest())
        extra = []
        for pkg in PROTECTED_PY_PACKAGES:
            for path in (ROOT / pkg).rglob("*.py"):
                rel = path.relative_to(ROOT).as_posix()
                if "__pycache__" not in rel and rel not in recorded:
                    extra.append(rel)
        self.assertEqual(extra, [], "new modules belong in ancient_texts/, not in a protected package")

    def test_other_styles_are_in_the_manifest(self):
        styles = {p for p in _manifest() if p.startswith("styles/")}
        on_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / "styles").glob("*.json")} - {"styles/enoch_template.json"}
        self.assertEqual(styles, on_disk)


class StyleRegistry(unittest.TestCase):
    def test_style_ids_are_the_baseline_plus_at_most_enoch_template(self):
        ids = {json.loads(p.read_text(encoding="utf-8"))["id"] for p in (ROOT / "styles").glob("*.json")}
        self.assertTrue(BASELINE_STYLE_IDS <= ids, f"a baseline style disappeared: {sorted(BASELINE_STYLE_IDS - ids)}")
        self.assertTrue((ids - BASELINE_STYLE_IDS) <= NEW_STYLE_IDS, f"unexpected new style(s): {sorted(ids - BASELINE_STYLE_IDS - NEW_STYLE_IDS)}")

    def test_manual_only_styles_are_never_auto_detected(self):
        from style_engine.detect import detect_style

        scripts = [
            "The Book of Enoch tells of the Watchers who descended on Mount Hermon, and of the Ethiopic manuscripts and Dead Sea Scrolls "
            "that kept it. Scholars such as Nickelsburg and VanderKam studied the Son of Man chapters.",
            "Ancient manuscripts, the Qumran caves and Gustave Doré engravings; a documentary about a hidden biblical text.",
            "Enoch walked with God and was not, for God took him.",
        ]
        for text in scripts:
            style = detect_style(script=text)[0]
            self.assertNotIn(style.id, {"book_of_enoch", "enoch_template"}, text[:40])

    def test_book_of_enoch_stays_manual_only(self):
        from style_engine.loader import load_style

        style = load_style("book_of_enoch")
        self.assertEqual(style.intelligence.weights, {})


class ZeroCostSentinel(unittest.TestCase):
    def test_external_connection_is_refused_and_counted(self):
        guard = NoPaidCalls()
        with guard:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with self.assertRaises(PaidCallAttempt):
                    s.connect(("93.184.216.34", 443))
            finally:
                s.close()
        self.assertEqual(len(guard.attempts), 1)
        with self.assertRaises(PaidCallAttempt):
            guard.assert_clean()

    def test_dns_lookup_of_an_external_host_is_refused(self):
        with NoPaidCalls() as guard:
            with self.assertRaises(PaidCallAttempt):
                socket.getaddrinfo("example.com", 443)
        self.assertEqual(len(guard.attempts), 1)

    def test_this_machine_stays_reachable(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        try:
            with NoPaidCalls() as guard:
                client = socket.create_connection(server.getsockname(), timeout=5)
                client.close()
            guard.assert_clean()
        finally:
            server.close()

    def test_node_and_chrome_launches_are_refused_but_ffmpeg_is_not(self):
        with NoPaidCalls() as guard:
            for program in ("node", "/usr/bin/chromium", "chrome.exe"):
                with self.assertRaises(PaidCallAttempt):
                    subprocess.Popen([program, "--version"])
        self.assertEqual(len(guard.attempts), 3)
        with NoPaidCalls() as guard:                                    # a harmless local program is untouched
            proc = subprocess.Popen(["python3", "-c", "pass"], stdout=subprocess.DEVNULL)
            proc.wait()
        guard.assert_clean()

    def test_flow_and_ai_router_calls_are_refused(self):
        from ai_router.providers import GeminiProvider
        from providers.flow.client import FlowClient
        from providers.flow.provider import FlowProvider

        with NoPaidCalls() as guard:
            for call in (lambda: FlowProvider.resolve(None, None, None), lambda: FlowProvider.resolve_batch(None, [], None),
                         lambda: FlowClient.generate(None), lambda: GeminiProvider.complete(None, "", "", model="x")):
                with self.assertRaises(PaidCallAttempt):
                    call()
        self.assertEqual(len(guard.attempts), 4)

    def test_everything_is_restored_after_the_block(self):
        from providers.flow.provider import FlowProvider

        before = FlowProvider.resolve
        before_connect = socket.socket.connect
        with NoPaidCalls():
            pass
        self.assertIs(FlowProvider.resolve, before)
        self.assertIs(socket.socket.connect, before_connect)


class HookSitesStillWhereTheSpecSays(unittest.TestCase):
    """The additive insertion sites of the later phases (specification, Part 10). If one moves, this fails first."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "app.py").read_text(encoding="utf-8")

    def test_picker_and_selection(self):
        for needle in ('STYLE_CHOICES = ("Normal video", "Modern Tech News"', "def _active_style(self)", "def _modern_tech_on(self)",
                       "def _on_style_pick(self, choice: str)", 'ws.set_editing_system("modern_tech" if choice == "Modern Tech News" else "")'):
            self.assertIn(needle, self.src)

    def test_plan_paths(self):
        for needle in ("modern_tech = self._modern_tech_on()", "guidance = style_prompt_adornment(resolved)",
                       "def _enforce_asset_mix_on_csv(self, csv_path: Path)", "self._enrich_entity_prompts(mixed)", "mixed.write_csv(csv_path)",
                       "self._enrich_entity_prompts(plan)"):
            self.assertIn(needle, self.src)

    def test_smart_editing_settings_and_csv_prompt(self):
        for needle in ("def _render_smart_editing_settings(self)", '"smart_editing": self._render_smart_editing_settings()',
                       "def _copy_csv_prompt(self, style: str", "text = build_prompt(style, script)"):
            self.assertIn(needle, self.src)
        self.assertIn("CSV_PROMPTS = {", (ROOT / "app_csv_prompts.py").read_text(encoding="utf-8"))

    def test_audio_chain_has_no_loudness_stage_today(self):
        """The finishing step is new and opt-in; today's render chain must stay as it is (amix, plain gains, no loudnorm)."""
        render = (ROOT / "video_generator.py").read_text(encoding="utf-8")
        self.assertIn("amix=inputs=2:duration=first:dropout_transition=0:normalize=0", render)
        for stage in ("loudnorm", "alimiter", "dynaudnorm"):
            self.assertNotIn(stage, render)


if __name__ == "__main__":
    unittest.main()
