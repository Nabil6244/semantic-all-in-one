# iPhone Duo film: evidence register (Phase 2C, 2026-11-06)

Decisions applied: premium real-footage-first hybrid; incident evidence only from verified owners, original reports and credible hands-on
sources; source screenshots only from Apple official pages, iFixit originals and attributable reporting; rear camera = two rear cameras in one
module plus flash, model geometry still to be checked against Apple's picture.

**What was done:** web searches for source pages (no AI generation); two pages read in full as text (iFixit teardown, Gulf News fact-check);
local files checked. **Nothing downloaded** (no images, no video), no renderer or pipeline change, nothing committed.
Script and sentence numbers are those of `DIAGNOSTIC_DUO.md` (47 sentences).

## Status words (Phase 2C.1: six explicit statuses)
An asset is **approved only when it carries APPROVED_FOR_PRODUCTION**. Existing online, or being found, never approves anything.

| Status | Meaning | Who sets it |
|---|---|---|
| UNVERIFIED | A claim or source seen but not confirmed against the original | default |
| VERIFIED | The *claim or event* is confirmed by the original or by two independent credible sources (says nothing about reuse) | me, after reading the source |
| VISUAL_FOUND | A specific image/clip showing it exists at a known URL or local path (not downloaded unless stated) | me |
| RIGHTS_CLEARED | Reuse in a **monetised** film is permitted: written permission, an explicit licence, or a documented legal basis you accept | **you**, with the evidence recorded |
| APPROVED_FOR_PRODUCTION | VERIFIED + VISUAL_FOUND + RIGHTS_CLEARED + attribution text recorded + you signed off | **you** |
| MISSING | No genuine material found; stays missing, nothing substituted | me |

Old tags map as: READ/FOUND = progress on VERIFIED or VISUAL_FOUND only; LOCAL = VISUAL_FOUND (rights not cleared); the old "Rights" column
below is a description of who owns the material, **not** a clearance.

## Rights and verification policy (permission-first)

