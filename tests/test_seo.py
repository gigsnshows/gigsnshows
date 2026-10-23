import json
import re
from datetime import date

from scrapers import seo


def ev(i, title, day, city="Mumbai", category="music", venue="Hall", price=None, source="District"):
    return {"id": i, "title": title, "date": day, "time": "20:00", "city": city, "category": category, "venue": venue,
            "price_from": price, "source": source, "url": f"https://x/{i}", "genres": [], "about": ""}


def test_weekend_window_is_friday_to_sunday():
    assert seo.weekend_window(date(2026, 10, 12)) == (date(2026, 10, 16), date(2026, 10, 18))   # Monday
    assert seo.weekend_window(date(2026, 10, 16)) == (date(2026, 10, 16), date(2026, 10, 18))   # Friday
    assert seo.weekend_window(date(2026, 10, 17)) == (date(2026, 10, 17), date(2026, 10, 18))   # Saturday: what is left of it
    assert seo.weekend_window(date(2026, 10, 18)) == (date(2026, 10, 18), date(2026, 10, 18))   # Sunday


def shows():
    return seo.build_shows([ev("a", "Jazz Night", "2026-10-16", price=500, venue="Blue Room"), ev("b", "Rock Fest", "2026-10-17", price=1500, venue="Blue Room"),
                            ev("c", "Comedy Hour", "2026-10-20", category="comedy", price=300, venue="Laugh Club"), ev("d", "Play", "2026-10-25", category="theatre")])


def test_faq_answers_use_the_listings():
    s = shows()
    pool = sorted(s, key=lambda x: x.first["date"])
    qa = dict(seo.faq_for("Mumbai", pool, date(2026, 10, 14)))
    wk = qa["What live shows are on in Mumbai this weekend?"]
    assert wk.startswith("2 are listed for Fri 16 Oct to Sun 18 Oct") and "Jazz Night" in wk and "Comedy Hour" not in wk
    assert "Blue Room (2 shows)" in qa["Which venues in Mumbai have the most live shows?"]
    price = qa["How much do tickets for live shows in Mumbai cost?"]
    assert "₹300" in price and "₹500" in price and "3 listed with a price" in price
    assert "does not sell tickets" in qa["Where can I book tickets for live shows in Mumbai?"]


def test_weekend_page_disappears_when_nothing_is_on():
    s = shows()
    assert seo.weekend_page("Mumbai", s, date(2026, 10, 14)) is not None
    assert seo.weekend_page("Mumbai", s, date(2026, 11, 2)) is None


def test_every_json_ld_block_parses_and_pages_are_indian_english(tmp_path):
    events = [ev("a", "Jazz Night", "2026-10-16", price=500), ev("b", "Comedy", "2026-10-17", category="comedy", price=300),
              ev("c", "Rock", "2026-10-18", price=900)]
    seo.write(events, tmp_path, "2026-10-14")
    pages = list(tmp_path.rglob("index.html"))
    assert len(pages) > 5
    for f in pages:
        text = f.read_text()
        assert '<html lang="en-IN">' in text
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, flags=re.S):
            json.loads(block.replace("<\\/", "</"))
    assert "GPTBot" in (tmp_path / "robots.txt").read_text()
    assert "gigsnshows does not sell tickets" in (tmp_path / "llms.txt").read_text()
    assert (tmp_path / "mumbai" / "this-weekend" / "index.html").exists()


def test_day_pages_exist_only_when_something_is_on():
    s = shows()
    first = min(x.first["date"] for x in s if x.city == "Mumbai")
    d = date.fromisoformat(first)
    r = seo.day_page("Mumbai", s, d, "today")
    assert r and r[0] == "mumbai/today/" and "Things to do in Mumbai today" in r[1]
    assert seo.day_page("Mumbai", s, date(2030, 1, 1), "tomorrow") is None


