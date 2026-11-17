"""Engaging v2 rewrites of five Flow-painted Toon Tales stories (the v1 scripts ran ~32 s / ~110 words; the
reference style runs ~50-60 s with more true, surprising details, open loops and a twist that loops back).
Keeps each story's painted places. python3 toontales/stories/engaging_v2.py [story_id ...] -> stories/<id>/plan.json
(the v1 plan stays as plan_v1.json)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def acts(spec):
    """'sneak money@1.2 walk>1.2,0 fall:right' -> acts list; no @ = spaced 1.1 s apart."""
    out = []
    for i, tok in enumerate(spec.split()):
        params = None
        at = round(i * 1.1, 2)
        if "@" in tok:
            tok, a = tok.split("@")
            at = float(a)
        if ">" in tok:
            tok, to = tok.split(">")
            params = {"to": [float(v) for v in to.split(",")]}
        if ":" in tok:
            tok, side = tok.split(":")
            params = {"side": side}
        a ={"do": tok, "at": at}
        if params:
            a["params"] = params
        out.append(a)
    return out


def cast(spec):
    return [{"id": who, "mark": mark, "acts": acts(a)} for who, mark, a in (p.split(":", 2) for p in spec.split("|") if p)]


def held(kind, who, text=None):
    d = {"type": kind, "held_by": who}
    return d | ({"text": text} if text else {})


def picked(kind, who, text=None):
    d = {"type": kind, "picked_by": who}
    return d | ({"text": text} if text else {})


def spot(kind, where, text=None):
    d = {"type": kind, "spot": where}
    return d | ({"text": text} if text else {})


def ov(kind, text=None):
    return {"type": kind} | ({"text": text} if text else {})


def sfx(*pairs):
    return [{"name": n, "at": a} for n, a in pairs]


def shot(beat, speaker, place, cam, move, text, who, props=(), overlay=None, sounds=(), **kw):
    s = {"beat": beat, "speaker": speaker, "text": text, "set": place, "camera": cam, "move": move,
         "cast": cast(who), "props": list(props), "sfx": list(sounds), "transition": "cut"}
    if overlay:
        s["overlay"] = overlay
    s.update(kw)
    return s


N = "narrator"
STORIES = {}

# ---------------------------------------------------------------- lemon juice robber
STORIES["lemon_robber"] = dict(
    hook_title="LEMON JUICE = INVISIBLE?",
    keywords=["lemon", "juice", "invisible", "camera", "banks", "news", "Dunning", "Kruger", "Polaroid", "blank"],
    sources=["https://en.wikipedia.org/wiki/Dunning%E2%80%93Kruger_effect"],
    shots=[
        shot("hook", N, "bank", "two_shot", "push", "In 1995, a man robbed two banks in broad daylight.",
             "walt:A:sneak money@1.4|pip:C:shock@0.6", [held("sack", "walt")], sounds=sfx(("cash", 0.9))),
        shot("hook", N, "bank", "close", "crash_zoom", "No mask. No hood. He even smiled at the cameras.",
             "walt:A:laugh wave@1.3", overlay=ov("circle", "CAMERA")),
        shot("hook", "pip", "bank", "close", "crash_zoom", "Why would anyone do that?", "pip:C:scratch_head think@1.0"),
        shot("concept", N, "street", "medium", "push", "His name was McArthur Wheeler, and he had a secret.",
             "walt:A:hips sneak@1.3", overlay=ov("label", "MCARTHUR WHEELER")),
        shot("concept", N, "kitchen", "insert", "push", "Lemon juice.", "walt:A:pick_up present@1.0",
             [picked("bottle", "walt", "LEMON JUICE")], sounds=sfx(("pop", 0.6))),
        shot("setup", N, "kitchen", "medium", "push", "His friends said lemon juice works as invisible ink.",
             "walt:A:hold nod@1.2", [held("letter", "walt", "INVISIBLE INK")]),
        shot("setup", "walt", "kitchen", "close", "crash_zoom", "So it'll make my face invisible!",
             "walt:A:point money@1.0"),
        shot("setup", N, "kitchen", "medium", "push", "He rubbed it all over his face, then took a Polaroid selfie.",
             "walt:A:tremble facepalm@1.4", overlay=ov("chalk", "POLAROID TEST")),
        shot("obstacle", N, "kitchen", "close", "crash_zoom", "The photo came out blank.", "walt:A:shock celebrate@0.8",
             overlay=ov("stamp", "BLANK"), sounds=sfx(("ding", 0.3))),
        shot("obstacle", "pip", "street", "close", "push", "You're invisible!", "pip:B:cheer jump@0.6"),
        shot("con", N, "bank", "wide", "pan_r", "So he walked into a bank and looked straight at the camera.",
             "walt:enter_l:walk>1.4,0 wave@1.7", sounds=sfx(("door", 0.1))),
        shot("con", N, "bank", "close", "crash_zoom", "Took the cash.", "walt:A:pick_up money@0.9",
             [picked("money", "walt")], sounds=sfx(("cash", 0.7))),
        shot("con", N, "street", "wide", "pan_l", "Then robbed a second bank.", "walt:A:run>-2,0",
             [held("sack", "walt")], sounds=sfx(("footsteps", 0.1))),
        shot("con", N, "street", "medium", "push", "Same day. Same smile.", "walt:A:laugh money@0.9", freeze="WAIT..."),
        shot("escalate", N, "newsroom", "medium", "push", "That night, the bank footage played on the eleven o'clock news.",
             "pip:B:hold shock@1.2", [spot("board", "wall_r", "BREAKING NEWS")]),
        shot("escalate", N, "newsroom", "close", "crash_zoom", "Viewers recognised him right away.", "pip:B:point shock@0.9",
             overlay=ov("stamp", "TIP"), sounds=sfx(("ding", 0.4))),
        shot("twist", N, "police", "medium", "push", "Police arrested him that same night.", "walt:A:shock tremble@0.8",
             overlay=ov("stamp", "ARRESTED")),
        shot("twist", N, "police", "close", "crash_zoom", "When they showed him the tapes, he was stunned.",
             "walt:A:shock dizzy@1.0"),
        shot("twist", "walt", "police", "close", "push", "But I wore the juice!", "walt:A:plead angry@0.8"),
        shot("payoff", N, "university", "medium", "push", "A psychology professor, David Dunning, read about the case.",
             "pip:A:think nod@1.2", overlay=ov("label", "DAVID DUNNING")),
        shot("payoff", N, "university", "medium", "push", "Can people be too clueless to know they're clueless?",
             "pip:A:scratch_head shrug@1.2", overlay=ov("chalk", "TOO CLUELESS TO KNOW?")),
        shot("payoff", N, "university", "insert", "crash_zoom", "That question became the famous Dunning-Kruger effect.",
             "pip:A:hold nod@1.2", [held("board", "pip", "DUNNING-KRUGER")], sounds=sfx(("ding", 0.5))),
        shot("payoff", "pip", "bank", "two_shot", "push", "So lemon juice doesn't work?",
             "pip:C:scratch_head|walt:A:look_around"),
        shot("payoff", "walt", "bank", "close", "crash_zoom", "Not on a camera, Pip.", "walt:A:sneak point_you@0.7"),
    ])

# ---------------------------------------------------------------- the man who sold the Eiffel Tower
STORIES["eiffel_sale"] = dict(
    hook_title="HE SOLD THE EIFFEL TOWER?",
    keywords=["tower", "scrap", "Lustig", "Poisson", "bribe", "Capone", "Alcatraz", "twice", "secret"],
    sources=["https://en.wikipedia.org/wiki/Victor_Lustig"],
    shots=[
        shot("hook", N, "tower", "two_shot", "push", "In 1925, a man sold the Eiffel Tower. Twice.",
             "walt:A:present money@1.3|pip:C:shock@0.6", [held("money", "walt")], sounds=sfx(("cash", 1.0))),
        shot("hook", "pip", "tower", "close", "crash_zoom", "Wait. How do you sell a tower?", "pip:C:scratch_head think@1.0"),
        shot("concept", N, "tower", "medium", "push", "Meet Victor Lustig, maybe the smoothest con man ever.",
             "walt:A:hips sneak@1.3", overlay=ov("label", "VICTOR LUSTIG")),
        shot("concept", N, "hotel", "insert", "push", "He read that the tower was rusting and cost a fortune to fix.",
             "walt:A:hold nod@1.3", [held("newspaper", "walt", "TOWER TOO COSTLY?")]),
        shot("setup", "walt", "hotel", "close", "crash_zoom", "Then let's sell it for scrap!", "walt:A:point_you money@0.9"),
        shot("setup", N, "hotel", "medium", "drift", "He forged official government letters.",
             "walt:A:pick_up present@1.2", [picked("letter", "walt", "GOVERNMENT OF FRANCE")], sounds=sfx(("paper", 0.6))),
        shot("setup", N, "hotel", "wide", "pan_r", "And invited six scrap dealers to a fancy hotel.",
             "walt:enter_l:walk>1.2,0 present@1.7|pip:C:look_around", overlay=ov("chalk", "6 DEALERS")),
        shot("deadline", N, "hotel", "close", "push", "Keep it secret, he warned, or Paris will riot.",
             "walt:A:sneak point_you@1.1"),
        shot("con", N, "tower", "wide", "tilt_up", "Seven thousand tons of iron, up for grabs.",
             "pip:B:money celebrate@1.0", overlay=ov("chalk", "7,000 TONS")),
        shot("con", N, "office", "medium", "push", "One dealer, André Poisson, wanted it badly.",
             "pip:B:money cheer@1.1", overlay=ov("label", "ANDRE POISSON")),
        shot("obstacle", N, "office", "close", "push", "But his wife smelled a rat.", "pip:B:think scratch_head@0.9",
             overlay=ov("stamp", "SUSPICIOUS")),
        shot("obstacle", "pip", "office", "close", "crash_zoom", "Hmm. This feels fishy.", "pip:B:think shrug@0.8"),
        shot("con", N, "office", "medium", "push", "So Lustig made a confession. He was a crooked official.",
             "walt:A:sneak shrug@1.2", freeze="WAIT..."),
        shot("con", "walt", "office", "close", "crash_zoom", "I need a little bribe.", "walt:A:money point_you@0.7"),
        shot("con", N, "tower", "two_shot", "orbit_r", "Now Poisson believed him. Crooks take bribes!",
             "pip:C:nod money@0.9|walt:A:laugh", [held("money", "pip")]),
        shot("escalate", N, "train", "wide", "pan_l", "Lustig grabbed a suitcase of cash and fled to Vienna.",
             "walt:A:run>-2.4,0", [held("sack", "walt")], sounds=sfx(("train", 0.2))),
        shot("escalate", N, "train", "close", "crash_zoom", "Then he waited for the police.", "walt:A:look_around tremble@1.0"),
        shot("escalate", N, "train", "medium", "push", "They never came.", "walt:A:laugh money@0.7"),
        shot("twist", N, "office", "close", "pull", "Poisson was too embarrassed to report it.", "pip:C:facepalm sad@1.0",
             overlay=ov("stamp", "SILENT")),
        shot("twist", N, "hotel", "medium", "push", "So Lustig came back and sold it again!", "walt:A:sneak money@1.0",
             overlay=ov("chalk", "AGAIN?!")),
        shot("twist", N, "hotel", "close", "crash_zoom", "This time, the buyer went to the police.", "walt:A:shock cower@0.9",
             sounds=sfx(("gasp", 0.4))),
        shot("payoff", N, "hotel", "medium", "push", "He escaped to America and even conned Al Capone.",
             "walt:A:present laugh@1.2", overlay=ov("label", "AL CAPONE")),
        shot("payoff", N, "prison", "wide", "tilt_down", "His fake money finally landed him in Alcatraz.",
             "walt:A:shock sad@1.1", overlay=ov("label", "ALCATRAZ")),
        shot("payoff", "pip", "tower", "two_shot", "push", "So the tower was never for sale?",
             "pip:B:scratch_head|walt:A:look_around"),
        shot("payoff", "walt", "tower", "close", "crash_zoom", "Shh. Wanna buy a tower?", "walt:A:sneak point_you@0.7"),
    ])

# ---------------------------------------------------------------- the emu war
STORIES["emu_war"] = dict(
    hook_title="AN ARMY LOST TO BIRDS?",
    keywords=["emus", "army", "machine", "guns", "bullets", "truck", "jammed", "tanks", "bounties", "wheat"],
    sources=["https://en.wikipedia.org/wiki/Emu_War"],
    shots=[
        shot("hook", N, "field", "two_shot", "push", "In 1932, Australia sent soldiers to fight birds.",
             "walt:A:point shock@1.2|pip:C:cower", overlay=ov("stamp", "EMU WAR")),
        shot("hook", N, "field", "close", "crash_zoom", "And the birds won.", "walt:A:facepalm sad@0.8"),
        shot("hook", "pip", "field", "close", "crash_zoom", "Wait. How do you lose to birds?", "pip:C:scratch_head think@1.0"),
        shot("concept", N, "farmhouse", "wide", "pan_r", "After World War One, soldiers were given land to grow wheat.",
             "pip:A:pick_up present@1.3", [picked("sack", "pip")]),
        shot("concept", N, "field", "medium", "push", "Then twenty thousand emus showed up.", "pip:A:shock tremble@0.9",
             overlay=ov("chalk", "20,000 EMUS")),
        shot("setup", N, "field", "wide", "pan_l", "They ate the wheat and trampled the fences.", "pip:A:angry fall:right@1.0"),
        shot("setup", "pip", "farmhouse", "close", "crash_zoom", "Send the army!", "pip:A:plead angry@0.7"),
        shot("setup", N, "army", "medium", "push", "So the army sent Major Meredith with two machine guns.",
             "walt:A:present fist_pump@1.3", [held("gun", "walt")], overlay=ov("label", "MAJOR MEREDITH")),
        shot("setup", N, "army", "medium", "push", "And ten thousand bullets.", "walt:A:hips nod@0.8",
             overlay=ov("chalk", "10,000 ROUNDS")),
        shot("deadline", "walt", "army", "close", "crash_zoom", "This will take a day.", "walt:A:hips laugh@0.6"),
        shot("obstacle", N, "field", "wide", "pan_r", "But emus run fifty kilometres an hour.", "walt:enter_l:run>2.2,0 shock@1.3",
             overlay=ov("chalk", "50 KM/H")),
        shot("obstacle", N, "field", "close", "crash_zoom", "And they scatter the second you shoot.", "walt:A:dizzy look_around@0.9",
             sounds=sfx(("gunshot", 0.2))),
        shot("con", N, "bush", "medium", "push", "So Meredith set up an ambush at a dam.", "walt:A:sneak point@1.1",
             freeze="WAIT..."),
        shot("con", N, "bush", "wide", "push", "A thousand emus walked right in.", "walt:A:cheer jump@0.9",
             overlay=ov("chalk", "1,000 EMUS")),
        shot("con", N, "bush", "close", "crash_zoom", "Then the gun jammed.", "walt:A:shock facepalm@0.7",
             overlay=ov("stamp", "JAMMED"), sounds=sfx(("bonk", 0.4))),
        shot("con", N, "bush", "medium", "push", "Twelve birds down.", "walt:A:sigh sad@0.8", overlay=ov("chalk", "12")),
        shot("escalate", N, "field", "wide", "pan_l", "So they bolted a gun onto a truck.", "walt:A:fist_pump run>-2,0@0.6",
             [held("gun", "walt")], sounds=sfx(("car", 0.1))),
        shot("escalate", N, "field", "close", "crash_zoom", "Too slow. Too bumpy.", "walt:A:dizzy tremble@0.7"),
        shot("escalate", N, "army", "medium", "push", "Meredith said the emus took bullets like tanks.",
             "walt:A:shock tremble@1.0", overlay=ov("chalk", "LIKE TANKS")),
        shot("twist", N, "parliament", "medium", "push", "Back home, politicians laughed, and the army was pulled out.",
             "pip:B:laugh point@1.2", overlay=ov("cross", "THE ARMY"), sounds=sfx(("laugh", 0.3))),
        shot("twist", N, "field", "wide", "pull", "The emus kept the field.", "walt:A:facepalm sad@0.9",
             overlay=ov("label", "WINNER: THE EMUS")),
        shot("payoff", N, "farmhouse", "medium", "push", "So farmers were paid a reward for each emu instead.",
             "pip:A:pick_up money@1.2", [picked("money", "pip")], sounds=sfx(("coins", 0.9))),
        shot("payoff", N, "farmhouse", "medium", "crash_zoom", "Over fifty seven thousand rewards in six months.",
             "pip:A:money celebrate@1.0", overlay=ov("chalk", "57,034")),
        shot("payoff", "pip", "field", "two_shot", "push", "So the farmers beat the birds?",
             "pip:C:scratch_head|walt:A:look_around"),
        shot("payoff", "walt", "field", "close", "crash_zoom", "Shh. Don't mention the war.", "walt:A:sneak tremble@0.8"),
    ])

# ---------------------------------------------------------------- operation mincemeat
STORIES["mincemeat"] = dict(
    hook_title="A DEAD MAN FOOLED HITLER?",
    keywords=["dead", "Hitler", "Sicily", "Greece", "letters", "briefcase", "submarine", "Spain", "Fleming", "Bond"],
    sources=["https://en.wikipedia.org/wiki/Operation_Mincemeat"],
    shots=[
        shot("hook", N, "office", "two_shot", "push", "In 1943, a dead man fooled Hitler.",
             "walt:A:sneak laugh@1.2|pip:C:shock@0.5", overlay=ov("stamp", "TOP SECRET")),
        shot("hook", "pip", "office", "close", "crash_zoom", "How does a dead man trick anyone?", "pip:C:scratch_head think@1.0"),
        shot("concept", N, "office", "medium", "push", "The Allies wanted to invade Sicily.", "walt:A:point present@1.1",
             [spot("map", "wall_l", "SICILY")]),
        shot("concept", N, "office", "close", "drift", "Problem: everyone knew Sicily was the obvious target.",
             "walt:A:think facepalm@1.3", overlay=ov("circle", "TOO OBVIOUS")),
        shot("setup", "walt", "office", "medium", "crash_zoom", "So let's lose some fake secrets.", "walt:A:sneak money@0.9"),
        shot("setup", N, "morgue", "medium", "push", "British spies found the body of a homeless Welshman.",
             "pip:B:fall:right|walt:A:look_around@0.6", overlay=ov("label", "GLYNDWR MICHAEL")),
        shot("setup", N, "morgue", "close", "push", "They gave him a new name: Major William Martin.",
             "walt:A:pick_up present@1.2", [picked("letter", "walt", "MAJOR WILLIAM MARTIN")]),
        shot("con", N, "morgue", "insert", "push", "Then they built him a whole fake life.", "walt:A:hold nod@1.0",
             [held("letter", "walt", "LOVE, PAM")]),
        shot("con", N, "morgue", "medium", "drift", "Love letters, theatre tickets, even an unpaid bank bill.",
             "walt:A:present laugh@1.3", overlay=ov("chalk", "TICKETS + BILLS")),
        shot("con", N, "office", "insert", "push", "And chained to his wrist, a briefcase of fake battle plans.",
             "walt:A:hold nod@1.3", [held("letter", "walt", "INVADE GREECE")]),
        shot("con", N, "sub", "medium", "push", "A submarine slipped him into the sea off Spain.", "walt:A:sneak throw@1.2",
             sounds=sfx(("splash", 1.6))),
        shot("con", N, "beach", "wide", "pan_r", "A fisherman found him floating.", "pip:enter_l:walk>1.2,0 shock@1.4",
             freeze="WAIT..."),
        shot("escalate", N, "beach", "medium", "push", "Spain was neutral, but crawling with German spies.",
             "pip:B:pick_up shock@1.2", [picked("letter", "pip", "INVADE GREECE")]),
        shot("escalate", N, "hq", "medium", "push", "They secretly copied the letters.", "pip:B:hold nod@0.9",
             [held("letter", "pip", "INVADE GREECE")], sounds=sfx(("paper", 0.4))),
        shot("escalate", "pip", "hq", "close", "crash_zoom", "Greece! Move the troops!", "pip:B:point angry@0.6"),
        shot("escalate", N, "hq", "wide", "pan_l", "Hitler sent a tank division to Greece.", "pip:B:run>-2.2,0",
             overlay=ov("arrow", "WRONG WAY")),
        shot("escalate", N, "office", "medium", "push", "In London, a message arrived: mincemeat swallowed.",
             "walt:A:hold celebrate@1.2", [held("letter", "walt", "MINCEMEAT SWALLOWED")]),
        shot("twist", N, "sicily", "wide", "tilt_down", "In July, the Allies landed in Sicily.", "walt:A:cheer celebrate@0.9",
             overlay=ov("chalk", "JULY 1943"), sounds=sfx(("boom", 0.4))),
        shot("twist", N, "sicily", "medium", "push", "Much of Germany's strength was waiting in the wrong place.",
             "pip:C:shock facepalm@1.1", overlay=ov("stamp", "FOOLED")),
        shot("payoff", N, "office", "medium", "push", "And the idea first came from a memo by a young officer.",
             "walt:A:sneak look_around@1.2"),
        shot("payoff", N, "office", "close", "crash_zoom", "His name? Ian Fleming.", "walt:A:hips laugh@0.7",
             overlay=ov("label", "IAN FLEMING")),
        shot("payoff", N, "office", "insert", "push", "He later created James Bond.", "walt:A:hold present@0.9",
             [held("board", "walt", "007")], sounds=sfx(("ding", 0.4))),
        shot("payoff", "pip", "office", "two_shot", "push", "So a dead man was a secret agent?",
             "pip:C:scratch_head|walt:A:look_around"),
        shot("payoff", "walt", "office", "close", "crash_zoom", "Shh. That file is top secret.", "walt:A:sneak point_you@0.8",
             [held("letter", "walt", "TOP SECRET")]),
    ])

# ---------------------------------------------------------------- the mona lisa theft
STORIES["mona_lisa_theft"] = dict(
    hook_title="THEY STOLE THE MONA LISA",
    keywords=["Mona", "Lisa", "Louvre", "glass", "smock", "Picasso", "trunk", "Florence", "famous", "empty"],
    sources=["https://en.wikipedia.org/wiki/Vincenzo_Peruggia"],
    shots=[
        shot("hook", N, "louvre", "two_shot", "push", "In 1911, the Mona Lisa vanished from the Louvre.",
             "pip:C:shock tremble@1.0|walt:A:sneak", [spot("board", "wall_r", "MONA LISA")]),
        shot("hook", N, "louvre", "close", "crash_zoom", "Nobody noticed for over a day.", "pip:C:look_around shrug@1.0",
             overlay=ov("chalk", "28 HOURS")),
        shot("hook", "pip", "louvre", "close", "crash_zoom", "Who steals the world's most famous painting?",
             "pip:C:scratch_head think@1.0"),
        shot("concept", N, "louvre", "medium", "push", "Back then, it wasn't that famous.", "walt:A:shrug look_around@0.9",
             overlay=ov("cross", "FAMOUS?")),
        shot("concept", N, "street", "medium", "drift", "The thief was Vincenzo Peruggia, a handyman.", "walt:A:hips sneak@1.2",
             overlay=ov("label", "VINCENZO PERUGGIA")),
        shot("setup", N, "louvre", "medium", "push", "And the crazy part? He had helped put it behind glass.",
             "walt:A:present laugh@1.3", overlay=ov("arrow", "HIS GLASS")),
        shot("setup", N, "closet", "close", "push", "One Sunday, he hid in a storeroom overnight.", "walt:A:cower look_around@1.0"),
        shot("obstacle", N, "closet", "medium", "push", "Monday, the museum was closed.", "walt:A:sneak look_around@0.8",
             overlay=ov("stamp", "CLOSED")),
        shot("con", N, "closet", "medium", "push", "He slipped on a white worker's smock.", "walt:A:pick_up hips@1.1"),
        shot("con", "walt", "closet", "close", "crash_zoom", "Just a workman. Nothing to see.", "walt:A:sneak point_you@1.0"),
        shot("con", N, "louvre", "wide", "pan_r", "He lifted it off the wall.", "walt:enter_l:sneak_walk>1.0,0 pick_up@1.0",
             [picked("board", "walt", "MONA LISA")]),
        shot("con", N, "louvre", "close", "crash_zoom", "Ditched the frame.", "walt:A:throw shock@0.7", sounds=sfx(("thud", 0.5))),
        shot("con", N, "street", "medium", "pan_l", "And walked out with it under his smock.", "walt:A:walk>-1.8,0 laugh@1.6",
             [held("board", "walt", "MONA LISA")], freeze="WAIT..."),
        shot("escalate", N, "street", "medium", "push", "The next day, it was front page news everywhere.",
             "pip:B:hold shock@1.2", [held("newspaper", "pip", "MONA LISA STOLEN")], sounds=sfx(("paper", 0.3))),
        shot("escalate", N, "street", "close", "push", "Police even questioned Pablo Picasso.", "pip:B:point shock@0.9",
             overlay=ov("label", "PABLO PICASSO")),
        shot("escalate", N, "louvre", "wide", "pull", "When the Louvre reopened, crowds lined up to stare at the empty wall.",
             "pip:C:look_around shrug@1.4", overlay=ov("chalk", "EMPTY WALL"), sounds=sfx(("crowd", 0.2))),
        shot("escalate", N, "louvre", "close", "crash_zoom", "Thousands came to see nothing.", "pip:C:shock facepalm@0.8"),
        shot("twist", N, "apartment", "wide", "tilt_down", "Meanwhile, it sat in a trunk in his tiny room.",
             "walt:A:pick_up present@1.2", [spot("box", "floor_front")]),
        shot("twist", N, "apartment", "medium", "push", "For two whole years.", "walt:A:hips laugh@0.8",
             overlay=ov("chalk", "2 YEARS")),
        shot("twist", N, "florence", "medium", "push", "Then he tried to sell it to an art dealer in Florence.",
             "walt:A:present money@1.2", [held("board", "walt", "MONA LISA")]),
        shot("twist", N, "florence", "close", "crash_zoom", "The dealer called the police.", "walt:A:shock cower@0.8",
             overlay=ov("stamp", "CAUGHT"), sounds=sfx(("gasp", 0.3))),
        shot("payoff", N, "florence", "medium", "push", "Many Italians cheered him, and he served just months in jail.",
             "pip:C:cheer celebrate@1.2|walt:A:shrug"),
        shot("payoff", N, "louvre", "low", "push", "And the Mona Lisa? Now the most famous painting on Earth.",
             "pip:C:celebrate cheer@1.3", overlay=ov("chalk", "MOST FAMOUS PAINTING")),
        shot("payoff", "pip", "louvre", "two_shot", "push", "So stealing it made it famous?",
             "pip:C:scratch_head|walt:A:look_around"),
        shot("payoff", "walt", "louvre", "close", "crash_zoom", "You're welcome, Mona.", "walt:A:sneak point_you@0.7"),
    ])


def build(sid):
    d = HERE / sid
    old = json.loads((d / "plan_v1.json" if (d / "plan_v1.json").exists() else d / "plan.json").read_text())
    st = STORIES[sid]
    shots = st["shots"]
    for i, s in enumerate(shots):
        s["id"] = f"s{i + 1:02d}"
    plan = {k: old[k] for k in ("id", "title", "topic", "cast", "places") if k in old}
    plan.update(hook_title=st["hook_title"], keywords=st["keywords"], sources=st["sources"], shots=shots, version="engaging_v2")
    (d / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    words = sum(len(s["text"].split()) for s in shots)
    print(f"{sid}: {len(shots)} shots, {words} words")


if __name__ == "__main__":
    for sid in sys.argv[1:] or STORIES:
        build(sid)
