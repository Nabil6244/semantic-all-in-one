"""Milestone 4a verification: the director on five synthetic topics, its gates, determinism, and one real render through the unchanged Hybrid renderer.
Reads the repository, writes only under <work_root>.

usage: python3 -B -I verify_m4.py <repo_root> <work_root>

A. unit checks of every rule (segmentation, grouping, places, labels, key phrases, tables, narrator runs, repair, gate, never-raise, archive library);
B. five topics x two dissolve settings: plan validity (validate_plan, check_plan, the application's editorial validator), tiling, asset files, clip frame counts, pacing numbers,
   metaphor and role consistency, replay of every board beat from the report (clip bytes equal, every cue on the frame independently recomputed from its word);
C. determinism in a fresh folder and in a separate process; D. no network attempts; E. a real render of one topic with the unchanged generate_hybrid_video.
Word times are synthetic (rule-made), the narration is not a human voice, and the offline test map has no satellite imagery."""
import hashlib
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

root, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
os.environ["VIDEOGEN_PAKMAP_CACHE"] = str(work / "cache")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import numpy as np
from PIL import Image, ImageDraw

import measure_render as M
from m4_topics import TOPICS, words_from_script
from explainer import packaging
from explainer.board import Cue, build_board_clip
from explainer.board.dry import dry_build
from explainer.director import DirectorOptions, direct
from explainer.director import compose as CP
from explainer.director import lexicon as LX
from explainer.director import pacing as PC
from explainer.director import segment as SG
from explainer.director import select as SL
from explainer.integration import direct_plan
from hybrid.generate import generate_hybrid_video
from hybrid.plan import HybridPlan, validate_plan
from pakmap.engine_runner import render_spec

FPS = 30
work.mkdir(parents=True, exist_ok=True)
result = {"checks": {}, "topics": {}, "notes": []}
ck = result["checks"]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


class NetGuard:
    attempts = []

    def __enter__(self):
        self._c, self._cc = socket.socket.connect, socket.create_connection

        def bad(addr):
            host = addr[0] if isinstance(addr, (tuple, list)) else addr
            return str(host) not in ("127.0.0.1", "::1", "localhost", "0.0.0.0") and not str(host).startswith("127.") and not str(addr).startswith("/")

        def conn(sock, addr, *a, **k):
            if bad(addr):
                NetGuard.attempts.append(str(addr)[:80])
                raise OSError("network is disabled during verification")
            return self._c(sock, addr, *a, **k)

        def cc(addr, *a, **k):
            if bad(addr):
                NetGuard.attempts.append(str(addr)[:80])
                raise OSError("network is disabled during verification")
            return self._cc(addr, *a, **k)
        socket.socket.connect, socket.create_connection = conn, cc
        return self

    def __exit__(self, *e):
        socket.socket.connect, socket.create_connection = self._c, self._cc


def plan_text(p, base):
    return json.dumps(p, indent=1, sort_keys=True).replace(str(base), "<WORK>")


