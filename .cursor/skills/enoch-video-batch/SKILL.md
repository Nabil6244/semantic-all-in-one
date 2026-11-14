---
name: enoch-video-batch
description: >-
  Builds Book of Enoch documentary packages end-to-end: Spanish script, visual CSV,
  and Alvaro (Spanish Spain) voiceover into videos_data/N/. Use when the user gives
  Enoch YouTube titles, asks for an Enoch batch, TalkTTS voiceovers for videos_data,
  or to run the script → CSV → voiceover workflow without re-explaining steps.
---

# Enoch video batch

Thin orchestrator. **Do not copy long writing rules into this skill.** Always read the live prompt files for content rules.

## Inputs the user must provide

- One or more English YouTube titles (and optional thumbnail labels).
- Optional start folder number (default: next empty `videos_data/N/` or `1` if empty).
- Optional: stop after script, after CSV, or after voiceover; default = all three.

## Paths (do not invent others)

| Role | Path |
|------|------|
| Script rules | `videos_data/script_prompt.txt` |
| CSV rules | `videos_data/csv_prompt.txt` |
| Per-video folder | `videos_data/N/` (`N` = 1, 2, 3, …) |
| Outputs | `script.txt`, `csv_file.csv`, `voiceover.mp3` |

**Never edit** `script_prompt.txt` or `csv_prompt.txt` unless the user explicitly asks.

## Pipeline

Copy and track:

```
For each title → folder N:
- [ ] 1. script.txt
- [ ] 2. csv_file.csv
- [ ] 3. voiceover.mp3
```

### 1. Script

1. Read `videos_data/script_prompt.txt`.
2. Substitute the title into that prompt’s title slot.
3. Write narration only to `videos_data/N/script.txt` (Spanish, voiceover-ready paragraphs).
4. **Do not** put a TITLE line in `script.txt` (CSV must match word-for-word).
5. Target ~4000–4300 words. Source-first from 1/2/3 Enoch; if the title’s claim is not in the texts, say so and investigate the closest genuine material.

### 2. CSV

1. Read `videos_data/csv_prompt.txt` (including any trailing user overrides in that file).
2. Build `videos_data/N/csv_file.csv` from the finished script.
3. Hard checks before finishing the video:
   - Header exactly: `scene_number,script_segment,asset_type,prompt`
   - Joining every `script_segment` == `script.txt` word for word
   - ≥170 `flow_image` (and/or `flow_video`) rows unless the prompt file says otherwise
   - No `map` rows; no Quranic/Islamic stand-in visuals
   - Never more than 2 consecutive `flow_*` rows
   - Stock searches: image 2–6 words with `||`; video 5–10 words; no empty prompts

### 3. Voiceover (TalkTTS)

1. Open https://talktts.io/
2. Language: **Spanish (Spain)** · Voice: **Alvaro - Male** · Speed **0** · Pitch **0**
3. Generate from the full `script.txt` (site limit ~200k chars; these scripts fit; chunk+ffmpeg only if rejected).
4. Save as `videos_data/N/voiceover.mp3`.
5. If UI paste is blocked, use the same `POST /api/tts` the Generate Speech button uses (`es-ES-AlvaroNeural`, rate 0, pitch 0). Report login/captcha/quota blockers instead of inventing audio.

## Parallelism

For many titles, split across agents by folder ranges (e.g. 1–3, 4–6). Keep one browser/TalkTTS owner at a time unless separate download paths are safe.

## Optional render (only if the user asks)

After folders have `script.txt`, `csv_file.csv`, and `voiceover.mp3`:

1. Close Semantic YT Studio.
2. Write a batch CSV (`style,voice,script,csv,music,title,out`) with style `enoch-template`.
3. Run: `python3 make_video.py batch <batch.csv>`

## What to change later (without rewriting this skill)

| Change | Edit this |
|--------|-----------|
| Script tone / length / source rules | `videos_data/script_prompt.txt` |
| CSV mix / Flow count / asset rules | `videos_data/csv_prompt.txt` |
| Voice, language, TTS site, file names, extra pipeline steps | this `SKILL.md` |

## Done criteria

For each `N`: all three files exist; CSV join == script; voiceover duration roughly matches a ~20–28 min Spanish read. Summarize a table: `N | words | csv rows | voiceover size/duration | notes (textual vs packaging)`.
