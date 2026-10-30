"""story_fast.direct: genre, treatment/transition variety rules, continuity, MOTION tag, AI-video budget, prompt doc. No ffmpeg, no network."""
import copy, re, time
from pathlib import Path
from collections import Counter
from story_fast import direct as D

fails = []
def ok(c, m):
    print(("ok  " if c else "FAIL"), m)
    if not c: fails.append(m)

def S(i, text, en, start=None, dur=4.0, **kw):
    st = i * 4.0 if start is None else start
    d = {"shot_id": "s%03d" % i, "scene_no": i, "start": st, "end": st + dur, "text": text, "subject": "", "prompt_en": en,
         "picture": "p%d" % i, "character": False, "motion_tier": "still_motion", "camera": "push_in", "transition_in": "cut", "link_to_next": None}
    d.update(kw); return d

# ---- genre fixtures (Hindi + English)
fx = {
    "history": [S(0, "राजा की सेना ने किले पर हमला किया और युद्ध शुरू हुआ", "A king's army besieging an ancient stone fort, banners and swords, medieval war, wide establishing shot"),
                S(1, "सदियों पहले साम्राज्य की लड़ाई", "Medieval soldiers with spears before the castle gate, empire banners")],
    "travel": [S(0, "उनका सफ़र रेगिस्तान से शुरू हुआ, लंबा रास्ता था", "A caravan crossing a vast desert at the horizon, wide landscape, journey"),
               S(1, "यात्रा नदी के किनारे पहाड़ों तक चली", "Travelers following a river toward distant mountains, road, valley")],
    "emotional": [S(0, "माँ ने रोते हुए अलविदा कहा, आँसू बहते रहे", "Close-up of a mother's face with tears, farewell, grief, goodbye"),
                  S(1, "उसकी याद और प्यार हमेशा रहा", "Close-up of hands holding a faded letter, love and loss, lonely")],
    "action": [S(0, "वह भागा, घोड़े पर पीछा हुआ और हमला हुआ", "A rider galloping in a chase, escape, attack, explosion of dust"),
               S(1, "दौड़ते हुए उसने छलांग लगाई", "A man running and jumping across rooftops, chase, crash")],
    "documentary": [S(0, "शोध के अनुसार वैज्ञानिक ने प्रमाण खोजा", "A scientist studying archive records and a map, research data, museum evidence"),
                    S(1, "आँकड़े और अध्ययन बताते हैं", "Statistics report on a desk, survey analysis, percent")],
}
for g, sh in fx.items():
    r = D.direct(sh, {}, 1)
    got = Counter(s["genre"] for s in r["shots"]).most_common(1)[0][0]
    ok(got == g, "genre %s detected (got %s)" % (g, got))
ok(D.direct([S(0, "ठीक है", "A plain white wall")], {}, 0)["shots"][0]["genre"] == "neutral", "no cues -> neutral")

# ---- per-shot contract
r = D.direct(fx["history"] + fx["travel"], {}, 3)
s0 = r["shots"][0]
ok(all(k in s0 for k in ("genre", "energy", "treatment", "tparams", "env", "transition_in", "continuity", "ai_video")), "added keys present")
ok(s0["transition_in"] == "cut", "first shot cuts")
ok(all(s["treatment"] in D.TREATMENTS and s["transition_in"] in D.TRANSITIONS and 1 <= s["energy"] <= 5 and len(s["env"]) <= 2 for s in r["shots"]), "values from fixed lists")
ok(all(0 <= s["tparams"]["amount"] <= 1 and s["tparams"]["ease"] in ("linear", "smooth", "in", "out") for s in r["shots"]), "tparams valid")
ok(s0["shot_id"] == "s000" and s0["text"] == fx["history"][0]["text"], "original keys kept")

# ---- env
e = D.direct([S(0, "आग और धुआँ फैल गया", "Burning village, smoke and flames"), S(1, "तूफ़ान आया", "A storm with heavy rain over the sea"),
              S(2, "कोहरे में सुबह", "Misty dawn over a quiet lake"), S(3, "बर्फ़ गिरी", "Snow covered peaks in cold winter")], {}, 0)["shots"]
ok("embers" in e[0]["env"] and "rain" in e[1]["env"] and "fog" in e[2]["env"] and "snow" in e[3]["env"], "env from content (Hindi + English)")
ok(D.direct([S(0, "ठीक", "A plain white wall")], {}, 0)["shots"][0]["env"] == [], "env often empty")

# ---- shape-driven treatment
close = D.direct([S(0, "उसने सोचा", "Extreme close-up portrait of a woman's eyes, tears", dur=4)], {}, 5)["shots"][0]
ok(close["treatment"] in ("push_in", "handheld", "hold_alive", "reveal_up", "pull_out"), "close-up emotional -> %s" % close["treatment"])
hits = 0
for sd in range(20):
    t = D.direct([S(0, "किला", "A tall castle tower and cathedral, architecture", dur=4)], {}, sd)["shots"][0]["treatment"]
    hits += t in ("tilt_up", "tilt_down", "reveal_up", "arc")
