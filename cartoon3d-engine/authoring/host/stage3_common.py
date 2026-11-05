"""Shared helpers for the Stage 3 host build (run inside Blender). Materials stay plain Principled + image, so what the
previews show is what the glTF exporter writes."""
import math
import os

import bmesh
import bpy
import mathutils
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(os.path.dirname(HERE), "build")
TEX = os.path.join(BUILD, "tex")
HEX = {"coral": "#ff7f6b", "mint": "#98e4c8", "silver": "#d4d8de", "stitch": "#9cc4ee", "hair": "#3a2416", "sole": "#f2efe9"}


def lin(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple((x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (1.0,)


def material(name, tex=None, colour=None, rough=0.6, metal=0.0, normal=None, alpha=False, nstrength=0.5, roughtex=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    if colour:
        b.inputs["Base Color"].default_value = lin(colour)
    if tex:
        n = nt.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(tex, check_existing=True)
        nt.links.new(n.outputs[0], b.inputs["Base Color"])
        if alpha:
            nt.links.new(n.outputs[1], b.inputs["Alpha"])
    if roughtex:                                      # glTF roughness lives in the green channel
        n = nt.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(roughtex, check_existing=True)
        n.image.colorspace_settings.name = "Non-Color"
        sp = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(n.outputs[0], sp.inputs[0]); nt.links.new(sp.outputs[1], b.inputs["Roughness"])
    if alpha:
        m.surface_render_method = "DITHERED"
    if normal:
        n = nt.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(normal, check_existing=True)
        n.image.colorspace_settings.name = "Non-Color"
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs[0].default_value = nstrength
        nt.links.new(n.outputs[0], nm.inputs[1]); nt.links.new(nm.outputs[0], b.inputs["Normal"])
    return m


def one_material(obj, mat):
    me = obj.data
    me.materials.clear(); me.materials.append(mat)
    me.polygons.foreach_set("material_index", np.zeros(len(me.polygons), int))


def coords(me):
    a = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def set_coords(me, p):
    me.vertices.foreach_set("co", p.ravel()); me.update()


def key_coords(kb):
    a = np.zeros(len(kb.data) * 3); kb.data.foreach_get("co", a)
    return a.reshape(-1, 3)


def studio(bg="#dfe7ee"):
    s = bpy.context.scene
    s.render.engine = "BLENDER_EEVEE"
    s.view_settings.view_transform = "Standard"; s.view_settings.look = "None"; s.view_settings.exposure = 0
    w = bpy.data.worlds.get("studio") or bpy.data.worlds.new("studio"); s.world = w; w.use_nodes = True
    n = w.node_tree.nodes["Background"]; n.inputs[0].default_value = lin(bg); n.inputs[1].default_value = 0.55
    if "key" not in bpy.data.objects:
        for nm, en, loc, size, col in (("key", 55, (1.4, -2.2, 2.4), 2.4, (1, .96, .9)), ("fill", 22, (-2.2, -1.8, 1.4), 3.0, (.92, .96, 1)),
                                       ("rim", 40, (-.8, 2.2, 2.3), 2.0, (1, 1, 1))):
            L = bpy.data.lights.new(nm, "AREA"); L.energy = en; L.size = size; L.color = col
            o = bpy.data.objects.new(nm, L); s.collection.objects.link(o); o.location = loc
            o.rotation_euler = (mathutils.Vector((0, 0, 1.0)) - mathutils.Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def shot(path, target, dist, azimuth=0, lens=85, res=(900, 1100), lift=0.0):
    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = res
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGBA" if s.render.film_transparent else "RGB"
    cd = bpy.data.cameras.new("c"); cd.lens = lens
    c = bpy.data.objects.new("c", cd); s.collection.objects.link(c)
    a = math.radians(azimuth); t = mathutils.Vector(target)
    c.location = t + mathutils.Vector((dist * math.sin(a), -dist * math.cos(a), lift))
    c.rotation_euler = (t - c.location).to_track_quat("-Z", "Y").to_euler()
    s.camera = c; s.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(c); bpy.data.cameras.remove(cd)


class Binder:
    """Ties any mesh to the body surface: nearest visible triangle + barycentric weights. Gives skin weights and shape-key deltas."""

    def __init__(self, body, rig):
        from mathutils.bvhtree import BVHTree
        me = body.data; self.P = coords(me)
        vis = body.vertex_groups["body"].index
        keep = np.array([any(g.group == vis for g in v.groups) for v in me.vertices])
        me.calc_loop_triangles()
        tri = np.zeros(len(me.loop_triangles) * 3, int); me.loop_triangles.foreach_get("vertices", tri); tri = tri.reshape(-1, 3)
        self.tri = tri[keep[tri].all(1)]
        self.bvh = BVHTree.FromPolygons([tuple(p) for p in self.P], [tuple(int(i) for i in t) for t in self.tri], all_triangles=True)
        bones = {b.name for b in rig.data.bones}
        names = {g.index: g.name for g in body.vertex_groups if g.name in bones}
        self.w = [{names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0} for v in me.vertices]

    def locate(self, pts):
        I = np.zeros((len(pts), 3), int); B = np.zeros((len(pts), 3))
        for n, p in enumerate(pts):
            _, _, f, _ = self.bvh.find_nearest(mathutils.Vector(p))
            t = self.tri[f]; a, b, c = self.P[t]
            v0, v1, v2 = b - a, c - a, np.asarray(p) - a
            d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
            den = d00 * d11 - d01 * d01 or 1e-12
            y = (d11 * d20 - d01 * d21) / den; z = (d00 * d21 - d01 * d20) / den
            bc = np.clip([1 - y - z, y, z], 0, 1); I[n] = t; B[n] = bc / bc.sum()
        return I, B

    def skin(self, obj, I, B, remap=None, limit=4):
        """Write the body's skin weights onto obj (up to `limit` bones per vertex, normalised)."""
        for g in list(obj.vertex_groups):
            obj.vertex_groups.remove(g)
        groups = {}
        for n in range(len(I)):
            acc = {}
            for i, b in zip(I[n], B[n]):
                for name, w in self.w[i].items():
                    name = (remap or {}).get(name, name)
                    acc[name] = acc.get(name, 0) + w * b
            top = sorted(acc.items(), key=lambda kv: -kv[1])[:limit]
            s = sum(w for _, w in top) or 1
            for name, w in top:
                g = groups.get(name) or obj.vertex_groups.new(name=name); groups[name] = g
                g.add([n], w / s, "REPLACE")


def add_key_deltas(obj, base, deltas):
    """deltas: {name: (n,3)} added as shape keys on obj, skipping ones that do not move it."""
    if not obj.data.shape_keys:
        obj.shape_key_add(name="Basis")
    for name, d in deltas.items():
        if np.abs(d).max() < 2e-5:
            continue
        k = obj.shape_key_add(name=name, from_mix=False); k.data.foreach_set("co", (base + d).ravel()); k.value = 0.0


def mesh_object(name, bm, mat, rig):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    me.materials.append(mat); me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    o.parent = rig; m = o.modifiers.new("Armature", "ARMATURE"); m.object = rig
    return o


def loft(rings, closed=True, uv=None):
    """rings: list of (k,3) arrays of equal size -> quad bmesh. uv(i,j) gives per-corner UVs, j may equal k for the wrap column."""
    bm = bmesh.new(); ul = bm.loops.layers.uv.new("UVMap")
    V = [[bm.verts.new(tuple(p)) for p in r] for r in rings]
    k = len(rings[0])
    for i in range(len(rings) - 1):
        for j in range(k if closed else k - 1):
            j2 = (j + 1) % k
            f = bm.faces.new((V[i][j], V[i][j2], V[i + 1][j2], V[i + 1][j]))
            if uv:
                for l, c in zip(f.loops, ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j))):
                    l[ul].uv = uv(*c)
    return bm


def portrait_lights():
    """The Stage 2/3 portrait studio: warm world at 0.44 plus key, fill, hair and bounce area lights aimed at the face."""
    s = bpy.context.scene
    s.view_settings.view_transform = "Standard"; s.view_settings.look = "None"; s.view_settings.exposure = 0
    w = bpy.data.worlds.get("portrait") or bpy.data.worlds.new("portrait"); s.world = w; w.use_nodes = True
    b0 = w.node_tree.nodes["Background"]; b0.inputs[0].default_value = lin("#e9e4de"); b0.inputs[1].default_value = 0.44
    tg = mathutils.Vector((0, -0.05, 1.475))
    for nme, en, off, size, colr in (("p_key", 24, (-0.85, -1.15, 0.65), 1.4, (1, .95, .89)), ("p_fill", 8, (1.1, -1.1, 0.05), 1.8, (.94, .96, 1)),
                                     ("p_hair", 16, (0.65, 0.95, 0.75), 0.8, (1, .97, .93)), ("p_bounce", 3, (0, -0.8, -0.7), 1.2, (1, .86, .76))):
        if nme in bpy.data.objects:
            continue
        lg = bpy.data.lights.new(nme, "AREA"); lg.energy = en; lg.size = size; lg.color = colr
        o = bpy.data.objects.new(nme, lg); s.collection.objects.link(o); o.location = tg + mathutils.Vector(off)
        o.rotation_euler = (tg - o.location).to_track_quat("-Z", "Y").to_euler()
