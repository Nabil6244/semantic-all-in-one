"""DEMO ONLY: before | after side by side with a note per moment. Usage: wall_compare.py <before.mp4> <after.mp4> <out.mp4>"""
import subprocess, sys
from PIL import Image, ImageDraw, ImageFont

BEF, AFT, OUT = sys.argv[1:4]
W, H, FPS, DUR = 1280, 720, 25, 41.0
FD = "/Users/muhammadnabil/Downloads/video_generator-main/assets/fonts/"
fb, fr = (lambda s: ImageFont.truetype(FD + "Outfit-ExtraBold.ttf", s)), (lambda s: ImageFont.truetype(FD + "Inter-Regular.ttf", s))
NOTES = [
    (0, 6.2, "SCENE 1 FOOTAGE - FULL SCREEN (kept)", ["NOW: the clip full screen", "AFTER: the same clip full screen, plus the date types on a yellow block",
                                                    "AFTER: handwritten 'Portugal's cabinet decides' lands on 'cabinet'"]),
    (6.2, 10.7, "FOOTAGE BECOMES A PRINT ON THE WALL", ["NOW: hard cut to a flat bar-chart card",
                                                       "AFTER: camera pulls back, the still-playing clip becomes a pinned print",
                                                       "AFTER: 'WINNER: LUFTHANSA' on 'Lufthansa'; string to €1.025 BN, which lands on 'billion'"]),
    (10.7, 20.3, "NUMBERS ON THE WALL", ["NOW: chart card, then a news-screen picture",
                                         "AFTER: 44.9% counts up, pen circle on 'of TAP', underline on 'climbs'",
                                         "AFTER: handwritten '≈ €1.2 BN' note on 'billion'"]),
    (20.3, 22.2, "STRANGE PART - FOOTAGE FULL SCREEN (kept)", ["NOW: the TAP-at-dusk clip full screen",
                                                              "AFTER: camera dives from the wall into the clip, same clip full screen",
                                                              "AFTER: 'HERE IS THE STRANGE PART' slams on with a deep boom"]),
    (22.2, 29.6, "THE LOSS ON THE WALL", ["NOW: flat red '€99.2 M' card",
                                          "AFTER: pull back, the clip keeps playing in its print beside the numbers",
                                          "AFTER: −€99.2 M lands on 'million'; '+40% WORSE' stamp slams on '40'"]),
    (29.6, 35.2, "RUNWAY FOOTAGE - FULL SCREEN (kept)", ["NOW: the aerial clip full screen",
                                                        "AFTER: same clip full screen; pen ring on the runway on 'single', push-in",
                                                        "AFTER: second ring + 'homes all around it' on 'neighbourhoods'"]),
    (35.2, 37.7, "THE BUYER - FOOTAGE FULL SCREEN (kept)", ["NOW: the two-planes picture full screen",
                                                           "AFTER: same picture full screen, 'NO MAJORITY' stamp + shake on 'majority'",
                                                           "AFTER: 'THE BUYER' name bar on 'buyer'"]),
    (37.7, 41.0, "PULL-BACK: EVERY CLIP AND NUMBER ON ONE WALL", ["NOW: next scene",
                                                                 "AFTER: camera pulls back, all clips still playing in their prints",
                                                                 "AFTER: 'BEAT AIR FRANCE-KLM' on 'beat'; string ties Lufthansa to the buyer"]),
]


def reader(p):
    pr = subprocess.Popen(["ffmpeg", "-v", "error", "-t", str(DUR), "-i", p, "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-"], stdout=subprocess.PIPE)
    while True:
        b = pr.stdout.read(W * H * 3)
        if len(b) < W * H * 3: return
        yield Image.frombytes("RGB", (W, H), b)


enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", str(FPS), "-i", "-",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", OUT], stdin=subprocess.PIPE)
for i, (b, a) in enumerate(zip(reader(BEF), reader(AFT))):
    t = i / FPS
    cv = Image.new("RGB", (1920, 1080), (14, 18, 24)); d = ImageDraw.Draw(cv)
    cv.paste(b.resize((944, 531)), (16, 96)); cv.paste(a.resize((944, 531)), (960, 96))
    d.text((16, 30), "NOW  (Lisbon TAP v7, in the app today)", font=fb(34), fill=(200, 206, 212))
    d.text((960, 30), "AFTER  (full-screen footage + the wall)", font=fb(34), fill=(255, 150, 40))
    nt = next((n for n in NOTES if n[0] <= t < n[1]), NOTES[-1])
    d.rounded_rectangle((16, 650, 1904, 1010), radius=18, fill=(24, 32, 42))
    d.text((44, 668), nt[2], font=fb(42), fill=(255, 255, 255))
    for j, ln in enumerate(nt[3]):
        d.text((44, 748 + j * 76), ln, font=fr(34), fill=(170, 178, 186) if ln.startswith("NOW") else (255, 196, 120))
    d.text((16, 1030), f"0:{t:05.2f}", font=fr(30), fill=(150, 160, 170))
    d.rectangle((960, 1046, 1904, 1054), fill=(40, 50, 60)); d.rectangle((960, 1046, 960 + int(944 * t / DUR), 1054), fill=(255, 150, 40))
    enc.stdin.write(cv.tobytes())
enc.stdin.close(); enc.wait(); print("ok")
