"""A picture for every beat, in the reference's manga style, generated from the beat's own narration through the app's Flow image workflow and cached in the Rep Theory library.
The prompt is the library's character + style text plus the beat's words, so the same lean trainee appears doing or showing what is being said; for a beat about tissue or objects the picture is an
illustration of that instead. The id is a hash of the prompt: re-rendering a script (or any script with the same beat) reuses the picture, nothing is generated twice.
Synthetic / made-up data is never illustrated (a picture would make it look real), and tier boards and equations keep their own graphics."""
from __future__ import annotations
import hashlib, re, tempfile, time
from pathlib import Path
from typing import Dict, List, Optional

from . import art as A, library as L

SKIP_KINDS = {"tier", "equation", "stat", "steps", "versus", "takeaway"}      # these keep their own graphic
REPEAT_KINDS = {"anatomy", "prop", "hold", "pose", "trainee"}      # a stored picture is kept for the first scene, but never shown again in the next scene: that scene gets its own picture
SYNTH_RX = re.compile(r"\b(synthetic|made[- ]up|fictional|invented|test study)\b", re.I)
TISSUE_RX = re.compile(r"\b(muscle|muscles|tendon|tendons|bone|bones|fibre|fibres|fiber|fibers|ligament|joint|nerve|blood flow|tissue)\b", re.I)

RIVAL_RX = re.compile(r"\b(big(?:ger)? guys?|bigger than you|opponent|rival|the other guy|giant|huge guy|heavier|stronger than (?:you|him)|against (?:guys|a guy|someone)|arm[- ]?wrestl\w*|versus him|his hand|he has you)\b", re.I)
FOCUS_RX = re.compile(r"\b(tendons?|forearms?|wrists?|fingers?|hands?|biceps?|triceps?|shoulders?|chest|core|abs|glutes?|quads?|thighs?|hamstrings?|calf|calves|knees?|elbows?|neck|spine|hips?|lower back|grip)\b", re.I)

WORKER_RX = re.compile(r"\b(?:mechanics?|bricklayers?|farmers?|carpenters?|tradesm[ae]n|plumbers?|builders?|labou?rers?|welders?|blue[- ]collar workers?|construction workers?|movers?)\b", re.I)

def _red_part(text: str) -> str:
    m = FOCUS_RX.search(text)
    return f" Paint his {m.group(1).lower()} glowing red over the ink." if m else ""

def _cat() -> bool:
    from . import theme as T
    return T.THEME == "cat"

def _jung() -> bool:
    from . import theme as T
    return T.THEME == "jung"

JUNG_FLOW_REFS = 3      # references sent per Jung picture (Flow's limit). If Flow's picker cannot show a later one, the engine sends with those it attached
                        # and saves reference-picker.txt for the fix (flow-engine/lib/flow-references.js); the first one alone always worked (2026-11-08).
JUNG_RX = re.compile(r"\b(?:jung|carl|he|his|him|himself)\b", re.I)      # a Carl Jung Theory line about the man himself: drawn with his reference images

def wants_refs(prompt: str) -> bool:
    """A Carl Jung Theory picture that shows Jung (its prompt carries his character sentence): sent to Flow with his reference images."""
    return _jung() and A.JUNG_SHEET in prompt

def _jung_prompt(desc: str, about_him: bool) -> str:
    return (f"{A.JUNG_SHEET}. {desc}. {A.JUNG_STYLE}." if about_him else f"{desc}. No real or famous person, no Carl Jung. {A.JUNG_STYLE}.")

def prompt_for(text: str, hook: bool = False) -> str:
    """Flow prompt for one beat: what the narration says at this moment, drawn in the reference style (ink, one side empty, the named part in red, the rival when there is an opponent)."""
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if _cat(): return f"A single scene from a cat behaviour explainer video, illustrating exactly this narration: \"{text}\". {A.CAT_STYLE}."
    if _jung(): return _jung_prompt(f"A single scene from a psychology documentary, illustrating exactly this narration: \"{text}\"", bool(JUNG_RX.search(text)))
    if TISSUE_RX.search(text) and not re.search(r"\b(hold|hang|pinch|squeeze|stand|lift|push|pull|squat|plank|rotate|wrestl\w*|curl|sit)\b", text, re.I):      # tissue: the realistic anatomy picture we always had, word for word, so pictures made before are reused
        return (f"A clear anatomical illustration that shows what this sentence of a fitness explainer is about: \"{text}\". Show the relevant muscles, tendons or bones of the body part concerned, "
                f"{A.REAL_STYLE}.")
    who = (f"{A.TRADESMAN}" + (f", with {A.CHARACTER} as the person he meets" if re.search(r"\b(?:you|your)\b", text, re.I) else "")) if WORKER_RX.search(text) and not RIVAL_RX.search(re.sub(r"\bbigger than\b", "", text)) \
        else f"{A.CHARACTER}" + (f", facing {A.RIVAL}" if RIVAL_RX.search(text) else "")      # the workers the line is about, not our trainee or the bodybuilder
    if hook: return (f"The opening image of a fitness explainer, one striking picture of this promise: \"{text}\". Show {who}, the contrast between them obvious at a glance, a dramatic "
                     f"moment caught mid-action.{_red_part(text)} {A.SCENE_STYLE}.")
    return (f"A single scene from a fitness explainer video, illustrating exactly this narration: \"{text}\". Show {who}, doing or demonstrating what is described, with any named object or "
            f"equipment drawn clearly, the whole action visible.{_red_part(text)} {A.SCENE_STYLE}.")

