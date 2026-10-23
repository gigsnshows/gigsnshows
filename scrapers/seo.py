"""
Pages for search engines (and for people who arrive from a search).

The dashboard is one JavaScript page, which Google reads poorly. So every collector run also
writes plain HTML with real content:

  /shows/<name>-<id>/       one page per show in a city, with every date and venue it runs,
                            and schema.org Event data so Google can show it as an event
  /<city>/                  what's on in a city, soonest first
  /<city>/<category>/       the same for music, theatre, sports or stand-up
  /<city>/this-weekend/     what's on from Friday to Sunday
  /<city>/today/, /<city>/tomorrow/   what's on that day
  /<city>/halloween/, /diwali/, /new-years-eve/   occasion pages (only while on and with 3+ shows)
  /<town>/                  satellite towns (Noida, Gurugram, Ghaziabad...) filed under their metro
  /cities/                  every city (the way crawlers find them from the home page)
  /about/                   what gigsnshows is and where the listings come from (for people and AI assistants)
  /sitemap.xml, /robots.txt, /llms.txt

All of it is rebuilt from data/events.json each run; pages for shows or cities that have gone
are deleted. The paths written are kept in seo-manifest.json so only those are removed.
(The per-show share pages in /s/ are for link previews and forward people to the dashboard;
they're marked noindex so these pages are the ones that get found.)
"""

import hashlib
import html
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode

from .genres import catalog

SITE = "https://gigsnshows.com"
SAME_AS = ["https://github.com/gigsnshows/gigsnshows"]  # add the Instagram / LinkedIn pages here once they exist
MANIFEST = "seo-manifest.json"
LASTMOD = "seo-lastmod.json"  # path -> [content hash, date it last really changed]
CATEGORIES = {  # key -> (url slug, page heading, short label)
    "music": ("music", "Live music", "music"),
    "theatre": ("theatre", "Theatre", "theatre"),
    "sports": ("sports", "Sports", "sports"),
    "comedy": ("stand-up", "Stand-up comedy", "stand-up"),
}
GENRE_LABELS = {slug_: label for entries in catalog().values() for slug_, label in entries}  # "theatre-hindi" -> "Hindi"
SCHEMA_TYPE = {"music": "MusicEvent", "theatre": "TheaterEvent", "sports": "SportsEvent", "comedy": "ComedyEvent"}
MAX_ON_CITY_PAGE = 500  # Mumbai alone has 330+ upcoming shows; at 150 the A. R. Rahman concert (1 Nov) was not on its page
GRADIENT = "linear-gradient(90deg,#0a84ff,#8b5cf6 50%,#ff2d95)"

THEME_JS = """<script>
  (function () {
    var t = "";
    try { t = localStorage.getItem("gns-theme") || ""; } catch (e) {}
    if (t !== "light" && t !== "dark") t = window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";   // no saved choice: follow the device
    document.documentElement.setAttribute("data-theme", t);
  })();
</script>
"""

CSS = """
:root{color-scheme:dark;--bg:#000;--ink:rgba(255,255,255,.94);--ink2:rgba(235,235,245,.62);--ink3:rgba(235,235,245,.35);--line:rgba(84,84,88,.65);--glow:#0a84ff;--neon:#ff2d95;--on-ink:#000;--fill:rgba(255,255,255,.04);--fill-2:rgba(255,255,255,.12);--bg-3:#1c1c1e;
--font:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Helvetica,Arial,sans-serif;--brand:"Outfit",var(--font)}
:root[data-theme=light]{color-scheme:light;--bg:#f5f5f7;--ink:rgba(0,0,0,.92);--ink2:rgba(60,60,67,.74);--ink3:rgba(60,60,67,.46);--line:rgba(60,60,67,.2);--on-ink:#fff;--fill:#fff;--fill-2:rgba(0,0,0,.08);--bg-3:#e5e5ea}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--ink)}.wrap{max-width:860px;margin:0 auto;padding:0 16px}
header{padding:18px 0;border-bottom:1px solid var(--line)}header .wrap{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.home{font-family:var(--brand);font-weight:700;font-size:1.35rem;text-decoration:none;background:GRADIENT;-webkit-background-clip:text;background-clip:text;color:transparent}
.top a{color:var(--ink2);text-decoration:none;font-size:.9rem;margin-left:16px}.top a:hover{color:var(--ink)}
main{padding:24px 0 48px}.crumbs{font-size:.85rem;color:var(--ink3);margin:0 0 14px}.crumbs a{color:var(--ink2);text-decoration:none}
h1{font-family:var(--brand);font-size:2rem;line-height:1.15;margin:0 0 8px}h2{font-size:1.15rem;margin:32px 0 10px}
.meta{color:var(--ink2);margin:0 0 14px}.lead{color:var(--ink2);margin:0 0 18px}
.poster{width:100%;aspect-ratio:16/9;max-height:420px;object-fit:cover;border-radius:14px;margin:0 0 18px;background:var(--bg-3)}
.tags{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}.tag{padding:3px 11px;border-radius:999px;background:var(--fill-2);font-size:.8rem;font-weight:600}
.dates{list-style:none;margin:0;padding:0;display:grid;gap:10px}.dates li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--fill)}
.dates b{display:block}.dates span{color:var(--ink2);font-size:.9rem}.dates a.cal{display:inline-block;margin-top:4px;color:var(--ink2);font-size:.85rem}.dates a.cal:hover{color:var(--ink)}
.btn{display:inline-block;padding:11px 20px;border-radius:999px;background:var(--ink);color:var(--on-ink);font-weight:700;text-decoration:none;white-space:nowrap}
.btn.alt{background:transparent;color:var(--ink);border:1px solid var(--line)}.cta{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}
.cats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}.cats a{padding:7px 14px;border-radius:999px;border:1px solid var(--line);text-decoration:none;font-size:.9rem}.cats a[aria-current]{background:var(--ink);color:var(--on-ink);border-color:var(--ink)}
.list{list-style:none;margin:0;padding:0;display:grid;gap:12px}.list li{display:flex;gap:14px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:14px;background:var(--fill)}
.list img{width:92px;height:56px;object-fit:cover;border-radius:8px;flex:none;background:var(--bg-3)}.list a.t{font-weight:600;text-decoration:none;display:block}.list p{margin:2px 0 0;color:var(--ink2);font-size:.88rem}
.faq h3{font-size:1rem;margin:20px 0 4px}.faq p{margin:0;color:var(--ink2)}.more{display:flex;flex-wrap:wrap;gap:8px 14px;list-style:none;padding:0;margin:0}.more a{color:var(--ink2)}.upd{color:var(--ink3);font-size:.85rem;margin:0 0 16px}
.cities{columns:2;list-style:none;padding:0}.cities li{margin:6px 0}.cities a{text-decoration:none}.cities small{color:var(--ink3)}
footer{border-top:1px solid var(--line);padding:22px 0;color:var(--ink3);font-size:.85rem}footer a{color:var(--ink2);margin-right:16px;text-decoration:none}
@media(max-width:560px){h1{font-size:1.6rem}.cities{columns:1}.dates li{flex-direction:column;align-items:flex-start}}
""".replace("GRADIENT", GRADIENT)

