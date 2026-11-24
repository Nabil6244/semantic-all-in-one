# Podcast Cut style: plan

Planned 2026-11-23. Nothing built yet.

## What we are copying (the pattern, not the channel)

Reference: Aerondight (handle @ExcelsiorSpirit). Studied video: "The Only 35 Minutes You Need To Rebuild Yourself | Andrew Huberman Motivation" (666K views).

- **Audio:** one long podcast episode cut down to 30–38 min. Host questions stay in. No narrator of our own. A quiet cinematic music bed runs the whole way.
- **Hook:** the strongest 15–25 s line from the middle of the talk plays first. Then a short "<Channel> presents" card over a sunset or skyline. Then the body, in the order it was said.
- **Picture:** about half the time it's the podcast's own camera. The rest is dark, moody stock: rainy streets at night, city aerials, skylines, a lone person at a window, forest, hands, a crowd from above. The stock mostly matches the mood. It only matches the words when a concrete thing is said (sharks, ice bath, car crash, marathon). A shot changes every 3–6 s.
- **Look:** heavy dark grade, low contrast, black and warm gold. Vignette. 16:9.
- **Text:** one small line of spaced uppercase caption in the middle of the frame, timed to the words. A small channel watermark sits bottom-centre.
- **Packaging:** "The Only N Minutes You Need To <Change> | <Speaker> Motivation", where N is the real length. A new video almost every day. The 30–38 min videos get the most views.

## Inputs (on the app page)

| Field | Default | Notes |
|---|---|---|
| Podcast | — | A YouTube link **or** a local .mp4/.mp3/.m4a |
| Target length | 35 min | 10–45 min. Picker hits it ±1 min |
| Speaker name | from video title | Goes in the title and thumbnail |
| Channel name | user setting | For the "presents" card and the watermark |
| Clip CSV (optional) | — | If given, it **is** the plan: zero Gemini calls, the picker is skipped |
| Preview | off | 720p fast render |

Nothing starts until Generate. Picking files and options only remembers them.

## Pipeline

New package `podcast_cut/`. It follows the Food Files layout: `runner.py` (plan / render), `fetch.py`, `picker.py`, `clipcsv.py`, `check.py`, `director.py`, `library.py`, `look.py`, `captions.py`, `audio.py`, `render.py`, `titles.py`.

### 1. Fetch (`fetch.py`)
- YouTube link: full download (best ≤1080p video + audio) through the existing yt-dlp code in `providers/youtube/strategies.py`. It is cached per video id in `out/podcast_cut/<id>/source.*`, so a second run never downloads again.
- Word times: use YouTube captions when the video has manual ones. Otherwise run Whisper with the existing model-reuse helper (word timestamps).
- Local file: skip the download and run Whisper.
- If the episode is audio only (mp3), there's no speaker camera. The director then uses b-roll only, plus an optional speaker photo with a slow push.

### 2. Clip picker (`picker.py`): no Gemini needed
- Split the transcript into **thoughts**: groups of sentences that end on a pause of 0.6 s or more.
- Drop the junk: sponsor reads, intros and outros, "subscribe / link in the description", housekeeping, crosstalk, long laughs. This uses a keyword list plus a "speaker is the host and talks for less than 4 s" rule.
- Score each thought on: punchy short sentences, "you"-talk, advice verbs, stories ("I remember", "when I was"), numbers, and how much it repeats the episode's main words.
- Choose stretches to hit the target length. Keep them in time order. Keep a host question only when the chosen answer needs it. Every cut lands on a pause (cut ±80 ms, 20 ms audio crossfade).
- Hook: the best-scoring 15–25 s stretch. It plays first and also stays in its normal place, like the reference.
- The result is saved as a **clip CSV**: `n, start, end, role (hook/body/question), text`. The user (or Claude, from a transcript) can edit it and run again.
- Optional, and only when there is no CSV: one Gemini pass to re-rank the top candidates. It's off by default.

### 3. Footage director (`director.py`)
- Cut the timeline into 3–6 s windows on word boundaries.
- **Speaker camera** on: questions, the first ~8 s after each jump, emphatic moments (loud or fast speech), laughs. Aim for about 45–50 % over the whole video. Never more than 25 s of b-roll in a row, and never more than 20 s of camera in a row.
- **B-roll**:
  1. If a concrete, filmable noun is said in that window (shark, ice bath, marathon, car crash, hospital, phone, gym), run a literal stock search for it (Pexels / Pixabay, existing `providers/stock`).
  2. Otherwise use a **mood clip** from the library, chosen by the window's feeling: struggle, calm, ambition, loss, discipline, city, nature, thinking.
