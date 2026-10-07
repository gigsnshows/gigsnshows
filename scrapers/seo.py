"""
Pages for search engines (and for people who arrive from a search).

The dashboard is one JavaScript page, which Google reads poorly. So every collector run also
writes plain HTML with real content:

  /shows/<name>-<id>/       one page per show in a city, with every date and venue it runs,
                            and schema.org Event data so Google can show it as an event
  /<city>/                  what's on in a city, soonest first
  /<city>/<category>/       the same for music, theatre, sports or stand-up
  /cities/                  every city (the way crawlers find them from the home page)
  /sitemap.xml, /robots.txt

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
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from .genres import catalog

SITE = "https://gigsnshows.com"
MANIFEST = "seo-manifest.json"
CATEGORIES = {  # key -> (url slug, page heading, short label)
    "music": ("music", "Live music", "music"),
    "theatre": ("theatre", "Theatre", "theatre"),
    "sports": ("sports", "Sports", "sports"),
    "comedy": ("stand-up", "Stand-up comedy", "stand-up"),
}
GENRE_LABELS = {slug_: label for entries in catalog().values() for slug_, label in entries}  # "theatre-hindi" -> "Hindi"
SCHEMA_TYPE = {"music": "MusicEvent", "theatre": "TheaterEvent", "sports": "SportsEvent", "comedy": "ComedyEvent"}
MAX_ON_CITY_PAGE = 150
GRADIENT = "linear-gradient(90deg,#0a84ff,#8b5cf6 50%,#ff2d95)"

CSS = """
:root{color-scheme:dark;--bg:#000;--ink:rgba(255,255,255,.94);--ink2:rgba(235,235,245,.62);--ink3:rgba(235,235,245,.35);--line:rgba(84,84,88,.65);--glow:#0a84ff;--neon:#ff2d95;
--font:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Helvetica,Arial,sans-serif;--brand:"Outfit",var(--font)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--ink)}.wrap{max-width:860px;margin:0 auto;padding:0 16px}
header{padding:18px 0;border-bottom:1px solid var(--line)}header .wrap{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.home{font-family:var(--brand);font-weight:700;font-size:1.35rem;text-decoration:none;background:GRADIENT;-webkit-background-clip:text;background-clip:text;color:transparent}
.top a{color:var(--ink2);text-decoration:none;font-size:.9rem;margin-left:16px}.top a:hover{color:var(--ink)}
main{padding:24px 0 48px}.crumbs{font-size:.85rem;color:var(--ink3);margin:0 0 14px}.crumbs a{color:var(--ink2);text-decoration:none}
h1{font-family:var(--brand);font-size:2rem;line-height:1.15;margin:0 0 8px}h2{font-size:1.15rem;margin:32px 0 10px}
.meta{color:var(--ink2);margin:0 0 14px}.lead{color:var(--ink2);margin:0 0 18px}
.poster{width:100%;max-height:420px;object-fit:cover;border-radius:14px;margin:0 0 18px;background:#1c1c1e}
.tags{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}.tag{padding:3px 11px;border-radius:999px;background:rgba(255,255,255,.12);font-size:.8rem;font-weight:600}
.dates{list-style:none;margin:0;padding:0;display:grid;gap:10px}.dates li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.04)}
.dates b{display:block}.dates span{color:var(--ink2);font-size:.9rem}
.btn{display:inline-block;padding:11px 20px;border-radius:999px;background:var(--ink);color:#000;font-weight:700;text-decoration:none;white-space:nowrap}
.btn.alt{background:transparent;color:var(--ink);border:1px solid var(--line)}.cta{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}
.cats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}.cats a{padding:7px 14px;border-radius:999px;border:1px solid var(--line);text-decoration:none;font-size:.9rem}.cats a[aria-current]{background:var(--ink);color:#000;border-color:var(--ink)}
.list{list-style:none;margin:0;padding:0;display:grid;gap:12px}.list li{display:flex;gap:14px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.04)}
.list img{width:92px;height:56px;object-fit:cover;border-radius:8px;flex:none;background:#1c1c1e}.list a.t{font-weight:600;text-decoration:none;display:block}.list p{margin:2px 0 0;color:var(--ink2);font-size:.88rem}
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


def link_for(e):
    links = e.get("links") or {e["source"]: e.get("url")}
    src = (e.get("sources") or [e["source"]])[0]
    return links.get(src) or e.get("url") or "", re.sub(r" (Plays|Sports)$", "", src)


def thumb(url):
    return f'<img src="{esc(url)}" alt="" loading="lazy">' if url else ""


def from_price(price):
    return f" · from ₹{int(price):,}" if price else ""


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
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<meta property="og:site_name" content="gigsnshows">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(og_image)}">
<meta name="twitter:card" content="summary_large_image">
{extra_head}{FONT}
<style>{CSS}</style>
{ld_tags}
</head>
<body>
<header><div class="wrap"><a class="home" href="/">gigsnshows</a><nav class="top"><a href="/cities/">All cities</a><a href="/">Open the app</a></nav></div></header>
<main><div class="wrap">
{body}
</div></main>
<footer><div class="wrap"><a href="/">Home</a><a href="/cities/">Cities</a><a href="/privacy.html">Privacy</a><a href="/contact.html">Contact</a><p>gigsnshows lists shows from the ticketing sites and venues linked on each page. Tickets are sold by them, not by us.</p></div></footer>
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
        offer = {"@type": "Offer", "url": link, "priceCurrency": "INR"}
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
        f'{esc(from_price(e.get("price_from")))}</span></div>'
        f'<a class="btn alt" href="{esc(link_for(e)[0])}" target="_blank" rel="noopener nofollow">Tickets on {esc(link_for(e)[1])}</a></li>'
        for e in show.events)
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in [cat_head] + [GENRE_LABELS.get(g, g.replace("-", " ").title()) for g in show.genres[:3]])
    more = "".join(f'<li>{thumb(r.image)}<div><a class="t" href="/{r.path}">{esc(r.title)}</a>'
                   f'<p>{esc(when(r.first))} · {esc(venue_short(r.first))}</p></div></li>' for r in related)
    price = from_price(show.price)
    body = f"""<p class="crumbs"><a href="/">Home</a> › <a href="/{city_slug}/">{esc(show.city)}</a> › <a href="/{city_slug}/{cat_slug}/">{esc(cat_head)}</a></p>
<article>
{f'<img class="poster" src="{esc(show.image)}" alt="{esc(show.title)}" loading="eager">' if show.image else ''}
<h1>{esc(show.title)}</h1>
<p class="meta">{esc(when(f))} · {esc(venue_short(f))}, {esc(show.city)}{esc(price)}{f' · {len(show.events)} dates' if len(show.events) > 1 else ''}</p>
<div class="tags">{tags}</div>
{f'<p class="lead">{esc(show.about)}</p>' if show.about else ''}
<h2>{'Dates and venues' if len(show.events) > 1 else 'Date and venue'}</h2>
<ul class="dates">{dates}</ul>
<div class="cta"><a class="btn" href="{esc(link)}" target="_blank" rel="noopener nofollow">Get tickets on {esc(platform)}</a>
<a class="btn alt" href="/?city={esc(city_slug)}&amp;event={esc(f['id'])}">Save it, share it or plan it with friends</a></div>
</article>
{f'<h2>More {esc(cat_label)} in {esc(show.city)}</h2><ul class="list">{more}</ul>' if more else ''}"""
    desc = f"{show.title} at {venue_short(f)}, {show.city}: {when(f, True)}{price}. " + (show.about[:90].rsplit(' ', 1)[0] + "… " if show.about else "") + f"Tickets on {platform}."
    title = f"{clip(show.title, 46)} · {show.city}, {when(f).split(',')[0]} | gigsnshows"
    return page(title, clip(desc, 158), show.path, body, image=show.image, ld=[event_ld(show, e) for e in show.events])


