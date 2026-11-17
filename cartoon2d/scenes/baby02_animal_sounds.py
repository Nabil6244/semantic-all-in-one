"""Channel 2 (baby speech), episode 2 - "Baby Talk with Ms Molly: Animal Sounds" (about 12 min). Writes baby02_animal_sounds.json.
Same format as baby01: face shots, slow words x3, sign, long pause for the baby, praise. Farm animal sounds + songs.
"""
import json
from pathlib import Path

L = []
M, B = "molly", "bobo"
TURN = 3.2                                  # silence after "your turn": time for a baby to try


def say(who, text, **k):
    L.append({"who": who, "text": text, **k})


def turn(text, **k):
    k.setdefault("gap_after", TURN)
    say(M, text, your_turn=True, cam=k.pop("cam", "face:molly"), **k)


def word(w, pic, sign=None, sound=None, extra=None):
    """One first word: picture, slow word x3, sign, try, praise, again."""
    say(M, f"Look! A {w}!", act="point", cam="face:molly", pic=pic, card=w, sfx="pop", chapter=w.capitalize())
    say(M, f"{w.capitalize()}... {w}... {w}.", act=f"sign_{sign}" if sign else "open", cam="face:molly", pic=pic, card=w,
        sign=sign, gap_after=0.8)
    turn(f"Can you say {w}?", act=f"sign_{sign}" if sign else "point", card=w, sign=sign)
    say(M, f"Yes! {w.capitalize()}! Good job!", act="clap", cam="face:molly", sfx="sparkle", face="happy")
    if sound:
        say(M, f"The {w} says {sound}! {sound}!", act="open", cam="face:molly", pic=pic, card=sound)
        turn(f"Can you say {sound}?", act="point")
    turn(f"One more time. {w.capitalize()}.", act=f"sign_{sign}" if sign else "open", card=w, sign=sign)
    if extra:
        say(*extra[:2], **extra[2])


# 1 ---------------------------------------------------------------- hook, then hello (rose)
say(B, "Moo! Peekaboo! I'm a cow! No, I'm Bobo!", act="hands_up", cam="cu:bobo", place="rose", sfx="pop", fx="bubbles",
    face="happy", chapter="Peekaboo!")
say(M, "Hi, baby! Hello! Today we will learn animal sounds!", act="wave", cam="face:molly", chapter="Hello song", goal=True,
    sign="bye")
turn("Can you wave hello? Hi!", act="wave")
say(M, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="face:molly")
say(M, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="clap", cam="face:molly", gap_after=0.6)
say(B, "Hi, baby! I'm Bobo! I love animals!", act="wave", cam="cu:bobo", face="happy")
say(M, "Baby talk, baby talk, la la la! Learning words with Ms Molly!", chant=True, act="dance", also={B: "dance"},
    cam="group", title="Animal Sounds\nwith Ms Molly!", fx="bubbles")

# 2 ---------------------------------------------------------------- warm-up: moo, baa, oo (rose)
say(M, "Let's make some sounds. Watch my mouth.", act="point", cam="face:molly", chapter="Moo, baa, oink")
for syl, w in (("moo", "cow"), ("baa", "sheep"), ("oink", "pig")):
    say(M, f"{syl.capitalize()}... {syl}... {syl}.", act="open", cam="face:molly", card=syl, gap_after=0.8)
    turn(f"Your turn. {syl.capitalize()}, {syl}.", act="point", card=syl)
    say(M, f"Yes! {syl.capitalize()}! Like a {w}!", act="clap", cam="face:molly", sfx="sparkle")

# 3 ---------------------------------------------------------------- cow, sheep, pig (aqua)
say(M, "Let's visit the farm animals!", act="open", cam="group", place="aqua", sfx="sparkle")
word("cow", "cow", sound="moo")
word("sheep", "sheep", sound="baa", extra=(B, "Baa baa! Fluffy sheep!", {"act": "bounce", "cam": "cu:bobo", "face": "happy"}))
word("pig", "pig", sound="oink oink")
say(M, "Old MacDonald had a farm, ee-i-ee-i-o!", chant=True, act="clap", also={B: "clap"}, cam="group", chapter="Old MacDonald")
say(M, "And on that farm he had a cow, ee-i-ee-i-o!", chant=True, act="clap", also={B: "clap"}, cam="group", pic="cow")
say(M, "With a moo moo here, and a moo moo there!", chant=True, act="dance", also={B: "dance"}, cam="group")
turn("Can you say moo?", act="point", card="moo")

