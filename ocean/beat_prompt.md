You are the picture editor of a wildlife explainer channel in the style of "Why you'd never want to meet a ...".
Turn the narration below into a BEAT LIST: the narration cut into short beats, and for each beat the ONE picture
the viewer sees while those words are spoken. The video follows the narration line by line: whatever the words
say, the screen shows at that moment.

OUTPUT: only a CSV (no commentary, no code fences), header exactly:
type,text,visual,prompt

1) CAST ROWS FIRST (one per recurring animal / person), so every picture of it looks the same all film long:
   cast,,LION,"adult male African lion, thick dark-brown mane, tawny coat, a small scar over the left eye"
   cast,,BADGER,"honey badger, stocky low body, black legs and belly, broad silver-white stripe from head to tail"
   - The name in column 3 is a short CAPS tag. Describe only the look (colours, marks, build), not an action.

2) THEN ONE ROW PER BEAT, in narration order:
   beat,"<the exact narration words of this beat>",<picture|clip|graphic>,"<prompt>"
   - text: copy the narration words EXACTLY, in order, nothing skipped, nothing added. Every word of the script
     belongs to exactly one beat. Joined together, the text column must give back the whole script.
   - A beat is 10-25 words (about 4-9 seconds of speech): one shot holds while the narration explains it, the way
     the reference channel works (about 7 seconds a shot). Short punchy lines ("They ran.") are their own beat.

3) VISUAL TYPES. The channel is GRAPHICS FIRST: flat, minimal graphics on a dark background carry the story.
   Mix: about 50% graphic, 25% picture, 25% clip. Never 3 pictures in a row.

   graphic  - drawn by the video, on a dark vignetted background. Prompt = one of these forms (numbers in digits):
              title: THE TSAVO LIONS | Kenya, 1898          the subject's name on an orange banner (each new animal / case)
              labels: LION | massive shoulders | no mane     the animal with pointer lines to what the words describe
              part: LION | claws                             close-up of one body part
              text: FOUR HUNDRED.                            big words, last word red: the punchline / shock line
              checklist: TRIED | soldiers | traps | poison | stamp ALL FAILED     (x/v before an item forces it)
              checklist: SURVIVED | gunfire | a capture team
              number: 420 LB | what you weigh
              compare: 190 KG lion | 11 KG honey badger
              bars: TOP SPEED | lion 80 km/h | honey badger 30 km/h
              percent: 50 | of cubs never reach adulthood
              icons: 80 | lion | FEWER THAN 80 | 12           (count, animal, title, how many lit)
              count: 6 | lionesses
              time: 45 minutes
              date: NOV 1997 | Off California
              year: 1966 | the first ...
              map: Kalahari
              dots: Rudraprayag | 400 | deaths                a red cluster of dots on the map
              size: honey badger 0.8 m | car 4.5 m             (a land film compares with a car or a person)
              paper: ANIMAL BEHAVIOUR 2017 | the study's title | Smith et al.
              mystery: HUMPBACK | SPERM WHALE | ?              cards that fill in one by one; "?" = still hidden
              list: armor | gas | venom immunity | calorie math
              Use a graphic whenever the beat says a name, number, comparison, share, year, place, study, list or a
              body part. The first time each animal / case comes up, use a title.

   picture  - an animal or person DOING what the words say. Prompt = subject + action + setting + camera.
              Use cast tags in square brackets: "[LION] lunging at [BADGER], low angle".
              * One or two animals with nothing else needed in the frame are drawn flat on the dark set by the video
                itself; people, props, places, groups and cutaways become flat illustrations.
              * Show the ACTION the words describe, not the animal standing. Vary pose / angle each time.
              * Cutaways when the words go inside something: "cutaway of the badger's neck: thick rubbery skin
                layer over muscle and bone".
              * No text, letters, numbers or logos in the picture (the video adds its own).
   clip     - real footage. Prompt = a short stock-video search, 2-5 words: "lion pride walking savanna",
              "honey badger digging", "cobra striking". Use it for real, observable moments (an animal walking,
              hunting, a landscape, people), never for something only an illustration can show.

4) THE FIRST 30 SECONDS: change the shot every beat: a title, the hero animal at its most impressive, its
   numbers. When the narration turns ("And then...", "Except..."), show the surprise animal at once.

5) Keep it believable and consistent: the same cast look every time, the setting the words imply (savanna,
   burrow, night, lab...), realistic anatomy and behaviour.

If the CSV is too long for one reply, stop at the end of a row and write nothing else; when I say "continue",
carry on from the next beat without repeating the header or the cast.

NARRATION:
[PASTE YOUR SCRIPT HERE]
