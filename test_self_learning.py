"""Self-Learning V1. ALL project data below is SYNTHETIC (generated in temp folders by these tests); no real project is read."""
import csv
import hashlib
import io
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from csv_generator import GenerationOptions, generate
from learning import analysis, csv_analyzer, events as ev, ledger as lg, packages as pk, review
from learning.scope import resolve_scope
from project_workspace import create_project

SCRIPT = ("Crews ran across the deck as the steel began to fall. Workers built a new frame and the river flowed fast. "
          "Engineers raced to fight the fire and travel north. ") * 60


def csv_text(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["scene_number", "script_segment", "asset_type", "prompt"])
    for i, (words, at) in enumerate(rows, 1):
        w.writerow([i, " ".join(["word"] * words), at, f"query {i}"])
    return buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "projects"
        self.pkg_root = self.dir / "k"
        self.led = lg.Ledger(self.dir / "l.sqlite")
        lg.set_default_ledger(self.led)
        self.addCleanup(lg.set_default_ledger, None)
        p = mock.patch("learning.packages._root", lambda r=None: self.pkg_root)
        p.start()
        self.addCleanup(p.stop)

    def project(self, title, text, style_id=None, rating=None, render_ok=True):
        ws = create_project(title, projects_root=self.root)
        ws.ensure_dirs()
        ws.csv_path.write_text(text, encoding="utf-8")
        if style_id:
            ws.set_video_style_settings(mode="manual", style_id=style_id)
        scope = resolve_scope(None, "normal", workspace=ws)
        if render_ok is not None:
            ev.record_event("render_outcome", style_scope=scope, project_id=ws.project_id, generation_id="g-" + ws.project_id, ledger=self.led,
                            payload={"outcome": "success" if render_ok else "failure"})
        if rating:
            self.assertTrue(ev.record_video_rating(ws.project_id, scope, rating, generation_id="g-" + ws.project_id, ledger=self.led).ok)
        return ws, scope

    def seed_pacing(self, style_id="p"):
        for i in range(4):
            self.project(f"short{i}", csv_text([(20, "stock_video" if k % 2 else "stock_image") for k in range(12)]), style_id, rating=5)
        for i in range(4):
            self.project(f"long{i}", csv_text([(70, "stock_video" if k % 2 else "stock_image") for k in range(12)]), style_id, rating=3)
        return f"normal/{style_id}"

    def seed_variety(self, style_id="v"):
        for i in range(4):
            self.project(f"rep{i}", csv_text([(40, "stock_video")] * 12), style_id, rating=2)
        for i in range(4):
            self.project(f"var{i}", csv_text([(40, "stock_video" if k % 2 else "stock_image") for k in range(12)]), style_id, rating=4)
        return f"normal/{style_id}"


