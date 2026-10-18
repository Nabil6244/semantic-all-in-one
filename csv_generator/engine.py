"""Rule-based local scene planner.

HONEST SCOPE. This is NOT a language model. It splits the script at sentence boundaries into narration-sized scenes (no cap on the
number of scenes), pulls content keywords from each scene, and picks an asset type from simple, inspectable rules (places, space,
archival/historical, abstract vs concrete wording, variety). The result is a reliable, schema-correct *starting plan* for the user to
review, not a semantic understanding of the script: queries are keyword-based, ambiguity is not resolved, and creative visual
direction is limited. A local model could be added by implementing ``Backend`` (``plan_scenes``) and passing it to ``generate``.

Learning data is used only through ``learning.packages.active_package(scope)`` -> approved rules for the EXACT scope; with no
package (or an empty ledger / no network) the plan is the same rule-based plan. Nothing here makes a network request.
"""

from __future__ import annotations

import csv
import io
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .validate import Issue, validate_rows

SUPPORTED_STYLES = {
    "normal": "Normal",
    "enoch_template": "Enoch Template",
    "overscaled": "Overscaled",
    "exp_solar": "Exp Solar",
}
COLUMNS = ("scene_number", "script_segment", "asset_type", "prompt")      # accepted as-is by all four supported workflows
UNSUPPORTED_STYLES = {
    "pakmap": "pakMap rows are timed to the narrator's words and need place data; use its own Copy-prompt / Plan workflow.",
    "hybrid": "Hybrid beats are timed to the voiceover (map/footage/cards); use its own planner or prompt.",
    "starmap": "StarMap beat CSVs need verified astronomy data per row; use its own planner.",
    "whatif": "What If shot CSVs need a shot list with assets and textures; What If has its own automatic planner.",
    "weather": "Weather plans need live data layers; Weather has a no-CSV script-to-video mode.",
}
_MODE = {"normal": "normal", "enoch_template": "normal", "overscaled": "overscaled", "exp_solar": "overscaled"}
ALL_TYPES = ("stock_video", "stock_image", "image", "video", "youtube_video", "nasa_video", "archive_video", "map")

_STOP = frozenset("the a an and or but of to in on at by for with from into over under about as is are was were be been it its this that these "
                  "those he she they them his her their we you i our your not no so than then there here have has had will would could "
                  "should can may might do does did what which who whom when where why how all any each more most some such only also "
                  "just very".split())
_SPACE = re.compile(r"\b(space|planet|planets|galaxy|galaxies|nebula|orbit|astronaut|moon|mars|jupiter|saturn|solar system|telescope|comet|asteroid|satellite|nasa|rocket|star|stars)\b", re.I)
_ARCHIVE = re.compile(r"\b(18\d\d|19[0-8]\d|ancient|medieval|empire|war|wartime|century|historic|history|archive|archival|vintage|old photograph|decades ago)\b", re.I)
_ABSTRACT = re.compile(r"\b(idea|concept|theory|meaning|truth|power|fear|hope|freedom|future|mystery|secret|question|why|how|imagine|think|believe)\b", re.I)
_ACTION = re.compile(r"\b(run|runs|ran|walk|fly|flies|flew|build|built|fight|fought|move|moved|crash|crashed|fall|fell|grow|grew|burn|burned|flow|flowed|race|raced|explode|exploded|travel|traveled)\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+|\n{2,}")


@dataclass
class GenerationOptions:
    target_words: int = 45                 # scene size the grouper aims for
    max_words: int = 80                    # hard ceiling per scene (long sentences are split at clauses)
    enabled_types: Sequence[str] = ("stock_video", "stock_image")     # asset types the plan may use (free sources by default)
    max_same_type_run: int = 3             # variety: at most this many consecutive scenes of one asset type


@dataclass
class GenerationResult:
    style: str
    columns: Sequence[str]
    rows: List[Dict[str, str]]
    issues: List[Issue] = field(default_factory=list)
    applied_knowledge: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    cancelled: bool = False
    informational: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.cancelled and bool(self.rows) and not any(i.severity == "error" for i in self.issues)

    @property
    def csv_text(self) -> str:
        return to_csv_text(self.columns, self.rows)


class Cancelled(Exception):
    pass


class Backend:
    """Seam for a future packaged local model: return one dict per scene with script_segment, asset_type, prompt."""

    def plan_scenes(self, narrations: List[str], opts: GenerationOptions, tuning: "Tuning", check: Callable[[], None],
                    progress: Callable[[float, str], None]) -> List[Dict[str, str]]:
        raise NotImplementedError


