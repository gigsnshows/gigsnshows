#!/usr/bin/env python3
"""
Read sources.yaml, pull listings from every source, merge, dedupe, and write
data/events.json for the dashboard.

    python run.py                 normal run
    python run.py --dry-run       show counts, don't write
    python run.py --only District only run sources whose name contains this (wherever it runs)
    python run.py --remerge       re-merge this machine's last results into the current
                                  events.json (after another collector uploaded first)
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

import health
from scrapers.base import NOT_SHOWS, get_html, now_iso
from scrapers import seo, sharepages
from scrapers.genres import catalog, language, languages, tag
from scrapers.parsers import PARSERS

# Which machine this run is on: "aws" (the Lightsail server), "mac" or "github" (Actions).
# Some sites refuse some of them, so each source's `runs_on` in sources.yaml says where it's read.
WHERE = os.environ.get("COLLECTOR") or ("github" if os.environ.get("GITHUB_ACTIONS") == "true" else "mac")
DEFAULT_RUNS_ON = ["aws", "github"]

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "events.json"
FRESH = ROOT / "data" / ".fresh.json"  # this machine's latest results, kept for --remerge (not committed)


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


def drop_tour_hubs(events):
    """
    BookMyShow lists a touring act's general page ("...-india-tour/<id>") under every city, each copy with the
    tour's FIRST date. When the tour also has a page per city, those carry the real dates and the general
    page's copies are wrong, so they're dropped (Diljit's tour: 21 Nov is Ahmedabad's date, but it showed for
    Mumbai, whose show is 27 Nov). A general page with no per-city pages is kept: it's all we know.
    """
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())  # noqa: E731
    cities = defaultdict(set)
    titles = defaultdict(set)
    for e in events:
        cities[(e["source"], e["url"])].add(e["city"])
        titles[(e["source"], e["url"])].add(norm(e["title"]))
    hubs = set()
    for key, cs in cities.items():
        if len(cs) < 2:
            continue
        src, url = key
        if any(e["source"] == src and e["url"] != url and any(t and norm(e["title"]).startswith(t) for t in titles[key]) for e in events):
            hubs.add(key)
    if hubs:
        gone = [e for e in events if (e["source"], e["url"]) in hubs]
        print(f"\nDropped {len(gone)} copies of {len(hubs)} general tour page(s) that have their own city pages: "
              + "; ".join(sorted({e["title"] for e in gone})))
    return [e for e in events if (e["source"], e["url"]) not in hubs]


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
            m["lang"] = m.get("lang", []) + [x for x in e.get("lang", []) if x not in m.get("lang", [])]
        else:
            e["sources"] = [e["source"]]
            e["links"] = {e["source"]: e["url"]}
            merged[e["id"]] = e
    return list(merged.values())


def main(dry_run=False, only=None, remerge=False):
    sources = yaml.safe_load((ROOT / "sources.yaml").read_text())
    today = date.today().isoformat()
    collected, failed, ran = [], {}, []  # failed: source -> cities whose pages all came back empty; ran: sources read
    if remerge:
        fresh = json.loads(FRESH.read_text())
        collected, failed, ran = fresh["events"], {k: set(v) for k, v in fresh["failed"].items()}, fresh.get("ran", [])

    for src in [] if remerge else sources:
        if only and only.lower() not in src["name"].lower():
            continue
        runs_on = src.get("runs_on", DEFAULT_RUNS_ON)
        if not only and WHERE not in runs_on:
            print(f"\n{src['name']}  (skipped here on {WHERE}; read on {' and '.join(runs_on)})")
            continue
        parser = PARSERS[src.get("parser", "jsonld")]
        ran.append(src["name"])
        print(f"\n{src['name']}  ({src.get('parser', 'jsonld')}{', rendered' if src.get('render') else ''})")
        tried, ok = set(), set()
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
            tried.add(city)
            if evs:
                ok.add(city)
        # Per city only for sources read city by city: a site that starts refusing partway
        # through a run (BookMyShow, after a few cities) shouldn't wipe the cities it didn't answer.
        if "cities" in src and ok and tried - ok:
            failed[src["name"]] = tried - ok
            print(f"  (no results for {', '.join(sorted(tried - ok))}; keeping their earlier shows)")
    if not remerge and not dry_run:
        FRESH.write_text(json.dumps({"events": collected, "failed": {k: sorted(v) for k, v in failed.items()}, "ran": ran},
                                    ensure_ascii=False))

    previous = json.loads(OUT.read_text()) if OUT.exists() else {}
    is_sample = str(previous.get("updated_at", "")).startswith("SAMPLE")

    # A source that came back empty (blocked, down, or skipped here) keeps its last known
    # upcoming shows rather than vanishing from the dashboard; so does a city it didn't answer.
    refreshed = {e["source"] for e in collected}
    stale = {s["name"] for s in sources} - refreshed
    covered = lambda src, e: src in refreshed and e["city"] not in failed.get(src, ())  # noqa: E731
    carried = [] if is_sample else [
        e for e in previous.get("events", [])
        if e["date"] >= today and not any(covered(src, e) for src in e.get("sources", [e["source"]]))
        and not NOT_SHOWS.search(e["title"])
    ]
    for e in carried:
        e.pop("sources", None)
        e.pop("links", None)
    if stale:
        print(f"\nNo fresh results from: {', '.join(sorted(stale))} — keeping {len(carried)} of their earlier upcoming shows")

    upcoming = drop_tour_hubs([e for e in collected if e["date"] >= today] + carried)
    merged = dedupe(upcoming)
    merged.sort(key=lambda e: (e["date"], e["time"]))
    print(f"\n{len(collected)} scraped + {len(carried)} kept -> {len(merged)} unique upcoming events")

    if dry_run:
        return
    # What each source returned this time, for the scheduled health check (even when it's nothing).
    health.record(ran, collected, failed, today, WHERE, len(merged))
    if not merged:
        print("Nothing found; leaving the existing events.json untouched.")
        return

    # first_seen powers the dashboard's "New" tray: a show keeps the date it first showed
    # up in this file; one that's genuinely new today gets stamped with today.
    fallback_seen = today if is_sample else str(previous.get("updated_at", today))[:10]
    prev_seen = {} if is_sample else {e["id"]: e.get("first_seen", fallback_seen) for e in previous.get("events", [])}
    for e in merged:
        e["first_seen"] = prev_seen.get(e["id"], today)
        if "lang" not in e:  # shows carried over from before languages were read: re-tag them
            e["lang"] = language(e["category"], e["title"], e.get("about", ""), e["venue"])
            e["genres"] = tag(e["category"], e["title"], f"{e.get('about', '')} {e['venue']}", e["lang"])

    OUT.parent.mkdir(exist_ok=True)
    cities = sorted({e["city"] for e in merged})
    OUT.write_text(json.dumps({"updated_at": now_iso(), "cities": cities, "genres": catalog(), "languages": languages(),
                               "count": len(merged), "events": merged}, indent=2, ensure_ascii=False))
    print(f"wrote {OUT}")
    cname = ROOT / "CNAME"
    sharepages.write(merged, ROOT, f"https://{cname.read_text().strip()}" if cname.exists() else "")
    print(f"wrote share pages to {ROOT / 's'}")
    n_shows, n_cities = seo.write(merged, ROOT, today)
    print(f"wrote {n_shows} show pages, {n_cities} city pages, sitemap.xml and robots.txt")


if __name__ == "__main__":
    args = sys.argv[1:]
    only = args[args.index("--only") + 1] if "--only" in args else None
    main(dry_run="--dry-run" in args, only=only, remerge="--remerge" in args)
