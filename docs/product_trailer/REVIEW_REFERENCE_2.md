# Review reference 2: two more styles (measured 2026-10-28)

## A. "Samsung Galaxy S27 Ultra - How's This Possible?" (4:26, 1280x640, 30 fps)
Style: **flat infographic explainer**, voice-over only, no presenter.
- Light paper-white background with faint grain; phones are flat 2D cut-outs (back or front), never 3D-orbited.
- One idea per 3-4 s: a giant number (%30, 60W, $1315, $80B) beside the phone, then the number/bar animates.
- Side-by-side comparison is the main device (S26 vs S27, S27 vs iPhone 18 Pro Max, four-phone row with watt labels).
- Charts: battery capsules filling, red/green line charts, bar gauges, building icons (Samsung semiconductor vs mobile).
- Evidence cards: screenshot of a tweet with a highlighted sentence.
- Rare real footage (box unboxing from above, hands on a board, hands holding a phone): 4 of ~55 shots.
- Cuts: 23 hard cuts, median 3.3 s, but 7 shots over 8 s (a graphic that keeps animating inside one shot).
- Sound: -17.2 LUFS, LRA 2.5 LU (flat, voice + quiet bed). No big music dynamics.

## B. "iPhone 18 Pro Review: I Have Mixed Feelings" (20:15, 1280x720, 29.97 fps)
Style: **presenter review with a 3D/diorama graphics layer**.
- Presenter shots (about a third) in different sets; we skip these (no host).
- The rest is the part our tool can own: miniature-diorama product scenes (desk, pegboard, cutting mat, warm wood), lineup of two phones with a big UI/feature on each screen, speed-test gauges (Uploads 30.12 vs 127.51 Mbps), benchmark chart on a monitor, heat-camera shots (orange thermal on the phones), battery icons on a desk, chip render with QLC (4bit) chips, cost-breakdown stack beside a phone.
- Section changes are marked by a clean title card or a set change; cuts are clustered: 33 cuts in one 2-minute block (a montage of specs), long calm talk elsewhere.
- Cuts: 72 hard cuts in 20 min, median 2.0 s, 13 shots over 8 s (talking head).
- Sound: -16.7 LUFS, LRA 5.8 LU (more dynamics: music swells in montages, drops under talk).

## What the tool already covers vs what is missing
| Need | Status |
|---|---|
| Voice-over, chapters, subtitles, bars/curve/compare/stat/chip/xray/fold/lineup | have |
| **Flat Infographic look** (light paper bg, flat phone cut-outs, giant number beside phone) | missing |
| Battery capsule fill, speed gauge, thermal (heat) view, tweet/evidence card | missing |
| Two-phone compare with a label per phone and a big number each | partly (compare3) |
| Diorama desk scene with a lineup | partly (rooms) |
| Montage mode (many 1.5-2 s shots then a long calm one) | missing; planner has one pace per film |
| Loudness target (-17 LUFS, ducked bed) | voiceover mix is close; not checked |

## Proposed style presets for Review (pick per film)
1. **Infographic** (reference A): light bg, flat phones, 3-4 s beats, numbers and capsules, no 3D camera moves. Cheapest to render and the easiest to make smooth.
2. **Diorama review** (reference B): 3D rooms + lineup + gauges + chip/heat shots, montage and calm sections.
3. **Cinematic** (what exists now): dark 3D product shots.

## Next build order (smallest first, nothing built yet)
1. `pt_capsule`, `pt_gauge`, `pt_tweet` layers and a light "paper" backdrop for the Infographic preset.
2. Style switch in the Review box (Infographic | Diorama | Cinematic) mapped to the directive defaults.
3. Pace profiles: `montage` (1.5-2 s) and `calm` (4-8 s) per chapter.
4. Post-render quality check: motion per frame, longest still stretch, loudness within -17 +/- 1 LUFS.
