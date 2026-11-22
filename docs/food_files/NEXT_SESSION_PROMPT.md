Run the Food Files video "The Deadliest Drinks Ever Sold" in the new Flow-budget mode (fewest Flow clips, most of
them at the start), check it, and send me the video.

Context (all in this repo, uncommitted - do not commit unless I ask):
- Food Files = a host-led countdown style built on the Prepper Host spine: foodfiles/ (runner.py, director.py,
  cards.py, scene2d.py, sources.py, scriptcheck.py), app page ui/foodfiles_section.py. Plans and studies:
  docs/food_files/REFERENCE_AND_PLAN.md, IMPROVEMENT_PLAN.md, SCRIPT_STUDY.md.
- Script: foodfiles/scripts/deadliest_drinks.txt (passes `python -m foodfiles.scriptcheck`); CSV:
  foodfiles/scripts/deadliest_drinks.csv (built by foodfiles/scripts/make_drinks_csv.py).
- Host = Theo, pack in out/foodfiles/hosts/theo (Flow voice "Achird"; Flow has no "Puck").
- Budget mode (runner.front_load): at most 15 Flow clips, 60 % in the opening (~first 150 s), 30 % middle, 10 % end;
  host lines without a clip keep his cloned voice; late ones become free Flow pictures, the rest show mood-matched
  still poses (pose_for: never the laughing pose on deaths / illness). Expect ~15 clips = ~150 Flow credits.
- Last full render (stills mode, Edge voice) for comparison: out/foodfiles/deadliest_drinks.mp4 (14:43).

Steps:
1. Make sure nothing else is using Flow (my app may be running Rep Theory batches: a new Flow batch stops the
   running one). If the app is open and busy, tell me and wait. Never kill processes you did not start.
2. Run (in the background, unbuffered, with a log):
   python3 -u -m foodfiles.runner foodfiles/scripts/deadliest_drinks.csv --clips 15 --preview \
     --out out/foodfiles/deadliest_drinks_flowvoice.mp4 > out/foodfiles/drinks_flowvoice.log 2>&1
   and watch the log with a Monitor (Flow stage, errors, the "Flow clip budget" line, render %).
   Also watch the newest out/prepper_host/library/runs/*/*/flow-ui-generation.log for Flow-side errors
   (e.g. "voice_not_attached").
3. If a step stalls (no progress for ~5 min), find the cause and fix the code, not just restart. Known fixes already
   in: Edge voice 60 s per-try timeout (edge_voiceover.py), Flow dead-engine detection + wait-idle before each batch
   (prepper_host/flow.py), Commons one call per photo + 7-day miss memory + circuit breaker (foodfiles/sources.py,
   no contact/repo link in the User-Agent).
4. When it finishes: report the clip count and where they landed (minutes), host share and median shot from the
   final JSON line, make a contact sheet, look for problems (pauses between lines, laughing on grave lines, empty or
   too-still cards, lip sync on clip shots), then send me the mp4 + thumbnail.
5. Keep answers short and in plain words. Ask me before any second render.
