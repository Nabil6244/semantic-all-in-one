"""Builds senior_trivia/episodes/ep01_1955_8th_grade.csv. Right answer is listed first here; options are rotated so the
right letter varies (fixed pattern, no randomness)."""
import csv
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
PAT = [1, 0, 2, 3, 1, 2, 0, 3, 2, 1]   # where the right answer lands, per question in a round

rows = []
H = ["type", "round", "question", "options", "answer", "fact", "picture", "fact_picture", "line", "seconds"]


def row(**k):
    rows.append({h: k.get(h, "") for h in H})


def q(i, text, right, wrong, fact, pic):
    pos = PAT[i % 10]
    opts = list(wrong)
    opts.insert(pos, right)
    row(type="question", question=text, options=" | ".join(opts), answer="ABCD"[pos], fact=fact, picture=pic, seconds="7")


row(type="intro", question="Could You Pass a 1955 8th Grade Test?",
    picture="a sunny 1950s American schoolroom, rows of wooden desks, chalkboard, flag, tall windows",
    line="Fifty-five questions from a 1955 eighth grade classroom. Arithmetic, spelling, geography, history and civics, "
         "getting harder as we go. Score forty to pass. Grab a pen, keep score, and stay for the bonus question at the end.")
row(type="host", picture="a 1950s school bus parked outside a red brick schoolhouse, autumn morning",
    line="Hello, friends, I'm Hal. Back in my day, this was the test that decided if you moved on to high school. Let's see how you do.")