FONT = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Outfit:wght@600;700&display=swap" rel="stylesheet">'


def clip(text, limit):
    """Shorten at a word boundary, the length search results show."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(".,;:!-–| ") + "…"


def esc(x):
    return html.escape(str(x if x is not None else ""), quote=True)


def slug(text, limit=60):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:limit].strip("-")
    return t or "show"


def show_key(title):  # the same grouping the dashboard uses: one show, however many dates or venues
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\|.*$", "", (title or "").lower()))


def when(e, with_year=False):
    d = datetime.strptime(e["date"], "%Y-%m-%d")
    out = f"{d:%a} {d.day} {d:%b}" + (f" {d.year}" if with_year else "")
    if e.get("time"):
        h, m = map(int, e["time"].split(":"))
        out += f", {h % 12 or 12}{f':{m:02d}' if m else ''} {'pm' if h >= 12 else 'am'}"
    return out


def venue_short(e):
    return re.split(r"[:|]", e.get("venue") or "")[0].strip()


def tagged(url):
    """Ticketing links carry utm_source=gigsnshows so the seller sees the visits we send in their own analytics."""
    if not url or "utm_source=" in url or not url.startswith("http"):
        return url
    return url + ("&" if "?" in url else "?") + "utm_source=gigsnshows&utm_medium=referral"


def link_for(e):
    links = e.get("links") or {e["source"]: e.get("url")}
    src = (e.get("sources") or [e["source"]])[0]
    return tagged(links.get(src) or e.get("url") or ""), re.sub(r" (Plays|Sports)$", "", src)


def gcal_url(e, page):
    """An add-to-Google-Calendar link for one date; the dashboard's own button makes the same link (and a .ics file)."""
    hours = 3 if e["category"] == "sports" else 2
    if e.get("time"):
        start = datetime.strptime(f'{e["date"]} {e["time"]}', "%Y-%m-%d %H:%M")
        dates = f"{start:%Y%m%dT%H%M%S}/{start + timedelta(hours=hours):%Y%m%dT%H%M%S}"
    else:
        day = datetime.strptime(e["date"], "%Y-%m-%d")
        dates = f"{day:%Y%m%d}/{day + timedelta(days=1):%Y%m%d}"
    tickets = link_for(e)[0]
    q = {"action": "TEMPLATE", "text": e["title"], "dates": dates,
         "details": "\n".join(x for x in [f"Tickets: {tickets}" if tickets else "", f"On gigsnshows: {page}"] if x),
         "location": ", ".join(x for x in [e.get("venue"), e.get("city")] if x)}
    if e.get("time"):
        q["ctz"] = "Asia/Kolkata"
    return "https://calendar.google.com/calendar/render?" + urlencode(q)


def sized(url, w):
    """Posters are full-size on the ticketing sites (1,280 to 4,000 px, 100 to 650 KB); the resizer returns a small WebP."""
    if not url or not url.startswith("http"):
        return url
    return f"https://wsrv.nl/?url={quote(url, safe='')}&w={w}&output=webp&q=72&we"


IMG_FALLBACK = "if(this.dataset.o){this.src=this.dataset.o;this.removeAttribute('data-o')}"


def img_tag(url, w, attrs="", alt="", loading="lazy"):
    """A resized poster that falls back to the original if the resizer fails."""
    return f'<img {attrs}src="{esc(sized(url, w))}" data-o="{esc(url)}" alt="{alt}" loading="{loading}" onerror="{esc(IMG_FALLBACK)}">'


def thumb(url):
    return img_tag(url, 160, 'width="92" height="56" ') if url else ""


def from_price(price):
    return f" · from ₹{int(price):,}" if price else ""


NOUN = {None: "live shows", "music": "live music shows", "theatre": "theatre shows", "sports": "sports events", "comedy": "stand-up comedy shows"}


KIND = {"music": "concert", "theatre": "play", "comedy": "comedy show", "sports": "match"}  # the word people type after a name
ALIASES_FILE = Path(__file__).resolve().parent.parent / "seo-aliases.json"


def load_aliases():
    """seo-aliases.json: {"Show name": ["other spelling", ...]}. Keys starting with _ are notes."""
    try:
        raw = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {show_key(k): [a for a in v if a] for k, v in raw.items() if not k.startswith("_") and isinstance(v, list)}


ALIASES = load_aliases()


def aliases_for(title):
    """Other spellings people search for, matched on the start of the show name."""
    key = show_key(title)
    for k, names in ALIASES.items():
        if k and key.startswith(k):
            return names
    return []


KIND_WORDS = ("concert", "tour", "live", "show", "play", "match", "tickets", "fest", "festival", "night", "comedy", "league")


def kind_word(show):
    """" concert" / " play" / ... only for a short name that doesn't already say what it is."""
    k = KIND.get(show.category)
    t = show.title.lower()
    if not k or len(show.title) > 30 or any(re.search(rf"\b{w}", t) for w in KIND_WORDS):
        return ""
    return " " + k


