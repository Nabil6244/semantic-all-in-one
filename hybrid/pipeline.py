"""Script narration -> a validated, critiqued, repaired HybridPlan.

    timed sentences -> Director -> validate -> critic -> repair ONLY the weak beats -> validate -> critic ... (at most MAX_REPAIRS passes)

Whatever is left after the last pass is reported, not hidden: warnings never block, errors do (hybrid.validate)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import critic as critic_mod
from . import quality as quality_mod
from .local_fix import fix as local_fix
from .director import DirectorError, chapter_state, derive_cameras, director_prompt, local_sentences, plan_beats, plan_chunk, repair_beats
from .narration import Chunk, Sentence, Word, build_sentences, plan_chunks
from .plan import Beat, HybridPlan
from .validate import Finding, errors, validate

MAX_REPAIRS = 2            # the most repair cycles ever allowed
DEFAULT_REPAIR_CYCLES = 1  # normally one creative repair cycle is all a plan gets
CRITIC_BATCH_CHARS = 24000 # chapters are reviewed together up to about this much text per critic request
REPAIRABLE_WARNINGS = {"out_of_frame", "layer_late", "text_too_long", "wide_view", "point_zoom"}


@dataclass
class PlanResult:
    plan: HybridPlan
    findings: List[Finding] = field(default_factory=list)
    critique: critic_mod.Critique = field(default_factory=critic_mod.Critique)
    sentences: List[Sentence] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)  # things the Director's answer got wrong that the code worked around
    repair_passes: int = 0
    repaired: List[List[str]] = field(default_factory=list)  # beat ids redone in each pass
    log: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)  # long-form measurements: chapters, Director / critic / repair calls, checkpoint hits

    @property
    def ok(self) -> bool:
        return not errors(self.findings)

    def to_dict(self) -> dict:
        return {"findings": [f.to_dict() for f in self.findings], "critique": self.critique.to_dict(), "problems": self.problems,
                "repair_passes": self.repair_passes, "repaired": self.repaired, "sentences": [s.to_dict() for s in self.sentences], "stats": self.stats}


def _weak_beats(plan: HybridPlan, findings: Sequence[Finding], crit: critic_mod.Critique, problems: Sequence[str]) -> Dict[str, List[str]]:
    weak: Dict[str, List[str]] = {}
    for f in findings:
        if f.beat and (f.severity == "error" or f.code in REPAIRABLE_WARNINGS):  # these warnings never block a render, but a repair is worth trying
            weak.setdefault(f.beat, []).append(f"validator {f.severity}: {f.message}")
    for bid, issues in crit.weak().items():
        weak.setdefault(bid, []).extend(f"critic: {i}" for i in issues)
    for p in problems:  # problems that name a beat ("beat b3: ...")
        for b in plan.beats:
            if p.startswith(f"beat {b.id}:"):
                weak.setdefault(b.id, []).append(f"director output: {p}")
    return weak


def plan_hybrid(words: Sequence[Word], llm: Any, *, script: Optional[str] = None, duration: Optional[float] = None, settings: Optional[Dict[str, Any]] = None,
                style_guidance: str = "", critic_llm: Any = None, use_critic: bool = True, max_repairs: int = DEFAULT_REPAIR_CYCLES,
                on_progress: Optional[Callable[[str], None]] = None, checkpoint_dir: "str | Path | None" = None, chunking: bool = True,
                critic_policy: str = "auto") -> PlanResult:
    say = on_progress or (lambda m: None)
    total = float(duration) if duration else float(words[-1][2])
    sentences = build_sentences(words, script, total)
    if not sentences:
        raise DirectorError("there is no narration to plan")
    res = PlanResult(plan=None, sentences=sentences)  # type: ignore[arg-type]
    policy = critic_policy if use_critic else "never"      # "auto": a critic only where something looks suspicious; "always": every review; "never"
    max_repairs = max(0, min(int(max_repairs), MAX_REPAIRS))
    chunks = plan_chunks(sentences, total) if chunking else [Chunk(1, 0, len(sentences) - 1, 0.0, total)]
    if len(chunks) > 1:
        return _plan_long(words, llm, sentences, chunks, total, res, settings=settings, style_guidance=style_guidance, critic_llm=critic_llm, policy=policy,
                          max_repairs=max_repairs, on_progress=say, checkpoint_dir=checkpoint_dir)
    res.stats = {"chapters": 1, "director_calls": 1, "checkpoint_hits": 0, "critic_calls": 0, "repair_calls": 0, "local_validations": 0, "local_fixes": 0}
    plan, problems = plan_beats(llm, sentences, words, total, settings=settings, style_guidance=style_guidance, on_progress=say)
    res.problems = list(problems)
    _review(plan, [], sentences, words, llm, critic_llm or llm, say, res, policy=policy, max_cycles=max_repairs, first_problems=list(problems))
    _finish(res, llm)
    return res


def _finish(res: PlanResult, llm: Any) -> None:
    """Close the books: critic notes beside the validator's on each beat, usage numbers for the report."""
    for f in res.critique.findings:
        for b in res.plan.beats:
            if b.id == f.beat:
                b.findings.append(f"CRITIC ({f.severity}): {f}")
    res.stats["key_rotations"] = getattr(getattr(llm, "credentials", None), "rotations", 0)
    usage = getattr(llm, "usage", None)
    if usage is not None:
        res.stats["ai_usage"] = usage.to_dict()
        res.stats["ai_summary"] = usage.summary()