ROUNDS = [
    ("Arithmetic | easy", "Round one. Arithmetic. Pencils ready.", [
        ("How many inches are in one yard?", "36", ["24", "48", "12"],
         "A yard is three feet, and every foot is twelve inches.", "a wooden yardstick lying on an old school desk next to a pencil"),
        ("How many ounces are in one pound?", "16", ["12", "10", "20"],
         "Grocers weighed cheese, coffee and candy by the pound and ounce on hanging scales.", "a 1950s general store counter with a hanging scale"),
        ("What is seven times eight?", "56", ["54", "63", "48"],
         "Children drilled their times tables out loud, often with flash cards.", "a child's hands holding arithmetic flash cards at a wooden desk"),
        ("How many pints make one quart?", "Two", ["Three", "Four", "Eight"],
         "Two pints make a quart, and four quarts make a gallon.", "glass milk bottles on a front porch at sunrise, 1950s"),
        ("If a candy bar costs five cents, how many can you buy with a quarter?", "Five", ["Three", "Four", "Six"],
         "A plain Hershey bar cost a nickel for decades, until 1969.", "a 1950s candy counter with jars and wrapped chocolate bars"),
        ("What is one quarter written as a decimal?", "0.25", ["0.4", "0.14", "0.5"],
         "That is why a quarter of a dollar is worth twenty-five cents.", "a few old silver coins on a school notebook page"),
        ("How many days are in a leap year?", "366", ["365", "364", "360"],
         "A leap year adds February twenty-ninth, almost every four years.", "an old paper wall calendar in a 1950s kitchen"),
        ("What is half of three quarters?", "Three eighths", ["One half", "One quarter", "Three halves"],
         "To halve a fraction, you double the bottom number.", "a chalkboard with a pie drawn in chalk and cut into slices"),
        ("How many feet are in one mile?", "5,280", ["5,000", "3,280", "1,760"],
         "And 1,760 is the number of yards in a mile.", "an empty country road stretching to the horizon with a mile marker, 1950s"),
        ("What number does the Roman numeral L stand for?", "50", ["100", "500", "1,000"],
         "C stands for one hundred, D for five hundred and M for one thousand.", "an old clock tower face with Roman numerals"),
        ("What is 144 divided by 12?", "12", ["14", "11", "16"],
         "One hundred forty-four is called a gross: a dozen dozens.", "egg cartons stacked in a 1950s grocery store"),
    ], "End of round one. Nine or more? Your arithmetic teacher would be proud."),
    ("Spelling and Grammar | easy", "Round two. Spelling and grammar.", [
        ("Which word is spelled correctly?", "Necessary", ["Neccessary", "Necesary", "Neccesary"],
         "Teachers used a trick: one collar and two sleeves, so one C and two S's.", "an open spelling book and an ink pen on a school desk"),
        ("What is the plural of mouse?", "Mice", ["Mouses", "Meese", "Mousen"],
         "Goose and geese change the same old way.", "a small gray mouse peeking from a hole in a farmhouse kitchen wall"),
        ("Which of these words is a noun?", "Happiness", ["Quickly", "Run", "Beautiful"],
         "A noun names a person, a place, a thing or an idea.", "a 1950s schoolteacher writing on a chalkboard, seen from behind"),
        ("What is the past tense of swim?", "Swam", ["Swimmed", "Swum", "Swammed"],
         "Swum is used with have: I have swum across the lake.", "children swimming at a summer lake with a wooden dock, 1950s"),
        ("Which sentence is correct?", "He and I went fishing.", ["Him and me went fishing.", "Me and him went fishing.", "Him and I went fishing."],
         "The old test: leave the other person out. You would say I went fishing, not me went fishing.",
         "two boys with fishing poles walking to a pond, 1950s summer"),
        ("Which word means the opposite of ancient?", "Modern", ["Old", "Antique", "Aged"],
         "Words with opposite meanings are called antonyms.", "an old stone ruin beside a shiny 1950s car, warm light"),
        ("Which of these words is a contraction?", "Don't", ["Done", "Dawn", "Down"],
         "The apostrophe stands in for the missing letter, here the O in not.", "a handwritten school composition on lined paper"),
        ("Which spelling is correct?", "Receive", ["Recieve", "Receeve", "Riceive"],
         "The rhyme every child learned: I before E, except after C.", "a stack of letters and an envelope on a hall table, 1950s"),
        ("What part of speech is the word quickly?", "Adverb", ["Adjective", "Verb", "Noun"],
         "Many adverbs end in L Y and tell how something is done.", "children running in a school playground at recess, 1950s"),
        ("Which word means nearly the same as enormous?", "Huge", ["Tiny", "Narrow", "Quiet"],
         "Words with the same meaning are called synonyms.", "a huge old oak tree towering over a small farmhouse"),
        ("Pick the correct spelling of the word that means apart.", "Separate", ["Seperate", "Separete", "Seprate"],
         "The old classroom trick: there is a rat in separate.", "a teacher handing back graded spelling tests, 1950s"),
    ], "End of round two. Eighteen or more so far? You're right on track."),
    ("Geography | medium", "Round three. Geography. Picture the map on the classroom wall.", [
        ("What is the capital of Texas?", "Austin", ["Dallas", "Houston", "San Antonio"],
         "Austin has been the capital since 1839, when it was a tiny frontier town.", "a wide Texas prairie with longhorn cattle at sunset"),
        ("Which is the longest river in the United States?", "The Missouri", ["The Mississippi", "The Colorado", "The Ohio"],
         "The Missouri runs about 2,341 miles, just a hair longer than the Mississippi.", "a wide American river winding through green plains, 1950s"),
        ("Which ocean lies along the coast of California?", "The Pacific", ["The Atlantic", "The Indian", "The Arctic"],
         "Pacific means peaceful. Magellan gave it that name in 1520.", "a rocky coastline with crashing waves and a lighthouse"),
        ("Which is the largest of the five Great Lakes?", "Lake Superior", ["Lake Michigan", "Lake Huron", "Lake Erie"],
         "Lake Superior holds about ten percent of all the fresh surface water on Earth.", "a vast cold blue lake with pine forest shores"),
        ("Which state is nicknamed the Sunshine State?", "Florida", ["California", "Arizona", "Hawaii"],
         "The nickname became official in 1970, and it was on license plates even earlier.", "palm trees and a pastel motel by a sunny beach, 1950s"),
        ("Which mountain range runs through Colorado?", "The Rocky Mountains", ["The Appalachians", "The Sierra Nevada", "The Cascades"],
         "Colorado has more than fifty peaks taller than fourteen thousand feet.", "snowy mountain peaks above a mountain town, 1950s"),
        ("Which is the largest state by area?", "Alaska", ["Texas", "California", "Montana"],
         "Alaska is more than twice the size of Texas.", "a wild landscape of glaciers and mountains under a big sky"),
        ("What is the capital of New York State?", "Albany", ["New York City", "Buffalo", "Syracuse"],
         "Albany has been the capital since 1797.", "a grand old state capitol building on a hill, autumn"),
        ("Which two states do not touch any of the other states?", "Alaska and Hawaii", ["Maine and Florida", "Hawaii and California", "Alaska and Washington"],
         "Both joined the Union in 1959, the last two states to do so.", "a 1950s classroom globe on a teacher's desk"),
        ("What is the smallest state by area?", "Rhode Island", ["Delaware", "Connecticut", "Vermont"],
         "You could fit Rhode Island inside Alaska more than four hundred times.", "a small New England harbor with sailboats, 1950s"),
        ("Which river forms much of the border between Texas and Mexico?", "The Rio Grande", ["The Colorado", "The Red River", "The Pecos"],
         "About 1,250 miles of that border follow the Rio Grande.", "a desert river canyon at sunset with cactus on the banks"),
    ], "End of round three. Twenty-six or more? You really knew that map."),
    ("American History | medium", "Round four. American history.", [
        ("In what year was the Declaration of Independence adopted?", "1776", ["1789", "1812", "1754"],
         "It was adopted on July fourth, but most delegates signed it on August second.", "an old quill pen and parchment on a wooden table by candlelight"),
        ("Who was the first President of the United States?", "George Washington", ["John Adams", "Thomas Jefferson", "Benjamin Franklin"],
         "He took the oath of office in New York City in 1789.", "a colonial-era balcony over a crowded street with flags"),
        ("Which President issued the Emancipation Proclamation?", "Abraham Lincoln", ["Ulysses Grant", "Andrew Johnson", "James Buchanan"],
         "It took effect on January first, 1863.", "an old wooden desk in a candlelit 1860s office"),
        ("Which city was the first capital under the Constitution?", "New York City", ["Philadelphia", "Boston", "Washington"],
         "The capital moved to Philadelphia in 1790, then to Washington in 1800.", "an 18th-century city street with horse carriages"),
        ("From which country did the United States buy the Louisiana Territory?", "France", ["Spain", "England", "Mexico"],
         "The 1803 purchase cost about fifteen million dollars and doubled the size of the country.", "a wide river delta with old sailing ships, 1800s"),
        ("Who wrote the words to The Star-Spangled Banner?", "Francis Scott Key", ["Paul Revere", "Samuel Adams", "John Hancock"],
         "He wrote them in 1814 after watching the bombardment of Fort McHenry.", "a star-shaped brick fort with a huge flag at dawn, 1800s"),
        ("In which years was the Civil War fought?", "1861 to 1865", ["1812 to 1815", "1846 to 1848", "1898 to 1899"],
         "About 620,000 soldiers died, more than in any other American war.", "an old split-rail fence across a quiet green battlefield at dawn"),
        ("Which two explorers led the 1804 expedition to the Pacific?", "Lewis and Clark", ["Boone and Crockett", "Pike and Fremont", "Hudson and Cabot"],
         "A young Shoshone woman, Sacagawea, helped guide them.", "explorers in canoes on a wild western river, 1800s"),
        ("Who was President for most of World War Two?", "Franklin Roosevelt", ["Harry Truman", "Herbert Hoover", "Dwight Eisenhower"],
         "He was elected four times, the only President to serve more than two terms.", "a 1940s family listening to a radio in the living room"),
        ("On which ship did the Pilgrims sail to America in 1620?", "The Mayflower", ["The Santa Maria", "The Endeavour", "The Constitution"],
         "The voyage took sixty-six days.", "an old wooden sailing ship on a stormy gray Atlantic"),
        ("From which country did the United States buy Alaska in 1867?", "Russia", ["Canada", "England", "Spain"],
         "It cost 7.2 million dollars, about two cents an acre.", "snowy northern mountains and a frozen bay, 1800s"),
    ], "End of round four. Thirty-five or more? Only the hard round stands between you and a pass."),
    ("Civics | hard", "Round five. The hard round. Civics.", [
        ("How many senators does each state have?", "Two", ["One", "Three", "It depends on population"],
         "That is why the Senate has one hundred members today.", "the white dome of a capitol building against a blue sky"),
        ("How many amendments make up the Bill of Rights?", "Ten", ["Twelve", "Five", "Twenty-seven"],
         "The Bill of Rights was ratified in 1791.", "an old printed document under glass in a museum, warm light"),
        ("How long is the term of a United States senator?", "Six years", ["Four years", "Two years", "Eight years"],
         "Only about one third of the Senate is up for election at a time.", "a grand marble hallway with tall columns"),
        ("How long is the term of a member of the House of Representatives?", "Two years", ["Four years", "Six years", "One year"],
         "So every seat in the House is up for election every two years.", "a 1950s town square with campaign posters and a crowd"),
        ("Which part of the government makes the laws?", "Congress", ["The President", "The Supreme Court", "The governors"],
         "Congress is the Senate and the House of Representatives together.", "a large ornate legislative chamber with rows of desks"),
        ("If the President and Vice President cannot serve, who is next?", "The Speaker of the House", ["The Secretary of State", "The Chief Justice", "The Senate Majority Leader"],
         "The Speaker was placed next in line by a law passed in 1947.", "a wooden gavel resting on a desk in an old chamber"),
        ("How many justices sit on the Supreme Court?", "Nine", ["Seven", "Eleven", "Twelve"],
         "The number has stayed at nine since 1869.", "a white marble courthouse with tall columns and wide steps"),
        ("What does the First Amendment protect?", "Freedom of speech", ["The right to bear arms", "Trial by jury", "Protection from searches"],
         "It also protects religion, the press, peaceful assembly and petitions to the government.", "an old printing press in a small-town newspaper office"),
        ("What is the youngest age a person can be elected President?", "35", ["30", "40", "25"],
         "A President must also be a natural-born citizen who has lived here at least fourteen years.", "a birthday cake with candles on a 1950s kitchen table"),
        ("Which document begins with the words We the People?", "The Constitution", ["The Declaration of Independence", "The Bill of Rights", "The Gettysburg Address"],
         "Those three words open its Preamble, written in 1787.", "an old parchment scroll and a quill on a polished wooden table"),
        ("Who is the commander in chief of the armed forces?", "The President", ["The Secretary of Defense", "The Speaker of the House", "The Chief Justice"],
         "Article Two of the Constitution gives the President that role.", "an American flag waving over a military parade ground, 1950s"),
    ], None),
]

