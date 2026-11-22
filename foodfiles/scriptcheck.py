"""Food Files script checker (docs/food_files/SCRIPT_STUDY.md section 9): measures a script against the format of the
top videos before it becomes a CSV. No network, no AI: plain counting.

Input: the script as paragraphs - the cold open first, one paragraph per item, the outro last (script_prompt.txt asks
for exactly that). check(text) -> {"ok", "problems", "notes", "stats"}.

  python -m foodfiles.scriptcheck my_script.txt
"""
import re
import sys
from pathlib import Path

WPM = 172
FALLOUT = re.compile(r"\b(recall\w*|sued|lawsuit|settle\w*|banned?|fined?|prison|jail\w*|sentenced|charged|guilty|law|act|"
                     r"pulled|bankrupt\w*|shut down|warning|died|dead|deaths?|killed|hospitali[sz]ed|sick|poisoned|"
                     r"cease|investigat\w*|executed|discontinued|blocked|seized)\b", re.I)
YEAR = re.compile(r"\b(1[6-9]\d\d|20[0-4]\d)\b|\b(nineteen|twenty)[ -](hundred|oh|o|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                  r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\b|"
                  r"\b(eighteen|seventeen|sixteen)[ -](fifty|sixty|seventy|eighty|ninety|forty|thirty|twenty|hundred)\b", re.I)
AGE = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
                 r"seventeen|eighteen|nineteen|twenty[\w-]*|thirty[\w-]*|forty[\w-]*|fifty[\w-]*|sixty[\w-]*|seventy[\w-]*|"
                 r"eighty[\w-]*)[ -]year[ -]old\b", re.I)
NUMBER = re.compile(r"\b\d[\d,.]*\b|\b(hundred|thousand|million|billion|dozens?|half|twice|double|triple|percent)\b|"
                    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|"
                    r"sixty|seventy|eighty|ninety)\b", re.I)
BRIDGE = re.compile(r"\bthis (next|last|final)\b|\bnext (one|candy|snack|drink|item|story|product|company|chain|cereal|meal|sweet)\b",
                    re.I)
REHOOK = re.compile(r"(as bad as it gets|we still (got|have)|still to come|coming up|stick around|it only gets worse|"
                    r"the worst is still)", re.I)
TWIST = re.compile(r"here'?s the (part|twist|thing|weird|creepy|crazy|kicker|catch|scariest|worst)|it gets worse|"
                   r"believe it or not|sounds fake|but here'?s", re.I)
STARTS = ("and", "but", "so")


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if s.strip()]


def words(text):
    return re.findall(r"[A-Za-z0-9'’$%,.-]+", text)


def paragraphs(text):
    ps = [p.strip() for p in re.split(r"\n\s*\n|\r\n\s*\r\n", str(text or "")) if p.strip()]
    if len(ps) == 1:                       # one block: split before every bridge's next sentence
        ps = split_on_bridges(ps[0])
    return [p for p in ps if not re.match(r"^\s*sources?\s*:", p, re.I)]


def split_on_bridges(text):
    out, cur = [], []
    for s in sentences(text):
        cur.append(s)
        if BRIDGE.search(s) and len(" ".join(cur).split()) > 120:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def check(text):
    text = str(text or "")
    body = re.split(r"\n\s*SOURCES?\s*:", text, flags=re.I)[0]
    paras = paragraphs(body)
    problems, notes = [], []
    all_words = words(body)
    n_words = len(all_words)
    minutes = n_words / WPM
    sents = sentences(body)
    open_p, items, outro = (paras[0], paras[1:-1], paras[-1]) if len(paras) >= 3 else (paras[0] if paras else "", paras[1:], "")
    # length
    if not 2300 <= n_words <= 3300:
        problems.append(f"{n_words} words (~{minutes:.1f} min); the format is 2,500-3,100 words (14.5-18 min)")
    if not 8 <= len(items) <= 13:
        problems.append(f"{len(items)} items; the format is 8-12 (one paragraph per item)")
    # cold open
    ow = len(open_p.split())
    if not re.search(r"^\s*from\b", open_p, re.I):
        problems.append("the cold open should start 'From [teaser] to [teaser], these are the...'")
    if not re.search(r"\bbut first\b", open_p, re.I) and not (items and re.search(r"\bbut first\b", items[0], re.I)):
        problems.append("no 'But first, we're starting with...' into item 1")
    if ow > 90 and not re.search(r"\bbut first\b", open_p[:600], re.I):
        notes.append(f"the cold open is {ow} words before item 1 starts (aim for 30-60)")
    # items
    for i, p in enumerate(items, 1):
        w = len(words(p))
        miss = []
        if not 200 <= w <= 450:
            miss.append(f"{w} words (220-420)")
        if not YEAR.search(p):
            miss.append("no year")
        if not (AGE.search(p) or re.search(r"\b(kids?|children|toddlers?|students?|people|customers|workers|family|"
                                             r"boy|girl|man|woman|teen\w*|mother|father|dad|mom|son|daughter)\b", p, re.I)):
            miss.append("no person")
        if len(NUMBER.findall(p)) < 3:
            miss.append("fewer than 3 numbers")
        if not FALLOUT.search(p):
            miss.append("no fallout (recall, lawsuit, ban, deaths...)")
        if i < len(items) and not BRIDGE.search(" ".join(sentences(p)[-2:])):
            miss.append("no bridge into the next item at its end")
        if miss:
            problems.append(f"item {i}: " + ", ".join(miss))
    # retention
    if items:
        start_i, end_i = int(len(items) * 0.35), max(int(len(items) * 0.65), int(len(items) * 0.35) + 1)
        if not any(REHOOK.search(p) for p in items[start_i:end_i + 1]):     # half the top videos have one: recommended
            notes.append("no mid-video re-hook ('...we still got [teasers]') between 40 % and 60 % - recommended")
    twists = sum(1 for p in items if TWIST.search(p))
    if items and twists < len(items) / 3:
        notes.append(f"only {twists} item(s) with a twist line ('here's the part...', 'it gets worse'); aim for one in two")
    # outro
    if not re.search(r"click (this|the) video", outro, re.I):
        problems.append("the outro does not send viewers to the next video ('click this video right here')")
    if not re.search(r"next time you", outro, re.I):
        notes.append("the outro has no 'the next time you...' advice line")
    # voice
    starts = sum(1 for s in sents if s.split()[0].strip(",").lower() in STARTS) / max(1, len(sents))
    avg = n_words / max(1, len(sents))
    if starts < 0.25:
        notes.append(f"{starts:.0%} of sentences start with And / But / So (the format is ~40 %)")
    if not 11 <= avg <= 19:
        notes.append(f"sentences average {avg:.1f} words (the format is 14-15)")
    per_min = len(NUMBER.findall(body)) / max(0.1, minutes)
    stats = {"words": n_words, "minutes": round(minutes, 1), "items": len(items), "and_but_so": round(starts, 2),
             "avg_sentence": round(avg, 1), "numbers_per_min": round(per_min, 1), "twists": twists}
    return {"ok": not problems, "problems": problems, "notes": notes, "stats": stats}


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    r = check(Path(a[0]).read_text(encoding="utf-8-sig"))
    print(r["stats"])
    for p in r["problems"]:
        print("  PROBLEM:", p)
    for n in r["notes"]:
        print("  note:", n)
    print("OK" if r["ok"] else f"{len(r['problems'])} problem(s)")


if __name__ == "__main__":
    main()
