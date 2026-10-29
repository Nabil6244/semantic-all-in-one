"""Fill the illustration library through the app's existing Flow image workflow (providers.flow.FlowProvider), one picture per missing illustration, never a variation.

    python3 -m health_cinema.bodymap_flow --id skin_infection_lesion_v1 --topic "skin infection" --view lesion --kind lesion \\
        --subject "..." [--account <id>] [--mode ui|agent|rpc] [--go]

Without --go it only prints what it would generate (dry run, no engine, no credit). With --go it generates exactly one image per --id that is not already in the library,
registers it with its topic, view, prompt, style and source, and prints the credit use (images requested). The same id is never generated twice: an existing real entry is reused."""
from __future__ import annotations
import argparse, json, sys, tempfile, time
from pathlib import Path

from . import illustrations as ILL

def generate(entries: list, account_ids=None, mode: str = "ui", log=print, settings: dict | None = None) -> list:
    """entries: [{id, topic, view, kind, subject}] -> [{id, status: reused|generated|failed, path?, error?}]. One Flow image per entry that is not in the library yet."""
    out, todo = [], []
    for e in entries:
        hit = ILL.find(e["id"])
        if hit: out.append({"id": e["id"], "status": "reused", "path": hit["path"]}); log(f"[ILLUSTRATION] {e['id']}: already in the library, reused")
        else: todo.append(e)
    if not todo: return out
    from providers.base import SceneRow
    from providers.flow.engine_manager import FlowEngineManager
    from providers.flow.provider import FlowProvider
    mgr = FlowEngineManager(log=log)
    fs = {"model": "GEM_PIX_2", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE", "generationMode": mode}; fs.update(settings or {})
    prov = FlowProvider(mgr, media_kind="image", account_ids=account_ids, flow_settings=fs)
    tmp = Path(tempfile.mkdtemp(prefix="hc_ill_")); rows = [SceneRow(scene_number=str(i + 1), script_segment=e["subject"], asset_type="image", prompt=ILL.full_prompt(e["subject"])) for i, e in enumerate(todo)]
    log(f"[ILLUSTRATION] requesting {len(rows)} Flow image(s) on {account_ids or 'all signed-in accounts'} (mode {mode})")
    res = prov.resolve_batch(rows, tmp, log=log)
    for i, e in enumerate(todo):
        r = res.get(str(i + 1)); path = getattr(r, "path", None) if r is not None else None
        if path and Path(path).is_file():
            ent = ILL.register(path, id=e["id"], topic=e["topic"], view=e["view"], kind=e.get("kind", e["view"]), prompt=rows[i].prompt, source="flow", notes=f"flow {mode} {time.strftime('%Y-%m-%d')}")
            out.append({"id": e["id"], "status": "generated", "path": ent["path"]})
        else: out.append({"id": e["id"], "status": "failed", "error": str(getattr(r, "error", None) or "no image returned")})
    return out

def needs_from_csv(path) -> list:
    """The distinct illustrations a body-map scenes CSV asks for that the library does not hold yet: [{id, topic, view, kind, subject}] (one per card_ref, first prompt wins).
    A row with a card_prompt but no card_ref is reported as an error: without an id the picture could not be reused."""
    from . import scenes_csv as S
    need, seen = [], set()
    for i, r in enumerate(S.read_scenes_csv(str(path)), 1):
        if (r.get("card_type") or "none") == "none": continue
        ref, prompt = r.get("card_ref", ""), r.get("card_prompt", "")
        if not ref: raise ValueError(f"row {i}: card_type {r['card_type']} needs card_ref (an id like skin_infection_lesion_v1) so the picture can be stored and reused")
        if ref in seen or ILL.find(ref): continue
        if not prompt: raise ValueError(f"row {i}: '{ref}' is not in the library and the row has no card_prompt to generate it from")
        seen.add(ref); need.append({"id": ref, "topic": r.get("body_label") or r.get("body_region", ""), "view": r["card_type"], "kind": r["card_type"], "subject": prompt})
    return need

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", help="a body-map scenes CSV: list (or, with --go, generate) every illustration it needs that the library lacks")
    ap.add_argument("--id"); ap.add_argument("--topic"); ap.add_argument("--view"); ap.add_argument("--kind", default="")
    ap.add_argument("--subject"); ap.add_argument("--account", action="append"); ap.add_argument("--mode", default="ui", choices=("ui", "agent", "rpc")); ap.add_argument("--go", action="store_true")
    a = ap.parse_args(argv)
    if a.csv:
        need = needs_from_csv(a.csv)
        if not a.go: print(json.dumps({"missing": [dict(n, prompt=ILL.full_prompt(n["subject"])) for n in need], "images_to_generate": len(need)}, indent=1)); return 0
        r = generate(need, a.account, a.mode) if need else []; print(json.dumps(r, indent=1)); return 0 if all(x["status"] != "failed" for x in r) else 1
    if not (a.id and a.topic and a.view and a.subject): ap.error("--id, --topic, --view and --subject are required (or use --csv)")
    e = {"id": a.id, "topic": a.topic, "view": a.view, "kind": a.kind or a.view, "subject": a.subject}
    if not a.go:
        print(json.dumps({"would_generate": not ILL.find(a.id), "id": a.id, "prompt": ILL.full_prompt(a.subject), "images": 0 if ILL.find(a.id) else 1}, indent=1)); return 0
    r = generate([e], a.account, a.mode); print(json.dumps(r, indent=1)); return 0 if all(x["status"] != "failed" for x in r) else 1

if __name__ == "__main__":
    sys.exit(main())