1. **Owner images and videos** (Reddit posts, X posts): explicit permission from the owner is required for any monetised production. Record the
   permission evidence (message, date, wording, the owner's handle) and the attribution the owner asked for. Without permission: text and a source
   link only; no image in the film.
2. **Press and publication screenshots**: prefer material that is explicitly licensed or authorised for reuse (a press kit, a stated licence,
   a written yes from the publisher). A limited editorial excerpt is **flagged for individual rights review**, one item at a time. Attribution alone
   is never treated as permission.
3. **Official Apple assets**: Apple's published terms are recorded below. Apple's website images are not assumed freely reusable.
4. **iFixit material**: the original source and its licensing status are recorded below; permission is sought where reuse is unclear.
5. **Third-party videos** (the Duo review on this Mac, YouTube): reference and timestamps only, until the creator permits reuse.
6. **Nothing is approved because it exists online.**

### Published terms recorded this phase (read as text; nothing downloaded)

| Owner | Page read | What it says | Effect on this film |
|---|---|---|---|
| Apple | https://www.apple.com/legal/intellectual-property/guidelinesfor3rdparties.html ("Guidelines for Using Apple Trademarks and Copyrights") | Covers use of Apple trademarks and images in promotional, advertising, instructional or reference materials. States Apple "does not support the use of ... images of Apple products by other parties in marketing, promotional or advertising materials" because it may imply endorsement; developers may show an image of an Apple product only to show compatibility, under conditions. Says "no other rights of any kind are granted". Commercial use of the Apple logo needs prior written consent | No blanket licence for newsroom or event images. A monetised review film using Apple imagery is not covered by these guidelines. Needs a rights review or Apple's written consent; **no Apple image or clip is RIGHTS_CLEARED**. Apple Newsroom has a "Media" section; its own terms were **not read** and must be before any use |
| iFixit | https://www.ifixit.com/Info/terms_of_use ("Right to Use iFixit Content") | Content is copyrighted. No copying, reproducing, publicly displaying or creating derivatives "except as expressly authorized ... or otherwise by iFixit in writing". iFixit grants a limited, revocable licence to display content **through the means it provides, e.g. embed codes**, keeping copyright notices. Anything else, including AI/ML training, needs written permission. Points to a separate "Content Licensing Policy" (**not read**). User submissions: the creators keep copyright; iFixit gets a broad licence; users must reuse submissions only non-commercially under CC BY-NC-SA | Teardown text, photos, video and the Lumafield CT scan: **permission needed for any copy in a monetised film**; embedding is the only authorised display found. Reddit images iFixit shows come from owners and are not iFixit's to license. Next step: read the Content Licensing Policy and ask iFixit in writing |
| Owners (Reddit/X) | n/a | Copyright stays with the poster | Permission-first rule applies |
| Gulf News, MacRumors, PhoneArena, Macworld, others | publisher sites | Not read for licensing terms | Rights review per item; attribution is not permission |
| Sketchfab models | `*.LICENSE.txt` in `whatif-engine/assets/models/phones/` | Pikkme: CC BY 4.0 (credit line recorded); extraakash: Sketchfab Standard (video use allowed, do not share the file); zhe_kan: CC BY-NC-SA 4.0 non-commercial | The 3D models are the only assets with a recorded licence. Their *accuracy* is still unverified (see section 6) |

## Status ledger (replaces the old per-row tags; see sections 1-5 for the detail)

| Item | UNVERIFIED | VERIFIED (claim) | VISUAL_FOUND | RIGHTS_CLEARED | APPROVED_FOR_PRODUCTION | MISSING |
|---|---|---|---|---|---|---|
| #12 Melbourne cracked screen | | yes (several outlets; iFixit and Gulf News read) | only via press reproductions; **original Reddit post not found** | no (owner permission not asked) | no | original owner image |
| #12 alt, leftyhyzer16 post (iFixit) | | partly (shown by iFixit as an owner report) | yes, inside the iFixit page | no | no | |
| #12 alt, Dallas owner | yes (single outlet via Gulf News) | | no | no | no | image |
| #13 hinge will not open/close | | text reports only | no | no | no | **MISSING** |
| #14 Australian owner | | claim yes | as #12 | no | no | as #12 |
| #1-2, 6-8 Apple specs/intro | battery, 120 Hz, 3,000 nits, 35%, 44/31 h | display sizes, A20 Pro, thinnest when open, Oct 23, passport-size closed (Apple press release read) | yes (Newsroom page; local event clips) | **no** (Apple terms above) | no | |
| #10 price | ladder 2,199/2,599/3,199 | $1,999 (Macworld, Apple event slide in local clips) | yes (local slide) | no | no | |
| #9 Pencil Oct 26 | yes | | | | | no source |
| #19-24 Apple response | Oct 23 guide, Nov 2 guidance | Oct 26 statement (TweakTown, Gulf News) | no screenshot chosen | no | no | Apple support page for the guide |
| #26-27 iFixit theory and powder test | | **yes (page read)** | yes (iFixit page, embedded video, CT scan) | **no (permission needed)** | no | |
| #30-31 repair costs | numbers not compared | | page found | no | no | |
| #34 5/10 score | | yes (iFixit, TechRadar) | | no | no | |
| #35-36 reviewers, battery | outlet unnamed for 25% claim | partly | | no | no | |
| #38 cameras | low-light, selfie detail | no telephoto, 48 MP + 48 MP (Engadget and others) | | no | no | |
| #40 Macworld verdict | wording not compared | 3.5/5 (search summary) | review page | no | no | |
| #42 supply date | **conflict: Jan 22 (script) vs Jan 25 (Macworld blog)** | | | | | |
| Local Apple Event / Iphone 18 clips | which clips are the Duo, per-clip times | | yes (LOCAL) | **no** (Apple terms; clip origin not recorded) | no | clip log |
| Local Duo review video | | | yes (LOCAL, timestamps in section 5) | **no** (third-party creator) | no | permission |
| 3D models | geometry accuracy | | yes (LOCAL) | licence recorded (see terms table); NC model barred from monetised use | no | verified model |

**Result: zero assets are RIGHTS_CLEARED or APPROVED_FOR_PRODUCTION.** The film can currently carry only: original graphics we draw ourselves
(figures, dates, labelled text, the 3D models under their licences) and text with source names. Every real photo or clip still needs permission.

## 1. Incident evidence (the part that was missing)

| # | Needed visual | Best source found | URL | Status | Rights | Caveat |
|---|---|---|---|---|---|---|
| 12 | Cracked inner screen along the fold, from a real owner | Melbourne owner's Reddit post (u/Midnight_Slump, r/iPhoneDuo), ~6 h, <20 openings; first reported by MacRumors, confirmed genuine by PhoneArena; Reddit moderators checked extra photos and Apple paperwork | Reporting: https://gulfnews.com/technology/are-iphone-duo-screens-really-cracking-fake-photos-cloud-crackgate-as-real-cases-emerge-1.500723812 (READ). PhoneArena: https://www.phonearena.com/news/iphone-duo-screen-cracks-hours-after-launch-and-the-internet-cries-fake_id184268 (FOUND; page blocks automated reading). Original Reddit post URL **not found**. | Evidence exists, original not located | owner | Verification covers the phone and its replacement, not the cause. Locate the Reddit original, or ask the owner |
| 12 (alt) | A second verified crack | Reddit user leftyhyzer16, "folded it 4 times... loud pop", embedded in iFixit's teardown as its own evidence | https://www.ifixit.com/News/119895/iphone-duo-teardown (READ) | Evidence exists, embedded in a credible source | owner (image), press (page) | iFixit presents it as an owner report, not as verified |
| 12 (alt) | Dallas owner, screen broke during setup after about four folds | Reported by tech-ish, cited by Gulf News | same Gulf News URL (READ) | Report only, no image located | owner | Do not use until a picture and its origin are found |
| 13 | Hinge that will not open or close fully, strange noises | No clip or photo found of a hinge failing to move | | **MISSING** | | Search found text reports only (stiff hinge, crunch). Keep missing. iFixit's dust test (see #27) shows the crunch, but it is a lab demonstration, not an owner's failure |
| 14 | The Australian owner | Same Melbourne case as #12; the narration claim "six hours, fewer than 20 openings, replaced on the spot" matches Gulf News (READ), which cites Tom's Guide for the on-the-spot replacement | Gulf News URL above | Claim verified in text; picture as #12 | owner | Same original-post gap |
| 2 | "Reports began soon after Oct 23" | Gulf News: photos spread within hours of the Oct 23 sale | Gulf News URL (READ) | Verified in text | press | |

**Fakes warning (important for a news film):** Gulf News (READ) reports an AI-generated "three months of use" image posted Sept 10 (Lead Stories: 99.9%
likely machine-made), one photo of a cracked phone in a Chinese Apple Store recycled by at least four posts, a crack wallpaper joke, and one photo
with an X note saying it was altered with AI. Reddit moderators called one widely shared photo collection "unverified" (Yahoo Tech, via Gulf News).
**Rule for the planner:** an incident image is only allowed with its original post or a named outlet that verified it; images only seen as reposts
stay MISSING. The film should say "reported" and show the source name.

## 2. Official Apple sources

| # | Needed visual | Source | URL | Status | Rights | Caveat |
|---|---|---|---|---|---|---|
| 1, 2, 6-8 | Product intro, 5.4 in / 7.6 in, A20 Pro, thermal and battery figures, Apple's own words | Apple Newsroom, "Apple unveils iPhone Duo" (Sept 9, 2026) | https://www.apple.com/newsroom/2026/09/apple-unveils-iphone-duo/ | FOUND | Apple (promotional; check Apple's media-use guidelines) | Search summary confirms 5.4 / 7.6 in, A20 Pro, iOS 27, Oct 23 launch. The 120 Hz / 3,000 nits / 35% / 44 h / 31 h figures were **not confirmed** this phase |
| 2, 19 | Launch date Oct 23 | Apple Newsroom, "Open up to new possibilities..." and "iPhone Duo arrives at Apple Store locations worldwide" | https://www.apple.com/newsroom/2026/10/open-up-to-new-possibilities-with-iphone-duo/ and https://www.apple.com/newsroom/2026/10/iphone-duo-arrives-at-apple-store-locations-worldwide/ | FOUND | Apple | Search says Oct 23 US launch, other countries Oct 30 |
| 10 | Price $1,999 | Macworld guide (starts $1,999) and the Apple event slide in the local clips | https://www.macworld.com/article/2629813/iphone-duo-folding-design-guide-problems-price-specs.html (FOUND) | FOUND | press | The ladder 2,199 / 2,599 / 3,199 was not confirmed. Apple's own US price page was not located; Apple AU page shows A$3,499 |
| 9 | Pencil support arriving Oct 26 | none located | | **Unverified** | | Do not show a date for this until a source is found |
| 19-21, 22, 24 | Apple's hinge troubleshooting guide (Oct 23), Oct 26 acknowledgement, Nov 2 guidance to stores, "no software fix", no formal programme | Apple's statement ("aware of an issue impacting the inner display on a small number of iPhone Duo units", contact AppleCare, AppleCare+ not required) | Reported by TweakTown https://www.tweaktown.com/news/114315/apple-confirms-iphone-duo-inner-screen-cracking-issue-within-days-of-global-launch/index.html , Gulf News https://gulfnews.com/technology/iphone-duo-crackgate-apple-breaks-silence-on-screen-cracks-offers-replacements-1.500724698 , MacRumors (via search) | FOUND (Oct 26 statement) | press | The Apple support page for the troubleshooting guide was **not found**. The Nov 2 "reportedly" item (script) was **not found** in any source this phase. Gulf News' Oct 26 12:24 fact-check says Apple had made no public statement, so the statement came later that day |
| 4, 17 | "Apple has now responded" | same as above | | FOUND | | |

