"""Realistic close-up objects for Channel 5 ('Trial & Eureka' look), built inside Blender for the diorama engine.

Glass, liquids, metals and glossy paint; spun (lathe) shapes for bottles, cups, caps and coins; a procedural
glazed subway-tile wall. Units are metres: a soda bottle is ~0.24 m tall, so close-ups use short camera distances.

Pieces ("m"), all with "at": [x, y, z] (z = bottom), optional "s" scale and "id":
  "@bottle"  {"style": "crown"|"torpedo"|"codd"|"cork", "glass": "clear"|"green"|"amber", "fill": 0..1,
              "liquid": "cola"|"amber"|"water"|"lemonade", "tilt": deg (about x; a torpedo bottle lies at 90)}
  "@lathe"   {"profile": [[r, z], ...], "mat": key, "solid": true|false (shell)}   any spun shape
  "@cap"     {"mat": "steel"|"gold"|"red_paint", "crimps": 21}                     crown cork
  "@cork"    {"r": .0095, "h": .03}
  "@coin"    {"r": .012, "h": .0022, "mat": "brass"|"steel"|"silver"|"copper", "hole": r (a washer),
              "reeds": n (ridged edge), "hammered": true (uneven hand-struck), "clip": [deg, depth] (a snipped sliver)}
  "@shears" {"open": deg}  "@shavings" {"n", "r"}  "@magnifier"
  "@scale_stand" + "@scale_beam" (beam origin at the pivot, z +0.16 over the stand; tilt with a move "tilt_to")
  "@magnet"  {"w": .05}                                                             red horseshoe, steel poles
  "@ball"    {"r": .012, "color": rgb}                                              glossy gumball
  "@wall"    {"size": [w, h], "tiles": rgb (subway tiles) | "color": rgb (flat backdrop), "tile": .075}
Named finishes for any piece's "mat": glass, brass, steel, chrome, gold, copper, silver, rubber, cork,
red_paint, black_paint, white_ceramic (plus every texture set in assets/diorama/textures).
"""
import math

import bmesh
import bpy
from mathutils import Matrix

FINISH = {  # base colour, roughness, metallic
    "brass": ([0.78, 0.58, 0.24], 0.22, 1.0), "gold": ([0.95, 0.72, 0.3], 0.18, 1.0),
    "steel": ([0.62, 0.63, 0.66], 0.28, 1.0), "chrome": ([0.86, 0.87, 0.9], 0.06, 1.0),
    "copper": ([0.85, 0.45, 0.3], 0.25, 1.0), "silver": ([0.9, 0.9, 0.92], 0.15, 1.0),
    "rubber": ([0.05, 0.05, 0.05], 0.8, 0.0), "red_paint": ([0.75, 0.04, 0.04], 0.18, 0.0),
    "black_paint": ([0.02, 0.02, 0.02], 0.25, 0.0), "white_ceramic": ([0.92, 0.92, 0.9], 0.12, 0.0),
}
GLASS = {"clear": [0.93, 0.97, 0.95], "green": [0.12, 0.45, 0.2], "amber": [0.55, 0.25, 0.04]}
LIQUID = {"cola": [0.05, 0.012, 0.004], "amber": [0.62, 0.28, 0.03], "water": [0.7, 0.85, 0.95],
          "lemonade": [0.78, 0.68, 0.12]}
_M = {}


