"""The Food Files host: our own AI presenter, kept the same in every picture and clip by Flow reference pictures.

Not the reference channel's host: different face, clothes, set and light. The pack lives in out/foodfiles/hosts/<name>/:
  portrait.png   waist-up anchor (face + clothes)         made by Flow on the first Generate (no references)
  set.png        the host at his desk in the studio set   made by Flow with the portrait as reference
  talk_*.mp4     optional silent talking loops            (Flow video credits, made once)
  host.json      name, look, set, Flow voice
A shipped pack in foodfiles/hosts/<name>/ (if any) is copied there once.
"""
import json
from pathlib import Path

from prepper_host import host as _ph

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ROOT / "out" / "foodfiles" / "hosts"
SHIPPED = Path(__file__).resolve().parent / "hosts"

THEO = {
    "name": "Theo",
    "tagline": "reads the recall notices so you don't have to",
    "look": ("Theo, an American man in his early thirties, short wavy dark-brown hair, neat short beard, warm brown eyes, "
             "friendly expressive face, wearing a mustard-yellow crewneck sweatshirt over a white t-shirt collar, "
             "a thin silver watch, no hat, no glasses"),
    "set": ("seated at a dark walnut desk with a black podcast microphone on a boom arm in front of him, in a cosy small studio: "
            "behind him a wall of open wooden shelves with glass jars of colourful candy, vintage cereal boxes and old soda "
            "bottles, a warm orange practical lamp on one side and a soft teal glow on the other, shallow depth of field"),
    "voice": "Achird",   # must be a name in Flow's Voices tab (Puck is not)
    "voice_performance": "upbeat, quick and conversational American man in his early thirties, curious, a little sarcastic",
}
LOOK = ("Photorealistic photo, shot on a full-frame camera with a 35mm lens, soft cinematic light, shallow depth of field, "
        "true-to-life skin texture, no text, no logos, no watermark.")


def pack_dir(name):
    return HOSTS / name.lower()


def load(name="theo"):
    """The host meta (same keys as Prepper Host's, so its Flow voice and clip code work unchanged)."""
    name = (name or "theo").lower()
    d = pack_dir(name)
    src = SHIPPED / name
    if src.is_dir() and not (d / "portrait.png").is_file():
        try:
            d.mkdir(parents=True, exist_ok=True)
            for f in src.iterdir():
                if f.is_file() and not (d / f.name).exists():
                    (d / f.name).write_bytes(f.read_bytes())
        except OSError:
            pass
    meta = dict(THEO) if name == "theo" else {"name": name.title(), "tagline": "", "look": name, "set": THEO["set"]}
    jf = d / "host.json"
    if jf.is_file():
        meta.update(json.loads(jf.read_text(encoding="utf-8")))
    else:
        try:
            d.mkdir(parents=True, exist_ok=True)
            jf.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        except OSError:
            pass
    meta["dir"] = str(d)
    meta["portrait"] = str(d / "portrait.png") if (d / "portrait.png").is_file() else None
    meta["set_image"] = str(d / "set.png") if (d / "set.png").is_file() else None
    meta["talk_clips"] = [str(p) for p in sorted(d.glob("talk_*.mp4"))]
    return meta


def pack_jobs(meta):
    """Flow jobs for the missing pack pictures: [(stage, {key: prompt}, uses_portrait_ref)]."""
    jobs = []
    if not meta.get("portrait"):
        jobs.append(("portrait", {f"ff_host_{meta['name'].lower()}_portrait":
                                  f"{meta['look']}. Waist-up portrait facing the camera, relaxed friendly half-smile, plain warm "
                                  f"grey studio backdrop, even soft light. {LOOK}"}, False))
    if not meta.get("set_image"):
        jobs.append(("set", {f"ff_host_{meta['name'].lower()}_set":
                             f"The man from the reference picture, {meta['look']}, {meta['set']}. Medium shot from the chest up, "
                             f"he looks straight into the camera mid-sentence with one hand raised in a small gesture, centred "
                             f"framing, the microphone at the lower edge of the frame. {LOOK}"}, True))
    return jobs


def make_pack(meta, session, log=print, cancel=None):
    """Make the missing portrait / set pictures with an open prepper_host.flow.Session; returns the reloaded meta."""
    from prepper_host import flow
    d = Path(meta["dir"])
    d.mkdir(parents=True, exist_ok=True)
    for stage, job, needs_ref in pack_jobs(meta):
        if cancel and cancel():
            break
        k = next(iter(job))
        if not flow.have(k):
            refs = [meta["portrait"]] if needs_ref and meta.get("portrait") else None
            log(f"food files: making the host's {stage} picture with Flow")
            session.pictures(job, refs=refs, cancel=cancel)
        got = flow.have(k)
        if got:
            (d / f"{stage if stage == 'portrait' else 'set'}.png").write_bytes(Path(got).read_bytes())
            meta = load(meta["name"])
    return meta


POSES = (   # free test mode (talking="stills"): Flow pictures of the host at his desk, no video credits
    "talking to the camera mid-sentence with one hand raised",
    "leaning in close to the camera with a serious face, elbows on the desk",
    "looking shocked, eyes wide, both hands up in disbelief",
    "laughing at something, head tilted back a little",
    "pointing straight at the camera, eyebrows raised",
    "shrugging with both palms up, a doubtful half-smile",
    "holding up an old glass soda bottle and looking at it suspiciously",
    "arms crossed, one eyebrow raised, skeptical",
)


def pose_jobs(meta):
    """{key: prompt} for the host's still poses (same face, clothes and set as his pack)."""
    return {f"ff_host_{meta['name'].lower()}_pose_{i + 1}":
            f"The man from the reference pictures, {meta['look']}, {meta['set']}. Medium shot from the chest up, he is {pose}, "
            f"centred framing, the microphone at the lower edge of the frame. {LOOK}"
            for i, pose in enumerate(POSES)}


refs = _ph.refs            # unique reference file names for Flow's picker


def shows_host(prompt, meta=None):
    """Only an explicit {host} (or his name) puts the host in a picture: food stories are full of other men and women."""
    p = f" {str(prompt).lower()} "
    name = str((meta or THEO).get("name", "")).lower()
    return "{host}" in p or (bool(name) and f" {name} " in p)


def expand(prompt, meta):
    p = str(prompt or "").strip()
    return p.replace("{host}", meta["look"]) if "{host}" in p else p
