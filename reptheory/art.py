"""The art set and how it is generated: one original character ("Rep", a lean beginner) plus props and anatomy, all in one hand-drawn manga style, generated ONCE through the
app's existing Flow image workflow (providers.flow.FlowProvider) and then reused by every video. Same shape as health_cinema/bodymap_flow.py:

    python3 -m reptheory.art                      # dry run: lists what is missing and the prompts (no engine, no credit)
    python3 -m reptheory.art --go [--only id ...] # generate exactly one image per missing id; an id already in the library is never generated again

Nothing is generated per video. Add an entry to ART to grow the library."""
from __future__ import annotations
import argparse, json, sys, tempfile, time
from pathlib import Path

from . import library as L

CHARACTER = ("an original manga-style young man: lean, skinny beginner build, short messy dark hair with a swept fringe and strong white rim-light highlights, narrow face, bare torso, "
             "plain charcoal-grey training shorts with an orange waistband, barefoot, sharp black-ink linework with soft grey cel shading")
STYLE = ("Hand-drawn manga illustration, clean line art, restrained palette of greys and white with a single orange accent, solid pure black background (#000000), no text, no letters, "
         "no numbers, no logos, no watermark, no border, no other people, subject fully inside the frame with space around it")
RIVAL = ("a big heavily muscled man with a buzz cut, huge arms and chest, wearing a plain grey tank top, drawn in the same manga ink style (the bigger, stronger-looking opponent)")
TRADESMAN = ("a weathered tradesman in his fifties: stocky and wiry rather than muscular, thick calloused hands and forearms, short grey stubble, plain work shirt with "
             "rolled-up sleeves and work trousers, drawn in the same manga ink style")      # the mechanic / farmer / bricklayer the narration talks about (render 054 drew the trainee or the bodybuilder)
SCENE_STYLE = ("Hand-drawn manga ink illustration, greyscale with white highlights, solid pure black background (#000000), no text, no letters, no numbers, no logos, no watermark, no border. "
               "The only colours are the trainee's orange waistband and, when a muscle, tendon or body part is the point of the scene, that part painted glowing red over the ink. "
               "Compose the subject in one side of the frame (about 60%) and leave the other side empty black for on-screen text")      # docs/rep_theory/STUDY_tendons_arm_wrestling.md section 2
INK_ANATOMY = ("Manga ink anatomical sketch, greyscale, the muscles and tendons the sentence names painted glowing red, solid pure black background (#000000), no text, no letters, no numbers, "
               "no logos, no watermark, the body part on one side of the frame with the other side empty black")
REAL_STYLE = "Realistic detailed illustration with studio lighting, solid pure black background (#000000), no text, no letters, no numbers, no brand logos, no watermark, subject fully inside the frame"

CAT_STYLE = ("Soft hand-drawn storybook illustration of a domestic cat, clean ink line art with warm watercolour shading, a single orange accent, plain solid pure white background (#FFFFFF), "
             "no text, no letters, no numbers, no logos, no watermark, no border, no people unless the sentence names them (then only hands or a friendly owner), "
             "the subject in one side of the frame (about 60%) with the other side empty white for on-screen text")      # the cat niche (theme.THEME == "cat")

SURVIVAL_STYLE = ("Hand-drawn field-guide illustration, confident black ink line art with loose muted watercolour washes (earth browns, sage, rust, pale sky blue), "
                  "plain solid pure white paper background (#FFFFFF), frontier and homestead feel, the detail the sentence is about (a cut, a knot, a mark, a tool) drawn large, "
                  "high-contrast and unmistakable as on a field-guide plate, no text, no letters, no numbers, no logos, no watermark, no border, "
                  "the subject in one side of the frame (about 60%) with the other side empty white for on-screen text")      # Survival theme (theme.THEME == "survival")

ELDER_STYLE = ("Soft-colour illustration with gentle watercolour shading and clean soft outlines, calm pastel palette of teal, sage, warm peach and navy, plain solid pure white "
               "background (#FFFFFF), warm and respectful, no text, no letters, no numbers, no logos, no watermark, no border, the subject in one side of the frame (about 60%) with "
               "the other side empty white for on-screen text")      # Elder Health Theory (theme.THEME == "elder"): older people in daily life
