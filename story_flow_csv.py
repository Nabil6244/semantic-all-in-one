"""story_flow_csv -- turn a shot plan into the CSV(s) Flow needs to make the NEW pictures, and the map that lets the story pipeline find them afterwards.

    files = export(plan, out_dir, name="hrt", start_no=101, character=False, protagonist=None)
        -> {"pictures_csv": ..., "map": ..., "character_csv": ... (only when character requests exist), "count": N}

* <name>_flow_pictures.csv: scene_number, script_segment, asset_type, prompt (the app's normal 4 columns, asset_type 'image'): one row per shot whose picture is 'new' and that is not a
  character shot. scene_number starts at start_no (101 by default) so the numbers can never collide with the project's own scenes. Run it in a pictures-only project (or any project:
  extra numbers are ignored by the render) and keep the images named by scene_number.
* <name>_picture_map.json: {shot_id: scene_number}. story_pipeline reads <project>/state/story/picture_map.json (copy it there) and finds <images_dir>/<scene_number>.<ext> for each shot.
* <name>_flow_character.csv (optional narrator): reference images first, then the character shots; see story_character.plan_generation. Not needed for the video.
Nothing here talks to Flow."""
from __future__ import annotations
import csv, json
from pathlib import Path

def _no_motion_tag(prompt):
    """The optional 'MOTION: ...' hint at the end of a CSV prompt is for the director, never for the image model."""
    try:
        from story_fast.direct import strip_motion
        return strip_motion(prompt)
    except Exception:
        return prompt

def export(plan, out_dir, name="project", start_no=101, character=False, protagonist=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rows, mp = [], {}
    n = int(start_no)
    for s in plan.get("shots", []):
        if s.get("picture") != "new" or s.get("character"):
            continue
        rows.append({"scene_number": n, "script_segment": s.get("text", ""), "asset_type": "image", "prompt": _no_motion_tag(s.get("prompt_en", ""))})
        mp[str(s["shot_id"])] = str(n); n += 1
    files = {"count": len(rows)}
    p = out / f"{name}_flow_pictures.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["scene_number", "script_segment", "asset_type", "prompt"], quoting=csv.QUOTE_ALL); w.writeheader(); w.writerows(rows)
    files["pictures_csv"] = str(p)
    m = out / f"{name}_picture_map.json"; m.write_text(json.dumps(mp, indent=1), encoding="utf-8"); files["map"] = str(m)
    if character:
        import story_character as sc
        g = sc.plan_generation(plan["shots"], protagonist or plan.get("protagonist"), {})
        crow = []
        for r in g.get("reference_requests", []):
            crow.append({"scene_number": f"ref_{r['kind']}", "script_segment": r["kind"], "asset_type": "image", "prompt": r["prompt"]})
        for r in g.get("character_requests", []):
            crow.append({"scene_number": r["shot_id"], "script_segment": r.get("script_segment", ""), "asset_type": "image", "prompt": r["prompt"]})
        c = out / f"{name}_flow_character.csv"
        with open(c, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["scene_number", "script_segment", "asset_type", "prompt"], quoting=csv.QUOTE_ALL); w.writeheader(); w.writerows(crow)
        files["character_csv"] = str(c)
    return files
