#!/usr/bin/env python3
"""Upload finished videos to many YouTube channels with no clicks, through the official YouTube Data API (free). Every video is uploaded
PRIVATE by default; a channel can be set to public, or to a publish schedule (both need a Cloud project that passed YouTube's API
audit: before that YouTube keeps every upload private, and the uploader says so).

The machines share one synced folder (Google Drive for desktop or Syncthing), the "root":

    <root>/client_secret.json          the Google Cloud "Desktop app" sign-in key (one per Cloud project; each gives ~6 uploads a day)
    <root>/<Channel>/channel.json      the channel's settings (tags, description footer, category, made for kids...)
    <root>/<Channel>/.token.json       the channel's sign-in (written by: login). Anyone with this folder can upload to the channel.
    <root>/<Channel>/ready/            videos waiting: <id>.mp4 + <id>.json (title, description, tags, size, checksum) [+ <id>.jpg]
    <root>/<Channel>/uploaded/         one <id>.json per uploaded video (YouTube link); the video copy is removed to keep Drive free
    <root>/<Channel>/failed/           videos YouTube refused for good, with the reason
    <root>/_status/                    what the uploading computer is doing (STATUS.txt, status.json, uploader.log)
    <root>/_control/control.json       commands from any computer: pause, resume, retry failed, check now

Where things run:
    the Mac (makes videos):   python3 upload_videos.py setup --root "<Drive folder>/YouTube Channels"
                              python3 upload_videos.py add "Food Files"
                              python3 upload_videos.py login "Food Files"     (open the link in that channel's ixBrowser profile)
                              python3 upload_videos.py enqueue "Food Files" film.mp4 --title "..."   (make_video.py batch does this
                                                                               itself for rows with a channel column)
    the uploading laptop:     python3 upload_videos.py setup --root "<same folder>"
                              python3 upload_videos.py autostart              (runs "watch" at every log-in, for good)
    anywhere:                 python3 upload_videos.py status | pause | resume | retry | now

Only the Python standard library is used."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"
CHUNK = 32 * 256 * 1024                 # 8 MB; YouTube wants multiples of 256 KB
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm")
THUMB_EXT = (".jpg", ".jpeg", ".png")
THUMB_MAX = 2 * 1024 * 1024
LOCAL = Path.home() / ".youtube_uploader"             # this computer only: where the root is, upload sessions, checksums
CONFIG = LOCAL / "config.json"
LOCK_PORT = 47613                                     # one "watch" per computer
DEFAULT_INTERVAL = 300
CONTROL_POLL = 30
HEARTBEAT_STALE = 20 * 60
PERMANENT_REASONS = {"invalidTitle", "invalidDescription", "invalidTags", "invalidCategoryId", "mediaBodyRequired", "invalidFilename",
                     "invalidVideoMetadata"}
PRIVACY = ("private", "unlisted", "public")
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded"}
DEFAULT_CHANNEL = {
    "privacy": "private",                 # private (default), unlisted or public (public needs a Cloud project that passed the API audit)
    "schedule": {},                       # {"times": ["17:00"], "timezone": "Europe/London", "days": ["mon", ...]}: uploaded private and
                                          # made public by YouTube at the channel's next free time (needs the audit too)
    "category_id": "22",                  # 22 People & Blogs, 27 Education, 28 Science & Tech, 24 Entertainment, 26 Howto & Style
    "language": "en",
    "made_for_kids": False,
    "tags": [],
    "description_footer": "",
    "client_secret": "client_secret.json",   # a file in the root; give channels different ones to spread the daily limit
    "max_uploads_per_day": 0,             # 0 = only YouTube's limit
    "remove_video_after_upload": True,    # the copy in the shared folder; the original stays where it was made
    "enabled": True,
}


class UploadError(Exception):
    def __init__(self, message: str, permanent: bool = False, reason: str = ""):
        super().__init__(message)
        self.permanent = permanent
        self.reason = reason


class QuotaError(UploadError):
    pass


class AuthError(UploadError):
    pass


# ---------------------------------------------------------------- small helpers

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Any, private: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if private:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^\w]+", "-", str(text or ""), flags=re.UNICODE).strip("-").lower()
    return (s[:limit].rstrip("-")) or "video"


def check_name(name: str) -> str:
    name = str(name or "").strip()
    if not re.fullmatch(r"[\w .&'-]{1,60}", name, flags=re.UNICODE) or name.startswith((".", "_")):
        raise UploadError(f"channel name {name!r}: use letters, numbers, spaces, - _ . & (up to 60), not starting with . or _")
    return name


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def copy_to_clipboard(text: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=10)
            return True
        if os.name == "nt":
            subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True, timeout=10)
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------- the root and channels

def find_root(explicit: str = "") -> Path:
    """--root, else $YT_UPLOADER_ROOT, else the root saved by: setup."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("YT_UPLOADER_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    saved = (read_json(CONFIG, {}) or {}).get("root")
    if saved:
        return Path(saved).expanduser()
    raise UploadError("no channels folder set: run  upload_videos.py setup --root \"<your synced folder>/YouTube Channels\"")


README = """YouTube Channels (made by upload_videos.py)

One folder per channel. Put nothing by hand in ready/ unless it has its .json beside it (use: upload_videos.py enqueue).
client_secret.json here is the Google Cloud "Desktop app" key (see docs/youtube_uploader/SETUP.md in the video app).
The .token.json in each channel folder is that channel's sign-in: do not share this folder with anyone.
"""


def setup_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("_status", "_control"):
        (root / sub).mkdir(exist_ok=True)
    if not (root / "README.txt").exists():
        (root / "README.txt").write_text(README, encoding="utf-8")
    cfg = read_json(CONFIG, {}) or {}
    cfg["root"] = str(root)
    write_json(CONFIG, cfg)
    return root


def channel_dir(root: Path, name: str) -> Path:
    return root / check_name(name)


def channel_cfg(ch: Path) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CHANNEL)
    cfg.update(read_json(ch / "channel.json", {}) or {})
    if cfg.get("privacy") not in PRIVACY:
        cfg["privacy"] = "private"
    if not isinstance(cfg.get("schedule"), dict):
        cfg["schedule"] = {}
    return cfg


