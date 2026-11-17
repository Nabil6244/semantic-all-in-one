"""Public-domain nursery-rhyme tunes with slots for our own words, plus a matching accompaniment.

Every tune is written in C major, one beat = one crotchet, at the song grid's tempo. A tune is made of halves
("A", "B"); each half is two lines of 8 beats (two bars). A line is a list of (word, notes): a fixed word, or a slot
"{c}" (colour), "{C}" (Colour) or "{k}" (vehicle, may be two words like "monster truck"). notes = [[midi | None, beats]].
fill(line, c, k) turns a line into the text and one note list per sung word for kids_audio.sing.
accompaniment(name, halves, bpm) synthesises chords + bass + drums + a glockenspiel lead that doubles the melody.

The melodies are traditional (public domain); the words are ours.
"""
import re

import numpy as np

from . import synth as S
from .synth import SR, hz

G3, B3, C4, D4, E4, F4, G4, A4, C5 = 55, 59, 60, 62, 64, 65, 67, 69, 72

_WHEELS_1 = [("The", [[G3, .5]]), ("{c}", [[C4, 1], [C4, .5]]), ("{k}", [[C4, .5], [C4, 1]]), ("goes", [[E4, .5]]),
             ("round", [[G4, 1]]), ("and", [[E4, 1]]), ("round", [[C4, 2]])]
_MARY_1 = [("Here", [[E4, 1]]), ("comes", [[D4, 1]]), ("a", [[C4, 1]]), ("{c}", [[D4, 1]])]
_LONDON_1 = [("Roll", [[G4, .75]]), ("along", [[A4, .25], [G4, .5]]), ("the", [[F4, .5]]),
             ("{c}", [[E4, .5], [F4, .5]]), ("{k}", [[G4, 1]])]
_LONDON_2 = [("{c}", [[D4, .5], [E4, .5]]), ("{k}", [[F4, 1]]), ("{c}", [[E4, .5], [F4, .5]]), ("{k}", [[G4, 1]])]

TUNES = {
    "wheels": {  # The Wheels on the Bus
        "form": ["A", "B"], "ends": ["A", "B"],
        "A": {"chords": ["C", "C", "G", "C"], "lines": [
            _WHEELS_1,
            [("round", [[D4, 1]]), ("and", [[B3, 1]]), ("round", [[G3, 2]]),
             ("round", [[G4, 1]]), ("and", [[E4, 1]]), ("round", [[C4, 2]])]]},
        "B": {"chords": ["C", "C", "G", "C"], "lines": [
            _WHEELS_1,
            [("all", [[D4, 2]]), ("through", [[G3, 1]]), ("the", [[G3, 1]]), ("town", [[C4, 3], [None, 1]])]]},
    },
    "mary": {  # Mary Had a Little Lamb
        "form": ["A", "B"], "ends": ["B"],
        "A": {"chords": ["C", "C", "G", "C"], "lines": [
            _MARY_1 + [("{k}", [[E4, 1], [E4, 1], [E4, 2]])],
            [("{c}", [[D4, 1]]), ("{k}", [[D4, 1], [D4, 2]]), ("{c}", [[E4, 1]]), ("{k}", [[G4, 1], [G4, 2]])]]},
        "B": {"chords": ["C", "C", "G", "C"], "lines": [
            _MARY_1 + [("{k}", [[E4, 1], [E4, 1]]), ("beep", [[E4, 1]]), ("beep!", [[E4, 1]])],
            [("Say", [[D4, 1]]), ("it", [[D4, 1]]), ("with", [[E4, 1]]), ("me:", [[D4, 1]]), ("{C}!", [[C4, 3], [None, 1]])]]},
    },
    "twinkle": {  # Twinkle, Twinkle, Little Star (A B A)
        "form": ["A", "B", "A"], "ends": ["A"],
        "A": {"chords": ["C", "F/C", "F/C", "G/C"], "lines": [
            [("Shiny,", [[C4, 1], [C4, 1]]), ("shiny", [[G4, 1], [G4, 1]]), ("{c}", [[A4, 1], [A4, 1]]), ("{k}", [[G4, 2]])],
            [("Can", [[F4, 1]]), ("you", [[F4, 1]]), ("say", [[E4, 1]]), ("the", [[E4, 1]]), ("colour", [[D4, 1], [D4, 1]]),
             ("{c}?", [[C4, 2]])]]},
        "B": {"chords": ["C/G", "C/G", "C/G", "C/G"], "lines": [
            [("Look", [[G4, 1]]), ("at", [[G4, 1]]), ("the", [[F4, 1]]), ("{c}", [[F4, 1]]), ("{k}", [[E4, 1], [E4, 1], [D4, 2]])],
            [("Driving", [[G4, 1], [G4, 1]]), ("down", [[F4, 1]]), ("the", [[F4, 1]]), ("road", [[E4, 1]]), ("to", [[E4, 1]]),
             ("play!", [[D4, 2]])]]},
    },
    "london": {  # London Bridge Is Falling Down
        "form": ["A", "B"], "ends": ["A", "B"],
        "A": {"chords": ["C", "G/C", "C", "G/C"], "lines": [
            _LONDON_1 + _LONDON_2,
            _LONDON_1 + [("Beep", [[D4, 1]]), ("beep,", [[G4, 1]]), ("hooray!", [[E4, .5], [C4, 1.5]])]]},
        "B": {"chords": ["C", "G/C", "C", "G/C"], "lines": [
            [("Wave", [[G4, .75]]), ("hello", [[A4, .25], [G4, .5]]), ("to", [[F4, .5]]),
             ("{c}", [[E4, .5], [F4, .5]]), ("{k}", [[G4, 1]])] + _LONDON_2,
            _LONDON_1 + [("{C},", [[D4, 1]]), ("{c},", [[G4, 1]]), ("hooray!", [[E4, .5], [C4, 1.5]])]]},
    },
}

