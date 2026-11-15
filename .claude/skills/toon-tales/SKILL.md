---
name: toon-tales
description: Write a Toon Tales story (Walt and Pip, 2D puppets on Flow-painted places in Blender): a ~45-55 s "How X worked" script in the six-beat formula plus the shot plan JSON with places and retention hooks, then run the plan checker until it passes. Use when the user asks for a new Toon Tales story, episode, script or plan, or gives a topic for one.
---

# Toon Tales story writer

You write the story and the shot plan. No Gemini, no other model: the plan comes from you.
Every story stars the recurring cast (Walt and Pip) and is told by the fixed narrator.
The engine never changes per story; a story is only `toontales/stories/<id>/plan.json`.

## 1. Know what you can use

```bash
python3 -m toontales.plan.vocab
```

It prints the cast (roles and traits), set kits with their marks and prop spots, every action, pose,
eye and mouth, cameras, moves, props, overlays, sounds, beats, the timing rules and the topics
already used. Use only names it lists. Do not pick a topic it lists under USED TOPICS.

## 2. Get the facts right

The topic is real history or real science ("How X worked"). Check facts before writing (web search
when needed). The jokes come from staging and the characters, never from changing facts.
Every number, date and name in the script must be true.

## 3. Write the script (six beats, ~60 s, ~220-240 narrator words)

| Beat | Job | Typical shots |
|---|---|---|
| hook | the strangest true image first, no intro | 1-2 |
| concept | name the thing in one plain line | 2-3 |
| setup / deadline | who wants what, and the clock | 2-4 |
| obstacle | the smart check that should stop the trick | 3-5 |
| con / escalate | how the trick beats the check, it grows | 4-6 |
| twist / payoff | the ironic true fact that flips it, in the last ~5 s | 2-4 |

* One sentence = one shot. Narrator sentences 5-11 words; character lines 2-8 words.
* Walt is the schemer (sly, confident, gets-rich ideas). Pip is the eager sidekick who believes it,
  then asks "wait, how?". The narrator is dry and deadpan. Keep these the same in every story.
* Characters speak only a few short lines (2-5 per story); the narrator carries the facts.
* Concrete nouns the camera can show (sack, sign, cart, coins), not abstractions.
* **Hook question:** the hook asks the question the story answers, as a line ending in "?"
  ("...never dug for gold. So how did he get rich?").
* **Quick cuts:** in con/escalate write at least 2 very short lines (2-5 words) so cuts speed up.
* **Loop ending:** the last line runs back into the first (the payoff joke sets up the opening line again),
  and the last shot is in the first shot's place.

## 3b. Places (the story travels)

The visuals tell the story on their own. Write `"places"` in the plan: 5-9 places the story really moves
through, each a one-sentence picture description (period, setting, lighting, what is in it; no people up close,
no text). Optional ambient: `{"prompt": "...", "ambient": "dust|rain|embers|snow|leaves|none"}` (default dust).
A shot's `set` is a place name. Rules: at least 4 places, never more than 5 shots in a row in one place,
first and last shot in the same place. Paint them once (Flow server up: `cd flow-engine && node server.js`):

```bash
cd flow-engine && FLOW_ALLOW_REAL_CREDITS=1 node ../toontales/sets/paint_places.mjs ../toontales/stories/<id>/plan.json
```

Look at the pictures; repaint a bad one with `--redo <name>`.

## 4. Write the plan

Copy the shape of `toontales/stories/shovel_king/plan.json` (places + acted lines) and the
format notes in `toontales/plan/schema.py`. For each shot:

* `beat`, `speaker` (`narrator` or a cast id), `text` (the sentence), `set`, `camera`, `move`.
* `cast`: who is on screen, each on a different `mark`, with `acts` = `[{"do", "at", "params"?}]`
  (`at` = seconds into the shot). Give every shot a visible action, and a new action at least every 2 s.
  The speaker's mouth is automatic; put a speaking character in the shot (or `"offscreen": true`).
* **Show every narrator line, don't gesture it:** each narrator shot needs a prop, an overlay, a story action
  (walk/run/pick_up/throw/fall/jump...) or a cut to the place where it happens. Explain/nod/point alone fails.
* Show abstract claims with `props` (text props carry `text`, short and in CAPS) or an `overlay`. Props are
  drawn big; put a held prop with words in a medium/close/insert shot.
* Reactions are automatic from actions (tremble/plead -> sweat, angry -> vein, shock -> burst, money/celebrate
  -> sparkles, run -> speed lines, think/scratch_head -> "?", dizzy/bonk -> stars): use them on the beats.
* Plan top level: `"hook_title"` (2-7 words, the card over shot 1) and `"keywords"` (caption words to pop
  yellow; numbers and $ pop on their own).
* One shot 35-65% in gets `"freeze": "WAIT..."` (pattern break). The checker adds the held beat before the twist.
* Music follows the beats (upbeat -> sneaky con -> sad twist -> upbeat payoff); a shot may set `"mood"`.
* `sfx` for every physical action (pick, coins, bonk, thud, glass...).
* Change `camera` every shot; use `dissolve` only with `"time_jump": true`.
* First shot: the hook with a strong action or prop. Last shot: twist or payoff.

## 5. Check and repair

```bash
python3 -m toontales.plan.check toontales/stories/<id>/plan.json --fix
```

`--fix` repairs what it safely can: it splits long shots at natural breaks, merges tiny ones,
changes repeated cameras, adds gestures to still shots and moves people off shared marks.
Read every `fixed` line and make sure the result still makes sense (rewrite the sentence yourself
if a split reads badly). Fix every `error` yourself, re-run until it prints `OK`, and keep
`warn`s only when you have a reason. Then tell the user the title, topic, beat outline, length
and any warnings left.

## 6. After the user approves

When the story is rendered, add it to `toontales/stories/index.json`
(`{"stories": [{"id", "title", "topic", "date"}]}`) so the topic is never repeated.
