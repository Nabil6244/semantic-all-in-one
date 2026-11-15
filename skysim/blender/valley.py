"""Sky Sim landscape look in Blender (docs/skysim/PLAN.md; realism rule: memory skysim-realism), v2 matched to the reference
frames of the TON 618 film: a fjord (flat floor under a big lake, sheer walls, snow high up, a jagged far ridge, a sandy
shore), a sky that stays blue, a tilted spiral accretion disc with a jet, and camera views that change between rungs.

blender -b --factory-startup -P skysim/blender/valley.py -- <job.json>
job.json: { "out", "res": [w, h], "samples", "trees", "quality": {...}, "anchors_file",
            "states": [ { "name", "t", "flux_x", "angular_deg", "kind", "object",
                          "cam": { "scale", "dx", "dy", "view", "view_from", "view_k" } } ] }
Writes <out>/<name>.png per state and <out>/<anchors_file> ({ name: { x, y, r } } in 0..1 frame units, y down).

The light (flux_x, sunlight at Earth = 1) drives everything (heat()): night -> moonlit blue, stars; day -> HDRI sky, sunlit
slopes; boil -> steam over the lake; burn -> fires on the slopes, the lake gone to a cracked bed; melt -> the camera stops
down (the sky turns navy, never black or brown), the rock glows with lava speckles.
"""
import json
import math
import sys
import time
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Euler, Vector, noise

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / 'assets'
job = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text())
OUT = Path(job['out']); OUT.mkdir(parents=True, exist_ok=True)
SIZE, N = 4000.0, int(job.get('mesh', 620))
TERRAIN = job.get('terrain')                 # a real place from skysim/tools/fetch_terrain.py, else the code-made valley
if TERRAIN:
    import numpy as np
    DEM = np.load(ASSETS / 'terrain' / f'{TERRAIN}.npy'); DEM_META = json.loads((ASSETS / 'terrain' / f'{TERRAIN}.json').read_text())
    SIZE, N = 8000.0, int(job.get('mesh', 900))
SKY_DIST = 12000.0
FLOOR = -8.0                         # the valley floor (the lake bed) under a lake at z = 0
DISC_RADII = 80.0                    # the glowing accretion disc reaches this many horizon radii
SHADOW_RADII = 1.6                   # the black centre (smaller than the photon shadow, as the reference draws it)


def clamp01(x): return min(1.0, max(0.0, x))
def smooth(x): k = clamp01(x); return k * k * (3 - 2 * k)
def lerp(a, b, k): return a + (b - a) * k


def heat(flux):
    """The light ladder (same thresholds as whatif-engine/lib/skysim_land.mjs heatOf())."""
    L = math.log10(max(flux or 0.0, 1e-30))
    raw = smooth((L + 4.5) / 4.5)
    stop = smooth((L - 1.5) / 3)
    evap = smooth((L - 0.6) / 0.7)
    return dict(L=L, raw=raw, stop=stop, direct=smooth((L + 2.2) / 2.2), scorch=smooth((L - 0.45) / 0.6),
                burn=smooth((L - 0.85) / 0.4), melt=smooth((L - 2.4) / 2), evap=evap, boil=smooth((L - 0.2) / 0.5) * (1 - evap),
                seen=smooth((L + 15) / 2))


# ---- render settings -----------------------------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = job.get('res', [1920, 1080])
sc.render.image_settings.file_format = 'PNG'
sc.view_settings.view_transform = 'AgX'
for attr, val in (('taa_render_samples', job.get('samples', 16)), ('use_raytracing', True), ('use_shadows', True),
                  ('shadow_resolution_scale', 1.0), ('volumetric_tile_size', '8'), ('volumetric_end', 6000.0),
                  ('shadow_pool_size', '1024')):
    try:
        setattr(sc.eevee, attr, val)
    except Exception as e:  # noqa: BLE001
        print('eevee setting skipped', attr, e)
# speed settings benchmarked as invisible (skysim/tools/bench_blender.py)
QUALITY = job.get('quality') or {}
for key, val in QUALITY.items():
    if key in ('cull_trees',):
        continue
    target, attr = (sc.eevee.ray_tracing_options, key[3:]) if key.startswith('rt_') else (sc.eevee, key)
    try:
        setattr(target, attr, val)
    except Exception as e:  # noqa: BLE001
        print('quality setting skipped', key, e)


def image(path, non_color=False):
    im = bpy.data.images.load(str(path), check_existing=True)
    if non_color:
        im.colorspace_settings.name = 'Non-Color'
    return im


