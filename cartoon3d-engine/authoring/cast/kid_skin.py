"""Shared kid-skin settings: the CC head shader adds red subsurface light on the nose and eyelids and a colour overlay;
toned down here so the face reads clean and friendly. Used by kid_restyle.py and kid_face_board.py (inside Blender)."""
import bpy
from mathutils import Quaternion, Vector

SKIN = {"Subsurface Scale": 1.3, "Nose Scatter Scale": 0.25, "Upper Lid Scatter Scale": 0.2, "Inner Lid Scatter Scale": 0.3,
        "Ear Scatter Scale": 0.5, "Blend Overlay Strength": 0.35,
        "Upper Lip Roughness Mod": 0.15, "Nose Roughness Mod": 0.0}      # no wet shine above the lip / on the nose


def friendly_skin(face_tex=None):
    m = bpy.data.materials.get("Std_Skin_Head")
    if not m:
        return
    new = bpy.data.images.load(face_tex) if face_tex else None
    for n in m.node_tree.nodes:
        if new and n.type == "TEX_IMAGE" and n.image and n.image.name.startswith("Std_Skin_Head_Diffuse"):
            n.image = new
            print("FACE_TEX", new.name)
        if n.type == "GROUP" and n.node_tree and "head_shader" in n.node_tree.name:
            for k, v in SKIN.items():
                if k in n.inputs and not n.inputs[k].is_linked:
                    n.inputs[k].default_value = v
            print("SKIN_SET", n.node_tree.name)


def pose_face(name, k=1.0):
    """One of the artist's pose-library expressions at strength k (0..1), written onto the bones with no action left assigned."""
    act = bpy.data.actions.get(name)
    if act is None:
        print("NO_POSE", name)
        return False
    sc = bpy.context.scene
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    for ob in arms:
        ob.animation_data_create()
        ob.animation_data.action = None
        for pb in ob.pose.bones:
            pb.location, pb.rotation_quaternion, pb.rotation_euler, pb.scale = (0, 0, 0), (1, 0, 0, 0), (0, 0, 0), (1, 1, 1)
        ob.animation_data.action = act
        try:
            if act.slots:
                ob.animation_data.action_slot = act.slots[0]
        except Exception:  # noqa: BLE001
            pass
    sc.frame_set(int(act.frame_range[0]))
    snap = {}
    for ob in arms:
        for pb in ob.pose.bones:
            snap[(ob.name, pb.name)] = (pb.location.copy(), pb.rotation_quaternion.copy(), pb.rotation_euler.copy(), pb.scale.copy())
        ob.animation_data.action = None
    for ob in arms:
        for pb in ob.pose.bones:
            l, q, e, s = snap[(ob.name, pb.name)]
            pb.location = l * k
            pb.rotation_quaternion = Quaternion().slerp(q, k)
            pb.rotation_euler = (e[0] * k, e[1] * k, e[2] * k)
            pb.scale = Vector((1, 1, 1)).lerp(s, k)
    bpy.context.view_layer.update()
    print("POSE", name, k)
    return True
