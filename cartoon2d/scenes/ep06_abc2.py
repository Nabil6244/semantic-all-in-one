"""Episode 6 - "ABC Adventure 2: K to T with Ms Molly & Bobo" (about 19 min). Writes ep06_abc2.json next to this file.

Follows ep05's teaser: block K was in the treasure box; Nutty the squirrel hid nine more blocks (L to T) across a new
map. Same journey pattern as ep05: one letter per place, find the block, sound, word, move/game, Bobo's mistake.

First journey episode (docs/cartoon2d/STORY_BIBLE.md). Cold open: Bobo's ten alphabet blocks (A to J) are ready for the ABC
party when Nutty the cheeky squirrel and a big gust of wind blow them out of the window. The treasure map shows where each
block landed; the friends travel through ten places, one letter each: find the hidden block (the child helps), learn the
letter, its sound and a word, do the letter's move or game, and Bobo gets one funny thing wrong. Back in the classroom the
blocks are all home, Nutty says sorry, a twist (one more block: K!) sets up the next episode, a calm recap, goodbye.
"""
import json
from pathlib import Path

ASK = 2.1
L = []


def say(who, text, **k):
    L.append({"who": who, "text": text, **k})


def ask(who, text, **k):
    k.setdefault("gap_after", ASK)
    say(who, text, **k)


M, LI, O, B = "molly", "lily", "ollie", "bobo"
KIDS = [LI, O]
ALL = [M, LI, O, B]
ALSO = lambda a: {LI: a, O: a, B: a}  # noqa: E731
STOPS = ["K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"]


def letter(k, place, arrive, where, spot, sound, word, pic, wrong, finder):
    """The common part of every letter place: map, arrive, find the block, the letter, its sound, its word, Bobo's mistake."""
    Lt = STOPS[k]
    ask(M, f"Where did block {Lt} go? Let's look at our map!", act="point", cam="host", map=k, gap_after=1.6)
    say(ALL, arrive, act="run", also=ALSO("run"), cam="group", place=place, chapter=f"{Lt} is for {word}", sfx="sparkle",
        gap_after=0.5)
    say(M, f"Nutty hid block {Lt} somewhere {where}. Can you find it?", act="think", cam="group", your_turn=True,
        find={"pic": f"block_{Lt.lower()}", "x": spot[0], "y": spot[1], "size": 0.085}, gap_after=2.6)
    say(finder, f"There it is! I found it!", act="point", cam="group", found=f"block_{Lt.lower()}", sfx="ding_3")
    say(M, f"Block {Lt}! Well done! This is the letter {Lt}.", act="cheer", cam="host", card=f"{Lt} {Lt.lower()}", sfx="pop")
    ask(M, f"{Lt} says {sound}, {sound}, {sound}. Can you say {sound}?", act="point", cam="host", your_turn=True, gap_after=0.6)
    say(ALL, f"{sound}, {sound}, {sound}!", act="clap", also=ALSO("clap"), cam="group", card=f"{Lt}")
    say(M, f"{Lt} is for {word}! {word.capitalize()}!", act="open", cam="host", pic=pic, card=f"{Lt} is for {word}")
    say(B, f"{Lt} is for... {wrong}!", act="silly", cam="cu:bobo", face="happy")
    say(KIDS, f"Nooo, Bobo! {wrong.capitalize()} doesn't start with {Lt}!", act="laugh", cam="kids")
    say(B, f"Oopsie-Bobo! {Lt} is for {word}! {sound}, {sound}, {word}!", act="tumble", cam="cu:bobo", sfx="pop")


# 1 ---------------------------------------------------------------- cold open: the hook + the goal
say(B, "Look! Block K came back! K is for kite!", act="hands_up", cam="cu:bobo", place="treehouse",
    chapter="Bobo's new blocks", pic="block_k", sfx="pop")
say(LI, "Oh no! Nutty took the rest of the blocks, L to T!", act="hands_up", also={B: "tumble", O: "wobble"}, cam="group",
    pic="squirrel", fx="leaves", face="surprised", sfx="whoosh")
say(M, "Nutty left us a brand new map! Let's go and find them all!", act="open", cam="host", goal=True)
say(ALL, "ABC adventure, part two!", act="yay", also=ALSO("yay"), cam="group", title="ABC Adventure 2\nK to T!",
    fx="confetti", sfx="success", gap_after=1.6)

# 2 ---------------------------------------------------------------- theme chant + hello
say(M, "Clap along with our song!", act="clap", also=ALSO("clap"), cam="group", your_turn=True, chapter="Hello song",
    gap_after=0.4)
