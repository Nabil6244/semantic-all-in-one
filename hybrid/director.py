"""The Hybrid Visual Director: timed narration -> HybridPlan, with a dedicated prompt (composition_styles/hybrid_director_prompt.txt).

The LLM chooses beats as RANGES OF SENTENCES; this module turns them into a plan with real times (the boundary between two beats
is the pause between their sentences), resolves overlay anchors to narration words, derives the camera moves, and reports anything
that does not hold together as problems the repair loop can act on. Any object with complete(system, user) -> str is an LLM."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ai_router.errors import AllRoutesUnavailable
from .narration import Sentence, Word, words_between
from .plan import Beat, CameraStep, Clip, HybridPlan, Layer, Support

PROMPT_DIR = Path(__file__).resolve().parent.parent / "composition_styles"
MODE_ALIASES = {"map": "map", "footage": "footage", "map_footage": "map_footage", "map+footage": "map_footage", "map_and_footage": "map_footage", "mapfootage": "map_footage"}
FRAMES = ("globe", "continental", "country", "region", "local")
ROLES_MARKER = ("dark", "neutral", "featured", "subject", "compare")
FILL_ROLES = ("subject", "featured", "compare", "orange", "accent", "water", "green")
LINE_KINDS = ("flow", "river", "rail", "border_trace", "divide", "reference", "connector")
TRANSITION_SOUNDS = ("", "soft_transition")


class DirectorError(RuntimeError):
    pass


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def director_prompt() -> str:
    return load_prompt("hybrid_director_prompt.txt")


RETRY_DELAYS = (4.0, 10.0, 25.0, 50.0, 90.0, 120.0)  # seconds between attempts when the provider says it is busy (about five minutes in all)
_TRANSIENT = re.compile(r"high demand|overloaded|try again|temporar|unavailable|rate.?limit|exceeded your current quota|quota exceeded|resource.?exhausted|429|500|502|503|504|timed? ?out|timeout|connection|request failed", re.I)


def _is_transient(exc: Exception) -> bool:
    text = str(exc)
    return bool(_TRANSIENT.search(text)) and "API key" not in text and "not configured" not in text.lower()


def _complete(llm: Any, system: str, user: str, say: Optional[Callable[[str], None]] = None, *, task: str = "director",
              accept: Optional[Callable[[str], bool]] = None, label: str = "") -> str:
    """One LLM call. With an AI router the request is routed by `task` (providers, models, fallbacks, caching and failure handling live there);
    with a plain client, a provider that is merely busy (demand spikes, rate limits, timeouts) is retried with a growing pause, telling `say`
    why it is waiting; anything else (no key, a bad request) fails at once."""
    import time

    if hasattr(llm, "run_task"):
        return llm.run_task(task, system, user, say=say, accept=accept, label=label)

    def once() -> str:
        try:
            from visual_director.llm import GeminiLLM

            if isinstance(llm, GeminiLLM):
                # the same latency/size tuning the app's Visual Director uses for a script of this length
                from visual_director.director import gemini_plan_settings

                opts = gemini_plan_settings(len(user.split()))
                tuned = GeminiLLM(api_key=llm.api_key, model=llm.model, base_url=llm.base_url, timeout=opts["timeout"], credentials=getattr(llm, "credentials", None))
                return tuned.complete(system, user, thinking_level=opts["thinking_level"], max_output_tokens=opts["max_output_tokens"])
        except ImportError:
            pass
        return llm.complete(system, user)

    for delay in RETRY_DELAYS:
        try:
            return once()
        except Exception as exc:
            if not _is_transient(exc):
                raise
            if say is not None:
                say(f"The AI service is busy ({str(exc)[:70]}…): trying again in {delay:.0f}s")
            time.sleep(delay)
    return once()


def _usable_plan(raw: str, sentences: Sequence[Sentence], words: Sequence[Word], duration: float, settings: Optional[Dict[str, Any]], **kw: Any) -> bool:
    """Would this answer turn into a plan? Checked locally, so an answer that does not is retried or re-routed and is never cached."""
    try:
        plan_from_payload(parse_json(raw), sentences, words, duration, settings, derive=False, **kw)
        return True
    except Exception:
        return False


def parse_json(raw: str) -> Any:
    from visual_director.schema import extract_json_payload

    return extract_json_payload(raw)


def sentences_message(sentences: Sequence[Sentence], *, duration: float, style_guidance: str = "", indices: Optional[Sequence[int]] = None) -> str:
    lines = []
    for s in sentences:
        if indices is not None and s.index not in indices:
            continue
        lines.append(f"[{s.index}] {s.start:6.1f}s-{s.end:6.1f}s  {s.text}")
    head = f"Video length {duration:.0f} seconds, {len(sentences)} sentences. Narration (sentence index, time span, text):\n"
    guide = f"\nPRODUCTION STYLE GUIDANCE (does not change the rules above):\n{style_guidance.strip()}\n" if style_guidance.strip() else ""
    return head + "\n".join(lines) + guide + "\nReturn the beats JSON for this narration."


# ---- payload -> plan ----------------------------------------------------------------------------------------------

def _norm_words(text: str) -> List[str]:
    return re.findall(r"[0-9a-z]+", text.lower())


def anchor_time(words: Sequence[Word], phrase: str, lo: float, hi: float, after: float = 0.0) -> Optional[float]:
    """When `phrase` is first spoken inside [lo, hi], preferring a place after `after`; None when it is not found. Uses pakMap's
    matcher, so "240 million" finds the spoken "two hundred and forty million" and a split name still matches."""
    from pakmap.anchor import Transcript

    seg = [w for w in words if lo - 0.05 <= w[1] <= hi + 0.05]
    if not seg or not str(phrase).strip():
        return None
    tr = Transcript(seg)
    cursor = sum(1 for (f, _l) in tr._spans if tr.words[f][1] < after - 1e-6)
    hit = tr.find(str(phrase), cursor)
    return None if hit is None else hit[0].t_start


def _ranges(payload_beats: List[dict], n_sentences: int, problems: List[str]) -> List[Tuple[int, int, dict]]:
    out: List[Tuple[int, int, dict]] = []
    for k, raw in enumerate(payload_beats):
        try:
            a, b = raw["sentences"]
            a, b = int(a), int(b)
        except (KeyError, TypeError, ValueError):
            problems.append(f"beat {k + 1}: it needs \"sentences\": [first, last]")
            continue
        out.append((a, b, raw))
    out.sort(key=lambda x: x[0])
    fixed: List[Tuple[int, int, dict]] = []
    expect = 0
    for a, b, raw in out:
        if a > b:
            problems.append(f"beat starting at sentence {a}: the range [{a}, {b}] runs backwards")
            continue
        if a < expect:
            problems.append(f"beat starting at sentence {a} overlaps the previous beat (it ends at sentence {expect - 1})")
            a = expect
            if a > b:
                continue
        if a > expect:
            problems.append(f"sentences {expect}-{a - 1} are in no beat")
            if fixed:  # close the gap by extending the previous beat: the plan stays usable, the problem is still reported
                pa, _pb, praw = fixed[-1]
                fixed[-1] = (pa, a - 1, praw)
            else:
                a = 0
        fixed.append((a, b, raw))
        expect = b + 1
    if fixed and expect < n_sentences:
        problems.append(f"sentences {expect}-{n_sentences - 1} are in no beat")
        pa, _pb, praw = fixed[-1]
        fixed[-1] = (pa, n_sentences - 1, praw)
    if not fixed:
        problems.append("the response contains no usable beats")
    return fixed


def clean_place(name: Any) -> str:
    """A place the way pakMap can find it: "Balochistan, Pakistan" -> "Balochistan" when the whole text is not found but its first part is.
    Coordinates ("35.3,75.6") and city:Name,ISO references are left alone."""
    text = str(name or "").strip()
    if not text or re.match(r"^-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?$", text) or text.lower().startswith("city:"):
        return text
    from .geo import GeoError, resolve

    for prefer in ("area", "point"):
        try:
            resolve(text, prefer)
            return text
        except GeoError:
            pass
    if "," in text:
        head = text.split(",")[0].strip()
        for prefer in ("area", "point"):
            try:
                resolve(head, prefer)
                return head
            except GeoError:
                pass
    return text


def _asset(source: str, query: str) -> str:
    source = (source or "").strip().lower()
    return f"{source}:{' '.join((query or '').split())}"


def _layers(raw_layers: List[dict], bid: str, start: float, end: float, words: Sequence[Word], problems: List[str]) -> List[Layer]:
    layers: List[Layer] = []
    last_t = start
    spread = (end - start) / (len(raw_layers) + 1) if raw_layers else 0
    for k, rl in enumerate(raw_layers):
        typ = str(rl.get("type", "")).strip().lower()
        t = anchor_time(words, str(rl.get("anchor", "")), start, end - 0.4, after=last_t - 0.01) if rl.get("anchor") else None
        if t is None:
            t = min(end - 0.5, start + 0.3 + spread * (k + 1) * 0.8)
            problems.append(f"beat {bid}: layer {k + 1} ({typ}) anchor {str(rl.get('anchor', ''))!r} was not found in this beat's narration; it was placed at {t:.1f}s")
        t = max(start, min(t, end - 0.4))
        last_t = t
        lay = Layer(id=f"{bid}_{typ or 'layer'}{k + 1}", type=typ, t=round(t, 2), place=clean_place(rl.get("place", "")), places=[clean_place(p) for p in rl.get("places") or []],
                    label=str(rl.get("label", "") or ""), sub=str(rl.get("sub", "") or ""), text=str(rl.get("text", "") or ""), role=str(rl.get("role", "") or ""),
                    kind=str(rl.get("kind", "") or ""), value_from=None if rl.get("from") is None else float(rl["from"]),
                    value_to=None if rl.get("to") is None else float(rl["to"]), format=str(rl.get("format", "") or ""), until=rl.get("until") or "beat_end")
        if typ == "marker" and lay.role and lay.role not in ROLES_MARKER:
            lay.role = ""
        if typ == "fill" and lay.role and lay.role not in FILL_ROLES:
            lay.role = "subject"
        if typ == "line" and lay.kind not in LINE_KINDS:
            lay.kind = "flow"
        layers.append(lay)
    return layers


def plan_from_payload(payload: Any, sentences: Sequence[Sentence], words: Sequence[Word], duration: float,
                      settings: Optional[Dict[str, Any]] = None, span: Optional[Tuple[float, float]] = None, *,
                      bounds: Optional[Tuple[float, float]] = None, id_start: int = 0, derive: bool = True) -> Tuple[HybridPlan, List[str]]:
    """Turn the Director's JSON into a HybridPlan with real times. Returns (plan, problems): problems are things the response got wrong
    that the code worked around (or could not); the pipeline reports them and the repair loop can fix the beats they name."""
    problems: List[str] = []
    beats_raw = payload.get("beats") if isinstance(payload, dict) else payload
    if not isinstance(beats_raw, list) or not beats_raw:
        raise DirectorError("the Director's answer has no beats")
    ranges = _ranges(beats_raw, len(sentences), problems)
    beats: List[Beat] = []
    for k, (a, b, raw) in enumerate(ranges):
        a = max(0, min(a, len(sentences) - 1))
        b = max(a, min(b, len(sentences) - 1))
        t_first, t_last = bounds if bounds is not None else (0.0, duration)   # a chapter owns [t_first, t_last] of the whole narration
        start = t_first if k == 0 else (sentences[a - 1].end + sentences[a].start) / 2 if a > 0 else sentences[a].start
        end = t_last if k == len(ranges) - 1 else (sentences[b].end + sentences[b + 1].start) / 2
        start, end = round(start, 3), round(end, 3)
        if k > 0:
            start = beats[-1].end
        if span is not None and len(ranges) == 1:  # one beat redone inside a plan: its real place on the timeline
            start, end = round(span[0], 3), round(span[1], 3)
        bid = f"b{id_start + k + 1}"
        mode = MODE_ALIASES.get(str(raw.get("mode", "")).strip().lower().replace(" ", "_").replace("-", "_"))
        if mode is None:
            problems.append(f"beat {bid}: mode {raw.get('mode')!r} is not map, footage or map_footage")
            mode = "map"
        beat = Beat(id=bid, mode=mode, start=start, end=end, purpose=str(raw.get("purpose", "") or ""),
                    narration=" ".join(s.text for s in sentences[a:b + 1]), confidence=float(raw.get("confidence", 0.8) or 0.8))
        bw = words_between(words, start, end)
        if mode in ("map", "map_footage"):
            m = raw.get("map") or {}
            beat.geo_intent = str(m.get("geo_intent", "") or "")
            beat.overlay_intent = str(m.get("overlay_intent", "") or "")
            cam = m.get("camera") or {}
            beat.cam_place = clean_place(cam.get("place", ""))
            beat.cam_frame = str(cam.get("frame", "") or "") if str(cam.get("frame", "")) in FRAMES else ("region" if cam.get("place") else "")
            beat.cam_move = str(cam.get("move", "") or "")
            beat.layers = _layers([l for l in (m.get("layers") or []) if isinstance(l, dict)], bid, start, end, bw, problems)
            if mode == "map_footage":
                sp = raw.get("support") or {}
                if sp.get("query"):
                    t = anchor_time(bw, str(sp.get("anchor", "")), start, end - 2.0) if sp.get("anchor") else None
                    beat.support = Support(asset=_asset(sp.get("source", "stock_image"), sp["query"]), t=None if t is None else round(t, 2), place=clean_place(sp.get("place", "")),
                                           label=str(sp.get("label", "") or "").upper())
                    beat.footage_intent = str(sp.get("reason", "") or sp.get("label", "") or "")
                else:
                    problems.append(f"beat {bid}: a map_footage beat needs a \"support\" card with a query")
        else:
            f = raw.get("footage") or {}
            beat.footage_intent = str(f.get("footage_intent", "") or "")
            beat.keep_overlays = bool(f.get("keep_overlays", False))
            ts = str(f.get("transition_sound", "") or "")
            beat.transition_sound = ts if ts in TRANSITION_SOUNDS else ""
            for c in f.get("clips") or []:
                if isinstance(c, dict) and (c.get("query") or c.get("asset")):
                    asset = str(c["asset"]) if c.get("asset") else _asset(c.get("source", "stock_video"), c["query"])
                    beat.clips.append(Clip(asset=asset, reason=str(c.get("reason", "") or ""), kenburns=asset.split(":")[0] in ("stock_image", "flow_image")))
            if not beat.clips:
                problems.append(f"beat {bid}: a footage beat needs at least one clip with a query")
        beats.append(beat)
    plan = HybridPlan(duration=round(float(duration), 3), beats=beats, settings=dict(settings or {}))
    if derive:
        derive_cameras(plan)
    return plan, problems


def _km_between(a: str, b: str) -> float:
    """Straight-line distance between two places the atlas can locate (0 when either cannot be found)."""
    import math

    from .geo import GeoError, resolve

    try:
        la, lb = resolve(a), resolve(b)
    except (GeoError, Exception):
        return 0.0
    p1, p2 = math.radians(la.lat), math.radians(lb.lat)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lb.lon - la.lon) / 2) ** 2
    return 12742.0 * math.asin(min(1.0, math.sqrt(h)))


def derive_cameras(plan: HybridPlan) -> None:
    """Camera steps from each map beat's target (cam_place / cam_frame / cam_move): the first map beat starts the camera; a later beat
    moves it only when its target differs, always clear of the footage dissolves on either side. Beats with no target keep the steps
    they already have (a hand-authored plan)."""
    from .plan import free_interval

    current: Optional[Tuple[str, str]] = None
    started = any(c.action == "start" for b in plan.beats if not b.cam_place for c in b.camera)
    for i, b in enumerate(plan.beats):
        if not plan.is_map_mode(b) or not b.cam_place:
            continue
        lo, hi = free_interval(plan, i)
        b.camera = []
        target = (b.cam_place, b.cam_frame or "region")
        if not started:
            if plan.setting("globe_opening") and b.start < 0.05 and target[1] != "globe" and hi - 1.4 >= 2.6:
                # the video opens on the whole planet for a moment, then flies in to its subject and stays close
                b.camera.append(CameraStep(action="start", place=target[0], frame="globe", t=0.0))
                b.camera.append(CameraStep(action="fly_to", place=target[0], frame=target[1], t=1.4, dur=2.2))
            else:
                b.camera.append(CameraStep(action="start", place=target[0], frame=target[1], t=0.0))
            started, current = True, target
        elif target != current and b.cam_move != "hold":
            t0 = round(lo + 0.3, 2)
            dur = round(min(2.4, hi - t0 - 0.2), 2)
            far = current is not None and _km_between(current[0], target[0]) >= float(plan.setting("globe_hop_km"))
            if far and hi - t0 - 0.2 >= 3.6 and target[1] != "globe":
                # a very long jump: pull out to the globe, travel while zoomed out, then zoom in on the new subject
                b.camera.append(CameraStep(action="fly_to", place=target[0], frame="globe", t=t0, dur=1.5))
                b.camera.append(CameraStep(action="fly_to", place=target[0], frame=target[1], t=round(t0 + 1.5, 2), dur=round(min(2.0, hi - t0 - 1.7), 2)))
                current = target
            elif dur >= 0.8:
                b.camera.append(CameraStep(action="fly_to", place=target[0], frame=target[1], t=t0, dur=dur))
                current = target
        elif b.cam_move == "push_in":
            t0 = round(lo + 0.3, 2)
            dur = round(min(8.0, hi - t0 - 0.2), 2)
            if dur >= 1.0:
                b.camera.append(CameraStep(action="push_in", t=t0, dur=dur, zoom_delta=0.6))
    if not any(c.action == "start" for b in plan.beats for c in b.camera):  # the video never shows a map target: give the camera one anyway
        for b in plan.beats:
            if plan.is_map_mode(b):
                tgt = next((l.place for l in b.layers if l.place), "") or b.cam_place
                if tgt:
                    b.camera.insert(0, CameraStep(action="start", place=tgt, frame="country", t=0.0))
                break


# ---- the Director ---------------------------------------------------------------------------------------------------

def plan_beats(llm: Any, sentences: Sequence[Sentence], words: Sequence[Word], duration: float, *, settings: Optional[Dict[str, Any]] = None,
               style_guidance: str = "", on_progress: Optional[Callable[[str], None]] = None, attempts: int = 2) -> Tuple[HybridPlan, List[str]]:
    system, user = director_prompt(), sentences_message(sentences, duration=duration, style_guidance=style_guidance)
    last = ""
    for attempt in range(attempts):
        if on_progress:
            on_progress(f"Hybrid Director: planning the beats (attempt {attempt + 1}/{attempts})…")
        raw = _complete(llm, system, user, on_progress, task="director", label="plan", accept=lambda t: _usable_plan(t, sentences, words, duration, settings))
        try:
            payload = parse_json(raw)
            return plan_from_payload(payload, sentences, words, duration, settings)
        except AllRoutesUnavailable:
            raise
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            user = (f"Your previous answer could not be used ({last[:300]}). Answer again with ONLY the JSON object described, with \"beats\" "
                    f"covering every sentence.\n\n") + sentences_message(sentences, duration=duration, style_guidance=style_guidance)
    raise DirectorError(f"the Director's answer could not be read: {last}")


# ---- long narrations: one chapter per request -----------------------------------------------------------------------

def chapter_state(beats: Sequence[Beat]) -> Dict[str, Any]:
    """What the next chapter must know about the story so far: where the camera is, what is still on the map, which titles and pictures
    were already used. Read from the beats planned so far, so a chapter never restarts the geography or repeats a title."""
    cam = next(((b.cam_place, b.cam_frame) for b in reversed(beats) if b.cam_place), ("", ""))
    carried = []
    for b in beats[-3:]:
        for l in b.layers:
            if l.until in ("after_footage", "end"):
                carried.append(f"{l.type} {l.label or l.place or l.text}".strip())
    places: List[str] = []
    for b in reversed(beats[-8:]):
        for p in ([b.cam_place] if b.cam_place else []) + [l.place for l in b.layers if l.place and l.type in ("marker", "fill", "zone_label")]:
            if p and p not in places:
                places.append(p)
    titles = [l.label for b in beats for l in b.layers if l.type == "hud_title" and l.label][-12:]
    assets = [c.asset for b in beats[-6:] for c in b.clips] + [b.support.asset for b in beats[-6:] if b.support]
    last = [f"{b.id} {b.mode}: {b.purpose or b.geo_intent or b.footage_intent}" for b in beats[-2:]]
    return {"camera": cam, "carried": carried, "places": places[:12], "titles": titles, "assets": assets, "last": last}


def chunk_message(local: Sequence[Sentence], *, chapter: int, chapters: int, t0: float, t1: float, state: Optional[Dict[str, Any]], upcoming: Sequence[str],
                  style_guidance: str = "") -> str:
    """The request for one chapter. Sentences are numbered from 0 within the chapter; their times are the whole video's."""
    lines = [f"[{s.index}] {s.start:7.1f}s-{s.end:7.1f}s  {s.text}" for s in local]
    head = (f"CHAPTER CONTEXT: you are planning chapter {chapter} of {chapters} of one long documentary. This chapter owns the narration from "
            f"{t0:.1f}s to {t1:.1f}s of the video (times below are the whole video's). Plan ONLY this chapter: your beats must cover every sentence "
            f"below, indexed from 0 as shown.\n")
    if state is None:
        head += "This is the opening chapter: the video opens as described in the rules.\n"
    else:
        cam = state["camera"]
        head += ("The video is already under way: do NOT open on the globe and do not restart the story. "
                 f"The map camera is currently looking at {cam[0] or 'the story so far'}{f' ({cam[1]})' if cam[1] else ''}; continue from there "
                 "(\"hold\" if the geography continues, \"fly_to\" when it moves).\n")
        if state["last"]:
            head += "The chapter before ended with: " + " | ".join(state["last"]) + "\n"
        if state["carried"]:
            head += "Still on the map from before: " + ", ".join(state["carried"]) + "\n"
        if state["places"]:
            head += "Places already shown recently: " + ", ".join(state["places"]) + "\n"
        if state["titles"]:
            head += "Titles already used (do not repeat): " + "; ".join(state["titles"][-12:]) + "\n"
        if state["assets"]:
            head += "Pictures and clips used just before (choose different ones): " + "; ".join(state["assets"]) + "\n"
    if upcoming:
        head += "The next chapter begins with: " + " ".join(upcoming) + "\n"
    head += "Also return \"chapter_title\": a short title for this chapter.\n"
    guide = f"\nPRODUCTION STYLE GUIDANCE (does not change the rules above):\n{style_guidance.strip()}\n" if style_guidance.strip() else ""
    return head + f"\nNarration of this chapter ({len(local)} sentences):\n" + "\n".join(lines) + guide + "\nReturn the beats JSON for this chapter."