# 4 ---------------------------------------------------------------- horse, duck, chick, peek-a-boo (apricot)
say(M, "More animal friends are here!", act="cheer", cam="group", place="apricot", sfx="sparkle")
word("horse", "horse", sound="neigh", extra=(M, "The horse goes clip clop, clip clop!", {"act": "march", "cam": "face:molly",
                                                                                         "pic": "horse"}))
word("duck", "duck", sound="quack quack")
word("chick", "chick", sound="cheep cheep")
say(M, "Where is Bobo? Let's play peek-a-boo!", act="think", cam="group", chapter="Peek-a-boo", game={"type": "hide", "who": B})
turn("Where is Bobo?", act="think", cam="group")
say(B, "Peek-a-boo! Quack quack!", act="cheer", cam="cu:bobo", game={"type": "found", "who": B}, face="happy", sfx="pop")
say(M, "Peek-a-boo! There he is! Hee hee!", act="laugh", cam="group")
turn("Can you say boo? Boo!", act="point", cam="face:molly")

# 5 ---------------------------------------------------------------- calm song (lilac)
say(M, "Let's sing a little song, and watch the bubbles.", act="open", cam="group", place="lilac", chapter="Baa baa black sheep",
    fx="bubbles")
for part in ("Baa, baa, black sheep, have you any wool?", "Yes sir, yes sir, three bags full!",
             "Baa, baa, black sheep, have you any wool?", "Yes sir, yes sir, three bags full!"):
    say(M, part, chant=True, act="hands_up", also={B: "hands_up"}, cam="group", fx="stars", pic="sheep")
turn("Can you say baa?", act="clap", card="baa")

# 6 ---------------------------------------------------------------- pets: dog, cat, bird, fish (cream)
say(M, "Now let's meet the pets at home!", act="cheer", cam="group", place="cream", chapter="Pets")
word("dog", "dog", sign="dog", sound="woof woof")
word("cat", "cat", sound="meow")
say(B, "Meow! I'm a kitty cat! Purr, purr!", act="silly", cam="cu:bobo", face="happy")
word("bird", "bird", sound="tweet tweet")
word("fish", "fish", extra=(M, "The fish goes swim, swim, swim! Blub blub!", {"act": "wave", "cam": "face:molly", "pic": "fish"}))
word("frog", "frog", sound="ribbit", extra=(M, "Hop, hop, hop like a frog!", {"act": "frog", "cam": "group"}))

# 7 ---------------------------------------------------------------- move song, calm, goodbye (rose again)
say(M, "Let's move like animals! Stomp like an elephant!", act="stomp", also={B: "stomp"}, cam="group", place="rose",
    chapter="Move like animals", pic="elephant")
say(M, "Hop like a bunny! Hop, hop, hop!", act="bunny", also={B: "bunny"}, cam="group")
say(M, "Flap like a bird! Flap, flap, flap!", act="wave", also={B: "wave"}, cam="group", pic="bird")
turn("Can you flap your arms?", act="wave", cam="group")
say(M, "Now let's be calm. Take a big breath in... and out.", act="open", cam="face:molly", calm=True, chapter="Bye-bye",
    gap_after=1.6)
say(M, "Today we said moo, baa, oink, neigh, quack, woof and meow!", act="count", cam="face:molly", calm=True,
    card="moo  baa  oink")
say(M, "You are doing so well, baby. I'm so proud of you.", act="sign_please", cam="face:molly", calm=True, face="happy")
say(M, "Next time, we will have yummy snacks! Yum, yum!", act="open", cam="face:molly", teaser=True, pic="strawberry")
say(M, "Let's wave bye-bye. Bye-bye.", act="sign_bye", cam="face:molly", sign="bye", your_turn=True, gap_after=2.8)
say(M, "Bye bye, bye bye, see you soon! Bye bye, bye bye, toodle-oo!", chant=True, act="wave", also={B: "wave"}, cam="group",
    gap_after=0.6)
say(M, "Bye-bye, baby! See you next time!", act="wave", also={B: "wave"}, cam="group", endcard="Bye-bye!\nSee you soon!",
    sfx="success")


script = {
    "voices": {
        M: {"voice": "en-US-AvaNeural", "rate": "-16%", "pitch": "+6Hz"},
        B: {"voice": "en-US-GuyNeural", "rate": "-8%", "pitch": "+14Hz"},
    },
    "bpm": 92, "lead_in": 0.6, "gap": 0.6, "tail": 22.0, "lines": L,
    "learn": ["cow", "sheep", "pig", "horse", "duck", "dog", "cat", "moo", "baa", "woof"],
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