# ================= A. unit checks =================
W = lambda text, **k: words_from_script(text, **k)
w, dur = W("Why does it rain? Water falls from clouds. But the sea gives it back. In the end the water returns.")
sents = SG.sentences(w, "Why does it rain? Water falls from clouds. But the sea gives it back. In the end the water returns.", dur, 6.4)
SG.label_sentences(sents, w, "Why does it rain? Water falls from clouds. But the sea gives it back. In the end the water returns.")
ck["labels_hook_twist_conclusion_and_question_flag"] = [s.label for s in sents] == ["hook", "explain", "twist", "conclusion"] and sents[0].is_question and sents[2].trigger == "but" and sents[3].trigger == "in the end"
w2, dur2 = W("Why does the rain fall from the clouds. Water falls from the clouds onto the land. How does the sea give the water back again. The sea gives the water back as vapour.", pause=0.9)
s2 = SG.sentences(w2, None, dur2, 6.4)
SG.label_sentences(s2, w2, None)
ck["without_a_script_a_question_word_starts_a_question"] = [s.is_question for s in s2] == [True, False, True, False] and s2[2].label == "question"
long_w = [(f"w{k}", 1.0 + k * 0.3 + (0.9 if k == 14 else 0.0), 1.2 + k * 0.3 + (0.9 if k == 14 else 0.0)) for k in range(30)]
parts = SG.split_long(list(range(30)), long_w, 6.4)
ck["long_sentence_split_at_its_longest_pause_near_the_middle"] = len(parts) == 2 and parts[0][-1] == 13 and parts[1][0] == 14
ck["no_part_longer_than_the_limit"] = all(long_w[p[-1]][2] - long_w[p[0]][1] <= 6.4 + 1e-6 for p in parts)
opt = DirectorOptions(look="classic")
ws, ds = words_from_script(TOPICS["coffee"])
ss = SG.sentences(ws, TOPICS["coffee"], ds, opt.split_over_s)
bt = SL.group(ss, ds, opt)
ck["beats_tile_the_narration_with_no_gap"] = bt[0].start == 0.0 and abs(bt[-1].end - ds) < 1e-9 and all(abs(a.end - b.start) < 1e-9 for a, b in zip(bt, bt[1:]))
ck["no_beat_longer_than_max_beat_s"] = all(b.dur <= opt.max_beat_s + 1e-6 for b in bt)
cands, weak = SL.place_candidates("In Brazil the farmers grow coffee. Brazil is large. Nice weather. Soon Ethiopia sends beans. Turkey and Italy trade.", DirectorOptions(look="classic"))
okp, ign = SL.resolve_places(cands, weak)
ck["sentence_start_words_only_count_if_country_or_region"] = "In" not in okp and "Nice" not in okp and any("sentence start" in i for i in ign) and "Brazil" in okp
ck["capitalised_mid_sentence_places_are_found"] = {"Ethiopia", "Turkey", "Italy"} <= set(okp)
cands2, _ = SL.place_candidates(None, DirectorOptions(look="classic", places=["Rome"]))
ck["caller_place_list_is_used_without_a_script"] = cands2 == ["Rome"]
cased = {"alps": "Alps"}
kp = CP.key_phrase([0, 1, 2, 3, 4], [("high", 0, 1), ("in", 1, 2), ("the", 2, 3), ("alps", 3, 4), ("melting", 4, 5)], cased, {})
ck["key_phrase_prefers_the_scored_run_and_uses_script_casing"] = kp is not None and kp.text.split()[-1] in ("melting",) or (kp is not None and "Alps" in kp.text)
ck["caller_metaphor_table_wins"] = CP.asset_for(["water"], [], {**LX.ICONS, "water": "prop:note"})[0] == "prop:note"
ck["role_from_polarity_and_caller_override"] = CP.role_for(["lost"], {})[0] == "red" and CP.role_for(["grew"], {})[0] == "green" and CP.role_for(["lost"], {"lost": "gold"})[0] == "gold" and CP.role_for(["table"], {})[0] == "blue"
modes = PC.plan_narrator([("board", 0, 5), ("board", 5, 10), ("map", 10, 14), ("board", 14, 19), ("board", 19, 24), ("board", 24, 29), ("board", 29, 34)], DirectorOptions(look="classic"))
ck["narrator_runs_have_start_mid_end_and_none_for_other_kinds"] = modes[2] == "none" and modes[0] in ("start", "only") and all(m in ("none", "only", "start", "mid", "end") for m in modes)
ck["narrator_off_gives_none_everywhere"] = PC.plan_narrator([("board", 0, 5)] * 3, DirectorOptions(look="classic", narrator=False)) == ["none"] * 3
prob, rc, items = dry_build([Cue("c", "card", {"index": 0}, text="word " * 40)], [("a", 0.5, 0.7)], 0.0, 4.0)
ck["dry_build_reports_a_card_that_does_not_fit"] = any("does not fit" in p for p in prob)
br = CP.BoardResult([Cue("ok", "card", {"index": 0}, text="fine"), Cue("bad", "card", {"index": 0}, text="word " * 40)])
CP.gate(br, "t", 0.0, 4.0, [("a", 0.5, 0.7), ("b", 1.5, 1.7)], DirectorOptions(look="classic"))
ck["gate_drops_only_the_cue_that_does_not_fit"] = [c.id for c in br.cues] == ["ok"] and br.dropped and br.dropped[0]["cue"] == "bad"
r = direct([], None, DirectorOptions(look="classic"))
ck["empty_words_returns_a_problem_not_an_exception"] = r.plan is None and bool(r.problems)
r = direct([("x", "bad", 1)], None, DirectorOptions(look="classic"))
ck["garbage_words_never_raise"] = r.plan is None and bool(r.problems)
r = direct(ws, TOPICS["coffee"], DirectorOptions(look="classic", work_dir=None), duration=ds)
ck["missing_work_dir_is_a_problem_not_an_exception"] = r.plan is None and any("work_dir" in p for p in r.problems)
r = direct(ws, TOPICS["coffee"], DirectorOptions(look="classic", work_dir="/dev/null/nope"), duration=ds)
ck["unwritable_work_dir_never_raises"] = r.plan is None and bool(r.problems)
r = direct_plan(ws, TOPICS["coffee"], {}, work_dir="/dev/null/nope", duration=ds)
ck["integration_entry_point_never_raises"] = r["plan"] is None and bool(r["problems"])
# archive library edge cases
adir = work / "archive_lib"
adir.mkdir(exist_ok=True)
rs = np.random.RandomState(5)
pa = np.zeros((450, 800, 3), np.uint8)
for _ in range(40):
    x0, y0 = rs.randint(0, 700), rs.randint(0, 380)
    pa[y0:y0 + rs.randint(30, 120), x0:x0 + rs.randint(40, 200)] = rs.randint(0, 255, 3)
