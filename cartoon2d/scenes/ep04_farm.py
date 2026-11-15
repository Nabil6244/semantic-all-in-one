"""Episode 4 - "Animals with Ms Molly & Bobo: Bobo's Farm Day" (about 19 min). Writes ep04_farm.json next to this file.

Spine: Bobo wants to be a farmer for a day, but he mixes up every animal sound ("cows say woof!"). The kids (and the child at
home) teach him the farm animals and their sounds: meet the animals, animal moves, baby animals, a sound-guessing game,
feeding time, counting animals, a farm song and an animal freeze dance. At the end Bobo gets every sound right.
Rules: ask -> pause -> answer -> praise; each animal's name and sound 3+ times; game / song / move break at least every
3 minutes; Bobo's mistakes corrected kindly; "Your turn!" pauses for the child to make the sounds and moves.
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
WORDS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]


def meet(pic, name, sound, who_answers, wrong, card):
    """Meet one animal: picture, name, Bobo's wrong sound, the kids correct him, everyone (and the child) makes the sound."""
    say(M, f"Look who's here! It's a {name}!", act="point", cam="host", pic=pic, card=card, sfx="pop", chapter=f"The {name}")
    ask(M, f"{name.capitalize()}. Can you say {name}?", act="point", cam="host")
    say(KIDS, f"{name.capitalize()}!", act="cheer", cam="kids")
    say(B, f"I know! The {name} says {wrong}!", act="silly", cam="cu:bobo")
    ask(M, f"Hmm. Friends, does a {name} say {wrong}?", act="think", cam="host")
    say(KIDS, f"Nooo! A {name} says {sound}!", act="laugh", cam="kids")
    say(B, f"Oopsie-daisy! {sound} {sound}! Silly Bobo!", act="silly", cam="cu:bobo", sfx="pop")
    say(M, f"Let's all say it like a {name}! Ready?", act="open", cam="host", your_turn=True, gap_after=0.4)
    say(ALL, f"{sound} {sound}!", act="cheer", cam="group", card=card)
    say(who_answers, f"Great {name} sounds!", act="thumbs_up", cam="kids" if who_answers in KIDS else "host")


# 1 ---------------------------------------------------------------- cold open: the hook
say(B, "Woof, woof! I'm a cow! Woof!", act="silly", cam="cu:bobo", place="playroom", chapter="Bobo the farmer", pic="cow",
    sfx="pop")
say(KIDS, "Hee hee hee! Cows don't say woof!", act="laugh", cam="kids")
say(B, "Then... quack? Oink? Cock-a-doodle-doo?", act="spin", cam="cu:bobo", face="surprised")
say(B, "Whoa! I'm so mixed up!", act="tumble", cam="group", sfx="drumroll")
say(M, "Oh, Bobo! Let's visit the farm, and learn all the animal sounds!", act="open", cam="host")
say(M, "Farm day!", act="yay", also={LI: "yay", O: "yay", B: "yay"}, cam="group",
    title="Farm Animals with\nMs Molly & Bobo!", sfx="success", gap_after=2.4)

# 2 ---------------------------------------------------------------- welcome + hello song
say(M, "Hi friends! I'm Miss Molly!", act="wave", cam="host", chapter="Hello song")
say(LI, "Hi! I'm Lily!", act="wave", cam="kids")
say(O, "And I'm Ollie!", act="cheer")
say(B, "And I'm Bobo the Bear! Today I'm Farmer Bobo!", act="wave", cam="cu:bobo", face="happy")
say(M, "Let's sing our hello song! Wave with us!", act="wave", also={LI: "wave", O: "wave", B: "wave"}, cam="group", gap_after=0.6)
say(ALL, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="group")
say(ALL, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="group", gap_after=0.8)
ask(M, "Are you ready to go to the farm?", act="point", cam="host")
say(KIDS, "Ready!", act="yay", cam="kids", sfx="sparkle")
say(M, "Let's gallop like horses all the way there! Giddy-up!", act="run", also={LI: "run", O: "run", B: "run"}, cam="group",
    chapter="Gallop to the farm")
say(ALL, "Giddy-up, giddy-up, off we go! Giddy-up, giddy-up, nice and slow!", chant=True, act="march", cam="group")
say(ALL, "Giddy-up, giddy-up, off we go! Giddy-up, giddy-up, nice and slow!", chant=True, act="march", cam="group", gap_after=0.7)
say(M, "Here we are at the farm!", act="open", also={LI: "cheer", O: "cheer", B: "cheer"}, cam="group", place="farm",
    sfx="sparkle", gap_after=0.8)
