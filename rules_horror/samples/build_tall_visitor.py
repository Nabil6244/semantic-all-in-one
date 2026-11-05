"""Builds samples/the_tall_visitor.csv and the_tall_visitor_script.txt from one list of rows, so the CSV's `line` cells are exactly the story, in order.
An original story (own creature, names and places). Run: python3 rules_horror/samples/build_tall_visitor.py"""
import csv
from pathlib import Path

H = "order,section,line,set,shot,subject,pose,action,tag,value,prompt".split(",")
R = []
def row(section, line, st="", shot="wide", subject="", pose="", action="", tag="", value="", prompt=""):
    R.append([section, line, st, shot, subject, pose, action, tag, value, prompt])
D = "deer"
# ---- hook
row("hook", "If you ever wake up at three in the morning,", "cutaway", "wide", "", "", "figure_sleep", "", "3:00 AM")
row("hook", "and see a deer standing in your yard,", "yard", "wide", D, "stand_side", "figure_look", "YOU")
row("hook", "do not wave.", "window", "push_in", D, "stand_side", "figure_look")
row("hook", "Do not call out to it.", "window", "pull_out", D, "stare", "sight_line+cross")
row("hook", "And whatever you do, do not turn on a light.", "bedroom", "wide", "", "", "figure_sit+bubble", "YOU", "NO LIGHTS")
# ---- narrowing
row("narrowing", "I am not talking about a normal deer.", "yard", "wide", D, "walk")
row("narrowing", "A normal deer bolts the moment a porch door opens.", "street", "wide", D, "walk")
row("narrowing", "This one has stood in the same patch of grass for three nights.", "yard", "wide", D, "stand_front", "prop_cctv", "", "CAM 02 FRONT YARD")
row("narrowing", "It is far too tall, with legs that bend in all the wrong places,", "yard", "pull_out", D, "stand_side")
row("narrowing", "and it never once lowers its head to eat.", "yard", "push_in", D, "head_low")
row("narrowing", "The first night I told myself it was lost.", "street", "wide", D, "stand_side", "figure_stand", "YOU")
row("narrowing", "The second night I stopped telling myself anything.", "prop", "wide", "", "", "prop_clock", "", "3:07")
row("narrowing", "Every house on my street was dark, and every window faced the same way.", "cutaway", "wide", D, "stand_side", "figure_sit")
# ---- turn
row("turn", "The strangest part is where it looks.", "window", "wide", D, "head_turned", "figure_look", "YOU")
row("turn", "It is not looking at your house.", "hall_lit", "push_in", D, "stare", "figure_look")
row("turn", "It is looking at something just behind you.", "window", "push_in", D, "stare", "sight_line", "YOU")
row("turn", "My grandmother called them the Watchers, and she kept a list.", "hallway", "wide", "", "", "figure_walk", "YOU")
row("turn", "I asked around, and nobody else had seen it, or nobody else would say so.", "hallway", "push_in", "", "", "figure_walk")
row("turn", "That is when I found her list, folded inside an old bible.", "prop", "wide", "", "", "prop_paper", "", "THE LIST", "1. do not turn on the lights|2. do not count its legs|3. do not answer the door")
row("turn", "Seven lines in pencil, and the third one was underlined twice.", "bedroom", "push_in", "", "", "figure_sit")
# ---- promise
row("promise", "Follow these seven rules and you will see the sun come up.", "house_section", "wide", "", "", "figure_sit+countdown", "", "5")
row("promise", "Most people break the third one,", "house_section", "push_in", "", "", "figure_sit", "YOU")
row("promise", "because it sounds like someone you love.", "house_section", "pull_out", "", "", "figure_flinch")
# ---- rules
def rule(n, text, body):
    row("rule", text, "card", "", "", "", "rule_card", "", str(n))
    for b in body:
        row(*b) if isinstance(b, tuple) else None
