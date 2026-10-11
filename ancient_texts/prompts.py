"""The two copyable prompts that sit before the CSV prompt (research, then script). Text only: pasting them into an AI is
the user's step; the app never sends them anywhere."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .subjects import SubjectPack

PROMPT_FILES = {"research": "enoch_template_research_prompt.txt", "script": "enoch_template_script_prompt.txt"}


def _dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "composition_styles"
    return Path(__file__).resolve().parent.parent / "composition_styles"


def research_prompt(topic: str = "", pack: Optional[SubjectPack] = None) -> str:
    text = (_dir() / PROMPT_FILES["research"]).read_text(encoding="utf-8")
    questions = "\n".join(f"- {w.id}: {w.prompt}" for w in (pack.research_watch_list if pack else ())) or "- (none)"
    text = text.replace("<<<OPEN QUESTIONS>>>", questions)
    return text.replace("<<<TOPIC>>>", topic.strip()) if topic.strip() else text


def script_prompt(ledger_json: str = "", language: str = "") -> str:
    text = (_dir() / PROMPT_FILES["script"]).read_text(encoding="utf-8")
    text = text.replace("<<<LANGUAGE>>>", language.strip() or "the language of the topic and audience")
    return text.replace("<<<PASTE THE CLAIMS LEDGER HERE>>>", ledger_json.strip()) if ledger_json.strip() else text