def listing(shows):
    return "".join(
        f'<li>{thumb(s.image)}<div><a class="t" href="/{s.path}">{esc(s.title)}</a>'
        f'<p>{esc(when(s.first))} · {esc(venue_short(s.first))}{f" · {len(s.events)} dates" if len(s.events) > 1 else ""}'
        f'{esc(from_price(s.price))}</p></div></li>' for s in shows)


def city_page(city, shows, category=None):
    city_slug = slug(city)
    pool = [s for s in shows if category is None or s.category == category]
    pool.sort(key=lambda s: (s.first["date"], s.first.get("time") or ""))
    heads = {None: (f"Live shows in {city}", f"{len(pool)} upcoming concerts, plays, stand-up shows and sports events in {city}, soonest first, from every major ticketing site.")}
    for k, (cs, ch, cl) in CATEGORIES.items():
        heads[k] = (f"{ch} in {city}", f"{len(pool)} upcoming {cl} shows in {city}, soonest first, from every major ticketing site.")
    h1, lead = heads[category]
    counts = defaultdict(int)
    for s in shows:
        counts[s.category] += 1
    cats = f'<a href="/{city_slug}/"{" aria-current=page" if category is None else ""}>All</a>' + "".join(
        f'<a href="/{city_slug}/{cs}/"{" aria-current=page" if category == k else ""}>{esc(ch)} ({counts[k]})</a>'
        for k, (cs, ch, cl) in CATEGORIES.items() if counts[k])
    shown = pool[:MAX_ON_CITY_PAGE]
    path = f"{city_slug}/" + (f"{CATEGORIES[category][0]}/" if category else "")
    body = f"""<p class="crumbs"><a href="/">Home</a> › {('<a href="/' + city_slug + '/">' + esc(city) + '</a> › ' + esc(CATEGORIES[category][1])) if category else esc(city)}</p>
<h1>{esc(h1)}</h1><p class="lead">{esc(lead)}</p>
<div class="cats">{cats}</div>
<ul class="list">{listing(shown)}</ul>
{f'<p class="lead">Showing the next {MAX_ON_CITY_PAGE} of {len(pool)}. <a href="/?city={esc(city_slug)}">See them all on gigsnshows</a>.</p>' if len(pool) > len(shown) else ''}
<div class="cta"><a class="btn" href="/?city={esc(city_slug)}{'&amp;tab=' + category if category else ''}">Open {esc(city)} on gigsnshows</a></div>"""
    ld = [{"@context": "https://schema.org", "@type": "ItemList", "name": h1,
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{SITE}/{s.path}", "name": s.title} for i, s in enumerate(shown[:50])]}]
    return path, page(f"{h1}: what's on | gigsnshows", clip(lead, 158), path, body, ld=ld)


def cities_page(by_city):
    items = "".join(f'<li><a href="/{slug(c)}/">{esc(c)}</a> <small>{n} shows</small></li>' for c, n in sorted(by_city.items(), key=lambda x: (-x[1], x[0])))
    body = f'<h1>Live shows by city</h1><p class="lead">Pick your city to see what\'s on: concerts, plays, stand-up and sports.</p><ul class="cities">{items}</ul>'
    return page("Live shows by city: concerts, plays, stand-up & sports | gigsnshows",
                "Browse live music, theatre, stand-up and sports across India by city.", "cities/", body)


def write(events, root, today=None):
    root = Path(root)
    today = today or date.today().isoformat()
    shows = build_shows(events)
    out = {}  # path -> html
    for s in shows:
        related = [r for r in shows if r.city == s.city and r.category == s.category and r.id != s.id]
        related.sort(key=lambda r: abs((datetime.strptime(r.first["date"], "%Y-%m-%d") - datetime.strptime(s.first["date"], "%Y-%m-%d")).days))
        out[s.path + "index.html"] = show_page(s, related[:6])
    by_city = defaultdict(list)
    for s in shows:
        by_city[s.city].append(s)
    for city, group in by_city.items():
        if city == "Unknown":
            continue
        path, html_ = city_page(city, group)
        out[path + "index.html"] = html_
        for k in CATEGORIES:
            if any(s.category == k for s in group):
                p2, h2 = city_page(city, group, k)
                out[p2 + "index.html"] = h2
    out["cities/index.html"] = cities_page({c: len(g) for c, g in by_city.items() if c != "Unknown"})

    urls = [("", "1.0"), ("cities/", "0.7")] + [(p[:-len("index.html")], "0.8" if p.count("/") <= 2 else "0.6") for p in sorted(out) if not p.startswith("cities/")]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"<url><loc>{SITE}/{u}</loc><lastmod>{today}</lastmod><priority>{pr}</priority></url>" for u, pr in urls]
    sitemap.append("</urlset>")
    out_files = {"sitemap.xml": "\n".join(sitemap) + "\n",
                 "robots.txt": f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n"}

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