say(ALL, "Ms Molly and Bobo! Here we go! Learning and playing, high and low!", chant=True, act="dance", also=ALSO("dance"),
    cam="group")
say(ALL, "Ms Molly and Bobo! Here we go! Learning and playing, high and low!", chant=True, act="dance", also=ALSO("dance"),
    cam="group", gap_after=0.6)
say(M, "Hi friends! I'm Miss Molly! Today we're learning letters K to T!", act="wave", cam="host", card="K L M")
say(LI, "Hi! I'm Lily! L is for Lily!", act="wave", cam="kids")
say(O, "And I'm Ollie! O is for Ollie!", act="cheer", cam="kids")
say(B, "And I'm Bobo! Please help me find my blocks again!", act="wave", cam="cu:bobo", face="happy")
ask(M, "Will you help Bobo? Shout yes!", act="point", cam="host", your_turn=True, gap_after=0.6)
say(KIDS, "Yes!", act="jump", also={B: "jump"}, cam="group", sfx="sparkle")
say(M, "First, K is for kite! Let's fly it in the windy meadow!", act="open", cam="host", pic="kite", sfx="chime")
say(O, "Let's go! Ready, steady...", act="squat", cam="kids")

# 3 ---------------------------------------------------------------- K: the windy meadow (no block to find: K came home)
say(ALL, "Go! Whoosh! The windy meadow!", act="run", also=ALSO("run"), cam="group", place="meadow", chapter="K is for kite",
    sfx="whoosh", gap_after=0.5)
say(M, "This is the letter K. K says k, k, k. Can you say k?", act="point", cam="host", card="K k", your_turn=True,
    gap_after=1.6)
say(ALL, "K, k, kite!", act="clap", also=ALSO("clap"), cam="group", card="K", pic="kite")
say(B, "K is for... cookie!", act="silly", cam="cu:bobo", face="happy")
say(KIDS, "Nooo, Bobo! Cookie starts with C!", act="laugh", cam="kids")
say(B, "Oopsie-Bobo! K is for kite! K, k, kite!", act="tumble", cam="cu:bobo", sfx="pop")
say(M, "Let's fly like kites! Arms out wide, and swoop, swoop, swoop!", act="hands_up", also=ALSO("hands_up"), cam="group",
    your_turn=True, gap_after=0.5, fx="leaves")
say(ALL, "Swoop! Swoop! Up in the sky! K, k, kite!", act="spin", also=ALSO("spin"), cam="group")

# 4 ---------------------------------------------------------------- L: the lemon grove
letter(1, "lemons", "Here we are in the lemon grove!", "under the lemon trees", (0.09, 0.84), "l", "lemon", "lemon", "apple", LI)
say(M, "Lemons are sour! Make a sour face! Ooooh!", act="giggle", also=ALSO("giggle"), cam="group", your_turn=True,
    gap_after=0.6)
say(ALL, "L, l, lemon! Sour, sour, sour!", act="wobble", also=ALSO("wobble"), cam="group", pic="lemon")
say(LI, "And L is for lamb! Baa!", act="point", cam="kids", pic="lamb")

# 5 ---------------------------------------------------------------- M: the treetops
letter(2, "treetops", "Wow! Up in the treetops!", "on the rope bridge", (0.92, 0.84), "m", "monkey", "monkey", "banana", O)
say(M, "Let's swing like monkeys! Ooh ooh, aah aah!", act="dance", also=ALSO("dance"), cam="group", your_turn=True,
    gap_after=0.4)
say(ALL, "M, m, monkey! Ooh ooh, aah aah!", chant=True, act="jump", also=ALSO("jump"), cam="group")
say(B, "I'm a monkey! Ah... ah... ah-CHOO!", act="sneeze", cam="cu:bobo", sfx="pop")
say(KIDS, "Hee hee! Bless you, Bobo!", act="laugh", cam="kids")

# 6 ---------------------------------------------------------------- N: the woodland nest
letter(3, "woods", "Shh! A quiet wood!", "by the big oak tree", (0.08, 0.85), "n", "nest", "egg", "duck", LI)
say(M, "A nest is a home for baby birds. Shh, they are sleeping. Tiptoe!", act="walk", also=ALSO("walk"), cam="group",
    calm=True, your_turn=True, gap_after=0.8)
say(ALL, "N, n, nest. Tiptoe, tiptoe.", act="walk", also=ALSO("walk"), cam="group", calm=True)
say(O, "Tweet tweet! Can you whisper tweet?", act="point", cam="cu:ollie", your_turn=True, gap_after=1.2, pic="bird")

