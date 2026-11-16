# Ms Molly & Bobo: story bible

The rules every episode follows. `cartoon2d/storycheck.py` checks the measurable ones on the voiced timeline before a
render (render.py refuses a story that fails, like the place rules).

## 1. The cast

| Who | Personality | How they talk | Running jokes |
|---|---|---|---|
| **Ms Molly** (host) | warm, patient, playful; never cross | short clear sentences; asks, waits, praises ("Yes! A is for apple!") | "Ready, steady... go!" before every game |
| **Bobo** (bear) | big-hearted, curious, gets things funny-wrong | silly guesses, big feelings, says sorry | "Oopsie-Bobo!" after every mistake; the giant sneeze; his tummy rumbles near food |
| **Lily** (6) | clever, kind, helps Bobo | complete answers, encourages | "I've got an idea!" |
| **Ollie** (4) | cheeky, bouncy, funny (never mean) | short excited lines, sound effects | "Again! Again!"; tumbles and pops back up |
| **Nutty** (squirrel, picture prop) | cheeky trickster who hides things, always sorry at the end | squeaks (Molly reads his notes) | pops up from a corner; giggles "hee hee!" |

Kindness rules: the kids correct Bobo gently, everybody says sorry when needed, Nutty is forgiven and shares at the end.

## 2. The show's fixed parts (same every episode: kids wait for them)

1. **Hook first, no "Coming up!" preview**: the very first line (by 2 s) grabs attention with a surprise, a big move,
   a sound or a picture, then the **cold open** problem in the first 5 seconds. (The teaser is off; `"hook": "auto"` opts in.)
2. **The goal** said by 15 s (`goal: true` on that line).
3. **Theme chant**: "Ms Molly and Bobo! Here we go! Learning and playing, high and low!" with the title card.
4. **Hello song** and the learning goal ("Today we're learning...").
5. **The journey**: 8-10 places, a new one at least every ~2 minutes, each opened with the **treasure map** (`map: k`).
6. In every place: a hidden object for the child (**Can you find it?** `find` ... `found`), the topic word 3+ times
   with picture and card, one action (move, game, song bit), one Bobo mistake.
7. A **freeze dance** or song in the middle, a **game** at least every ~3 minutes.
8. **The big success** (confetti) then a **twist** (the surprise).
9. **Calm wind-down**: a breath, a cuddle, a quiet recap (`calm: true`).
10. **Teaser** for the next episode (`teaser: true`) then the **goodbye song** and **end screen** (20 s, room on the right
    for YouTube's end-screen boxes).

## 3. Retention rules (checked)

| Rule | Limit |
|---|---|
| Something new happens | at least every 40 s (place, game, song, your turn, find, map, picture, title, effect, big move) |
| Talking with no action / picture / card | at most 20 s in a row |
| "Your turn!" for the child | at least every 75 s |
| Open questions | each journey place opens with the map, each hidden object is found before leaving the place |
| A new place | at least every 125 s; each place at most twice; backgrounds new to the show |
| Learning words | every word in the script's `learn` list said 3+ times |
| Calm part | in the last 3 minutes |
| Teaser + end screen | teaser in the last 90 s; at least 20 s after the last goodbye line starts |

## 4. For parents

- One learning goal, said at the start and recapped at the end; the description lists what the child learns.
- High-energy parts always come back down to calm ones; the episode ends calm.
- No scary moments, no brands, no mean jokes; sharing, helping and sorry in every story.
- A "Parent tip" line in every description (a game to play after watching).

## 5. Formats from every episode

- `compile.py`: 3+ episodes joined into one long video (chapters, thumbnail, UPLOAD.md).
- `shorts.py`: 4-6 vertical Shorts cut from songs, games and Bobo moments, each pointing to the full episode.
