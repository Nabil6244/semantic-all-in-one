"""Textures used only by the Hybrid concept (python3 host/make_concept_tex.py). Separate names: existing textures are not touched."""
import os
import numpy as np
from PIL import Image
from make_textures import OUT, blur1d, normal_from, save, srgb

rng = np.random.default_rng(21)


def eye():
    H = 768; yy, xx = np.mgrid[0:H, 0:H].astype(float)
    dx, dy = xx / H - 0.5, yy / H - 0.5; r = np.hypot(dx, dy); th = np.arctan2(dy, dx)
    a = np.ones((H, H, 3)) * srgb("#fdfaf5")
    R = 0.31; t = np.clip(r / R, 0, 1)[..., None]
    fib = (0.5 + 0.5 * np.sin(th * 58 + 3 * np.sin(th * 9)))[..., None]
    fib2 = (0.5 + 0.5 * np.sin(th * 23 + 1.7))[..., None]
    col = srgb("#3d1f0e") * (1 - t) ** 1.2 + srgb("#a8652a") * (1 - (1 - t) ** 1.2)
    col = col * (0.9 + 0.14 * fib + 0.08 * fib2)
    glow = np.clip(1 - np.hypot(dx + 0.02, dy - 0.13) / 0.24, 0, 1)[..., None] ** 1.5
    col = col + srgb("#f0a850") * glow * 0.55 * (t > 0.42)
    ring = np.clip((t - 0.8) / 0.2, 0, 1) ** 1.6
    col = col * (1 - ring) + srgb("#1d0f08") * ring
    pupil = np.clip((0.15 - r) / 0.007, 0, 1)[..., None]
    col = col * (1 - pupil) + srgb("#070403") * pupil
    m = np.clip((R - r) / 0.006, 0, 1)[..., None]
    shade = 1 - 0.34 * np.clip((-0.04 - dy) / 0.26, 0, 1)[..., None] ** 1.4     # lid shadow on the iris only
    a = a * (1 - m) + col * shade * m
    for cx, cy, rad in ((-0.1, -0.12, 0.064), (0.115, 0.115, 0.028)):
        h = np.clip((rad - np.hypot(dx - cx, dy - cy)) / 0.007, 0, 1)[..., None]
        a = a * (1 - h) + h
    save(a, "eye_h.png")


def hair():
    S = 1024
    fine = blur1d(blur1d(rng.standard_normal((S, S)), 1.6, 1), 170, 0); fine /= fine.std()
    broad = blur1d(blur1d(rng.standard_normal((S, S)), 22, 1), 300, 0); broad /= broad.std()
    h = 0.45 * fine + 0.75 * broad
    t = np.clip(0.5 + h * 0.15, 0, 1)[..., None]
    save(srgb("#2c180d") * (1 - t) + srgb("#57331c") * t, "hair_h.png")
    save(normal_from(0.5 * fine + 0.4 * broad, 0.22), "hair_h_n.png")


eye(); hair(); print("ok")