def _note_local(llm: Any, what: str, n: int = 1) -> None:
    usage = getattr(llm, "usage", None)
    if usage is not None:
        usage.note_local(what, n)


def _critic_targets(plan: HybridPlan, units: List[Chunk], findings: Sequence[Any], policy: str) -> Tuple[List[Optional[Chunk]], List[str]]:
    """Which parts of the plan deserve a critic, and why. [None] stands for a plan without chapters (all of it)."""
    if policy == "never":
        return [], []
    parts: List[Optional[Chunk]] = list(units) or [None]
    if policy == "always":
        return parts, ["always"]
    reasons: List[str] = []
    picked: List[Optional[Chunk]] = []
    for u in parts:
        beats = plan.beats if u is None else [b for b in plan.beats if b.chapter == u.index]
        why = quality_mod.unit_flags(beats, findings)
        if why:
            picked.append(u)
            reasons += why
    g = quality_mod.global_flags(plan)
    if g:
        reasons += g
        picked = parts          # a documentary-wide suspicion is judged on the whole, together
    return picked, reasons


def _critic_batches(plan: HybridPlan, parts: List[Optional[Chunk]], findings: Sequence[Any]) -> List[HybridPlan]:
    """The chosen parts as critic requests: chapters travel together until a request would be too long."""
    if parts == [None]:
        return [plan]
    batches: List[HybridPlan] = []
    cur: List[Any] = []
    size = 0
    for u in parts:
        sub = _chapter_plan(plan, u)
        n = len(critic_mod.plan_summary(sub, [f for f in findings if f.beat in {b.id for b in sub.beats}]))
        if cur and size + n > CRITIC_BATCH_CHARS:
            batches.append(HybridPlan(duration=plan.duration, beats=[b for x in cur for b in x.beats], settings=dict(plan.settings)))
            cur, size = [], 0
        cur.append(sub)
        size += n
    if cur:
        batches.append(HybridPlan(duration=plan.duration, beats=[b for x in cur for b in x.beats], settings=dict(plan.settings)))
    return batches


