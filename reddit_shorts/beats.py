"""Narration-matched pictures per story. Each beat = (first words of the line it starts on, picture).
"" starts at the title. Pictures are painted once by Flow into reddit_shorts/stories/<id>/places/b<N>.png.
cast = fixed look of the recurring people, added to every prompt so they stay the same."""

BEATS = {
    "grandma_house": dict(
        cast="Narrator: a young woman, late 20s, short brown bob hair, green sweater. Sister: woman with long blonde hair, red coat. Grandma: kind old lady, white bun, glasses",
        beats=[
            ("", "the narrator standing in front of a cosy old cottage with a garden and a front porch, holding a set of keys, surprised"),
            ("my grandma left me", "grandma in a rocking chair smiling warmly next to the narrator as a little girl, old family photo feeling"),
            ("the day after the funeral", "the sister at the front door with a stern lawyer in a grey suit holding papers, the narrator shocked inside"),
            ("my mom took her side", "a family living room, mom and dad standing with arms crossed behind the sister, the narrator alone on the other side"),
            ("for two weeks", "the narrator sitting alone at night on a sofa with a phone showing no replies, sad, rain on the window"),
            ("then my sister finally opened", "the sister holding an open handwritten letter in an envelope, eyes wide"),
            ("ten years ago", "flashback: the sister young, taking a thick stack of money from grandma at a kitchen table, sepia tones"),
            ("my sister read it out loud", "a big Sunday family dinner table with roast and potatoes, the sister standing reading the letter, everyone frozen in shock"),
            ("nobody said a word", "the dad smiling quietly passing a bowl of potatoes across the table to the narrator"),
        ]),
    "boss_impression": dict(
        cast="Narrator: young man, curly black hair, blue shirt. Boss: tall bald man, grey suit, bushy eyebrows",
        beats=[
            ("", "the narrator at an office desk staring at a laptop in horror, hands on his head"),
            ("our boss has a very specific", "the boss talking with big hand gestures in front of a whiteboard in a meeting room"),
            ("i do a perfect impression", "the narrator doing a funny impression of the boss for laughing coworkers by the water cooler"),
            ("so on friday i recorded", "the narrator recording a voice memo on his phone next to an office coffee machine, grinning"),
            ("i sent it to the all staff", "a huge open-plan office, hundreds of employees all looking at their screens at once"),
            ("then my boss reacted", "close view of the narrator sweating at his desk, pale, a coworker behind him gasping"),
            ("ten minutes later", "the boss's office, the boss sitting behind a big desk, the narrator standing nervous in front"),
            ("you're doing the company holiday video", "the narrator in front of a camera and a microphone in a festive office with decorations, the boss giving a thumbs up"),
        ]),
    "package_thief": dict(
        cast="Narrator: man in his 30s, beard, orange hoodie. Neighbour: skinny middle-aged man, moustache, white tank top, cap",
        beats=[
            ("", "a suburban front porch with an empty doormat and a doorbell camera, the narrator looking annoyed"),
            ("three packages in one month", "doorbell camera view: the neighbour sneaking off a porch with a cardboard box under his arm"),
            ("the police said", "the narrator talking to a shrugging police officer on the sidewalk"),
            ("so i ordered the biggest", "the narrator in a backyard shovelling rocks into a giant cardboard box"),
            ("i left it on my porch", "the narrator peeking through window blinds, a big box waiting on the porch outside"),
            ("he tried to pick it up", "the neighbour straining to lift a huge box on the porch, face red"),
            ("he dragged it across my lawn", "the neighbour dragging the giant box across the lawn while three neighbours watch from their yards laughing"),
            ("that night his wife knocked", "night, a woman in a bathrobe at the narrator's door holding a small note, unimpressed"),
            ("they were on my porch by morning", "morning sun, three cardboard boxes stacked neatly on the narrator's porch, the narrator smiling with coffee"),
        ]),
    "surprise_party": dict(
        cast="Narrator: woman, 30, long curly red hair, yellow dress. Best friend: woman with black braids, purple dress. Boyfriend: man with glasses, navy suit",
        beats=[
            ("", "the narrator frozen in a doorway as a crowd jumps out shouting surprise, balloons and streamers"),
            ("i hate surprise parties", "the narrator with arms crossed shaking her head, a calendar with a birthday circled behind her"),
            ("so for my thirtieth birthday", "a packed living room party, fifty guests, music, a big banner shape with no writing"),
            ("then halfway through", "the best friend tapping a champagne glass with a spoon, the crowd turning"),
            ("in front of everyone", "the boyfriend down on one knee holding a ring box in front of the best friend, crowd cheering"),
            ("people forgot i existed", "a birthday cake pushed aside on a table to make room for champagne bottles"),
            ("so i quietly took my coat", "the narrator slipping out the front door at night with her coat, party lights behind her"),
            ("her boyfriend texted me later", "the narrator on her bed at home reading a phone message, surprised"),
        ]),
    "fridge_labels": dict(
        cast="Narrator: young man, messy blond hair, grey t-shirt. Roommate Derek: tall man, neat side parting, polo shirt, glasses",
        beats=[
            ("", "an open fridge full of food with little white labels stuck on everything, the narrator staring"),
            ("my roommate started labeling", "Derek proudly sticking labels on fridge shelves and an ice cube tray"),
            ("so i bought a label maker", "the narrator holding a label maker like a weapon, evil grin"),
            ("the couch half mine", "a living room where the couch, TV and router all have big white labels stuck on them"),
            ("he came home", "Derek standing frozen in a bathroom staring at labelled toilet paper rolls"),
            ("can we talk", "Derek at the narrator's bedroom door holding a toilet paper roll, awkward"),
            ("we had a two hour", "the two roommates sitting at a kitchen table with notes, a serious meeting, clock on the wall"),
            ("except one", "the fridge light glowing inside an open fridge with one tiny label, both roommates laughing"),
        ]),
    "stolen_project": dict(
        cast="Narrator: woman, 30s, black hair in a bun, white blazer. Coworker: smug young man, slicked-back hair, tight beige suit",
        beats=[
            ("", "a conference room with a big projector screen, the coworker presenting, the narrator watching calmly"),
            ("i spent three months", "the narrator working late at a desk covered in charts and coffee cups, night city outside"),
            ("my coworker added his name", "the coworker shaking the manager's hand, the narrator behind them unimpressed"),
            ("would he like to present", "the coworker giving two thumbs up, confident"),
            ("slide forty two is a hidden", "the narrator's laptop screen showing a grid of slide thumbnails, one glowing"),
            ("the directors read it", "a long boardroom table of serious directors in suits, all looking at the coworker"),
            ("he had no idea", "the coworker sweating at the front of the room, a blank face"),
            ("i did", "the narrator presenting confidently at the screen, the directors nodding"),
        ]),
    "library_note": dict(
        cast="Narrator: young man, short dark hair, round glasses, brown cardigan. June: very old lady, silver curls, pink cardigan, bright eyes",
        beats=[
            ("", "a cosy old library aisle, the narrator holding an old book about lighthouses with a folded note falling out"),
            ("i borrowed an old book", "close view of an old yellowed handwritten note on top of a book with a lighthouse on the cover"),
            ("so i searched the town", "the narrator at home at night surrounded by old newspapers and a laptop, map on the wall"),
            ("june was eighty one", "the narrator driving a small car along a coast road holding the book on the passenger seat"),
            ("when i gave her the note", "June in a care home armchair laughing with tears, holding the note, the narrator beside her"),
            ("she wrote it for her husband", "flashback in warm sepia: a young couple on a pier, the man nervously looking at big waves"),
            ("she never went either", "June and the narrator sitting together, June smiling with a twinkle"),
            ("so last saturday", "June in a wheelchair and the narrator in front of a tall red and white lighthouse by the sea, sunny day"),
        ]),
    "deposit_lease": dict(
        cast="Narrator: woman, 20s, purple hair in a ponytail, denim jacket. Landlord: chubby older man, comb-over, brown vest",
        beats=[
            ("", "the narrator in an empty clean apartment holding a paint roller, hands on hips"),
            ("i moved out", "a spotless empty white apartment with a sparkling floor, moving boxes by the door"),
            ("he said the paint was the wrong", "the landlord squinting at a white wall with a magnifying glass, shaking his head"),
            ("so i sat down and read", "the narrator at a kitchen table with a thick stack of papers, coffee and a highlighter"),
            ("on page twenty six", "close view of a document page with one paragraph highlighted in bright yellow"),
            ("i sent him a polite letter", "the narrator dropping an envelope into a red mailbox, smiling"),
            ("he called me furious", "the landlord red-faced yelling into an old phone in a cluttered office"),
            ("two days later", "the narrator happily holding up a paper check at her new apartment, confetti feeling"),
        ]),
    "mom_groupchat": dict(
        cast="Narrator: young man, buzz cut, red hoodie. Brother: guy with a man bun, green jacket. Mom: cheerful woman, 50s, short grey hair, floral blouse",
        beats=[
            ("", "the narrator lying on a bed staring at his phone in horror, hand over mouth"),
            ("my mom's birthday was coming up", "the narrator and his brother at a table with a laptop showing a map of Italy, a piggy bank full of coins"),
            ("she has wanted to see italy", "mom daydreaming at a kitchen window, a dreamy cloud showing the Colosseum and gondolas"),
            ("last night i typed", "the narrator typing on his phone at night on the sofa, grinning"),
            ("i saw the read receipt", "mom in her kitchen looking at her phone, eyebrows raised"),
            ("i panicked", "the narrator panicking, phone in both hands, sweat drops"),
            ("the next morning", "the brother laughing loudly on a phone call in a car"),
            ("but apparently i'm engaged", "a big family living room, relatives cheering and hugging a very confused narrator, mom beaming"),
        ]),
    "own_the_place": dict(
        cast="Narrator: woman, 30s, afro hair, orange blazer. Manager: thin man, small moustache, too-tight tie. Owner: friendly older man, white beard, cardigan",
        beats=[
            ("", "the narrator walking into an office like a boss with sunglasses and a coffee, coworkers staring"),
            ("at our team meeting", "the manager pointing at a team around a meeting table, motivational posture"),
            ("i came in at ten", "a wall clock showing ten, the narrator strolling in relaxed"),
            ("i took a ninety minute lunch", "the narrator at a nice restaurant table laughing with a client"),
            ("i fixed the broken printer", "the narrator fixing an office printer with a screwdriver, a fancy new coffee machine beside it"),
            ("my manager called me in", "the manager furious behind his desk, veins popping, the narrator calm"),
            ("then the actual owner", "the owner leaning into the doorway smiling, the manager shocked"),
            ("he shook it", "the owner shaking the narrator's hand in the hallway, coworkers clapping"),
        ]),
}