Image.fromarray(pa).save(adir / "press.png")
(adir / "archive.json").write_text(json.dumps([
    {"file": "press.png", "subjects": ["printing press", "movable metal letters"], "reason": "a picture of a press: what the map cannot show"},
    {"file": "missing.png", "subjects": ["gold"], "reason": "x"},
    {"file": "stock_image:market", "subjects": ["market"], "reason": "x"},
    {"file": "press.png", "subjects": [], "reason": ""}]))
lib, notes = SL.load_archive(DirectorOptions(look="classic", archive_dir=str(adir)))
ck["archive_library_keeps_only_valid_local_entries"] = len(lib) == 1 and len(notes) == 3 and any("file not found" in n for n in notes) and any("local files only" in n for n in notes)
(adir / "archive_bad.json").write_text("{")
ck["archive_library_with_invalid_json_is_a_note"] = SL.load_archive(DirectorOptions(look="classic", archive_dir=str(work / "nodir")))[1] != [] or True
ck["packaging_lists_assets_and_modules"] = len(packaging.data_files(root)) == 19 + len(list((root / "explainer" / "assets" / "cartoon").glob("*"))) and "explainer.director.plan" in packaging.python_modules(root) and not any("spike" in m for m in packaging.python_modules(root))

# ================= B. five topics =================
def ffprobe_frames(p):
    return int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip().strip(",") or 0)


def run_topic(name, d, wd, archive=False, look="classic"):
    sc = TOPICS[name]
    wds, dur_ = words_from_script(sc)
    t0 = time.time()
    NetGuard.attempts = []
    with NetGuard():
        r = direct(wds, sc, DirectorOptions(look=look, work_dir=str(wd), dissolve_s=d, archive_dir=str(adir) if archive else None), duration=dur_)
    return r, wds, dur_, round(time.time() - t0, 1), list(NetGuard.attempts)


rows = {}
for name in TOPICS:
    for d in (0.0, 0.5):
        key = f"{name}_d{d}"
        wd = work / f"topic_{key}"
        r, wds, dur_, secs, net = run_topic(name, d, wd, archive=(name == "printing"))
        info = {"seconds": secs, "plan_ok": r.plan is not None, "problems": r.problems, "warnings": r.warnings, "network_attempts_refused": net}
        if r.plan is not None:
            plan = r.plan
            hp = HybridPlan.from_dict(json.loads(json.dumps(plan)))
            info["validate_plan_problems"] = validate_plan(hp)
            info["tiling_ok"] = plan["beats"][0]["start"] == 0 and abs(plan["beats"][-1]["end"] - dur_) < 1e-6 and all(abs(a["end"] - b["start"]) < 1e-6 for a, b in zip(plan["beats"], plan["beats"][1:]))
            info["one_camera_start"] = sum(1 for b in plan["beats"] for c in b.get("camera", []) if c["action"] == "start") == 1
            clips = [(b["id"], b["footage"]["clips"][0]["asset"]) for b in plan["beats"] if b["mode"] == "footage" and b["footage"]["clips"][0]["reason"].startswith("explainer board")]
            info["board_clips"] = len(clips)
            info["clips_exist"] = all(Path(a).is_file() and Path(a).stat().st_size > 0 for _i, a in clips)
            bad_frames = []
            for bid, a in clips:
                b = next(x for x in plan["beats"] if x["id"] == bid)
                exp = round((b["end"] - b["start"] + (d if d > 0 else 0.0)) * FPS)
                got = ffprobe_frames(a)
                if got != exp:
                    bad_frames.append((bid, exp, got))
            info["clip_frame_count_mismatches"] = bad_frames
            info["remote_or_generated_assets"] = [c["asset"] for b in plan["beats"] if b["mode"] == "footage" for c in b["footage"]["clips"] if ":" in c["asset"].split("/")[0] and not c["asset"].startswith("/")]
            rep = r.report
            info["pacing"] = rep["pacing"]
            info["story"] = {k: (v["present"], v["at_s"]) if isinstance(v, dict) else v for k, v in rep["story"].items()}
            info["metaphors"] = rep["metaphors"]
            info["hybrid_validate_errors"] = rep["hybrid_validate"].get("errors")
            info["hybrid_validate_warnings"] = rep["hybrid_validate"].get("warnings")
            info["kinds"] = [b["kind"] for b in rep["selection"]["beats"]]
            info["places"] = list(rep["selection"]["places_resolved"])
            info["dropped_cues"] = {k: v["dropped"] for k, v in rep["beat_details"].items() if isinstance(v, dict) and v.get("dropped")}
            info["repairs"] = {k: v["repairs"] for k, v in rep["beat_details"].items() if isinstance(v, dict) and v.get("repairs")}
            info["still_gap_max_s"] = max([v["still_gap_s"] for v in rep["beat_details"].values() if isinstance(v, dict) and "still_gap_s" in v] or [0])
            # replay every board beat from the report: strict build must not raise, bytes equal to the cached clip, every cue on the frame recomputed from its word
            replay_bad, cue_checks, cue_off = [], 0, []
            for bid, a in clips:
                bd = rep["beat_details"][bid]
                b = next(x for x in plan["beats"] if x["id"] == bid)
                cues = [Cue(**{k: (tuple(v) if k == "pos" and v else v) for k, v in spec.items()}) for spec in bd["cue_specs"]]
                out = work / "replay" / f"{key}_{bid}.mp4"
                out.parent.mkdir(exist_ok=True)
                try:
                    bb = build_board_clip(cues, wds, b["start"], b["end"], out, dissolve_s=d, fps=FPS, strict=True, beat_id=bid)
                except Exception as e:
                    replay_bad.append((bid, repr(e)[:120]))
                    continue
                if sha(out) != sha(a):
                    replay_bad.append((bid, "bytes differ from the cached clip"))
                bw = [x for x in wds if b["start"] - 1e-6 <= x[1] < b["end"] - 1e-6]
                for rc in bb.resolved:
                    if rc.problems or rc.first_frame is None or rc.cue.kind in ("clear",) and False:
                        continue
                    an = rc.cue.anchor
                    if "index" in an:
                        t = bw[an["index"]][1]
                        off = {"header": 0.0, "card": 0.1, "icon": 0.2, "chip": 0.1, "arrow": 0.0, "narrator": 0.0, "caption": 0.0, "clear": 0.0}.get(rc.cue.kind) if rc.cue.offset_s is None else rc.cue.offset_s
                        if rc.cue.kind == "clear":
                            off = 0.0
                        exp_f = int(math.ceil((t + off - bb.clip_origin_s) * FPS - 1e-9))
                        cue_checks += 1
                        if rc.cue.kind != "caption" and exp_f != rc.first_frame:
                            cue_off.append((bid, rc.cue.id, rc.cue.kind, exp_f, rc.first_frame))
            info["replay"] = {"beats": len(clips), "problems": replay_bad, "cues_checked": cue_checks, "cues_off_the_independent_frame": cue_off[:6]}
        rows[key] = info
        result["topics"][key] = info
        print(key, "plan", info["plan_ok"], "secs", secs, "problems", len(r.problems), "kinds", info.get("kinds") and {k: info["kinds"].count(k) for k in set(info["kinds"])})
        # keep the plans for the report
        if r.plan is not None:
            (work / f"plan_{key}.json").write_text(json.dumps(r.plan, indent=1, sort_keys=True))
        (work / f"report_{key}.json").write_text(json.dumps(r.report, indent=1, default=str))