@dataclass
class Tuning:
    avoid_types: set = field(default_factory=set)
    max_run: int = 3
    target_scale: float = 1.0
    target_cap: Optional[int] = None
    applied: List[str] = field(default_factory=list)
    informational: List[str] = field(default_factory=list)     # approved rules this engine cannot (or may not) apply


def style_scope_mode(style: str) -> str:
    return _MODE.get(style, "normal")


def knowledge_tuning(scope: Optional[str], opts: GenerationOptions, root=None) -> Tuning:
    """Approved, validated rules of the exact style scope -> planner tuning. Missing/invalid package or no scope -> defaults."""
    t = Tuning(max_run=opts.max_same_type_run)
    if not scope:
        return t
    try:
        from learning import packages
        from learning.assets import canonical_source
        pkg = packages.active_package(scope, root)
    except Exception:
        return t
    from datetime import datetime, timezone
    for r in (pkg or {}).get("rules", []):
        if r.get("status") != "approved":
            continue
        if r.get("expires_at"):
            try:
                exp = datetime.fromisoformat(str(r["expires_at"]))
                if (exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)) < datetime.now(timezone.utc):
                    t.informational.append(f"{r['id']}: expired, ignored")
                    continue
            except ValueError:
                continue
        if r["kind"] == "variety_run":
            t.max_run = min(t.max_run, int(r["param"]))
            t.applied.append(f"{r['id']}: at most {int(r['param'])} same-type scenes in a row")
        elif r["kind"] == "pacing_target":
            t.target_cap = int(r["param"]) if t.target_cap is None else min(t.target_cap, int(r["param"]))
            t.applied.append(f"{r['id']}: scene size capped at {int(r['param'])} words")
        elif r["kind"] == "asset_type_failure" and canonical_source(r.get("asset_type")):
            t.avoid_types.add(r["asset_type"])
            t.applied.append(f"{r['id']}: avoid {r['asset_type']}")
        elif r["id"] == "tag-repetitive_scenes":
            t.max_run = min(t.max_run, 2)
            t.applied.append(f"{r['id']}: stricter variety")
        elif r["id"] == "tag-poor_pacing" or r["id"] == "cat-pacing":
            t.target_scale = min(t.target_scale, 0.8)
            t.applied.append(f"{r['id']}: shorter scenes")
        else:
            t.informational.append(f"{r['id']}: shown as guidance only (the generator has no deterministic action for it)")
    return t


def split_sentences(script: str) -> List[str]:
    text = re.sub(r"\r\n?", "\n", script or "").strip()
    return [re.sub(r"\s+", " ", p).strip() for p in _SENT.split(text) if p and p.strip()]


def _split_long(sentence: str, max_words: int) -> List[str]:
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words // 2 and w.endswith((",", ";", ":", "—", "-")) or len(cur) >= max_words:
            out.append(" ".join(cur))
            cur = []
    if cur:
        if out and len(cur) < 6:
            out[-1] += " " + " ".join(cur)
        else:
            out.append(" ".join(cur))
    return out


def group_narrations(script: str, target: int, max_words: int) -> List[str]:
    """Consecutive sentences up to ``target`` words per scene; nothing dropped, nothing reordered, no limit on scene count."""
    pieces: List[str] = []
    for s in split_sentences(script):
        pieces += _split_long(s, max_words)
    out, buf, n = [], [], 0
    for p in pieces:
        w = len(p.split())
        if buf and n + w > max_words:
            out.append(" ".join(buf))
            buf, n = [], 0
        buf.append(p)
        n += w
        if n >= target:
            out.append(" ".join(buf))
            buf, n = [], 0
    if buf:
        if out and n < 8 and len(out[-1].split()) + n <= max_words:
            out[-1] += " " + " ".join(buf)
        else:
            out.append(" ".join(buf))
    return out


