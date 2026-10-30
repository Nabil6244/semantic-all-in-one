"""The pose library (docs/rep_theory/UPGRADE_LIST.md Step 5): one character in ~30 poses, generated once through Flow (reptheory/art.py) and reused by every video.
A pose is chosen by the ACTION the sentence names (an exercise, or doing something: eating, sleeping, running, weighing yourself), never by the topic, and only when its
picture is in the library. Each pose has a body-region map (ellipses cx, cy, w, h as fractions of the picture) so a part the narration names lights up in the right place;
a part a pose has no map for is simply not lit on it."""
from __future__ import annotations
import re
from typing import Callable, Dict, List, Optional

# pose id -> (words that call for it, a short label). Earlier in the sentence wins; on a tie, the first listed.
POSES: Dict[str, tuple] = {
    "rep_pushup_bottom_v1": (r"(?:bottom|lower(?:ing)?|chest (?:to|near) the floor)\b[^.!?]{0,30}\b(?:push|press)[- ]?ups?|(?:push|press)[- ]?ups?\b[^.!?]{0,30}\b(?:bottom|lower(?:ing)? (?:your|the) chest)", "PUSH-UP"),
    "rep_pushup_top_v1": (r"(?:push|press)[- ]?ups?", "PUSH-UP"),
    "rep_side_plank_v1": (r"side planks?", "SIDE PLANK"),
    "rep_plank_v1": (r"planks?|planking", "PLANK"),
    "rep_wall_sit_v1": (r"wall sits?", "WALL SIT"),
    "rep_squat_v1": (r"squats?|squatting", "SQUAT"),
    "rep_lunge_v1": (r"lunges?|lunging", "LUNGE"),
    "rep_bridge_v1": (r"(?:glute|hip) bridges?|bridges?", "BRIDGE"),
    "rep_pullup_top_v1": (r"(?:pull|chin)[- ]?ups?", "PULL-UP"),
    "rep_row_v1": (r"(?<!in a )\brows?\b(?! of)|rowing", "ROW"),
    "rep_hinge_v1": (r"deadlifts?|hip hinge|hinge|romanian", "HINGE"),
    "rep_press_v1": (r"overhead press|shoulder press|press(?:ing)? (?:it |them |the weight )?overhead", "PRESS"),
    "rep_curl_v1": (r"curls?|curling", "CURL"),
    "rep_calf_raise_v1": (r"calf raises?|on your toes", "CALF RAISE"),
    "rep_hamstring_stretch_v1": (r"touch your toes|hamstring stretch|forward fold|reach (?:for|toward) your toes", "STRETCH"),
    "rep_hip_stretch_v1": (r"hip flexor stretch|kneeling stretch|stretch(?:es|ing)? (?:your|the) hips?|couch stretch", "HIP STRETCH"),
    "rep_run_v1": (r"run(?:s|ning)?|jog(?:s|ging)?|sprint(?:s|ing)?|\d+k\b", "RUN"),
    "rep_walk_v1": (r"walk(?:s|ing)?|steps a day|step count", "WALK"),
    "rep_sleep_v1": (r"sleep(?:s|ing)?|asleep|bedtime|in bed|naps?|napping", "SLEEP"),
    "rep_eat_v1": (r"eat(?:s|ing)?|meals?|breakfast|lunch|dinner|snacks?|portions?", "EAT"),
    "rep_drink_v1": (r"drink(?:s|ing)?|sips?|hydrat\w*|water bottle", "DRINK"),
    "rep_scale_v1": (r"the scale|weigh(?:s|ing)? yourself|step on a scale", "SCALE"),
    "rep_tired_v1": (r"tired|exhausted|fatigue\w*|overtrain\w*|burn(?:ed|t)? out|out of breath|wiped out", "TIRED"),
    "rep_bench_rest_v1": (r"rest (?:between|for) (?:sets|\w+ (?:seconds|minutes))|between sets|rest days?", "REST"),
    "rep_flex_v1": (r"bigger arms|build(?:s|ing)? muscle|gain(?:s|ing)? muscle|muscle grows|get(?:ting)? stronger|look stronger", "STRONGER"),
    "rep_side_v1": (r"posture|stand(?:ing)? tall|from the side|side view", "POSTURE"),
}
POSE_RX = {k: re.compile(rf"\b(?:{v[0]})", re.I) for k, v in POSES.items()}
FRONT = {"rep_stand_v1", "rep_point_v1", "rep_think_v1", "rep_flex_v1", "rep_side_plank_v1", "rep_pullup_top_v1", "rep_press_v1", "rep_curl_v1", "rep_drink_v1", "rep_scale_v1"}