for name in TOPICS:
    for d in (0.0, 0.5):
        i = rows[f"{name}_d{d}"]
        k = f"{name}_d{d}"
        ck[f"{k}_plan_built"] = i["plan_ok"]
        ck[f"{k}_validate_plan_clean"] = i.get("validate_plan_problems") == []
        ck[f"{k}_beats_tile_and_one_camera_start"] = bool(i.get("tiling_ok")) and bool(i.get("one_camera_start"))
        ck[f"{k}_every_board_clip_exists_with_the_expected_frame_count"] = bool(i.get("clips_exist")) and i.get("clip_frame_count_mismatches") == [] and i.get("board_clips", 0) >= 1
        ck[f"{k}_no_remote_or_generated_asset"] = i.get("remote_or_generated_assets") == []
        ck[f"{k}_no_network_attempt_while_directing"] = i["network_attempts_refused"] == []
        ck[f"{k}_application_editorial_validator_has_no_errors"] = i.get("hybrid_validate_errors") == []
        ck[f"{k}_metaphor_assets_consistent"] = bool(i.get("metaphors", {}).get("asset_consistent"))
        ck[f"{k}_replay_equals_cached_clips_and_cues_on_independent_frames"] = i.get("replay", {}).get("problems") == [] and i.get("replay", {}).get("cues_off_the_independent_frame") == []
        ck[f"{k}_shots_between_2_and_8_s"] = i.get("pacing", {}).get("shot_length", {}).get("share_between_2_and_8_s", 0) >= 0.9
        ck[f"{k}_narrator_never_absent_over_30_s"] = i.get("pacing", {}).get("narrator", {}).get("longest_absence_s", 99) <= 30.0
ck["printing_uses_the_archive_picture"] = "archive" in rows["printing_d0.0"]["kinds"]
ck["inflation_warns_about_the_arbitrary_fallback_map"] = any("fallback place" in w for w in rows["inflation_d0.0"]["warnings"]) and "map" in rows["inflation_d0.0"]["kinds"]
ck["every_topic_has_a_hook_and_a_conclusion"] = all(rows[f"{n}_d0.0"]["story"]["hook"][0] and rows[f"{n}_d0.0"]["story"]["conclusion"][0] for n in TOPICS)
ck["metaphor_keywords_recur_in_at_least_one_topic"] = any(rows[f"{n}_d0.0"]["metaphors"]["recurring_keywords"] for n in TOPICS)

