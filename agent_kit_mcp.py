#!/usr/bin/env python3
"""Agent Kit as an MCP server: Claude (Claude Code / Desktop) or Gemini (Gemini CLI, Antigravity) makes a video itself
from a script and a voiceover, with five tools: align, find, scene, look, join. The how-to is the `guide` tool
(agent_kit/GUIDE.md). Standard library only on the MCP side; speaks JSON-RPC over stdin/stdout.

    claude mcp add videokit --scope project -- python3 /path/to/agent_kit_mcp.py
    gemini mcp add videokit python3 /path/to/agent_kit_mcp.py"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from agent_kit import kit  # noqa: E402

PROTOCOL = "2025-06-18"


DRAWN = {"history_toon", "doodle_dark"}      # all-drawn packs: no 3D/footage rules, their own README instead
OWN_RULES = DRAWN | {"city_lens"}            # packs whose README replaces the doc_teal "3D first" section


def guide(pack: str = "") -> str:
    """The guide. With pack=<look pack>: only the parts that pack needs, plus its README (shorter = fewer credits)."""
    text = (HERE / "agent_kit" / "GUIDE.md").read_text(encoding="utf-8")
    pack = (pack or "").strip()
    if not pack:
        return text
    parts = text.split("\n## ")
    keep = [parts[0]]
    for sec in parts[1:]:
        title = sec.split("\n", 1)[0]
        if title.startswith("Look packs") or (pack in OWN_RULES and title.startswith("3D first")):
            continue
        keep.append(sec)
    out = "\n## ".join(keep)
    readme = HERE / "agent_kit" / "looks" / pack / "README.md"
    if readme.exists():
        out += f"\n\n## Your look pack: {pack}\n" + readme.read_text(encoding="utf-8").split("\n", 1)[1]
    out += (f"\n\n## Short scene files (use them)\nA scene file may hold ONLY its script: no <html>, <head>, layers or imports. "
            f"The kit wraps it in the {pack} page with the layers #cam (svg #s + div #h inside it), svg #tags (outside the camera), "
            f"#fl, vignette, grain, and these names already imported: {kit.SHORT_FORM_NAMES.get(pack, 'K')}. "
            "window.sceneReady is set to document.fonts.ready. Import only your own film's names, e.g. "
            "`import { CAST, city } from '/@scene/common.js';` (common.js must not re-export the names above). "
            "Start an overlay page with the comment `// overlay` for a transparent body.\n"
            "Make all scene files, look at their stills, then call `render_all` ONCE (it renders every drawn scene of plan.json "
            "and keeps clips that did not change), instead of one `scene` call per scene.")
    return out


def look(path: str, frames: int = 8, times: str = "", at: float | None = None, duration: float = 30.0, size: int = 960):
    text = kit.look(path, frames=frames, times=times, at=at, duration=duration, size=size)
    content = [{"type": "text", "text": text}]
    for line in text.splitlines():
        p = Path(line.split("  ")[0].strip())
        if p.suffix.lower() in (".jpg", ".png") and p.exists() and p.stat().st_size < 4_000_000:
            mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
            content.append({"type": "image", "data": base64.b64encode(p.read_bytes()).decode(), "mimeType": mime})
    return content


S, I, N, A = {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "array"}
TOOLS = {
    "guide": (guide, "Read this first: how to make a video with these tools (steps, scene page rules, look, pacing). Pass "
              "pack=<look pack> (doc_teal, history_toon, doodle_dark, city_lens) to get only what that look needs.", {"pack": S}, []),
    "align": (kit.align, "Step 1. Transcribe the voiceover with word times into the project folder. Returns every sentence with its "
              "start and end time; word times are in <project>/voice/words.json.",
              {"project": S, "voice": S, "script": S, "language": S}, ["project", "voice"]),
    "find": (kit.find, "Find and download footage or photos into <project>/media: kind=video|photo (Pexels stock) or wiki "
             "(Wikimedia Commons: real people, places, history, science). Returns file paths with size, length and source.",
             {"project": S, "query": S, "kind": S, "count": I, "min_seconds": N}, ["project", "query"]),
    "map": (kit.map_svg, "Make a sharp vector map of a region (west/south/east/north in degrees) into <project>/scenes/<name>.svg "
            "(land path #land, country borders #borders) + <name>.json (projection for K.lonlat(proj, lon, lat) to place pins, "
            "labels, routes). Use it for every place the narration names.",
            {"project": S, "name": S, "west": N, "south": N, "east": N, "north": N, "countries": {"type": "boolean"}},
            ["project", "name", "west", "south", "east", "north"]),
    "terrain": (kit.terrain, "Real 3D elevation of a region, land AND seafloor, into <project>/scenes/<name>_dem.png/.json. Draw it "
                "with /agent_kit/looks/doc_teal/terrain3d.js: 3D relief, a water level you can raise or lower (flood, drain), "
                "camera moves, T.screen(lon, lat) for pins. Use it for every sea, coast, valley or mountain the narration names.",
                {"project": S, "name": S, "west": N, "south": N, "east": N, "north": N, "zoom": I},
                ["project", "name", "west", "south", "east", "north"]),
    "satellite": (kit.satellite, "Real satellite picture of a city or place (west/south/east/north in degrees) into "
                  "<project>/scenes/<name>_sat.jpg + <name>_sat.json (projection in frame px for K.lonlat). Use it for every "
                  "downtown, freeway, district or river the narration names (city_lens maps sit on it).",
                  {"project": S, "name": S, "west": N, "south": N, "east": N, "north": N, "zoom": I},
                  ["project", "name", "west", "south", "east", "north"]),
    "check_plan": (kit.check_plan, "Step 3. Check <project>/plan.json against the voice before making scenes: timing, scene "
                   "lengths, graphics share (70 %+), bare footage, hooks on spoken words, and names/places/numbers said but not "
                   "shown. Fix every problem it lists, then check again.", {"project": S}, ["project"]),
    "scene": (kit.scene, "Make one clip, exactly `duration` seconds, into <project>/clips/<name>.mp4: from an HTML scene you wrote "
              "(html=scenes/<name>.html, defines window.renderAt(t)), or from media (a video cut from `start`, or a photo with a slow "
              "Ken Burns move), optionally with a transparent overlay_html page drawn on top. grade: doc_teal|city_lens|warm|bw|none. "
              "Always pass `at` (the scene's start in the voice): the page then gets window.WORDS for K.when('word').",
              {"project": S, "name": S, "duration": N, "html": S, "media": S, "start": N, "zoom": N, "pan": S, "grade": S,
               "overlay_html": S, "workers": I, "at": N}, ["project", "name", "duration"]),
    "look": (look, "See your work: a contact sheet of a clip (frames spread over it, or at `times`), or stills of an HTML "
             "scene at `times` (e.g. \"0.5,2,4\") without rendering it, 960 px wide (size=1920 only when you need fine detail). "
             "Always look before moving on.",
             {"path": S, "frames": I, "times": S, "at": N, "duration": N, "size": I}, ["path"]),
    "render_all": (kit.render_all, "Render EVERY drawn scene of plan.json in one call (scenes/<name>.html, start/end from the plan, "
                   "word times included). Clips whose scene file did not change are kept, so after fixing a few scenes call it "
                   "again. Use it instead of one `scene` call per drawn scene.", {"project": S, "workers": I}, ["project"]),
    "join": (kit.join, "Last step. Join the clips (in order) with the voice, optional music (a file, ducked under the voice) and "
             "sound effects sfx=[{at, sound, db}] (sound: whoosh, impact, riser, transition, ui, text, cinematic, technology, "
             "ambience, or a file) into <project>/final.mp4 at -14 LUFS.",
             {"project": S, "clips": A, "voice": S, "music": S, "music_db": N, "sfx": {"type": "array", "items": {"type": "object"}},
              "out": S, "tail": N, "voice_end": N}, ["project", "clips"]),
}


def handle(msg: dict) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if mid is None:
        return None
    ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}   # noqa: E731
    if method == "initialize":
        return ok({"protocolVersion": params.get("protocolVersion") or PROTOCOL, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "videokit", "version": "1.0"},
                   "instructions": "Call `guide` first (with pack=<look pack>). You make the video yourself: align -> story + plan.json -> check_plan -> scene files -> look -> render_all -> join."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": props, "required": req}}
                             for n, (_, d, props, req) in TOOLS.items()]})
    if method == "tools/call":
        name = params.get("name", "")
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        fn, _, props, _ = TOOLS[name]
        args = {k: v for k, v in (params.get("arguments") or {}).items() if k in props}
        try:
            res = fn(**args)
            content = res if isinstance(res, list) else [{"type": "text", "text": str(res)}]
            return ok({"content": content, "isError": False})
        except Exception as exc:                         # the error goes back to the AI to read and fix
            return ok({"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