# ---------------------------------------------------------------- publish times

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def channel_tz(cfg: Dict[str, Any]):
    sch = cfg.get("schedule") or {}
    off = str(sch.get("utc_offset") or "").strip()
    if off:
        m = re.fullmatch(r"([+-])(\d{1,2}):?(\d{2})?", off)
        if not m:
            raise UploadError(f"schedule.utc_offset {off!r}: write it like \"+04:00\"", permanent=True)
        mins = int(m.group(2)) * 60 + int(m.group(3) or 0)
        return timezone(timedelta(minutes=mins if m.group(1) == "+" else -mins))
    name = str(sch.get("timezone") or "UTC")
    if name.upper() == "UTC":
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        raise UploadError(f"time zone {name!r} is not known on this computer: run  pip install tzdata  or set schedule.utc_offset "
                          f"(like \"+00:00\") in channel.json")


def _times(cfg: Dict[str, Any]) -> List[Tuple[int, int]]:
    out = []
    for t in (cfg.get("schedule") or {}).get("times") or []:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(t).strip())
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise UploadError(f"schedule time {t!r}: write it like \"17:00\"")
        out.append((int(m.group(1)), int(m.group(2))))
    return sorted(set(out))


def next_slot(cfg: Dict[str, Any], taken: List[datetime], now: Optional[datetime] = None) -> Optional[datetime]:
    """The channel's next free publish time (UTC), at least schedule.min_lead_minutes (60) from now; None without a schedule."""
    times = _times(cfg)
    if not times:
        return None
    sch = cfg.get("schedule") or {}
    tz = channel_tz(cfg)
    now = now or datetime.now(timezone.utc)
    earliest = now + timedelta(minutes=int(sch.get("min_lead_minutes", 60)))
    days = {str(d).strip().lower()[:3] for d in sch.get("days") or []} or set(DAYS)
    first = earliest.astimezone(tz).date()
    for n in range(0, 400):
        day = first + timedelta(days=n)
        if DAYS[day.weekday()] not in days:
            continue
        for hh, mm in times:
            t = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz).astimezone(timezone.utc)
            if t >= earliest and not any(abs((t - x).total_seconds()) < 60 for x in taken):
                return t
    return None


def taken_slots(ch: Path) -> List[datetime]:
    out = []
    for p in list((ch / "uploaded").glob("*.json")):
        d = read_json(p, {}) or {}
        t = parse_utc(d.get("publish_at"))
        if t:
            out.append(t)
    return out


def parse_utc(text: Any) -> Optional[datetime]:
    if not text:
        return None
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)


def parse_local(cfg: Dict[str, Any], text: str) -> datetime:
    """'2026-11-25 17:00' in the channel's time zone (or an ISO time with its own offset) -> UTC."""
    text = str(text or "").strip()
    try:
        t = datetime.fromisoformat(text.replace("Z", "+00:00").replace("T", " "))
    except ValueError:
        raise UploadError(f"publish time {text!r}: write it like 2026-11-25 17:00")
    if t.tzinfo is None:
        t = t.replace(tzinfo=channel_tz(cfg))
    return t.astimezone(timezone.utc)


def utc_z(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_channel(root: Path, name: str, made_for_kids: bool = False, tags: Optional[List[str]] = None) -> Path:
    ch = channel_dir(root, name)
    for sub in ("ready", "uploaded", "failed"):
        (ch / sub).mkdir(parents=True, exist_ok=True)
    if not (ch / "channel.json").exists():
        cfg = {"name": ch.name, **DEFAULT_CHANNEL, "made_for_kids": bool(made_for_kids), "tags": list(tags or [])}
        write_json(ch / "channel.json", cfg)
    return ch


def channels(root: Path) -> List[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_")) and (p / "channel.json").is_file())


# ---------------------------------------------------------------- HTTP (no extra libraries)

def _request(method: str, url: str, headers: Optional[Dict[str, str]] = None, body: Optional[bytes] = None,
             timeout: float = 120) -> Tuple[int, Dict[str, str], bytes]:
    u = urlparse(url)
    conn = http.client.HTTPSConnection(u.netloc, timeout=timeout)
    try:
        conn.request(method, u.path + (f"?{u.query}" if u.query else ""), body=body, headers=headers or {})
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        conn.close()


def api_error(status: int, data: bytes, what: str) -> UploadError:
    reason, msg = "", ""
    try:
        err = json.loads(data.decode("utf-8", "replace")).get("error") or {}
        if isinstance(err, dict):
            msg = err.get("message") or ""
            errs = err.get("errors") or []
            reason = (errs[0].get("reason") if errs and isinstance(errs[0], dict) else "") or err.get("status") or ""
        else:
            reason, msg = str(err), ""
    except Exception:
        msg = data[:300].decode("utf-8", "replace")
    text = f"{what}: YouTube said {status} {reason} {msg}".strip()
    if reason in QUOTA_REASONS:
        return QuotaError(text, reason=reason)
    if status == 401 or reason in ("invalid_grant", "authError", "unauthorized_client"):
        return AuthError(text + " -> sign in again: upload_videos.py login <channel>", reason=reason)
    if status == 403 and reason in ("forbidden", "youtubeSignupRequired", "channelClosed", "accountClosed", "accountSuspended"):
        return AuthError(text, reason=reason)
    return UploadError(text, permanent=(status == 400 or reason in PERMANENT_REASONS), reason=reason)


# ---------------------------------------------------------------- sign-in

def load_client(root: Path, cfg: Dict[str, Any]) -> Dict[str, str]:
    path = root / (cfg.get("client_secret") or "client_secret.json")
    d = read_json(path)
    if not d:
        raise UploadError(f"the Google sign-in key is missing: put the downloaded client_secret JSON at {path}")
    c = d.get("installed")
    if not c:
        raise UploadError(f"{path.name} is not a 'Desktop app' key: in Google Cloud make an OAuth client of type Desktop app")
    return {"client_id": c["client_id"], "client_secret": c.get("client_secret", ""), "path": str(path)}


def _token_post(client: Dict[str, str], fields: Dict[str, str]) -> Dict[str, Any]:
    body = urlencode({"client_id": client["client_id"], "client_secret": client["client_secret"], **fields}).encode()
    status, _, data = _request("POST", TOKEN_URI, {"Content-Type": "application/x-www-form-urlencoded"}, body, timeout=60)
    try:
        d = json.loads(data.decode("utf-8", "replace"))
    except ValueError:
        d = {}
    if status != 200:
        err = d.get("error") or status
        if err == "invalid_grant":
            raise AuthError("the channel's sign-in expired or was removed -> upload_videos.py login <channel>. (If this keeps happening "
                            "every 7 days, set the Google Cloud consent screen to 'In production'.)", reason="invalid_grant")
        raise UploadError(f"Google sign-in failed: {err} {d.get('error_description', '')}".strip())
    return d


def auth_url(client: Dict[str, str], redirect: str, challenge: str, state: str) -> str:
    return AUTH_URI + "?" + urlencode({"client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
                                       "scope": SCOPES, "access_type": "offline", "prompt": "consent select_account",
                                       "code_challenge": challenge, "code_challenge_method": "S256", "state": state})


def parse_redirect(text: str, state: str) -> str:
    q = parse_qs(urlparse(text.strip()).query)
    if q.get("error"):
        raise UploadError(f"sign-in was refused: {q['error'][0]}")
    if (q.get("state") or [""])[0] != state:
        raise UploadError("that address is not from this sign-in (state does not match); run login again")
    code = (q.get("code") or [""])[0]
    if not code:
        raise UploadError("no sign-in code in that address")
    return code


_LAST_VERIFIER: Dict[str, str] = {}      # state -> PKCE verifier of links shown in this run (the app page finishes a pasted one)


def login(root: Path, name: str, paste: bool = False, open_browser: bool = False, say: Callable[[str], None] = print,
          ask: Callable[[str], str] = input, wait_s: int = 600) -> Dict[str, str]:
    ch = channel_dir(root, name)
    if not (ch / "channel.json").is_file():
        raise UploadError(f"no channel {name!r}: run  upload_videos.py add \"{name}\"")
    client = load_client(root, channel_cfg(ch))
    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(16)
    got: Dict[str, str] = {}
    srv = None
    if paste:
        redirect = "http://127.0.0.1:8"            # nothing listens: the tab shows an error page whose address holds the code
    else:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if "code=" in self.path or "error=" in self.path:
                    got["url"] = "http://127.0.0.1" + self.path
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h2>Signed in. You can close this tab.</h2>".encode())

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), Handler)
        srv.timeout = 1
        redirect = f"http://127.0.0.1:{srv.server_address[1]}"
    url = auth_url(client, redirect, challenge, state)
    _LAST_VERIFIER[state] = verifier
    say(f"\nSign in the channel '{ch.name}': open this link in the browser (ixBrowser profile) where that channel is signed in,")
    say("pick the channel, and click Allow:\n")
    say(url + "\n")
    if copy_to_clipboard(url):
        say("(the link is copied: paste it into the profile's address bar)")
    if open_browser:
        webbrowser.open(url)
    try:
        if paste:
            got["url"] = ask("After Allow the tab shows an error page. Copy its whole address and paste it here: ")
        else:
            say("waiting for the sign-in (10 minutes)... If the tab says it cannot connect, stop with Ctrl+C and run login again with --paste")
            deadline = time.time() + wait_s
            while "url" not in got and time.time() < deadline:
                srv.handle_request()
    finally:
        if srv is not None:
            srv.server_close()
    if "url" not in got:
        raise UploadError("the sign-in did not come back in time; run login again (or with --paste)")
    return finish_login(root, name, got["url"], redirect, state, verifier)


