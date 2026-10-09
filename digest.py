#!/usr/bin/env python3
"""
The weekly picks email.

Builds the email from data/events.json: for each city the best shows for the coming weekend, a few
for early next week, and what was just announced. Nothing is sent from here.

    python digest.py                       every city with enough shows, into build/digest/
    python digest.py --city Mumbai Pune    previews of only these cities
    python digest.py --out some/folder     somewhere else
    python digest.py --today 2026-10-08    pretend it's another day (the email is built for the weekend after it)

It writes <city>.html (a preview of what a subscriber in that city sees), an index.html to flip
through them, and buttondown.json / buttondown.html: ONE email for everyone, with a block per city
wrapped in Buttondown template conditions on the city saved at signup (`subscriber.metadata.city`),
and a highlights block for anyone else. Buttondown renders it per subscriber when it sends, so
each person gets only their own city's picks. The unsubscribe link is Buttondown's merge tag;
there is no postal address in the footer (a choice, like the NMACC emails).
"""

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scrapers import seo
from scrapers.seo import SITE, build_shows, slug, venue_short, when
from scrapers.seo import esc as _esc

ROOT = Path(__file__).parent
EVENTS = ROOT / "data" / "events.json"
OUT = ROOT / "build" / "digest"

UNSUBSCRIBE = "{{ unsubscribe_url }}"  # Buttondown's merge tag; Brevo uses {{ unsubscribe }}, Mailchimp *|UNSUB|*
MIN_WEEKEND_SHOWS = 3  # a city with fewer shows than this on the weekend doesn't get an email
WEEKEND_PICKS, NEXT_PICKS, NEW_PICKS = 6, 3, 3
RECENT_DAYS = 7  # "just announced" means first listed within this many days
CATEGORY_LABEL = {"music": "Live music", "theatre": "Theatre", "comedy": "Stand-up", "sports": "Sports"}
GLOW, VIOLET, NEON = "#0a84ff", "#8b5cf6", "#ff2d95"
FAVOURITE_VENUES = re.compile(r"ncpa|nmacc|antisocial|svp|dome|^prithvi|piano man", re.I)  # the home page's "From Your Favourite Venues"
NOT_A_NIGHT_OUT = re.compile(r"\b(meet-?up|cycling|run club|board ?games?|ranking|virtual|playdate)\b", re.I)


def esc(x):
    """HTML-escape, and defuse curly braces so a show title can't be read as a template tag by the mailing service."""
    return _esc(x).replace("{", "&#123;").replace("}", "&#125;")


def today_in_india():
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def windows(today):
    """The weekend this email is about, and the few days after it."""
    wd = today.weekday()  # Monday is 0
    start = today if wd >= 4 else today + timedelta(days=4 - wd)  # Fri-Sun: what's left of this weekend
    end = start + timedelta(days=6 - start.weekday())  # that Sunday
    return (start, end), (end + timedelta(days=1), end + timedelta(days=3))  # weekend; Monday to Wednesday


def parse_day(text):
    return datetime.strptime(text, "%Y-%m-%d").date()


def in_window(e, span):
    return span[0] <= parse_day(e["date"]) <= span[1]


def score(show, e, today):
    """How much a show deserves a place: listed on several sites, fresh, well described, with a poster."""
    s = 0.0
    if len(e.get("sources") or []) > 1:
        s += 2
    if e.get("first_seen") and (today - parse_day(e["first_seen"][:10])).days <= RECENT_DAYS:
        s += 0.3
    if FAVOURITE_VENUES.search(e.get("venue") or "") or "NMACC" in (e.get("sources") or [e.get("source")]):
        s += 1
    if e.get("time") and e["time"] < "12:00":  # a night out, not a sunrise run
        s -= 1
    if NOT_A_NIGHT_OUT.search(show.title):
        s -= 3
    s += 1.5 if show.image else -2
    s += 0.5 if show.about else 0
    s += 0.3 if show.price else 0
    s += 0.3 if e.get("time") else 0
    if show.category == "sports":  # community runs and rankings aren't what a night-out email is for; a big match still can be
        s -= 1.5
    return s


