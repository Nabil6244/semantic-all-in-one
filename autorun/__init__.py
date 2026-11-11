"""Make a video with no clicks: a job file (style, voiceover, script, optional CSV) that the app runs through its own buttons.

    python3 make_video.py run --style explainer --voice vo.mp3 --script script.txt --csv scenes.csv --out film.mp4

The app is started with SYT_AUTORUN=<job.json> (app.main), opens as usual, and autorun.driver presses its own buttons in order (the same
code paths as a person: Visuals, Generate, Render, Export). Progress goes to <job>.status.json and <job>.log; the app closes when done."""
