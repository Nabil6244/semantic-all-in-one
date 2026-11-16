"""Acts a realistic diorama actor (sets/actor.py) can do. Pure Python: the plan checker reads it without Blender.

name: (default seconds, tool in hand, about)
"""
ACTS = {
    "idle":      (2.0, None, "stand, breathing"),
    "walk":      (1.6, None, "walk; params to=[dx, dy] metres (faces where it goes), speed m/s (1.3)"),
    "carry":     (1.6, "crate", "carry a crate in both arms; params to=[dx, dy] walks while carrying"),
    "dig":       (2.4, "shovel", "dig with a shovel, bent over, pushing and lifting"),
    "hammer":    (1.6, "hammer", "hammer at chest height (a wall, a board)"),
    "drill":     (1.6, "drill", "hold a drill to the wall at chest height, little shakes"),
    "climb":     (2.0, None, "climb a ladder or rope; params up=dz metres (the actor rises)"),
    "crouch":    (1.2, None, "crouch down to look at or fix something low"),
    "point":     (1.2, None, "point; params dir=[x, y, z] (default forward-right)"),
    "look":      (1.2, None, "turn the head; params yaw degrees (+ = his left), pitch degrees (+ = up)"),
    "look_down": (1.2, None, "look down (into a hole, at the water)"),
    "explain":   (1.6, None, "talk with both hands"),
    "nod":       (0.8, None, "nod"),
    "cheer":     (1.2, None, "both arms up"),
    "shock":     (1.0, None, "jump back a little, hands up"),
    "wipe":      (1.4, None, "wipe the forehead (hard work done)"),
}
ACTOR_KEYS = ("actor",)  # a cast entry with "actor" is a realistic actor, not a 2D puppet
