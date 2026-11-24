"""Builds foodfiles/scripts/dangerous_breakfast.csv from dangerous_breakfast.txt: one row per sentence, cards placed by
hand where the story calls for them (keyed by the first words of the sentence). Every word of the script is kept.

  python foodfiles/scripts/make_breakfast_csv.py
"""
import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLS = ("line", "shot", "item", "title", "name", "year", "place", "visual", "stamp", "note", "rows", "source", "find", "url")

A = {
    # cold open
    "From a wave of syrup": dict(shot="host", note="33 PEOPLE?!"),
    "But first, we're starting with a cereal": dict(shot="title", title="THE MOST DANGEROUS | BREAKFAST FOODS | EVER SOLD"),
    # 1 Lucky Charms
    "This is Lucky Charms": dict(item="1", title="A 2022 MYSTERY", name="LUCKY CHARMS", year="2022", find="Lucky Charms"),
    "It's been around since 1964": dict(shot="host", note="HARMLESS...?"),
    "Well, in the spring of 2022": dict(shot="scene2d", place="kitchen", rows="woman: eat bowl; man: sick"),
    "Stomach cramps, vomiting, diarrhea": dict(shot="symptoms", name="man", rows="STOMACH CRAMPS; VOMITING; DIARRHEA"),
    "A food safety website called I Was Poisoned": dict(shot="big", rows="3,000+ = REPORTS IN A FEW WEEKS"),
    "So the FDA opened an investigation": dict(shot="folder", title="THE INVESTIGATION", rows="WHO = THE FDA; COMPLAINTS = 100+; FOUND = NOTHING"),
    "But here's the weird part.": dict(shot="host", note="NOTHING?!"),
    "General Mills tested its cereal": dict(shot="explain", title="THE TESTS", rows="germ = NO BACTERIA; x = NO BAD INGREDIENT"),
    "Some experts think a lot of it": dict(shot="compare", rows="POWER OF SUGGESTION = brain; SOMETHING CHANGED = cereal"),
    "Magically delicious, magically mysterious.": dict(shot="host"),
    # 2 Cheerios
    "This is Cheerios": dict(item="2", title="THE SAFE CHOICE", name="CHEERIOS", year="2015", find="Cheerios"),
    "Cheerios was going gluten-free": dict(shot="explain", title="CELIAC DISEASE", rows="bag = WHEAT; +x = GETS THEM SICK"),
    "Well, a few months later, in October 2015": dict(shot="big", rows="1,800,000 = BOXES RECALLED", stamp="RECALLED"),
    "At a plant in Lodi, California": dict(shot="map", place="Lodi, California", year="2015", rows="WHEAT IN THE OAT FLOUR"),
    "So the boxes said gluten-free": dict(shot="compare", rows="THE BOX SAID = check; THE CEREAL HAD = bag"),
    "And more than a hundred people with celiac": dict(shot="tally", rows="man x 6 = OF 100+ PEOPLE SICK"),
    "So yeah, the one cereal you'd trust": dict(shot="host", note="THE SAFE ONE"),
    # 3 eggs
    "We're talking about eggs": dict(item="3", title="THE BIGGEST EGG RECALL", name="IOWA EGGS", year="2010", find="egg carton"),
    "It started in the summer of 2010": dict(shot="explain", title="THE OUTBREAK", rows="egg = EGGS; +germ = SALMONELLA"),
    "And those eggs came from two big farms": dict(shot="map", place="Iowa", year="2010", rows="WRIGHT COUNTY EGG + HILLANDALE"),
    "So in August 2010, the two companies": dict(shot="big", rows="550,000,000 = EGGS RECALLED", stamp="RECALLED"),
    "To put that in perspective": dict(shot="states", place="United States; Canada", title="ONE EGG FOR EVERY PERSON", rows="USA; CANADA"),
    "In the end, nearly two thousand people": dict(shot="big", rows="~2,000 = PEOPLE SICK"),
    "And when inspectors walked into the Iowa barns": dict(shot="evidence", title="WHAT INSPECTORS FOUND", rows="RODENTS = germ; FLIES = germ; 8 FT MANURE = warning"),
    "In 2015, the owner, Austin DeCoster": dict(shot="folder", title="THE SENTENCE · 2015", rows="WHO = AUSTIN + PETER DECOSTER; SENTENCE = 3 MONTHS IN JAIL; FINE = $100,000 EACH", stamp="JAILED"),
    "So yeah, a bad egg went to jail.": dict(shot="host", note="A BAD EGG"),
    # 4 poppy seeds
    "This is a poppy seed muffin": dict(item="4", title="THE MUFFIN THAT FAILS DRUG TESTS", name="POPPY SEEDS", year="1998", find="poppy seed muffin"),
    "Because poppy seeds come from the opium poppy": dict(shot="photo", find="opium poppy", rows="THE OPIUM POPPY"),
    "And the seeds themselves don't contain much": dict(shot="explain", title="WHERE THE MORPHINE IS", rows="drop = SEED; +pill = MORPHINE ON THE OUTSIDE"),
    "So if you eat a poppy seed bagel": dict(shot="scene2d", place="office", rows="man: eat; doctor: point; say = POSITIVE?!"),
    "Well, it happened so often that in 1998": dict(shot="timeline", title="THE DRUG TEST LIMIT", rows="BEFORE = 300 NG/ML; 1998 = 2,000 NG/ML !green"),
    "Some people figured out you could soak": dict(shot="explain", title="POPPY SEED TEA", rows="jar = UNWASHED SEEDS; +cup = MORPHINE TEA !red"),
    "And in 2016, a twenty-four-year-old": dict(shot="map", place="Arkansas", year="2016", rows="STEPHEN HACALA, 24"),
    "His parents started pushing": dict(shot="host", name="STEPHEN HACALA'S PARENTS | pushing for a ban"),
    # 5 maple heist
    "Because this is maple syrup": dict(item="5", title="A CANADIAN HEIST", name="MAPLE SYRUP", year="2012", find="maple syrup"),
    "Quebec makes most of the world's maple syrup": dict(shot="photo", find="maple syrup barrels", rows="THE STRATEGIC RESERVE"),
    "And in 2012, during a routine check": dict(shot="map", place="Canada", year="2012", rows="SAINT-LOUIS-DE-BLANDFORD"),
    "Because it was supposed to be full of syrup": dict(shot="scene2d", place="factory", rows="worker: shock; say = EMPTY?!"),
    "Well, over about a year, a group of men": dict(shot="flow", title="THE HEIST", rows="DRAIN THE SYRUP; REFILL WITH WATER; SELL IT ON"),
    "In the end, around three thousand tons": dict(shot="big", rows="~3,000 = TONS STOLEN; $18M = THE VALUE"),
    "And in 2017, the ringleader": dict(shot="folder", title="THE SENTENCE · 2017", rows="WHO = RICHARD VALLIERES; SENTENCE = 8 YEARS; FINE = $9 MILLION+", stamp="GUILTY"),
    "Nobody got hurt, but some pancakes": dict(shot="host", note="DRY PANCAKES"),
    # 6 molasses
    "This is molasses": dict(item="6", title="BOSTON, 1919", name="THE MOLASSES FLOOD", year="1919", find="Boston Molasses Disaster"),
    "Because in the North End of the city": dict(shot="map", place="Boston, Massachusetts", year="1919", rows="THE NORTH END"),
    "And people living nearby said the tank leaked": dict(shot="host", note="PAINTED BROWN?!"),
    "So around lunchtime that day, the tank burst.": dict(shot="big", rows="2,300,000 = GALLONS"),
    "And a wave of molasses": dict(shot="big", rows="25 FT = HIGH; 35 MPH = FAST", stamp="BURST"),
    "It knocked buildings off their foundations": dict(shot="photo", find="Boston molasses flood 1919 damage", rows="THE NORTH END AFTERWARD"),
    "Sailors from a navy ship nearby": dict(shot="scene2d", place="street", rows="worker: run; man: run; worker: carry"),
    "In the end, twenty-one people died": dict(shot="big", rows="21 = DEAD; ~150 = HURT", stamp="FATAL"),
    "And as a result, the families sued": dict(shot="folder", title="THE LAWSUIT", rows="FILED BY = THE FAMILIES; RESULT = THE COMPANY PAID; AMOUNT = $600,000+"),
    "But if you think a syrup flood": dict(shot="next", title="STILL TO COME..."),
    # 7 Death Wish
    "This is Death Wish Coffee": dict(item="7", title="THE WORLD'S STRONGEST COFFEE", name="DEATH WISH COFFEE", year="2019", find="Death Wish Coffee"),
    "A man named Mike Brown started it": dict(shot="timeline", title="DEATH WISH", rows="2012 = A SMALL COFFEE SHOP; 2016 = A SUPER BOWL AD; 2019 = THE RECALL !red"),
    "Cold brew coffee isn't very acidic": dict(shot="flow", title="THE PROBLEM", rows="LOW ACID; SEALED WITH NITROGEN; NOT IN A FRIDGE"),
    "And those are almost exactly the conditions": dict(shot="explain", title="BOTULISM", rows="can = THE CAN; +germ = BOTULISM TOXIN !red"),
    "So in September 2019, Death Wish recalled": dict(shot="photo", find="cold brew coffee can", rows="NITRO COLD BREW", stamp="RECALLED"),
    "A coffee called Death Wish, pulled for a deadly toxin.": dict(shot="host", note="THE IRONY"),
    # 8 Jif
    "This is Jif peanut butter": dict(item="8", title="CHOOSY MOMS CHOOSE...", name="JIF PEANUT BUTTER", year="2022", find="Jif peanut butter"),
    "Because the CDC traced a salmonella outbreak": dict(shot="map", place="Lexington, Kentucky", year="2022", rows="ONE FACTORY"),
    "In the end, twenty-one people in seventeen states": dict(shot="big", rows="21 = SICK; 17 = STATES"),
    "It goes into crackers, snack packs": dict(shot="flow", title="WHERE JIF GOES", rows="JIF JARS; CRACKERS + SNACK PACKS; FUDGE + DIPPING CUPS"),
    "And families had to go through their cupboards": dict(shot="scene2d", place="kitchen", rows="woman: point jar; kid: shock; say = 425?"),
    "And according to the FDA, the same strain": dict(shot="host", note="YEARS BEFORE?"),
    # 9 formula
    "We're talking about baby formula.": dict(item="9", title="THE TINIEST CUSTOMERS", name="BABY FORMULA", year="2022", find="Similac"),
    "And in February 2022, the company Abbott": dict(shot="map", place="Sturgis, Michigan", year="2022", rows="ONE ABBOTT PLANT", stamp="RECALLED"),
    "Because four babies who drank formula": dict(shot="tally", rows="kid x 4 = BABIES SICK, 2 DIED"),
    "But inspectors found Cronobacter": dict(shot="evidence", title="WHAT INSPECTORS FOUND", rows="CRONOBACTER = germ; STANDING WATER = drop; CRACKS = warning"),
    "Months earlier, in October 2021": dict(shot="browser", title="a report to the FDA · OCT 2021", name="WHISTLEBLOWER REPORT",
                                           rows="A former worker warned about *problems at the Sturgis plant* months before the recall."),
    "By May 2022, around forty percent": dict(shot="big", rows="~40% = OUT OF STOCK"),
    "Parents drove from store to store": dict(shot="scene2d", place="supermarket", rows="woman: shock; man: walk; say = EMPTY!"),
    "And just weeks after the plant finally reopened": dict(shot="host", note="AGAIN?!"),
    # 10 cantaloupe
    "Because this is cantaloupe": dict(item="10", title="THE DEADLIEST OUTBREAK IN 100 YEARS", name="CANTALOUPE", year="2011", find="cantaloupe"),
    "And in the summer of 2011, a farm in Colorado": dict(shot="map", place="Colorado", year="2011", rows="JENSEN FARMS"),
    "But they were carrying listeria": dict(shot="explain", title="LISTERIA", rows="fridge = SURVIVES THE COLD; +old = HITS OLDER PEOPLE HARDEST"),
    "And listeria is sneaky": dict(shot="timeline", title="WHY IT WAS LATE", rows="DAY 1 = YOU EAT IT; WEEKS LATER = YOU GET SICK; BY THEN = THE MELONS ARE GONE"),
    "In the end, a hundred and forty-seven people": dict(shot="big", rows="147 = SICK; 33 = DEAD", stamp="FATAL"),
    "It was the deadliest food outbreak": dict(shot="host", note="100 YEARS"),
    "Well, investigators found that the farm": dict(shot="compare", rows="MEANT FOR = POTATOES; USED FOR = MELONS"),
    "As a result, in 2013, the farm's owners": dict(shot="folder", title="THE CASE · 2013", rows="WHO = ERIC + RYAN JENSEN; PLEA = GUILTY; SENTENCE = 5 YEARS PROBATION", stamp="GUILTY"),
    # outro
    "So the next time you pour a bowl": dict(shot="host"),
    "And the next time you pack a lunch": dict(shot="next", title="LUNCH..."),
}


def main():
    text = (HERE / "dangerous_breakfast.txt").read_text(encoding="utf-8").split("\n", 2)[2]
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if s.strip()]
    sents = []
    for s in parts:     # keep initials together
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
    out.append(dict({c: "" for c in COLS}, shot="thumbnail", title="DANGEROUS | BREAKFAST",
                    visual="{host} looking shocked at the camera, holding up a bowl of colourful cereal, his studio shelves behind him"))
    missing = [k for k in A if k not in used]
    with open(HERE / "dangerous_breakfast.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out) - 1} rows, {len(used)} with cards; not matched: {missing}")


if __name__ == "__main__":
    main()
