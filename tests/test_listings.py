"""What counts as a show, and when two listings are the same show. Run: python -m pytest tests (from the repo root)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from run import dedupe  # noqa: E402
from scrapers.base import NOT_SHOWS, event, tidy_title  # noqa: E402


@pytest.mark.parametrize("title", [
    "Kidz Play Park", "Tiny Twinkles Play Zone", "Wild Wonders Kids Play Area", "Play 'N' Learn \u2013 Inorbit Mall Malad",
    "Infinity Play Go-karting", "The Rising Gun Shooting Range", "Ziel Shooting Academy", "Private Open Sailing",
    "Xs 63 - Yacht Sailing in Mumbai", "MCA Museum & Stadium Tour", "Mumbai Midnight Cycling", "Jaipur Sunrise E-CYCLING TOUR",
    "Indoor Rock Climbing \u2013 High Rock, Powai", "AN EVENING WITH SHORT FILMS", "Pottery Workshop",
])
def test_activities_are_not_shows(title):
    assert NOT_SHOWS.search(title)


@pytest.mark.parametrize("title", [
    "A R Rahman \u2013 Wonderment Tour Live in Concert", "Aamne Saamne - Marathi Play", "Diljit Dosanjh - RuPay Aura India Tour, Mumbai",
    "Hamilton", "Archery Premier League", "Playboy: a comedy", "The Play That Goes Wrong", "SBI Green Marathon S7", "Papon Live In Concert",
    "Sunburn Festival", "Where Cocktails Meet Jazz at The Hedonist",
])
def test_real_shows_are_kept(title):
    assert not NOT_SHOWS.search(title)


def show(i, title, venue, source, date="2026-10-16", city="Goa"):
    return {"id": i, "title": title, "venue": venue, "source": source, "date": date, "city": city, "url": f"https://x/{i}", "image": None,
            "price_from": None, "lang": [], "time": ""}


def test_same_show_on_two_platforms_is_one_entry():
    out = dedupe([show("a", "Classic Rock ft. Medium rare", "Hard Rock Cafe | Chennai", "District", city="Chennai"),
                  show("b", "CLASSIC ROCK ft. Medium Rare", "Hard Rock Cafe Chennai", "Skillbox", city="Chennai")])
    assert len(out) == 1 and out[0]["sources"] == ["District", "Skillbox"] and set(out[0]["links"]) == {"District", "Skillbox"}


def test_different_nights_or_cities_stay_apart():
    out = dedupe([show("a", "Comedy Night", "A", "District"), show("b", "Comedy Night", "B", "Skillbox", date="2026-10-17"),
                  show("c", "Comedy Night", "C", "thumpN", city="Pune")])
    assert len(out) == 3


@pytest.mark.parametrize("raw, city, tidy", [
    ("A R Rahman | Wonderment Tour Live in Concert | Mumbai", "Mumbai", "A R Rahman \u2013 Wonderment Tour Live in Concert"),
    ("Mere Krishn | A Live Theatrical Experience | Delhi", "Delhi", "Mere Krishn \u2013 A Live Theatrical Experience"),
    ("*AN EVENING WITH POETRY*", "Mumbai", "AN EVENING WITH POETRY"),
    ("DJ Ganesh Live at UNVRS Vagator \u2013 ", "Goa", "DJ Ganesh Live at UNVRS Vagator"),
    ("Hamilton", "Mumbai", "Hamilton"),
    ("Arijit Singh India Tour - Pune", "Pune", "Arijit Singh India Tour - Pune"),
])
def test_titles_are_tidied(raw, city, tidy):
    assert tidy_title(raw, city) == tidy


def test_tidying_a_title_never_changes_the_id():
    """A show's id (and so anyone's saved copy of it) comes from the title as the site wrote it."""
    a = event("A R Rahman | Wonderment Tour Live in Concert | Mumbai", "2026-11-01", "District", "Mumbai", "music", "Jio World Garden")
    assert a["title"] == "A R Rahman \u2013 Wonderment Tour Live in Concert"
    from scrapers.base import make_id
    assert a["id"] == make_id("A R Rahman | Wonderment Tour Live in Concert | Mumbai", "2026-11-01", "Jio World Garden")


def test_a_title_with_no_clue_is_classed_from_the_description():
    from scrapers.parsers import _description_category
    assert _description_category("Samay Raina is back on the road. Catch Samay Raina Live for an evening of stand-up, stories and chaos.") == "comedy"
    assert _description_category("An evening of music with A.R. Rahman, as his compositions come alive in a spectacular live concert.") == "music"
    assert _description_category("Splash around all day in our water park. Sports, slides and a lazy river.") is None   # not a show
    assert _description_category("Create pottery with loved ones. Play with clay and take home your piece.") is None
    assert _description_category("") is None and _description_category(None) is None


def test_a_page_remembered_as_not_a_show_is_read_again_when_the_rules_change(tmp_path, monkeypatch):
    """Samay Raina Live was filed as 'not a show' under the first rules and stayed hidden, because remembered pages were never reread."""
    import json
    from scrapers import parsers
    mem = tmp_path / "district_pages.json"
    url = "https://www.district.in/events/samay-raina-live-mumbai-shanmukhananda-1-2027-buy-tickets"
    mem.write_text(json.dumps({url: {"m": "2026-10-12", "e": []}}))          # remembered under the older rules (no "v")
    monkeypatch.setattr(parsers, "DISTRICT_PAGES", mem)
    reads = []
    monkeypatch.setattr(parsers, "get_html", lambda u, *a, **k: reads.append(u) or None)
    sitemap = f"<urlset><url><loc>{url}</loc><lastmod>2026-10-12</lastmod></url></urlset>"
    parsers.parse_district_sitemap(sitemap, "x", {"name": "District"}, {"city": "Mumbai"})
    assert reads == [url]                                                  # read again
    mem.write_text(json.dumps({url: {"m": "2026-10-12", "e": [], "v": parsers.DISTRICT_RULES}}))
    reads.clear()
    parsers.parse_district_sitemap(sitemap, "x", {"name": "District"}, {"city": "Mumbai"})
    assert reads == []                                                     # up to date: left alone


@pytest.mark.parametrize("title,description,kind", [
    ("The Philosophy of Resonance – Satinder Sartaaj Live in Delhi", "Soulful Punjabi poetry, Sufi music and high-energy Bhangra in a live experience.", "music"),
    ("Vivek Samtani Live", "Get ready for a night of unadulterated laughter with sharp wit.", "comedy"),
    ("Asees Kaur Live at Rangtaari 2026", "An unforgettable celebration that brings music, culture and more.", "music"),
    ("Chennai's First-Ever Dhandiya Night in a Theme Park", "", "music"),
    ("Rang Raass 2026", "", "music"),
    ("Tribute to Fred Again | High Big Gigs", "", "music"),
    ("Jamming Night - Mumbai", "", "music"),
    ("Kidz Water Park", "Laughter, fun and music for the whole family all day.", None),  # no "live" in the title: not enough
    ("Pinnaca 2026", "", None),
])
def test_what_kind_of_show_from_title_and_description(title, description, kind):
    from scrapers.parsers import _show_kind
    assert _show_kind(title, description) == kind


@pytest.mark.parametrize("lat,lng,city", [
    (22.5638, 88.4649, "Kolkata"),   # Newtown
    (26.8131, 81.0201, "Lucknow"),   # Ekana Stadium
    (23.1499, 72.6847, "Ahmedabad"),  # Gift City, Gandhinagar
    (19.0330, 73.0297, "Mumbai"),    # Navi Mumbai
    (28.3765, 79.4653, None),        # Bareilly: no listed city near
])
def test_a_venue_with_no_known_city_name_is_placed_by_its_map_position(lat, lng, city):
    from scrapers.cities import nearest_city
    assert nearest_city(lat, lng) == city
    assert nearest_city(None, None) is None


@pytest.mark.parametrize("title", ["Raas Garba Flea Market & Brand Expo Vol - 8", "Diwali Flea Market"])
def test_markets_are_not_shows(title):
    assert NOT_SHOWS.search(title)


def test_small_towns_on_a_tour_are_cities():
    from scrapers.cities import detect_city
    assert detect_city("Satinder Sartaaj Live in Hisar") == "Hisar"
    assert detect_city("Divine - Banaras") == "Varanasi"
    assert detect_city("Parade Ground, Yamunanagar, Haryana") == "Yamuna Nagar"


def test_symphonic_is_music():
    from scrapers.base import guess_category
    assert guess_category("Red Bull Symphonic with Sunidhi Chauhan") == "music"


@pytest.mark.parametrize("title", [
    "India Retail Investors Expo & Conference 2026 – Chennai", "Moto Summit Kochi 2026", "Aim Montessori Dasara Mahotsava - Harikatha",
    "Skanda International School Chess Championship", "WINTER ARC 2026 VIRTUAL RUN & RIDE CHALLENGE", "Small World Run Club",
    "The Fun Boardgames Meetup", "Near-Venue Stay + Festival / Double", "Seed Business School Festival 2026 - Mumbai", "Slide School - Motoverse 2026",
])
def test_trade_school_and_club_events_are_not_shows(title):
    assert NOT_SHOWS.search(title)


@pytest.mark.parametrize("title", ["Hamilton", "Zakir Khan Live", "Sunburn Arena ft. DJ Snake", "Mumbai Half Marathon", "Comedy Club Night", "School of Rock"])
def test_these_stay_shows(title):
    assert not NOT_SHOWS.search(title)


def test_a_well_known_acts_page_needs_music_in_its_description_but_not_live_in_the_title():
    from scrapers.parsers import _show_kind
    assert _show_kind("25 Years Of The Raghu Dixit Project - Pune", "The music. Iconic songs and melodies.", loose=True) == "music"
    assert _show_kind("Timezone – Dhillon Plaza", "Level up your game, claw machines, in it for the laughs!", loose=True) is None
    assert _show_kind("Divine Banaras", "A Dev Diwali boat ride on the Ganga with fireworks.", loose=True) is None


@pytest.mark.parametrize("title,before,after", [
    ("A R Rahman – Wonderment Tour Live in Concert", "theatre", "music"),
    ("Saturday Night Live - Bryan Adams Tribute Ft. LiveWire Band", "theatre", "music"),
    ("‘Light of Bhakti: Bhajans Unplugged by Siyer’", "theatre", "music"),
    ("Halloween Night (Bolly vs Kolly) ft. DJ Deepika", "theatre", "music"),
    ("Hamlet", "theatre", "theatre"),
    ("Aamne Saamne - Marathi Play", "theatre", "theatre"),
    ("A Musical Play: Mamma Mia Concert Edition", "theatre", "theatre"),   # says play: leave it
    ("Samay Raina Live", "comedy", "comedy"),
])
def test_a_concert_filed_under_theatre_is_music(title, before, after):
    from scrapers.base import fix_category
    assert fix_category({"title": title, "category": before})["category"] == after


@pytest.mark.parametrize("title", ["Resin Trinket Tray Date", "Tie Dye Art", "Japanese Bowl Kintsugi", "Candle Wax Flower Tree", "Bad Drawing Party", "Playdate with Parents",
                                   "Play Date With Parents", "Rage Room Mumbai", "Rage Therapy", "Talking to the Moon", "Japanese Sumi e Art", "DIY Shell Mirror"])
def test_art_workshops_and_rage_rooms_are_not_shows(title):
    assert NOT_SHOWS.search(title)


@pytest.mark.parametrize("title", ["Resident Evil Live Orchestra", "Tie Me Up: a play", "The Moon and Sixpence", "Date Night Comedy"])
def test_lookalike_titles_stay(title):
    assert not NOT_SHOWS.search(title)
