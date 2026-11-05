"""python3 host/stage5_validate.py build/stage5/f1/host.glb
Structural glTF 2.0 checks without downloads (the Khronos gltf-validator is not installed):
GLB header/chunks, buffer view and accessor bounds, index ranges, skin joints and weights, morph target consistency, images and textures."""
import json
import struct
import sys

import numpy as np

path = sys.argv[1]; f = open(path, "rb").read(); errs, warns = [], []
magic, ver, length = struct.unpack("<4sII", f[:12])
if magic != b"glTF" or ver != 2 or length != len(f):
    errs.append(f"bad header {magic} v{ver} len {length} vs {len(f)}")
jl, jt = struct.unpack("<I4s", f[12:20]); J = json.loads(f[20:20 + jl]); o = 20 + jl
bl, bt = struct.unpack("<I4s", f[o:o + 8]); BIN = f[o + 8:o + 8 + bl]
if jt != b"JSON" or bt != b"BIN\x00":
    errs.append("bad chunk types")
CT = {5120: ("i1", 1), 5121: ("u1", 1), 5122: ("i2", 2), 5123: ("u2", 2), 5125: ("u4", 4), 5126: ("f4", 4)}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
bvs = J.get("bufferViews", [])
for i, bv in enumerate(bvs):
    if bv.get("byteOffset", 0) + bv["byteLength"] > bl:
        errs.append(f"bufferView {i} past the buffer")


def read(ai):
    a = J["accessors"][ai]; dt, sz = CT[a["componentType"]]; n = NC[a["type"]]
    if "bufferView" not in a:
        return np.zeros((a["count"], n))
    bv = bvs[a["bufferView"]]; st = bv.get("byteStride", sz * n); off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    need = off + st * (a["count"] - 1) + sz * n
    if need > bv.get("byteOffset", 0) + bv["byteLength"]:
        errs.append(f"accessor {ai} past its bufferView"); return None
    raw = np.frombuffer(BIN, dtype=np.dtype(dt).newbyteorder("<"), count=(st // sz) * (a["count"] - 1) + n, offset=off)
    arr = np.lib.stride_tricks.as_strided(raw, (a["count"], n), (st, sz)).astype(float)
    if "sparse" in a:
        sp = a["sparse"]; idt, isz = CT[sp["indices"]["componentType"]]
        ib = bvs[sp["indices"]["bufferView"]]; vb = bvs[sp["values"]["bufferView"]]
        idx = np.frombuffer(BIN, np.dtype(idt).newbyteorder("<"), sp["count"], ib.get("byteOffset", 0) + sp["indices"].get("byteOffset", 0)).astype(int)
        val = np.frombuffer(BIN, np.dtype(dt).newbyteorder("<"), sp["count"] * n, vb.get("byteOffset", 0) + sp["values"].get("byteOffset", 0)).reshape(-1, n)
        arr = arr.copy(); arr[idx] = val
    if a.get("normalized"):
        arr = arr / {"u1": 255, "u2": 65535}.get(dt, 1)
    if "min" in a and "max" in a and not a.get("normalized"):
        if (arr.min(0) < np.array(a["min"]) - 1e-4).any() or (arr.max(0) > np.array(a["max"]) + 1e-4).any():
            errs.append(f"accessor {ai} outside its min/max")
    if not np.isfinite(arr).all():
        errs.append(f"accessor {ai} has NaN/inf")
    return arr


nodes = J["nodes"]; skins = J.get("skins", []); stats = dict(meshes=0, prims=0, morphs=set(), tris=0)
for ni, nd in enumerate(nodes):
    if "mesh" not in nd:
        continue
    m = J["meshes"][nd["mesh"]]; stats["meshes"] += 1
    names = m.get("extras", {}).get("targetNames", [])
    for p in m["primitives"]:
        stats["prims"] += 1; at = p["attributes"]; P = read(at["POSITION"]); nv = len(P)
        for k, ai in at.items():
            if J["accessors"][ai]["count"] != nv:
                errs.append(f"{m['name']}: {k} count differs from POSITION")
        if "indices" in p:
            I = read(p["indices"]); stats["tris"] += len(I) // 3
            if I.max() >= nv:
                errs.append(f"{m['name']}: index out of range")
        if "JOINTS_0" in at:
            if "skin" not in nd:
                errs.append(f"{m['name']}: JOINTS_0 without a skin")
            else:
                nj = len(skins[nd["skin"]]["joints"]); Jt = read(at["JOINTS_0"]); W = read(at["WEIGHTS_0"])
                if Jt.max() >= nj:
                    errs.append(f"{m['name']}: joint index {int(Jt.max())} >= {nj}")
                s = W.sum(1)
                if np.abs(s - 1).max() > 0.01:
                    errs.append(f"{m['name']}: weights sum off by {np.abs(s - 1).max():.3f}")
        tg = p.get("targets", [])
        if tg and len(tg) != len(names):
            errs.append(f"{m['name']}: {len(tg)} targets, {len(names)} names")
        for t in tg:
            for k, ai in t.items():
                if J["accessors"][ai]["count"] != nv:
                    errs.append(f"{m['name']}: morph {k} count differs")
                read(ai)
        stats["morphs"] |= set(names)
        mi = p.get("material")
        if mi is None:
            warns.append(f"{m['name']}: no material")
for si, sk in enumerate(skins):
    if "inverseBindMatrices" in sk:
        ibm = read(sk["inverseBindMatrices"])
        if len(ibm) != len(sk["joints"]):
            errs.append(f"skin {si}: inverse bind count")
for i, im in enumerate(J.get("images", [])):
    bv = bvs[im["bufferView"]]; head = BIN[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + 4]
    ok = (im["mimeType"] == "image/png" and head == b"\x89PNG") or (im["mimeType"] == "image/jpeg" and head[:2] == b"\xff\xd8")
    if not ok:
        errs.append(f"image {i} {im.get('name')}: data does not match {im['mimeType']}")
for i, t in enumerate(J.get("textures", [])):
    if t.get("source", -1) >= len(J.get("images", [])):
        errs.append(f"texture {i}: missing image")
imgs = [(im.get("name"), im["mimeType"], bvs[im["bufferView"]]["byteLength"]) for im in J.get("images", [])]
rep = dict(file_mb=round(len(f) / 1e6, 2), images_mb=round(sum(x[2] for x in imgs) / 1e6, 2), meshes=stats["meshes"], primitives=stats["prims"], triangles=stats["tris"],
           morph_names=len(stats["morphs"]), joints=[len(s["joints"]) for s in skins], extensions=J.get("extensionsUsed", []), errors=errs, warnings=warns)
print(json.dumps(rep, indent=1))
sys.exit(1 if errs else 0)
