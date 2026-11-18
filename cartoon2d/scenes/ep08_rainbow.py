"""Episode 8 - "Rainbow Colours with Ms Molly & Bobo" (about 15 min). Writes ep08_rainbow.json next to this file.

Journey episode (STORY_BIBLE.md), set up by ep07's teaser (the spinner landed on a rainbow). Cold open: Bobo's rainbow
painting loses all its colours. The friends visit seven places, one colour each: see it, say it, find two things that
colour, do the colour move, Bobo gets it wrong, the child corrects him. A paint-mixing stop (red + yellow = orange,
blue + yellow = green) and a colour freeze dance. The rainbow comes back, a twist (Bobo's paw prints lead to the next
episode, body parts), calm recap, goodbye. Places reuse painted Flow backgrounds from ep05-ep07 (no new art needed).
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


def colour(k, place, arrive, c, pic_a, pic_b, name_a, name_b, move, chant, finder, mix):
    """One colour stop: map, arrive, the colour, two things that colour, the move, Bobo mixes it up, the kids put him right."""
    ask(M, "Which colour is next? Let's look at the map!", act="point", cam="host", map=k, gap_after=1.4)
    say(ALL, arrive, act="run", also=ALSO("run"), cam="group", place=place, chapter=c.capitalize(), sfx="sparkle", gap_after=0.5)
    say(M, f"Look! Everything here is {c}! {c.capitalize()}!", act="open", cam="host", card=c, sfx="pop")
    ask(M, f"Can you say {c}?", act="point", cam="host", your_turn=True, card=c, gap_after=1.6)
    say(KIDS, f"{c.capitalize()}!", act="cheer", cam="kids", card=c)
    say(M, f"A {name_a} is {c}!", act="point", cam="host", card=c, **({"pic": pic_a} if pic_a else {}))
    say(finder, f"And a {name_b} is {c} too!", act="point", cam="kids", card=c, **({"pic": pic_b} if pic_b else {}))
    say(ALL, chant, chant=True, act=move, also=ALSO(move), cam="group")
    say(M, f"Find something {c} where you are! Point to it!", act="point", cam="host", your_turn=True, gap_after=1.8)
    say(B, mix, act="silly", cam="cu:bobo", face="happy")
    say(KIDS, f"Nooo, Bobo! It's {c}!", act="laugh", cam="kids")
    say(B, f"Oopsie-Bobo! {c.capitalize()}! {c.capitalize()} for my rainbow!", act="tumble", cam="cu:bobo", sfx="pop")
    say(M, f"We found {c}! It flies back into Bobo's rainbow!", act="yay", also=ALSO("yay"), cam="group", fx="stars",
        sfx="chime", card=c)


# 1 ---------------------------------------------------------------- cold open: the hook + the goal
say(B, "Look at my rainbow painting! It's so colourful!", act="hands_up", cam="cu:bobo", place="livingroom",
    chapter="Bobo's rainbow", sfx="pop", pic="rainbow")
say(LI, "Oh no! The colours are floating away! The rainbow is all white!", act="hands_up", also={B: "tumble", O: "wobble"},
    cam="group", fx="stars", face="surprised", sfx="whoosh")
say(M, "Let's follow the map and find every colour of the rainbow! One, two, three, go!", act="open", cam="host", goal=True)
say(ALL, "Rainbow adventure!", act="yay", also=ALSO("yay"), cam="group", title="Rainbow Colours with\nMs Molly & Bobo!",
    fx="confetti", sfx="success", gap_after=1.6)

# 2 ---------------------------------------------------------------- theme chant + hello
say(M, "Clap along with our song!", act="clap", also=ALSO("clap"), cam="group", your_turn=True, chapter="Hello song",
    gap_after=0.4)
say(ALL, "Ms Molly and Bobo! Here we go! Learning and playing, high and low!", chant=True, act="dance", also=ALSO("dance"),
    cam="group")
say(ALL, "Ms Molly and Bobo! Here we go! Learning and playing, high and low!", chant=True, act="dance", also=ALSO("dance"),
    cam="group", gap_after=0.6)
say(M, "Hi friends! I'm Miss Molly! Today we will find all the colours of the rainbow!", act="wave", cam="host",
    card="rainbow")
say(LI, "Hi! I'm Lily!", act="wave", cam="kids")
say(O, "And I'm Ollie!", act="cheer", cam="kids")
say(B, "And I'm Bobo! Please help me bring back my colours!", act="wave", cam="cu:bobo", face="sad")
ask(M, "Will you help Bobo? Shout yes!", act="point", cam="host", your_turn=True, gap_after=0.6)
say(KIDS, "Yes!", act="jump", also={B: "jump"}, cam="group", sfx="sparkle")
say(O, "Let's go! Ready, steady...", act="squat", cam="kids")

# 3 ---------------------------------------------------------------- red
colour(0, "orchard", "Go! An orchard full of apple trees!", "red", "apple", "strawberry", "apple", "strawberry", "stomp",
       "Red, red, red like an apple! Stomp, stomp, stomp your feet!", LI, "Red is a banana! Peel, peel!")
say(B, "Crunch, crunch! Red apples are yummy!", act="bounce", cam="cu:bobo", face="happy", pic="apple")

# 4 ---------------------------------------------------------------- orange
colour(1, "pumpkins", "Wow! A pumpkin patch!", "orange", None, None, "pumpkin", "carrot", "spin",
       "Orange, orange, round and round! Spin like a pumpkin on the ground!", O, "Orange is the sky! Oops!")

# 5 ---------------------------------------------------------------- yellow
colour(2, "sunflowers", "Sunny! A field of sunflowers!", "yellow", "sun", "duck", "sun", "duck", "hands_up",
       "Yellow, yellow, bright like the sun! Reach up high and have some fun!", LI, "Yellow is a frog! Ribbit!")
say(O, "Quack, quack! I'm a yellow duck!", act="wobble", cam="cu:ollie", pic="duck")

# 6 ---------------------------------------------------------------- paint mixing
ask(M, "Let's stop at the art room and mix some paint! Look at the map!", act="point", cam="host", map=3, gap_after=1.4)
say(ALL, "Art time! Paint pots!", act="run", also=ALSO("run"), cam="group", place="classroom", chapter="Mixing colours",
    sfx="sparkle", gap_after=0.5)
say(M, "Red paint, and yellow paint. Let's mix them. Stir, stir, stir!", act="open", cam="host", pic="paint", card="red + yellow")
ask(M, "What colour did we make?", act="point", cam="host", your_turn=True, gap_after=1.6)
say(KIDS, "Orange!", act="cheer", cam="kids", card="orange", sfx="pop")
say(M, "Yes! Red and yellow make orange! Now blue and yellow. Stir, stir, stir!", act="open", cam="host", pic="paint",
    card="blue + yellow")
ask(M, "What colour is it now?", act="point", cam="host", your_turn=True, gap_after=1.6)
say(KIDS, "Green!", act="cheer", cam="kids", card="green", sfx="pop")
say(B, "I'll mix ALL the colours! Stir, stir... oh. It's brown! Like mud!", act="silly", cam="cu:bobo", face="happy")
say(KIDS, "Hee hee! Silly Bobo!", act="laugh", cam="kids")

# 7 ---------------------------------------------------------------- green
colour(4, "meadow", "Whoosh! A big green meadow!", "green", "frog", "turtle", "frog", "turtle", "jump",
       "Green, green, hop like a frog! Jump, jump, over the log!", O, "Green is my pink nose!")

# 8 ---------------------------------------------------------------- blue + freeze dance
colour(5, "beach", "Splash! The seaside!", "blue", "fish", "balloon_blue", "fish", "balloon", "wobble",
       "Blue, blue, like the sea! Wave your arms and swim with me!", LI, "The sea is red! The fish is purple!")
say(M, "Time for the colour freeze dance! Dance, and freeze when I say a colour!", act="dance", cam="host",
    chapter="Colour freeze dance", fx="stars")
for word, odd in (("Red!", B), ("Yellow!", None), ("Blue!", O)):
    say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", also=ALSO("dance"), cam="group",
        gap_after=0.3)
    also = {LI: "freeze", O: "freeze", B: "freeze"}
    if odd:
        also[odd] = "wobble"
    say(M, f"Freeze! {word}", act="freeze", also=also, cam="group", card=word.strip("!").lower(), sfx="pop", gap_after=0.8)
    say(ALL, f"{word} {word}", act="freeze", cam="group", your_turn=True, gap_after=1.0)
    if odd == B:
        say(B, "Whoa! Wobble, wobble! I'm a wobbly red bear!", act="wobble", cam="cu:bobo", face="happy")
    if odd == O:
        say(O, "Whoops! Blue feet, wobbly feet!", act="wobble", cam="cu:ollie")
say(M, "Great dancing! Take a big breath. In... and out.", act="open", cam="host", gap_after=1.0)

# 9 ---------------------------------------------------------------- purple
colour(6, "night", "Ooh! A purple night sky!", "purple", "sun_purple", None, "purple sun", "plum", "squat",
       "Purple, purple, night is here! Sparkle, twinkle, far and near!", O, "Purple is a carrot! Crunch!")
say(M, "Twinkle, twinkle, little star! Let's twinkle our fingers!", act="hands_up", also=ALSO("hands_up"), cam="group",
    calm=True, fx="stars", gap_after=0.6)

# 10 --------------------------------------------------------------- the rainbow comes back
ask(M, "We found every colour! Let's go to the rainbow! Look at the map!", act="point", cam="host", map=7, gap_after=1.4)
say(ALL, "Wow! A real rainbow!", act="run", also=ALSO("run"), cam="group", place="rainbow", chapter="Rainbow song",
    sfx="sparkle", gap_after=0.4)
say(LI, "Look! All the colours are flying back!", act="point", cam="kids", pic="rainbow", fx="confetti", sfx="chime")
say(B, "My rainbow! Thank you, friends! Thank you!", act="yay", cam="cu:bobo", face="happy", fx="hearts")
say(M, "Let's sing the rainbow song! Sing with us!", act="cheer", cam="host", your_turn=True, gap_after=0.5)
for part in ("Red and orange, yellow too!", "Green and blue, and purple for you!", "Red and orange, yellow too!",
             "I can sing a rainbow, so can you!"):
    say(ALL, part, chant=True, act="dance", also=ALSO("dance"), cam="group", pic="rainbow")
say(ALL, "Hooray!", act="yay", also=ALSO("yay"), cam="group", sfx="success", gap_after=0.6)

# 11 --------------------------------------------------------------- home: success + twist
ask(M, "Let's take the rainbow home! Look at the map!", act="point", cam="host", map=8, gap_after=1.4)
say(ALL, "Home again! Back to the living room!", act="run", also=ALSO("run"), cam="group", place="livingroom",
    chapter="Home again", sfx="sparkle", gap_after=0.4)
ask(M, "How many colours did we find? Let's count!", act="count", cam="host", your_turn=True, gap_after=0.5)
say(M, "Red, orange, yellow, green, blue and purple! Six colours! Hooray!", act="cheer", also=ALSO("cheer"), cam="group",
    fx="confetti", sfx="success", card="six colours")
say(B, "Oops! I got paint on my paws! Look, paw prints!", act="silly", cam="cu:bobo", face="happy", sfx="pop")
say(O, "Paws, hands, feet... Next time, let's learn our body parts!", act="point", cam="kids", sfx="chime")
say(M, "Yes! Next time we'll learn head, shoulders, knees and toes!", act="open", cam="host", teaser=True)
ask(M, "Can you touch your toes?", act="touch_toes", cam="host", your_turn=True, gap_after=0.8)
say(KIDS, "Toes! Yay!", act="yay", cam="kids")

# 12 --------------------------------------------------------------- calm recap + goodbye
say(M, "Now, let's sit and rest. Take a big breath in... and out.", act="open", cam="host", calm=True,
    chapter="Quiet time and goodbye", gap_after=1.6)
say(M, "Today we found red apples, orange pumpkins, yellow sunflowers, and green frogs.", act="count", cam="host",
    calm=True, card="red  orange  yellow")
say(M, "Blue sea, purple night, and we mixed paint to make orange and green.", act="count", cam="host", calm=True,
    card="green  blue  purple")
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
    "learn": ["red", "orange", "yellow", "green", "blue", "purple"],
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