# ---------------------------------------------------------------- materials
def _principled(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _refractive(m):
    for attr, val in (("use_raytrace_refraction", True), ("use_screen_refraction", True),
                      ("surface_render_method", "DITHERED"), ("thickness_mode", "SLAB")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass


def _set(b, key, val):
    for k in ([key] if isinstance(key, str) else key):
        if k in b.inputs:
            b.inputs[k].default_value = val
            return


def _blended(m, alpha_socket_owner, alpha):
    alpha_socket_owner.inputs["Alpha"].default_value = alpha
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND"), ("use_backface_culling", False),
                      ("show_transparent_back", True)):
        try:
            setattr(m, attr, val)
        except Exception:
            pass


def glass(tint="clear"):
    """Real-time glass: alpha-blended with a clear coat, so a liquid or a marble inside still shows through
    (Eevee cannot refract through two refracting layers: a refractive bottle hid its own drink)."""
    lst = isinstance(tint, (list, tuple))
    key = "obj_glass_" + ("_".join(str(round(c, 2)) for c in tint) if lst else str(tint))
    if key in _M:
        return _M[key]
    m, b = _principled(key)
    col = list(tint) if lst else GLASS.get(tint, GLASS["clear"])
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = 0.03
    b.inputs["IOR"].default_value = 1.5
    _set(b, ("Coat Weight",), 1.0)
    _set(b, ("Specular IOR Level", "Specular"), 0.9)
    _blended(m, b, 0.16 if (not lst and tint == "clear") else 0.42)
    _M[key] = m
    return m


def liquid(kind="cola"):
    key = f"obj_liquid_{kind}"
    if key in _M:
        return _M[key]
    m, b = _principled(key)
    b.inputs["Base Color"].default_value = (*LIQUID.get(kind, LIQUID["amber"]), 1)
    b.inputs["Roughness"].default_value = 0.08
    _set(b, ("Subsurface Weight",), 0.0)
    _blended(m, b, {"cola": 0.93, "water": 0.25}.get(kind, 0.55))
    _M[key] = m
    return m


def cork_mat():
    if "obj_cork" in _M:
        return _M["obj_cork"]
    m, b = _principled("obj_cork")
    nt = m.node_tree
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 420.0
    n.inputs["Detail"].default_value = 6.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.45, 0.28, 0.14, 1)
    ramp.color_ramp.elements[1].color = (0.8, 0.6, 0.38, 1)
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = 0.85
    _M["obj_cork"] = m
    return m


def finish(key, color=None):
    """A named finish, or a flat colour."""
    if key == "glass":
        return glass()
    if key == "cork":
        return cork_mat()
    name = f"obj_{key}" + (f"_{'_'.join(str(round(c, 2)) for c in color)}" if color else "")
    if name in _M:
        return _M[name]
    base, rough, metal = FINISH.get(key, (color or [0.5, 0.5, 0.5], 0.65 if key == "matte" else 0.16, 0.0))
    m, b = _principled(name)
    b.inputs["Base Color"].default_value = (*(color or base), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if metal == 0.0 and rough < 0.3:
        _set(b, ("Coat Weight",), 0.6)  # lacquer / glaze
    _M[name] = m
    return m


def subway(color, tile=0.075, grout=(0.82, 0.78, 0.68)):
    """Glazed subway tiles (2:1, running bond) from the brick texture, mapped on the wall's x/z."""
    key = f"obj_subway_{'_'.join(str(round(c, 2)) for c in color)}_{tile}"
    if key in _M:
        return _M[key]
    m, b = _principled(key)
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs["X"], comb.inputs["X"])
    nt.links.new(sep.outputs["Z"], comb.inputs["Y"])
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.5
    br.inputs["Scale"].default_value = 1.0 / (tile * 2)
    br.inputs["Brick Width"].default_value = 1.0
    br.inputs["Row Height"].default_value = 0.5
    br.inputs["Mortar Size"].default_value = 0.012
    c1 = [min(1.0, c * 1.08) for c in color]
    br.inputs["Color1"].default_value = (*color, 1)
    br.inputs["Color2"].default_value = (*c1, 1)
    br.inputs["Mortar"].default_value = (*grout, 1)
    nt.links.new(comb.outputs[0], br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], b.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.004
    bump.invert = True
    nt.links.new(br.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = 0.12
    _set(b, ("Coat Weight",), 0.5)
    _M[key] = m
    return m


# ---------------------------------------------------------------- meshes
def _obj(name, me, mat):
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(mat)
    for poly in o.data.polygons:
        poly.use_smooth = True
    return o


def lathe(profile, mat, name="lathe", steps=72, solid=True, wobble=None):
    """Spin a profile [[r, z], ...] (bottom to top) around z. solid: closes the ends at r = 0 if the profile does."""
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0.0, z)) for r, z in profile]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    bmesh.ops.spin(bm, geom=verts + edges, angle=2 * math.pi, steps=steps, axis=(0, 0, 1), cent=(0, 0, 0))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    if wobble:
        wobble(bm)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _obj(name, me, mat)


