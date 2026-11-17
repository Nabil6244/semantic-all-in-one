"""Channel 2 (baby speech), episode 3 - "Baby Talk with Ms Molly: Yummy Snacks" (about 12 min). Writes baby03_yummy_snacks.json.
Same format as baby01: face shots, slow words x3, sign, long pause for the baby, praise. Food words, more / all done / please.
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


# 1 ---------------------------------------------------------------- hook, then hello (pistachio)
say(B, "Yum yum! Peekaboo! Is it snack time?", act="hands_up", cam="cu:bobo", place="pistachio", sfx="pop", fx="bubbles",
    face="happy", chapter="Peekaboo!")
say(M, "Hi, baby! Hello! Today we will say yummy food words!", act="wave", cam="face:molly", chapter="Hello song", goal=True,
    sign="bye")
turn("Can you wave hello? Hi!", act="wave")
say(M, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="face:molly")
say(M, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="clap", cam="face:molly", gap_after=0.6)
say(B, "Hi, baby! I'm Bobo! I'm hungry!", act="wave", cam="cu:bobo", face="happy")
say(M, "Baby talk, baby talk, la la la! Learning words with Ms Molly!", chant=True, act="dance", also={B: "dance"},
    cam="group", title="Yummy Snacks\nwith Ms Molly!", fx="bubbles")

# 2 ---------------------------------------------------------------- warm-up: mmm, yum, num (pistachio)
say(M, "Let's make some yummy sounds. Watch my mouth.", act="point", cam="face:molly", chapter="Mmm, yum, num")
for syl in ("mmm", "yum", "num"):
    say(M, f"{syl.capitalize()}... {syl}... {syl}.", act="open", cam="face:molly", card=syl, gap_after=0.8)
    turn(f"Your turn. {syl.capitalize()}, {syl}.", act="point", card=syl)
    say(M, f"Yes! {syl.capitalize()}! So yummy!", act="clap", cam="face:molly", sfx="sparkle")

# 3 ---------------------------------------------------------------- fruit (coral)
say(M, "Let's find some fruit!", act="open", cam="group", place="coral", sfx="sparkle", chapter="Fruit")
word("apple", "photo_apple", sign="eat")
word("banana", "photo_banana", sign="eat", extra=(B, "Peel, peel, peel! Yum!", {"act": "sign_eat", "cam": "cu:bobo", "sign": "eat",
                                                                                  "face": "happy"}))
word("strawberry", "strawberry", sign="eat")
word("lemon", "lemon", extra=(M, "Ooh, a lemon is sour! Make a sour face!", {"act": "giggle", "cam": "face:molly", "pic": "lemon"}))

# 4 ---------------------------------------------------------------- please / thank you / more (periwinkle)
say(M, "When we want something, we say please.", act="sign_please", cam="face:molly", place="periwinkle", sign="please",
    chapter="Please and thank you", card="please")
say(M, "Please. Please.", act="sign_please", cam="face:molly", card="please", sign="please", gap_after=0.8)
turn("Can you say please?", act="sign_please", sign="please", card="please")
say(B, "Cookie, please!", act="sign_please", cam="cu:bobo", sign="please", face="happy", pic="cookie")
say(M, "Here you go, Bobo!", act="give", cam="group", give={"from": M, "to": B, "pic": "cookie"}, gap_after=0.8)
say(B, "Thank you!", act="sign_thank_you", cam="cu:bobo", sign="thank_you", face="happy")
say(M, "Thank you. Thank you.", act="sign_thank_you", cam="face:molly", card="thank you", sign="thank_you", gap_after=0.8)
turn("Can you say thank you?", act="sign_thank_you", sign="thank_you", card="thank you")
say(M, "Do you want more? More. More.", act="sign_more", cam="face:molly", card="more", sign="more", gap_after=0.8)
turn("Can you say more?", act="sign_more", sign="more", card="more")

# 5 ---------------------------------------------------------------- lunch (butter)
say(M, "It's lunch time! Yum, yum!", act="cheer", cam="group", place="butter", chapter="Lunch time")
word("egg", "egg", sign="eat")
word("sandwich", "sandwich", sign="eat")
word("pizza", "pizza", sign="eat", extra=(B, "Pizza! My favourite! Yum yum yum!", {"act": "bounce", "cam": "cu:bobo", "face": "happy"}))
word("bowl", "photo_bowl")
word("cup", "photo_cup", extra=(M, "We drink from a cup. Sip, sip!", {"act": "sign_milk", "cam": "face:molly", "pic": "photo_cup"}))
word("milk", "photo_milk", sign="milk")
say(M, "Now we are all done. All done.", act="sign_all_done", cam="face:molly", card="all done", sign="all_done", gap_after=0.8)
turn("Can you say all done?", act="sign_all_done", sign="all_done", card="all done")

# 6 ---------------------------------------------------------------- treats + a song (blush)
say(M, "A little treat! And a song!", act="cheer", cam="group", place="blush", chapter="Treats and a song")
word("cookie", "cookie", sign="eat")
word("ice cream", "ice_cream", extra=(M, "Ice cream is cold! Brrr! Lick, lick!", {"act": "giggle", "cam": "face:molly", "pic": "ice_cream"}))
for part in ("Pat-a-cake, pat-a-cake, baker's man!", "Bake me a cake as fast as you can!",
             "Roll it, and pat it, and mark it with a B!", "And put it in the oven for baby and me!"):
    say(M, part, chant=True, act="clap", also={B: "clap"}, cam="group")
turn("Can you clap? Pat-a-cake!", act="clap", cam="group")

# 7 ---------------------------------------------------------------- bubbles, calm, goodbye (pistachio again)
say(M, "After snacks, we wash our hands. Bubbles!", act="open", cam="group", place="pistachio", chapter="Bubbles and bye-bye",
    pic="photo_bubbles", fx="bubbles")
say(M, "Pop, pop, pop the bubbles! Pop!", act="clap", cam="face:molly", fx="bubbles", sfx="pop")
turn("Can you say pop? Pop!", act="clap")
say(M, "Now let's be calm. Take a big breath in... and out.", act="open", cam="face:molly", calm=True, gap_after=1.6)
say(M, "Today we said apple, banana, egg, pizza, cookie, and milk. Please and thank you too!", act="count", cam="face:molly",
    calm=True, card="apple  banana  milk")
say(M, "You are doing so well, baby. I'm so proud of you.", act="sign_please", cam="face:molly", calm=True, face="happy")
say(M, "Next time, we will play with toys! Ball, car and boat!", act="open", cam="face:molly", teaser=True, pic="boat")
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
    "learn": ["apple", "banana", "egg", "pizza", "cookie", "milk", "more", "please", "thank you", "all done"],
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
