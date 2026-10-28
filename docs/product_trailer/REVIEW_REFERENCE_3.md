# Reference check 3: how four narrated explainers plan scenes (2026-10-28)

Method: transcribed each video (faster-whisper base), took one frame at the middle of every narration segment, read the pictures against the words.
Videos: How's This Possible (flat infographic), This Was NEVER Expected, Galaxy S26 Ultra NEW CHANGES, iPhone 17 Pro Max THE TRUTH (three real-footage news compilations).

## Two families
**A. Flat infographic (How's This Possible).** One sentence = one claim drawn literally: "700mAh bigger battery" -> two phones with +700mAh; "silicon-carbon" -> a battery
cutaway; "unchanged at 60W" -> both phones 60W on a cable; "2 to 3% faster" -> two charge capsules racing; "80% to 100% vs 0% to 50%" -> two capsules over one phone.
A sentence with no new fact keeps the scene before it, changed slightly. Real footage only for real-world mentions.

**B. Real-footage news compilation (the other three).** A new clip every 3-5 s, each matched to the words:
- certification / database sentence -> a screenshot of the listing (BIS, 3C) with the row highlighted
- "tipster X" -> the tweet or post screenshot
- battery sentence -> a battery settings screen, a teardown with the battery in hand
- colours sentence -> the phones in those colours in a hand or row, in the order named
- design / cameras sentence -> hands turning the phone, camera close-ups, cases
- launch / event sentence -> stage or crowd footage
Nothing generic: no clip is a beauty shot unrelated to the sentence.

## What the tool now does (`product_trailer/director.py`, style "Mixed (auto)")
Evidence document (`pt_doc`), quote card, before/now phones with +delta, one figure beside a phone, colour phones, model lineup, camera count, charge range;
3D shots for inside / hinge / chip / camera / display / frame; a sentence that calls for nothing keeps the previous scene (at most 9 s), then 3D beats.

## Not done (needs more than rules)
- Understanding a sentence semantically (needs the LLM router that already exists in `ai_router/`, one call for the whole script, returning scene JSON).
- Real footage for family B: needs a footage source per sentence (stock search with the Pexels / Pixabay keys in Settings, the user's local library, or Flow pictures).
- Hand-written `[scene: {...}]` directives still give the best result; see `out/charging_follow/`.
