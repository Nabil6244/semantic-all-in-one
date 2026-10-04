# pakMap CSV reference (for script authors)

One row per thing that appears on screen. Rows are grouped into **items** (`item_no`): a countdown number, a "part", or the cold open (item 0 or 1 with no title). The compiler (`python3 -m pakmap compile script.csv --words words.json --out spec.json`) turns the CSV and the narration's word timestamps into the render spec.

Open the CSV in a spreadsheet or a text editor. The first row is the header. **A cell that contains a comma must be wrapped in double quotes** (a number format like `"UP TO #,##0 MM"`, or `"-1.29,36.82"`); the compiler tells you the row if one isn't.

## When things appear
| Column | Meaning |
|---|---|
| `vo_anchor` | Words from the narration, as spoken. The layer appears on the first word. `Nairobi`, `forty seven million`, `the railway runs`. Add `|end` to land on the last word (`Nairobi|end`). Numbers match both ways (`47` = "forty seven", `250` = "two hundred and fifty", `2000` = "two thousand", `1984` = "nineteen eighty four"; "million" stays a separate word: `47 million`). A name that the transcription split in two ("Marsa Bit" for Marsabit) is still found. If a phrase can't be found, the error tells you the closest words it heard and when, so you can copy that spelling or use `t_start`. Small spelling slips and one extra spoken word are tolerated (and reported as warnings). |
| `offset_s` | Nudge in seconds (negative = earlier), for example `-0.2` for a chip that should land just before the number. |
| `t_start` | Exact time in seconds. Wins over `vo_anchor`. |
| `hold` / `t_end` | How long it stays (`hold`) or when it ends (`t_end`). If neither is given: stat 4.5 s, caption 4 s, marker/zone label 9 s, photo card 6 s, filmstrip 7 s, sticker 5 s, interlude 6 s, ghost shape 7 s, streak 5 s, clusters 8 s, dots 10 s; the title, fills, lines and overlays stay until the item ends. |
| `layer_action` | `in` (default) or `out`. An `out` row (with the `layer_id` of an earlier layer) ends that layer at its time. |
| none of the above | The row is spread evenly between the rows around it and marked **PROPORTIONAL** in the plan report, so you can see it was guessed. |

Rules the compiler applies for you:
- The title chip lands **0.14 s before** its words.
- Between items there is a fixed **0.5 s clear beat**: every layer of the previous item ends 0.5 s before the next item's first event. The last item runs to the end of the narration.
- At most **2 stat chips** and **5 text layers** (a title and subtitle count as 2) on screen at once; a sticker never appears with a photo card or filmstrip; one full-screen interlude at a time; the camera cannot move during an interlude (the map holds still). A breach is an error that names the layers involved.
- More than 5 s with nothing changing is a warning.

## Layer types (`layer_type`)
| Type | Needs | Notes |
|---|---|---|
| `hud_title` | `label_text`, optional `sub_text` | `PART 1` / `NUMBER 14` / anything. Optional: leave it out for a cold open. |
| `stat` | `value_to` | `value_from` (counts up from it), `value_format` (see below), `sub_text`, `anchor`: `br` (default) `bl` `tr` `tl` `bc`. Put a position in `params`: `{"pos": {"x": 1195, "y": 171}}`. |
| `caption` | `label_text` | `sub_text` is the tiny source line. `\n` makes a second line. `anchor`: `bc` (default) `bl` etc. |
| `marker` | `geo_ref`, `label_text` | Ring dot + dark label chip. `sub_text` = second chip. `color_role`: dark (default) neutral featured subject compare. `params`: `{"value": "4.4 MILLION"}`, `{"side": "l"}`. |
| `zone_label` | `geo_ref`, `label_text` | A county/zone name on its region (no dot). |
| `fill` | `geo_ref` (an area) | `color_role`: subject (dark red), featured, compare, orange, accent, water, green. |
| `line` | `line_kind`, `geo_ref` = `A;B;C` | `line_kind`: flow (arrowhead), river, rail, border_trace, divide, reference, connector. Or `params`: `{"coords": [[lon, lat], ...]}`. Draws head-first in 0.9 s. |
| `pip` | `asset_path` | A photo or clip card. `a.jpg|b.jpg` crossfades. `anchor`: tl tr ml mr bl br center. `label_text` = yellow label. `geo_ref` = leader line to that place. `params`: `{"shape": "square"}`. |
| `filmstrip` | 3-7 rows with the same `layer_id` | One row per card: `asset_path` + `label_text`. `anchor`: center, left or right. |
| `sticker` | `asset_path` (PNG with transparency), `geo_ref` | Stands on the place. `params`: `{"height_frac": 0.4}` or `{"at": {"x": 960, "y": 700}}`. Never together with a photo card. |
| `media_full` | `asset_path` | Photo or clip covering the screen with a 0.5 s dissolve; the HUD, stat chips and cards stay on top; the map holds still and returns where it left. Use one clip per row. (If a row does list several with `|`, they play in turn inside its time on screen, each dissolving into the next, so a render never fails on it; the CSV prompt does not ask for this.) |
| `dots` | `data_source`, `geo_ref` | `bundled:populated_places` (approximate) or `file:points.csv` (`lat,lon`). `params`: `{"per_million": 150}`. |
| `cluster` | `geo_ref` = `A;B;C` | A few dots popping in one after another. |
| `value_overlay` | `data_source`, `geo_ref` (a country) | Colour map from data: `bundled:rainfall_chirps` or your own `file:grid.tif` (.tif in lon/lat, .asc, or `lon,lat,value` .csv). |
| `ghost_shape` | `geo_ref` (a country), `params.to` | That country's outline at its true size, moved to `{"lon": .., "lat": ..}`. |
| `streak` | `geo_ref` | Decorative curved lines over a region. |
| `camera` | see below | Or put `camera_action` on any row. |
| `sound` | `sfx` or `ambience` | Places a sound or starts an ambience bed at the row's time. No picture. |

