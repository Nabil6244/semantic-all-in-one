"""upload_videos.py with a fake YouTube (no network)."""

import json
import os
import time
from pathlib import Path

import pytest

import upload_videos as U


class FakeYouTube:
    """Answers token, channels, resumable upload (in 308 steps) and thumbnail calls."""

    def __init__(self, quota=False, drop_once=False, audited=True):
        self.calls, self.received, self.quota, self.drop_once, self.bodies = [], 0, quota, drop_once, []
        self.audited = audited

    def __call__(self, method, url, headers=None, body=None, timeout=120):
        headers = headers or {}
        self.calls.append((method, url.split("?")[0]))
        if url.startswith(U.TOKEN_URI):
            return 200, {}, json.dumps({"access_token": "AT", "expires_in": 3600, "refresh_token": "RT"}).encode()
        if "/channels" in url:
            return 200, {}, json.dumps({"items": [{"id": "UC1", "snippet": {"title": "Food Files"}}]}).encode()
        if method == "POST" and "uploadType=resumable" in url:
            if self.quota:
                return 403, {}, json.dumps({"error": {"errors": [{"reason": "quotaExceeded"}], "message": "quota"}}).encode()
            self.bodies.append(json.loads(body))
            return 200, {"location": "https://www.googleapis.com/upload/session/1"}, b""
        if method == "PUT" and "/session/" in url:
            rng = headers["Content-Range"]
            total = int(rng.split("/")[1])
            if rng.startswith("bytes */"):
                return 308, ({"range": f"bytes=0-{self.received - 1}"} if self.received else {}), b""
            if self.drop_once:
                self.drop_once = False
                return 503, {}, b"busy"
            self.received += len(body)
            if self.received >= total:
                st = dict(self.bodies[-1]["status"]) if self.audited else {"privacyStatus": "private"}
                return 200, {}, json.dumps({"id": "VID123", "status": st}).encode()
            return 308, {"range": f"bytes=0-{self.received - 1}"}, b""
        if "thumbnails/set" in url:
            return 200, {}, b"{}"
        return 404, {}, b""


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "YouTube Channels"
    local = tmp_path / "local"
    monkeypatch.setattr(U, "LOCAL", local)
    monkeypatch.setattr(U, "CONFIG", local / "config.json")
    monkeypatch.setattr(U, "CHUNK", 256 * 1024)
    U.setup_root(root)
    (root / "client_secret.json").write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "cs"}}))
    ch = U.add_channel(root, "Food Files", tags=["food"])
    U.write_json(ch / ".token.json", {"refresh_token": "RT", "access_token": "AT", "expires_at": time.time() + 3600, "channel_title": "Food Files"})
    video = tmp_path / "film.mp4"
    video.write_bytes(os.urandom(700 * 1024))
    (tmp_path / "film.jpg").write_bytes(b"\xff\xd8jpg")
    return root, ch, local, video


def age(path: Path, seconds=60):
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_enqueue_writes_kit_and_thumbnail(env):
    root, ch, local, video = env
    kit_path = U.enqueue(root, "Food Files", video, "Why <Ketchup> Was Medicine", "desc", "ketchup, history")
    kit = json.loads(kit_path.read_text())
    assert kit["title"] == "Why Ketchup Was Medicine"
    assert kit["size"] == video.stat().st_size and len(kit["sha256"]) == 64
    assert kit["thumbnail"].endswith(".jpg") and (ch / "ready" / kit["thumbnail"]).is_file()
    assert kit["tags"] == ["ketchup", "history"]


def test_kit_waits_for_sync(env):
    root, ch, local, video = env
    kit_path = U.enqueue(root, "Food Files", video, "T")
    kit = json.loads(kit_path.read_text())
    v = ch / "ready" / kit["video"]
    data = v.read_bytes()
    v.write_bytes(data[:1000])                       # half synced
    age(v)
    assert U.kit_ready(ch, kit_path, local)[0] is None
    v.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))  # right size, wrong bytes
    age(v)
    k, why = U.kit_ready(ch, kit_path, local)
    assert k is None and "checksum" in why
    v.write_bytes(data)
    age(v)
    assert U.kit_ready(ch, kit_path, local)[0] is not None