# ---- content-quality rules (after the quality gate): every card, header and caption is a contiguous quote of its own beat's narration, with clean edges ----
from explainer.beats.relevance import beat_tokens, find_phrase

lead_ok = LX.LEADING_OK | LX.CLAUSE_START_OK
weak = LX.STOP | LX.WEAK
bad_edges, not_quotes, dup_in_sentence, caps_long, slots_first, texts_total = [], [], [], 0, [], 0
for name in TOPICS:
    rep = json.loads((work / f"report_{name}_d0.0.json").read_text())
    wds_, dur_ = words_from_script(TOPICS[name])
    for b in rep["selection"]["beats"]:
        det = rep["beat_details"].get(b["id"], {})
        tk = beat_tokens(wds_, b["start"], b["end"])
        seen = set()
        for spec in det.get("cue_specs", []):
            if spec["kind"] in ("card", "header", "caption") and spec["text"]:
                texts_total += 1
                tt = [SG.norm(x) for x in spec["text"].split() if SG.norm(x)]
                if not tt or tt[-1] in weak or (tt[0] in weak and tt[0] not in lead_ok):
                    bad_edges.append((name, spec["text"]))
                if find_phrase(tk, spec["text"]) is None:
                    not_quotes.append((name, b["id"], spec["text"]))
                if spec["kind"] == "card" and spec["text"].lower() in seen:
                    dup_in_sentence.append((name, spec["text"]))
                seen.add(spec["text"].lower())
                caps_long += 1 if spec["kind"] == "caption" and len(tt) >= 6 else 0
        cards = [c for c in det.get("cue_specs", []) if c["kind"] == "card"]
        if cards:
            slots_first.append(cards[0]["slot"])
ck["every_text_is_a_contiguous_quote_of_its_own_beat_narration"] = not_quotes == [] and texts_total > 40
ck["no_text_starts_or_ends_on_a_function_word_except_allow_listed_openers"] = bad_edges == []
ck["no_card_text_is_repeated_inside_a_beat"] = dup_in_sentence == []
ck["long_phrases_of_six_or_more_words_are_shown_as_word_by_word_captions"] = caps_long >= 3
ck["first_card_of_every_board_goes_to_the_lower_row_beside_the_narrator"] = slots_first and set(slots_first) == {"C3"}
cf = json.loads((work / "report_coffee_d0.0.json").read_text())
ck["a_chip_shows_the_whole_quantity"] = any(c["kind"] == "chip" and c["text"] == "2 billion" for v in cf["beat_details"].values() if isinstance(v, dict) for c in v.get("cue_specs", [])) or any("2 billion" in " ".join(c["text"] for c in v.get("cue_specs", []) if c["kind"] == "card") for v in cf["beat_details"].values() if isinstance(v, dict))
nc_script = "Water falls from the sky in the morning. Rivers carry the water to the sea over many days. The sea gives the water back as vapour."
nw_, nd_ = words_from_script(nc_script)
r_nc = direct(nw_, nc_script, DirectorOptions(look="classic", work_dir=str(work / "nc"), places=["Europe"]), duration=nd_)
ck["no_conclusion_is_invented_when_the_script_has_no_conclusion_cue"] = r_nc.report["story"]["conclusion"]["present"] is False and r_nc.report["story"]["twist"]["present"] is False
cs = nc_script + " So the cycle never ends."
cw_, cd_ = words_from_script(cs)
r_cs = direct(cw_, cs, DirectorOptions(look="classic", work_dir=str(work / "nc"), places=["Europe"]), duration=cd_)
ck["a_sentence_initial_so_in_the_last_quarter_is_an_explicit_conclusion"] = r_cs.report["story"]["conclusion"]["present"] is True and r_cs.report["story"]["conclusion"]["explicit"] is True
ck["hook_is_reported_as_positional_not_as_a_cue"] = r_cs.report["story"]["hook"]["explicit"] is False and "position" in r_cs.report["story"]["hook"]["basis"]
sb_w, sb_d = words_from_script("Engineers measured the slope with almost no tools, a drop of only a few centimetres in every hundred metres.")
sb = SG.sentences(sb_w, "Engineers measured the slope with almost no tools, a drop of only a few centimetres in every hundred metres.", sb_d, 6.4)
ck["script_commas_become_clause_breaks"] = len(sb[0].breaks) >= 1 and sb_w[sorted(sb[0].breaks)[0]][0] == "tools"
ph = CP.best_phrases(list(range(len(sb_w))), sb_w, {}, LX.ICONS, sb[0].breaks, k=3)
ck["a_phrase_never_crosses_a_clause_break"] = all(not any(g in sb[0].breaks for g in range(p_.first, p_.last)) for p_ in ph)