# 7 ---------------------------------------------------------------- O: the rock pools
letter(4, "rockpools", "Splish! The rock pools!", "by the little pools", (0.93, 0.85), "o", "octopus", "octopus", "fish", O)
say(M, "An octopus has eight arms! Let's wiggle our arms like an octopus!", act="wave", also=ALSO("wave"), cam="group",
    your_turn=True, gap_after=0.5)
say(ALL, "O, o, octopus! Wiggle, wiggle, wiggle!", act="dance", also=ALSO("dance"), cam="group", fx="bubbles")
say(B, "And O is for... Ollie!", act="point", cam="cu:bobo", face="happy")
say(O, "Yes! O is for Ollie! That's me!", act="yay", cam="kids")

# 8 ---------------------------------------------------------------- P: the pumpkin patch + freeze dance
letter(5, "pumpkins", "Look! A pumpkin patch!", "behind the pumpkins", (0.08, 0.84), "p", "pig", "pig", "cow", LI)
say(B, "P is for pumpkin too! A big, round, orange pumpkin!", act="hands_up", cam="cu:bobo", face="happy")
say(M, "Time for the letter freeze dance! Dance, and freeze when I say a letter!", act="dance", cam="host",
    chapter="Letter freeze dance", fx="stars")
for Lt, word, odd in (("K", "Kite", B), ("L", "Lemon", None), ("M", "Monkey", O)):
    say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", also=ALSO("dance"), cam="group",
        gap_after=0.3)
    also = {LI: "freeze", O: "freeze", B: "freeze"}
    if odd:
        also[odd] = "wobble"
    say(M, f"Freeze! {Lt}!", act="freeze", also=also, cam="group", card=Lt, sfx="pop", gap_after=0.8)
    say(ALL, f"{Lt} is for {word}!", act="freeze", cam="group", your_turn=True, gap_after=1.0)
    if odd == B:
        say(B, "Whoa! Wobble, wobble! I'm a wobbly kite!", act="wobble", cam="cu:bobo", face="happy")
    if odd == O:
        say(O, "Ooh ooh! I'm a wobbly monkey!", act="wobble", cam="cu:ollie")
say(M, "Great dancing! Take a big breath. In... and out.", act="open", cam="host", gap_after=1.0)

# 9 ---------------------------------------------------------------- Q: the palace garden
letter(6, "palace", "Ooh! A royal palace garden!", "by the fountain", (0.92, 0.85), "q", "queen", "crown", "king", O)
say(M, "Let's be kings and queens! Bow and curtsy, very fancy!", act="squat", also=ALSO("squat"), cam="group",
    your_turn=True, gap_after=0.5)
say(ALL, "Q, q, queen! Bow, and curtsy!", act="squat", also=ALSO("squat"), cam="group")
say(B, "Look at my crown! I'm Queen Bobo! No wait, King Bobo!", act="silly", cam="cu:bobo", hold={B: "crown"}, face="happy")
say(KIDS, "Hee hee! Silly Bobo!", act="laugh", cam="kids")

# 10 --------------------------------------------------------------- R: the rainbow waterfall
letter(7, "rainbow", "Wow! A rainbow over the waterfall!", "by the river stones", (0.08, 0.84), "r", "rainbow", "rainbow",
       "sun", LI)
say(M, "Let's name the rainbow colours! Red, orange, yellow, green, blue, and purple!", act="count", cam="host",
    pic="rainbow", your_turn=True, gap_after=0.6)
say(ALL, "R, r, rainbow! Red, orange, yellow, green, blue, purple!", chant=True, act="dance", also=ALSO("dance"),
    cam="group", fx="stars")
say(O, "And R is for rabbit! Hop, hop!", act="bunny", cam="cu:ollie", pic="rabbit")

# 11 --------------------------------------------------------------- S: the sunflower field (sharing)
letter(8, "sunflowers", "So many sunflowers!", "between the sunflowers", (0.92, 0.84), "s", "sun", "sun", "moon", O)
say(B, "S is for sandwich! My tummy is rumbling! Rumble, rumble!", act="wobble", cam="cu:bobo", sfx="drumroll",
    pic="sandwich")
say(B, "But... there is only one sandwich.", act="think", cam="cu:bobo", face="sad", hold={B: "sandwich"})
say(O, "Bobo, can we share it?", act="open", cam="kids")
say(B, "Yes! A bite for you, and you, and you! Sharing is kind!", act="give", cam="group", face="happy",
    give={"from": B, "to": O, "pic": "sandwich"}, gap_after=0.8)
say(M, "Thank you, Bobo! S is for sun, and S is for sharing!", act="thumbs_up", cam="host", fx="hearts")

