# Writing a Roblox Cinema HORROR story CSV

Paste this whole file into an AI chat, then add your script. The AI must answer with ONE CSV only (no commentary).

**The script is never changed.** Copy every word exactly as given, in order, into the `text` cells. Only cut it into beats at
sentence ends (1-3 whole sentences per beat, about 15-35 words). Do not shorten, reword, merge, fix, add or drop anything. Your job
is only the other columns. Save it as a .csv, set Story type to "Horror story" in the Roblox Cinema page and choose the CSV.

## What the film is
A quiet modern horror story told in a blocky, toy-like 3D world: one or two people on an empty street or in a room, the same hero
in every scene, night and rain, slow cameras. No soldiers, no crowds, no maps, no number callouts. Subtitles are added automatically.

## Columns (in this order, first line is the header)
`row,id,chapter,text,date,location,event,environment,time,weather,characters,actions,vehicles,props,effects,camera,subtitle,audio,transition,duration,extra`

Only `row` and `text` are needed. Leave a cell empty to let the engine choose. Double quotes around any cell with a comma; double a quote inside a cell.

### Row types
- `plan` (first row): `text` = film title, `extra` = `{"genre":"horror","time":"night"}`. `time` is the hour the story starts in
  (it is kept until a beat changes it). Optional `"hero":"Name"` gives the hero a name (same face every beat).
- `chapter`: `chapter` = a short title (for example "Rule number one"). Optional; one per rule or part.
- `beat`: one scene. `text` = the script's own words, unchanged.

### Beat columns
| column | what to put |
|---|---|
| id | b1, b2, ... |
| location | a real town or city ("Tulsa", "Kansas City") shows a place tag; or a room: Kitchen, Hallway, Bedroom, Living room, Bathroom |
| event | one of: quiet_moment (the hero alone), encounter (a stranger stops in front of the hero), pursuit_slow (the hero walks, something keeps pace behind), alone_inside (at home with what they found), phone_call, flashback (a memory from long ago), refuge (reaching someone who loves them). Empty = read from the words |
| environment | town, city, village, interior (others work but rarely suit) |
| time | dawn, day, sunset, dusk, night |
| weather | clear, overcast, rain, storm, fog |
| characters | `role[:Name][*count]` separated by `;`. Horror roles: hero, stranger, mother, parent, child, civilian. Keep it to 1-3 people. e.g. `hero; stranger` |
| actions | `state[@word]` separated by `;`: idle, walk, turn, look, point, talk, gesture, listen, crouch, react, sit, wave, fall |
| props | Indoors: phone, table, door, window, lamp, mirror, bed, television, coffee, plate, cabinet, hands. Or a close-up card: `card: wrapper with a name in blue ink` |
| effects | rain, rain_light, fog, haze, dust_motes |
| camera | one or two joined with `>`: push_in, static_close, over_shoulder, follow, ground_track, side_track, low_angle, dolly_in, dolly_out, establishing_interior, pullback_reveal |
| transition | cut, dissolve, dip |
| extra | JSON, quotes doubled: `{"seed":11}` (changes the look), `{"card":"..."}` (a close-up card, see below) |

## Close-up cards
The blocky world cannot show small details, so they appear as a card: the camera pushes into the thing in the hand, then the film
dissolves to the card for 3-4 seconds. Use a card for the moment the script looks closely at something, at most one per beat.

The engine already makes a card when the narration says: a name printed or written ("your name printed on the wrapper"), handwriting
or pencil, drawings, a license or ID card, a letter or envelope, or a time on a phone or clock ("the time on it will be 11:40").
Add a card yourself when the words alone do not say it, or to give the exact text:

- `extra` `{"card":"wrapper with a name in blue ink"}`, or the `props` cell `card: wrapper with a name in blue ink`.
- For more control, `extra` `{"card":{"what":"...","text":"...","at":"...","hold":4}}`:

| key | what to put |
|---|---|
| what | the close-up in plain words. It is also the picture's prompt, so describe what is seen |
| kind | optional: phone_screen, clock, name, handwriting, drawing, id_card, letter, note. Empty = read from `what` |
| text | the exact words written on it, for example a name. Without it, a name card uses the plan row's `hero` |
| time | the time on a phone or clock, for example `11:40` |
| style | ink, pencil or crayon |
| at | a word from this beat's `text`: the card starts when that word is spoken |
| hold | seconds on screen, 1.5 to 8 (default about 3.4) |
| asset | your own picture file (png, jpg, webp), next to the CSV or a full path |
| prompt | the picture's prompt, when it should differ from `what` |

`{"card":false}` turns off a card the narration would have made. Phone screens, clocks and names are drawn by the engine and need no
picture unless you give `asset` or `prompt`. Drawings, ID cards, letters, handwriting and notes are fetched at Generate and shown in the
Visuals tab, where you can change them. If one has no picture, the engine draws the card itself.

## What the engine builds from the words
A beat that names a porch, doorstep, front door, door mat, doorbell, front lawn or pumpkin is set at the front of a house with an open lit door (lit pumpkins when the words name them). A bus stop or a shop gets its own set. A child described in a white sheet wears it in every beat; a child with their own name does not. High cameras (`pullback_reveal`, and anything aerial) are replaced at night, because fog hides everything from up there. Events from a history CSV are ignored in a horror story: the beat is read from the words.

These work in a history CSV as well, when you name them: the porch, shop and bus stop sets, pumpkins, the child in a sheet, things in a named person's hand, and `{"card":...}` cards.

## Rules
1. Every beat has a horror event; the hero is in every scene (as `child` in a flashback).
2. Stay on one street or one room while the script stays there; change sets only when the script moves.
3. Night and rain carry over: set them once and change them only when the script does.
4. Give every beat a different `seed`; vary the camera from beat to beat.
5. No gore. Keep casts small. No `stat`, no maps.
6. A supplied script is never edited: the `text` cells joined in order must equal the script word for word.
7. Output the CSV only.

## Example
```
row,id,chapter,text,date,location,event,environment,time,weather,characters,actions,vehicles,props,effects,camera,subtitle,audio,transition,duration,extra
plan,,,"The Candy Wrapper",,,,,,,,,,,,,,,,,"{""genre"":""horror"",""time"":""night""}"
beat,b1,,"It's late, and you're standing alone in the rain. The street is empty.",,,quiet_moment,town,night,rain,hero,look,,,,side_track>push_in,,,dip,,"{""seed"":11}"
beat,b2,,"A stranger stops in front of you, smiling.",,,encounter,town,,,hero; stranger,,,,,over_shoulder,,,,,"{""seed"":12}"
beat,b3,"Rule number one","Your phone rings. Don't answer it.",,Kitchen,phone_call,interior,,,hero,listen,,phone; table,,static_close,,,dip,,"{""seed"":13}"
beat,b4,,"There is writing on the wrapper. It is your name.",,,quiet_moment,town,,,hero,,,,,,,,,,"{""seed"":14,""card"":{""what"":""candy wrapper with a name in blue ink"",""text"":""Sarah"",""at"":""writing""}}"
```
