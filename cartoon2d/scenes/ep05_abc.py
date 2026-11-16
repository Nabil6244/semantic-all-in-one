"""Episode 5 - "ABC with Ms Molly & Bobo: Bobo's ABC Adventure" (about 19 min). Writes ep05_abc.json next to this file.

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
STOPS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]


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
say(B, "My ABC blocks! For the ABC party!", act="hands_up", cam="cu:bobo", place="classroom",
    chapter="Bobo's ABC blocks", pic="block_a", sfx="pop")
say(LI, "Oh no! Nutty opened the window!", act="hands_up", also={B: "tumble", O: "wobble"}, cam="group", pic="squirrel",
    fx="leaves", face="surprised", sfx="whoosh")
say(M, "The wind blew Bobo's blocks away! Let's go and find them all!", act="open", cam="host", goal=True)
say(ALL, "ABC adventure!", act="yay", also=ALSO("yay"), cam="group", title="ABC Adventure with\nMs Molly & Bobo!",
    fx="confetti", sfx="success", gap_after=1.6)

# 2 ---------------------------------------------------------------- theme chant + hello
say(M, "Clap along with our song!", act="clap", also=ALSO("clap"), cam="group", your_turn=True, chapter="Hello song",
    gap_after=0.4)
say(ALL, "Ms Molly and Bobo! Here we go! Learning and playing, high and low!", chant=True, act="dance", also=ALSO("dance"),
    cam="group")
say(ALL, "Ms Molly and Bobo! Here we go! Learning and playing, high and low!", chant=True, act="dance", also=ALSO("dance"),
    cam="group", gap_after=0.6)
say(M, "Hi friends! I'm Miss Molly! Today we're learning letters, from A to J!", act="wave", cam="host", card="A B C")
say(LI, "Hi! I'm Lily!", act="wave", cam="kids")
say(O, "And I'm Ollie!", act="cheer", cam="kids")
say(B, "And I'm Bobo! B is for Bobo! Please help me find my blocks!", act="wave", cam="cu:bobo", face="happy")
ask(M, "Will you help Bobo? Shout yes!", act="point", cam="host", your_turn=True, gap_after=0.6)
say(KIDS, "Yes!", act="jump", also={B: "jump"}, cam="group", sfx="sparkle")
say(M, "Look! Nutty left us a treasure map! Ten blocks, ten places!", act="open", cam="host", sfx="chime")
say(O, "Let's go! Ready, steady...", act="squat", cam="kids")

# 3 ---------------------------------------------------------------- A: the apple orchard
letter(0, "orchard", "Go! Here we are in the apple orchard!", "in the apple trees", (0.09, 0.82), "a", "apple", "apple",
       "banana", LI)
say(M, "Let's pick apples! Jump up high! One, two, three!", act="jump", also=ALSO("jump"), cam="group", your_turn=True,
    gap_after=0.5)
say(ALL, "Jump! Jump! Jump! Apples for everyone!", act="jump", also=ALSO("jump"), cam="group", hold={LI: "apple"})
say(LI, "A is for apple! Crunch, crunch!", act="giggle", cam="kids", pic="apple")

# 4 ---------------------------------------------------------------- B: the beach
letter(1, "beach", "Wheee! We're at the beach!", "on the sand", (0.92, 0.84), "b", "ball", "ball", "fish", O)
say(M, "B is for ball! Let's play catch on the beach!", act="cheer", cam="host", pic="ball")
say(B, "Catch, Lily! B, b, ball!", act="cheer", cam="group", game={"type": "throw", "from": B, "to": LI, "bounces": 1, "at": 0.8},
    gap_after=1.4)
say(LI, "Got it! Your turn, Ollie! Bounce, bounce!", act="cheer", cam="group", game={"type": "throw", "from": LI, "to": O,
    "bounces": 2, "at": 0.9}, gap_after=1.4)
say(O, "B is for boat too! Look, a little boat!", act="point", cam="kids", pic="boat")

# 5 ---------------------------------------------------------------- C: the castle
letter(2, "castle", "Look! A big castle!", "near the castle", (0.08, 0.86), "c", "cat", "cat", "dog", LI)
say(M, "C is for castle too! Let's march like kings and queens!", act="march", also=ALSO("march"), cam="group",
    your_turn=True, gap_after=0.4)
say(ALL, "March, march, march to the castle! C, c, castle!", chant=True, act="march", also=ALSO("march"), cam="group")
say(B, "I'm King Bobo! Ah... ah... ah-CHOO!", act="sneeze", cam="cu:bobo", sfx="pop")
say(KIDS, "Hee hee! Bless you, King Bobo!", act="laugh", cam="kids")

# 6 ---------------------------------------------------------------- D: dinosaur valley
letter(3, "dino", "Stomp, stomp! Dinosaur valley!", "by the big rocks", (0.93, 0.83), "d", "dinosaur", "dinosaur", "cookie", O)
say(M, "Let's stomp like dinosaurs! Big stomps! Ready?", act="stomp", also=ALSO("stomp"), cam="group", your_turn=True,
    gap_after=0.4)
say(ALL, "Stomp! Stomp! Roooar! D, d, dinosaur!", act="stomp", also=ALSO("stomp"), cam="group", sfx="drumroll")
say(O, "Can you roar like a dinosaur? Roooar!", act="hands_up", cam="cu:ollie", your_turn=True, gap_after=1.2)

# 7 ---------------------------------------------------------------- E: the zoo
letter(4, "zoo", "Here we are at the zoo!", "by the fence", (0.09, 0.85), "e", "elephant", "elephant", "monkey", LI)
say(M, "Elephants are big and strong! Swing your trunk and stomp slowly!", act="wave", also=ALSO("wave"), cam="group",
    your_turn=True, gap_after=0.5)
say(ALL, "E, e, elephant! Stomp... stomp... toot!", act="stomp", also=ALSO("stomp"), cam="group", sfx="pop")
say(B, "And E is for egg! An egg in a nest!", act="point", cam="cu:bobo", pic="egg")
say(KIDS, "Yes! E is for egg!", act="yay", cam="kids")

# 8 ---------------------------------------------------------------- F: the forest pond + freeze dance
letter(5, "pond", "Splash! A pond in the forest!", "by the water", (0.92, 0.86), "f", "fish", "fish", "frog", O)
say(B, "Wait! F is for frog! Ribbit! Hop, hop!", act="frog", cam="cu:bobo", pic="frog", face="happy")
say(M, "Time for the letter freeze dance! Dance, and freeze when I say a letter!", act="dance", cam="host",
    chapter="Letter freeze dance", fx="stars")
for Lt, word, odd in (("A", "Apple", B), ("B", "Ball", None), ("C", "Cat", O)):
    say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", also=ALSO("dance"), cam="group",
        gap_after=0.3)
    also = {LI: "freeze", O: "freeze", B: "freeze"}
    if odd:
        also[odd] = "wobble"
    say(M, f"Freeze! {Lt}!", act="freeze", also=also, cam="group", card=Lt, sfx="pop", gap_after=0.8)
    say(ALL, f"{Lt} is for {word}!", act="freeze", cam="group", your_turn=True, gap_after=1.0)
    if odd == B:
        say(B, "Whoa! Wobble, wobble! I'm a wobbly apple!", act="wobble", cam="cu:bobo", face="happy")
    if odd == O:
        say(O, "Meow! I'm a wobbly cat!", act="wobble", cam="cu:ollie")
say(M, "Great dancing! Take a big breath. In... and out.", act="open", cam="host", gap_after=1.0)

# 9 ---------------------------------------------------------------- G: the savanna
letter(6, "savanna", "Whoa! A big sunny savanna!", "in the long grass", (0.08, 0.84), "g", "giraffe", "giraffe", "lion", LI)
say(M, "Giraffes are so tall! Stretch up tall like a giraffe!", act="hands_up", also=ALSO("hands_up"), cam="group",
    your_turn=True, gap_after=0.6)
say(ALL, "Stretch up high! G, g, giraffe! And touch your toes!", act="touch_toes", also=ALSO("touch_toes"), cam="group")
say(O, "I'm the tallest giraffe! Look at me!", act="hands_up", cam="cu:ollie", face="happy")

# 10 --------------------------------------------------------------- H: the balloon hill
letter(7, "hill", "Up, up, up! The top of the hill!", "on the hill", (0.93, 0.83), "h", "hat", "hat", "shoe", O)
say(B, "H is for hat! Look at my sun hat!", act="silly", cam="cu:bobo", hold={B: "hat"}, face="happy")
say(M, "And H is for hop! Hop, hop, hop!", act="bunny", also=ALSO("bunny"), cam="group", your_turn=True, gap_after=0.4)
say(ALL, "H, h, hop! Hop, hop, hop!", act="bunny", also=ALSO("bunny"), cam="group")
say(LI, "Look! Balloons! Let's pop them! H, h, hooray!", act="point", cam="kids",
    game={"type": "balloons", "colors": ["red", "yellow", "blue", "red"]}, gap_after=2.4)

# 11 --------------------------------------------------------------- I: the ice cream shop (sharing)
letter(8, "icecream", "Yum! An ice cream shop!", "near the counter", (0.08, 0.84), "i", "ice cream", "ice_cream", "pizza", LI)
say(B, "Ice cream! My tummy is rumbling! Rumble, rumble!", act="wobble", cam="cu:bobo", sfx="drumroll")
say(B, "But... there is only one ice cream.", act="think", cam="cu:bobo", face="sad", hold={B: "ice_cream"})
say(LI, "Bobo, can we share it?", act="open", cam="kids")
say(B, "Yes! Sharing is kind! A lick for you, and you, and you!", act="give", cam="group", face="happy",
    give={"from": B, "to": LI, "pic": "ice_cream"}, gap_after=0.8)
say(M, "Thank you, Bobo! That was very kind. I is for ice cream, and I is for... I love sharing!", act="thumbs_up", cam="host",
    fx="hearts")

# 12 --------------------------------------------------------------- J: the jungle + the ABC song
letter(9, "jungle", "Wow! The jungle!", "under the big leaves", (0.92, 0.85), "j", "jump", "block_j", "nap", O)
say(M, "J is for jump! Jump, jump, jump!", act="jump", also=ALSO("jump"), cam="group", your_turn=True, gap_after=0.4)
say(ALL, "J, j, jump! Jump, jump, jump!", act="jump", also=ALSO("jump"), cam="group")
say(O, "And J is for jelly! Wobble, wobble!", act="wobble", cam="cu:ollie", pic="jelly")
say(LI, "We found all ten blocks! A to J!", act="cheer", cam="kids", fx="stars")
say(M, "Let's sing our ABC song! Sing with us!", act="cheer", cam="host", chapter="ABC song", your_turn=True, gap_after=0.5)
for part in ("A, B, C, D, E, F, G!", "H, I, J, and dance with me!", "A, B, C, D, E, F, G!", "H, I, J, and dance with me!"):
    say(ALL, part, chant=True, act="dance", also=ALSO("dance"), cam="group")
say(ALL, "Hooray!", act="yay", also=ALSO("yay"), cam="group", sfx="success", gap_after=0.6)

# 13 --------------------------------------------------------------- home: Nutty says sorry, the big success, the twist
ask(M, "Let's take the blocks home! Look at the map!", act="point", cam="host", map=10, gap_after=1.4)
say(ALL, "Home again! Back to the classroom!", act="run", also=ALSO("run"), cam="group", place="classroom",
    chapter="Home again", sfx="sparkle", gap_after=0.4)
say(B, "Look who's here! It's Nutty!", act="point", cam="group", pic="squirrel")
say(M, "Nutty says: Sorry, Bobo! I just wanted to play with your blocks.", act="open", cam="host", pic="squirrel")
say(B, "That's okay, Nutty! We can play together! Sharing is fun!", act="hands_up", cam="cu:bobo", face="happy", fx="hearts")
ask(M, "Can you count the blocks with us? Ready?", act="count", cam="host", your_turn=True, gap_after=0.5)
say(M, "All ten blocks are home! A, B, C, D, E, F, G, H, I, J! Hooray!", act="cheer", also=ALSO("cheer"), cam="group",
    fx="confetti", sfx="success")
say(O, "Wait! What's in the treasure box?", act="point", cam="kids", pic="treasure_chest", sfx="chime")
say(B, "Another block! It's... K!", act="hands_up", cam="cu:bobo", face="surprised", pic="kite", card="K")
say(M, "K is for kite! Next time, we'll go on a new adventure, from K to T!", act="open", cam="host", teaser=True,
    pic="kite")
ask(M, "Can you say K? K, k, kite!", act="point", cam="host", your_turn=True, card="K k", gap_after=0.8)
say(KIDS, "K, k, kite! Yay!", act="yay", cam="kids")

# 14 --------------------------------------------------------------- calm recap + goodbye
say(M, "Now, let's sit and rest. Take a big breath in... and out.", act="open", cam="host", calm=True,
    chapter="Quiet time and goodbye", gap_after=1.6)
say(M, "Today we learned A for apple, B for ball, C for cat, D for dinosaur, and E for elephant.", act="count", cam="host",
    calm=True, card="A B C D E")
say(M, "F for fish, G for giraffe, H for hat, I for ice cream, and J for jump.", act="count", cam="host", calm=True,
    card="F G H I J")
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
    "learn": ["apple", "ball", "cat", "dinosaur", "elephant", "fish", "giraffe", "hat", "ice cream", "jump"],
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
