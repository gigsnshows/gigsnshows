"""
Parsers turn one page into a list of events. Each takes (html, page_url, src, entry)
where `src` is the source block from sources.yaml and `entry` is the expanded
{url, city, category} being processed.

To support a new site layout, add a function here and register it in PARSERS.
"""

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from .base import (collect_links, event, extract_jsonld_events, get_html, guess_category,
                   jsonld_to_event, meta_event, parse_date, summary)
from .cities import detect_city, nearest_city
from .genres import language

_visited = set()  # detail pages already read this run (same event linked from several city pages)

DATE_RE = re.compile(
    r"^(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?\d{1,2}\s+[A-Z][a-z]{2,8}(?:\s+20\d{2})?", re.I
)
DAY_WORD_RE = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b")


# ---------------------------------------------------------------- generic

_returned = set()  # ids of the BookMyShow-style event pages ("ET00515069") returned this run
COVERAGE = {}  # per sitemap reader: pages listed, pages still to read, well-known acts' pages still to read; run.py records it


def _page_id(url):
    m = re.search(r"/(et[0-9a-z]{6,12})/?(?:[?#].*)?$", (url or "").lower())
    return m.group(1) if m else None


def parse_jsonld(html, page_url, src, entry):
    nodes = extract_jsonld_events(html)
    evs = [jsonld_to_event(n, src["name"], entry.get("city"), entry.get("category"), page_url,
                           default=src.get("default_category")) for n in nodes]
    evs = [e for e in evs if e]
    _returned.update(i for i in (_page_id(e["url"]) for e in evs) if i)
    return evs


def parse_detail_pages(html, page_url, src, entry):
    """Collect event links from a listing page, then read each event's own page."""
    links = [l for l in collect_links(html, page_url, src.get("link_pattern", "/event")) if l not in _visited]
    limit = src.get("max_pages", 60)
    print(f"      {len(links)} new event links found" + (f", reading first {limit}" if len(links) > limit else ""))
    out = []
    for link in links[:limit]:
        _visited.add(link)
        page = get_html(link, src.get("render_details", False), src.get("wait_ms", 2500), scroll=False,
                        delay=src.get("crawl_delay", 0))
        if not page:
            continue
        evs = parse_jsonld(page, link, src, entry)
        if not evs:
            ev = meta_event(page, src["name"], entry.get("city"), entry.get("category"), link,
                            default=src.get("default_category"))
            evs = [ev] if ev else []
        out.extend(evs)
    return out


# ---------------------------------------------------------------- district.in

_district_abouts = {}  # event URL -> description; a show often appears on several listing pages
_district_listed = set()  # event pages the listing parser returned this run


def _district_about(href, src):
    """The show's own description (listing cards carry only a title), for genre tagging."""
    if href not in _district_abouts:
        page = get_html(href, delay=src.get("crawl_delay", 0))
        nodes = extract_jsonld_events(page) if page else []
        _district_abouts[href] = " ".join(n.get("description") or "" for n in nodes)[:1500]
    return _district_abouts[href]


