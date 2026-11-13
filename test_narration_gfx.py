"""product_trailer/narration_gfx.py: narration shapes -> graphics and 3D props, with the repeat caps (synthetic sentences, not one video's)."""
from product_trailer import narration_gfx as G


def kinds(got):
    return {i: (d.get("object") or d["layer"]["type"]) for i, d in got.items()}


def test_steps_run_builds_with_path_and_app():
    L = ["Here is how to sign up.", "One: install Acme Hub from the App Market.", "Two: tap the Beta Program card.",
         "Three: go to Settings, Software update, and tap Download now."]
    got = G.plan(L)
    assert [got[i]["layer"]["n"] for i in (1, 2, 3)] == [1, 2, 3]
    assert got[1]["layer"]["target"] == "Acme Hub" and got[1]["layer"]["app"] == "App Market"
    assert got[2]["layer"]["app"] == "Acme Hub" and got[2]["layer"]["target"] == "Beta Program card"
    assert got[3]["layer"]["target"] == "Download now" and got[3]["layer"]["text"].startswith("Go to Settings")


def test_checklist_builds_and_stops_at_recap():
    L = ["Here's your packing checklist.", "Charge the battery.", "Pack a cable.", "And bring a case.", "Let me recap.", "Known: a, b."]
    got = G.plan(L)
    assert all(got[i]["layer"]["mode"] == "check" for i in (1, 2, 3)) and 4 not in got
    items = got[3]["layer"]["items"]
    assert [x.get("done", False) for x in items] == [True, True, False] and items[2]["text"] == "Bring a case"


def test_breakdown_parts_sum_and_inner():
    got = G.plan(["The update fixes 120 bugs: 100 system fixes, including 9 urgent ones, and 20 app fixes."])
    L = got[0]["layer"]
    assert L["total"] == 120 and [p["value"] for p in L["parts"]] == [100, 20] and L["inner"]["value"] == 9 and L["inner"]["of"] == 0


def test_chips_ledger_months_and_caps():
    got = G.plan(["It ships to five markets: France, Spain, Italy, Japan and Brazil.", "You may need to wait.",
                  "Known: the name, the price.", "Unknown: the date."])
    k = kinds(got)
    assert k[0] == "pt_list" and got[0]["layer"]["title"] == "five markets" and len(got[0]["layer"]["items"]) == 5
    assert 1 not in got                                     # "may" is not the month May
    assert k[2] == k[3] == "pt_ledger" and got[3]["layer"]["active"] == 1


def test_props_rotate_moves_and_respect_caps():
    L = ["A new firmware build hit the servers.", "Another build reached the servers.", "Then the security patch came.",
         "The beta opened on March 3.", "A third build appeared on the servers.", "A fourth build appeared on the servers.", "Yet another build hit the servers."]
    got = G.plan(L)
    k = kinds(got)
    assert k[0] == "server" and 1 not in got                # the same kind not again right away
    assert list(k.values()).count("server") <= G.CAP["server"]
    moves = [got[i]["move"] for i in sorted(got) if "move" in got[i]]
    assert all(a != b for a, b in zip(moves, moves[1:]))    # no camera move twice in a row
    assert got[3]["pages"][-1] == {"month": "Mar", "day": "3"}


def test_apply_replaces_director_pick_but_keeps_authors():
    parsed = {"chapters": [{"title": "", "items": [{"kind": "macro", "text": "x"}, {"kind": "line", "text": "Betas can have bugs."},
                                                   {"kind": "chip", "_own": True}, {"kind": "line", "text": "Battery life can be worse."}]}]}
    out = G.apply(parsed, log=lambda m: None)
    ks = [it["kind"] for it in out["chapters"][0]["items"]]
    assert ks == ["gfx", "line", "chip", "gfx", "line"]


def test_a_held_3d_prop_never_becomes_an_empty_black_shot():
    """A sentence with no picture after a 3D prop (no 2D layers) keeps the prop moving; it used to be copied as a blank black shot."""
    from product_trailer import review, voiceover as V
    lines = ["Last year the beta opened on December 8 for everyone who signed up early.",
             "Analysts think it may slip a little this time around.", "Nobody has said anything official yet about any of it."]
    parsed = review.parse_script("# R\n[chip: X]\n" + "\n".join(lines) + "\n")
    parsed = G.apply(parsed, log=lambda m: None)
    pack = review.plan_review_scenes(parsed, "galaxy s26 ultra", ["Black"])
    W, t = [], 0.5
    for ln in lines:
        for w in ln.split():
            W.append((w.strip(".,"), round(t, 3), round(t + 0.3, 3)))
            t += 0.42
        t += 0.6
    spec = review.plan_review_timed(parsed, pack, {}, V.align_lines(lines, W, W[-1][2] + 1.0), W, style="follow")
    assert any(s.get("object") == "calendar" for s in spec["shots"])
    for s in spec["shots"]:
        if s["kind"] == "black":
            assert any(L["start"] < s["end"] and L["end"] > s["start"] for L in spec["layers"] if L["type"] != "pt_subtitle"), f"empty black shot {s}"