say(O, "Look! A big red barn!", act="point", cam="cu:ollie", face="surprised")
say(LI, "And a pond!", act="point", cam="kids")
say(B, "Where are the animals? Come out, animals!", act="hands_up", cam="cu:bobo")

# 3 ---------------------------------------------------------------- meet the animals
meet("cow", "cow", "Moo", LI, "woof", "MOO")
say(B, "The cow gives us milk! Moo! Thank you, cow!", act="wave", cam="cu:bobo", face="happy")
meet("pig", "pig", "Oink", O, "quack", "OINK")
say(O, "Pigs love to roll in the mud! Squish, squish!", act="giggle", cam="cu:ollie")
say(KIDS, "Hee hee! Muddy pig!", act="laugh", cam="kids")
meet("sheep", "sheep", "Baa", LI, "meow", "BAA")
say(LI, "The sheep is so fluffy! Like a cloud!", act="open", cam="kids")
meet("duck", "duck", "Quack", O, "moo", "QUACK")
say(B, "The duck is swimming in the pond! Splash, splash!", act="point", cam="cu:bobo")

# 4 ---------------------------------------------------------------- animal moves
say(M, "Animals move in different ways. Let's move like them!", act="cheer", cam="host", chapter="Move like the animals")
ask(M, "Can you waddle like a duck? Waddle, waddle!", act="march", cam="host", your_turn=True, gap_after=0.4)
say(ALL, "Quack, quack! Waddle, waddle!", act="march", cam="group", card="QUACK")
ask(M, "Can you hop like a frog? Ribbit!", act="frog", cam="host", pic="frog", your_turn=True, gap_after=0.4)
say(ALL, "Ribbit! Ribbit! Hop, hop!", act="frog", cam="group", card="RIBBIT")
ask(M, "Can you stomp like a big horse? Clip, clop!", act="stomp", cam="host", pic="horse", your_turn=True, gap_after=0.4)
say(ALL, "Neigh! Clip, clop, clip, clop!", act="stomp", cam="group", card="NEIGH")
ask(M, "Can you flap like a chicken? Flap your wings!", act="yay", cam="host", pic="chicken", your_turn=True, gap_after=0.4)
say(ALL, "Cluck, cluck, cluck! Flap, flap!", act="yay", cam="group", card="CLUCK")
say(B, "Look at me! I'm a flying bear!", act="bounce", cam="cu:bobo", face="happy")
say(KIDS, "Hee hee! Bears can't fly!", act="laugh", cam="kids")
ask(M, "And can you roll like a pig? Round and round!", act="spin", also={LI: "spin", O: "spin", B: "spin"}, cam="group",
    your_turn=True, gap_after=1.0)
say(B, "Oink! I'm dizzy! Oink, oink!", act="wobble", cam="cu:bobo", face="surprised")
say(KIDS, "Hee hee hee!", act="laugh", cam="kids")

# 5 ---------------------------------------------------------------- more animals
meet("horse", "horse", "Neigh", O, "baa", "NEIGH")
say(O, "I want to ride the horse! Giddy-up!", act="run", cam="group")
say(M, "What a fast horse, Ollie!", act="clap", cam="host", gap_after=1.0)
meet("chicken", "chicken", "Cluck", LI, "oink", "CLUCK")
say(LI, "The chicken lays eggs! One, two, three eggs!", act="count", cam="kids", card="3")
meet("dog", "dog", "Woof", O, "neigh", "WOOF")
say(B, "Wait! The dog says woof! I said the cow says woof!", act="think", cam="cu:bobo")
say(M, "That's right, Bobo! The DOG says woof. The cow says moo!", act="open", cam="host")
say(B, "I'm learning! Woof, woof, dog! Moo, moo, cow!", act="yay", cam="cu:bobo", face="happy", sfx="sparkle")

# 6 ---------------------------------------------------------------- play ball with the puppy
say(O, "Can we play with the puppy? Fetch!", act="cheer", cam="cu:ollie", hold={O: "ball"}, chapter="Play with the puppy")
say(M, "Yes! Throw the ball, and let's count the throws!", act="open", cam="host")
say(O, "One! Catch, Bobo!", act="talk", card="1", game={"type": "throw", "from": O, "to": B, "bounces": 1}, cam="group", gap_after=1.4)
say(B, "Two! Catch, Lily!", act="talk", card="2", game={"type": "throw", "from": B, "to": LI, "bounces": 1, "at": 0.8}, cam="group",
    gap_after=1.4)
