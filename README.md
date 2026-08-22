# Semantic YT Studio

**Semantic YT Studio** turns a narration script into a finished video (`final.mp4`). Each scene’s picture or clip can come from AI (Google Flow), stock (Pexels), YouTube, or a file you provide. Voiceover can be your own recording or a cloned voice via **Qwen3-TTS** (downloaded once in-app).

| | |
|---|---|
| **App name** | Semantic YT Studio |
| **Windows** | `Semantic-YT-Studio-Setup.exe` (x64) |
| **macOS** | `Semantic-YT-Studio.dmg` (Apple Silicon only — M1/M2/M3/…) |
| **Projects** | `~/Downloads/Semantic YT Studio/` (or `~/Semantic YT Studio/` if Downloads is missing) |
| **Voice engine** | Not in the installer — in-app **Download** once into `~/.videogen/` |
| **Voice model** | [Qwen/Qwen3-TTS-12Hz-1.7B-Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) |

Intel Macs are not supported. You do **not** install Python, pip, Torch, Node, or FFmpeg yourself.

Desktop builds come from the **Build Desktop Apps** GitHub Actions workflow (artifacts retained ~14 days). Qwen portable runtimes ship on Release tag `install-v1` (not inside the DMG/Setup).

---

## 1. Install

**Windows (x64)**  
1. Run `Semantic-YT-Studio-Setup.exe`.  
2. Open **Semantic YT Studio**.  
3. For voice: use in-app **Download** once (~several GB; needs internet).

**Mac (Apple Silicon)**  
1. Open `Semantic-YT-Studio.dmg` and drag **Semantic YT Studio** to Applications.  
2. First launch: right-click → **Open** if macOS warns about an unidentified developer.  
3. For voice: use in-app **Download** once.

**AI / Flow note:** On first Flow use (Settings → AI / Flow Accounts, or Generate with AI scenes), the app may download Playwright Chromium once into your user cache if Google Chrome is not installed. That needs internet the first time only.

---

## 2. Typical workflow

The main button follows your progress. While a job runs it becomes **Stop** (not “Generating…”).

1. **＋ New Project** — creates a folder under Downloads for this video.  
2. Choose **Manual CSV** or **AI Script**.  
3. Build a visual plan (import CSV, or paste narration → **Analyze Script**).  
4. **Generate Assets** — resolve AI / stock / YouTube / local media per scene.  
5. **Voice** — Download Qwen if needed → **+ Create Voice** → **Generate Narration** (or browse an existing voiceover).  
6. **Render Video** — Whisper alignment + FFmpeg export to the project’s `final/` folder.

Stage labels in the top bar: `SCRIPT` → `PLAN` → `GENERATE` / `REVIEW` → `VOICE` → `EXPORT`.

---

## 3. Projects

Each video is one project folder, for example:

```
Downloads/Semantic YT Studio/
  001_My_Video_Title/
    script/          narration.txt
    csv/             visual_plan.csv
    audio/           narration.wav (after Generate Narration)
    assets/          local files you drop in (001.png, …)
    flow/ stock/ youtube/ …
    final/           final.mp4, final_1.mp4, …
    project.json
```

Use the project menu to switch, open another folder, or start a new project. Closing the app keeps everything on disk.

---

## 4. Script modes

### AI Script (recommended)

1. Settings → paste a **Gemini** API key (Gemini 3.6 Flash visual director).  
2. Paste your full narration.  
3. Click **Analyze Script** — Gemini writes a visual plan CSV (`asset_type` + `prompt` per scene).  
4. Optionally **Export CSV**.

### Manual CSV

Point **Script CSV** at a spreadsheet (see §5). Older 2- or 4-column scripts still work.

---

## 5. Visual plan CSV

### Current format

| Column | Required? | What it is |
|---|---|---|
| `scene_number` | yes | 1, 2, 3, … |
| `script_segment` | yes | Words said during this scene |
| `asset_type` | yes* | How to get the visual (see below) |
| `prompt` | usually | AI prompt, stock keywords, or YouTube search text |

\*Required for the new format. Omit `asset_type` only when using the legacy columns below.

**`asset_type` values:**

| Value | Source |
|---|---|
| `image` / `flow_image` | Google Flow AI still |
| `video` / `flow_video` | Google Flow AI video |
| `stock` / `stock_image` / `stock_video` | Pexels (`prompt` = search keywords) |
| `youtube_video` | YouTube clip (`prompt` = search query; `\|\|` separates alternatives) |
| `local` | File in the project **assets** folder named for the scene (`001.png`, `002.mp4`, …) |

Example:

