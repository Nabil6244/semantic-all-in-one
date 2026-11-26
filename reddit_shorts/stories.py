"""Original Reddit-style stories for Ch1 Shorts (written here, not copied from any real post).

Each story: id, sub (shown on the card), user, title (read first), body (~150 words), voice.
"""

M = "en-US-AndrewNeural"
F = "en-US-AvaNeural"

STORIES = [
    dict(id="grandma_house", sub="AmITheJerk", user="quiet_lemon_88", voice=F, ups="24.1k", com="3.2k",
         title="Am I the jerk for refusing to give my sister the house our grandma left me?",
         body="My grandma left me her house. Just me. My sister got her jewelry and a letter. "
              "The day after the funeral, my sister showed up with a lawyer and said the house should be split, "
              "because she has kids and I live alone. My mom took her side. My dad stopped answering my calls. "
              "For two weeks I was the villain of the whole family. Then my sister finally opened grandma's letter. "
              "She had been too angry to read it. Inside, grandma explained everything. Ten years ago, "
              "my sister borrowed forty thousand dollars from her and never paid a cent back. "
              "Grandma wrote, the house is your sister's half, plus interest. "
              "My sister read it out loud at Sunday dinner, by accident, thinking it was a sweet goodbye. "
              "Nobody said a word. Then my dad passed me the potatoes. So, am I the jerk?"),
    dict(id="boss_impression", sub="TodayIMessedUp", user="replyall_regret", voice=M, ups="41.7k", com="5.9k",
         title="Today I messed up by sending my boss impression to the entire company.",
         body="Our boss has a very specific way of talking. Every sentence starts with, so here's the thing, "
              "and ends with, let's circle back. I do a perfect impression of him. My coworkers love it. "
              "So on Friday I recorded a voice memo, two full minutes of him explaining why the coffee machine "
              "is a team player, and I sent it to my work best friend. Except I didn't. "
              "I sent it to the all staff channel. Four hundred people. I watched the little numbers go up. "
              "Fifty listens. Ninety. Then my boss reacted with a thumbs up. My stomach dropped. "
              "Ten minutes later he called me into his office. He sat down, looked at me, and said, "
              "so here's the thing. You're doing the company holiday video. I am now the official voice "
              "of our office. Let's circle back."),
    dict(id="package_thief", sub="PettyPayback", user="porch_patrol", voice=M, ups="33.5k", com="2.1k",
         title="My neighbor kept stealing my packages, so I sent him exactly what he deserved.",
         body="Three packages in one month. My camera showed the same guy every time. My neighbor, "
              "the one who waves at me every morning. The police said there wasn't much they could do. "
              "So I ordered the biggest, heaviest box I could find. Inside, I packed forty pounds of rocks "
              "from my backyard, and one small note. I left it on my porch and waited. "
              "At two in the afternoon, there he was. He tried to pick it up casually. It did not move. "
              "He squatted. He groaned. He dragged it across my lawn like a dead body, "
              "all the way to his garage, in front of three other neighbors who were watching. "
              "That night his wife knocked on my door, holding the note. It said, return my other three boxes "
              "and you can keep the rocks. They were on my porch by morning."),
    dict(id="surprise_party", sub="AmITheJerk", user="not_a_party_girl", voice=F, ups="19.8k", com="4.4k",
         title="Am I the jerk for walking out of my own surprise party?",
         body="I hate surprise parties. Everyone knows this. I've said it for years. "
              "So for my thirtieth birthday, my best friend threw me one anyway. Fifty people jumped out, "
              "music blasting, and I stood there frozen. Fine. I smiled. I stayed. "
              "Then halfway through, she tapped her glass, and her boyfriend got down on one knee. "
              "In front of everyone. At my birthday. My cake still had my name on it. "
              "People forgot I existed. Someone moved my cake to make room for champagne. "
              "So I quietly took my coat and went home. She called me selfish the next day. "
              "Here's the twist. Her boyfriend texted me later and said sorry. "
              "He told me the party was his idea. He'd begged her for weeks to propose somewhere else, "
              "and she told him, no, my birthday was perfect, because everyone would already be there."),
    dict(id="fridge_labels", sub="PettyPayback", user="snack_lawyer", voice=M, ups="28.3k", com="1.7k",
         title="My roommate labeled everything in the fridge, so I labeled him.",
         body="My roommate started labeling his food. Fine. Then he labeled the shelves. "
              "Then the ice cube tray. Then he put a label on the light inside the fridge that said, "
              "Derek's light, do not use after ten. So I bought a label maker. "
              "While he was at work, I labeled everything he owned that I had paid for. "
              "The couch, half mine. The TV, mine. The wifi router, mine. "
              "The toilet paper. Every single roll said, property of Sam, ask before use. "
              "He came home, walked into the bathroom, and I heard a very long silence. "
              "Then he knocked on my door holding a roll and said, can we talk? "
              "We had a two hour roommate meeting. The labels are gone now. "
              "Except one. He left the label on the fridge light. He said it was funny. "
              "Honestly, it is."),
    dict(id="stolen_project", sub="WorkStories", user="slide_forty_two", voice=F, ups="37.2k", com="3.8k",
         title="My coworker stole credit for my project, so I let him present it.",
         body="I spent three months building a project. My coworker added his name to the first slide "
              "and told our manager he led the whole thing. I didn't argue. I just asked one question. "
              "Would he like to present it to the directors? He said absolutely. "
              "What he didn't know is that I build every presentation the same way. "
              "Slide forty two is a hidden slide. It only shows up if you skip ahead. "
              "And every time he rushed, he skipped ahead. Slide forty two said, "
              "if you are reading this, ask the presenter how the pricing model works. "
              "The directors read it. They asked. He had no idea. Silence. "
              "Then the head director turned to me and said, I'm guessing you know. "
              "I did. I walked them through all of it. I'm leading the next three projects. "
              "He now asks me before he touches a slide."),
    dict(id="library_note", sub="TrueStoriesHub", user="overdue_since_87", voice=M, ups="52.6k", com="6.3k",
         title="I found a note in a library book from 1987, so I tracked down the person who wrote it.",
         body="I borrowed an old book about lighthouses. Inside the back cover was a folded note. "
              "It said, if you are reading this, I hope you finally went to see one. Love, June. 1987. "
              "There was a town name on the back. I couldn't stop thinking about it. "
              "So I searched the town, the name, and old newspapers. It took me two months. "
              "June was eighty one, living in a care home three hours away. I drove there with the book. "
              "When I gave her the note, she laughed so hard she cried. "
              "She wrote it for her husband. He was afraid of the ocean and never went. "
              "He passed before he could. And then she told me the best part. "
              "She never went either. So last Saturday, June and I went to see a lighthouse together. "
              "She brought a new note. She left it in the visitor book."),
    dict(id="deposit_lease", sub="PettyPayback", user="read_the_fine_print", voice=F, ups="45.9k", com="4.0k",
         title="My landlord kept my deposit, so I finally read the lease properly.",
         body="I moved out and left the apartment spotless. My landlord kept my entire deposit anyway. "
              "He said the paint was the wrong shade of white. I painted it the same color he gave me. "
              "He didn't care. So I sat down and read all thirty pages of the lease. Every line. "
              "On page twenty six, there was a clause he clearly copied from the internet. "
              "It said the landlord must return the deposit within fourteen days, "
              "or pay the tenant three times the amount. It had been twenty days. "
              "I sent him a polite letter with the page number highlighted. "
              "He called me furious. He said nobody reads page twenty six. "
              "I said, well, you wrote it. Two days later I got a check for triple my deposit. "
              "The memo line just said, paint."),
    dict(id="mom_groupchat", sub="TodayIMessedUp", user="wrong_chat_again", voice=M, ups="30.4k", com="2.6k",
         title="Today I messed up by sending my mom the message meant for my brother.",
         body="My mom's birthday was coming up, and my brother and I were planning a surprise trip. "
              "She has wanted to see Italy her whole life. We saved for a year. "
              "Last night I typed, she is going to cry so hard, she has no idea, "
              "and hit send. In my mom's chat. I saw the read receipt instantly. Then the typing dots. "
              "They stopped. They started again. I panicked and sent, that was for a work friend. "
              "She replied with one word. Okay. The next morning, my brother called me laughing. "
              "Mom had sent him a long message saying she thinks I'm planning to propose to someone at work, "
              "and she wants to meet her first. So now the surprise is safe. "
              "But apparently I'm engaged. And mom has already told the whole family."),
    dict(id="own_the_place", sub="WorkStories", user="acting_owner", voice=F, ups="48.8k", com="5.1k",
         title="My boss told me to work like I own the place, so I did.",
         body="At our team meeting, my manager said, I want everyone to work like they own the place. "
              "So the next day, I did exactly that. I came in at ten, because owners set their own hours. "
              "I took a ninety minute lunch with a client, because owners build relationships. "
              "I fixed the broken printer myself, ordered better coffee, and canceled two pointless meetings, "
              "because owners hate wasting money. My manager called me in, furious. "
              "Then the actual owner of the company walked past and asked who canceled the Tuesday meeting. "
              "My manager pointed at me. The owner said, thank God. That meeting cost us six hours a week. "
              "Then he asked who ordered the new coffee. I raised my hand. He shook it. "
              "I now report directly to him. My old manager still says, work like you own the place. "
              "Just not to me."),
]
