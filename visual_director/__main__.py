#!/usr/bin/env python3
"""Plan a video from a full script, then optionally write the existing CSV shape."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from visual_director import VisualDirector
from visual_director.llm import LLMError, MISSING_GEMINI_KEY
from visual_director.schema import VisualPlanError, assert_pipeline_compatible


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="AI Visual Director: full script → structured scene plan (existing CSV schema)."
    )
    parser.add_argument("--script", required=True, help="UTF-8 text file with the complete narration")
    parser.add_argument("--out-json", help="Write the full plan JSON here")
    parser.add_argument("--out-csv", help="Write scene_number,script_segment,asset_type,prompt CSV")
    parser.add_argument("--preview", action="store_true", help="Print a human-readable preview")
    args = parser.parse_args(argv)

    script = Path(args.script).read_text(encoding="utf-8")
    try:
        plan = VisualDirector().plan(script)
    except LLMError as exc:
        print(str(exc) or MISSING_GEMINI_KEY, file=sys.stderr)
        return 2
    except VisualPlanError as exc:
        print(f"Invalid visual plan: {exc}", file=sys.stderr)
        return 2
    errors = assert_pipeline_compatible(plan)
    if errors:
        print("Plan is not compatible with AssetManager:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 2
    if args.preview or (not args.out_json and not args.out_csv):
        print(plan.format_preview())
    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(plan.to_dict(), indent=2), encoding="utf-8"
        )
        print(f"Wrote {args.out_json}")
    if args.out_csv:
        plan.write_csv(Path(args.out_csv))
        print(f"Wrote {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
