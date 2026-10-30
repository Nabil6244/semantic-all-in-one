# Semantic Intelligence Engine (measured on project 047, 373 scenes)

Setting: `ai_planning` in settings.json: `auto` (default), `off`, `full`. No Gemini key means AI is never asked.

| Stage | Before (real run) | After (measured) |
|---|---|---|
| Editorial AI | ~212 s, 10 sequential calls, 6 truncated, stopped at first failure, 28 of 373 intents | cold 184.9 s, warm 90.3 s, but Gemini quota was spent during the run: 144 AI intents, 229 rules fallback; no truncation |
| Ambience | Gemini call 51.8 s, result then overridden by a substring heuristic | rules only 0.36 s for 373 scenes; Gemini only for conflicting scenes |
| SFX | generic beat accents | event-based, 1 detected event on 047 (library has impacts, machinery, clicks, water, movement, tension) |
| Mix (ffmpeg) | not measured | 68.2 s, 130 SFX + 373 beds, no fallback |

Not measured: a cold run with healthy Gemini quota. The quota error was found afterwards by a direct probe; the warm 90 s was spent on spent-quota retries, fixed by stopping all remaining batches after the first quota error (test added).
