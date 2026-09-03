"""CLI entry point.

    python -m app.cli.main research --topic "..." --domain real_estate --output ./research_output
    python -m app.cli.main research --script ./script.txt --domain auto --output ./research_output
    python -m app.cli.main research --url "https://example.com/listing" --output ./research_output
    python -m app.cli.main inspect ./research_output
    python -m app.cli.main download ./research_output --output ./research_output/media

By default `research` is a discovery-only pass (candidates are ranked but
not fetched) — pass --download to fetch media inline, or run `download`
against the resulting package afterwards.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.dedup.media import MediaDeduplicator
from app.discovery.search import DuckDuckGoSearchProvider, NullSearchProvider, SearchProvider, TavilySearchProvider
from app.extraction.webpage import (
    Crawl4AIProvider,
    CrawlProvider,
    EscalatingCrawlProvider,
    FirecrawlProvider,
    HttpxCrawlProvider,
)
from app.media.downloader import download_media
from app.models.research import ResearchInput
from app.research.planner import guess_domain
from app.research.property_researcher import PropertyResearcher
from app.research.researcher import Researcher
from app.storage.cache import ResearchCache
from app.storage.media_manifest import write_media_manifest
from app.storage.package import load_package, summarize_package, write_package


def _build_crawl_provider(name: str) -> CrawlProvider:
    if name == "crawl4ai":
        return Crawl4AIProvider()
    if name == "firecrawl":
        return FirecrawlProvider()
    if name == "auto":
        return EscalatingCrawlProvider(primary=HttpxCrawlProvider(), secondary=Crawl4AIProvider())
    return HttpxCrawlProvider()


def _resolve_domain(args: argparse.Namespace) -> str:
    domain = args.domain or "auto"
    if domain != "auto":
        return domain
    text = " ".join(filter(None, [args.topic, "\n".join(args.url or [])]))
    if args.script:
        script_path = Path(args.script)
        if script_path.exists():
            text += " " + script_path.read_text(encoding="utf-8")
    return guess_domain(text) if text.strip() else "unknown"


def _build_search_provider(name: str) -> SearchProvider:
    if name == "tavily":
        return TavilySearchProvider()
    if name == "duckduckgo":
        return DuckDuckGoSearchProvider()
    return NullSearchProvider()


def cmd_research(args: argparse.Namespace) -> int:
    script_text = None
    if args.script:
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"error: script file not found: {args.script}", file=sys.stderr)
            return 1
        script_text = script_path.read_text(encoding="utf-8")

    resolved_domain = _resolve_domain(args)
    research_input = ResearchInput(
        topic=args.topic,
        script=script_text,
        urls=args.url or [],
        domain=args.domain or "auto",
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = None
    if not args.no_cache:
        cache = ResearchCache(output_dir / ".cache" / "research_cache.db")

    use_property_pipeline = resolved_domain == "real_estate" and not args.no_property_pipeline

    try:
        if use_property_pipeline:
            # For --provider auto: primary is always the cheap httpx one,
            # and the heavier provider is only invoked per-page when that
            # page's results look thin (see
            # property_researcher._maybe_escalate) — not unconditionally
            # for every page. Any other explicit --provider choice is
            # respected as-is (no separate escalation provider), same as
            # the general pipeline.
            if args.provider == "auto":
                primary_provider: CrawlProvider = HttpxCrawlProvider()
                escalation_provider = Crawl4AIProvider()
            else:
                primary_provider = _build_crawl_provider(args.provider)
                escalation_provider = None
            def _make_property_researcher():
                # A FRESH researcher per property (see property_job): its own
                # target identity, its own probe cache. Providers are shared
                # because they are stateless fetchers.
                return PropertyResearcher(
                    crawl_provider=primary_provider,
                    escalation_provider=escalation_provider,
                    search_provider=_build_search_provider(args.search),
                    cache=cache,
                    fetch_concurrency=args.concurrency,
                    download_concurrency=args.concurrency,
                    max_pages=args.max_pages,
                    max_media_per_property=args.max_media_per_property,
                    probe_media=not args.no_probe,
                    probe_concurrency=args.concurrency,
                    image_source=args.property_image_source,
                )

            if args.multi_property:
                # Each --url is a SEPARATE listing, researched independently
                # into properties/<property_id>/. Opt-in: without this flag
                # multiple --url values keep their existing meaning (several
                # pages about ONE property), so no existing invocation changes.
                # NB: no local re-imports of write_package/write_media_manifest
                # here — a function-local import of a name already bound at
                # module level makes it local for the WHOLE function, which
                # breaks the single-property path below with UnboundLocalError.
                from app.research.property_job import JOB_FILENAME, run_property_job

                job = asyncio.run(run_property_job(
                    urls=research_input.urls,
                    researcher_factory=_make_property_researcher,
                    output_dir=output_dir,
                    download=args.download,
                    topic=research_input.topic,
                    script=research_input.script,
                    write_package_fn=write_package,
                    write_manifest_fn=write_media_manifest,
                ))
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / JOB_FILENAME).write_text(
                    json.dumps(job.to_dict(), indent=2, default=str), encoding="utf-8",
                )
                for prop in job.properties:
                    status = "ok" if prop.ok else f"FAILED ({prop.error})"
                    print(f"  {prop.property_id}: {status} "
                          f"({len(prop.media())} media, {len(prop.facts())} facts) {prop.source_url}")
                print(f"Wrote {output_dir / JOB_FILENAME}")
                return 0

            property_researcher = _make_property_researcher()
            package = asyncio.run(
                property_researcher.run(research_input, output_dir=output_dir, download=args.download)
            )
        else:
            researcher = Researcher(
                crawl_provider=_build_crawl_provider(args.provider),
                search_provider=_build_search_provider(args.search),
                cache=cache,
                fetch_concurrency=args.concurrency,
                download_concurrency=args.concurrency,
                max_images=args.max_images,
                max_videos=args.max_videos,
                max_pages=args.max_pages,
                max_media_per_page=args.max_media_per_page,
                max_total_media=args.max_total_media,
                max_depth=args.max_depth,
            )
            package = asyncio.run(
                researcher.run(research_input, output_dir=output_dir, download=args.download)
            )
    finally:
        if cache is not None:
            cache.close()

    write_package(package, output_dir)
    print(summarize_package(package))
    if use_property_pipeline:
        print(f"\n(property-centric pipeline: target confidence={package.property.confidence:.2f})")
        manifest_path = write_media_manifest(package, output_dir)
        print(f"Media manifest: {manifest_path}")
    print(f"\nWritten to: {output_dir}")
    if not args.download:
        print("(discovery only — media not fetched; run `download` to fetch it)")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    try:
        package = load_package(Path(args.path))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(summarize_package(package))
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    try:
        package = load_package(Path(args.path))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    package_dir = Path(args.path) if Path(args.path).is_dir() else Path(args.path).parent
    media_dir = Path(args.output) if args.output else package_dir / "media"
    # `download_media` creates media_dir/images and media_dir/videos itself.

    to_download = [m for m in package.media if not m.downloaded]
    if not to_download:
        print("Nothing to download — all media already downloaded (or no media in this package).")
        return 0

    dedup = MediaDeduplicator()
    downloaded = asyncio.run(
        download_media(to_download, media_dir, concurrency=args.concurrency, dedup=dedup)
    )
    by_id = {m.media_id: m for m in downloaded}
    package.media = [by_id.get(m.media_id, m) for m in package.media]

    write_package(package, package_dir)
    print(summarize_package(package))
    if package.domain == "real_estate" and package.property.identity.confidence > 0:
        manifest_path = write_media_manifest(package, package_dir)
        print(f"Media manifest: {manifest_path}")
    print(f"\nMedia written to: {media_dir}")
    print(f"Package updated at: {package_dir}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.main", description="Semantic Research Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    research_p = subparsers.add_parser("research", help="Run a research pass and write a research package.")
    research_p.add_argument("--topic", type=str, default=None)
    research_p.add_argument("--script", type=str, default=None, help="Path to a script text file.")
    research_p.add_argument("--url", action="append", default=[], help="Direct URL to research (repeatable).")
    research_p.add_argument(
        "--multi-property", action="store_true",
        help="Treat every --url as a SEPARATE listing, researched independently into "
             "properties/<property_id>/ with its own facts and media. Without this "
             "flag multiple --url values keep their existing meaning: several pages "
             "about one property.",
    )
    research_p.add_argument(
        "--no-probe", action="store_true",
        help="Skip measuring real image dimensions. Probing reads only each image's "
             "header bytes (a few KB) and is what makes ranking pick the genuinely "
             "highest-resolution variant; without it, ranking falls back to whatever "
             "the page declared, which is often wrong or missing.",
    )
    research_p.add_argument("--domain", type=str, default="auto")
    research_p.add_argument("--output", type=str, required=True)
    research_p.add_argument("--provider", choices=["httpx", "crawl4ai", "firecrawl", "auto"], default="httpx",
                             help="Crawling backend. 'httpx' (default) needs no extra install. "
                                  "'auto' uses httpx and escalates to crawl4ai only for JS-shell pages.")
    research_p.add_argument("--search", choices=["none", "tavily", "duckduckgo"], default="none",
                             help="Search discovery backend for generated queries.")
    research_p.add_argument("--concurrency", type=int, default=5)
    research_p.add_argument("--max-images", type=int, default=12)
    research_p.add_argument("--max-videos", type=int, default=6)
    research_p.add_argument("--max-pages", type=int, default=12, help="Cap on total pages fetched.")
    research_p.add_argument("--max-media-per-page", type=int, default=20)
    research_p.add_argument("--max-total-media", type=int, default=30)
    research_p.add_argument("--max-depth", type=int, default=0,
                             help="Reserved for future link-following; V2 does not follow links (see README).")
    research_p.add_argument("--max-media-per-property", type=int, default=18,
                             help="V3 property-centric pipeline: cap on selected media for the target property "
                                  "(used instead of --max-images/--max-videos/--max-total-media when the "
                                  "resolved domain is real_estate).")
    research_p.add_argument(
        "--property-image-source", choices=["existing", "realtyapi", "both"], default="existing",
        help="Property Video pipeline only. 'existing' (default): current scrape-based "
             "acquisition, no RealtyAPI calls. 'realtyapi': RealtyAPI supplies the property "
             "photos (facts/other research signals are unaffected). 'both': RealtyAPI photos "
             "are added alongside the existing ones; the existing quality/variant pipeline "
             "picks the winner per photo. Reads the key from the REALTYAPI_API_KEY "
             "environment variable — never accepted as a CLI value.",
    )
    research_p.add_argument("--no-property-pipeline", action="store_true",
                             help="Force the general V2 multi-source pipeline even if the domain resolves to "
                                  "real_estate (V3's property-identity gating is skipped).")
    research_p.add_argument("--download", action="store_true",
                             help="Fetch selected media inline. Default is discovery-only "
                                  "(ranked candidates, nothing downloaded) — use the `download` "
                                  "command afterwards, or pass this flag.")
    research_p.add_argument("--discover", action="store_true",
                             help="No-op / explicit alias for the default discovery-only behavior.")
    research_p.add_argument("--no-cache", action="store_true")
    research_p.set_defaults(func=cmd_research)

    inspect_p = subparsers.add_parser("inspect", help="Print a summary of an existing research package.")
    inspect_p.add_argument("path", type=str, help="Path to a research_output directory or a research.json file.")
    inspect_p.set_defaults(func=cmd_inspect)

    download_p = subparsers.add_parser("download", help="Download media referenced by an existing research package.")
    download_p.add_argument("path", type=str, help="Path to a research_output directory or a research.json file.")
    download_p.add_argument("--output", type=str, default=None, help="Directory to save media into (default: <package>/media).")
    download_p.add_argument("--concurrency", type=int, default=5)
    download_p.set_defaults(func=cmd_download)

    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