class G:
    """Tiny node-graph helper: G(node_tree).math('MULTIPLY', a, b) etc. Inputs may be sockets or numbers."""
    def __init__(self, nt): self.nt, self.n, self.L = nt, nt.nodes, nt.links

    def _in(self, sock, v):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, tuple):
            n = len(sock.default_value) if hasattr(sock.default_value, '__len__') else 0
            sock.default_value = (*v, 1.0) if n == 4 and len(v) == 3 else v
        else:
            self.L.new(v, sock)

    def math(self, op, a, b=None, c=None):
        m = self.n.new('ShaderNodeMath'); m.operation = op
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self._in(m.inputs[i], v)
        return m.outputs[0]

    def range(self, v, fmin, fmax, tmin=0.0, tmax=1.0):
        m = self.n.new('ShaderNodeMapRange')
        self._in(m.inputs['Value'], v); m.inputs['From Min'].default_value = fmin; m.inputs['From Max'].default_value = fmax
        m.inputs['To Min'].default_value = tmin; m.inputs['To Max'].default_value = tmax
        return m.outputs['Result']

    def mix(self, a, b, fac, blend='MIX'):
        m = self.n.new('ShaderNodeMix'); m.data_type = 'RGBA'; m.blend_type = blend
        self._in(m.inputs[6], a); self._in(m.inputs[7], b); self._in(m.inputs['Factor'], fac)
        return m.outputs[2]

    def mixv(self, a, b, fac):
        m = self.n.new('ShaderNodeMix'); m.data_type = 'VECTOR'
        self._in(m.inputs[4], a); self._in(m.inputs[5], b); self._in(m.inputs['Factor'], fac)
        return m.outputs[1]

    def value(self, v=0.0):
        x = self.n.new('ShaderNodeValue'); x.outputs[0].default_value = v
        return x

    def coords(self, kind='Object'):
        return self.n.new('ShaderNodeTexCoord').outputs[kind]

    def xyz(self, v):
        s = self.n.new('ShaderNodeSeparateXYZ'); self._in(s.inputs[0], v)
        return s.outputs

    def noise(self, v, scale, detail=6, rough=0.55):
        t = self.n.new('ShaderNodeTexNoise'); self._in(t.inputs['Vector'], v)
        t.inputs['Scale'].default_value = scale; t.inputs['Detail'].default_value = detail; t.inputs['Roughness'].default_value = rough
        return t

    def ramp(self, v, stops):
        r = self.n.new('ShaderNodeValToRGB'); self._in(r.inputs['Fac'], v)
        els = r.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for e, (pos, col) in zip(els, stops):
            e.position = pos; e.color = (*col, 1) if len(col) == 3 else col
        return r.outputs['Color']

    def tex_set(self, name, scale, vec):
        """A Poly Haven set box-projected in object space -> (colour, roughness, normal)."""
        mp = self.n.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1 / scale,) * 3; self._in(mp.inputs['Vector'], vec)
        out = {}
        for key, nc in (('diff', False), ('rough', True), ('nor', True)):
            t = self.n.new('ShaderNodeTexImage'); t.image = image(ASSETS / 'textures' / name / f'{key}.jpg', nc)
            t.projection = 'BOX'; t.projection_blend = 0.3; self.L.new(mp.outputs['Vector'], t.inputs['Vector']); out[key] = t.outputs['Color']
        nm = self.n.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = 1.2; self.L.new(out['nor'], nm.inputs['Color'])
        return out['diff'], out['rough'], nm.outputs['Normal']


def blended(mat):
    for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):   # dithered drops fully transparent glow
        try:
            setattr(mat, attr, val)
        except Exception:  # noqa: BLE001
            pass


# ---- terrain: a fjord ----------------------------------------------------------------------------------------------
bpy.ops.mesh.primitive_grid_add(x_subdivisions=N, y_subdivisions=N, size=SIZE)
terr = bpy.context.active_object
def dem_sample():
    """Real elevation under every vertex: the camera (world 0, -1700) sits at cam_px on the water looking along axis_deg.
    Water becomes a shallow bowl just under the lake (a bed that shows when it dries); the shore rises from the waterline."""
    m = DEM_META['m_per_px']; n = DEM.shape[0]
    c0, r0 = DEM_META['cam_px']; b = math.radians(DEM_META['axis_deg'])
    fwd = (math.sin(b), -math.cos(b)); right = (math.cos(b), math.sin(b))
    co = np.array([(v.co.x, v.co.y) for v in terr.data.vertices], dtype=np.float64)
    x, yy = co[:, 0], co[:, 1] + 1700.0
    level = DEM_META.get('level_m', 0.0)
    c = np.clip(c0 + (x * right[0] + yy * fwd[0]) / m, 0, n - 1.001); r = np.clip(r0 + (x * right[1] + yy * fwd[1]) / m, 0, n - 1.001)
    ci, ri = c.astype(int), r.astype(int); fc, fr = c - ci, r - ri
    hgt = (DEM[ri, ci] * (1 - fc) * (1 - fr) + DEM[ri, ci + 1] * fc * (1 - fr) + DEM[ri + 1, ci] * (1 - fc) * fr + DEM[ri + 1, ci + 1] * fc * fr - level)
    land = np.clip((hgt - 1.0) / 6.0, 0, 1)                       # 0 = water, 1 = land
    z = np.where(land > 0, FLOOR + 8.0 * land + np.maximum(hgt - 7.0, 0.0), FLOOR - 2.5 * (1 - land))
    for v, zz in zip(terr.data.vertices, z):
        v.co.z = float(zz)


for v in ([] if TERRAIN else terr.data.vertices):
    x, y = v.co.x, v.co.y
    u = (y + SIZE / 2) / SIZE                                    # 0 at the camera end, 1 at the far end
    p = Vector((x / 650, y / 650, 0.0))
    half = lerp(330, 150, u) + noise.fractal(Vector((0.0, y / 420, 7.3 if x > 0 else 1.1)), 0.7, 2.0, 4, noise_basis='PERLIN_ORIGINAL') * 110   # a ragged shore
    pw = Vector((x / 1400, y / 1400, 0.0))
    pw += Vector((noise.fractal(pw * 1.7, 0.5, 2.0, 3), noise.fractal(pw * 1.7 + Vector((5.2, 1.3, 0)), 0.5, 2.0, 3), 0.0)) * 0.35   # domain warp: no grid of peaks
    ridged = noise.ridged_multi_fractal(pw, 0.85, 2.0, 6, 1.0, 2.0, noise_basis='PERLIN_ORIGINAL') * 0.55
    mass = 0.45 + 0.55 * smooth(0.5 + 0.9 * noise.fractal(Vector((x / 2600, y / 2600, 3.7)), 0.5, 2.0, 2, noise_basis='PERLIN_ORIGINAL'))   # some summits tower, others are low
    ridged = clamp01(ridged) * mass
    detail = noise.fractal(p * 6, 0.6, 2.0, 5, noise_basis='PERLIN_ORIGINAL')
    out = max(0.0, abs(x) - half)                                # distance up the wall
    side = min(1.0, out / (SIZE * 0.42 - half))
    wall = side ** 1.3 * 1150 * (0.35 + 0.65 * ridged)         # forested lower slopes, uneven summits
    farwall = max(0.0, (y - 900) / (SIZE * 0.5 - 900)) ** 1.2 * 900 * (0.4 + 0.6 * ridged)   # the jagged ridge closing the valley
    beach = smooth((-x - half + 150) / 90) * smooth((-1100 - y) / 500) * 12 if x < 0 else 0.0   # a sandy shore, near left
    z = FLOOR + max(wall, farwall) + beach + detail * (2 + 30 * smooth(out / 250))
    v.co.z = z
