# AI Director: Claude or Gemini makes the video

You give a **script** (and a **voiceover**, or pick a free Edge voice). The AI makes the whole video itself with the
Video Kit: real 3D land and seafloor, 3D rock cut-aways, maps, real footage and animals, short text, every scene timed
to your voice, music and sound effects.

## One-time setup

### Claude (already on this Mac)
The Claude app's Code tab installs Claude Code. Its command-line copy keeps its own sign-in, so sign in once:

1. Open **Terminal**.
2. Paste this (with the quotes) and press Return:
   ```
   "$HOME/Library/Application Support/Claude/claude-code/2.1.330/4262a1273231/claude.app/Contents/MacOS/claude"
   ```
   (the version folder may change after an update; the AI Director page shows the current path)
3. Type `/login`, sign in in the browser, then type `/exit`.

### Gemini
1. Open **Terminal** and install it (Node is already on this Mac):
   ```
   npm install -g @google/gemini-cli
   ```
2. Run `gemini` once, choose **Login with Google**, sign in, then type `/quit`.
   A Google account gets a free daily allowance; a long video can use it up, so test 2 minutes first.

## Make a video in the app
1. Open a project, pick the style **AI Director** (Documentary group).
2. Choose the **script** (.txt) and your **voiceover** (mp3/wav), or leave the voiceover empty and pick an Edge voice.
3. **AI**: Claude Code or Gemini CLI. **Length**: start with *Test: first 2 minutes*. **Look** (optional): a few words.
4. Click **Generate**. The AI's steps show in the log; Stop ends it. The video lands in the project's final folder; the
   AI's work (plan, scene pages, clips) is in *Open work folder*.
5. Happy with the test? Pick *Whole video* and Generate again in the same project: rendered clips are reused.

## Make a video from Terminal (no app)
```
cd ~/Downloads/video_generator-main
python3 -m agent_kit.runner --agent gemini --script ~/Downloads/my_video/script.txt --voice ~/Downloads/my_video/voice.mp3 --out ~/Downloads/agent_videos/my_video --minutes 2
```
`--agent claude` for Claude, `--minutes 0` for the whole video, no `--voice` for the free Edge voice.

## Or talk to it yourself
In Terminal: `cd ~/Downloads/agent_videos/my_video` (after a run, or after `--prepare-only`), then run `gemini`
(or Claude) and say: *"Read TASK.md and do it."* You can watch and give notes as it works ("more animals here").

## What the AI is allowed to do
Only the Video Kit tools (align, find, map, terrain, check_plan, scene, look, join) and writing files in its project
folder. It cannot run other commands. Claude: `--strict-mcp-config`, `--allowedTools mcp__videokit Read Write Edit`,
`--permission-mode acceptEdits`. Gemini: the kit server is trusted in the project's `.gemini/settings.json`,
`--approval-mode auto_edit`; shell commands need approval, which a headless run cannot give, so they are refused.