def own_prompt(text: str) -> str:
    """The scenes CSV's own picture description, in the same style and with the same trainee (and rival) as every other picture of the video."""
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if _cat(): return f"{text}. {A.CAT_STYLE}."      # the cat niche: no trainee cast, white background
    if _jung(): return _jung_prompt(text, bool(re.search(r"\b(?:jung|carl)\b", text, re.I)))      # the CSV prompt names Jung when he is in the picture
    if TISSUE_RX.search(text) and not re.search(r"\b(trainee|man|woman|person|athlete|he|she|rival|guy)\b", text, re.I): return f"{text}. {A.INK_ANATOMY}." if re.search(r"\b(ink|sketch|manga)\b", text, re.I) else f"{text}, {A.REAL_STYLE}."      # as before, unless the CSV asks for an ink drawing
    cast = f" If the trainee is shown, he is {A.CHARACTER}." + (f" The rival / big guy is {A.RIVAL}." if re.search(r"\b(rival|big guy|bigger guy|opponent|big man)\b", text, re.I) else "") + \
           (f" The tradesman is {A.TRADESMAN}." if re.search(r"\btradesm[ae]n\b|\bworker\b", text, re.I) else "")
    return f"{text}.{cast} {A.SCENE_STYLE}."

# A prompt Flow refused ("This generation might violate our policies") is tried once more in a safer wording. Only the retry changes: every
# picture that was drawn keeps its prompt and its id, so nothing already made is drawn again. The trainee's look stays exactly the same.
SAFE_SUBS = (
    (re.compile(r"\byoung man\b", re.I), "adult man in his late twenties"), (re.compile(r"\bskinny\b", re.I), "slim"),
    (re.compile(r"\b(?:boys?|kids?|child(?:ren)?|teen(?:ager)?s?)\b", re.I), "adults"),
    (re.compile(r"\bpainted glowing red\b|\bglowing red\b", re.I), "highlighted in red"), (re.compile(r"\bPaint (his|the) ", re.I), r"Highlight \1 "),
    (re.compile(r"\b(?:tear(?:s|ing)?|torn|ruptur(?:e|es|ed|ing)|snap(?:s|ped|ping)?|broken|bleed(?:s|ing)?|blood(?:y)?|wound(?:s|ed)?|injur(?:y|ies|ed)|strain(?:s|ed)?|sprain(?:s|ed)?|"
                r"pain(?:ful)?|hurts?|hurting|agony|damaged?)\b", re.I), "under load"),
    (re.compile(r"\b(?:fight(?:s|ing)?|attack(?:s|ing)?|punch(?:es|ing)?|crush(?:es|ing)?|smash(?:es|ing)?|destroy(?:s|ing)?|kill(?:s|ing)?|slam(?:s|med|ming)?)\b", re.I), "compete with"),
    (re.compile(r"\bthe bigger, stronger-looking opponent\b", re.I), "his friendly training partner"),
)
SAID_RX = re.compile(r'(illustrating exactly this narration|one striking picture of this promise|what this sentence of a fitness explainer is about): "([^"]*)"')

def safe_prompt(prompt: str) -> str:
    """The retry wording for a refused prompt: an adult, no injury or fight words, the red part 'highlighted', the narration quoted in it cut to its first
    clause (the action and the body part)."""
    p = SAID_RX.sub(lambda m: f'{m.group(1)}: "{re.split(r"[,;:.!?]", m.group(2))[0].strip()}"', prompt)
    for rx, rep in SAFE_SUBS: p = rx.sub(rep, p)
    return p + (" A calm, friendly illustration for a general audience." if _cat() else " A calm, respectful painting for a general audience." if _jung() else " A calm, friendly fitness illustration for a general audience.")

