# Kids Channel 3 — story-based play adventures (2D cartoon engine)

Decided 2026-11-18. Senior's feedback on Ch1 (Ms Molly): go story-based. Reference: YouTube @MsMiaLearnings.
Look: our 2D cartoon engine (cartoon2d/), NOT photoreal Flow video.

Channels: Ch1 = Ms Molly (learning). Ch2 = Ms Molly + Bhalu only. Ch3 = this, new cast, new brand.

## What the reference does (studied 2026-11-18)
- Photoreal host + furry puppet friend + toddler, in bright play places (playground, ball pit, obstacle course,
  train rides, water slides, beach, safari, ocean).
- "Story" = an adventure through ONE place: arrive, "Let's go!", 6-8 play stops, learning inside the play
  ("two yellow balls"), a title card per stop ("Obstacle Course Champions!"), goodbye.
- Length decides views: 15-22 min videos 150K-440K views; 8-9 min videos ~3K.
- Titles: "Learn to Play with <host> <emoji> <Place>! <things> | Toddler Learning".

We adopt the patterns, not the look or characters (see Cast).

## Episode shape (18-20 min)
1. Cold open (0:00-0:30): a small goal, shown not told — e.g. "Five lost ducklings are hiding in the playground!"
2. Arrive at the place, hello song.
3. 6-8 play stops, ~2-2.5 min each. Each stop:
   - title card (2-3 s) — reuse story_fx cards
   - the play itself (slide, ball pit, swing, train, splash pad, sand pit…)
   - one learning beat (colour, count, animal sound, first word, action word) with a pause for the child
   - one found goal item (duckling 1 of 5…) + cheer
   - a small funny moment from the sidekick
4. Goal complete, happy song/dance, calm recap of what we learned, goodbye.
Rules for the checker (storycheck.py): hook in first 10 s, a new stop every ~2.5 min, every stop has a
learning beat + a pause, the goal count is shown on screen, no stop longer than 3 min.

## Cast (new, must not look like Ms Mia OR Ms Molly)
- Host: young woman, NOT red hair, NOT overalls (e.g. dark curly hair, yellow top + teal skirt/joggers).
- Sidekick: a puppet-like animal friend, NOT blue/furry monster (e.g. a green frog or orange fox).
- Toddler: one small child the audience identifies with.
- 2026-11-18 owner: stories can have many characters. Proposed cast from the concept sheet (docs/cartoon2d/ch3_cast_options.jpg):
  Host B (Ms Lina, made older in one more Flow pass) leads; Nia (A) and Poppy (C) read as ~9-year-olds, so they become two
  big-kid friends; Tobi + Rosie are the toddlers; Fizz (fox), Pip (frog), Dot (dino) are the animal friends.
  Each episode uses 4-6 of them in frame (more = slower render), the rest rotate in by place.
- Made the same way as Ch1 cast: Flow pictures (no Flow video) -> cut-out rig in cartoon2d/cast/<name>/.

## Engine work (cartoon2d/)
Already there: journey/map episodes, places from Flow art, acts (point, cheer, count, clap, run, hands_up…),
hide/peek and ball games, title cards, story bible + storycheck, voices, mix, thumbnails, Shorts.
New:
1. Play moves: slide down, swing, ride (train/bus/car seat moving across), ball-pit sink + throw, splash,
   climb, jump in sand/puddle. Prop-ride: characters parented to a moving vehicle.
2. Play-place sets: Flow background per stop + foreground props (slide, swing, train) as separate layers
   so characters can be in front/behind.
3. Goal tracker: "ducklings found 3/5" on-screen counter + found-item pop.
4. Ch3 brand: logo, intro sting, title-card colours, end screen.
5. Episode generator template scenes/ch3_<place>.py (like ep06_abc2.py) with the stop pattern above.

## Steps
1. Cast concepts (3-4 options each) -> owner picks.
2. Rig the picked cast; test clip of each move.
3. New play moves + prop-ride; 30 s test clip.
4. Episode template + checker rules.
5. Pilot: "Playground adventure — find 5 lost ducklings" (~18 min). Owner + senior review.
6. Fix what they flag (fix the engine, not the one video), then episodes 2-5 (beach, farm, train ride, park).