def pick(shows, span, count, today, taken):
    """The best `count` shows with a date in the span, mixing kinds of show and venues rather than five of one."""
    rows = []
    for show in shows:
        if show.id in taken:
            continue
        dates = [e for e in show.events if in_window(e, span)]
        if dates:
            rows.append((show, dates[0], len(dates), score(show, dates[0], today)))
    chosen = []
    while rows and len(chosen) < count:
        def adjusted(row):
            show, e = row[0], row[1]
            same_kind = sum(1 for c in chosen if c[0].category == show.category)
            same_venue = sum(1 for c in chosen if venue_short(c[1]) == venue_short(e))
            return row[3] - 1.2 * same_kind - 1.5 * same_venue
        best = max(rows, key=adjusted)
        rows.remove(best)
        chosen.append(best)
    taken.update(c[0].id for c in chosen)
    return chosen


def build(city, shows, today):
    weekend, early = windows(today)
    taken = set()
    count_weekend = sum(1 for s in shows if any(in_window(e, weekend) for e in s.events))
    sections = [("This weekend", pick(shows, weekend, WEEKEND_PICKS, today, taken)),
                ("Early next week", pick(shows, early, NEXT_PICKS, today, taken))]
    fresh = [s for s in shows if s.id not in taken and any(e.get("first_seen") and (today - parse_day(e["first_seen"][:10])).days <= RECENT_DAYS for e in s.events)]
    sections.append(("Just announced", pick(fresh, (early[1] + timedelta(days=1), today + timedelta(days=400)), NEW_PICKS, today, taken)))
    sections = [(name, rows) for name, rows in sections if rows]
    flat = [r for _, rows in sections for r in rows]
    names = [r[0].title for r in sections[0][1]] if sections else []  # best first
    first_two = ", ".join(clip_title(n) for n in names[:2])
    more = max(count_weekend - 2, 0)
    subject = f"This weekend in {city}: {first_two}" + (f" and {more} more" if more and first_two else "") if first_two else f"What's on in {city}"
    pre = f"{weekend[0]:%a} {weekend[0].day} – {weekend[1]:%a} {weekend[1].day} {weekend[1]:%b}: " + ", ".join(
        sorted({CATEGORY_LABEL.get(r[0].category, r[0].category).lower() for r in flat}, key=lambda x: ["live music", "theatre", "stand-up", "sports"].index(x) if x in ["live music", "theatre", "stand-up", "sports"] else 9))
    return {"city": city, "subject": subject, "preheader": pre, "weekend": [str(weekend[0]), str(weekend[1])], "weekend_shows": count_weekend,
            "skip": count_weekend < MIN_WEEKEND_SHOWS, "sections": sections, "picks": len(flat)}


def clip_title(title, limit=34):
    t = re.sub(r"\s+", " ", re.sub(r"\s*[|:–—-]\s.*$", "", title)).strip(" |:–—-")
    t = t if len(t) >= 6 else title
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0].rstrip(",.;:!-– ") + "…"


def utm(city, today):
    return f"utm_source=weekly&utm_medium=email&utm_campaign={slug(city)}-{today:%Y%m%d}"


def show_url(show, city, today):
    return f"{SITE}/{show.path}?{utm(city, today)}"


def meta_line(show, e, n_dates):
    bits = [when(e), venue_short(e)]
    if show.price:
        bits.append(f"from ₹{int(show.price):,}")
    return " · ".join(b for b in bits if b) + (f" · +{n_dates - 1} more date{'s' if n_dates > 2 else ''} this period" if n_dates > 1 else "")


def card(show, e, n_dates, city, today, hero):
    url = esc(show_url(show, city, today))
    label = esc(CATEGORY_LABEL.get(show.category, show.category))
    img = ""
    if show.image:
        w, h = (520, 292) if hero else (96, 96)
        img = (f'<a href="{url}"><img src="{esc(show.image)}" width="{w}" {"" if hero else f"height={chr(34)}{h}{chr(34)} "}alt="" '
               f'style="display:block;width:{"100%" if hero else f"{w}px"};max-width:{w}px;{"" if hero else f"height:{h}px;"}object-fit:cover;border-radius:10px;border:0"></a>')
    if hero:
        return f"""<tr><td style="padding:6px 0 18px">{img}
<div style="padding-top:10px;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:{NEON}">{label}</div>
<a href="{url}" style="display:block;padding-top:2px;font-size:20px;line-height:1.25;font-weight:700;color:#111;text-decoration:none">{esc(show.title)}</a>
<div style="padding-top:4px;font-size:14px;line-height:1.45;color:#555">{esc(meta_line(show, e, n_dates))}</div></td></tr>"""
    return f"""<tr><td style="padding:0 0 16px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td width="112" valign="top" style="padding-right:14px">{img}</td>
<td valign="top"><div style="font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:{NEON}">{label}</div>
<a href="{url}" style="display:block;padding-top:1px;font-size:16px;line-height:1.3;font-weight:700;color:#111;text-decoration:none">{esc(show.title)}</a>
<div style="padding-top:3px;font-size:13px;line-height:1.45;color:#555">{esc(meta_line(show, e, n_dates))}</div></td></tr></table></td></tr>"""