## 3. iFixit originals

| # | Needed visual | Source | URL | Status | Rights | Caveat |
|---|---|---|---|---|---|---|
| 26, 27 | Teardown, hinge support bar not dropping far enough, CT scan, fluorescent-powder test | iFixit, "iPhone Duo Teardown: The Most Repairable Foldable Has a Huge Screen Problem" (Oct 25, 2026) | https://www.ifixit.com/News/119895/iphone-duo-teardown | **READ** | iFixit; **licence not stated on the page text I read**; the CT scan is credited to Lumafield | Confirms: breaks cluster where the flex-cable gap meets the central support; support bar theory; powder reached the hinge and it crunched; iFixit says it is a hypothesis. Matches the script's "theory" wording |
| 30, 31 | Repair costs (cover layer $49 / $19, full inner display $999 / $99) | iFixit, "How the iPhone Duo's Crazy Repair Prices Compare" | https://www.ifixit.com/News/119797/how-the-iphone-duos-crazy-repair-prices-compare | FOUND | iFixit | Numbers **not yet checked** against the page |
| 34 | Provisional 5/10 repairability, highest for a foldable | iFixit teardown (above); TechRadar and iPhone in Canada also report it | https://www.techradar.com/phones/iphone/ifixit-tears-down-the-iphone-duo-and-awards-it-the-highest-repair-score-yet-for-a-foldable-but-replacing-the-inner-screen-and-hinge-takes-a-lot-of-work (FOUND) | FOUND | | "Removable outer display" confirmed in the search summary; "electrically released batteries" not confirmed |
| 27 | A real test shown on screen | iFixit teardown video (embedded on the page) | same iFixit URL | Exists on the page; not located as a downloadable file | iFixit | Use needs iFixit's permission or a short attributed excerpt; not decided |