def local_sentences(sentences: Sequence[Sentence], first: int, last: int) -> List[Sentence]:
    return [Sentence(i, s.text, s.start, s.end, s.para_end) for i, s in enumerate(sentences[first:last + 1])]


def plan_chunk(llm: Any, sentences: Sequence[Sentence], words: Sequence[Word], chunk: Any, chapters: int, prior: Sequence[Beat], id_start: int, *,
               settings: Optional[Dict[str, Any]] = None, style_guidance: str = "", on_progress: Optional[Callable[[str], None]] = None,
               attempts: int = 2, cached: Optional[Dict[str, Any]] = None) -> Tuple[List[Beat], str, List[str], Dict[str, Any]]:
    """Plan one chapter. Returns (beats with global ids and times, chapter title, problems, the Director's raw payload for the checkpoint).
    `cached` is a payload saved by an earlier run of the same chapter: it is used instead of asking again."""
    local = local_sentences(sentences, chunk.first, chunk.last)
    upcoming = [s.text for s in sentences[chunk.last + 1: chunk.last + 3]]
    state = chapter_state(prior) if prior else None
    system = director_prompt()
    user = chunk_message(local, chapter=chunk.index, chapters=chapters, t0=chunk.start, t1=chunk.end, state=state, upcoming=upcoming, style_guidance=style_guidance)
    payload: Any = cached
    last = ""
    for attempt in range(attempts + (0 if cached is None else 1)):
        try:
            if payload is None:
                if on_progress:
                    on_progress(f"Hybrid Director: chapter {chunk.index}/{chapters} ({chunk.start / 60:.0f}-{chunk.end / 60:.0f} min), attempt {attempt + 1}/{attempts}…")
                payload = parse_json(_complete(llm, system, user, on_progress, task="director", label=f"chapter {chunk.index}",
                                               accept=lambda t: _usable_plan(t, local, words, chunk.end, settings, bounds=(chunk.start, chunk.end), id_start=id_start)))
            sub, problems = plan_from_payload(payload, local, words, chunk.end, settings, bounds=(chunk.start, chunk.end), id_start=id_start, derive=False)
            for b in sub.beats:
                b.chapter = chunk.index
            title = str(payload.get("chapter_title", "")).strip() if isinstance(payload, dict) else ""
            return sub.beats, title or f"Chapter {chunk.index}", problems, payload if isinstance(payload, dict) else {"beats": payload}
        except AllRoutesUnavailable:
            raise      # no provider can answer right now: say so plainly (the saved chapters are kept), do not ask again
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            payload = None
            user = (f"Your previous answer could not be used ({last[:300]}). Answer again with ONLY the JSON object described, with \"beats\" "
                    f"covering every sentence of this chapter.\n\n") + chunk_message(local, chapter=chunk.index, chapters=chapters, t0=chunk.start, t1=chunk.end,
                                                                                        state=state, upcoming=upcoming, style_guidance=style_guidance)
    raise DirectorError(f"chapter {chunk.index}: the Director's answer could not be read: {last}")