say(LI, "Three! Bounce, bounce!", act="talk", card="3", game={"type": "dribble", "who": LI, "n": 3}, cam="kids", gap_after=0.6)
say(M, "The puppy wants a bone! Woof, woof!", act="point", cam="host", pic="puppy_bone", drop=[LI], sfx="pop")
say(B, "Big bear kick! Fetch, puppy!", act="kick", game={"type": "kick", "who": B, "to": 0.95, "at": 0.3}, cam="group", sfx="whoosh",
    gap_after=1.2)
say(KIDS, "Woof, woof! Good puppy!", act="clap", cam="kids")

# 7 ---------------------------------------------------------------- baby animals
say(M, "Shh! Look! Baby animals!", act="point", cam="host", chapter="Baby animals", face="surprised")
say(M, "A baby chicken is called a chick! Peep, peep!", act="open", cam="host", pic="chick", card="PEEP")
ask(M, "What does the little chick say?", act="think", cam="host")
say(KIDS, "Peep, peep!", act="cheer", cam="kids", card="PEEP")
say(M, "A baby sheep is called a lamb!", act="open", cam="host", pic="lamb")
ask(M, "What does the little lamb say? A soft little baa!", act="think", cam="host")
say(LI, "Baa, baa!", act="cheer", cam="kids", card="BAA")
say(M, "And a baby dog is called a puppy!", act="open", cam="host", pic="dog")
ask(M, "What does the puppy say?", act="think", cam="host")
say(O, "Woof, woof! A little woof!", act="cheer", cam="cu:ollie", card="WOOF")
say(B, "Baby animals are so cute! Aww!", act="open", cam="cu:bobo", face="happy")
say(M, "Babies need quiet. Let's whisper. Shh!", act="touch_head", cam="host", gap_after=1.2)
say(KIDS, "Shh!", act="touch_toes", cam="kids", gap_after=1.0)

# 8 ---------------------------------------------------------------- guess the sound game
say(M, "Let's play a guessing game! Listen to the sound, and guess the animal!", act="cheer", cam="host",
    chapter="Guess the animal sound", sfx="chime")
for sound, name, pic, who in (("Oink, oink!", "pig", "pig", B), ("Baa, baa!", "sheep", "sheep", LI),
                              ("Neigh!", "horse", "horse", O), ("Quack, quack!", "duck", "duck", B),
                              ("Ribbit, ribbit!", "frog", "frog", LI)):
    say(who, sound, act="talk", cam="cu:bobo" if who == B else "kids")
    ask(M, "Who says that?", act="think", cam="host")
    say(KIDS if who != LI else [O, B], f"A {name}!", act="cheer", cam="group", pic=pic, sfx="pop")
    say(M, f"Yes! The {name}!", act="thumbs_up", cam="host")
say(B, "I guessed them all! I'm a real farmer now!", act="yay", cam="cu:bobo", face="happy", sfx="success")

# 9 ---------------------------------------------------------------- feeding time + counting animals
say(M, "It's feeding time! The animals are hungry!", act="open", cam="host", chapter="Feeding time")
say(B, "I'll feed them! Here, chickens! Cluck, cluck!", act="give", cam="cu:bobo", pic="chicken")
ask(M, "Bobo is feeding the chickens. Let's count them!", act="count", cam="host", gap_after=0.4)
for i in range(1, 6):
    say(ALL, f"{WORDS[i - 1]}!", act="count", card=str(i), cam="group", gap_after=0.35)
say(M, "Five chickens! Cluck, cluck!", act="cheer", cam="host", card="5")
say(LI, "And the cows! One, two, three cows! Moo!", act="count", cam="kids", pic="cow", card="3")
say(O, "And one big horse! Neigh!", act="point", cam="cu:ollie", pic="horse", card="1")
ask(M, "What do you think the cow likes to eat?", act="think", cam="host")
say(B, "Honey!", act="silly", cam="cu:bobo", pic="honey")
say(KIDS, "Nooo! Cows eat grass!", act="laugh", cam="kids")
say(B, "Hee hee! Bears eat honey. Cows eat grass! Munch, munch!", act="laugh", cam="cu:bobo")

# 9b --------------------------------------------------------------- Animal Simon Says
say(M, "Let's play Simon Says, farm style! Do what Simon says!", act="cheer", cam="host", chapter="Animal Simon Says", sfx="chime")
say(M, "Simon says, flap like a chicken!", act="yay", also={LI: "yay", O: "yay", B: "yay"}, cam="group", card="CLUCK",
    your_turn=True, gap_after=1.6)
