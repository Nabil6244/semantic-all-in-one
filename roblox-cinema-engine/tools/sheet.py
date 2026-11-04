"""Contact sheet of still frames: python3 tools/sheet.py out/dday.mp4 t1,t2,... [cols]  -> out/dday.mp4.sheet.jpg"""
import sys
from PIL import Image, ImageDraw

base, ts = sys.argv[1], sys.argv[2].split(',')
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 3
ims = [(t, Image.open(f'{base}.t{t}.jpg')) for t in ts]
w, h = 640, 360
rows = (len(ims) + cols - 1) // cols
sheet = Image.new('RGB', (cols * w, rows * h), 'black')
for i, (t, im) in enumerate(ims):
    im = im.resize((w, h))
    ImageDraw.Draw(im).text((8, 6), f't={t}', fill='yellow')
    sheet.paste(im, ((i % cols) * w, (i // cols) * h))
sheet.save(f'{base}.sheet.jpg', quality=88)
print(f'{base}.sheet.jpg')