def city_rows(d, today):
    """The email's body for one city: heading, the picks by section, and the button to the whole city."""
    city, first, body = d["city"], True, []
    for n, (name, rows) in enumerate(d["sections"]):
        lead, rest = rows[0], sorted(rows[1:], key=lambda r: (r[1]["date"], r[1].get("time") or ""))
        rows = [lead] + rest if n == 0 else sorted(rows, key=lambda r: (r[1]["date"], r[1].get("time") or ""))  # the best pick first, then by date
        edge = "" if first else "border-top:1px solid #e6e6ec;"
        body.append(f'<tr><td style="padding:{"4px" if first else "22px"} 0 10px;font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:{VIOLET};{edge}">{esc(name)}</td></tr>')
        for show, e, n_dates, _ in rows:
            body.append(card(show, e, n_dates, city, today, hero=first))
            first = False
    total = f"{d['weekend_shows']} shows" if d["weekend_shows"] != 1 else "1 show"
    return f"""<tr><td style="padding:22px 24px 6px">
<div style="font-size:22px;line-height:1.25;font-weight:800;color:#111">This weekend in {esc(city)}</div>
<div style="padding-top:4px;font-size:14px;color:#555">{esc(d['preheader'])}. {esc(total)} on this weekend; here are the ones we'd go to.</div></td></tr>
<tr><td style="padding:12px 24px 8px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
{"".join(body)}
</table></td></tr>
<tr><td align="center" style="padding:6px 24px 26px"><a href="{esc(f"{SITE}/?city={slug(city)}&{utm(city, today)}")}" style="display:inline-block;padding:13px 26px;border-radius:999px;background:#111;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none">See everything on in {esc(city)}</a></td></tr>"""


def fallback_rows(biggest, today):
    """For subscribers whose city has too little on (or who didn't say): the biggest cities' best picks."""
    body = []
    for d in biggest:
        body.append(f'<tr><td style="padding:14px 0 10px;font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:{VIOLET}">'
                    f'<a href="{esc(f"{SITE}/?city={slug(d["city"])}&{utm(d["city"], today)}")}" style="color:{VIOLET};text-decoration:none">{esc(d["city"])} ›</a></td></tr>')
        for show, e, n_dates, _ in d["sections"][0][1][:2]:
            body.append(card(show, e, n_dates, d["city"], today, hero=False))
    return f"""<tr><td style="padding:22px 24px 6px">
<div style="font-size:22px;line-height:1.25;font-weight:800;color:#111">This weekend across India</div>
<div style="padding-top:4px;font-size:14px;color:#555">{{% if subscriber.metadata.city %}}We don't have much on yet in {{{{ subscriber.metadata.city }}}}, so here are the highlights from the biggest cities.{{% else %}}Here are the highlights from the biggest cities.{{% endif %}}</div></td></tr>
<tr><td style="padding:6px 24px 8px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
{"".join(body)}
</table></td></tr>
<tr><td align="center" style="padding:6px 24px 26px"><a href="{esc(f"{SITE}/?utm_source=weekly&utm_medium=email&utm_campaign=india-{today:%Y%m%d}")}" style="display:inline-block;padding:13px 26px;border-radius:999px;background:#111;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none">Pick your city on gigsnshows</a></td></tr>"""


def shell(rows, preheader, today, unsubscribe):
    """The card every version of the email sits in: brand header, the body rows, and a plain footer (no postal address)."""
    return f"""<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#f2f2f7">{esc(preheader)}</div>
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
<tr><td style="padding:22px 24px;background:{VIOLET};background-image:linear-gradient(90deg,{GLOW},{VIOLET} 55%,{NEON})">
<a href="{esc(SITE)}/?utm_source=weekly&amp;utm_medium=email&amp;utm_campaign=header-{today:%Y%m%d}" style="font-size:24px;font-weight:800;letter-spacing:-.02em;color:#ffffff;text-decoration:none">gigs<span style="font-weight:500">n</span>shows</a>
<div style="padding-top:2px;font-size:13px;color:rgba(255,255,255,.88)">Your kind of night out</div></td></tr>
{rows}
<tr><td style="padding:16px 24px 22px;background:#fafafc;border-top:1px solid #e6e6ec;font-size:12px;line-height:1.55;color:#777">
You're getting this because you signed up for weekly picks at gigsnshows.com. We list shows from ticketing sites and venues; always check the seller's page before you buy.
<br><a href="{unsubscribe}" style="color:#777">Unsubscribe</a> · <a href="{esc(SITE)}/privacy.html" style="color:#777">Privacy</a></td></tr>
</table>"""


