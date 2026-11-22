# Kids styles map

This is the single list of every kids style in the app. Use it to name the pages in the redesign.

Naming rule: **Channel → Style → Type.**
- A *channel* is the YouTube channel.
- A *style* is one engine with one app page.
- A *type* is the kind of video that style makes.

---

## 1. Toy Vehicles: 3D toy cars and trucks (Blender)
Code: `toycolors/`. App page: **Toy Vehicles** (Kids group).

| Type | What it is | Input | Length |
|---|---|---|---|
| **Colour Songs** | One sung verse per colour while a vehicle changes colour. Six ways to change: paint pour, surprise egg, garage, magic portal, new wheels, convoy. | A colour list | 40 s – 2 min per song |
| **Toy Stories** | Zip the car, Hooky the crane and friends on a toy playground: races, jumps, getting stuck, helping each other. | A story file (`toycolors/stories/*.json`) | 3 – 10 min |
| **Truck Convoy** *(new)* | Colour trucks carry little cars over speed bumps, potholes and train crossings. Cars fall off and Hooky lifts them back. | A convoy story file (e.g. `convoy_big_trip.json`) | about 3 min |
| **Songs + Stories episode** | A compilation: theme song opening, then story parts with song breaks. | Finished songs + a story | 10 – 15 min |

Not done: Truck Convoy and the Songs + Stories episode are not on the app page yet. They run from the command line.

---

## 2. Kids Stories: 2D cartoon show episodes
Code: `cartoon2d/`. App page: **Kids Stories** (imports a `.kidstory` file that Claude writes and packs).

| Channel | Cast | Type | Length |
|---|---|---|---|
| **Ms Molly** (Channel 1) | Ms Molly (host), Lily, Ollie, Bobo the Bear, plus Nutty the squirrel as a picture | **Learning journeys** | 18 – 20 min |
| **Baby Talk with Ms Molly** (Channel 2) | Ms Molly and Bobo only | **Baby speech** | about 15 min |
| **Ms Lina** (Channel 3) | Ms Lina, Nia, Poppy, Tobi, Rosie, Fizz (fox), Pip (frog), Dot (dino) | **Play adventures** | 15 – 22 min |

The same 2D engine also makes **Urdu and Punjabi versions** (e.g. `urdu01_ayan_shahad`, `punjabi01_noraiz_shahad`).
These use the Channel 1 cast with Urdu or Punjabi voices.

### Channel 1: Ms Molly, learning journeys (ages 1–5)
- **Rules:** `docs/cartoon2d/STORY_BIBLE.md`, checked by `cartoon2d/storycheck.py`.
- **Plans:** `CONTENT_PLAN.md` (Season 1, 24 episodes) and `EP01_PLAN.md`.
- **Brand:** `cartoon2d/brand/`, which has `CHANNEL.md` (description, keywords, settings), `profile_molly.png` and `banner.png`.
- **Cast and personalities:**
  - **Ms Molly:** warm host, asks a question then waits for the child to answer.
  - **Bobo the Bear:** gets things funny-wrong, says "Oopsie-Bobo!", does a giant sneeze.
  - **Lily (6):** clever, "I've got an idea!"
  - **Ollie (4):** cheeky, "Again! Again!"
  - **Nutty the squirrel:** hides things, says sorry at the end.
- **Episode shape (same every time):**
  1. Hook in the first 2 s.
  2. Goal said by 15 s.
  3. Theme chant ("Ms Molly and Bobo! Here we go!") with the title card.
  4. Hello song.
  5. A treasure-map journey through 8–10 places. Each place has a hidden "Can you find it?" object, the topic word 3+ times and one Bobo mistake.
  6. A freeze dance in the middle.
  7. The big success, then a twist.
  8. Calm wind-down.
  9. Teaser for the next episode, goodbye song, 20 s end screen.
- **Retention rules:**
  - Something new happens at least every 40 s.
  - "Your turn!" at least every 75 s.
  - A new place at least every 125 s.
- **Episodes:**
  - ep01 Colours
  - ep02 Counting
  - ep03 Shapes
  - ep04 Farm
  - ep05–06 ABC
  - ep07 Opposites
  - ep08 Rainbow
- **Also made from it:** `compile.py` (long compilations) and `shorts.py` (4–6 Shorts per episode).

### Channel 2: Baby Talk with Ms Molly, baby speech (ages 0–3)
- **Format:**
  - Ms Molly close to the camera (the "face" shot), speaking slowly and clearly.
  - One word at a time: show the picture, say it 3 times slowly, sign it, wait a long pause for the baby to try, then praise.
  - Simple public-domain action songs, peek-a-boo with Bobo, bubbles.
  - Calm studio sets (`cartoon2d/baby_sets.py`).
- **Episodes:**
  - baby01 First Words
  - baby02 Animal Sounds
  - baby03 Yummy Snacks
  - baby04 Toy Time
- **Brand:** shares Ms Molly's look. It has no banner or profile of its own yet.

### Channel 3: Ms Lina, play adventures (ages 2–6)
- **Plan:** `docs/cartoon2d/CHANNEL3_PLAN.md`. The cast sheet is `docs/cartoon2d/ch3_cast_options.jpg`.
- **Look:** a new cast and brand, made to look different from Ms Molly and from the reference channel.
  - Ms Lina has dark curly hair and a yellow top. No red hair, no overalls.
  - The animal friends are a fox, a frog and a dino.
- **Story shape:**
  1. Cold open with a goal, e.g. "Five lost ducklings are hiding in the playground!"
  2. Hello song.
  3. 6–8 play stops (slide, swing, ball pit, train), about 2–2.5 min each. Each stop has a title card, a ride or game, one learning beat with a pause, one goal item found with a counter on screen, and a funny sidekick moment.
  4. The goal completed, a dance, a calm recap, goodbye.
- **Story rules** (checked by storycheck):
  - Each episode has a hero who wants something, tries, gets stuck, has a setback and wins at the end.
  - A giver character appears at least every 2 stops.
  - The story is never just a list of stops.
- **Episodes:** ch3_ep01 Playground (14:34, with the ducklings).
- **Brand:** not made yet (logo, intro sting, title-card colours and end screen are planned).

---

## 3. Kids Learn: preschool lessons with a 3D host
Code: `cartoon3d-engine/`. App page: **Kids Learn**.

| Host | Type | Input |
|---|---|---|
| Maya (3D tutor) or the girl puppet (2D picture host) | **Lessons**: first words, counting, colours, opposites, animals and their sounds, shapes, letters, feelings. Sets: playroom, park, farm, beach, bedroom, space. | A lesson CSV, plus an optional voice-over |

---

## 4. In progress (no app page)
- **3D Kids Story (Blender cast)**: real 3D people. The lead is the CGTrader woman, with Hoorain as the kid. No Flow video. Still being built.

## Not kids (keep out of the Kids group)
- **Toon Tales**: Walt and Pip, cartoon history Shorts ("How X worked"). This is an adult Shorts style and belongs in **Stories**.
- **Roblox Cinema / Voxel Map**: block-toy look, but history videos.

---

## Suggested Kids group in the redesign

```
Kids
├── Toy Vehicles        → Colour Songs · Toy Stories · Truck Convoy · Songs + Stories
├── Cartoon Shows (2D)  → Ch1 Ms Molly · Ch2 Baby Talk · Ch3 Ms Lina adventures
├── Kids Learn (3D)     → Lessons (words, numbers, colours, animals, shapes, letters, feelings)
└── 3D Kids Story       → (coming)
```

On each page, pick the **type** first. The page then shows only the inputs that type needs.
