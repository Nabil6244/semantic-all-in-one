"""Cut one full-body cartoon picture (white background) into a 2D cut-out rig.

python3 cartoon2d/rig.py cartoon2d/cast/<name>       (reads source.png + spec.json, writes parts/*.png + rig.json + debug.png)

spec.json (all points in source.png pixels):
  neck [x, y]            head pivot; the head part is everything above `neck_y` (plus a small overlap)
  head_box [x0,y0,x1,y1] where the head is (hair included) - limits the head cut
  arms: {"sl": {...}, "sr": {...}}   sl = screen-left (the character's right arm), sr = screen-right
      poly  [[x,y],...]  loose outline around the whole arm + hand; only its shoulder edge must be exact
      shoulder [x,y]     pivot of the upper arm
      elbow [x,y]        pivot of the forearm
      sleeve [x,y]       colour sample for the shoulder cap; elbow_skin [x,y] for the elbow cap
  mouth {"c": [x,y], "w": px, "h": px}   the drawn mouth (replaced while talking)
  eyes [[cx,cy,rx,ry], ...]               the eye openings (covered for blinks)
  skin [x,y]   cheek colour sample; line [x,y] outline colour sample
  feet [x,y]   ground point (centre between the shoes)
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))


def cutout(img, thresh=238):
    """White background -> alpha: flood from the border through near-white pixels, so white inside the character
    (eyes, socks, shoes) stays solid."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    h, w = a.shape[:2]
    white = (a.min(2) >= thresh) & (a.max(2) - a.min(2) < 18)
    bg = np.zeros((h, w), bool)
    seed = np.zeros((h, w), bool)
    seed[0, :] = seed[-1, :] = True
    seed[:, 0] = seed[:, -1] = True
    seed &= white
    bg |= seed
    # iterative flood fill on a numpy grid (fast enough for ~2k images: dilate within `white` until stable)
    while True:
        grown = bg.copy()
        grown[1:, :] |= bg[:-1, :]
        grown[:-1, :] |= bg[1:, :]
        grown[:, 1:] |= bg[:, :-1]
        grown[:, :-1] |= bg[:, 1:]
        grown &= white
        if (grown == bg).all():
            break
        bg = grown
    alpha = Image.fromarray(((~bg) * 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))   # trim the white halo, soft edge
    out = img.convert("RGBA")
    out.putalpha(alpha)
    return out


def _box(x, r):
    """Box sum over a (2r+1)^2 window (edges clamped), numpy only."""
    p = np.pad(x, ((r + 1, r), (r + 1, r)) + ((0, 0),) * (x.ndim - 2), mode="edge")
    c = p.cumsum(0).cumsum(1)
    return c[2 * r + 1:, 2 * r + 1:] - c[:-2 * r - 1, 2 * r + 1:] - c[2 * r + 1:, :-2 * r - 1] + c[:-2 * r - 1, :-2 * r - 1]


def bleed(rgba):
    """Copy edge colours into transparent pixels so scaling/rotating never pulls white or black into the outline."""
    a = np.asarray(rgba).copy()
    m = (a[..., 3] > 8).astype(np.float64)
    acc = a[..., :3].astype(np.float64) * m[..., None]
    wsum = m.copy()
    for _ in range(4):
        acc, wsum = _box(acc, 2), _box(wsum, 2)
    fill = acc / np.maximum(wsum[..., None], 1e-9)
    hole = a[..., 3] <= 8
    a[..., :3][hole] = np.clip(fill[hole], 0, 255).astype(np.uint8)
    return Image.fromarray(a)


def poly_mask(size, pts):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in pts], fill=255)
    return np.asarray(m) > 127


def side_of(p, a, b):
    """>0 on one side of line a->b for each pixel grid point p (h,w,2)."""
    return (b[0] - a[0]) * (p[..., 1] - a[1]) - (b[1] - a[1]) * (p[..., 0] - a[0])