hosts_after = {0: "You're doing fine. Arithmetic was always the hardest part for me. Words come next.",
               2: "Halfway there, and the questions get tougher from here. Stay with me.",
               3: "Here comes the hard round. This is the one that sent plenty of us to summer school."}
n = 0
for ri, (rtitle, rline, qs, check) in enumerate(ROUNDS):
    if ri == 4:
        row(type="host", picture="an empty 1950s classroom at dusk, chalkboard and wooden desks", line=hosts_after[3])
    row(type="round", round=rtitle, line=rline)
    for i, (text, right, wrong, fact, pic) in enumerate(qs):
        q(n, text, right, wrong, fact, pic)
        n += 1
    if check:
        row(type="check", line=check)
    if ri in (0, 2):
        row(type="host", picture="a 1950s school hallway with lockers and a clock", line=hosts_after[ri])

pos = 1
opts = ["Alaska", "Hawaii", "Arizona", "New Mexico"]
row(type="bonus", question="Which was the very last state to join the Union?", options=" | ".join(opts), answer="B",
    fact="Hawaii became the fiftieth state on August twenty-first, 1959.", picture="a 1950s ocean liner arriving at a tropical harbor")
row(type="outro", picture="a warm 1950s living room at night with a lamp and a radio",
    line="Under twenty-eight, no worries, school was a long time ago. Twenty-eight to thirty-nine, so close. "
         "Forty or more, you passed. Fifty or more, top of the class. Tell us your score in the comments, "
         "and which round was hardest for you.")
row(type="host", picture="a front porch at dusk with a rocking chair",
    line="Thanks for taking the test with me. Tomorrow I'll bring a new one. Class dismissed.")
row(type="thumbnail", question="1955 | 8TH GRADE TEST", picture="a 1950s schoolroom with a chalkboard, wooden desks and a test paper with an A grade")

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=H)
    w.writeheader()
    w.writerows(rows)
print(OUT, len(rows), "rows,", n, "questions,", sum(r["type"] == "host" for r in rows), "host rows")
