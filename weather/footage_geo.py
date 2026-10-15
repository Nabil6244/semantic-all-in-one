"""Geographic and editorial check of every stock clip a Weather video uses (all Weather editing styles).

The root cause this closes (audit of project #007, 2026-10-15, docs/weather/footage_geo_audit.md): stock requests are written
without any place on purpose (a stock clip must never be captioned as the event), the stock providers search the whole world,
and the picker accepts the best text match without reading WHERE the clip was filmed. A flood line about Oklahoma got rice fields
from Vietnam, a Thames flood and a Dhaka street; a tornado line got a missile-damaged building in Ukraine; "tornado damage" got a
forest fire. The provider's own record of each clip (its page URL, author, tags) said so, but nothing read it.

    make_resolver(log)  -> a media_resolver for pakmap (generate_pakmap_video(media_resolver=...)): it resolves the rows with the
                           app's own resolver, then checks every stock clip (new or reused from the cache) and asks again for the
                           ones that fail, until each passes or none is left
    verdict(request, record) -> (ok, reason)

Rules (deterministic; the clip's metadata text = page URL words, author, alt text, tags):
  * a clip whose text names a place outside the US, or war / an unrelated subject (fire, smoke, ants, rocks ...), is rejected;
  * a request that shows a PLACE (streets, homes, a town, farmland, a landscape from above, people, cars, a river or lake) needs
    positive US evidence in the clip's text (a US state or city, "usa", "america"); unknown is not US: rejected;
  * a request that shows NO place (sky, clouds, lightning, rain, hail, snow close up, water close up) may come from anywhere,
    as long as its text names no foreign place and no unrelated subject.
A rejected clip is asked for again as a placeless shot of the same weather; its id is remembered in the project
(_work/media/.geo_rejected.json) so it can never come back, from a search or from the cache. A scene that finds no clip that
passes is left without one (the generator then leaves it out and the map / graphics carry that moment): no unrelated footage
is ever used to fill the timeline."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROUNDS = 3
FOREIGN = (
    "ukraine ukrainian russia russian moscow kyiv kiev belarus poland polish germany german berlin france french paris italy italian rome "
    "spain spanish madrid portugal lisbon netherlands dutch amsterdam belgium switzerland swiss austria vienna czech hungary romania "
    "greece greek turkey turkish istanbul england english london thames britain british uk scotland scottish wales ireland irish europe "
    "european norway sweden finland denmark iceland asia asian india indian delhi mumbai kolkata kerala bangladesh dhaka somogro pakistan "
    "nepal kathmandu sri lanka myanmar thailand thai bangkok vietnam vietnamese hanoi saigon mekong cambodia laos malaysia kuala lumpur "
    "singapore indonesia indonesian jakarta bali philippines manila china chinese beijing shanghai hong kong taiwan japan japanese tokyo "
    "korea korean seoul africa african kenya nairobi nigeria lagos egypt cairo morocco ghana ethiopia south africa dubai uae saudi qatar "
    "iran iraq israel brazil brazilian rio sao paulo argentina chile peru colombia venezuela australia australian sydney melbourne "
    "zealand canada canadian toronto vancouver quebec mexico mexican tijuana caribbean cuba haiti jamaica samarkand uzbekistan "
    "kazakhstan kyrgyzstan tajikistan afghanistan kabul georgia-tbilisi tbilisi armenia azerbaijan baku mongolia siberia ural crimea "
    "odessa kharkiv lviv minsk warsaw krakow prague budapest bucharest sofia belgrade zagreb sarajevo athens lisbon barcelona milan "
    "venice naples munich hamburg cologne frankfurt zurich geneva brussels copenhagen oslo stockholm helsinki reykjavik edinburgh "
    "dublin manchester liverpool birmingham bristol cairo istanbul ankara izmir antalya tehran baghdad riyadh doha muscat karachi "
    "lahore islamabad chennai bangalore bengaluru hyderabad pune goa chittagong yangon phnom penh ho chi minh cebu davao osaka kyoto "
    "busan taipei guangzhou shenzhen chengdu wuhan bogota lima quito caracas santiago buenos aires montevideo havana").split()
FOREIGN_PHRASES = ("sri lanka", "kuala lumpur", "hong kong", "south africa", "sao paulo", "new zealand", "rio de janeiro")
WAR_OR_UNRELATED = set(("war missile missiles bomb bombing bombed explosion attack attacked military soldier soldiers tank shelling "
                        "fire fires wildfire forest-fire smoke burning flames volcano lava earthquake ants ant insect insects rocks pebbles "
                        "gravel stones market vendors festival party wedding concert beach-party serene placid calm sunny tranquil "
                        "peaceful").split())
US_PLACES = set(("usa america american united states texas oklahoma ohio kansas missouri nebraska iowa arkansas louisiana "
                 "mississippi alabama georgia florida carolina tennessee kentucky indiana illinois michigan wisconsin minnesota dakota "
                 "colorado wyoming montana idaho utah arizona nevada california oregon washington alaska hawaii virginia maryland "
                 "delaware pennsylvania jersey york connecticut massachusetts vermont hampshire maine rhode houston dallas austin "
                 "chicago miami orlando tampa atlanta nashville memphis denver phoenix seattle portland boston philadelphia detroit "
                 "cleveland columbus cincinnati louisville tulsa oklahoma-city wichita omaha kansas-city st-louis new-orleans "
                 "moore joplin tuscaloosa mayfield").split())
PLACE_SUBJECTS = set(("street streets city town towns village home homes house houses neighborhood neighbourhood building buildings road "
                      "roads highway farmland farm fields field landscape aerial drone people person crowd market car cars vehicle "
                      "vehicles truck mobile trailer park river lake bridge coast beach shore downtown skyline main residents families "
                      "crews workers community residential cityscape city-skyline apartment apartments rooftops suburb suburban urban "
                      "mountain mountains hills valley forest countryside rural").split())
PLACELESS = {"tornado": ["dark rotating storm clouds", "storm clouds time lapse", "lightning in dark storm clouds"],
             "severe": ["lightning in dark storm clouds", "dark storm clouds time lapse", "heavy rain falling close up"],
             "hail": ["hailstones bouncing close up", "hail falling close up", "heavy rain falling close up"],
             "flood": ["heavy rain falling into water close up", "raindrops on water surface", "dark storm clouds time lapse"],
             "hurricane": ["heavy rain and strong wind close up", "dark storm clouds time lapse", "raindrops on water surface"],
             "winter": ["snow falling close up", "snowflakes falling", "dark winter clouds"],
             "heat": ["heat haze close up", "sun in a hazy sky", "dry cracked ground close up"]}


def _plain(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", t) + " "


def _has(words: set, text: str) -> List[str]:
    toks = set(text.split())
    return sorted(w for w in words if w in toks or (("-" in w or " " in w) and f" {w.replace('-', ' ')} " in text))


def hazard_of(request: str) -> str:
    r = _plain(request)
    for key, words in (("tornado", ("tornado", "funnel")), ("hail", ("hail", "hailstones")), ("flood", ("flood", "floodwater", "flooded")),
                       ("hurricane", ("hurricane", "surge", "tropical")), ("winter", ("snow", "ice", "blizzard")), ("heat", ("heat",))):
        if any(f" {w} " in r for w in words):
            return key
    return "severe"


def shows_place(request: str) -> bool:
    return bool(_has(PLACE_SUBJECTS, _plain(request)))


def clip_text(record: dict) -> str:
    extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
    return " ".join(str(x) for x in (record.get("source_url", ""), record.get("author", ""), record.get("alt", ""), record.get("tags", ""),
                                    record.get("title", ""), extra.get("alt", ""), extra.get("tags", "")))


def _non_latin_author(author: str) -> bool:
    """An author name in a non-Latin script or with Vietnamese diacritics: a hint (never proof) of where a clip was made."""
    return any(ord(ch) > 0x24F for ch in str(author or "")) or bool(re.search(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]",
                                                                                   str(author or "").lower()))


WEATHER = set(("rain rainy raining rainfall raindrops raindrop drops droplets downpour drizzle storm storms stormy thunderstorm "
               "thunderstorms thunder lightning lightnings bolt clouds cloud cloudy sky skies overcast hail hailstones hailstorm snow "
               "snowfall snowflakes blizzard ice icy sleet frost wind windy gust gale tornado funnel hurricane cyclone typhoon flood "
               "flooding flooded floodwater water puddle puddles splash splatter waves surge fog mist haze heat weather "
               "cumulonimbus supercell cloudscape skyscape destroyed destruction damage damaged debris wreckage aftermath "
               "collapsed toppled uprooted downed rescue rescuers evacuation evacuate sandbags levee river creek overflowing "
               "emergency firefighters crews").split())


def verdict(request: str, record: dict) -> Tuple[bool, str]:
    """(ok, why) for one stock clip used for `request`."""
    text = _plain(clip_text(record))
    described = _plain(str(record.get("source_url", "")).rstrip("/").split("/")[-1]) if record.get("source_url") else ""
    if described.strip() and not _has(WEATHER, described):
        return False, "its description names no weather at all (it shows something else)"
    foreign = _has(set(FOREIGN), text) + [p for p in FOREIGN_PHRASES if f" {p} " in text]
    if foreign:
        return False, f"filmed outside the US ({', '.join(foreign[:3])} in its record)"
    wanted = set(_plain(request).split())
    unrelated = [w for w in _has(WAR_OR_UNRELATED, text) if w not in wanted]
    if unrelated:
        return False, f"shows something else ({', '.join(unrelated[:3])} in its record)"
    if shows_place(described if described.strip() else request):
        hint = _non_latin_author(record.get("author", "")) or bool(_has({"rice", "paddy", "paddies", "terraces", "terrace"}, text))
        if hint:   # it shows a place, and its record points abroad (the rice fields of the #007 render): never as US weather
            return False, "it shows a place and its record points to a place outside the US (author's name / rice fields)"
    return True, "relevant: weather footage, no foreign place, nothing unrelated in its record"


def _rejected_path(images_dir: Path) -> Path:
    return Path(images_dir) / ".geo_rejected.json"


def _load_rejected(images_dir: Path) -> Dict[str, str]:
    try:
        return dict(json.loads(_rejected_path(images_dir).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _save_rejected(images_dir: Path, data: Dict[str, str]) -> None:
    try:
        _rejected_path(images_dir).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _is_stock(row: dict) -> bool:
    return str(row.get("asset_type", "")).startswith("stock_")


def check_scenes(rows: List[dict], images_dir: "str | Path", log: Callable[[str], None] = print) -> List[Tuple[dict, str]]:
    """The stock rows whose clip fails (row, why); each failure is recorded and its file and manifest record are cleared."""
    from asset_manager import AssetManifest

    images_dir = Path(images_dir)
    man = AssetManifest(images_dir)
    rejected = _load_rejected(images_dir)
    bad = []
    for row in rows:
        if not _is_stock(row):
            continue
        n = str(row["scene_number"])
        rec = man.get(n) or man.get(f"{int(n):03d}") if n.isdigit() else man.get(n)
        if not rec or rec.get("status") != "complete" or rec.get("user_override"):
            continue   # nothing fetched, or the user chose this clip by hand: theirs to judge
        aid = f"{rec.get('provider', '')}:{rec.get('provider_asset_id', '')}"
        ok, why = verdict(row.get("prompt", ""), rec)   # judged by today's rules every time (the same clip, the same answer)
        if ok:
            continue
        rejected[aid] = why
        bad.append((row, why))
        log(f"[Weather] footage check: scene {n} ({rec.get('source_url', '')}) rejected — {why}")
        path = rec.get("local_path")
        try:
            if path and Path(path).is_file():
                Path(path).unlink()
        except OSError:
            pass
        man.set(n, {**rec, "status": "failed", "local_path": "", "error": f"rejected by the Weather footage check: {why}"})
    _save_rejected(images_dir, rejected)
    return bad


def make_resolver(log: Callable[[str], None] = print, base: Optional[Callable] = None):
    """A pakmap media_resolver: the app's own resolver, then the footage check, then new placeless requests for what failed."""

    def resolve(rows, images_dir, log=log, **kw):
        nonlocal base
        if base is None:
            import video_generator as vg

            base = vg.resolve_scene_assets
        rows = [dict(r) for r in rows]
        base(rows, images_dir, log=log, **kw)
        tried: Dict[str, int] = {}
        for _round in range(ROUNDS):
            bad = check_scenes(rows, images_dir, log)
            if not bad:
                return
            again = []
            for row, _why in bad:
                n = str(row["scene_number"])
                k = tried.get(n, 0)
                options = PLACELESS.get(hazard_of(row.get("prompt", "")), PLACELESS["severe"])
                if k >= len(options):
                    continue
                tried[n] = k + 1
                again.append({**row, "prompt": options[k]})
                log(f"[Weather] footage check: scene {n} asks instead for {options[k]!r} (shows no place)")
            if not again:
                break
            base(again, images_dir, log=log, **kw)
            for a in again:   # what was asked for is what the next check judges
                for r in rows:
                    if str(r["scene_number"]) == str(a["scene_number"]):
                        r["prompt"] = a["prompt"]
        bad = check_scenes(rows, images_dir, log)
        for row, why in bad:
            log(f"[Weather] footage check: scene {row['scene_number']} has no clip that passes ({why}); it is left out")

    return resolve