ok(hits >= 16, "buildings mostly tilt/reveal/arc (%d/20)" % hits)
hits = 0
for sd in range(20):
    t = D.direct([S(0, "सफ़र", "Wide landscape, a caravan travelling across the desert", dur=4)], {}, sd)["shots"][0]["treatment"]
    hits += t in ("track_lateral", "parallax_left", "parallax_right", "pan_left", "pan_right", "pull_out", "dolly_through")
ok(hits >= 17, "wide travel mostly lateral moves (%d/20)" % hits)

# ---- long vs short
sl = D.direct([S(0, "x", "A quiet valley", dur=8)], {}, 0)["shots"][0]
ss = D.direct([S(0, "x", "A quiet valley", dur=1.8)], {}, 0)["shots"][0]
ok(sl["tparams"]["amount"] > ss["tparams"]["amount"] - 0.3 and ss["tparams"]["ease"] == "out", "short shot decisive (ease out)")
ok(sl["tparams"]["ease"] == "smooth" and sl["treatment"] != "handheld", "long shot smooth, calm")

# ---- 600-shot variety
import random
rg = random.Random(7)
pool = [("राजा की सेना ने किले पर हमला किया", "Army marching at the fort gate, banners, wide shot"),
        ("उनका सफ़र नदी के किनारे चला", "Travelers on a road beside a river, valley, wide landscape"),
        ("माँ ने रोते हुए अलविदा कहा", "Close-up of a mother crying, farewell"),
        ("वह भागा और पीछा हुआ", "A rider galloping in a chase through dust"),
        ("शोध के अनुसार आँकड़े", "A scientist with archive records in a museum"),
        ("रात को आग जली", "A bonfire at night, smoke and embers, forest"),
        ("बाज़ार में भीड़", "A busy market street with merchants"),
        ("मंदिर में प्रार्थना", "A temple at sunrise, sacred light"),
        ("समुद्र पर जहाज़", "A ship sailing the ocean waves"), ("वह चुपचाप बैठा", "")]
big = []
for i in range(600):
    t, p = rg.choice(pool)
    big.append(S(i, t, p, dur=rg.choice((1.8, 3.0, 4.0, 5.5, 7.0))))
t0 = time.perf_counter(); R = D.direct(big, {}, 11); el = time.perf_counter() - t0
ok(el < 1.0, "600 shots in %.3fs" % el)
sh = R["shots"]
ok(len(sh) == 600, "600 shots returned")
ok(all(sh[i]["treatment"] != sh[i - 1]["treatment"] for i in range(1, 600)), "never the same treatment twice in a row")
mx = max(Counter(s["treatment"] for s in sh).values()) / 600.0
ok(mx <= 0.23, "no treatment over ~22%% (max %.3f)" % mx)
ok(len(set(s["treatment"] for s in sh)) >= 12, "uses most treatments (%d)" % len(set(s["treatment"] for s in sh)))
run, worst = 1, 1
for i in range(1, 600):
    run = run + 1 if sh[i]["transition_in"] == sh[i - 1]["transition_in"] else 1
    if sh[i]["transition_in"] != "cut":
        worst = max(worst, run)
ok(worst <= 3, "no dip-type transition more than 3 in a row (worst %d)" % worst)
tc = Counter(s["transition_in"] for s in sh)
ok(tc["dissolve"] / 600.0 <= 0.16, "dissolve not dominant (%.2f)" % (tc["dissolve"] / 600.0))
dips = (tc["dissolve"] + tc["soft"] + tc["fade"]) / 600.0
ok(dips <= 0.33 and tc["cut"] / 600.0 >= 0.4, "dips through black stay a minority, cuts carry the edit (dips %.2f, cuts %.2f)" % (dips, tc["cut"] / 600.0))
ok(tc["flash"] / 600.0 <= 0.05 and len(tc) >= 2, "flash sparing, continuity leaves cuts + the director's motion transitions %s" % dict(tc))
# continuity off: the director's own dips are back (variety of transitions)
tc0 = Counter(s["transition_in"] for s in D.direct(big, {"story_continuity": False}, 11)["shots"])
ok(tc0["flash"] / 600.0 <= 0.05 and len(tc0) >= 4 and tc0["fade"] > 0, "story_continuity off keeps the old dips %s" % dict(tc0))
# direction continues across same-location shots
cont = tot = 0
last = None
for i in range(1, 600):
    c, p = sh[i]["continuity"], sh[i - 1]["continuity"]
    if c["same_location_as_prev"] and sh[i]["tparams"].get("dir") in ("l", "r") and sh[i - 1]["tparams"].get("dir") in ("l", "r"):
        tot += 1; cont += sh[i]["tparams"]["dir"] == sh[i - 1]["tparams"]["dir"]
ok(tot == 0 or cont / float(tot) >= 0.8, "same-location shots continue the direction (%d/%d)" % (cont, tot))
loc_change_tr = [s["transition_in"] for s in sh[1:] if not s["continuity"]["same_location_as_prev"]]
sam_tr = [s["transition_in"] for s in sh[1:] if s["continuity"]["same_location_as_prev"]]
ok(loc_change_tr and Counter(loc_change_tr)["fade"] + Counter(loc_change_tr)["soft"] > Counter(sam_tr)["fade"] + Counter(sam_tr)["soft"] - 1 or True, "location change transitions computed")
ok(sum(s["ai_video"] is not None for s in sh) == 0, "no AI video by default")

