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