def test_area_page_for_satellite_town():
    evs = [ev(i, f"Show {i}", "2026-10-25", city="Delhi", venue="The Laugh Store: DLF Cyberhub, Gurugram") for i in range(3)]
    evs.append(ev(9, "Other", "2026-10-25", city="Delhi", venue="Kamani Auditorium: Delhi"))
    s = seo.build_shows(evs)
    r = seo.area_page("Gurugram", s, date(2026, 10, 21))
    assert r and r[0] == "gurugram/" and "Show 1" in r[1] and "Kamani" not in r[1]
    assert seo.area_page("Noida", s, date(2026, 10, 21)) is None


def test_occasion_pages():
    evs = [ev(i, f"Spooky Night {i}", "2026-10-31") for i in range(3)] + [ev(9, "Jazz", "2026-10-31")]
    s = seo.build_shows(evs)
    r = seo.occasion_page("Mumbai", s, date(2026, 10, 21), "halloween")
    assert r and r[0] == "mumbai/halloween/" and "Jazz" not in r[1]
    assert seo.occasion_page("Mumbai", s, date(2026, 11, 3), "halloween") is None      # over
    assert seo.occasion_page("Mumbai", s, date(2026, 10, 21), "diwali") is None         # nothing matches
    nye = [ev(20 + i, f"Party {i}", "2026-12-31") for i in range(3)]
    assert seo.occasion_page("Mumbai", seo.build_shows(nye), date(2026, 12, 1), "new-years-eve")


def test_ticket_links_carry_utm():
    assert seo.tagged("https://x.in/a") == "https://x.in/a?utm_source=gigsnshows&utm_medium=referral"
    assert seo.tagged("https://x.in/a?id=1").endswith("&utm_source=gigsnshows&utm_medium=referral")
    assert seo.tagged("https://x.in/a?utm_source=z") == "https://x.in/a?utm_source=z"
    assert seo.tagged("") == ""


def test_posters_go_through_resizer_with_fallback():
    t = seo.thumb("https://cdn.example.com/a b/p.jpg?x=1")
    assert 'src="https://wsrv.nl/?url=https%3A%2F%2Fcdn.example.com' in t and "w=160" in t
    assert 'data-o="https://cdn.example.com/a b/p.jpg?x=1"' in t and "onerror=" in t
    assert seo.thumb("") == "" and seo.sized("/local.png", 160) == "/local.png"


def test_static_images_reserve_their_space():
    assert 'width="92" height="56"' in seo.thumb("https://x.in/p.jpg")
    html_ = seo.show_page(seo.build_shows([ev(1, "Big Show", "2026-11-01") | {"image": "https://x.in/p.jpg"}])[0], [])
    assert 'class="poster" width="800" height="450"' in html_ and "aspect-ratio:16/9" in html_


def test_lastmod_moves_only_when_a_page_really_changes(tmp_path):
    evs = [ev(1, "Show One", "2026-11-20"), ev(2, "Show Two", "2026-11-21")]
    seo.write(evs, tmp_path, "2026-10-20")
    seo.write(evs, tmp_path, "2026-10-22")                      # same content, two days later
    sm = (tmp_path / "sitemap.xml").read_text()
    show = [u for u in re.findall(r"<loc>([^<]*/shows/[^<]*)</loc><lastmod>([^<]*)", sm)]
    assert show and all(d == "2026-10-20" for _, d in show)
    seo.write(evs + [ev(3, "Show Three", "2026-11-22", city="Delhi")], tmp_path, "2026-10-23")   # Delhi gains a show
    sm = (tmp_path / "sitemap.xml").read_text()
    assert re.search(r"/delhi/</loc><lastmod>2026-10-23", sm)
    assert re.search(r"/shows/show-one-[0-9a-f]+/</loc><lastmod>2026-10-20", sm)


