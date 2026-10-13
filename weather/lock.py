"""The password that unlocks the Weather style in Settings > General.

Only a salted PBKDF2 hash of the password is kept here (UNLOCK_HASH). Set or change the password on your own machine with

    .venv310/bin/python -m weather.lock

which asks for it twice (nothing is shown as you type) and rewrites UNLOCK_HASH in this file. With no hash set, Weather stays locked.

Turning the switch on with the right password saves weather_enabled plus an unlock token (derived from the hash) in settings.json;
Weather counts as on only when both are there, so flipping weather_enabled by hand in settings.json does not unlock it."""

from __future__ import annotations

import hashlib
import hmac
import re
import sys
from pathlib import Path

SALT = b"semantic-yt-studio/weather/unlock/v1"
ITERATIONS = 200_000
UNLOCK_HASH = "c6d73923b512c6057e304c345c4ae8307da5b6ed09b767fcbfc8a85550b4ab6e"  # set by `python -m weather.lock`
SETTING_TOKEN = "weather_unlock"


def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SALT, ITERATIONS).hex()


def has_password() -> bool:
    return bool(UNLOCK_HASH)


def check(password: str) -> bool:
    return has_password() and hmac.compare_digest(hash_password(password or ""), UNLOCK_HASH)


def token() -> str:
    """What settings.json keeps while Weather is unlocked (changes whenever the password changes)."""
    return hashlib.sha256(f"weather-on:{UNLOCK_HASH}".encode("utf-8")).hexdigest()[:32] if has_password() else ""


def unlocked(settings) -> bool:
    t = str((settings or {}).get(SETTING_TOKEN) or "")
    return has_password() and hmac.compare_digest(t, token())


def set_password(password: str, path: Path = Path(__file__)) -> None:
    """Rewrite UNLOCK_HASH in this file."""
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(r'^UNLOCK_HASH = "[0-9a-f]*"', f'UNLOCK_HASH = "{hash_password(password)}"', text, count=1, flags=re.M)
    if n != 1:
        raise RuntimeError(f"UNLOCK_HASH not found in {path}")
    path.write_text(new, encoding="utf-8")


def main() -> int:
    import getpass

    first = getpass.getpass("New Weather password: ")
    if len(first) < 4:
        print("Too short (at least 4 characters). Nothing changed.")
        return 1
    if getpass.getpass("Type it again: ") != first:
        print("The two did not match. Nothing changed.")
        return 1
    set_password(first)
    print("Saved (only its hash is in weather/lock.py). Turn Weather on again in Settings > General with the new password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
