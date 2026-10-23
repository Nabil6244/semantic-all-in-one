# Phase 1, step 1: handwriting font check

Date: 2026-10-22. Nothing was added to the repository except this note. Font files and the comparison sheet are in the session scratchpad
(`.../scratchpad/fonts/`, local to this Mac, not portable). Nothing committed, staged or pushed.

## Licence (read from the downloaded packages, not from memory)

| Font | Source | Licence file | Result |
|---|---|---|---|
| Patrick Hand Regular | github.com/google/fonts, `ofl/patrickhand/` (214,772 bytes) | `OFL.txt`, copyright 2010-2012 Patrick Wagesreiter | SIL Open Font License 1.1 |
| Kalam Regular, Bold | github.com/google/fonts, `ofl/kalam/` (427,360 and 460,896 bytes) | `OFL.txt`, copyright 2014 Indian Type Foundry | SIL Open Font License 1.1 |

Both licence texts were downloaded and their headers read. Not yet done: a legal read of the reserved-font-name clause for redistribution inside
the installers; to ship, store each `OFL.txt` beside the font (pattern: `pakmap-engine/assets/fonts/README.txt`).

## Glyph coverage (rendered check, 8 test strings)

Present in all three files: accented Latin (í ü ï ã ñ ç é ö å), dashes, curly quotes, euro, percent, digits and thousands separators. Missing in all
three: the arrow `→` (arrows must be drawn as shapes, not typed).

## Visual comparison on board grey (#C0C0C0, 56 px, 8 phrases from the guide)

- **Patrick Hand**: upright, narrow, neat, lower-case friendly. Closest to the guide's "thin, casual, lower case" body voice. Digits are clear;
  the `7` has a crossbar that reads slightly odd in "1700".
- **Kalam Regular**: slanted, wider, looser. Reads as more informal, takes more width (phrases collided in a 470 px column).
- **Kalam Bold**: heavy and slanted; a candidate for the outlined display title, not for body text.

This is one reviewer (me) on one sheet; the guide asks for three reviewers and a side-by-side with the reference crop, which has not been done.
Proposal, not a decision: **Patrick Hand for body lettering, Kalam Bold with an outline for titles, a sans (Inter, already in `assets/fonts`) for chips.**
Final choice is yours.
