"""body.glb (skin, skeleton, organs) + muscles.glb (gym muscle groups, prep_muscles.py) -> body_gym.glb + anchors_gym.json. Usage: python3 build_gym_body.py [bench_dir] [--slim OUT_DIR]
--slim writes the model Rep Theory ships (assets/reptheory_3d): only the layers its clips draw (skin, skeleton, the gym muscle groups), a fraction of the full body's size."""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path
from prep_body import merge, read_glb

SLIM_KEEP = lambda n: n in ("Layer_Skin", "Layer_Skeleton") or n.startswith("Layer_M_")

def slim(bench: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True); full = bench / "body_gym.glb"; roots = {j["nodes"][i]["name"] for j in [read_glb(full)[0]] for i in j["scenes"][0]["nodes"]}
    merge([(full, {n: n for n in roots if SLIM_KEEP(n)})], out / "body_gym.glb"); shutil.copy(bench / "anchors_gym.json", out / "anchors_gym.json")
    print("slim body_gym.glb", (out / "body_gym.glb").stat().st_size // 1024, "KB ->", out)

def main(bench: Path):
    g = bench / "gym"; roots = lambda p: {j["nodes"][i]["name"]: j["nodes"][i]["name"] for j in [read_glb(p)[0]] for i in j["scenes"][j.get("scene", 0)]["nodes"]}
    body, mus = bench / "body.glb", g / "muscles.glb"
    merge([(body, {k: v for k, v in roots(body).items() if k != "Layer_Muscle"}), (mus, roots(mus))], bench / "body_gym.glb")      # the chest-only Layer_Muscle is replaced by the full groups
    A = json.loads((bench / "anchors_body.json").read_text()); A["anchors"].update({f"m_{k}": v for k, v in json.loads((g / "anchors_muscles.json").read_text())["anchors"].items()})
    (bench / "anchors_gym.json").write_text(json.dumps(A, indent=1)); print("body_gym.glb", (bench / "body_gym.glb").stat().st_size // 1024, "KB;", len(A["anchors"]), "anchors")

if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--slim"]; b = Path(a[0]) if a and "--slim" not in sys.argv[:2] else Path.home() / "HealthCinemaTools" / "bench"
    if "--slim" in sys.argv: slim(b, Path(sys.argv[sys.argv.index("--slim") + 1]))
    else: main(b)
