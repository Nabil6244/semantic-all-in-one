"""Kids Channel 3, episode 1 - "Playground Adventure with Ms Lina: find the 5 lost ducklings" (about 16 min).

Writes ch3_ep01_playground.json (script) + ch3_ep01_playground_render.json next to this file (cartoon2d/ch3.py).

The story: the bubble man's bubbles floated into the playground and Mama Duck's five ducklings chased them. Tobi wants
to help most of all, but he is scared of the big slide on the hill. Every duckling is stuck somewhere for a reason,
and the play at that stop is how the friends get it back:
  swings   - a shy duckling hides from the noise; Rosie swings slowly and they sing softly until it comes out
  sandpit  - Dot's sandcastle fell on a duckling; dig it out by finding the castle with the triangle door
  train    - a duckling is across the railway and the train keeps passing; ride the train round to it
  setback  - Fizz toots so loudly that one duckling jumps out of the basket and runs into the soft play house
  softplay - it hides among the coloured balls; Fizz learns a quiet voice to call it; Tobi tries the little slide
  splash   - a duckling is behind the water jets; jump, spin and stomp through when the jets stop
  hill     - the last duckling is at the top of the big slide; Tobi climbs and slides down with it
Then home to Mama Duck at the pond: every duckling's rescue remembered, a calm recap, a teaser, the goodbye song.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ch3 import Episode, LINA, NIA, POPPY, TOBI, ROSIE, FIZZ, PIP, DOT  # noqa: E402

BG = "cartoon2d/art/bg/ch3e1_{}.png"
ep = Episode("ch3_ep01_playground", goal=("duckling", 5), music="sunny", hero=TOBI, giver="mama_duck",
             learn=["duckling", "slide", "swing", "train", "splash", "brave"])
ep.place("gate", BG.format("gate"), [LINA, NIA, TOBI, ROSIE, FIZZ])
ep.place("swings", BG.format("swings"), [LINA, ROSIE, TOBI, PIP], rides={ROSIE: "swing"})
ep.place("sandpit", BG.format("sandpit"), [LINA, TOBI, DOT, POPPY])
ep.place("train", BG.format("railway"), [LINA, TOBI, ROSIE, FIZZ, PIP])
ep.place("softplay", BG.format("softplay"), [LINA, FIZZ, TOBI, ROSIE], rides={TOBI: "pit", ROSIE: "pit"})
ep.place("splash", BG.format("splash"), [LINA, TOBI, NIA, POPPY, FIZZ])
ep.place("slide", BG.format("hill"), [LINA, TOBI, ROSIE, FIZZ], rides={TOBI: "slide"})
ep.place("picnic", BG.format("picnic"), [LINA, TOBI, ROSIE, FIZZ, DOT], music="calm")
say, ask, found = ep.say, ep.ask, ep.found
KIDS = [TOBI, ROSIE]


def everyone(place, act):
    return {w: act for w in ep.places[place]["who"][1:]}


def chant(place, intro, words, act="dance", who=None, intro_by=LINA):
    who = who or ep.places[place]["who"]
    ask(intro_by, intro, act="clap", also=everyone(place, "clap"), cam="group", gap_after=0.4)
    for _ in range(2):
        say(who, words, chant=True, act=act, also=everyone(place, act), cam="group")


# 1 ---------------------------------------------------------------- cold open: the problem, the hero, the goal (gate)
say(FIZZ, "Oh no! Look! Mama Duck is crying by the gate!", act="hands_up", place="gate", cam="group", pic="mama_duck",
    sfx="whoosh", face="surprised", chapter="Mama Duck needs help")
say(ROSIE, "The bubble man's bubbles floated into the playground, and her five ducklings chased them!", act="point",
    also={TOBI: "wobble"}, cam="kids", pic="duckling", fx="bubbles")
say(LINA, "Let's find all five ducklings and bring them home to Mama Duck!", act="open", cam="host", goal=True)
ep.want(TOBI, "I want to find them! I'm a good finder!", act="jump")
ep.want(TOBI, "But... not on the big slide. The big slide is too big for me.", act="wobble", face="surprised")
say(LINA, "That's okay, Tobi. Being brave means trying, one little step at a time.", act="open", cam="host",
    card="BRAVE")
say([LINA, NIA, TOBI, ROSIE, FIZZ], "Playground adventure! Let's go!", act="yay", also=everyone("gate", "yay"),
    cam="group", title="Playground\nAdventure!", fx="confetti", sfx="success", gap_after=1.4)

# 2 ---------------------------------------------------------------- hello song + names
say(LINA, "Clap along with our hello song!", act="clap", also=everyone("gate", "clap"), cam="group", your_turn=True,
    chapter="Hello song", gap_after=0.4)
for _ in range(2):
    say([LINA, NIA, TOBI, ROSIE, FIZZ], "Hello, hello, come and play! It's a playground adventure day!", chant=True,
        act="dance", also=everyone("gate", "dance"), cam="group")
say(LINA, "Hi friends! I'm Ms Lina!", act="wave", cam="host", gap_after=0.4)
say(NIA, "I'm Nia! I'm fast!", act="wave", cam="group")
say(TOBI, "I'm Tobi! I'm a good finder!", act="jump", cam="kids")
say(ROSIE, "I'm Rosie! I love the swings!", act="giggle", cam="kids")
say(FIZZ, "And I'm Fizz the fox! I'm the LOUDEST! TOOT TOOT!", act="cheer", cam="cu:fizz", sfx="whistle")
say(NIA, "Fizz! Shh! You'll scare the ducklings!", act="laugh", cam="group", funny=True)
ask(LINA, "Will you help us find the ducklings? Shout yes!", act="point", cam="host", gap_after=0.6)
say(KIDS, "Yes!", act="jump", also={FIZZ: "jump", NIA: "jump"}, cam="group", sfx="sparkle")
say(LINA, "Ducklings say peep peep. Can you say peep peep?", act="open", cam="host", pic="duckling", your_turn=True,
    gap_after=1.6)
say(ROSIE, "Listen! Peep, peep! It's coming from the swings!", act="point", cam="kids", sfx="pop")

# 3 ---------------------------------------------------------------- stop 1: swings (a shy duckling, slow and soft)
ep.arrive("swings", "The swings! Let's go!", "Swing\nTime!")
ep.stuck(ROSIE, "There's a duckling hiding by the swing! But it's shaking. It's shy!", act="point",
         at=("swing", ROSIE))
say(PIP, "Ribbit! I'll catch it! JUMP!", act="frog", cam="cu:pip", sfx="boing", funny=True)
say(LINA, "Wait, Pip! Big jumps and loud noises scare little ducklings.", act="open", cam="host")
say(LINA, "If we swing slowly and sing softly, it will feel safe and come out.", act="think", cam="host",
    card="SLOW SOFT")
say(ROSIE, "I can swing slowly! Watch me!", act="giggle", game={"type": "swing", "who": ROSIE, "lines": 12},
    cam="group")
say(LINA, "Rosie swings forward, high! And back, low!", act="open", cam="host", card="HIGH LOW")
ask(LINA, "When the swing goes high, reach high! When it comes back low, crouch low!", act="hands_up",
    also={TOBI: "hands_up", PIP: "hands_up"}, cam="group", card="HIGH LOW", gap_after=1.8)
ask(LINA, "Let's count the swings very softly. One... two... three... four... five...", act="count", cam="host",
    card="1 2 3 4 5", gap_after=1.6)
say(TOBI, "Look! It's peeking out!", act="point", cam="kids", sfx="pop")
chant("swings", "Let's sing it softly, like a whisper.", "Swing, swing, slow and low. Little duckling, here we go.",
      act="sway", who=[LINA, ROSIE, TOBI, PIP])
say(PIP, "Ribbit... ribbit... I'm being quiet... RIBBIT! Oops.", act="wobble", cam="cu:pip", sfx="boing", funny=True)
say(KIDS, "Shhh, Pip!", act="giggle", cam="kids")
ask(LINA, "Can you hold out your hands, nice and gentle?", act="open", cam="host", gap_after=1.6)
found(ROSIE, "It hopped right into my hands! Hello, shy little duckling.", fx="stars")
say(LINA, "We were slow and soft, and it felt safe. That's one duckling!", act="cheer", also=everyone("swings", "cheer"),
    cam="group", card="1", sfx="success")
say(TOBI, "Peep peep! I hear another one... in the sand!", act="point", cam="kids")

# 4 ---------------------------------------------------------------- stop 2: sandpit (a castle fell on a duckling)
ep.arrive("sandpit", "The sandpit! Soft, warm sand!", "Sand\nCastles!")
say(DOT, "Rawr! I built three sandcastles! But one fell down... and now it's peeping!", act="stomp", cam="cu:dot",
    sfx="boing")
ep.stuck(POPPY, "A duckling is stuck in the sand! Only its little head is peeking out!", act="think", peek=0.5)
say(POPPY, "Dot says the castle with the triangle door fell on it. We have to know our shapes to dig the right way!",
    act="point", cam="group", pic="shape_triangle")
say(LINA, "Let's learn the doors, so we dig the right one. This door is a circle. Round and round!", act="spin",
    cam="host", pic="shape_circle")
ask(LINA, "Can you draw a circle in the air with your finger?", act="spin", cam="host", pic="shape_circle",
    your_turn=True, gap_after=1.6)
say(TOBI, "This door is a square! Four sides! One, two, three, four!", act="count", cam="kids", pic="shape_square",
    card="4")
say(POPPY, "And this door has three sides. One, two, three! A triangle!", act="count", cam="group",
    pic="shape_triangle", card="3")
say(DOT, "I'll dig the round one! Stomp stomp!", act="stomp", cam="cu:dot", sfx="boing", funny=True)
say(TOBI, "No, Dot! That's the circle! We need the door with three sides!", act="point", cam="kids")
ask(LINA, "Which door has three sides? Is it the circle, the square, or the triangle?", act="think", cam="host",
    pic="shape_triangle", gap_after=2.2)
say(KIDS[:1] + [POPPY], "The triangle!", act="yay", cam="group", sfx="ding_5")
say(POPPY, "Dig, Dot, dig! I'll throw you the little spade!", act="point", cam="group",
    game={"type": "throw", "from": POPPY, "to": DOT, "pic": "ball", "bounces": 1})
say(DOT, "Got it! Dig, dig, dig!", act="catch", cam="group", sfx="pop")
ask(LINA, "Dig with Dot! Dig, dig, dig!", act="squat", also=everyone("sandpit", "squat"), cam="group", gap_after=1.4)
found(TOBI, "There it is! A sandy little duckling! I found it!", fx="stars")
say(LINA, "Tobi, you are a good finder! Two ducklings!", act="cheer", also=everyone("sandpit", "cheer"), cam="group",
    card="2", sfx="success")
chant("sandpit", "Shape song, everybody!", "Circle, square and triangle too! Three little doors, and a duckling for you!",
      intro_by=POPPY)
ep.waiting("Mama Duck is waiting by the pond. Two found, three to go, Mama Duck!", act="wave")
say(DOT, "Choo choo! I hear the little train!", act="point", cam="cu:dot", sfx="whistle")

# 5 ---------------------------------------------------------------- stop 3: train (a duckling across the track)
ep.arrive("train", "All aboard! The little train station!", "Train\nRide!")
ep.stuck(ROSIE, "Look! A duckling on the other side of the track! But the train keeps going past!", act="point",
         at="back")
say(FIZZ, "I know! We ride the train all the way round, and get off on the other side!", act="cheer",
    cam="cu:fizz")
say(LINA, "Great idea, Fizz! Everybody hop on. Which carriage will you pick?", act="point", cam="host")
say(LINA, "The red carriage for Tobi! The blue one for Rosie! The yellow one for Fizz!", act="point", cam="host",
    card="RED BLUE YELLOW")
say([TOBI, ROSIE, FIZZ], "Choo choo! Here we go!", act="wave", cam="group",
    game={"type": "train", "who": [TOBI, ROSIE, FIZZ], "lines": 8, "off": True})
ask(LINA, "Can you say red, blue, yellow?", act="count", cam="host", card="RED BLUE YELLOW", gap_after=1.8)
say(PIP, "Red, blue, yellow! Round and round the track!", act="frog", cam="cu:pip")
ask(LINA, "How many carriages? Count with me! One, two, three!", act="count", cam="host", card="1 2 3", gap_after=1.6)
chant("train", "Train song! March along with Pip!", "Choo choo, round the track! Red and blue and yellow, and back!",
      act="march", who=[LINA, PIP], intro_by=PIP)
say(LINA, "The train is stopping on the other side. Off we hop!", act="open", cam="host", sfx="whistle")
found(ROSIE, "Got you, little duckling! You were waiting for the train too!", fx="stars")
say(LINA, "Three ducklings! Into the basket, all safe together.", act="cheer", also=everyone("train", "cheer"),
    cam="group", card="3", sfx="success")
say(FIZZ, "Three ducklings! I'm SO happy! TOOT TOOT TOOOOT!", act="cheer", cam="cu:fizz", sfx="whistle")
ep.setback(ROSIE, "Oh no! The loud toot scared one! It jumped out of the basket!", lost=True, act="hands_up",
           face="surprised")
ep.setback(TOBI, "It's running into the soft play house!", act="point")
say(FIZZ, "Oh no... that was my fault. I was too loud.", act="wobble", cam="cu:fizz")
say(LINA, "It's okay, Fizz. Everybody makes mistakes. We can fix it together.", act="open", cam="host")
ask(LINA, "Can you help Fizz be quiet? Put a finger on your lips and say shhh.", act="open", cam="host",
    your_turn=True, gap_after=1.8)

# 6 ---------------------------------------------------------------- stop 4: soft play (the runaway, a quiet voice)
ep.arrive("softplay", "The soft play house! Look at all the balls!", "Ball Pit\nFun!")
ep.stuck(LINA, "The duckling is hiding in the balls! Only its head is peeking out! Everything is red, green and purple!",
         act="think", peek=0.45, mound=(235, 70, 80))
say(LINA, "Ducklings are yellow. Let's find the yellow one!", act="point", cam="host", card="YELLOW", pic="duckling")
ep.tries(TOBI, "There's a little slide into the balls. I'll try the little one first!", act="jump")
say(TOBI, "One, two... wheee! I did a little slide!", act="cheer", game={"type": "pit", "who": [TOBI, ROSIE], "lines": 10},
    cam="group")
say(LINA, "That was brave, Tobi! A little step, and then a bigger one.", act="cheer", cam="host", card="BRAVE")
say(ROSIE, "Here's a red ball! Not yellow.", act="hands_up", cam="kids", card="RED", sfx="pop")
ask(LINA, "Can you see a green ball? Point to the green one!", act="think", cam="host", card="GREEN", gap_after=1.8)
say(TOBI, "Green, like Pip the frog! Still not yellow.", act="point", cam="kids", sfx="pop")
say(FIZZ, "I want to call it. But a quiet voice. Like this... peep, peep.", act="open", cam="cu:fizz")
ask(LINA, "Use your quiet voice with Fizz. Peep... peep...", act="open", cam="host", your_turn=True, gap_after=1.8)
chant("softplay", "Whisper with us!", "Yellow, yellow, where are you? Little duckling, peep peep too.",
      act="sway", intro_by=FIZZ)
ask(LINA, "Can you see something yellow? Where is it?", act="think", cam="host", card="YELLOW", gap_after=2.0)
found(FIZZ, "It peeped back! There you are! I'm sorry I was loud.", fx="hearts")
say(LINA, "Fizz used his quiet voice and fixed it! Three ducklings again!", act="cheer",
    also=everyone("softplay", "cheer"), cam="group", card="3", sfx="success")
say(FIZZ, "Quiet voice for ducklings. Loud voice... for the train!", act="giggle", cam="cu:fizz", funny=True)
ep.waiting("Mama Duck, we have three! Two more ducklings, then we're coming home.", act="wave")
say(ROSIE, "I hear splashing! And a little peep!", act="point", cam="kids", sfx="pop")

# 7 ---------------------------------------------------------------- stop 5: splash pad (behind the water jets)
ep.arrive("splash", "The splash pad! Splish, splash, splosh!", "Splash\nTime!", fx="bubbles")
ep.stuck(NIA, "A duckling is behind the water jets! The water is too strong to walk through!", act="point",
         at="back")
say(POPPY, "The jets stop for a moment, then go again. When they stop, we jump through!", act="think",
    cam="group")
chant("splash", "Water song first! Jump with Poppy!", "Splish, splash, splosh! Wait for the water, splash!",
      act="jump", intro_by=POPPY)
say(LINA, "Ready? The jets stopped. Jump!", act="jump", cam="host", fx="bubbles", sfx="burst")
ask(LINA, "Jump! Jump! Jump! Can you jump with us?", act="jump", also=everyone("splash", "jump"), cam="group",
    card="JUMP", gap_after=1.4)
say(FIZZ, "Catch the beach ball, Nia! It's bouncing over the jets!", act="point", cam="group",
    game={"type": "throw", "from": FIZZ, "to": NIA, "pic": "ball"})
say(NIA, "Got it! Now spin past the little fountain!", act="catch", cam="group", sfx="burst")
ask(LINA, "Spin around! Spin, spin, spin!", act="spin", also=everyone("splash", "spin"), cam="group", card="SPIN",
    gap_after=1.4)
say(FIZZ, "Foxes don't like water! Eek! Oh wait... it's fun! Splash!", act="wobble", cam="cu:fizz", sfx="boing",
    funny=True)
ask(LINA, "Last one! Stomp, stomp, through the puddle!", act="stomp", also=everyone("splash", "stomp"), cam="group",
    card="STOMP", fx="bubbles", gap_after=1.4)
found(NIA, "Made it! A wet little duckling, all splashy!", fx="stars")
say(LINA, "Four ducklings! Just one more!", act="cheer", also=everyone("splash", "cheer"), cam="group", card="4",
    sfx="success")
say(TOBI, "Peep... peep... It's coming from up the hill.", act="think", cam="kids")
say(TOBI, "From the top of... the big slide.", act="wobble", cam="kids", face="surprised")

# 8 ---------------------------------------------------------------- stop 6: the big slide (Tobi's fear)
ep.arrive("slide", "The big slide on the grassy hill.", "The Big\nSlide!", act="walk")
ep.stuck(ROSIE, "There it is! The last duckling is stuck at the top of the slide! It can't get down by itself!",
         act="point", at=("slide", TOBI))
ep.waiting("Mama Duck is waiting. This is the very last one!", who=ROSIE, cam="kids")
say(TOBI, "It's scared. Like me. The slide is so big.", act="wobble", cam="kids")
say(LINA, "Remember the little slide, Tobi? One little step at a time. We'll count every step with you.",
    act="open", cam="host", card="BRAVE")
say(TOBI, "Okay. I'll try. Will you count with me?", act="hands_up", cam="kids")
for n, w in enumerate(["One", "Two", "Three", "Four", "Five"], 1):
    say(LINA if n % 2 else [ROSIE, FIZZ], f"{w}!", act="march", also={TOBI: "march"}, cam="group", card=str(n),
        gap_after=0.3)
ask(LINA, "Count the steps with Tobi! One, two, three, four, five!", act="count", cam="host", card="5",
    gap_after=1.6)
say(TOBI, "I'm at the top! I've got you, little duckling. Hold on to me! Down we go!", act="cheer",
    game={"type": "slide", "who": TOBI}, cam="group", gap_after=0.8)
found(TOBI, "We're at the bottom! The last duckling is safe!", fx="stars")
ep.payoff(TOBI, "Wheee! I did it! I went down the big slide!", act="yay", also=everyone("slide", "yay"),
          sfx="success")
say(LINA, "Tobi! You were scared, and you did it anyway. That's brave!", act="cheer", cam="host", card="BRAVE")
chant("slide", "Brave song! Clap for Tobi!", "Up the steps and down the slide! Tobi was brave, wheee, what a ride!",
      act="dance")
say(LINA, "Five ducklings! We found them all! Let's take them home!", act="cheer", also=everyone("slide", "cheer"),
    cam="group", card="5", fx="confetti")

# 9 ---------------------------------------------------------------- home: the reunion, every rescue remembered, goodbye
ep.arrive("picnic", "Here's the duck pond. Mama Duck, look!", "Home Again!", act="walk")
ask(LINA, "Count them home with Mama Duck! One, two, three, four, five little ducklings!", act="count", cam="host",
    card="1 2 3 4 5", pic="mama_duck", fx="hearts", sfx="sparkle", gap_after=1.6)
say(ROSIE, "Mama Duck says quack quack! Thank you, friends!", act="giggle", cam="kids", pic="mama_duck")
say(DOT, "Rawr! I missed everything! What happened?", act="stomp", cam="cu:dot", funny=True)
say(LINA, "Let's sit and rest, and tell Dot. Take a big breath in... and out.", act="open", cam="host", calm=True,
    chapter="Quiet time and goodbye", gap_after=1.6)
say(ROSIE, "The shy duckling came out when we swung slowly and sang softly.", act="sway", cam="kids", calm=True,
    card="SLOW SOFT")
say(TOBI, "We dug the sandy one out of the castle with the triangle door.", act="count", cam="kids", calm=True,
    pic="shape_triangle")
say(FIZZ, "We rode the red, blue and yellow train round the track. And I learned my quiet voice.", act="open",
    cam="cu:fizz", calm=True, card="RED BLUE YELLOW")
say(LINA, "We jumped through the splash pad. And Tobi went down the big slide.", act="open", cam="host", calm=True)
say(TOBI, "I was scared. But I tried one little step at a time. I'm brave!", act="hands_up", cam="kids", calm=True,
    card="BRAVE")
ask(LINA, "Say it with Tobi, nice and proud. I am brave!", act="open", cam="host", calm=True, card="BRAVE",
    gap_after=1.8)
say(FIZZ, "Next time, let's go to the farm! The piglets are lost! Oink oink!", act="cheer", cam="cu:fizz", teaser=True,
    pic="cow")
ask(LINA, "Wave goodbye with us! Let's sing our goodbye song!", act="wave", also=everyone("picnic", "wave"), cam="group",
    gap_after=0.6)
say([LINA, TOBI, ROSIE, FIZZ, DOT], "Bye bye, bye bye, see you soon! Bye bye, bye bye, toodle-oo!", chant=True,
    act="wave", also=everyone("picnic", "wave"), cam="group", gap_after=0.6)
say([LINA, TOBI, ROSIE, FIZZ, DOT], "Bye bye, friends! See you next time!", act="wave", also=everyone("picnic", "wave"),
    cam="group", endcard="Bye bye!\nSee you next time!", sfx="success")

ep.write()
