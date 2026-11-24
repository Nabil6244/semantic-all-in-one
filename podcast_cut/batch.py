"""Podcast Cut overnight batch: several podcasts one after another, no app window, no clicks.

    python -m podcast_cut.batch videos.csv [--out-dir ~/Downloads/Podcast Cuts] [--preview]

CSV columns: source (YouTube link or file, required), minutes, channel, speaker, clips (your clip CSV), shorts, out.
One failure never stops the rest; a report (batch_report.json next to the CSV) is written after every video.
The literal stock shots are fetched automatically (the command line has no Visuals tab to check them in).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from podcast_cut import fetch, runner  # noqa: E402


def run(csv_path: Path, out_dir: Path, preview: bool = False, log=print) -> list:
    rows = list(csv.DictReader(Path(csv_path).open(encoding="utf-8-sig")))
    report_p = Path(csv_path).with_name("batch_report.json")
    report = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for k, r in enumerate(rows, 1):
        r = {(a or "").strip().lower(): (b or "").strip() for a, b in r.items()}
        src = r.get("source", "")
        item = {"n": k, "source": src, "state": "failed", "out": "", "error": "", "seconds": 0.0}
        t0 = time.time()
        try:
            if not src:
                raise ValueError("no source")
            shorts = int(r.get("shorts") or 0)
            res = runner.plan(src, target_min=float(r.get("minutes") or 35), clip_csv=r.get("clips") or None,
                              channel=r.get("channel", ""), speaker=r.get("speaker", ""), shorts=shorts, log=log)
            if not res["ok"]:
                raise RuntimeError("; ".join(res["errors"][:3]))
            out = Path(r["out"]).expanduser() if r.get("out") else out_dir / f"{k:02d}_{fetch.source_id(src)}.mp4"
            rr = runner.render(res["workdir"], out, preview=preview, shorts=shorts > 0, log=log)
            item.update(state="done", out=str(out), title=rr["titles"][0] if rr["titles"] else "",
                        shorts=[str(p) for p in rr["shorts"]])
        except Exception as exc:  # noqa: BLE001 - the next video still runs
            item["error"] = f"{type(exc).__name__}: {exc}"
            log(traceback.format_exc()[-800:])
        item["seconds"] = round(time.time() - t0, 1)
        report.append(item)
        report_p.write_text(json.dumps(report, indent=1), encoding="utf-8")
        log(f"[{k}/{len(rows)}] {item['state']}: {item['out'] or item['error']}")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv")
    ap.add_argument("--out-dir", default=str(Path.home() / "Downloads" / "Podcast Cuts"))
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args(argv)
    rep = run(Path(a.csv), Path(a.out_dir).expanduser(), preview=a.preview)
    return 0 if all(x["state"] == "done" for x in rep) else 1


if __name__ == "__main__":
    sys.exit(main())
