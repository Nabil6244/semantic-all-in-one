# Story Motion: dense CSV generator prompt

The page's "Copy CSV prompt" button copies the text inside the code block below. Paste it into Gemini (or any LLM), put your script in, save the reply as a `.csv`, load it on the Story Motion page and press Check plan.
One row = one picture = one narration phrase. Flow makes every row's picture, so a picture changes every 2-5 seconds.

```
You are a film director and storyboard artist for a narrated YouTube story video told with engraved sepia paper-collage pictures. Turn the script below into a DENSE PICTURE CSV: one row per narration phrase, one new picture per row.

SCRIPT:
<paste the full script here>

LANGUAGE OF THE SCRIPT: <Hindi / English / mixed>

OUTPUT: only the CSV in one code block, nothing before or after. First line exactly:
scene_number,script_segment,asset_type,prompt

RULES FOR THE ROWS
- Comma separated, UTF-8, every field in double quotes, a double quote inside a field written as "".
- scene_number: 1, 2, 3 ... in order, one number per row.
- script_segment: the exact words of the script, copied word for word, in order. Joined together the rows must give the whole script, nothing added, nothing left out.
- Cut at natural narration breaks: sentence ends, commas, and connectors (and / but / when / then / because; in Hindi: और / लेकिन / जब / फिर / क्योंकि).
- Every row is 6 to 14 spoken words (2.5 to 5.5 seconds). Never fewer than 5 words, never more than 16. Never a one- or two-word row: join it to the phrase next to it.
- asset_type is always: image
- A long pause or a dramatic list is still cut into rows of normal length by its sentences; do not leave a very long row.

RULES FOR THE PICTURE PROMPTS (the prompt column)
- English, one picture per row, 25 to 45 words, describing what is SEEN, concretely: objects, place, light, composition. No abstract words ("success", "future") without an object that shows them.
- The picture must show what that phrase says. If the phrase is a number or an idea, show an object that carries it (coins, a clock, a chart cut like a cliff, a scale).
- Give neighbouring rows different framings: alternate wide establishing, medium, close-up on one object, top-down, low angle, through a doorway or window, over-the-shoulder. Never two rows in a row with the same framing or the same main object.
- People are faceless silhouettes only, never a face, never a named real person. No text, letters, logos or numbers drawn inside any picture.
- End every prompt with exactly this style line:
  engraved sepia paper-collage illustration, halftone dot shading, white cut-out outline, torn cream parchment edges, muted sepia and terracotta palette, no text, no letters, no logos.
- Keep one motif that returns (for example a single glowing red dot, a wax seal, a clock) so the video feels like one story.

Before you answer, check: (1) the script_segment cells joined in order equal the script exactly; (2) no row is under 5 or over 16 words; (3) no two neighbouring prompts are alike.
```
