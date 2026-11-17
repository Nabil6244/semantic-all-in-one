"""Urdu story 1 - "Ayan Bhalu aur Shahad" (about 2 min). Writes urdu01_ayan_shahad.json next to this file.

Cast (same rigs, Urdu names): Hira Ammi (molly), Junnat (lily, sister), Saim (ollie, brother), Ayan Bhalu (bobo, brother).
Lesson: sharing (mil baant kar khana). Spoken lines are Urdu script for the Edge Urdu voices; on-screen cards stay in
Roman Urdu because the card font has no Urdu shaping.
"""
import json
from pathlib import Path

ASK = 2.0
L = []


def say(who, text, **k):
    L.append({"who": who, "text": text, **k})


def ask(who, text, **k):
    k.setdefault("gap_after", ASK)
    say(who, text, your_turn=True, **k)


M, J, S, A = "molly", "lily", "ollie", "bobo"
KIDS = [J, S]
ALL = [M, J, S, A]
ALSO = lambda a: {J: a, S: a, A: a}  # noqa: E731

# 1 ------------------------------------------------------------ hook + hello (home)
say(A, "واہ! شہد کا مرتبان! یہ سارا شہد میرا ہے!", act="hands_up", cam="cu:bobo", place="home", pic="honey",
    sfx="pop", face="happy", chapter="Ayan aur shahad")
say(M, "السلام علیکم بچو! میں ہوں آپ کی ہیرا امی۔ آج ہم ایک پیاری سی کہانی سنیں گے!", act="wave", cam="host",
    goal=True, title="Ayan Bhalu\naur Shahad")
say(J, "السلام علیکم! میں جنت ہوں!", act="wave", cam="kids", face="happy")
say(S, "اور میں صائم ہوں!", act="wave", cam="kids", face="happy")
say(A, "اور میں ایان بھالو! مجھے شہد بہت پسند ہے!", act="cheer", cam="cu:bobo", face="happy", sfx="boing")

# 2 ------------------------------------------------------------ to the orchard
say(M, "آج ہم باغ سے میٹھے میٹھے سیب توڑیں گے۔ چلو، باغ میں چلتے ہیں!", act="point", cam="host", pic="apple",
    card="Seb")
say(ALL, "چلو باغ میں!", act="run", also=ALSO("run"), cam="group", place="orchard", sfx="whoosh",
    chapter="Baagh mein", gap_after=0.5)
ask(M, "دیکھو، چار سیب! آؤ مل کر گنیں!", act="count", cam="host", pic="apple", card="4", gap_after=0.8)
say(ALL, "ایک، دو، تین، چار! سیب ہیں مزیدار!", chant=True, act="clap", also=ALSO("clap"), cam="group", gap_after=0.5)

# 3 ------------------------------------------------------------ the problem
say(S, "یہ سارے سیب میرے ہیں! میں سب کھاؤں گا!", act="hands_up", cam="kids", pic="apple")
say(A, "اور یہ سارا شہد میرا! کسی کو نہیں دوں گا!", act="stomp", cam="cu:bobo", pic="honey", sfx="boing")
say(J, "لیکن مجھے بھی تو بھوک لگی ہے...", act="talk", cam="kids", face="sad", gap_after=0.8)
say(M, "رکو رکو بچو! اگر ایک ہی سب کچھ کھا لے، تو باقی دوست اداس ہو جائیں گے۔", act="open", cam="host",
    face="think", chapter="Mil baant kar")
ask(M, "بچو، آپ بتاؤ، کیا ہمیں مل بانٹ کر کھانا چاہیے؟", act="point", cam="host")
say(M, "جی ہاں! شاباش!", act="clap", cam="host", sfx="sparkle", face="happy")

# 4 ------------------------------------------------------------ sharing sum
ask(M, "چار سیب، اور ہم چار گھر والے۔ تو ہر ایک کو کتنے سیب ملیں گے؟", act="count", cam="host", card="4")
say(J, "ایک ایک سیب!", act="cheer", cam="kids", card="1", face="happy", sfx="chime")
say(M, "بالکل ٹھیک! ایک سیب جنت کا، ایک صائم کا، ایک ایان کا، اور ایک امی کا!", act="count", cam="group",
    pic="apple")
say(S, "اوہ... مل کر کھانے میں تو اور بھی مزہ ہے!", act="talk", cam="kids", face="think")
say(A, "اور میں سب کو تھوڑا تھوڑا شہد دوں گا! سیب اور شہد، واہ!", act="giggle", cam="cu:bobo", pic="honey",
    face="happy")
say(ALL, "واہ! سیب اور شہد!", act="yay", also=ALSO("yay"), cam="group", fx="hearts", sfx="success")
say(ALL, "مل کر کھاؤ، مل کر کھاؤ، خوشیاں سب میں بانٹو!", chant=True, act="dance", also=ALSO("dance"),
    cam="group", fx="confetti", chapter="Gaana", gap_after=0.5)

# 5 ------------------------------------------------------------ lesson + goodbye
say(M, "بچو، آج ہم نے سیکھا کہ جب ہم چیزیں بانٹتے ہیں، تو سب خوش ہوتے ہیں۔", act="open", cam="host", calm=True,
    card="Share", chapter="Sabaq")
ask(M, "آپ بھی آج اپنے بہن بھائیوں کے ساتھ کچھ بانٹنا، ٹھیک ہے؟", act="point", cam="host", gap_after=1.4)
say(KIDS, "ٹھیک ہے امی!", act="thumbs_up", also={A: "thumbs_up"}, cam="kids", face="happy")
say(ALL, "اللہ حافظ بچو! پھر ملیں گے!", act="wave", also=ALSO("wave"), cam="group",
    endcard="Allah Hafiz!\nPhir milenge!", sfx="success")

script = {
    "voices": {
        M: {"voice": "ur-PK-UzmaNeural", "rate": "-6%", "pitch": "+0Hz"},
        J: {"voice": "ur-PK-UzmaNeural", "rate": "+4%", "pitch": "+38Hz"},
        S: {"voice": "ur-PK-AsadNeural", "rate": "+8%", "pitch": "+48Hz"},
        A: {"voice": "ur-PK-AsadNeural", "rate": "-6%", "pitch": "+10Hz"},
    },
    "bpm": 104, "lead_in": 0.6, "gap": 0.45, "tail": 6.0, "lines": L,
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1, ensure_ascii=False))
print(len(L), "lines ->", out)