- No clip repeats within 8 minutes. Never use the same mood tag 3 times in a row.
- If the source video has burned-in captions or a lower third, there's an optional crop and blur strip.

### 4. Mood library (`library.py` + `scripts/build_podcast_mood_library.py`): built once
- About 400 free Pexels and Pixabay clips across about 25 mood tags (night rain street, city aerial night, skyline, window silhouette, forest light, ocean dusk, lone walker, gym dark, hands close, clock, crowd top-down, mountain mist, candle, desk at night, running dawn, …).
- Each clip is trimmed to its best 6–8 s, pre-graded into the look, and saved at 1080p. There's an index json with tags, length and brightness.
- One build script, run once. After that the user can drop their own clips into the library folder. Each video only downloads the literal gap fills.

### 5. Look (`look.py`)
- One ffmpeg grade for both the camera and the b-roll: lower the blacks, about −25 % saturation, warm the highlights, soft vignette, light grain. That way the podcast camera and the stock look like one film.
- The "presents" card: channel name over a sunset or skyline clip, 2.5 s, with a fade.

### 6. Captions (`captions.py`)
- One line of 3–6 words, small spaced uppercase, centred at about 52 % height. White at 85 %, with a soft shadow. Timed from the word times.
- Watermark: the channel name, small, bottom-centre, 35 % opacity.
- An option to turn captions off.

### 7. Audio (`audio.py`)
- Make the podcast audio even with the existing `audio_level.py` (from the PK style). Gentle de-ess and a light compressor.
- Music bed: the dark tracks in `assets/music` (dark_fog, echoes_of_time_v2, ascending_the_vale, …) at about −26 dB under speech. It dips a bit more on the hook, and the track changes every 6–9 minutes with a 4 s crossfade.
- No SFX. The reference has none.

### 8. Render (`render.py`)
- Pieces of about 60 s rendered in parallel (videotoolbox on Mac), then a stream-copy join. This is the GTA ch2 / Enoch fast-join pattern, so there's no whole-film re-encode. A 35-min video should take a few minutes, not an hour.
- Output: `out/podcast_cut/<name>.mp4` plus a thumbnail `.jpg` plus `chapters.txt`.

### 9. Titles, thumbnail, chapters (`titles.py`)
- Title choices built from the pattern, with the change verb drawn from the episode's main topic: "The Only {N} Minutes You Need To {Rewire Your Mind | Take Back Control | Reinvent Yourself} | {Speaker} Motivation".
- Thumbnail: the darkest, cleanest close-up of the speaker from the source (chosen by face size and sharpness), graded, with 2–3 big words.
- YouTube chapters from the clip CSV stretches.

## App wiring
- Its own style page `ui/podcastcut_section.py` with the inputs above. Generate → Render split, like Hybrid.
- **Visuals tab** through `visual_bridge.py`. Each b-roll window is listed with Retry / Change source / Use camera. The clip list can be edited there too.
- **Export page**: `_track_generation_start / _export_progress / _track_generation_end`.
- `make_video.py` STYLES entry `"podcast-cut"`, plus autorun for no-click overnight batches. A batch of podcast links gives one video each.
- Existing styles stay untouched.

## Build phases (each one is a separate yes)

1. **Fetch + transcript + picker + clip CSV + checker.** No rendering. Test it on the Huberman episode and read the chosen cuts.
2. **Mood library build** (one time, about 400 clips) plus the footage director.
3. **Renderer**: look, captions, audio, parallel pieces. One 2-min test render, sent to you.
4. **App page**, Visuals tab, Export, make_video, autorun.
5. **Titles, thumbnail and chapters**, then Shorts: 9:16 cuts of the best hook quotes, centred speaker crop, bigger captions.

## Risks
- **Rights:** the whole audio is someone else's podcast. It can get Content ID claims, and YouTube can treat it as "reused content" for monetisation. The edit (b-roll, cutting, captions) is what makes it count as changed. That's a choice for you, not something the code can fix.
- **YouTube downloads** sometimes need cookies or fail on age-gated videos. We fall back to a local file.
- **Speaker diarisation** (host vs guest): a simple rule first (who talks briefly before a long answer). pyannote is only an option if that isn't good enough.
- **Disk space:** a 2-hour 1080p source is about 2–4 GB. The source is deleted after export unless you choose to keep it.