if TERRAIN:
    dem_sample()
    terr.modifiers.new('rock_detail', 'DISPLACE')                 # sub-9 m relief the elevation data cannot hold
    _dt = bpy.data.textures.new('rock_detail', 'CLOUDS'); _dt.noise_scale = 6.0; _dt.noise_depth = 4
    terr.modifiers['rock_detail'].texture = _dt; terr.modifiers['rock_detail'].strength = 3.0; terr.modifiers['rock_detail'].mid_level = 0.5
    terr.data.update()
bpy.ops.object.shade_smooth()

tm = bpy.data.materials.new('terrain'); tm.use_nodes = True
g = G(tm.node_tree); bsdf = tm.node_tree.nodes['Principled BSDF']
obj = g.coords('Object'); oz = g.xyz(obj)[2]
nz = g.xyz(g.n.new('ShaderNodeNewGeometry').outputs['Normal'])[2]
ROCK_A, ROCK_B = (('rock_face_03', 18.0), ('cliff_side', 55.0)) if TERRAIN else (('aerial_rocks_02', 60.0), ('aerial_rocks_02', 173.0))
rock_a, rock_r, rock_n = g.tex_set(ROCK_A[0], ROCK_A[1], obj)
rot = g.n.new('ShaderNodeMapping'); rot.inputs['Rotation'].default_value = (0.4, 0.7, 1.1); g.L.new(obj, rot.inputs['Vector'])
rock_b, _, _ = g.tex_set(ROCK_B[0], ROCK_B[1], rot.outputs['Vector'])
rock_c = g.mix(rock_a, rock_b, g.range(g.noise(obj, 0.006, 4).outputs['Fac'], 0.35, 0.65))
if TERRAIN:
    rock_c = g.mix(rock_c, (0.16, 0.16, 0.155), 0.45)                     # Norwegian gneiss is grey, not tan
grass_c, grass_r, grass_n = g.tex_set('aerial_grass_rock', 45.0, obj)
big = g.noise(obj, 0.004, 6)
gentle = g.range(g.math('ADD', nz, g.math('MULTIPLY', big.outputs['Fac'], 0.14)), *((0.5, 0.72) if TERRAIN else (0.86, 1.0)))   # 1 = gentle (grass), 0 = sheer
scorch_v, burn_v, melt_v, evap_v = (g.value() for _ in range(4))
if TERRAIN:                                                               # summer meadow: the scan's detail, a real green
    _bw = g.n.new('ShaderNodeRGBToBW'); g.L.new(grass_c, _bw.inputs[0])
    grass_c = g.mix((0.0, 0.0, 0.0), (0.05, 0.11, 0.025), g.range(_bw.outputs[0], 0.0, 0.5, 0.45, 1.3))
grass_t = g.mix(grass_c, (0.12, 0.09, 0.05), g.math('MULTIPLY', scorch_v.outputs[0], 0.75))       # green -> brown
ground = g.mix(rock_c, grass_t, gentle)
# snow on the high, not-too-steep faces (moonlight catches it at night)
snow = g.math('MULTIPLY', g.range(oz, 620, 760), g.range(nz, 0.35, 0.6))
snow_k = g.math('MULTIPLY', g.math('MULTIPLY', snow, g.range(g.noise(obj, 0.02, 4).outputs['Fac'], 0.35, 0.6)), g.math('SUBTRACT', 1.0, scorch_v.outputs[0]))
ground = g.mix(ground, (0.75, 0.78, 0.82), snow_k)
# sand at the waterline
sand = g.math('MULTIPLY', g.range(oz, FLOOR + 6, FLOOR + 9), g.range(oz, FLOOR + 22, FLOOR + 14))
sandcol = g.mix((0.42, 0.37, 0.3), (0.55, 0.5, 0.42), g.noise(obj, 0.3, 4).outputs['Fac'])
ground = g.mix(ground, sandcol, g.math('MULTIPLY', sand, gentle))
# the dry lake bed: grey with dark polygon cracks, showing as the water goes
bed = g.range(oz, FLOOR + 5, FLOOR + 1.5)
cr = g.n.new('ShaderNodeTexVoronoi'); cr.feature = 'DISTANCE_TO_EDGE'; cr.inputs['Scale'].default_value = 0.06; g.L.new(obj, cr.inputs['Vector'])
cracks = g.range(cr.outputs['Distance'], 0.0, 0.05)                           # 0 on a crack: ~17 m plates, readable from the shore
mud_c, _, _ = g.tex_set('mud_cracked_dry_03', 6.0, obj)                       # fine cracks close to the camera
mud_grey = g.mix(mud_c, (0.06, 0.058, 0.055), 0.65)                           # dark grey, not brown
bedcol = g.mix((0.006, 0.006, 0.006), g.mix(mud_grey, (0.075, 0.072, 0.068), g.range(g.noise(obj, 0.05, 5).outputs['Fac'], 0.3, 0.7, 0.0, 0.5)), cracks)
ground = g.mix(ground, bedcol, bed)
g.L.new(ground, bsdf.inputs['Base Color'])
g.L.new(g.mix(rock_r, grass_r, gentle), bsdf.inputs['Roughness'])
g.L.new(g.mixv(rock_n, grass_n, gentle), bsdf.inputs['Normal'])
# heat glow: fire patches on the gentle slopes while it burns, lava speckles over the rock as it melts
spk = g.n.new('ShaderNodeTexVoronoi'); spk.feature = 'F1'; spk.inputs['Scale'].default_value = 0.35; spk.inputs['Randomness'].default_value = 1.0
g.L.new(obj, spk.inputs['Vector'])
rnd = g.xyz(spk.outputs['Color'])[0]
speck = g.math('MULTIPLY', g.range(spk.outputs['Distance'], 0.35, 0.15), g.range(rnd, 0.45, 0.75))   # small blobs, some cells
fire_blob = g.range(g.noise(obj, 0.012, 5).outputs['Fac'], 0.52, 0.62)
notbed = g.math('SUBTRACT', 1.0, bed)
forest_band = g.math('MULTIPLY', g.range(nz, 0.55, 0.7), g.range(oz, 600, 480))
fire = g.math('MULTIPLY', g.math('MULTIPLY', g.math('MULTIPLY', fire_blob, forest_band), notbed),   # fires on the slopes, never the lake bed
             g.math('MULTIPLY', burn_v.outputs[0], g.math('SUBTRACT', 1.0, melt_v.outputs[0])))
