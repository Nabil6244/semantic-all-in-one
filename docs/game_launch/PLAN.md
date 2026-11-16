# Game Launch style ("Game vs Real") - integration plan

Prototype (works, not in the app yet): `gta6_launch/`
- `build_test20.py` - shared look: Vice-sunset colours, pills, headline/split cards, glitch cut, synthwave bed made in code.
- `build_full.py` - full video from a hard-coded LINES list: shot kinds g/r/s/h/c/m (game, real, split, headline, chapter, Florida map);
  cut-safe trailer clipping (CUTS lists, auto slow-mo + hold so no shot crosses a trailer cut); edge-tts voice with retries
  (Edge refuses "GTA 6." at a sentence end - write "GTA six"); music ducked under voice; whoosh/impact on chapters and maps.
- `make_shorts.py` - 9:16 Shorts cut from the full video by narration line (blurred bg + title).
- Outputs: `gta6_launch/out/` (full 3:10, 4 Shorts, thumbnail).

## To integrate (new style page, like ui/aviation_section.py)
1. `game_launch/` package: move shot renderer, map, music, Shorts and thumbnail code out of the scripts; no GTA-specific constants.
2. Input = scenes CSV: `line, kind, game_src, game_in, real_query|real_src, real_in, label_left, label_right, head, sub`.
   CSV run = zero Gemini calls. Region map = generic place pins (lon/lat columns) instead of the hand-traced Florida only.
3. Game footage: user drops official trailer files (or a URL list) on the page; cut detection (ffmpeg scene>0.28) builds CUTS automatically.
4. Real footage: fetched through AssetManager into the Visuals tab (owner `game_launch`), so it goes Visuals + Export like every style.
5. Voice: the Voiceover tab's file, or edge-tts per line (with the retry/reword rule).
6. Page: Generate scenes -> Render; extras checkboxes: Shorts (N, by line ranges) and thumbnail (left/right frame picks + 2 text lines).
   Nothing starts until Generate.
7. Tests: timeline split, cut-safe clipping math, CSV parse; run only those tests.
