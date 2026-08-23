# Semantic YT Studio

**Semantic YT Studio** turns a narration script into a finished video (`final.mp4`). Each scene’s picture or clip can come from AI (Google Flow), stock (Pexels), YouTube, or a file you provide. Voiceover is **your own audio file** (MP3/WAV/M4A/…) — import it in the app.

| | |
|---|---|
| **App name** | Semantic YT Studio |
| **Windows** | `Semantic-YT-Studio-Setup.exe` (x64) |
| **macOS** | `Semantic-YT-Studio.dmg` (Apple Silicon only — M1/M2/M3/…) |
| **Projects** | `~/Downloads/Semantic YT Studio/` (or `~/Semantic YT Studio/` if Downloads is missing) |

Intel Macs are not supported. You do **not** install Python, pip, Node, or FFmpeg yourself.

Desktop builds come from the **Build Desktop Apps** GitHub Actions workflow (artifacts retained ~14 days).

---

## 1. Install

**Windows (x64)**  
1. Run `Semantic-YT-Studio-Setup.exe`.  
2. Open **Semantic YT Studio**.

**Mac (Apple Silicon)**  
1. Open `Semantic-YT-Studio.dmg` and drag **Semantic YT Studio** to Applications.  
2. First launch: right-click → **Open** if macOS warns about an unidentified developer.

**AI / Flow note:** On first Flow use (Settings → AI / Flow Accounts, or Generate with AI scenes), the app may download Playwright Chromium once into your user cache if Google Chrome is not installed. That needs internet the first time only.

---

## 2. Typical workflow

Every launch is a **fresh session** — the last project is not opened automatically. A **Choose a project** modal appears first. You cannot work until you pick one.

The main button always does the next action: **Analyze Script** / **Import CSV** / **Generate Assets** / **Import Voiceover** / **Render Video**. While a job runs it becomes **Stop**.

1. **Choose a project** — create new, pick an existing project (`#001 Title`), or **Open folder**. Last-used may be labeled but is not loaded until you select it.  
2. **Paste script** (default, recommended) or **Import CSV**. Paste narration → **Analyze Script**, or import a visual-plan CSV.  
3. **Generate Assets** — resolve AI / stock / YouTube / local media per scene.  
4. **Voiceover** — import your narration audio (one **Play** toggle to preview).  
5. **Render Video** — Whisper alignment + FFmpeg export to the project’s `final/` folder.

Top bar: project chip (`#001 Title`) + **Switch** (reopens the picker), and a 5-step stepper: **Script → Scenes → Assets → Voice → Render**. Narrow windows show `Step N of 5 · Name`. The left column scrolls; the desktop window is resize-safe.

---

## 3. Projects

Each video is one project folder, for example:

```
Downloads/Semantic YT Studio/
  001_My_Video_Title/
    script/          narration.txt
    csv/             visual_plan.csv
    audio/           your voiceover (e.g. narration.wav, voiceover.mp3)
    assets/          local files you drop in (001.png, …)
    flow/ stock/ youtube/ …
    final/           final.mp4, final_1.mp4, …
    project.json
```

On launch, **Choose a project** lists existing folders as `#001 Title`. Create new, pick one, or **Open folder**. Closing the dialog does not select a ghost project — click **Choose project** to open the picker again.

The top-bar chip shows the current project. **Switch** reopens the picker. Closing the app keeps everything on disk; the next launch still starts fresh and does not auto-open the last project.

---

## 4. Script modes

### Paste script (recommended)

Default mode. Fields use placeholders inside the inputs (not ALL-CAPS labels over empty boxes).

1. Settings → paste a **Gemini** API key (Gemini 3.6 Flash visual director).  
2. Paste your full narration.  
3. Click **Analyze Script** in this section — Gemini writes a visual plan CSV (`asset_type` + `prompt` per scene). There is no separate Analyze button in the top bar.  
4. Optionally **Export CSV**.

### Import CSV

Choose a visual-plan spreadsheet (see §5). Older 2- or 4-column scripts still work.

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

## 7. Voiceover

Import the audio the final video will use:

1. In the **Voiceover** section, choose an MP3/WAV/M4A (or similar) file. The field uses a placeholder until a file is set.  
2. The file is copied into the project `audio/` folder when a project is open.  
3. Use the **Play** toggle to preview the selected file.  
4. When scenes are ready and no audio is set, the main button is **Import Voiceover**. After audio is set, it becomes **Render Video**.

**Background music** is optional and collapsed — expand it only if you want a bed under the voiceover.

Older project folders may still contain `narration.wav` or `voiceover_qwen*` files — those are discovered like any other audio; there is no built-in TTS / voice-clone engine.

SFX and other app data still use `~/.videogen/` where applicable (unrelated to voiceover).

---

## 8. Generate Assets & Render

1. Review the **Scenes** table (source tags: AI Image/Video, Stock, YouTube, Manual, Local).  
2. Click **Generate Assets**. The main button becomes **Stop** — cancels remaining scene work (in-flight Flow/stock may finish shortly; completed scenes are kept).  
3. Select a scene to open the inspector — recovery actions (retry, alternatives, **Change Source**) appear there. **Go to Error** / **Issues** show only when there are failures. **Cleanup** and **Activity** live in an overflow menu.  
4. When every scene is ready and audio exists, the main button is **Render Video**. If audio is still missing, it is **Import Voiceover**.  
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
| App opened with no project / last video missing | Every launch is fresh. Use **Choose a project** — last-used may be labeled but is not opened automatically |
| Closed the project picker | Click **Choose project** (nothing is selected until you pick one) |
| Main button is **Analyze Script** or **Import CSV** | Paste narration and Analyze, or switch to **Import CSV** and pick a file |
| Main button is **Import Voiceover** | Choose an audio file in the Voiceover section |
| “No prompt / stock / local file” | Fill `asset_type` + `prompt`, or drop `001.png`-style files |
| “No Pexels API key” | Settings → Stock |
| “No signed-in accounts” | Settings → AI / Flow Accounts → Sign in |
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

Team installers are **Build Desktop** artifacts from that workflow.