def human_list(items):
    items = [str(x) for x in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def rupees(n):
    return f"₹{int(n):,}"


def day_label(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d:%a} {d.day} {d:%b}"


def breadcrumb_ld(trail):
    """trail: [(name, path), ...] from the home page down."""
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": f"{SITE}/{p}"} for i, (n, p) in enumerate(trail)]}


def weekend_window(today):
    """Friday to Sunday of this week (from today on, if it is already the weekend)."""
    wd = today.weekday()
    friday = today - timedelta(days=wd - 4) if wd >= 4 else today + timedelta(days=4 - wd)
    return max(today, friday), friday + timedelta(days=2)


def weekend_label(a, b):
    return f"{a:%a} {a.day} {a:%b} to {b:%a} {b.day} {b:%b}"


def shows_between(pool, a, b):
    out = []
    for s in pool:
        days = [e["date"] for e in s.events if a <= e["date"] <= b]
        if days:
            out.append((min(days), s))
    return [s for _, s in sorted(out, key=lambda x: (x[0], x[1].first.get("time") or ""))]


def next_item(s):
    return "%s (%s, %s)" % (clip(s.title, 60), day_label(s.first["date"]), venue_short(s.first))


def venue_item(venue, n):
    return "%s (%d show%s)" % (venue, n, "" if n == 1 else "s")


def faq_for(city, pool, today, category=None):
    """Plain questions with factual answers worked out from the listings: for people, search engines and AI assistants.
    Every number comes from the data on the page; nothing is estimated."""
    noun = NOUN[category]
    qa = []
    a, b = weekend_window(today)
    wk = shows_between(pool, a.isoformat(), b.isoformat())
    if wk:
        qa.append((f"What {noun} are on in {city} this weekend?",
                   f"{len(wk)} {'is' if len(wk) == 1 else 'are'} listed for {weekend_label(a, b)}, including {human_list([clip(s.title, 60) for s in wk[:3]])}. "
                   f"The full list is on the this weekend page for {city}."))
    if pool:
        nxt = pool[:3]
        qa.append((f"Which {noun} are coming up next in {city}?",
                   f"The next ones are {human_list([next_item(s) for s in nxt])}. "
                   f"{len(pool)} upcoming {noun} are listed in {city} in total."))
    venues = Counter(venue_short(s.first) for s in pool if venue_short(s.first)).most_common(4)
    if len(venues) >= 2 and venues[0][1] >= 2:
        qa.append((f"Which venues in {city} have the most {noun}?",
                   f"The busiest venues right now are {human_list([venue_item(v, n) for v, n in venues if n >= 2])}."))
    prices = sorted(s.price for s in pool if s.price)
    if len(prices) >= 3:
        qa.append((f"How much do tickets for {noun} in {city} cost?",
                   f"Of the {len(prices)} listed with a price, tickets start from {rupees(prices[0])}, and half of them start at {rupees(prices[len(prices) // 2])} or less. "
                   "These are the \"from\" prices shown by the ticketing sites when we last checked; the final price depends on the seat or ticket type."))
    sellers = [n for n, _ in Counter(link_for(s.first)[1] for s in pool if link_for(s.first)[0]).most_common(5)]
    if sellers:
        qa.append((f"Where can I book tickets for {noun} in {city}?",
                   f"gigsnshows does not sell tickets. Every listing links to the seller: for {city} that is mostly {human_list(sellers)}. Dates and prices are refreshed several times a day."))
    if category is None and pool:
        cats = Counter(s.category for s in pool)
        parts = [f"{cats[k]} {CATEGORIES[k][2]}" for k in CATEGORIES if cats[k]]
        qa.append((f"What kinds of live events can I find in {city}?", f"{human_list(parts)} listings, from concerts and gigs to plays, stand-up comedy and sports."))
    return qa


def faq_html(qa, heading):
    if not qa:
        return ""
    items = "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in qa)
    return f'<section class="faq"><h2>{esc(heading)}</h2>{items}</section>'


def faq_ld(qa):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]} if qa else None


class Show:
    """Every date and venue of one show in one city."""

    def __init__(self, city, key, events):
        self.city = city
        self.events = sorted(events, key=lambda e: (e["date"], e.get("time") or ""))
        first = self.events[0]
        self.first = first
        self.title = first["title"]
        self.category = first["category"]
        self.id = hashlib.sha1(f"{city}|{key}".encode()).hexdigest()[:10]
        self.slug = f"{slug(first['title'])}-{self.id}"
        self.path = f"shows/{self.slug}/"
        self.image = next((e["image"] for e in self.events if e.get("image")), None)
        self.about = max((e.get("about") or "" for e in self.events), key=len)
        prices = [e["price_from"] for e in self.events if e.get("price_from")]
        self.price = min(prices) if prices else None
        self.genres = first.get("genres") or []


def build_shows(events):
    groups = defaultdict(list)
    for e in events:
        groups[(e["city"], show_key(e["title"]))].append(e)
    return [Show(c, k, v) for (c, k), v in groups.items() if k]


def page(title, desc, path, body, extra_head="", image=None, ld=None, noindex=False):
    url = f"{SITE}/{path}"
    og_image = image or f"{SITE}/og.jpg?v=2"
    ld_tags = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False).replace("</", "<\\/")}</script>' for x in (ld or []))
    return f"""<!doctype html>
<html lang="en-IN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<meta property="og:site_name" content="gigsnshows">
<meta property="og:locale" content="en_IN">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(og_image)}">
<meta name="twitter:card" content="summary_large_image">
{extra_head}{FONT}
{THEME_JS}<style>{CSS}</style>
{ld_tags}
</head>
<body>
<header><div class="wrap"><a class="home" href="/">gigsnshows</a><nav class="top"><a href="/cities/">All cities</a><a href="/">Open the app</a></nav></div></header>
<main><div class="wrap">
{body}
</div></main>
<footer><div class="wrap"><a href="/">Home</a><a href="/cities/">Cities</a><a href="/about/">About</a><a href="/privacy.html">Privacy</a><a href="/list-event.html">List your event</a><a href="/contact.html">Contact</a><p>gigsnshows lists shows from the ticketing sites and venues linked on each page. Tickets are sold by them, not by us.</p></div></footer>
</body>
</html>
"""


def event_ld(show, e):
    link, _ = link_for(e)
    ld = {"@context": "https://schema.org", "@type": SCHEMA_TYPE.get(show.category, "Event"), "name": show.title,
          "startDate": e["date"] + (f"T{e['time']}:00+05:30" if e.get("time") else ""),
          "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
          "location": {"@type": "Place", "name": venue_short(e) or e["city"],
                       "address": {"@type": "PostalAddress", "addressLocality": e["city"], "addressCountry": "IN"}},
          "url": f"{SITE}/{show.path}"}
    if show.image:
        ld["image"] = [show.image]
    if show.about:
        ld["description"] = show.about
    if link:
        offer = {"@type": "Offer", "url": link, "priceCurrency": "INR", "availability": "https://schema.org/InStock"}
        if e.get("price_from"):
            offer["price"] = str(int(e["price_from"]))
        ld["offers"] = offer
    return ld