class AnalyzerTests(Base):
    def test_features_measured_and_unavailable_fields_are_none(self):
        f = csv_analyzer.features(csv_text([(10, "stock_video"), (30, "stock_video"), (20, "image")]))
        self.assertEqual((f["rows"], f["words_max"], f["max_same_type_run"]), (3, 30, 2))
        self.assertEqual(f["asset_counts"], {"stock_video": 2, "image": 1})
        plain = csv_analyzer.features("scene_number,script_segment\n1,hello there\n2,bye\n")
        self.assertIsNone(plain["asset_counts"])
        self.assertIsNone(plain["max_same_type_run"])
        self.assertIsNone(plain["duplicate_prompt_share"])
        self.assertEqual(plain["rows"], 2)

    def test_scan_is_read_only_idempotent_and_incremental(self):
        ws, scope = self.project("a", csv_text([(20, "stock_video")] * 5))
        before = hashlib.sha256(ws.csv_path.read_bytes()).hexdigest()
        mtime = ws.csv_path.stat().st_mtime_ns
        s1 = csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual((s1["projects"], s1["analyzed_new"]), (1, 1))
        n_events = len(self.led.events(event_type="csv_analysis"))
        with mock.patch.object(csv_analyzer, "features", side_effect=AssertionError("re-read an unchanged CSV")):
            s2 = csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual((s2["analyzed_new"], s2["unchanged"]), (0, 1))
        self.assertEqual(len(self.led.events(event_type="csv_analysis")), n_events)
        self.assertEqual(hashlib.sha256(ws.csv_path.read_bytes()).hexdigest(), before)
        self.assertEqual(ws.csv_path.stat().st_mtime_ns, mtime)
        ws.csv_path.write_text(csv_text([(20, "stock_video")] * 6), encoding="utf-8")                 # real change -> one new event
        self.assertEqual(csv_analyzer.scan_projects(self.root, ledger=self.led)["analyzed_new"], 1)
        # same bytes re-written -> same sha -> same event id -> no inflation
        ws.csv_path.write_text(csv_text([(20, "stock_video")] * 6), encoding="utf-8")
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual(len(self.led.events(event_type="csv_analysis")), n_events + 1)

    def test_other_schemas_are_counted_not_read(self):
        ws, _ = self.project("p", csv_text([(20, "stock_video")]))
        ws.pakmap_csv_path.write_text("item_no,vo_anchor,layer_type\n1,x,hud_title\n", encoding="utf-8")
        s = csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual(s["unsupported_schema"], 1)
        self.assertEqual(len(self.led.events(event_type="csv_analysis")), 1)

    def test_status_and_stale_flag(self):
        self.assertTrue(csv_analyzer.status(self.led)["stale"])
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        st = csv_analyzer.status(self.led)
        self.assertFalse(st["stale"])
        self.assertTrue(st["last_run"])
        ev.record_event("render_outcome", style_scope="normal/x", ledger=self.led)
        self.assertTrue(csv_analyzer.status(self.led)["stale"])

    def test_large_collection_cancellation_and_recovery(self):
        for i in range(250):
            self.project(f"p{i}", csv_text([(20 + i % 7, "stock_video")] * 3), render_ok=None)
        cancel = threading.Event()
        seen = []

        def prog(f, m):
            seen.append(m)
            if len(seen) == 3:
                cancel.set()
        t0 = time.time()
        part = csv_analyzer.scan_projects(self.root, ledger=self.led, cancel=cancel, progress=prog)
        self.assertTrue(part["cancelled"])
        self.assertLess(part["projects"], 250)
        done_so_far = len(self.led.events(event_type="csv_analysis", limit=10000))
        full = csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertFalse(full["cancelled"])
        self.assertEqual(len(self.led.events(event_type="csv_analysis", limit=10000)), 250)
        self.assertEqual(done_so_far + full["analyzed_new"], 250)           # nothing double counted across the interruption
        self.assertLess(time.time() - t0, 60)

    def test_errors_never_raise(self):
        self.assertEqual(csv_analyzer.scan_projects(self.dir / "does-not-exist", ledger=self.led)["projects"], 0)
        ws, _ = self.project("bad", "x")
        ws.csv_path.write_bytes(b"\xff\xfe\x00bad\x00bytes\n,,,\n")
        s = csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertIsNone(s["error"])


class DiscoveryTests(Base):
    def test_thresholds_and_missing_ratings_are_not_negative(self):
        for i in range(2):
            self.project(f"s{i}", csv_text([(20, "stock_video")] * 6), "q", rating=5)
        for i in range(2):
            self.project(f"l{i}", csv_text([(70, "stock_video")] * 6), "q", rating=3)
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual([c for c in review.suggestions(self.led) if c["style_scope"] == "normal/q"], [])      # too few rated projects
        for i in range(6):                                                                                      # unrated projects: ignored
            self.project(f"u{i}", csv_text([(90, "stock_video")] * 6), "q", rating=None, render_ok=False)
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual([c for c in review.suggestions(self.led) if c["style_scope"] == "normal/q"], [])

    def test_pacing_candidate_has_full_evidence_and_states_association(self):
        scope = self.seed_pacing()
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        c = next(x for x in review.suggestions(self.led) if x["id"] == "pace-shorter")
        self.assertEqual(c["style_scope"], scope)
        self.assertEqual(c["kind"], "pacing_target")
        self.assertTrue(12 <= c["param"] <= 30)
        self.assertEqual(c["evidence_count"], 8)
        self.assertIn("Association only", c["pattern"])
        for k in ("confidence", "expected_benefit", "side_effects", "evaluation_criteria", "suggested_action"):
            self.assertTrue(c[k])
        self.assertEqual(c["status"], "candidate")
        self.assertEqual(review.approved(), {})                         # nothing approved automatically

    def test_variety_candidate(self):
        scope = self.seed_variety()
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        c = next(x for x in review.suggestions(self.led) if x["id"] == "variety-run2")
        self.assertEqual((c["style_scope"], c["param"]), (scope, 2))

    def test_one_project_many_ratings_or_reimports_is_one_vote(self):
        scope = self.seed_pacing("one")
        ws, _ = self.project("dup", csv_text([(20, "stock_video")] * 6), "dupstyle", rating=1)
        for r in (1, 2, 1, 2, 1):
            ev.record_video_rating(ws.project_id, "normal/dupstyle", r, generation_id="g-" + ws.project_id, ledger=self.led)
        for _ in range(5):
            ws.csv_path.write_text(csv_text([(20, "stock_video")] * 6), encoding="utf-8")
            csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual([c for c in review.suggestions(self.led) if c["style_scope"] == "normal/dupstyle"], [])
        # the same data copied into a second project IS independent evidence (it is a different project)
        evs = self.led.events(limit=10000)
        c = analysis.build_candidates(evs, scope)
        self.assertEqual(next(x for x in c if x["id"] == "pace-shorter")["evidence_count"], 8)

    def test_styles_do_not_contaminate_each_other(self):
        self.seed_pacing("a")
        for i in range(4):
            self.project(f"b{i}", csv_text([(20, "stock_video")] * 6), "b", rating=5)
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        scopes = {c["style_scope"] for c in review.suggestions(self.led)}
        self.assertEqual(scopes, {"normal/a"})


