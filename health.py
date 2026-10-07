#!/usr/bin/env python3
"""
Collector health.

run.py calls record() after every run, noting what each source returned in data/health.json
(shown on the dashboard nowhere; it just lives in the repo). The scheduled "Health check"
workflow runs `python health.py check`, which reads that file and the live site and exits
non-zero when something is off, so GitHub emails the repo owner about the failed run.

    python health.py check             check everything, including the live site
    python health.py check --offline   only what's in the repo
    python health.py seed              build data/health.json from the current events.json

A problem is an error (fails the run, so you get an email) or a warning (only shown in the
run's summary). What counts as which is in the constants below.
"""

import json
import os
import socket
import ssl
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
HEALTH = ROOT / "data" / "health.json"
EVENTS = ROOT / "data" / "events.json"
SITE = "https://gigsnshows.com"

# How long a source may go without a successful read, by where it is read (hours).
STALE_AFTER = {"aws": (20, 20), "mac": (48, 96)}  # (warn, error): the Mac is often asleep
DROP_ERROR, DROP_WARN = 0.5, 0.75  # a run below this share of the usual count
TOTAL_DROP_ERROR = 0.7  # all listings together
CERT_WARN_DAYS, CERT_ERROR_DAYS = 21, 7
FIREBASE_KEY = "AIzaSyD6SaNLKN7HSd9VxzsoApAZponyV0JPAV4"  # public web key, as in index.html


def now():
    return datetime.now(timezone.utc)