def _review(plan: HybridPlan, units: List[Chunk], sentences: Sequence[Sentence], words: Sequence[Word], llm: Any, cllm: Any, say: Callable[[str], None],
            res: PlanResult, *, policy: str, max_cycles: int, first_problems: Sequence[str]) -> None:
    """validate -> fix what code can fix -> (only if something looks creatively wrong) critic -> targeted repair -> validate again.
    The order is the point: every step is cheaper than the next, and the plan leaves as soon as nothing is left to do."""
    stats = res.stats
    for cycle in range(max_cycles + 1):
        final = cycle == max_cycles
        say(f"Validating the plan ({len(plan.beats)} beats)…")
        findings = validate(plan)
        stats["local_validations"] += 1
        _note_local(llm, "validation")
        n, notes = local_fix(plan, findings)
        if n:
            stats["local_fixes"] += n
            _note_local(llm, "deterministic repairs", n)
            res.log += notes
            say(f"Fixed {n} small thing(s) locally, no AI needed.")
            findings = validate(plan)
            stats["local_validations"] += 1
        crit = critic_mod.Critique()
        run_critic = (not final) or policy == "always"
        targets, reasons = _critic_targets(plan, units, findings, policy) if run_critic else ([], [])
        if run_critic and policy != "never" and not targets:
            stats["critic_skipped"] = True
            say("Critic skipped: nothing in the plan looks creatively wrong.")
        for batch in _critic_batches(plan, targets, findings) if targets else []:
            say(f"Hybrid critic: reviewing {len(batch.beats)} beats" + (f" ({'; '.join(reasons[:2])})" if reasons and policy == "auto" else "") + "…")
            try:
                stats["critic_calls"] += 1
                c = critic_mod.critique(cllm, batch, [f for f in findings if f.beat in {b.id for b in batch.beats}], say)
                crit.findings += c.findings
                crit.ran = True
                if c.overall:
                    crit.overall.setdefault("reviews", []).append(c.overall)
            except Exception as exc:   # a critic that cannot run must not lose a good plan
                res.log.append(f"critic unavailable: {exc}")
                say(f"The critic could not run ({str(exc)[:90]}); continuing with the validator only.")
        reviews = crit.overall.get("reviews") or []
        if reviews:
            crit.overall.update({k: reviews[0].get(k) for k in ("balance", "coherence", "summary") if reviews[0].get(k) is not None})
            scores = [r["coherence"] for r in reviews if isinstance(r.get("coherence"), (int, float))]
            if len(scores) > 1:
                crit.overall["coherence"] = round(sum(scores) / len(scores), 1)
        weak = _weak_beats(plan, findings, crit, first_problems if cycle == 0 else [])
        res.plan, res.findings, res.critique = plan, findings, crit
        if not weak or final:
            break
        res.repair_passes += 1
        res.repaired.append(list(weak))
        try:
            if units:
                plan = _repair_chapters(llm, plan, units, weak, sentences, words, say, stats, res)
            else:
                stats["repair_calls"] += 1
                plan, problems = repair_beats(llm, plan, weak, sentences, words, on_progress=say)
                res.problems += problems
        except Exception as exc:
            res.log.append(f"repair pass {cycle + 1} failed: {exc}")
            say(f"Repair pass {cycle + 1} failed ({str(exc)[:90]}); keeping the plan as it is.")
            break


# ---- long narrations ---------------------------------------------------------------------------------------------------

def _chunk_key(sentences: Sequence[Sentence], chunk: Chunk, n_chunks: int, style_guidance: str) -> str:
    """Identifies a chapter's request: the same script, cut the same way, with the same prompt and guidance, gives the same key."""
    blob = json.dumps([chunk.index, n_chunks, round(chunk.start, 2), round(chunk.end, 2), [s.text for s in sentences[chunk.first:chunk.last + 1]], style_guidance.strip(),
                       hashlib.sha1(director_prompt().encode("utf-8")).hexdigest()], ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:20]


def _load_checkpoint(folder: Optional[Path], chunk: Chunk, key: str) -> Optional[dict]:
    if folder is None:
        return None
    f = folder / f"chapter_{chunk.index:03d}.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data["payload"] if data.get("key") == key and isinstance(data.get("payload"), dict) else None
    except (OSError, ValueError, KeyError):
        return None


