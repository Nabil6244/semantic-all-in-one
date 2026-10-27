"""Phase 1 demonstration timeline: repo footage (Images/), fixture text and fixture word timings. No real facts, no real person.

    python3 -m cinematic_explainer.demo out/cinematic_phase1.mp4
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw

from .render import Layer, Shot, render

ROOT = Path(__file__).resolve().parents[1]

# Fixture narration for the source card: (word, start seconds from the card start). The highlighter follows `mark`.
SOURCE_WORDS = ("The refinery shut down one of its main processing units for repairs.").split()
SOURCE_TIMES = [0.5 + 0.28 * i for i in range(len(SOURCE_WORDS))]
SOURCE_MARK = (4, 8)   # "one of its main processing"


def placeholder_portrait(size: int = 400) -> Image.Image:
    """A neutral silhouette: the prototype never shows a real person."""
    im = Image.new("RGB", (size, size), (58, 66, 82))
    d = ImageDraw.Draw(im)
    d.ellipse([size * .32, size * .18, size * .68, size * .54], fill=(150, 158, 172))
    d.ellipse([size * .12, size * .56, size * .88, size * 1.3], fill=(150, 158, 172))
    return im


def timeline() -> Tuple[List[Shot], List[Layer]]:
    clip = lambda n: str(ROOT / "Images" / n)
    shots = [Shot(clip("008.mp4"), 0.0, 4.6), Shot(clip("013.mp4"), 4.6, 10.4, seek=1.0), Shot(clip("009.mp4"), 10.4, 15.2, seek=4.0),
             Shot(clip("025.mp4"), 15.2, 20.6, seek=3.0), Shot(clip("012.mp4"), 20.6, 25.4, seek=5.0)]
    layers = [
        Layer("shot_head", 0.3, 4.2, {"text": "A sample shot headline"}),
        Layer("kicker", 4.8, 10.0, {"text": "Sample evidence"}, dim=False),
        Layer("source", 4.8, 10.0, {"outlet": "Example Source", "date": "12 October", "words": SOURCE_WORDS, "times": SOURCE_TIMES,
                                    "mark": SOURCE_MARK}, dim=True),
        Layer("kicker", 10.6, 14.8, {"text": "Sample figures"}),
        Layer("number", 10.6, 14.8, {"value": 5, "prefix": "×", "label": "More than the year before", "sub": "Fixture figure, not a claim",
                                     "colour": "red"}, dim=True),
        Layer("kicker", 15.4, 20.2, {"text": "In this video"}),
        Layer("list", 15.4, 20.2, {"title": "Three questions", "items": ["Why it happened", "What changed", "What comes next"],
                                   "times": [0.6, 1.9, 3.2]}, dim=True),
        Layer("kicker", 20.8, 25.0, {"text": "Sample portrait"}),
        Layer("portrait", 20.8, 25.0, {"image": placeholder_portrait(), "name": "Sample person", "role": "Placeholder, no identity"},
              dim=True),
    ]
    return shots, layers


def main(argv: List[str]) -> int:
    out = argv[1] if len(argv) > 1 else str(ROOT / "out" / "cinematic_phase1.mp4")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    shots, layers = timeline()
    stats = render(shots, layers, out)
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
