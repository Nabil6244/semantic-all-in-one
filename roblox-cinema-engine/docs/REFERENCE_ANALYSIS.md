# Reference analysis

**How this was done, honestly:** eight reference videos were analysed through vidIQ's automated video-watch tool. Claude did not watch them frame
by frame; these are patterns reported by that tool and then used as blueprints (adopt patterns, not a fixed copy of any video).

| Video | Why it was studied |
|---|---|
| Mitsi Studio - Vietnam War (Lm9OUWWw59Y), Blitzkrieg (eTLq7j7ZrYM), Gulf War (3LiVXSCIvtI) | documentary pacing, subtitles, chapter and date cards |
| 3/1 Marines Roblox Vietnam film (0b9I_MpHqSo) | block-world war staging, vehicles |
| banastic "I joined the Vietnam War on Roblox" (Y_l1nkd6w40) | comedy-pace cutting (2-4 s shots), crowds |
| W-A Vietnam War cinematic (mZFkN4ezYHo) | cinematic camera work, low tracking shots |
| The Last Guest, Roblox movie (1ZM6ztUlLWY) | acting, interiors, lighting |
| Kings and Generals - First Chechen War (xjIu9pkrIP4) | map storytelling: arrows, pins, unit routes |

## Patterns adopted
* R6-style rigid-limb block bodies with decal faces; toy-plastic dioramas, conical pines, blocky clouds -> `characters.mjs`, `world3d.js`.
* Tabletop relief maps with red arrows and pins -> `map3d.js`.
* Low tracking shots with vehicles, top-down tactical overviews, sweeping aerial follows -> `camera.mjs` (21 behaviours).
* Hard cuts on topic shifts, dissolves for time passing, black title cards -> `director.mjs` transitions + chapter cards.
* Golden-hour / cool blue night fog / desaturated overcast combat -> `look.js` presets.
* Yellow-white subtitles with the spoken word lit, lower-third place tags, date tiles -> `hud.js`.
* Shot length 2-4 s (comedy) to 3-6 s (documentary) -> 3.6-9.5 s here, with long shots split at sentence pauses.

## Not adopted
Gore, real insignia/flags, copyrighted maps, any footage or audio from the references.
