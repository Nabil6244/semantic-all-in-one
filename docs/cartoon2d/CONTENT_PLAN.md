# Kids 2D cartoon channel — content research and plan

Researched 2026-11-15. Cast names chosen 2026-11-15: **Miss Molly** (host), **Lily** (girl), **Ollie** (boy). Other ideas kept in section 6.

## 1. What the research says

| Finding | What it means for us |
|---|---|
| The biggest kids channels in 2026 (BabyBillion, Cocomelon, BabyBus, Kids Diana) are all preschool/family, and Shorts drive a large share of preschool views. | The audience is huge; plan Shorts from day one, not only long videos. |
| Core topics on top toddler channels: **colours, numbers, ABC, shapes, animals**; then **vehicles, daily routines (brushing teeth, bedtime), feelings**. | Build the first season around the core five, then routines and feelings. |
| Single songs/episodes run **2–4 min**; **compilations** raise watch time and revenue (one kids channel: +19 % watch duration, +72 % RPM). | Make 2–4 min episodes, then join them into 20–60 min compilations. |
| Ms Rachel–style techniques: talking straight to the child, **pauses for the child to answer**, repetition, child-directed speech, gestures/signs, songs. No direct studies of her show; under-3s learn few new words from video alone. | Every episode uses ask → pause → answer → praise, repeats key words 3+ times, and shows each word as a big card. Don't claim the videos teach speech. |
| YouTube's **kids quality principles** (written with child-development experts) decide YouTube Kids inclusion, recommendations and Made-for-Kids ads. Low quality = heavily promotional (toys, brands, unboxing), negative behaviour, hard to follow or "deceptively educational". | Real learning goal per episode, clear story, kind behaviour, no brands/toys-as-ads. |
| **Inauthentic content** policy (renamed July 2025, clarified July 2026): mass-produced, near-identical, repetitive videos can't earn; AI tools themselves are allowed. Reviews look at the whole channel. Synthetic content needs disclosure where it applies. | Each episode needs an original script, new situation and new learning goal — never the same video with swapped words. Same cast and world are fine (that's a show). |
| Made-for-Kids RPM is **low** (no personalised ads): estimates range from ~$0.25 to ~$1.65 per 1,000 views. | Income comes from volume + long watch time (compilations) — keep production cost per episode near zero (our engine renders 2 min in minutes). |

## 2. Show format

- **Episode (2–4 min, 16:9):** cold open with a hook in the first 5 s (a surprise, a sound, a question) → one learning goal → 2–3 interactive games → a song or chant → goodbye that teases the next episode.
- **Compilation (20–60 min):** 8–15 episodes of one theme ("Colours and Shapes with …"), short bumpers between.
- **Shorts (15–45 s, 9:16):** one game from an episode (e.g. "What does the cow say?"), ends on the answer.
- **Rhythm per minute:** at least one question to the child, one pause (1.2–1.6 s), one card or picture, one big movement (jump, clap, wave).

## 3. Episode checklist (every script)

1. One clear learning goal, said in the first 15 s.
2. Ask → pause → answer → praise ("Yes! Red!").
3. Key word said 3+ times and shown as a card.
4. Kids characters model good behaviour (sharing, saying sorry, trying again); the cheeky brother is funny, never mean.
5. A movement break for the child (jump, clap, stretch).
6. Slow, clear voices; short sentences; no sarcasm.
7. No brands, logos, toy promotion or real-person likeness.
8. Different situation, place or props from the last episode in the series.

## 4. Season 1 (24 episodes)

| # | Series | Episodes |
|---|---|---|
| 1–4 | Colours | Red and blue; yellow and green; rainbow colours; colour hunt in the playroom |
| 5–8 | Counting | 1 to 5 with jumps; 1 to 10 with balloons; counting animals; counting down to blast-off |
| 9–12 | Animals | Farm animal sounds; animal moves (hop like a bunny); baby animals; animal homes |
| 13–15 | Shapes | Circle, square, triangle; shapes in the room; build a house from shapes |
| 16–18 | ABC | A, B, C words; letter sounds; ABC song |
| 19–21 | Routines | Brushing teeth; washing hands; bedtime |
| 22–24 | Feelings and kindness | Happy and sad; sharing; saying sorry |

Compilations after every 4–6 episodes; 2–3 Shorts cut from each episode.

## 5. What the engine needs for Season 1

- **New places:** park, farm, bathroom, bedroom, kitchen (one Flow background each, reused across episodes).
- **Prop cards:** fruits, vehicles, shapes, toothbrush, balloons, letters (Flow stickers, reused).
- **Songs:** sung or chanted lines over the kids_audio beds (`kids_audio/chant.py`; `sing.py` waiting for the user's ear test).
- **New acts:** brush teeth, wash hands, sleep, hop like a bunny, point to a card, sad/happy faces.
- **9:16 Shorts mode** for the renderer.
- **Character expressions:** a happy-closed-eyes and a sad face per character (Flow sheet using the same character as reference).

## 6. English names (placeholders, check YouTube for clashes before choosing)

| Role | Ideas |
|---|---|
| Host (red-haired woman) | Miss Molly, Miss Penny, Miss Poppy |
| Girl (ponytail, pink) | Lily, Ellie, Rosie |
| Boy (cheeky, freckles) | Ollie, Benny, Max |
| Channel / world | Rainbow Playroom, Sunny Playland, Molly's Playroom |

Pick names that are short, easy for a 2-year-old to say, and not used by a big kids channel.

## 7. Sources

- Tubefilter weekly top 50 (2026): https://www.tubefilter.com/2026/03/17/top-50-most-viewed-youtube-channels-week-of-03-15-2026/
- AIR — most subscribed kids channels 2026: https://air.io/en/youtube-hacks/most-subscribed-youtube-kids-channels
- AIR — kids channel compilations case study: https://air.io/en/creators-spotlight/268-view-growth-for-a-million-subscriber-kids-channel-case-study
- AIR — big-screen kids viewing: https://air.io/en/youtube-hacks/kids-videos-are-booming-on-big-screens-how-to-adapt-to-the-living-room-experience
- YouTube — best practices for kids & family content: https://support.google.com/youtube/answer/10774223
- YouTube blog — high-quality kids experience: https://blog.youtube/inside-youtube/enabling-high-quality-youtube-kids-experience/
- TechCrunch — low-quality kids content demonetised: https://techcrunch.com/2021/10/25/youtube-warns-creators-it-will-start-to-demonetize-low-quality-kids-videos-next-month/
- Tubefilter — inauthentic content update (2026): https://www.tubefilter.com/2026/07/13/youtube-inauthentic-content-monetization-policy-update/
- Plagiarism Today — inauthentic content (2025): https://www.plagiarismtoday.com/2025/07/08/youtube-targets-inauthentic-content/
- Parenting Translator — can babies learn from Ms Rachel: https://parentingtranslator.substack.com/p/can-babies-learn-from-ms-rachel-and
- AIR — RPM by niche 2026: https://air.io/en/air-data-findings/which-youtube-niche-makes-the-most-money-in-2026-ranked-by-real-rpm-and-cpm
- vidIQ — making money with a kids channel: https://vidiq.com/blog/post/make-money-kids-youtube-channel/

Caveats: most numbers come from third-party trackers and vendor blogs (rough); YouTube's own policy pages should be re-read before launch.
