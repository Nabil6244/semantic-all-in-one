"""AI Visual Director: full script → structured plan for AssetManager."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .llm import GeminiLLM, LLMError, LLMProvider
from .schema import MIN_SCENES, VisualPlan, VisualPlanError, parse_visual_plan

PlanProgressCallback = Callable[[str, Optional[float]], None]

# Planning estimate only — not an exact runtime and not a scene-count formula.
NARRATION_WPM_LOW = 130
NARRATION_WPM_HIGH = 160
NARRATION_WPM_ESTIMATE = 145
# Implied speech-seconds per visual beat above this is severe under-segmentation
# (documentary rhythm is ~2–5s; provider clips max out at 3–6s).
SEVERE_HOLD_SECONDS = 8.0
MIN_COVERAGE_RATIO = 0.55
CHUNK_SECTION_MAX_ATTEMPTS = 3


def max_implied_speech_per_scene(word_count: int) -> float:
    """How much average narration one scene may cover before we reject the plan.

    Short scripts keep the strict 8s documentary rhythm. Very long scripts cannot
    realistically emit 400+ JSON scenes in one Gemini call, so the cap relaxes
    slightly when scene count is already dense (see plan_segmentation_issue).
    """
    if word_count >= 4500:
        return 12.0
    if word_count >= 2500:
        return 10.5
    if word_count >= 1200:
        return 9.0
    return SEVERE_HOLD_SECONDS


def plan_max_attempts(word_count: int) -> int:
    """Gemini revision passes — long scripts often need an extra split attempt."""
    return 3 if word_count >= 2500 else 2

SYSTEM_PROMPT = """You are the Visual Director for a narrated documentary.

PRIMARY JOB: turn the COMPLETE narration into a COMPLETE visual timeline.
Walk the script sequentially from the first sentence to the last. Do not
summarize a long documentary into a short list of scenes. Do not stop because
you have produced "enough" scenes. Scene count is not a goal. Coverage and
visual storytelling are the goals.

There is NO target number of scenes. A 15-minute narration may need many
short beats; a 90-second piece may need only a handful. The count must emerge
from the narration's visual structure.

PROCESS FOR EVERY SECTION (repeat until the script is fully covered):
1. Read what is being said.
2. Identify the visual ideas in that section.
3. Note changes of subject, action, location, camera scale, or concept.
4. Split those into visual beats (not "one sentence = one scene" and not
   "one paragraph = one scene").
5. Assign each beat a short duration within the HARD caps below.
6. Choose the strongest media source for THAT beat.
7. Continue to the next uncovered words.

NARRATION → visual ideas → visual beats → short durations → media selection.

EXAMPLE — one sentence, two beats:
"Thousands of cars rush through the streets as bright lights reflect across
the wet roads."
  • Wide nighttime traffic (~3.5s stock_video)
  • Close-up wet asphalt with neon reflections (~2.5s stock_video or stock_image)
Same narration section; different visual information.

EXAMPLE — do not collapse this into one scene:
"Far beyond the crowded streets, a rocket prepares for launch beneath a dark
sky. Its engines ignite, filling the launchpad with fire, smoke, and powerful
vibrations. The rocket slowly rises into the night, leaving a glowing trail
behind."
Beats such as: rocket on pad; ignition; fire/smoke close-up; first motion;
ascent; glowing trail. Each is a short clip within provider caps.

RHYTHM (guideline, not a cut-every-N-seconds rule):
Aim for a meaningful visual change about every 2–5 seconds of the film.
Fast idea → shorter beat. Normal B-roll → 3–5s. Strong establishing shot →
up to that provider's HARD MAX. Conceptual transition → a short beat.
Do NOT invent empty cuts. Do NOT split "the man walks" into five identical
shots. Split when action, perspective, subject, location, concept, or a
useful metaphor/transition changes.

DO NOT PAD. Every scene must earn its place with a distinct visual purpose.
Vary scale and treatment across the film (establishing, close-up, detail,
aerial, human POV, environment, conceptual, motion, transition). Avoid
city→city→city or phone→phone→phone.

