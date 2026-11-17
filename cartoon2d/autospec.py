"""Find a cast picture's rig points automatically (spec.json for rig.py), so a new character needs no hand-marking.

python3 cartoon2d/autospec.py cartoon2d/cast/<name> [--paw]     (reads source.png, writes spec.json)

Works on the cast pictures' fixed pose (front view, arms hanging a little away from the body, white background):
  eyes   = the two white eye openings inside the figure, side by side in the top third
  mouth  = the widest dark stroke under the eyes, near the face centre
  neck   = just under the chin outline below the mouth
  arms   = the outermost runs of each row that stand apart from the torso (armpit down to the hand)
  wrist  = the narrowest row of the arm's lower part; elbow part way between shoulder and wrist
  sleeve end = where the arm's centre colour turns from the shoulder colour to the forearm colour
Check debug.png after rig.py; any point can still be fixed by hand in spec.json.
"""
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rig import cutout, runs  # noqa: E402


def comps(mask, min_n=30):
    """Connected components of a bool mask: list of (n, x0, y0, x1, y1, pixel list)."""
    h, w = mask.shape
    lab = np.zeros((h, w), bool)
    out = []
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0]:
            continue
        q, px = deque([(y0, x0)]), []
        lab[y0, x0] = True
        while q:
            y, x = q.popleft()
            px.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = True
                    q.append((yy, xx))
        if len(px) >= min_n:
            a = np.array(px)
            out.append((len(px), int(a[:, 1].min()), int(a[:, 0].min()), int(a[:, 1].max()), int(a[:, 0].max()), a))
    return out


def colour(rgb, x, y, r=3):
    a = rgb[max(0, int(y) - r):int(y) + r + 1, max(0, int(x) - r):int(x) + r + 1]
    return np.median(a.reshape(-1, 3), 0)


def pair(ec):
    """The best side-by-side pair of similar blobs: (score, a, b) or None."""
    best = None
    for i in range(len(ec)):
        for j in range(i + 1, len(ec)):
            a, b = ec[i], ec[j]
            ya, yb = (a[2] + a[4]) / 2, (b[2] + b[4]) / 2
            ha = max(a[4] - a[2], b[4] - b[2])
            if abs(ya - yb) > 0.5 * ha or abs(a[0] - b[0]) > 0.6 * max(a[0], b[0]):
                continue
            score = a[0] + b[0] - 3 * abs(a[0] - b[0])
            if best is None or score > best[0]:
                best = (score, a, b)
    return best


def find_eyes(cast_dir, lum, fg, W, hc, top):
    """[[cx, cy, rx, ry], [..]] left to right: white openings holding a pupil, else (fox) the dark round pupils."""
    y_lim = top + int(0.42 * hc)
    white = (lum > 228) & fg
    white[y_lim:] = False

    def dark_in(c):
        return (lum[c[2]:c[4] + 1, c[1]:c[3] + 1] < 90).mean()
    ec = [c for c in comps(white, 60) if (c[3] - c[1]) < 0.25 * W and (c[4] - c[2]) < 0.15 * hc and dark_in(c) > 0.08]
    best = pair(ec)
    if best is None:
        dark = (lum < 95) & fg
        dark[y_lim:] = False
        dc = []
        for c in comps(dark, 200):
            w_, h_ = c[3] - c[1] + 1, c[4] - c[2] + 1
            if 0.6 < w_ / h_ < 1.6 and c[0] > 0.5 * w_ * h_ and w_ < 0.2 * W:
                g = int(0.15 * w_)
                dc.append((c[0], c[1] - g, c[2] - g, c[3] + g, c[4] + g, c[5]))
        best = pair(dc)
    if best is None:
        raise SystemExit(f"{cast_dir.name}: no eye pair found")
    eyes = sorted([best[1], best[2]], key=lambda c: c[1])
    eye_list = [[(c[1] + c[3]) / 2, (c[2] + c[4]) / 2, (c[3] - c[1]) / 2 + 2, (c[4] - c[2]) / 2 + 2] for c in eyes]
    rx_, ry_ = max(e[2] for e in eye_list), max(e[3] for e in eye_list)          # both eyes the same size (blink covers)
    for e in eye_list:
        e[2], e[3] = rx_, ry_
    return eye_list


