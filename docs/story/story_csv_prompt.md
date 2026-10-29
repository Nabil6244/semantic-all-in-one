# Story shot-list CSV generator prompt

Paste the prompt into an LLM (Gemini etc.), fill in the three fields, save the reply as the visual-plan CSV. It produces the same columns as `shot_director.to_csv_rows`, so the result can be read with `shot_director.from_csv_rows` and the image step can generate the extra pictures with one consistent protagonist.

Notes:
* `asset_type` is `image` for rows that need a new picture and `reuse` for rows that stay on the previous picture of the same scene (so the scene's first row is always `image`).
* Keep `script_segment` word for word from the script; the app aligns rows to the voiceover.
* Rows for one scene share `scene_number`; `shot_id` is the scene number (3 digits) plus a letter.
* Old 4-column CSVs keep working; the app treats them as one shot per scene.

## Prompt

```
You are a film director and storyboard artist for a narrated YouTube story video
told with engraved sepia paper-collage pictures. Break the script below into a
SHOT LIST and output it as a CSV. The picture must change every 2 to 5 seconds,
following the narration phrase by phrase.

SCRIPT:
<paste the full script here>

LANGUAGE OF THE SCRIPT: <Hindi / English>
PROTAGONIST (one person for the whole video): <e.g. a night-shift warehouse worker>
VOICEOVER SPEED: about 2.5 spoken words per second (so a 2-5 second shot is 5 to 12 words)

OUTPUT FORMAT
Output ONLY the CSV, in one code block, nothing before or after. First line exactly:

scene_number,shot_id,script_segment,asset_type,prompt,character,motion_tier,camera,transition_in,link_to_next

Rules for the file:
- Comma separated, UTF-8. Wrap every field in double quotes; write a double quote inside a field as "".
- A SCENE is one idea of the script (one or two sentences). Number scenes 1, 2, 3 ...
  A SHOT is one phrase of a scene. shot_id = scene number as 3 digits + a letter:
  001a, 001b, 002a ...
- Split each scene at natural narration breaks: commas, sentence ends, and
  connectors (and / but / when / then / because; in Hindi: और / लेकिन / जब / फिर / क्योंकि).
  Every shot is 5 to 12 spoken words (2 to 5 seconds). Never 1-2 word shots, never over 14 words.
- script_segment: the exact words of the script for that shot, copied word for word.
  The shots of a scene, read in order, must reproduce the scene's sentences exactly.
- asset_type:
    image  = this shot needs its own picture (use for the first shot of every scene, and
             for any later shot that shows something NEW and concrete: a place, object, vehicle or person)
    reuse  = this shot stays on the previous picture of the same scene (abstract phrases, filler
             like "and that is the whole game"). At most 1 reuse in a row. Overall about
             60% of the rows should be image.
- prompt: an English image prompt, 35 to 70 words. Always start with the same style words
  and keep these exact words in every prompt:
    "engraved sepia paper-collage illustration, halftone shading, white cut-out outline, torn cream parchment background, muted sepia and terracotta palette"
  End every prompt with: "no text, no letters, no logos". Never ask for words, signs, numbers,
  captions or a watch/clock with readable digits in the picture.
  For asset_type "reuse" repeat the prompt of the picture it stays on.
- ONE SUBJECT per picture, stated with its position: "main subject on the left third" or
  "on the right third", with open space on the other side. Alternate left/right from shot to
  shot, but when two consecutive shots show the SAME object (box, dot, door, clock), keep
  that object on the SAME side and at a similar size so the cut between them is a match cut.
- Walking / travelling shots: frame them wide and low with "a clear empty floor strip across
  the bottom third", the figure small and side-on, so a character can walk along the floor.
- Vary scale: alternate wide establishing views, medium views and close-ups. Never two wide
  views in a row for the same place.
- character: true only when the shot shows the PROTAGONIST doing something (a person acting
  in the phrase). Otherwise false (places, objects, vehicles, charts, hands holding phones).
  Show at most one person per picture.
- CHARACTER SHEET (write it once, then paste it VERBATIM into the prompt of EVERY row where
  character is true, directly after the framing words, unchanged, never reworded, never
  shortened, no extra clothing details):
    "<CHARACTER SHEET: one sentence of 25-40 words describing the protagonist: faceless sepia
    paper-collage silhouette, build, hat, coat, boots, one carried item, white cut-out outline>"
  Example for a warehouse worker (use as a model, adapt to the protagonist above):
    "a faceless sepia paper-collage silhouette of a lean night-shift warehouse worker in a flat cap, a high-collar work coat, rolled sleeves and heavy boots, a handheld scanner on his belt, white cut-out outline"
  Then add only the ACTION of this shot after the sheet (scanning a parcel, walking out of a door).
- motion_tier: one of
    still_motion = default; the picture gets a slow camera move
    link         = this shot flows into the NEXT shot through a movement or matching object
                   (someone walks out of a door, a van turns a corner, a box becomes another box).
                   Use for about 15-20% of rows; link_to_next must be filled.
    ai_video     = a key moment with clear character action or a journey. At most 1 in 5 rows,
                   never two in a row. The picture must show the action's starting pose.
    graphic      = the narration gives a number, percentage, year or amount; the app overlays an
                   animated graphic. The prompt is a calm backdrop with no numbers.
- camera: push_in, pull_out, drift_l, drift_r, diag, or hold_alive. Never the same value twice in
  a row. Use push_in for close-ups and drama, pull_out for reveals and scale, drift for travel.
- transition_in: how this shot comes in. cut (default), match_cut (same object continues),
  torn_wipe (change of place), doorway_push (go through a door or opening), dissolve (time passes),
  whip (sudden jump). The first shot of the video is "cut". Never use the same value three times in a row.
- link_to_next: empty, or "kind: short note" where kind is one of match_cut, walk_through,
  push_through, torn_wipe, for example "walk_through: worker leaves the shelf aisle through the door".
  The next row's transition_in must agree (match_cut -> match_cut, torn_wipe -> torn_wipe,
  walk_through/push_through -> doorway_push).

SELF-CHECK before answering:
 1. Joining script_segment of all rows reproduces the script word for word, in order.
 2. Every row with character=true contains the character sheet sentence verbatim.
 3. No shot over 14 words or under 5 words (except a scene that is a single short sentence).
 4. No prompt asks for text, numbers or logos in the picture.
 5. Every link_to_next row is followed by a row whose transition_in matches.
```

## Example rows

```
scene_number,shot_id,script_segment,asset_type,prompt,character,motion_tier,camera,transition_in,link_to_next
1,001a,"आज रात Amazon के किसी ऑर्डर का ट्रैकिंग पेज खोलिए","image","Close-up of a hand holding a phone showing a tracking page with a single red dot on a dashed route, main subject on the left third, open space on the right, engraved sepia paper-collage illustration, halftone shading, white cut-out outline, torn cream parchment background, muted sepia and terracotta palette, no text, no letters, no logos.","false","still_motion","push_in","cut",""
1,001b,"और आपको वहाँ कोई दुकान दिखाई नहीं देगी।","image","Wide view of a small old storefront fading into a huge warehouse across a torn seam, main subject on the right third, open space on the left, engraved sepia paper-collage illustration, halftone shading, white cut-out outline, torn cream parchment background, muted sepia and terracotta palette, no text, no letters, no logos.","false","still_motion","pull_out","dissolve",""
2,002a,"वहाँ एक कर्मचारी रात के तीन बजे एक डिब्बे को स्कैन कर रहा होता है।","image","Medium view, a faceless sepia paper-collage silhouette of a lean night-shift warehouse worker in a flat cap, a high-collar work coat, rolled sleeves and heavy boots, a handheld scanner on his belt, white cut-out outline, scanning a parcel on a long shelf aisle, main subject on the left third, open space on the right, engraved sepia paper-collage illustration, halftone shading, torn cream parchment background, muted sepia and terracotta palette, no text, no letters, no logos.","true","ai_video","diag","torn_wipe",""
```
