"""Mocap -> our rigs. CMU BVH clips (free incl. commercial, downloads/mocap/*.bvh, cgspeed conversion) are copied
onto the host (CC rig), Hoorain (Auto-Rig Pro FK controls) and Noraiz (our rig) by DIRECTION matching: each target
bone is turned so the segment to its child joint points where the matching mocap segment points, after rotating the
mocap's facing onto the character's facing. Works across different bone rolls/rests; twist is not copied.

    import mocap
    mocap.apply(rig, "host", bvh, src_t0=0.2, dur=2.6, at_frame=20, holder=holder_obj, blend=0.3)
"""
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

# target bone -> (target child joint bone or None, source bone). Parents before children.
MAPS = {
    "host": [
        ("CC_Base_Spine01", "CC_Base_Spine02", "Spine"), ("CC_Base_Spine02", "CC_Base_NeckTwist01", "Spine1"),
        ("CC_Base_NeckTwist01", "CC_Base_Head", "Neck"), ("CC_Base_Head", None, "Head"),
        ("CC_Base_L_Upperarm", "CC_Base_L_Forearm", "LeftArm"), ("CC_Base_L_Forearm", "CC_Base_L_Hand", "LeftForeArm"),
        ("CC_Base_L_Hand", None, "LeftHand"),
        ("CC_Base_R_Upperarm", "CC_Base_R_Forearm", "RightArm"), ("CC_Base_R_Forearm", "CC_Base_R_Hand", "RightForeArm"),
        ("CC_Base_R_Hand", None, "RightHand"),
    ],
    "hoorain": [
        ("c_arm_fk.l", "c_forearm_fk.l", "LeftArm"), ("c_forearm_fk.l", "c_hand_fk.l", "LeftForeArm"),
        ("c_arm_fk.r", "c_forearm_fk.r", "RightArm"), ("c_forearm_fk.r", "c_hand_fk.r", "RightForeArm"),
    ],
    "noraiz": [
        ("spine", "chest", "Spine"), ("chest", "neck", "Spine1"), ("head", None, "Head"),
        ("upper_arm.L", "forearm.L", "LeftArm"), ("forearm.L", "hand.L", "LeftForeArm"), ("hand.L", None, "LeftHand"),
        ("upper_arm.R", "forearm.R", "RightArm"), ("forearm.R", "hand.R", "RightForeArm"), ("hand.R", None, "RightHand"),
    ],
}
# mocap is the performer's left; our rigs' ".L"/"_L_"/".l" are the character's left too


def load_clip(bvh, fps):
    """Import a BVH, sample every bone's world head/tail at the scene fps; returns frames list + rest data."""
    before = set(bpy.data.objects)
    bpy.ops.import_anim.bvh(filepath=str(bvh), axis_forward="-Z", axis_up="Y", use_fps_scale=True, global_scale=0.01,
                            update_scene_fps=False, update_scene_duration=False, rotate_mode="NATIVE")
    src = next(o for o in bpy.data.objects if o not in before)
    act = src.animation_data.action
    f0, f1 = (int(x) for x in act.frame_range)
    sc = bpy.context.scene
    keep = sc.frame_current
    frames = []
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        mw = src.matrix_world
        frames.append({b.name: (mw @ b.head, mw @ b.tail) for b in src.pose.bones})
    sc.frame_set(keep)
    bpy.data.objects.remove(src, do_unlink=True)
    bpy.data.actions.remove(act)
    return frames


def facing(fr):
    """Yaw of the performer: forward = up x (left hip -> right hip) ... returns forward vector in XY."""
    l, r = fr["LeftUpLeg"][0], fr["RightUpLeg"][0]
    right = (r - l)
    right.z = 0
    fwd = Vector((0, 0, 1)).cross(right)          # z-up: rotate 'right' +90 -> forward
    fwd.z = 0
    return fwd.normalized()


def _aim(rig, pb, child, d_world):
    head = rig.matrix_world @ pb.head
    tip = rig.matrix_world @ (rig.pose.bones[child].head if child else pb.tail)
    cur = (tip - head).normalized()
    if cur.length < 1e-6:
        return
    r = cur.rotation_difference(Vector(d_world).normalized())
    q = rig.matrix_world.to_quaternion()
    r = q.inverted() @ r @ q
    m = pb.matrix.copy()
    loc = m.to_translation()
    m.translation = (0, 0, 0)
    new = r.to_matrix().to_4x4() @ m
    new.translation = loc
    pb.matrix = new
    bpy.context.view_layer.update()


def _key(pb, frame):
    pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler", frame=frame)