def art_id(prompt: str) -> str:
    """The picture's library id: a hash of its prompt, and for a Carl Jung Theory picture of Jung also of the references it is drawn from (other references, another picture)."""
    key = prompt
    if wants_refs(prompt):
        refs = A.jung_refs()[:JUNG_FLOW_REFS]; key += "|refs:" + ",".join(hashlib.sha1(Path(r).read_bytes()).hexdigest()[:8] for r in refs)
    return "beat_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

def eligible(sc: dict) -> bool:
    return sc["kind"] not in SKIP_KINDS and sc["kind"] != "clip3d" and not SYNTH_RX.search(sc.get("text", "")) and bool(sc.get("text", "").strip())

def _same(a, b) -> bool: return " ".join(str(a or "").split()).lower() == " ".join(str(b or "").split()).lower()

def prepare(scenes: List[dict], mode: str = "agent", account_ids=None, log=print, settings: Optional[dict] = None, generate_missing: bool = True, directed: bool = False,
            collect: Optional[list] = None, chosen: Optional[Dict[int, dict]] = None) -> Dict[str, int]:
    """Gives every eligible scene its picture: kind becomes "illus", art the cached id. A scene whose picture could not be had keeps its previous treatment (and says so in `decisions`).
    collect (Generate scenes): nothing is generated; each scene that wants a picture is appended as {no, text, prompt, cached} for the Visuals tab.
    chosen (Render): {scene no: the Visuals tab's finished file record}; that file is the scene's picture, whatever made it."""
    todo: Dict[str, str] = {}; stat = {"reused": 0, "generated": 0, "failed": 0, "skipped": 0, "chosen": 0}; prev_fp, prev_text = "", None
    prev = None
    for sc in scenes:
        asked = bool(sc.get("directed_look"))      # the scenes CSV chose this scene's look: a picture only where it asked for one
        if (directed or asked) and sc.get("look") != "flow": stat["skipped"] += 1; continue      # the variety director chose which scenes get a Flow picture
        sig = (sc["kind"], sc.get("art"), sc.get("prop")); repeat = sc["kind"] in REPEAT_KINDS and prev == sig; prev = sig
        if sc["kind"] in REPEAT_KINDS and not repeat and not sc.get("want_picture") and not (directed or asked): stat["skipped"] += 1; continue
        if not eligible(sc): stat["skipped"] += 1; continue
        if sc.get("asset"):      # a library asset (assets.py): one fixed prompt and id, made once and reused by every video
            from . import assets as AS
            p = AS.prompt(sc["asset"]); i = AS.art_id(sc["asset"])
        else:
            fp = sc.get("flow_prompt") or ""
            if fp and not sc.get("same_picture") and _same(fp, prev_fp) and not _same(sc.get("text"), prev_text):      # the same picture for a different line (render 054: "steel cables" got the "rubber bands" picture)
                sc["decisions"].append("CSV picture repeats the previous row's for a different line: drawn from its own narration"); fp = ""
            elif fp and WORKER_RX.search(sc.get("text", "")) and not WORKER_RX.search(fp) and not re.search(r"\btradesm[ae]n\b|\bworker\b", fp, re.I):      # the line is about mechanics / farmers, the CSV drew our cast
                sc["decisions"].append("the line is about the workers it names; the CSV picture shows the trainee or the rival: drawn from the narration"); fp = ""
            prev_fp, prev_text = sc.get("flow_prompt") or "", sc.get("text")
            p = own_prompt(fp) if fp else prompt_for(sc["text"], hook=bool(sc.get("hook"))); i = art_id(p)
        sc["_illus"] = (i, p)
        if collect is not None: collect.append({"no": sc["no"], "text": sc["text"], "prompt": p, "cached": (L.find(i) or {}).get("path")}); continue
        pick = (chosen or {}).get(sc["no"])
        if pick and pick.get("ok") and _same(pick.get("narration"), sc["text"]):
            same = str(pick.get("source")) in ("flow_image", "image") and _same(pick.get("query"), p)      # the picture made for this prompt: kept under its own id, reused by other scripts
            pid = i if same else "pick_" + hashlib.sha1(f"{p}|{pick['path']}|{Path(pick['path']).stat().st_size}".encode("utf-8")).hexdigest()[:12]
            if not L.find(pid): L.register(pick["path"], id=pid, kind="scene", subject=p[:120], prompt=p, source="flow" if same else "supplied", notes="from the Visuals tab")
            sc["_illus"] = (pid, p); stat["chosen"] += 1; continue
        if L.find(i): stat["reused"] += 1
        elif generate_missing: todo[i] = p
    if todo:
        from providers.base import SceneRow
        from providers.flow.engine_manager import FlowEngineManager
        from providers.flow.provider import FlowProvider
        mgr = FlowEngineManager(log=log); fs = {"model": "GEM_PIX_2", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE", "generationMode": mode}; fs.update(settings or {})
        prov = FlowProvider(mgr, media_kind="image", account_ids=account_ids, flow_settings=fs); ids = list(todo)
        ref_ids = [i for i in ids if wants_refs(todo[i])]; refs = A.flow_ref_copies(A.jung_refs()[:JUNG_FLOW_REFS]) if ref_ids else []
        if ref_ids and not refs: log(f"[JUNG THEORY ART] no reference images in assets/jung/refs: {len(ref_ids)} picture(s) of Jung are drawn from the description alone")
        if ref_ids and refs:      # Jung's pictures go in their own batch with his reference images (Flow attaches them through the UI agent: flow-engine/lib/flow-references.js)
            ids = [i for i in ids if i not in ref_ids] + ref_ids
            prov_refs = FlowProvider(mgr, media_kind="image", account_ids=account_ids, flow_settings=dict(fs, referenceImages=refs))
        rows = [SceneRow(scene_number=str(n + 1), script_segment=todo[i], asset_type="image", prompt=todo[i]) for n, i in enumerate(ids)]
        log(f"[REP THEORY ART] requesting {len(rows)} Flow image(s) for this script (mode {mode})" + (f"; {len(ref_ids)} of Jung with {len(refs)} reference image(s)" if ref_ids and refs else ""))
        if ref_ids and refs:
            plain = [r for r, i in zip(rows, ids) if i not in ref_ids]; withr = [r for r, i in zip(rows, ids) if i in ref_ids]
            res = prov.resolve_batch(plain, Path(tempfile.mkdtemp(prefix="rt_beat_")), log=log) if plain else {}
            res = dict(res or {}); res.update(prov_refs.resolve_batch(withr, Path(tempfile.mkdtemp(prefix="rt_beat_ref_")), log=log) or {})
        else: res = prov.resolve_batch(rows, Path(tempfile.mkdtemp(prefix="rt_beat_")), log=log)
        retry = []
        for n, i in enumerate(ids):
            r = res.get(str(n + 1)); path = getattr(r, "path", None) if r is not None else None
            if path and Path(path).is_file(): L.register(path, id=i, kind="scene", subject=todo[i][:120], prompt=todo[i], source="flow", notes=f"flow {mode} {time.strftime('%Y-%m-%d')}"); stat["generated"] += 1
            else: retry.append((n, i))
        if retry:      # refused or failed: once more in the safer wording, saved under the scene's own id
            log(f"[REP THEORY ART] {len(retry)} picture(s) refused or failed; trying each once more in a safer wording")
            rows2 = [SceneRow(scene_number=str(n + 1), script_segment=todo[i], asset_type="image", prompt=safe_prompt(todo[i])) for n, i in retry]
            if ref_ids and refs:      # each picture retried with its own batch's references
                r_plain = [r for r, (n, i) in zip(rows2, retry) if i not in ref_ids]; r_ref = [r for r, (n, i) in zip(rows2, retry) if i in ref_ids]
                res2 = dict(prov.resolve_batch(r_plain, Path(tempfile.mkdtemp(prefix="rt_beat_retry_")), log=log) or {}) if r_plain else {}
                if r_ref:      # the retry sends one reference (the first, the main portrait): fewer pictures to attach through Flow's picker
                    prov_one = FlowProvider(mgr, media_kind="image", account_ids=account_ids, flow_settings=dict(fs, referenceImages=refs[:1]))
                    res2.update(prov_one.resolve_batch(r_ref, Path(tempfile.mkdtemp(prefix="rt_beat_retry_ref_")), log=log) or {})
            else: res2 = prov.resolve_batch(rows2, Path(tempfile.mkdtemp(prefix="rt_beat_retry_")), log=log)
            for (n, i), row in zip(retry, rows2):
                r = res2.get(str(n + 1)); path = getattr(r, "path", None) if r is not None else None
                if path and Path(path).is_file(): L.register(path, id=i, kind="scene", subject=todo[i][:120], prompt=row.prompt, source="flow", notes=f"flow {mode} safer retry {time.strftime('%Y-%m-%d')}"); stat["generated"] += 1; stat["retried"] = stat.get("retried", 0) + 1
                else: stat["failed"] += 1; log(f"[REP THEORY ART] {i}: refused again ({getattr(r, 'error', None)}); that scene keeps its card or text. Prompt: {row.prompt[:160]}")
    for sc in scenes:
        got = sc.pop("_illus", None)
        if got and L.find(got[0]): sc["decisions"].append(f"picture from the narration: {sc['kind']} -> illus"); sc["was_kind"] = sc["kind"]; sc["kind"] = "illus"; sc["art"] = got[0]; sc["prop"] = ""
    return stat
