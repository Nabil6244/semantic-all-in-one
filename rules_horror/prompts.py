"""The two prompts the Rules Horror page copies for an AI chat: write a new story + CSV, or convert a script the user already has into the CSV.
Both share one CSV description (the part of prompt.txt from "THE CSV" to the last line), so a new set, prop or action is documented in one place."""
from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).parent
_START, _END = "THE CSV (write it in a code block, nothing else around it)", "Write the story as plain text first"


def story_prompt() -> str:
    return (_HERE / "prompt.txt").read_text(encoding="utf-8")


def csv_spec() -> str:
    """The CSV description: the header line, every column, and the CSV rules."""
    text = story_prompt()
    a, b = text.index(_START) + len(_START), text.index(_END)
    return text[a:b].strip()


def convert_prompt() -> str:
    return (_HERE / "prompt_convert.txt").read_text(encoding="utf-8").replace("{{CSV_SPEC}}", csv_spec())