def _keywords(text: str, limit: int = 5) -> List[str]:
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z][A-Za-z'-]+", text):
        lw = w.lower().strip("'-")
        if len(lw) < 4 or lw in _STOP or lw in seen:
            continue
        seen.add(lw)
        out.append(w if w[0].isupper() and out else lw)
        if len(out) >= limit:
            break
    return out or ["documentary"]


class RuleBasedBackend(Backend):
    def _choose(self, text: str, enabled: Sequence[str], tuning: Tuning, recent: List[str]) -> str:
        allowed = [t for t in ALL_TYPES if t in enabled and t not in tuning.avoid_types] or [t for t in enabled if t in ALL_TYPES]
        if not allowed:
            allowed = ["stock_video"]
        prefs: List[str] = []
        if _SPACE.search(text):
            prefs.append("nasa_video")
        if _ARCHIVE.search(text):
            prefs += ["archive_video", "stock_image"]
        if _ABSTRACT.search(text):
            prefs += ["image", "stock_image"]
        if _ACTION.search(text):
            prefs += ["video", "stock_video"]
        prefs += ["stock_video", "stock_image"] if len(recent) % 2 == 0 else ["stock_image", "stock_video"]
        prefs += list(allowed)
        for p in prefs:
            if p in allowed and not (len(recent) >= tuning.max_run and all(r == p for r in recent[-tuning.max_run:])):
                return p
        return allowed[0]

    def _prompt(self, at: str, text: str) -> str:
        kws = _keywords(text)
        if at in ("image", "video"):
            return ("Cinematic documentary " + ("shot" if at == "video" else "still") + " of " + " ".join(kws[:4]) +
                    ", realistic, natural light, no text, no logos")
        if at in ("youtube_video", "archive_video", "nasa_video"):
            return " || ".join([" ".join(kws[:3]), " ".join(kws[:2]) + " footage"])
        return " ".join(kws[:4])

    def plan_scenes(self, narrations, opts, tuning, check, progress):
        rows, recent = [], []
        enabled = [t for t in opts.enabled_types]
        n = len(narrations)
        for i, narr in enumerate(narrations, 1):
            check()
            at = self._choose(narr, enabled, tuning, recent)
            recent.append(at)
            rows.append({"scene_number": str(i), "script_segment": narr, "asset_type": at, "prompt": self._prompt(at, narr)})
            if i % 25 == 0 or i == n:
                progress(0.1 + 0.8 * i / n, f"Planned {i}/{n} scenes")
        return rows


def to_csv_text(columns: Sequence[str], rows: Sequence[Dict[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def generate(script: str, style: str, options: Optional[GenerationOptions] = None, *, scope: Optional[str] = None,
             backend: Optional[Backend] = None, cancel: Optional[threading.Event] = None,
             progress: Optional[Callable[[float, str], None]] = None, knowledge_root=None) -> GenerationResult:
    """Script -> validated plan in ``style``'s CSV schema. Pure function of its inputs: touches no project, file or network."""
    opts = options or GenerationOptions()
    prog = progress or (lambda f, m: None)
    if style in UNSUPPORTED_STYLES:
        return GenerationResult(style, COLUMNS, [], [Issue("error", UNSUPPORTED_STYLES[style])])
    if style not in SUPPORTED_STYLES:
        return GenerationResult(style, COLUMNS, [], [Issue("error", f"Unknown style {style!r}.")])
    if not (script or "").strip():
        return GenerationResult(style, COLUMNS, [], [Issue("error", "Enter a script first.")])

    def check() -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
    try:
        prog(0.02, "Reading the script")
        tuning = knowledge_tuning(scope, opts, knowledge_root)
        base_target = opts.target_words if tuning.target_cap is None else min(opts.target_words, tuning.target_cap)   # never above the user's own choice
        target = max(12, int(base_target * tuning.target_scale))
        narrations = group_narrations(script, target, max(target + 10, opts.max_words if tuning.target_scale == 1.0 else int(opts.max_words * tuning.target_scale)))
        check()
        prog(0.1, f"{len(narrations)} scenes")
        rows = (backend or RuleBasedBackend()).plan_scenes(narrations, opts, tuning, check, prog)
        check()
        prog(0.95, "Validating")
        issues = validate_rows(rows, columns=COLUMNS, style=style, script=script, allowed_asset_types=list(opts.enabled_types) + ["stock"])
        notes = ["Rule-based local planner: keyword queries and simple rules, not language-model understanding. Review every scene."]
        if style == "enoch_template":
            notes.append("Enoch Template editorial rules are not applied by this planner; the CSV uses the same four columns.")
        prog(1.0, "Done")
        return GenerationResult(style, COLUMNS, rows, issues, tuning.applied, notes, informational=tuning.informational)
    except Cancelled:
        return GenerationResult(style, COLUMNS, [], [], [], ["Cancelled."], cancelled=True)
