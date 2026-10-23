"""Five synthetic topics for the director verification: a script, and word times made by rule (0.294 s per word, 0.7 s between sentences; the app's words have no punctuation
and no capitals). NOT a human voice. Each topic exercises something different: places, numbers, no place at all, an archive picture, loss words and a conclusion."""
import re

TOPICS = {
    "aqueducts": ("Every city begins with a simple problem: how do you bring water to thirsty people? The oldest answer was a ditch, dug by hand across the land. Then the Romans built the aqueduct, "
                  "a channel lifted on arches so that gravity could keep working across a valley. Engineers measured the slope with almost no tools, a drop of only a few centimetres in every hundred metres. "
                  "But if the slope was too steep, the water tore the stone apart. If it was too shallow, the water simply stopped. Rome solved this eleven times over, and each line carried water from a different spring. "
                  "Today the same idea hides under the streets of Italy, in pipes and pumps. So the principle has not changed: water still travels downhill, and every system we build is a way of persuading it to go where we need."),
    "coffee": ("Why did a small red fruit from Ethiopia change the whole world? Legend says a goat herder noticed his goats dancing after eating the berries. By the year 1600 coffee had crossed the sea to Arabia, "
               "and merchants guarded the beans like gold. But the Dutch smuggled a single plant to their islands, and the monopoly broke. Brazil planted millions of trees, and prices fell. "
               "Soon farmers in Colombia were growing coffee on steep mountain slopes. Today more than 2 billion cups are drunk every day. So the story of coffee is really a story of trade, and of the people who work the land."),
    "inflation": ("What happens when a loaf of bread costs a million marks? In 1923 workers were paid twice a day, because the money lost its value by the afternoon. Families carried wheelbarrows of cash to the shop. "
                  "Savings built over a lifetime became worthless in weeks. But the cause was simple: the government printed money to pay its debts. Prices rose faster than anyone could count. "
                  "Then a new currency arrived, and the crisis ended almost overnight. In 2008 another crisis showed that the lesson is easy to forget. That is why money is only a promise, and trust is what keeps it alive."),
    "printing": ("Before 1440 a single book took a monk many months to copy. Then a goldsmith in Mainz, in Germany, built a machine with movable metal letters. The printing press could make hundreds of pages in a day. "
                 "Ideas spread faster than any army could march. Within fifty years millions of books filled the cities of Europe. But the rulers were afraid, and they tried to control every page. "
                 "Readers wanted to learn, and the books slipped across borders. So one machine changed who could read, who could argue, and who could be heard."),
    "glaciers": ("High in the Alps the ice has been melting for a hundred years. The glaciers of Greenland now lose more than 250 billion tonnes of ice every year. Scientists drill deep into the ice to read the air of the past. "
                 "Each layer is a record of one winter. But the fastest loss is happening now, and the sea is rising along every coast. Iceland has already lost its first glacier. Farmers below the mountains fear for their water. "
                 "In the end the ice is a clock, and it is telling us how much time we have."),
}
PLACES = {"aqueducts": [], "coffee": [], "inflation": [], "printing": [], "glaciers": []}
ARCHIVE_TOPIC = "printing"


def words_from_script(script: str, speed: float = 0.294, pause: float = 0.7, start: float = 0.5):
    words, t = [], start
    for sent in re.split(r"(?<=[.!?])\s+", script.strip()):
        for tok in sent.split():
            clean = re.sub(r"[^\w']+", "", tok.lower().replace("-", ""))
            if not clean:
                continue
            words.append((clean, round(t, 3), round(t + speed * 0.85, 3)))
            t += speed
        t += pause
    return words, round(words[-1][2] + 0.4, 3)