def crop_part(rgba, mask, pad=4):
    ys, xs = np.nonzero(mask)
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(rgba.width, xs.max() + pad + 1), min(rgba.height, ys.max() + pad + 1)
    a = np.asarray(rgba).copy()
    a[..., 3] = (a[..., 3] * mask).astype(np.uint8)
    part = Image.fromarray(a[y0:y1, x0:x1])
    return part, (int(x0), int(y0))


def width_at(mask, p, d):
    """Width of the mask across direction d (unit) at point p: walk both ways along the normal."""
    n = (-d[1], d[0])
    h, w = mask.shape
    tot = 0
    for sgn in (1, -1):
        k = 0
        while k < 400:
            x, y = int(round(p[0] + sgn * n[0] * k)), int(round(p[1] + sgn * n[1] * k))
            if not (0 <= x < w and 0 <= y < h) or not mask[y, x]:
                break
            k += 1
        tot += k
    return tot


def mid_at(mask, p, d):
    """Centre of the mask's cross-section through p, across direction d."""
    n = (-d[1], d[0])
    h, w = mask.shape
    ext = []
    for sgn in (1, -1):
        k = 0
        while k < 400:
            x, y = int(round(p[0] + sgn * n[0] * (k + 1))), int(round(p[1] + sgn * n[1] * (k + 1)))
            if not (0 <= x < w and 0 <= y < h) or not mask[y, x]:
                break
            k += 1
        ext.append(sgn * k)
    m = (ext[0] + ext[1]) / 2
    return [float(p[0] + n[0] * m), float(p[1] + n[1] * m)]


def sample(img, p, r=3):
    a = np.asarray(img.convert("RGB"))[int(p[1]) - r:int(p[1]) + r + 1, int(p[0]) - r:int(p[0]) + r + 1]
    return tuple(int(v) for v in np.median(a.reshape(-1, 3), 0))


def runs(row):
    """[(x0, x1), ...] of the True runs in a 1-D bool row (runs under 12 px ignored)."""
    d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
    s, e = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return [(int(a), int(b)) for a, b in zip(s, e) if b - a >= 12]


