"""The editorial director, answered scene by scene: every scene's decision is cached on its own input, only the scenes that changed are asked,
batches run concurrently and fail independently, and a scene Gemini could not answer falls back to the editorial rules.

Plugs into editorial.compile_editorial_plan(reasoner=...), so editorial/ itself is untouched. Why batches of 12 and not 28: a 28-scene answer
needs more tokens than the call allowed (the 047 run: 8 of 10 answers stopped at the 5433-token cap, cut off mid-JSON and thrown away, ~25 s each)."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .core import DecisionCache, TELEMETRY, run_batches, stable_key

TASK = "editorial"
BATCH = 12
MAX_OUT_TOKENS = 8192


class _Truncated(Exception):
    """Gemini answered, but the JSON could not be read (usually cut off at the token limit)."""


def _model_name() -> str:
    try:
        from visual_director.llm import DEFAULT_GEMINI_MODEL
    except Exception:
        DEFAULT_GEMINI_MODEL = "gemini"
    return os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL


class SceneCachedEditorialReasoner:
    """Same `reason(plan, candidates_by_scene=...)` contract as editorial.reasoner.GeminiEditorialReasoner."""

    def __init__(self, settings: Optional[Mapping[str, Any]] = None, *, cache_dir: Optional[Path] = None,
                 llm_factory: Optional[Callable[[], Any]] = None, batch_size: int = BATCH, workers: int = 3, retries: int = 2,
                 backoff: float = 2.0, style_key: str = "", sleep: Callable[[float], None] = time.sleep):
        self.settings = dict(settings or {})
        self.cache = DecisionCache(Path(cache_dir) / "editorial_scenes.json" if cache_dir else None)
        self.llm_factory = llm_factory
        self.batch_size = max(1, int(batch_size))
        self.workers, self.retries, self.backoff, self.sleep = workers, retries, backoff, sleep
        self.style_key = style_key
        self.provenance: Dict[str, str] = {}
        self._local = threading.local()

    # -- one Gemini call ------------------------------------------------------------------------------------------------------------
    def _llm(self) -> Any:
        llm = getattr(self._local, "llm", None)
        if llm is None:
            if self.llm_factory is not None:
                llm = self.llm_factory()
            else:
                from visual_director.llm import GeminiLLM

                llm = GeminiLLM(settings=self.settings, timeout=75.0)
            self._local.llm = llm
        return llm

    def _ask(self, beats: List[dict], idxs: List[int]) -> Dict[int, Any]:
        """{index: EditorialIntent | None} for the beats at `idxs`. A cut-off answer is retried as two half-size requests."""
        import json

        from editorial import reasoner as R

        chunk = [beats[i] for i in idxs]
        user = "Documentary editorial intents for these beats. Return JSON only.\n\n" + json.dumps({"beats": chunk}, ensure_ascii=False)
        llm = self._llm()
        try:
            from visual_director.llm import GeminiLLM

            real = isinstance(llm, GeminiLLM)
        except Exception:
            real = False
        raw = (llm.complete(R.SYSTEM_PROMPT, user, thinking_level="low", max_output_tokens=MAX_OUT_TOKENS) if real
               else llm.complete(R.SYSTEM_PROMPT, user))
        payload = R._extract_json_object(raw)
        if not payload:
            if len(idxs) > 1:
                half = len(idxs) // 2
                out = self._ask(beats, idxs[:half])
                out.update(self._ask(beats, idxs[half:]))
                return out
            raise _Truncated("the answer could not be read as JSON")
        parsed = R.parse_intent_payload(payload, valid_scenes=[beats[i]["scene_number"] for i in idxs])
        return {i: parsed.get(str(beats[i]["scene_number"])) for i in idxs}

    # -- the contract ---------------------------------------------------------------------------------------------------------------
    def reason(self, plan: Any, *, candidates_by_scene: Optional[Mapping[str, Sequence[Any]]] = None) -> Dict[str, Any]:
        from editorial import reasoner as R
        from editorial.intent import EditorialIntent, REASONER_VERSION

        t0 = time.monotonic()
        before = TELEMETRY.snapshot().get(TASK, {})
        scenes = list(plan.scenes)
        if not scenes:
            return {}
        beats = R._beat_payload(scenes, candidates_by_scene=candidates_by_scene, start=0, end=len(scenes))
        prompt_id = hashlib.sha256(R.SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
        model = _model_name()
        keys = [stable_key(model, REASONER_VERSION, prompt_id, self.style_key, {k: v for k, v in b.items() if k != "index"}) for b in beats]
        decided: Dict[int, Any] = {}
        missing: List[int] = []
        for i, key in enumerate(keys):
            if self.cache.has(key):
                cached = self.cache.get(key)
                decided[i] = EditorialIntent.from_dict(cached) if isinstance(cached, dict) else None
                self.provenance[beats[i]["scene_number"]] = "cache"
            else:
                missing.append(i)
        hits = len(scenes) - len(missing)
        batches = [missing[k:k + self.batch_size] for k in range(0, len(missing), self.batch_size)]
        failed_scenes = 0
        if batches:
            results = run_batches(batches, lambda idxs: self._ask(beats, idxs), workers=self.workers, retries=self.retries,
                                  backoff=self.backoff, sleep=self.sleep, task=TASK)
            for res, idxs in zip(results, batches):
                if not res.ok:
                    failed_scenes += len(idxs)
                    for i in idxs:
                        self.provenance[beats[i]["scene_number"]] = "rules"
                    continue
                for i in idxs:
                    intent = res.value.get(i)
                    if intent is not None:
                        intent.source = "ai"
                    decided[i] = intent
                    self.cache.put(keys[i], intent.to_dict() if intent is not None else None)
                    self.provenance[beats[i]["scene_number"]] = "ai"
            self.cache.flush()
        out: Dict[str, Any] = {}
        for i in range(len(scenes)):   # scene order, whatever order the batches finished in
            intent = decided.get(i)
            if intent is None:
                continue
            sn = str(intent.scene_number or beats[i]["scene_number"]).strip()
            for k in {sn, sn.zfill(3), sn.lstrip("0") or sn}:
                out[k] = intent
        asked = len(missing) - failed_scenes
        TELEMETRY.add(TASK, decisions=len(scenes), cache=hits, ai=asked, rules=failed_scenes + sum(1 for i in range(len(scenes)) if decided.get(i) is None and i not in missing),
                      wall_s=time.monotonic() - t0)
        print(TELEMETRY.line(TASK, before))
        return out
