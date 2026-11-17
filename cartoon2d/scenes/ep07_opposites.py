"""Episode 7 - "Opposites with Ms Molly & Bobo" (about 19 min). Writes ep07_opposites.json next to this file.

Journey episode (STORY_BIBLE.md). Cold open: Bobo's magic opposite spinner gets blown away and every place on the map turns
"upside down". The friends visit ten places, one pair of opposites each: see it, say both words, do the move for each,
Bobo mixes them up, the child corrects him. Home again: the spinner is found, a twist (U block from ep06 sets up the next
alphabet episode), calm recap, goodbye.
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
STOPS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]


def pair(k, place, arrive, a, b, pic_a, pic_b, move_a, move_b, chant, finder, mix):
    """One opposite pair: map, arrive, show a, show b, both moves, Bobo mixes them up, the kids put him right."""
    ask(M, "Where shall we go next? Let's look at the map!", act="point", cam="host", map=k, gap_after=1.4)
    say(ALL, arrive, act="run", also=ALSO("run"), cam="group", place=place, chapter=f"{a.capitalize()} and {b}",
        sfx="sparkle", gap_after=0.5)
    say(M, f"This one is {a}!", act="open", cam="host", pic=pic_a, card=a, sfx="pop")
    say(finder, f"And this one is {b}!", act="point", cam="kids", pic=pic_b, card=b)
    say(M, f"{a.capitalize()} and {b} are opposites! {a.capitalize()}... {b}.", act="count", cam="host", card=f"{a}  {b}")
    ask(M, f"Can you say {a}? And {b}?", act="point", cam="host", your_turn=True, gap_after=1.6)
    say(ALL, f"{a.capitalize()}! {b.capitalize()}!", act=move_a, also=ALSO(move_a), cam="group", card=f"{a}  {b}")
    say(M, f"Show me {a}!", act=move_a, also=ALSO(move_a), cam="group", your_turn=True, gap_after=1.0)
    say(M, f"Now show me {b}!", act=move_b, also=ALSO(move_b), cam="group", your_turn=True, gap_after=1.0)
    say(ALL, chant, chant=True, act="dance", also=ALSO("dance"), cam="group")
    say(B, mix, act="silly", cam="cu:bobo", face="happy")
    say(KIDS, f"Nooo, Bobo! That's backwards!", act="laugh", cam="kids")
    say(B, f"Oopsie-Bobo! {a.capitalize()} and {b}! Opposites!", act="tumble", cam="cu:bobo", sfx="pop")


# 1 ---------------------------------------------------------------- cold open: the hook + the goal
say(B, "Look at my magic spinner! It spins things opposite!", act="hands_up", cam="cu:bobo", place="livingroom",
    chapter="Bobo's opposite spinner", sfx="pop")
say(LI, "Oh no! The wind blew it out of the window!", act="hands_up", also={B: "tumble", O: "wobble"}, cam="group",
    fx="leaves", face="surprised", sfx="whoosh")
say(M, "Let's follow the map and find Bobo's spinner! We'll learn opposites on the way!", act="open", cam="host", goal=True)
say(ALL, "Opposites adventure!", act="yay", also=ALSO("yay"), cam="group", title="Opposites with\nMs Molly & Bobo!",
    fx="confetti", sfx="success", gap_after=1.6)

# 2 ---------------------------------------------------------------- theme chant + hello
say(M, "Clap along with our song!", act="clap", also=ALSO("clap"), cam="group", your_turn=True, chapter="Hello song",
    gap_after=0.4)
say(ALL, "Ms Molly and Bobo! Here we go! Learning and playing, high and low!", chant=True, act="dance", also=ALSO("dance"),
    cam="group")
say(ALL, "Ms Molly and Bobo! Here we go! Learning and playing, high and low!", chant=True, act="dance", also=ALSO("dance"),
    cam="group", gap_after=0.6)
say(M, "Hi friends! I'm Miss Molly! High and low are opposites! Today we learn lots of opposites!", act="wave", cam="host",
    card="high  low")
say(LI, "Hi! I'm Lily!", act="wave", cam="kids")
say(O, "And I'm Ollie!", act="cheer", cam="kids")
say(B, "And I'm Bobo! Please help me find my spinner!", act="wave", cam="cu:bobo", face="happy")
ask(M, "Will you help Bobo? Shout yes!", act="point", cam="host", your_turn=True, gap_after=0.6)
say(KIDS, "Yes!", act="jump", also={B: "jump"}, cam="group", sfx="sparkle")
say(O, "Let's go! Ready, steady...", act="squat", cam="kids")

# 3 ---------------------------------------------------------------- big and small
pair(0, "giantveg", "Go! Whoa! A garden with giant vegetables!", "big", "small", "elephant", "mouse", "hands_up", "squat",
     "Big, big, big like an elephant! Small, small, small like a mouse!", LI, "The elephant is small! The mouse is big!")
say(O, "Squeak, squeak! I'm a tiny mouse!", act="squat", cam="cu:ollie", pic="mouse")

# 4 ---------------------------------------------------------------- fast and slow
pair(1, "track", "Zoom! A running track!", "fast", "slow", "rabbit", "turtle", "run", "walk",
     "Fast, fast, run like a rabbit! Slow, slow, walk like a turtle!", O, "The turtle is fast! Zoom zoom, turtle!")
say(M, "Let's race! Ready, steady, go! Run fast! Now... slow!", act="run", also=ALSO("run"), cam="group", your_turn=True,
    gap_after=0.6)
say(B, "I'm slow like a turtle... very... very... slow.", act="walk", cam="cu:bobo", face="happy")

# 5 ---------------------------------------------------------------- up and down
pair(2, "mountain", "Look up! Big mountains!", "up", "down", "balloon_red", "house", "hands_up", "touch_toes",
     "Up, up, up to the sky! Down, down, down to the ground!", LI, "Up is my toes! Down is the sky!")
say(M, "The cable car goes up... and down! Point up! Point down!", act="point", also=ALSO("point"), cam="group",
    your_turn=True, gap_after=0.6)

# 6 ---------------------------------------------------------------- hot and cold
pair(3, "snow", "Brrr! A snowy village!", "cold", "hot", "snowman", "sun", "wobble", "hands_up",
     "Cold, cold, shiver like a snowman! Hot, hot, sunny day!", O, "The snow is hot! The sun is cold!")
say(B, "Brrr! I'm so cold! Ah... ah... ah-CHOO!", act="sneeze", cam="cu:bobo", sfx="pop")
say(KIDS, "Hee hee! Bless you, Bobo!", act="laugh", cam="kids")

# 7 ---------------------------------------------------------------- wet and dry + freeze dance
pair(4, "rainy", "Splash! A rainy street!", "wet", "dry", "umbrella", "hat", "jump", "freeze",
     "Wet, wet, splash in the puddles! Dry, dry, under the umbrella!", LI, "My umbrella makes me wet!")
say(M, "Time for the opposite freeze dance! Dance, and freeze when I say a word!", act="dance", cam="host",
    chapter="Opposite freeze dance", fx="stars")
for word, odd in (("Big!", B), ("Small!", None), ("Fast!", O)):
    say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", also=ALSO("dance"), cam="group",
        gap_after=0.3)
    also = {LI: "freeze", O: "freeze", B: "freeze"}
    if odd:
        also[odd] = "wobble"
    say(M, f"Freeze! {word}", act="freeze", also=also, cam="group", card=word.strip("!").lower(), sfx="pop", gap_after=0.8)
    say(ALL, f"{word} {word}", act="freeze", cam="group", your_turn=True, gap_after=1.0)
    if odd == B:
        say(B, "Whoa! Wobble, wobble! I'm a wobbly big bear!", act="wobble", cam="cu:bobo", face="happy")
    if odd == O:
        say(O, "Whoops! Fast feet, wobbly feet!", act="wobble", cam="cu:ollie")
say(M, "Great dancing! Take a big breath. In... and out.", act="open", cam="host", gap_after=1.0)

# 8 ---------------------------------------------------------------- loud and quiet
pair(5, "bandstand", "Listen! Music in the park!", "loud", "quiet", "drum", "bird", "stomp", "squat",
     "Loud, loud, bang the drum! Quiet, quiet, shh, shh, shh!", O, "Shh! The drum is quiet! BANG!")
say(M, "Let's clap loud! Now clap quiet... shh...", act="clap", also=ALSO("clap"), cam="group", your_turn=True,
    gap_after=0.8)

# 9 ---------------------------------------------------------------- day and night
pair(6, "night", "Ooh! It's night time!", "night", "day", "moon", "sun", "squat", "hands_up",
     "Night, night, moon so bright! Day, day, sunny day!", LI, "At night the sun comes out!")
say(M, "Twinkle, twinkle, little star! Let's twinkle our fingers!", act="hands_up", also=ALSO("hands_up"), cam="group",
    calm=True, fx="stars", gap_after=0.6)

# 10 --------------------------------------------------------------- full and empty (sharing)
pair(7, "bakery", "Yum! A bakery!", "full", "empty", "cookie", "photo_bowl", "hands_up", "open",
     "Full, full, a full plate! Empty, empty, nothing there!", O, "My tummy is full! No... it's empty!")
say(B, "But... there is only one cookie.", act="think", cam="cu:bobo", face="sad", hold={B: "cookie"})
say(LI, "Bobo, can we share it?", act="open", cam="kids")
say(B, "Yes! A piece for you, and you, and you! Sharing is kind!", act="give", cam="group", face="happy",
    give={"from": B, "to": LI, "pic": "cookie"}, gap_after=0.8)
say(M, "Thank you, Bobo! Now the plate is empty, and our tummies are full!", act="thumbs_up", cam="host", fx="hearts")

# 11 --------------------------------------------------------------- open and shut
pair(8, "library", "Shh! A library full of books!", "open", "shut", "photo_book", "present", "open", "clap",
     "Open, shut them, open, shut them, give a little clap!", LI, "Open is shut! Shut is open!")
say(M, "Open the book... and shut it! Open... shut!", act="open", also=ALSO("open"), cam="group", your_turn=True,
    gap_after=0.6)

# 12 --------------------------------------------------------------- in and out + the spinner
pair(9, "doghouse", "Woof! A garden with a doghouse!", "in", "out", "dog", "puppy_bone", "squat", "jump",
     "In, in, in the doghouse! Out, out, out to play!", O, "The dog is out... of my sandwich!")
say(LI, "Look! Bobo's spinner is in the doghouse!", act="point", cam="kids", sfx="chime", fx="stars")
say(B, "My spinner! Thank you, friends! Thank you, puppy!", act="yay", cam="cu:bobo", face="happy", fx="confetti")
say(M, "Let's sing our opposite song! Sing with us!", act="cheer", cam="host", chapter="Opposite song", your_turn=True,
    gap_after=0.5)
for part in ("Big and small, short and tall!", "Up and down, all around!", "Fast and slow, here we go!",
             "Loud and quiet, try it, try it!"):
    say(ALL, part, chant=True, act="dance", also=ALSO("dance"), cam="group")
say(ALL, "Hooray!", act="yay", also=ALSO("yay"), cam="group", sfx="success", gap_after=0.6)

# 13 --------------------------------------------------------------- home: success + twist
ask(M, "Let's take the spinner home! Look at the map!", act="point", cam="host", map=10, gap_after=1.4)
say(ALL, "Home again! Back to the living room!", act="run", also=ALSO("run"), cam="group", place="livingroom",
    chapter="Home again", sfx="sparkle", gap_after=0.4)
ask(M, "How many opposites did we find? Let's count!", act="count", cam="host", your_turn=True, gap_after=0.5)
say(M, "Ten pairs of opposites! Hooray!", act="cheer", also=ALSO("cheer"), cam="group", fx="confetti", sfx="success")
say(B, "Let's spin it! Spin, spin, spin!", act="spin", cam="cu:bobo", face="happy")
say(O, "Wait! The spinner landed on a rainbow!", act="point", cam="kids", pic="rainbow", sfx="chime")
say(M, "A rainbow! Next time, we'll learn all the colours of the rainbow!", act="open", cam="host", teaser=True, pic="rainbow")
ask(M, "Can you say rainbow?", act="point", cam="host", your_turn=True, card="rainbow", gap_after=0.8)
say(KIDS, "Rainbow! Yay!", act="yay", cam="kids")

# 14 --------------------------------------------------------------- calm recap + goodbye
say(M, "Now, let's sit and rest. Take a big breath in... and out.", act="open", cam="host", calm=True,
    chapter="Quiet time and goodbye", gap_after=1.6)
say(M, "Today we learned big and small, fast and slow, up and down, hot and cold, and wet and dry.", act="count",
    cam="host", calm=True, card="big  small")
say(M, "Loud and quiet, day and night, full and empty, open and shut, and in and out.", act="count", cam="host",
    calm=True, card="in  out")
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
    "learn": ["big", "small", "fast", "slow", "up", "down", "hot", "cold", "loud", "quiet"],
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