def parse_district(html, page_url, src, entry):
    """
    Listing pages at /activities/<category>-in-<city>. Each card is an <a> to
    /events/<name>-<mon><dd>-<yyyy>-buy-tickets containing an image and lines for
    the date, title, venue and price — in no fixed order from card to card.
    """
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.select('a[href*="-buy-tickets"]'):
        href = a["href"]
        if href in seen:
            continue
        seen.add(href)
        if not href.startswith("http"):
            href = "https://www.district.in" + href
        _district_listed.add(href)
        strings = [s.strip() for s in a.stripped_strings if s.strip()]
        img = a.find("img")
        date_txt = next((s for s in strings if DATE_RE.match(s)), "")
        if not date_txt or "Every" in date_txt:
            continue  # recurring bar nights / undated announcements
        price = next((s for s in strings if "₹" in s), None)
        others = [s for s in strings if s != date_txt and s != price and not DATE_RE.match(s)]
        # Cards without image alt text: the title is whichever line best matches the event's URL slug.
        slug = re.sub(r"(-[a-z]{3}\d{1,2}-\d{4})?-buy-tickets$", "", href.rstrip("/").rsplit("/", 1)[-1])
        slug_words = set(slug.split("-"))
        title = ((img.get("alt") or "").strip() if img else "") or max(
            others, key=lambda s: len(slug_words & set(re.findall(r"[a-z0-9]+", s.lower()))), default="")
        place = next((s for s in others if s != title and "," in s), "")
        venue = place.rsplit(",", 1)[0].strip()
        day, time = parse_date(date_txt)
        image = None
        if img:
            image = img.get("src") or img.get("data-src")
        about = _district_about(href, src) if src.get("details") else ""
        ev = event(title, day, src["name"], entry.get("city"), entry.get("category"),
                   venue, time, price, href, image, place=place, hint=about)
        if ev:
            out.append(ev)
    return out


# ---------------------------------------------------------------- district.in: every event in its sitemap
#
# A District listing page shows at most 24 shows for a city and kind, whatever else is on, so big concerts (A. R.
# Rahman's Wonderment Tour in Mumbai and Delhi) can be missing from every listing page. District also publishes a
# sitemap of every event page; each page carries the show as schema.org JSON-LD. This reads those pages.
#
# About 1,600 pages in the sitemap aren't already over, so what's been read is remembered in
# data/district_pages.json (page URL -> its sitemap date and the shows found there). A page is read again only if
# it's new, or it was a show and its sitemap date has changed. At most `max_pages` new pages are read per run,
# newest first, so the first few runs fill the memory and later runs read only what's new.

DISTRICT_PAGES = Path(__file__).resolve().parent.parent / "data" / "district_pages.json"
# Bump this whenever the rules for what counts as a show change (categories, filters): a page remembered as "not a show" under
# older rules is then read again once. Without it a show the rules newly accept (Samay Raina Live) stays hidden for good.
DISTRICT_RULES = 3
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def _district_over(slug, today):
    """True if the page's own name says the show has passed ("...-oct23-2026-buy-tickets", or a 2025 show)."""
    m = re.search(r"-(%s)(\d{1,2})-(20\d\d)-buy-tickets$" % "|".join(_MONTHS), slug)
    if m:
        try:
            return date(int(m.group(3)), _MONTHS.index(m.group(1)) + 1, int(m.group(2))) < today
        except ValueError:
            return False
    return bool(re.search(r"-20(1\d|2[0-5])(-|$)", slug.replace("-buy-tickets", "")))


def _description_category(text):
    """For a title that says nothing ("Samay Raina Live"): a few clear words in the opening of the description. Kept narrow on purpose:
    a description that merely mentions "sports" or "play" once put a water park among the shows."""
    t = (text or "")[:500].lower()
    if re.search(r"\b(stand-?up|stand up|comedian|comedians|comedy show|comedy night)\b", t):
        return "comedy"
    if re.search(r"\b(live in concert|live concert|in concert|live music|concert)\b", t):
        return "music"
    return None


def _show_kind(title, description):
    """The kind of show from its title, else its description. A title that says "... Live" ("Satinder Sartaaj Live in Delhi",
    "Vivek Samtani Live") is a show: the description then only has to say which kind (laughter, or music). Titles with no
    "live" need the narrower rule above, since water parks and classes describe themselves as fun too."""
    kind = guess_category(title) or _description_category(description)
    if kind or not re.search(r"\blive\b", title or "", re.I):
        return kind
    t = (description or "")[:600].lower()
    if re.search(r"\b(laugh|laughs|laughter|comic|comedians?|humou?r|stand-?up|roast)\b", t):
        return "comedy"
    if re.search(r"\b(music|musical|singing|singer|songs?|concert|band|dj|sufi|bhangra|ghazal|qawwali|melod\w+)\b", t):
        return "music"
    return None


