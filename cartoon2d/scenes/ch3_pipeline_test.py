"""A ~25 s two-place story to test the .kidstory pipeline (pack -> app Generate -> Render). Not an episode."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ch3 import Episode, LINA, TOBI, ROSIE, FIZZ  # noqa: E402

BG = "cartoon2d/art/bg/ch3e1_{}.png"
ep = Episode("ch3_pipeline_test", goal=("duckling", 1), hero=TOBI, giver="mama_duck")
ep.place("gate", BG.format("gate"), [LINA, TOBI, ROSIE, FIZZ])
ep.place("slide", BG.format("hill"), [LINA, TOBI, ROSIE, FIZZ], rides={TOBI: "slide"})
ep.say(FIZZ, "Oh no! A little duckling is lost!", act="hands_up", place="gate", cam="group", pic="mama_duck", goal=True)
ep.want(TOBI, "I want to find it! But the big slide is scary.", act="wobble")
ep.say(LINA, "Let's go and look, one little step at a time!", act="open", cam="host", title="Test\nStory!")
ep.arrive("slide", "The big slide!", "Slide\nTime!")
ep.stuck(ROSIE, "There it is, at the top of the slide!", at=("slide", TOBI))
ep.say(TOBI, "I'll climb up and bring it down! Wheee!", act="cheer", game={"type": "slide", "who": TOBI}, cam="group", gap_after=0.8)
ep.found(TOBI, "Got it! I did it!", fx="stars")
ep.ask(LINA, "Can you say brave? Brave!", act="cheer", cam="host", card="BRAVE")
ep.say([LINA, TOBI, ROSIE, FIZZ], "Bye bye, friends!", act="wave", cam="group", endcard="Bye bye!")
ep.write()