PROFILES = {  # outer glass, metres, bottom (z 0) to lip
    "crown": [[0, 0], [0.026, 0.0], [0.031, 0.006], [0.032, 0.02], [0.032, 0.135], [0.029, 0.16], [0.02, 0.185],
              [0.0135, 0.205], [0.0128, 0.228], [0.0148, 0.231], [0.0148, 0.238], [0.0118, 0.24]],
    "torpedo": [[0, 0], [0.012, 0.004], [0.022, 0.018], [0.029, 0.045], [0.031, 0.08], [0.031, 0.17],
                [0.027, 0.195], [0.017, 0.215], [0.012, 0.23], [0.0118, 0.25], [0.0142, 0.254], [0.0142, 0.262],
                [0.011, 0.264]],
    "codd": [[0, 0], [0.027, 0.0], [0.032, 0.008], [0.032, 0.12], [0.027, 0.14], [0.019, 0.15], [0.024, 0.165],
             [0.019, 0.18], [0.0145, 0.2], [0.0145, 0.225], [0.016, 0.228], [0.0125, 0.232]],
    "cork": [[0, 0], [0.03, 0.0], [0.035, 0.008], [0.036, 0.16], [0.03, 0.2], [0.015, 0.24], [0.0115, 0.275],
             [0.013, 0.278], [0.013, 0.29], [0.0105, 0.292]],
}


def _shell(o, t=0.0018):
    mod = o.modifiers.new("wall", "SOLIDIFY")
    mod.thickness = t
    mod.offset = -1
    return o


def bottle(p):
    style = p.get("style", "crown")
    prof = PROFILES[style]
    root = bpy.data.objects.new(f"bottle_{style}", None)
    bpy.context.scene.collection.objects.link(root)
    g = _shell(lathe(prof, glass(p.get("glass", "clear")), "glass"))
    g.parent = root
    fill = p.get("fill", 0.8)
    if fill > 0:
        top = max(z for _, z in prof)
        lvl = top * fill
        inner = [[max(0.0, r - 0.0022), max(0.0015, z)] for r, z in prof if z <= lvl]
        rr = next((r for r, z in reversed(prof) if z <= lvl), 0.02) - 0.0022
        inner += [[rr, lvl], [0.0, lvl]]
        inner[0] = [0.0, 0.0015]
        liq = lathe(inner, liquid(p.get("liquid", "cola")), "liquid")
        liq.parent = root
    if style == "codd":  # the marble trapped in the pinched neck
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0085, segments=32, ring_count=16, location=(0, 0, 0.158))
        mb = bpy.context.active_object
        mb.data.materials.append(glass([0.6, 0.9, 0.8]))
        bpy.ops.object.shade_smooth()
        mb.parent = root
    if p.get("tilt"):
        root.rotation_euler.x = math.radians(p["tilt"])
    return root


def cap(p):
    """Crown cork: a shallow cup whose skirt is crimped into 'crimps' flutes."""
    n = p.get("crimps", 21)
    prof = [[0, 0.0065], [0.0148, 0.0065], [0.0158, 0.006], [0.0162, 0.004], [0.0172, 0.0]]

    def crimp(bm):
        for v in bm.verts:
            if v.co.z < 0.0055:
                a = math.atan2(v.co.y, v.co.x)
                k = 1 + 0.07 * max(0.0, math.cos(n * a)) * (1 - v.co.z / 0.0055)
                v.co.x *= k
                v.co.y *= k
    o = lathe(prof, finish(p.get("mat", "steel")), "cap", steps=n * 8, wobble=crimp)
    return _shell(o, 0.0004)


