"""Record weather/testdata/automation/prep_recording.json.gz for test_weather_auto_prep.py: one real prep, every NWS and GIBS answer kept.
Run between about 5:30 AM and 9 PM Central (NWS forecasts are too old overnight):  python -m weather.automation.record"""
import gzip, json, tempfile
from datetime import datetime, timezone
from pathlib import Path

from weather.automation.prep import prep
from weather.cache import HttpCache
from weather.nws import NwsClient, urllib_fetch
from weather.resolve import _gibs_get
R = {}
def fetch(url, headers):
    r = urllib_fetch(url, headers); R[url] = [r.status, r.body.decode("utf-8")]; return r
def gibs(url):
    t = _gibs_get(url); R[url] = [200, t]; return t
now = datetime.now(timezone.utc).replace(microsecond=0)
c = NwsClient("https://example.invalid", cache=HttpCache(Path(tempfile.mkdtemp())), fetch=fetch)
res = prep(tempfile.mkdtemp(), now=now, client=c, gibs_get=gibs, log=print)
print(res.summary, len(R))
Path("weather/testdata/automation/prep_recording.json.gz").write_bytes(gzip.compress(json.dumps({"now": now.isoformat(), "responses": R}).encode()))