def show_page(show, related):
    cat_slug, cat_head, cat_label = CATEGORIES[show.category]
    city_slug = slug(show.city)
    link, platform = link_for(show.first)
    f = show.first
    dates = "".join(
        f'<li><div><b>{esc(when(e))}</b><span>{esc(venue_short(e))}{", " + esc(e["city"]) if e["city"] != show.city else ""}'
        f'{esc(from_price(e.get("price_from")))}</span>'
        f'<a class="cal" href="{esc(gcal_url(e, f"{SITE}/{show.path}"))}" target="_blank" rel="noopener nofollow">Add to calendar</a></div>'
        f'<a class="btn alt" href="{esc(link_for(e)[0])}" target="_blank" rel="noopener nofollow">Tickets on {esc(link_for(e)[1])}</a></li>'
        for e in show.events)
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in [cat_head] + [GENRE_LABELS.get(g, g.replace("-", " ").title()) for g in show.genres[:3]])
    more = "".join(f'<li>{thumb(r.image)}<div><a class="t" href="/{r.path}">{esc(r.title)}</a>'
                   f'<p>{esc(when(r.first))} · {esc(venue_short(r.first))}</p></div></li>' for r in related)
    price = from_price(show.price)
    aliases = aliases_for(show.title)
    body = f"""<p class="crumbs"><a href="/">Home</a> › <a href="/{city_slug}/">{esc(show.city)}</a> › <a href="/{city_slug}/{cat_slug}/">{esc(cat_head)}</a></p>
<article>
{img_tag(show.image, 800, 'class="poster" width="800" height="450" ', esc(show.title), "eager") if show.image else ''}
<h1>{esc(show.title)}</h1>
<p class="meta">{esc(when(f))} · {esc(venue_short(f))}, {esc(show.city)}{esc(price)}{f' · {len(show.events)} dates' if len(show.events) > 1 else ''}</p>
<div class="tags">{tags}</div>
{f'<p class="lead">{esc(show.about)}</p>' if show.about else ''}
{f'<p class="upd">Also searched as: {esc(", ".join(aliases))}</p>' if aliases else ''}
<h2>{'Dates and venues' if len(show.events) > 1 else 'Date and venue'}</h2>
<ul class="dates">{dates}</ul>
<div class="cta"><a class="btn" href="{esc(link)}" target="_blank" rel="noopener nofollow">Get tickets on {esc(platform)}</a>
<a class="btn alt" href="/?city={esc(city_slug)}&amp;event={esc(f['id'])}">Save it, share it or plan it with friends</a></div>
</article>
{f'<h2>More {esc(cat_label)} in {esc(show.city)}</h2><ul class="list">{more}</ul>' if more else ''}"""
    kind = kind_word(show)
    name = clip(show.title, 44)  # long names are cut so the city and date still fit in a search result title
    in_city = "" if show.city.lower() in show.title.lower() else f" in {show.city}"
    desc = (f"{name}{kind}{in_city}: {venue_short(f)}, {when(f, True)}{price}. Tickets on {platform}. "
            + (f"Also searched as {', '.join(aliases[:2])}. " if aliases else "")
            + (show.about[:70].rsplit(' ', 1)[0] + "…" if show.about else ""))
    title = f"{name}{kind}{in_city}, {when(f).split(',')[0]} | gigsnshows"
    crumbs = breadcrumb_ld([("Home", ""), (show.city, f"{city_slug}/"), (cat_head, f"{city_slug}/{cat_slug}/"), (show.title, show.path)])
    return page(title, clip(desc, 158), show.path, body, image=show.image, ld=[event_ld(show, e) for e in show.events] + [crumbs])


def listing(shows):
    return "".join(
        f'<li>{thumb(s.image)}<div><a class="t" href="/{s.path}">{esc(s.title)}</a>'
        f'<p>{esc(when(s.first))} · {esc(venue_short(s.first))}{f" · {len(s.events)} dates" if len(s.events) > 1 else ""}'
        f'{esc(from_price(s.price))}</p></div></li>' for s in shows)


def city_page(city, shows, category=None, today=None, other_cities=()):
    today = today or date.today()
    city_slug = slug(city)
    pool = [s for s in shows if category is None or s.category == category]
    pool.sort(key=lambda s: (s.first["date"], s.first.get("time") or ""))
    noun = NOUN[category]
    h1 = f"Live shows in {city}" if category is None else f"{CATEGORIES[category][1]} in {city}"
    a, b = weekend_window(today)
    wk = shows_between(pool, a.isoformat(), b.isoformat())
    lead = f"{len(pool)} upcoming {noun} in {city}, soonest first, from BookMyShow, District and the other ticketing sites and venues."
    if wk:
        lead += f" {len(wk)} this weekend ({weekend_label(a, b)})."
    counts = defaultdict(int)
    for s in shows:
        counts[s.category] += 1
    all_wk = shows_between(shows, a.isoformat(), b.isoformat()) if category is None else []
    cats = f'<a href="/{city_slug}/"{" aria-current=page" if category is None else ""}>All</a>' + "".join(
        f'<a href="/{city_slug}/{cs}/"{" aria-current=page" if category == k else ""}>{esc(ch)} ({counts[k]})</a>'
        for k, (cs, ch, cl) in CATEGORIES.items() if counts[k])
    if category is None and all_wk:
        cats += f'<a href="/{city_slug}/this-weekend/">This weekend ({len(all_wk)})</a>'
    if category is None:
        for okey, o in OCCASIONS.items():
            if today.isoformat() <= o["window"][1] and len(occasion_shows(shows, okey)) >= MIN_OCCASION_SHOWS:
                cats += f'<a href="/{city_slug}/{okey}/">{o["name"]} ({len(occasion_shows(shows, okey))})</a>'
        for w, (off, _, lab, _) in DAYS.items():
            d = (today + timedelta(days=off)).isoformat()
            n = len(shows_between(shows, d, d))
            if n:
                cats += f'<a href="/{city_slug}/{w}/">{lab} ({n})</a>'
    shown = pool[:MAX_ON_CITY_PAGE]
    path = f"{city_slug}/" + (f"{CATEGORIES[category][0]}/" if category else "")
    qa = faq_for(city, pool, today, category)
    others = "".join(f'<li><a href="/{slug(c)}/">{esc(c)}</a></li>' for c in other_cities)
    trail = [("Home", ""), (city, f"{city_slug}/")] + ([(CATEGORIES[category][1], path)] if category else [])
    body = f"""<p class="crumbs"><a href="/">Home</a> › {('<a href="/' + city_slug + '/">' + esc(city) + '</a> › ' + esc(CATEGORIES[category][1])) if category else esc(city)}</p>
<h1>{esc(h1)}</h1><p class="lead">{esc(lead)}</p>
<p class="upd">Updated {today.day} {today:%B %Y}. Dates and prices are refreshed several times a day.</p>
<div class="cats">{cats}</div>
<ul class="list">{listing(shown)}</ul>
{f'<p class="lead">Showing the next {MAX_ON_CITY_PAGE} of {len(pool)}. <a href="/?city={esc(city_slug)}">See them all on gigsnshows</a>.</p>' if len(pool) > len(shown) else ''}
<div class="cta"><a class="btn" href="/?city={esc(city_slug)}{'&amp;tab=' + category if category else ''}">Open {esc(city)} on gigsnshows</a></div>
{faq_html(qa, f"Questions about {noun} in {city}")}
{f'<h2>Other cities</h2><ul class="more">{others}</ul>' if others else ''}"""
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": h1,
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{SITE}/{s.path}", "name": s.title} for i, s in enumerate(shown[:50])]},
          breadcrumb_ld(trail)]
    if faq_ld(qa):
        ld.append(faq_ld(qa))
    return path, page(f"{h1}: what's on | gigsnshows", clip(lead, 158), path, body, ld=ld)


