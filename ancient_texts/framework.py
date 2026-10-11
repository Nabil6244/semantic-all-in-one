"""Narrative framework: roles, presets and the script map.

A script is the narrator's text, exactly as recorded. Its structure comes from a SCRIPT MAP that tags each sentence with a
role (written by the script prompt, or by hand) -- never from the script's words, so any language works. The framework
checks the map; it never rewrites the script.

Roles (each optional unless the preset or the evidence requires it):
  hook -> provenance -> evidence (1..n sections) -> counterargument -> strongest_finding -> synthesis -> conclusion
  plus `transition` and `cta` anywhere. `counterargument` is REQUIRED whenever a linked claim is an interpretation or disputed.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from . import language as L
from .claims import SENTENCE_ID, Ledger, check_wording
from .issues import Issue, ValidationError

ROLES = ("hook", "provenance", "evidence", "counterargument", "strongest_finding", "synthesis", "conclusion",
         "transition", "cta")
ORDERED_ROLES = ("hook", "provenance", "evidence", "counterargument", "strongest_finding", "synthesis", "conclusion")
NON_FACTUAL = ("transition", "rhetorical", "question", "cta")


@dataclasses.dataclass(frozen=True)
class Preset:
    name: str
    min_evidence_sections: int
    max_evidence_sections: Optional[int]      # None: no upper bound
    note: str


PRESETS: Dict[str, Preset] = {
    "adaptive": Preset("adaptive", 1, None, "default: as many evidence sections as the subject and the evidence need"),
    "reference_inspired": Preset("reference_inspired", 3, 5,
                                 "the reference's shape: 3-5 evidence loops (setup, what the text says, the overlooked "
                                 "detail, who studied it, how to check it, payoff); a soft target, not a template"),
    "single_thread": Preset("single_thread", 1, 2, "one line of argument"),
    "survey": Preset("survey", 3, None, "many short evidence sections"),
}
CUE_TARGET_S = (40.0, 60.0)        # reference observation; a soft target for evaluation only
CUE_MAX_GAP_S = 90.0


@dataclasses.dataclass(frozen=True)
class ScriptSentence:
    id: str
    text: str
    hash: str
    role: str
    section: str = ""
    claim_ids: tuple = ()
    non_factual: str = ""
    cue: bool = False
    opens: str = ""
    resolves: str = ""


@dataclasses.dataclass(frozen=True)
class ScriptMap:
    language: str
    sentences: tuple
    preset: str = "adaptive"

    def by_id(self) -> Dict[str, ScriptSentence]:
        return {s.id: s for s in self.sentences}

    def text(self) -> str:
        return " ".join(s.text for s in self.sentences)


def build_script_map(script: str, annotations: Union[dict, None] = None, *, preset: str = "adaptive") -> Tuple[ScriptMap, List[Issue]]:
    """Pair the script's sentences with their annotations (matched in order by text fingerprint). The script is the truth:
    an annotation whose text is not in the script is reported, a script sentence without annotation becomes 'unassigned'."""
    issues: List[Issue] = []
    sentences = L.split_sentences(script)
    ann = list((annotations or {}).get("sentences") or [])
    if preset not in PRESETS:
        raise ValidationError("script map", [f"unknown preset {preset!r} (one of {sorted(PRESETS)})"])
    lang = str((annotations or {}).get("language") or "") or L.detect_language(script)
    problems: List[str] = []
    for i, a in enumerate(ann):
        if not isinstance(a, dict):
            problems.append(f"sentences[{i}] must be an object")
            continue
        if a.get("role") not in ROLES:
            problems.append(f"sentences[{i}]: role {a.get('role')!r} must be one of {ROLES}")
        if a.get("id") and not SENTENCE_ID.match(str(a["id"])):
            problems.append(f"sentences[{i}]: malformed id {a['id']!r}")
        nf = a.get("non_factual") or ""
        if nf and nf not in NON_FACTUAL:
            problems.append(f"sentences[{i}]: non_factual {nf!r} must be one of {NON_FACTUAL}")
    if problems:
        raise ValidationError("script map", problems)

    pending = [(L.sentence_hash(str(a.get("text") or "")), a) for a in ann if isinstance(a, dict)]
    out: List[ScriptSentence] = []
    cursor = 0
    for n, text in enumerate(sentences, start=1):
        h = L.sentence_hash(text)
        match = None
        for k in range(cursor, len(pending)):
            if pending[k][0] == h:
                match, cursor = pending[k][1], k + 1
                break
        sid = str(match.get("id")) if match and match.get("id") else f"S-{n:03d}"
        if match is None:
            out.append(ScriptSentence(id=sid, text=text, hash=h, role="unassigned"))
            if ann:
                issues.append(Issue("unannotated_sentence", "review", f"{sid} has no annotation: {text[:60]}", sid))
            continue
        out.append(ScriptSentence(id=sid, text=text, hash=h, role=str(match["role"]), section=str(match.get("section") or ""),
                                  claim_ids=tuple(str(c) for c in (match.get("claim_ids") or ())),
                                  non_factual=str(match.get("non_factual") or ""), cue=bool(match.get("cue")),
                                  opens=str(match.get("opens") or ""), resolves=str(match.get("resolves") or "")))
    used ={L.sentence_hash(s.text) for s in out if s.role != "unassigned"}
    for h, a in pending:
        if h not in used:
            issues.append(Issue("script_mismatch", "hard",
                                f"annotation {a.get('id') or '?'} quotes a sentence that is not in the script (edited after the map "
                                f"was made?): {str(a.get('text') or '')[:60]}", str(a.get("id") or "")))
    ids = [s.id for s in out]
    dupes = {i for i in ids if ids.count(i) > 1}
    for d in sorted(dupes):
        issues.append(Issue("duplicate_sentence_id", "hard", f"sentence id {d} is used more than once", d))
    return ScriptMap(language=lang, sentences=tuple(out), preset=preset), issues


def load_annotations(path: Union[str, Path]) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValidationError(str(path), ["script map file not found"]) from None
    except json.JSONDecodeError as exc:
        raise ValidationError(str(path), [f"not valid JSON: {exc}"]) from None
    if not isinstance(data, dict):
        raise ValidationError(str(path), ["a script map is a JSON object with 'sentences'"])
    return data


def evidence_sections(smap: ScriptMap) -> List[str]:
    """Evidence sections in order: by explicit `section` label, else by runs of consecutive evidence sentences."""
    out: List[str] = []
    run, in_run = 0, False
    for s in smap.sentences:
        if s.role == "evidence":
            if s.section:
                key = s.section
            else:
                if not in_run:
                    run += 1
                key = f"run{run}"
            if key not in out:
                out.append(key)
            in_run = True
        elif s.role not in ("transition", "cta"):
            in_run = False
    return out


def estimated_times(smap: ScriptMap, timings: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Start time of each sentence: real timings when given (sentence id -> seconds), else a words-per-second estimate."""
    if timings:
        return dict(timings)
    wps = L.words_per_second(smap.language)
    t, out = 0.0, {}
    for s in smap.sentences:
        out[s.id] = t
        t += max(1, len(s.text.split())) / wps
    return out


