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
print("FAILED" if fails else "ALL OK"); raise SystemExit(1 if fails else 0)