## 4. Reviews and attributable reporting

| # | Needed visual | Source | URL | Status | Rights | Caveat |
|---|---|---|---|---|---|---|
| 40 | Macworld's verdict (3.5/5, "exciting but not one we can recommend yet") | Macworld review | https://www.macworld.com/article/3272761/iphone-duo-review.html | FOUND | Macworld | Wording of the script vs the page not compared. Search summary says 3.5 out of 5 |
| 35 | "Reviewers liked the nano-texture display and performance" | Macworld roundup | https://www.macworld.com/article/3266294/iphone-duo-review-roundup-a-little-weird-a-lot-of-fun-and-a-breath-of-fresh-air.html | FOUND | Macworld | |
| 36 | "About 25% left after a mixed-use day" (one outlet) / "comfortably lasted a busy day" (another) | **not located** | | **Unverified** | | The outlets are unnamed in the script. Name them before using a card |
| 38 | Cameras: no telephoto, main camera behind 18 Pro in low light, under-display selfie weak | Photoworkout, Engadget, Gruber (Daring Fireball), Notebookcheck | e.g. https://engadget.com/2254121/the-iphone-duo-lacks-variable-aperture-and-a-dedicated-telephoto-camera/ (FOUND) | FOUND (no telephoto; 48 MP Fusion main + 48 MP ultra-wide) | press | "Low light" and "poor detail" claims not located |
| 42 | Supply: Jan 22, 2027 quote for 256 GB on launch day | Macworld pre-order live blog says **Jan 25, 2027** (later) | https://www.macworld.com/article/3262078/iphone-duo-pre-order-live-blog-how-quickly-will-apples-folding-phone-sell-out.html | **Discrepancy** | | Script says Jan 22 on launch day; source seen says Jan 25. Discrepancy recorded; script not changed |
| 35, durability | JerryRigEverything-style durability test (named in Gulf News as the strongest case against the Duo) | Gulf News, truncated in my read | Gulf News URL | Partly read | | Do not cite until the paragraph is read in full |