def apply(rig, who, bvh, src_t0, dur, at_frame, fps=25, holder=None, blend=0.3, char_forward=None, root_bounce=0.0,
          strength=1.0, only=None, cache={}):
    """Key mocap onto `rig` for `dur` seconds from clip time `src_t0`, starting at scene frame `at_frame`.
    Bones ease in/out of their current animation over `blend` seconds. root_bounce: copy the hips' vertical motion
    (metres, scaled) onto holder.location.z. strength < 1 mixes the mocap direction with the bone's own direction."""
    key = (str(bvh), fps)
    if key not in cache:
        cache[key] = load_clip(bvh, fps)
    frames = cache[key]
    sc = bpy.context.scene
    mp = [m for m in MAPS[who] if m[0] in rig.pose.bones and (m[1] is None or m[1] in rig.pose.bones)
          and (only is None or any(k in m[0] for k in only))]
    for t, _, _ in mp:
        pb = rig.pose.bones[t]
        if pb.rotation_mode not in ("QUATERNION",):
            pb.rotation_mode = "QUATERNION"
    i0 = int(round(src_t0 * fps))
    n = int(round(dur * fps))
    if char_forward is None:
        q = (holder.matrix_world if holder else rig.matrix_world).to_quaternion()
        char_forward = q @ Vector((0, -1, 0))
    cf = Vector((char_forward.x, char_forward.y, 0)).normalized()
    sf = facing(frames[min(i0, len(frames) - 1)])
    yaw = math.atan2(cf.y, cf.x) - math.atan2(sf.y, sf.x)
    R = Matrix.Rotation(yaw, 3, "Z")
    bf = int(round(blend * fps))
    # ease in: key the current (pre-mocap) pose just before
    sc.frame_set(max(1, at_frame - bf))
    for t, _, _ in mp:
        _key(rig.pose.bones[t], max(1, at_frame - bf))
    hip0 = frames[min(i0, len(frames) - 1)]["Hips"][0].z
    z0 = holder.location.z if holder else 0.0
    for k in range(n + 1):
        fr = frames[min(i0 + k, len(frames) - 1)]
        sc.frame_set(at_frame + k)
        for t, child, s in mp:
            h, tl = fr[s]
            d = R @ (tl - h)
            if strength < 1.0:
                pb = rig.pose.bones[t]
                cur = (rig.matrix_world @ (rig.pose.bones[child].head if child else pb.tail)) - rig.matrix_world @ pb.head
                d = cur.normalized().lerp(d.normalized(), strength)
            _aim(rig, rig.pose.bones[t], child, d)
            _key(rig.pose.bones[t], at_frame + k)
        if holder is not None and root_bounce:
            holder.location.z = z0 + max(0.0, (fr["Hips"][0].z - hip0)) * root_bounce
            holder.keyframe_insert("location", index=2, frame=at_frame + k)
    if holder is not None and root_bounce:
        holder.location.z = z0
        holder.keyframe_insert("location", index=2, frame=at_frame + n + bf)
    # ease out: drop the mocap keys after the window so the bones return to what was keyed later
    end = at_frame + n + bf
    for t, _, _ in mp:
        pb = rig.pose.bones[t]
        fcs = [fc for fc in _fcurves(rig) if fc.data_path == f'pose.bones["{t}"].rotation_quaternion']
        nxt = None
        for fc in fcs:
            for kp in fc.keyframe_points:
                if kp.co.x > end and (nxt is None or kp.co.x < nxt):
                    nxt = kp.co.x
        if nxt is None:      # nothing keyed later: settle back to the pre-mocap pose
            sc.frame_set(max(1, at_frame - bf))
            vals = tuple(pb.rotation_quaternion)
            pb.rotation_quaternion = vals
            pb.keyframe_insert("rotation_quaternion", frame=end)
    return len(mp)


def _fcurves(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return []
    act = ad.action
    if hasattr(act, "fcurves") and len(getattr(act, "fcurves", [])):
        return list(act.fcurves)
    out = []                                   # Blender 5 layered actions
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out += list(bag.fcurves)
    return out


def clear_range(rig, bones, f0, f1):
    """Remove existing rotation keys of `bones` inside [f0, f1] so mocap owns that window."""
    for fc in _fcurves(rig):
        for b in bones:
            if fc.data_path.startswith(f'pose.bones["{b}"].rotation'):
                for kp in [kp for kp in fc.keyframe_points if f0 <= kp.co.x <= f1][::-1]:
                    fc.keyframe_points.remove(kp)


CLIPS = Path(__file__).resolve().parent.parent / "downloads" / "mocap"