lava = g.math('MULTIPLY', g.math('MULTIPLY', speck, melt_v.outputs[0]), notbed)
glow = g.math('ADD', g.math('MULTIPLY', fire, 2.5), g.math('MULTIPLY', lava, 2.2))
glow_k = g.value(1.0)                                         # x2^stops, so the glow holds when the camera stops down
bsdf.inputs['Emission Color'].default_value = (1.0, 0.32, 0.05, 1)
g.L.new(g.math('MULTIPLY', glow, glow_k.outputs[0]), bsdf.inputs['Emission Strength'])
terr.data.materials.append(tm)


# ---- forest ------------------------------------------------------------------------------------------------------
def conifer():
    parts = []
    for r, z, d in ((3.0, 5, 8), (2.3, 9, 7), (1.5, 12.5, 6), (0.8, 15.2, 4)):
        bpy.ops.mesh.primitive_cone_add(vertices=7, radius1=r, depth=d, location=(0, 0, z - 4000)); parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=5, radius=0.3, depth=3, location=(0, 0, 1.5 - 4000)); parts.append(bpy.context.active_object)
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    t = bpy.context.active_object; t.location = (0, 0, -4000)
    return t


tree = conifer()
scan_tree = None
_scan = ASSETS / 'models' / 'fir_tree_01' / 'fir_tree_01.blend'
if TERRAIN and _scan.exists():
    with bpy.data.libraries.load(str(_scan), link=False) as (src, dst):
        dst.objects = [o for o in src.objects if o.endswith('_LOD2')]
    scans = [o for o in dst.objects if o]
    for o in scans:
        sc.collection.objects.link(o); o.location = (0, 0, -4000)
    if scans:
        scol = bpy.data.collections.new('scan_trees')
        for o in scans:
            scol.objects.link(o)
        scan_tree = scol
lm = bpy.data.materials.new('leaf'); lm.use_nodes = True
lg = G(lm.node_tree); lb = lm.node_tree.nodes['Principled BSDF']; lb.inputs['Roughness'].default_value = 0.9
rnd_t = lg.n.new('ShaderNodeObjectInfo').outputs['Random']
leaf = lg.ramp(rnd_t, [(0.0, (0.006, 0.016, 0.008)), (1.0, (0.025, 0.045, 0.016))])
char_v = lg.value()
lg.L.new(lg.mix(leaf, (0.015, 0.01, 0.008), char_v.outputs[0]), lb.inputs['Base Color'])
tfire_v = lg.value()
lb.inputs['Emission Color'].default_value = (1.0, 0.34, 0.05, 1)
lg.L.new(lg.math('MULTIPLY', lg.range(rnd_t, 0.4, 1.0), tfire_v.outputs[0]), lb.inputs['Emission Strength'])
tree.data.materials.append(lm)
vg = terr.vertex_groups.new(name='forest')
CAM_Y = -1700.0
FAR_FROM_M = float(job.get('scan_tree_m', 700)) if scan_tree else 160.0   # cones only where scanned firs are not
forest_n, kept = 0, 0
for v in terr.data.vertices:
    if v.normal.z > (0.5 if TERRAIN else 0.62) and FLOOR + 10 < v.co.z < (700 if TERRAIN else 560) and math.hypot(v.co.x, v.co.y - CAM_Y) > FAR_FROM_M:
        forest_n += 1
        if QUALITY.get('cull_trees') and abs(v.co.x) > (v.co.y - CAM_Y + 400) * math.tan(math.radians(52)) + 80:
            continue
        kept += 1
        vg.add([v.index], 1.0, 'REPLACE')
TREE_SHARE = kept / max(1, forest_n)
NEAR_M = float(job.get('scan_tree_m', 700))               # scanned firs inside this distance of the camera
if scan_tree:
    vg_near = terr.vertex_groups.new(name='forest_near'); near_n = 0
    for v in terr.data.vertices:
        if v.normal.z > 0.5 and FLOOR + 10 < v.co.z < 700 and 60 < math.hypot(v.co.x, v.co.y - CAM_Y) < NEAR_M and v.co.y > CAM_Y - 50:
            vg_near.add([v.index], 1.0, 'REPLACE'); near_n += 1