## 5. Real footage already on this Mac

| Use | File | Timestamp | Content | Rights | Status |
|---|---|---|---|---|---|
| Product hero, hook, #1, #23, #37, #39 | `~/Downloads/Apple/Apple Event/1105-1..11.mp4` (11 clips) | per-clip times not logged | Official event footage incl. a "$1999 256GB" slide (which clip is not logged) | Apple event material; origin of these clips (downloaded from where) is not recorded | LOCAL, needs a clip-by-clip log |
| Duo moods and shots | `~/Downloads/Apple/Iphone 18/` (13 clips) | not logged | Some Duo, some mood shots | as above | LOCAL; must be checked that each clip is the Duo, not an 18 Pro |
| Third-party hands-on and lab evidence | `~/Downloads/iPhone Duo Review_ After 3,000 Folds, Here's What We Found.mp4` (26:26) | crease 02:36-03:28; crease chart 03:29-04:04; CT scan and 3D hinge 04:59-05:55; pencil scratch 08:36-09:20; durability 10:39-11:00; apps 12:58-17:48; split screen 16:29-17:10; battery 19:42-20:33; cameras 20:37-22:16; verdict 24:15-24:45 | Third-party review. It says the crease is almost invisible and shows **no** crack or hinge-failure footage | **Not cleared**: another creator's video | LOCAL; reference only until permission; **does not satisfy #12-14** |
| 3D hero | `whatif-engine/assets/models/phones/iphone_duo_fold_star_white.glb` and `..._night_sky.glb` (extraakash, Sketchfab Standard, git-ignored) | open/close animation, t=0 open, ~1.5 s nearly closed | Matches Apple's open (1.41:1) and closed (0.70:1) proportions | Sketchfab Standard (video use allowed, do not share the file) | LOCAL; label as an illustrative model |
| 3D, credited | `iphone_duo.glb` (Pikkme, CC BY 4.0) | | Multi-device scene, not a single phone | Credit line in `iphone_duo.LICENSE.txt` | LOCAL; extraction needed |
| 3D, non-commercial | `iphone_duo_nc.glb` (zhe_kan, CC BY-NC-SA) | | Not for monetised videos | | LOCAL; keep out of any monetised film |

## 6. Rear camera (decision applied)

Your decision: two rear cameras in one module, plus flash.
- Consistent with: Apple's lineup per search summaries (48 MP Fusion Main + 48 MP Ultra Wide, no telephoto, from several outlets) and the three models
  (a pill-shaped module with two stacked lenses and sensor dots).
- **Not yet verified:** (a) Apple's own back-view picture compared with the model (the Newsroom page is found, the image is not compared);
  (b) the flash position on each model; (c) the Star White back reads dark in my lighting.
- `DESIGN.md` (docs/product_trailer/refs/iphone_duo/DESIGN.md) corrected 2026-11-06: the closed phone is **portrait**, not "short and wide". Supported by Apple's Sept 9 press release ("similar in size to a passport", 5.4 in outer display = 90% of iPhone 18 Pro's screen area) and by Apple event frames in the local clips (portrait slab, punch-hole top right). The "one round camera bump" line is marked UNRESOLVED, not replaced. The open-panel ratio (old text "almost square") is flagged for re-check, not changed.

## 7. Sentence-by-sentence summary

| Sentence | Need | State |
|---|---|---|
| 1-5 hook, launch, response | Apple Newsroom clip or the local event footage; 3D hero only as a fallback, labelled | sources FOUND; local clips not logged |
| 6-8 specs | labelled figures | partly verified (display sizes, chip); battery/brightness/thermal figures unverified |
| 9 | Pencil Oct 26 | unverified |
| 10 | price | $1,999 FOUND; ladder unverified |
| 12 | cracked fold | evidence exists (Melbourne case); the original post must be located |
| 13 | hinge not closing | **MISSING** |
| 14 | Australian owner | text verified; picture as 12 |
| 17-24 | Apple responses and dates | Oct 26 FOUND; Oct 23 guide page not found; Nov 2 not found |
| 26-27 | iFixit theory and powder test | **READ**, matches script |
| 30-31 | repair costs | iFixit page FOUND, numbers unchecked |
| 34 | 5/10 score | FOUND |
| 35-36 | reviewers, battery | partly; outlet for the 25% claim unnamed |
| 38 | camera compromises | partly |
| 40 | Macworld | FOUND (3.5/5) |
| 42 | supply date | discrepancy (22 vs 25 Jan) |