def _district_title(name, city):
    """"A R Rahman | Wonderment Tour Live in Concert | Mumbai" -> "A R Rahman – Wonderment Tour Live in Concert"."""
    parts = [p.strip() for p in re.split(r"\s+\|\s+", name or "") if p.strip()]
    if len(parts) > 1 and city and parts[-1].lower() == city.lower():
        parts = parts[:-1]
    return " – ".join(parts)


def parse_district_sitemap(html, page_url, src, entry):
    try:
        memory = json.loads(DISTRICT_PAGES.read_text())
    except (OSError, ValueError):
        memory = {}
    today = date.today()
    pages = re.findall(r"<url>\s*<loc>(.*?)</loc>(?:\s*<lastmod>(.*?)</lastmod>)?", html, re.S)
    todo = []
    for url, changed in pages:
        if not url.endswith("-buy-tickets") or url in _district_listed or _district_over(url.rsplit("/", 1)[-1], today):
            continue
        seen = memory.get(url)
        if seen is None or (seen["m"] != changed and seen["e"]) or (not seen["e"] and seen.get("v", 1) < DISTRICT_RULES):
            todo.append((changed, url))  # new, or a show whose page has changed, or "not a show" under older rules
    watch = [w.lower() for w in src.get("watch", [])]
    todo.sort(key=lambda t: t[0], reverse=True)  # newest first
    todo.sort(key=lambda t: 0 if any(w in t[1] for w in watch) else 1)  # then (the sort is stable) well-known acts first
    limit = int(os.environ.get("SITEMAP_MAX_PAGES") or src.get("max_pages", 600))
    print(f"      {len(pages)} pages in the sitemap, {len(todo)} to read" + (f", reading the first {limit}" if len(todo) > limit else ""))
    COVERAGE["District"] = {"listed": len(pages), "unread": max(0, len(todo) - limit),
                            "watched_unread": sum(1 for _, u in todo[limit:] if any(w in u for w in watch))}
    for changed, url in todo[:limit]:
        page = get_html(url, delay=src.get("crawl_delay", 0))
        if not page:
            continue  # not remembered, so the next run tries again
        nodes = extract_jsonld_events(page)
        for node in nodes:
            loc = node.get("location") if isinstance(node.get("location"), dict) else {}
            addr = loc.get("address")
            addr = ", ".join(str(addr.get(k) or "") for k in ("streetAddress", "addressLocality")) if isinstance(addr, dict) else str(addr or "")
            node["name"] = _district_title(node.get("name"), detect_city(f"{loc.get('name', '')}, {addr}"))
        # The kind of show comes from its title ("Concert", "Tour", "Comedy"...): a description mentions "play" or "run" for
        # almost anything, and this source also lists water parks and classes. A title that says nothing is left out; the
        # listing pages cover ordinary shows. No city is passed in: each show is filed under the city its own venue and
        # address name, and one that names none is left out.
        kind = lambda n: _show_kind(n["name"], n.get("description"))  # noqa: E731
        near = lambda n: nearest_city(*(((n.get("location") or {}).get("geo") or {}).get(k) for k in ("latitude", "longitude"))) if isinstance(n.get("location"), dict) else None  # noqa: E731
        shows = [e for e in (jsonld_to_event(n, src["name"], near(n), kind(n), url) if kind(n) else None
                             for n in nodes) if e and e["city"] != "Unknown"]
        for e in shows:  # "Satinder Sartaaj Live in Jalandhar": the title's city beats an address that also names the highway to Delhi
            named = re.search(r"\blive in ([A-Za-z .]+?)\s*$", e["title"], re.I)
            e["city"] = (named and detect_city(named.group(1))) or e["city"]
        if not nodes:  # some pages carry no structured data: fall back to the page's own title and date
            fallback = meta_event(page, src["name"], None, None, url)
            if fallback and guess_category(fallback["title"]) and fallback["city"] != "Unknown":
                shows = [{**fallback, "category": guess_category(fallback["title"])}]
        memory[url] = {"m": changed, "e": shows, "v": DISTRICT_RULES}
    listed = {u for u, _ in pages}
    memory = {u: v for u, v in memory.items() if u in listed}  # pages District has dropped are forgotten
    try:
        DISTRICT_PAGES.write_text(json.dumps(memory, ensure_ascii=False, separators=(",", ":")))
    except OSError as exc:
        print(f"      ! couldn't save {DISTRICT_PAGES.name}: {exc}")
    return [e for u, v in memory.items() if u not in _district_listed for e in v["e"] if e["date"] >= today.isoformat()]


