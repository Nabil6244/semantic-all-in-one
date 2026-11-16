"""Toon Tales puppets: flat 2D stick-figure characters that stand inside a lit 3D Blender scene.

Parts per character (all under one empty "CH-<id>" at the feet):
  head   flat white disc + ink rim; face planes in front (extra_back, mouth, eyes, extra_front)
  body   soft toon-shaded bean with a front-projected outfit texture + ink outline (inverted hull)
  limbs  ink tubes (bevelled curves) shoulder->elbow->hand, hip->knee->foot; round ink hands/shoes
  hat    low-poly toon-shaded 3D piece + ink outline
Everything casts shadows, so the puppet stands in the set like the reference.

Library use (inside Blender):  import puppet; ch = puppet.build(cfg, faces_dir); puppet.set_pose(ch, "wave")
Stills spike:  blender -b --factory-startup --python toontales/cast/puppet.py -- <cast.json> <faces dir> <out dir>
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

INK = (38 / 255, 24 / 255, 28 / 255)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "library"))
import actions as A  # noqa: E402  (pure-python pose/action library shared with the planner)

# ---------------------------------------------------------------- materials


def _srgb(c):
    """0-255 sRGB -> linear 0-1 (Blender colours are linear)."""
    def f(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (f(c[0]), f(c[1]), f(c[2]), 1.0)


def _lin(c):
    def f(v):
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (f(c[0]), f(c[1]), f(c[2]), 1.0)


def mat_ink():
    m = bpy.data.materials.get("TT_ink")
    if m:
        return m
    m = bpy.data.materials.new("TT_ink")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = _lin(INK)
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    m.use_backface_culling = True
    return m


def mat_toon(name, color=None, image=None, shade=0.72, soft=0.12):
    """Two-tone toon: lit side = colour, shadow side = colour * shade (also inside cast shadows)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    L = nt.links
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    L.new(diff.outputs[0], s2r.inputs[0])
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    L.new(s2r.outputs[0], bw.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "EASE"
    a, b = ramp.color_ramp.elements
    a.position, a.color = 0.18, (shade, shade, shade, 1)
    b.position, b.color = 0.18 + soft, (1, 1, 1, 1)
    L.new(bw.outputs[0], ramp.inputs[0])
    if image is not None:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        L.new(tc.outputs["Generated"], sep.inputs[0])
        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        L.new(sep.outputs["X"], comb.inputs["X"])
        L.new(sep.outputs["Z"], comb.inputs["Y"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = "EXTEND"
        L.new(comb.outputs[0], tex.inputs[0])
        base = tex.outputs["Color"]
    else:
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = _srgb(color)
        base = rgb.outputs[0]
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    L.new(base, mul.inputs[6])
    L.new(ramp.outputs[0], mul.inputs[7])
    em = nt.nodes.new("ShaderNodeEmission")
    L.new(mul.outputs[2], em.inputs[0])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    L.new(em.outputs[0], out.inputs[0])
    return m


def mat_decal(name, image):
    """Flat unlit picture with alpha (face parts)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    L = nt.links
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = "IMG"
    tex.image = image
    tex.extension = "CLIP"
    em = nt.nodes.new("ShaderNodeEmission")
    L.new(tex.outputs["Color"], em.inputs[0])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    L.new(tex.outputs["Alpha"], mix.inputs[0])
    L.new(tr.outputs[0], mix.inputs[1])
    L.new(em.outputs[0], mix.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    L.new(mix.outputs[0], out.inputs[0])
    try:
        m.surface_render_method = "BLENDED"
    except Exception:
        m.blend_method = "BLEND"
    m.use_backface_culling = True
    return m


def _img(path):
    return bpy.data.images.load(str(path), check_existing=True)


# ---------------------------------------------------------------- geometry helpers


def _link(o, parent):
    bpy.context.scene.collection.objects.link(o) if o.name not in bpy.context.scene.collection.objects else None
    o.parent = parent
    return o


def _outline(o, thick=0.012):
    o.data.materials.append(mat_ink())
    sm = o.modifiers.new("outline", "SOLIDIFY")
    sm.thickness = thick
    sm.offset = 1.0
    sm.use_flip_normals = True
    sm.material_offset = len(o.data.materials) - 1
    sm.use_rim = False


def _ellipsoid(name, size, loc, mat, parent, outline=0.012, segs=48):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, radius=1.0, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    if outline:
        _outline(o, outline)
    o.parent = parent
    return o


def _cyl(name, r, depth, loc, mat, parent, rot=(0, 0, 0), outline=0.012, verts=64, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(mat)
    if outline:
        _outline(o, outline)
    o.parent = parent
    return o


def _plane(name, size, loc, mat, parent):
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc, rotation=(math.pi / 2, 0, 0))
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    o.parent = parent
    # rotated +90 deg about X the plane faces -Y (the camera side) and reads unmirrored
    o.visible_shadow = False
    return o


def _tube(name, n_pts, radius, parent):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new("NURBS")
    sp.points.add(n_pts - 1)
    sp.order_u = 3
    sp.use_endpoint_u = True
    sp.resolution_u = 12
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(mat_ink())
    o.parent = parent
    return o


def _set_tube(o, pts):
    sp = o.data.splines[0]
    for p, v in zip(sp.points, pts):
        p.co = (v[0], v[1], v[2], 1.0)


# ---------------------------------------------------------------- hats


def _hat(cfg, head_c, r, parent):
    h = cfg.get("hat") or {}
    t = h.get("type")
    col = h.get("color", [90, 80, 70])
    m = mat_toon(f"TT_hat_{cfg['id']}", col, shade=0.68)
    top = head_c.z + r
    parts = []
    if t == "flatcap":
        # puffy dome a touch wider than the head, pulled down at the front, short stiff bill
        cz = top - r * 0.30
        crown = _ellipsoid(f"{cfg['id']}_hat_crown", (r * 1.0, r * 0.34, r * 0.50), (head_c.x, head_c.y - r * 0.02, cz), m, parent)
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(crown.data)
        # mesh coords are in character space (object sits at the root origin)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < cz - 0.02 * r], context="VERTS")  # keep upper dome
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(head_c.x, head_c.y, cz),
                         matrix=Matrix.Rotation(math.radians(-10), 3, "X") @ Matrix.Rotation(math.radians(4), 3, "Y"))
        bm.to_mesh(crown.data)
        bm.free()
        bill = _cyl(f"{cfg['id']}_hat_bill", 1.0, r * 0.05, (head_c.x, head_c.y - r * 0.22, cz - r * 0.02), m, parent,
                    rot=(math.radians(-14), 0, 0), scale=(r * 0.70, r * 0.30, 1))
        parts += [crown, bill]
    elif t == "boater":
        band_c = h.get("band", [150, 40, 50])
        mb = mat_toon(f"TT_hatband_{cfg['id']}", band_c, shade=0.68)
        brim = _cyl(f"{cfg['id']}_hat_brim", 1.0, r * 0.05, (head_c.x, head_c.y, top - r * 0.20), m, parent,
                    scale=(r * 1.35, r * 0.55, 1), rot=(math.radians(-8), 0, 0))
        crown = _cyl(f"{cfg['id']}_hat_crown", 1.0, r * 0.50, (head_c.x, head_c.y, top + r * 0.06), m, parent,
                     scale=(r * 0.86, r * 0.40, 1), rot=(math.radians(-8), 0, 0))
        band = _cyl(f"{cfg['id']}_hat_band", 1.0, r * 0.16, (head_c.x, head_c.y, top - r * 0.08), mb, parent,
                    scale=(r * 0.875, r * 0.41, 1), rot=(math.radians(-8), 0, 0), outline=0)
        parts += [brim, crown, band]
    elif t in ("conductor", "shako"):
        band_c = h.get("band", [200, 160, 60])
        mb = mat_toon(f"TT_hatband_{cfg['id']}", band_c, shade=0.68)
        tilt = (math.radians(-6), 0, 0)
        tall = r * (0.42 if t == "conductor" else 0.95)
        wide = r * (0.80 if t == "conductor" else 0.74)
        crown = _cyl(f"{cfg['id']}_hat_crown", 1.0, tall, (head_c.x, head_c.y, top - r * 0.10 + tall / 2), m, parent,
                     scale=(wide, r * 0.40, 1), rot=tilt)
        band = _cyl(f"{cfg['id']}_hat_band", 1.0, r * 0.12, (head_c.x, head_c.y, top - r * 0.04), mb, parent,
                    scale=(wide + r * 0.015, r * 0.41, 1), rot=tilt, outline=0)
        bill = _cyl(f"{cfg['id']}_hat_bill", 1.0, r * 0.04, (head_c.x, head_c.y - r * 0.24, top - r * 0.12), mat_ink(), parent,
                    rot=(math.radians(-18), 0, 0), scale=(r * 0.62, r * 0.26, 1), outline=0)
        parts += [crown, band, bill]
        if t == "shako":  # badge plate + plume ball on top
            plate = _cyl(f"{cfg['id']}_hat_plate", 1.0, r * 0.02, (head_c.x, head_c.y - r * 0.42, top + tall * 0.42), mb, parent,
                         rot=(math.radians(90), 0, 0), scale=(r * 0.22, r * 0.26, 1), outline=0)
            plume = _ellipsoid(f"{cfg['id']}_hat_plume", (r * 0.16, r * 0.16, r * 0.26),
                               (head_c.x, head_c.y, top - r * 0.10 + tall + r * 0.22),
                               mat_toon(f"TT_plume_{cfg['id']}", h.get("plume", [245, 245, 245]), shade=0.7), parent)
            parts += [plate, plume]
    elif t in ("cowboy", "tophat", "bowler"):
        band_c = h.get("band", [60, 40, 30])
        mb = mat_toon(f"TT_hatband_{cfg['id']}", band_c, shade=0.68)
        tilt = (math.radians(-8), 0, 0)
        if t == "cowboy":  # wide brim, tall pinched crown
            brim = _cyl(f"{cfg['id']}_hat_brim", 1.0, r * 0.06, (head_c.x, head_c.y, top - r * 0.16), m, parent,
                        scale=(r * 1.75, r * 0.72, 1), rot=tilt)
            crown = _ellipsoid(f"{cfg['id']}_hat_crown", (r * 0.74, r * 0.40, r * 0.60), (head_c.x, head_c.y, top + r * 0.20), m, parent)
            band = _cyl(f"{cfg['id']}_hat_band", 1.0, r * 0.12, (head_c.x, head_c.y, top - r * 0.06), mb, parent,
                        scale=(r * 0.83, r * 0.44, 1), rot=tilt, outline=0)
        elif t == "tophat":  # tall straight crown, narrow brim
            brim = _cyl(f"{cfg['id']}_hat_brim", 1.0, r * 0.05, (head_c.x, head_c.y, top - r * 0.12), m, parent,
                        scale=(r * 1.15, r * 0.50, 1), rot=tilt)
            crown = _cyl(f"{cfg['id']}_hat_crown", 1.0, r * 1.05, (head_c.x, head_c.y, top + r * 0.42), m, parent,
                         scale=(r * 0.72, r * 0.36, 1), rot=tilt)
            band = _cyl(f"{cfg['id']}_hat_band", 1.0, r * 0.16, (head_c.x, head_c.y, top - r * 0.02), mb, parent,
                        scale=(r * 0.735, r * 0.37, 1), rot=tilt, outline=0)
        else:  # bowler: round dome, small curled brim
            brim = _cyl(f"{cfg['id']}_hat_brim", 1.0, r * 0.05, (head_c.x, head_c.y, top - r * 0.14), m, parent,
                        scale=(r * 1.08, r * 0.48, 1), rot=tilt)
            crown = _ellipsoid(f"{cfg['id']}_hat_crown", (r * 0.78, r * 0.40, r * 0.52), (head_c.x, head_c.y, top + r * 0.02), m, parent)
            band = _cyl(f"{cfg['id']}_hat_band", 1.0, r * 0.12, (head_c.x, head_c.y, top - r * 0.08), mb, parent,
                        scale=(r * 0.80, r * 0.41, 1), rot=tilt, outline=0)
        parts += [brim, crown, band]
    return parts


# ---------------------------------------------------------------- build + pose


def build(cfg, faces_dir, out_dir, at=(0, 0, 0)):
    faces_dir = Path(faces_dir) / cfg["id"]
    root = bpy.data.objects.new(f"CH-{cfg['id']}", None)
    bpy.context.scene.collection.objects.link(root)
    root.location = at
    b = cfg["body"]
    r = cfg["head_r"]
    legs = cfg["legs"]
    bw, bh, bd = b["w"], b["h"], b["d"]
    body_c = Vector((0, 0, legs + bh * 0.5 - 0.04))
    head_c = Vector((0, -0.02, legs + bh - 0.04 + r * 0.92))

    # body
    img = _img(faces_dir / "outfit.png")  # drawn by faces.py
    body = _ellipsoid(f"{cfg['id']}_body", (bw / 2, bd / 2, bh / 2), body_c, mat_toon(f"TT_body_{cfg['id']}", image=img), root)

    # head disc + face planes
    head_m = mat_toon(f"TT_head_{cfg['id']}", tuple(cfg.get("skin", (255, 255, 255))), shade=0.86, soft=0.25)
    head = _cyl(f"{cfg['id']}_head", r, r * 0.22, head_c, head_m, root, rot=(math.pi / 2, 0, 0), outline=0.014)
    front = head_c.y - r * 0.11
    face = {}
    for i, layer in enumerate(["extra_back", "mouth", "eyes", "extra_front"]):
        fn = {"mouth": "mouth_X.png", "eyes": "eyes_open.png"}.get(layer, f"{layer}.png")
        mt = mat_decal(f"TT_{cfg['id']}_{layer}", _img(faces_dir / fn))
        face[layer] = _plane(f"{cfg['id']}_face_{layer}", 2 * r, (head_c.x, front - 0.003 * (i + 1), head_c.z), mt, root)

    hat = _hat(cfg, head_c, r, root)

    # limbs
    limb_r = max(0.016, cfg["height"] * 0.011)
    tubes = {k: _tube(f"{cfg['id']}_{k}", 3, limb_r, root) for k in ("arm_L", "arm_R", "leg_L", "leg_R")}
    hands = {k: _ellipsoid(f"{cfg['id']}_hand_{k}", (limb_r * 2.1,) * 3, (0, 0, 0), mat_ink(), root, outline=0, segs=16)
             for k in ("L", "R")}
    shoes = {k: _ellipsoid(f"{cfg['id']}_shoe_{k}", (limb_r * 3.2, limb_r * 2.4, limb_r * 1.6), (0, 0, 0), mat_ink(), root, outline=0, segs=16)
             for k in ("L", "R")}

    # upper body pivots at the hips: squats, leans and bounces move body+head+hat together
    pivot = Vector((0, 0, legs + 0.06))
    upper = bpy.data.objects.new(f"{cfg['id']}_upper", None)
    bpy.context.scene.collection.objects.link(upper)
    upper.parent = root
    upper.location = pivot
    for o in [body, head, *face.values(), *hat]:
        o.parent = upper
        o.matrix_parent_inverse = Matrix.Translation(-pivot)

    ch = {"cfg": cfg, "root": root, "at": Vector(at), "upper": upper, "pivot": pivot,
          "body": body, "head": head, "face": face, "hat": hat,
          "tubes": tubes, "hands": hands, "shoes": shoes, "faces_dir": faces_dir,
          "shoulder": Vector((bw * 0.40, 0, legs + bh * 0.80 - 0.04)),
          "hip": Vector((bw * 0.20, 0, legs + 0.06)),
          "arm_len": bh * 0.62 + legs * 0.25, "leg_len": legs + 0.06,
          "body_c": body_c, "body_w": bw, "body_h": bh, "limb_r": limb_r}
    set_pose(ch, "idle")
    return ch


POSES = A.POSES  # static poses live in toontales/library/poses.json


def set_face(ch, eyes=None, mouth=None):
    for layer, state in (("eyes", eyes), ("mouth", mouth)):
        if state:
            node = ch["face"][layer].active_material.node_tree.nodes["IMG"]
            node.image = _img(ch["faces_dir"] / f"{layer}_{state}.png")


def metrics(ch):
    c = ch["cfg"]
    return {"arm_len": ch["arm_len"], "leg_len": ch["leg_len"], "shoulder_z": ch["shoulder"].z,
            "hip_z": ch["hip"].z, "head_r": c["head_r"], "body_w": c["body"]["w"]}


def _clear_body(ch, p, sx):
    """Push an elbow/hand out to the body's side outline so arms never sink behind a round body."""
    c, hw, hh = ch["body_c"], ch["body_w"] / 2, ch["body_h"] / 2
    dz = (p.z - c.z) / hh
    if abs(dz) >= 1:
        return p
    edge = hw * math.sqrt(1 - dz * dz) + ch["limb_r"] * 1.6
    if sx * p.x < edge:
        p = Vector((sx * edge, p.y, p.z))
    return p


def _knee(hip, foot, ll, sx):
    """Two-bone leg: knee bends forward and a little outward; a stretched leg drags the foot along."""
    a = ll / 2
    d = foot - hip
    L = d.length
    if L >= 2 * a * 0.999:
        foot = hip + d.normalized() * 2 * a * 0.999
        return (hip + foot) / 2, foot
    n = d.normalized()
    bend = Vector((sx * 0.55, -0.85, 0))
    bend -= n * bend.dot(n)
    bend.normalize()
    return (hip + foot) / 2 + bend * math.sqrt(max(0.0, a * a - (L / 2) ** 2)), foot


def apply_state(ch, st, bob=0.0, face=True):
    """Put a library state (see library/actions.py) on the puppet for this frame."""
    la, ll = ch["arm_len"], ch["leg_len"]
    sh, hp, P = ch["shoulder"], ch["hip"], ch["pivot"]
    up = Vector((st["up"][0], 0, st["up"][1]))
    R = Matrix.Rotation(math.radians(st["tilt"]), 3, "Y")
    ch["upper"].location = P + up
    ch["upper"].rotation_euler = (0, math.radians(st["tilt"]), 0)

    def xf(v):
        return P + up + R @ (v - P)

    hands = {}
    for i, side in enumerate(("L", "R")):
        sx = -1 if side == "L" else 1
        (ex, ez, ey), (hx, hz, hy) = st["arm"][i]
        s0 = Vector((sx * sh.x, sh.y, sh.z))
        e0 = s0 + Vector((sx * ex * la, -0.02 if ey is None else ey, ez * la))
        h0 = s0 + Vector((sx * hx * la, -0.04 if hy is None else hy, hz * la))
        front = hy is not None and hy < -0.06
        if not front:
            e0, h0 = _clear_body(ch, e0, sx), _clear_body(ch, h0, sx)
        s, e, h = xf(s0), xf(e0), xf(h0)
        _set_tube(ch["tubes"][f"arm_{side}"], [s, e, h])
        ch["hands"][side].location = h
        hands[side] = h
        fx, fz = st["foot"][i]
        hip0 = Vector((sx * hp.x, 0, hp.z))
        hip = xf(hip0)
        f = hip0 + Vector((sx * fx * ll, 0, fz * ll))
        f.z = max(f.z, 0.03)
        k, f = _knee(hip, f, ll, sx)
        _set_tube(ch["tubes"][f"leg_{side}"], [hip, k, f])
        ch["shoes"][side].location = f + Vector((sx * 0.03, -0.02, 0))
    ch["_hands"] = hands
    rt = st["root"]
    ch["root"].location = ch["at"] + Vector((rt[0], rt[1], rt[2]))
    ch["root"].rotation_euler = (0, math.radians(rt[3]), 0)
    set_bob(ch, dz=st["head"][1] + bob, dx=st["head"][0])
    if face:
        set_face(ch, st["eyes"], st["mouth"])


def hand_world(ch, side="R"):
    """World position of a hand (for props held or thrown)."""
    return ch["root"].matrix_world @ ch["_hands"][side]


def set_pose(ch, name, to=None, t=0.0, face=True):
    """Pose by name; with `to` and 0..1 `t` the limbs blend from `name` to `to`."""
    st = A.pose(name)
    if to is not None and t > 0:
        st = A.blend(st, A.pose(to), t)
    apply_state(ch, st, face=face)


def set_bob(ch, dz=0.0, dx=0.0):
    """Small head/hat offset for breathing, talking nods and reactions (body stays planted)."""
    parts = [ch["head"], *ch["face"].values(), *ch["hat"]]
    base = ch.setdefault("_head_base", {o.name: o.location.copy() for o in parts})
    for o in parts:
        o.location = base[o.name] + Vector((dx, 0, dz))


# ---------------------------------------------------------------- spike scene + stills


def _engine():
    sc = bpy.context.scene
    for e in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = e
            return
        except TypeError:
            continue


def spike_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    _engine()
    sc.view_settings.view_transform = "Standard"
    sc.render.film_transparent = False
    try:
        sc.eevee.taa_render_samples = 64
    except Exception:
        pass
    world = bpy.data.worlds.new("W")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = _srgb((120, 100, 86))
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    # warm floor + back wall (stand-in set)
    floor_m = bpy.data.materials.new("floor")
    floor_m.use_nodes = True
    floor_m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = _srgb((196, 160, 118))
    floor_m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 2, 0))
    bpy.context.active_object.data.materials.append(floor_m)
    wall_m = bpy.data.materials.new("wall")
    wall_m.use_nodes = True
    wall_m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = _srgb((150, 108, 76))
    wall_m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.95
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 2.2, 5), rotation=(math.pi / 2, 0, 0))
    bpy.context.active_object.data.materials.append(wall_m)
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 6), rotation=(math.radians(50), 0, math.radians(-35)))
    sun = bpy.context.active_object
    sun.data.energy = 3.2
    sun.data.angle = math.radians(3)
    sun.data.color = (1.0, 0.92, 0.8)
    bpy.ops.object.light_add(type="AREA", location=(-2.5, -3, 2.5))
    fill = bpy.context.active_object
    fill.data.energy = 120
    fill.data.size = 3
    fill.rotation_euler = (math.radians(60), 0, math.radians(-40))
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    sc.camera = cam
    return cam


