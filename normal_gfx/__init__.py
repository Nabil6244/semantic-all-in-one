"""Normal Video: the gfx-core template library (Hybrid Map's graphics) drawn over ordinary footage.

    runner     batch renderer client: template jobs -> transparent PNG sequences, cached by a deterministic key (gfx-overlay-engine/)
    allowlist  which templates may appear on ordinary footage, as data (allowlist.json)
    planner    narration -> template events (gfx_templates.auto_events), reservations, caption-safety
    composite  the transparent layer laid over the finished video (ffmpeg), without touching video_generator.py
"""
