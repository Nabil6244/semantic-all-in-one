"""Punjabi story 1 - "Noraiz te Shahad" (about 2 min). Writes punjabi01_noraiz_shahad.json next to this file.

Cast (same rigs, Punjabi names): Mobeen Ammi (molly, mother), Hoorain (lily, girl), Noraiz (ollie, boy).
Lesson: sharing (ral mil ke khana). Lines are Punjabi in Shahmukhi; there is no free Edge Punjabi voice, so the
Pakistani Urdu voices read them. On-screen cards are Roman (the card font has no Urdu/Shahmukhi shaping).
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


M, H, N = "molly", "lily", "ollie"
KIDS = [H, N]
ALL = [M, H, N]
ALSO = lambda a: {H: a, N: a}  # noqa: E731

# 1 ------------------------------------------------------------ hook + hello (home)
say(N, "واہ! شہد دا مرتبان! ایہہ سارا شہد میرا اے!", act="hands_up", cam="cu:ollie", place="home", pic="honey",
    sfx="pop", face="happy", chapter="Noraiz te shahad")
say(M, "السلام علیکم بچیو! میں آں تہاڈی مبین امی۔ اج اسیں اک سوہنی جہی کہانی سناں گے!", act="wave", cam="host",
    goal=True, title="Noraiz te\nShahad")
say(H, "السلام علیکم! میں حورین آں!", act="wave", cam="kids", face="happy")
say(N, "تے میں نوریز آں! مینوں شہد بڑا چنگا لگدا اے!", act="cheer", cam="kids", face="happy", sfx="boing")

# 2 ------------------------------------------------------------ to the orchard
say(M, "اج اسیں باغ چوں مٹھے مٹھے سیب توڑاں گے۔ چلو، باغ چلدے آں!", act="point", cam="host", pic="apple", card="Seb")
say(ALL, "چلو، باغ چلدے آں!", act="run", also=ALSO("run"), cam="group", place="orchard", sfx="whoosh",
    chapter="Baagh vich", gap_after=0.5)
ask(M, "ویکھو، تن سیب! آؤ رل کے گنیے!", act="count", cam="host", pic="apple", card="3", gap_after=0.8)
say(ALL, "اک، دو تے تن! سیباں نال خوش اے من!", chant=True, act="clap", also=ALSO("clap"), cam="group",
    gap_after=0.5)

# 3 ------------------------------------------------------------ the problem
say(N, "ایہہ سارے سیب میرے نیں! میں سارے کھاواں گا!", act="hands_up", cam="kids", pic="apple")
say(N, "تے سارا شہد وی میرا! کسے نوں نئیں دیواں گا!", act="stomp", cam="cu:ollie", pic="honey", sfx="boing")
say(H, "پر مینوں وی تے بھکھ لگی اے...", act="talk", cam="kids", face="sad", gap_after=0.8)
say(M, "رُکو رُکو بچیو! جے اک ای سب کجھ کھا لوے، تے دوجا اداس ہو جاوے گا۔", act="open", cam="host",
    face="think", chapter="Ral mil ke")
ask(M, "بچیو، تسیں دسو، کی سانوں رل مل کے کھانا چاہیدا اے؟", act="point", cam="host")
say(M, "ہاں جی! شاباش!", act="clap", cam="host", sfx="sparkle", face="happy")

# 4 ------------------------------------------------------------ sharing sum
ask(M, "تن سیب، تے اسیں تن جنے۔ تے ہر اک نوں کنے سیب ملن گے؟", act="count", cam="host", card="3")
say(H, "اک اک سیب!", act="cheer", cam="kids", card="1", face="happy", sfx="chime")
say(M, "بالکل ٹھیک! اک سیب حورین دا، اک نوریز دا، تے اک امی دا!", act="count", cam="group", pic="apple")
say(N, "اوہو... رل کے کھان دا تے ہور وی مزہ اے!", act="talk", cam="kids", face="think")
say(N, "تے میں ساریاں نوں تھوڑا تھوڑا شہد وی دیواں گا! سیب تے شہد، واہ!", act="giggle", cam="cu:ollie",
    pic="honey", face="happy")
say(ALL, "واہ! سیب تے شہد!", act="yay", also=ALSO("yay"), cam="group", fx="hearts", sfx="success")
say(ALL, "رل کے کھاؤ، رل کے کھاؤ، خوشیاں سب نوں ونڈو!", chant=True, act="dance", also=ALSO("dance"),
    cam="group", fx="confetti", chapter="Gaana", gap_after=0.5)

# 5 ------------------------------------------------------------ lesson + goodbye
say(M, "بچیو، اج اسیں سکھیا کہ جدوں اسیں چیزاں ونڈنے آں، تے سارے خوش ہوندے نیں۔", act="open", cam="host",
    calm=True, card="Share", chapter="Sabaq")
ask(M, "تسیں وی اج اپنے بہن بھراواں نال کجھ ونڈنا، ٹھیک اے؟", act="point", cam="host", gap_after=1.4)
say(KIDS, "ٹھیک اے امی!", act="thumbs_up", cam="kids", face="happy")
say(ALL, "اللہ حافظ بچیو! فیر ملاں گے!", act="wave", also=ALSO("wave"), cam="group",
    endcard="Allah Hafiz!\nFer milange!", sfx="success")

script = {
    "voices": {
        M: {"voice": "ur-PK-UzmaNeural", "rate": "-6%", "pitch": "+0Hz"},
        H: {"voice": "ur-PK-UzmaNeural", "rate": "+4%", "pitch": "+38Hz"},
        N: {"voice": "ur-PK-AsadNeural", "rate": "+8%", "pitch": "+48Hz"},
    },
    "bpm": 104, "lead_in": 0.6, "gap": 0.45, "tail": 6.0, "lines": L,
}
out = Path(__file__).with_suffix(".json")
out.write_text(json.dumps(script, indent=1, ensure_ascii=False))
print(len(L), "lines ->", out)