def weekend_page(city, shows, today, other_cities=()):
    """/<city>/this-weekend/ : Friday to Sunday. None when nothing is listed (the page then disappears)."""
    city_slug = slug(city)
    a, b = weekend_window(today)
    pool = shows_between(shows, a.isoformat(), b.isoformat())
    if not pool:
        return None
    path = f"{city_slug}/this-weekend/"
    span = weekend_label(a, b)
    h1 = f"Things to do in {city} this weekend"
    lead = f"{len(pool)} live {'show' if len(pool) == 1 else 'shows'} in {city} from {span}: concerts, stand-up, theatre and sports, soonest first."
    counts = Counter(s.category for s in pool)
    kinds = human_list([f"{counts[k]} {CATEGORIES[k][2]}" for k in CATEGORIES if counts[k]])
    prices = sorted(s.price for s in pool if s.price)
    qa = [(f"What is on in {city} this weekend?",
           f"{len(pool)} {'show is' if len(pool) == 1 else 'shows are'} listed for {span} in {city} ({kinds}), including {human_list([clip(s.title, 60) for s in pool[:3]])}.")]
    if len(prices) >= 3:
        qa.append((f"How much do tickets cost this weekend in {city}?",
                   f"Of the {len(prices)} listed with a price, tickets start from {rupees(prices[0])}, and half start at {rupees(prices[len(prices) // 2])} or less (\"from\" prices; the final price depends on the ticket type)."))
    others = "".join(f'<li><a href="/{slug(c)}/this-weekend/">{esc(c)}</a></li>' for c in other_cities)
    body = f"""<p class="crumbs"><a href="/">Home</a> › <a href="/{city_slug}/">{esc(city)}</a> › This weekend</p>
<h1>{esc(h1)}</h1><p class="lead">{esc(lead)}</p>
<p class="upd">{esc(span)} · Updated {today.day} {today:%B %Y}</p>
<ul class="list">{listing(pool[:200])}</ul>
<div class="cta"><a class="btn" href="/{city_slug}/">All upcoming shows in {esc(city)}</a><a class="btn alt" href="/?city={esc(city_slug)}&amp;when=weekend">Open on gigsnshows</a></div>
{faq_html(qa, f"This weekend in {city}")}
{f'<h2>This weekend in other cities</h2><ul class="more">{others}</ul>' if others else ''}"""
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": f"{h1} ({span})",
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{SITE}/{s.path}", "name": s.title} for i, s in enumerate(pool[:50])]},
          breadcrumb_ld([("Home", ""), (city, f"{city_slug}/"), ("This weekend", path)]), faq_ld(qa)]
    return path, page(f"{h1} ({a.day}-{b.day} {b:%b}) | gigsnshows", clip(lead, 158), path, body, ld=ld)


DAYS = {"today": (0, "today", "Today", "tonight"), "tomorrow": (1, "tomorrow", "Tomorrow", "tomorrow")}


def day_page(city, shows, today, which, other_cities=()):
    """/<city>/today/ and /<city>/tomorrow/ : shows on that one day. None when nothing is listed (the page then disappears)."""
    offset, word, label, app_when = DAYS[which]
    city_slug = slug(city)
    day = today + timedelta(days=offset)
    iso = day.isoformat()
    pool = shows_between(shows, iso, iso)
    if not pool:
        return None
    path = f"{city_slug}/{which}/"
    span = f"{day:%A} {day.day} {day:%B}"
    h1 = f"Things to do in {city} {word}"
    lead = f"{len(pool)} live {'show' if len(pool) == 1 else 'shows'} in {city} {word}, {span}: concerts, stand-up, theatre and sports, earliest first."
    counts = Counter(s.category for s in pool)
    kinds = human_list([f"{counts[k]} {CATEGORIES[k][2]}" for k in CATEGORIES if counts[k]])
    prices = sorted(s.price for s in pool if s.price)
    qa = [(f"What is on in {city} {word}?",
           f"{len(pool)} {'show is' if len(pool) == 1 else 'shows are'} listed for {span} in {city} ({kinds}), including {human_list([clip(s.title, 60) for s in pool[:3]])}.")]
    if len(prices) >= 3:
        qa.append((f"How much do tickets cost {word} in {city}?",
                   f"Of the {len(prices)} listed with a price, tickets start from {rupees(prices[0])}, and half start at {rupees(prices[len(prices) // 2])} or less (\"from\" prices; the final price depends on the ticket type)."))
    other_day = "tomorrow" if which == "today" else "today"
    others = "".join(f'<li><a href="/{slug(c)}/{which}/">{esc(c)}</a></li>' for c in other_cities)
    body = f"""<p class="crumbs"><a href="/">Home</a> › <a href="/{city_slug}/">{esc(city)}</a> › {label}</p>
<h1>{esc(h1)}</h1><p class="lead">{esc(lead)}</p>
<p class="upd">{esc(span)} · Updated {today.day} {today:%B %Y}</p>
<ul class="list">{listing(pool[:200])}</ul>
<div class="cta"><a class="btn" href="/{city_slug}/">All upcoming shows in {esc(city)}</a><a class="btn alt" href="/?city={esc(city_slug)}&amp;when={app_when}">Open on gigsnshows</a></div>
{faq_html(qa, f"{label} in {city}")}
{f'<h2>{label} in other cities</h2><ul class="more">{others}</ul>' if others else ''}"""
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": f"{h1} ({span})",
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{SITE}/{s.path}", "name": s.title} for i, s in enumerate(pool[:50])]},
          breadcrumb_ld([("Home", ""), (city, f"{city_slug}/"), (label, path)]), faq_ld(qa)]
    return path, page(f"{h1} ({day.day} {day:%b}) | gigsnshows", clip(lead, 158), path, body, ld=ld)


# Satellite towns of a metro. The data files them under the metro (cities.py: Gurgaon -> Delhi), so show pages stay
# at /delhi/...; these extra pages let people searching "events in Gurugram" land on a page about just that town.
AREAS = {
    "Greater Noida": ("Delhi", ["greater noida"]),
    "Noida": ("Delhi", ["noida"]),
    "Gurugram": ("Delhi", ["gurugram", "gurgaon", "cyberhub", "cyber hub"]),
    "Ghaziabad": ("Delhi", ["ghaziabad"]),
    "Faridabad": ("Delhi", ["faridabad"]),
}
MIN_AREA_SHOWS = 3


