"""
Shared scraping utilities.

Two ways to get a page:
  fetch(url)            plain HTTP, fast, works for server-rendered sites
  render(url)           headless Chromium via Playwright, for pages that only
                        fill in with JavaScript

Two generic ways to read events out of a page:
  extract_jsonld_events schema.org Event objects embedded for search engines
  meta_event            og:title / description fallback for detail pages
"""

import atexit
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from .cities import CITIES, detect_city

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

CATEGORIES = ("music", "theatre", "sports", "comedy")

CATEGORY_KEYWORDS = {
    "comedy": ["comedy", "comic", "stand-up", "standup", "stand up", "improv", "open mic", "roast", "crowd work"],
    "theatre": ["theatre", "theater", "play", "drama", "musical", "natak", "monologue",
                "dastangoi", "storytelling"],
    "sports": ["cricket", "football", "ipl", "isl", "kabaddi", "match", "marathon",
               "tennis", "badminton", "hockey", "10k", "5k", "run", "race", "championship",
               "t20i", "t20", "odi", "test cricket", "world cup"],
    "music": ["concert", "live music", "gig", "band", "tour", "dj", "festival",
              "classical", "jazz", "indie", "rock", "hip hop", "sufi", "ghazal",
              "orchestra", "recital", "philharmonic", "qawwali", "unplugged", "jam"],
}

# ---------------------------------------------------------------- fetching

def fetch(url, timeout=25):
    """GET a page and return its HTML, or None on any failure."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as exc:  # noqa: BLE001
        print(f"  ! fetch failed {url}: {exc}")
        return None


# One browser for the whole run; launching Chromium per page was most of the run time.
_playwright = None
_browser = None


def _get_browser():
    global _playwright, _browser
    if _browser is None or not _browser.is_connected():
        from playwright.sync_api import sync_playwright
        if _playwright is None:
            _playwright = sync_playwright().start()
            atexit.register(_close_browser)
        _browser = _playwright.chromium.launch()
    return _browser


def _close_browser():
    if _browser is not None and _browser.is_connected():
        _browser.close()
    if _playwright is not None:
        _playwright.stop()


def render(url, wait_ms=2500, scroll=True):
    """Load a page in headless Chromium and return the rendered HTML."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("  ! playwright not installed; run: pip install playwright && playwright install chromium")
        return None
    try:
        page = _get_browser().new_page(user_agent=HEADERS["User-Agent"])
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(wait_ms)
            if scroll:  # trigger lazy-loaded rows on listing pages
                for _ in range(4):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(500)
            return page.content()
        finally:
            page.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  ! render failed {url}: {exc}")
        return None


def get_html(url, use_render=False, wait_ms=2500, scroll=True):
    return render(url, wait_ms, scroll) if use_render else fetch(url)


# ---------------------------------------------------------------- helpers

def guess_category(text, fallback=None):
    t = (text or "").lower()
    for cat, words in CATEGORY_KEYWORDS.items():
        if any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words):
            return cat
    return fallback


def make_id(title, day, venue):
    raw = f"{title}|{day}|{venue}".lower()
    raw = re.sub(r"[^a-z0-9|]", "", raw)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def parse_date(text):
    """
    Turn 'Sat, 12 Dec, 7:00 PM', '6 September 2026', '2026-09-20T19:30'
    into (YYYY-MM-DD, HH:MM). Returns (None, '') if no day can be found.
    Dates without a year are assumed to be the next occurrence.
    """
    if not text:
        return None, ""
    text = text.strip()
    # Ranges like 'Sat, 12 Sep – Sun, 13 Sep, 7:00 PM' -> take the first day + any time.
    first = re.split(r"\s[–-]\s", text)[0]
    time_match = re.search(r"\d{1,2}:\d{2}\s*[AP]M", text, re.I)
    if time_match and time_match.group(0) not in first:
        first = f"{first}, {time_match.group(0)}"
    # Need an actual day: '12 Dec', 'Aug 25', or ISO. 'Late 2026' or 'November 2026' won't do.
    if not re.search(r"\d{1,2}\s*[A-Za-z]{3,}|[A-Za-z]{3,}\.?\s*\d{1,2}\b|\d{4}-\d{2}-\d{2}", first):
        return None, ""
    try:
        dt = dateparser.parse(first, dayfirst=True, fuzzy=True, default=datetime(date.today().year, 1, 1))
    except (ValueError, OverflowError):
        return None, ""
    has_year = re.search(r"\b(20\d{2})\b", first) is not None
    if not has_year and dt.date() < date.today() - timedelta(days=7):
        dt = dt.replace(year=dt.year + 1)
    time_str = dt.strftime("%H:%M") if time_match or "T" in first else ""
    return dt.date().isoformat(), time_str