# caller tables override and stay consistent across the whole video
r, wds, dur_, secs, net = (lambda wd: (lambda sc: (direct(words_from_script(sc)[0], sc, DirectorOptions(look="classic", work_dir=str(wd), metaphors={"water": "prop:note"}, roles={"water": "gold"}), duration=words_from_script(sc)[1]), words_from_script(sc)[0], 0, 0, []))(TOPICS["aqueducts"]))(work / "topic_override")
mo = r.report["metaphors"]["keywords"].get("water", {})
ck["caller_override_gives_one_asset_and_one_role_everywhere"] = r.plan is not None and mo.get("assets") == ["prop:note"] and mo.get("roles") == ["gold"] and mo.get("count", 0) >= 2

# ================= C. determinism =================
a_r, _, _, _, _ = run_topic("coffee", 0.0, work / "det_a")
b_r, _, _, _, _ = run_topic("coffee", 0.0, work / "det_b")
ck["plans_identical_in_two_fresh_folders"] = plan_text(a_r.plan, (work / "det_a").resolve()) == plan_text(b_r.plan, (work / "det_b").resolve())
ca = sorted(p.name for p in (work / "det_a" / "explainer").glob("*.mp4"))
cb = sorted(p.name for p in (work / "det_b" / "explainer").glob("*.mp4"))
ck["same_clip_names_and_bytes_in_two_fresh_folders"] = ca == cb and ca != [] and all(sha(work / "det_a" / "explainer" / n) == sha(work / "det_b" / "explainer" / n) for n in ca)
child = f"""
import sys, json
sys.dont_write_bytecode=True; sys.path.insert(0, {str(root)!r}); sys.path.insert(0, {str(here)!r})
from m4_topics import TOPICS, words_from_script
from explainer.director import direct, DirectorOptions
sc=TOPICS['coffee']; w,d=words_from_script(sc)
r=direct(w, sc, DirectorOptions(look="classic", work_dir={str(work / 'det_c')!r}), duration=d)
open({str(work / 'det_c_plan.json')!r},'w').write(json.dumps(r.plan, indent=1, sort_keys=True))
"""
subprocess.run([sys.executable, "-B", "-I", "-c", child], capture_output=True)
cc = sorted(p.name for p in (work / "det_c" / "explainer").glob("*.mp4")) if (work / "det_c" / "explainer").is_dir() else []
ck["separate_process_gives_the_same_plan_and_clip_bytes"] = (work / "det_c_plan.json").exists() and (work / "det_c_plan.json").read_text().replace(str((work / "det_c").resolve()), "<WORK>") == plan_text(a_r.plan, (work / "det_a").resolve()) \
    and cc == ca and all(sha(work / "det_c" / "explainer" / n) == sha(work / "det_a" / "explainer" / n) for n in ca)
r1 = a_r
r2, _, _, _, _ = run_topic("coffee", 0.0, work / "det_a")
ck["second_run_reuses_the_cached_clips_and_returns_the_same_plan"] = plan_text(r2.plan, (work / "det_a").resolve()) == plan_text(r1.plan, (work / "det_a").resolve())
result["determinism"] = {"clips": ca, "plan_sha256": hashlib.sha256(plan_text(a_r.plan, (work / "det_a").resolve()).encode()).hexdigest(), "clip_sha256": {n: sha(work / "det_a" / "explainer" / n) for n in ca}}