def document(fragment, title):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title></head>
<body style="margin:0;padding:0;background:#f2f2f7"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f2f2f7"><tr><td align="center" style="padding:20px 12px">
{fragment}
</td></tr></table></body></html>"""


def combined(sendable, today, unsubscribe, blocks=None):
    """One email for everyone. The mailing service shows each subscriber only the block for the city saved at signup
    (Buttondown's `subscriber.metadata.city`), and the highlights block to everyone else."""
    rows, subjects = [], []
    for i, d in enumerate([d for d in sendable if not blocks or d["city"] in blocks]):
        assert '"' not in d["city"] and "{" not in d["city"]
        test = f'subscriber.metadata.city == "{d["city"]}"'
        rows.append(f'{{% {"if" if i == 0 else "elif"} {test} %}}{city_rows(d, today)}')
        subjects.append(f'{{% {"if" if i == 0 else "elif"} {test} %}}{d["subject"].replace("{", "").replace("}", "")}')
    biggest = sorted(sendable, key=lambda d: -d["weekend_shows"])[:6]
    w0, w1 = parse_day(sendable[0]["weekend"][0]), parse_day(sendable[0]["weekend"][1])
    pre = f"{w0:%a} {w0.day} – {w1:%a} {w1.day} {w1:%b}: the shows we'd go to"
    all_rows = "".join(rows) + "{% else %}" + fallback_rows(biggest, today) + "{% endif %}"
    subject = "".join(subjects) + "{% else %}This weekend across India: " + ", ".join(
        clip_title(d["sections"][0][1][0][0].title) for d in biggest[:2]) + " and more{% endif %}"
    body = "<!-- buttondown-editor-mode: fancy -->\n" + shell(all_rows, pre, today, unsubscribe)
    return subject, body


def run(cities=None, out=OUT, today=None, unsubscribe=UNSUBSCRIBE, blocks=None):
    today = today or today_in_india()
    events = json.loads(EVENTS.read_text())["events"]
    events = [e for e in events if e["date"] >= str(today)]
    by_city = {}
    for show in build_shows(events):
        by_city.setdefault(show.city, []).append(show)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for city in sorted(by_city):
        if cities and city not in cities:
            continue
        d = build(city, by_city[city], today)
        rows.append(d)
        if d["skip"] and not cities:
            continue
        (out / f"{slug(city)}.html").write_text(document(shell(city_rows(d, today), d["preheader"], today, unsubscribe), d["subject"]))
    sendable = [d for d in rows if not d["skip"]]
    if sendable and not cities:
        subject, body = combined(sendable, today, unsubscribe, blocks)
        (out / "buttondown.json").write_text(json.dumps({"subject": subject, "body": body, "cities": [d["city"] for d in sendable if not blocks or d["city"] in blocks]}, indent=1, ensure_ascii=False) + "\n")
        (out / "buttondown.html").write_text(body)
    index = "".join(f'<li><a href="{slug(d["city"])}.html">{esc(d["city"])}</a> · {d["weekend_shows"]} shows this weekend · <i>{esc(d["subject"])}</i></li>' for d in rows if not d["skip"] or cities)
    (out / "index.html").write_text(f'<!doctype html><meta charset="utf-8"><title>Weekly picks</title><body style="font-family:sans-serif;max-width:720px;margin:30px auto;line-height:1.7"><h1>Weekly picks, built {today}</h1><ul>{index}</ul>')
    return rows, today


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", nargs="*", help="only these cities (previews; skips the combined email)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--today", help="YYYY-MM-DD, to build for another week")
    ap.add_argument("--unsubscribe", default=UNSUBSCRIBE)
    ap.add_argument("--blocks", nargs="*", help="only put these cities' blocks in the combined email (the cities that have subscribers); the highlights block is always there")
    a = ap.parse_args()
    rows, day = run(a.city, a.out, parse_day(a.today) if a.today else None, a.unsubscribe, a.blocks)
    for d in rows:
        print(f"{'skip' if d['skip'] else 'ok  '} {d['city']:<18} {d['weekend_shows']:>3} on the weekend, {d['picks']} picks  {d['subject']}")
    print(f"written to {a.out} for the weekend after {day}")