say(M, "Simon says, hop like a frog!", act="frog", also={LI: "frog", O: "frog", B: "frog"}, cam="group", card="RIBBIT",
    your_turn=True, gap_after=1.6)
say(M, "Simon says, stomp like a horse!", act="stomp", also={LI: "stomp", O: "stomp", B: "stomp"}, cam="group", card="NEIGH",
    your_turn=True, gap_after=1.6)
say(M, "Now moo like a cow!", act="point", cam="host", gap_after=0.8)
say(B, "Moo! Moo!", act="cheer", cam="cu:bobo", face="happy")
say(KIDS, "Bobo! Simon didn't say!", act="laugh", cam="kids")
say(B, "Oopsie-daisy! Silly Bobo! Moo!", act="silly", cam="cu:bobo", sfx="pop")
say(M, "Simon says, sleep like a sleepy sheep. Shh!", act="touch_head", also={LI: "touch_head", O: "touch_head", B: "touch_head"},
    cam="group", your_turn=True, gap_after=1.8)
say(M, "Simon says, wake up and jump like a happy puppy!", act="jump", also={LI: "jump", O: "jump", B: "jump"}, cam="group",
    card="WOOF", your_turn=True, gap_after=1.2)
say(M, "Great listening, little animals!", act="thumbs_up", cam="host", sfx="success")

# 9c --------------------------------------------------------------- who is hiding?
say(M, "Uh oh! Where did Bobo go?", act="think", cam="host", chapter="Who is hiding?", game={"type": "hide", "who": B},
    face="surprised", gap_after=0.8)
say(B, "Moo! Moo!", act="talk", cam="group")
ask(M, "Hmm. Is that a cow hiding behind the box?", act="think", cam="host")
say(B, "Oink! Oink! Quack, quack!", act="talk", cam="group")
say(O, "A cow that says oink and quack? That's not a cow!", act="laugh", cam="cu:ollie")
ask(M, "Who do you think is hiding, friends?", act="point", cam="group")
say(KIDS, "It's Bobo! We see your ears!", act="point", cam="kids")
say(B, "You found me! Hee hee! I'm a moo-oink-quack bear!", act="yay", cam="cu:bobo", game={"type": "found", "who": B},
    face="happy", sfx="sparkle")
say(KIDS, "Hee hee hee!", act="laugh", cam="kids")
say(LI, "My turn to hide! Guess my animal!", act="cheer", cam="kids", game={"type": "hide", "who": LI}, gap_after=0.8)
say(LI, "Baa! Baa!", act="talk", cam="group")
ask(M, "What animal says baa?", act="think", cam="host")
say([O, B], "A sheep!", act="cheer", cam="group", pic="sheep")
say(LI, "Yes! I'm a fluffy sheep! Baa!", act="yay", cam="kids", game={"type": "found", "who": LI}, face="happy", sfx="sparkle")

# 10 --------------------------------------------------------------- the farm song
say(M, "Let's sing our farm song! Clap and make the sounds!", act="clap", also={LI: "clap", O: "clap", B: "clap"}, cam="group",
    chapter="Farm song", gap_after=0.6)
SONG1 = "The cow on the farm says moo, moo, moo! The duck on the farm says quack, quack, quack!"
SONG2 = "The pig on the farm says oink, oink, oink! And we all say hello to you!"
CARDS = {"moo,": "MOO", "quack,": "QUACK", "oink,": "OINK", "moo!": "MOO", "quack!": "QUACK", "oink!": "OINK"}
for rep in range(2):
    say(ALL, SONG1, chant=True, act="beatclap", cam="group", word_cards=CARDS, gap_after=0.4)
    say(ALL, SONG2, chant=True, act="beatclap" if rep == 0 else "dance", cam="group", word_cards=CARDS, gap_after=0.8)
    if rep == 0:
        say(B, "Again! Again! I love the farm song!", act="jump", cam="cu:bobo", gap_after=0.5)
say(KIDS, "Yay!", act="yay", also={B: "yay", M: "cheer"}, cam="group", sfx="success")

# 11 --------------------------------------------------------------- animal freeze dance
say(M, "Now the animal freeze dance! Dance, and when I say an animal, freeze and make its sound!", act="cheer", cam="host",
    chapter="Animal freeze dance")