def cork(p):
    r, h = p.get("r", 0.0095), p.get("h", 0.03)
    return lathe([[0, 0], [r * 0.9, 0], [r, h], [0, h]], cork_mat(), "cork", steps=48)


def coin(p):
    """A coin, bottom at z 0. "reeds": n ridges round the edge (milled coin); "hammered": uneven hand-struck rim;
    "clip": [deg, depth] a sliver snipped off at that angle; "hole": r (a washer); faces get a raised rim + relief."""
    r, h = p.get("r", 0.012), p.get("h", 0.0022)
    hole = p.get("hole", 0.0)
    rim = [[hole, 0], [r - 0.0004, 0], [r, 0.0004], [r, h - 0.0004], [r - 0.0004, h], [r * 0.88, h],
           [r * 0.86, h * 0.8], [hole + 0.0006 if hole else 0.0, h * 0.8]]
    if hole:
        rim += [[hole, h * 0.8], [hole, 0]]
    reeds, ham, clip = p.get("reeds", 0), p.get("hammered", False), p.get("clip")
    seed = (hash(str(p.get("at"))) % 997) / 997.0

    def shape(bm):
        for v in bm.verts:
            rv = math.hypot(v.co.x, v.co.y)
            if rv < r * 0.9:
                continue
            a = math.atan2(v.co.y, v.co.x)
            k = 1.0
            if reeds:
                k *= 1 + 0.018 * math.cos(reeds * a)
            if ham:
                k *= 1 + 0.035 * math.sin(3 * a + seed * 6) + 0.02 * math.sin(7 * a + seed * 11)
            if clip:
                d = math.atan2(math.sin(a - math.radians(clip[0])), math.cos(a - math.radians(clip[0])))
                if abs(d) < 0.7:
                    k *= 1 - clip[1] * math.cos(d / 0.7 * math.pi / 2)
            v.co.x *= k
            v.co.y *= k
    steps = max(96, reeds * 4)
    o = lathe(rim, coin_mat(p.get("mat", "silver"), ham), "coin", steps=steps, wobble=shape)
    return o


def coin_mat(key, worn=False):
    """Metal with a stamped-looking relief (noise bump on the faces), worn = softer, duller."""
    name = f"obj_coin_{key}_{worn}"
    if name in _M:
        return _M[name]
    base, rough, metal = FINISH.get(key, FINISH["silver"])
    m, b = _principled(name)
    nt = m.node_tree
    b.inputs["Base Color"].default_value = (*[min(1.0, c * 1.05) for c in base], 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = 0.32 + (0.12 if worn else 0.0)  # satin: catches the key light in a dark studio
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 90.0
    n.inputs["Detail"].default_value = 4.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6 if worn else 0.4
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    _M[name] = m
    return m


def shears(p):
    """Old iron hand shears: two long blades crossing at a pivot, ring handles. Lies flat (blades along +x)."""
    root = bpy.data.objects.new("shears", None)
    bpy.context.scene.collection.objects.link(root)
    iron, dark = finish("steel"), finish("black_paint")
    open_deg = p.get("open", 18)
    for side in (-1, 1):
        arm = bpy.data.objects.new("arm", None)
        bpy.context.scene.collection.objects.link(arm)
        arm.parent = root
        arm.rotation_euler.z = math.radians(side * open_deg / 2)
        me = bpy.data.meshes.new("blade")
        me.from_pydata([(0, -0.004, 0), (0.11, -0.0005, 0), (0.11, 0.0005, 0), (0, 0.006, 0),
                        (0, -0.004, 0.002), (0.11, -0.0005, 0.002), (0.11, 0.0005, 0.002), (0, 0.006, 0.002)], [],
                       [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)])
        bl = _obj("blade", me, iron)
        bl.location.z = 0.002 if side > 0 else 0.0
        bl.parent = arm
        bpy.ops.mesh.primitive_cylinder_add(radius=0.0035, depth=0.07, vertices=12, location=(-0.035, 0, 0.002),
                                            rotation=(0, math.radians(90), 0))
        hd = bpy.context.active_object
        hd.data.materials.append(dark)
        hd.parent = arm
        bpy.ops.mesh.primitive_torus_add(major_radius=0.012, minor_radius=0.003, location=(-0.08, side * 0.004, 0.002))
        ring = bpy.context.active_object
        ring.data.materials.append(dark)
        ring.parent = arm
    bpy.ops.mesh.primitive_cylinder_add(radius=0.0035, depth=0.006, vertices=16, location=(0, 0, 0.002))
    piv = bpy.context.active_object
    piv.data.materials.append(finish("brass"))
    piv.parent = root
    return root


