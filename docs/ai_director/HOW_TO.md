# AI Director: Claude or Gemini makes the video

You give a **script** (and a **voiceover**, or pick a free Edge voice). The AI makes the whole video itself with the
Video Kit: real 3D land and seafloor, 3D rock cut-aways, maps, real footage and animals, short text, every scene timed
to your voice, music and sound effects.

## One-time setup (two clicks)
On the AI Director page, next to **AI**:
1. Click **Set up / sign in**. It uses the Claude already on this computer (the Claude app's own Claude Code), or installs
   Claude Code / Gemini CLI if there is none, and opens it in a Terminal window.
   - Claude: type `/login`, press Return, sign in in the browser, then type `/exit`.
   - Gemini: choose **Login with Google**, sign in, then type `/quit`.
2. Click **Check**. It asks the AI one tiny question and shows *ready: installed and signed in*.

The Claude app and its Claude Code keep separate sign-ins, so this is needed once even when the Claude app is already signed in.
Gemini needs Node (npm) installed; a free Google account has a daily allowance, so test 2 minutes first.

## Make a video in the app
1. Open a project, pick the style **AI Director** (Documentary group).
2. Choose the **script** (.txt) and your **voiceover** (mp3/wav), or leave the voiceover empty and pick an Edge voice.
3. **AI**: Claude Code or Gemini CLI. **Length**: start with *Test: first 2 minutes*. **Look pack**: Teal documentary,
   Cartoon history (drawn) or Doodle night story. **Notes** (optional): a few words.
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