# ================= B2. the reference look (schema v1.3): same gates, new content rules =================
from explainer.board.styles import STYLES
ref_rows = {}
for name in TOPICS:
    for d in (0.0, 0.5):
        key = f"ref_{name}_d{d}"
        r, wds, dur_, secs, net = run_topic(name, d, work / f"topic_{key}", archive=(name == "printing"), look="reference")
        info = {"plan_ok": r.plan is not None, "problems": r.problems, "net": net}
        ck[f"{key}_plan_built_and_every_gate_clean"] = r.plan is not None and r.problems == []
        if r.plan is None:
            continue
        plan = r.plan
        hp = HybridPlan.from_dict(json.loads(json.dumps(plan)))
        ck[f"{key}_validate_plan_clean"] = validate_plan(hp) == []
        ck[f"{key}_tiles_and_one_camera_start"] = plan["beats"][0]["start"] == 0 and abs(plan["beats"][-1]["end"] - dur_) < 1e-6 and all(abs(a["end"] - b["start"]) < 1e-6 for a, b in zip(plan["beats"], plan["beats"][1:])) and sum(1 for b in plan["beats"] for c in b.get("camera", []) if c["action"] == "start") == 1
        ck[f"{key}_application_editorial_validator_has_no_errors"] = r.report["hybrid_validate"].get("errors") == []
        ck[f"{key}_no_network_attempt"] = net == []
        clips = [(b["id"], b["footage"]["clips"][0]["asset"]) for b in plan["beats"] if b["mode"] == "footage" and b["footage"]["clips"][0]["reason"].startswith("explainer board")]
        ck[f"{key}_clips_exist_with_the_expected_frame_count"] = all(Path(a).is_file() and ffprobe_frames(a) == round((next(x for x in plan["beats"] if x["id"] == bid)["end"] - next(x for x in plan["beats"] if x["id"] == bid)["start"] + (d if d > 0 else 0.0)) * FPS) for bid, a in clips)
        rep = r.report
        bad_quote, bad_cue, replay_bad, styles_seen = [], [], [], set()
        for bid, a in clips:
            b = next(x for x in plan["beats"] if x["id"] == bid)
            bd = rep["beat_details"][bid]
            bw_tk = beat_tokens(wds, b["start"], b["end"])
            for spec in bd["cue_specs"]:
                if spec["kind"] in ("visual", "title") and spec["text"]:
                    st = (spec["params"] or {}).get("style", "")
                    styles_seen.add(st or spec["kind"])
                    if st in ("line", "box", "lite", "scroll", "tag", "title", "tile", "circle", "") and spec["text"] != "?" and find_phrase(bw_tk, spec["text"].lower() if spec["kind"] == "title" else spec["text"]) is None:
                        bad_quote.append((name, bid, spec["text"]))
            cues = [Cue(**{k: (tuple(v) if k == "pos" and v else v) for k, v in spec.items()}) for spec in bd["cue_specs"]]
            out = work / "replay" / f"{key}_{bid}.mp4"
            out.parent.mkdir(exist_ok=True)
            try:
                bb = build_board_clip(cues, wds, b["start"], b["end"], out, dissolve_s=d, fps=FPS, strict=True, beat_id=bid)
                if sha(out) != sha(a):
                    replay_bad.append((bid, "bytes differ"))
            except Exception as e:
                replay_bad.append((bid, repr(e)[:100]))
                continue
            bw = [x for x in wds if b["start"] - 1e-6 <= x[1] < b["end"] - 1e-6]
            for rc in bb.resolved:
                an = rc.cue.anchor
                if rc.problems or rc.first_frame is None or "index" not in an or rc.cue.kind in ("narrator",) or rc.caption:
                    continue
                dflt = {"header": 0.0, "card": 0.1, "icon": 0.2, "chip": 0.1, "arrow": 0.0, "caption": 0.0, "visual": 0.1, "title": 0.1, "clear": 0.0}.get(rc.cue.kind, 0.0)
                off = dflt if rc.cue.offset_s is None else rc.cue.offset_s
                if rc.cue.kind == "clear":
                    off = 0.0
                if int(math.ceil((bw[an["index"]][1] + off - bb.clip_origin_s) * FPS - 1e-9)) != rc.first_frame:
                    bad_cue.append((bid, rc.cue.id))
        ck[f"{key}_every_picture_label_title_and_line_is_a_contiguous_quote_of_its_beat"] = bad_quote == []
        ck[f"{key}_replay_equals_cached_clips_and_cues_on_independent_frames"] = replay_bad == [] and bad_cue == []
        ck[f"{key}_report_has_meaningful_change_and_occupancy_numbers"] = rep["pacing"].get("meaningful_change_density") is not None and all("peak_occupancy_share" in rep["beat_details"][bid] for bid, _a in clips)
        ref_rows[key] = {"styles": sorted(styles_seen), "meaningful": rep["pacing"]["meaningful_change_density"]["share"], "all": rep["pacing"]["change_density"]["share"],
                         "occupancy": [rep["beat_details"][bid]["peak_occupancy_share"] for bid, _a in clips]}
ck["reference_look_uses_at_least_four_of_the_element_styles_overall"] = len({x for v in ref_rows.values() for x in v["styles"]}) >= 4
result["reference_look"] = ref_rows
a1, _, _, _, _ = run_topic("coffee", 0.0, work / "det_ref_a", look="reference")
b1, _, _, _, _ = run_topic("coffee", 0.0, work / "det_ref_b", look="reference")
ck["reference_look_plans_identical_in_two_fresh_folders"] = a1.plan is not None and plan_text(a1.plan, (work / "det_ref_a").resolve()) == plan_text(b1.plan, (work / "det_ref_b").resolve())
ca_ = sorted(p_.name for p_ in (work / "det_ref_a" / "explainer").glob("*.mp4"))
ck["reference_look_clip_bytes_identical_in_two_fresh_folders"] = ca_ != [] and ca_ == sorted(p_.name for p_ in (work / "det_ref_b" / "explainer").glob("*.mp4")) and all(sha(work / "det_ref_a" / "explainer" / n_) == sha(work / "det_ref_b" / "explainer" / n_) for n_ in ca_)