## Pictures from stock, Flow or YouTube
`asset_path` is normally a file. It can instead name a source and what to find, using the same source names as the other styles: `stock_image`, `stock_video`, `flow_image`, `flow_video`, `youtube_video`.

    stock_image:Nairobi skyline at dusk
    flow_video:aerial of Lake Victoria at sunrise
    stock_image:Nairobi skyline|stock_image:Kenyan highlands      (a|b is a cross-fade inside a photo card, `pip`; other layers take one picture or clip; files and sources can be mixed)

Works on `pip`, every `filmstrip` card and `media_full`. A `sticker` must be a transparent PNG file (no provider can supply one). **You do not edit these in the CSV after the AI has written them.** Loading the script puts every such picture in the app's **Visual Plan** tab as its own row (numbered in script order, one per use), with the source (Stock / Flow / YouTube) and what it is for. There you use the normal Retry, Change source (another stock result, Flow, YouTube, a local file), Skip and Local clip actions. Generate then fetches only what is missing through the app's existing providers, reuses everything saved (including your replacements, so no picture is fetched or generated twice), and renders from the files in the Visual Plan's folder. Flow generation costs credits, so the app asks before generating anything new with Flow. If a picture cannot be found the run stops before drawing, names the picture, and opens the Visual Plan tab; Skip leaves that layer out. Local-file pictures are your own choice and are not rows. **Check plan** lists which pictures will be fetched, generated with Flow, or are already saved, and puts the second each one appears in front of its Visual Plan row.

## Sound (optional)
Two optional columns, `sfx` and `ambience`, and one row type, `sound`. A marker, stat, line, card and sticker already get a quiet sound by themselves; use these to silence one or to add one. `sfx=none` on a row removes its sound; `sfx=bone_tap` replaces it; `sfx=catalog:whoosh_02` plays that exact library file; the same on a `camera` row controls that move. A `sound` row places a sound at its time without adding a picture. `ambience=desert_wind` on any row starts a quiet bed that runs until the next `ambience` row (`ambience=none` ends it). The ids, what each one plays, and the rules are in `sound-design.md`.

## Places (`geo_ref`)
`-1.29,36.82` (latitude first) · `KEN` (ISO country code) · `Kenya`, a state, a county, a named region · a city (`Nairobi`; `city:Moscow,RUS` to say which). A bare name is read as the city for markers, route stops, stickers and leaders, and as the area for fills, overlays and dots. A misspelling suggests the closest name. Several places in one cell: `Mombasa;Nairobi;Lodwar`.

## Camera
`camera_action`: `start` (where the video opens), `fly_to`, `push_in`, `pull_back`, `drift` (settings in `params`: `{"pct_per_s": 0.5, "heading_deg": 60}`). The target is `geo_ref` + `frame` (`globe`, `continental`, `country`, `region`, `local`), or `lat` + `lon` + `zoom`. `camera_dur` sets the length (fly_to 2.2 s, push_in 8 s, pull_back 2 s). `push_in` / `pull_back` with no target zoom one level in or out. Moves that would overlap are shortened (with a warning); moves too close together are an error.

## Number formats (`value_format`)
One number placeholder (`0`, `#,##0`, `0.0`) with any text around it: `#,##0 KM` -> 9,300 KM · `0.0M` -> 12.6M · `0/5` -> 1/5 · `0% OF THE LAND` · `< 0 MM` · `M0.0` -> M8.8 · `0.0 °C` (a negative value shows a real minus sign).

## Anything else
`params` is a JSON object whose entries go straight to the renderer, so a new renderer option is usable the day it exists. Unknown column names are ignored with a warning (with a "did you mean").

## Example
See `pakmap-engine/samples/kenya-story.csv` and `kenya-story.txt`, and `phase5/plan-report-sample.txt` for what the compiler prints.
