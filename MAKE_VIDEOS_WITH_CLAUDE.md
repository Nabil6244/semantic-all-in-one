# Making videos with Claude (no clicks)

Put this file (renamed to `CLAUDE.md`) and `make_video.py` in the folder where you run Claude Code or Claude Cowork. Then ask, for example:
"Make an Explainer video from `script.txt` and `voiceover.mp3`."

## For Claude: how to make a video

1. **Get the inputs.**
   - Most styles need the **voiceover** audio (.mp3/.wav/.m4a) and the **narration script** (.txt). The video follows the voiceover's real timing.
   - If something is missing, ask the user once.
2. **Pick the style.** Run `python3 make_video.py styles`. It lists every style, whether it needs a CSV, and whether it needs a voiceover. If the user names a style loosely ("the war one", "Jung"), match it to a name in that list.
3. **Write the CSV yourself** when the style needs one, or when it is optional and the user has no CSV:
   - Run `python3 make_video.py prompt --style <style>` and follow that prompt exactly, using the script.
   - Save the CSV next to the script: plain CSV, no code fence, no commentary.
   - For `kids-learn` the "prompt" is a sample lesson CSV: write the new lesson in the same columns.
   - A supplied CSV means the app makes no Gemini calls for planning.
4. **Run it in the background, then stop and wait to be notified.** Do not keep checking: every check uses the user's Claude credits, and a long video takes 1–2 hours.
   ```
   python3 make_video.py run --style explainer --voice voiceover.mp3 --script script.txt --csv scenes.csv --out ~/Desktop/video.mp4
   ```
   - Options: `--music track.mp3` (Product Trailer, Kids Learn, City Timelapse, Roblox Cinema, Health Cinema) and `--title "My video"`.
   - It prints each step and `VIDEO: <path>` at the end. Exit code 0 means done, 1 failed, 2 bad arguments.
   - Without background commands, use `--detach` and read `python3 make_video.py status <job.json>` only when the user asks.
   - Never start a second job while one runs. Both would drive the same app and use the same Flow accounts.
5. **When it ends:**
   - On success, give the user the video path.
   - On failure, the command prints the reason, the scenes that failed (number + reason), and the project folder. Tell the user in plain words.
   - Failed scenes: the app already retried them (3 rounds of Generate fetch only the missing scenes). The user can open the project in the app, Retry, replace or skip them in the Visuals tab, and press Render. Do not re-run the whole job blindly.

## Several videos (overnight)

When the user wants several videos, for example "make these 5 while I sleep":

1. **Before starting**, while the user is still there:
   - Check every input and ask about anything missing.
   - Write every CSV.
2. **Write a batch file** `videos.csv` next to the files. Paths can be relative to it.
   ```
   style,voice,script,csv,music,title,out
   explainer,venice/vo.mp3,venice/script.txt,venice/scenes.csv,,Venice,~/Desktop/venice.mp4
   war,moskva/vo.mp3,moskva/script.txt,moskva/scenes.csv,,Moskva,~/Desktop/moskva.mp4
   ```
3. **Check it, then start it.**
   - `python3 make_video.py batch videos.csv` refuses to start if any line is wrong and says which. Fix the lines, or add `--skip-bad` to run the valid ones.
   - It also refuses while the app is open: ask the user to close it.
4. **Start it in the background and stop.** Don't wait or check during the night; that only uses credits. The batch:
   - makes the videos one after another;
   - keeps the computer awake (the lid must stay open);
   - after a failed video, or one still running after `--max-hours` (default 6), stops that one and goes on to the next;
   - rewrites a report after every video: the path is printed at the start (`~/.videogen/jobs/batch_<time>_report.txt`).
5. **In the morning**, read the report to the user. It lists:
   - which videos are done and where;
   - which failed, with the reason and the failed scenes;
   - the project folder to open in the app, fix and Render.

## What the user must have set up once

- The app is installed (or this is the development folder, which has `app.py`), and the user has signed in once. If a sign-in is needed, the app window asks for it. The job waits up to 30 minutes, then goes on by itself. Never type passwords for the user.
- Flow (Google) accounts and any keys (Pexels and others) are set in the app's Settings. Claude cannot create accounts.

## What happens inside

`make_video.py run` starts the app with a job file (`SYT_AUTORUN`). The app opens its window and works like a person following its big button:

1. Makes a new project, adds the voiceover and script.
2. Clicks the style's card and fills the style page's file fields.
3. Presses the big button for whatever it asks next (load the CSV, Direct with Explainer, Generate the scenes, Make pictures, Render). While it shows Stop, the job waits.
4. Finishes when the video appears in the project's `final/` folder, then copies it to `--out`.

How pop-ups are handled:
- **File pickers** are answered with the job's files.
- **Questions** are answered **Yes**, which is the app's own way to go on.
- **An error** stops the job and reports its text.

Files: `~/.videogen/jobs/job_*.json`, `*.status.json`, `*.log`.
