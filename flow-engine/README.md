# flow-engine

Headless Google Flow generation engine, extracted from
`semantic-automator-main/desktop/` (commit-time snapshot, 2026-08-18). This is
**not** a fork of the whole Semantic Automator desktop app — only the
automation core, with Electron, the HUD's own `public/` GUI, and all
Firebase/Stripe/licensing/admin code left out:

| Kept (copied verbatim) | Left out |
|---|---|
| `server.js` — WS+HTTP server, `127.0.0.1` only | `electron-main.js` |
| `lib/flow-api.js` — Flow REST calls, reCAPTCHA, retry error types | `desktop/public/` (HUD GUI) |
| `lib/batch-runner.js` — per-account prompt loop, retry/backoff/model-fallback | `electron-builder` packaging config |
| `lib/orchestrator.js` — multi-account concurrency, prompt slicing | |
| `lib/accounts.js` — Playwright persistent browser contexts | |
| `lib/paths.js`, `lib/store.js` — on-disk account registry (plaintext, no secrets) | |
| `config.js` — trimmed to only the constants these files use | Firebase config, Stripe URLs, admin emails, access/quota |

**Why this exists:** the Video Generator (Python) needs to turn a CSV prompt
into a downloaded image. Google Flow's generation API is undocumented and
requires a real authenticated browser session + a reCAPTCHA Enterprise token
minted in-page — `flow-api.js`/`accounts.js` already do this correctly and
handle retry/quota/model-fallback, so this engine reuses that logic verbatim
instead of reimplementing it. It runs as a plain background Node process
(`node server.js`, no Electron needed — confirmed the original app's own
`npm start` script does the same) and speaks the *same* WebSocket protocol
`desktop/public/app.js` already used, over `ws://127.0.0.1:<port>/ws`.
`providers/flow/client.py` in the Python app is a client for that exact
protocol — see `GENERATE`/`STATE`/`BATCH_PROGRESS`/`BATCH_DONE` in
`server.js`.

**Setup (development):**

```bash
cd flow-engine
npm install
npm run install-browser   # optional in CI/dev; packaged app downloads Chromium on first Flow use
npm start                 # http://127.0.0.1:8787
```

**Packaged app:** `node_modules` (including Playwright) ship inside the app; Chromium
itself is **not** bundled. On first Flow/AI use the Python host runs
`node node_modules/playwright/cli.js install chromium` via the bundled Node
binary (`providers/playwright_chromium.py`) into the user Playwright cache.
System Google Chrome is preferred when present (`lib/accounts.js`).

**Provenance / updating:** if `semantic-automator-main/desktop/lib/*` gets a
bug fix upstream, port it here manually — this is a deliberate one-time
extraction, not a live link (the two products' needs have already diverged:
this engine is headless-only, the original is Electron-packaged with its own
HUD). Do not modify the original `semantic-automator-main` checkout as part of
maintaining this copy.
