"""Word lists and default tables for the director. Plain data; edit here."""

STOP = frozenset("""a an the and or but nor so yet for of in on at to from by with without into onto over under about as is are was were be been being am do does did done have has had having will would
shall should can could may might must it its this that these those there here he she they them his her their our your you we i me my mine us not no than then too very just also only even still more most much many some any all
each every both either neither such own same other another what which who whom whose when where why how if because while until unless although though whether once again further up down out off s t""".split())
# a contraction of a function word ("it's", "he's", "don't") is itself a function word: a phrase never begins (as a bare edge) or ends on one
CONTRACTIONS = frozenset("""it's he's she's that's there's here's what's who's where's how's when's let's i'm you're we're they're i've you've we've they've i'll you'll he'll she'll we'll they'll it'll
i'd you'd he'd she'd we'd they'd it'd don't doesn't didn't can't couldn't won't wouldn't isn't aren't wasn't weren't hasn't haven't hadn't shouldn't mustn't""".split())
STOP = STOP | CONTRACTIONS
# a single capitalised direction word is not a place ("The South is blazing"); inside a longer name ("South Korea") it is part of the name
DIRECTION_WORDS = frozenset("north south east west northeast northwest southeast southwest northern southern eastern western central upper lower middle inner outer".split())
# words that, just before a place name, make it a yardstick rather than a destination ("the size of England", "bigger than Texas")
COMPARISON_BEFORE = (r"size of", r"sizes of", r"as (?:big|large|small|tall|long|wide|old|rich|poor) as", r"(?:bigger|larger|smaller|greater|taller|longer|wider|older|richer|poorer|heavier|lighter) than",
                     r"(?:times|twice|half) the (?:size|area|population) of", r"area of", r"compared (?:to|with)", r"(?:same|equal) (?:size|area) as", r"similar to", r"equivalent to", r"unlike", r"rather than")
QUESTION_START = ("why", "how", "what", "who", "when", "where", "which", "is", "are", "can", "could", "would", "do", "does", "did", "will", "was", "were")
TWIST = ("but", "however", "yet", "except", "actually", "surprisingly", "instead", "unexpectedly", "twist")
CONCLUSION = ("therefore", "finally", "remember", "overall", "ultimately", "conclusion")
CONCLUSION_PHRASES = ("in the end", "that is why", "that's why", "to sum", "so now", "this is why", "the lesson")
CAUSE = ("because", "so", "therefore", "since", "which means", "leading")
LOSS = frozenset("lost loss lose losing cost costs costly crisis decline fall fell falling fail failed failure war poor poverty debt danger disease famine fear worse worst collapse".split())
GAIN = frozenset("gain gained grow grew growth rich wealth profit rise rose rising win won success built build better best boom invented discovered".split())
# keyword -> asset; checked in order, first hit wins; a caller's table is consulted first
ICONS = {
    "water": "icon:drop", "river": "icon:drop", "rain": "icon:drop", "sea": "icon:drop", "ocean": "icon:drop", "flood": "icon:drop",
    "money": "icon:coin", "price": "icon:coin", "prices": "icon:coin", "cost": "icon:coin", "tax": "icon:coin", "coin": "icon:coin", "trade": "prop:scale", "market": "icon:coin",
    "gold": "prop:chest", "treasure": "prop:chest", "silver": "prop:chest",
    "people": "icon:person", "farmers": "icon:person", "workers": "icon:person", "farmer": "icon:person", "worker": "icon:person", "king": "icon:person", "citizens": "icon:person", "population": "icon:person",
    "home": "icon:house", "homes": "icon:house", "house": "icon:house", "city": "icon:house", "village": "icon:house", "town": "icon:house",
    "year": "icon:clock", "years": "icon:clock", "century": "icon:clock", "time": "icon:clock", "decade": "icon:clock", "age": "icon:clock",
    "danger": "icon:warning", "crisis": "icon:warning", "warning": "icon:warning", "war": "icon:warning", "risk": "icon:warning", "famine": "icon:warning",
    "law": "icon:document", "laws": "icon:document", "document": "icon:document", "paper": "icon:document", "treaty": "icon:document", "record": "icon:document",
    "machine": "icon:gear", "engine": "icon:gear", "factory": "icon:gear", "system": "icon:gear", "press": "icon:gear", "technology": "icon:gear",
    "book": "prop:book", "books": "prop:book", "read": "prop:book", "printing": "prop:book", "idea": "prop:bulb", "ideas": "prop:bulb", "invention": "prop:bulb", "invented": "prop:bulb",
    "key": "prop:key", "secret": "prop:key", "flag": "prop:flag", "nation": "prop:flag", "empire": "prop:flag", "country": "prop:flag",
    "justice": "prop:scale", "balance": "prop:scale", "search": "prop:magnifier", "investigate": "prop:magnifier", "discovered": "prop:magnifier", "note": "prop:note",
}

# generic words that may sit inside a phrase but never begin or end one (and carry almost no weight)
WEAK = frozenset("almost simply really just very many some other also even still quite rather thing things way one two often always never ever already now soon today".split())
# a clause begins at these words (a phrase never runs across them); "and" is not here because it joins nouns ("pipes and pumps")
SOFT_BREAK = frozenset("but so because which while when if then until although whereas since".split())

# words that may BEGIN a phrase although they are function words, because they change its meaning ("no tools", "every hundred metres", "only a few centimetres")
LEADING_OK = frozenset("no not never every each all only more most less few same".split())

# function words that may begin a phrase when the phrase is a whole clause ("who could argue", "how do you bring water to thirsty people", "it was too shallow")
CLAUSE_START_OK = frozenset("who what how why where when which that it we they he she you i there".split())


# ---- cartoon beats (Phase 7): which scene a beat suggests, which props and which people words it carries; first-hit counts decide, the table order breaks ties ----
SET_WORDS = {
    "field": "farm farms farmer farmers farming field fields crop crops harvest wheat grain plantation soil rain rains".split(),
    "town": "village villages town towns home homes house houses families family neighbours desert square".split(),
    "city": "city cities market markets bank banks capital street streets factory factories shop shops office offices".split(),
    "harbour": "harbour harbor port ports ship ships sea boat boats sail sailors sailing dock docks voyage".split(),
    "room": "room rooms school classroom parliament court palace throne meeting council ministry students teacher king queen".split(),
}
PEOPLE_WORDS = frozenset("people families family farmers workers citizens villagers crowd everyone children kids men women population residents sailors students".split())
PROP_WORDS = {"house": "house houses home homes village".split(), "tree": "tree trees forest wood timber".split(), "cactus": "desert cactus dry".split(), "fence": "fence fences border wall walls boundary".split(),
              "flag": "flag flags nation country empire king government".split(), "sign": "law laws rule rules notice price prices tax taxes sign".split(), "crate": "trade goods cargo crates grain barrels".split()}
DUSK_WORDS = frozenset("evening dusk sunset night twilight".split())