ELDER_ORGAN_STYLE = ("Soft-colour medical illustration in the style of a friendly patient leaflet: the organ drawn clearly and accurately with gentle watercolour shading, soft pink, "
                     "red and peach tones with teal highlights on the part that matters, plain solid pure white background (#FFFFFF), not gory, no blood, no text, no letters, "
                     "no numbers, no labels, no logos, no watermark, the organ on one side of the frame (about 60%) with the other side empty white for on-screen text")

JUNG_STYLE = ("Oil painting in the manner of an early 20th-century old-master portrait: rich umber, sepia and ochre palette, visible brushstrokes on canvas, dramatic chiaroscuro "
              "lighting, a dark warm background, no text, no letters, no numbers, no logos, no watermark, no border, the subject in one side of the frame (about 60%) with the other "
              "side dark and calm for on-screen text")      # Carl Jung Theory (theme.THEME == "jung"): every picture one painted film
JUNG_SHEET = ("Carl Jung exactly as in the reference images: an elderly Swiss psychiatrist with swept-back white hair, round wire-rimmed glasses and a white moustache, "
              "in a dark three-piece suit")      # the verbatim character sentence, used with the reference images (story_character.py pattern)
JUNG_REFS_FILE = Path(__file__).resolve().parent.parent / "assets" / "jung" / "refs.json"

