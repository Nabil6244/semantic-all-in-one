"""Word timing of a voice-over: faster-whisper (local) -> [{word,start,end}], the shape lib/narration.mjs alignTiming() reads.
    python3 tools/narration_timing.py out/vo.wav out/words.json [model=base]"""
import json, sys


def transcribe(src, dst, model_name='base'):
    """Words with times for a voice-over file; writes dst (json) and returns the number of words."""
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device='cpu', compute_type='int8')
    segs, info = model.transcribe(src, word_timestamps=True, language='en', vad_filter=False, beam_size=5)
    words = [{'word': w.word.strip(), 'start': round(w.start, 3), 'end': round(w.end, 3)} for s in segs for w in (s.words or [])]
    json.dump({'duration': round(info.duration, 3), 'words': words}, open(dst, 'w'))
    return len(words)


def main():
    n = transcribe(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'base')
    print(f'{n} words -> {sys.argv[2]}')


if __name__ == '__main__':
    main()