def _save_checkpoint(folder: Optional[Path], chunk: Chunk, key: str, payload: dict) -> None:
    if folder is None:
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"chapter_{chunk.index:03d}.json").write_text(json.dumps({"key": key, "payload": payload}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass   # a checkpoint is a convenience: never fail the plan over it


def _save_state(folder: Optional[Path], state: dict) -> None:
    """Where planning stopped, for a person reading the project folder (the saved results themselves are what resuming uses)."""
    if folder is None:
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "planning_state.json").write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def chunks_from_plan(plan: HybridPlan, sentences: Sequence[Sentence]) -> List[Chunk]:
    """The chapters of a plan that has them, as sentence ranges (empty for a plan without chapters)."""
    out: List[Chunk] = []
    for ch in plan.chapters:
        inside = [s.index for s in sentences if ch["start"] - 1e-6 <= (s.start + s.end) / 2 < ch["end"] + 1e-6]
        if inside:
            out.append(Chunk(int(ch["id"]), min(inside), max(inside), float(ch["start"]), float(ch["end"])))
    return out


def _chapter_plan(master: HybridPlan, chunk: Chunk) -> HybridPlan:
    """The chapter's beats as a plan of their own (global times), for the critic and for repair."""
    return HybridPlan(duration=chunk.end, beats=[b for b in master.beats if b.chapter == chunk.index], settings=dict(master.settings))


def _plan_long(words: Sequence[Word], llm: Any, sentences: Sequence[Sentence], chunks: List[Chunk], total: float, res: PlanResult, *, settings: Optional[Dict[str, Any]],
               style_guidance: str, critic_llm: Any, policy: str, max_repairs: int, on_progress: Callable[[str], None], checkpoint_dir: "str | Path | None") -> PlanResult:
    say = on_progress
    folder = Path(checkpoint_dir) if checkpoint_dir else None
    stats: Dict[str, Any] = {"chapters": len(chunks), "director_calls": 0, "checkpoint_hits": 0, "critic_calls": 0, "repair_calls": 0, "local_validations": 0, "local_fixes": 0}
    res.stats = stats
    beats: List[Beat] = []
    chapters: List[Dict[str, Any]] = []
    for chunk in chunks:
        key = _chunk_key(sentences, chunk, len(chunks), style_guidance)
        cached = _load_checkpoint(folder, chunk, key)
        if cached is not None:
            say(f"Chapter {chunk.index}/{len(chunks)}: reusing the saved plan.")
            stats["checkpoint_hits"] += 1
        else:
            stats["director_calls"] += 1
        got, title, probs, payload = plan_chunk(llm, sentences, words, chunk, len(chunks), beats, len(beats), settings=settings, style_guidance=style_guidance,
                                                on_progress=say, cached=cached)
        _save_checkpoint(folder, chunk, key, payload)
        beats += got
        res.problems += probs
        last = getattr(llm, "last", None) or {}
        who = "saved result" if cached is not None else (f"{last.get('provider', '?')}/{last.get('model', '?')}" if last.get("provider") not in (None, "cache") else "saved result")
        say(f"Chapter {chunk.index}/{len(chunks)} · Director: {who} ✓ · Validation: local ✓")
        _save_state(folder, {"chapters": {str(c.index): ("director done" if c.index <= chunk.index else "not started") for c in chunks}, "stage": "directing"})
        chapters.append({"id": chunk.index, "title": title, "start": chunk.start, "end": chunk.end})
    plan = HybridPlan(duration=round(float(total), 3), beats=beats, settings=dict(settings or {}), chapters=chapters)
    derive_cameras(plan)   # once, over the whole timeline: the camera and the overlays flow across chapter boundaries
    _save_state(folder, {"chapters": {str(c.index): "director done" for c in chunks}, "stage": "reviewing"})
    _review(plan, chunks, sentences, words, llm, critic_llm or llm, say, res, policy=policy, max_cycles=max_repairs, first_problems=list(res.problems))
    _finish(res, llm)
    _save_state(folder, {"chapters": {str(c.index): "locked" for c in chunks}, "stage": "complete",
                         "critic_calls": res.stats.get("critic_calls", 0), "repair_calls": res.stats.get("repair_calls", 0)})
    return res


def _repair_chapters(llm: Any, plan: HybridPlan, chunks: List[Chunk], weak: Dict[str, List[str]], sentences: Sequence[Sentence], words: Sequence[Word],
                     say: Callable[[str], None], stats: Dict[str, Any], res: PlanResult) -> HybridPlan:
    """Repair the weak beats chapter by chapter, each request carrying only its own chapter's narration; then splice the answers back
    (times, ids and chapters never change) and derive the cameras again over the whole timeline."""
    by_id = {b.id: b for b in plan.beats}
    new_beats = {b.id: b for b in plan.beats}
    for chunk in chunks:
        mine = {bid: issues for bid, issues in weak.items() if by_id.get(bid) is not None and by_id[bid].chapter == chunk.index}
        if not mine:
            continue
        sub = _chapter_plan(plan, chunk)
        local = local_sentences(sentences, chunk.first, chunk.last)
        try:
            stats["repair_calls"] += 1
            fixed, problems = repair_beats(llm, sub, mine, local, words, on_progress=say)
        except Exception as exc:
            res.log.append(f"repair of chapter {chunk.index} failed: {exc}")
            say(f"Repair of chapter {chunk.index} failed ({exc}); keeping it as it is.")
            continue
        res.problems += problems
        for b in fixed.beats:
            if b.id in mine:
                b.chapter = chunk.index
                new_beats[b.id] = b
    out = HybridPlan(duration=plan.duration, beats=[new_beats[b.id] for b in plan.beats], settings=dict(plan.settings), version=plan.version, chapters=list(plan.chapters))
    derive_cameras(out)
    return out


def repair_errors(plan: HybridPlan, words: Sequence[Word], llm: Any, *, script: Optional[str] = None, duration: Optional[float] = None,
                  max_repairs: int = DEFAULT_REPAIR_CYCLES, on_progress: Optional[Callable[[str], None]] = None) -> PlanResult:
    """For a plan that already exists (loaded from a file, or edited): send ONLY the beats that have validator errors back to the Director
    (an unfindable place, an unsupported source, footage too short ...), at most `max_repairs` times. No critic, no new plan."""
    say = on_progress or (lambda m: None)
    total = float(duration) if duration else plan.duration
    sentences = build_sentences(words, script, total)
    res = PlanResult(plan=plan, sentences=sentences)
    chunks = chunks_from_plan(plan, sentences)
    res.stats = {"chapters": len(chunks) or 1, "repair_calls": 0}
    for pass_no in range(max_repairs + 1):
        findings = validate(plan)
        n, notes = local_fix(plan, findings)
        if n:
            res.stats["local_fixes"] = res.stats.get("local_fixes", 0) + n
            res.log += notes
            findings = validate(plan)
        res.plan, res.findings = plan, findings
        weak = _weak_beats(plan, findings, critic_mod.Critique(), [])
        if not weak or pass_no == max_repairs:
            break
        res.repair_passes += 1
        res.repaired.append(list(weak))
        try:
            if len(chunks) > 1:
                plan = _repair_chapters(llm, plan, chunks, weak, sentences, words, say, res.stats, res)
            else:
                res.stats["repair_calls"] += 1
                plan, problems = repair_beats(llm, plan, weak, sentences, words, on_progress=say)
                res.problems += problems
        except Exception as exc:
            res.log.append(f"repair pass {pass_no + 1} failed: {exc}")
            say(f"Repair pass {pass_no + 1} failed ({exc}).")
            break
    return res


# ---- persistence ---------------------------------------------------------------------------------------------------

def save_bundle(folder: "str | Path", result: PlanResult) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    result.plan.save(folder / "plan.json")
    (folder / "plan_report.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_plan(folder: "str | Path") -> Optional[HybridPlan]:
    p = Path(folder) / "plan.json"
    return HybridPlan.load(p) if p.is_file() else None