_SYL = {"yellow": 2, "orange": 2, "purple": 2, "monster": 2, "water": 2, "hooray": 2, "shiny": 2, "colour": 2,
        "driving": 2, "hello": 2, "along": 2}


def syllables(w):
    w = re.sub(r"[^a-z]", "", w.lower())
    return _SYL.get(w, 1)


def _fit(notes, s):
    """Fit a note list to a word of s syllables: merge same-pitch neighbours if too many, halve the longest if too few."""
    notes = [list(n) for n in notes]
    sung = [n for n in notes if n[0] is not None]
    while len(sung) > s:
        for i in range(len(notes) - 1):
            a, b = notes[i], notes[i + 1]
            if a[0] is not None and a[0] == b[0]:
                notes[i:i + 2] = [[a[0], a[1] + b[1]]]
                break
        else:
            break
        sung = [n for n in notes if n[0] is not None]
    while len(sung) < s:
        i = max((j for j, n in enumerate(notes) if n[0] is not None), key=lambda j: notes[j][1])
        m, b = notes[i]
        notes[i:i + 1] = [[m, b / 2], [m, b / 2]]
        sung = [n for n in notes if n[0] is not None]
    return notes


def _split(notes, k):
    """Share one slot's notes between k words (contiguous groups; a note is halved when there are too few)."""
    notes = [list(n) for n in notes]
    while len(notes) < k:
        i = max(range(len(notes)), key=lambda j: notes[j][1])
        m, b = notes[i]
        notes[i:i + 1] = [[m, b / 2], [m, b / 2]]
    per = len(notes) // k
    groups = [notes[i * per:(i + 1) * per] for i in range(k - 1)]
    return groups + [notes[(k - 1) * per:]]


def fill(line, colour, kind):
    """-> (text, words, tune): the sung line, its words, one note list per word."""
    words, tune = [], []
    for word, notes in line:
        m = re.match(r"^\{([cCk])\}(.*)$", word)
        if m:
            val = {"c": colour, "C": colour.capitalize(), "k": kind}[m.group(1)]
            parts = val.split()
            parts[-1] += m.group(2)
            for w, g in zip(parts, _split(notes, len(parts))):
                words.append(w)
                tune.append(_fit(g, syllables(w)))
        else:
            words.append(word)
            tune.append(_fit(notes, syllables(word)))
    for i in range(len(words) - 1):                               # "a orange" -> "an orange"
        if words[i].lower() == "a" and words[i + 1][:1].lower() in "aeiou":
            words[i] += "n"
    text = " ".join(words)
    return text[0].upper() + text[1:], words, tune


def line_beats(line):
    return sum(b for _, ns in line for _, b in ns)


def halves_for(name, n):
    """The half sung by each of n verses: the tune's form repeated; the last verse must be a half that ends on home."""
    t = TUNES[name]
    out = [t["form"][i % len(t["form"])] for i in range(n)]
    if n and out[-1] not in t["ends"]:
        out[-1] = t["ends"][0]
    return out


_CH = {"C": ["C4", "E4", "G4", "C5"], "G": ["B3", "D4", "G4", "B4"], "F": ["C4", "F4", "A4", "C5"], "Am": ["C4", "E4", "A4", "C5"]}
_ROOT = {"C": "C3", "G": "G2", "F": "F2", "Am": "A2"}


def _mhz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def accompaniment(name, halves, bpm, lead=True):
    """Song-long backing (stereo float array): uke strum, bass, soft drums, and a glockenspiel + marimba lead on the tune."""
    beat = 60.0 / bpm
    bars = 4 * len(halves)
    n = int((bars * 4 * beat + 2.0) * SR)
    buf = np.zeros((2, n))

    def add(x, at, gain=1.0, pan=0.0):
        S.place(buf, x * gain, at, pan=pan)

    for h, half in enumerate(halves):
        part = TUNES[name][half]
        for b, ch in enumerate(part["chords"]):
            t0 = (h * 4 + b) * 4 * beat
            chs = ch.split("/")
            for k, at in enumerate((0, 1.5, 2, 3)):                    # down on 1, 2&, 3, 4
                c = chs[0] if at < 2 or len(chs) == 1 else chs[1]
                for s, nt in enumerate(_CH[c]):
                    add(S.pluck(hz(nt), 0.22 if k else 0.3, dur=beat * 1.5, bright=0.6, seed=h * 31 + b * 7 + k),
                        t0 + at * beat + s * 0.012, pan=-0.35)
            for at in (0, 2):
                c = chs[0] if at < 2 or len(chs) == 1 else chs[1]
                add(S.bass(hz(_ROOT[c]), 0.5, dur=beat * 1.7), t0 + at * beat)
                add(S.kick(0.45), t0 + at * beat)
            for at in (1, 3):
                add(S.snap(0.22, seed=b), t0 + at * beat, pan=0.1)
            for k in range(8):
                add(S.shaker(0.1 if k % 2 else 0.06, seed=b * 8 + k), t0 + k * beat / 2, pan=0.45)
        if lead:
            t = h * 16 * beat
            for line in part["lines"]:
                for _, notes in line:
                    for m, b in notes:
                        if m is not None:
                            add(S.glock(_mhz(m + 12), 0.16, dur=max(0.5, b * beat * 1.2)), t, pan=0.3)
                            add(S.marimba(_mhz(m), 0.22, dur=max(0.5, b * beat * 1.3)), t, pan=0.2)
                        t += b * beat
    return buf
