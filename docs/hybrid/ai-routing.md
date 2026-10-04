# Hybrid Map: AI routing

Hybrid Map plans a documentary with AI, one chapter at a time. Everything that code can do, code does; AI is asked only where judgment is needed.

## Flow

```
Narration -> Whisper (local) -> chapters (local) -> Director (AI router: Gemini, then Groq)
          -> validate (local) -> fix what code can fix (local) -> suspicious?  no -> accept
                                                                    yes -> Critic (Groq first) -> targeted Repair (Groq first) -> validate (local) -> accept
```

* `ai_router/` is the only place that knows about providers. Hybrid calls `llm.run_task(task, system, user, accept=...)`.
* Tasks: `director`, `critic`, `repair`, `utility`. Routes per task are data (`ai_router/config.py`, overridable in Settings > AI providers).
* Default routes: Director = Gemini main model, Gemini second model, Groq. Critic and Repair = Groq, then Gemini only if Groq cannot.
* The plan schema, validator, compiler and renderer do not know which provider wrote a plan: a Groq plan must pass exactly the same checks.

## Failures are classified, not retried blindly

| Failure | What the router does |
|---|---|
| per-minute rate limit | rest that route for the stated time, use the next route (one short wait if it is the only one) |
| daily / project quota | rest that route (remembered across restarts), next route immediately, no retries |
| access denied, invalid key, missing model | retire that route for the session |
| 5xx, timeouts | two short retries on the same route, then the next route |
| bad request | stop: no other route would accept it |
| unreadable answer | one corrective retry, then the next route |
| nothing can answer | stop cleanly: `AllRoutesUnavailable`, saved chapters kept |

Gemini keys: the main key plus up to four backups (Settings, or `GEMINI_API_KEY_1..4`). A key that is permanently refused is retired for the session; the others carry on. Keys from the same Google project share one quota.

## What costs AI calls

* Director: one request per chapter (about 6 minutes of narration).
* Critic: **only** when local checks suspect something creative (monotony, repetition, an unbalanced mix, chapters that open alike). Flagged chapters are reviewed together in one compact request (one line per beat), not one request each.
* Repair: **only** for beats that still have a defect after local fixes, one chapter per request, carrying just the weak beats, their neighbours, the complaint and a compact story-so-far.
* One repair cycle is the default. Local checks, deterministic fixes and the final validation cost nothing.

## Saved work

* `hybrid/_chapters/chapter_NNN.json`: each chapter's Director answer (never re-asked for the same script, prompt and guidance).
* `hybrid/_ai/cache/`: every accepted AI answer by request identity (whitespace-insensitive); a rerun costs nothing.
* `hybrid/_ai/route_state.json`: routes that are resting (a daily quota survives a restart).
* `hybrid/_ai/ai_calls.jsonl`: one safe line per request (task, provider, model, attempt, outcome, failure class, latency, tokens). No prompts, no keys.
* `hybrid/_chapters/planning_state.json`: where planning stopped.