psm = terr.modifiers.new('trees', 'PARTICLE_SYSTEM'); ps = psm.particle_system; pset = ps.settings
pset.type = 'HAIR'; pset.use_advanced_hair = True; pset.count = max(1, int(int(job.get('trees', 300000 if TERRAIN else 120000)) * TREE_SHARE))
pset.render_type = 'OBJECT'; pset.instance_object = tree; pset.particle_size = 1.7; pset.size_random = 0.5   # 20-30 m spruces
pset.use_rotations = True; pset.rotation_mode = 'GLOB_Z'; pset.phase_factor_random = 2.0; pset.hair_length = 1.0
ps.vertex_group_density = 'forest'
if scan_tree and near_n:
    m2 = terr.modifiers.new('scan_trees', 'PARTICLE_SYSTEM'); p2 = m2.particle_system; s2 = p2.settings
    s2.type = 'HAIR'; s2.use_advanced_hair = True; s2.count = int(job.get('scan_trees', 2500))
    s2.render_type = 'COLLECTION'; s2.instance_collection = scan_tree; s2.use_collection_pick_random = True
    s2.particle_size = 1.3; s2.size_random = 0.4; s2.use_rotations = True; s2.rotation_mode = 'GLOB_Z'; s2.phase_factor_random = 2.0
    s2.hair_length = 1.0; p2.vertex_group_density = 'forest_near'
    print('scan trees near the camera:', s2.count, 'over', near_n, 'vertices')

# ---- lake ----------------------------------------------------------------------------------------------------------
bpy.ops.mesh.primitive_plane_add(size=SIZE, location=(0, 0, 0.0)); lake = bpy.context.active_object
wm = bpy.data.materials.new('water'); wm.use_nodes = True; wg = G(wm.node_tree); wb = wm.node_tree.nodes['Principled BSDF']
wb.inputs['Base Color'].default_value = (0.006, 0.012, 0.016, 1); wb.inputs['Roughness'].default_value = 0.015; wb.inputs['IOR'].default_value = 1.33
wmap = wg.n.new('ShaderNodeMapping'); wmap.inputs['Scale'].default_value = (0.2, 1.0, 1.0); wg.L.new(wg.coords('Object'), wmap.inputs['Vector'])
wave = wg.noise(wmap.outputs['Vector'], 0.5, 4)
wbump = wg.n.new('ShaderNodeBump'); wbump.inputs['Strength'].default_value = 0.025
wg.L.new(wave.outputs['Fac'], wbump.inputs['Height']); wg.L.new(wbump.outputs['Normal'], wb.inputs['Normal'])
lake.data.materials.append(wm)
try:                                          # EEVEE planar probe: the lake mirrors what the screen cannot see
    bpy.ops.object.lightprobe_add(type='PLANE', location=(0, 0, 0.05))
    probe = bpy.context.active_object; probe.scale = (SIZE / 2, SIZE / 2, 1)
except Exception as e:  # noqa: BLE001
    probe = None
    print('planar probe skipped', e)


# ---- air: thin haze over everything, steam low over the lake while it boils -------------------------------------------
def volume_box(name, loc, scale):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); b = bpy.context.active_object; b.name = name; b.scale = scale
    m = bpy.data.materials.new(name); m.use_nodes = True; nn = m.node_tree.nodes; nn.remove(nn['Principled BSDF'])
    vol = nn.new('ShaderNodeVolumePrincipled'); m.node_tree.links.new(vol.outputs[0], nn['Material Output'].inputs['Volume'])
    vg_ = G(m.node_tree); gx, gy, gz = vg_.xyz(vg_.coords('Generated'))        # 0..1 inside the box
    edge = None
    for comp_, lo in ((gx, 0.25), (gy, 0.12), (gz, 0.45)):
        k = vg_.math('MINIMUM', vg_.range(comp_, 0.0, lo), vg_.range(comp_, 1.0, 1.0 - lo))
        edge = k if edge is None else vg_.math('MULTIPLY', edge, k)
    dens = vg_.value()
    vg_.L.new(vg_.math('MULTIPLY', edge, dens.outputs[0]), vol.inputs['Density'])
    b.data.materials.append(m)
    return vol, dens


haze, haze_d = volume_box('haze', (0, 0, 700), (SIZE * 1.6, SIZE * 1.6, 1800))
steam, steam_d = volume_box('steam', (0, -200, 70), (900, 3600, 160))
steam.inputs['Color'].default_value = (0.92, 0.94, 0.97, 1)

# ---- cameras: the reference's views; a rung can glide from one to the next ------------------------------------------
VIEWS = {                                   # location, pitch (deg above straight down), lens (mm)
    'shore': (Vector((0, -1700, 3.0)), 93.0, 20.0),
    'high': (Vector((0, -2050, 640)), 86.0, 22.0),
    'mirror': (Vector((0, -1500, 7.0)), 83.0, 18.0),
    'wide': (Vector((-120, -1900, 60.0)), 92.0, 16.0),
    'low_left': (Vector((-230, -1400, 2.0)), 95.0, 24.0),
}
VIEW_YAW = {'wide': 4.0, 'low_left': 7.0}     # degrees; the far end (and the object) stays in frame
cd = bpy.data.cameras.new('cam'); cd.clip_end = 40000
cam = bpy.data.objects.new('cam', cd); sc.collection.objects.link(cam); sc.camera = cam