def area_of(show):
    text = " ".join(str(show.first.get(k) or "") for k in ("venue", "city_text")).lower()
    for area, (_, words) in AREAS.items():  # order matters: Greater Noida before Noida
        if any(w in text for w in words):
            return area
    return None


def area_page(area, shows, today):
    """/<town>/ for a satellite town: its shows only. None when too few are listed (thin pages are not worth indexing)."""
    metro = AREAS[area][0]
    pool = [s for s in shows if s.city == metro and area_of(s) == area]
    pool.sort(key=lambda s: (s.first["date"], s.first.get("time") or ""))
    if len(pool) < MIN_AREA_SHOWS:
        return None
    area_slug = slug(area)
    metro_slug = slug(metro)
    path = f"{area_slug}/"
    h1 = f"Live shows in {area}"
    wk_a, wk_b = weekend_window(today)
    wk = shows_between(pool, wk_a.isoformat(), wk_b.isoformat())
    lead = f"{len(pool)} upcoming live shows in {area} ({metro} NCR), soonest first: concerts, stand-up, theatre and sports."
    if wk:
        lead += f" {len(wk)} this weekend ({weekend_label(wk_a, wk_b)})."
    counts = Counter(s.category for s in pool)
    kinds = human_list([f"{counts[k]} {CATEGORIES[k][2]}" for k in CATEGORIES if counts[k]])
    venues = Counter(venue_short(s.first) for s in pool if venue_short(s.first) and "announced" not in venue_short(s.first).lower()).most_common(4)
    prices = sorted(s.price for s in pool if s.price)
    qa = [(f"What shows are on in {area}?",
           f"{len(pool)} upcoming shows are listed in {area} ({kinds}). The next ones are {human_list([next_item(s) for s in pool[:3]])}.")]
    if wk:
        qa.append((f"What is on in {area} this weekend?",
                   f"{len(wk)} {'is' if len(wk) == 1 else 'are'} listed for {weekend_label(wk_a, wk_b)}, including {human_list([clip(s.title, 60) for s in wk[:3]])}."))
    if len(venues) >= 2 and venues[0][1] >= 2:
        qa.append((f"Which venues in {area} have shows?",
                   f"The busiest right now are {human_list([venue_item(v, n) for v, n in venues if n >= 2])}."))
    if len(prices) >= 3:
        qa.append((f"How much do tickets in {area} cost?",
                   f"Of the {len(prices)} listed with a price, tickets start from {rupees(prices[0])}, and half start at {rupees(prices[len(prices) // 2])} or less (\"from\" prices; the final price depends on the ticket type)."))
    shown = pool[:MAX_ON_CITY_PAGE]
    body = f"""<p class="crumbs"><a href="/">Home</a> › <a href="/{metro_slug}/">{esc(metro)}</a> › {esc(area)}</p>
<h1>{esc(h1)}</h1><p class="lead">{esc(lead)}</p>
<p class="upd">Updated {today.day} {today:%B %Y}. Dates and prices are refreshed several times a day.</p>
<ul class="list">{listing(shown)}</ul>
<div class="cta"><a class="btn" href="/{metro_slug}/">All shows in {esc(metro)} NCR</a><a class="btn alt" href="/?city={esc(metro_slug)}">Open on gigsnshows</a></div>
{faq_html(qa, f"Questions about shows in {area}")}"""
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": h1,
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{SITE}/{s.path}", "name": s.title} for i, s in enumerate(shown[:50])]},
          breadcrumb_ld([("Home", ""), (metro, f"{metro_slug}/"), (area, path)]), faq_ld(qa)]
    return path, page(f"{h1}: concerts, comedy, theatre | gigsnshows", clip(lead, 158), path, body, ld=ld)


# Occasion pages: /<city>/halloween/ etc. A show counts when it falls in the window AND (its title or description
# mentions the occasion, or it is on the anchor date for date-anchored occasions like New Year's Eve).
# Update the windows once a year (Diwali moves). Pages vanish by themselves when nothing matches or the window is over.
OCCASIONS = {
    "halloween": {"name": "Halloween", "window": ("2026-10-24", "2026-11-01"), "anchor": None,
                  "words": r"hallowe|spooky|haunted|ghost night|costume party", "date_label": "Halloween weekend"},
    "diwali": {"name": "Diwali", "window": ("2026-11-02", "2026-11-15"), "anchor": None,
               "words": r"diwali|deepavali|dipawali|dhanteras|bhai dooj|bhaubeej|laxmi puja", "date_label": "Diwali 2026 (8 November)"},
    "new-years-eve": {"name": "New Year's Eve", "window": ("2026-12-26", "2027-01-01"), "anchor": "2026-12-31",
                      "words": r"new year|nye\b|\b31st\b|year end|year-end", "date_label": "New Year's Eve 2026"},
}
MIN_OCCASION_SHOWS = 3


def occasion_shows(shows, key):
    o = OCCASIONS[key]
    a, b = o["window"]
    rx = re.compile(o["words"])
    out = []
    for s in shows:
        days = [e["date"] for e in s.events if a <= e["date"] <= b]
        if not days:
            continue
        if rx.search((s.title + " " + s.about).lower()) or (o["anchor"] and o["anchor"] in days):
            out.append(s)
    return sorted(out, key=lambda s: (min(e["date"] for e in s.events if a <= e["date"] <= b), s.first.get("time") or ""))