# ---------------------------------------------------------------- bookmyshow.com: every event in its sitemap
#
# BookMyShow's city pages show only some of what's on: its own sitemap lists 5,000+ event pages (only current ones; the
# listing pages gave us about 60 of the music and comedy ones). This reads the sitemap's concert-like pages one by one
# (BookMyShow's robots.txt asks for 10 seconds between requests, so it's slow), the pages of well-known acts first
# (`watch:` in sources.yaml), skipping pages the city pages already returned. Pages read are remembered in
# data/bms_pages.json; a show's page is read again after 10 days, a page that wasn't a show never. At most `max_pages` are
# read per run (the `SITEMAP_MAX_PAGES` environment variable overrides it, for a big first fill).

BMS_PAGES = Path(__file__).resolve().parent.parent / "data" / "bms_pages.json"
BMS_RULES = 3  # bump when the rules for what counts as a show change (see DISTRICT_RULES)
BMS_CONCERTY = re.compile(r"(tour|concert|live|festival|fest\b|unplugged|symphony|orchestra|world|india|night|jam\b|dj|band|music|sufi|"
                          r"ghazal|qawwali|opera|comedy|stand-?up|roast|singh|rahman|rehman|ghoshal|dosanjh|kumar|sharma|khan|"
                          r"gig|rock|jazz|indie|folk|bhajan|kirtan|mushaira|musical|karaoke|open-mic)")


def _node_category(node, title):
    kind = str(node.get("@type") or "")
    for key, cat in (("Comedy", "comedy"), ("Music", "music"), ("Theat", "theatre"), ("Sport", "sports")):
        if key in kind:
            return cat
    return _show_kind(title, node.get("description"))


def parse_bms_sitemap(html, page_url, src, entry):
    try:
        memory = json.loads(BMS_PAGES.read_text())
    except (OSError, ValueError):
        memory = {}
    today = date.today()
    others = set(_returned)  # pages the city listings already returned this run
    watch = [w.lower() for w in src.get("watch", [])]
    todo = []
    for url in re.findall(r"<loc>\s*(.*?)\s*</loc>", html):
        m = re.search(r"/events/([^/]+)/(et[0-9a-z]+)/?$", url, re.I)  # ids come in both cases: ET00515069 and et5g31o909
        if not m or _page_id(url) in others or not BMS_CONCERTY.search(m.group(1)):
            continue
        seen = memory.get(url)
        stale = seen and ((seen["e"] and (today - date.fromisoformat(seen["t"])).days >= 10) or (not seen["e"] and seen.get("v", 1) < BMS_RULES))
        if seen is None or stale:
            todo.append((0 if any(w in m.group(1) for w in watch) else 1, 0 if seen is None else 1, url))
    todo.sort()
    limit = int(os.environ.get("SITEMAP_MAX_PAGES") or src.get("max_pages", 40))
    print(f"      {len(todo)} concert-like pages to read" + (f", reading the first {limit}" if len(todo) > limit else ""))
    COVERAGE["BookMyShow"] = {"listed": len(re.findall(r"<loc>", html)), "unread": max(0, len(todo) - limit),
                              "watched_unread": sum(1 for k, _, _ in todo[limit:] if k == 0)}
    for _, _, url in todo[:limit]:
        page = get_html(url, src.get("render_details", True), src.get("wait_ms", 3000), scroll=False, delay=src.get("crawl_delay", 10))
        if not page:
            continue  # not remembered, so the next run tries again
        nodes = extract_jsonld_events(page)
        shows = [e for e in (jsonld_to_event(n, src["name"], None, _node_category(n, n.get("name") or ""), url) if _node_category(n, n.get("name") or "") else None
                             for n in nodes) if e and e["city"] != "Unknown"]
        memory[url] = {"t": today.isoformat(), "e": shows, "v": BMS_RULES}
    listed = set(re.findall(r"<loc>\s*(.*?)\s*</loc>", html))
    memory = {u: v for u, v in memory.items() if u in listed}  # pages BookMyShow has dropped are forgotten
    try:
        BMS_PAGES.write_text(json.dumps(memory, ensure_ascii=False, separators=(",", ":")))
    except OSError as exc:
        print(f"      ! couldn't save {BMS_PAGES.name}: {exc}")
    return [e for v in memory.values() for e in v["e"] if e["date"] >= today.isoformat() and _page_id(e["url"]) not in others]