def set_camera(c):
    v_to, v_from = VIEWS.get(c.get('view'), VIEWS['shore']), VIEWS.get(c.get('view_from') or c.get('view'), VIEWS['shore'])
    k = smooth(c.get('view_k', 1.0))
    loc = v_from[0].lerp(v_to[0], k); pitch = lerp(v_from[1], v_to[1], k); lens = lerp(v_from[2], v_to[2], k)
    cam.location = loc + Vector((c.get('dx', 0) * 300, 0, -c.get('dy', 0) * 200))
    yaw = lerp(VIEW_YAW.get(c.get('view_from') or c.get('view'), 0.0), VIEW_YAW.get(c.get('view'), 0.0), k)
    cam.rotation_euler = (math.radians(pitch) - c.get('dy', 0) * 0.3, 0, math.radians(-yaw))
    cd.lens = lens * c.get('scale', 1.0)


# ---- light and sky ---------------------------------------------------------------------------------------------------
ELEV = math.radians(13)                     # the sky object above the far end of the valley, inside every view's frame
SKY_DIR = Vector((0, math.cos(ELEV), math.sin(ELEV)))
sd = bpy.data.lights.new('sun', 'SUN'); sd.angle = math.radians(0.6)
sun = bpy.data.objects.new('sun', sd); sc.collection.objects.link(sun)
sun.rotation_euler = (-SKY_DIR).to_track_quat('-Z', 'Y').to_euler()
md = bpy.data.lights.new('moon', 'SUN'); md.angle = math.radians(1.0); md.color = (0.62, 0.72, 1.0)
moon = bpy.data.objects.new('moon', md); sc.collection.objects.link(moon)
moon.rotation_euler = (-Vector((-0.5, -0.6, 0.62)).normalized()).to_track_quat('-Z', 'Y').to_euler()   # moonlight from behind-left

world = bpy.data.worlds.new('world'); sc.world = world; world.use_nodes = True
sg = G(world.node_tree); bg = world.node_tree.nodes['Background']
gen = sg.coords('Generated')
hm = sg.n.new('ShaderNodeMapping'); hm.inputs['Rotation'].default_value = (0, 0, math.radians(180)); sg.L.new(gen, hm.inputs['Vector'])
hdri = sg.n.new('ShaderNodeTexEnvironment'); hdri.image = image(ASSETS / 'hdri' / 'kloofendal_43d_clear_puresky.hdr'); sg.L.new(hm.outputs['Vector'], hdri.inputs['Vector'])
gz = sg.xyz(gen)[2]
night = sg.ramp(gz, [(0.0, (0.045, 0.07, 0.16)), (0.55, (0.012, 0.022, 0.07))])            # moonlit blue, never black
sv = sg.n.new('ShaderNodeTexVoronoi'); sv.inputs['Scale'].default_value = 420; sg.L.new(gen, sv.inputs['Vector'])
star = sg.math('MULTIPLY', sg.math('POWER', sg.range(sv.outputs['Distance'], 0.2, 0.0), 5.0), sg.math('POWER', sg.xyz(sv.outputs['Color'])[0], 4.0))
star_k = sg.value()
stars = sg.math('MULTIPLY', star, star_k.outputs[0])
starsky = sg.mix(night, sg.mix((0, 0, 0), (1, 1, 1), stars), 1.0, 'ADD')
day_v = sg.value(); navy_v = sg.value()
seen_sky = sg.mix(sg.mix(starsky, hdri.outputs['Color'], day_v.outputs[0]), (0.012, 0.028, 0.09), navy_v.outputs[0])   # stopped down: navy
amb_sky = sg.mix(sg.mix(night, hdri.outputs['Color'], day_v.outputs[0]), (0.012, 0.028, 0.09), navy_v.outputs[0])
lp = sg.n.new('ShaderNodeLightPath')
sg.L.new(sg.mix(amb_sky, seen_sky, lp.outputs['Is Camera Ray']), bg.inputs['Color'])     # stars are seen, never lit by


# ---- the sky object: a point of light, then a tilted spiral accretion disc with a jet ---------------------------------
def emission_mat(name, colour):
    m = bpy.data.materials.new(name); m.use_nodes = True; nn = m.node_tree.nodes; nn.remove(nn['Principled BSDF'])
    e = nn.new('ShaderNodeEmission'); e.inputs['Color'].default_value = (*colour, 1)
    m.node_tree.links.new(e.outputs[0], nn['Material Output'].inputs['Surface'])
    return m, e


bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1, location=tuple(SKY_DIR * SKY_DIST)); orb = bpy.context.active_object
orb_m, orb_e = emission_mat('orb', (0.9, 0.93, 1.0)); orb.data.materials.append(orb_m)

bh_view = bpy.data.objects.new('bh_view', None); sc.collection.objects.link(bh_view); bh_view.location = SKY_DIR * SKY_DIST
tt = bh_view.constraints.new('TRACK_TO'); tt.target = cam; tt.track_axis = 'TRACK_Z'; tt.up_axis = 'UP_Y'
bh = bpy.data.objects.new('bh', None); sc.collection.objects.link(bh); bh.parent = bh_view
bh.rotation_euler = Euler((math.radians(-68), 0, math.radians(-9)))    # seen ~22 degrees from edge-on, tipped like the reference

