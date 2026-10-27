"""Medical-claim guard: rule-based flags for narration that needs human review. It never judges whether a claim is TRUE; it only notices
patterns that must not go out unreviewed (unsourced statistics, causal and absolute wording, medication/supplement advice, preliminary
research wording) and labels visuals that could be mistaken for clinical imagery. Nothing here invents facts."""
from __future__ import annotations
import re
from typing import Dict, List

STAT_RE = re.compile(r"(\d[\d,.]*\s?(?:%|(?:percent|per cent|mg/dl|mg|mmhg|mmol|bpm|million|billion|thousand|years?|times|fold)\b)|\b(one|two|three|four|five|1 in|one in)\s+in\s+(\d+|two|three|four|five|ten))", re.I)
NUM_RE = re.compile(r"\d[\d,.]*")
CAUSAL_RE = re.compile(r"\b(causes?|caused by|leads? to|results? in|triggers?|prevents?|reverses?|cures?|heals?|fixes?)\b", re.I)
ABSOLUTE_RE = re.compile(r"\b(always|never|guarantee[sd]?|proven|proves?|100 ?%|everyone|nobody|miracle|cure[sd]?)\b", re.I)
MED_RE = re.compile(r"\b(stop taking|instead of (your )?(medic\w+|pills?|insulin|statins?)|replace (your )?(medic\w+|pills?|insulin|statins?)|without (a )?doctor|dose|dosage|mg\b)", re.I)
SUPP_RE = re.compile(r"\b(supplements?|vitamin|herbal|detox|superfood|natural remed\w+)\b", re.I)
PRELIM_RE = re.compile(r"\b(early (study|research|findings?)|pilot|in mice|in rats|animal stud\w+|preliminary|petri dish|cell cultures?|small study|may help|might|could help|hypothes\w+)\b", re.I)
STUDY_RE = re.compile(r"\b(study|studies|trial|research(ers)?|meta-?analysis|according to|evidence|survey|cohort)\b", re.I)
MYTH_RE = re.compile(r"\b(myth|claim(s|ed)?|rumou?r|viral|they say|people say|is it true|debunk\w*)\b", re.I)

def analyze(text: str, sources: List[dict] | None = None) -> Dict:
    """-> {"flags": [{code, severity, message}], "evidence_level": established|preliminary|unsourced|none, "has_stat": bool, "numbers": [...]}.
    `sources` = source dicts attached to the scene by the script author (title/citation/url/year/population...)."""
    sources = sources or []; flags: List[dict] = []
    def flag(code, severity, msg): flags.append({"code": code, "severity": severity, "message": msg})
    has_stat = bool(STAT_RE.search(text)); has_study = bool(STUDY_RE.search(text)); prelim = bool(PRELIM_RE.search(text))
    if has_stat and not sources: flag("stat_unsourced", "review", "Statistic with no source attached: add the study, population, units and year, or remove the number.")
    if has_stat and sources and not any(s.get("population") or s.get("context") for s in sources):
        flag("stat_context_missing", "note", "Source attached but no population or context recorded for the statistic.")
    if CAUSAL_RE.search(text): flag("causal_wording", "review", "Causal or outcome wording: check the source supports causation, not only association.")
    if ABSOLUTE_RE.search(text): flag("absolute_wording", "review", "Absolute or guarantee wording: soften or support it.")
    if MED_RE.search(text): flag("medication_advice", "high", "Medication or dosing wording: needs medical review and a clear 'talk to your doctor' framing.")
    if SUPP_RE.search(text): flag("supplement_claim", "review", "Supplement claim: do not imply it replaces prescribed treatment; check the evidence level.")
    if prelim: flag("preliminary_research", "note", "Preliminary research (animal, cell, pilot or hypothesis): present as preliminary, not established.")
    if has_study and not sources: flag("study_unsourced", "review", "Refers to research without naming it: attach the source.")
    level = "none"
    if has_study or has_stat: level = "preliminary" if prelim else ("established" if sources else "unsourced")
    return {"flags": flags, "evidence_level": level, "has_stat": has_stat, "has_study": has_study, "is_claim_or_myth": bool(MYTH_RE.search(text)),
            "numbers": NUM_RE.findall(text)}

ILLUSTRATIVE_3D = "3D illustration. Not clinical imagery."
def illustrative_label(kind: str) -> str:
    return ILLUSTRATIVE_3D if kind == "anatomy_3d" else ""
