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
REAL_STYLE = "Realistic detailed illustration with studio lighting, solid pure black background (#000000), no text, no letters, no numbers, no brand logos, no watermark, subject fully inside the frame"

# id -> (kind, subject sentence, style)
ART = {
    "rep_stand_v1": ("character", f"Full-body front view of {CHARACTER}, standing relaxed, arms hanging at his sides, calm focused expression", STYLE),
    "rep_hang_v1": ("character", f"Full-body front view of {CHARACTER}, hanging from a plain horizontal steel pull-up bar that is fully visible across the top of the picture, arms straight overhead, gripping the bar", STYLE),
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
