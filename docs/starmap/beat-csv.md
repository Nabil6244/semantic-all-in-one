# StarMap beat CSV

`composition_styles/starmap_beats_prompt.txt`: give it, filled in, and your script to an AI (for example Claude):

    python3 -m starmap prompt --script my_script.txt --out prompt.txt

The filled prompt lists every dataset in the library and what each lets the CSV name (events, sites, craft, paths, orbits,
as qualified ids such as `apollo11.lm`), with its status (historical, current, planned, projected, hypothetical). Its worked
example is the shipped sample (`starmap/samples/apollo11_beats.csv`), so the two never drift apart. The AI writes the
plan: one row per beat, layer, photo card and clip, timed by the narrator's own words. Nothing is re-cut or guessed:
a row the plan cannot hold is an error naming its row.

## Check plan

    python3 -m starmap check plan.csv --words words.json [--media media.json]

* **ERROR** (stops the render): a bad column or row, words the narrator never says, an unknown place / event / craft /
  path / orbit, beats that do not fit together, a footage clip under 2 s.
* **WARNING** (never blocks): the rhythm (footage outside 25-45 %, more than 25 s of map with no card or footage, nothing
  new on the map for 6 s), crowding (two stats in one corner, two cards in one place, two captions), short or long
  footage.
* **NOTE**: what the loader adjusted (a row spoken outside its beat joins the beat; a near-miss word match).
* **TO FIND**: pictures and clips named by description (`nasa_image:...`, `stock_video:...`) still to be found.
  `file:<name>` names a file in the media folder directly.

## Compile and render

    python3 -m starmap render plan.csv --words words.json --media media.json --media-dir DIR --channel "My Channel" --out video.mp4

`--words` is the voiceover's transcript (Whisper word list; `python3 -m starmap words script.txt --out words.json`
estimates one to try a script). `--media` maps each asset description to a file (`{"file": ..., "credit": ...}`).

## What the CSV says, and what the engine gets

| CSV | engine |
|---|---|
| beat `place` + `frame` (surface / close / body / system / inner / solar / galaxy / universe) + `type` (push_in, pull_out, orbit, hold) | a camera shot lit from the Sun's side; a glide to it when the view changes (on the map, never under footage); a beat with an orbit or path looks down on it |
| beat `date` (an event, event +/- HH:MM, T+HHH:MM:SS, or ISO) | universe clock keys. Dated map beats next to each other: time runs from one date to the next (the craft flies on screen). Footage between them: the earlier date runs in real time and the jump happens under the footage, out of sight |
| layers title, marker, zone, craft, path, orbit, stat, caption, distance, line, rings, pointer | title, marker, region, spacecraft, trajectory, orbit, stat_chip, caption, distance (+ a measuring link between its two things), link (light / measure), rings, pointer |
| automatic | planet and Moon orbits (faint, in their real planes); a galaxy seen from outside gets its landmarks (galaxy_guide: you are here, centre, arms); neighbour stars appear once the camera leaves the solar system; galaxies by the thousand in the universe frame |
| cards (map_footage) | photo_card at tr / ml / mr / bl: a picture, or a short clip that plays in the card while the map stays up |
| clips (footage) | footage beats, one after another |
| automatic | atmospheres, body labels, the mission clock (when there are dates), the channel name |

Layers leave with their beat unless `until` says `after_footage`, `end`, or a beat id; `hold` only makes them leave
sooner. Defaults: stat 4.5 s, caption 4 s, card 6 s.

## Datasets: found, never selected

Every `*.json` file in `starmap/packs/` is a dataset (`starmap/datasets.py` finds them; there is no list to keep). One CSV may
use any number of them: Apollo 11 in 1969, Voyager 1 today, Artemis III planned for 2027 and a hypothetical Moon base in 2050
can share one video. Adding a mission, spacecraft, telescope, rover, asteroid flyby or scenario is adding a file; the renderer
never changes for it (`test_starmap_universal.py` proves it with a dataset written during the test).

A dataset: `id`, `name`, optional `names` (how narration may say it), `kind`, `temporal` (`status`, `as_of`, `source`,
`date_precision`, `basis`, `continuity_days`), `met_zero`, `events` (a plain UTC date, or `{utc, status, net, precision}`),
`sites`, `craft`, `craft_aliases`, `paths`, `orbits`, `trajectories` (each with a `basis`, and for live spacecraft
`observed_until` and an optional `extrapolate: {"rule": "linear", "max_days": N}`), and `world` (extra bodies: an asteroid, a
comet, moons). The six original mission packs are valid datasets as they are: historical, illustrated geometry.

**Resolving** (`starmap/resolve.py`, deterministic, local only, no network and no AI): a beat's datasets come from its extra
(`{"mission": "artemis3"}`), qualified ids, names only one dataset has, then the previous beat, and only as a fallback the
narration. A name several datasets share (`launch`, `csm`, `spacecraft`, `voyager`) is an error unless the context settles it;
nothing is guessed. Qualified ids are `<dataset>.<name>` everywhere (`apollo11.landing-00:12:40`, `artemis3.T-01:00:00`).

