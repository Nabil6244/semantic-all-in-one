# Semantic YT Studio — User Guide

Semantic YT Studio turns a **script + voiceover** into a finished video (`final.mp4`) automatically. Each scene's picture can come from a file you provide, from stock photo/video search, or from AI image generation — you choose per scene in a simple spreadsheet. No coding, no terminal.

---

## 1. Installing the application

Install the **full Semantic YT Studio app**. Qwen voice is **not** included — download it once later from inside the app when you need voice features.

**Windows (x64):**
1. Run `Semantic-YT-Studio-Setup.exe`.
2. Open **Semantic YT Studio**.
3. For voice: use in-app **Download** once (~several GB; needs internet).

**Mac (Apple Silicon only — M1/M2/M3/…):**
1. Open `Semantic-YT-Studio.dmg` and drag **Semantic YT Studio** to Applications.
2. Launch it (first time: right-click → Open if macOS warns about an unidentified developer).
3. For voice: use in-app **Download** once.

Intel Macs are not supported. You do **not** install Python, pip, conda, Torch, Node, or FFmpeg yourself.

**AI / Flow note:** On first use of Flow (Settings → AI / Flow Accounts, or Generate with AI scenes), the app downloads Playwright Chromium once into your user cache if Google Chrome is not already installed. That needs a working internet connection the first time only.

---

## 2. Creating your script CSV

Your script is a spreadsheet (CSV) with one row per scene. Columns:

| Column | Required? | What it is |
|---|---|---|
| `scene_number` | yes | 1, 2, 3, … |
| `script_segment` | yes | What's said in the voiceover during this scene |
| `prompt` | no | An AI image description (see §5) |
| `stock` | no | Search keywords for stock footage (see §4) |

Example:

```csv
scene_number,script_segment,prompt,stock
1,"A futuristic city appears at night.","cinematic futuristic city at night",
2,"People working in a modern office.",,"modern office workspace"
3,"A mountain journey begins.",,
```

Save it as `script.csv` (any spreadsheet app can "Export as CSV"). Older 2-column scripts (just `scene_number, script_segment`) still work exactly as before.

---

## 3. Adding your voiceover

Record or generate one audio file with your full narration, in order, matching the script. Any common format works (MP3, WAV, M4A). The app listens to it and automatically times each scene to match what's being said — you don't set timings by hand.

---

## 4. Using local assets (your own images/videos)

For any scene, leave both `prompt` and `stock` empty and put a file in your **Assets** folder named after the scene number:

```
Assets/
  001.png
  002.mp4
  003.jpg
```

Images and videos can be mixed freely. This works exactly like it always has.

---

## 5. Using Stock footage (Pexels)

Fill in the `stock` column with a few search keywords (e.g. `"modern office workspace"`) and leave `prompt` empty. The app searches Pexels, picks the best matching photo or video, and downloads it automatically for that scene.

Requires a Pexels API key — see §6.

---

## 6. Adding your Pexels API key

1. Get a free key at [pexels.com/api](https://www.pexels.com/api/) (sign up, copy your API key).
2. In Semantic YT Studio, click **Settings** (top right).
3. Under **Stock Providers**, paste your key and click **Save Key**.

The key is stored only on your computer. You only need to do this once, and only if you plan to use Stock scenes.

---

## 7. Adding Google Flow (AI) accounts

Fill in the `prompt` column with a description and leave `stock` empty to generate that scene's image with AI.

To set this up:
1. Click **Settings** → **AI / Flow Accounts** → **+ Add Google Account**.
2. Click **Sign in** next to the new account.
3. A real Chrome window opens — sign in to your Google account there, normally.
4. Close nothing; the app detects when sign-in succeeds and the window can be closed.

Repeat for as many Google accounts as you want to use. You only sign in once per account — after that, the app reuses that saved session.

**Your password is never seen, typed into, or stored by this app.** Sign-in happens entirely inside the real Chrome window, and only that window's own browser profile remembers you're logged in.

---

## 8. Understanding multiple Flow workers

Each signed-in Google account works **independently**, with its own browser profile and session — nothing is shared between accounts. If you have 4 accounts and 20 AI scenes, the app spreads the 20 prompts across all 4 accounts (about 5 scenes each) and generates them **at the same time**, so more accounts means faster AI generation.

In **Settings → AI / Flow Accounts**, each account shows a live status while generating:

- ● gray — idle / not working right now
- ● amber — signing in / preparing
- ● blue — generating a scene
- ● green — ready / finished
- ● red — error (check the message next to it)

You don't have to do anything to manage this — just add accounts, sign them in once, and the app uses however many you've added.

---

## 9. Generating a video

1. Choose your **Script CSV**, **Voiceover Audio**, and **Assets Folder**.
2. Check the **Scenes** table — it shows each scene's source (AI / Stock / Manual) before you start.
3. Click **Generate Video**.
4. Watch progress in the Activity panel: assets are resolved first (AI generated / stock downloaded / local files checked), then the video is transcribed, aligned, and rendered.
5. When done, your video opens in the preview panel and is saved where you chose.

---

## 10. Regenerating a scene

Not happy with one scene's AI or Stock picture? In the Scenes table, click **Regenerate** on that row:

- **AI scenes** — sends the same prompt again for a fresh result.
- **Stock scenes** — searches again, skipping the picture it already tried.

Only that one scene changes — nothing else is re-done, and you don't need to re-run the whole video.

---

## 11. Cancelling generation

Click **Cancel** while a run is in progress. Scenes still being generated or downloaded finish or stop shortly after; scenes not yet started are skipped. Scenes already completed are kept — a later run picks up only what's left, it won't redo finished work.

(Cancel affects picture generation. Once the final rendering step starts, it runs to completion.)

---

## 12. Troubleshooting

| Problem | What to do |
|---|---|
| "No prompt, no stock keywords, and no local file found" | That scene has nothing to show — add a prompt, stock keywords, or a file in Assets named for that scene number |
| "No Pexels API key is set" | Add one in Settings → Stock Providers (§6) |
| "No suitable stock result found" | Try broader/different keywords in the `stock` column, or use **Regenerate** |
| "No signed-in accounts" | Add and sign in to at least one Google account in Settings (§7) |
| A Flow scene fails repeatedly | That account may need signing in again — check its status dot in Settings; red means there's a problem to look at |
| Video/audio feel out of sync | Make sure `script_segment` text matches what's actually said in the voiceover |
| App won't open (Mac) | Right-click the app → Open, then confirm — only needed the first time |
| First Flow/AI use is slow or mentions Chromium | The app is downloading Playwright Chromium once; needs internet. Or install Google Chrome and retry |
| Generation seems slow | AI scenes generate one browser session per account; more signed-in accounts run more scenes in parallel |

Still stuck? Note the exact message shown and the scene number it mentions, and send it to whoever set up the app for you.