class ApprovalAndGenerationTests(Base):
    def approve(self, cid, scope):
        cand = next(c for c in review.suggestions(self.led) if c["id"] == cid and c["style_scope"] == scope)
        res = review.decide(cand, "approve", self.led)
        self.assertTrue(res.ok, res.reason)
        return cand

    def runs(self, rows):
        best = run = 0
        prev = None
        for r in rows:
            run = run + 1 if r["asset_type"] == prev else 1
            prev = r["asset_type"]
            best = max(best, run)
        return best

    def test_approved_variety_rule_changes_generated_output_measurably(self):
        scope = self.seed_variety()
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        opts = GenerationOptions(enabled_types=("stock_video", "stock_image", "video"))
        before = generate(SCRIPT, "normal", opts, scope=scope, knowledge_root=self.pkg_root)
        self.approve("variety-run2", scope)
        after = generate(SCRIPT, "normal", opts, scope=scope, knowledge_root=self.pkg_root)
        self.assertGreater(self.runs(before.rows), 2)
        self.assertLessEqual(self.runs(after.rows), 2)
        self.assertTrue(before.ok and after.ok)
        self.assertEqual(" ".join(r["script_segment"] for r in after.rows).split(), SCRIPT.split())       # narration intact
        self.assertEqual(after.applied_knowledge, ["variety-run2: at most 2 same-type scenes in a row"])    # auditable
        self.assertEqual(before.applied_knowledge, [])
        again = generate(SCRIPT, "normal", opts, scope=scope, knowledge_root=self.pkg_root)
        self.assertEqual(again.csv_text, after.csv_text)                                                    # deterministic

    def test_approved_pacing_rule_shrinks_scenes_but_never_exceeds_the_users_choice(self):
        scope = self.seed_pacing()
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        cand = self.approve("pace-shorter", scope)
        base = generate(SCRIPT, "normal", GenerationOptions(target_words=60))
        tuned = generate(SCRIPT, "normal", GenerationOptions(target_words=60), scope=scope, knowledge_root=self.pkg_root)
        mean = lambda r: sum(len(x["script_segment"].split()) for x in r.rows) / len(r.rows)
        self.assertLess(mean(tuned), mean(base))
        self.assertGreater(len(tuned.rows), len(base.rows))
        small = generate(SCRIPT, "normal", GenerationOptions(target_words=15), scope=scope, knowledge_root=self.pkg_root)
        self.assertLessEqual(mean(small), mean(generate(SCRIPT, "normal", GenerationOptions(target_words=15))) + 0.01)   # cap only lowers
        self.assertTrue(tuned.ok)

    def test_wrong_scope_never_applies(self):
        scope = self.seed_variety()
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.approve("variety-run2", scope)
        opts = GenerationOptions(enabled_types=("stock_video", "stock_image", "video"))
        other = generate(SCRIPT, "normal", opts, scope="normal/other", knowledge_root=self.pkg_root)
        self.assertEqual(other.applied_knowledge, [])
        self.assertGreater(self.runs(other.rows), 2)
        self.assertEqual(generate(SCRIPT, "overscaled", opts, scope="overscaled/overscaled", knowledge_root=self.pkg_root).applied_knowledge, [])

    def test_reject_defer_disable_rollback(self):
        scope = self.seed_variety()
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        cand = next(c for c in review.suggestions(self.led) if c["id"] == "variety-run2")
        review.decide(cand, "defer", self.led)
        self.assertIn("variety-run2", [c["id"] for c in review.suggestions(self.led)])               # deferred stays listed
        review.decide(cand, "reject", self.led)
        self.assertNotIn("variety-run2", [c["id"] for c in review.suggestions(self.led)])
        self.assertEqual(review.approved(), {})
        # approve another style's rule twice-versioned, then disable and roll back
        s2 = self.seed_pacing()
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.approve("pace-shorter", s2)
        self.assertEqual([r["id"] for r in review.approved()[s2]], ["pace-shorter"])
        self.assertTrue(review.disable(s2, "pace-shorter", self.led).ok)
        self.assertEqual(review.approved()[s2], [])
        self.assertEqual(generate(SCRIPT, "normal", scope=s2, knowledge_root=self.pkg_root).applied_knowledge, [])
        self.assertTrue(review.rollback(s2, self.led).ok)                                              # back to the version with the rule
        self.assertEqual([r["id"] for r in review.approved()[s2]], ["pace-shorter"])
        self.assertEqual(len(generate(SCRIPT, "normal", scope=s2, knowledge_root=self.pkg_root).applied_knowledge), 1)
        acts = [e["payload"]["action"] for e in self.led.events(event_type="rule_decision")]
        self.assertEqual(acts, ["defer", "reject", "approve", "disable", "rollback"])

    def test_malformed_unsupported_and_expired_rules_are_ignored(self):
        scope = "normal/zz"
        good = {"id": "variety-run2", "kind": "variety_run", "text": "Limit repeats.", "confidence": 0.8, "evidence_count": 9, "status": "approved", "param": 2}
        bad_param = dict(good, param=99)
        self.assertFalse(pk.install(pk.build_package(scope, [bad_param], version=1), root=self.pkg_root).ok)
        self.assertFalse(pk.install(pk.build_package(scope, [dict(good, kind="rewrite_prompts")], version=1), root=self.pkg_root).ok)
        expired = dict(good, expires_at="2001-01-01T00:00:00+00:00")
        self.assertTrue(pk.install(pk.build_package(scope, [expired, {**good, "id": "note-1", "kind": "note"}], version=1), root=self.pkg_root).ok)
        r = generate(SCRIPT, "normal", GenerationOptions(enabled_types=("stock_video", "stock_image", "video")), scope=scope, knowledge_root=self.pkg_root)
        self.assertEqual(r.applied_knowledge, [])
        self.assertTrue(any("expired" in x for x in r.informational))
        self.assertTrue(any("note-1" in x and "guidance only" in x for x in r.informational))              # informational stays informational

    def test_empty_database_and_offline(self):
        self.assertEqual(review.suggestions(self.led), [])
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network")), mock.patch("socket.getaddrinfo", side_effect=AssertionError("network")):
            self.assertEqual(csv_analyzer.scan_projects(self.root, ledger=self.led)["projects"], 0)
            self.assertTrue(generate(SCRIPT, "normal", scope="normal/x", knowledge_root=self.pkg_root).ok)
        src = "".join((Path(__file__).parent / "learning" / f).read_text(encoding="utf-8") for f in ("csv_analyzer.py", "review.py", "analysis.py"))
        for w in ("requests", "urllib", "socket"):
            self.assertNotIn("import " + w, src)

    def test_full_loop_import_render_rate_analyze_approve_generate_evaluate(self):
        scope = self.seed_variety()                                   # steps 1-3: imports, renders, ratings (synthetic)
        self.assertTrue(csv_analyzer.status(self.led)["stale"])
        csv_analyzer.scan_projects(self.root, ledger=self.led)         # 4
        self.assertFalse(csv_analyzer.status(self.led)["stale"])
        cand = next(c for c in review.suggestions(self.led) if c["id"] == "variety-run2")      # 5
        review.decide(cand, "approve", self.led)                       # 6
        opts = GenerationOptions(enabled_types=("stock_video", "stock_image", "video"))
        off = generate(SCRIPT, "normal", opts)
        on = generate(SCRIPT, "normal", opts, scope=scope, knowledge_root=self.pkg_root)       # 7
        # 8: offline evaluation on measurable properties only (NOT viewer quality)
        self.assertTrue(off.ok and on.ok)
        self.assertLess(self.runs(on.rows), self.runs(off.rows))
        self.assertEqual(" ".join(r["script_segment"] for r in on.rows).split(), " ".join(r["script_segment"] for r in off.rows).split())
        self.assertEqual([i for i in on.issues if i.severity == "error"], [])


