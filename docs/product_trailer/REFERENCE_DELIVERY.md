# How the reference videos are delivered, and why our iPhone Duo film was not (2026-11-06)

Measured on the three references studied today (REVIEW_REFERENCE_4.md: A, B; REVIEW_REFERENCE_5.md: C) and on our test film
(out/duo_test/iphone_duo_review_test.mp4). Cuts: ffmpeg scene changes; sentences: Whisper.

## 1. Pacing: cutting speed was not our problem

| | length | shots | median shot | under 2 s | 2-4 s | 4-8 s | over 8 s | longest | sentences with no cut |
|---|---|---|---|---|---|---|---|---|---|
| Ref A (S27 decisions) | 4.2 min | 38 | 5.0 s | 8 % | 26 % | 39 % | 26 % | 25 s | 40 % |
| Ref B (S27 upgrade) | 4.8 min | 39 | 4.3 s | 41 % | 8 % | 33 % | 18 % | 54 s | 72 % |
| Ref C (Design changed) | 11.3 min | 223 | 2.4 s | 37 % | 41 % | 18 % | 4 % | 19 s | 10 % |
| **Our Duo film** | 4.1 min | 68 | 2.9 s | 15 % | 60 % | 19 % | 6 % | 14 s | 10 % |

We cut **as often as or more often than** the references. A and B hold one picture for 25-54 s, and it never feels slow, because
that picture keeps **adding information** on the narrator's words (labels, badges, a "?", a second figure). Ours cut every
2-4 s **between angles of the same phone**: lots of movement, no new information. In the references, pace comes from new facts on screen,
not from cuts.

## 2. Scene selection: what is on screen

| | a fact or a source on screen | the real phone / real event | an empty generic object |
|---|---|---|---|
| Refs A, B, C (estimated from the frame sheets) | about 55-65 % | about 35-45 % | **never** |
| **Our Duo film** (measured from the plan) | 44 % (much of it one-word labels: "Display", "The hinge") | 0 % (wrong phone design) | **50 %** (a white phone turning, nothing on it) |

The rule the references follow: **every second shows the thing being said**. That is the source that says it, the fact itself,
or the real object or event. A plain product shot only appears when the narration is about the design itself.

## 3. Which picture each kind of sentence gets (the references' choices)

| Kind of sentence | Example | What all three references show |
|---|---|---|
| Opening tease + topic list | "new information about the design, cameras, processors, and the launch timeline" | one quick shot per topic, in the order said |
| A claim with a source | "Ice Universe says…", "according to a report…", "Apple says…" | that source's post / article / statement, the spoken words marked as they are read |
| A figure | "5,700 mAh", "$1,499", "7.9 mm" | the figure, big, beside the real phone, landing on its word |
| Two figures / a comparison | "6,000 and 5,500", "S26 Ultra vs S27 Ultra" | both, side by side, each named |
| A list | "black, blue, light pink, white" | items appear one by one in spoken order |
| A date / timeline | "January … February", "October 23 … 26 … November 2" | big date type that changes to the next date |
| A real-world event or use | "gaming", "the Snapdragon Summit", "an owner in Australia" | real footage / photos of exactly that |
| A problem | "cracks", "the hinge won't close" | the real problem (photos, teardown) |
| A question | "but what about the Ultra?" | the thing asked about, everything else dimmed |
| Opinion / talk | "honestly", "I'd rather", "my take" | presenter or hands with the phone, **no new graphic** |
| Sign-off | "subscribe", "click here" | end card |

## 4. Delivery: how the videos are built

1. **Hook, 0-15 s**: the news in one sentence, then a montage of what's coming, one shot per topic.
2. **Greeting**, a second or two, over the phone or the presenter.
3. **Sections** (C names them bottom-left). Each opens on its **source** or on the real phone. Inside a section, one canvas
   keeps building while the narrator stays on the same point, then cuts when the point changes.
4. Each section **ends on the creator's opinion** (presenter or hands footage).
5. **Verdict + call to action**, then the end card.

## 5. The Duo script against this

The script (46 sentences) is a **news story**. Its sentences, by kind:

| Kind | Count | Example | What our film showed |
|---|---|---|---|
| A claim with a source (Apple, iFixit, Macworld, reviewers, an owner) | ~16 | "Apple has now responded…", "iFixit's teardown offers one theory" | mostly a white phone turning; once a plain quote card |
| A date / timeline | 5 | "On October 26, it acknowledged…" | three unrelated "Oct 26" style cards |
| A figure / two figures | ~9 | "$999 … or $99 with it", "5.4 inch … 7.6 inch" | 2 two-sided figures; the rest a turning phone |
| A problem | 4 | "cracks along the fold", "hinges that won't open" | a generic phone, a blue "hinge" box |
| Opinion / take | ~6 | "So my take is simple" | a turning phone, "Wait" type |
| Questions | 3 | "So what is the cause?" | a turning phone |
| Opening / sign-off | 3 | "Let's break down what's happening" | a turning phone |

**Why it failed.** Today's work built the figure, colour and lens pieces (rows 3-5 of section 3). This script mostly needs
rows 2, 6, 7 and 8: sources, the timeline, and real problem pictures. Those are not built, so 50 % of the film fell back to an empty phone.
And the phone itself had the wrong design.

## 6. The smallest change that follows from this (proposal, nothing built)

One rule, not a list of features: **no empty phone shots**. Each sentence is sorted into one of the kinds in section 3, and its
picture comes from that row. Where that picture cannot be made yet (no real photo, no design pack), the scene before it **keeps building**
instead of cutting to an empty phone. A plain phone shot is allowed only when the sentence is about the design. To check it before any
render: the planner writes section 5's table (sentence, kind, picture) for the script, and we compare it with section 3 here.
