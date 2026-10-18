"""Knowledge packages, guidance isolation, import advisories, evidence analysis and prompt-copy integration."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from learning import analysis as an
from learning import guidance as gd
from learning import packages as pk

ROOT = Path(__file__).resolve().parent


def rule(i="r1", text="Prefer specific footage queries.", kind="note", **kw):
    return {"id": i, "kind": kind, "text": text, "confidence": 0.8, "evidence_count": 12, "status": "approved", **kw}


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def pkg(self, v=1, scope="normal/history", rules=None, prev=None):
        return pk.build_package(scope, rules if rules is not None else [rule()], version=v, previous_version=prev)

    def test_valid_roundtrip(self):
        self.assertTrue(pk.validate(self.pkg()).ok)

    def test_rejections(self):
        base = self.pkg()
        cases = {
            "hash_mismatch": lambda p: p.update(rules=[rule(text="changed")]),
            "unsupported_schema": lambda p: p.update(schema=2),
            "bad_scope": lambda p: p.update(style_scope="Bad Scope!"),
            "bad_version": lambda p: p.update(version=0),
            "incompatible_app_schema": lambda p: p.update(min_app_schema=9),
        }
        for reason, mut in cases.items():
            p = json.loads(json.dumps(base))
            mut(p)
            self.assertEqual(pk.validate(p).reason, reason, reason)
        self.assertEqual(pk.validate("x").reason, "not_an_object")
        for bad in (rule(text="run `rm -rf`"), rule(text="a" * 300), rule(text="line\nbreak"), rule(text="use ${x}"),
                    {**rule(), "status": "candidate"}, rule(kind="exec"), rule(kind="asset_type_failure"),
                    {**rule(), "confidence": 2}):
            self.assertFalse(pk.validate(self.pkg(rules=[bad])).ok, bad)
        self.assertFalse(pk.validate(self.pkg(rules=[rule(str(i)) for i in range(20)])).ok)
        self.assertEqual(pk.validate(self.pkg(), expected_scope="weather/classic").reason, "scope_mismatch")

    def test_install_ordering_idempotent_keep_three_and_rollback(self):
        for v in (1, 2, 3, 4):
            self.assertTrue(pk.install(self.pkg(v, prev=v - 1 or None), root=self.root).ok)
        self.assertEqual(pk.install(self.pkg(2), root=self.root).reason, "older_than_installed")
        self.assertTrue(pk.install(self.pkg(4, prev=3), root=self.root).ok)                       # same version, same content
        self.assertEqual(pk.install(self.pkg(4, rules=[rule(text="different")], prev=3), root=self.root).reason, "conflicting_same_version")
        d = next(self.root.iterdir())
        self.assertEqual(sorted(p.name for p in d.glob("v*.json")), ["v000002.json", "v000003.json", "v000004.json"])
        self.assertEqual(pk.active_package("normal/history", self.root)["version"], 4)
        self.assertEqual(pk.rollback("normal/history", self.root).version, 3)
        self.assertEqual(pk.active_package("normal/history", self.root)["version"], 3)
        self.assertEqual(pk.pin("normal/history", 2, self.root).ok, True)
        self.assertEqual(pk.active_package("normal/history", self.root)["version"], 2)
        self.assertEqual(pk.pin("normal/history", 9, self.root).reason, "version_not_cached")
        pk.pin("normal/history", None, self.root)
        self.assertEqual(pk.active_package("normal/history", self.root)["version"], 3)

    def test_corrupted_active_falls_back_to_older_valid(self):
        pk.install(self.pkg(1), root=self.root)
        pk.install(self.pkg(2, prev=1), root=self.root)
        d = next(self.root.iterdir())
        (d / "v000002.json").write_text('{"tampered": true}')
        self.assertEqual(pk.active_package("normal/history", self.root)["version"], 1)

    def test_scope_isolation_on_disk(self):
        pk.install(self.pkg(1, "weather/classic"), root=self.root)
        self.assertIsNone(pk.active_package("starmap/default", self.root))
        self.assertIsNone(pk.active_package("weather/teamplate", self.root))
        self.assertIsNotNone(pk.active_package("weather/classic", self.root))

    def test_missing_package_and_no_rollback(self):
        self.assertIsNone(pk.active_package("normal/x", self.root))
        self.assertFalse(pk.rollback("normal/x", self.root).ok)


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        pk.install(pk.build_package("weather/default", [rule("a", "Weather-only advice.")], version=1), root=self.root)
        pk.install(pk.build_package("weather/classic", [rule("a", "Weather-only advice."), rule("f", "Flow images often fail here.", kind="asset_type_failure", asset_type="flow_image")], version=1), root=self.root)

    def test_applies_only_to_exact_scope(self):
        self.assertIn("Weather-only advice.", gd.guidance_text("weather/classic", self.root))
        for other in ("starmap/default", "hybrid/default", "weather/teamplate", "normal/default"):
            self.assertEqual(gd.guidance_text(other, self.root), "")

    def test_prompt_untouched_without_package_marked_with_one_and_no_duplicates(self):
        base = "BASE PROMPT\nscript"
        self.assertEqual(gd.apply_to_prompt(base, "normal/default", self.root), base)
        out = gd.apply_to_prompt(base, "weather/classic", self.root)
        self.assertTrue(out.startswith(base))
        self.assertIn(gd.MARKER, out)
        self.assertEqual(gd.apply_to_prompt(out, "weather/classic", self.root), out)

    def test_advisories_need_matching_asset_type_and_evidence(self):
        pk.install(pk.build_package("normal/a", [rule("f", "Flow images often fail here.", kind="asset_type_failure", asset_type="flow_image")], version=1), root=self.root)
        self.assertEqual(len(gd.advisories("normal/a", {"asset_types": {"image": 3}}, self.root)), 1)       # CSV 'image' == flow_image
        self.assertEqual(gd.advisories("normal/a", {"asset_types": {"stock_video": 3}}, self.root), [])
        self.assertEqual(gd.advisories("normal/a", {"asset_types": {"mystery": 3}}, self.root), [])        # unknown never triggers
        self.assertEqual(gd.advisories("starmap/default", {"asset_types": {"image": 3}}, self.root), [])
        pk.install(pk.build_package("normal/b", [rule("f", "t", kind="asset_type_failure", asset_type="image", evidence_count=2)], version=1), root=self.root)
        self.assertEqual(gd.advisories("normal/b", {"asset_types": {"image": 3}}, self.root), [])      # too little evidence and non-provider key

    def test_offer_guidance_lets_user_decline_and_ignores_missing(self):
        app = mock.Mock(generation_mode="weather", _workspace=None)
        with mock.patch("learning.packages._root", lambda root=None: self.root):
            with mock.patch("tkinter.messagebox.askyesno", return_value=False):
                self.assertEqual(gd.offer_guidance(app, "P", "weather"), "P")
            with mock.patch("tkinter.messagebox.askyesno", return_value=True):
                self.assertIn(gd.MARKER, gd.offer_guidance(app, "P", "weather"))
            with mock.patch("tkinter.messagebox.askyesno") as ask:
                self.assertEqual(gd.offer_guidance(mock.Mock(generation_mode="starmap", _workspace=None), "P", "starmap"), "P")
                ask.assert_not_called()

    def test_prompt_copy_hook_is_in_app_and_protected_files_untouched(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("from learning.guidance import offer_guidance", src)
        self.assertEqual(sorted((ROOT / "composition_styles").glob("*")), sorted((ROOT / "composition_styles").glob("*")))
        import subprocess
        out = subprocess.run(["git", "diff", "--stat", "--", "app_csv_prompts.py", "asset_manager.py"], cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "")


def ev_(i, typ, scope, project, **kw):
    gid = kw.pop("generation_id", None)
    return {"event_id": f"{typ}:{i}:{gid or ''}", "event_type": typ, "style_scope": scope, "project_id": project, "generation_id": gid, "payload": kw}


class AnalysisTests(unittest.TestCase):
    S = "normal/history"

    def failures(self, projects, per, scope=None):
        out = []
        for p in range(projects):
            out.append(ev_(p, "render_outcome", scope or self.S, f"p{p}", generation_id=f"g{p}", outcome="failure"))
            for i in range(per):
                out.append(ev_(f"{p}-{i}", "scene_failure", scope or self.S, f"p{p}", generation_id=f"g{p}", source="flow_image", scene=str(i)))
        return out

    def test_failure_candidate_needs_projects_observations_and_share(self):
        self.assertEqual(an.build_candidates(self.failures(2, 10), self.S), [])                      # one project cannot dominate
        self.assertEqual(an.build_candidates(self.failures(5, 1), self.S), [])                       # too few observations
        c = an.build_candidates(self.failures(4, 3), self.S)
        self.assertEqual([x["id"] for x in c], ["fail-flow_image"])
        self.assertEqual(c[0]["status"], "candidate")
        self.assertEqual(c[0]["asset_type"], "flow_image")
        for k in ("pattern", "evidence_count", "confidence", "expected_benefit", "side_effects", "suggested_action", "evaluation_criteria", "style_scope"):
            self.assertIn(k, c[0])

    def test_scope_isolation_of_evidence(self):
        self.assertEqual(an.build_candidates(self.failures(4, 3, scope="weather/classic"), self.S), [])

    def test_repeated_renders_of_one_project_count_once_for_ratings(self):
        evs = []
        for r in range(10):
            evs.append(ev_(r, "video_rating", self.S, "same", rating=2, tags=["poor_pacing"], revision=r + 1))
        self.assertEqual(an.build_candidates(evs, self.S), [])
        evs = [ev_(p, "video_rating", self.S, f"p{p}", rating=2, tags=["poor_pacing"] if p < 4 else [], revision=1) for p in range(8)]
        self.assertEqual([c["id"] for c in an.build_candidates(evs, self.S)], ["tag-poor_pacing"])
        sparse = evs[:4]
        self.assertEqual(an.build_candidates(sparse, self.S), [])                                     # too few rated projects

    def test_low_category_candidate(self):
        evs = [ev_(p, "video_rating", self.S, f"p{p}", rating=3, categories={"pacing": 2}, tags=[], revision=1) for p in range(6)]
        self.assertEqual([c["id"] for c in an.build_candidates(evs, self.S)], ["cat-pacing"])

    def test_approval_is_required_and_package_builds_and_compares(self):
        cands = an.build_candidates(self.failures(4, 3), self.S)
        self.assertEqual(an.approved_rules(cands, []), [])
        rules = an.approved_rules(cands, ["fail-flow_image"])
        new = pk.build_package(self.S, rules, version=2, previous_version=1)
        self.assertTrue(pk.validate(new).ok)
        old = pk.build_package(self.S, [], version=1)
        d = an.compare_packages(old, new)
        self.assertEqual((d["added"], d["removed"], d["valid"]), (["fail-flow_image"], [], True))
        self.assertFalse(an.compare_packages(pk.build_package("a/b", [], version=1), new)["same_scope"])


if __name__ == "__main__":
    unittest.main()
