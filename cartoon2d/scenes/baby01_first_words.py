"""Channel 2 (baby speech), episode 1 - "Baby Talk with Ms Molly: First Words" (about 15 min). Writes baby01_first_words.json.

Format (ages 0-3): Ms Molly close to the camera ("face" shot), slow clear speech, one word at a time: show the picture,
say it slowly three times, sign it, then a long pause for the baby to try, then praise. Simple public-domain songs with
actions, peek-a-boo with Bobo, bubbles, calm studio sets. Words: ball, dog, duck, car, more, eat, milk, all done, shoes,
mama, dada, bye-bye.
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


# 1 ---------------------------------------------------------------- hook, then hello (peach)
say(B, "Peekaboo! I see you, baby!", act="hands_up", cam="cu:bobo", place="peach", sfx="pop", fx="bubbles", face="happy",
    chapter="Peekaboo!")
say(M, "Hi, baby! Hello! Today we will say our first words!", act="wave", cam="face:molly", chapter="Hello song", goal=True,
    sign="bye")
turn("Can you wave hello? Hi!", act="wave")
say(M, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="face:molly")
say(M, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="clap", cam="face:molly", gap_after=0.6)
say(B, "Hi, baby! I'm Bobo! Hello!", act="wave", cam="cu:bobo", face="happy")
say(M, "Baby talk, baby talk, la la la! Learning words with Ms Molly!", chant=True, act="dance", also={B: "dance"},
    cam="group", title="Baby Talk with\nMs Molly!", fx="bubbles")

# 2 ---------------------------------------------------------------- mouth warm-up: ba, ma, da (peach)
say(M, "Let's make some sounds. Watch my mouth.", act="point", cam="face:molly", chapter="Ba, ma, da")
for syl, w, sg in (("ba", "ball", None), ("ma", "mama", "mama"), ("da", "dada", "dada")):
    say(M, f"{syl.capitalize()}... {syl}... {syl}.", act=f"sign_{sg}" if sg else "open", cam="face:molly", card=syl, gap_after=0.8)
    turn(f"Your turn. {syl.capitalize()}, {syl}.", act="point", card=syl)
    say(M, f"Yes! {syl.capitalize()} {syl}! Like {w}!", act=f"sign_{sg}" if sg else "clap", cam="face:molly", sfx="sparkle",
        sign=sg)
say(M, "Mama. Mama.", act="sign_mama", cam="face:molly", card="mama", sign="mama", gap_after=0.8)
turn("Can you say mama?", act="sign_mama", sign="mama", card="mama")
say(M, "Dada. Dada.", act="sign_dada", cam="face:molly", card="dada", sign="dada", gap_after=0.8)
turn("Can you say dada?", act="sign_dada", sign="dada", card="dada")
say(M, "Yay! Mama and dada! Clap, clap, clap!", act="clap", cam="face:molly", sfx="success", fx="hearts")

# 3 ---------------------------------------------------------------- ball and dog (mint)
say(M, "Let's find some toys!", act="open", cam="group", place="mint", sfx="sparkle")
word("ball", "photo_ball", sign="ball", extra=(M, "Let's roll the ball! Roll, roll, roll!", {"act": "open", "cam": "face:molly",
                                                                                              "pic": "photo_ball"}))
word("dog", "photo_puppy", sign="dog", sound="woof woof")
say(B, "Woof woof! I love dogs!", act="bounce", cam="cu:bobo", face="happy")

# 4 ---------------------------------------------------------------- duck, car, peek-a-boo (sky)
say(M, "More friends are here!", act="cheer", cam="group", place="sky", sfx="sparkle")
word("duck", "photo_duck", sound="quack quack")
word("car", "photo_car", sound="vroom vroom",
     extra=(M, "Vroom! The car goes fast! Vroom, vroom!", {"act": "march", "cam": "face:molly", "pic": "photo_car"}))
say(M, "Where is Bobo? Let's play peek-a-boo!", act="think", cam="group", chapter="Peek-a-boo",
    game={"type": "hide", "who": B})
turn("Where is Bobo?", act="think", cam="group")
say(B, "Peek-a-boo!", act="cheer", cam="cu:bobo", game={"type": "found", "who": B}, face="happy", sfx="pop")
say(M, "Peek-a-boo! There he is! Hee hee!", act="laugh", cam="group")
turn("Can you say boo? Boo!", act="point", cam="face:molly")

# 5 ---------------------------------------------------------------- a calm song with bubbles (lavender)
say(M, "Let's sing a little song, and watch the bubbles.", act="open", cam="group", place="lavender",
    chapter="Twinkle, twinkle", fx="bubbles")
for part in ("Twinkle, twinkle, little star, how I wonder what you are!",
             "Up above the world so high, like a diamond in the sky!",
             "Twinkle, twinkle, little star, how I wonder what you are!"):
    say(M, part, chant=True, act="hands_up", also={B: "hands_up"}, cam="group", fx="stars")
say(M, "Pop, pop, pop the bubbles! Pop!", act="clap", cam="face:molly", fx="bubbles", sfx="pop")
turn("Can you say pop? Pop!", act="clap")

# 6 ---------------------------------------------------------------- snack time: more, eat, milk, all done (lemon)
say(M, "It's snack time! Yum, yum!", act="cheer", cam="group", place="lemon", chapter="Snack time")
word("banana", "photo_banana", sign="eat",
     extra=(B, "Yum! I want to eat the banana!", {"act": "sign_eat", "cam": "cu:bobo", "sign": "eat", "face": "happy"}))
say(M, "Eat. Eat.", act="sign_eat", cam="face:molly", card="eat", sign="eat", gap_after=0.8)
turn("Can you say eat?", act="sign_eat", sign="eat", card="eat")
word("milk", "photo_milk", sign="milk")
say(M, "Do you want more? More. More.", act="sign_more", cam="face:molly", card="more", sign="more", gap_after=0.8)
turn("Can you say more?", act="sign_more", sign="more", card="more")
say(B, "More, please! More banana!", act="sign_more", cam="cu:bobo", sign="more", face="happy")
say(M, "Here you go, Bobo! More!", act="give", cam="group", give={"from": M, "to": B, "pic": "photo_banana"}, gap_after=0.8)
say(M, "More, more, more! Yummy!", act="sign_more", cam="face:molly", sign="more", card="more")
say(M, "Now we are all done. All done.", act="sign_all_done", cam="face:molly", card="all done", sign="all_done", gap_after=0.8)
turn("Can you say all done?", act="sign_all_done", sign="all_done", card="all done")
say(B, "All done! Thank you!", act="sign_thank_you", cam="cu:bobo", sign="thank_you", face="happy")
word("cup", "photo_cup", extra=(M, "We drink from a cup. Sip, sip!", {"act": "sign_eat", "cam": "face:molly", "pic": "photo_cup"}))
word("apple", "photo_apple", sign="eat",
     extra=(M, "Crunch, crunch! We eat the apple! Eat, eat!", {"act": "sign_eat", "cam": "face:molly", "sign": "eat",
                                                               "pic": "photo_apple"}))

# 6b --------------------------------------------------------------- book and a rocking song (mint again)
say(M, "Story time! Let's look at a book.", act="sign_book", cam="group", place="mint", chapter="Book and boat song",
    sign="book")
word("book", "photo_book", sign="book")
say(M, "Let's rock in a little boat! Rock, rock, rock!", act="dance", also={B: "dance"}, cam="group", fx="bubbles")
for part in ("Row, row, row your boat, gently down the stream!", "Merrily, merrily, merrily, merrily, life is but a dream!",
             "Row, row, row your boat, gently down the stream!", "Merrily, merrily, merrily, merrily, life is but a dream!"):
    say(M, part, chant=True, act="dance", also={B: "dance"}, cam="group")
turn("Can you rock with me? Rock, rock!", act="dance", cam="group")

# 7 ---------------------------------------------------------------- move song, shoes, calm, goodbye (peach again)
say(M, "Let's stand up and move! Head, shoulders, knees and toes!", act="hands_up", cam="group", place="peach",
    chapter="Head, shoulders, knees and toes")
for part in ("Head, shoulders, knees and toes, knees and toes!", "Head, shoulders, knees and toes, knees and toes!",
             "And eyes and ears and mouth and nose!", "Head, shoulders, knees and toes, knees and toes!"):
    say(M, part, chant=True, act="touch_head" if "Head" in part else "point", also={B: "touch_toes"}, cam="group")
word("shoes", "photo_shoes", extra=(M, "Shoes go on our feet! Tap, tap, tap!", {"act": "stomp", "cam": "group"}))
say(M, "Now let's be calm. Take a big breath in... and out.", act="open", cam="face:molly", calm=True, chapter="Bye-bye",
    gap_after=1.6)
say(M, "Today we said ball, dog, duck, car, banana, milk, and shoes. Mama and dada too!", act="count", cam="face:molly",
    calm=True, card="ball  dog  duck  car")
say(M, "You are doing so well, baby. I'm so proud of you.", act="sign_please", cam="face:molly", calm=True, face="happy")
say(M, "Next time, we will learn animal sounds! Moo! Baa!", act="open", cam="face:molly", teaser=True, pic="cow")
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
    "learn": ["ball", "dog", "duck", "car", "milk", "more", "eat", "shoes", "mama", "dada"],
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