def cut_legs(spec, rig, rgba, body, parts_dir, yy, xx):
    """Legs become two pieces each (thigh, lower leg + shoe), pivoting at hip and knee, drawn behind the body.
    The split (crotch, or a dress hem) is found from the picture: going up from the shoes, the first row where the two legs
    join. Each thigh gets a hidden stub above the cut (its top row repeated), so a swung leg never opens a gap at the hip."""
    ls = spec.get("legs", {})
    if ls is False:
        return body
    nx = rig["neck"][0]
    fy = int(rig["feet"][1])
    ankle_y = int(ls.get("ankle_y", fy - 0.1 * (fy - rig["neck"][1])))
    split = ls.get("split_y")
    if split is None:
        split = None
        for y in range(ankle_y, int(rig["neck"][1]), -1):
            r = [ab for ab in runs(body[y]) if ab[1] > nx - 260 and ab[0] < nx + 260]
            if len(r) == 1 and r[0][0] < nx < r[0][1]:
                split = y
                break
        if split is None:
            print("RIG", "no leg split found - legs stay in the body")
            return body
    split = int(split)
    knee_y = int(ls.get("knee_y", split + ls.get("knee_frac", 0.48) * (ankle_y - split)))
    below = yy > split
    a = np.asarray(rgba)
    ext = int(ls.get("stub", 0.16 * (ankle_y - split)))
    rig["legs"] = {}
    for side in ("sl", "sr"):
        leg = body & below & ((xx < nx) if side == "sl" else (xx >= nx))
        if leg.sum() < 500:
            continue

        def centre(y):
            r = runs(leg[y])
            return (sum((x0 + x1) / 2 for x0, x1 in r) / len(r)) if r else float(nx)
        H = [centre(split + 4), float(split - 0.06 * (ankle_y - split))]
        K = [centre(knee_y), float(knee_y)]
        Af = [centre(ankle_y), float(ankle_y)]
        ov = 10
        up = leg & (yy < knee_y + ov)
        lo = leg & (yy >= knee_y - ov)
        # thigh: picture pixels + a stub of its top row repeated upward (hidden behind the body at rest)
        pu, off_u = crop_part(Image.fromarray(a), up, pad=0)
        pa = np.asarray(pu).copy()
        top = pa[min(3, pa.shape[0] - 1)].copy()
        stub = np.repeat(top[None], ext, 0)
        pa = np.concatenate([stub, pa], 0)
        n = pa.shape[0]
        fade = np.clip((n - 1 - np.arange(n)) / 8.0, 0, 1)                        # soft bottom edge over the knee
        pa[..., 3] = (pa[..., 3] * fade[:, None]).astype(np.uint8)
        im_u = bleed(Image.fromarray(pa))
        off_u = (off_u[0], off_u[1] - ext)
        pl, off_l = crop_part(Image.fromarray(a), lo, pad=0)
        la = np.asarray(pl).copy()                                                 # shin stub: hides the knee gap when bent
        ext_k = int(0.22 * (ankle_y - knee_y))
        la = np.concatenate([np.repeat(la[min(ov + 2, la.shape[0] - 1)][None], ext_k, 0), la], 0)
        im_l = bleed(Image.fromarray(la))
        off_l = (off_l[0], off_l[1] - ext_k)
        im_u.save(parts_dir / f"thigh_{side}.png")
        im_l.save(parts_dir / f"shin_{side}.png")
        rig["parts"][f"thigh_{side}"] = {"file": f"parts/thigh_{side}.png", "offset": [int(off_u[0]), int(off_u[1])], "pivot": H}
        rig["parts"][f"shin_{side}"] = {"file": f"parts/shin_{side}.png", "offset": [int(off_l[0]), int(off_l[1])], "pivot": K}
        rig["legs"][side] = {"H": H, "K": K, "A": Af, "Lu": K[1] - H[1], "Ll": Af[1] - K[1]}
    rig["leg_split"] = split
    # crotch fill: the split row repeated a little way down as a narrowing wedge, drawn behind the legs and shown only while
    # the legs spread (squat, kick), so the floor never shows between the thighs
    r = runs(body[split])
    r = [ab for ab in r if ab[0] < nx < ab[1]]
    if r:
        x0, x1 = r[0]
        dep = int(0.2 * (ankle_y - split))
        w = x1 - x0
        wedge = np.zeros((dep, w, 4), np.uint8)
        wedge[:] = a[split, x0:x1][None]
        rows = np.arange(dep)[:, None]
        cols = np.arange(w)[None, :]
        half = (w / 2) * (1 - rows / dep) * 0.75
        wedge[..., 3] = np.where(np.abs(cols - w / 2) <= half, wedge[..., 3], 0)
        bleed(Image.fromarray(wedge)).save(parts_dir / "crotch.png")
        rig["parts"]["crotch"] = {"file": "parts/crotch.png", "offset": [int(x0), int(split - 2)], "pivot": [nx, split]}
    return body & ~(below & (yy > split + 6))


def fade_bottom(part, off, split, n=6):
    """The body's lowest rows (overlapping the thighs) fade out, so there is no line where body meets legs."""
    if split is None:
        return part
    a = np.asarray(part).copy()
    rows = np.arange(a.shape[0]) + off[1]
    f = np.clip((split + n - rows) / n, 0, 1)
    a[..., 3] = (a[..., 3] * f[:, None]).astype(np.uint8)
    return Image.fromarray(a)


