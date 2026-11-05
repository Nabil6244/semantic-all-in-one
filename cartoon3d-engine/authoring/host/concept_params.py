"""Three deliberately different head designs. Metres; x right, -y towards camera, z up."""
LID = dict(tilt=0.1, v0=-0.02, up=0.52, down=0.46, a=0.7, u0=0.0, pow=2.4, thick=0.0013, blend=0.0045, crease=0.1)
SMILE = dict(lift=0.0135, wide=0.1, back=0.005, open_up=0.0042, open_down=0.0075, jaw=0.004, cheek=0.0052, lid=0.0022, teeth_show=0.0006)
HAIRLINE = dict(line_az=[0, 18, 45, 70, 92, 112, 140, 180], line_el=[33, 32, 25, 6, -20, -30, -42, -52])


def combed(az_list, anchor, el_line, r0, r1, off0=0.009, off1=0.016):
    """Locks starting along the hairline and sweeping back to the ponytail."""
    import numpy as np
    out = []
    for az in az_list:
        e = float(np.interp(abs(az), el_line["line_az"], el_line["line_el"]))
        mid_az = az * 1.1 if abs(az) < 60 else az * 1.25
        out.append(([(az, e + 3, off0), (mid_az, e + 24, off1 - 0.002), (anchor[0] if az > 0 else -anchor[0], anchor[1], off1 - 0.012)], r0, r1))
    return out