STAR_HEAD = "beat,row,vo_anchor,start,end,t,mode,type,id,place,frame,date,label,sub,text,value_from,value_to,format,anchor,until,hold,asset,dur,why,extra"


def starmap_text(modes, secs):
    lines = [STAR_HEAD, "0,plan,,,,,,,,,,,,,,,,,,,,,,,"]
    for i, m in enumerate(modes):
        lines.append(f"{i + 1},beat,anchor {i},{i * secs},{(i + 1) * secs},,{m},,,Mars,body,,,,,,,,,,,,,,")
    return "\n".join(lines) + "\n"


def whatif_text(kinds):
    head = "row,shot,vo_anchor,kind,asset,model,texture,label,sub,text,type,id,value_from,value_to,format,anchor,until,hold,why,extra,t,end"
    return head + "\n" + "\n".join(f"shot,{i + 1},w{i},{k},nasa_image:x,,,,,,,,,,,,,,,,," for i, k in enumerate(kinds)) + "\n"


def hybrid_json(modes, secs):
    import json
    return json.dumps({"version": 1, "duration": len(modes) * secs, "beats": [
        {"id": f"b{i}", "mode": m, "start": i * secs, "end": (i + 1) * secs, "layers": [{"type": "x"}] if m != "footage" else [], "cards": []} for i, m in enumerate(modes)]})