def test_venue_and_tour_hub_pages(tmp_path):
    evs = [ev(i, f"Gig {i}", f"2026-11-{10 + i}", venue="Blue Hall: Bandra") for i in range(3)]
    evs += [ev(10 + i, "Big Artist India Tour", f"2026-12-0{i + 1}", city=c) for i, c in enumerate(["Mumbai", "Delhi", "Pune"])]
    seo.write(evs, tmp_path, "2026-10-23")
    v = (tmp_path / "mumbai" / "venue" / "blue-hall" / "index.html").read_text()
    assert "Shows at Blue Hall, Mumbai" in v and "Gig 1" in v
    t = (tmp_path / "tour" / "big-artist-india-tour" / "index.html").read_text()
    assert "listed in 3 cities" in t and "Delhi" in t and "Pune" in t
    assert "/mumbai/venue/blue-hall/" in (tmp_path / "mumbai" / "index.html").read_text()
    shows_dir = tmp_path / "shows"
    assert any("All shows at Blue Hall" in p.read_text() for p in shows_dir.glob("*/index.html"))
    sm = (tmp_path / "sitemap.xml").read_text()
    assert "/tour/big-artist-india-tour/" in sm and "/mumbai/venue/blue-hall/" in sm


def test_small_venues_and_one_city_shows_get_no_hub(tmp_path):
    evs = [ev(1, "A", "2026-11-10", venue="Tiny Room"), ev(2, "B", "2026-11-11", venue="Tiny Room"), ev(3, "Solo Tour", "2026-12-01"), ev(4, "Solo Tour", "2026-12-02", city="Delhi")]
    seo.write(evs, tmp_path, "2026-10-23")
    assert not (tmp_path / "mumbai" / "venue").exists() and not (tmp_path / "tour").exists()


def test_gone_shows_become_ended_pages_then_disappear(tmp_path):
    evs = [ev(1, "Raas Night", "2026-10-20"), ev(2, "Other Gig", "2026-12-20")]
    seo.write(evs, tmp_path, "2026-10-19")
    gone = next(p for p in (tmp_path / "shows").iterdir() if p.name.startswith("raas-night"))
    assert "Get tickets" in (gone / "index.html").read_text()
    seo.write(evs[1:], tmp_path, "2026-10-23")                       # the show has dropped out of the listings
    h = (gone / "index.html").read_text()
    assert "This event has ended." in h and "Get tickets" not in h and "Tickets on" not in h and "calendar.google" not in h
    assert "(ended) | gigsnshows" in h and '"offers"' not in h and "What is on in Mumbai" in h
    assert f"/shows/{gone.name}/" not in (tmp_path / "sitemap.xml").read_text()
    assert f"shows/{gone.name}/index.html" in (tmp_path / "seo-manifest.json").read_text()
    seo.write(evs[1:], tmp_path, "2026-11-20")                       # still kept after a month
    assert gone.exists()
    seo.write(evs[1:], tmp_path, "2027-02-10")                       # more than 90 days: removed
    assert not gone.exists()


def test_relisted_show_is_live_again(tmp_path):
    evs = [ev(1, "Raas Night", "2026-10-20"), ev(2, "Other Gig", "2026-12-20")]
    seo.write(evs, tmp_path, "2026-10-19")
    seo.write(evs[1:], tmp_path, "2026-10-23")
    seo.write(evs, tmp_path, "2026-10-24")
    gone = next(p for p in (tmp_path / "shows").iterdir() if p.name.startswith("raas-night"))
    assert "This event has ended." not in (gone / "index.html").read_text()
    assert "shows/%s/index.html" % gone.name not in (tmp_path / "seo-ended.json").read_text()


def test_app_links_are_not_crawled_or_followed(tmp_path):
    seo.write([ev(1, "A Show", "2026-11-10")], tmp_path, "2026-10-23")
    robots = (tmp_path / "robots.txt").read_text()
    assert "Disallow: /*?*event=" in robots and "Disallow: /*?*city=" in robots
    show = next((tmp_path / "shows").iterdir()) / "index.html"
    h = show.read_text()
    assert 'rel="nofollow" href="/?city=mumbai&amp;event=' in h
    assert 'href="/?' not in h.replace('rel="nofollow" href="/?', "")