def test_watcher_uploads_private_and_cleans_up(env, monkeypatch):
    root, ch, local, video = env
    yt = FakeYouTube(drop_once=True)
    monkeypatch.setattr(U, "_request", yt)
    monkeypatch.setattr(U.time, "sleep", lambda s: None)
    kit_path = U.enqueue(root, "Food Files", video, "Why Ketchup", "story", "ketchup")
    for f in (ch / "ready").iterdir():
        age(f)
    w = U.Watcher(root, say=lambda m: None, local=local)
    counts = w.cycle()
    assert counts["uploaded"] == 1
    assert yt.received == video.stat().st_size
    body = yt.bodies[0]
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert body["snippet"]["tags"] == ["ketchup", "food"]
    assert not list((ch / "ready").iterdir())        # copies removed
    rec = json.loads((ch / "uploaded" / kit_path.name).read_text())
    assert rec["url"] == "https://youtu.be/VID123"
    assert ("POST", U.UPLOAD_API + "/thumbnails/set") in yt.calls
    st = json.loads((root / "_status" / "status.json").read_text())
    assert st["channels"][0]["uploaded_today"] == 1
    assert "Food Files" in U.status_text(root)


def test_quota_stops_until_reset(env, monkeypatch):
    root, ch, local, video = env
    monkeypatch.setattr(U, "_request", FakeYouTube(quota=True))
    U.enqueue(root, "Food Files", video, "A")
    for f in (ch / "ready").iterdir():
        age(f)
    w = U.Watcher(root, say=lambda m: None, local=local)
    assert w.cycle()["uploaded"] == 0
    assert len(list((ch / "ready").glob("*.json"))) == 1   # kept for later
    assert w.quota_blocked(str(root / "client_secret.json")) > time.time()


def test_pause_from_another_computer(env, monkeypatch):
    root, ch, local, video = env
    yt = FakeYouTube()
    monkeypatch.setattr(U, "_request", yt)
    U.enqueue(root, "Food Files", video, "A")
    U.send_control(root, paused=True)
    w = U.Watcher(root, say=lambda m: None, local=local)
    w.cycle()
    assert not yt.calls
    assert "PAUSED" in U.status_text(root)


def test_permanent_error_goes_to_failed_and_retry(env, monkeypatch):
    root, ch, local, video = env

    def bad(method, url, headers=None, body=None, timeout=120):
        return 400, {}, json.dumps({"error": {"errors": [{"reason": "invalidTitle"}], "message": "bad title"}}).encode()

    monkeypatch.setattr(U, "_request", bad)
    U.enqueue(root, "Food Files", video, "A")
    for f in (ch / "ready").iterdir():
        age(f)
    U.Watcher(root, say=lambda m: None, local=local).cycle()
    assert len(list((ch / "failed").glob("*.json"))) == 1
    assert U.retry_failed(root) == 1
    assert len(list((ch / "ready").glob("*.json"))) == 1 and len(list((ch / "ready").glob("*.mp4"))) == 1


def test_tags_limit_and_titles():
    tags = U.clean_tags([f"tag number {i}" for i in range(100)])
    assert sum(len(t) + 2 for t in tags) + len(tags) - 1 <= 500
    assert len(U.clean_title("word " * 40)) <= 100
    assert U.next_quota_reset() > time.time()


def test_login_paste_flow(env, monkeypatch):
    root, ch, local, video = env
    (ch / ".token.json").unlink()
    monkeypatch.setattr(U, "_request", FakeYouTube())
    monkeypatch.setattr(U, "copy_to_clipboard", lambda t: True)
    seen = {}

    def ask(prompt):
        from urllib.parse import parse_qs, urlparse
        state = parse_qs(urlparse(seen["url"]).query)["state"][0]
        return f"http://127.0.0.1:8/?state={state}&code=4/abc"

    def say(m):
        if m.startswith(U.AUTH_URI):
            seen["url"] = m.strip()

    info = U.login(root, "Food Files", paste=True, say=say, ask=ask)
    assert info["title"] == "Food Files"
    tok = json.loads((ch / ".token.json").read_text())
    assert tok["refresh_token"] == "RT" and tok["channel_id"] == "UC1"


