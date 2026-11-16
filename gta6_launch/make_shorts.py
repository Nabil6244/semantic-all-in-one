"""Cut 4 vertical Shorts from the full Leonida video, by narration line."""
import subprocess
from PIL import Image
import build_full as b
from build_test20 import shadow_text, font, F_HEAD, PINK, TEAL

b.make_voice()
shots, vo, total = b.timeline()
starts = [at - 0.15 for _, at in vo]
ends = [starts[i + 1] for i in range(len(starts) - 1)] + [total]
SRC = b.OUT / "gta6_leonida_vs_florida_full.mp4"
SHORTS = {
    "short1_vice_city_vs_miami": (["VICE CITY", "IS REAL MIAMI"], [range(4, 11)]),
    "short2_gta6_swamp_is_real": (["THE GTA 6 SWAMP", "IS REAL"], [range(15, 19)]),
    "short3_florida_man_is_real": (["GTA 6 FLORIDA MAN", "IS REAL"], [range(28, 31)]),
    "short4_5_real_places": (["5 REAL PLACES", "IN GTA 6"], [[5], [12], [17], [20], [23]]),
}
for name, (title, groups) in SHORTS.items():
    segs = [(starts[g[0]], ends[g[-1]]) for g in map(list, groups)]
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    shadow_text(img, (540, 330), title[0], font(F_HEAD, 140 if len(title[0]) < 12 else 110))
    shadow_text(img, (540, 470), title[1], font(F_HEAD, 120), fill=PINK)
    shadow_text(img, (540, 1560), "GTA 6 · NOV 19", font(F_HEAD, 90), fill=TEAL)
    ov = b.WORK / f"{name}.png"; img.save(ov)
    parts, cat = [], ""
    for k, (s, e) in enumerate(segs):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{k}];[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{k}]")
        cat += f"[v{k}][a{k}]"
    L = sum(e - s for s, e in segs)
    fc = ";".join(parts) + f";{cat}concat=n={len(segs)}:v=1:a=1[cv][ca];" \
        "[cv]split[x][y];[x]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:2,eq=brightness=-0.15[bg];" \
        "[y]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2[v1];" \
        f"[v1][1:v]overlay=0:0,fade=out:st={L-0.6:.2f}:d=0.6[v];[ca]afade=out:st={L-0.8:.2f}:d=0.8[a]"
    out = b.OUT / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(SRC), "-i", str(ov), "-filter_complex", fc,
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "19",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)], check=True)
    print(out.name, round(L, 1))