def repair_message(plan: HybridPlan, weak: Dict[str, List[str]], sentences: Sequence[Sentence]) -> str:
    """Only the weak beats, each with its sentence range, its current content and what is wrong, plus one beat of context either side."""
    parts = ["Redo ONLY the beats listed below. Keep each beat's sentence range exactly (you may change its mode, purpose and content, but do not merge or split beats).",
             "Return JSON {\"beats\": [...]} containing exactly these beats, each with its \"beat\" id (for example \"beat\": \"b3\") and its \"sentences\" range as given, in the same format as before.\n"]
    ids = [b.id for b in plan.beats]
    first = min(ids.index(b) for b in weak)
    state = chapter_state(plan.beats[:first]) if first else None
    if state:
        cam = state["camera"]
        parts.append(f"Story so far: the camera was looking at {cam[0] or 'the opening view'}{f' ({cam[1]})' if cam[1] else ''}; recent places: "
                     f"{', '.join(state['places']) or 'none'}; titles already used: {'; '.join(state['titles'][-12:]) or 'none'}; pictures just used: {'; '.join(state['assets']) or 'none'}.\n")
    for bid, issues in sorted(weak.items(), key=lambda kv: ids.index(kv[0])):
        i = ids.index(bid)
        b = plan.beats[i]
        s0 = next(s.index for s in sentences if s.start >= b.start - 0.6)
        s1 = max(s.index for s in sentences if s.end <= b.end + 0.6)
        around = [plan.beats[j] for j in (i - 1, i + 1) if 0 <= j < len(plan.beats)]
        parts.append(f"--- BEAT {bid}: sentences [{s0}, {s1}] ({b.start:.1f}s-{b.end:.1f}s), currently mode={b.mode}")
        parts.append("Narration: " + b.narration)
        parts.append("Current plan: " + json.dumps(_brief(b), ensure_ascii=False))
        parts.append("What is wrong: " + " | ".join(issues))
        parts.append("Neighbouring beats (for continuity, do not change): " + "; ".join(f"{n.id} {n.mode}: {n.purpose or n.geo_intent or n.footage_intent}" for n in around))
    return "\n".join(parts)


