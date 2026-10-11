"""Sources, claims and the claim ledger.

A ledger -- above all one written by an AI from the research prompt -- is a set of ASSERTIONS TO CHECK. Nothing here
proves a historical fact. The checks are deterministic and offline; they find what is missing, inconsistent or
overstated, and they keep apart:

  * whether a source exists           (Source.exists: unchecked | confirmed | not_found, and who said so)
  * whether it supports the claim     (Support.relation: direct | partial | context | contradicts | unchecked)
  * what the claim's evidence status is (Claim.status: documented | interpretation | disputed | reconstruction)
  * whether a person reviewed it      (Claim.review: unreviewed | reviewed | rejected, by whom, on what basis)

Nothing is ever filled in: a missing locator, credential or quotation stays missing and is reported.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Union

from . import language as L
from .issues import Issue, ValidationError

STATUSES = ("documented", "interpretation", "disputed", "reconstruction")
RELATIONS = ("direct", "partial", "context", "contradicts", "unchecked")
EXISTS = ("unchecked", "confirmed", "not_found")
REVIEW_STATES = ("unreviewed", "reviewed", "rejected")
SOURCE_KINDS = ("primary", "edition", "translation", "scholarship", "museum", "archive", "reference", "other")
SUPPORTING = ("direct", "partial")

CLAIM_ID = re.compile(r"^C-\d{3,}$")
SENTENCE_ID = re.compile(r"^S-\d{3,}$")
SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


@dataclasses.dataclass(frozen=True)
class Source:
    id: str
    kind: str
    citation: str
    exists: str = "unchecked"
    exists_checked_by: str = ""          # who/what set `exists` (a person's name, "catalogue lookup" ...)
    url: str = ""
    license: str = ""
    credential: str = ""                 # e.g. a scholar's post, ONLY as this source states it
    credential_locator: str = ""


@dataclasses.dataclass(frozen=True)
class Quote:
    text: str
    edition: str
    verified: bool = False               # true only when a person matched the text exactly against the edition
    verified_by: str = ""


@dataclasses.dataclass(frozen=True)
class Support:
    source_id: str
    locator: str = ""
    relation: str = "unchecked"
    quote: Optional[Quote] = None
    note: str = ""


@dataclasses.dataclass(frozen=True)
class Review:
    state: str = "unreviewed"
    by: str = ""
    date: str = ""
    basis: str = ""                      # what the reviewer actually looked at


@dataclasses.dataclass(frozen=True)
class Claim:
    id: str
    text: str
    status: str
    support: tuple = ()
    conflicts_with: tuple = ()
    limitations: str = ""
    review: Review = Review()
    sentence_ids: tuple = ()             # the exact script sentences this claim supports


@dataclasses.dataclass
class Ledger:
    sources: Dict[str, Source]
    claims: Dict[str, Claim]

    def claim(self, cid: str) -> Optional[Claim]:
        return self.claims.get(cid)


# ---------------------------------------------------------------- parsing (schema errors raise, with every problem)

def _req(d: dict, key: str, where: str, problems: List[str]) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        problems.append(f"{where}: missing '{key}'")
        return ""
    return v.strip()


def ledger_from_dict(data: dict) -> Ledger:
    problems: List[str] = []
    if not isinstance(data, dict):
        raise ValidationError("ledger", ["a ledger is a JSON object with 'sources' and 'claims'"])
    sources: Dict[str, Source] = {}
    for i, s in enumerate(data.get("sources") or []):
        where = f"sources[{i}]"
        if not isinstance(s, dict):
            problems.append(f"{where}: must be an object")
            continue
        sid = _req(s, "id", where, problems)
        if sid and not SOURCE_ID.match(sid):
            problems.append(f"{where}: malformed id {sid!r}")
        if sid in sources:
            problems.append(f"{where}: duplicate source id {sid!r}")
        kind = str(s.get("kind") or "")
        if kind not in SOURCE_KINDS:
            problems.append(f"{where} ({sid}): kind {kind!r} must be one of {SOURCE_KINDS}")
        exists = str(s.get("exists") or "unchecked")
        if exists not in EXISTS:
            problems.append(f"{where} ({sid}): exists {exists!r} must be one of {EXISTS}")
        citation = _req(s, "citation", where, problems)
        sources[sid] = Source(id=sid, kind=kind, citation=citation, exists=exists,
                              exists_checked_by=str(s.get("exists_checked_by") or ""), url=str(s.get("url") or ""),
                              license=str(s.get("license") or ""), credential=str(s.get("credential") or ""),
                              credential_locator=str(s.get("credential_locator") or ""))
    claims: Dict[str, Claim] = {}
    for i, c in enumerate(data.get("claims") or []):
        where = f"claims[{i}]"
        if not isinstance(c, dict):
            problems.append(f"{where}: must be an object")
            continue
        cid = _req(c, "id", where, problems)
        if cid and not CLAIM_ID.match(cid):
            problems.append(f"{where}: malformed id {cid!r} (expected C-001 style)")
        if cid in claims:
            problems.append(f"{where}: duplicate claim id {cid!r}")
        status = str(c.get("status") or "")
        if status not in STATUSES:
            problems.append(f"{where} ({cid}): unknown status {status!r} (one of {STATUSES})")
        text = _req(c, "text", where, problems)
        supports = []
        for j, sp in enumerate(c.get("support") or []):
            w2 = f"{where}.support[{j}]"
            if not isinstance(sp, dict):
                problems.append(f"{w2}: must be an object")
                continue
            rel = str(sp.get("relation") or "unchecked")
            if rel not in RELATIONS:
                problems.append(f"{w2}: relation {rel!r} must be one of {RELATIONS}")
            q = sp.get("quote")
            quote = None
            if q is not None:
                if not isinstance(q, dict) or not str(q.get("text") or "").strip():
                    problems.append(f"{w2}: a quote needs its exact text")
                else:
                    quote = Quote(text=str(q["text"]), edition=str(q.get("edition") or ""), verified=q.get("verified") is True,
                                  verified_by=str(q.get("verified_by") or ""))
            supports.append(Support(source_id=str(sp.get("source_id") or ""), locator=str(sp.get("locator") or "").strip(),
                                    relation=rel, quote=quote, note=str(sp.get("note") or "")))
        rv = c.get("review") or {}
        state = str(rv.get("state") or "unreviewed") if isinstance(rv, dict) else "unreviewed"
        if state not in REVIEW_STATES:
            problems.append(f"{where} ({cid}): review state {state!r} must be one of {REVIEW_STATES}")
        review = Review(state=state, by=str(rv.get("by") or ""), date=str(rv.get("date") or ""), basis=str(rv.get("basis") or "")) \
            if isinstance(rv, dict) else Review()
        sids = tuple(str(x) for x in (c.get("sentence_ids") or ()))
        for x in sids:
            if not SENTENCE_ID.match(x):
                problems.append(f"{where} ({cid}): malformed sentence id {x!r}")
        claims[cid] = Claim(id=cid, text=text, status=status, support=tuple(supports),
                            conflicts_with=tuple(str(x) for x in (c.get("conflicts_with") or ())),
                            limitations=str(c.get("limitations") or ""), review=review, sentence_ids=sids)
    if problems:
        raise ValidationError("ledger", problems)
    return Ledger(sources=sources, claims=claims)


def load_ledger(path: Union[str, Path]) -> Ledger:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValidationError(str(path), ["ledger file not found"]) from None
    except json.JSONDecodeError as exc:
        raise ValidationError(str(path), [f"not valid JSON: {exc}"]) from None
    return ledger_from_dict(data)


# ---------------------------------------------------------------- checks

def _supporting(ledger: Ledger, claim: Claim) -> List[Support]:
    """Supports that actually back the claim: a known source that is not known to be missing, relation direct/partial,
    with a locator."""
    out = []
    for sp in claim.support:
        src = ledger.sources.get(sp.source_id)
        if src is None or src.exists == "not_found":
            continue
        if sp.relation in SUPPORTING and sp.locator:
            out.append(sp)
    return out


def check_ledger(ledger: Ledger) -> List[Issue]:
    """Ledger-internal checks (no script needed)."""
    issues: List[Issue] = []
    for c in ledger.claims.values():
        documented = c.status == "documented"
        if not c.support:
            sev = "hard" if documented else "review"
            issues.append(Issue("unsupported_claim", sev, f"{c.id} has no source at all"
                                + (" but is marked documented" if documented else ""), c.id))
        for sp in c.support:
            src = ledger.sources.get(sp.source_id)
            if src is None:
                issues.append(Issue("invalid_source_reference", "hard", f"{c.id} cites unknown source {sp.source_id!r}", c.id))
                continue
            if src.exists == "not_found":
                issues.append(Issue("source_not_found", "hard", f"{c.id} cites {src.id}, which is recorded as not found"
                                    + (f" (by {src.exists_checked_by})" if src.exists_checked_by else ""), c.id))
            elif src.exists == "unchecked":
                issues.append(Issue("source_existence_unchecked", "review",
                                    f"{c.id}: nobody has confirmed that source {src.id} exists ({src.citation})", c.id))
            if not sp.locator:
                issues.append(Issue("missing_locator", "hard" if documented else "review",
                                    f"{c.id} cites {sp.source_id} without a page, verse, fragment or section", c.id))
            if sp.relation == "contradicts":
                issues.append(Issue("source_contradicts_claim", "hard" if documented else "review",
                                    f"{c.id}: source {sp.source_id} contradicts the claim", c.id))
            elif sp.relation in ("context", "unchecked"):
                issues.append(Issue("source_does_not_support", "hard" if documented and not _supporting(ledger, c) else "review",
                                    f"{c.id}: {sp.source_id} is cited but its support is '{sp.relation}' -- a source existing "
                                    "is not the same as it supporting the claim", c.id))
            if sp.quote is not None and not (sp.quote.verified and sp.quote.edition and sp.locator):
                issues.append(Issue("unverified_quote", "review",
                                    f"{c.id}: quotation from {sp.source_id} is not verified against a named edition and "
                                    "locator; it may not be shown as a quotation", c.id))
        if documented and c.support and not _supporting(ledger, c):
            issues.append(Issue("documented_without_support", "hard",
                                f"{c.id} is marked documented but no cited source directly or partly supports it with a locator",
                                c.id))
        rel = {sp.relation for sp in c.support if sp.source_id in ledger.sources}
        if "contradicts" in rel and rel & set(SUPPORTING):
            issues.append(Issue("conflicting_sources", "hard" if documented else "review",
                                f"{c.id}: sources disagree ({', '.join(sorted(rel))}); keep the disagreement in the script", c.id))
        for other_id in c.conflicts_with:
            other = ledger.claims.get(other_id)
            if other is None:
                issues.append(Issue("invalid_claim_reference", "hard", f"{c.id} conflicts_with unknown claim {other_id!r}", c.id))
            elif documented and other.status == "documented":
                issues.append(Issue("conflicting_documented_claims", "hard",
                                    f"{c.id} and {other_id} conflict but are both marked documented", c.id))
        if c.review.state == "reviewed":
            if not c.review.by:
                issues.append(Issue("review_without_reviewer", "hard", f"{c.id} is marked reviewed but not by whom", c.id))
            if not _supporting(ledger, c) and c.status != "reconstruction":
                issues.append(Issue("reviewed_without_evidence", "hard",
                                    f"{c.id} is marked reviewed but has no supporting source with a locator", c.id))
        elif c.review.state == "unreviewed" and c.status != "reconstruction":
            issues.append(Issue("unreviewed_claim", "review", f"{c.id} has not been reviewed by a person", c.id))
        if c.status == "disputed":
            issues.append(Issue("disputed_claim", "review", f"{c.id} is disputed: a person should judge the wording", c.id))
        if c.status in ("documented", "interpretation") and len({sp.source_id for sp in _supporting(ledger, c)}) == 1:
            issues.append(Issue("single_source", "review", f"{c.id} rests on one source", c.id))
    return issues


def check_wording(ledger: Ledger, claim_id: str, sentence: str, lang: str, sentence_id: str = "") -> List[Issue]:
    """Does the sentence's wording match the claim's status? Interpretations and disputes must not read as settled fact."""
    c = ledger.claims.get(claim_id)
    ref = sentence_id or claim_id
    if c is None:
        return [Issue("invalid_claim_reference", "hard", f"{ref} links unknown claim {claim_id!r}", ref)]
    if c.status not in ("interpretation", "disputed"):
        return []
    if not L.supported_language(lang):
        return [Issue("wording_unchecked_language", "review",
                      f"{ref}: {claim_id} is {c.status}; language {lang!r} has no word list, so a person must check the "
                      "sentence is qualified", ref)]
    absolutes, hedges = L.absolutes_in(sentence, lang), L.hedges_in(sentence, lang)
    if absolutes and not hedges:
        return [Issue("interpretation_stated_as_fact", "hard",
                      f"{ref}: {claim_id} is {c.status} but the sentence states it as settled ({', '.join(absolutes)})", ref)]
    if not hedges:
        return [Issue("needs_qualification", "hard" if c.status == "disputed" else "soft",
                      f"{ref}: {claim_id} is {c.status}; the sentence carries no qualifier (e.g. 'according to', "
                      "'some scholars')", ref)]
    return []


def quote_for_card(ledger: Ledger, claim_id: str) -> Optional[tuple]:
    """(quote text, edition, source citation, locator) only when a person verified the quotation; else None."""
    c = ledger.claims.get(claim_id)
    if c is None:
        return None
    for sp in _supporting(ledger, c):
        q = sp.quote
        if q is not None and q.verified and q.edition and sp.locator:
            return q.text, q.edition, ledger.sources[sp.source_id].citation, sp.locator
    return None


def credential_for_card(ledger: Ledger, source_id: str) -> Optional[str]:
    """A credential only as a confirmed source states it, with a locator; else None (the card shows the name only)."""
    src = ledger.sources.get(source_id)
    if src is None or not src.credential or not src.credential_locator or src.exists != "confirmed":
        return None
    return src.credential


def sources_markdown(ledger: Ledger) -> str:
    """The verification sheet exported next to the video: what each claim rests on and its state. It says 'not verified'
    wherever nobody verified, and never calls the ledger proof."""
    lines = ["# Sources and claims", "",
             "This sheet lists what the script asserts and what each assertion rests on. It is a checklist, not proof: "
             "claims marked 'unreviewed' have not been checked by a person.", ""]
    for c in sorted(ledger.claims.values(), key=lambda c: c.id):
        lines.append(f"## {c.id} — {c.status} — review: {c.review.state}"
                     + (f" by {c.review.by}" if c.review.by else ""))
        lines.append(c.text)
        if c.limitations:
            lines.append(f"*Limitations:* {c.limitations}")
        for sp in c.support:
            src = ledger.sources.get(sp.source_id)
            cite = src.citation if src else f"(unknown source {sp.source_id})"
            exists = src.exists if src else "unknown"
            lines.append(f"- {cite} — {sp.locator or 'NO LOCATOR'} — supports: {sp.relation} — source existence: {exists}")
        lines.append("")
    return "\n".join(lines)


def report(issues: Sequence[Issue]) -> Dict[str, List[dict]]:
    """Group issues by what a reviewer has to do about them."""
    groups = {
        "unsupported_claims": ("unsupported_claim", "documented_without_support", "reviewed_without_evidence"),
        "missing_locators": ("missing_locator",),
        "invalid_sources": ("invalid_source_reference", "source_not_found", "invalid_claim_reference"),
        "source_does_not_support": ("source_does_not_support", "source_contradicts_claim"),
        "conflicting_sources": ("conflicting_sources", "conflicting_documented_claims"),
        "unreviewed_claims": ("unreviewed_claim", "review_without_reviewer", "source_existence_unchecked"),
        "wording_vs_evidence": ("interpretation_stated_as_fact", "needs_qualification", "wording_unchecked_language"),
        "quotes_without_verified_text": ("unverified_quote", "quote_not_verified"),
        "credentials_without_backing": ("unbacked_credential",),
        "needs_careful_qualification": ("disputed_claim", "single_source"),
        "unlinked_factual_sentences": ("unlinked_factual_sentence",),
    }
    out: Dict[str, List[dict]] = {k: [] for k in groups}
    for i in issues:
        for k, codes in groups.items():
            if i.code in codes:
                out[k].append(i.to_dict())
    return out


def watch_list_as_claims(items: Iterable) -> List[Issue]:
    """A pack's research watch-list as open review items: they stay open until a ledger claim with evidence covers them."""
    return [Issue("open_research_question", "review", f"{w.id}: {w.topic} -- {w.prompt}", w.id) for w in items]
