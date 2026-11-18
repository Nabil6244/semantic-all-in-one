"""Channel 2 (baby speech), episode 4 - "Baby Talk with Ms Molly: Toy Time" (about 12 min). Writes baby04_toy_time.json.
Same format as baby01-03: face shots, slow words x3, sign, long pause for the baby, praise. Toy words, go / up / more.
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


# 1 ---------------------------------------------------------------- hook, then hello (seafoam)
say(B, "Peekaboo! I found the toy box!", act="hands_up", cam="cu:bobo", place="seafoam", sfx="pop", fx="bubbles",
    face="happy", chapter="Peekaboo!", pic="present")
say(M, "Hi, baby! Hello! Today we will play with toys and say toy words!", act="wave", cam="face:molly", chapter="Hello song",
    goal=True, sign="bye")
turn("Can you wave hello? Hi!", act="wave")
say(M, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="face:molly")
say(M, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="clap", cam="face:molly", gap_after=0.6)
say(B, "Hi, baby! I'm Bobo! Let's play!", act="wave", cam="cu:bobo", face="happy")
say(M, "Baby talk, baby talk, la la la! Learning words with Ms Molly!", chant=True, act="dance", also={B: "dance"},
    cam="group", title="Toy Time\nwith Ms Molly!", fx="bubbles")

# 2 ---------------------------------------------------------------- warm-up: go, up, bang (seafoam)
say(M, "Let's make some fun play sounds. Watch my mouth.", act="point", cam="face:molly", chapter="Go, up, bang")
for syl, extra in (("go", "Ready, set, go!"), ("up", "Up, up, up we go!"), ("bang", "Bang, bang on the drum!")):
    say(M, f"{syl.capitalize()}... {syl}... {syl}.", act="open", cam="face:molly", card=syl, gap_after=0.8)
    turn(f"Your turn. {syl.capitalize()}, {syl}.", act="point", card=syl)
    say(M, f"Yes! {extra}", act="clap", cam="face:molly", sfx="sparkle")

# 3 ---------------------------------------------------------------- ball games (honeydew)
say(M, "What's in the toy box? Let's see!", act="open", cam="group", place="honeydew", sfx="sparkle", chapter="Ball games",
    pic="present")
word("ball", "photo_ball", sign="ball",
     extra=(B, "Roll the ball to me! Roll, roll, roll!", {"act": "bounce", "cam": "cu:bobo", "face": "happy", "pic": "ball"}))
say(M, "Here comes the ball, Bobo! Go!", act="give", cam="group", give={"from": M, "to": B, "pic": "ball"}, gap_after=0.8)
say(B, "Again! More ball, please!", act="sign_more", cam="cu:bobo", sign="more", face="happy")
say(M, "More. More. Bobo wants more!", act="sign_more", cam="face:molly", card="more", sign="more", gap_after=0.8)
turn("Can you say more?", act="sign_more", sign="more", card="more")
say(M, "Throw the ball up! Up, up, up!", act="hands_up", cam="face:molly", card="up", pic="ball", sfx="pop")
turn("Can you say up?", act="hands_up", card="up")
word("balloon", "balloon_red", extra=(M, "The balloon floats up, up, up! Bye-bye, balloon!", {"act": "hands_up", "cam": "face:molly",
                                                                                              "pic": "balloon_red"}))

# 4 ---------------------------------------------------------------- things that go (sand)
say(M, "Now let's play with things that go! Vroom!", act="cheer", cam="group", place="sand", chapter="Things that go")
word("car", "photo_car", sound="beep beep")
say(M, "Ready, set... go! The car goes fast!", act="point", cam="face:molly", card="go", pic="photo_car", sfx="pop")
turn("Can you say go?", act="point", card="go")
word("train", "train", sound="choo choo",
     extra=(B, "Choo choo! All aboard! Here I go!", {"act": "bounce", "cam": "cu:bobo", "face": "happy", "pic": "train"}))
word("boat", "boat", extra=(M, "The boat goes on the water. Splash, splash!", {"act": "open", "cam": "face:molly", "pic": "boat"}))

# 5 ---------------------------------------------------------------- bath toys and music (bluebell)
say(M, "Some toys love bath time! And some make music!", act="open", cam="group", place="bluebell", chapter="Duck and drum")
word("duck", "photo_duck", sound="quack quack")
word("drum", "drum", extra=(B, "Bang, bang, bang! I'm a drummer!", {"act": "clap", "cam": "cu:bobo", "face": "happy", "pic": "drum"}))
say(M, "Let's play the drum together. Bang, bang, bang!", act="clap", also={B: "clap"}, cam="group", card="bang", sfx="pop")
turn("Can you clap and say bang?", act="clap", card="bang")
say(M, "Do you want more music? More!", act="sign_more", cam="face:molly", card="more", sign="more", gap_after=0.8)
turn("Can you say more?", act="sign_more", sign="more", card="more")

# 6 ---------------------------------------------------------------- blocks and a song (melon)
say(M, "Let's build a tower with blocks!", act="cheer", cam="group", place="melon", chapter="Blocks and a song", pic="block_a")
word("block", "block_b", extra=(M, "One block, two blocks, up, up, up! Oh no! Fall down, boom!", {"act": "giggle", "cam": "face:molly",
                                                                                                "pic": "block_c"}))
say(B, "Again! Up, up, up!", act="hands_up", cam="cu:bobo", face="happy", card="up")
turn("Can you say up?", act="hands_up", card="up")
for part in ("Row, row, row your boat, gently down the stream!", "Merrily, merrily, merrily, merrily, life is but a dream!",
             "Row, row, row your boat, gently down the stream!", "Merrily, merrily, merrily, merrily, life is but a dream!"):
    say(M, part, chant=True, act="dance", also={B: "dance"}, cam="group", pic="boat")
turn("Can you row the boat? Row, row!", act="dance", cam="group")

# 7 ---------------------------------------------------------------- a book, tidy up, goodbye (seafoam again)
say(M, "Toys away, and one quiet book before we go.", act="sign_book", cam="group", place="seafoam", chapter="Book and bye-bye",
    sign="book", pic="photo_book")
word("book", "photo_book", sign="book")
say(M, "Now we put the toys away. All done. All done.", act="sign_all_done", cam="face:molly", card="all done", sign="all_done",
    gap_after=0.8)
turn("Can you say all done?", act="sign_all_done", sign="all_done", card="all done")
say(B, "All done! All done! Bye-bye, toys!", act="sign_all_done", cam="cu:bobo", sign="all_done", face="happy")
say(M, "Now let's be calm. Take a big breath in... and out.", act="open", cam="face:molly", calm=True, gap_after=1.6)
say(M, "Today we said ball, car, train, boat, duck, drum, block and book. And go, up and more!", act="count",
    cam="face:molly", calm=True, card="ball  car  boat")
say(M, "You are doing so well, baby. I'm so proud of you.", act="sign_please", cam="face:molly", calm=True, face="happy")
say(M, "Next time, it's bath time! Splash, bubbles and duck!", act="open", cam="face:molly", teaser=True, pic="photo_bubbles")
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
    "learn": ["ball", "car", "train", "boat", "duck", "drum", "block", "book", "go", "up", "more", "all done"],
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
