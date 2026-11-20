"""Host test for the prepper 'cart' format: one AI host that looks the same in every picture.

Step 1  ref_portrait   waist-up portrait on a plain backdrop (no references) -> the face/clothes anchor
Step 2  ref_fullbody, set_talking   made WITH the portrait as reference (body/clothes + the talking-head set)
Step 3  three b-roll scenes made with the portrait + full body as references (store aisle, garage, porch)
Then a contact sheet out/host_sheet.jpg to judge consistency by eye.

Our own host (not a copy of any channel): name "Dale", no cap, no camo, no flag.
Usage: python prepper_host/host_test.py [--from-step N]
"""
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT.parent
sys.path.insert(0, str(APP))
from providers.flow.engine_manager import FlowEngineManager  # noqa: E402

OUT = ROOT / "out"
LOOK = ("Photorealistic photo, shot on a full-frame camera with a 50mm lens, natural soft light, shallow depth of field, "
        "true-to-life skin texture, no text, no logos, no watermark.")
HOST = ("Dale, a weathered American man in his late fifties, short grey hair, short salt-and-pepper beard, deep smile lines, "
        "kind pale-blue eyes, broad shoulders, wearing a dark olive-green canvas work jacket open over a red-and-black buffalo "
        "check flannel shirt, worn dark jeans, brown leather work boots, no hat")

STEPS = {
    1: [(f"portrait_{i}", f"{HOST}. Waist-up portrait facing the camera, {pose}, plain warm grey studio backdrop, even light. {LOOK}")
        for i, pose in enumerate(["relaxed friendly expression", "warm half-smile", "calm serious look, arms crossed",
                                  "slight smile, hands in jacket pockets", "talking mid-sentence, one hand raised"], 1)],
    2: [("ref_fullbody", f"{HOST}. Full body from head to boots, standing straight facing the camera, plain warm grey studio "
                         f"backdrop, both feet visible. {LOOK}"),
        ("set_talking", f"{HOST}. Seated on a wooden stool, waist-up, talking to the camera with one hand raised mid-gesture, in "
                        f"a cosy home workshop: weathered barn-wood wall behind him, wooden shelves of mason jars, canned food, "
                        f"stacked water jugs and a hanging oil lantern, warm tungsten light, centred framing. {LOOK}")],
    3: [("test_store", f"{HOST}. Pushing a flat warehouse store cart loaded with rice sacks and water cases down a tall "
                       f"warehouse-club aisle with high metal shelving, looking at a shelf, bright overhead store lights. {LOOK}"),
        ("test_garage", f"{HOST}. Lifting a plastic-wrapped case of water bottles onto a metal garage shelf full of stored food "
                        f"and water, side view, afternoon light through the garage door. {LOOK}"),
        ("test_porch", f"{HOST}. Cooking a pot of rice on a small camping stove on a wooden ranch porch at dusk, steam rising, "
                       f"fields behind, warm lantern light on his face. {LOOK}")],
}
PICK = ROOT / "out" / "picked_portrait.txt"   # which portrait_N is the anchor (default portrait_1)
REFS_FOR = {1: [], 2: ["@portrait"], 3: ["@portrait", "ref_fullbody"]}


MANIFEST = OUT / "manifest.json"


def _manifest():
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def picture(key):
    if key == "@portrait":
        key = PICK.read_text().strip() if PICK.exists() else "portrait_1"
    p = _manifest().get(key)
    return Path(p) if p and Path(p).exists() else None


def run_step(client, n, base, accounts):
    refs = [picture(k) for k in REFS_FOR[n]]
    if any(r is None for r in refs):
        raise SystemExit(f"step {n}: a reference picture is missing: {REFS_FOR[n]}")
    todo = [(k, pr) for k, pr in STEPS[n] if not picture(k)]
    if not todo:
        print(f"[step {n}] all made, skipped", flush=True)
        return
    d = OUT / f"step{n}" / time.strftime("run_%H%M%S")   # own folder per run: a retry must not overwrite an earlier 001.png
    d.mkdir(parents=True, exist_ok=True)
    settings = {**base, "mediaKind": "image", "imageCount": 1, "autoDownload": True, "outputDir": str(d)}
    if refs:
        settings["referenceImages"] = [str(r) for r in refs]
    events = []
    unsub = client.subscribe(events.append)
    t0 = time.time()
    print(f"[step {n}] sending {len(todo)} pictures (refs: {[r.name for r in refs]})", flush=True)
    try:
        client.generate([pr for _, pr in todo], settings, accounts, prompt_keys=[f"prepper_host_{k}" for k, _ in todo])
        client.wait_for(lambda m: m.get("type") == "GENERATE_DONE" or bool(m.get("generateError")), timeout=2400)
    finally:
        unsub()
    m = _manifest()
    for e in events:
        if e.get("type") == "PROMPT_RESULT" and e.get("status") == "done" and e.get("path") and isinstance(e.get("index"), int):
            m[todo[e["index"]][0]] = e["path"]
    OUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=1))
    for k, _ in todo:
        print(f"[step {n}] {k}: {'OK' if picture(k) else 'NO PICTURE'}", flush=True)
    errs = {str(e.get("generateError") or e.get("error"))[:200] for e in events if e.get("generateError") or e.get("error")}
    if errs:
        print(f"[step {n}] errors: {errs}", flush=True)
    print(f"[step {n}] {time.time() - t0:.0f}s", flush=True)
    if any(not picture(k) for k, _ in todo):
        raise SystemExit(f"stopped: step {n} incomplete")


def sheet():
    keys = [k for n in (1, 2, 3) for k, _ in STEPS[n]]
    pics = [(k, picture(k)) for k in keys if picture(k)]
    args, filt = [], []
    for i, (k, p) in enumerate(pics):
        args += ["-i", str(p)]
        filt.append(f"[{i}]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2[v{i}]")
    cols = 3
    layout = "|".join(f"{(i % cols) * 640}_{(i // cols) * 360}" for i in range(len(pics)))
    fc = ";".join(filt) + ";" + "".join(f"[v{i}]" for i in range(len(pics))) + f"xstack=inputs={len(pics)}:layout={layout}:fill=black"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", fc, "-frames:v", "1", str(OUT / "host_sheet.jpg")], check=True)
    print("SHEET", OUT / "host_sheet.jpg", flush=True)


def main():
    start = int(sys.argv[sys.argv.index("--from-step") + 1]) if "--from-step" in sys.argv else 1
    s = json.loads((APP / "settings.json").read_text())
    mode = "agent" if s.get("flow_agent_images") else ("ui" if s.get("flow_ui_mode", True) else "rpc")
    fs = s.get("flow_settings", {})
    base = {"model": fs.get("model"), "aspectRatio": fs.get("aspectRatio", "IMAGE_ASPECT_RATIO_LANDSCAPE"), "generationMode": mode}
    prof = next(p for p in s["video_profiles"] if p["id"] == s.get("default_video_profile_id", "default"))
    accounts = prof["account_ids"] if mode == "agent" else None
    print("mode", mode, "model", base["model"], flush=True)
    client = FlowEngineManager(log=lambda m: None).ensure_running()
    time.sleep(1.5)
    stop = int(sys.argv[sys.argv.index("--to-step") + 1]) if "--to-step" in sys.argv else 3
    for n in (1, 2, 3):
        if start <= n <= stop:
            run_step(client, n, base, accounts)
    sheet()
    client.close()


if __name__ == "__main__":
    main()
