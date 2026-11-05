# Writing a Roblox Cinema story CSV

Paste this whole file into an AI chat, then add your topic (for example: "Topic: the 1971 India-Pakistan war, about 30 seconds").
The AI must answer with ONE CSV only (no commentary).

**If the topic message includes a finished script or voice-over text: do NOT change it.** Copy every word of the script exactly as given, in order, into the `text` cells. Only cut it into beats at sentence ends (1-3 whole sentences per beat, about 15-35 words). Do not shorten, reword, merge, summarise, fix, add or drop anything, and do not add sentences of your own. Your job is only the other columns. If no script is given, write the narration yourself. Save it as a .csv and choose it in the Roblox Cinema page.

## What the film is
A history film told in a blocky, toy-like 3D world: small characters, vehicles, maps and effects, with date tiles, place tags,
subtitles and music added automatically. You write the narration and say what is happening; the engine builds the scenes.

## Columns (in this order, first line is the header)
`row,id,chapter,text,date,location,event,environment,time,weather,characters,actions,vehicles,props,effects,camera,subtitle,audio,transition,duration,extra`

Only `row` and `text` are needed. Leave a cell empty to let the engine choose. Use double quotes around any cell with a comma, and double a quote inside a cell.

### Row types
- `plan` (first row): `text` = film title, `date` = year of the story, `extra` = `{"side_a":"india","side_b":"pakistan","music":"stormfront"}`. For a story before 1500 AD add `"era":"ancient"` (up to 499 AD) or `"era":"medieval"`; BC years are written like "753 BC".
  Sides: us, uk, allied, germany, soviet, japan, france, north_vietnam, south_vietnam, india, pakistan, roman, carthage (omit for civilians-only stories).
- `chapter`: `text` empty, `chapter` = the chapter title, `date` = a short banner such as "JUNE 1944". Optional; use one per 1-3 minutes.
- `beat`: one scene. `text` = the narration. With a supplied script it is that script's own words, unchanged (whole sentences only). When you have to write the narration yourself, use 1-2 plain sentences (about 8-25 words) and aim for 2.5 spoken words per second.

