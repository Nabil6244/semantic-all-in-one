# Doodle Survival — how to make a video

The AI (Gemini or Claude) draws the whole video itself through **videokit**. You give a script; the voice is yours or free.

## A. From the app (one button)
1. Open the app, choose or create a project.
2. Style picker → **Explainers → Doodle Survival**.
3. **Script (.txt)**: the story as it should be read. Optional: **Your voice** (else pick a free voice).
4. **AI**: *Gemini CLI* or *Claude Code*. Optional **Notes for the AI** ("make day 30 very dark", "3 zombies at the end").
5. Click **Make video**. Progress shows "reading the brief → voice aligned → n/N scenes drawn → n/N rendered → joined".
   A 40 s video takes about 10–20 minutes. The finished video lands in the project's final folder;
   **Open project folder** shows the work files (plan.json, scenes/*.html, clips/, ai.log).

## B. One-time setup for Gemini
Needs Node.js (already on this Mac).
```bash
npm install -g @google/gemini-cli
```
```bash
gemini
```
Sign in with your Google account once (free tier works; a Gemini API key or Google AI Pro raises the limits), then quit.
The app connects videokit to Gemini by itself for each video (it writes `.gemini/settings.json` in the work folder).

## C. Without the app: Gemini by hand
```bash
gemini mcp add videokit python3 /Users/muhammadnabil/Downloads/video_generator-main/agent_kit_mcp.py
```
Then in a new empty folder with your `script.txt` and `voice/voice.mp3`:
```bash
gemini --include-directories /Users/muhammadnabil/Downloads/video_generator-main/agent_kit/looks/doodle_dark
```
and ask: *"Use the videokit tools. Read agent_kit/looks/doodle_dark/README.md and 2 example scenes in its examples folder.
Make a Doodle Survival video in this folder from script.txt and voice/voice.mp3, look doodle_dark, until final.mp4 exists."*

## D. Claude
Same as A with **Claude Code** picked (found automatically, including the copy inside the Claude desktop app), or ask
Claude in this repo directly — videokit is already in `.mcp.json`.

## Tips
- Scripts that name concrete things per sentence (a radio, the barn door, 12 cans) give the best pictures.
- Say days out loud ("On day 12…"): every day becomes a DAY tag and a day card.
- Gemini is faster and cheaper; Claude usually draws richer scenes. Both follow the same README rules.
