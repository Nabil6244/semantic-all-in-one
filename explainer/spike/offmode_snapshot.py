"""Snapshot of the existing (off-mode) Hybrid path: the original fixture compiled by the unmodified code, plus the protected-scope hashes.

usage: python3 -B -I explainer/spike/offmode_snapshot.py <repo_root> <out.json>
Read-only on the repository. Run before and after the spike; the two outputs are compared by analyze.py / by hand."""
import hashlib, json, subprocess, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
sys.path.insert(0, str(root))
sys.dont_write_bytecode = True


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jsha(obj) -> str:
    return sha(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode())


def git(*a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True).stdout


from hybrid import plan as hplan
from hybrid.compile import compile_plan, plan_to_rows, rows_to_csv

fixture = root / "test_hybrid_app_plan.json"
snap = {"head": git("rev-parse", "HEAD").strip(), "git_status": git("status", "--short").splitlines()}
snap["fixture_file_sha256"] = sha(fixture.read_bytes())


def compile_once():
    plan = hplan.HybridPlan.load(fixture)
    rows, line_map, notes = plan_to_rows(plan)
    res = compile_plan(plan)
    return {
        "plan_dict_sha256": jsha(plan.to_dict()),
        "validate_plan": hplan.validate_plan(plan),
        "rows_csv_sha256": sha(rows_to_csv(rows).encode()),
        "row_count": len(rows),
        "line_map_sha256": jsha({str(k): v for k, v in line_map.items()}),
        "notes": notes,
        "spec_sha256": jsha(res.spec),
        "report_warnings": list(res.report.warnings),
        "report_errors": list(res.report.errors),
        "event_types": sorted({e.get("type") for e in res.spec.get("events", [])}),
        "spec_event_count": len(res.spec.get("events", [])),
    }


snap["compile_run_1"] = compile_once()
snap["compile_run_2"] = compile_once()   # control: the compile is deterministic, so a before/after difference means something
snap["compile_deterministic"] = snap["compile_run_1"] == snap["compile_run_2"]

snap["config"] = {
    "DEFAULT_SETTINGS_sha256": jsha(hplan.DEFAULT_SETTINGS),
    "MODES": list(hplan.MODES), "LAYER_TYPES": list(hplan.LAYER_TYPES), "TRANSITIONS": list(hplan.TRANSITIONS), "SOURCES": list(hplan.SOURCES),
    "settings_json_sha256": sha((root / "settings.json").read_bytes()),
    "settings_json_relevant": {k: json.loads((root / "settings.json").read_text()).get(k) for k in ("doc_style", "hybrid_auto_templates", "caption_style", "normal_hybrid_style")},
    "app_py_sha256": sha((root / "app.py").read_bytes()),
    "spec_sha256": sha((root / "VideoGenerator.spec").read_bytes()),
}

scope_dirs = ["hybrid", "pakmap", "pakmap-engine", "composition_styles", "map_scene", "map-engine", "providers", "flow-engine", "starmap", "starmap-engine", "gfx-core", "gfx-overlay-engine", "graphics", "normal_gfx"]
scope_files = [f for f in git("ls-files", *scope_dirs).splitlines() if "node_modules" not in f]
scope_files += ["project_workspace.py", "app_csv_prompts.py", "asset_manager.py", "video_generator.py", "gfx_templates.py", "test_hybrid_app_plan.json",
                "test_weather_isolation.py", "test_fixtures/weather_protected.json", "test_fixtures/enoch_template_protected.json"]
snap["scope_sha256"] = {f: sha((root / f).read_bytes()) for f in sorted(set(scope_files)) if (root / f).is_file()}
census = []
for d in ["hybrid", "pakmap", "pakmap-engine", "composition_styles", "providers", "map_scene", "map-engine", "flow-engine", "starmap", "starmap-engine"]:
    for p in sorted((root / d).rglob("*")):
        if p.is_file() and "node_modules" not in p.parts:
            census.append(str(p.relative_to(root)))
snap["protected_folder_file_census"] = census
out.write_text(json.dumps(snap, indent=1, sort_keys=True))
print("deterministic:", snap["compile_deterministic"], "scope files:", len(snap["scope_sha256"]), "census:", len(census))
