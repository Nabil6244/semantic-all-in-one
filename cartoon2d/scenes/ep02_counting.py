"""Episode 2 - "Counting with Ms Molly & Bobo: Bobo's Big Bounce" (about 19 min). Writes ep02_counting.json next to this file.

Spine: Bobo wants to bounce 10 times on the trampoline for the Big Bounce, but he can only count "1, 2, 7, 100!".
The kids (and the child at home) teach him 1-10 through games: jumps, trampoline bounces, catch, dribbling, balloon pop,
animal hops, a counting song, hide and seek, a blast-off countdown - then Bobo does the Big Bounce, counting right.
Rules (docs/cartoon2d/EP01_PLAN.md): ask -> pause -> answer -> praise; every number shown as a card and said 3+ times;
a game, song or movement break at least every 3 minutes; Bobo's mistakes are corrected kindly; "Your turn!" pauses.
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
NUM_CARDS = {w.lower(): str(i + 1) for i, w in enumerate(WORDS)}


def count_along(n, who=KIDS, bounce=None, act="count", start=1, gap=0.35, **extra):
    """One line per number: the number card pops, and whoever bounces does one bounce per number."""
    for i in range(start, n + 1):
        k = dict(extra)
        if bounce:
            k["also"] = {b: "bounce" for b in bounce}
        say(who, f"{WORDS[i - 1]}!", act=act, card=str(i), gap_after=gap, **k)


# 1 ---------------------------------------------------------------- cold open: the hook (Bobo can't count)
say(B, "Look at me! I'm the bounciest bear in the world!", act="bounce", cam="cu:bobo", place="playroom",
    game={"type": "trampoline", "who": B}, chapter="Bobo's big bounce", sfx="boing")
say(B, "One, two... seven... one hundred!", act="bounce", cam="group")
say(B, "Whoa! Whoa! Oopsie-daisy!", act="tumble", cam="group", sfx="drumroll")
say(KIDS, "Hee hee hee! Silly Bobo!", act="laugh", cam="kids")
say(M, "Bobo! One, two, seven, one hundred? That's not how we count!", act="open", cam="host")
say(B, "Hmm. Is it not?", act="think", cam="cu:bobo", face="sad")
say(M, "Let's all learn to count, and help Bobo!", act="cheer", also={LI: "cheer", O: "cheer", B: "cheer"}, cam="group",
    title="Counting with\nMs Molly & Bobo!", sfx="success", gap_after=2.4)

# 2 ---------------------------------------------------------------- welcome + hello song
say(M, "Hi friends! I'm Miss Molly!", act="wave", cam="host", chapter="Hello song")
say(LI, "Hi! I'm Lily!", act="wave", cam="kids")
say(O, "And I'm Ollie!", act="cheer")
say(B, "And I'm Bobo the Bear! The bounciest bear!", act="wave", cam="cu:bobo")
say(M, "Let's sing our hello song! Wave with us!", act="wave", also={LI: "wave", O: "wave", B: "wave"}, cam="group", gap_after=0.6)
say(ALL, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="group")
say(ALL, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="group", gap_after=0.8)
say(M, "Yay! Hello, friends!", act="yay", also={LI: "yay", O: "yay", B: "yay"}, sfx="sparkle")
say(B, "Miss Molly, today is the Big Bounce!", act="jump", cam="cu:bobo", face="happy")
ask(M, "The Big Bounce? What's that, Bobo?", act="open", cam="host")
say(B, "I want to bounce ten times on my trampoline! But I can't count to ten.", act="think", cam="cu:bobo", face="sad")
say(LI, "Don't worry, Bobo! We can teach you!", act="open", cam="kids")
say(O, "Counting is easy peasy!", act="thumbs_up", cam="cu:ollie")
ask(M, "Will you help Bobo count too? Are you ready?", act="point", cam="host")
say(KIDS, "Ready!", act="yay", cam="kids", sfx="sparkle")
say(B, "Ready, ready, ready!", act="bounce", cam="cu:bobo")

# 3 ---------------------------------------------------------------- 1, 2, 3 with jumps
say(M, "Let's start with one, two, three!", act="count", cam="host", chapter="Jump and count 1 2 3", card="1")
say(M, "Watch me. One jump!", act="jump", cam="host", card="1", sfx="boing")
say(M, "Two jumps! Jump, jump!", act="jump", cam="host", card="2")
say(M, "Three jumps! Jump, jump, jump!", act="jump", cam="host", card="3")
ask(M, "Now you! Stand up and jump three times with us!", act="point", cam="group", your_turn=True, gap_after=0.6)
count_along(3, who=ALL, act="jump", cam="group")
say(M, "Great jumping! One, two, three!", act="clap", cam="host", sfx="success")
say(B, "One, two, three! I did it!", act="yay", cam="cu:bobo", face="happy")
say(LI, "Good job, Bobo!", act="thumbs_up", cam="kids")
say(B, "Can I bounce now? One, two, three, banana!", act="silly", cam="cu:bobo", pic="banana")
say(KIDS, "Nooo! Banana is not a number!", act="laugh", cam="kids")
say(B, "Oopsie-daisy! Silly Bobo!", act="silly", cam="cu:bobo", sfx="pop")
ask(M, "What comes after three, friends?", act="think", cam="host")
say(KIDS, "Four!", act="cheer", cam="kids", card="4")
say(M, "Yes! Four! And then five!", act="count", cam="host", card="5")

# 4 ---------------------------------------------------------------- trampoline 1-5
say(M, "Bobo, jump on your trampoline. Let's count your bounces to five!", act="point", cam="group",
    chapter="Trampoline counting to 5")
say(B, "Okay! Here I go!", act="cheer", cam="cu:bobo")
count_along(5, who=KIDS, bounce=[B], act="count", cam="group")
say(B, "Five bounces! Wheee!", act="bounce", cam="cu:bobo", face="happy", sfx="success")
say(M, "Great counting! One, two, three, four, five!", act="count", cam="host", card="5")
ask(M, "Can you bounce like Bobo? Bounce five times!", act="bounce", cam="host", your_turn=True, gap_after=0.5)
count_along(5, who=ALL, bounce=[B, M], act="count", cam="group")
say(KIDS, "Yay! We bounced five times!", act="yay", cam="kids", sfx="sparkle")
say(B, "Now I'll do ten! One, two, three, four, five, six...", act="bounce", cam="cu:bobo")
say(B, "Um... seven... eleven... twenty?", act="think", cam="cu:bobo", face="sad")
say(O, "Oh no! You got mixed up, Bobo!", act="open", cam="cu:ollie")
say(M, "That's okay, Bobo. Learning takes practice! Let's play some counting games.", act="open", cam="host")
say(B, "Counting games? I love games!", act="yay", cam="cu:bobo", face="happy", game={"type": "trampoline_off", "who": B})

# 5 ---------------------------------------------------------------- catch: count the throws (garden)
say(M, "Let's go to the garden and play catch!", act="point", cam="host", chapter="Catch and count")
say(M, "March with us! March, march, march!", act="march", also={LI: "march", O: "march", B: "march"}, cam="group")
say(ALL, "March, march, march! March, march, march!", chant=True, act="march", cam="group", gap_after=0.7)
say(M, "Here we are in the garden!", act="open", also={LI: "cheer", O: "cheer", B: "cheer"}, cam="group", place="garden",
    sfx="sparkle", hold={M: "ball"}, gap_after=0.8)
say(M, "I have a ball! Let's count every catch. Ready?", act="talk", cam="host")
say(KIDS, "Ready!", act="cheer", cam="kids")
say(M, "One! Catch, Ollie!", act="talk", card="1", game={"type": "throw", "from": M, "to": O, "bounces": 1}, cam="group", gap_after=1.3)
say(O, "Got it! Two! Catch, Lily!", act="talk", card="2", game={"type": "throw", "from": O, "to": LI, "bounces": 0, "at": 0.9},
    cam="group", gap_after=1.0)
say(LI, "Got it! Three! Catch, Bobo!", act="talk", card="3", game={"type": "throw", "from": LI, "to": B, "bounces": 1, "at": 1.0},
    cam="group", gap_after=1.3)
say(B, "I got it! Four! Back to you, Miss Molly!", act="talk", card="4", face="happy",
    game={"type": "throw", "from": B, "to": M, "bounces": 1, "at": 1.4}, cam="group", gap_after=1.3)
say(M, "Five! We caught it five times!", act="cheer", card="5", cam="host", sfx="success")
say(KIDS, "One, two, three, four, five!", act="count", cam="kids")
say(M, "Now Lily will bounce the ball. Count the bounces!", act="point", cam="group",
    give={"from": M, "to": LI, "pic": "ball"}, gap_after=0.8)
say(LI, "One!", act="talk", card="1", game={"type": "dribble", "who": LI, "n": 1}, cam="kids", gap_after=0.4)
say(LI, "Two!", act="talk", card="2", game={"type": "dribble", "who": LI, "n": 1}, cam="kids", gap_after=0.4)
say(LI, "Three!", act="talk", card="3", game={"type": "dribble", "who": LI, "n": 1}, cam="kids", gap_after=0.4)
say(LI, "Four!", act="talk", card="4", game={"type": "dribble", "who": LI, "n": 1}, cam="kids", gap_after=0.4)
say(LI, "Five!", act="talk", card="5", game={"type": "dribble", "who": LI, "n": 1}, cam="kids", gap_after=0.4)
say(LI, "Six!", act="talk", card="6", game={"type": "dribble", "who": LI, "n": 1}, cam="kids", gap_after=0.6)
ask(M, "Wow! How many bounces was that?", act="think", cam="host")
say(O, "Six!", act="yay", cam="cu:ollie", card="6")
say(M, "Six! Great counting!", act="thumbs_up", cam="host")
say(B, "My turn! I'm going to kick it!", act="cheer", cam="cu:bobo", drop=[LI])
say(B, "Big bear kick!", act="kick", game={"type": "kick", "who": B, "to": O, "at": 0.3}, cam="group", sfx="whoosh", gap_after=1.2)
say(O, "Whoa! It went so far!", act="open", cam="cu:ollie", face="surprised")
ask(M, "How many hops did the ball do?", act="think", cam="host")
say(KIDS, "Three!", act="cheer", cam="kids", card="3")
say(B, "Three hops! I counted too!", act="yay", cam="cu:bobo")

# 6 ---------------------------------------------------------------- 6 to 10
say(M, "Bobo, you know one to five. Now let's learn six, seven, eight, nine, ten!", act="count", cam="host",
    chapter="Learn 6 to 10", card="10")
say(M, "Six!", act="count", cam="host", card="6", gap_after=0.5)
ask(M, "Say six!", act="point", cam="host", gap_after=1.6)
say(KIDS, "Six!", act="cheer", cam="kids")
say(M, "Seven!", act="count", cam="host", card="7", gap_after=0.5)
ask(M, "Say seven!", act="point", cam="host", gap_after=1.6)
say(KIDS, "Seven!", act="cheer", cam="kids")
say(M, "Eight!", act="count", cam="host", card="8", gap_after=0.5)
ask(M, "Say eight!", act="point", cam="host", gap_after=1.6)
say(KIDS, "Eight!", act="cheer", cam="kids")
say(B, "Eight? Like a snowman! Two circles!", act="silly", cam="cu:bobo", card="8")
say(KIDS, "Hee hee! Yes!", act="giggle", cam="kids")
say(M, "Nine!", act="count", cam="host", card="9", gap_after=0.5)
ask(M, "Say nine!", act="point", cam="host", gap_after=1.6)
say(KIDS, "Nine!", act="cheer", cam="kids")
say(M, "And ten!", act="count", cam="host", card="10", gap_after=0.5)
ask(M, "Say ten! Nice and loud!", act="point", cam="host", gap_after=1.6)
say(KIDS, "Ten!", act="yay", cam="kids", sfx="sparkle")
say(B, "TEN! That's the Big Bounce number!", act="jump", cam="cu:bobo", face="happy")
say(M, "Let's count all the way to ten with our fingers. Hold up your hands!", act="hands_up", cam="host",
    your_turn=True, gap_after=0.6)
count_along(10, who=ALL, act="count", cam="group", gap=0.45)
say(M, "Ten fingers! Wiggle, wiggle!", act="open", cam="host", sfx="success")

# 7 ---------------------------------------------------------------- balloon pop counting
say(O, "Look! Balloons!", act="point", cam="cu:ollie", chapter="Balloon pop", face="surprised")
say(M, "Let's pop them and count! Ready?", act="cheer", cam="host")
say(M, "Pop, pop, pop!", act="point", cam="group", game={"type": "balloons", "colors": ["red", "blue", "yellow"]}, gap_after=1.6)
say(KIDS, "One, two, three!", act="count", cam="kids", card="3")
say(M, "Three balloons! More are coming!", act="open", cam="host")
say(B, "Pop, pop, pop, pop, pop!", act="yay", cam="group",
    game={"type": "balloons", "colors": ["yellow", "red", "blue", "red", "yellow"]}, gap_after=3.6)
ask(M, "How many balloons did Bobo pop?", act="think", cam="host")
say(LI, "Five!", act="cheer", cam="kids", card="5")
say(B, "Five balloons! Pop, pop!", act="bounce", cam="cu:bobo", face="happy")
ask(M, "Three balloons and five balloons. Wow! That's a lot of balloons!", act="open", cam="host")

# 8 ---------------------------------------------------------------- animal moves counting
say(M, "Now let's count with animal moves!", act="cheer", cam="host", chapter="Animal moves")
ask(M, "Can you hop like a bunny? Two hops!", act="bunny", cam="host", your_turn=True, gap_after=0.4)
say(ALL, "One! Two!", act="bunny", cam="group", card="2")
say(B, "Boing, boing! I'm a bunny bear!", act="bunny", cam="cu:bobo", face="happy")
ask(M, "Jump like a frog! Three jumps! Ribbit!", act="frog", cam="host", your_turn=True, gap_after=0.4)
say(ALL, "One! Two! Three!", act="frog", cam="group", card="3")
say(O, "Ribbit, ribbit!", act="frog", cam="cu:ollie")
ask(M, "Bounce like a kangaroo! Four big bounces!", act="kangaroo", cam="host", your_turn=True, gap_after=0.4)
say(ALL, "One! Two! Three! Four!", act="kangaroo", cam="group", card="4")
ask(M, "Stomp like a big bear! Five stomps!", act="stomp", cam="host", your_turn=True, gap_after=0.4)
say(ALL, "One! Two! Three! Four! Five!", act="stomp", cam="group", card="5")
say(B, "That's my favourite! Bear stomps!", act="stomp", cam="cu:bobo", face="happy")
say(KIDS, "Hee hee!", act="giggle", cam="kids")
say(M, "Now spin around like a spinning top! One spin!", act="spin", also={LI: "spin", O: "spin", B: "spin"}, cam="group",
    card="1", gap_after=0.8)
say(B, "Whoa! I'm dizzy!", act="wobble", cam="cu:bobo", face="surprised")
say(KIDS, "Hee hee hee!", act="laugh", cam="kids")

# 8b --------------------------------------------------------------- Bobo's snack: count and take away
say(B, "All this counting makes me hungry! Snack time!", act="silly", cam="cu:bobo", chapter="Bobo's snack", face="happy")
say(M, "Let's count Bobo's snack. Look! Apples!", act="point", cam="host", pic="apple", sfx="pop")
ask(M, "Bobo has three apples. Let's count them!", act="count", cam="host", gap_after=0.4)
count_along(3, who=ALL, act="count", cam="group")
say(B, "Yum! I'll eat one! Munch, munch, munch!", act="giggle", cam="cu:bobo", face="happy")
ask(M, "Bobo had three apples. He ate one. How many are left?", act="think", cam="host")
say(LI, "Two apples!", act="cheer", cam="kids", card="2")
say(M, "Yes! Two apples left! Great thinking, Lily!", act="thumbs_up", cam="host")
say(M, "Now look! Strawberries!", act="point", cam="host", pic="strawberry", sfx="pop")
ask(M, "There are five strawberries. Count with me!", act="count", cam="host", gap_after=0.4)
count_along(5, who=ALL, act="count", cam="group")
say(B, "I'm a hungry bear! I'll eat two! Munch, munch!", act="silly", cam="cu:bobo")
ask(M, "Five strawberries, and Bobo ate two. How many are left? Use your fingers!", act="hands_up", cam="host", gap_after=2.6)
say(O, "Three! Three strawberries!", act="yay", cam="cu:ollie", card="3")
say(M, "Three! Wow, Ollie! You're a counting star!", act="thumbs_up", cam="host", sfx="sparkle")
say(B, "And I have honey for later! One, two, three, four honey pots!", act="count", cam="cu:bobo", pic="honey", card="4")
say(KIDS, "Hee hee! Bobo loves honey!", act="giggle", cam="kids")

# 9 ---------------------------------------------------------------- counting song
say(M, "Let's sing our counting song! Clap with me!", act="clap", also={LI: "clap", O: "clap", B: "clap"}, cam="group",
    chapter="Counting song", gap_after=0.6)
SONG = "One, two, three, four, five! Jump up high, we're all alive! Six, seven, eight, nine, ten! Let's all count it once again!"
say(ALL, SONG, chant=True, act="beatclap", cam="group", word_cards=NUM_CARDS)
say(M, "Again! Sing with us!", act="cheer", cam="host", gap_after=0.5)
say(ALL, SONG, chant=True, act="beatclap", cam="group", word_cards=NUM_CARDS, gap_after=0.8)
say(B, "One more time! And jump!", act="jump", cam="cu:bobo", gap_after=0.5)
say(ALL, SONG, chant=True, act="dance", cam="group", word_cards=NUM_CARDS, gap_after=0.8)
say(KIDS, "Yay!", act="yay", also={B: "yay", M: "cheer"}, cam="group", sfx="success")

# 9b --------------------------------------------------------------- number freeze dance
say(M, "Now it's the number freeze dance! Dance, and when I say a number, freeze and jump that many times!", act="cheer",
    cam="host", chapter="Number freeze dance")
for n, odd in ((2, None), (3, B), (4, O), (5, None)):
    say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", cam="group", gap_after=0.3)
    also = {LI: "freeze", O: "freeze", B: "freeze"}
    if odd:
        also[odd] = "wobble"
    say(M, f"Freeze! {WORDS[n - 1]}!", act="freeze", also=also, cam="group", card=str(n), sfx="pop", gap_after=1.0)
    if odd == B:
        say(B, "Oh! I can't freeze! I'm a wobbly bear!", act="wobble", cam="cu:bobo", face="happy")
        say(KIDS, "Hee hee hee!", act="laugh", cam="kids")
    if odd == O:
        say(O, "Whoa! Wobble, wobble!", act="wobble", cam="cu:ollie")
    say(M, f"Now jump {WORDS[n - 1].lower()} times!", act="point", cam="group", your_turn=True, gap_after=0.3)
    count_along(n, who=ALL, act="jump", cam="group")
say(M, "Great dancing and jumping! Now take a big breath. In, and out.", act="open", cam="host", gap_after=1.2)

# 10 --------------------------------------------------------------- hide and seek: count to ten
say(B, "Let's play hide and seek! I'll hide. You count to ten!", act="cheer", cam="cu:bobo", chapter="Hide and seek")
say(M, "Okay! Close your eyes and count with us!", act="open", cam="host", game={"type": "hide", "who": B}, gap_after=0.5)
count_along(10, who=[M, LI, O], act="talk", cam="group", gap=0.5)
say([LI, O], "Ready or not, here we come!", act="cheer", cam="kids", sfx="chime")
ask(M, "Where is Bobo? Can you see him?", act="think", cam="group")
say(O, "Is he behind the tree?", act="point", cam="cu:ollie")
say(LI, "No! Look! I see two ears!", act="point", cam="kids", face="surprised")
ask(M, "How many ears can you see, friends?", act="think", cam="group")
say(KIDS, "Two!", act="cheer", cam="kids", card="2")
say(KIDS, "Found you, Bobo!", act="point", cam="group")
say(B, "You found me! Hee hee!", act="yay", cam="cu:bobo", game={"type": "found", "who": B}, face="happy", sfx="sparkle")
say(O, "My turn to hide! Count to five!", act="cheer", cam="cu:ollie")
say(M, "Okay, Ollie! Hide!", act="open", cam="host", game={"type": "hide", "who": O}, gap_after=0.5)
count_along(5, who=[M, LI, B], act="talk", cam="group", gap=0.5)
say(B, "Ready or not! Hmm... where is Ollie?", act="think", cam="cu:bobo")
say(B, "Is he in the sky?", act="point", cam="cu:bobo")
say(KIDS, "Nooo!", act="laugh", cam="kids")
ask(M, "Friends, where is Ollie? Can you see his hair?", act="think", cam="group")
say(LI, "Behind the box! Found you, Ollie!", act="point", cam="kids")
say(O, "You found me!", act="yay", cam="cu:ollie", game={"type": "found", "who": O}, face="happy", sfx="sparkle")

# 11 --------------------------------------------------------------- blast-off countdown
say(M, "Let's go back inside. It's time for something exciting!", act="point", cam="host", chapter="Blast off countdown")
say(M, "Here we are!", act="open", also={LI: "cheer", O: "cheer", B: "cheer"}, cam="group", place="playroom", sfx="sparkle",
    gap_after=0.8)
say(M, "Let's be rockets! We count backwards from ten. Then we blast off!", act="hands_up", cam="host")
say(B, "Backwards? Like walking backwards?", act="think", cam="cu:bobo")
say(M, "Hee hee! No, Bobo. Ten, nine, eight... all the way down to one!", act="count", cam="host", card="10")
say(M, "Squat down low like a rocket. Ready?", act="squat", also={LI: "squat", O: "squat", B: "squat"}, cam="group", your_turn=True,
    gap_after=0.5)
for i in range(10, 0, -1):
    say(ALL, f"{WORDS[i - 1]}!", act="squat", card=str(i), cam="group", gap_after=0.35)
say(ALL, "Blast off!", act="jump", cam="group", sfx="success", face="happy")
say(KIDS, "Whoosh! We're flying!", act="hands_up", cam="kids", sfx="whoosh")
say(B, "Zoom! I'm a rocket bear!", act="run", run={B: 0.95}, cam="group", face="happy")
say(O, "Me too! Zoom!", act="run", run={O: 0.72}, cam="group")
say(M, "Come back, rockets! Time to land!", act="open", cam="host", go={B: "home", O: "home"}, gap_after=1.6)

# 12 --------------------------------------------------------------- the Big Bounce
say(M, "Bobo, I think you are ready. Is it time for the Big Bounce?", act="open", cam="host", chapter="The Big Bounce")
say(B, "Yes! I'm ready! I can count to ten now!", act="yay", cam="cu:bobo", face="happy", game={"type": "trampoline", "who": B})
say(M, "Everybody, count Bobo's bounces with us!", act="point", cam="group", your_turn=True, gap_after=0.4)
count_along(10, who=[M, LI, O], bounce=[B], act="count", cam="group", gap=0.3)
say(B, "TEN! I did it! The Big Bounce!", act="bounce", cam="cu:bobo", face="happy", sfx="success")
say(KIDS, "Hooray! Bobo did it!", act="yay", also={M: "cheer"}, cam="group", sfx="sparkle")
say(B, "Thank you, friends! You taught me to count!", act="thumbs_up", cam="cu:bobo", face="happy",
    game={"type": "trampoline_off", "who": B})
say(M, "Great job, Bobo! And great job, everybody at home!", act="thumbs_up", cam="host")

# 13 --------------------------------------------------------------- quiz + goodbye
say(M, "Let's play a quick number quiz!", act="cheer", cam="host", chapter="Number quiz and goodbye", sfx="chime")
ask(M, "How many ears does Bobo have?", act="point", cam="group")
say(LI, "Two!", act="cheer", cam="kids", card="2")
ask(M, "How many fingers on one hand?", act="hands_up", cam="host")
say(O, "Five!", act="cheer", cam="cu:ollie", card="5")
ask(M, "What comes after nine?", act="think", cam="host")
say(B, "Banana!", act="silly", cam="cu:bobo", pic="banana")
say(KIDS, "Nooo! Ten!", act="laugh", cam="kids", card="10")
say(B, "Hee hee! I'm joking! Ten comes after nine!", act="laugh", cam="cu:bobo")
ask(M, "And how many bounces in the Big Bounce?", act="point", cam="group")
say(KIDS, "Ten!", act="yay", cam="kids", card="10", sfx="success")
say(M, "Today we counted all the way to ten!", act="count", cam="host", card="10")
say(M, "Next time, we'll find shapes with Bobo! Circles, squares, and triangles!", act="point", cam="host")
say(B, "Shapes? I love shapes! Is a banana a shape?", act="silly", cam="cu:bobo")
say(KIDS, "Hee hee! Silly Bobo!", act="giggle", cam="kids")
say(M, "Let's sing our goodbye song!", act="wave", also={LI: "wave", O: "wave", B: "wave"}, cam="group", gap_after=0.6)
say(ALL, "Bye bye, bye bye, see you soon! Bye bye, bye bye, toodle-oo!", chant=True, act="wave", cam="group")
say(ALL, "Bye bye, bye bye, see you soon! Bye bye, bye bye, toodle-oo!", chant=True, act="wave", cam="group", gap_after=0.6)
say(ALL, "Bye bye, friends!", act="wave", cam="group", endcard="Bye bye!\nSee you next time!", sfx="success")


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
