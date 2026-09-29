"""
Parsers turn one page into a list of events. Each takes (html, page_url, src, entry)
where `src` is the source block from sources.yaml and `entry` is the expanded
{url, city, category} being processed.

To support a new site layout, add a function here and register it in PARSERS.
"""

import json
import re
from datetime import datetime

from bs4 import BeautifulSoup

from .base import (collect_links, event, extract_jsonld_events, get_html,
                   jsonld_to_event, meta_event, parse_date, summary)
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
    "ncpa": parse_ncpa,
    "prithvi": parse_prithvi,
    "pianoman": parse_pianoman,
}
