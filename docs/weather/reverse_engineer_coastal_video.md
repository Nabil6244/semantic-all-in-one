# Reverse engineering: "videoplayback (6).mp4" (SoCal coast / Storm Rachel, 19:26)

Measured locally (ffmpeg scene cuts + faster-whisper small, no paid services), 2026-10-14.

## Numbers
- 178 shots in 19.4 min. Median shot 4.2 s, mean 6.6 s. 52 shots under 2 s, none over 35 s.
- Map: **1 shot** (17:20, "storms spinning up off Mexico"). Everything else is footage + graphics.
- About a third of the shots are local TV news clips with the station logo left on
  (CBS LA, KTLA 5, FOX 5, NBC 4, ABC7, 10News, AP). News audio is muted: only the narrator speaks.
- The rest: drone/stock b-roll, plus graphics drawn over footage.

## How a clip is chosen
The script is written first, from news reports, with exact places, dates and numbers.
Each sentence is then cut against footage of **that place and that event**:
- "Beach Road in Dana Point… 10 homes red tagged" -> KTLA "Coastal erosion damaging homes", NBC "More homes red-tagged".
- "bluff collapse at Grandview, Leucadia" -> FOX 5 "Bluff collapse forces beach closure".
- "Newport… water filled garages" -> CBS LA flooded garage shots.
- "the 2019 collapse killed three women" -> AP archive clip with a big "2019".
Search key = place + event + month (what a viewer would type on YouTube). The newest local news upload wins.
Concept sentences (sand conveyor, dams, harbors, swell physics) get generic drone/stock b-roll instead.

## Graphics (every one is triggered by a kind of sentence)
| Sentence has… | Graphic | Examples |
|---|---|---|
| a place first named | place tag bottom-left, NAME + sub | ALAMITOS PENINSULA / Long Beach, DANA POINT / Beach Road, CARLSBAD, SAN CLEMENTE |
| one big number | huge number over the footage | $4-6.7M, 400K CY, 26 COTTAGES, $55M, 20 YRS, 1%, $15 MILLION |
| a year | huge year over the footage | 2019, 2026, 1950 |
| a probability | ring gauge | 90% chance of very strong El Niño |
| numbers that change over time | line chart | Carlsbad sand volume |
| two or three amounts to compare | bar chart | homes red vs yellow tagged, Newport property values, repair bills |
| a list | checklist card | 5 weeks 6 communities, the warnings, public infrastructure protected, public cost layer |
| the key line of a section | quote card, red highlight on 1-3 words | "…cannot replace what storms remove", "…moved down the row", "…mechanism fast enough…" |
| a new section | chapter title | THE CONVEYOR BROKEN, TWO TYPES OF LOSS, THE PRIVATIZATION OF COASTAL DEFENSE, WHO IS RESPONSIBLE?, RETREAT |
| a mechanism | simple diagram | high tides + tropical swells wave |
| a person | name tag | JULIE LAUGHTON |
| a named law/agency | corner tag + logo | CALIFORNIA COASTAL ACT, Coastal Commission |
| a value change | small chip on footage | +1.5 FT, +300%, $44.6B real estate in impact zone |
Also: polaroid frames, footage framed inside a dark panel, glitch transitions between parts.

## Story structure
1. 0:00 Cold open: "stand on the sand at…" one street, the price of the houses, what broke last weekend, hard numbers.
2. 1:14 Widen: same thing in 6 places in 5 weeks; the question; "and El Niño hasn't even started".
3. 1:59 Subscribe ask.
4. 2:08 Why: how the beaches are fed, how the system broke, this year's extras (swells, Kelvin wave, El Niño), the physics of swell.
5. 4:40 Framework: two ways homes are lost (undermining vs inundation).
6. 5:32 Place by place in order (Dana Point, Carlsbad, Encinitas, San Clemente).
7. 8:33 Mid-video like ask + "the last five days are where it gets expensive".
8. 8:41 Climax: the storm itself (Newport, Long Beach, Crystal Cove), then "the knowledge was there".
9. 10:48 The debate: walls vs beaches, the Coastal Act, who gets protected.
10. 12:43 The menu: armor, sand, or retreat, with the money; the warning case (Palos Verdes).
11. 15:56 Fairness: the response worked, nobody died.
12. 16:24 Who is responsible: five suspects, each answered.
13. 17:34 "Picture this from your window."
14. 17:56 Thesis: the baseline moved; infrastructure fails before mansions.
15. 18:54 Open questions + "tell me in the comments".