def test_make_video_batch_reads_channel_columns(tmp_path):
    import make_video as M
    f = tmp_path / "b.csv"
    f.write_text("style,voice,title,channel,tags,thumbnail\nexplainer,vo.mp3,T,Food Files,\"a,b\",t.jpg\n")
    rows = M.read_batch(f)
    assert rows[0]["channel"] == "Food Files" and rows[0]["tags"] == "a,b"
    assert rows[0]["thumbnail"] == str((tmp_path / "t.jpg").resolve())


def _ready(root, ch, video, **kw):
    U.enqueue(root, "Food Files", video, "A", **kw)
    for f in (ch / "ready").iterdir():
        age(f)


def _set(ch, **cfg):
    d = json.loads((ch / "channel.json").read_text())
    d.update(cfg)
    (ch / "channel.json").write_text(json.dumps(d))


def test_next_slot_skips_taken_and_lead_time():
    from datetime import datetime, timezone
    cfg = {"schedule": {"times": ["17:00", "09:00"], "timezone": "UTC"}}
    now = datetime(2026, 11, 23, 16, 30, tzinfo=timezone.utc)            # 17:00 today is under the 60 min lead
    first = U.next_slot(cfg, [], now)
    assert first == datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
    assert U.next_slot(cfg, [first], now) == datetime(2026, 11, 24, 17, 0, tzinfo=timezone.utc)
    cfg["schedule"]["days"] = ["sat"]
    assert U.next_slot(cfg, [], now).weekday() == 5
    off = {"schedule": {"times": ["17:00"], "utc_offset": "+04:00"}}
    assert U.next_slot(off, [], now).hour == 13
    assert U.next_slot({"schedule": {}}, [], now) is None


def test_scheduled_upload_sets_publish_at(env, monkeypatch):
    root, ch, local, video = env
    yt = FakeYouTube()
    monkeypatch.setattr(U, "_request", yt)
    _set(ch, schedule={"times": ["17:00"], "timezone": "UTC"})
    _ready(root, ch, video)
    U.Watcher(root, say=lambda m: None, local=local).cycle()
    st = yt.bodies[0]["status"]
    assert st["privacyStatus"] == "private" and st["publishAt"].endswith(":00Z")
    rec = json.loads(next((ch / "uploaded").glob("*.json")).read_text())
    assert rec["publish_at"] and rec["privacy"].startswith("scheduled")
    _ready(root, ch, video)                                                 # the next video takes the next day's slot
    U.Watcher(root, say=lambda m: None, local=local).cycle()
    assert yt.bodies[1]["status"]["publishAt"] != st["publishAt"]


def test_public_and_unaudited_project_note(env, monkeypatch):
    root, ch, local, video = env
    yt = FakeYouTube(audited=False)
    monkeypatch.setattr(U, "_request", yt)
    _set(ch, privacy="public")
    _ready(root, ch, video)
    U.Watcher(root, say=lambda m: None, local=local).cycle()
    assert yt.bodies[0]["status"]["privacyStatus"] == "public"
    rec = json.loads(next((ch / "uploaded").glob("*.json")).read_text())
    assert rec["privacy"] == "private" and any("audit" in n for n in rec["notes"])


def test_own_publish_time_from_enqueue(env, monkeypatch):
    root, ch, local, video = env
    yt = FakeYouTube()
    monkeypatch.setattr(U, "_request", yt)
    _set(ch, schedule={"times": ["17:00"], "utc_offset": "+04:00"})
    _ready(root, ch, video, publish_at="2030-01-02 20:00")
    U.Watcher(root, say=lambda m: None, local=local).cycle()
    assert yt.bodies[0]["status"]["publishAt"] == "2030-01-02T16:00:00Z"
