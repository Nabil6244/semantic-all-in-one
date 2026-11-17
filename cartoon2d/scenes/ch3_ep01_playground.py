"""Kids Channel 3, episode 1 - "Playground Adventure with Ms Lina: find the 5 lost ducklings" (about 18 min).

Writes ch3_ep01_playground.json (script) + ch3_ep01_playground_render.json next to this file (cartoon2d/ch3.py).

Cold open at the park gate: Mama Duck's five ducklings ran off into the playground. Ms Lina, Tobi, Rosie and friends
look for them at six play stops - one duckling at five of them - and play and learn at each:
  slide (up and down, counting steps), swings (counting pushes, high and low), sandpit (shapes in the sand),
  little train (colours of the carriages), ball pit (colours of the balls), splash pad (action words).
Then all five are back with Mama Duck at the picnic pond: calm recap, a teaser for next time, the goodbye song.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ch3 import Episode, LINA, NIA, POPPY, TOBI, ROSIE, FIZZ, PIP, DOT  # noqa: E402

BG = "cartoon2d/art/bg/ch3e1_{}.png"
ep = Episode("ch3_ep01_playground", goal=("duckling", 5), music="sunny",
             learn=["duckling", "slide", "swing", "train", "splash"])
ep.place("gate", BG.format("gate"), [LINA, NIA, TOBI, ROSIE, FIZZ])
ep.place("slide", BG.format("hill"), [LINA, TOBI, ROSIE, FIZZ], rides={TOBI: "slide"})
ep.place("swings", BG.format("swings"), [LINA, ROSIE, PIP], rides={ROSIE: "swing"})
ep.place("sandpit", BG.format("sandpit"), [LINA, TOBI, DOT, POPPY])
ep.place("train", BG.format("railway"), [LINA, TOBI, ROSIE, FIZZ, PIP])
ep.place("softplay", BG.format("softplay"), [LINA, PIP, DOT, ROSIE], rides={PIP: "pit", DOT: "pit", ROSIE: "pit"})
ep.place("splash", BG.format("splash"), [LINA, TOBI, NIA, POPPY, FIZZ])
ep.place("picnic", BG.format("picnic"), [LINA, TOBI, ROSIE, FIZZ, DOT], music="calm")
say, ask, found = ep.say, ep.ask, ep.found
KIDS = [TOBI, ROSIE]


def everyone(place, act):
    here = ep.places[place]["who"]
    return {w: act for w in here[1:]}


def song(place, words, act="dance", who=None):
    who = who or ep.places[place]["who"]
    ask(LINA, "Sing it with us!", act="clap", also=everyone(place, "clap"), cam="group", gap_after=0.4)
    for _ in range(2):
        say(who, words, chant=True, act=act, also=everyone(place, act), cam="group")


def mistake(silly, wrong, fixer, right, place):
    """The sidekick gets one thing funny-wrong, the kids put it right (laughs keep little ones watching)."""
    say(silly, wrong, act="wobble", cam="group", sfx="boing")
    say(fixer, f"No, silly! {right}", act="laugh", cam="group")
    say(silly, "Oopsie! Hee hee!", act="tumble", cam="group", sfx="pop")


def duckling_hunt(place, k, where, spot, finder, cheer_line):
    """One lost duckling hidden in the place: look, the child helps, found, counted on screen."""
    spot = ep.free_spot(place)                          # in the open, never behind a character
    ask(LINA, f"Duckling number {k} is hiding {where}. Can you see it? Point to it!", act="think", cam="group",
        find={"pic": "duckling", "x": spot[0], "y": spot[1], "size": 0.08}, gap_after=2.8)
    found(finder, f"There! I found the duckling!", fx="stars")
    say(LINA, f"Hooray! {cheer_line} That's {k} duckling{'s' if k > 1 else ''}!", act="cheer",
        also=everyone(place, "cheer"), cam="group", card=str(k), sfx="success")
    say(ROSIE if finder != ROSIE else TOBI, "Quack quack! Hello, little duckling!", act="wave", cam="kids", pic="duckling")


# 1 ---------------------------------------------------------------- cold open: hook + goal (park gate)
say(FIZZ, "Oh no! Look! Mama Duck is crying!", act="hands_up", place="gate", cam="group", pic="mama_duck",
    sfx="whoosh", face="surprised", chapter="Mama Duck needs help")
say(ROSIE, "Her five little ducklings ran into the playground!", act="point", also={TOBI: "wobble"}, cam="kids",
    pic="duckling", fx="leaves")
say(LINA, "Let's find all five ducklings and bring them home to Mama Duck!", act="open", cam="host", goal=True)
say([LINA, NIA, TOBI, ROSIE, FIZZ], "Playground adventure! Let's go!", act="yay", also=everyone("gate", "yay"),
    cam="group", title="Playground\nAdventure!", fx="confetti", sfx="success", gap_after=1.4)

# 2 ---------------------------------------------------------------- hello song + names
say(LINA, "Clap along with our hello song!", act="clap", also=everyone("gate", "clap"), cam="group", your_turn=True,
    chapter="Hello song", gap_after=0.4)
for _ in range(2):
    say([LINA, NIA, TOBI, ROSIE, FIZZ], "Hello, hello, come and play! It's a playground adventure day!", chant=True,
        act="dance", also=everyone("gate", "dance"), cam="group")
say(LINA, "Hi friends! I'm Ms Lina! Welcome to the big park!", act="wave", cam="host", gap_after=0.4)
say(NIA, "Hi! I'm Nia! I love to run and climb!", act="wave", cam="group")
say(TOBI, "I'm Tobi! I love the slide!", act="jump", cam="kids")
say(ROSIE, "I'm Rosie! I love the swings!", act="giggle", cam="kids")
say(FIZZ, "And I'm Fizz the fox! I love trains! Choo choo!", act="cheer", cam="cu:fizz")
ask(LINA, "Will you help us find the ducklings? Shout yes!", act="point", cam="host", gap_after=0.6)
say(KIDS, "Yes!", act="jump", also={FIZZ: "jump", NIA: "jump"}, cam="group", sfx="sparkle")
say(LINA, "Ducklings say quack quack. Can you say quack quack?", act="open", cam="host", pic="duckling", your_turn=True,
    gap_after=1.6)
say([TOBI, ROSIE, FIZZ], "Quack quack! Quack quack!", act="bunny", also={NIA: "bunny"}, cam="group")
say(LINA, "Listen! I hear a little quack by the big slide!", act="point", cam="host", sfx="pop")

# 3 ---------------------------------------------------------------- stop 1: the slide (up and down, count the steps)
ep.arrive("slide", "Here's the big slide on the grassy hill!", "Slide\nTime!")
say(TOBI, "Can I go down the slide? Please, please?", act="hands_up", cam="kids")
say(LINA, "Yes! First we climb up the steps. Let's count them!", act="count", cam="host")
for n, w in enumerate(["One", "Two", "Three", "Four", "Five"], 1):
    say(LINA if n % 2 else [TOBI, ROSIE], f"{w}!", act="march", also={TOBI: "march", ROSIE: "march"}, cam="group",
        card=str(n), gap_after=0.25)
ask(LINA, "Five steps! Can you count to five with us? One, two, three, four, five!", act="count", cam="host",
    card="5", gap_after=1.6)
say(TOBI, "Up, up, up I go! And down, down, wheee!", act="cheer", game={"type": "slide", "who": TOBI}, cam="group",
    gap_after=0.8)
say(LINA, "Tobi went up the steps, and down the slide! Up and down!", act="open", cam="host", card="UP DOWN")
ask(LINA, "Point up! Point down! Up! Down!", act="hands_up", also=everyone("slide", "hands_up"), cam="group", gap_after=1.2)
say(FIZZ, "Up, down, up, down! I'm dizzy!", act="wobble", cam="cu:fizz", sfx="boing")
say(KIDS, "Hee hee! Silly Fizz!", act="giggle", cam="kids")
song("slide", "Up the steps and down the slide! Wheee, wheee, what a ride!")
mistake(FIZZ, "I'll go down the slide... upside down! Head first!", TOBI, "We sit down and go feet first!", "slide")
ask(LINA, "How do we go down the slide? We sit down! Can you sit down?", act="squat", also=everyone("slide", "squat"),
    cam="group", card="SIT DOWN", gap_after=1.6)
say(TOBI, "Again! Again! Up, up, up, and wheee!", act="cheer", game={"type": "slide", "who": TOBI}, cam="group",
    gap_after=0.8)
duckling_hunt("slide", 1, "near the bushes", (0.92, 0.84), ROSIE, "We found one!")
say(LINA, "One duckling found! Four more to find. Let's go to the swings!", act="point", cam="host", card="1")

# 4 ---------------------------------------------------------------- stop 2: the swings (push and count, high and low)
ep.arrive("swings", "Swing time! Back and forth, back and forth!", "Swing\nTime!")
say(ROSIE, "Push me, push me! Higher, higher!", act="giggle", game={"type": "swing", "who": ROSIE, "lines": 10},
    cam="group")
say(LINA, "Let's count the pushes. One, two, three, four, five!", act="count", cam="host", card="1 2 3 4 5")
ask(LINA, "Swing your arms with us! Back and forth! Back and forth!", act="dance", also={PIP: "dance"}, cam="group",
    gap_after=1.2)
say(ROSIE, "Wheee! I can see the whole park from up here!", act="cheer", cam="group")
say(PIP, "Ribbit! I'll push you, Rosie! Wheee!", act="jump", cam="cu:pip", sfx="boing")
say(LINA, "Rosie swings high, and swings low!", act="open", cam="host", card="HIGH LOW")
ask(LINA, "When the swing goes up, say up! When it comes down, say down! Up! Down!", act="hands_up", cam="host",
    card="UP DOWN", gap_after=1.6)
song("swings", "Swing, swing, swing so high! Swing up, swing up, to the sky!", act="dance", who=[LINA, ROSIE, PIP])
say(ROSIE, "I love the swing! It feels like flying!", act="giggle", cam="kids")
ask(LINA, "Let's count Rosie's swings! One, two, three, four, five!", act="count", cam="host", card="5",
    pic="duckling", gap_after=1.6)
mistake(PIP, "Ribbit! I'll swing with my eyes closed and my feet in the air!", ROSIE, "Hold on tight with both hands!", "swings")
ask(LINA, "Can you stretch up high? Now crouch down low!", act="hands_up", also={PIP: "squat"}, cam="group",
    gap_after=1.4)
say(PIP, "High and low! High and low! Ribbit ribbit!", act="frog", cam="cu:pip")
duckling_hunt("swings", 2, "behind the big tree", (0.08, 0.84), PIP, "Another one!")
say(LINA, "Two ducklings! Three more to find. Off to the sandpit!", act="point", cam="host", card="2")

# 5 ---------------------------------------------------------------- stop 3: the sandpit (shapes in the sand)
ep.arrive("sandpit", "The sandpit! Soft, warm sand!", "Sand\nShapes!")
say(DOT, "Rawr! I'm Dot the dino! Let's draw shapes in the sand!", act="stomp", cam="cu:dot", sfx="boing")
say(LINA, "A circle! Round and round! Can you draw a circle in the air?", act="spin", cam="host", pic="shape_circle",
    your_turn=True, gap_after=1.6)
say(POPPY, "A triangle! One, two, three sides!", act="count", cam="group", pic="shape_triangle", card="3")
say(TOBI, "A square! Four sides! One, two, three, four!", act="count", cam="kids", pic="shape_square", card="4")
say(DOT, "And a star! Twinkle twinkle!", act="hands_up", cam="cu:dot", pic="shape_star", fx="stars")
song("sandpit", "Circle, triangle, square and star! Shapes, shapes, here they are!")
ask(LINA, "How many sides does a triangle have? Count them! One, two, three!", act="count", cam="host",
    pic="shape_triangle", card="3", gap_after=1.6)
mistake(DOT, "A square is round like a ball! Rawr!", POPPY, "A square has four sides, Dot! A circle is round!", "sandpit")
ask(LINA, "Which shape is round? Is it the circle, or the square?", act="think", cam="host", pic="shape_circle",
    gap_after=2.2)
say(KIDS[:1] + [POPPY], "The circle! The circle is round!", act="yay", cam="group", sfx="ding_5")
say(POPPY, "Catch the ball, Dot! It's round like a circle!", act="point", cam="group",
    game={"type": "throw", "from": POPPY, "to": DOT, "pic": "ball", "bounces": 1})
say(DOT, "Got it! Now you, Tobi!", act="catch", cam="group", game={"type": "throw", "from": DOT, "to": TOBI, "pic": "ball"})
say(TOBI, "Bounce, bounce, bounce!", act="cheer", cam="kids", game={"type": "dribble", "who": TOBI, "n": 4, "pic": "ball"})
duckling_hunt("sandpit", 3, "by the sand buckets", (0.92, 0.85), DOT, "Three ducklings!")
say(LINA, "Three ducklings! Two more. Listen! Choo choo! The little train!", act="point", cam="host", card="3",
    sfx="whistle")

# 6 ---------------------------------------------------------------- stop 4: the little train (colours of the carriages)
ep.arrive("train", "All aboard the little train!", "Train\nRide!")
say(LINA, "Here comes the train! Count the carriages with me!", act="point", cam="host", card="1 2 3")
say([TOBI, ROSIE, FIZZ], "Choo choo! Choo choo!", act="wave", cam="group",
    game={"type": "train", "who": [TOBI, ROSIE, FIZZ], "lines": 7})
say(LINA, "The red carriage! Tobi is in the red one!", act="point", cam="host", card="RED")
say(LINA, "The blue carriage! That's Rosie!", act="point", cam="host", card="BLUE")
say(LINA, "And the yellow carriage! That's Fizz!", act="point", cam="host", card="YELLOW")
ask(LINA, "Can you say red, blue, yellow?", act="count", cam="host", card="RED BLUE YELLOW", gap_after=1.8)
say(PIP, "Red, blue, yellow! Ribbit!", act="frog", cam="cu:pip")
song("train", "Choo choo, choo choo, round the track! Red and blue and yellow, and back!", act="march",
     who=[LINA, PIP])
ask(LINA, "How many carriages? Count them with me! One, two, three!", act="count", cam="host", card="1 2 3", gap_after=1.6)
say(PIP, "Three carriages! And one big engine at the front!", act="point", cam="cu:pip", pic="train")
say(FIZZ, "Toot toot! I love trains!", act="cheer", cam="group", sfx="whistle")
duckling_hunt("train", 4, "next to the little station", (0.08, 0.84), PIP, "Four ducklings!")
say(LINA, "Four ducklings! Just one more! Wave bye bye to the train!", act="wave", also={PIP: "wave"}, cam="host",
    card="4", your_turn=True, gap_after=1.0)
say(PIP, "Bye bye, train! See you soon!", act="wave", cam="cu:pip")

# 7 ---------------------------------------------------------------- stop 5: soft play ball pit (colours of the balls)
ep.arrive("softplay", "Into the soft play house! Look at all the balls!", "Ball Pit\nFun!")
say([PIP, DOT, ROSIE], "Jump in! Splash!", act="cheer", cam="group",
    game={"type": "pit", "who": [PIP, DOT, ROSIE], "lines": 9})
say(LINA, "So many colours! Let's find a red ball!", act="point", cam="host", card="RED")
ask(LINA, "Can you see a red ball? Point to the red one!", act="think", cam="host", card="RED", gap_after=1.8)
say(ROSIE, "Red! Here's a red ball!", act="hands_up", cam="kids", sfx="pop")
say(LINA, "Now a green ball! Green like Pip!", act="point", cam="host", card="GREEN")
say(PIP, "Green like me! Ribbit ribbit!", act="cheer", cam="cu:pip", sfx="pop")
say(LINA, "And a purple ball! Purple like Dot!", act="point", cam="host", card="PURPLE")
say(DOT, "Purple like me! Rawr!", act="cheer", cam="cu:dot", sfx="pop")
song("softplay", "Jump in the balls, red and green! The bounciest balls you've ever seen!", act="jump")
ask(LINA, "Can you find a yellow ball? Yellow like the sun!", act="think", cam="host", card="YELLOW", pic="sun",
    gap_after=1.8)
say(PIP, "Yellow! Here! Bounce, bounce!", act="frog", cam="cu:pip", sfx="pop")
mistake(DOT, "Is this ball blue? It's purple, like me!", ROSIE, "That one is blue, Dot! Blue like the sky!", "softplay")
ask(LINA, "Red, green, purple! Can you say them with us?", act="count", cam="host", card="RED GREEN PURPLE", gap_after=1.8)
say(ROSIE, "No duckling in the ball pit. Where is the last one?", act="think", cam="kids")
say(LINA, "I hear splashing! Let's try the splash pad!", act="point", cam="host", sfx="pop")

# 8 ---------------------------------------------------------------- stop 6: the splash pad (action words)
ep.arrive("splash", "The splash pad! Splish, splash, splosh!", "Splash\nTime!", fx="bubbles")
say(POPPY, "Let's play splash games! Jump in the puddles!", act="jump", also={NIA: "jump"}, cam="group", fx="bubbles",
    sfx="burst")
ask(LINA, "Jump! Jump! Jump! Can you jump with us?", act="jump", also=everyone("splash", "jump"), cam="group",
    card="JUMP", gap_after=1.4)
ask(LINA, "Now spin around! Spin, spin, spin!", act="spin", also=everyone("splash", "spin"), cam="group", card="SPIN",
    gap_after=1.4)
ask(LINA, "Now stomp in the water! Stomp, stomp, splash!", act="stomp", also=everyone("splash", "stomp"), cam="group",
    card="STOMP", fx="bubbles", gap_after=1.4)
say(FIZZ, "Catch the beach ball, Nia!", act="point", cam="group", game={"type": "throw", "from": FIZZ, "to": NIA, "pic": "ball"})
say(NIA, "Splash! Got it!", act="catch", cam="group", sfx="burst")
song("splash", "Splish, splash, splosh! Jump in the water, splash!", act="jump")
ask(LINA, "Now wiggle like a fish! Wiggle, wiggle, wiggle!", act="dance", also=everyone("splash", "dance"), cam="group",
    card="WIGGLE", pic="fish", gap_after=1.4)
mistake(FIZZ, "Foxes don't like water! Eek! Oh wait, it's fun! Splash!", NIA, "Everybody splash!", "splash")
duckling_hunt("splash", 5, "by the big whale", (0.92, 0.84), TOBI, "The last one!")
say(LINA, "Five ducklings! We found them all! Let's take them home to Mama Duck!", act="cheer",
    also=everyone("splash", "cheer"), cam="group", card="5", fx="confetti", sfx="success")

# 9 ---------------------------------------------------------------- home to Mama Duck: count, calm recap, teaser, goodbye
ep.arrive("picnic", "Here's the duck pond. Mama Duck, look!", "Home Again!", act="walk")
say(LINA, "One, two, three, four, five little ducklings, home with Mama Duck!", act="count", cam="host",
    card="1 2 3 4 5", pic="mama_duck", fx="hearts", sfx="sparkle")
say(ROSIE, "Mama Duck says quack quack! Thank you!", act="giggle", cam="kids", pic="mama_duck")
say(LINA, "Now let's sit and rest. Take a big breath in... and out.", act="open", cam="host", calm=True,
    chapter="Quiet time and goodbye", gap_after=1.6)
say(LINA, "Today we went down the slide, up and down. We counted on the swings, high and low.", act="count", cam="host",
    calm=True, card="UP DOWN")
say(LINA, "We drew shapes in the sand, rode the little train, and found colours in the ball pit.", act="count",
    cam="host", calm=True, card="RED BLUE YELLOW")
say(LINA, "And we jumped and splashed at the splash pad! Splash, splash!", act="open", cam="host", calm=True)
say(FIZZ, "Next time, let's go to the farm! Moo! Baa! Oink!", act="cheer", cam="cu:fizz", teaser=True, pic="cow")
ask(LINA, "Wave goodbye with us! Let's sing our goodbye song!", act="wave", also=everyone("picnic", "wave"), cam="group",
    gap_after=0.6)
say([LINA, TOBI, ROSIE, FIZZ, DOT], "Bye bye, bye bye, see you soon! Bye bye, bye bye, toodle-oo!", chant=True,
    act="wave", also=everyone("picnic", "wave"), cam="group", gap_after=0.6)
say([LINA, TOBI, ROSIE, FIZZ, DOT], "Bye bye, friends! See you next time!", act="wave", also=everyone("picnic", "wave"),
    cam="group", endcard="Bye bye!\nSee you next time!", sfx="success")

ep.write()
