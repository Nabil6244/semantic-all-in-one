# War Documentary — footage relevance audit (2026-11-09)

**Question:** why do War videos show footage that "looks like war" instead of what the narrator is saying?
**Scope:** read-only. No production code, shared file or protected file was changed for this audit.

## Evidence used
- **Render 038** `Video_2026-11-09_038_test_wasdf` (your latest, CSV `~/Downloads/footage_plan.csv`, 23 scenes, topic: Ukraine's strikes on Russian refineries). Sources: the asset manifest (per-scene query, video, channel, cut point, selection method, visual-QA verdict), `logs/generation.log`, and frames from every selected clip at 2 s / 4 s / 6 s.
- **Discovery replay:** the same search backend (`YtDlpBackend.search`, 5 results) and the same ranking (`providers/youtube/ranking.py`) run again on each scene's first query, metadata only. It reproduced the render's pick for 12 of the 15 YouTube scenes. YouTube results drift over time, so the other 3 differ slightly.
- **Render 033** `Video_2026-11-07_033_ahmed_test` (front-line topic, 20 scenes) as a cross-check.
- **Targeted searches:** 7 hand-written specific queries, to test whether the right material exists at all.

## Headline numbers (render 038, 17 clips placed)

| Verdict (from the actual frames) | Clips | Scenes |
|---|---|---|
| Matches the narration | **1** | 008 |
| Partial (right topic, unverified place/time) | 3 | 003, 005, 012 |
| Generic and repeated (same picture) | 6 | 001, 004, 006, 010, 020 (one identical shot ×5), 022 |
| Wrong (different place, opposite meaning, or not footage) | **7** | 009, 011, 015, 016, 017, 018, 021 |

Other facts from the same render:
- **Blind cut points:** 13 of 15 YouTube clips were cut at a guessed time (`selection_method: fallback`), because the transcript was missing, refused (HTTP 429) or didn't match. In 033 it was 9 of 17.
- **Vertical phone video:** 9 of 17 clips are phone video inside a 16:9 upload with blurred side bars (001, 003, 004, 005, 006, 010, 012, 020, 021). Cropped to fill the frame, they are upscaled from ~600 px wide. **This is a large part of the "low quality" you see, and it is a selection problem, not an encoding one.**
- **Repeats:** one New York Post moment (88.5 s) fills 5 scenes. In 033, one Kanal13 moment (64.25 s) fills 4.
- **Visual QA saw problems but nothing acted on them:** it marked scenes 006, 012 and 021 FAIL ("semantic mismatch") and 7 more WEAK, but every clip was still placed.
- **Broken CSV row:** scene 13 ("Second, Russians are feeling it. AP reported…") has an unquoted comma. Its narration landed in the `asset_type` column, so it was never searched.

## Scene by scene (render 038)

Each scene lists the narration, its entities, the query used, what discovery found, what was picked and why, and the verdict from the frames. "Score" is the shared ranking's number: title word overlap ×3, plus filmed-footage words, plus captions, minus long-video penalty.

**001** — *"Ukraine says its drones have disabled 51 percent of Russia's oil refining capacity."*
- **Entities:** Ukraine, Russia, 51 % (a **claim/statistic**, not an event).
- **Query:** "Ukraine drone strike Russian oil refinery fire footage" (query 2 never used).
- **Found:** Kanal13 Kirishi fire, Sunday Guardian LIVE, Kanal13 Ryazan, Kanal13 Saratov, MIRROR NOW talk.
- **Picked:** NY Post "Thick Black Smoke Engulfs Russian Oil Refinery…" at 88.5 s (fallback).
- **Frames:** distant smoke over apartment blocks, vertical phone video.
- **Verdict:** generic. A claim sentence has no footage of its own.

**002** — *"AP reported that the claim could not be independently verified."* CSV `none`. Card only (correct).

**003** — *"Overnight on November 5, drones set the Ryazan refinery on fire."*
- **Entities:** Ryazan refinery, 5 November, drones (an **event**).
- **Query:** "Ryazan refinery fire drone attack footage".
- **Picked:** Daily Mail "…Ryazan in brazen drone attack" (rank 1, score 1.81) at 150.5 s (fallback).
- **Frames:** phone video, refinery smoke behind a parked car.
- **Verdict:** partial. Right place in the title, but the date was never checked. Ryazan has been hit many times, so this may be a different night.

**004** — *"Euromaidan Press counted it as the fifth Russian refinery hit since October 30."*
- **Entities:** a source plus a count (**claim**).
- **Query:** "Russian refinery fire drone strike footage" → NY Post (score 2.07: every generic word is in its title).
- **Verdict:** generic, the same shot as 001.

**005** — *"So is Russia really running out of fuel? There are three parts to the answer…"*
- **Type:** rhetorical question.
- **Query:** "Russia gasoline station queue fuel shortage footage" → Kanal13 "Fuel riots…" at 97 s.
- **Frames:** refinery fire, then a crowd at a petrol station.
- **Verdict:** partial (on topic).

**006** — *"First, the strikes now reach deep into Russia."*
- **Query:** generic → NY Post again. Visual QA: FAIL, sem 0.0.
- **Verdict:** generic repeat. Placed anyway.

**007** — *"The IEA says that by late August, only five major Russian refineries had not been hit."* `none` → card (correct).

**008** — *"The IEA says the Moscow refinery, badly damaged in June, is reported to be offline until early 2027."*
- **Query:** "Moscow refinery drone attack fire footage".
- **Found:** Reuters 31 s, Guardian 27 s, WION, BBC — all on topic.
- **Picked:** Reuters "Moscow refinery on fire after Ukrainian drone attack" (score 2.85).
- **Frames:** Moscow refinery smoke over a street.
- **Verdict:** **match** (the date wasn't verified, but the place is right). This is what success looks like: a named place plus an agency upload.

**009** — *"In September, Reuters reported that Kirishi, one of Russia's biggest diesel refineries, had shut down completely."*
- **Query:** "Kirishi refinery fire September footage".
- **Found:** MIRROR NOW 502 s talk (1.68), MIRROR NOW "Russia's Oil Refinery Inferno" (1.58), **Kanal13 "Ukrainian drones attacked the Kirishi Oil Refinery" (0.90, rank 3)**.
- **Why the wrong one won:** the MIRROR NOW title has more of the query's words ("Kirishi Refinery Erupts In Flames"). The Kirishi-specific raw clip lost on word count.
- **Frames:** caption "OZON'S ROSTOV WAREHOUSE WAS HIT EARLIER", a firefighter at night.
- **Verdict:** **wrong place, wrong target.**

**010** — *"Reuters also said three of Russia's six largest diesel refineries had cut or halted output."* (claim/statistic) → NY Post again. Visual QA: sem 0.245. Generic repeat.

**011** — *"Reuters said NORSI and the Volgograd refinery were running at about a fourth of capacity."*
- **Query:** "NORSI refinery drone attack footage".
- **Picked:** "Ueodu Twuxb" channel, 1,021 s faceless video, cut via transcript match at 50 s.
- **Frames:** a poppy field and a city bridge at sunset (stock-style filler inside a narrated video).
- **Verdict:** **wrong, not footage.** The transcript matched because the *voice* said "NORSI", while the picture showed flowers.

**012** — *"AP noted that strikes increasingly hit equipment that cleans fuel, which takes months to repair."*
- **Query:** "refinery unit fire drone strike footage" → Kanal13 "FP-1 drone strike on Russia's key **Omsk** Oil Refinery". Visual QA: FAIL.
- **Frames:** refinery fire, vertical video.
- **Verdict:** partial. Refinery damage, but a random refinery.

**013** — *"Second, Russians are feeling it. AP reported that drivers had to wait up to 40 hours at gasoline stations."*
- **Not searched:** broken CSV row.
- **Exists:** Reuters 31 s "Gas station queues in Russia after largest refinery attacked".

**014** — Rosstat prices `none` → card (correct).

**015** — *"Russia banned diesel exports and began importing gasoline by rail from Belarus and Kazakhstan."*
- **Query:** "Russia gasoline imports rail Belarus footage".
- **Found:** Lithuania *gas*, US oil ban, Belarus-from-Norway, Spain LNG, China rail. Not one is about rail gasoline from Belarus.
- **Picked:** TVC News Nigeria "Lithuania Becomes First EU Country To End Imports Of Russian Gas" (score 0.51). Visual QA: PASS (sem 0.67, text words overlapped).
- **Frames:** studio presenter.
- **Verdict:** **wrong country, wrong fuel, a talking head.** Nothing checks that the scene's entities (Belarus, Kazakhstan, rail, gasoline) are in the candidate, or that a different country (Lithuania) is named.

**016** — *"Third, Russia is fighting back. Reuters reported that refining rates rose 25 percent…"*
- **Query:** "Russian refinery repair October footage" → NBC "Ukraine resumes strikes on Russian refineries".
- **Frames:** a **US** gas-price graphic ("$4 a gallon"), then a burning ship.
- **Verdict:** **opposite meaning** (recovery narrated, strikes shown) and the wrong country's prices.

**017** — *"Still, Reuters said Ryazan's main distillation unit was halted again after an October attack."*
- **Query:** "Ryazan refinery attack October footage" → "Secrets Beneath The Tide" commentary channel at 543 s (fallback after 429).
- **Frames:** a YouTuber talking on camera plus AI paintings.
- **Verdict:** **wrong, not footage.**

**018** — *"The Financial Times reported that tankers carrying Russian diesel toward the US changed course on November 2."*
- **Query:** "tanker carrying Russian diesel at sea footage" → Orbisentinel 1,237 s commentary (rank 1, 0.87), just ahead of News24 "US seizes Russian oil tanker" (0.85).
- **Frames:** an article screenshot and a US senator's portrait.
- **Verdict:** **wrong, not footage.** A 20-minute commentary is penalised only above 20 minutes, and only slightly.

**019** — Flow clip, AI cap 0 → nothing (grey grid / cards).

**020** — *"So the strikes are real and costly, but the 51 percent figure is Ukraine's own claim."* (claim) → NY Post a 5th time. Generic repeat.

**021** — *"Russia is repairing refineries and importing fuel, so the picture is damage without collapse."*
- **Query:** "Russian refinery repair footage" → Guardian "Moment fuel storage lid flies off Moscow refinery during drone attack" (1.47). Visual QA: FAIL.
- **Frames:** an explosion.
- **Verdict:** **opposite meaning** (repair narrated, explosion shown).
- **Exists:** NewsX "Putin says refinery repairs near completion", BBC/Rosenberg "unscheduled repairs".

**022** — *"Do you think Ukraine can keep this up through winter?"* Stock "refinery in winter snow" → a couple walking in a snowy forest. Off topic.

**023** — Flow, AI cap 0 → nothing.

### Cross-check: render 033 (front lines)
- **Opposite sides:** "Third, Russia is hitting back from the air" got Kanal13 "Ukrainian drones hunt down Russian troops", the opposite side. The same moment (64.25 s) was used in 4 scenes.
- **Contradicting number:** "Putin claimed … 6,500 km²" got the "Valor Ascent" commentary "Putin Claimed 1,301 km²". It was a transcript match on a commentary voice, with a contradicting number.
- **Wrong subject:** "DeepState's latest four-week figure…" got "Russian Special Forces Ambushed Ukrainian Elite Forces" (also a transcript match).

Same failure modes, different topic.

## Where the problem starts (layer by layer)

| Layer | Finding | Weight |
|---|---|---|
| **1. Narration understanding** | Nothing classifies a sentence. About 9 of 23 sentences in 038 are claims, statistics, source attributions or rhetorical questions (001, 004, 005, 006, 010, 020, 021, 022, plus the `none` rows). They have no footage of their own, yet the CSV asks YouTube for footage, gets the generic "refinery fire" and repeats it. The app never extracts entities from the narration for YouTube: the query is *only* the CSV prompt. | High |
| **2. Query generation** | Queries are generic and nearly identical across scenes ("Russian refinery fire drone strike footage" in 4 scenes), so the same top video wins every time. Month words ("September", "October") narrow nothing on YouTube. There's no agency/broadcaster variant, so the best queries in the replay ("Reuters Ryazan refinery", "Kirishi refinery drone") were never tried. | **Very high** |
| **3. Source discovery** | One source, 5 flat results (title, channel, duration only). **The first query that returns anything wins; query 2 is never searched.** Results aren't pooled across queries. Duplicates are excluded within a scene, not across the film. A "find another clip" re-run repeats the same search and gets the same video. | High |
| **4. Candidate ranking** | Title-word overlap decides: a title stuffed with generic words beats a specific raw clip (009). No channel trust tiers (agency vs aggregator vs commentary). Long commentary is penalised only above 20 min. No entity check (015). No contradiction check on another place, country or side (009, 015, 033). Phone video inside 16:9 isn't detected. **Nothing looks at the picture.** | **Very high** |
| **5. Clip moment** | 13/15 cut points were guessed (429s, no captions, no match). When a transcript *does* match, it finds where a voice *says* the words, which in commentary videos is a talking head or filler (011, 033). No frame check for studio, presenter, text screen or filler. | High |
| **6. Timeline placement** | Visual QA marks FAIL/WEAK, but CSV clips are always kept. A mismatch is placed silently instead of becoming a card or map. | Medium |

**Root cause in one line:** search is driven by generic CSV keywords and judged by video titles alone, and no step ever checks (a) that the scene's specific entities are present, (b) that the picture is filmed footage, or (c) that the moment shows the event. Better download quality can't fix any of this.

## Answers to the specific questions

- **Generic keywords instead of specifics?** Yes. 12 of 15 YouTube queries in 038 reduce to the same 4–5 words. The specific entities that *are* in the narration (Kirishi, NORSI, Volgograd, Belarus, Kazakhstan, rail, distillation unit, tanker, FT, 2 November) either aren't in the query or lose in ranking to longer generic titles. Military units, equipment and dates aren't used at all for YouTube (War's own catalogue knows equipment and places, but only the graphics use it).
- **Can it tell visually similar but contextually different footage apart?** No. It has no place, date or side check on candidates and no frame understanding. So any refinery fire is accepted for any refinery (009, 012), an attack is used for a repair (016, 021), and a Ukrainian strike is used for a Russian one (033). War's `footage_match.py` does have a contradiction check (different place, country, system or year), but it only runs on records *after* download and is never used to reject a candidate.
- **Do the sources have enough material?** Mostly yes, if asked specifically:
  - **Scene 13:** "Russia gas station queue gasoline" → Reuters 31 s "Gas station queues in Russia after largest refinery attacked".
  - **Scene 9:** "Kirishi refinery drone" → four Kirishi-specific uploads, including short ones.
  - **Scene 16/21:** "Russian refinery repair work" → NewsX "refinery repairs near completion" and BBC/Rosenberg on repairs.
  - **Scene 18:** "Russian diesel tanker Atlantic" → BBC, News24 and RTÉ tanker reports.
  - **Agency clips:** "Ukraine drone hits Russian refinery Reuters" → five Reuters clips of 27–79 s each. Short agency uploads are almost pure footage.
  - **Weak spot:** gasoline imported by rail from Belarus and Kazakhstan (015) has thin, low-trust coverage. That sentence is better served by a map with rail arrows than by footage.

## Proposed solution (War-only, for your approval; nothing built yet)

War gets its own **footage director**: a new War module that decides *which video and which moment*. The shared YouTube downloader is then only asked to capture that exact video and second. No shared or protected file changes; whether the shared fetch can take a pinned video id + start is the first thing to verify (Visuals-tab "Change source" already does something similar).

1. **Sentence type first.** Each narration sentence is classified (rules, no Gemini):
   - **EVENT** (something happened at a place or time)
   - **SUBJECT** (a facility, weapon, unit or person)
   - **CLAIM / STAT / SOURCE** ("X said / reported / counted N")
   - **RHETORICAL**

   Only EVENT and SUBJECT search for footage. CLAIM/STAT gets the War panels and cards, which already exist. RHETORICAL gets a chapter card or a *deliberate* return of the topic's best clip, labelled as such. In 038 this removes about 9 of the 15 YouTube searches that could only return generic or repeated footage.
2. **Entity-first queries from the narration plus the CSV.** Use the place/facility, equipment, unit and person names (War's catalogue, equipment list and geo data already hold them) plus the event noun. Send 3–4 short queries per scene: `Kirishi refinery drone strike`, `Reuters Kirishi refinery`, `Kirishi refinery fire`. No month words. **Pool all results** (10 per query), don't take the first hit.
3. **Candidate scoring with hard rules:**
   - **Must name** the scene's key entity (title or description), otherwise rejected.
   - **Contradiction = reject** (reuse `footage_match`'s place/country/system/year logic): another named place, country or side.
   - **Channel trust tiers:** agencies and broadcasters (Reuters, AP, AFP, BBC, Guardian, DW, Sky, NBC…) > regional news (Kanal13, United24…) > aggregators > commentary/faceless.
   - **Prefer short uploads** (under 3 min = raw news clip). Long narrated videos are a last resort.
   - **One video moment once per film,** at most 2 moments per video, and "another clip" excludes everything already used.
4. **Moment check on the frames before capture** (free: ffmpeg + numpy, no Gemini). Sample the window and reject:
   - talking heads and studio presenters (a large static face)
   - text and article screens (high text density, flat background)
   - phone video in side bars (blurred pillarbox detection)
   - still or very dark segments

   For short agency clips, take the most active stretch. Transcripts are only a hint, fetched with a cache and pauses.
5. **No silent misses.** A scene with no candidate that passes gets a War card or map (the War rules already handle this). It's never filled with "any war footage". The Visuals tab shows the reason per scene.
6. **CSV side:**
   - The CSV prompt asks for entity + event queries and marks claim/stat sentences `none` (War CSV prompt file only).
   - The CSV reader repairs rows broken by an unquoted comma (scene 13).
7. **Discovery report per render** (`state/war/discovery_report.json`): queries, every candidate, score, reason and moment. Future audits then need no replay.

**How we'd measure it:** keep 038 + 033 as a fixed test set with the hand verdicts above (038 today: 1 match / 3 partial / 6 generic / 7 wrong). Run discovery only (no render) after each step and compare. Target: no wrong-place or opposite-meaning clips, no repeated moment, no talking heads, and claim sentences on cards.

**Suggested order:** 1 (sentence type) → 2+3 (queries and scoring, the biggest gain) → 4 (frame check) → 5 + 7 → 6. Each is small and testable on its own.
