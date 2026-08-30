# Vendored research engine (lightweight core only)

This is the `app/` package from the standalone `semantic-research-engine`
project, vendored directly into this repo so Manual Research works with zero
external setup — no separate checkout, no user-configured "Engine
folder"/"Python interpreter" fields.

**Only the engine's core dependencies are used: `pydantic`, `httpx`,
`beautifulsoup4`, `lxml`, `imagesize`, `chompjs`** (all listed in this
project's top-level `requirements.txt`). The engine's optional Crawl4AI
extra (real-browser crawling via Playwright, ~700MB with its own
transitive deps: litellm, openai, scipy, networkx, ...) is **not** vendored
and is not needed: the CLI's `--provider` flag already defaults to
`"httpx"` ("needs no extra install" — see `app/cli/main.py`), and
`research/property_provider.py` has never passed `--provider crawl4ai`, so
this is not a behavior change from how the app already used the external
engine — only a change in *where* the code lives.

Run via `research/settings.py::load_engine_config()`, which points at this
directory using the running process's own Python interpreter automatically
— unless overridden in Settings, or unless the app is a frozen/packaged
build (see the docstring there: a PyInstaller executable can't be invoked
as `<exe> -m some.module` the way a real `python` binary can, so packaged
builds still need an explicit external engine configured until a bundled
interpreter exists for this — tracked separately, not part of this change).

To pick up a newer version of the upstream engine, re-sync just the `app/`
package here (this README, and this repo's own requirements.txt, are not
part of that upstream project and should not be overwritten).
