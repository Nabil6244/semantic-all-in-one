"""Language-neutral sentence handling plus small per-language word lists (hedges, absolutes, attribution).

The structure of a script is never read from its words (roles are tagged in the script map). Word lists are used only for
wording checks; for a language without a list the checks say so (a review item) instead of guessing.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Dict, List, Tuple

_STOPWORDS: Dict[str, frozenset] = {
    "en": frozenset("the and of to is was that it in for with as his her this which by from they were be are".split()),
    "es": frozenset("el la los las de que y en un una es por con para se del al lo como su más pero fue".split()),
    "fr": frozenset("le la les de des et en un une est que qui dans pour par sur au du pas ce son".split()),
    "de": frozenset("der die das und ist nicht ein eine zu den von mit sich des auf für im dem".split()),
    "pt": frozenset("o a os as de que e em um uma é por com para do da não se mais foi".split()),
    "it": frozenset("il lo la gli le di che e è un una per con non del della si sono".split()),
}

# hedges: wording that marks an interpretation or a dispute as such
HEDGES: Dict[str, Tuple[str, ...]] = {
    "en": ("may", "might", "could", "possibly", "probably", "likely", "perhaps", "suggests", "suggest", "according to",
           "some scholars", "many scholars", "scholars argue", "argue", "argues", "interpret", "interpreted", "interpretation",
           "debated", "disputed", "contested", "remains unclear", "it is thought", "is thought", "seems", "appears to",
           "one reading", "in one reading", "others", "proposed"),
    "es": ("podría", "podrían", "puede", "pueden", "posiblemente", "probablemente", "quizá", "quizás", "tal vez", "sugiere",
           "sugieren", "según", "algunos", "algunos estudiosos", "muchos estudiosos", "sostienen", "sostiene", "interpreta",
           "interpretan", "interpretación", "se debate", "debatido", "discutido", "discuten", "no está claro", "parece",
           "parecen", "una lectura", "otros", "propone", "proponen"),
    "fr": ("pourrait", "peut-être", "probablement", "selon", "certains", "suggère", "interprétation", "débattu", "discuté",
           "semble", "d'autres"),
    "de": ("könnte", "vielleicht", "wahrscheinlich", "laut", "einige", "deutet", "deutung", "umstritten", "scheint", "andere"),
    "pt": ("poderia", "pode", "talvez", "provavelmente", "segundo", "alguns", "sugere", "interpretação", "debatido",
           "discutido", "parece", "outros"),
    "it": ("potrebbe", "forse", "probabilmente", "secondo", "alcuni", "suggerisce", "interpretazione", "dibattuto",
           "discusso", "sembra", "altri"),
}

# absolutes: wording that states a thing as settled, total or unique
ABSOLUTES: Dict[str, Tuple[str, ...]] = {
    "en": ("no other", "the only", "never", "always", "all", "every", "proves", "proof", "certainly", "undeniably",
           "without doubt", "exactly", "nobody", "no one", "everyone", "definitely", "beyond doubt", "it is a fact"),
    "es": ("ningún otro", "ninguna otra", "el único", "la única", "nunca", "jamás", "siempre", "todos", "todas", "demuestra",
           "prueba", "sin duda", "exactamente", "nadie", "definitivamente", "es un hecho", "no se discute"),
    "fr": ("aucun autre", "le seul", "la seule", "jamais", "toujours", "tous", "prouve", "sans doute", "exactement", "personne"),
    "de": ("kein anderer", "der einzige", "die einzige", "niemals", "immer", "alle", "beweist", "zweifellos", "genau", "niemand"),
    "pt": ("nenhum outro", "o único", "a única", "nunca", "sempre", "todos", "prova", "sem dúvida", "exatamente", "ninguém"),
    "it": ("nessun altro", "l'unico", "l'unica", "mai", "sempre", "tutti", "dimostra", "senza dubbio", "esattamente", "nessuno"),
}

# attribution verbs and phrases: a sentence saying that someone or something says/wrote/dated/found
ATTRIBUTION: Dict[str, Tuple[str, ...]] = {
    "en": ("says", "said", "wrote", "writes", "states", "stated", "describes", "dated", "found", "discovered", "published",
           "according to", "records", "recorded"),
    "es": ("dice", "dijo", "escribió", "escribe", "afirma", "afirmó", "describe", "fechado", "encontró", "encontraron",
           "descubrió", "publicó", "publicaron", "según", "registra", "señaló", "señalaron", "observa"),
    "fr": ("dit", "écrit", "affirme", "décrit", "daté", "trouvé", "découvert", "publié", "selon"),
    "de": ("sagt", "schrieb", "schreibt", "beschreibt", "datiert", "gefunden", "entdeckt", "veröffentlicht", "laut"),
    "pt": ("diz", "disse", "escreveu", "afirma", "descreve", "datado", "encontrou", "descobriu", "publicou", "segundo"),
    "it": ("dice", "disse", "scrisse", "afferma", "descrive", "datato", "trovato", "scoperto", "pubblicato", "secondo"),
}

_SENTENCE_END = re.compile(r"(?:(?<=[.!?…。؟])|(?<=[.!?…。؟][\"'»”)\]]))\s+(?=\S)")
_NUMBER = re.compile(r"\d")


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def sentence_hash(text: str) -> str:
    """Stable fingerprint of a sentence (whitespace and Unicode form normalised); 12 hex chars."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:12]


def split_sentences(text: str) -> List[str]:
    """Split on sentence-final punctuation of any language; keeps punctuation; never drops text."""
    body = normalize_text(text)
    if not body:
        return []
    return [p.strip() for p in _SENTENCE_END.split(body) if p.strip()]


def words(text: str) -> List[str]:
    return re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", (text or "").lower())


def detect_language(text: str) -> str:
    """'en', 'es', 'fr', 'de', 'pt', 'it' by stopword count, or 'und' when it cannot tell."""
    toks = words(text)
    if not toks:
        return "und"
    scores = {lang: sum(1 for t in toks if t in sw) for lang, sw in _STOPWORDS.items()}
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    if ranked[0] < 2 or (len(ranked) > 1 and ranked[0] == ranked[1]):
        return "und"
    return best


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<![\w'])" + re.escape(phrase.lower()) + r"(?![\w'])", (text or "").lower()) is not None


def hedges_in(text: str, lang: str) -> List[str]:
    return [h for h in HEDGES.get(lang, ()) if _contains(text, h)]


def absolutes_in(text: str, lang: str) -> List[str]:
    return [a for a in ABSOLUTES.get(lang, ()) if _contains(text, a)]


def supported_language(lang: str) -> bool:
    return lang in HEDGES


def looks_factual(text: str, lang: str) -> bool:
    """Heuristic only (it can be wrong both ways, so its result is a review item, never a hard failure): a digit, an
    attribution verb, or a capitalised name in the middle of the sentence."""
    if _NUMBER.search(text or ""):
        return True
    if any(_contains(text, a) for a in ATTRIBUTION.get(lang, ())):
        return True
    toks = (text or "").split()
    return any(t[:1].isupper() and t[1:2].islower() for t in toks[1:] if not t.startswith(("¿", "¡", '"', "«")))


def words_per_second(lang: str) -> float:
    """Typical narration speed for timing estimates when real timings are not known."""
    return {"es": 2.3, "it": 2.3, "pt": 2.2, "fr": 2.3, "de": 2.0, "en": 2.5}.get(lang, 2.3)