Think in this order for EVERY scene:
NARRATION → VISUAL PURPOSE → BEST MEDIA TYPE → SPECIFIC SEARCH/PROMPT →
TIMESTAMP REQUIREMENT → QUALITY → FALLBACK.

Each scene.narration must be the exact spoken words this beat covers — not a
paraphrase of later paragraphs, not a summary of the whole film, and not a
visual prompt. Every scene must map to a real slice of the script. No
significant stretch of narration may be left without visuals.

Semantic, not literal. Show the meaning in a watchable shot.
- "social jet lag" is not a person looking tired. It is two clocks / two
  schedules that do not line up.
- "biological clock" is not a wall clock. It is a body-internal system
  (sleep, hormones, temperature, alertness) colliding with a calendar.
- "like traveling across time zones" is a metaphor: prefer a conceptual
  image, not generic airplane stock, unless the script is actually about flying.
- "you are not lazy" is not a person on a couch. It is someone trying to
  meet a schedule their body is resisting.

MEDIA RULES (evaluate the visual — do NOT use a fixed Stock→YouTube→Flow ladder):
- stock_video is the DEFAULT for ordinary modern real-world B-roll stock can film:
  people, cities, commuting, driving, sleeping, phones, nature, airplanes,
  ordinary daily activities. Pexels/Pixabay/Openverse cover this. Prefer HD
  stock when it is sufficient. HARD MAX 6.0s.
- archive_video (Internet Archive) for HISTORICAL / PUBLIC-DOMAIN documentary
  footage: pre-2000s newsreels, old government film, classic space-program
  archival clips, historical events where rights-clear authentic footage exists
  on archive.org. Prefer archive over YouTube when the beat is clearly
  historical and archive likely has better rights/metadata. HARD MAX 3.0s.
- nasa_video (NASA media library) for US space/science footage: rocket
  launches, mission control, planets, satellites, ISS, rovers, official NASA
  animations/real telemetry visuals. Use for space/science beats BEFORE generic
  YouTube or stock when NASA likely has the authentic clip. HARD MAX 3.0s.
- youtube ONLY when RECENT authentic footage has documentary value that archive
  and NASA cannot supply: a recent rocket launch, a contemporary news event,
  a real scientific demo uploaded recently, a specific modern real-world event.
  Never pick YouTube for pre-1980 history if archive can serve the beat.
  Never pick YouTube because a video exists. HARD MAX 3.0s.
- flow_video when generated motion helps: scientific visualization, biological
  processes, conceptual explanation, impossible camera moves, cinematic
  transitions, time/space metaphors, tech+nature, shots stock/archives cannot
  provide. HARD MAX 6.0s.
- flow_image for conceptual/static visualizations when motion is unnecessary.
  HARD MAX 3.0s.
- stock_image when motion adds nothing or video is unavailable. HARD MAX 3.0s.
- local only if the user said a file already exists.
- NEVER use local in an analyzed plan — local is for manual CSV / user-dropped files only.
  If unsure, use stock_video or stock_image with search_queries.

SOURCE PRIORITY CHEAT-SHEET (pick the strongest fit per beat, not a ladder):
- Modern everyday life → stock_video
- US space / NASA missions / planets / rockets (official) → nasa_video
- Historical newsreel / old film / public-domain archive → archive_video
- Famous historical photo / map / diagram / encyclopedic still → stock_image
- Recent authentic event not in archives → youtube_video
- Abstract concept / impossible shot → flow_video or flow_image

QUALITY: every scene needs minimum_quality, normally "1080p".
Stock/archive/NASA/YouTube: prefer 1080p+ when available. Flow: cinematic.