def jung_refs() -> list:
    """The reference images for every picture Jung is in (at most 3, Flow's limit): assets/jung/refs.json "use", else the first 3 pictures in assets/jung/refs. [] when none."""
    folder = JUNG_REFS_FILE.parent / "refs"
    try: names = json.loads(JUNG_REFS_FILE.read_text(encoding="utf-8")).get("use") or []
    except Exception: names = []
    paths = [folder / n for n in names] if names else sorted(p for p in folder.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    return [str(p) for p in paths if p.is_file()][:3]

def flow_ref_copies(paths: list) -> list:
    """The reference images under short names (jungref1_<hash>.jpg) for Flow: its asset picker cuts long file names, so a picture uploaded as a 40-character
    name could not be found again to attach (Carl Jung Theory test 2026-11-08: "not in Flow's asset picker"). Same content, same name: never uploaded twice."""
    import hashlib, shutil, tempfile
    out, folder = [], Path(tempfile.gettempdir()) / "rt_flow_refs"; folder.mkdir(parents=True, exist_ok=True)
    for n, src in enumerate(paths, 1):
        src = Path(src); h = hashlib.sha1(src.read_bytes()).hexdigest()[:8]; dst = folder / f"jungref{n}_{h}{src.suffix.lower()}"
        if not dst.is_file(): shutil.copyfile(src, dst)
        out.append(str(dst))
    return out

# id -> (kind, subject sentence, style)
ART = {
    "rep_stand_v1": ("character", f"Full-body front view of {CHARACTER}, standing relaxed, arms hanging at his sides, calm focused expression", STYLE),
    "rep_hang_v1": ("character", f"Full-body front view of {CHARACTER}, hanging from a plain horizontal steel pull-up bar that is fully visible across the top of the picture, arms straight overhead, gripping the bar", STYLE),
    # Step 5: the pose library (one character, made once, reused by every video; body-region maps per pose in poses.py)
    **{f"rep_{k}_v1": ("character", f"Full-body picture of {CHARACTER}. Pose: {v}, the whole body visible", STYLE) for k, v in {
        "side": "side view (facing right)", "point": "front view, pointing straight at the viewer with one hand, explaining, friendly confident expression",
        "think": "front view, standing with one hand on his chin, thinking, slightly puzzled expression",
        "flex": "front view, flexing both biceps with a proud grin", "tired": "side view (facing right), bent over with his hands on his knees, exhausted and sweating, breathing hard",
        "pushup_top": "side view (facing right) at the top of a push-up on the floor, arms straight, body in one straight line", "pushup_bottom": "side view (facing right) at the bottom of a push-up, chest just above the floor, elbows bent",
        "squat": "side view (facing right) at the bottom of a bodyweight squat, thighs parallel to the floor, arms reaching forward", "lunge": "side view (facing right) in a deep forward lunge, front knee bent at ninety degrees, back knee near the floor",
        "plank": "side view (facing right) holding a forearm plank on the floor, body in one straight line", "side_plank": "front view holding a side plank on one forearm, hips lifted, body straight",
        "bridge": "side view (facing right) lying on his back doing a glute bridge, feet flat, hips lifted high", "pullup_top": "front view at the top of a pull-up, chin above a plain steel bar that is fully visible across the picture",
        "row": "side view (facing right) in a bent-over row, back flat, pulling one dumbbell to his hip", "hinge": "side view (facing right) in a hip hinge holding a barbell just below his knees, back flat, hips pushed back",
        "press": "front view pressing two dumbbells straight overhead, arms locked", "curl": "front view curling two dumbbells, elbows at his sides, forearms up",
        "walk": "side view (facing right) walking briskly, mid-stride", "run": "side view (facing right) running, mid-stride, arms pumping",
        "hamstring_stretch": "side view (facing right) sitting on the floor with legs straight, leaning forward to reach his toes", "hip_stretch": "side view (facing right) in a kneeling hip flexor stretch, one knee on the floor, hips pushed forward",
        "wall_sit": "side view (facing right) in a wall sit, back flat against a plain wall, thighs parallel to the floor", "calf_raise": "side view (facing right) standing high on his toes in a calf raise",
        "eat": "side view (facing right) sitting at a plain table eating a plate of chicken, rice and vegetables with a fork", "drink": "front view drinking from a clear water bottle",
        "sleep": "side view asleep on his side in a plain bed with a pillow and blanket, peaceful", "scale": "front view standing on a plain bathroom scale, looking down at it",
        "bench_rest": "side view (facing right) sitting on a plain gym bench resting between sets, a towel over his shoulder"}.items()},
    "prop_bottle_2l_v1": ("prop", "A full 2 litre clear plastic water bottle with a blue screw cap and a plain blank label, standing upright, centred", REAL_STYLE),
    "anat_forearm_v1": ("anatomy", "Both human forearms and hands in front (palm-up) view, drawn as a muscle-anatomy illustration with the flexor muscles and tendons visible, forearms upright and symmetrical, hands open", REAL_STYLE),
}

def prompt_for(art_id: str) -> str:
    kind, subject, style = ART[art_id]; return f"{subject.strip().rstrip('.')}. {style}."

def generate(ids=None, account_ids=None, mode: str = "ui", log=print, settings: dict | None = None) -> list:
    out, todo = [], []
    for i in (ids or list(ART)):
        hit = L.find(i)
        if hit: out.append({"id": i, "status": "reused", "path": hit["path"]}); log(f"[REP THEORY ART] {i}: already in the library, reused")
        else: todo.append(i)
    if not todo: return out
    from providers.base import SceneRow
    from providers.flow.engine_manager import FlowEngineManager
    from providers.flow.provider import FlowProvider
    mgr = FlowEngineManager(log=log)
    fs = {"model": "GEM_PIX_2", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE", "generationMode": mode}; fs.update(settings or {})
    prov = FlowProvider(mgr, media_kind="image", account_ids=account_ids, flow_settings=fs)
    rows = [SceneRow(scene_number=str(n + 1), script_segment=ART[i][1], asset_type="image", prompt=prompt_for(i)) for n, i in enumerate(todo)]
    log(f"[REP THEORY ART] requesting {len(rows)} Flow image(s) (mode {mode})")
    res = prov.resolve_batch(rows, Path(tempfile.mkdtemp(prefix="rt_art_")), log=log)
    for n, i in enumerate(todo):
        r = res.get(str(n + 1)); path = getattr(r, "path", None) if r is not None else None
        if path and Path(path).is_file():
            ent = L.register(path, id=i, kind=ART[i][0], subject=ART[i][1], prompt=rows[n].prompt, source="flow", notes=f"flow {mode} {time.strftime('%Y-%m-%d')}")
            out.append({"id": i, "status": "generated", "path": ent["path"]})
        else: out.append({"id": i, "status": "failed", "error": str(getattr(r, "error", None) or "no image returned")})
    return out

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0]); ap.add_argument("--go", action="store_true"); ap.add_argument("--only", nargs="*"); ap.add_argument("--account", action="append")
    ap.add_argument("--mode", default="ui", choices=("ui", "agent", "rpc")); a = ap.parse_args(argv)
    ids = a.only or list(ART)
    if not a.go:
        print(json.dumps({"missing": [{"id": i, "prompt": prompt_for(i)} for i in ids if not L.find(i)], "images_to_generate": len(L.missing(ids))}, indent=1)); return 0
    r = generate(ids, a.account, a.mode); print(json.dumps(r, indent=1)); return 0 if all(x["status"] != "failed" for x in r) else 1

if __name__ == "__main__":
    sys.exit(main())