# 12 --------------------------------------------------------------- T: the train station + the alphabet song
letter(9, "station", "Toot toot! A train station!", "on the platform", (0.08, 0.85), "t", "train", "train", "car", LI)
say(M, "Let's be a train! Hold on, and choo choo!", act="march", also=ALSO("march"), cam="group", your_turn=True,
    gap_after=0.4)
say(ALL, "T, t, train! Choo choo! Toot toot!", chant=True, act="march", also=ALSO("march"), cam="group")
say(LI, "We found all the blocks! K to T!", act="cheer", cam="kids", fx="stars")
say(M, "Let's sing our letter song! Sing with us!", act="cheer", cam="host", chapter="Letter song", your_turn=True,
    gap_after=0.5)
for part in ("K, L, M, N, O, P!", "Q, R, S, T, sing with me!", "K, L, M, N, O, P!", "Q, R, S, T, sing with me!"):
    say(ALL, part, chant=True, act="dance", also=ALSO("dance"), cam="group")
say(ALL, "Hooray!", act="yay", also=ALSO("yay"), cam="group", sfx="success", gap_after=0.6)

# 13 --------------------------------------------------------------- home: Nutty says sorry, success, twist
ask(M, "Let's take the blocks home! Look at the map!", act="point", cam="host", map=10, gap_after=1.4)
say(ALL, "Home again! Back to the treehouse!", act="run", also=ALSO("run"), cam="group", place="treehouse",
    chapter="Home again", sfx="sparkle", gap_after=0.4)
say(B, "Look who's here! It's Nutty!", act="point", cam="group", pic="squirrel")
say(M, "Nutty says: Sorry, Bobo! I wanted to learn letters too!", act="open", cam="host", pic="squirrel")
say(B, "That's okay, Nutty! Let's learn together!", act="hands_up", cam="cu:bobo", face="happy", fx="hearts")
ask(M, "Can you count the blocks with us? Ready?", act="count", cam="host", your_turn=True, gap_after=0.5)
say(M, "All ten blocks are home! K, L, M, N, O, P, Q, R, S, T! Hooray!", act="cheer", also=ALSO("cheer"), cam="group",
    fx="confetti", sfx="success")
say(O, "Wait! What's in the treasure box?", act="point", cam="kids", pic="treasure_chest", sfx="chime")
say(B, "Another block! It's... U!", act="hands_up", cam="cu:bobo", face="surprised", pic="umbrella", card="U")
say(M, "U is for umbrella! Next time, we'll finish the alphabet, from U to Z!", act="open", cam="host", teaser=True,
    pic="umbrella")
ask(M, "Can you say U? U, u, umbrella!", act="point", cam="host", your_turn=True, card="U u", gap_after=0.8)
say(KIDS, "U, u, umbrella! Yay!", act="yay", cam="kids")

# 14 --------------------------------------------------------------- calm recap + goodbye
say(M, "Now, let's sit and rest. Take a big breath in... and out.", act="open", cam="host", calm=True,
    chapter="Quiet time and goodbye", gap_after=1.6)
say(M, "Today we learned K for kite, L for lemon, M for monkey, N for nest, and O for octopus.", act="count", cam="host",
    calm=True, card="K L M N O")
say(M, "P for pig, Q for queen, R for rainbow, S for sun, and T for train.", act="count", cam="host", calm=True,
    card="P Q R S T")
say(M, "Wave goodbye with us! Let's sing our goodbye song!", act="wave", also=ALSO("wave"), cam="group", your_turn=True,
    gap_after=0.6)
say(ALL, "Bye bye, bye bye, see you soon! Bye bye, bye bye, toodle-oo!", chant=True, act="wave", cam="group", gap_after=0.6)
say(ALL, "Bye bye, friends! See you next time!", act="wave", also=ALSO("wave"), cam="group",
    endcard="Bye bye!\nSee you next time!", sfx="success")

script = {
    "voices": {
        M: {"voice": "en-US-AvaNeural", "rate": "-4%", "pitch": "+6Hz"},
        LI: {"voice": "en-US-AnaNeural", "rate": "+0%", "pitch": "+0Hz"},
        O: {"voice": "en-US-AnaNeural", "rate": "+8%", "pitch": "-14Hz"},
        B: {"voice": "en-US-GuyNeural", "rate": "-4%", "pitch": "+14Hz"},
    },
    "bpm": 104, "lead_in": 0.6, "gap": 0.45, "tail": 22.0, "lines": L,
    "learn": ["kite", "lemon", "monkey", "nest", "octopus", "pig", "queen", "rainbow", "sun", "train"],
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
