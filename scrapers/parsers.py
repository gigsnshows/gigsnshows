"""
Parsers turn one page into a list of events. Each takes (html, page_url, src, entry)
where `src` is the source block from sources.yaml and `entry` is the expanded
{url, city, category} being processed.

To support a new site layout, add a function here and register it in PARSERS.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from .base import (collect_links, event, extract_jsonld_events, get_html, guess_category,
                   jsonld_to_event, meta_event, parse_date, summary)
from .cities import detect_city
from .genres import language

_visited = set()  # detail pages already read this run (same event linked from several city pages)

DATE_RE = re.compile(
    r"^(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?\d{1,2}\s+[A-Z][a-z]{2,8}(?:\s+20\d{2})?", re.I
)
DAY_WORD_RE = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b")


# ---------------------------------------------------------------- generic

def parse_jsonld(html, page_url, src, entry):
    nodes = extract_jsonld_events(html)
    evs = [jsonld_to_event(n, src["name"], entry.get("city"), entry.get("category"), page_url,
                           default=src.get("default_category")) for n in nodes]
    return [e for e in evs if e]


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
        if seen is None or (seen["m"] != changed and seen["e"]):  # new, or a show whose page has changed
            todo.append((changed, url))
    todo.sort(reverse=True)
    limit = src.get("max_pages", 600)
    print(f"      {len(pages)} pages in the sitemap, {len(todo)} to read" + (f", reading the newest {limit}" if len(todo) > limit else ""))
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
        shows = [e for e in (jsonld_to_event(n, src["name"], None, guess_category(n["name"]), url) if guess_category(n["name"]) else None
                             for n in nodes) if e and e["city"] != "Unknown"]
        memory[url] = {"m": changed, "e": shows}
    listed = {u for u, _ in pages}
    memory = {u: v for u, v in memory.items() if u in listed}  # pages District has dropped are forgotten
    try:
        DISTRICT_PAGES.write_text(json.dumps(memory, ensure_ascii=False, separators=(",", ":")))
    except OSError as exc:
        print(f"      ! couldn't save {DISTRICT_PAGES.name}: {exc}")
    return [e for u, v in memory.items() if u not in _district_listed for e in v["e"] if e["date"] >= today.isoformat()]


# ---------------------------------------------------------------- ncpamumbai.com

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
    "ncpa": parse_ncpa,
    "prithvi": parse_prithvi,
    "pianoman": parse_pianoman,
}
