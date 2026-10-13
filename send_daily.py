#!/usr/bin/env python3
"""
Builds today's daily picks email and hands it to Buttondown.

    python send_daily.py              make a DRAFT in Buttondown (nothing goes to subscribers; you read it there and press Send)
    python send_daily.py --send       send it to everyone now
    python send_daily.py --dry-run    build it and print what would be sent (no key needed)

The API key is read from the BUTTONDOWN_API_KEY environment variable (the server keeps it in ~/.buttondown.env, never in this
repository). Safety checks: it won't run twice in a day (marker file data/.daily-<date>), won't build from listings older than
6 hours, and won't send when fewer than 4 cities have enough on (something is wrong then, not a quiet day).
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import digest

ROOT = Path(__file__).parent
API = "https://api.buttondown.com/v1/emails"
MIN_CITIES = 4
MAX_AGE_HOURS = 6


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--send", action="store_true", help="send to subscribers (default: save a draft)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore the once-a-day marker")
    a = ap.parse_args()

    today = digest.today_in_india()
    marker = ROOT / "data" / f".daily-{today:%Y%m%d}"
    if marker.exists() and not a.force and not a.dry_run:
        print(f"already done today ({marker.name})"); return 0

    listings = json.loads(digest.EVENTS.read_text())
    updated = datetime.fromisoformat(listings["updated_at"].replace("Z", "+00:00")) if listings.get("updated_at") else None
    if updated:
        age = (datetime.now(ZoneInfo("UTC")) - updated.astimezone(ZoneInfo("UTC"))).total_seconds() / 3600
        if age > MAX_AGE_HOURS:
            print(f"listings are {age:.1f} hours old: not sending stale picks"); return 1

    with tempfile.TemporaryDirectory() as out:
        rows, _ = digest.run(None, out, today, daily=True)
        made = json.loads((Path(out) / "buttondown.json").read_text()) if (Path(out) / "buttondown.json").exists() else None
    cities = [d for d in rows if not d["skip"]]
    if not made or len(cities) < MIN_CITIES:
        print(f"only {len(cities)} cities have enough on: not sending"); return 1
    print(f"{len(cities)} cities, subject: {made['subject'][:120]}")
    if a.dry_run:
        print(f"body {len(made['body'])} bytes"); return 0

    key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if not key:
        print("BUTTONDOWN_API_KEY is not set"); return 2
    headers = {"Authorization": f"Token {key}", "X-API-Version": "2026-04-01"}
    if a.send:
        headers["X-Buttondown-Live-Dangerously"] = "true"  # Buttondown asks for this once per key before it will send from the API
    r = requests.post(API, headers=headers, timeout=60, json={
        "subject": made["subject"], "body": made["body"], "status": "about_to_send" if a.send else "draft",
        "metadata": {"daily": today.isoformat()}})
    print("Buttondown:", r.status_code, r.text[:200])
    if r.status_code in (200, 201):
        marker.write_text(r.text[:200])
        return 0
    return 3


if __name__ == "__main__":
    sys.exit(main())