def finish_login(root: Path, name: str, returned_url: str, redirect: str, state: str, verifier: str) -> Dict[str, str]:
    """The address the browser came back to (or that was pasted) -> the channel's saved sign-in. Returns {"id", "title"}."""
    ch = channel_dir(root, name)
    client = load_client(root, channel_cfg(ch))
    code = parse_redirect(returned_url, state)
    tok = _token_post(client, {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect, "code_verifier": verifier})
    if not tok.get("refresh_token"):
        raise UploadError("Google gave no lasting sign-in; remove the app's access at myaccount.google.com/permissions and log in again")
    token = {"refresh_token": tok["refresh_token"], "access_token": tok.get("access_token", ""),
             "expires_at": time.time() + float(tok.get("expires_in", 0) or 0), "client_id": client["client_id"], "signed_in": now_iso()}
    write_json(ch / ".token.json", token, private=True)
    info = channel_info(root, ch)
    token.update({"channel_id": info.get("id", ""), "channel_title": info.get("title", "")})
    write_json(ch / ".token.json", token, private=True)
    return info


def access_token(root: Path, ch: Path, force: bool = False) -> str:
    tok = read_json(ch / ".token.json")
    if not tok or not tok.get("refresh_token"):
        raise AuthError(f"'{ch.name}' is not signed in: upload_videos.py login \"{ch.name}\"")
    if not force and tok.get("access_token") and float(tok.get("expires_at", 0)) - 120 > time.time():
        return tok["access_token"]
    client = load_client(root, channel_cfg(ch))
    d = _token_post(client, {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    tok["access_token"] = d["access_token"]
    tok["expires_at"] = time.time() + float(d.get("expires_in", 3600))
    write_json(ch / ".token.json", tok, private=True)
    return tok["access_token"]


def authed(root: Path, ch: Path, method: str, url: str, headers: Optional[Dict[str, str]] = None, body: Optional[bytes] = None,
           timeout: float = 120) -> Tuple[int, Dict[str, str], bytes]:
    for attempt in (0, 1):
        h = dict(headers or {})
        h["Authorization"] = "Bearer " + access_token(root, ch, force=bool(attempt))
        status, hdr, data = _request(method, url, h, body, timeout)
        if status != 401 or attempt:
            return status, hdr, data
    return status, hdr, data


def channel_info(root: Path, ch: Path) -> Dict[str, str]:
    status, _, data = authed(root, ch, "GET", f"{API}/channels?part=snippet&mine=true")
    if status != 200:
        raise api_error(status, data, "reading the channel")
    items = json.loads(data.decode()).get("items") or []
    if not items:
        raise AuthError("this Google account has no YouTube channel (pick the channel, not the account, in the sign-in)")
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}


# ---------------------------------------------------------------- video kits (what the Mac puts in ready/)

def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", str(title or "").replace("<", "").replace(">", "")).strip()
    if len(t) > 100:
        t = t[:100].rsplit(" ", 1)[0].strip() or t[:100]
    return t


def clean_description(text: str) -> str:
    d = str(text or "").replace("<", "").replace(">", "").strip()
    raw = d.encode("utf-8")
    if len(raw) > 5000:
        d = raw[:5000].decode("utf-8", "ignore")
    return d


def clean_tags(*groups: Any) -> List[str]:
    """YouTube's limit: about 500 characters for all tags together (a tag with a space counts its quotes)."""
    out, seen, total = [], set(), 0
    for g in groups:
        items = g.split(",") if isinstance(g, str) else list(g or [])
        for t in items:
            t = re.sub(r"\s+", " ", str(t).replace("<", "").replace(">", "").replace(",", " ")).strip().lstrip("#")
            if not t or len(t) > 100 or t.lower() in seen:
                continue
            cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
            if total + cost > 500:
                return out
            out.append(t)
            seen.add(t.lower())
            total += cost
    return out


def enqueue(root: Path, name: str, video: "str | Path", title: str = "", description: str = "", tags: Any = None,
            thumbnail: "str | Path" = "", made_for_kids: Optional[bool] = None, publish_at: str = "") -> Path:
    """Copy a finished video into the channel's ready/ folder with its .json (written last: a video without it is never uploaded)."""
    ch = channel_dir(root, name)
    if not (ch / "channel.json").is_file():
        raise UploadError(f"no channel {name!r}: run  upload_videos.py add \"{name}\"")
    src = Path(video).expanduser().resolve()
    if not src.is_file() or src.suffix.lower() not in VIDEO_EXT:
        raise UploadError(f"not a video file: {video}")
    when = utc_z(parse_local(channel_cfg(ch), publish_at)) if str(publish_at or "").strip() else ""
    title = clean_title(title or src.stem.replace("_", " ").replace("-", " "))
    vid = f"{time.strftime('%Y%m%d-%H%M%S')}_{slug(title)}"
    ready = ch / "ready"
    ready.mkdir(parents=True, exist_ok=True)
    n = 1
    while (ready / f"{vid}.json").exists() or (ready / f"{vid}{src.suffix.lower()}").exists():
        n += 1
        vid = f"{time.strftime('%Y%m%d-%H%M%S')}_{slug(title)}_{n}"
    dest = ready / f"{vid}{src.suffix.lower()}"
    part = ready / f".{vid}.part"
    shutil.copyfile(src, part)
    os.replace(part, dest)
    thumb_name = ""
    t = Path(thumbnail).expanduser() if thumbnail else next((src.with_suffix(e) for e in THUMB_EXT if src.with_suffix(e).is_file()), None)
    if t and t.is_file() and t.suffix.lower() in THUMB_EXT:
        thumb_name = f"{vid}{t.suffix.lower()}"
        shutil.copyfile(t, ready / thumb_name)
    kit = {"kit": 1, "video": dest.name, "size": dest.stat().st_size, "sha256": sha256_file(dest), "title": title,
           "description": str(description or ""), "tags": clean_tags(tags or []), "thumbnail": thumb_name,
           "made_for_kids": made_for_kids, "publish_at": when, "source": str(src), "queued": now_iso(), "queued_on": socket.gethostname()}
    write_json(ready / f"{vid}.json", kit)
    return ready / f"{vid}.json"


def video_body(kit: Dict[str, Any], cfg: Dict[str, Any], publish_at: Optional[datetime] = None) -> Dict[str, Any]:
    desc = str(kit.get("description") or "").strip()
    footer = str(cfg.get("description_footer") or "").strip()
    if footer:
        desc = (desc + "\n\n" + footer).strip()
    kids = kit.get("made_for_kids")
    lang = str(cfg.get("language") or "en")
    snippet = {"title": clean_title(kit.get("title") or "Video") or "Video", "description": clean_description(desc),
               "tags": clean_tags(kit.get("tags") or [], cfg.get("tags") or []), "categoryId": str(cfg.get("category_id") or "22"),
               "defaultLanguage": lang, "defaultAudioLanguage": lang}
    status = {"privacyStatus": cfg.get("privacy") if cfg.get("privacy") in PRIVACY else "private",
              "selfDeclaredMadeForKids": bool(cfg.get("made_for_kids") if kids is None else kids), "embeddable": True}
    if publish_at is not None:                # YouTube's rule: a scheduled video is private until its time
        status["privacyStatus"] = "private"
        status["publishAt"] = utc_z(publish_at)
    if cfg.get("synthetic_media") is not None:
        status["containsSyntheticMedia"] = bool(cfg["synthetic_media"])
    return {"snippet": snippet, "status": status}


def kit_ready(ch: Path, kit_path: Path, local: Path = LOCAL) -> Tuple[Optional[Dict[str, Any]], str]:
    """(the kit, "") when its video has fully arrived and matches its checksum, else (None, why)."""
    kit = read_json(kit_path)
    if not isinstance(kit, dict) or not kit.get("video"):
        return None, "its .json cannot be read yet"
    video = kit_path.parent / kit["video"]
    if not video.is_file():
        return None, "the video has not arrived yet"
    st = video.stat()
    if st.st_size != int(kit.get("size") or -1):
        return None, f"the video is still arriving ({st.st_size * 100 // max(1, int(kit.get('size') or 1))}%)"
    if time.time() - st.st_mtime < 20:
        return None, "the video was just written"
    cache_path = local / "checksums.json"
    cache = read_json(cache_path, {}) or {}
    key = f"{ch.name}/{video.name}"
    c = cache.get(key) or {}
    if c.get("size") == st.st_size and c.get("mtime") == st.st_mtime:
        digest = c.get("sha256")
    else:
        digest = sha256_file(video)
        cache[key] = {"size": st.st_size, "mtime": st.st_mtime, "sha256": digest}
        write_json(cache_path, cache)
    if kit.get("sha256") and digest != kit["sha256"]:
        return None, "the video does not match its checksum yet (still syncing or damaged)"
    return kit, ""


# ---------------------------------------------------------------- the upload

def _offset_from(hdr: Dict[str, str]) -> int:
    m = re.search(r"bytes=0-(\d+)", hdr.get("range", ""))
    return int(m.group(1)) + 1 if m else 0


def upload_video(root: Path, ch: Path, video: Path, body: Dict[str, Any], say: Callable[[str], None] = print,
                 local: Path = LOCAL, sleep: Callable[[float], None] = time.sleep) -> str:
    """A resumable upload; a stopped upload goes on where it stopped (even after a restart). Returns YouTube's answer ({"id", "status"})."""
    size = video.stat().st_size
    sess_path = local / "sessions" / f"{ch.name}__{video.name}.json"
    sess = read_json(sess_path) or {}
    if sess.get("size") != size or time.time() - float(sess.get("started", 0)) > 5 * 86400:
        sess = {}
    offset = 0
    if sess:
        offset, done = _query(root, ch, sess["url"], size)
        if done:
            sess_path.unlink(missing_ok=True)
            return done
        if offset < 0:
            sess = {}
            offset = 0
    if not sess:
        meta = json.dumps(body).encode("utf-8")
        ctype = "video/mp4" if video.suffix.lower() in (".mp4", ".m4v") else "video/*"
        status, hdr, data = authed(root, ch, "POST", f"{UPLOAD_API}/videos?uploadType=resumable&part=snippet,status",
                                   {"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Length": str(size),
                                    "X-Upload-Content-Type": ctype}, meta, timeout=60)
        if status != 200 or not hdr.get("location"):
            raise api_error(status, data, "starting the upload")
        sess = {"url": hdr["location"], "size": size, "started": time.time()}
        write_json(sess_path, sess, private=True)
    retries, last_pct = 0, -1
    with open(video, "rb") as f:
        while True:
            f.seek(offset)
            chunk = f.read(CHUNK)
            headers = {"Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{size}"}
            try:
                status, hdr, data = authed(root, ch, "PUT", sess["url"], headers, chunk, timeout=300)
            except (OSError, http.client.HTTPException) as exc:
                status, hdr, data = 0, {}, str(exc).encode()
            if status in (200, 201):
                sess_path.unlink(missing_ok=True)
                return json.loads(data.decode())
            if status == 308:
                offset, retries = _offset_from(hdr), 0
                pct = offset * 100 // max(1, size)
                if pct // 10 != last_pct // 10:
                    say(f"  {ch.name}: {video.name} {pct}%")
                    last_pct = pct
                continue
            if status in (404, 410):
                sess_path.unlink(missing_ok=True)
                raise UploadError("YouTube dropped the upload; it starts again next round")
            if status in (0, 429) or status >= 500:
                retries += 1
                if retries > 8:
                    raise UploadError(f"the connection kept failing ({status or data[:120].decode('utf-8', 'replace')}); tried 8 times")
                sleep(min(2 ** retries, 120))
                offset, done = _query(root, ch, sess["url"], size)
                if done:
                    sess_path.unlink(missing_ok=True)
                    return done
                if offset < 0:
                    sess_path.unlink(missing_ok=True)
                    raise UploadError("YouTube dropped the upload; it starts again next round")
                continue
            raise api_error(status, data, "uploading")


def _query(root: Path, ch: Path, url: str, size: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    """(bytes YouTube already has, YouTube's answer if it is complete). Offset -1 = the session is gone."""
    try:
        status, hdr, data = authed(root, ch, "PUT", url, {"Content-Length": "0", "Content-Range": f"bytes */{size}"}, b"", timeout=60)
    except (OSError, http.client.HTTPException):
        return 0, None
    if status in (200, 201):
        try:
            return size, json.loads(data.decode())
        except Exception:
            return 0, None
    if status == 308:
        return _offset_from(hdr), None
    if status in (404, 410):
        return -1, None
    return 0, None


def set_thumbnail(root: Path, ch: Path, video_id: str, thumb: Path) -> str:
    if thumb.stat().st_size > THUMB_MAX:
        return "thumbnail skipped: over 2 MB"
    ctype = "image/png" if thumb.suffix.lower() == ".png" else "image/jpeg"
    status, _, data = authed(root, ch, "POST", f"{UPLOAD_API}/thumbnails/set?videoId={video_id}&uploadType=media",
                             {"Content-Type": ctype}, thumb.read_bytes(), timeout=120)
    if status == 200:
        return ""
    if status == 403:
        return "thumbnail skipped: the channel needs phone verification for custom thumbnails (youtube.com/verify)"
    return f"thumbnail failed: {api_error(status, data, 'thumbnail')}"


# ---------------------------------------------------------------- the watcher (the uploading computer)

def next_quota_reset(now: Optional[datetime] = None) -> float:
    """YouTube's daily limit resets at midnight Pacific time (08:00 UTC in winter, 07:00 in summer): wait until 08:05 UTC."""
    now = now or datetime.now(timezone.utc)
    t = now.replace(hour=8, minute=5, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t.timestamp()


def uploads_today(ch: Path) -> int:
    day = datetime.now(timezone.utc).date().isoformat()
    n = 0
    for p in (ch / "uploaded").glob("*.json"):
        d = read_json(p, {}) or {}
        if str(d.get("uploaded_utc", "")).startswith(day):
            n += 1
    return n


def control(root: Path) -> Dict[str, Any]:
    return read_json(root / "_control" / "control.json", {}) or {}


def send_control(root: Path, **changes: Any) -> Dict[str, Any]:
    c = control(root)
    c.update(changes)
    c["changed"] = now_iso()
    c["changed_on"] = socket.gethostname()
    write_json(root / "_control" / "control.json", c)
    return c


def retry_failed(root: Path, names: Optional[List[str]] = None) -> int:
    """Move failed videos back to ready/ (they are tried again)."""
    n = 0
    for ch in channels(root):
        if names and ch.name not in names:
            continue
        for kit in (ch / "failed").glob("*.json"):
            d = read_json(kit, {}) or {}
            for f in [d.get("video"), d.get("thumbnail")]:
                if f and (ch / "failed" / f).exists():
                    os.replace(ch / "failed" / f, ch / "ready" / f)
            d.pop("error", None)
            d.pop("failed", None)
            write_json(ch / "ready" / kit.name, d)
            kit.unlink()
            n += 1
    return n


class Watcher:
    def __init__(self, root: Path, say: Callable[[str], None] = print, local: Path = LOCAL):
        self.root, self.local, self._say = root, local, say
        self.state = read_json(local / "state.json", {}) or {}
        self.waiting: Dict[str, str] = {}
        self.last: Dict[str, Any] = {}

    def say(self, msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        self._say(line)
        log = self.root / "_status" / "uploader.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            if log.exists() and log.stat().st_size > 2 * 1024 * 1024:
                os.replace(log, log.with_suffix(".old.log"))
            with open(log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def save_state(self) -> None:
        write_json(self.local / "state.json", self.state)

    def quota_blocked(self, client_path: str) -> float:
        until = float((self.state.get("quota_until") or {}).get(client_path, 0))
        return until if until > time.time() else 0.0

    def cycle(self) -> Dict[str, int]:
        """One pass: round-robin over the channels, one video each per round, until nothing more can go now."""
        c = control(self.root)
        if c.get("retry") and c.get("retry") != self.state.get("retry_seen"):
            n = retry_failed(self.root)
            self.state["retry_seen"] = c["retry"]
            self.save_state()
            self.say(f"retry: {n} failed video(s) put back in ready/")
        counts = {"uploaded": 0, "failed": 0, "waiting": 0}
        if c.get("paused"):
            self.write_status("paused from " + str(c.get("changed_on") or "another computer"), counts)
            return counts
        queues: Dict[Path, List[Path]] = {}
        for ch in channels(self.root):
            cfg = channel_cfg(ch)
            if not cfg.get("enabled", True):
                continue
            queues[ch] = sorted((ch / "ready").glob("*.json"))
        while True:
            progressed = False
            for ch, kits in queues.items():
                while kits:
                    kit_path = kits.pop(0)
                    r = self.one(ch, kit_path)
                    if r == "waiting":
                        counts["waiting"] += 1
                        continue
                    if r == "stop-channel":
                        kits.clear()
                        break
                    counts[r] = counts.get(r, 0) + 1
                    progressed = True
                    break
                if control(self.root).get("paused"):
                    self.say("paused while uploading: stopping after this video")
                    self.write_status("paused", counts)
                    return counts
            if not progressed:
                break
        self.write_status("idle", counts)
        return counts

    def one(self, ch: Path, kit_path: Path) -> str:
        cfg = channel_cfg(ch)
        try:
            client = load_client(self.root, cfg)
        except UploadError as exc:
            self.note(ch, str(exc))
            return "stop-channel"
        if self.quota_blocked(client["path"]):
            self.note(ch, "YouTube's daily limit is used up for " + Path(client["path"]).name + "; goes on after "
                      + datetime.fromtimestamp(self.quota_blocked(client["path"])).strftime("%H:%M"))
            return "stop-channel"
        cap = int(cfg.get("max_uploads_per_day") or 0)
        if cap and uploads_today(ch) >= cap:
            self.note(ch, f"{cap} upload(s) today already (max_uploads_per_day)")
            return "stop-channel"
        if not (ch / ".token.json").is_file():
            self.note(ch, f"not signed in: run  upload_videos.py login \"{ch.name}\"  on the Mac")
            return "stop-channel"
        kit, why = kit_ready(ch, kit_path, self.local)
        if kit is None:
            key = f"{ch.name}/{kit_path.name}"
            if self.waiting.get(key) != why:
                self.say(f"{ch.name}: {kit_path.stem}: waiting ({why})")
                self.waiting[key] = why
            return "waiting"
        video = kit_path.parent / kit["video"]
        try:
            publish = self.publish_time(ch, kit, cfg)
        except UploadError as exc:
            self.note(ch, str(exc), loud=True)
            return "stop-channel"
        when = f", goes public {publish.astimezone(channel_tz(cfg)):%a %d %b %H:%M}" if publish else f", {cfg.get('privacy')}"
        self.say(f"{ch.name}: uploading '{kit.get('title')}' ({video.stat().st_size / 1e6:.0f} MB{when})")
        try:
            resp = upload_video(self.root, ch, video, video_body(kit, cfg, publish), say=self.say, local=self.local)
            vid = resp["id"]
        except QuotaError as exc:
            until = next_quota_reset()
            self.state.setdefault("quota_until", {})[client["path"]] = until
            self.save_state()
            self.say(f"{ch.name}: {exc}; uploads with this key wait until {datetime.fromtimestamp(until):%Y-%m-%d %H:%M}")
            return "stop-channel"
        except AuthError as exc:
            self.note(ch, str(exc), loud=True)
            return "stop-channel"
        except UploadError as exc:
            if exc.permanent:
                self.fail(ch, kit_path, kit, str(exc))
                return "failed"
            self.say(f"{ch.name}: {exc} (tried again next round)")
            return "stop-channel"
        except Exception as exc:            # a bug must not stop the other channels
            self.say(f"{ch.name}: unexpected error {exc!r} (tried again next round)")
            return "stop-channel"
        notes = []
        thumb = kit_path.parent / kit["thumbnail"] if kit.get("thumbnail") else None
        if thumb and thumb.is_file():
            try:
                t = set_thumbnail(self.root, ch, vid, thumb)
            except Exception as exc:
                t = f"thumbnail failed: {exc}"
            if t:
                notes.append(t)
        st = resp.get("status") or {}
        wanted_public = publish is not None or cfg.get("privacy") == "public"
        if st and wanted_public and st.get("privacyStatus") == "private" and not st.get("publishAt"):
            notes.append("YouTube kept it PRIVATE: the Cloud project has not passed the API audit yet, so public and scheduled uploads "
                         "are locked; make it public in Studio")
            publish = None
        self.done(ch, kit_path, kit, vid, cfg, notes, publish, st.get("privacyStatus") or "")
        return "uploaded"

    def publish_time(self, ch: Path, kit: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[datetime]:
        """The kit's own publish time if it is still ahead, else the channel's next free schedule time, else None (privacy as set)."""
        own = parse_utc(kit.get("publish_at"))
        if own and own > datetime.now(timezone.utc) + timedelta(minutes=15):
            return own
        if own:
            self.say(f"{ch.name}: '{kit.get('title')}' publish time {kit.get('publish_at')} has passed; using the channel's schedule")
        return next_slot(cfg, taken_slots(ch))

    def note(self, ch: Path, msg: str, loud: bool = False) -> None:
        if self.last.get(ch.name) != msg or loud:
            self.say(f"{ch.name}: {msg}")
        self.last[ch.name] = msg

    def done(self, ch: Path, kit_path: Path, kit: Dict[str, Any], vid: str, cfg: Dict[str, Any], notes: List[str],
             publish: Optional[datetime] = None, actual: str = "") -> None:
        rec = dict(kit)
        privacy = f"scheduled {publish.astimezone(channel_tz(cfg)):%Y-%m-%d %H:%M}" if publish else (actual or cfg.get("privacy", "private"))
        rec.update({"youtube_id": vid, "url": f"https://youtu.be/{vid}", "studio": f"https://studio.youtube.com/video/{vid}/edit",
                    "privacy": privacy, "publish_at": utc_z(publish) if publish else "", "uploaded": now_iso(),
                    "uploaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "uploaded_on": socket.gethostname(),
                    "notes": notes})
        up = ch / "uploaded"
        up.mkdir(exist_ok=True)
        files = [kit.get("video"), kit.get("thumbnail")]
        if cfg.get("remove_video_after_upload", True):
            for f in files:
                if f:
                    (kit_path.parent / f).unlink(missing_ok=True)
            rec["video_copy"] = "removed after upload (the original: source)"
        else:
            for f in files:
                if f and (kit_path.parent / f).exists():
                    os.replace(kit_path.parent / f, up / f)
        write_json(up / kit_path.name, rec)
        kit_path.unlink(missing_ok=True)
        with open(ch / "uploads.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": rec["uploaded"], "title": rec.get("title"), "url": rec["url"], "notes": notes}, ensure_ascii=False) + "\n")
        self.say(f"{ch.name}: DONE '{kit.get('title')}' -> {rec['url']} ({rec['privacy']})" + (f"; {'; '.join(notes)}" if notes else ""))

    def fail(self, ch: Path, kit_path: Path, kit: Dict[str, Any], why: str) -> None:
        bad = ch / "failed"
        bad.mkdir(exist_ok=True)
        for f in [kit.get("video"), kit.get("thumbnail")]:
            if f and (kit_path.parent / f).exists():
                os.replace(kit_path.parent / f, bad / f)
        rec = dict(kit)
        rec.update({"error": why, "failed": now_iso()})
        write_json(bad / kit_path.name, rec)
        kit_path.unlink(missing_ok=True)
        self.say(f"{ch.name}: FAILED '{kit.get('title')}': {why} (fix it and run: upload_videos.py retry)")

    def write_status(self, state: str, counts: Dict[str, int]) -> None:
        chans = []
        for ch in channels(self.root):
            tok = read_json(ch / ".token.json", {}) or {}
            chans.append({"name": ch.name, "signed_in_as": tok.get("channel_title", ""), "ready": len(list((ch / "ready").glob("*.json"))),
                          "uploaded_today": uploads_today(ch), "failed": len(list((ch / "failed").glob("*.json"))),
                          "note": self.last.get(ch.name, "")})
        st = {"computer": socket.gethostname(), "state": state, "heartbeat": now_iso(), "heartbeat_ts": time.time(),
              "last_round": counts, "channels": chans}
        write_json(self.root / "_status" / "status.json", st)
        lines = [f"Uploader on {st['computer']}: {state} (checked {time.strftime('%Y-%m-%d %H:%M')})", ""]
        for c in chans:
            lines.append(f"{c['name']}: {c['ready']} waiting, {c['uploaded_today']} uploaded today, {c['failed']} failed"
                         + (f" | signed in as {c['signed_in_as']}" if c["signed_in_as"] else " | NOT signed in")
                         + (f" | {c['note']}" if c["note"] else ""))
        try:
            (self.root / "_status" / "STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass


def keep_awake() -> Any:
    if sys.platform == "darwin":
        try:
            return subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return None
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        except Exception:
            pass
    return None


def single_instance() -> Optional[socket.socket]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def watch(root: Path, interval: int = DEFAULT_INTERVAL, once: bool = False, say: Callable[[str], None] = print) -> int:
    lock = single_instance()
    if lock is None:
        say("the uploader is already running on this computer")
        return 1
    keep_awake()
    w = Watcher(root, say=say)
    w.say(f"uploader started on {socket.gethostname()}; folder {root}; checking every {interval // 60} min")
    seen_now = control(root).get("now")
    try:
        while True:
            try:
                w.cycle()
            except Exception as exc:
                w.say(f"round failed: {exc!r}; trying again later")
            if once:
                return 0
            deadline = time.time() + interval
            while time.time() < deadline:            # commands from the Mac are picked up within CONTROL_POLL seconds
                time.sleep(CONTROL_POLL)
                c = control(root)
                if c.get("now") != seen_now or (c.get("retry") and c.get("retry") != w.state.get("retry_seen")):
                    seen_now = c.get("now")
                    w.say("checking now (asked from " + str(c.get("changed_on") or "another computer") + ")")
                    break
                if c.get("paused"):
                    w.write_status("paused from " + str(c.get("changed_on") or "another computer"), {})
    except KeyboardInterrupt:
        w.say("uploader stopped")
        return 0
    finally:
        lock.close()


# ---------------------------------------------------------------- start at log-in

def autostart(root: Path, remove: bool = False) -> str:
    script = Path(__file__).resolve()
    if os.name == "nt":
        name = "YouTube Uploader"
        if remove:
            subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"], check=False)
            return "removed the Windows task"
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        runner = pyw if pyw.is_file() else exe
        cmd = f'"{runner}" "{script}" --root "{root}" watch'
        subprocess.run(["schtasks", "/Create", "/TN", name, "/SC", "ONLOGON", "/TR", cmd, "/RL", "LIMITED", "/F"], check=True)
        subprocess.run(["schtasks", "/Run", "/TN", name], check=False)
        return f"Windows task '{name}' made: the uploader starts at every log-in (and is running now)"
    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.youtube-uploader.watch.plist"
        if remove:
            subprocess.run(["launchctl", "unload", str(plist)], check=False)
            plist.unlink(missing_ok=True)
            return "removed the start-at-log-in item"
        log = LOCAL / "watch.log"
        LOCAL.mkdir(parents=True, exist_ok=True)
        plist.parent.mkdir(parents=True, exist_ok=True)
        args = "".join(f"<string>{x}</string>" for x in (sys.executable, str(script), "--root", str(root), "watch"))
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.youtube-uploader.watch</string>
<key>ProgramArguments</key><array>{args}</array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{log}</string><key>StandardErrorPath</key><string>{log}</string>
</dict></plist>
""", encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist)], check=False, stderr=subprocess.DEVNULL)
        subprocess.run(["launchctl", "load", str(plist)], check=True)
        return f"start-at-log-in item made ({plist}); the uploader is running now"
    raise UploadError("autostart is made for Windows and macOS only; run: upload_videos.py watch")


# ---------------------------------------------------------------- status from anywhere

def status_text(root: Path) -> str:
    st = read_json(root / "_status" / "status.json")
    c = control(root)
    lines = []
    if not st:
        lines.append("The uploading computer has not reported yet (is 'watch' running there, and is the folder syncing?)")
    else:
        age = time.time() - float(st.get("heartbeat_ts", 0))
        alive = "OK" if age < HEARTBEAT_STALE else f"NO NEWS FOR {age / 60:.0f} MIN (off, asleep or not syncing?)"
        lines.append(f"Uploader on {st.get('computer')}: {st.get('state')} - last seen {st.get('heartbeat')} [{alive}]")
    if c.get("paused"):
        lines.append("PAUSED (resume with: upload_videos.py resume)")
    lines.append("")
    for ch in channels(root):
        tok = read_json(ch / ".token.json", {}) or {}
        ready = len(list((ch / "ready").glob("*.json")))
        failed = sorted((ch / "failed").glob("*.json"))
        lines.append(f"{ch.name}: {ready} waiting, {uploads_today(ch)} uploaded today, {len(failed)} failed"
                     + (f" | signed in as {tok.get('channel_title')}" if tok.get("channel_title") else " | NOT signed in"))
        for f in failed[:5]:
            d = read_json(f, {}) or {}
            lines.append(f"    failed: {d.get('title')}: {d.get('error')}")
        last = sorted((ch / "uploaded").glob("*.json"))[-3:]
        for f in last:
            d = read_json(f, {}) or {}
            lines.append(f"    uploaded {d.get('uploaded', '')[:16]}: {d.get('title')} {d.get('url')} [{d.get('privacy', '')}]")
    return "\n".join(lines)


# ---------------------------------------------------------------- command line

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="upload_videos.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--root", default="", help="the shared channels folder (default: the one saved by setup)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="choose the shared channels folder on this computer")
    s.add_argument("folder", nargs="?", default="")
    a_ = sub.add_parser("add", help="add a channel")
    a_.add_argument("name")
    a_.add_argument("--kids", action="store_true", help="videos are made for kids")
    a_.add_argument("--tags", default="", help="default tags, comma separated")
    lg = sub.add_parser("login", help="sign a channel in (once)")
    lg.add_argument("name")
    lg.add_argument("--paste", action="store_true", help="paste the address after Allow (when the tab cannot reach this computer)")
    lg.add_argument("--open", action="store_true", help="also open the link in the default browser")
    eq = sub.add_parser("enqueue", help="put a finished video in a channel's queue")
    eq.add_argument("name")
    eq.add_argument("video")
    eq.add_argument("--title", default="")
    eq.add_argument("--description", default="")
    eq.add_argument("--description-file", default="")
    eq.add_argument("--tags", default="")
    eq.add_argument("--thumbnail", default="")
    eq.add_argument("--publish-at", default="", help="e.g. \"2026-11-25 17:00\" in the channel's time zone (else its schedule)")
    w = sub.add_parser("watch", help="upload everything that arrives (the uploading computer)")
    w.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="seconds between checks")
    w.add_argument("--once", action="store_true")
    au = sub.add_parser("autostart", help="run 'watch' at every log-in on this computer")
    au.add_argument("--remove", action="store_true")
    sub.add_parser("status", help="what the uploader is doing")
    sub.add_parser("pause", help="stop uploading (after the current video)")
    sub.add_parser("resume", help="go on uploading")
    sub.add_parser("now", help="check for new videos right away")
    rt = sub.add_parser("retry", help="try the failed videos again")
    rt.add_argument("names", nargs="*")
    sub.add_parser("channels", help="list the channels")
    a = p.parse_args(argv)
    try:
        if a.cmd == "setup":
            folder = a.folder or a.root
            if not folder:
                print("give the folder: upload_videos.py setup \"<Google Drive>/YouTube Channels\"", file=sys.stderr)
                return 2
            root = setup_root(Path(folder).expanduser().resolve())
            print(f"channels folder on this computer: {root}")
            if not (root / "client_secret.json").exists():
                print(f"next: put the Google Cloud Desktop-app key at {root / 'client_secret.json'}")
            return 0
        root = find_root(a.root)
        if a.cmd == "add":
            ch = add_channel(root, a.name, a.kids, clean_tags(a.tags))
            print(f"channel folder: {ch}\nsettings: {ch / 'channel.json'}\nnext: upload_videos.py login \"{ch.name}\"")
        elif a.cmd == "login":
            info = login(root, a.name, paste=a.paste, open_browser=a.open)
            print(f"\nsigned in: '{info['title']}' ({info['id']}). Uploads for '{a.name}' go to this channel.")
        elif a.cmd == "enqueue":
            desc = Path(a.description_file).expanduser().read_text(encoding="utf-8") if a.description_file else a.description
            kit = enqueue(root, a.name, a.video, a.title, desc, a.tags, a.thumbnail, publish_at=a.publish_at)
            print(f"queued: {kit}")
        elif a.cmd == "watch":
            return watch(root, max(60, a.interval), a.once)
        elif a.cmd == "autostart":
            print(autostart(root, a.remove))
        elif a.cmd == "status":
            print(status_text(root))
        elif a.cmd == "pause":
            send_control(root, paused=True)
            print("paused: the uploader stops after the video it is on (within a minute once synced)")
        elif a.cmd == "resume":
            send_control(root, paused=False, now=now_iso())
            print("resumed")
        elif a.cmd == "now":
            send_control(root, now=now_iso())
            print("asked the uploader to check now")
        elif a.cmd == "retry":
            if a.names:
                print(f"{retry_failed(root, a.names)} video(s) put back in ready/")
            else:
                send_control(root, retry=now_iso(), now=now_iso())
                print("asked the uploader to try the failed videos again")
        elif a.cmd == "channels":
            for ch in channels(root):
                tok = read_json(ch / ".token.json", {}) or {}
                print(f"{ch.name}: " + (f"signed in as {tok.get('channel_title')}" if tok else "NOT signed in"))
        return 0
    except UploadError as exc:
        print(f"upload_videos: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
