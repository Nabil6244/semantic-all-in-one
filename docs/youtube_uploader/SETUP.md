# Auto-upload: Mac makes the videos, the UAE laptop uploads them

```
Mac: make_video.py batch  ->  <Drive>/YouTube Channels/<Channel>/ready/  ->  (Google Drive syncs)  ->  UAE laptop: upload_videos.py watch  ->  YouTube (private)
```

Nobody has to touch the laptop day to day. You control it from the Mac with `status`, `pause`, `resume`, `retry` and `now`.

## 1. Google Cloud key (once, on the Mac, about 10 minutes, free)

1. Go to console.cloud.google.com and create a project called "Video Uploader 1".
2. Under **APIs & Services → Library**, find **YouTube Data API v3** and click Enable.
3. Under **APIs & Services → OAuth consent screen**:
   - User type: External.
   - App name: anything.
   - Add your Google account(s) under **Test users**.
   - Then click **Publish app** so it is **In production**. If you skip this, every sign-in expires after 7 days. Google will warn that the app is "unverified". That is fine for your own channels.
4. Under **APIs & Services → Credentials → Create credentials → OAuth client ID**, choose type **Desktop app**, then click **Download JSON**.
5. Save the downloaded file as `client_secret.json` in the channels folder (step 2).

Each Cloud project gives about **6 uploads a day** (10,000 free units, about 1,600 per upload). For more, make project 2, 3 and so on. Save each key as `client_secret_2.json` and so on, then set `"client_secret": "client_secret_2.json"` in the `channel.json` of the channels that should use it.

The video stays **private** until Google audits the project. The audit is free (search "YouTube API audit form"). You make videos public in YouTube Studio.

## 2. The shared folder

Install **Google Drive for desktop** on both machines and sign in to the **same** Google account.

- On the **UAE laptop**, go to Drive settings → Google Drive → **Mirror files**. Streaming mode only downloads a file when something opens it.
- Use a folder inside My Drive, for example `My Drive/YouTube Channels`.

Drive needs room for the videos waiting to upload. After each upload, the uploader deletes the video's copy from Drive (the Mac keeps the original). Set `"remove_video_after_upload": false` in `channel.json` to keep the copies.

## 3. On the Mac

```bash
python3 upload_videos.py setup "$HOME/Library/CloudStorage/GoogleDrive-<your account>/My Drive/YouTube Channels"
```

```bash
python3 upload_videos.py add "Food Files"
```

```bash
python3 upload_videos.py login "Food Files"
```

- `login` prints a sign-in link and copies it. Paste it into the **ixBrowser profile of that channel**, pick the channel, and click Allow.
- If the tab then says it cannot connect, run `login "Food Files" --paste`. After Allow, copy the whole address from the tab and paste it into the terminal.
- The sign-in is saved in the channel folder, and Drive brings it to the laptop.

Repeat `add` and `login` for each channel. Then edit `<Channel>/channel.json` for each one:

| Setting | What it does |
|---|---|
| `tags` | Tags added to every video |
| `description_footer` | Links and credits added to every description |
| `category_id` | 22 People, 27 Education, 28 Science & Tech, 24 Entertainment |
| `language` | The video's language |
| `made_for_kids` | **true for kids channels** |
| `max_uploads_per_day` | Upload limit for this channel; 0 means only YouTube's limit |
| `enabled` | Set to false to skip the channel |
| `privacy` | `private` (default), `unlisted` or `public` |
| `schedule` | Publish times, for example `{"times": ["17:00"], "timezone": "Europe/London", "days": ["mon","wed","fri"]}` |

**Public and scheduled videos.** These only work once your Cloud project has passed YouTube's API audit. Until then, YouTube keeps every upload private, and the uploader writes "YouTube kept it PRIVATE" in `status`.