A_ANCHOR = (178, 6)
CONCEPTS = {
    # A: round and gentle. Wide soft face, full low cheeks, round eyes, button nose, small sweet mouth.
    "A": dict(
        head_c=(0, -0.03, 1.52), cran_c=(0, -0.018, 1.545), cran_r=(0.121, 0.13, 0.118), face_c=(0, -0.055, 1.462), face_r=(0.112, 0.102, 0.098),
        cheek_c=(0.06, -0.112, 1.448), cheek_r=(0.046, 0.046, 0.044), cheek_k=0.04, chin_c=(0, -0.11, 1.39), chin_r=(0.05, 0.046, 0.036), chin_k=0.05, drop=0.036,
        neck_a=(0, -0.012, 1.24), neck_b=(0, -0.03, 1.44), neck_r=0.043,
        eye_z=1.492, eye_x=0.055, eye_y=-0.107, eye_r=0.0385, iris_k=1.08, gaze_in=0.0,
        lid=dict(LID, tilt=0.06, up=0.64, down=0.56, a=0.84, pow=2.2),
        nose=dict(root=(0, -0.148, 1.482), tip=(0, -0.181, 1.449), bridge=0.0075, tip_r=(0.0135, 0.0125, 0.0115), wing=0.0135, wing_r=0.0075),
        mouth=dict(z=1.4135, y=-0.163, yc=8.5, w=0.032, curve=0.0048, up=0.0044, low=0.0062, bow=0.3),
        ear_c=(0.121, -0.012, 1.468), ear_r=(0.011, 0.024, 0.036),
        skin="#fbcfae", skin_rough=0.48, blush=0.5, blush_c="#f6917f", lip_c="#ec7a6d", lid_c="#eeb99b",
        smile=dict(SMILE), iris_note="round",
        brow=dict(x0=-0.03, x1=0.047, z=0.021, arch=0.0065, peak=0.85, drop=0.008, th=0.0066),
        lash=dict(w0=0.05, w1=0.05, wing=0.05),
        hair_c=(0, -0.018, 1.545), hair_r=(0.121, 0.13, 0.118),
        hair=dict(HAIRLINE, cap_off=0.014, lock_k=0.016, anchor=A_ANCHOR,
                  locks=combed([-105, -82, -60, -40, -20, 62, 84, 106], A_ANCHOR, HAIRLINE, 0.021, 0.018)
                  + [([(14, 62, 0.002), (42, 36, 0.008), (78, 8, 0.008), (112, -14, 0.006), (178, 6, -0.002)], 0.026, 0.016),      # soft sweep from the part
                     ([(14, 62, 0.002), (-12, 42, 0.01), (-52, 22, 0.01), (-95, -6, 0.006), (-178, 6, -0.002)], 0.03, 0.016),
                     ([(14, 62, 0.003), (2, 54, 0.008), (-30, 42, 0.01), (-80, 30, 0.008), (-178, 6, -0.002)], 0.024, 0.016)],
                  band=dict(front=(0, 54), back=(180, -34), w=0.034),
                  tail=dict(path=[(0, 0, 0), (0, 0.055, 0.006), (0.006, 0.098, -0.04), (0.014, 0.112, -0.125), (0.022, 0.1, -0.22), (0.036, 0.082, -0.3), (0.05, 0.068, -0.36)],
                            prof_s=[0, 0.08, 0.3, 0.65, 0.9, 1], prof_r=[0.021, 0.025, 0.046, 0.046, 0.024, 0.005], strands=6, twist=3.2, strand_r=0.55, k=0.008))),
    # B: lively and readable. Heart-shaped face, large upturned eyes, bold brows, wide smile, high bouncy ponytail.
    "B": dict(
        head_c=(0, -0.03, 1.525), cran_c=(0, -0.016, 1.553), cran_r=(0.126, 0.132, 0.12), face_c=(0, -0.056, 1.47), face_r=(0.108, 0.1, 0.098),
        cheek_c=(0.07, -0.104, 1.456), cheek_r=(0.044, 0.044, 0.042), cheek_k=0.03, chin_c=(0, -0.118, 1.386), chin_r=(0.036, 0.038, 0.034), chin_k=0.05, drop=0.04,
        neck_a=(0, -0.012, 1.24), neck_b=(0, -0.03, 1.44), neck_r=0.04,
        eye_z=1.5, eye_x=0.058, eye_y=-0.104, eye_r=0.0425, iris_k=1.0, gaze_in=0.0,
        lid=dict(LID, tilt=0.2, up=0.62, down=0.47, a=0.86, pow=2.6, v0=-0.03),
        nose=dict(root=(0, -0.146, 1.484), tip=(0, -0.183, 1.453), bridge=0.0064, tip_r=(0.0105, 0.0115, 0.0098), wing=0.0108, wing_r=0.0058),
        mouth=dict(z=1.4145, y=-0.1625, yc=6.2, w=0.0445, curve=0.0078, up=0.0042, low=0.0058, bow=0.4),
        ear_c=(0.124, -0.008, 1.478), ear_r=(0.011, 0.022, 0.033),
        skin="#f9cdae", skin_rough=0.46, blush=0.36, blush_c="#f58872", lip_c="#e7685f", lid_c="#e9ae8e",
        smile=dict(SMILE, lift=0.0165, wide=0.11, open_up=0.0055, open_down=0.0105, cheek=0.0065),
        brow=dict(x0=-0.034, x1=0.056, z=0.0245, arch=0.0105, peak=0.7, drop=0.016, th=0.0082),
        lash=dict(w0=0.06, w1=0.08, wing=0.09),
        hair_c=(0, -0.016, 1.553), hair_r=(0.126, 0.132, 0.12),
        hair=dict(HAIRLINE, line_el=[37, 36, 28, 8, -18, -26, -38, -46], cap_off=0.013, lock_k=0.014, anchor=(180, 42),
                  locks=combed([-108, -88, -66, -44, -22, 0, 22, 44, 66, 88, 108], (180, 42), HAIRLINE, 0.018, 0.016, 0.006, 0.014),
                  band=dict(front=(0, 54), back=(180, -24), w=0.04),
                  tail=dict(path=[(0, 0, 0), (0, 0.06, 0.05), (0.002, 0.135, 0.045), (0.01, 0.2, -0.04), (0.02, 0.215, -0.15), (0.04, 0.18, -0.25), (0.075, 0.13, -0.3)],
                            prof_s=[0, 0.07, 0.3, 0.62, 0.88, 1], prof_r=[0.02, 0.026, 0.056, 0.058, 0.03, 0.005], strands=7, twist=4.4, strand_r=0.52, k=0.008))),
    # C: refined film character. Longer oval face, cheekbones, defined nose bridge, almond eyes, fuller lips, side part, low elegant tail.
    "C": dict(
        head_c=(0, -0.03, 1.52), cran_c=(0, -0.016, 1.553), cran_r=(0.112, 0.126, 0.112), face_c=(0, -0.05, 1.465), face_r=(0.099, 0.1, 0.112),
        cheek_c=(0.06, -0.1, 1.432), cheek_r=(0.038, 0.04, 0.042), cheek_k=0.03, bone=(0.07, -0.098, 1.47, (0.03, 0.028, 0.018)),
        chin_c=(0, -0.114, 1.366), chin_r=(0.034, 0.034, 0.03), chin_k=0.045, drop=0.03,
        neck_a=(0, -0.012, 1.24), neck_b=(0, -0.032, 1.42), neck_r=0.038,
        eye_z=1.497, eye_x=0.052, eye_y=-0.1, eye_r=0.0365, iris_k=1.02, gaze_in=0.0,
        lid=dict(LID, tilt=0.16, up=0.55, down=0.42, a=0.88, pow=2.9, u0=0.04, thick=0.0012, crease=0.09),
        nose=dict(root=(0, -0.142, 1.49), tip=(0, -0.181, 1.446), bridge=0.0068, tip_r=(0.0102, 0.0118, 0.0095), wing=0.012, wing_r=0.0058),
        mouth=dict(z=1.4055, y=-0.1575, yc=7.0, w=0.0355, curve=0.0052, up=0.0047, low=0.0066, bow=0.45),
        ear_c=(0.11, -0.01, 1.46), ear_r=(0.0105, 0.023, 0.036),
        skin="#f7cfb3", skin_rough=0.44, blush=0.28, blush_c="#ef8f7c", lip_c="#d9625e", lid_c="#e2a98c",
        smile=dict(SMILE, lift=0.0125, wide=0.1, open_up=0.0044, open_down=0.0078, cheek=0.0046),
        brow=dict(x0=-0.03, x1=0.052, z=0.0205, arch=0.0072, peak=0.62, drop=0.0125, th=0.0048),
        lash=dict(w0=0.055, w1=0.07, wing=0.08),
        hair_c=(0, -0.016, 1.553), hair_r=(0.112, 0.126, 0.112),
        hair=dict(HAIRLINE, line_el=[30, 29, 23, 5, -22, -32, -44, -54], cap_off=0.012, lock_k=0.012, anchor=(172, -14),
                  locks=combed([-106, -80, 70, 96], (172, -14), HAIRLINE, 0.018, 0.016, 0.006, 0.014)
                  + [([(-26, 60, 0.002), (6, 46, 0.01), (46, 24, 0.01), (84, -2, 0.008), (172, -14, -0.002)], 0.028, 0.016),     # strong side part, sweeping across
                     ([(-26, 60, 0.002), (20, 54, 0.01), (70, 28, 0.009), (120, -4, 0.006), (172, -14, -0.002)], 0.026, 0.016),
                     ([(-26, 60, 0.002), (-4, 58, 0.009), (40, 52, 0.009), (100, 28, 0.007), (172, -14, -0.002)], 0.024, 0.016),
                     ([(-26, 60, 0.002), (-52, 36, 0.009), (-84, 6, 0.008), (-118, -14, 0.005), (-172, -14, -0.002)], 0.026, 0.016),
                     ([(-26, 60, 0.002), (-44, 54, 0.008), (-90, 34, 0.007), (-172, -14, -0.002)], 0.024, 0.016)],
                  band=dict(front=(0, 58), back=(180, -40), w=0.03),
                  tail=dict(path=[(0, 0, 0), (0.002, 0.045, -0.012), (0.012, 0.075, -0.07), (0.028, 0.08, -0.16), (0.05, 0.068, -0.25), (0.075, 0.05, -0.32), (0.09, 0.03, -0.37)],
                            prof_s=[0, 0.08, 0.3, 0.65, 0.9, 1], prof_r=[0.018, 0.021, 0.037, 0.036, 0.018, 0.004], strands=6, twist=3.8, strand_r=0.55, k=0.007))),
}