# ---------------------------------------------------------------- ncpamumbai.com

_ncpa_listed = set()  # event pages the home-page reader returned this run
NCPA_GENRES = {
    "theatre": "theatre",
    "indian music": "music",
    "international music": "music",
    "western classical": "music",
    "western classical music": "music",
}


def parse_ncpa(html, page_url, src, entry):
    """
    Home page lists events under genre headings. Walk the document in order,
    remembering the last genre heading, date text and image, and emit an
    event each time we reach an /event/ link with a title.
    """
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    genre, last_date, last_img, pending_title = None, None, None, None
    for el in soup.find_all(True):
        if el.name in ("h1", "h2", "h3", "h4", "h5") and not el.find("a"):
            txt = el.get_text(" ", strip=True).lower()
            if txt and txt not in NCPA_GENRES and txt not in ("dance", "films & screenings", "film & screenings",
                                                              "multi arts", "photography", "featured event",
                                                              "streaming now", "upcoming this week", "about us",
                                                              "in the news"):
                pending_title = el.get_text(" ", strip=True)  # featured cards: title in a heading, link says "View Event"
                continue
            if txt in NCPA_GENRES or txt in ("dance", "films & screenings", "film & screenings",
                                             "multi arts", "photography", "featured event"):
                genre = NCPA_GENRES.get(txt) if txt != "featured event" else genre
                if txt not in NCPA_GENRES and txt != "featured event":
                    genre = "skip"
            continue
        if el.name == "img" and el.get("src"):
            last_img = el["src"]
            continue
        if el.name == "a" and "/genre/" in (el.get("href") or ""):
            g = el.get_text(" ", strip=True).lower()
            genre = NCPA_GENRES.get(g, "skip")
            continue
        if el.name in ("span", "p", "div", "li", "time") and not el.find(True):
            txt = el.get_text(" ", strip=True)
            if re.fullmatch(r"\d{1,2} [A-Z][a-z]+ 20\d{2}", txt):
                last_date = txt
            continue
        if el.name == "a" and "/event/" in (el.get("href") or ""):
            title = el.get_text(" ", strip=True)
            href = el["href"]
            if (not title or title.lower().startswith(("view", "book"))) and pending_title:
                title = pending_title
            pending_title = None
            if not title or title.lower().startswith(("view", "book")) or href in seen or not last_date:
                continue
            seen.add(href)
            _ncpa_listed.add(href.rstrip("/").lower())
            day, _ = parse_date(last_date)
            category = None if genre in (None, "skip") else genre
            if genre == "skip":
                # dance / film / photography: only keep if the title clearly fits a tab
                category = None
                if not any(k in title.lower() for k in ("live", "comedy", "play", "concert", "jazz")):
                    continue
            ev = event(title, day, src["name"], entry.get("city"), category,
                       "NCPA", "", None, href, last_img, default=src.get("default_category"))
            if ev:
                out.append(ev)
    return out