```csv
scene_number,script_segment,asset_type,prompt
1,"A futuristic city appears at night.",video,"cinematic futuristic city at night"
2,"People working in a modern office.",stock_video,modern office workspace
3,"A mountain journey begins.",youtube_video,mountain trail sunrise hiking || alpine ridge sunrise
4,"Close on the logo.",local,
```

### Legacy format (still supported)

```csv
scene_number,script_segment,prompt,stock
1,"City at night.","cinematic city",
2,"Office work.",,"modern office"
3,"Mountains.",,
```

- Non-empty `prompt` → AI image  
- Non-empty `stock` → Pexels  
- Both empty → local file in Assets  

---

## 6. Settings you may need

| Feature | Where | Notes |
|---|---|---|
| **Pexels** | Settings → Stock | Free key from [pexels.com/api](https://www.pexels.com/api/) |
| **Gemini** | Settings | Required for **Analyze Script** |
| **Google Flow** | Settings → AI / Flow Accounts | Sign in once per Google account in a real Chrome window. Password is never stored by the app. |
| **Whisper / captions** | Settings | Transcription model and burn-in captions |
| **YouTube clip options** | Settings | Clip length, search depth, transcript matching |

Keys stay on your computer only.

### Multiple Flow accounts

Each signed-in Google account is independent. More accounts → more AI scenes in parallel. Status dots in Settings:

- gray idle · amber preparing · blue generating · green ready · red error  

---

## 7. Voice (Qwen)

1. Click **Download** in the Voice panel (progress bar + ✕ to cancel). Completes only at **100%** when every model file matches the install manifest.  
2. **+ Create Voice** — name, reference audio, transcript of *only* what is spoken in that clip.  
3. Select the voice → **Test Voice** (play/pause + stop).  
4. Paste full narration (or use the project script) → **Generate Narration**.  
5. While generating, the button shows **Stop** — cancels the voice worker.

You can still browse any MP3/WAV/M4A as the video’s voiceover instead of Qwen.

Runtime + model live under `~/.videogen/` (portable Python runtime + `qwen3-tts/…`). Re-open the app anytime; if something is incomplete, **Download** appears again with progress when a partial file exists.

---

## 8. Generate Assets & Render

1. Review the **Scenes** table (source tags: AI Image/Video, Stock, YouTube, Manual, Local).  
2. Click **Generate Assets**. The CTA becomes **Stop** — cancels remaining scene work (in-flight Flow/stock may finish shortly; completed scenes are kept).  
3. Fix failures with **GO TO ERROR**, retry, alternatives, or **Change Source** on a row.  
4. When every scene is ready and audio exists, the CTA becomes **Render Video**.  
5. Preview opens when export finishes; files land in the project `final/` folder.

**Stop / cancel** applies to asset resolution. Whisper transcription and FFmpeg render are not interruptible once started.

Per-scene **Regenerate** re-runs that provider only (AI again, or stock again skipping the last pick). **Change Source** switches a scene to another provider without rebuilding the whole plan.

---

## 9. Local assets

For `local` scenes (or legacy rows with empty prompt/stock), put files in the project **assets** folder:

```
assets/
  001.png
  002.mp4
  003.jpg
```

Images and videos can be mixed.

---

## 10. Troubleshooting

| Problem | What to do |
|---|---|
| CTA says “New Project first” | Create or open a project |
| “Analyze or import CSV” | Paste script + Analyze, or choose a CSV |
| “Generate Narration first” | Create/select voice and generate narration, or browse an audio file |
| “No prompt / stock / local file” | Fill `asset_type` + `prompt`, or drop `001.png`-style files |
| “No Pexels API key” | Settings → Stock |
| “No signed-in accounts” | Settings → AI / Flow Accounts → Sign in |
| Qwen still shows Download | Wait for 100%; incomplete/corrupt files are re-downloaded |
| Video/audio out of sync | Make `script_segment` match what is actually said |
| App won’t open (Mac) | Right-click → Open (first launch only) |
| First Flow use is slow | Chromium download once; or install Google Chrome |
| Generation feels slow | Add more signed-in Flow accounts for parallel AI scenes |

Still stuck? Note the exact message and scene number.

---

## 11. Build / release (maintainers)

| Workflow | Produces |
|---|---|
| **Build Desktop Apps** | `Semantic-YT-Studio.dmg`, `Semantic-YT-Studio-Setup.exe` |
| **Build Qwen Runtime** | `qwen-runtime-darwin-arm64.zip`, `qwen-runtime-win-amd64.zip` |
| **Publish Install Payloads** | Attaches runtime zips to Release `install-v*` and prints SHA-256 for `tts/install_manifest.json` |

Model file hashes: `python scripts/fill_model_manifest.py --write`. Team installers are **Build Desktop** artifacts, not the `install-v1` Release assets.