SEARCH QUERIES:
- stock_video / stock_image: 6–12 words: subject + action + setting + time of day.
- archive_video / nasa_video / youtube_video: 3–8 searchable words.
  Multiple queries REQUIRED (at least 2), progressively broader:
  specific event/person/mission → slightly broader → semantic synonym.
  Examples:
    Apollo 11 launch (archive): ["apollo 11 launch 1969", "saturn v liftoff moon mission"]
    Pluto flyby (nasa): ["new horizons pluto flyby", "pluto encounter nasa"]
    Moon landing (stock_image): ["apollo 11 moon landing", "neil armstrong lunar surface"]
    Recent Falcon 9 (youtube): ["Falcon 9 rocket launch night", "SpaceX Falcon 9 launch"]
  Forbidden: cinematic fluff, narration copied verbatim, tiny rewrites of the same
  sentence, or irrelevant queries to pad the list.
- Forbidden generic: "tired person", "people walking", "busy city", "man thinking",
  "person using phone", or the narration copied verbatim.
- Flow: put the generation prompt in visual_description; leave search_queries empty.

If phones or beds appear more than once, each shot must differ (alarm-as-clock
vs blue-light scrolling vs phone face-down; dawn vs weekend vs night).

timestamp_needed is true ONLY for youtube_video scenes that need a specific moment.
Archive/NASA do not use timestamp_needed — pick search queries instead.
You do not extract transcripts.

DURATION HARD LIMITS (a plan is INVALID if any scene exceeds its cap):
- youtube / youtube_video / archive / archive_video / nasa / nasa_video:
  preferred 2.0–3.0s, HARD MAX 3.0s
- flow_video: preferred 3.0–5.0s, HARD MAX 6.0s
- stock_video: preferred 2.5–5.0s, HARD MAX 6.0s
- flow_image: preferred 2.0–3.0s, HARD MAX 3.0s
- stock_image: preferred 2.0–3.0s, HARD MAX 3.0s
Never use 4–6s for a still image. Images are short visual beats, not long
static shots. Rhythm: image ~2.5s, video ~3–4s, important flow_video ~4–5s.
If an important narration section needs more time, do NOT extend the clip
past its cap. Split into another beat. Every scene duration >= 1.5s.

Fallbacks must match THIS scene's visual (not one chain for every scene):
stock_video → stock_image → flow_image;
flow_image → stock_image (or stock_video if a real approximation exists);
flow_video → stock_video → flow_image;
archive_video → youtube → stock_video → flow_image;
nasa_video → archive → youtube → flow_video;
youtube → archive → stock_video → flow_image (prefer archive for historical
beats if YouTube fails; prefer stock/flow for modern lifestyle beats).
Always declare at least one fallback for archive, nasa, and youtube.
Never let a single failed search query kill the scene.

VISUAL ALLOCATION (application-side — you do NOT micromanage counts):
Describe WHAT visual is needed (visual_goal, visual_description, provider_preference
as a HINT). The application automatically decides image vs video mix, AI-video
budget, and coverage — do NOT specify exact counts of Flow/stock/image scenes.
Focus on semantic visual requirements per beat; the Visual Allocation Engine
assigns asset types after your plan is parsed.

Return ONE JSON object, no prose:
{
  "topic": "short topic",
  "scenes": [
    {
      "scene_id": 1,
      "narration": "exact words this scene covers (may be more than one sentence)",
      "visual_goal": "what the shot must communicate",
      "visual_description": "concrete visible content",
      "asset_type": "youtube_video | archive_video | nasa_video | stock_video | stock_image | image | video",
      "provider_preference": "youtube | archive | nasa | stock_video | stock_image | flow_image | flow_video",
      "search_queries": ["apollo 11 launch 1969", "saturn v moon mission liftoff"],
      "timestamp_needed": false,
      "timestamp_hint": "",
      "duration": 2.5,
      "importance": "high | medium | low",
      "fallbacks": ["youtube", "stock_video", "flow_image"],
      "visual_treatment": "subtle push-in",
      "transition": "cut",
      "minimum_quality": "1080p"
    }
  ]
}

Return as many scene objects as the narration requires. The example above is
the shape of ONE scene, not the length of the film.

