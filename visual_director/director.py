"""AI Visual Director: full script → structured plan for AssetManager."""

from __future__ import annotations

from .llm import GeminiLLM, LLMError, LLMProvider
from .schema import MIN_SCENES, VisualPlan, VisualPlanError, parse_visual_plan

# Planning estimate only — not an exact runtime and not a scene-count formula.
NARRATION_WPM_LOW = 130
NARRATION_WPM_HIGH = 160
NARRATION_WPM_ESTIMATE = 145
# Implied speech-seconds per visual beat above this is severe under-segmentation
# (documentary rhythm is ~2–5s; provider clips max out at 3–6s).
SEVERE_HOLD_SECONDS = 8.0
MIN_COVERAGE_RATIO = 0.55

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
- stock_video is the DEFAULT for ordinary real-world B-roll stock can film:
  people, cities, commuting, driving, sleeping, phones, nature, airplanes,
  ordinary daily activities. Prefer HD stock when it is sufficient.
- youtube ONLY when authentic footage has documentary value: a real rocket
  launch, a historical event, a real scientific demonstration, a specific
  real-world event stock cannot reproduce. Never pick YouTube because a
  video exists. HARD MAX 3.0s.
- flow_video is first-class when generated motion helps: scientific
  visualization, biological processes, conceptual explanation, impossible
  camera moves, cinematic transitions, time/space metaphors, tech+nature,
  shots stock cannot provide. HARD MAX 6.0s.
- flow_image for conceptual/static visualizations when motion is unnecessary.
  HARD MAX 3.0s.
- stock_image when motion adds nothing or video is unavailable. HARD MAX 3.0s.
- local only if the user said a file already exists.

QUALITY: every scene needs minimum_quality, normally "1080p".
YouTube/stock: prefer 1080p+. Flow: cinematic, sharp, well-lit.

SEARCH QUERIES:
- stock_video / stock_image: 6–12 words: subject + action + setting + time of day.
- youtube_video: 3–8 searchable words. Multiple queries REQUIRED, progressively
  broader (specific → slightly broader → semantic → still-relevant generic).
  Example for a night Falcon 9:
    ["Falcon 9 rocket launch night", "SpaceX Falcon 9 launch",
     "Falcon 9 night launch", "rocket launch night"]
  Forbidden: cinematic fluff ("standing on launchpad", "floodlights",
  "static view", "cinematic", "close-up tracking shot") and tiny rewrites of
  the same sentence. Do not invent irrelevant queries to pad the list.
- Forbidden generic: "tired person", "people walking", "busy city", "man thinking",
  "person using phone", or the narration copied verbatim.
- Flow: put the generation prompt in visual_description; leave search_queries empty.

If phones or beds appear more than once, each shot must differ (alarm-as-clock
vs blue-light scrolling vs phone face-down; dawn vs weekend vs night).

timestamp_needed is true ONLY for YouTube scenes that need a specific moment.
You do not extract transcripts.

DURATION HARD LIMITS (a plan is INVALID if any scene exceeds its cap):
- youtube / youtube_video: preferred 2.0–3.0s, HARD MAX 3.0s
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
flow_video → stock_video → flow_image.
youtube: pick fallbacks that still serve the beat if authentic footage cannot
be found. Example for a launch: flow_video, stock_video, flow_image. For a
real historical event where generated footage would mislead, prefer
stock_video then flow_image — not a fake recreation. Always declare at least
one fallback for youtube. Never let a single failed YouTube query kill the scene.

Return ONE JSON object, no prose:
{
  "topic": "short topic",
  "scenes": [
    {
      "scene_id": 1,
      "narration": "exact words this scene covers (may be more than one sentence)",
      "visual_goal": "what the shot must communicate",
      "visual_description": "concrete visible content",
      "asset_type": "youtube_video | stock_video | stock_image | image | video | local",
      "provider_preference": "youtube | stock_video | stock_image | flow_image | flow_video | local",
      "search_queries": ["Falcon 9 rocket launch night", "SpaceX Falcon 9 launch", "rocket launch night"],
      "timestamp_needed": false,
      "timestamp_hint": "",
      "duration": 2.5,
      "importance": "high | medium | low",
      "fallbacks": ["flow_video", "stock_video", "flow_image"],
      "visual_treatment": "subtle push-in",
      "transition": "cut",
      "minimum_quality": "1080p"
    }
  ]
}

Return as many scene objects as the narration requires. The example above is
the shape of ONE scene, not the length of the film.

asset_type must match provider_preference:
youtube→youtube_video, stock_video→stock_video, stock_image→stock_image,
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
        if implied > SEVERE_HOLD_SECONDS:
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


class VisualDirector:
    def __init__(self, llm: LLMProvider | None = None, settings=None):
        self.llm = llm or GeminiLLM(settings=settings, timeout=300.0)

    def plan(self, script: str, *, style_guidance: str = "") -> VisualPlan:
        text = (script or "").strip()
        if not text:
            raise ValueError("script is empty")
        user = _plan_user_message(text)
        tip = (style_guidance or "").strip()
        if tip:
            user = (
                "PRODUCTION STYLE GUIDANCE (follow without changing scene coverage rules):\n"
                f"{tip}\n\n"
                + user
            )
        last_issue = ""
        for attempt in range(2):
            try:
                raw = self.llm.complete(SYSTEM_PROMPT, user)
            except LLMError:
                raise
            plan = parse_visual_plan(raw)
            issue = plan_segmentation_issue(text, plan)
            if issue is None:
                return plan
            last_issue = issue
            user = _revision_user_message(text, plan, issue)
        raise VisualPlanError(last_issue)
