"""Story Motion style: registry, variant pick/active, pipeline settings, CSV prompt, no Tk needed."""
from types import SimpleNamespace as NS
from ui import style_registry as R, style_pages as P, story_motion_section as S

fails = []
def ok(c, m):
    print(("ok  " if c else "FAIL"), m)
    if not c: fails.append(m)

ok("Story Motion" in R.with_extras(("Normal video", "Overscaled")), "card listed")
ok(R.with_extras(("Normal video", "Overscaled")).index("Story Motion") == 1, "right after Normal video")
ok(R.group_of("Story Motion") == "General", "in General")
ok(R.BUILT_ON["Story Motion"] == "Normal video", "built on Normal video")
ok("Story Motion" in R.EXTRA_BLURBS and "Story Motion" in R.EXTRA_CARDS, "blurb + card")

app = NS(generation_mode="normal")
ok(P.active_variant(app, "normal") == "", "not active by default")
ch, done = P.pick_variant(app, "Story Motion")
ok(app._story_motion_active and (ch, done) == ("Story Motion", True), "pick in normal mode: flag only")
ok(P.active_variant(app, "normal") == "Story Motion", "variant active")
app.generation_mode = "hybrid"
ok(P.pick_variant(app, "Story Motion") == ("Normal video", False), "from another engine: switch to Normal")
P.pick_variant(app, "Overscaled")
ok(not app._story_motion_active, "other pick clears flag")

app._story_vars = None
ps = S.pipeline_settings(app)
ok(ps["story_video"] and ps["story_dry_run"] is False and ps["story_motion_intensity"] == "medium", "default settings")
txt = S.prompt_text()
ok("scene_number" in txt and len(txt) > 500, "csv prompt loaded")

# saved in the project: reopening keeps it, another project does not inherit it
import tempfile
from pathlib import Path
from project_workspace import ProjectWorkspace
with tempfile.TemporaryDirectory() as d:
    ws = ProjectWorkspace(project_id="p1", title="p1", seq=1, root=Path(d) / "p1"); ws.ensure_dirs()
    a = NS(generation_mode="normal", _workspace=ws)
    P.pick_variant(a, "Story Motion")
    ok(ws.story_motion() and S.is_active(a), "pick saves story_motion in the project")
    ws2 = ProjectWorkspace(project_id="p1", title="p1", seq=1, root=Path(d) / "p1")
    ok(S.is_active(NS(_workspace=ws2)) and P.active_variant(NS(_workspace=ws2), "normal") == "Story Motion", "reopened project is still Story Motion")
    other = ProjectWorkspace(project_id="p2", title="p2", seq=2, root=Path(d) / "p2"); other.ensure_dirs()
    ok(not S.is_active(NS(_workspace=other, _story_motion_active=True)), "another project does not inherit the session flag")
    P.pick_variant(a, "Overscaled")
    ok(not ws.story_motion(), "picking another style clears it")
print("FAILED" if fails else "ALL OK"); raise SystemExit(1 if fails else 0)