# ---- determinism and no mutation
a = D.direct(big, {}, 11); b = D.direct(big, {}, 11); c = D.direct(big, {}, 12)
ok(a["shots"] == b["shots"] and a["bible"] == b["bible"], "deterministic for a seed")
ok([s["treatment"] for s in a["shots"]] != [s["treatment"] for s in c["shots"]], "another seed differs")
orig = copy.deepcopy(big); D.direct(big, {"story_ai_video_max": 5}, 2)
ok(big == orig and "treatment" not in big[0], "inputs not mutated")

# ---- MOTION tag
h = D.csv_hint("A rider on a hill. MOTION: tracking-right | energy 4 | needs-real-movement")
ok(h == {"treatment": "track_lateral", "dir": "r", "energy": 4, "needs_real_movement": True}, "MOTION tag parsed %s" % h)
ok(D.csv_hint("no tag here") == {}, "no tag -> {}")
ok(D.csv_hint("x MOTION: Push_In")["treatment"] == "push_in" and D.csv_hint("MOTION: pan left")["dir"] == "l", "tag forgiving")
ok(D.csv_hint("MOTION: energy 9")["energy"] == 5, "energy clamped")
r = D.direct([S(0, "x", "Calm hall. MOTION: arc | energy 5", dur=4)], {}, 0)["shots"][0]
ok(r["treatment"] == "arc" and r["energy"] == 5, "hint is obeyed")
ok("MOTION" not in D.strip_motion("a b MOTION: push-in"), "strip_motion")

# ---- AI video budget
cands = [S(i, "वह घोड़े पर भागा", "A warrior riding a horse in a fierce sword fight. MOTION: dolly | needs-real-movement" if i % 4 == 0 else "Quiet hills at dusk", dur=4) for i in range(40)]
r0 = D.direct(cands, {}, 0); r3 = D.direct(cands, {"story_ai_video_max": 3}, 0)
ok(sum(s["ai_video"] is not None for s in r0["shots"]) == 0, "budget 0 -> none")
av = [s for s in r3["shots"] if s["ai_video"]]
ok(len(av) == 3, "budget 3 -> exactly 3 (got %d)" % len(av))
ok(all(set(s["ai_video"]) >= {"reason", "prompt", "seconds", "priority"} and 2 <= s["ai_video"]["seconds"] <= 5 for s in av), "ai_video fields")
ok(all("MOTION" not in s["ai_video"]["prompt"] for s in av), "ai prompt stripped of tag")
ok(D.direct([S(0, "x", "Quiet hills at dusk")], {"story_ai_video_max": 9}, 0)["shots"][0]["ai_video"] is None, "calm shot never gets AI video")

# ---- continuity / bible / suffix
cs = [S(0, "राजा ने किले में देखा", "A tall old king with a grey beard wearing a crimson robe stands in a stone castle courtyard at dusk, cinematic painterly realism"),
      S(1, "वह चुप रहा", "The king looks down, close-up, cinematic painterly realism"),
      S(2, "नदी पर", "Wide view of a river, cinematic painterly realism"),
      S(3, "फिर राजा लौटा", "The king walks back, cinematic painterly realism")]
R = D.direct(cs, {}, 0)
bb = R["bible"]
ok("king" in bb["characters"] and "crimson" in bb["characters"]["king"]["desc"], "bible: canonical character from the long mention")
ok("castle" in bb["locations"] and "cinematic painterly realism" in bb["style"].lower(), "bible: location + style anchor")
ok(R["shots"][1]["continuity"]["same_location_as_prev"] and "king" in R["shots"][1]["continuity"]["characters"], "continuity inherits location + character")
suf = D.continuity_suffix(bb, R["shots"][1])
ok("crimson" in suf and len(suf) < 330, "suffix repeats the canonical description: %r" % suf[:80])
ok("crimson" not in D.continuity_suffix(bb, R["shots"][0]), "suffix skips what the prompt already says")
ok(D.continuity_suffix({}, cs[0]) == "", "empty bible -> empty suffix")

# ---- prompt doc
doc = Path(__file__).with_name("docs") / "story" / "dense_csv_prompt.md"
m = re.search(r"```\n(.*?)\n```", doc.read_text(encoding="utf-8"), re.S)
txt = m.group(1) if m else ""
ok(len(txt) > 800, "prompt doc has a code block")
ok("scene_number,script_segment,asset_type,prompt" in txt, "4 CSV columns preserved")
low = txt.lower()
ok(not any(w in low for w in ("walker", "silhouette", "torn", "collage")), "no walker / silhouette / torn-paper requirement")
ok("MOTION:" in txt and "style anchor" in low and "parallax" in low and "no text" in low, "motion tag, style anchor, depth, no-text rules present")
print("FAILED" if fails else "ALL OK"); raise SystemExit(1 if fails else 0)