bpy.ops.mesh.primitive_circle_add(vertices=192, radius=1, fill_type='TRIFAN'); disc = bpy.context.active_object; disc.parent = bh
dmat = bpy.data.materials.new('disc'); dmat.use_nodes = True; dg = G(dmat.node_tree); dn = dmat.node_tree.nodes; dn.remove(dn['Principled BSDF'])
dc = dg.coords('Object'); dx_, dy_, _ = dg.xyz(dc)
r = dg.math('SQRT', dg.math('ADD', dg.math('MULTIPLY', dx_, dx_), dg.math('MULTIPLY', dy_, dy_)))
theta = dg.math('ARCTAN2', dy_, dx_)
spin_v = dg.value()
logr = dg.math('LOGARITHM', dg.math('MAXIMUM', r, 0.002), 2.718281828)
arms = dg.math('SINE', dg.math('ADD', dg.math('ADD', dg.math('MULTIPLY', theta, 2.0), dg.math('MULTIPLY', logr, 9.0)), spin_v.outputs[0]))
turb_in = dg.n.new('ShaderNodeCombineXYZ'); dg.L.new(dg.math('MULTIPLY', logr, 3.0), turb_in.inputs[0]); dg.L.new(dg.math('ADD', theta, spin_v.outputs[0]), turb_in.inputs[1])
turb = dg.noise(turb_in.outputs[0], 2.5, 9, 0.6).outputs['Fac']
bands = dg.math('ADD', dg.math('MULTIPLY', arms, 0.22), dg.math('MULTIPLY', turb, 1.1))
col = dg.ramp(r, [(0.0, (1.0, 0.95, 0.85)), (0.025, (1.0, 0.78, 0.38)), (0.08, (1.0, 0.45, 0.06)), (0.3, (1.0, 0.3, 0.02)),
                   (0.65, (0.75, 0.16, 0.01)), (1.0, (0.0, 0.0, 0.0))])
inten = dg.math('MULTIPLY', dg.range(bands, 0.25, 1.1, 0.35, 1.25), dg.range(r, 1.0, 0.6))
disc_e = dn.new('ShaderNodeEmission'); dg.L.new(col, disc_e.inputs['Color'])
disc_k = dg.value()
dg.L.new(dg.math('MULTIPLY', inten, disc_k.outputs[0]), disc_e.inputs['Strength'])
dtr = dn.new('ShaderNodeBsdfTransparent'); dadd = dn.new('ShaderNodeAddShader')
dg.L.new(disc_e.outputs[0], dadd.inputs[0]); dg.L.new(dtr.outputs[0], dadd.inputs[1]); dg.L.new(dadd.outputs[0], dn['Material Output'].inputs['Surface'])
blended(dmat); disc.data.materials.append(dmat)

bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1); shadow = bpy.context.active_object; shadow.parent = bh
smat = bpy.data.materials.new('shadow'); smat.use_nodes = True; sb = smat.node_tree.nodes['Principled BSDF']
sb.inputs['Base Color'].default_value = (0, 0, 0, 1); sb.inputs['Roughness'].default_value = 1; sb.inputs['Specular IOR Level'].default_value = 0
shadow.data.materials.append(smat)