# part -> default ellipse size (w, h) as fractions of the 16:9 picture, for an upright body; parts named as in states.BODY
SIZE = {"brain": (.04, .07), "neck": (.025, .04), "shoulders": (.04, .07), "chest": (.06, .08), "heart": (.025, .045), "lungs": (.03, .07), "arms": (.025, .1), "forearms": (.025, .1),
        "hands": (.03, .05), "core": (.045, .09), "back": (.045, .1), "hips": (.06, .07), "legs": (.035, .14), "knees": (.03, .05), "calves": (.03, .1), "feet": (.04, .04)}
LYING = {"rep_pushup_bottom_v1", "rep_pushup_top_v1", "rep_plank_v1", "rep_side_plank_v1", "rep_bridge_v1", "rep_hamstring_stretch_v1", "rep_sleep_v1"}      # a horizontal body: limb ellipses lie down
_POINTS = {      # pose -> part -> centre points (x, y) read off each generated picture (fractions); one point per side that shows
    "rep_side_v1": {"brain": [(.50, .06)], "neck": [(.50, .16)], "shoulders": [(.49, .21)], "chest": [(.51, .26)], "back": [(.47, .28)], "arms": [(.49, .34)], "forearms": [(.49, .45)], "hands": [(.49, .55)], "core": [(.50, .37)], "hips": [(.50, .50)], "legs": [(.50, .62)], "knees": [(.50, .72)], "calves": [(.50, .82)], "feet": [(.51, .95)]},
    "rep_flex_v1": {"brain": [(.50, .07)], "neck": [(.50, .15)], "shoulders": [(.43, .22), (.57, .22)], "arms": [(.40, .20), (.60, .20)], "forearms": [(.41, .12), (.59, .12)], "hands": [(.42, .07), (.58, .07)], "chest": [(.50, .30)], "core": [(.50, .41)], "hips": [(.50, .51)], "legs": [(.47, .65), (.53, .65)], "knees": [(.46, .76), (.54, .76)], "calves": [(.46, .86), (.54, .86)], "feet": [(.45, .95), (.55, .95)]},
    "rep_tired_v1": {"brain": [(.60, .10)], "neck": [(.57, .17)], "shoulders": [(.55, .22)], "back": [(.45, .22)], "chest": [(.53, .28)], "arms": [(.53, .42)], "hands": [(.48, .58)], "core": [(.45, .34)], "hips": [(.40, .40)], "legs": [(.44, .55)], "knees": [(.47, .66)], "calves": [(.45, .80)], "feet": [(.48, .93)]},
    "rep_pushup_top_v1": {"brain": [(.83, .18)], "neck": [(.79, .30)], "shoulders": [(.71, .38)], "back": [(.62, .38)], "chest": [(.68, .47)], "arms": [(.72, .52)], "forearms": [(.72, .70)], "hands": [(.73, .86)], "core": [(.60, .48)], "hips": [(.50, .52)], "legs": [(.36, .62)], "knees": [(.27, .66)], "calves": [(.19, .70)], "feet": [(.10, .76)]},
    "rep_pushup_bottom_v1": {"brain": [(.10, .43)], "neck": [(.16, .50)], "shoulders": [(.28, .48)], "back": [(.33, .45)], "chest": [(.27, .56)], "arms": [(.33, .54)], "forearms": [(.30, .65)], "hands": [(.30, .70)], "core": [(.40, .55)], "hips": [(.47, .52)], "legs": [(.58, .52)], "knees": [(.70, .53)], "calves": [(.80, .52)], "feet": [(.92, .60)]},
    "rep_squat_v1": {"brain": [(.53, .11)], "neck": [(.51, .20)], "shoulders": [(.42, .30)], "back": [(.37, .38)], "chest": [(.45, .37)], "arms": [(.60, .31)], "forearms": [(.70, .31)], "hands": [(.78, .30)], "core": [(.42, .46)], "hips": [(.36, .58)], "legs": [(.47, .57)], "knees": [(.55, .58)], "calves": [(.52, .75)], "feet": [(.50, .91)]},
    "rep_lunge_v1": {"brain": [(.60, .10)], "neck": [(.58, .18)], "shoulders": [(.53, .28)], "chest": [(.56, .33)], "back": [(.50, .33)], "arms": [(.43, .38), (.64, .33)], "core": [(.52, .43)], "hips": [(.47, .56)], "legs": [(.56, .60), (.35, .78)], "knees": [(.62, .62), (.24, .86)], "calves": [(.62, .80)], "feet": [(.66, .93), (.14, .93)]},
    "rep_plank_v1": {"brain": [(.84, .22)], "neck": [(.79, .33)], "shoulders": [(.73, .42)], "back": [(.64, .40)], "chest": [(.70, .50)], "arms": [(.75, .62)], "forearms": [(.82, .74)], "hands": [(.88, .72)], "core": [(.60, .53)], "hips": [(.52, .55)], "legs": [(.37, .62)], "knees": [(.29, .63)], "calves": [(.20, .66)], "feet": [(.10, .70)]},
    "rep_side_plank_v1": {"brain": [(.25, .22)], "neck": [(.29, .30)], "shoulders": [(.33, .33)], "chest": [(.37, .40)], "arms": [(.27, .55)], "forearms": [(.27, .66)], "hands": [(.27, .77)], "core": [(.42, .47)], "hips": [(.52, .55)], "legs": [(.64, .62)], "knees": [(.70, .67)], "calves": [(.78, .70)], "feet": [(.88, .77)]},
    "rep_bridge_v1": {"brain": [(.11, .64)], "neck": [(.18, .70)], "shoulders": [(.23, .73)], "chest": [(.30, .66)], "arms": [(.36, .80)], "hands": [(.60, .83)], "core": [(.40, .60)], "back": [(.35, .70)], "hips": [(.50, .50)], "legs": [(.62, .37)], "knees": [(.73, .28)], "calves": [(.77, .55)], "feet": [(.83, .80)]},
    "rep_wall_sit_v1": {"brain": [(.46, .11)], "neck": [(.45, .20)], "shoulders": [(.44, .29)], "back": [(.41, .40)], "chest": [(.46, .35)], "arms": [(.45, .42)], "hands": [(.52, .52)], "core": [(.45, .45)], "hips": [(.43, .57)], "legs": [(.51, .56)], "knees": [(.58, .57)], "calves": [(.57, .75)], "feet": [(.58, .89)]},
    "rep_pullup_top_v1": {"brain": [(.50, .07)], "neck": [(.50, .15)], "shoulders": [(.43, .25), (.57, .25)], "arms": [(.40, .29), (.60, .29)], "forearms": [(.40, .20), (.60, .20)], "hands": [(.40, .12), (.60, .12)], "chest": [(.50, .30)], "back": [(.45, .38), (.55, .38)], "core": [(.50, .41)], "hips": [(.50, .51)], "legs": [(.46, .65), (.54, .65)], "knees": [(.46, .73), (.54, .73)], "calves": [(.46, .83), (.54, .83)], "feet": [(.47, .95), (.53, .95)]},
    "rep_row_v1": {"brain": [(.63, .09)], "neck": [(.59, .15)], "shoulders": [(.55, .20)], "back": [(.48, .25)], "chest": [(.53, .29)], "arms": [(.50, .30)], "forearms": [(.50, .38)], "hands": [(.50, .43)], "core": [(.48, .35)], "hips": [(.42, .34)], "legs": [(.42, .50)], "knees": [(.43, .62)], "calves": [(.42, .76)], "feet": [(.43, .93)]},
    "rep_hinge_v1": {"brain": [(.60, .09)], "neck": [(.57, .16)], "shoulders": [(.52, .24)], "back": [(.46, .27)], "chest": [(.52, .32)], "arms": [(.53, .42)], "forearms": [(.54, .53)], "hands": [(.54, .60)], "core": [(.45, .38)], "hips": [(.40, .38)], "legs": [(.44, .58)], "knees": [(.47, .70)], "calves": [(.48, .82)], "feet": [(.50, .95)]},
    "rep_press_v1": {"brain": [(.50, .14)], "neck": [(.50, .22)], "shoulders": [(.44, .28), (.57, .28)], "arms": [(.43, .19), (.58, .19)], "forearms": [(.43, .10), (.59, .10)], "hands": [(.43, .04), (.59, .04)], "chest": [(.50, .33)], "core": [(.50, .42)], "hips": [(.50, .51)], "legs": [(.47, .66), (.54, .66)], "knees": [(.47, .75), (.54, .75)], "calves": [(.47, .85), (.55, .85)], "feet": [(.46, .96), (.56, .96)]},
    "rep_curl_v1": {"brain": [(.50, .07)], "neck": [(.50, .14)], "shoulders": [(.45, .20), (.55, .20)], "arms": [(.43, .30), (.57, .30)], "forearms": [(.41, .27), (.59, .27)], "hands": [(.39, .23), (.61, .23)], "chest": [(.50, .27)], "core": [(.50, .38)], "hips": [(.50, .49)], "legs": [(.47, .62), (.53, .62)], "knees": [(.46, .72), (.54, .72)], "calves": [(.46, .83), (.54, .83)], "feet": [(.46, .95), (.55, .95)]},
    "rep_calf_raise_v1": {"brain": [(.51, .06)], "neck": [(.50, .14)], "shoulders": [(.50, .20)], "chest": [(.52, .25)], "back": [(.48, .27)], "arms": [(.49, .35)], "core": [(.50, .37)], "hips": [(.50, .49)], "legs": [(.50, .60)], "knees": [(.50, .70)], "calves": [(.49, .80)], "feet": [(.50, .95)]},
    "rep_hamstring_stretch_v1": {"brain": [(.50, .40)], "neck": [(.46, .48)], "shoulders": [(.44, .55)], "back": [(.33, .50)], "arms": [(.60, .58)], "hands": [(.78, .66)], "core": [(.32, .62)], "hips": [(.30, .75)], "legs": [(.55, .78)], "knees": [(.62, .79)], "calves": [(.70, .79)], "feet": [(.78, .74)]},
    "rep_hip_stretch_v1": {"brain": [(.50, .13)], "neck": [(.51, .25)], "shoulders": [(.50, .32)], "chest": [(.53, .36)], "back": [(.47, .42)], "arms": [(.56, .48)], "hands": [(.63, .57)], "core": [(.50, .48)], "hips": [(.48, .60)], "legs": [(.40, .80), (.58, .62)], "knees": [(.66, .62), (.22, .90)], "calves": [(.28, .89), (.66, .80)], "feet": [(.72, .93), (.12, .91)]},
    "rep_run_v1": {"brain": [(.55, .13)], "neck": [(.53, .21)], "shoulders": [(.50, .27)], "chest": [(.52, .31)], "arms": [(.40, .35), (.63, .30)], "core": [(.50, .41)], "hips": [(.50, .50)], "legs": [(.45, .60), (.57, .62)], "knees": [(.38, .68), (.60, .72)], "calves": [(.30, .73), (.61, .85)], "feet": [(.22, .79), (.68, .95)]},
    "rep_walk_v1": {"brain": [(.50, .09)], "neck": [(.50, .17)], "shoulders": [(.50, .22)], "chest": [(.51, .28)], "arms": [(.44, .40), (.58, .40)], "core": [(.50, .37)], "hips": [(.50, .48)], "legs": [(.48, .60)], "knees": [(.46, .71), (.56, .72)], "calves": [(.42, .82), (.60, .82)], "feet": [(.40, .95), (.62, .95)]},
    "rep_eat_v1": {"brain": [(.50, .10)], "neck": [(.51, .18)], "shoulders": [(.48, .22)], "back": [(.44, .28)], "chest": [(.51, .28)], "arms": [(.53, .33)], "hands": [(.57, .27)], "core": [(.49, .40)], "hips": [(.47, .52)], "legs": [(.51, .55)], "knees": [(.55, .60)], "calves": [(.53, .76)], "feet": [(.56, .91)]},
    "rep_drink_v1": {"brain": [(.50, .09)], "neck": [(.50, .17)], "shoulders": [(.45, .23), (.56, .23)], "arms": [(.43, .27), (.57, .36)], "hands": [(.45, .17), (.58, .55)], "chest": [(.50, .28)], "core": [(.50, .39)], "hips": [(.50, .48)], "legs": [(.47, .62), (.53, .62)], "knees": [(.47, .71), (.53, .71)], "calves": [(.47, .82), (.54, .82)], "feet": [(.47, .93), (.54, .93)]},
    "rep_scale_v1": {"brain": [(.50, .08)], "neck": [(.50, .15)], "shoulders": [(.45, .20), (.55, .20)], "chest": [(.50, .25)], "arms": [(.43, .32), (.57, .32)], "core": [(.50, .37)], "hips": [(.50, .46)], "legs": [(.47, .58), (.53, .58)], "knees": [(.47, .68), (.53, .68)], "calves": [(.47, .80), (.53, .80)], "feet": [(.47, .93), (.53, .93)]},
    "rep_bench_rest_v1": {"brain": [(.55, .09)], "neck": [(.53, .17)], "shoulders": [(.50, .22)], "back": [(.45, .30)], "chest": [(.55, .28)], "arms": [(.52, .38)], "core": [(.50, .42)], "hips": [(.50, .50)], "legs": [(.57, .52)], "knees": [(.60, .56)], "calves": [(.60, .75)], "feet": [(.62, .90)]},
    "rep_sleep_v1": {"brain": [(.20, .28)], "neck": [(.25, .36)], "shoulders": [(.32, .32)], "back": [(.38, .30)], "core": [(.43, .38)], "hips": [(.52, .40)], "legs": [(.65, .45)], "feet": [(.85, .55)]},
}

def _ellipses(pose: str, part: str, pts) -> tuple:
    w, h = SIZE.get(part, (.04, .07))
    if pose in LYING and part not in ("brain", "neck", "hands", "feet", "knees", "heart"): w, h = h * 9 / 16, w * 16 / 9      # same shape on screen, turned on its side
    return tuple((x, y, w, h) for x, y in pts)

REGIONS: Dict[str, Dict[str, tuple]] = {pose: {part: _ellipses(pose, part, pts) for part, pts in parts.items()} for pose, parts in _POINTS.items()}      # pose -> part -> ellipses (cx, cy, w, h)

def pick(text: str, art_ok: Callable[[str], bool]) -> Optional[tuple]:
    """(pose id, char position of the words that call for it) for the earliest action in the text whose picture is in the library, else None."""
    best = None
    for pid, rx in POSE_RX.items():
        m = rx.search(text)
        if m and art_ok(pid) and (best is None or m.start() < best[1]): best = (pid, m.start())
    return best

def regions(pose: str, part: str) -> Optional[tuple]:
    return REGIONS.get(pose, {}).get(part)