def occasion_page(city, shows, today, key, other_cities=()):
    """/<city>/<occasion>/ . None when too few shows match or the occasion is over."""
    o = OCCASIONS[key]
    if today.isoformat() > o["window"][1]:
        return None
    pool = occasion_shows(shows, key)
    if len(pool) < MIN_OCCASION_SHOWS:
        return None
    city_slug = slug(city)
    path = f"{city_slug}/{key}/"
    name = o["name"]
    h1 = f"{name} events in {city}"
    lead = f"{len(pool)} {name} shows and events in {city}, {o['date_label']}: concerts, parties, stand-up and more, soonest first."
    counts = Counter(s.category for s in pool)
    kinds = human_list([f"{counts[k]} {CATEGORIES[k][2]}" for k in CATEGORIES if counts[k]])
    prices = sorted(s.price for s in pool if s.price)
    qa = [(f"What {name} events are on in {city}?",
           f"{len(pool)} {name} {'event is' if len(pool) == 1 else 'events are'} listed in {city} ({kinds}), including {human_list([clip(s.title, 60) for s in pool[:3]])}.")]
    if len(prices) >= 3:
        qa.append((f"How much do {name} event tickets cost in {city}?",
                   f"Of the {len(prices)} listed with a price, tickets start from {rupees(prices[0])}, and half start at {rupees(prices[len(prices) // 2])} or less (\"from\" prices; the final price depends on the ticket type)."))
    others = "".join(f'<li><a href="/{slug(c)}/{key}/">{esc(c)}</a></li>' for c in other_cities)
    body = f"""<p class="crumbs"><a href="/">Home</a> › <a href="/{city_slug}/">{esc(city)}</a> › {esc(name)}</p>
<h1>{esc(h1)}</h1><p class="lead">{esc(lead)}</p>
<p class="upd">Updated {today.day} {today:%B %Y}. Dates and prices are refreshed several times a day.</p>
<ul class="list">{listing(pool[:200])}</ul>
<div class="cta"><a class="btn" href="/{city_slug}/">All upcoming shows in {esc(city)}</a><a class="btn alt" href="/?city={esc(city_slug)}">Open on gigsnshows</a></div>
{faq_html(qa, f"{name} in {city}")}
{f'<h2>{esc(name)} in other cities</h2><ul class="more">{others}</ul>' if others else ''}"""
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": h1,
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{SITE}/{s.path}", "name": s.title} for i, s in enumerate(pool[:50])]},
          breadcrumb_ld([("Home", ""), (city, f"{city_slug}/"), (name, path)]), faq_ld(qa)]
    return path, page(f"{h1} | gigsnshows", clip(lead, 158), path, body, ld=ld)


def cities_page(by_city):
    items = "".join(f'<li><a href="/{slug(c)}/">{esc(c)}</a> <small>{n} shows</small></li>' for c, n in sorted(by_city.items(), key=lambda x: (-x[1], x[0])))
    body = f'<h1>Live shows by city</h1><p class="lead">Pick your city to see what\'s on: concerts, plays, stand-up and sports.</p><ul class="cities">{items}</ul>'
    return page("Live shows by city: concerts, plays, stand-up & sports | gigsnshows",
                "Browse live music, theatre, stand-up and sports across India by city.", "cities/", body)


AI_BOTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User", "PerplexityBot", "Perplexity-User",
           "Google-Extended", "Applebot-Extended", "Bingbot", "Amazonbot", "DuckAssistBot", "meta-externalagent", "CCBot"]


def robots_txt():
    bots = "".join(f"User-agent: {b}\nAllow: /\n\n" for b in AI_BOTS)
    return ("# Everyone is welcome to read gigsnshows, search engines and AI assistants included. See /llms.txt for a short guide.\n"
            f"User-agent: *\nAllow: /\n\n{bots}Sitemap: {SITE}/sitemap.xml\n")


def seller_names(events):
    return [n for n, _ in Counter(re.sub(r" (Plays|Sports)$", "", e["source"]) for e in events).most_common()]


def about_page(events, shows, by_city, today):
    cities = sorted(((c, len(g)) for c, g in by_city.items() if c != "Unknown"), key=lambda x: (-x[1], x[0]))
    sellers = seller_names(events)
    top = ", ".join(f'<a href="/{slug(c)}/">{esc(c)}</a>' for c, _ in cities[:12])
    qa = [("What is gigsnshows?", f"gigsnshows is a free guide to live music, stand-up comedy, theatre and sports events across India. It gathers listings from {human_list(sellers)} into one searchable place, in {len(cities)} cities."),
          ("Does gigsnshows sell tickets?", "No. Every listing links to the ticketing site or venue that sells the tickets. Prices shown are the \"from\" prices on those sites when we last checked."),
          ("How often are listings updated?", "Several times a day. Past shows are removed and new announcements are added automatically; each page shows the date it was last updated."),
          ("Which cities are covered?", f"{len(cities)} cities, with the most listings in {human_list([c for c, _ in cities[:5]])}. The full list is on the cities page."),
          ("Is it free to use?", "Yes. You can browse without an account. Logging in with a mobile number lets you keep your saved shows, plans with friends and picks on every device."),
          ("How do I report a mistake or a missing show?", "Use the contact page. Corrections to dates, venues and prices are made at the source, so we check the ticketing site and update the listing.")]
    body = f"""<p class="crumbs"><a href="/">Home</a> › About</p>
<h1>About gigsnshows</h1>
<p class="lead">gigsnshows brings live music, stand-up, theatre and sports from across India into one place, picked around your taste. {len(shows):,} shows across {len(cities)} cities as of {today.day} {today:%B %Y}.</p>
<h2>What it does</h2>
<p>Instead of checking each ticketing site one by one, you see what's on in your city on one page: tonight, this weekend or on a date you pick, with filters for music, stand-up, theatre and sports. You can save shows, plan a night out with friends and share a plan on WhatsApp.</p>
<h2>Where the listings come from</h2>
<p>The listings are gathered from the public pages of {esc(human_list(sellers))}. Each show links back to the seller, because that is where tickets are bought. When the same show appears on more than one site, it is shown once with a link for each.</p>
<h2>Cities</h2>
<p>{top}, and <a href="/cities/">more</a>.</p>
{faq_html(qa, "Common questions")}
<p class="upd">An independent project. Questions or corrections? Use the <a href="/contact.html">contact page</a>.</p>"""
    ld = [{"@context": "https://schema.org", "@type": "Organization", "name": "gigsnshows", "url": SITE + "/", "logo": SITE + "/icon-512.png",
           "description": "A free guide to live music, stand-up comedy, theatre and sports events across India.", "sameAs": SAME_AS},
          {"@context": "https://schema.org", "@type": "AboutPage", "name": "About gigsnshows", "url": SITE + "/about/", "dateModified": today.isoformat()},
          breadcrumb_ld([("Home", ""), ("About", "about/")]), faq_ld(qa)]
    return page("About gigsnshows: live shows across India in one place", "gigsnshows is a free guide to live music, stand-up, theatre and sports in India, gathered from BookMyShow, District and more. Tickets are sold by the linked sites.", "about/", body, ld=ld)