# Hybrid: A's face and gentleness, B's eyes, brows and wider smile (balanced), C's clean side-part hair flow, a refined natural ponytail.
_A, _B, _C = CONCEPTS["A"], CONCEPTS["B"], CONCEPTS["C"]
_LINE = dict(line_az=[0, 18, 45, 70, 92, 112, 140, 180], line_el=[31, 30, 24, 6, -20, -30, -42, -54])
_ANCH = (176, -6)
CONCEPTS["H"] = dict(_A, c2=True, relax=5, full_views=True, voxel=0.0011, hvoxel=0.0015, eye_tex="eye_h.png", hair_tex="hair_h.png", hair_n="hair_h_n.png", hair_rough=0.4, hair_shadow=0.34,
    skin="#fbceab", blush=0.46, lip_c="#e96f62",
    eye_z=1.494, eye_x=0.0565, eye_y=-0.105, eye_r=0.0405, iris_k=1.03, gaze_in=-0.13, slit=0.0009, slit_w=0.97,
    lid=dict(LID, tilt=0.13, up=0.62, down=0.5, a=0.85, pow=2.4, v0=-0.025, thick=0.0013, crease=0.1, blend=0.0095),
    lash=dict(w0=0.05, w1=0.075, wing=0.075, paint=0.0019),
    brow=dict(x0=-0.032, x1=0.049, z=0.0225, arch=0.0085, peak=0.72, drop=0.0125, th=0.0072),
    nose=dict(root=(0, -0.146, 1.484), tip=(0, -0.1745, 1.451), bridge=0.0068, tip_r=(0.0125, 0.0118, 0.0112), wing=0.0124, wing_r=0.0068),
    mouth=dict(z=1.4135, y=-0.1625, yc=7.4, w=0.0395, curve=0.0066, up=0.0043, low=0.006, bow=0.34),
    smile=dict(SMILE, lift=0.0155, wide=0.11, open_up=0.0066, open_down=0.0098, cheek=0.0062, teeth_show=-0.0012),
    ear_r=(0.0105, 0.022, 0.033),
    hair=dict(_LINE, cap_off=0.012, lock_k=0.013, anchor=_ANCH, band_seat=True, band_lift=0.03,
        locks=combed([-106, -82, 72, 98], _ANCH, _LINE, 0.018, 0.016, 0.006, 0.014)
        + [([(-24, 60, -0.004), (6, 46, 0.006), (46, 24, 0.008), (84, -2, 0.008), (176, -6, -0.002)], 0.024, 0.016),
           ([(-24, 60, -0.004), (20, 54, 0.004), (70, 28, 0.007), (120, -4, 0.006), (176, -6, -0.002)], 0.022, 0.016),
           ([(-24, 60, -0.004), (-4, 58, 0.002), (40, 52, 0.004), (100, 28, 0.006), (176, -6, -0.002)], 0.02, 0.016),
           ([(-24, 60, -0.004), (-52, 36, 0.006), (-84, 6, 0.007), (-118, -14, 0.005), (-176, -6, -0.002)], 0.022, 0.016),
           ([(-24, 60, -0.004), (-44, 54, 0.002), (-90, 34, 0.006), (-176, -6, -0.002)], 0.02, 0.016)],
        band=dict(front=(0, 57), back=(180, -38), w=0.032),
        tail=dict(path=[(0, 0, 0), (0.001, 0.05, -0.002), (0.006, 0.09, -0.05), (0.016, 0.104, -0.13), (0.03, 0.096, -0.22), (0.052, 0.074, -0.3), (0.08, 0.062, -0.345)],
                  prof_s=[0, 0.07, 0.28, 0.6, 0.86, 1], prof_r=[0.019, 0.023, 0.042, 0.043, 0.022, 0.004], strands=8, twist=3.6, strand_r=0.46, k=0.011)))