def build(cast_dir):
    cast_dir = Path(cast_dir)
    spec = json.loads((cast_dir / "spec.json").read_text())
    src = Image.open(cast_dir / "source.png").convert("RGB")
    rgba = cutout(src)
    W, H = rgba.size
    alpha = np.asarray(rgba)[..., 3] > 40
    yy, xx = np.mgrid[0:H, 0:W]
    grid = np.stack([xx, yy], -1).astype(np.float32)
    parts_dir = cast_dir / "parts"
    parts_dir.mkdir(exist_ok=True)
    rig = {"size": [W, H], "feet": spec["feet"], "neck": spec["neck"], "parts": {}, "mouth": spec["mouth"], "eyes": spec["eyes"],
           "skin": sample(src, spec["skin"]), "line": spec.get("line_rgb") or sample(src, spec["line"], 1),
           "lid": sample(src, spec.get("lid", spec["skin"]))}
    body = alpha.copy()
    for side, arm in spec["arms"].items():
        am = poly_mask((W, H), arm["poly"]) & alpha
        body &= ~am
        sh = arm["shoulder"]
        d = np.array(arm["elbow"], float) - np.array(sh, float)
        d /= np.linalg.norm(d)
        el = mid_at(am, arm["elbow"], d)                                # joints on the arm's centre line
        d2 = np.array(arm["wrist"], float) - np.array(el, float)
        d2 /= np.linalg.norm(d2)
        wr = mid_at(am, arm["wrist"], d2)
        se = arm["sleeve_end"]
        # the arm is drawn as smooth tubes (sleeve + skin) at render time; only the hand is cut from the picture
        along = (grid[..., 0] - wr[0]) * d2[0] + (grid[..., 1] - wr[1]) * d2[1]
        hand = am & (along > -4)
        p_, off = crop_part(rgba, hand)
        bleed(p_).save(parts_dir / f"hand_{side}.png")
        rig["parts"][f"hand_{side}"] = {"file": f"parts/hand_{side}.png", "offset": off, "pivot": wr}
        mid_up = [(se[0] + el[0]) / 2, (se[1] + el[1]) / 2]
        mid_fo = [el[0] + (wr[0] - el[0]) * 0.75, el[1] + (wr[1] - el[1]) * 0.75]
        mid_sl = [(sh[0] + se[0]) / 2, (sh[1] + se[1]) / 2]
        rig.setdefault("arms", {})[side] = {
            "S": [float(v) for v in sh], "E": el, "W": wr, "SE": [float(v) for v in se],
            "uw": width_at(am, mid_up, d), "fw": width_at(am, mid_fo, d2), "sw": width_at(am, mid_sl, d),
            "skin": sample(src, arm.get("elbow_skin", el)), "sleeve": sample(src, arm["sleeve"])}
    # head: above the neck line inside the head box, with a 14 px feathered overlap below it
    nx, ny = spec["neck"]
    hb = spec["head_box"]
    cut = spec.get("head_cut") or [[0, ny], [W, ny]]                 # polyline: the head is everything above it
    cx_, cy_ = zip(*sorted(cut))
    cut_y = np.interp(np.arange(W), cx_, cy_)[None, :]
    nw = spec.get("neck_w", 60)
    near_neck = np.abs(xx - nx) < nw
    above = yy < cut_y
    head_m = body & (above | (near_neck & (yy < cut_y + 14))) & (xx >= hb[0]) & (xx <= hb[2]) & (yy >= hb[1])
    body_wo_head = body & ~(head_m & above)
    hp, hoff = crop_part(rgba, head_m)
    ha = np.asarray(hp).copy()
    rows = np.arange(ha.shape[0])[:, None] + hoff[1]
    cols = np.arange(ha.shape[1])[None, :] + hoff[0]
    cy_part = np.interp(cols, cx_, cy_)
    fade = np.where(np.abs(cols - nx) < nw, np.clip((cy_part + 14 - rows) / 14.0, 0, 1), 1.0)   # soft edge over the neck stub only
    ha[..., 3] = (ha[..., 3] * fade).astype(np.uint8)
    bleed(Image.fromarray(ha)).save(parts_dir / "head.png")
    rig["parts"]["head"] = {"file": "parts/head.png", "offset": hoff, "pivot": [nx, ny]}
    # the body keeps a 4 px lip past each shoulder cut, so the body edge and the drawn sleeve overlap (no seam)
    lip = np.zeros_like(body_wo_head)
    for side, arm in spec["arms"].items():
        near = np.hypot(grid[..., 0] - arm["shoulder"][0], grid[..., 1] - arm["shoulder"][1]) < 120
        grown = np.asarray(Image.fromarray(body_wo_head.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(17))) > 127
        lip |= grown & alpha & near & ~body_wo_head
    body_wo_head = body_wo_head | lip
    # old sleeve outline bits inside the lip would show as dark ticks: paint them shirt colour
    arr = np.asarray(rgba).copy()
    lum = arr[..., :3].astype(np.int32).sum(-1) / 3
    for side, arm in spec["arms"].items():
        near = np.hypot(grid[..., 0] - arm["shoulder"][0], grid[..., 1] - arm["shoulder"][1]) < 120
        arr[lip & near & (lum < 120)] = sample(src, arm["sleeve"]) + (255,)
    # where the arms were cut away the body has a bare straight edge: give it the picture's outline, so a raised arm
    # shows a drawn side instead of a sliced one (faded out at the shoulder, where the sleeve tube covers it)
    def grow(m, r):
        return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * r + 1))) > 127
    removed = alpha & ~body_wo_head & ~(head_m & above)
    # clean the cut first: the loose arm outline leaves slivers, tufts of sleeve and bits of old outline along the chest
    # side, which show as a torn edge when the arm lifts. Smooth the silhouette there (blur + threshold, then open to drop
    # thin bits) and repaint dark leftovers near the cut with the shirt colour around them.
    # torso hull: below the shoulders, nothing of the body may lie outside the inner edge of either arm (hair tips and
    # sleeve bits there were cut loose from the arm and show as shards when it lifts)
    for side, arm in spec["arms"].items():
        am = poly_mask((W, H), arm["poly"])
        has = am.any(1)
        ys_ = np.nonzero(has)[0]
        y_from = int(arm["shoulder"][1] + 0.35 * rig["arms"][side]["sw"])
        for y in ys_[ys_ >= y_from]:
            xs_ = np.nonzero(am[y])[0]
            if side == "sl":
                body_wo_head[y, :xs_.max()] = False
            else:
                body_wo_head[y, xs_.min() + 1:] = False
    removed = alpha & ~body_wo_head & ~(head_m & above)
    hair_pt = spec.get("clean_hair")                   # long hair lying on the chest sides: becomes shirt (head keeps its hair)
    if hair_pt:
        hc = np.array(sample(src, hair_pt), float)
        dist = np.abs(arr[..., :3].astype(float) - hc).sum(-1)
        y_cut = min(a_["shoulder"][1] for a_ in spec["arms"].values()) - 20
        hairy = body_wo_head & (dist < 70) & (yy > y_cut) & ~above
        tmp = arr.copy()
        tmp[..., 3] = np.where(body_wo_head & ~hairy, 255, 0).astype(np.uint8)
        filled = np.asarray(bleed(Image.fromarray(tmp)))
        arr[hairy, :3] = filled[hairy, :3]
    zone = grow(removed, 26) & ~above
    soft = np.asarray(Image.fromarray(body_wo_head.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(5))) > 140
    opened = np.asarray(Image.fromarray(soft.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(13)).filter(ImageFilter.MaxFilter(13))) > 127
    new_body = np.where(zone, opened & alpha, body_wo_head)
    lum2 = arr[..., :3].astype(np.int32).sum(-1) / 3
    holes = new_body & zone & (grow(removed, 12) & (lum2 < 115) | ~body_wo_head)
    tmp = arr.copy()
    tmp[..., 3] = np.where(new_body & ~holes, 255, 0).astype(np.uint8)
    filled = np.asarray(bleed(Image.fromarray(tmp)))
    arr[holes, :3] = filled[holes, :3]
    arr[new_body, 3] = 255
    body_wo_head = new_body
    removed = alpha & ~body_wo_head & ~(head_m & above)
    edge = body_wo_head & grow(removed, 2) & ~above
    for side, arm in spec["arms"].items():
        r_sh = 0.55 * rig["arms"][side]["sw"]
        edge &= np.hypot(grid[..., 0] - arm["shoulder"][0], grid[..., 1] - arm["shoulder"][1]) > r_sh
    arr[edge] = tuple(int(v) for v in rig["line"]) + (255,)
    # neck back-fill: a band of body colour under the head, so a tilted head never opens a gap (torn neck) to the room
    band = int(spec.get("neck_fill", 44))
    nk = sample(src, (nx, min(H - 4, ny + 10)))
    if sum(nk) / 3 < 120:
        nk = rig["skin"]
    ref_y = np.clip((cut_y[0] + 6).astype(int), 0, H - 1)
    ref = arr[ref_y, np.arange(W)][:, :3].astype(np.int32)                         # the body colour just below the cut, per column
    ok = body_wo_head[ref_y, np.arange(W)] & (ref.sum(-1) / 3 >= 120)
    # where the body under the cut is solid and light (neck, fur, collar - not hair or outline), or right at the neck
    cols_ok = ok[None, :] | (np.abs(xx - nx) < nw * 1.15)
    fill_m = head_m & above & (yy >= cut_y - band) & ~body_wo_head & cols_ok
    col = np.where(ok[:, None], ref, np.array(nk, np.int32)[None, :]).astype(np.uint8)
    ys, xs = np.nonzero(fill_m)
    arr[ys, xs, :3] = col[xs]
    arr[ys, xs, 3] = 255
    body_wo_head = body_wo_head | fill_m
    rgba = Image.fromarray(arr)
    body_wo_head = cut_legs(spec, rig, rgba, body_wo_head, parts_dir, yy, xx)
    bp, boff = crop_part(rgba, body_wo_head)
    bp = fade_bottom(bp, boff, rig.get("leg_split"))
    bleed(bp).save(parts_dir / "body.png")
    rig["parts"]["body"] = {"file": "parts/body.png", "offset": boff, "pivot": spec["feet"]}
    import hands                                                         # hand shapes, when their pictures exist
    hands.add(cast_dir, rig, spec, cutout, bleed)
    (cast_dir / "rig.json").write_text(json.dumps(rig, indent=1))
    # debug sheet: the cut lines and points on the picture
    dbg = src.copy()
    dd = ImageDraw.Draw(dbg)
    for side, arm in spec["arms"].items():
        dd.line([tuple(p) for p in arm["poly"]] + [tuple(arm["poly"][0])], fill=(255, 0, 255), width=3)
        for k in ("shoulder", "elbow", "wrist", "sleeve_end"):
            x, y = arm[k]
            dd.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(0, 160, 255), width=3)
    dd.line([tuple(p) for p in sorted(cut)], fill=(0, 200, 0), width=3)
    mc = spec["mouth"]
    dd.rectangle([mc["c"][0] - mc["w"] / 2, mc["c"][1] - mc["h"] / 2, mc["c"][0] + mc["w"] / 2, mc["c"][1] + mc["h"] / 2], outline=(255, 0, 0), width=2)
    for cx, cy, rx, ry in spec["eyes"]:
        dd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=(255, 120, 0), width=2)
    dbg.save(cast_dir / "debug.png")
    print("RIG", cast_dir.name, {k: v["offset"] for k, v in rig["parts"].items()})


if __name__ == "__main__":
    build(sys.argv[1])