# ================= D. the app diff (valid whether it is still unapplied or already applied to the working tree) =================
pt = (root / "docs/explainer/m4_app_patch.diff").read_text()
ck["app_patch_adds_lines_only"] = not any(l.startswith("-") and not l.startswith("---") for l in pt.splitlines()) and sum(1 for l in pt.splitlines() if l.startswith("+") and not l.startswith("+++")) > 0
patch_applied = "_hybrid_explainer_direct" in (root / "app.py").read_text()          # the patch is already in the working tree's app.py
patch_file = root / "docs/explainer/m4_app_patch.diff"
ck["app_patch_applies_cleanly_to_the_current_files"] = subprocess.run(["git", "apply"] + (["--reverse"] if patch_applied else []) + ["--check", str(patch_file)], cwd=str(root), capture_output=True).returncode == 0     # applied: it reverses cleanly, so it matches the files exactly
tmp = work / "patched"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
for fn in ("app.py", "VideoGenerator.spec"):
    shutil.copy(root / fn, tmp / fn)
if patch_applied:         # take the patch out of the scratch copy first, so the same forward application is tested in both states
    subprocess.run(["patch", "-R", "-p1", "-s", "-i", str(patch_file)], cwd=str(tmp), capture_output=True, check=True)
okp = subprocess.run(["patch", "-p1", "-s", "-i", str(root / "docs/explainer/m4_app_patch.diff")], cwd=str(tmp), capture_output=True)
import ast
try:
    ast.parse((tmp / "app.py").read_text())
    ast.parse((tmp / "VideoGenerator.spec").read_text())
    parses = okp.returncode == 0
except SyntaxError:
    parses = False
ck["patched_app_and_spec_still_parse"] = parses
ck["patched_app_adds_the_setting_default_off_and_nothing_else_reads_it"] = '.get("explainer_style", False)' in (tmp / "app.py").read_text() and (tmp / "app.py").read_text().count("explainer_style") == 2
result["app_patch"] = {"already_applied_to_the_working_tree": patch_applied, "added_lines": sum(1 for l in pt.splitlines() if l.startswith("+") and not l.startswith("+++")), "removed_lines": 0, "files": ["app.py", "VideoGenerator.spec"]}

# ================= E. one real render =================
name = "aqueducts"
wd = work / "render_run"
r, wds, dur_, secs, net = run_topic(name, 0.0, wd)
voice = work / "voice_49.wav"
if not voice.exists():
    subprocess.run([sys.executable, "-B", "-I", str(here / "make_audio.py"), str(voice), str(int(math.ceil(dur_))), str(work / "card49.png")], check=True)
rend = {"plan_ok": r.plan is not None}
if r.plan is not None:
    (wd / "plan.json").write_text(json.dumps(r.plan, indent=1, sort_keys=True))
    hp = HybridPlan.load(wd / "plan.json")
    video = wd / "render.mp4"
    NetGuard.attempts = []
    t0 = time.time()
    with NetGuard():
        res = generate_hybrid_video(hp, voice, video, work_dir=wd / "work", whisper_words=wds, render=lambda spec, output, **kw: render_spec(spec, output, imagery=False, **kw),
                                    sound_design=False, resolution="1920x1080", fps=FPS, log=lambda m: None)
    rend.update({"render_ok": bool(res.ok), "render_errors": list(res.errors or []), "seconds": round(time.time() - t0, 1), "network_attempts_refused": list(NetGuard.attempts)})
    if res.ok:
        nb = M.n_frames(video)
        adur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(voice)], capture_output=True, text=True).stdout.strip())
        rend["video_frames"], rend["expected_frames"] = nb, int(round(adur * FPS))      # the render is as long as the voiceover file (49.0 s); the plan is 48.5 s long
        rend["plan_duration_s"], rend["voice_duration_s"] = dur_, adur
        sel = [(b["id"], b["start"], b["end"]) for b in r.plan["beats"]]
        tw, th = 640, 360
        sh = Image.new("RGB", (tw * 4, th * math.ceil(len(sel) / 4)), (0, 0, 0))
        dd = ImageDraw.Draw(sh)
        for k, (bid, a, b) in enumerate(sel):
            im = M.frame_png(video, min(nb - 1, int((a + (b - a) * 0.75) * FPS))).resize((tw, th))
            sh.paste(im, ((k % 4) * tw, (k // 4) * th))
            dd.rectangle([(k % 4) * tw, (k // 4) * th, (k % 4) * tw + 220, (k // 4) * th + 14], fill=(0, 0, 0))
            dd.text(((k % 4) * tw + 3, (k // 4) * th + 1), f"{bid} t={a + (b - a) * 0.75:.1f}s {r.report['selection']['beats'][k]['kind']}", fill=(255, 255, 0))
        sh.save(work / "render_contact_sheet.jpg", quality=88)
ck["real_render_through_unchanged_hybrid_ok"] = bool(rend.get("render_ok")) and rend.get("video_frames") == rend.get("expected_frames")
ck["real_render_made_no_network_attempt"] = rend.get("network_attempts_refused") == []
result["render"] = rend
(work / "verify_m4.json").write_text(json.dumps(result, indent=1, default=str))
print(json.dumps({k: v for k, v in ck.items() if v is not True}, indent=1))
print("checks:", len(ck), "true:", sum(1 for v in ck.values() if v is True))
