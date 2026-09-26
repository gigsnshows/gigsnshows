#!/usr/bin/env python3
"""
Read sources.yaml, pull listings from every source, merge, dedupe, and write
data/events.json for the dashboard.

    python run.py                 normal run
    python run.py --dry-run       show counts, don't write
    python run.py --only District only run sources whose name contains this
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import yaml

from scrapers.base import NOT_SHOWS, get_html, now_iso
from scrapers.genres import catalog, tag
from scrapers.parsers import PARSERS

# GitHub's servers get refused by some sites (cloud: false in sources.yaml); the Mac collector covers those.
IN_CLOUD = os.environ.get("GITHUB_ACTIONS") == "true"

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "events.json"


def as_list(v):
    return v if isinstance(v, list) else [v]


def expand(src):
    """
    Turn a source block into concrete entries. Each entry carries a list of
    candidate URLs (slugs in sources.yaml may be lists); the first candidate
    that yields events wins.
    """
    if "urls" in src:
        return [{**u, "urls": [u["url"]]} for u in src["urls"]]
    cats = src.get("categories") or {None: ""}
    out = []
    for city, cslugs in src.get("cities", {}).items():
        for cat, catslugs in cats.items():
            urls = [src["url"].format(city=c, category=k) for c in as_list(cslugs) for k in as_list(catslugs)]
            out.append({"urls": urls, "city": city, "category": cat})
    return out


def dedupe(events):
    """Same show on two platforms -> one entry that remembers every source."""
    merged = {}
    for e in events:
        if e["id"] in merged:
            m = merged[e["id"]]
            if e["source"] not in m["sources"]:
                m["sources"].append(e["source"])
                m["links"][e["source"]] = e["url"]
            m["image"] = m["image"] or e["image"]
            m["price_from"] = m["price_from"] or e["price_from"]
        else:
            e["sources"] = [e["source"]]
            e["links"] = {e["source"]: e["url"]}
            merged[e["id"]] = e
    return list(merged.values())


def main(dry_run=False, only=None):
    sources = yaml.safe_load((ROOT / "sources.yaml").read_text())
    today = date.today().isoformat()
    collected = []

    for src in sources:
        if only and only.lower() not in src["name"].lower():
            continue
        if IN_CLOUD and src.get("cloud") is False:
            print(f"\n{src['name']}  (skipped: refuses cloud servers; refreshed from the Mac)")
            continue
        parser = PARSERS[src.get("parser", "jsonld")]
        print(f"\n{src['name']}  ({src.get('parser', 'jsonld')}{', rendered' if src.get('render') else ''})")
        for entry in expand(src):
            city, cat = entry.get("city"), entry.get("category")
            evs = []
            for url in entry["urls"]:
                print(f"  {city or '-':10} {cat or 'all':8} {url}")
                html = get_html(url, src.get("render", False), src.get("wait_ms", 2500),
                                delay=src.get("crawl_delay", 0))
                if not html:
                    continue
                try:
                    evs = parser(html, url, src, entry)
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! parser error: {exc}")
                    evs = []
                print(f"      -> {len(evs)} events")
                if evs:
                    break
            collected.extend(evs)

    previous = json.loads(OUT.read_text()) if OUT.exists() else {}
    is_sample = str(previous.get("updated_at", "")).startswith("SAMPLE")

    # A source that came back empty (blocked, down, or skipped with --only) keeps its
    # last known upcoming shows rather than vanishing from the dashboard.
    refreshed = {e["source"] for e in collected}
    stale = {s["name"] for s in sources} - refreshed
    carried = [] if is_sample else [
        e for e in previous.get("events", [])
        if e["date"] >= today and not set(e.get("sources", [e["source"]])) & refreshed
        and not NOT_SHOWS.search(e["title"])
    ]
    for e in carried:
        e.pop("sources", None)
        e.pop("links", None)
    if stale:
        print(f"\nNo fresh results from: {', '.join(sorted(stale))} — keeping {len(carried)} of their earlier upcoming shows")

    upcoming = [e for e in collected if e["date"] >= today] + carried
    merged = dedupe(upcoming)
    merged.sort(key=lambda e: (e["date"], e["time"]))
    print(f"\n{len(collected)} scraped + {len(carried)} kept -> {len(merged)} unique upcoming events")

    if dry_run:
        return
    if not merged:
        print("Nothing found; leaving the existing events.json untouched.")
        return

    # first_seen powers the dashboard's "New" tray: a show keeps the date it first showed
    # up in this file; one that's genuinely new today gets stamped with today.
    fallback_seen = today if is_sample else str(previous.get("updated_at", today))[:10]
    prev_seen = {} if is_sample else {e["id"]: e.get("first_seen", fallback_seen) for e in previous.get("events", [])}
    for e in merged:
        e["first_seen"] = prev_seen.get(e["id"], today)
        if "genres" not in e:  # shows carried over from before genres existed
            e["genres"] = tag(e["category"], e["title"], e["venue"])

    OUT.parent.mkdir(exist_ok=True)
    cities = sorted({e["city"] for e in merged})
    OUT.write_text(json.dumps({"updated_at": now_iso(), "cities": cities, "genres": catalog(),
                               "count": len(merged), "events": merged}, indent=2, ensure_ascii=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    args = sys.argv[1:]
    only = args[args.index("--only") + 1] if "--only" in args else None
    main(dry_run="--dry-run" in args, only=only)