- With `"privacy": "public"`, a video goes live as soon as it's uploaded.
- With a `schedule`, each video is uploaded private and given the channel's next free time (at least 60 minutes ahead, never two videos on the same slot). YouTube then makes it public by itself. `days` is optional; without it, every day is used.
- If the laptop is Windows and says the time zone is unknown, run `pip install tzdata`, or use `"utc_offset": "+00:00"` instead of `timezone`.
- One video can have its own time: use the `publish_at` column in the batch CSV, or `enqueue ... --publish-at "2026-11-25 17:00"` (in the channel's time zone). If that time has already passed, the channel's schedule is used.

**Making videos that upload by themselves:** in the `make_video.py batch` CSV, add the columns `channel`, `description`, `tags` and `thumbnail`:

```
style,voice,script,csv,title,channel,description,tags,thumbnail,publish_at
food-files,vo1.mp3,s1.txt,c1.csv,Why Ketchup Was Medicine,Food Files,The strange history...,"food history,ketchup",thumb1.jpg,
```

Every video that finishes goes into that channel's `ready/` folder. A thumbnail is used if you name one, or if a `.jpg` or `.png` with the same name sits beside the video.

To queue one video by hand:

```bash
python3 upload_videos.py enqueue "Food Files" film.mp4 --title "..." --description-file desc.txt --tags "a,b"
```

## 4. On the UAE laptop (once, through AnyDesk or Chrome Remote Desktop)

1. Install Python 3 from python.org. On Windows, tick "Add Python to PATH".
2. Copy `upload_videos.py` onto the laptop. It's one file with no extra installs.
3. Run setup with **that laptop's** path to the Drive folder:

   Windows:
   ```bash
   python upload_videos.py setup "G:\My Drive\YouTube Channels"
   ```
   Mac:
   ```bash
   python3 upload_videos.py setup "$HOME/Library/CloudStorage/GoogleDrive-<account>/My Drive/YouTube Channels"
   ```
4. Make it start by itself at every log-in:
   ```bash
   python upload_videos.py autostart
   ```
5. Set the laptop so it keeps running on its own:
   - Plugged in, with sleep set to **Never** while on power.
   - Lid closing does nothing: on Windows, Power options → "When I close the lid" → Do nothing.
   - Automatic log-in after a restart: on Windows use `netplwiz`; on a Mac, Users & Groups → Automatic login.
   - Windows Update active hours set to the daytime.

The uploader checks every 5 minutes. It waits until a video has fully synced (size and checksum must match) before uploading it. A stopped upload continues where it stopped. When YouTube's daily limit is used up, it waits for the reset (midnight Pacific).

## 5. Managing it from the Mac

**In the app:** Tools → **Open Uploads**. The page shows:
- whether the laptop is alive, and its last check;
- every channel: who it's signed in as, videos waiting, uploaded today, failed (with the reason), and its last uploads (click one to open it);
- the buttons Pause, Resume, Check now, Retry failed, Choose folder, Add channel, Sign in and Settings (privacy, schedule, tags, footer, kids);
- Queue a video;
- the laptop's recent log.

It refreshes every 30 seconds while it's open.

**Or in the terminal:**

```bash
python3 upload_videos.py status
```
```bash
python3 upload_videos.py pause
```
```bash
python3 upload_videos.py resume
```
```bash
python3 upload_videos.py now
```
```bash
python3 upload_videos.py retry
```

| Command | What it does |
|---|---|
| `status` | Shows whether the laptop is alive, what's waiting, what was uploaded today with links, and what failed and why |
| `pause` | Stops after the current video |
| `resume` | Starts uploading again |
| `now` | Checks for new videos straight away instead of waiting 5 minutes |
| `retry` | Puts failed videos back in the queue |

Commands reach the laptop through Drive, usually within about a minute. The laptop's full log is in `YouTube Channels/_status/uploader.log`.

**Keep the channels folder private.** Its `.token.json` files let anyone upload to your channels. To cancel a channel's sign-in, go to myaccount.google.com/permissions.