def _brief(b: Beat) -> dict:
    d: Dict[str, Any] = {"mode": b.mode, "purpose": b.purpose}
    if b.mode == "footage":
        d["clips"] = [c.asset for c in b.clips]
        d["footage_intent"] = b.footage_intent
    else:
        d["camera"] = {"place": b.cam_place, "frame": b.cam_frame}
        d["layers"] = [f"{l.type}:{l.label or l.place or l.text}" for l in b.layers]
        if b.support:
            d["support"] = b.support.asset
    return d


def _usable_repair(raw: str) -> bool:
    try:
        payload = parse_json(raw)
        items = payload.get("beats") if isinstance(payload, dict) else payload
        return isinstance(items, list) and bool(items)
    except Exception:
        return False


def _pair_repairs(items: List[Any], weak_ids: List[str], plan: HybridPlan, sentences: Sequence[Sentence]) -> List[Tuple[str, dict]]:
    """Which answer is for which beat. By the echoed "beat" id when there is one; otherwise by the sentence range (the answer that starts
    inside the beat); otherwise by position in the timeline (the Director answers in timeline order, which is not the order the beats were
    sent in). Never by the order of `weak`."""
    beats = {b.id: b for b in plan.beats}
    order = [b.id for b in plan.beats if b.id in weak_ids]
    taken: Dict[str, dict] = {}
    rest: List[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        bid = str(raw.get("beat", "")).strip()
        if bid in weak_ids and bid not in taken:
            taken[bid] = raw
            continue
        rest.append(raw)
    for raw in list(rest):
        try:
            first = int(raw["sentences"][0])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        t0 = sentences[max(0, min(first, len(sentences) - 1))].start
        for bid in order:
            b = beats[bid]
            if bid not in taken and b.start - 0.7 <= t0 < b.end:
                taken[bid] = raw
                rest.remove(raw)
                break
    for bid in order:  # whatever is left, in timeline order
        if bid not in taken and rest:
            taken[bid] = rest.pop(0)
    return [(bid, taken[bid]) for bid in order if bid in taken]


def repair_beats(llm: Any, plan: HybridPlan, weak: Dict[str, List[str]], sentences: Sequence[Sentence], words: Sequence[Word],
                 on_progress: Optional[Callable[[str], None]] = None) -> Tuple[HybridPlan, List[str]]:
    """Ask the Director to redo just the weak beats and splice the answers into a copy of the plan. Times never change."""
    import copy

    if on_progress:
        on_progress(f"Hybrid Director: redoing {len(weak)} weak beat(s): {', '.join(weak)}…")
    # Targeted: only the weak beats (their own narration, their neighbours, what was wrong) and a compact record of the story so far.
    # The rest of the chapter's narration is not sent: the beats' times and ranges are fixed, so it cannot change the answer.
    raw = _complete(llm, director_prompt(), repair_message(plan, weak, sentences), on_progress, task="repair", label=",".join(weak), accept=_usable_repair)
    payload = parse_json(raw)
    items = payload.get("beats") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise DirectorError("the repair answer has no beats")
    new = copy.deepcopy(plan)
    problems: List[str] = []
    ids = [b.id for b in new.beats]
    for bid, raw_beat in _pair_repairs(items, list(weak), plan, sentences):
        i = ids.index(bid)
        old = new.beats[i]
        # rebuild this beat from its own sentence range, with the old beat's real times
        tmp = {"beats": [{**raw_beat, "sentences": [0, 0]}]}
        fake = [Sentence(0, old.narration, old.start, old.end)]
        sub, probs = plan_from_payload(tmp, fake, words, old.end, span=(old.start, old.end))
        nb = sub.beats[0]
        nb.id, nb.start, nb.end, nb.narration = bid, old.start, old.end, old.narration
        for k, lay in enumerate(nb.layers):
            lay.id = f"{bid}_{lay.type}{k + 1}"
        new.beats[i] = nb
        problems += [p.replace("beat b1", f"beat {bid}") for p in probs]
    derive_cameras(new)
    return new, problems