### Beat columns
| column | what to put |
|---|---|
| id | b1, b2, ... |
| date | "3 December 1971" (shows as a date tile) |
| location | a real place name ("Lahore", "Omaha Beach") or "lon,lat" |
| event | one of: establishing, troop_deployment, defensive_position, political_meeting, natural_disaster, airborne_drop, city_occupation, naval_operation, landing_operation, battle, ambush, airstrike, military_invasion, convoy_movement, retreat, surrender, peace_agreement, protest, revolution, assassination, evacuation, civilian_life, liberation, industrial_production, infrastructure_construction, historical_discovery, aftermath, consequence, map |
| environment | one of: city, town, village, farmland, forest, jungle, hills, mountains, valley, desert, beach, river, island, airfield, military_base, factory, port, monument, battlefield, interior, sea, map |
| time | dawn, day, sunset, dusk, night |
| weather | clear, overcast, rain, storm, fog, snow |
| characters | `role[:Name][*count]` separated by `;` e.g. `commander:Eisenhower; officer*3; soldier*12`. Roles: soldier, officer, commander, leader, politician, civilian, farmer, worker, police, pilot, sailor, medic, journalist, crowd, paratrooper, tank_crew, child, forecaster, guard |
| actions | `state[@word]` separated by `;`, the word is a keyword from the narration that times the action. States: idle, walk, run, march, turn, look, point, talk, gesture, listen, salute, crouch, cover, carry, enter_vehicle, exit_vehicle, climb, fall, react, aim, fire, wade, parachute, cheer, wave, sit, ride, hands_up, crawl, lie |
| vehicles | `kind[*count][>motion]` separated by `;` e.g. `tank*3>advance; jet*2>flyover`. Kinds: tank, tank_ww1, halftrack, apc, jeep, humvee, truck, truck_old, car_old, car, motorbike, bicycle, artillery, radar, cart, train, landing_craft, patrol_boat, sampan, ship, battleship, steam_ship, sailing_ship, galley, submarine, transport_plane, bomber, fighter_prop, biplane, jet, helicopter, drone, horse. Motions: advance, convoy, flyover, circle, land, takeoff, park, drift, approach_beach, patrol, cross |
| text (mirrors) | in a room with a mirror the reflection acts on what the narration says: smiles, moves first / half a second early, blinks, turned its head, face pressed against the glass, stutters / goes still, has no face, the mirror was empty, the reflection's hands |
| props | what is in the shot, separated by `;`. Indoors these build the set and aim the camera: mirror, sink, towel, bathtub, toilet, door, light switch, window, bed, lamp, television, phone, table, coffee, plate, cabinet, hands, ring. Set `location` to Bathroom, Kitchen, Hallway, Bedroom or Living room to pick the room |
| effects | separated by `;`: smoke, smoke_light, fire, fire_small, dust, explosions, splashes, tracers_in, flak, rain, rain_light, snow, clouds, clouds_storm, haze, fog, confetti, chimney_smoke, birds, dust_motes, contrails, naval_guns, waves_high, debris, muzzle |
| camera | one behaviour, or two joined with `>` (e.g. `low_angle>ground_track`): establishing_wide, aerial_geo, low_angle, follow, over_shoulder, ground_track, vehicle_follow, flyover, orbit, dolly_in, dolly_out, crane_up, descend, rise, side_track, push_in, pullback_reveal, establishing_interior, map_overview, map_dive, static_close |
| subtitle | only to override the caption text |
| audio | optional sound cues, `;` separated: gunfire, gunfire_far, explosion, flak, ship_guns, planes_pass, tanks, marching, thunder, clock, bells, surf, wind, whoosh |
| transition | cut, dissolve, dip, clouds, map_dive, match |
| duration | seconds (only used when there is no voice-over) |
| extra | JSON, quotes doubled. Keys: `{"seed":11}` (any number, changes the look), `{"stat":"13 days | the length of the war"}` (big number callout), `{"label":"text"}`, and for map scenes `{"map":{"pins":["New Delhi","Lahore","Dhaka"],"dive":"Dhaka","margin":1.5}}` |

## Rules
1. Start with a map beat (`event` = map, `environment` = map, pins listed in `extra`) to place the story, then alternate ground, air and sea scenes.
2. Give every beat a different `seed`, and vary environment, time and camera from beat to beat.
3. Keep facts accurate and neutral. Do not invent dates, casualty numbers or quotes. Maps are present-day borders and approximate.
4. No gore, no flags or insignia. Name sides with the `plan` row's side_a / side_b.
5. Use `stat` for one or two real numbers in the whole film, not on every beat.
6. A supplied script is never edited: the `text` cells joined in order must equal the script word for word.
7. Output the CSV only.

## Example
```
row,id,chapter,text,date,location,event,environment,time,weather,characters,actions,vehicles,props,effects,camera,subtitle,audio,transition,duration,extra
plan,,,"The 1971 India-Pakistan War",1971,,,,,,,,,,,,,,,,"{""side_a"":""india"",""side_b"":""pakistan"",""music"":""stormfront""}"
beat,b1,,"In 1971, a crisis in East Pakistan pushed India and Pakistan toward their third war.",1971,Eastern front,map,map,,,,,,,,,,,,,"{""map"":{""pins"":[""New Delhi"",""Lahore"",""Dhaka""],""dive"":""Dhaka"",""margin"":1.5},""seed"":31}"
beat,b2,,"On the third of December, Pakistani jets struck Indian airfields, and war began.",3 December 1971,Amritsar,airstrike,airfield,dusk,clear,,,jet*3>flyover,,,vehicle_follow>rise,,,,,"{""seed"":32}"
```