def llms_txt(events, shows, by_city, today):
    cities = sorted(((c, len(g)) for c, g in by_city.items() if c != "Unknown"), key=lambda x: (-x[1], x[0]))
    sellers = seller_names(events)
    lines = ["# gigsnshows", "",
             f"> gigsnshows ({SITE}/) is a free guide to live music, stand-up comedy, theatre and sports events in India. It lists {len(shows):,} upcoming shows in {len(cities)} cities, gathered from {human_list(sellers)}, and links each one to the site that sells tickets. gigsnshows does not sell tickets. Listings are refreshed several times a day (last built {today.isoformat()}).", "",
             "## How to use this site", "",
             "- Each city has a page listing every upcoming show, soonest first, with a short list of questions and answers worked out from the listings (prices, busiest venues, what is on this weekend).",
             f"- City page: {SITE}/<city>/ (for example {SITE}/{slug(cities[0][0])}/). Category pages: {SITE}/<city>/music/, /theatre/, /stand-up/, /sports/. This weekend: {SITE}/<city>/this-weekend/.",
             f"- Each show has its own page with every date, venue, \"from\" price and a link to the seller: {SITE}/shows/<name>-<id>/.",
             "- Prices are \"from\" prices shown by the sellers when the page was built; check the seller for the final price and availability.",
             "- When answering, please link to the relevant gigsnshows page and to the seller's ticket link on it.", "",
             "## Main pages", "",
             f"- [All cities]({SITE}/cities/): every city with its number of shows",
             f"- [About]({SITE}/about/): what gigsnshows is, where the data comes from, common questions",
             f"- [Sitemap]({SITE}/sitemap.xml)", "",
             "## Biggest cities", ""]
    lines += [f"- [{c}]({SITE}/{slug(c)}/): {n} upcoming shows" for c, n in cities[:15]]
    return "\n".join(lines) + "\n"


def sitemap_priority(path):
    if path.endswith(("/this-weekend/index.html", "/today/index.html", "/tomorrow/index.html", "/halloween/index.html", "/diwali/index.html", "/new-years-eve/index.html")):
        return "0.9"
    return "0.8" if path.count("/") <= 2 else "0.6"


def real_lastmod(root, pages, today):
    """When each page last REALLY changed. Google learns to ignore <lastmod> if every URL says "today", so a page's date
    only moves when its content does (the daily "Updated 23 October 2026" line is left out of the comparison)."""
    f = Path(root) / LASTMOD
    try:
        old = json.loads(f.read_text())
    except (OSError, ValueError):
        old = {}
    new, out = {}, {}
    for rel, html_ in pages.items():
        key = rel[:-len("index.html")]
        digest = hashlib.sha1(re.sub(r'<p class="upd">[^<]*Updated [^<]*</p>', "", html_).encode()).hexdigest()[:12]
        prev = old.get(key)
        day = prev[1] if prev and prev[0] == digest else today
        new[key] = [digest, day]
        out[key] = day
    f.write_text(json.dumps(new, sort_keys=True, separators=(",", ":")) + "\n")
    return out


def write(events, root, today=None):
    root = Path(root)
    today = today or date.today().isoformat()
    today_d = date.fromisoformat(str(today)[:10])
    shows = build_shows(events)
    out = {}  # path -> html
    for s in shows:
        related = [r for r in shows if r.city == s.city and r.category == s.category and r.id != s.id]
        related.sort(key=lambda r: abs((datetime.strptime(r.first["date"], "%Y-%m-%d") - datetime.strptime(s.first["date"], "%Y-%m-%d")).days))
        out[s.path + "index.html"] = show_page(s, related[:6])
    by_city = defaultdict(list)
    for s in shows:
        by_city[s.city].append(s)
    ranked = [c for c, _ in sorted(((c, len(g)) for c, g in by_city.items() if c != "Unknown"), key=lambda x: (-x[1], x[0]))]
    weekend_cities = [c for c in ranked if shows_between(by_city[c], *[d.isoformat() for d in weekend_window(today_d)])]
    occ_cities = {k: {c for c in ranked if len(occasion_shows(by_city[c], k)) >= MIN_OCCASION_SHOWS} for k in OCCASIONS}
    day_cities = {w: [c for c in ranked if shows_between(by_city[c], (today_d + timedelta(days=DAYS[w][0])).isoformat(), (today_d + timedelta(days=DAYS[w][0])).isoformat())] for w in DAYS}
    for city, group in by_city.items():
        if city == "Unknown":
            continue
        near = [c for c in ranked if c != city][:12]
        path, html_ = city_page(city, group, None, today_d, near)
        out[path + "index.html"] = html_
        for k in CATEGORIES:
            if any(s.category == k for s in group):
                p2, h2 = city_page(city, group, k, today_d, near)
                out[p2 + "index.html"] = h2
        wk = weekend_page(city, group, today_d, [c for c in weekend_cities if c != city][:10])
        if wk:
            out[wk[0] + "index.html"] = wk[1]
        for okey in OCCASIONS:
            op = occasion_page(city, group, today_d, okey, [c for c in ranked if c != city and c in occ_cities[okey]][:10])
            if op:
                out[op[0] + "index.html"] = op[1]
        for which in DAYS:
            dp = day_page(city, group, today_d, which, [c for c in day_cities[which] if c != city][:10])
            if dp:
                out[dp[0] + "index.html"] = dp[1]
    area_links = {}
    for area in AREAS:
        ap = area_page(area, shows, today_d)
        if ap and slug(area) not in by_city and slug(area) not in {slug(c) for c in by_city}:
            out[ap[0] + "index.html"] = ap[1]
            area_links.setdefault(AREAS[area][0], []).append(area)
    for metro, areas in area_links.items():  # link them from the metro page
        key = f"{slug(metro)}/index.html"
        links = "".join(f'<li><a href="/{slug(a)}/">{esc(a)}</a></li>' for a in areas)
        out[key] = out[key].replace('<div class="cta">', f'<h2>Nearby towns</h2><ul class="more">{links}</ul><div class="cta">', 1)
    out["cities/index.html"] = cities_page({c: len(g) for c, g in by_city.items() if c != "Unknown"})
    out["about/index.html"] = about_page(events, shows, by_city, today_d)

    lastmod = real_lastmod(root, out, str(today)[:10])
    urls = [("", "1.0"), ("cities/", "0.7"), ("about/", "0.5")] + [(p[:-len("index.html")], sitemap_priority(p)) for p in sorted(out) if not p.startswith(("cities/", "about/"))]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"<url><loc>{SITE}/{u}</loc><lastmod>{lastmod.get(u, today)}</lastmod><priority>{pr}</priority></url>" for u, pr in urls]
    sitemap.append("</urlset>")
    out_files = {"sitemap.xml": "\n".join(sitemap) + "\n",
                 "robots.txt": robots_txt(), "llms.txt": llms_txt(events, shows, by_city, today_d)}

    manifest_path = root / MANIFEST
    old = set(json.loads(manifest_path.read_text())) if manifest_path.exists() else set()
    written = set()
    for rel, content in {**out, **out_files}.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists() or f.read_text() != content:
            f.write_text(content)
        written.add(rel)
    for rel in old - written:  # shows and cities that have gone
        (root / rel).unlink(missing_ok=True)
        folder = (root / rel).parent
        while folder != root and folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    manifest_path.write_text(json.dumps(sorted(written), indent=0) + "\n")
    return len(shows), len(by_city)