B = lambda sec, line, *a, **k: (sec, line) + a
rule(1, "Do not turn on the lights.", [
    ("rule", "Light tells it exactly where you are.", "bedroom", "wide", "", "", "figure_sit", "YOU"),
    ("rule", "Even a phone screen counts, so turn it face down and keep it there.", "prop", "push_in", "", "", "prop_phone", "", "", "them:are you awake|them:i can see your light"),
    ("rule", "A man named Hale, two streets over, flicked on his porch bulb.", "street", "wide", D, "stand_side"),
    ("rule", "The deer turned its head all the way around,", "yard", "push_in", D, "head_turned"),
    ("rule", "Hale says it was only a second, and the second is still going.", "yard", "wide", D, "stand_front"),
    ("rule", "Now his whole street leaves its curtains open, in case it looks back.", "crowd", "wide", "", "", "crowd_turn", "", "NORMAL"),
    ("scare", "and Hale's porch has been dark ever since.", "closeup", "push_in", D, "close_up_face", "glitch", "", "", "a long white deer face staring straight into the camera, pure black background"),
])
rule(2, "Do not count its legs.", [
    ("rule", "Everyone wants to. The legs are wrong, and you want to prove it.", "window", "push_in", D, "stand_front", "figure_look", "YOU"),
    ("rule", "A woman at my old job counted them out loud.", "window", "wide", D, "stand_side", "figure_look"),
    ("rule", "The number keeps changing, which is how it keeps you counting.", "window", "push_in", D, "walk", "figure_look"),
    ("rule", "She got to nine, and then she stopped getting to anything.", "window", "pull_out", D, "walk", "figure_flinch"),
    ("rule", "If you have to look, look at its head and nowhere lower.", "window", "wide", D, "stare", "figure_look", "YOU"),
])
rule(3, "Do not answer the door.", [
    ("rule", "Around four it will knock, three soft taps.", "door", "wide", "", "", "figure_flinch"),
    ("rule", "Then it speaks, and it uses a voice you know.", "door", "push_in", "", "", "figure_flinch", "", "", ""),
    ("rule", "Three taps, a pause, and then a fourth that does not belong to the rhythm.", "door", "wide", "", "", "figure_flinch"),
    ("rule", "Your mother. Your brother. The friend who moved away.", "hallway", "wide", "", "", "figure_walk", "YOU"),
    ("rule", "It will say it is cold. It will say please.", "door", "push_in", D, "stand_front", "figure_flinch"),
    ("rule", "My cousin opened it and said it was only for a second.", "door", "wide", D, "stand_side", "figure_flinch"),
    ("rule", "We still set a place for him, and nobody sits there.", "classroom", "wide", "", "", "figure_sit"),
    ("scare", "It has never once got the pause right between the words.", "closeup", "push_in", D, "close_up_face", "glitch", "", "", "a grinning white face with far too many teeth filling the frame, pure black background"),
])
rule(4, "If it moves, stay exactly where you are.", [
    ("rule", "The first night it stands at the fence.", "yard", "wide", D, "stand_side"),
    ("rule", "The second night it stands at the porch.", "yard", "push_in", D, "walk"),
    ("rule", "The third night it is simply closer, and you never see it move.", "yard", "wide", D, "stand_front"),
    ("rule", "Do not measure the distance. Distance is the whole game.", "yard", "pull_out", D, "stand_front", "countdown", "", "3"),
    ("rule", "Count the seconds instead, and count them slowly.", "yard", "wide", D, "stand_side", "countdown", "", "3"),
    ("rule", "If you run, it learns that you can be made to run.", "hallway", "push_in", "", "", "figure_run"),
    ("rule", "Stillness is the only thing it has never learned to copy.", "bedroom", "pull_out", "", "", "figure_sit", "YOU"),
    ("rule", "It can learn your voice and your walk, but not how long you can wait.", "bedroom", "push_in", "", "", "figure_sit"),
])
rule(5, "Do not speak to anyone who says they are outside.", [
    ("rule", "Your phone will light up with a neighbour's name.", "bedroom", "wide", "", "", "figure_sit", "YOU", "NEW MESSAGE"),
    ("rule", "They will say they can see it too and ask you to come out.", "bedroom", "push_in", "", "", "figure_sit", "YOU"),
    ("rule", "Their messages are perfect, with every comma in its place.", "bedroom", "wide", "", "", "figure_sit"),
    ("rule", "My sister replied once, from a bed three towns away.", "bedroom", "push_in", "", "", "figure_flinch"),
    ("rule", "She said she was fine, and I believed her, and that was the mistake.", "classroom", "wide", "", "", "figure_sit"),
    ("rule", "Your neighbours are asleep. They are always asleep.", "window", "wide", D, "stand_side", "figure_look"),
    ("rule", "If you reply, the typing dots start, and they never stop.", "bedroom", "push_in", "", "", "figure_flinch", "", "", ""),
])
rule(6, "Do not follow the sound of your name.", [
    ("rule", "It calls from the hallway, then from the stairs, then from the walls.", "hallway", "push_in", "", "", "figure_walk", "YOU"),
    ("rule", "The voice is warm and a little out of breath.", "hallway", "wide", "", "", "figure_flinch"),
    ("rule", "It sounds like someone running up the stairs to tell you good news.", "hallway", "push_in", "", "", "figure_walk"),
    ("rule", "Give it nothing. Not a word, not a breath, not a turn of the head.", "bedroom", "wide", "", "", "figure_sit", "YOU"),
    ("rule", "A voice that is looking for you has never needed to ask where you are.", "house_section", "wide", "", "", "figure_sit", "YOU"),
    ("scare", "Stay in bed, and let it say your name until it forgets how.", "closeup", "push_in", D, "close_up_face", "glitch", "", "", "two pale eyes in total darkness staring at the viewer, pure black background"),
])
rule(7, "Do not sleep until the sun is fully up.", [
    ("rule", "Sunrise is a promise, and it keeps it.", "window", "wide", D, "stand_side", "figure_look", "YOU"),
    ("rule", "The yard will empty a little before the light arrives.", "yard", "pull_out", D, "walk"),
    ("rule", "Not all at once. It leaves the way a held breath leaves.", "yard", "wide", D, "look_back"),
    ("rule", "Wait for the birds. Wait for the first car. Wait.", "bedroom", "push_in", "", "", "figure_sit", "YOU"),
    ("rule", "My grandmother waited eleven years of mornings like that.", "house_section", "wide", "", "", "figure_sit"),
    ("rule", "She was never once found in the yard.", "yard", "wide", D, "stand_side"),
])
# ---- twist
row("twist", "There is one thing I have not told you yet.", "bedroom", "wide", "", "", "figure_sit", "YOU", "3:02 AM")
row("twist", "After the third night I stopped being afraid of the deer.", "window", "push_in", D, "stand_side", "figure_look")
row("twist", "Because I finally worked out what it was looking at.", "window", "wide", D, "head_turned", "figure_look", "YOU")
row("twist", "Something had been living in my house longer than I had.", "house_section", "wide", "", "", "figure_sit")
row("twist", "It moved when I slept. It stood where I stood.", "hallway", "wide", "", "", "figure_walk", "YOU")
row("twist", "Every night it practised how to look like me,", "hallway", "push_in", "", "", "figure_walk")
row("twist", "It got the way I tilt my head, and the way I hold a door.", "hallway", "wide", "", "", "figure_walk")
row("twist", "It learned the sound I make when I clear my throat.", "house_section", "wide", "", "", "figure_sit")
row("twist", "and every night the deer stood in the yard, watching it,", "yard", "wide", D, "stare", "sight_line")
row("twist", "close enough to be seen and far enough not to be reached.", "yard", "push_in", D, "stand_front")
row("twist", "The deer was never the danger. The deer was the warning.", "yard", "pull_out", D, "stand_side", "cross")
row("twist", "Think about it. A predator would hide.", "yard", "wide", D, "walk")
row("twist", "The deer stood in the open, under the moon, so that I would look.", "yard", "push_in", D, "stand_front")
row("twist", "I watched my own bedroom light flicker on, and I was in bed.", "bedroom", "wide", "", "", "figure_sleep", "YOU", "3:04 AM")
row("twist", "I was lying there, and I was also the one standing at the switch.", "bedroom", "push_in", "", "", "figure_flinch", "YOU")
row("twist", "That is when the deer turned and looked at me for the first time.", "window", "wide", D, "stare", "sight_line", "YOU")
row("twist", "It did not look angry. It looked sorry.", "window", "push_in", D, "stand_front")
row("twist", "Then I understood the seventh rule, and why my grandmother never slept.", "house_section", "push_in", "", "", "figure_sit")
row("twist", "It is not the deer you have to outlast. It is the other one.", "hallway", "wide", "", "", "figure_walk", "YOU")
row("twist", "The one that wears your sleep like a coat and waits for you to forget.", "bedroom", "pull_out", "", "", "figure_sleep", "YOU", "3:05 AM")
row("twist", "I scratched the list into the bedpost, one rule for every night.", "bedroom", "push_in", "", "", "figure_sit")
row("twist", "Not to keep it out, because it was never outside.", "window", "wide", D, "head_low", "figure_look")
row("twist", "Only to remind the one in the bed which of us is real.", "bedroom", "wide", "", "", "figure_sit", "YOU")
row("scare", "And behind me, very softly, someone said my name.", "closeup", "push_in", D, "close_up_face", "glitch", "", "", "a pale blank face, almost human, with a thin wrong smile, pure black background")
# ---- close
row("close", "So if you ever wake up at three in the morning", "bedroom", "wide", "", "", "figure_sleep", "", "3:00 AM")
row("close", "and see a deer standing in your yard,", "window", "push_in", D, "stand_side", "figure_look", "YOU")
row("close", "stay in bed, keep the lights off,", "bedroom", "pull_out", "", "", "figure_sit")
row("close", "and be very kind to the deer.", "window", "wide", D, "look_back", "figure_look")
row("close", "It is the only one who has been watching out for you.", "yard", "wide", D, "stand_side")

# rule() helper tuples: first two fields are (section, line)
out = Path(__file__).parent
with open(out / "the_tall_visitor.csv", "w", newline="", encoding="utf-8") as f:
    f.write('#subject,deer,"tall deer, long thin legs, antlers"\n#location,house,yard\n')
    w = csv.writer(f); w.writerow(H)
    for i, r in enumerate(R, 1):
        w.writerow([i] + r + [""] * (10 - len(r)))
(out / "the_tall_visitor_script.txt").write_text(" ".join(r[1] for r in R) + "\n", encoding="utf-8")
print(len(R), "rows;", sum(len(r[1].split()) for r in R), "words")
