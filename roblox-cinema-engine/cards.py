"""Horror picture cards through the Visuals tab. The planner (lib/horror.mjs) says which cards a film wants; this file turns the ones that want a
picture into Visuals-tab rows, fetches them, and hands the renderer {card id: file}.

  requests(plan_json, images_dir)   the plan's picture cards, numbered for the table. A card keeps its number while its prompt stays the same, so a
                                    second Generate never shows an old picture on a different card
  table_rows(reqs)                  the Visuals-tab rows (providers.base.SceneRow), one per distinct picture
  missing(reqs, images_dir)         the rows that have no finished file yet
  fetch(reqs, manager, dir, ..)     the CSV's own files filed as finished, the rest fetched through the app's AssetManager; no Gemini, ever
  write_pictures(out, reqs, recs)   {card id: file} from what the table holds now (a picture swapped there is what the film uses)

A card with no picture is not an error anywhere: the renderer draws its code-made card. Nothing here stops a film."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
NUMBERS = "card_numbers.json"


def _numbers(images_dir: Optional[Path]) -> dict:
    try:
        return json.loads((Path(images_dir) / NUMBERS).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - no file yet, or a hand-damaged one: numbering starts again
        return {}


def requests(plan_json: str, images_dir: Optional[Path] = None) -> List[dict]:
    """Every picture card of the plan: [{n, id, kind, what, prompt, asset}]. [] for a film without any (all history films)."""
    cards = json.loads(Path(plan_json).read_text(encoding="utf-8")).get("cards") or []
    wanted = [c for c in cards if c.get("picture")]
    if not wanted:
        return []
    index = _numbers(images_dir) if images_dir else {}
    out = []
    for c in wanted:
        key = c.get("prompt") or c.get("asset") or c["id"]
        if key not in index:
            index[key] = max([int(v) for v in index.values()] + [0]) + 1
        out.append({"n": int(index[key]), "id": c["id"], "kind": c.get("kind", ""), "what": c.get("what") or c.get("kind", ""), "prompt": c.get("prompt", ""), "asset": c.get("asset", "")})
    if images_dir:
        try:
            Path(images_dir).mkdir(parents=True, exist_ok=True)
            (Path(images_dir) / NUMBERS).write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


def table_rows(reqs: List[dict]) -> list:
    """One Visuals-tab row per distinct picture (two cards with the same prompt share one)."""
    from providers.base import SceneRow

    rows, seen = [], set()
    for c in reqs:
        if c["n"] not in seen:
            seen.add(c["n"])
            rows.append(SceneRow.from_csv_row({"scene_number": str(c["n"]), "script_segment": c["what"], "asset_type": "flow_image", "prompt": c["prompt"]}))
    return rows


def missing(reqs: List[dict], images_dir: Path) -> list:
    """The rows still to fetch: no finished picture, and no file of the CSV's own."""
    import visual_bridge

    own = {c["n"] for c in reqs if c.get("asset")}
    return [r for r in table_rows(reqs) if int(str(r.scene_number)) not in own and not visual_bridge.records(images_dir, [r])]


def _own_file(asset: str, base_dir: str) -> str:
    p = Path(asset)
    p = p if p.is_absolute() else Path(base_dir) / p
    return str(p) if p.suffix.lower() in IMAGE_EXT and p.is_file() else ""


def fetch(reqs: List[dict], manager, images_dir: Path, *, base_dir: str = "", log: Callable = lambda m: None, cancel: Optional[Callable] = None) -> list:
    """Fills the Visuals table's folder and returns its rows. A picture already there, or one the user picked, is kept. A failed fetch only costs that picture."""
    import visual_bridge

    Path(images_dir).mkdir(parents=True, exist_ok=True)
    for c in reqs:
        f = _own_file(c["asset"], base_dir) if c.get("asset") else ""
        if f:
            visual_bridge.seed(images_dir, str(c["n"]), f, "local", prompt=c["prompt"])
        elif c.get("asset"):
            log(f"card {c['id']}: the CSV's picture file is not there ({c['asset']})")
    rows = table_rows(reqs)
    todo = [r for r in rows if not visual_bridge.records(images_dir, [r])]
    if not todo or manager is None:
        return rows
    try:
        manager.settings["gemini_enabled"] = False      # a supplied story directs itself: no AI planning, retries or checks
    except Exception:  # noqa: BLE001
        pass
    log(f"Fetching {len(todo)} card pictures…")
    stop = threading.Event()
    if cancel is not None:
        def watch() -> None:
            while not stop.wait(0.3):
                if cancel():
                    try:
                        manager.request_cancel()
                    except Exception:  # noqa: BLE001
                        pass
                    return

        threading.Thread(target=watch, daemon=True, name="rc-card-cancel").start()
    try:
        manager.resolve_all(todo)
    except Exception as exc:  # noqa: BLE001 - those cards stay code-made
        log(f"card pictures stopped early, those cards stay code-made: {type(exc).__name__}: {exc}")
    finally:
        stop.set()
    return rows


def pictures(reqs: List[dict], records: Dict[int, dict]) -> Dict[str, str]:
    """{card id: picture file} the table holds. A video put in the table, or a file that has gone, is left out: that card stays code-made."""
    out: Dict[str, str] = {}
    for c in reqs:
        p = (records.get(c["n"]) or {}).get("path") or ""
        if p and p.lower().endswith(IMAGE_EXT) and Path(p).is_file():
            out[c["id"]] = p
    return out


def write_pictures(out_path: str, reqs: List[dict], records: Dict[int, dict]) -> str:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(pictures(reqs, records), indent=1, ensure_ascii=False), encoding="utf-8")
    return out_path


def summary(reqs: List[dict], records: Dict[int, dict]) -> str:
    have = len(pictures(reqs, records))
    return f"{have} of {len(reqs)} picture cards have a picture (see the Visuals tab); the rest use the code-made card."