# the jet: a thin beam along the disc's axis, bright at the core, fading along its length and across its width
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=1, depth=2); jet = bpy.context.active_object; jet.parent = bh
jmat = bpy.data.materials.new('jet'); jmat.use_nodes = True; jg = G(jmat.node_tree); jn = jmat.node_tree.nodes; jn.remove(jn['Principled BSDF'])
jx, jy, jz = jg.xyz(jg.coords('Object'))
lw = jg.n.new('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = 0.5
across = jg.range(lw.outputs['Facing'], 1.0, 0.0)          # bright where the beam faces us, fading at its edges
along = jg.math('POWER', jg.range(jg.math('ABSOLUTE', jz), 1.0, 0.0), 1.6)
jstr = jg.value()
je = jn.new('ShaderNodeEmission'); je.inputs['Color'].default_value = (0.82, 0.88, 1.0, 1)
jg.L.new(jg.math('MULTIPLY', jg.math('MULTIPLY', jg.math('POWER', across, 2.0), along), jstr.outputs[0]), je.inputs['Strength'])
jtr = jn.new('ShaderNodeBsdfTransparent'); jadd = jn.new('ShaderNodeAddShader')
jg.L.new(je.outputs[0], jadd.inputs[0]); jg.L.new(jtr.outputs[0], jadd.inputs[1]); jg.L.new(jadd.outputs[0], jn['Material Output'].inputs['Surface'])
blended(jmat); jet.data.materials.append(jmat)


# ---- compositor glare (Blender 5: a compositing node group) ----------------------------------------------------------
def compositor():
    ng = bpy.data.node_groups.new('skysim_comp', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new('CompositorNodeRLayers'); out = ng.nodes.new('NodeGroupOutput')
    glow_n = ng.nodes.new('CompositorNodeGlare'); streak = ng.nodes.new('CompositorNodeGlare')
    for g_, kind, thr, size, strength in ((glow_n, 'Fog Glow', 1.5, 0.45, 0.55), (streak, 'Streaks', 30.0, 0.5, 0.35)):   # streaks: the point star only
        for k, v in (('Type', kind), ('Threshold', thr), ('Size', size), ('Strength', strength), ('Quality', 'High'), ('Streaks', 4)):
            try:
                g_.inputs[k].default_value = v
            except Exception as e:  # noqa: BLE001
                print('glare input skipped', k, e)
    ng.links.new(rl.outputs['Image'], glow_n.inputs['Image']); ng.links.new(glow_n.outputs['Image'], streak.inputs['Image'])
    ng.links.new(streak.outputs['Image'], out.inputs[0])
    sc.compositing_node_group = ng


try:
    compositor()
except Exception as e:  # noqa: BLE001
    print('compositor skipped', e)


# ---- one state -------------------------------------------------------------------------------------------------------
def set_state(st):
    flux, ang, kind = float(st.get('flux_x', 1.0)), float(st.get('angular_deg', 0.5)), st.get('kind', 'star')
    h = heat(flux)
    t = float(st.get('t', 0.0))
    set_camera(st.get('cam', {}))
    # exposure: brighter at night (a moonlit look), stopping down as the light grows; emitters are compensated
    exp = 0.9 * (1 - h['raw']) - 1.3 * h['scorch'] - 2.2 * h['melt']
    sc.view_settings.exposure = exp
    comp = 2 ** (-min(exp, 0.0))
    # sky
    day_v.outputs[0].default_value = clamp01(h['raw'] * 1.15)
    navy_v.outputs[0].default_value = clamp01(h['stop'] * 1.2) * 0.9
    bg.inputs['Strength'].default_value = lerp(1.0, 0.9, h['raw']) * lerp(1.0, comp * 0.9, h['stop'])
    star_k.outputs[0].default_value = 250.0 * (1 - clamp01(h['raw'] * 1.6))
    md.energy = 0.35 * (1 - h['raw'])                         # moonlight on the snow at night
    sd.energy = 5.0 * h['direct'] * (1 + 0.3 * h['scorch'] + 0.6 * h['melt'])
    sd.color = (0.94, 0.95, 1.0) if kind == 'black_hole' else (1.0, 0.96, 0.9)
    # ground, forest, water, air
    scorch_v.outputs[0].default_value = h['scorch']; burn_v.outputs[0].default_value = h['burn']
    melt_v.outputs[0].default_value = h['melt']; evap_v.outputs[0].default_value = h['evap']
    flick = 0.75 + 0.25 * math.sin(t * 7.0) * math.sin(t * 4.3 + 1.0)
    glow_k.outputs[0].default_value = comp * flick
    char_v.outputs[0].default_value = clamp01(h['burn'] * 1.1)
    tfire_v.outputs[0].default_value = (5.0 * h['burn'] * (1 - h['melt']) * flick + 3.0 * h['melt']) * comp
    lake.location.z = lerp(0.0, FLOOR - 4.0, h['evap'])
    if probe is not None:
        probe.location.z = lake.location.z + 0.05
    wmap.inputs['Location'].default_value = (t * 0.35, t * 0.12, 0)
    haze_d.outputs[0].default_value = (lerp(0.00002, 0.0001, h['raw']) + 0.00003 * h['burn']) * (1 - 0.8 * h['melt'])
    haze.inputs['Color'].default_value = (0.62, 0.76, 1.0, 1)
    steam_d.outputs[0].default_value = 0.006 * h['boil']
    # the sky object
    rh = SKY_DIST * math.tan(math.radians(ang) / 2)             # horizon radius in world units
    px = (2 * math.atan(18 / cd.lens)) / sc.render.resolution_x
    disc_r = rh * DISC_RADII
    disc_px = disc_r / SKY_DIST / px
    seen = h['seen']
    show_disc = kind == 'black_hole' and disc_px > 1.5
    dk = smooth((disc_px - 1.5) / 10) if kind == 'black_hole' else 0.0
    orb.scale = (max(rh, SKY_DIST * px * 2.5),) * 3
    orb.hide_render = seen < 0.01 or dk > 0.99
    orb_e.inputs['Strength'].default_value = (120 + 300 * h['raw']) * seen * (1 - dk) if h['L'] < 0 else 250 * seen * (1 - dk)
    orb_e.inputs['Color'].default_value = (0.86, 0.9, 1.0, 1) if kind == 'black_hole' else (1.0, 0.97, 0.92, 1)
    for o in (disc, shadow, jet):
        o.hide_render = not show_disc
    if show_disc:
        bh.scale = (1, 1, 1)
        disc.scale = (disc_r, disc_r, disc_r)
        shadow.scale = (rh * SHADOW_RADII,) * 3
        jet_len = max(disc_r * 4.0, SKY_DIST * math.tan(math.radians(30)))
        jw = max(disc_r * 0.006, SKY_DIST * px * 3.0)
        jet.scale = (jw, jw, jet_len)
        spin_v.outputs[0].default_value = -t * 0.25
        disc_k.outputs[0].default_value = 0.6 * dk * comp      # bright, but below where AgX washes orange to white
        jstr.outputs[0].default_value = 30.0 * dk * comp / (1 + disc_px / 150)   # a huge disc: the jet stays a thin bright line
    return orb if not show_disc else shadow


anchors = {}
for i, st in enumerate([{**job['states'][0], 'name': '_warmup'}] + job['states']):
    target = set_state(st)
    bpy.context.view_layer.update()
    if job.get('debug'):
        for o in (orb, disc, shadow, jet):
            print('DBG', o.name, 'hidden', o.hide_render, 'at', tuple(round(x) for x in o.matrix_world.translation), 'dims', tuple(round(x) for x in o.dimensions))
        print('DBG jet strength', jstr.outputs[0].default_value, 'disc', disc_k.outputs[0].default_value)
    sc.render.filepath = str(OUT / f"{st['name']}.png")
    t_frame = time.time()
    bpy.ops.render.render(write_still=True)
    if st['name'] == '_warmup':
        continue
    c = target.matrix_world.translation
    p = world_to_camera_view(sc, cam, c)
    radius = (disc.matrix_world.to_scale().x if not disc.hide_render else target.matrix_world.to_scale().x)
    edge = world_to_camera_view(sc, cam, c + cam.matrix_world.to_quaternion() @ Vector((radius, 0, 0)))
    anchors[st['name']] = {'x': round(p.x, 5), 'y': round(1 - p.y, 5), 'r': round(abs(edge.x - p.x), 5)}
    print('rendered', st['name'], f'{time.time() - t_frame:.2f}s')
(OUT / job.get('anchors_file', 'anchors.json')).write_text(json.dumps(anchors, indent=1))
