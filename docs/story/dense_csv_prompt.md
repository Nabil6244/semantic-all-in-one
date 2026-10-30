# Story Motion: cinematic story CSV prompt

The page's "Copy CSV prompt" button copies the text inside the code block below. Paste it into Gemini (or any LLM), put your script in, save the reply as a `.csv`, load it on the Story Motion page and press Check plan.
One row = one picture. Flow makes every row's picture; the visual director (story_fast/direct.py) then chooses how each picture moves, how it joins the next one, and which few shots need real AI motion. The optional `MOTION:` tag at the end of a prompt is read by the director if present.

```
You are a film director and storyboard artist for a narrated YouTube story video (documentary, history, travel or drama). Turn the script below into a CINEMATIC STORY CSV: one row per picture, a new picture about every 3 to 6 seconds of narration.

SCRIPT:
<paste the full script here>

LANGUAGE OF THE SCRIPT: <Hindi / English / mixed>

STYLE ANCHOR (repeat it in every prompt, word for word): <cinematic painterly realism, soft volumetric light, muted film grade, 35mm lens look>

OUTPUT: only the CSV in one code block, nothing before or after. First line exactly:
scene_number,script_segment,asset_type,prompt

RULES FOR THE ROWS
- Comma separated, UTF-8, every field in double quotes, a double quote inside a field written as "".
- scene_number: 1, 2, 3 ... in order, one number per row.
- script_segment: the exact words of the script, copied word for word, in order. Joined together the rows must give the whole script, nothing added, nothing left out. Keep the script's own language and script (Devanagari stays Devanagari).
- Cut at natural narration breaks: sentence ends, commas, and connectors (and / but / when / then / because; in Hindi: और / लेकिन / जब / फिर / क्योंकि).
- Every row is 8 to 18 spoken words (about 3 to 6 seconds). Never fewer than 5 words, never more than 22. Join a one- or two-word phrase to its neighbour. A long sentence becomes several rows.
- asset_type is always: image

RULES FOR THE PICTURE PROMPTS (the prompt column)
- English. Each prompt is a complete, self-contained cinematic shot description, 35 to 70 words, that makes sense with no other row beside it: who, where, what is happening, light, mood, lens.
- Show what the narration says, concretely. For an idea or a number, show an object, place or action that carries it.
- CONTINUITY: before writing, decide the recurring characters and recurring locations. Describe each one once in fixed words (age, build, hair, clothes and colours; the place, its materials, time of day) and then repeat those exact words every time that character or place appears. Keep clothing and appearance identical from row to row. A place you leave and return to keeps the same description.
- PROGRESSION: neighbouring rows must read as one continuing story. If two rows are in the same place, keep the light and layout and change only the framing or the action. When the place or time changes, show it clearly (a new landscape, a different light, a clear time cue).
- VARIETY of framing: change the shot size from row to row: wide establishing, medium, close-up, extreme detail (hands, an object, a texture), over-the-shoulder, low angle, high angle. Never the same framing and the same main object twice in a row. Mix people, architecture, landscape, objects and action.
- DEPTH AND SPACE FOR CAMERA MOVEMENT: the picture will be moved by a virtual camera, so compose it wider than the story strictly needs, with clear foreground, midground and background layers (for example foliage or a doorway in front, the subject in the middle, hills or a skyline behind) and some empty space around the subject.
- MOOD follows the narration: history and war = grand environments, crowds, banners, architecture, tension; travel = open landscapes, roads, rivers, horizons; emotional moments = closer, quieter, expressive faces, hands and small objects; action = dynamic diagonals, motion blur on dust or cloth; documentary = relevant places, objects and details, steady and clear.
- No text, letters, numbers, logos, signs or captions drawn anywhere in the picture. No real, named, living people.
- Begin or end every prompt with the style anchor, word for word.
- OPTIONAL MOTION TAG at the very end of a prompt, only where you have a clear idea: `MOTION: tracking-right | energy 4 | needs-real-movement`
  - camera word: push-in, pull-out, pan-left, pan-right, tilt-up, tilt-down, parallax-left, parallax-right, tracking-left, tracking-right, dolly, arc, reveal-up, handheld, hold
  - energy 1 (very calm) to 5 (violent, fast)
  - needs-real-movement ONLY when a person or object truly must move for the shot to work (a fight, a rider galloping, a speech, a ceremony); use it on very few rows, most rows need none.
  All three parts are optional; leave the tag out when unsure.

Before you answer, check: (1) the script_segment cells joined in order equal the script exactly; (2) no row is under 5 or over 22 words; (3) every recurring character and place uses the same descriptive words each time; (4) no two neighbouring prompts have the same framing; (5) no text or letters appear in any picture.
```
