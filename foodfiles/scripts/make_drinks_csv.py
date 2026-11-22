"""Builds foodfiles/scripts/deadliest_drinks.csv from deadliest_drinks.txt: one row per sentence, with the cards placed
by hand where the story calls for them (keyed by the first words of the sentence). Every word of the script is kept.

  python foodfiles/scripts/make_drinks_csv.py
"""
import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLS = ("line", "shot", "item", "title", "name", "year", "place", "visual", "stamp", "note", "rows", "source", "find", "url")

# first words of a sentence -> its cells
A = {
    # cold open
    "From a ginger tonic": dict(shot="host", note="TENS OF THOUSANDS?!"),
    "But first, we're starting with soda": dict(shot="title", title="THE DEADLIEST | DRINKS | EVER SOLD"),
    # 1 BVO
    "This is brominated vegetable oil": dict(item="1", title="HIDING IN YOUR SODA", name="BROMINATED VEGETABLE OIL", year="1931-2024",
                                              find="Mountain Dew"),
    "And you've never tasted it": dict(shot="photo", find="Sun Drop soda", rows="CITRUS SODAS"),
    "Citrus flavor comes from oils": dict(shot="explain", title="WHY BVO WAS IN THERE", rows="drop = FLAVOR OIL; up = FLOATS TO THE TOP"),
    "So drink makers bonded the oil": dict(shot="explain", title="THE FIX", rows="drop = FLAVOR OIL; +bottle = STAYS MIXED IN"),
    "Sounds harmless, right?": dict(shot="host", note="SOUNDS HARMLESS..."),
    "Well, bromine is the same element": dict(shot="compare", rows="BVO IN SODA = bottle; FLAME RETARDANT = fire"),
    "It builds up.": dict(shot="host"),
    "According to one case report from 2003": dict(shot="symptoms", title="ONE CASE REPORT · 2003", name="man",
                                                    rows="8 LITERS A DAY; PAINFUL SKIN SORES"),
    "And to put that in perspective": dict(shot="tally", rows="can x 12 = CANS... AND THAT'S ONLY HALF"),
    "The FDA had already pulled BVO": dict(shot="timeline", title="THE FDA'S TIMELINE", rows="1970 = OFF THE SAFE LIST; 2014 = SODAS DROP IT; 2024 = BANNED !red"),
    "In 2012, a fifteen-year-old": dict(shot="map", place="Hattiesburg, Mississippi", year="2012", rows="15-YEAR-OLD SARAH KAVANAGH"),
    "Within a year Gatorade dropped it": dict(shot="photo", find="Gatorade bottle", rows="GATORADE DROPPED BVO", stamp="DROPPED"),
    "And in July 2024, the FDA finally": dict(shot="page", url="https://www.fda.gov/food/food-additives-petitions/brominated-vegetable-oil-bvo",
                                               title="FDA · JULY 2024", rows="*Brominated vegetable oil* is no longer authorized", stamp="BANNED"),
    "So yeah, a teenager beat the FDA": dict(shot="host", note="12 YEARS!"),
    # 2 Radithor
    "This is Radithor": dict(item="2", title="A 1920s 'HEALTH' TONIC", name="RADITHOR", year="1927", find="Radithor"),
    "And back then, radium was": dict(shot="photo", find="radium advertisement", rows="RADIUM WAS THE NEW MIRACLE"),
    "So in 1927, a rich Pittsburgh": dict(shot="map", place="Pittsburgh, Pennsylvania", year="1927", rows="EBEN BYERS · STEEL MAN + GOLFER"),
    "And Byers loved it.": dict(shot="photo", find="Eben Byers", rows="EBEN BYERS", name="EBEN BYERS | Pittsburgh industrialist"),
    "By most estimates, he drank": dict(shot="big", rows="~1,400 = BOTTLES"),
    "Well, radium acts a lot like calcium": dict(shot="explain", title="WHAT RADIUM DOES", rows="bottle = RADIUM; +brain = TREATED LIKE CALCIUM; skull = BUILT INTO BONE"),
    "Byers' bones started falling apart.": dict(shot="host", note="HIS JAW?!"),
    "In 1932, Byers died at fifty-one": dict(shot="big", rows="51 = YEARS OLD; LEAD = LINED COFFIN", stamp="1932"),
    "As a result, the government cracked down": dict(shot="folder", title="THE CRACKDOWN", rows="WHO = WILLIAM BAILEY, RADITHOR'S MAKER; MEDICAL DEGREE = NONE; ORDER = STOP SELLING IT", stamp="ORDERED TO STOP"),
    "Not exactly a great look.": dict(shot="host"),
    # 3 snail
    "Because this is a bottle of ginger beer": dict(item="3", title="THE CASE THAT CHANGED THE LAW", name="THE PAISLEY SNAIL", year="1928", find="ginger beer bottle"),
    "On August 26th, 1928": dict(shot="map", place="Paisley, Scotland", year="1928", rows="MAY DONOGHUE"),
    "And the bottle was dark brown glass": dict(shot="scene2d", place="restaurant", rows="woman: talk; woman: eat"),
    "She drank about half of it": dict(shot="scene2d", place="restaurant", rows="woman: shock; say = A SNAIL?!"),
    "Donoghue got sick with stomach pain": dict(shot="symptoms", name="woman", rows="STOMACH PAIN; SHOCK"),
    "But here's the problem.": dict(shot="host", note="SHE DIDN'T PAY"),
    "So she sued the man who made it": dict(shot="folder", title="THE LAWSUIT", rows="FILED BY = MAY DONOGHUE; AGAINST = DAVID STEVENSON, DRINK MAKER; COURT = HOUSE OF LORDS"),
    "In 1932, the judges ruled": dict(shot="flow", title="THE RULING · 1932", rows="YOU MAKE IT; ANYONE CAN USE IT; YOU OWE THEM CARE !yellow", stamp="LANDMARK"),
    "But here's the twist.": dict(shot="host", note="WAS THERE A SNAIL?"),
    "Stevenson died before the trial": dict(shot="big", rows="£200 = SETTLED"),
    # 4 Odwalla
    "We're talking about Odwalla": dict(item="4", title="THE HEALTHY CHOICE", name="ODWALLA APPLE JUICE", year="1996", find="Odwalla juice"),
    "Odwalla didn't heat its juice": dict(shot="compare", rows="HEATED JUICE = fire; ODWALLA = apple"),
    "Well, in October 1996": dict(shot="states", place="California; Washington; Colorado", title="OCTOBER 1996", rows="E. COLI; E. COLI; E. COLI"),
    "In the end, sixty-six people got sick": dict(shot="big", rows="66 = SICK; 14 = KIDS WITH KIDNEY FAILURE"),
    "A sixteen-month-old girl in Colorado": dict(shot="map", place="Colorado", year="1996", rows="16-MONTH-OLD GIRL"),
    "And investigators later reported": dict(shot="scene2d", place="factory", rows="worker: carry apple; say = ROTTEN?"),
    "As a result, Odwalla recalled": dict(shot="folder", title="THE CASE", rows="PLEA = GUILTY, 1998; FINE = $1.5 MILLION; CHANGE = HEAT-TREATED JUICE", stamp="GUILTY"),
    "Healthy, until it wasn't.": dict(shot="host", note="...HEALTHY"),
    # 5 Perrier
    "This is Perrier": dict(item="5", title="THE FANCY WATER", name="PERRIER", year="1990", find="Perrier bottle"),
    "But in early 1990, a lab in North Carolina": dict(shot="map", place="North Carolina", year="1990", rows="A WATER-TESTING LAB"),
    "And the tests kept picking up benzene": dict(shot="explain", title="WHAT THE LAB FOUND", rows="bottle = PERRIER; +flask = BENZENE !red"),
    "So at first, Perrier blamed": dict(shot="timeline", title="PERRIER'S STORY", rows="FIRST = ONE PLANT; THEN = ONLY NORTH AMERICA; THEN = EUROPE TOO !red"),
    "By February 1990, Perrier was recalling": dict(shot="big", rows="160,000,000 = BOTTLES RECALLED", stamp="RECALLED"),
    "But here's the part that hurt": dict(shot="host"),
    "For years, the label said": dict(shot="flow", title="THE BUBBLES", rows="TAKEN OUT; HANDLED; ADDED BACK IN"),
    "So Perrier had to drop the word": dict(shot="host", note="NATURALLY?"),
    # 6 Coke Belgium
    "This is Coca-Cola in Belgium": dict(item="6", title="A MYSTERY IN A CAN", name="COCA-COLA BELGIUM", year="1999", find="Coca-Cola can"),
    "And one morning, students at a school": dict(shot="scene2d", place="classroom", rows="kid: sick; kid: sick; kid: sick; list = HEADACHES | NAUSEA | DIZZINESS"),
    "Within days, more than a hundred people": dict(shot="states", place="Belgium; France", title="JUNE 1999", rows="BORNEM; NORTHERN FRANCE"),
    "So Belgium did something no country": dict(shot="host"),
    "It banned the sale of every single Coke": dict(shot="photo", find="Coca-Cola bottles", rows="EVERY COKE PRODUCT", stamp="BANNED"),
    "So what was in the cans?": dict(shot="explain", title="WHAT THEY FOUND", rows="can = BAD CARBON DIOXIDE; box = TREATED PALLETS"),
    "But here's the weird part.": dict(shot="host", note="MASS PANIC?"),
    "Scientists who studied it later said": dict(shot="scene2d", place="classroom", rows="kid: shock; kid: sick; kid: shock; say = ME TOO!"),
    "Coke lost millions, and later that year": dict(shot="host", stamp="STEPPING DOWN"),
    "But if you think a mystery Coke": dict(shot="next", title="STILL TO COME..."),
    # 7 swill milk
    "This is swill milk": dict(item="7", title="1850s NEW YORK", name="SWILL MILK", year="1858", find="swill milk"),
    "Next to the city's whiskey distilleries": dict(shot="flow", title="HOW IT WAS MADE", rows="WHISKEY DISTILLERY; HOT LEFTOVER MASH; FED TO COWS"),
    "The cows got so sick that some couldn't stand": dict(shot="host", note="GROSS."),
    "The milk came out thin and bluish": dict(shot="explain", title="THE COVER-UP", rows="milk = THIN AND BLUISH; +jar = CHALK AND PLASTER"),
    "And in 1858, a newspaper called": dict(shot="big", rows="8,000 = CHILDREN A YEAR (CLAIMED)"),
    "As a result, the public was furious": dict(shot="timeline", title="WHAT CHANGED", rows="1858 = THE EXPOSE; 1862 = SWILL MILK BANNED; LATER = PASTEURIZED MILK !green"),
    "So the next time milk smells": dict(shot="host", note="PLASTER?!"),
    # 8 Jake leg
    "We're talking about Jamaica Ginger": dict(item="8", title="A PROHIBITION LOOPHOLE", name="JAMAICA GINGER", year="1930", find="Jamaica ginger extract"),
    "Because alcohol was banned, but medicine": dict(shot="compare", rows="ALCOHOL = x; MEDICINE = pill"),
    "And Jake was a ginger extract": dict(shot="big", rows="~70% = ALCOHOL"),
    "So in 1930, two businessmen in Boston": dict(shot="map", place="Boston, Massachusetts", year="1930", rows="HARRY GROSS + MAX REISMAN"),
    "And they swapped some of the ginger": dict(shot="explain", title="THE SHORTCUT", rows="flask = TOCP; +x = CHEAPER THAN GINGER"),
    "It passed the test.": dict(shot="host", stamp="PASSED"),
    "In the spring of 1930, people who drank": dict(shot="scene2d", place="street", rows="man: walk; man: fall; old: walk"),
    "Estimates of how many were hurt": dict(shot="big", rows="UP TO 100,000 = PEOPLE HURT"),
    "It was so widespread that blues singers": dict(shot="host", note="JAKE LEG BLUES"),
    "And in the end, Gross and Reisman": dict(shot="folder", title="THE CASE", rows="WHO = HARRY GROSS + MAX REISMAN; RESULT = CONVICTED; VICTIMS = MOSTLY NOTHING", stamp="CONVICTED"),
    # 9 Elixir
    "This is Elixir Sulfanilamide": dict(item="9", title="A MEDICINE FOR KIDS", name="ELIXIR SULFANILAMIDE", year="1937", find="Elixir Sulfanilamide"),
    "So a company in Bristol, Tennessee": dict(shot="map", place="Bristol, Tennessee", year="1937", rows="S. E. MASSENGILL CO."),
    "Their chief chemist, Harold Watkins": dict(shot="explain", title="THE RECIPE", rows="pill = THE DRUG; +bottle = DIETHYLENE GLYCOL; candy = RASPBERRY FLAVOR"),
    "And nobody tested it on animals first": dict(shot="host", note="NO TESTS?!"),
    "Well, diethylene glycol is a close cousin": dict(shot="compare", rows="THE ELIXIR = bottle; ANTIFREEZE = car"),
    "Within weeks, people who took the elixir": dict(shot="scene2d", place="hospital", rows="kid: sick; monitor"),
    "The FDA sent almost every inspector": dict(shot="scene2d", place="street", rows="doctor: run; worker: run"),
    "But by the end, more than a hundred people": dict(shot="big", rows="100+ = DEAD", stamp="FATAL"),
    "The company was only fined about": dict(shot="big", rows="$26,100 = THE FINE"),
    "As a result, in 1938, Congress passed": dict(shot="timeline", title="WHAT CHANGED", rows="1937 = THE ELIXIR; 1938 = DRUG SAFETY LAW !green; TODAY = SAFETY TESTS FIRST"),
    # 10 arsenic beer
    "Because this is beer": dict(item="10", title="MANCHESTER, 1900", name="THE ARSENIC BEER", year="1900", find="Manchester 1900"),
    "People started showing up with burning hands": dict(shot="symptoms", name="man", rows="BURNING HANDS AND FEET; NUMB LEGS; DARKENED SKIN"),
    "Thousands of people across the north of England": dict(shot="map", place="Manchester, England", year="1900", rows="THE NORTH OF ENGLAND"),
    "Well, a doctor named Ernest Reynolds": dict(shot="host", name="ERNEST REYNOLDS | the doctor who found it"),
    "And it turned out the brewers were using": dict(shot="flow", title="THE CHAIN", rows="ARSENIC IN THE ORE; SULFURIC ACID; CHEAP BREWING SUGAR; BEER !red"),
    "In the end, more than six thousand": dict(shot="big", rows="6,000+ = POISONED; 70+ = DEAD", stamp="POISONED"),
    "As a result, the government set up": dict(shot="photo", find="Lord Kelvin", rows="LORD KELVIN LED THE INQUIRY"),
    "It was coming from the malt": dict(shot="explain", title="THE SECOND SOURCE", rows="fire = COAL FIRES; +germ = ARSENIC IN THE MALT"),
    "It glowed, it was in the news": dict(shot="photo", find="radium", rows="IT GLOWED"),
    "Holes opened in his skull": dict(shot="explain", title="WHAT IT DID", rows="skull = HOLES IN HIS SKULL; +x = MOST OF HIS JAW REMOVED"),
    "And the case went all the way": dict(shot="photo", find="House of Lords chamber", rows="THE HIGHEST COURT IN BRITAIN"),
    "And the one thing they had in common was Odwalla": dict(shot="photo", find="apple juice", rows="ODWALLA APPLE JUICE"),
    "In the 1980s, it was the drink of rich people": dict(shot="scene2d", place="office", rows="man: talk bottle; woman: eat bottle"),
    "And the real cause was dirty filters": dict(shot="flow", title="THE REAL CAUSE", rows="DIRTY FILTERS; GAS NOT CLEANED; BENZENE IN THE WATER !red"),
    "Coca-Cola pulled millions of cans": dict(shot="states", place="Belgium; Luxembourg; France; Netherlands", title="PULLED FROM SHELVES",
                                              rows="PULLED; PULLED; PULLED; PULLED"),
    "And it would take decades more of fighting": dict(shot="photo", find="milk pasteurization", rows="PASTEURIZED MILK"),
    "To stop people drinking it, the government": dict(shot="photo", find="ginger root", rows="SO MUCH GINGER IT TASTED AWFUL"),
    "They walked with a slapping, stumbling step": dict(shot="scene2d", place="street", rows="man: walk; old: fall; say = JAKE WALK"),
    "Sulfanilamide was one of the first real antibiotics": dict(shot="photo", find="sulfanilamide", rows="ONE OF THE FIRST ANTIBIOTICS"),
    "Then he added raspberry flavor": dict(shot="scene2d", place="store", rows="worker: carry box; worker: carry box"),
    "That sugar was made with sulfuric acid": dict(shot="photo", find="sulfuric acid", rows="SULFURIC ACID"),
    "So without knowing it, the brewers": dict(shot="photo", find="pint of beer", rows="THOUSANDS OF PINTS"),
    # outro
    "So the next time you grab a drink": dict(shot="host"),
    "And the next time you pour a bowl": dict(shot="next", title="BREAKFAST..."),
}


def main():
    text = (HERE / "deadliest_drinks.txt").read_text(encoding="utf-8").split("\n", 2)[2]
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if s.strip()]
    sents = []
    for s in parts:     # keep initials together: "E. coli", "S. E. Massengill"
        if sents and re.search(r"(^|\s)[A-Z]\.$", sents[-1]):
            sents[-1] += " " + s
        else:
            sents.append(s)
    out, used = [], set()
    for s in sents:
        row = {c: "" for c in COLS}
        row["line"] = s
        for k, cells in A.items():
            if s.startswith(k) and k not in used:
                row.update(cells)
                used.add(k)
                break
        out.append(row)
    out.append(dict({c: "" for c in COLS}, shot="thumbnail", title="DEADLIEST | DRINKS",
                    visual="{host} looking shocked at the camera, holding up an old glass soda bottle, his studio shelves behind him"))
    missing = [k for k in A if k not in used]
    with open(HERE / "deadliest_drinks.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out) - 1} rows, {len(used)} with cards; not matched: {missing}")


if __name__ == "__main__":
    main()
