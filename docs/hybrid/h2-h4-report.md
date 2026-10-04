# Hybrid Map: H2-H4 report

- H2: Director (own prompt, sentence-range answers, code derives times), deterministic validator, Gemini critic (structured findings), bounded repair (<=2 passes, weak beats / validator errors / out_of_frame / layer_late / text_too_long only).
- H3: third top-level style "Hybrid Map"; footage rows in the existing Visual Tab (AssetManager, manifest, overrides); map beats in the plan / Check plan; persistence and restore; compile into ONE pakMap item.
- H4: real scripts A (geography-led), B (balanced), C (experience-led), D (3 min long-form) planned and rendered with real Pexels/YouTube media.

QA findings fixed during H4: footage-after-footage overlap (xfade_prev), prompt bundling, repair pairing, anchors for spoken numbers, over-long captions running off screen (new `text_too_long` warning, repairable, Director prompt limit 44 characters).

D audio: -16.4 LUFS integrated, LRA 1.6 LU, no transition SFX on clip handovers.

Limits: Gemini quota restricted the number of full Director/critic runs (B re-plan and C final critic not repeated); Flow was not exercised; rivers/mountains/seas/small towns need "lat,lon".