**Proves the material can be sourced?** Partly. The Apple, iFixit and reporting sources exist and match the narration (strongest: iFixit, READ).
The Melbourne crack case is real and widely corroborated, but its original image is not located and rights are not cleared. The hinge-failure
visual (#13) does not exist in any source found. About five script claims are unverified or conflicting (listed above).

## 8. Next steps for your decision (nothing started)
1. Locate the original Reddit post for the Melbourne case (and iFixit's embedded leftyhyzer16 post); decide: ask the owner, or use a short
   attributed screenshot, or leave as text.
2. Read in full: Apple Newsroom Sept 9 (specs), the iFixit repair-price article, the Macworld review, the Gulf News tester paragraph.
3. Decide a rights policy for press and owner images (permission, short attributed excerpt, or link/text only).
4. Log each local Apple clip (duration, what it shows, is it the Duo) so they can be matched to sentences.
5. Settle three script claims before use: the Nov 2 guidance, the Pencil date, the Jan 22 date.
6. Compare the model's back with Apple's picture (camera layout, flash), then correct `DESIGN.md`.

---------------------------------------------------------------------------------------------------------------------------------

# Phase 2C.2 additions (2026-11-06): rights terms read, script fact-check

Still no asset is RIGHTS_CLEARED or APPROVED_FOR_PRODUCTION. Nothing downloaded; two reports and a draft were written (MODEL_VERIFICATION_DUO.md,
PERMISSION_DRAFTS_DUO.md).

## A. Terms read this phase

| Owner | Page | Exact points | Effect |
|---|---|---|---|
| iFixit | https://www.ifixit.com/Info/Licensing | "All iFixit content is licensed under the Creative Commons BY-NC-SA 3.0 license" (Attribution, **Noncommercial**, ShareAlike). "Using our data to train a machine learning or AI model is a violation." "We grant usage licenses to certain commercial entities ... contact us ... legal@ifixit.com." Press: "Please see the Media Information page." | Monetised film = commercial = **not covered**; written permission needed |
| iFixit | https://www.ifixit.com/Info/Media | "If you'd like to use any of our photos for a story, please email press@ifixit.com. Our content is licensed under the Creative Commons BY-NC-SA 3.0 license, which does not allow it to be used for commercial purposes." | Photos: ask press@ |
| iFixit | https://www.ifixit.com/Info/Teardown_FAQ | "Members of the press may use three teardown photos per story with attribution without specific permission. More generous press licensing is easily obtainable by emailing us." Commercial use of a user teardown: contact a named address | Whether a monetised YouTube film is "press" is not stated. Unresolved; the request asks |
| iFixit | https://www.ifixit.com/Info/terms_of_use | display only "using the means provided ... (e.g. ... embed codes)"; other copying needs written permission | Embed is the only pre-authorised display |
| Apple | https://www.apple.com/legal/internet-services/terms/site.html ("Terms of Use" for apple.com) | Site content "is owned, controlled or licensed by or to Apple ... no part of the Site and no Content may be copied, reproduced, republished, uploaded, posted, publicly displayed ... for any commercial enterprise, without Apple's express prior written consent." Apple allows use of "information ... (such as data sheets, knowledge base articles, and similar materials) purposely made available ... for downloading" under conditions I did not read to the end | Newsroom and product-page images: **written consent needed** for a commercial film |
| Apple Newsroom | https://www.apple.com/newsroom/ and the Sept 9 release | The release page offers its images as downloadable zip files, but **no Newsroom-specific media or usage terms were found** (the only press terms found, Apple TV Press, are for a different site and say use is for editorial or promotional purposes of a production's release, other use needs Apple's written consent). Contact named there: media.help@apple.com (Apple TV Press page) | **Unresolved**: downloadable is not licensed; ask Apple before any image use |
| Apple | https://www.apple.com/legal/intellectual-property/guidelinesfor3rdparties.html | as recorded in Phase 2C.1 (no blanket licence; endorsement concern) | unchanged |
| Sketchfab / extraakash | model pages and https://sketchfab.com/licenses | "License: Free Standard"; "Non-official, fan-made visualization"; "NoAI". Editorial licences bar commercial use; Standard does not carry that bar but forbids standalone redistribution and any violation of trademarks and other third-party IP | label verified; **monetised use not verified** (see MODEL_VERIFICATION_DUO.md) |

## B. Original incident source (Melbourne owner)

- Reddit blocks automated access (403 on curl; the search tool refuses reddit.com), so the original post was **not seen**.
- The handle u/Midnight_Slump (r/iPhoneDuo) appears in search summaries based on PhoneArena and others. Gulf News (read) does not give it. Status:
  **handle reported, not confirmed**. Details agree across outlets (about six hours, fewer than 20 openings, replaced); the outcome and cost differ.
- Public contact route if confirmed: a Reddit private message to that account. No other contact was sought. No request drafted (see PERMISSION_DRAFTS_DUO.md).
- MacRumors is cited by others as the first outlet, but no MacRumors article on the Melbourne case was found (not in its Duo roundup page).

## C. Script fact-check

| Claim in script | Finding | Source and passage | Status |
|---|---|---|---|
| Nov 2: Apple "reportedly sent diagnostic guidance to Apple Stores and authorized service providers" | The memo was reported on **Oct 30** ("in a memo shared with Apple Stores and Apple Authorized Service Providers this week"). No Nov 2 date found | MacRumors, Oct 30, 2026, https://www.macrumors.com/2026/10/30/apple-alerts-stores-to-iphone-duo-display-cracking/ : "Apple provided technicians with guidance on how to diagnose and address the iPhone Duo's inner display cracking issue ... inspect the iPhone Duo and repair or replace it in accordance with their standard procedures." | **Discrepancy recorded: the source says Oct 30; the script says Nov 2. Script not changed** |
| Oct 26: Apple acknowledged an inner display issue, contact AppleCare | Confirmed | MacRumors (same page): "'We are aware of an issue impacting the inner display on a small number of iPhone Duo units,' said Apple, in a statement shared with MacRumors. If users experience issues ... they should contact AppleCare for a replacement." and "a public statement on Monday" (Oct 26). Also TweakTown | **VERIFIED** (the replacement wording is MacRumors'; Apple's quoted words end at "units") |
| Oct 23: Apple "published a hinge troubleshooting guide" on launch day | Macworld says the support page "iPhone Duo Troubleshooting Hinge Issues" "was published Sunday" (Oct 25). Another summary said launch day, unattributed | Macworld, https://macworld.com/article/3269038/iphone-duo-hinge-issue-whats-wrong-with-apples-folding-phone-and-how-to-fix-it.html (page dated 2026-10-25 in its metadata): "a support page titled 'iPhone Duo Troubleshooting Hinge Issues' was published Sunday to offer 'steps to help resolve issues,' including: Device won't open or close completely; Unexpected noise ...; Loose hinge; Bent or broken hinge; Enclosure damage that affects hinge operation" | **Discrepancy recorded: the one dated source says Oct 25; the script says Oct 23. Script not changed.** Apple's own support page not opened |
| "No software fix for the hinge problems" | One report; Apple's page not confirmed | search summary of Apple's article via press (iTechify): no diagnostics or software remedies for hinge issues | **UNVERIFIED** until Apple's page is read |
| Oct 26: Apple Pencil arrived with an update | Reported: iOS 27.2 "out Monday" (Oct 26) adds Apple Pencil (USB-C) support; Apple's Sept release said "Later this year, iPhone Duo will support Apple Pencil with USB-C" | Apple Newsroom Sept 9 (read) and reports dated Oct 21 and Oct 26 (9to5Mac Oct 21 headline: "iPhone Duo adding Apple Pencil support next week with iOS 27.2"; other outlets Oct 26) | **VERIFIED by secondary sources** (the Oct 26 pages not read in full) |
| Jan 22, 2027 for 256 GB "on launch day" | **No source found for Jan 22.** Sources give **Jan 25** (US estimate, soon after pre-orders opened Oct 16; some buyers saw Jan 29). One report says some pre-orders later moved to November | Macworld pre-order live blog; iThinkDiff "iPhone Duo Delivery Slides to January After Pre-Order Rush" (search summaries) | **Discrepancy recorded: no source for Jan 22; sources say Jan 25 after pre-orders opened. Script not changed** |
| 120 Hz, 3,000 nits | Confirmed | Apple Newsroom (read): "ProMotion, Always On, and 3000 nits of peak outdoor brightness"; Tech Specs (read): "up to 120Hz ... 3000 nits peak brightness (outdoor)" | **VERIFIED** |
| 35% better sustained performance than iPhone 17 Pro; A20 Pro same as iPhone 18 Pro | Confirmed | Apple Newsroom (read): "up to 35 percent better sustained performance than iPhone 17 Pro"; "A20 Pro — the same chip in iPhone 18 Pro models" | **VERIFIED** |
| Battery: up to 44 h video (outer), 31 h (inner) | Confirmed | Apple Tech Specs (read): "Video playback Up to 44 hours when using the outer display ... Up to 31 hours when using the inner display" | **VERIFIED** (video playback) |
| Display sizes 5.4 in / 7.6 in, both OLED | Confirmed | Apple Newsroom and Tech Specs (read) | **VERIFIED** |
| "About 25% left after a mixed-use day" (one outlet) | **Not found.** Found instead: Tom's Guide browsing test 13 h 20 min; iThinkDiff: outer display matches iPhone 18 Pro Max, open drains faster; a recording test: 61% left after two hours (Duo) vs 59% (Pro Max) | search summaries (Tom's Guide, iThinkDiff, Zeera Wireless) | **UNVERIFIED** (outlet unnamed in the script; no source found) |
| "Another found it comfortably lasted a busy day" | not found | | **UNVERIFIED** |
| Price $1,999 for 256 GB | Confirmed; ladder not | Macworld (search summary: "starts at $1,999"); local Apple event slide | $1,999 **VERIFIED**; 2,199 / 2,599 / 3,199 **UNVERIFIED** |

**Discrepancies recorded (script untouched, no rewriting task created):** the Nov 2 memo date, the Oct 23 guide date, the Jan 22 date, the 25% battery line, the unverified
price ladder, and the "no software fix" line. The Oct 26 acknowledgement, the chip, 35%, 120 Hz, 3,000 nits, 44 h / 31 h and the screen sizes are
supported by Apple's own pages.

## D. Open questions
1. Is a monetised YouTube film "press" for iFixit's three-photo allowance? Ask (draft ready).
2. Apple: written consent route for Newsroom and event images; media.help@apple.com is named only on the Apple TV Press page.
3. Free Standard Sketchfab licence: monetised use not confirmed from a page I could read; the author's page says "Free Standard" only.
4. Reddit original post: needs you to open it (or another route) to confirm author and date.
5. Camera layout and flash on the models: see MODEL_VERIFICATION_DUO.md.

## E. Phase 2C.3 status note (2026-11-06)
- `DESIGN.md` ratios corrected to Apple's published dimensions (open about 1.40:1 landscape, closed about 0.71:1 portrait); camera geometry, flash and
  material remain UNRESOLVED.
- This register records evidence and discrepancies only. The original script, its dates, numbers, claims, narration and editorial direction are **unchanged**,
  and no script-rewriting work is open. Any decision about the script is outside this register.
- Policy unchanged: permission-first. **No item is RIGHTS_CLEARED or APPROVED_FOR_PRODUCTION**; those two statuses can be set only by you, with the
  rights documents recorded here.
- Reference videos and analyses (REVIEW_REFERENCE*.md, PRODUCTION_BLUEPRINT.md, CONCEPT_REFERENCE_BLUEPRINT.md, quality/) were not touched.

### Rights status at a glance
| Asset group | Rights status | Basis |
|---|---|---|
| Apple Newsroom / product-page images, event clips | not cleared | apple.com Terms of Use: written consent for commercial use; no Newsroom media terms found |
| iFixit text, images, video, CT scan | not cleared | CC BY-NC-SA 3.0 (non-commercial); request drafted, not sent |
| Owner photos and posts (Reddit, X) | not cleared | owner copyright; no permission asked; original post not seen |
| Press articles and screenshots (Gulf News, MacRumors, Macworld, others) | not cleared | per-item review; attribution is not permission |
| Third-party Duo review video on this Mac | not cleared | other creator's video |
| 3D models | label only | Pikkme CC BY 4.0 (credit recorded); extraakash "Free Standard" (monetised use unverified); zhe_kan non-commercial |