**Time and certainty**: STATUS (historical, current, planned, projected, hypothetical) and BASIS (observed, modelled,
illustrated, illustrative) are separate. "now"/"today" is the project's reference date: the plan row's `date`, else the date
Check plan first ran, saved with the project (never the clock of the rendering machine). A position past a dataset's observed
data is drawn only under its extrapolation rule (labelled ESTIMATED), else Check plan reports it. A CSV may lower a beat's
certainty (`extra {"status": "hypothetical"}`), never raise it. On screen: PLANNED / PROJECTED / HYPOTHETICAL / ESTIMATED
badges, dashed coloured paths for uncertain things, a small FLIGHT PATH ILLUSTRATED line under illustrated history, and a
mission clock per mission (its own T-zero, T- before launch). Between missions or eras time JUMPS (under footage, or behind a
short time-jump card such as "1969 → 2026"); within one mission it runs on screen. `extra {"continuous": true|false}` overrides.

**Visual actions** (`starmap/actions.py`): the resolver says what happened; an action says how to SHOW it. A beat's `type`
may name one (liftoff, landing, orbit_insert, orbit, departure, transfer, flyby, approach, docking, undocking, separation,
impact, reentry, rover_drive, deep_space_departure ...), or `extra {"action": ...}`; left empty, a beat that shows a craft takes
it from its date's event (launch → liftoff, loi → orbit_insert, pdi → descent ...; a dataset event may declare `"action"`). The
action reads only the craft's trajectory data -- a surface track that starts at a site is the launch, one that ends at a site
the landing, an orbit arc its period, a transfer its two bodies -- and becomes camera intents for the existing camera (frame the
body or site, FOLLOW the craft on its trajectory, settle or pull back), a clock span (the ascent, the descent, the closest
approach) or, for journeys of months to decades, a narration-paced motion that carries the craft without spinning the planets,
plus an engine-burn glow for a manoeuvre. Check plan lists every beat's action; an action the data cannot support is an error
when asked for ("Launch visual incomplete: no spacecraft resolved") and a warning when inferred. Labels and basis are unchanged.

The **Moon Missions** datasets, each with a sample script, beat CSV and media map in `starmap/samples/` (pictures in
`starmap-engine/samples/media/`, credited in its `CREDITS.txt`):

| dataset | mission | what the trajectory shows |
|---|---|---|
| `apollo8` | Apollo 8 (Dec 1968) | launch, parking orbit, coast, 10 lunar orbits, coast home |
| `apollo11` | Apollo 11 (Jul 1969) | launch, parking orbit, coast, lunar orbit; Eagle's descent to Tranquility Base |
| `apollo13` | Apollo 13 (Apr 1970) | launch, coast, the loop behind the Moon, coast home (Fra Mauro as the planned site) |
| `artemis1` | Artemis I (Nov-Dec 2022) | launch, coast, outbound flyby, distant retrograde orbit, return flyby, coast home |
| `chandrayaan3` | Chandrayaan-3 (Jul-Aug 2023) | launch, widening Earth orbits, coast, shrinking lunar orbit; Vikram's descent to Shiv Shakti point |
| `change4` | Chang'e-4 (Dec 2018-Jan 2019) | launch, coast, lunar orbit; the descent into Von Karman crater on the far side |

Event times come from NASA (SP-4029 *Apollo by the Numbers*, the Artemis I timeline and mission blog), ISRO and published
mission records; a time a source gives only approximately is marked approximate in the dataset's `_about`. Every trajectory is
**illustrated** (built from those times, orbit heights and sites), not flight data; real state vectors can replace any of them
without a renderer change. `python3 -m starmap packs` lists the datasets. `test_fixtures/starmap_datasets/` holds about forty
small ARCHITECTURAL fixtures (Voyager 1/2, Juno, Parker, JWST, ISS, Perseverance, OSIRIS-REx, Artemis III, a Moon base ...):
approximate test data, not shipped.

## In the app

**Visual Director > StarMap** (the sixth style card):

1. Choose the voiceover on the Script page.
2. Type or paste your script, click **Copy the CSV prompt**, paste it into any AI, and save the CSV it writes. There is nothing
   to select: Check plan lists the missions, spacecraft and scenarios it found, with their status and dates.
3. **Load beat CSV…**: the CSV is kept in the project (`starmap/beats.csv`), its photo cards and clips appear in the Visual Plan
   table, and the plan is checked against the narration (**Check plan** runs it again; **Edit in spreadsheet** opens the file).
4. In the Visual Plan, Retry, Change source, Skip or use a Local clip for any picture, like every other style. `nasa_image:` rows
   show as stock_image rows marked "(NASA image library first)": Generate looks in NASA's image library first and keeps what it
   finds (with its credit); a row you change is yours. NASA's server sometimes drops connections: each request is retried a few
   times, and a row NASA still did not answer is listed as missing (Generate again retries it) rather than filled with a stock
   photo, so a modern stock picture never stands in for a historical one. A row NASA answered with no good match goes to the stock
   search as before. `nasa_video:` rows use the app's NASA video provider.
5. **Generate**: pictures and clips are found (nothing found twice; Flow asks before spending credits), space is drawn,
   the sound is designed (switch: Sound effects + ambience), the narration is added, and the video goes to `final/` with
   `… - credits.txt` (NASA image ids; each dataset with its status, geometry basis, source and as-of date; the catalogues).

The channel name is the same setting as pakMap's and Hybrid's. The style, the sound switch and the reference date are saved with the project.

| sound | when |
|---|---|
| space drone (ambience) | under the map; off under footage |
| soft whoosh / deep earth spin | the camera flies to a new view / across many orders of magnitude |
| soft transition | footage dissolving in |
| thud, pop, pluck, whoosh, ticks, click | a title, a marker, a region, a path or orbit drawing, a number counting, a photo card |

Effects never stack (0.6 s apart, the more important one wins); the mix ducks them under the narration (pakMap's mixer).
