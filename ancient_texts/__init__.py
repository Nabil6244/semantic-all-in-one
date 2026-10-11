"""Ancient-text documentary production core (first user: the Enoch Template style).

Topic-agnostic: a subject is a data pack (ancient_texts/packs/<id>.json); the code knows roles, claims, sources, cards and
checks, never Enoch. Every stage is local and deterministic -- no AI provider, no Flow, no network. Research and script
writing happen outside the app through copyable prompts; this package validates what comes back and plans around it.

  issues     the shared diagnostic record (hard failure / soft deviation / human review)
  subjects   subject packs (ancient_texts/packs/*.json): load and validate
  claims     sources, claims, the claim ledger and its checks (a ledger is a set of assertions to check, never proof)
  framework  narrative roles, presets, the script map, structure checks, language-neutral sentence handling
  cards      the four card kinds the existing graphics engine lacks, rendered as ordinary PNG stills
  plan       the style's refine pass on a VisualPlan: relevance reasons, AI ceiling, motifs, cards
  audio      opt-in loudness finishing for this style's finished file (video stream copied)
  qc         the evaluator: hard failures, soft deviations, review items; never "equivalent to the reference"
  integration  the small functions app.py calls; everything is a no-op unless the project's style is enoch_template
"""

STYLE_ID = "enoch_template"