def shavings(p):
    """A little heap of bright silver slivers (clippings): thin curved strips scattered within radius r."""
    import random
    rng = random.Random(p.get("seed", 3))
    n, rad = p.get("n", 24), p.get("r", 0.02)
    me = bpy.data.meshes.new("shavings")
    bm = bmesh.new()
    for i in range(n):
        a, d = rng.uniform(0, 2 * math.pi), rad * math.sqrt(rng.random())
        cx, cy = d * math.cos(a), d * math.sin(a)
        L, rot, z = rng.uniform(0.004, 0.009), rng.uniform(0, math.pi), 0.0004 + 0.0012 * (1 - d / rad) * rng.random()
        pts = []
        for k in range(5):
            t = k / 4 - 0.5
            x, y = t * L, 0.0012 * math.cos(t * math.pi) * 2
            pts.append((cx + x * math.cos(rot) - y * math.sin(rot), cy + x * math.sin(rot) + y * math.cos(rot), z))
        vs = [bm.verts.new(q) for q in pts] + [bm.verts.new((q[0], q[1], q[2] + 0.0007)) for q in pts]
        for k in range(4):
            bm.faces.new((vs[k], vs[k + 1], vs[k + 6], vs[k + 5]))
    bm.to_mesh(me)
    bm.free()
    return _obj("shavings", me, finish("silver"))


def scale_stand(p):
    """Balance scale base + post; the swinging beam is its own piece ("@scale_beam" at the pivot, z = 0.16)."""
    root = bpy.data.objects.new("scale_stand", None)
    bpy.context.scene.collection.objects.link(root)
    lathe([[0, 0], [0.05, 0], [0.05, 0.008], [0.03, 0.014], [0.008, 0.02], [0.008, 0.155], [0.012, 0.16],
           [0, 0.165]], finish("brass"), "stand").parent = root
    return root


def scale_beam(p):
    """Beam (origin at the pivot) with two hanging pans; tilt it with a shot move "tilt_to" (deg)."""
    root = bpy.data.objects.new("scale_beam", None)
    bpy.context.scene.collection.objects.link(root)
    brass = finish("brass")
    bpy.ops.mesh.primitive_cylinder_add(radius=0.003, depth=0.2, vertices=12, rotation=(0, math.radians(90), 0))
    b = bpy.context.active_object
    b.data.materials.append(brass)
    b.parent = root
    for sx in (-1, 1):
        for k in range(3):  # three chains as thin rods
            a = k * 2 * math.pi / 3
            bpy.ops.mesh.primitive_cylinder_add(radius=0.0007, depth=0.09, vertices=6,
                                                location=(sx * 0.1 + 0.012 * math.cos(a) / 2, 0.012 * math.sin(a) / 2,
                                                          -0.045))
            c = bpy.context.active_object
            c.rotation_euler = (0.13 * math.sin(a), -0.13 * math.cos(a), 0)
            c.data.materials.append(brass)
            c.parent = root
        pan = lathe([[0, -0.098], [0.03, -0.096], [0.034, -0.088], [0.0335, -0.087], [0.029, -0.094],
                     [0, -0.0955]], brass, "pan")
        pan.location.x = sx * 0.1
        pan.parent = root
    return root


