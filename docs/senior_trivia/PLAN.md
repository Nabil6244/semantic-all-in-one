# Senior Trivia — plan (2026-11-25)

A new style for US viewers aged 60+ who watch YouTube on their TV: long, calm quiz videos they play along with.
It needs no maps, no stock footage and no Flow video. It is made from cards, a countdown, Flow pictures, a voice and sound.

## Why this niche (outlier scan, 2026-11-25)
In the last month, new channels in this niche got **50–150 times their subscriber count** in views:

| Channel | Started | Subscribers | Best video (last month) |
|---|---|---|---|
| Quiz Magnet | Jun 2025 | 8.3K | 1.2M, "Can You Identify These 50 Old Items in Just 7 Seconds?" |
| Knowledge Dose | Oct 2025 | 3.2K | 329K, "Are You Around 72 Years Old? Let's See Your Brain Power!" |
| Still Sharp Trivia | Mar 2025 | 627 | 88K, Christmas quiz, "Can You Get 40 Out of 45?" |
| Knowledge Engine | Jun 2025 | 4.7K | 104K, "Are You Around 65? Let's Check Your Memory!" |
| Seniors Quiz Club | May 2026 | 765 | 60K, "63 Words That Meant Something Else in the 1950s" |
| Recall Lane | Nov 2026 | 461 | 47K in 1 day, "Name the State from One Clue! Score 35 to Pass" |

What the winning videos share:
- **Length:** 20–35 minutes. The 5–7 minute versions do much worse.
- **Title formula:** an age hook ("Are you around 72?"), a pass mark ("Score 35 to pass", "Can you get 40 out of 45?") or a speed challenge ("in 7 seconds").
- **Topics:** American nostalgia, such as old household items, words from the 1950s, the 50 states, classic TV-era things, holidays, and general knowledge.
- **Format:** a question, then a countdown, then the answer reveal with a short fun fact. Viewers keep score at home.

## How the video looks (draft, to be confirmed by the study in Step 0)
1. **Cold open (≈20 s):** the challenge ("50 questions, most people your age get 30, score 40 and your memory is sharp"), a quick montage of 3 upcoming pictures, and "grab a pen and paper".
2. **Rounds of 10 questions:** a round title card ("ROUND 2 · AROUND THE HOUSE").
3. **Each question (≈25–35 s):**
   - The voice reads the question, and the text appears in large type.
   - A picture card (for picture questions) or 3–4 answer options (A/B/C/D).
   - A countdown ring with a soft tick, 7–10 s, always moving. The picture gets a slow push-in, so the screen never sits still.
   - The reveal: a chime, the right option lights up green, the answer is spoken, then **one fun fact** with a second picture.
4. **Score check every 10 questions:** "If you have 8 or more so far, you are doing better than most."
5. **End:** a score ladder (0–20 "keep practising", 21–35 "sharp", 36+ "genius"), "tell us your score in the comments", and the next quiz.

Question types:
- **picture:** "What was this used for?"
- **choice:** A/B/C/D.
- **truefalse**
- **year:** "Which year…?"
- **clue:** "Name the state from one clue."
- **first:** "Which came first?"
- **price:** "What did a gallon of milk cost in 1960?"

Readable on a TV: very large text, high contrast, warm colours, and a calm male or female US voice. No fast cuts, and no rejected effects (no typewriter, stamp, sweep, underline or double text).

## Update after the reference study (see REFERENCE_STUDY.md)
- **Two modes.** **Rounds** (voiced, pictures, about 28 s per question, 6–7 s countdown, a bonus question at the end) and **Old Items** (silent after the intro, a big photo and a green-to-red time bar for 7 s, then the name bar, 50 items in about 10 min). The second is the format of the 1.2M-view hit.
- **Host: 5–6 talking clips per video** (owner request, 2026-11-25). They reuse the Prepper Host talking-clip code (Flow video with references, about 8 s, 10 credits each). The host gets his own host pack and set: a friendly man of about 65 in a warm living room or den. He is never shown as a still. If a clip fails, that line plays over a picture.
  - **Where he appears:** the cold-open challenge, 3–4 round intros or score checks, and the score ladder and goodbye. The question reading stays on the cards.
  - **Voice:** his clips use the Flow voice, and the questions use an Edge voice. On screen this plays like a show host plus a quiz announcer, so the change in voice works as two roles. To be confirmed with the owner.
- **CSV gains `host` rows** (`type=host`, `line` = what he says), and the director checks there are 5–6 of them.

## Steps
**Step 0. Reference study.** Read 8+ top videos from the channels above: how long the timer runs, what the voice says, where the music sits, how they word the score checks, the layout, and the thumbnails. Write `docs/senior_trivia/REFERENCE_STUDY.md`. We adopt their patterns but build our own look.

**Step 1. CSV and plan (`senior_trivia/csvplan.py`, `csv_prompt.txt`).** One row per question:
`round,type,question,options,answer,fact,picture,fact_picture,seconds`. There are also `intro`, `check` and `outro` rows, plus one `thumbnail` row.
A checker catches a missing answer, an answer that isn't among the options, duplicate questions, or a round with too few questions.
A supplied CSV means zero Gemini calls.

**Step 2. Pictures (`senior_trivia/pictures.py`).** One Flow picture per picture question and per fact, in a warm, realistic vintage-photo look, cached in a shared library (`out/senior_trivia/library`) so repeated items cost nothing. The pictures go through the Visuals tab like every other style. If a picture is missing, that question shows as a text-only card. Nothing goes blank.

**Step 3. Renderer (`senior_trivia/render.py`).** PIL frames on an all-core pool, one question per worker:
- layouts: question, options, picture, reveal, fact, round title, score check, score ladder;
- the countdown ring and slow push-in on pictures;
- a 1080p one-pass encode, with the cut-and-join approach from Explainer to keep disk use small.

**Step 4. Sound (`senior_trivia/audio.py`).** Edge voice (one sentence at a time; voice to be picked), a soft tick, a reveal chime, a round sting, a quiet warm music bed under the narration, ducked under speech. Loudness goes through `audio_level.py`.

**Step 5. Director.** Spaces out difficulty (easy, easy, medium, then one hard one every 5), makes sure the same type never appears 3 times in a row, places the score checks, and times the countdown from the question length.

**Step 6. Wiring into the app.** An app page under a new "Quiz" group in the style picker, style_registry/style_kit, export_state, `autorun/job.py` and `make_video.py` ("senior-trivia"), the exe spec, and tests. Generate, then Render. Nothing starts until Generate.

**Step 7. Shorts.** A 9:16 version with 3–5 questions each, cut from the long video ("Only 1 in 10 seniors gets #3").

**Step 8. Test.** One 3-minute test video (8 questions). I'll ask before rendering it.

## Questions for you
1. Voice: a calm man (like Andrew) or a warm woman (like Jenny/Aria)?
2. Default length: 50 questions (about 25 min) or 35 questions (about 18 min)?
3. Famous-face questions ("name this 70s star") get big views, but they need real photos of real people. Skip them, or use only Wikimedia/public-domain photos?
4. Channel name and colours: decide now, or later?
