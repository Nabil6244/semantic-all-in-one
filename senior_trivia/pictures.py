"""Flow pictures and host clips for Senior Trivia, through the Prepper Host Flow session (same engine, same library
out/prepper_host/library, keys prefixed st_ so repeated prompts cost nothing). Never raises for Flow trouble: what could
not be made is listed, and the renderer shows a text-only card (pictures) or the line over a scene picture (host clips)."""
import hashlib

from prepper_host import flow
from prepper_host import flowvoice as fv
from prepper_host import host as ph_host

from senior_trivia import host as st_host

STYLE = ("warm painted vintage Americana illustration, soft gouache and oil-painting look, golden light, gentle colours, "
         "16:9, no text, no letters, no logos, no real famous people")
ITEM_STYLE = "realistic studio product photo, the single object alone, centred, plain light-grey background, soft shadow, no text"


def key_of(prompt):
    return "st_" + hashlib.sha1(str(prompt).encode()).hexdigest()[:12]


def prompt_for(row, field):
    p = str(row.get(field) or "").strip()
    if not p:
        return ""
    return f"{p}. {ITEM_STYLE}" if row["type"] == "item" else f"{p}. {STYLE}"


def jobs(rows):
    """{key: full prompt} for every picture the show needs (question, fact, item, host-fallback, intro, outro)."""
    out = {}
    for r in rows:
        if r["type"] == "thumbnail":
            continue
        for field in ("picture", "fact_picture"):
            p = prompt_for(r, field)
            if p:
                out[key_of(p)] = p
    return out


def picture_keys(row):
    return (key_of(prompt_for(row, "picture")) if row.get("picture") else None,
            key_of(prompt_for(row, "fact_picture")) if row.get("fact_picture") else None)


def have_all(keys):
    return {k: flow.have(k) for k in keys if flow.have(k)}


def make(rows, use_flow=True, log=print, cancel=None):
    """-> {key: png path} for every picture in the library now (made what was missing when use_flow)."""
    need = jobs(rows)
    missing = {k: p for k, p in need.items() if not flow.have(k)}
    log(f"senior trivia: {len(need)} picture(s), {len(need) - len(missing)} already made, {len(missing)} to make")
    if missing and use_flow and not (cancel and cancel()):
        try:
            with flow.Session(log=log) as fs:
                fs.pictures(missing, cancel=cancel)
        except Exception as e:  # noqa: BLE001 - missing pictures become text-only cards
            log(f"senior trivia: Flow trouble ({type(e).__name__}: {e}); missing pictures show as text cards")
    return have_all(need)


# ------------------------------------------------------------------ host clips
def clip_key(meta, line):
    return fv.clip_key(meta, line)


def host_clips(rows, meta, use_flow=True, log=print, cancel=None):
    """One Flow talking clip per host row (his own voice in the clip). -> {row index: mp4 path} for the clips that exist."""
    lines = {i: r["line"] for i, r in enumerate(rows) if r["type"] == "host" and r["line"]}
    if not lines:
        return {}
    if use_flow and not (cancel and cancel()):
        pack = st_host.pack_jobs(meta)
        try:
            with flow.Session(log=log) as fs:
                if pack:
                    log(f"senior trivia: making {meta['name']}'s reference pictures (once)")
                    meta.update(st_host.save_pack(meta, fs.pictures(pack, cancel=cancel)))
                missing = {clip_key(meta, l): fv.clip_prompt(meta, l) for l in lines.values() if not flow.have(clip_key(meta, l), "mp4")}
                if missing and meta.get("portrait"):
                    log(f"senior trivia: Flow is making {len(missing)} host clip(s) (about {len(missing) * flow.CLIP_CREDITS} credits)")
                    fs.clips(missing, refs=ph_host.refs(meta), cancel=cancel, voice=fv.flow_voice(meta))
        except Exception as e:  # noqa: BLE001 - a missing clip = his line over a scene picture
            log(f"senior trivia: Flow trouble with host clips ({type(e).__name__}: {e})")
    got = {i: flow.have(clip_key(meta, l), "mp4") for i, l in lines.items()}
    got = {i: p for i, p in got.items() if p}
    if len(got) < len(lines):
        log(f"senior trivia: {len(lines) - len(got)} host line(s) have no clip yet; they play over a scene picture")
    return got