def magnifier(p):
    root = bpy.data.objects.new("magnifier", None)
    bpy.context.scene.collection.objects.link(root)
    lens = lathe([[0, 0.0], [0.03, 0.002], [0.03, 0.004], [0, 0.006]], glass("clear"), "lens", steps=64)
    lens.parent = root
    bpy.ops.mesh.primitive_torus_add(major_radius=0.031, minor_radius=0.0025, location=(0, 0, 0.003))
    rim = bpy.context.active_object
    rim.data.materials.append(finish("brass"))
    rim.parent = root
    bpy.ops.mesh.primitive_cylinder_add(radius=0.005, depth=0.08, vertices=16, location=(0.072, 0, 0.003),
                                        rotation=(0, math.radians(90), 0))
    hd = bpy.context.active_object
    hd.data.materials.append(finish("black_paint"))
    hd.parent = root
    return root


def magnet(p):
    w = p.get("w", 0.05)
    root = bpy.data.objects.new("magnet", None)
    bpy.context.scene.collection.objects.link(root)
    red, steel = finish("red_paint"), finish("chrome")
    bpy.ops.mesh.primitive_torus_add(major_radius=w * 0.35, minor_radius=w * 0.15, major_segments=48,
                                     minor_segments=16, location=(0, 0, w * 0.75), rotation=(math.radians(90), 0, 0))
    arc = bpy.context.active_object
    bm = bmesh.new()
    bm.from_mesh(arc.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > 0.0005], context="VERTS")  # keep the top half
    bm.to_mesh(arc.data)
    bm.free()
    arc.data.materials.append(red)
    arc.parent = root
    for sx in (-1, 1):
        for z0, h, mat in ((w * 0.12, w * 0.63, red), (0.0, w * 0.12, steel)):
            bpy.ops.mesh.primitive_cylinder_add(radius=w * 0.15, depth=h, vertices=24,
                                                location=(sx * w * 0.35, 0, z0 + h / 2))
            leg = bpy.context.active_object
            leg.data.materials.append(mat)
            leg.parent = root
    for o in root.children:
        for poly in o.data.polygons:
            poly.use_smooth = True
    return root


def ball(p):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=p.get("r", 0.012), segments=32, ring_count=16,
                                         location=(0, 0, p.get("r", 0.012)))
    o = bpy.context.active_object
    o.data.materials.append(finish("gloss", p.get("color", [0.9, 0.2, 0.2])))
    bpy.ops.object.shade_smooth()
    return o


def wall(p):
    """A vertical backdrop facing -y: subway tiles or a flat colour. 'at' is its bottom centre."""
    w, h = p.get("size", [2.0, 1.5])
    me = bpy.data.meshes.new("wall")
    me.from_pydata([(-w / 2, 0, 0), (w / 2, 0, 0), (w / 2, 0, h), (-w / 2, 0, h)], [], [(0, 1, 2, 3)])
    mat = subway(p["tiles"], p.get("tile", 0.075)) if p.get("tiles") else finish("matte", p.get("color", [0.4, 0.75, 0.72]))
    o = _obj("wall", me, mat)
    for poly in o.data.polygons:
        poly.use_smooth = False
    return o


def custom_lathe(p):
    o = lathe(p["profile"], finish(p.get("mat", "steel"), p.get("color")), "lathe")
    return o if p.get("solid", True) else _shell(o)


BUILD = {"bottle": bottle, "cap": cap, "cork": cork, "coin": coin, "magnet": magnet, "ball": ball, "wall": wall,
         "lathe": custom_lathe, "shears": shears, "shavings": shavings, "scale_stand": scale_stand,
         "scale_beam": scale_beam, "magnifier": magnifier}
KINDS = tuple(BUILD)


def place(o, p):
    """Position a built object (its own origin at the bottom) at 'at', turned 'rot' degrees, scaled 's'."""
    o.location = tuple(p.get("at", (0, 0, 0)))
    o.rotation_mode = "XYZ"
    o.rotation_euler.z = math.radians(p.get("rot", 0.0))
    if p.get("tilt") and p["m"] != "@bottle":
        o.rotation_euler.x = math.radians(p["tilt"])
    s = p.get("s", 1.0)
    o.scale = (s, s, s)
    return o


_ = Matrix  # (kept for callers that build matrices from this module)