class OtherSchemaTests(Base):
    """Hybrid (plan.json), StarMap (beats.csv) and What If (shots.csv) have their own formats; SYNTHETIC files in each real format."""

    def mk(self, kind, content, rating, style_scope_name=None, tag="p"):
        ws = create_project(f"{kind}-{tag}", projects_root=self.root)
        ws.ensure_dirs()
        path = {"starmap": ws.starmap_csv_path, "whatif": Path(ws.root) / "whatif" / "shots.csv", "hybrid": ws.hybrid_plan_path}[kind]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        scope = style_scope_name or f"{kind}/default"
        ev.record_event("csv_import", style_scope=scope, project_id=ws.project_id, ledger=self.led, payload={"rows": 1})
        ev.record_event("render_outcome", style_scope=scope, project_id=ws.project_id, generation_id="g-" + ws.project_id, ledger=self.led, payload={"outcome": "success"})
        if rating:
            ev.record_video_rating(ws.project_id, scope, rating, generation_id="g-" + ws.project_id, ledger=self.led)
        return ws, scope

    def test_features_in_each_real_format(self):
        sm = csv_analyzer.features_starmap(starmap_text(["map", "map", "footage", "map_footage"], 5))
        self.assertEqual((sm["beats"], sm["max_same_mode_run"], sm["beat_s_mean"]), (4, 2, 5.0))
        self.assertEqual(sm["mode_counts"], {"map": 2, "footage": 1, "map_footage": 1})
        wi = csv_analyzer.features_whatif(whatif_text(["image", "image", "image", "video"]))
        self.assertEqual((wi["beats"], wi["max_same_mode_run"], wi["asset_counts"]), (4, 3, {"nasa_image": 4}))
        self.assertIsNone(wi["beat_s_mean"])                                   # no timings in the file -> unavailable, not guessed
        hy = csv_analyzer.features_hybrid(hybrid_json(["map", "footage", "footage", "footage", "footage"], 4))
        self.assertEqual((hy["beats"], hy["max_same_mode_run"], hy["beat_s_mean"], hy["layers"]), (5, 4, 4.0, 1))

    def test_scan_reads_all_three_schemas_and_uses_the_scope_of_the_users_own_events(self):
        _, s1 = self.mk("starmap", starmap_text(["map"] * 4, 5), None, "starmap/cinema")
        _, s2 = self.mk("whatif", whatif_text(["image"] * 3), None)
        _, s3 = self.mk("hybrid", hybrid_json(["map", "footage"], 5), None, "hybrid/doc")
        summ = csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual(summ["analyzed_new"], 3)
        got = {e["style_scope"] for e in self.led.events(event_type="csv_analysis")}
        self.assertEqual(got, {"starmap/cinema", "whatif/default", "hybrid/doc"})
        self.assertEqual(csv_analyzer.scan_projects(self.root, ledger=self.led)["analyzed_new"], 0)

    def test_candidates_for_each_style_are_guidance_notes_isolated_by_style(self):
        for kind, rep, var, secs in (("hybrid", ["map"] * 6, ["map", "footage"] * 3, 4), ("starmap", ["map"] * 6, ["map", "footage"] * 3, 4)):
            for i in range(4):
                self.mk(kind, hybrid_json(rep, secs) if kind == "hybrid" else starmap_text(rep, secs), 2, tag=f"r{i}")
            for i in range(4):
                self.mk(kind, hybrid_json(var, secs) if kind == "hybrid" else starmap_text(var, secs), 4, tag=f"v{i}")
        for i in range(4):
            self.mk("whatif", whatif_text(["image"] * 6), 2, tag=f"r{i}")
        for i in range(4):
            self.mk("whatif", whatif_text(["image", "video"] * 3), 5, tag=f"v{i}")
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        got = {(c["style_scope"], c["id"], c["kind"]) for c in review.suggestions(self.led)}
        self.assertEqual(got, {("hybrid/default", "mode-run2", "note"), ("starmap/default", "mode-run2", "note"), ("whatif/default", "mode-run2", "note")})
        # approve Hybrid's only: guidance reaches the Hybrid prompt scope and no other style; the generator has no Hybrid planner
        cand = next(c for c in review.suggestions(self.led) if c["style_scope"] == "hybrid/default")
        self.assertIn("Association only", cand["pattern"])
        self.assertTrue(review.decide(cand, "approve", self.led).ok)
        from learning import guidance
        self.assertIn("alternate the modes", guidance.guidance_text("hybrid/default"))
        self.assertEqual(guidance.guidance_text("starmap/default"), "")
        self.assertEqual(guidance.guidance_text("whatif/default"), "")
        self.assertFalse(generate(SCRIPT, "hybrid", scope="hybrid/default", knowledge_root=self.pkg_root).ok)     # still not a generator style

    def test_too_few_projects_or_missing_timings_give_no_pacing_suggestion(self):
        for i in range(2):
            self.mk("whatif", whatif_text(["image"] * 6), 2, tag=f"r{i}")
            self.mk("whatif", whatif_text(["image", "video"] * 3), 5, tag=f"v{i}")
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual(review.suggestions(self.led), [])                      # 4 rated projects: below the minimum
        for i in range(2, 5):
            self.mk("whatif", whatif_text(["image"] * 6), 2, tag=f"r{i}")
            self.mk("whatif", whatif_text(["image", "video"] * 3), 5, tag=f"v{i}")
        csv_analyzer.scan_projects(self.root, ledger=self.led)
        self.assertEqual([c["id"] for c in review.suggestions(self.led)], ["mode-run2"])      # What If has no timings -> no beat-length suggestion