def event(title, day, source, city, category=None, venue="", time="", price=None, url="", image=None, hint="", default=None, place=""):
    """
    Build a normalised event dict; returns None if it lacks a title or date.
    `city` is only the listing page's city: the show's own venue/address (`place`, or
    `venue`) wins, then a city named in the title.
    """
    title = re.sub(r"\s+", " ", title or "").strip()
    if not title or not day:
        return None
    city = detect_city(place or venue) or detect_city(title) or city
    cat = category or guess_category(f"{title} {hint}", default)
    if cat not in CATEGORIES:
        return None
    if isinstance(price, str):
        m = re.search(r"\d[\d,]*", price)
        price = int(m.group(0).replace(",", "")) if m else None
    return {
        "id": make_id(title, day, venue),
        "title": title,
        "category": cat,
        "city": city or "Unknown",
        "venue": (venue or "").strip(),
        "date": day,
        "time": time,
        "price_from": price,
        "url": url,
        "image": image,
        "source": source,
    }


def collect_links(html, base_url, pattern):
    """Absolute URLs on the page whose path contains `pattern`, deduplicated."""
    soup = BeautifulSoup(html, "lxml")
    seen, out = set(), []
    candidates = [a["href"] for a in soup.find_all("a", href=True)]
    candidates += [loc.get_text(strip=True) for loc in soup.find_all("loc")]  # XML sitemaps
    for raw in candidates:
        href = urljoin(base_url, raw).split("?")[0].split("#")[0]
        if pattern in href and href not in seen and href.rstrip("/") != base_url.rstrip("/"):
            seen.add(href)
            out.append(href)
    return out


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- generic extraction

def extract_jsonld_events(html):
    """Every schema.org Event object found in JSON-LD blocks."""
    soup = BeautifulSoup(html, "lxml")
    found = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                t = node.get("@type", "")
                types = t if isinstance(t, list) else [t]
                if any("Event" in str(x) for x in types):
                    found.append(node)
                for key in ("@graph", "itemListElement", "item", "mainEntity", "subEvent"):
                    if key in node:
                        stack.append(node[key])
    return found


def jsonld_to_event(node, source, city=None, category=None, page_url="", default=None):
    loc = node.get("location") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    venue, place = "", ""
    if isinstance(loc, dict):
        venue = loc.get("name") or ""
        addr = loc.get("address")
        if isinstance(addr, dict):
            addr = ", ".join(str(addr.get(k) or "") for k in ("streetAddress", "addressLocality"))
        place = f"{venue}, {addr if isinstance(addr, str) else ''}"
    offers = node.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = offers.get("lowPrice") or offers.get("price") if isinstance(offers, dict) else None
    image = node.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    day, time = parse_date(node.get("startDate") or "")
    return event(node.get("name"), day, source, city, category, venue, time, price,
                 node.get("url") or page_url, image, hint=node.get("description", ""), default=default, place=place)


def meta_event(html, source, city, category, page_url, default=None):
    """Fallback for detail pages without JSON-LD: og:title + a date in the description."""
    soup = BeautifulSoup(html, "lxml")
    og = lambda k: (soup.find("meta", property=k) or soup.find("meta", attrs={"name": k}) or {}).get("content")  # noqa: E731
    title = og("og:title") or (soup.title.string if soup.title else "")
    title = re.sub(r"\s*[|·-]\s*(thumpN|SkillBox|NMACC|District|BookMyShow).*$", "", title or "", flags=re.I)
    desc = og("description") or og("og:description") or ""
    m = re.search(r"\b(\d{1,2}\s+\w{3,9}\s+20\d{2}|\w{3,9}\s+\d{1,2},?\s+20\d{2}|20\d{2}-\d{2}-\d{2})", desc)
    day, time = parse_date(m.group(1)) if m else (None, "")
    venue = ""
    vm = re.search(r"\bat\s+(.+?),\s*(?:" + "|".join(re.escape(c) for c in CITIES) + r")\b", desc)
    if vm:
        venue = vm.group(1)
    return event(title, day, source, city, category, venue, time, None, page_url,
                 og("og:image"), hint=desc, default=default, place=f"{venue}, {desc}")
