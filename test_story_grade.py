"""Story Fast project grade: measured once, per-shot filter, lighter vignette on white backgrounds, wired into plan_clips + the compose cache key."""
import re, shutil, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from story_fast import grade as G, runner as R, compose as C

fails = []
def ok(c, m):
    print(("ok  " if c else "FAIL"), m)
    if not c: fails.append(m)

T = Path(tempfile.mkdtemp(prefix="sf_grade_"))
def mk(name, bg, ink=(30, 30, 90)):
    a = np.zeros((180, 320, 3), np.uint8); a[:] = bg; a[60:140, 100:220] = ink
    p = T / name; Image.fromarray(a).save(p); return str(p)
white1, white2, cream = mk("w1.png", (255, 255, 255)), mk("w2.png", (250, 252, 255)), mk("cr.png", (246, 238, 220))
dark = mk("dk.png", (40, 30, 30), (200, 160, 60))
g = G.compute_project_grade([white1, white2, cream, dark])
ok(g.stills == 4 and g.ref, "grade measured from 4 pictures")
ang = lambda still: float(re.search(r"vignette=([\d.]+)", g.filter_for(still)).group(1))
ok(ang(white1) < ang(dark) * 0.6, f"white-background picture gets a much lighter vignette ({ang(white1):.2f} vs {ang(dark):.2f})")
ok(ang(dark) < 0.6, "no vignette is stronger than the old fixed look (0.63)")
ok(g.filter_for(white1) and "noise=" in g.filter_for(white1) and not g.filter_for(white1).startswith(","), "filter chain is well formed")
ok(g.color_filter(cream) != "" , "a cream picture is pulled toward the set's white point")
g2 = G.ProjectGrade.from_dict(g.to_dict())
ok(g2.filter_for(cream) == g.filter_for(cream), "grade survives JSON round trip")

shots = [{"shot_id": "001a", "start": 0.0, "end": 2.0, "treatment": "push_in", "tparams": {}}, {"shot_id": "002a", "start": 2.0, "end": 4.0, "treatment": "push_in", "tparams": {}}]
imgs = {"001a": cream, "002a": white1}
jobs = R.plan_clips(shots, imgs, {"size": (320, 180), "fps": 30, "story_grade": g.to_dict(), "story_continuity": "off"})
ok(all(j.get("grade_vf") for j in jobs) and jobs[0]["grade_vf"] != jobs[1]["grade_vf"], "plan_clips puts each shot's own grade on the job")
jobs0 = R.plan_clips(shots, imgs, {"size": (320, 180), "fps": 30, "story_continuity": "off"})
ok(not any(j.get("grade_vf") for j in jobs0), "no grade given -> old fixed look (no grade_vf)")
ok(C.job_key(jobs[0]) != C.job_key(jobs0[0]), "compose cache key covers the grade")
ok("vignette=PI/5" in C._build_graph(C._norm(dict(jobs0[0])), C._camera(C._norm(dict(jobs0[0])), False), 1, 30), "no grade -> fixed finish kept")
gr = C._build_graph(C._norm(dict(jobs[0])), C._camera(C._norm(dict(jobs[0])), False), 1, 30)
ok(jobs[0]["grade_vf"] in gr and "PI/5" not in gr, "grade filter replaces the fixed vignette in the graph")
shutil.rmtree(T, ignore_errors=True)
print("ALL OK" if not fails else f"{len(fails)} FAILED"); sys.exit(1 if fails else 0)