class LearningWindowTests(Base):
    def test_window_analyzes_lists_approves_and_shows_the_rule(self):
        try:
            import customtkinter as ctk
            root = ctk.CTk()
            root.geometry("200x80+30+30")
        except Exception as exc:
            raise unittest.SkipTest(f"no display: {exc}")
        self.addCleanup(root.destroy)
        scope = self.seed_variety()
        root._projects_root_path = lambda: self.root
        from learning import self_learning_ui as ui
        ui.open_learning(root)
        win = next(w for w in root.winfo_children() if w.winfo_class() == "Toplevel")

        def walk(w):
            yield w
            for c in w.winfo_children():
                yield from walk(c)

        def find(text):
            return next((w for w in walk(win) if isinstance(w, ctk.CTkButton) and w.cget("text") == text), None)

        def pump(cond, secs=8):
            end = time.time() + secs
            while time.time() < end and not cond():
                root.update()
                time.sleep(0.02)
            return cond()
        find("Analyze Existing CSVs").invoke()
        self.assertTrue(pump(lambda: csv_analyzer.status(self.led)["last_run"] is not None))
        self.assertTrue(pump(lambda: find("Approve") is not None))
        find("Approve").invoke()
        self.assertTrue(pump(lambda: scope in review.approved() and review.approved()[scope]))
        self.assertTrue(pump(lambda: find("Disable") is not None))
        self.assertIsNotNone(find("Roll back to previous version"))
        win.destroy()


if __name__ == "__main__":
    unittest.main()