# NCPA's home page lists only part of its calendar (a harmonium recital, a ghazal evening and a play were all missing).
# Its sitemaps list every event page with the date it last changed; this reads the pages changed in the last 90 days.
# An event page says "Venue <hall> Date Time 22 November 2026 | 10:30 am-12:30 pm ... Non Member Price Rs. 500".

# NCPA also runs talks, screenings, classes and exhibitions; these aren't shows.
_NCPA_NOT_SHOWS = re.compile(r"movies? under the stars|illustrated talks?|literature live|listening sessions?|page to stage|masterclass|"
                             r"demystifying|short film|reality check|screening|lecture|in conversation|\btalks?\b|workshop|"
                             r"connections india|photograph|exhibition|guided|orientation", re.I)
_NCPA_DATE = re.compile(r"(\d{1,2} [A-Z][a-z]+ 20\d\d)\s*\|\s*(\d{1,2}(?::\d{2})?\s*[ap]m)", re.I)


def parse_ncpa_sitemap(html, page_url, src, entry):
    today = date.today()
    cutoff = (today.toordinal() - 90)
    out = []
    for url, changed in re.findall(r"<url>\s*<loc>(.*?)</loc>(?:\s*<lastmod>(.*?)</lastmod>)?", html, re.S):
        if "/event/" not in url or not changed or date.fromisoformat(changed[:10]).toordinal() < cutoff:
            continue
        if url.rstrip("/").lower() in _ncpa_listed:
            continue
        page = get_html(url, delay=src.get("crawl_delay", 0.5))
        if not page:
            continue
        soup = BeautifulSoup(page, "lxml")
        title = re.sub(r"\s*[-–|]\s*NCPA\s*$", "", soup.title.get_text(" ", strip=True) if soup.title else "").strip()
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        m = re.search(r"Venue (.+?) Date Time", text)
        hall = m.group(1).strip() if m else ""
        details = text.split("Event Details", 1)[1][:300] if "Event Details" in text else ""
        category = guess_category(title) or guess_category(f"{title} {details}")
        if category not in ("music", "theatre", "comedy") or _NCPA_NOT_SHOWS.search(title):
            continue  # talks, masterclasses, screenings and exhibitions are left out
        prices = [int(x.replace(",", "")) for x in re.findall(r"Price Rs\. ?([\d,]+)", text)]
        og = soup.find("meta", property="og:image")
        for day_text, time_text in dict.fromkeys(_NCPA_DATE.findall(text)):  # the page repeats its dates
            day, hhmm = parse_date(f"{day_text}, {time_text.upper()}")
            ev = event(title, day, src["name"], "Mumbai", category, "NCPA", hhmm, min(prices) if prices else None, url,
                       og["content"] if og and og.get("content") else None, hint=details, place=f"NCPA, {hall}, Mumbai")
            if ev and ev["date"] >= today.isoformat():
                out.append(ev)
    return out


# ---------------------------------------------------------------- prithvitheatre.org

# Plays (event type PL) are theatre; of Prithvi's other listings, these are shows. Talks
# and film screenings are left out.
PRITHVI_KINDS = {"Music Shows": "music", "Performances": "theatre"}
PRITHVI_BOOKING = "https://prithvitheatre.org/booktickets"


