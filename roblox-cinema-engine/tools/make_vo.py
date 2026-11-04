"""Stand-in test voice for the Roblox Cinema engine: macOS `say` reads the story's beats. This is a PLACEHOLDER voice used only to give
the render real word timing and a track to mix; the real production voice-over comes from the app's own voice step.
    python3 tools/make_vo.py samples/dday_1944.csv out/vo.wav [voice=Daniel] [rate=165]
Pauses: 0.9 s between beats, 1.8 s before a chapter's first beat.  Writes <out>.json with the exact text spoken."""
import csv, subprocess, sys, tempfile, json, os
from pathlib import Path


def narration(csv_path):
    rows = list(csv.DictReader(open(csv_path, newline='', encoding='utf-8')))
    out = []
    for r in rows:
        kind = (r.get('row') or '').strip().lower()
        if kind == 'chapter': out.append(('chapter', ''))
        elif kind == 'beat' and (r.get('text') or '').strip(): out.append(('beat', r['text'].strip()))
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else 'Daniel'
    rate = sys.argv[4] if len(sys.argv) > 4 else '165'
    parts, text = [], []
    pending_chapter = False
    for kind, t in narration(src):
        if kind == 'chapter': pending_chapter = True; continue
        text.append((('[[slnc 1800]] ' if pending_chapter else '[[slnc 900]] ') if text else '[[slnc 1200]] ') + t)
        pending_chapter = False
    with tempfile.TemporaryDirectory() as d:
        txt = Path(d) / 'vo.txt'; txt.write_text('\n'.join(x for x in text), encoding='utf-8')
        aiff = Path(d) / 'vo.aiff'
        subprocess.run(['say', '-v', voice, '-r', rate, '-f', str(txt), '-o', str(aiff)], check=True, timeout=1800)
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(aiff), '-ar', '48000', '-ac', '1', dst], check=True, timeout=1800)
    Path(dst + '.json').write_text(json.dumps({'voice': voice, 'rate': rate, 'placeholder': True, 'text': [t for _, t in narration(src) if t]}, indent=1))
    print(dst)


if __name__ == '__main__':
    main()