def stamp(dt=None):
    return (dt or now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load():
    try:
        return json.loads(HEALTH.read_text())
    except (OSError, ValueError):
        return {"sources": {}, "total": {"recent": []}}


def save(h):
    HEALTH.parent.mkdir(exist_ok=True)
    HEALTH.write_text(json.dumps(h, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------- recording (called by run.py)

def record(ran, collected, failed, today, where, total):
    """
    ran: names of the sources this run actually read; collected: what they returned;
    failed: source -> cities that came back empty; total: unique listings after merging.
    """
    h = load()
    at = stamp()
    for name in ran:
        n = sum(1 for e in collected if e["source"] == name and e["date"] >= today)
        s = h["sources"].setdefault(name, {"recent": []})
        s.update(count=n, last_run=at, by=where, failed_cities=sorted(failed.get(name, [])))
        if n:
            s["last_ok"] = at
        s["recent"] = (s.get("recent", []) + [n])[-14:]
    t = h.setdefault("total", {"recent": []})
    t.update(count=total, at=at)
    t["recent"] = (t.get("recent", []) + [total])[-20:]
    h["updated_at"] = at
    save(h)


def seed():
    """Start the record from the listings as they stand, so the first checks have something to compare."""
    d = json.loads(EVENTS.read_text())
    sources = yaml.safe_load((ROOT / "sources.yaml").read_text())
    h = {"sources": {}, "total": {"count": d["count"], "at": d["updated_at"], "recent": [d["count"]]}, "updated_at": d["updated_at"]}
    for src in sources:
        n = sum(1 for e in d["events"] if src["name"] in e.get("sources", [e["source"]]))
        h["sources"][src["name"]] = {"count": n, "last_ok": d["updated_at"] if n else None, "last_run": d["updated_at"],
                                     "by": "seed", "failed_cities": [], "recent": [n]}
    save(h)
    print(f"seeded {HEALTH} with {len(sources)} sources")


# ---------------------------------------------------------------- checking

def hours_since(ts):
    return (now() - parse(ts)).total_seconds() / 3600 if ts else None


def check_sources(h, sources):
    errors, warnings, rows = [], [], []
    for src in sources:
        name = src["name"]
        runs_on = src.get("runs_on", ["aws", "github"])
        where = "aws" if "aws" in runs_on else "mac" if "mac" in runs_on else None
        s = h["sources"].get(name)
        if where is None:
            continue  # only read by the manual GitHub run: nothing to expect
        if not s:
            warnings.append(f"{name}: no record yet (a new source, or the collector hasn't run since it was added)")
            rows.append((name, where, "-", "-", "-", "no record yet"))
            continue
        problems = []
        age = hours_since(s.get("last_ok"))
        warn_h, err_h = STALE_AFTER[where]
        if age is None:
            errors.append(f"{name}: has never returned any shows")
            problems.append("never returned shows")
        elif age > err_h:
            errors.append(f"{name}: last refreshed {age:.0f} hours ago (it should be every {warn_h} hours" +
                          (", and the Mac needs to be awake" if where == "mac" else ", so the server's collector may have stopped") + ")")
            problems.append(f"stale {age:.0f}h")
        elif age > warn_h:
            warnings.append(f"{name}: last refreshed {age:.0f} hours ago" + (" (open the Mac so it can collect)" if where == "mac" else ""))
            problems.append(f"stale {age:.0f}h")
        count, base = s.get("count", 0), s.get("recent", [])[:-1]
        med = statistics.median(base) if len(base) >= 3 else None
        if med and med >= 5:
            if count == 0:
                errors.append(f"{name}: returned nothing on its last run (usually {med:.0f}); the old listings are being kept")
                problems.append("returned nothing")
            elif count < DROP_ERROR * med:
                errors.append(f"{name}: returned {count} shows on its last run, well below the usual {med:.0f}")
                problems.append(f"{count} vs usual {med:.0f}")
            elif count < DROP_WARN * med:
                warnings.append(f"{name}: returned {count} shows on its last run, below the usual {med:.0f}")
                problems.append(f"{count} vs usual {med:.0f}")
        if s.get("failed_cities"):
            warnings.append(f"{name}: no results for {', '.join(s['failed_cities'])} on its last run (earlier shows kept)")
            problems.append(f"{len(s['failed_cities'])} cities empty")
        rows.append((name, where, count, f"{med:.0f}" if med else "-", f"{age:.0f}h" if age is not None else "never",
                     "; ".join(problems) or "ok"))
    t = h.get("total", {})
    base = t.get("recent", [])[:-1]
    if len(base) >= 3 and t.get("count") is not None:
        med = statistics.median(base)
        if t["count"] < TOTAL_DROP_ERROR * med:
            errors.append(f"All listings together: {t['count']} now, usually about {med:.0f}")
    return errors, warnings, rows


def site_checks():
    import requests
    errors, warnings, notes = [], [], []

    def get(url, **kw):
        return requests.get(url, timeout=25, headers={"User-Agent": "gigsnshows-health/1.0"}, **kw)

    try:
        r = get(SITE + "/")
        if r.status_code != 200 or "gigsnshows" not in r.text:
            errors.append(f"Home page: HTTP {r.status_code}")
        else:
            notes.append(f"home page ok ({len(r.content) // 1024} KB)")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Home page unreachable: {exc}")
    try:
        r = get(f"{SITE}/data/events.json?t={int(now().timestamp())}")
        d = r.json()
        age = hours_since(d["updated_at"])
        if not d.get("count"):
            errors.append("Live events.json has no shows")
        elif age > 20:
            errors.append(f"Live listings were last updated {age:.0f} hours ago: no collector has uploaded since")
        else:
            notes.append(f"live listings: {d['count']} shows, updated {age:.1f}h ago")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Live events.json unreadable: {exc}")
    try:
        r = get(SITE + "/og.jpg")
        if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
            warnings.append(f"Share card image: HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Share card image unreachable: {exc}")
    try:
        import certifi  # the same certificate bundle requests uses, so this works on any machine
        ctx = ssl.create_default_context(cafile=certifi.where())
        with socket.create_connection(("gigsnshows.com", 443), timeout=15) as sock, ctx.wrap_socket(sock, server_hostname="gigsnshows.com") as tls:
            exp = datetime.strptime(tls.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days = (exp - now()).days
        if days < CERT_ERROR_DAYS:
            errors.append(f"HTTPS certificate expires in {days} days")
        elif days < CERT_WARN_DAYS:
            warnings.append(f"HTTPS certificate expires in {days} days (GitHub normally renews it by itself)")
        else:
            notes.append(f"certificate valid for {days} more days")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"HTTPS check failed: {exc}")
    try:  # plans can be read by anyone with the link; a missing one answers 404, a broken setup doesn't
        r = get(f"https://firestore.googleapis.com/v1/projects/gigsnshows/databases/(default)/documents/plans/healthcheck0000?key={FIREBASE_KEY}")
        if r.status_code == 404:
            notes.append("database reachable")
        else:
            errors.append(f"Firestore (plans, logins and lists) answered HTTP {r.status_code}; expected 404")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Firestore unreachable: {exc}")
    return errors, warnings, notes


def check(offline=False):
    h = load()
    sources = yaml.safe_load((ROOT / "sources.yaml").read_text())
    errors, warnings, rows = check_sources(h, sources)
    notes = []
    if not offline:
        e2, w2, notes = site_checks()
        errors += e2
        warnings += w2

    lines = ["## gigsnshows health", ""]
    lines += [("**Problems**" if errors else "**No problems**"), ""] + [f"- ❌ {e}" for e in errors]
    lines += [f"- ⚠️ {w}" for w in warnings] + [f"- ✅ {n}" for n in notes] + [""]
    lines += ["| Source | Read on | Last run | Usual | Last refreshed | Status |", "|---|---|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} | {e} | {f} |" for a, b, c, d, e, f in rows]
    report = "\n".join(lines)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(report + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "seed":
        seed()
    elif cmd == "check":
        sys.exit(check(offline="--offline" in sys.argv))
    else:
        sys.exit(__doc__)