asset_type must match provider_preference:
youtube→youtube_video, archive→archive_video, nasa→nasa_video,
stock_video→stock_video, stock_image→stock_image,
flow_image→image, flow_video→video, local→local.
transition: cut, dissolve, fade, or match_cut.
"""


def estimate_narration_seconds(word_count: int, wpm: float = NARRATION_WPM_ESTIMATE) -> float:
    if word_count <= 0 or wpm <= 0:
        return 0.0
    return word_count * 60.0 / wpm


def script_word_count(script: str) -> int:
    return len((script or "").split())


def coverage_ratio(script: str, narrations: list[str]) -> float:
    script_tokens = [
        w.lower().strip(".,;:!?\"'()[]")
        for w in (script or "").split()
        if w.strip(".,;:!?\"'()[]")
    ]
    if not script_tokens:
        return 1.0
    spoken = " ".join(narrations).lower()
    spoken_set = {
        w.strip(".,;:!?\"'()[]")
        for w in spoken.split()
        if w.strip(".,;:!?\"'()[]")
    }
    hits = sum(1 for w in script_tokens if w in spoken_set)
    return hits / len(script_tokens)


def plan_segmentation_issue(script: str, plan: VisualPlan) -> str | None:
    """Return a human-readable failure if the plan obviously compresses the film.

    Does not require visual duration to equal narration duration.
    Does not impose a target scene count.
    """
    words = script_word_count(script)
    n = len(plan.scenes)
    if n < MIN_SCENES:
        return f"Plan has {n} scene(s); need a visual timeline, not an empty list."
    estimated = estimate_narration_seconds(words)
    # Short pieces are allowed to stay compact.
    if estimated >= 120 and n > 0:
        implied = estimated / n
        hold_cap = max_implied_speech_per_scene(words)
        # Dense plans (many scenes for the word count) are acceptable even near the cap.
        dense_enough = n >= max(MIN_SCENES, int(words / 26))
        if implied > hold_cap and not (dense_enough and implied <= hold_cap + 2.5):
            minutes = estimated / 60.0
            return (
                f"Plan is under-segmented: about {words:,} words "
                f"(~{minutes:.0f} min of narration at {NARRATION_WPM_ESTIMATE:.0f} wpm) "
                f"were packed into {n} scenes (~{implied:.0f}s of speech per visual beat). "
                "Documentary visuals should change about every 2–5 seconds. "
                "Walk the script again and split each visual idea into short beats "
                "within the duration caps. Do not summarize."
            )
    ratio = coverage_ratio(script, [s.narration for s in plan.scenes])
    if words >= 80 and ratio < MIN_COVERAGE_RATIO:
        return (
            "Plan does not cover the full narration "
            f"(only {ratio:.0%} of script words appear in scene narration). "
            "Map every section of the script to visual beats."
        )
    return None


def _plan_user_message(script: str) -> str:
    chars = len(script)
    words = script_word_count(script)
    est = estimate_narration_seconds(words)
    lo = estimate_narration_seconds(words, NARRATION_WPM_HIGH)
    hi = estimate_narration_seconds(words, NARRATION_WPM_LOW)
    return (
        "Create a complete visual timeline for this entire narration.\n"
        f"Script length: {chars:,} characters, {words:,} words.\n"
        f"Estimated spoken duration: about {est / 60:.1f} minutes "
        f"(range {lo / 60:.1f}–{hi / 60:.1f} min at {NARRATION_WPM_LOW}–"
        f"{NARRATION_WPM_HIGH} words/minute). This is a planning estimate, "
        "not a runtime to match clip-for-clip.\n"
        "There is NO required scene count and NO maximum scene count. "
        "Split the script into short visual beats (about 2–5s of visual "
        "change) covering every section. Do not compress a long documentary "
        "into a handful of summary scenes. Do not pad with duplicate shots.\n"
        "Each scene.narration = the exact spoken words for that beat.\n"
        "Obey the duration HARD MAX rules.\n\n"
        "--- SCRIPT ---\n"
        f"{script}\n"
        "--- END SCRIPT ---\n"
    )


def _revision_user_message(script: str, previous: VisualPlan, issue: str) -> str:
    return (
        "Your previous visual plan was REJECTED.\n"
        f"Reason: {issue}\n\n"
        "Revise by walking the SAME script from start to finish. Split visual "
        "ideas into short beats. Do not reuse the compressed scene list. "
        "Do not aim for a specific number of scenes. Cover the entire "
        "narration. Keep duration HARD MAX rules. No duplicate padding.\n\n"
        + _plan_user_message(script)
    )


def _json_revision_prefix(issue: str) -> str:
    return (
        "Your previous JSON response was rejected.\n"
        f"Reason: {issue}\n"
        "Return ONE JSON object with \"topic\" and \"scenes\" keys "
        "(not a bare array, not prose outside JSON). "
        "Each scene needs narration, visual_goal, visual_description, "
        "provider_preference, and search_queries.\n\n"
    )


def gemini_plan_settings(word_count: int) -> dict:
    """Tune Gemini latency vs coverage from script size (Analyze Script)."""
    if word_count < 120:
        return {"thinking_level": "low", "max_output_tokens": 8192, "timeout": 90.0}
    if word_count < 400:
        return {"thinking_level": "low", "max_output_tokens": 16384, "timeout": 120.0}
    if word_count < 1200:
        return {"thinking_level": "low", "max_output_tokens": 32768, "timeout": 180.0}
    return {"thinking_level": "medium", "max_output_tokens": 65536, "timeout": 300.0}


class VisualDirector:
    def __init__(self, llm: LLMProvider | None = None, settings=None):
        self.llm = llm or GeminiLLM(settings=settings, timeout=300.0)
        self.settings = settings

    def _emit_progress(
        self,
        on_progress: PlanProgressCallback | None,
        message: str,
        fraction: float | None = None,
    ) -> None:
        if on_progress is not None:
            on_progress(message, fraction)

    def _llm_for_words(self, words: int) -> tuple[LLMProvider, dict]:
        gemini_opts = gemini_plan_settings(words)
        llm = self.llm
        if isinstance(llm, GeminiLLM):
            llm = GeminiLLM(
                api_key=llm.api_key,
                model=llm.model,
                base_url=llm.base_url,
                timeout=gemini_opts["timeout"],
                settings=self.settings,
            )
        return llm, gemini_opts

    def _complete_plan(
        self,
        llm: LLMProvider,
        user: str,
        *,
        gemini_opts: dict,
    ) -> VisualPlan:
        if isinstance(llm, GeminiLLM):
            raw = llm.complete(
                SYSTEM_PROMPT,
                user,
                thinking_level=gemini_opts["thinking_level"],
                max_output_tokens=gemini_opts["max_output_tokens"],
            )
        else:
            raw = llm.complete(SYSTEM_PROMPT, user)
        return parse_visual_plan(raw)

    def _plan_single(
        self,
        text: str,
        *,
        style_guidance: str = "",
        on_progress: PlanProgressCallback | None = None,
    ) -> VisualPlan:
        user = _plan_user_message(text)
        tip = (style_guidance or "").strip()
        if tip:
            user = (
                "PRODUCTION STYLE GUIDANCE (follow without changing scene coverage rules):\n"
                f"{tip}\n\n"
                + user
            )
        words = script_word_count(text)
        llm, gemini_opts = self._llm_for_words(words)
        last_issue = ""
        max_attempts = plan_max_attempts(words)
        base_user = user
        for attempt in range(max_attempts):
            self._emit_progress(
                on_progress,
                f"Gemini planning — attempt {attempt + 1}/{max_attempts}…",
                0.15 + (attempt / max(max_attempts, 1)) * 0.55,
            )
            try:
                plan = self._complete_plan(llm, user, gemini_opts=gemini_opts)
            except LLMError:
                raise
            except VisualPlanError as exc:
                last_issue = str(exc)
                if attempt + 1 >= max_attempts:
                    raise
                self._emit_progress(
                    on_progress,
                    f"JSON revision needed: {last_issue[:120]}…",
                    0.2 + (attempt / max(max_attempts, 1)) * 0.5,
                )
                user = _json_revision_prefix(last_issue) + base_user
                continue
            issue = plan_segmentation_issue(text, plan)
            if issue is None:
                self._emit_progress(
                    on_progress,
                    f"Plan accepted — {len(plan.scenes)} scene(s).",
                    0.75,
                )
                return plan
            last_issue = issue
            self._emit_progress(
                on_progress,
                f"Revision needed: {issue[:120]}…",
                0.2 + (attempt / max(max_attempts, 1)) * 0.5,
            )
            user = _revision_user_message(text, plan, issue)
        raise VisualPlanError(last_issue)

    def _plan_chunked(
        self,
        text: str,
        *,
        style_guidance: str = "",
        on_progress: PlanProgressCallback | None = None,
    ) -> VisualPlan:
        from .chunking import (
            chunk_plan_user_message,
            merge_chunk_plans,
            split_script_into_chunks,
        )

        words = script_word_count(text)
        chunks = split_script_into_chunks(text)
        total = len(chunks)
        self._emit_progress(
            on_progress,
            f"Long script ({words:,} words) — planning {total} sections in parallel…",
            0.05,
        )
        tip = (style_guidance or "").strip()
        style_prefix = ""
        if tip:
            style_prefix = (
                "PRODUCTION STYLE GUIDANCE (follow without changing scene coverage rules):\n"
                f"{tip}\n\n"
            )

        def plan_one(index: int, chunk: str) -> VisualPlan:
            chunk_words = script_word_count(chunk)
            llm, gemini_opts = self._llm_for_words(chunk_words)
            base_user = style_prefix + chunk_plan_user_message(
                chunk,
                section_index=index,
                section_total=total,
                full_word_count=words,
            )
            user = base_user
            section_label = f"Section {index + 1}/{total}"
            for attempt in range(CHUNK_SECTION_MAX_ATTEMPTS):
                try:
                    return self._complete_plan(llm, user, gemini_opts=gemini_opts)
                except LLMError:
                    raise
                except VisualPlanError as exc:
                    if attempt + 1 >= CHUNK_SECTION_MAX_ATTEMPTS:
                        raise VisualPlanError(f"{section_label}: {exc}") from exc
                    user = f"{section_label}: " + _json_revision_prefix(str(exc)) + base_user

        plans: list[VisualPlan | None] = [None] * total
        done = 0
        workers = min(4, total)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(plan_one, i, chunk): i
                for i, chunk in enumerate(chunks)
            }
            for fut in as_completed(futures):
                index = futures[fut]
                plans[index] = fut.result()
                done += 1
                scene_so_far = sum(len(p.scenes) for p in plans if p is not None)
                self._emit_progress(
                    on_progress,
                    f"Section {index + 1}/{total} complete — {scene_so_far} scenes so far…",
                    0.1 + (done / total) * 0.55,
                )

        merged = merge_chunk_plans([p for p in plans if p is not None])
        self._emit_progress(
            on_progress,
            f"Merged {len(merged.scenes)} scenes — validating full script…",
            0.7,
        )
        issue = plan_segmentation_issue(text, merged)
        if issue is None:
            return merged

        self._emit_progress(
            on_progress,
            "Merged plan needs refinement — running full-script revision…",
            0.72,
        )
        return self._plan_single(text, style_guidance=style_guidance, on_progress=on_progress)

    def plan(
        self,
        script: str,
        *,
        style_guidance: str = "",
        on_progress: PlanProgressCallback | None = None,
    ) -> VisualPlan:
        text = (script or "").strip()
        if not text:
            raise ValueError("script is empty")
        from .chunking import should_chunk_plan

        words = script_word_count(text)
        self._emit_progress(
            on_progress,
            f"Starting analyze (~{words:,} words)…",
            0.02,
        )
        if should_chunk_plan(text):
            return self._plan_chunked(
                text, style_guidance=style_guidance, on_progress=on_progress
            )
        return self._plan_single(
            text, style_guidance=style_guidance, on_progress=on_progress
        )
