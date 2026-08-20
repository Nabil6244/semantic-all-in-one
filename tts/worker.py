"""Persistent Qwen3-TTS worker. JSON lines on stdin/stdout; logs on stderr."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tts.base import DEFAULT_LANGUAGE, TTSResult
from tts.errors import TTSError, map_exception
from tts.qwen_provider import Qwen3TTSProvider

_provider: Qwen3TTSProvider | None = None


def _log(message: str) -> None:
    sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()


def _send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _get_provider() -> Qwen3TTSProvider:
    global _provider
    if _provider is None:
        _provider = Qwen3TTSProvider(log=_log)
    return _provider


def _result_payload(result: TTSResult) -> dict:
    return {
        "type": "result",
        "path": str(result.path),
        "duration_seconds": result.duration_seconds,
        "sample_rate": result.sample_rate,
        "format": result.format,
        "provider": result.provider,
        "voice": result.voice,
        "generation_time_seconds": result.generation_time_seconds,
        "load_time_seconds": result.load_time_seconds,
        "device": result.device,
        "model": result.model,
        "local": result.local,
    }


def _handle(msg: dict) -> dict:
    op = msg.get("op")
    if op == "ping":
        return {"type": "pong"}
    if op == "shutdown":
        if _provider is not None:
            _provider.shutdown()
        return {"type": "bye"}
    if op == "build_voice_prompt":
        _get_provider().build_voice_prompt(
            ref_audio=msg.get("ref_audio") or "",
            ref_text=msg.get("ref_text") or "",
            prompt_path=Path(msg["prompt_path"]),
        )
        return {"type": "ok", "prompt_path": msg.get("prompt_path")}
    if op == "generate_clone":
        text = msg.get("text") or ""
        output = Path(msg["output_path"])
        kwargs = {
            "text": text,
            "output_path": output,
            "language": msg.get("language") or DEFAULT_LANGUAGE,
        }
        if msg.get("voice_prompt_path"):
            kwargs["voice_prompt_path"] = msg.get("voice_prompt_path")
        else:
            kwargs["ref_audio"] = msg.get("ref_audio") or ""
            kwargs["ref_text"] = msg.get("ref_text") or ""
        result = _get_provider().generate_clone(**kwargs)
        return _result_payload(result)
    return {"type": "error", "code": "unknown_op", "message": f"Unknown op: {op}"}


def main() -> None:
    _send({"type": "ready"})
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send({"type": "error", "code": "bad_json", "message": "Invalid worker request."})
            continue
        try:
            payload = _handle(msg)
            _send(payload)
            if payload.get("type") == "bye":
                return
        except Exception as exc:
            mapped = map_exception(exc) if not isinstance(exc, TTSError) else exc
            if mapped.code == "generation_failure":
                traceback.print_exc(file=sys.stderr)
            _send({"type": "error", "code": mapped.code, "message": mapped.message})


if __name__ == "__main__":
    main()
