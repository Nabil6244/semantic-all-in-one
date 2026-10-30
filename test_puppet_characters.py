"""Puppet characters: python3 test_puppet_characters.py"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image
import health_cinema.puppet as P
from health_cinema.puppet import actions as A, cast

OUT = Path(__file__).resolve().parent / "out" / "puppet_cache"


def test_all_render():
    assert len(P.list_characters()) >= 7 and len(P.list_actions()) >= 17
    for a in ("walk_phone", "knock", "carry_box_walk", "shrug", "think", "lean"): assert a in P.list_actions(), a
    for c in ("courier", "shopkeeper"): assert c in P.list_characters(), c
    for c in P.list_characters():
        for a in P.list_actions():
            d = P.action_duration(a); assert d > 0
            for t in (0.0, d * 0.5, d):
                im, (ax, ay) = P.render_character_frame(c, a, t, 0.6)
                assert im.mode == "RGBA" and im.width > 2 and im.height > 20, (c, a)
                assert 0 <= ax < im.width and 0 <= ay < im.height, (c, a, t, ax, ay, im.size)
                assert np.asarray(im)[..., 3].max() > 200, (c, a)


DUTY = {"walk": 0.62, "walk_phone": 0.64, "carry_box_walk": 0.64, "run": 0.36}


def test_feet_on_ground_and_locked():
    for c in P.list_characters():
        rig = cast.get_rig(c); d = rig.d
        for act, duty in DUTY.items():
            D = A.get(act).stride(d, {"prop": None}); assert D and D > 50 and A.get(act).cyclic
            ref = {}
            for i in range(120):
                ph = i / 120 * 2
                pose = A.get(act).pose_at(0, {"prop": None}, d, ph); J = rig.joints(pose)
                low = max(J["bottom_a"], J["bottom_b"])
                if act != "run": assert abs(low) < 1.0, (c, act, ph, low)         # lowest sole on the ground (run has a flight phase)
                else: assert low < 1.0 and low > -40, (c, act, ph, low)
                hx = D * ph  # hip world travel
                for s_, off in (("b", 0.0), ("a", 0.5)):
                    u = (ph + off) % 1.0
                    if 0.03 < u < duty - 0.03:   # stance: ankle world x must not slide
                        key = (s_, int((ph + off) // 1))
                        wx = J["ankle_" + s_][0] + hx
                        ref.setdefault(key, wx); assert abs(wx - ref[key]) < 2.5, (c, act, s_, ph, wx, ref[key])
                        assert abs(J["bottom_" + s_]) < 1.0, (c, act, s_, ph, J["bottom_" + s_])


def test_standing_actions_keep_a_foot_on_the_ground():
    for c in P.list_characters():
        rig = cast.get_rig(c)
        for a in P.list_actions():
            if A.get(a).cyclic or a == "stop": continue
            D = P.action_duration(a)
            for k in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
                J = rig.joints(A.get(a).pose_at(D * k, {}, rig.d))
                assert abs(max(J["bottom_a"], J["bottom_b"])) < 1.5, (c, a, k, J["bottom_a"], J["bottom_b"])


def test_motion_is_smooth_and_has_life():
    """no pose jumps between adjacent frames (30 fps) and the idle/gesture clips actually move"""
    d = cast.get_rig("suit_man").d
    for a in P.list_actions():
        act = A.get(a); D = P.action_duration(a); prev = None; tot = 0.0
        for i in range(int(D * 30) + 1):
            ph = i / 30 / (act.period or 1) if act.cyclic else None
            pose = act.pose_at(i / 30, {}, d, ph)
            if prev:
                for k in ("lean", "head", "uab", "uaa", "fab", "faa", "thb", "tha", "shb", "sha", "sh_dy", "squash"):
                    assert abs(pose[k] - prev[k]) < 45 or k == "squash", (a, k, i, pose[k], prev[k])
                tot += abs(pose["lean"] - prev["lean"]) + abs(pose["head"] - prev["head"]) + abs(pose["uab"] - prev["uab"])
            prev = pose
        assert tot > 1.0, (a, tot)


def test_fit_height_and_scale():
    from health_cinema.puppet import character as C
    far, near = C.fit_height(1080, 0.62, 0.5), C.fit_height(1080, 0.92, 0.5)
    assert 0.34 * 1080 <= far < near <= 0.54 * 1080 + 1e-6, (far, near)
    assert abs(C.fit_height(1080, 0.88, 0.48) / 1080 - 0.47) < 0.03
    assert C.fit_height(1080, 0.9, 0.5, 0.40) > C.fit_height(1080, 0.7, 0.5, 0.40)
    sc = C.scale_for_height("suit_man", 450); im, (ax, ay) = P.render_character_frame("suit_man", "stand_idle", 0.0, sc)
    bb = im.getbbox(); assert 0.85 * 450 < ay - bb[1] < 1.2 * 450, (ay - bb[1])


def test_tint_and_sticker_look():
    import numpy as np
    sc = 0.9; a, _ = P.render_character_frame("woman", "stand_idle", 0.0, sc)
    b, _ = P.render_character_frame("woman", "stand_idle", 0.0, sc, tint=(1.15, 1.0, 0.8))
    assert a.size == b.size
    A_, B_ = np.asarray(a, float), np.asarray(b, float); m = A_[..., 3] > 250
    assert B_[m][:, 0].mean() > A_[m][:, 0].mean() and B_[m][:, 2].mean() < A_[m][:, 2].mean()
    # inked (not grey, not washed out): a real dark ink share, and the figure is warm (red > blue) on average
    lum = A_[m][:, :3].mean(1); assert (lum < 70).mean() > 0.05, (lum < 70).mean()
    assert A_[m][:, 0].mean() > A_[m][:, 2].mean() + 15
    # white paper border: a ring of near-white opaque pixels around the figure
    assert ((A_[..., 3] > 250) & (A_[..., :3].min(-1) > 215)).sum() > 0.02 * m.sum()


def test_frame_speed():
    import time
    P.render_character_frame("worker", "walk", 0.0, 1.0); t = time.time()
    for i in range(8): P.render_character_frame("worker", "walk", 0.1 * i, 1.0)
    assert (time.time() - t) / 8 < 0.25     # ~50 ms on an idle machine; loose bound so a busy box does not flake


def test_every_character_has_cached_parts_for_new_props():
    for c in ("courier", "shopkeeper"):
        rig = cast.get_rig(c)
        for pn in ("clipboard", "newspaper", "briefcase", "box"): assert "prop_" + pn in rig.parts


def test_distance_mode_matches_phase():
    D = P.stride_length("suit_man", "walk", 0.5); assert D > 50
    a, _ = P.render_character_frame("suit_man", "walk", 0, 0.5, params={"distance": D * 0.3})
    b, _ = P.render_character_frame("suit_man", "walk", 0, 0.5, ground_phase=0.3)
    assert np.array_equal(np.asarray(a), np.asarray(b))


def test_facing_mirror():
    r, (rx, ry) = P.render_character_frame("worker", "stand_idle", 0.5, 0.6, "right")
    l, (lx, ly) = P.render_character_frame("worker", "stand_idle", 0.5, 0.6, "left")
    assert r.size == l.size and abs(ry - ly) < 1e-6 and abs((r.width - rx) - lx) < 1.5
    assert np.abs(np.asarray(r.transpose(Image.FLIP_LEFT_RIGHT)).astype(int) - np.asarray(l).astype(int)).max() < 2


def test_turn_flips():
    w = [P.render_character_frame("woman", "turn", t, 0.6)[0].width for t in (0.0, 0.4, 0.8)]
    assert w[1] < 0.45 * w[0] and abs(w[2] - w[0]) < 0.1 * w[0], w


def test_pick_up_box_moves():
    p0 = A.get("pick_up").pose_at(0.2, {}, A.DEFAULT_D)["prop"]; p1 = A.get("pick_up").pose_at(2.0, {}, A.DEFAULT_D)["prop"]
    assert p0["y"] > p1["y"] - 1e-9 or p0["y"] != p1["y"]
    assert p1["y"] < -150, p1   # carried up at chest height


def test_stop_decelerates():
    d = A.DEFAULT_D; assert A.stop_travel(0.9, {}, d) > A.stop_travel(0.45, {}, d) > 0
    assert P.action_travel("child", "stop", 0.9, 0.5) > 0 and P.action_travel("child", "walk", 1, 0.5) == 0


def test_cache_on_disk():
    assert any(p.is_dir() and p.name.startswith("suit_man_v") and (p / "torso.png").is_file() for p in OUT.iterdir())


def contact_sheet():
    chars, acts = P.list_characters(), P.list_actions(); CW, CH = 340, 400
    sheet = Image.new("RGB", (CW * len(acts), CH * len(chars)), (120, 100, 80))
    for i, c in enumerate(chars):
        for j, a in enumerate(acts):
            im, (ax, ay) = P.render_character_frame(c, a, P.action_duration(a) * 0.4, 0.5, ground_phase=0.15 if A.get(a).cyclic else None)
            sheet.paste(im, (int(j * CW + CW / 2 - ax), int(i * CH + CH - 30 - ay)), im)
    OUT.mkdir(parents=True, exist_ok=True); sheet.save(OUT / "contact_sheet.png")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
    contact_sheet(); print("contact sheet written")


from unittest_adopt import adopt
adopt(globals())