def check_structure(smap: ScriptMap, ledger: Optional[Ledger] = None, *, timings: Optional[Dict[str, float]] = None) -> List[Issue]:
    issues: List[Issue] = []
    preset = PRESETS[smap.preset]
    roles = [s.role for s in smap.sentences]
    if not smap.sentences:
        return [Issue("empty_script", "hard", "the script has no sentences")]
    if "unassigned" in roles and all(r == "unassigned" for r in roles):
        return [Issue("no_script_map", "review", "no script map: structure cannot be checked (roles are never guessed from the words)")]

    first_role = next((r for r in roles if r not in ("transition",)), "")
    if first_role != "hook":
        issues.append(Issue("missing_hook", "hard", "the script must open with a hook (a contrast or a question and a promise)"))
    if "conclusion" not in roles:
        issues.append(Issue("missing_conclusion", "hard", "the script needs a conclusion that resolves the opening question"))
    elif any(r in ORDERED_ROLES and r != "conclusion" for r in roles[roles.index("conclusion"):]):
        issues.append(Issue("conclusion_not_last", "soft", "material after the conclusion: the conclusion should close the film"))
    sections = evidence_sections(smap)
    if len(sections) < preset.min_evidence_sections:
        sev = "hard" if not sections else "soft"
        issues.append(Issue("evidence_sections", sev, f"{len(sections)} evidence section(s); preset '{preset.name}' expects at "
                            f"least {preset.min_evidence_sections}"))
    if preset.max_evidence_sections is not None and len(sections) > preset.max_evidence_sections:
        issues.append(Issue("evidence_sections", "soft", f"{len(sections)} evidence sections; preset '{preset.name}' suggests at "
                            f"most {preset.max_evidence_sections}"))
    if "provenance" not in roles:
        issues.append(Issue("no_provenance", "soft", "no provenance section (where the text survived, how it is known)"))

    # order: hook before evidence; counterargument after some evidence
    idx = {r: i for i, r in reversed(list(enumerate(roles)))}
    if "hook" in idx and "evidence" in idx and idx["evidence"] < idx["hook"]:
        issues.append(Issue("order", "soft", "evidence appears before the hook"))
    if "counterargument" in idx and "evidence" in idx and idx["counterargument"] < idx["evidence"]:
        issues.append(Issue("order", "soft", "the counterargument comes before any evidence"))

    # counterargument is required when the evidence includes interpretation or dispute
    if ledger is not None:
        contested = sorted({cid for s in smap.sentences for cid in s.claim_ids
                            if ledger.claim(cid) is not None and ledger.claim(cid).status in ("interpretation", "disputed")})
        if contested and "counterargument" not in roles:
            issues.append(Issue("missing_counterargument", "hard",
                                f"claims {', '.join(contested)} are interpretation/disputed: the script needs a counterargument "
                                "or limitations section"))

    # open questions must be paid off
    opened = {s.opens: s.id for s in smap.sentences if s.opens}
    resolved = {s.resolves for s in smap.sentences if s.resolves}
    for q, sid in opened.items():
        if q not in resolved:
            issues.append(Issue("unresolved_question", "soft", f"question {q} opened in {sid} is never resolved", sid))
    if not opened and any(s.role == "hook" for s in smap.sentences):
        issues.append(Issue("no_opening_question", "review", "the hook does not mark an opening question (opens: Q1)"))

    # claim links and wording
    for s in smap.sentences:
        if s.role == "unassigned":
            continue
        if ledger is not None:
            for cid in s.claim_ids:
                c = ledger.claim(cid)
                if c is None:
                    issues.append(Issue("invalid_claim_reference", "hard", f"{s.id} links unknown claim {cid!r}", s.id))
                    continue
                if c.sentence_ids and s.id not in c.sentence_ids:
                    issues.append(Issue("link_mismatch", "soft", f"{s.id} links {cid}, but {cid} does not list {s.id}", s.id))
                issues.extend(check_wording(ledger, cid, s.text, smap.language, s.id))
        if not s.claim_ids and not s.non_factual and s.role not in ("transition", "cta") and L.looks_factual(s.text, smap.language):
            issues.append(Issue("unlinked_factual_sentence", "review",
                                f"{s.id} looks factual but links no claim and is not marked non-factual: {s.text[:70]}", s.id))

    # curiosity cues (soft, measured on real or estimated time)
    times = estimated_times(smap, timings)
    cue_times = [times[s.id] for s in smap.sentences if s.cue]
    total = times[smap.sentences[-1].id] if smap.sentences else 0.0
    if total > 2 * CUE_MAX_GAP_S:
        marks = [0.0] + cue_times + [total]
        gaps = [b - a for a, b in zip(marks, marks[1:])]
        if gaps and max(gaps) > CUE_MAX_GAP_S:
            issues.append(Issue("cue_spacing", "soft", f"longest stretch without a curiosity cue ≈{max(gaps):.0f} s "
                                f"(reference: one every {CUE_TARGET_S[0]:.0f}-{CUE_TARGET_S[1]:.0f} s)"))
    return issues


def cue_intervals(smap: ScriptMap, timings: Optional[Dict[str, float]] = None) -> List[float]:
    times = estimated_times(smap, timings)
    cue_times = [times[s.id] for s in smap.sentences if s.cue]
    return [b - a for a, b in zip(cue_times, cue_times[1:])]
