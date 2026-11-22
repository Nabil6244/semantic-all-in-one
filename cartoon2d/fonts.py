"""The show's rounded bold font: Arial Rounded Bold where the Mac has it (the look every episode was approved in),
else Outfit ExtraBold (OFL, shipped with the app in stickman/assets/fonts) - Windows has no Arial Rounded."""
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CANDIDATES = (Path("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"),
               Path("C:/Windows/Fonts/ARLRDBD.TTF"),
               _ROOT / "stickman" / "assets" / "fonts" / "Outfit-ExtraBold.ttf")
FONT = str(next((p for p in _CANDIDATES if p.is_file()), _CANDIDATES[-1]))
