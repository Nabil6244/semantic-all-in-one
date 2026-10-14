"""One secure-connection setup for every Weather download, so a certificate problem on someone's computer never stops a video.

It trusts what the operating system trusts (on Windows the same certificate store Chrome and Edge use — including the
certificate an antivirus or a company network installs to inspect HTTPS), AND the public roots shipped with the app (certifi:
a packaged macOS app has no other certificate list). A server is still verified: nothing here turns verification off."""

from __future__ import annotations

import ssl
from functools import lru_cache


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()   # the system's store (Windows: ROOT and CA stores)
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except Exception:   # no certifi: the system's store alone
        pass
    return ctx