for animal, sound, card, odd in (("Cow", "Moo!", "MOO", B), ("Duck", "Quack!", "QUACK", None), ("Sheep", "Baa!", "BAA", O),
                                 ("Dog", "Woof!", "WOOF", None)):
    say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", cam="group", gap_after=0.3)
    also = {LI: "freeze", O: "freeze", B: "freeze"}
    if odd:
        also[odd] = "wobble"
    say(M, f"Freeze! {animal}!", act="freeze", also=also, cam="group", card=card, sfx="pop", gap_after=0.9)
    say(ALL, sound, act="freeze", cam="group", your_turn=True, gap_after=1.2)
    if odd == B:
        say(B, "Moo! I'm a wobbly cow!", act="wobble", cam="cu:bobo", face="happy")
        say(KIDS, "Hee hee hee!", act="laugh", cam="kids")
    if odd == O:
        say(O, "Baa! Whoa! Wobble, wobble!", act="wobble", cam="cu:ollie")
say(M, "Great dancing, little animals! Take a big breath. In, and out.", act="open", cam="host", gap_after=1.2)

# 12 --------------------------------------------------------------- Farmer Bobo gets it right
say(M, "Farmer Bobo, are you ready? Let's see if you know all the sounds now!", act="open", cam="host",
    chapter="Farmer Bobo's big test")
for pic, name, sound in (("cow", "cow", "Moo, moo"), ("pig", "pig", "Oink, oink"), ("duck", "duck", "Quack, quack"),
                         ("dog", "dog", "Woof, woof"), ("sheep", "sheep", "Baa, baa")):
    ask(M, f"What does the {name} say?", act="point", cam="host", pic=pic, gap_after=1.2)
    say(B, f"{sound}!", act="cheer", cam="cu:bobo", face="happy", sfx="ding_3")
say(KIDS, "Hooray! Bobo got them all right!", act="yay", also={M: "cheer"}, cam="group", sfx="success")
say(B, "Thank you, friends! You taught me all the animal sounds!", act="thumbs_up", cam="cu:bobo", face="happy")
say(B, "Party balloons for the animals! Pop, pop, pop!", act="bounce", cam="group",
    game={"type": "balloons", "colors": ["red", "yellow", "blue"]}, face="happy", gap_after=2.6)

# 13 --------------------------------------------------------------- quiz + goodbye
say(M, "Let's play a quick farm quiz!", act="cheer", cam="host", chapter="Farm quiz and goodbye", sfx="chime")
ask(M, "Which animal gives us milk?", act="think", cam="host")
say(LI, "The cow!", act="cheer", cam="kids", pic="cow")
ask(M, "What is a baby chicken called?", act="think", cam="host")
say(O, "A chick! Peep, peep!", act="cheer", cam="cu:ollie", pic="chick")
ask(M, "And who says woof?", act="point", cam="group")
say(B, "The cow!", act="silly", cam="cu:bobo")
say(KIDS, "Nooo! The dog!", act="laugh", cam="kids", pic="dog")
say(B, "Hee hee! I'm joking! The dog says woof!", act="laugh", cam="cu:bobo")
say(M, "You know all the farm animals! Great job, everybody!", act="thumbs_up", cam="host", sfx="success")
say(M, "Next time, we'll learn our ABCs with Bobo! A, B, C!", act="count", cam="host")
say(B, "ABC? Is B for Bobo?", act="think", cam="cu:bobo")
say(KIDS, "Yes! B is for Bobo!", act="yay", cam="kids")
say(M, "Let's sing our goodbye song!", act="wave", also={LI: "wave", O: "wave", B: "wave"}, cam="group", gap_after=0.6)
say(ALL, "Bye bye, bye bye, see you soon! Bye bye, bye bye, toodle-oo!", chant=True, act="wave", cam="group")
say(ALL, "Bye bye, bye bye, see you soon! Bye bye, bye bye, toodle-oo!", chant=True, act="wave", cam="group", gap_after=0.6)
say(ALL, "Bye bye, friends! Moo!", act="wave", cam="group", endcard="Bye bye!\nSee you next time!", sfx="success")


script = {
    "voices": {
        M: {"voice": "en-US-AvaNeural", "rate": "-4%", "pitch": "+6Hz"},
        LI: {"voice": "en-US-AnaNeural", "rate": "+0%", "pitch": "+0Hz"},
        O: {"voice": "en-US-AnaNeural", "rate": "+8%", "pitch": "-14Hz"},
        B: {"voice": "en-US-GuyNeural", "rate": "-4%", "pitch": "+14Hz"},
    },
    "bpm": 104, "lead_in": 0.6, "gap": 0.45, "tail": 4.0, "lines": L,
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1))
print(len(L), "lines ->", out)