def aim(cam, target, dist, yaw=0.0, pitch=4.0, lens=40):
    cam.data.lens = lens
    t = Vector(target)
    yr, pr = math.radians(yaw), math.radians(pitch)
    cam.location = t + Vector((math.sin(yr) * math.cos(pr) * dist, -math.cos(yr) * math.cos(pr) * dist, math.sin(pr) * dist))
    d = t - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def render(path, w, h):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main(argv):
    cast_path, faces, out = argv[:3]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cast = json.loads(Path(cast_path).read_text())
    cam = spike_scene()
    chars = []
    x = -0.55
    for cfg in cast["characters"]:
        chars.append(build(cfg, faces, out, at=(x, 0, 0)))
        x += 1.1
    # 1) cast together, slight 3/4 and low camera, shadows on floor and wall
    set_pose(chars[0], "hips")
    set_pose(chars[1], "wave")
    aim(cam, (0, 0, 0.95), 4.6, yaw=14, pitch=3, lens=38)
    render(out / "cast_full.png", 1080, 1350)
    # 2) every pose, each character
    for ch in chars:
        others = [c for c in chars if c is not ch]
        for o in others:
            o["root"].location.x += 50
        for pn in POSES:
            set_pose(ch, pn)
            aim(cam, (ch["root"].location.x, 0, ch["cfg"]["height"] * 0.52), 3.4 * ch["cfg"]["height"] / 1.8 + 0.6, yaw=10, pitch=3, lens=40)
            render(out / f"pose_{ch['cfg']['id']}_{pn}.png", 540, 860)
        for o in others:
            o["root"].location.x -= 50
    # 3) close-ups: talking mouths on Walt
    ch = chars[0]
    for o in chars[1:]:
        o["root"].location.x += 50
    set_pose(ch, "idle")
    c = ch["cfg"]
    hc = ch["root"].location + Vector((0, 0, c["legs"] + c["body"]["h"] - 0.04 + c["head_r"] * 0.92))
    print("close-up target", tuple(round(v, 2) for v in hc))
    for i, (e, m) in enumerate([("open", "D"), ("half", "smirk"), ("shock", "o_shock"), ("happy", "laugh")]):
        set_face(ch, e, m)
        aim(cam, (hc.x, 0, hc.z - 0.15), 1.6, yaw=8, pitch=2, lens=50)
        render(out / f"close_{i}.png", 540, 700)
    print("stills ->", out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(argv)
