"""story_fast.similar + the director's reframing of long same-picture stretches + hard cuts as the default."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from collections import Counter
from PIL import Image
from story_fast import similar, direct

fails = []
def ok(c, m):
    print(("ok   " if c else "FAIL ") + m)
    if not c: fails.append(m)

tmp = tempfile.mkdtemp(); rng = np.random.default_rng(3)
def pic(name, base, noise=0.0):
    a = np.clip(base + rng.normal(0, noise, base.shape), 0, 255).astype(np.uint8); p = os.path.join(tmp, name); Image.fromarray(a).save(p); return p
b1 = np.full((360, 640, 3), 240, np.uint8); b1[100:300, 50:200] = (30, 40, 90); b1[120:260, 420:600] = (200, 60, 50)       # host + chart on white
b2 = np.full((360, 640, 3), 240, np.uint8); b2[60:340, 380:560] = (20, 120, 60); b2[200:340, 80:180] = (90, 30, 30)       # another composition on white
b3 = np.full((360, 640, 3), 30, np.uint8); b3[:, 300:] = (200, 180, 90)
A, A2, B, C = pic("a.png", b1), pic("a2.png", b1, 4.0), pic("b.png", b2), pic("c.png", b3)
ok(similar.distance(similar.fingerprint(A), similar.fingerprint(A)) == 0.0, "same picture distance 0")
ok(similar.distance(similar.fingerprint(A), similar.fingerprint(A2)) < similar.THRESHOLD, "a re-encoded copy counts as near-identical")
ok(similar.distance(similar.fingerprint(A), similar.fingerprint(B)) > similar.THRESHOLD, "a different composition on the same white background is not")
ok(similar.distance(similar.fingerprint(A), similar.fingerprint(C)) > 0.2, "a dark picture is far")
ok(similar.fingerprint(os.path.join(tmp, "nope.png")) is None, "missing file -> None")

def shots(spec):
    out, t = [], 0.0
    for i, (sc, d) in enumerate(spec):
        out.append({"shot_id": f"s{i}", "scene_no": sc, "start": t, "end": t + d, "text": "He explained the plan to her.", "prompt_en": "A man beside a chart", "picture": "same"}); t += d
    return out
imgs = {1: A, 2: A2, 3: B, 4: C, 5: C}
ann = similar.annotate(shots([(1, 4.0), (2, 4.0), (3, 3.0), (4, 3.0), (5, 3.0)]), imgs)
ok("same_run" in ann[0] and ann[0]["same_run"]["id"] == ann[1]["same_run"]["id"] and ann[0]["same_run"]["seconds"] == 8.0, "scenes 1+2 (near-identical) form one stretch of 8 s")
ok("same_run" not in ann[2], "a different picture is outside the stretch")
ok(ann[3]["same_run"]["id"] == ann[4]["same_run"]["id"] and ann[4]["same_run"]["pos"] == 1, "the same file twice is a stretch")

# the director reframes a long stretch: a different subject rank and tightness per shot, jump cuts inside it, and hard cuts are the norm elsewhere
long = similar.annotate(shots([(1, 4.0), (2, 4.0), (1, 4.0)]), {1: A, 2: A2})
r = direct.direct(long, {}, 0)["shots"]
ok([s["tparams"].get("focus_rank") for s in r] == [0, 1, 2], "focus_rank 0,1,2 across the stretch")
ok(r[0]["tparams"]["amount"] != r[1]["tparams"]["amount"], "wide / tight alternate")
ok(all(s["transition_in"] == "cut" for s in r), "jump cuts inside the stretch")
many = shots([(i, 3.0) for i in range(120)])
for s in many: s["picture"] = "new"
rm = direct.direct(many, {}, 1)["shots"]
tc = Counter(s["transition_in"] for s in rm)
ok(tc["cut"] / 120.0 >= 0.8, "with no story reason for a dip, hard cuts are the default (%s)" % dict(tc))
timejump = shots([(1, 3.0), (2, 3.0)]); timejump[1]["text"] = "Ten years later, everything had changed."
ok(direct.direct(timejump, {}, 0)["shots"][1]["transition_in"] in ("fade", "dissolve", "soft"), "a time jump earns a dip")
print("ALL OK" if not fails else "FAILED: %s" % fails); sys.exit(1 if fails else 0)
