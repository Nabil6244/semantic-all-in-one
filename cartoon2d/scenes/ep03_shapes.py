"""Episode 3 - "Shapes with Ms Molly & Bobo: Bobo's Shape Party" (about 19 min). Writes ep03_shapes.json next to this file.

Spine: it's Bobo's birthday party. He needs circle cookies, square presents and triangle pizza, but he mixes the shapes up
("a banana is a circle!"). The kids teach circle, square, triangle (and a bonus star) through a shape hunt, counting sides on
the trampoline, catch with a circle ball, balloon pop, hide and seek behind the square box, a shape song and freeze dance.
Rules: ask -> pause -> answer -> praise; each shape named 3+ times per segment with its card; a game / song / move break at
least every 3 minutes; Bobo's mistakes corrected kindly; "Your turn!" pauses for drawing shapes in the air.
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
WORDS = ["One", "Two", "Three", "Four", "Five"]
SHAPE_CARDS = {"circle": "CIRCLE", "circles": "CIRCLE", "square": "SQUARE", "squares": "SQUARE", "triangle": "TRIANGLE",
               "triangles": "TRIANGLE", "star": "STAR"}


def sides(n, who=ALL, bounce=None):
    for i in range(1, n + 1):
        k = {"also": {b: "bounce" for b in bounce}} if bounce else {}
        say(who, f"{WORDS[i - 1]}!", act="count", card=str(i), cam="group", gap_after=0.35, **k)


# 1 ---------------------------------------------------------------- cold open: the hook
say(B, "Hooray! Hooray! It's my birthday party today!", act="bounce", cam="cu:bobo", place="playroom", face="happy",
    chapter="Bobo's birthday", sfx="boing", game={"type": "trampoline", "who": B})
say(B, "I need round cookies, and square presents, and triangle pizza!", act="count", cam="cu:bobo")
say(B, "Look! I found a round cookie!", act="silly", cam="cu:bobo", pic="banana", sfx="pop")
say(KIDS, "Hee hee hee! That's a banana!", act="laugh", cam="kids")
say(B, "Oopsie-daisy! Bananas aren't round?", act="tumble", cam="group", face="surprised", sfx="drumroll",
    game={"type": "trampoline_off", "who": B})
say(M, "Oh, Bobo! Let's learn our shapes, so your party is perfect!", act="open", cam="host")
say(M, "Shapes party!", act="yay", also={LI: "yay", O: "yay", B: "yay"}, cam="group",
    title="Shapes with\nMs Molly & Bobo!", sfx="success", gap_after=2.4)

# 2 ---------------------------------------------------------------- welcome + hello song
say(M, "Hi friends! I'm Miss Molly!", act="wave", cam="host", chapter="Hello song")
say(LI, "Hi! I'm Lily!", act="wave", cam="kids")
say(O, "And I'm Ollie!", act="cheer")
say(B, "And I'm Bobo the Bear! It's my birthday!", act="wave", cam="cu:bobo", face="happy")
say(KIDS, "Happy birthday, Bobo!", act="yay", cam="kids", sfx="sparkle")
say(M, "Let's sing our hello song! Wave with us!", act="wave", also={LI: "wave", O: "wave", B: "wave"}, cam="group", gap_after=0.6)
say(ALL, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="group")
say(ALL, "Hello, hello, hello to you! Hello, hello, how do you do!", chant=True, act="wave", cam="group", gap_after=0.8)
say(M, "Today we're learning three shapes. A circle, a square, and a triangle!", act="count", cam="host", card="3")
ask(M, "Will you help Bobo get ready for his party?", act="point", cam="host")
say(KIDS, "Yes!", act="yay", cam="kids", sfx="sparkle")
say(B, "Thank you, friends! Let's go!", act="jump", cam="cu:bobo", face="happy")

# 3 ---------------------------------------------------------------- CIRCLE
say(M, "Our first shape is a circle!", act="open", cam="host", pic="shape_circle", card="CIRCLE", chapter="Circle", sfx="pop")
ask(M, "Circle. Can you say circle?", act="point", cam="host")
say(KIDS, "Circle!", act="cheer", cam="kids")
say(M, "A circle is round, round, round. It has no corners!", act="spin", cam="host")
say(M, "Let's draw a circle in the air with our finger. Round and round!", act="point", also={LI: "point", O: "point", B: "point"},
    cam="group", your_turn=True, gap_after=2.2)
say(M, "Great circles! Now look. What is this?", act="point", cam="host", pic="cookie", sfx="pop")
ask(M, "It's a cookie! What shape is the cookie?", act="open", cam="host")
say(O, "A circle!", act="cheer", cam="cu:ollie", card="CIRCLE")
say(B, "A round circle cookie! For my party! Yum!", act="yay", cam="cu:bobo", face="happy")
say(M, "Here's another circle. Tick, tock!", act="point", cam="host", pic="clock", sfx="chime")
ask(M, "What shape is the clock?", act="think", cam="host")
say(LI, "The clock is a circle!", act="point", cam="kids", card="CIRCLE")
say(M, "Yes! And look up at the sky.", act="point", cam="host", pic="sun")
ask(M, "What shape is the sun?", act="think", cam="host")
say(KIDS, "A circle!", act="cheer", cam="kids", card="CIRCLE")
say(B, "Ooh! Ooh! Is my tummy a circle?", act="silly", cam="cu:bobo")
say(M, "Hee hee! Bobo's tummy is round, like a circle!", act="laugh", cam="host")
say(KIDS, "Hee hee hee!", act="giggle", cam="kids")

# 4 ---------------------------------------------------------------- circle games: catch + balloon pop
say(M, "Let's play with circles in the garden!", act="point", cam="host", chapter="Circle games")
say(M, "Here we are in the garden!", act="open", also={LI: "cheer", O: "cheer", B: "cheer"}, cam="group", place="garden",
    sfx="sparkle", hold={O: "ball"}, gap_after=0.8)
ask(O, "Look! My ball is round. What shape is it?", act="talk", cam="cu:ollie")
say(KIDS, "A circle!", act="cheer", cam="kids", card="CIRCLE")
say(O, "Catch, Bobo!", act="talk", game={"type": "throw", "from": O, "to": B, "bounces": 1}, cam="group", gap_after=1.4)
say(B, "I caught the circle! Catch, Lily!", act="talk", face="happy", game={"type": "throw", "from": B, "to": LI, "bounces": 0, "at": 1.3},
    cam="group", gap_after=1.2)
say(LI, "Got it! Bounce, bounce, bounce!", act="talk", game={"type": "dribble", "who": LI, "n": 3}, cam="kids", gap_after=0.6)
say(M, "Wonderful! Now look! Balloons! Balloons are round, like circles.", act="point", cam="host", drop=[LI])
say(M, "Pop the circle balloons!", act="cheer", cam="group",
    game={"type": "balloons", "colors": ["red", "blue", "yellow", "red"]}, gap_after=3.0)
ask(M, "How many circle balloons did we pop?", act="think", cam="host")
say(KIDS, "Four!", act="yay", cam="kids", card="4")
say(M, "Four round balloons! Great counting!", act="thumbs_up", cam="host", sfx="success")

# 5 ---------------------------------------------------------------- SQUARE
say(M, "Our next shape is a square!", act="open", cam="host", pic="shape_square", card="SQUARE", chapter="Square", sfx="pop")
ask(M, "Square. Can you say square?", act="point", cam="host")
say(KIDS, "Square!", act="cheer", cam="kids")
say(M, "A square has four sides. All the same! Let's count them.", act="count", cam="host", card="4")
sides(4, who=ALL)
say(M, "Four sides! Let's draw a square in the air. Across, down, across, up!", act="point",
    also={LI: "point", O: "point", B: "point"}, cam="group", your_turn=True, gap_after=2.2)
say(M, "Now look. What is this?", act="point", cam="host", pic="present", sfx="pop")
ask(M, "It's a present! What shape is the present?", act="open", cam="host")
say(LI, "A square!", act="cheer", cam="kids", card="SQUARE")
say(B, "A square present! For my party! Is it for me?", act="yay", cam="cu:bobo", face="happy")
say(M, "Maybe! Here's another square.", act="point", cam="host", pic="window")
ask(M, "What shape is the window?", act="think", cam="host")
say(O, "The window is a square!", act="point", cam="cu:ollie", card="SQUARE")
say(B, "I know one! Is a cookie a square?", act="silly", cam="cu:bobo", pic="cookie")
ask(M, "Hmm. Friends, is a cookie a square?", act="think", cam="host")
say(KIDS, "Nooo! A cookie is a circle!", act="laugh", cam="kids", card="CIRCLE")
say(B, "Oopsie-daisy! Silly Bobo! Cookies are round!", act="silly", cam="cu:bobo", sfx="pop")

# 6 ---------------------------------------------------------------- hide and seek behind the square box
say(B, "Let's play hide and seek! I'll hide behind the square box!", act="cheer", cam="cu:bobo", chapter="Hide and seek")
say(M, "Okay, Bobo! Close your eyes and count to five, friends!", act="open", cam="host", game={"type": "hide", "who": B}, gap_after=0.5)
for i in range(1, 6):
    say([M, LI, O], f"{WORDS[i - 1]}!", act="talk", card=str(i), cam="group", gap_after=0.5)
say(KIDS, "Ready or not, here we come!", act="cheer", cam="kids", sfx="chime")
ask(M, "Where is Bobo? Can you see him?", act="think", cam="group")
say(O, "I see his ears! Behind the box!", act="point", cam="cu:ollie", face="surprised")
ask(M, "And what shape is the box?", act="point", cam="group")
say(KIDS, "A square!", act="cheer", cam="kids", card="SQUARE")
say(KIDS, "Found you, Bobo!", act="point", cam="group")
say(B, "You found me! The square box was too small!", act="yay", cam="cu:bobo", game={"type": "found", "who": B}, face="happy",
    sfx="sparkle")
say(KIDS, "Hee hee hee!", act="laugh", cam="kids")

# 7 ---------------------------------------------------------------- TRIANGLE (+ bouncing the sides)
say(M, "Let's go back inside for our last shape!", act="point", cam="host", chapter="Triangle")
say(M, "Here we are!", act="open", also={LI: "cheer", O: "cheer", B: "cheer"}, cam="group", place="playroom", sfx="sparkle",
    gap_after=0.8)
say(M, "This shape is a triangle!", act="open", cam="host", pic="shape_triangle", card="TRIANGLE", sfx="pop")
ask(M, "Triangle. Can you say triangle?", act="point", cam="host")
say(KIDS, "Triangle!", act="cheer", cam="kids")
say(M, "A triangle has three sides and three pointy corners!", act="count", cam="host", card="3")
say(B, "Can I bounce the sides on my trampoline?", act="jump", cam="cu:bobo", game={"type": "trampoline", "who": B})
say(M, "Yes! Count Bobo's bounces. Three sides!", act="point", cam="group", your_turn=True, gap_after=0.4)
sides(3, who=[M, LI, O], bounce=[B])
say(B, "Three bounces for a triangle! Wheee!", act="bounce", cam="cu:bobo", face="happy", sfx="success")
say(M, "And how many bounces for a square? Four!", act="count", cam="host", card="4")
sides(4, who=[M, LI, O], bounce=[B])
say(B, "Four for a square! I did it!", act="yay", cam="cu:bobo", face="happy", game={"type": "trampoline_off", "who": B})
say(M, "Now look at this. Yum!", act="point", cam="host", pic="pizza", sfx="pop")
ask(M, "It's a slice of pizza! What shape is the pizza?", act="open", cam="host")
say(O, "A triangle!", act="cheer", cam="cu:ollie", card="TRIANGLE")
say(B, "Triangle pizza! For my party! Yum, yum, yum!", act="yay", cam="cu:bobo", face="happy")
say(M, "And here's a sandwich.", act="point", cam="host", pic="sandwich")
ask(M, "What shape is the sandwich?", act="think", cam="host")
say(LI, "A triangle sandwich!", act="cheer", cam="kids", card="TRIANGLE")
say(M, "Let's make a triangle with our arms! Hands up, and touch them together!", act="hands_up",
    also={LI: "hands_up", O: "hands_up", B: "hands_up"}, cam="group", your_turn=True, gap_after=2.0)
say(M, "Great triangles, everybody!", act="thumbs_up", cam="host", sfx="success")

# 8 ---------------------------------------------------------------- shape house
say(M, "Look at this house. It's made of shapes!", act="point", cam="host", pic="house", chapter="The shape house", sfx="pop")
ask(M, "The house has a roof. What shape is the roof?", act="think", cam="host")
say(KIDS, "A triangle!", act="cheer", cam="kids", card="TRIANGLE")
ask(M, "The front of the house is a big...?", act="think", cam="host")
say(O, "Square!", act="cheer", cam="cu:ollie", card="SQUARE")
ask(M, "And the little window at the top is a...?", act="think", cam="host")
say(LI, "Circle!", act="cheer", cam="kids", card="CIRCLE")
say(B, "Wow! A circle, a square, and a triangle make a house!", act="open", cam="cu:bobo", face="surprised")
say(M, "Yes! Shapes are everywhere! Look around your room. Can you find a circle?", act="open", cam="host", your_turn=True,
    gap_after=2.4)
say(M, "Can you find a square?", act="point", cam="host", your_turn=True, gap_after=2.4)
say(M, "Wow! You found shapes! Great looking!", act="clap", cam="host", sfx="sparkle")

# 8b --------------------------------------------------------------- Shape Simon Says
say(M, "Let's play Simon Says with shapes! Do what Simon says!", act="cheer", cam="host", chapter="Shape Simon Says", sfx="chime")
say(M, "Simon says, draw a big circle in the air!", act="point", also={LI: "point", O: "point", B: "point"}, cam="group",
    card="CIRCLE", your_turn=True, gap_after=1.8)
say(M, "Simon says, jump four times, like the four sides of a square!", act="point", cam="host", card="SQUARE", gap_after=0.3)
for i in range(1, 5):
    say(ALL, f"{WORDS[i - 1]}!", act="jump", card=str(i), cam="group", gap_after=0.35)
say(M, "Simon says, make a triangle with your arms!", act="hands_up", also={LI: "hands_up", O: "hands_up", B: "hands_up"},
    cam="group", card="TRIANGLE", your_turn=True, gap_after=1.8)
say(M, "Spin around like a circle!", act="point", cam="host", gap_after=0.8)
say(B, "Wheee! Spinning!", act="spin", cam="cu:bobo", face="happy")
say(KIDS, "Bobo! Simon didn't say!", act="laugh", cam="kids")
say(B, "Oopsie-daisy! Simon didn't say! Silly Bobo!", act="silly", cam="cu:bobo", sfx="pop")
say(M, "Simon says, touch your toes!", act="touch_toes", also={LI: "touch_toes", O: "touch_toes", B: "touch_toes"}, cam="group",
    your_turn=True, gap_after=1.6)
say(M, "Simon says, touch your head!", act="touch_head", also={LI: "touch_head", O: "touch_head", B: "touch_head"}, cam="group",
    your_turn=True, gap_after=1.6)
say(M, "Simon says, be a star! Arms up high!", act="hands_up", also={LI: "hands_up", O: "hands_up", B: "hands_up"}, cam="group",
    card="STAR", your_turn=True, gap_after=1.6)
say(M, "Great listening, everybody!", act="thumbs_up", cam="host", sfx="success")

# 8c --------------------------------------------------------------- Bobo's shape snack
say(B, "All these shapes make me hungry! Snack time!", act="silly", cam="cu:bobo", chapter="Bobo's shape snack", face="happy")
say(M, "Look! Bobo has round cookies. Let's count the circles!", act="point", cam="host", pic="cookie", card="CIRCLE")
for i in range(1, 4):
    say(ALL, f"{WORDS[i - 1]}!", act="count", card=str(i), cam="group", gap_after=0.35)
say(B, "Three circle cookies! I'll eat one! Munch, munch!", act="giggle", cam="cu:bobo", face="happy")
ask(M, "Three cookies, and Bobo ate one. How many circles are left?", act="think", cam="host")
say(LI, "Two!", act="cheer", cam="kids", card="2")
say(M, "Two circle cookies! Well done, Lily!", act="thumbs_up", cam="host")
say(M, "And here's a triangle sandwich!", act="point", cam="host", pic="sandwich", card="TRIANGLE")
say(B, "If I bite the corner, is it still a triangle?", act="think", cam="cu:bobo")
say(KIDS, "Hee hee! No! Now it's a bitten sandwich!", act="laugh", cam="kids")
say(B, "Then I'll eat it all! Yum!", act="laugh", cam="cu:bobo")

# 8d --------------------------------------------------------------- quick shape hunt
say(M, "Quick! Let's play shape hunt! I show it, you shout the shape!", act="cheer", cam="host", chapter="Quick shape hunt",
    sfx="chime")
for pic, shp, who in (("clock", "Circle", LI), ("window", "Square", O), ("pizza", "Triangle", B), ("present", "Square", LI),
                      ("sun", "Circle", O), ("shape_star", "Star", B)):
    ask(M, "What shape is this?", act="point", cam="host", pic=pic, gap_after=1.4)
    say(who, f"{shp}!", act="cheer", cam="cu:bobo" if who == B else ("cu:ollie" if who == O else "kids"), card=shp.upper())
say(M, "Six shapes! You're shape experts!", act="yay", cam="host", card="6", sfx="success")

# 9 ---------------------------------------------------------------- bonus: the star
say(B, "Miss Molly, look! A shape with lots of points!", act="point", cam="cu:bobo", pic="shape_star", chapter="Bonus shape: star",
    sfx="sparkle")
say(M, "That's a star! Twinkle, twinkle!", act="open", cam="host", card="STAR")
ask(M, "Star. Can you say star?", act="point", cam="host")
say(KIDS, "Star!", act="cheer", cam="kids")
ask(M, "Let's count the points on the star!", act="count", cam="host", gap_after=0.4)
sides(5, who=ALL)
say(M, "Five points! A star has five points!", act="hands_up", cam="host", card="5")
ask(O, "Ollie has a star too! Where is my star?", act="point", cam="cu:ollie")
say(LI, "On your shirt!", act="point", cam="kids", card="STAR")
say(O, "My red star!", act="yay", cam="cu:ollie", face="happy")
say(M, "Let's be stars! Arms out, legs out, and shine!", act="hands_up", also={LI: "hands_up", O: "hands_up", B: "hands_up"},
    cam="group", your_turn=True, gap_after=1.6)

# 9b --------------------------------------------------------------- colours and shapes
say(M, "Shapes have colors too! Let's play colors and shapes!", act="cheer", cam="host", chapter="Colors and shapes", sfx="chime")
for pic, col, shp, who in (("shape_circle", "red", "circle", LI), ("shape_square", "blue", "square", O),
                           ("shape_triangle", "yellow", "triangle", B), ("shape_star", "orange", "star", LI)):
    ask(M, "What color is this shape? And what shape is it?", act="point", cam="host", pic=pic, gap_after=1.8)
    say(who, f"A {col} {shp}!", act="cheer", cam="cu:bobo" if who == B else ("cu:ollie" if who == O else "kids"),
        card=shp.upper())
    say(M, f"Yes! A {col} {shp}! Great job!", act="thumbs_up", cam="host")
say(B, "I know! I'm a brown circle bear!", act="silly", cam="cu:bobo", face="happy")
say(KIDS, "Hee hee hee!", act="laugh", cam="kids")

# 9c --------------------------------------------------------------- Ollie hides behind the square box
say(O, "My turn to hide! Count to five!", act="cheer", cam="cu:ollie", chapter="Ollie hides")
say(M, "Okay, Ollie! Hide behind the square box!", act="open", cam="host", game={"type": "hide", "who": O}, gap_after=0.5)
for i in range(1, 6):
    say([M, LI, B], f"{WORDS[i - 1]}!", act="talk", card=str(i), cam="group", gap_after=0.5)
say(B, "Ready or not! Hmm. Is Ollie inside the circle clock?", act="think", cam="cu:bobo", pic="clock")
say(KIDS, "Nooo!", act="laugh", cam="kids")
say(B, "Is he inside the triangle pizza?", act="silly", cam="cu:bobo", pic="pizza")
say(LI, "Nooo, Bobo! Look at the square box!", act="point", cam="kids", card="SQUARE")
say(B, "I see his hair! Found you, Ollie!", act="point", cam="cu:bobo", face="surprised")
say(O, "You found me!", act="yay", cam="cu:ollie", game={"type": "found", "who": O}, face="happy", sfx="sparkle")

# 9d --------------------------------------------------------------- draw with shapes
say(M, "Let's draw pictures with shapes!", act="cheer", cam="host", chapter="Draw with shapes")
say(M, "First, a big circle. Then lines all around it. What is it?", act="point", cam="host", card="CIRCLE", gap_after=1.6)
say(LI, "The sun!", act="cheer", cam="kids", pic="sun")
say(M, "Yes! A circle makes the sun! Now, a square, and a triangle on top. What is it?", act="point", cam="host",
    card="SQUARE", gap_after=1.8)
say(O, "A house!", act="cheer", cam="cu:ollie", pic="house")
say(M, "A square and a triangle make a house!", act="thumbs_up", cam="host", card="TRIANGLE")
say(B, "Now me! A triangle, with red circles on it. What is it?", act="point", cam="cu:bobo", gap_after=1.8)
say(KIDS, "Pizza!", act="yay", cam="kids", pic="pizza")
say(B, "Pizza! For my party! Yum!", act="yay", cam="cu:bobo", face="happy")
ask(M, "What will you draw with shapes? Get some paper and try it!", act="open", cam="host", pic="paint", your_turn=True,
    gap_after=2.2)

# 10 --------------------------------------------------------------- shape song
say(M, "Let's sing the shape song! Clap with me!", act="clap", also={LI: "clap", O: "clap", B: "clap"}, cam="group",
    chapter="Shape song", gap_after=0.6)
SONG = "A circle is round like a ball! A square has four sides, one and all! A triangle has three, can you see? Shapes, shapes, for you and me!"
say(ALL, SONG, chant=True, act="beatclap", cam="group", word_cards=SHAPE_CARDS)
say(M, "Again! Sing with us!", act="cheer", cam="host", gap_after=0.5)
say(ALL, SONG, chant=True, act="beatclap", cam="group", word_cards=SHAPE_CARDS, gap_after=0.8)
say(B, "One more time! It's my birthday!", act="jump", cam="cu:bobo", gap_after=0.5)
say(ALL, SONG, chant=True, act="dance", cam="group", word_cards=SHAPE_CARDS, gap_after=0.8)
say(KIDS, "Yay!", act="yay", also={B: "yay", M: "cheer"}, cam="group", sfx="success")

# 11 --------------------------------------------------------------- shape freeze dance
say(M, "Now it's the shape freeze dance! Dance, and when I show a shape, freeze!", act="cheer", cam="host",
    chapter="Shape freeze dance")
say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", cam="group", gap_after=0.3)
say(M, "Freeze! Circle!", act="freeze", also={LI: "freeze", O: "freeze", B: "wobble"}, cam="group", card="CIRCLE", sfx="pop",
    gap_after=1.2)
say(B, "I can't freeze! I'm a wobbly birthday bear!", act="wobble", cam="cu:bobo", face="happy")
say(KIDS, "Hee hee hee!", act="laugh", cam="kids")
say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", cam="group", gap_after=0.3)
say(M, "Freeze! Square!", act="freeze", also={LI: "freeze", O: "freeze", B: "freeze"}, cam="group", card="SQUARE", sfx="pop",
    gap_after=1.2)
say(B, "I froze! Look at me!", act="freeze", cam="cu:bobo")
say(ALL, "Dance, dance, dance! Wiggle, wiggle, wiggle!", chant=True, act="dance", cam="group", gap_after=0.3)
say(M, "Freeze! Triangle!", act="freeze", also={LI: "freeze", O: "wobble", B: "freeze"}, cam="group", card="TRIANGLE", sfx="pop",
    gap_after=1.2)
say(O, "Whoa! Wobble, wobble!", act="wobble", cam="cu:ollie")
say(KIDS, "Hee hee!", act="laugh", cam="kids")
say(M, "Great dancing! Now take a big breath. In, and out.", act="open", cam="host", gap_after=1.2)

# 12 --------------------------------------------------------------- the party
say(M, "Bobo, your party is ready!", act="open", cam="host", chapter="Bobo's shape party", sfx="success")
ask(M, "We have round cookies. What shape?", act="point", cam="host", pic="cookie")
say(KIDS, "Circle!", act="cheer", cam="kids", card="CIRCLE")
ask(M, "Square presents. What shape?", act="point", cam="host", pic="present")
say(KIDS, "Square!", act="cheer", cam="kids", card="SQUARE")
ask(M, "And triangle pizza. What shape?", act="point", cam="host", pic="pizza")
say(KIDS, "Triangle!", act="cheer", cam="kids", card="TRIANGLE")
say(B, "The best shape party ever! Thank you, friends!", act="thumbs_up", cam="cu:bobo", face="happy")
say(M, "Let's sing happy birthday to Bobo!", act="cheer", cam="group", gap_after=0.5)
say(ALL, "Happy birthday, Bobo bear! Happy birthday, everywhere!", chant=True, act="beatclap", cam="group", gap_after=0.6)
say(ALL, "Happy birthday, Bobo bear! Happy birthday, everywhere!", chant=True, act="dance", cam="group", gap_after=0.6)
say(B, "Party balloons! Pop, pop, pop!", act="bounce", cam="group",
    game={"type": "balloons", "colors": ["yellow", "red", "blue"]}, face="happy", gap_after=2.6)
say(KIDS, "Hooray!", act="yay", also={M: "cheer"}, cam="group", sfx="sparkle")

# 13 --------------------------------------------------------------- quiz + goodbye
say(M, "Let's play a quick shape quiz!", act="cheer", cam="host", chapter="Shape quiz and goodbye", sfx="chime")
ask(M, "What shape is round, with no corners?", act="spin", cam="host")
say(LI, "A circle!", act="cheer", cam="kids", card="CIRCLE")
ask(M, "What shape has three sides?", act="count", cam="host")
say(B, "A banana!", act="silly", cam="cu:bobo", pic="banana")
say(KIDS, "Nooo! A triangle!", act="laugh", cam="kids", card="TRIANGLE")
say(B, "Hee hee! I'm joking! A triangle has three sides!", act="laugh", cam="cu:bobo")
ask(M, "What shape has four sides, all the same?", act="count", cam="host")
say(O, "A square!", act="cheer", cam="cu:ollie", card="SQUARE")
say(M, "You know all your shapes! Circle, square, triangle!", act="thumbs_up", cam="host", sfx="success")
say(M, "Next time, we'll visit the farm and meet the animals! Moo!", act="point", cam="host")
say(B, "The farm? Do cows say woof?", act="silly", cam="cu:bobo")
say(KIDS, "Nooo! Cows say moo!", act="laugh", cam="kids")
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