def make(cast_dir, paw=False):
    cast_dir = Path(cast_dir)
    src = Image.open(cast_dir / "source.png").convert("RGB")
    rgb = np.asarray(src).astype(np.int32)
    lum = rgb.mean(-1)
    fg = np.asarray(cutout(src))[..., 3] > 40
    H, W = fg.shape
    rows = np.nonzero(fg.any(1))[0]
    top, bot = int(rows.min()), int(rows.max())
    hc = bot - top

    # eyes: white openings inside the figure (not the background) in the top part, else dark round pupils
    eye_list = find_eyes(cast_dir, lum, fg, W, hc, top)
    fx = (eye_list[0][0] + eye_list[1][0]) / 2
    ey = (eye_list[0][1] + eye_list[1][1]) / 2
    d = eye_list[1][0] - eye_list[0][0]
    ery = max(e[3] for e in eye_list)

    # skin / face colour: between the eyes (nose bridge, or the top of an animal's head)
    skin_pt = [fx, ey]
    if lum[int(ey), int(fx)] < 110:
        skin_pt = [fx, ey - ery]

    # mouth: the widest stroke clearly darker than the face around it, in the band under the eyes (not the chin line)
    y0, y1 = int(ey + ery + 0.12 * d), int(ey + 0.85 * d)            # the chin line sits lower (Rosie: 0.92 d)
    band = np.zeros_like(fg)
    xa, xb = int(fx - 0.55 * d), int(fx + 0.55 * d)
    face_l = float(np.median(lum[y0:y1, xa:xb][fg[y0:y1, xa:xb]]))
    band[y0:y1, xa:xb] = (lum[y0:y1, xa:xb] < min(150, face_l - 55)) & fg[y0:y1, xa:xb]
    mc = [c for c in comps(band, 25) if abs((c[1] + c[3]) / 2 - fx) < 0.3 * d and (c[3] - c[1]) < 1.1 * d
          and (c[3] - c[1]) > 1.6 * (c[4] - c[2]) and (c[3] - c[1]) > 0.18 * d]
    mc.sort(key=lambda c: (c[3] - c[1]), reverse=True)
    if mc:
        m = mc[0]
        mh = min(max(1.4 * (m[4] - m[2]), 0.18 * d), 0.24 * d)          # a nose joined to the mouth line (fox) stays out
        mouth = {"c": [(m[1] + m[3]) / 2, m[4] - mh / 2 + 4 if (m[4] - m[2]) > 0.3 * d else (m[2] + m[4]) / 2],
                 "w": max(1.2 * (m[3] - m[1]), 0.6 * d), "h": mh}
    else:
        mouth = {"c": [fx, ey + 0.7 * d], "w": 0.65 * d, "h": 0.2 * d}
    my = mouth["c"][1]

    # neck: the chin outline under the mouth, then a little below it
    chin = None
    for y in range(int(my + mouth["h"] / 2 + 6), min(H - 1, int(my + 1.6 * d))):
        if lum[y, int(fx)] < 110 or not fg[y, int(fx)]:
            chin = y
            break
    neck_y = (chin + 12) if chin else int(my + 0.75 * (my - ey))
    neck_w = int(0.42 * d)

    # arms: rows with 3+ runs (arm, torso, arm) between the shoulders and mid-thigh
    arms_rows = {"sl": {}, "sr": {}}
    for y in range(neck_y + int(0.2 * d), top + int(0.72 * hc)):
        r = runs(fg[y])
        if len(r) >= 3:
            arms_rows["sl"][y] = r[0]
            arms_rows["sr"][y] = r[-1]
    face_c = colour(rgb, *skin_pt)
    arms = {}
    sh_tops = []
    for side, rr in arms_rows.items():
        if len(rr) < 20:
            raise SystemExit(f"{cast_dir.name}: arm {side} does not stand apart from the body")
        ys = sorted(rr)
        # the longest run of consecutive rows (ignore stray bits)
        segs, cur = [], [ys[0]]
        for y in ys[1:]:
            if y - cur[-1] <= 3:
                cur.append(y)
            else:
                segs.append(cur)
                cur = [y]
        segs.append(cur)
        seg = max(segs, key=len)
        ap, hb = seg[0], seg[-1]
        cx = {y: (rr[y][0] + rr[y][1]) / 2 for y in seg}
        wd = {y: rr[y][1] - rr[y][0] for y in seg}
        w_ap = np.median([wd[y] for y in seg[:12]])
        # shoulder: going up from the armpit, where the figure's outer edge turns in (arms fused to the body - fox,
        # dino - stand apart only low down, so the armpit row alone puts the shoulder at the elbow)
        outer = 0 if side == "sl" else 1
        L_ap = rr[ap][outer]
        y_t = ap
        for y in range(ap, neck_y, -1):
            r_ = runs(fg[y])
            if not r_:
                break
            L = r_[0][0] if side == "sl" else r_[-1][1]
            if abs(L - L_ap) > 0.6 * w_ap:
                break
            y_t = y
        S = [cx[ap], min(ap - 0.3 * w_ap, y_t + 0.55 * w_ap)]
        # better: follow the arm's own line up from the armpit through the sleeve to the top of the shoulder (Tobi's
        # short sleeve is joined to his body, so the gap - and the old shoulder - began at the sleeve hem)
        up_rows = [y for y in seg if y < ap + 0.4 * (hb - ap)]
        if len(up_rows) > 8:
            ka, kb = np.polyfit(up_rows, [cx[y] for y in up_rows], 1)
            y_min = int(neck_y + 0.25 * (ap - neck_y))
            y_top = ap
            for y in range(ap, y_min, -1):
                if not fg[y, int(round(ka * y + kb))]:
                    break
                y_top = y
            sy = min(S[1], y_top + 0.5 * w_ap)
            sx = ka * sy + kb
            S = [sx, sy]
        lower = [y for y in seg if y > ap + 0.55 * (hb - ap) and y < hb - 0.06 * (hb - ap)]
        wy = min(lower, key=lambda y: wd[y]) if lower else int(hb - 0.18 * (hb - ap))
        Wp = [cx[wy], wy]
        ey_ = int(S[1] + 0.55 * (Wp[1] - S[1]))
        ey_ = min(max(ey_, ap), hb)
        ny_ = min(cx, key=lambda y: abs(y - ey_))
        E = [cx[ny_], ey_]
        # colours along the centre line: shoulder colour vs forearm colour
        # shoulder colour at the shoulder itself (short sleeves end above the armpit: Tobi's red sleeve read as skin)
        sl_pt = [S[0], int(S[1])]
        up_c = colour(rgb, *sl_pt)
        fo_y = int(E[1] + 0.5 * (Wp[1] - E[1]))
        fo_c = colour(rgb, cx[min(cx, key=lambda y: abs(y - fo_y))], fo_y)
        se_y = None
        if np.abs(up_c - fo_c).sum() > 60:
            for y in range(int(S[1]), int(E[1])):
                x_ = cx[y] if y in cx else S[0] + (cx[ap] - S[0]) * (y - S[1]) / max(1, ap - S[1])
                c = colour(rgb, x_, y, 2)
                if np.abs(c - fo_c).sum() < np.abs(c - up_c).sum() and lum[y, int(x_)] > 60:
                    se_y = y
                    break
        if se_y is None:
            se_y = int(S[1] + 0.35 * (E[1] - S[1]))
        SE = [cx[se_y] if se_y in cx else S[0] + (cx[ap] - S[0]) * (se_y - S[1]) / max(1, ap - S[1]), se_y]
        hand_y = int(Wp[1] + 0.4 * (hb - Wp[1]))
        hand_c = colour(rgb, cx[min(cx, key=lambda y: abs(y - hand_y))], hand_y, 2)
        # poly: exact inner (cut) edge from the shoulder top down the arm's inner side, loose outside
        inner = 1 if side == "sl" else 0
        out_x = 0 if side == "sl" else W - 1
        xi = rr[ap][inner] + (3 if side == "sl" else -3)
        top_y = int(S[1] - 0.9 * w_ap)
        poly = [[xi, top_y], [out_x, top_y - int(0.3 * w_ap)], [out_x, min(H - 1, hb + 25)], [rr[hb][inner], min(H - 1, hb + 25)]]
        for y in reversed(seg[::12]):
            poly.append([rr[y][inner] + (2 if side == "sl" else -2), y])
        poly.append([xi, ap])
        sh_tops.append(top_y)
        arms[side] = {"poly": [[int(p[0]), int(p[1])] for p in poly], "shoulder": [int(S[0]), int(S[1])], "elbow": [int(E[0]), int(E[1])],
                      "wrist": [int(Wp[0]), int(Wp[1])], "sleeve_end": [int(SE[0]), int(SE[1])],
                      "sleeve": [int(sl_pt[0]), int(sl_pt[1])],
                      "elbow_skin": [int(cx[min(cx, key=lambda y: abs(y - fo_y))]), fo_y],
                      "hand_rgb": [int(v) for v in hand_c]}
    # head box: the figure above the shoulders; the cut drops beside the neck so loose hair goes with the head
    hy = min(sh_tops)
    hx = np.nonzero(fg[top:max(hy, neck_y)].any(0))[0]
    head_box = [int(hx.min()) - 4, max(0, top - 4), int(hx.max()) + 4, int(neck_y + 0.9 * d)]
    side_y = max(neck_y + 8, hy + int(0.25 * (neck_y - hy)) if hy > neck_y else neck_y + 8)
    head_cut = [[head_box[0], side_y], [int(fx - 1.5 * neck_w), side_y], [int(fx - neck_w), neck_y],
                [int(fx + neck_w), neck_y], [int(fx + 1.5 * neck_w), side_y], [head_box[2], side_y]]
    # outline colour: the darkest pixels on the figure's edge
    edge = fg & ~np.roll(fg, 2, 0) | fg & ~np.roll(fg, -2, 0) | fg & ~np.roll(fg, 2, 1) | fg & ~np.roll(fg, -2, 1)
    ev = rgb[edge]
    line_rgb = np.median(ev[ev.mean(1) < np.percentile(ev.mean(1), 30)], 0)
    feet_x = float(np.nonzero(fg[bot - 30:bot + 1].any(0))[0].mean())
    spec = {"neck": [int(fx), int(neck_y)], "head_box": head_box, "neck_w": neck_w, "head_cut": head_cut, "arms": arms,
            "mouth": {"c": [int(v) for v in mouth["c"]], "w": int(mouth["w"]), "h": int(mouth["h"])},
            "eyes": [[int(v) for v in e] for e in eye_list], "skin": [int(v) for v in skin_pt], "line": [0, 0],
            "line_rgb": [int(v) for v in line_rgb], "feet": [int(feet_x), bot - 2], "auto": True}
    if paw:
        spec["paw"] = True
    (cast_dir / "spec.json").write_text(json.dumps(spec, indent=1))
    print("SPEC", cast_dir.name, "eyes", spec["eyes"], "mouth", spec["mouth"]["c"], "neck", spec["neck"],
          {s: (a["shoulder"], a["elbow"], a["wrist"], a["sleeve_end"]) for s, a in arms.items()})


if __name__ == "__main__":
    make(sys.argv[1], "--paw" in sys.argv)