def parse_prithvi(html, page_url, src, entry):
    """
    Prithvi's site reads its whole schedule from one JSON feed: shows (aEV), each
    performance's date, time and stage (aST), and the stages themselves (aVN).
    """
    data = json.loads(html)["BookMyShow"]
    shows = {e["EventCode"]: e for e in data.get("aEV", [])}
    stages = {v["Venue_strID"]: v["Venue_strName"] for v in data.get("aVN", [])}
    out = []
    for perf in data.get("aST", []):
        e = shows.get(perf["EventCode"])
        if not e:
            continue
        cat = "theatre" if e.get("EventType") == "PL" else PRITHVI_KINDS.get(e.get("Genre"))
        if not cat:
            continue
        d, t = perf.get("ShowDateCode", ""), perf.get("ShowTimeNumeric", "")
        if not re.fullmatch(r"\d{8}", d):
            continue
        price = int(float(e.get("MinPrice") or 0)) or None  # 0 = free
        about = summary(e.get("Synopsis"))
        ev = event(e["EventTitle"], f"{d[:4]}-{d[4:6]}-{d[6:]}", src["name"], entry.get("city"), cat,
                   perf.get("ScreenName") or "Prithvi Theatre", f"{t[:2]}:{t[2:]}" if re.fullmatch(r"\d{4}", t) else "",
                   price, PRITHVI_BOOKING,
                   f"https://in.bmscdn.com/Events/moviecard/{e['ImageCode']}.jpg" if e.get("ImageCode") else None,
                   hint=f"{about} {e.get('Genre', '')}", place=stages.get(perf.get("VenueID"), "Juhu, Mumbai"),
                   about=about, lang=language(cat, e.get("strLanguage", "")))  # the site states it: "Hindi", "English/Hindi"
        if ev:
            out.append(ev)
    return out


# ---------------------------------------------------------------- thepianoman.in

_pianoman_pages = {}  # show page -> (description, price)


def _pianoman_details(href, src):
    """A show's own page adds what the list lacks: its description and ticket price."""
    if href not in _pianoman_pages:
        html = get_html(href, delay=src.get("crawl_delay", 0))
        about, price = "", None
        if html:
            soup = BeautifulSoup(html, "lxml")
            desc = soup.select_one("div.content")
            about = desc.get_text(" ", strip=True) if desc else ""
            m = re.search(r"₹\s*([\d,]+)", soup.get_text(" "))
            price = int(m.group(1).replace(",", "")) if m else None
        _pianoman_pages[href] = (about, price)
    return _pianoman_pages[href]


def parse_pianoman(html, page_url, src, entry):
    """
    One venue's list: a card per show with its title, date (29.09.26), seating time,
    the club's genre label (Jazz, Sufi, Retro…) and the venue's logo, named in its alt text.
    """
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select("div.card-body"):
        title, link = card.select_one(".cs-title"), card.select_one("a[href*='/event/detail/']")
        when = card.select_one(".cs-venue-date")
        m = when and re.search(r"(\d{2})\.(\d{2})\.(\d{2})", when.get_text())
        if not (title and link and m):
            continue
        seating = card.select_one(".cs-venue-time")
        tm = seating and re.search(r"\d{1,2}:\d{2}\s*[AP]M", seating.get_text(), re.I)
        time = datetime.strptime(tm.group(0).replace(" ", "").upper(), "%I:%M%p").strftime("%H:%M") if tm else ""
        label = next((d.get_text(" ", strip=True) for d in card.select("div.cs-text") if "cs-venue-date" not in d["class"]), "")
        logo, img = card.select_one(".cs-logo img"), card.select_one(".card-img img")
        name = title.get_text(" ", strip=True)
        about, price = _pianoman_details(link["href"], src)
        ev = event(name, f"20{m[3]}-{m[2]}-{m[1]}", src["name"], entry.get("city"),
                   "comedy" if re.search(r"\b(comedy|stand-?up)\b", name, re.I) else "music",
                   logo.get("alt", "The Piano Man") if logo else "The Piano Man", time, price, link["href"],
                   img.get("src") if img else None, hint=f"{label} {about}", about=about)
        if ev:
            out.append(ev)
    return out


PARSERS = {
    "jsonld": parse_jsonld,
    "detail_pages": parse_detail_pages,
    "district": parse_district,
    "district_sitemap": parse_district_sitemap,
    "bms_sitemap": parse_bms_sitemap,
    "ncpa_sitemap": parse_ncpa_sitemap,
    "ncpa": parse_ncpa,
    "prithvi": parse_prithvi,
    "pianoman": parse_pianoman,
}