# Round 2 of the Hybrid: bigger smile, shaped lids, more hair, fuller profile. Same identity.
_H = CONCEPTS["H"]
_LINE2 = dict(line_az=[0, 18, 45, 70, 92, 112, 140, 180], line_el=[27, 26, 21, 5, -20, -30, -42, -54])
_LOCK = [(-24, 62, 0.004)]


def _sweep(way, r0=0.021, r1=0.015):
    return (way, r0, r1)


CONCEPTS["H"] = dict(_H,
    muzzle=((0, -0.116, 1.423), (0.05, 0.036, 0.036)), ball_off=-0.0002,
    chin_c=(0, -0.118, 1.388), chin_r=(0.05, 0.046, 0.036),
    ear_c=(0.121, -0.012, 1.482), ear_r=(0.0098, 0.0205, 0.031),
    lid=dict(_H["lid"], crease=0.11, fold=0.0011),
    nose=dict(_H["nose"], tip=(0, -0.1785, 1.452), root=(0, -0.149, 1.486)),
    mouth=dict(_H["mouth"], y=-0.1675, up=0.0049, low=0.0068, philtrum=False),
    smile=dict(_H["smile"], lift=0.0195, wide=0.15, back=0.006, open_up=0.0098, open_down=0.0135, cheek=0.0088, lid=0.0036, jaw=0.0055, teeth_root=0.0125, teeth_follow=0.62, teeth_wide=1.0),
    hair=dict(_H["hair"], line_az=_LINE2["line_az"], line_el=_LINE2["line_el"], cap_off=0.0165, lock_k=0.0098,
        locks=combed([-108, -86, -64, 62, 80, 100], _ANCH, _LINE2, 0.017, 0.014, 0.01, 0.019)
        + [_sweep([(-24, 62, 0.002), (-2, 44, 0.012), (34, 22, 0.014), (72, -3, 0.012), (116, -14, 0.008), (176, -6, 0.002)], 0.024, 0.016),
           _sweep([(-24, 62, 0.004), (10, 50, 0.014), (50, 32, 0.016), (92, 8, 0.012), (176, -6, 0.002)]),
           _sweep([(-24, 62, 0.004), (22, 58, 0.015), (66, 42, 0.016), (110, 18, 0.011), (176, -6, 0.002)]),
           _sweep([(-24, 62, 0.004), (34, 64, 0.014), (84, 50, 0.014), (130, 26, 0.009), (176, -6, 0.002)], 0.019),
           _sweep([(-24, 62, 0.002), (-46, 40, 0.014), (-74, 12, 0.013), (-112, -12, 0.009), (-176, -6, 0.002)], 0.023, 0.016),
           _sweep([(-24, 62, 0.004), (-52, 52, 0.015), (-90, 30, 0.012), (-130, 8, 0.008), (-176, -6, 0.002)]),
           _sweep([(-24, 62, 0.004), (-50, 66, 0.013), (-104, 48, 0.012), (-140, 22, 0.008), (-176, -6, 0.002)], 0.019)],
        band=dict(front=(0, 54), back=(180, -38), w=0.032)))
