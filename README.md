# gigsnshows

One page for live music, theatre, sports and stand-up across India's cities, collated from District, BookMyShow, NCPA, NMACC, Prithvi Theatre, The Piano Man, thumpN and Skillbox.

- `index.html` – the dashboard (static, works on mobile and desktop)
- `data/events.json` – the listings the page reads
- `sources.yaml` – **where listings come from; edit this to add sites**
- `run.py` + `scrapers/` – reads every source and writes the JSON
- `.github/workflows/update.yml` – runs the collector twice a day and publishes

First-time visitors get a two-step **onboarding**: their city, then what they're into (categories, genres, and which languages they want shows in). It's saved in their browser; "Edit" on the For you row, or "Your interests" in the footer, reopens it.

**For you** also learns from behaviour, kept in the browser only (`whatsOn.profile` in localStorage): shows opened in the swipe view for a couple of seconds, saved to Wanna Go, shared, or clicked through to buy, plus genre chips tapped and searches — each adding weight to that show's genres, category and venue (and search words). Older activity fades with a 30-day half-life. Genres you picked count for much more than a whole category you picked, and "happening soon" is only a small nudge, so a rock fan isn't shown every play on tonight. **Not for me** (thumbs-down in the swipe view) hides that show from For you and pushes down its genres, venue and language. Picked languages leave shows in other languages out of For you; shows that don't say which language stay in. The row says why ("Because you like Jazz & blues · NCPA"), and onboarding has a "Forget what I've browsed" button.

**Languages** are read by the collector (`language()` in `scrapers/genres.py`): a language named in the title, then in the description (ignoring "with English subtitles"), then — for plays — Mumbai and Pune's Marathi natyagruhas. Each show carries them as `lang`, and theatre and stand-up also get a language genre chip (Marathi, Hindi…) that never crowds out the other genres.

**Tapping any card opens the swipe view** — one show per screen (poster, genres, date, venue, description, other dates, Tickets / Wanna go / Share / Not for me) — and swiping up moves through the rest of that row, TikTok-style. "Swipe" on the For you row starts a personal feed. Back closes it. Cmd/Ctrl-click a card still goes straight to the ticket site.

**Dates:** a chip row on Home, the category tabs and search — Any time, Tonight, Tomorrow, This weekend (Fri–Sun), Next 7 days, or Pick a date (the device's own calendar). It filters everything except Wanna Go and is kept in the link (`?when=weekend`, `?when=2026-10-03`).

**Repeat shows are one card:** a show on several dates (or at several venues) appears once, at its earliest date, with a "4 dates" / "2 venues" / "2 times" badge; the swipe view lists the other dates.

**Book by voice** (the round mic button, bottom right): say or type a request such as "two tickets for stand-up this Saturday" or "jazz in Delhi next Friday". It reads the request for a show (or kind of show), a day, a city and a number of tickets, lists up to five matching shows, and each **Book** button goes to that show's ticket page, where seats are picked and paid for. If nothing fits on that day it offers other days in the same city, then other cities. It is booking-only by construction: a request that names no listed show gets "I can only book shows listed on gigsnshows". Speech-to-text is the browser's own (Chrome, Edge, Safari; elsewhere it's type-only), and nothing spoken is stored or sent to analytics — only whether a request found a show (`voice_open`, `voice_request`).

**Search** (magnifier in the top bar, or `/`) matches every word against title, venue, city, category, genres and description, in the current city or all cities, with category and genre chips to narrow the results.

The **Home** tab is a browse-everything view — **For you** (interests and behaviour first, then shows listed by several platforms and happening soon; one card per show), **Wanna Go** (tap the heart under any card; saved in your browser), Tonight, This Weekend, Just Announced (shows first seen in the last few days), **From Your Favourite Venues** (edit the `FAVOURITE_VENUES` list at the top of the `<script>` in `index.html` to change which venues get a row), then one row per category.

Each category tab has **genre chips** (Jazz & blues, Stand-up, Running, Marathi…) for the genres showing in that city. Genres are tagged by the collector from each show's title and description — the list and keywords are in `scrapers/genres.py`. Workshops and classes (pottery, painting dates…) are left out; see `NOT_SHOWS` in `scrapers/base.py`.

Shared links point to `/s/<id>`, a tiny page per show that the collector writes (`scrapers/sharepages.py`) so WhatsApp and other apps preview the link with the show's poster, title, date and venue; it forwards straight to the show on the dashboard. Pages are kept for 30 days after the show.

**Analytics** (Google Analytics 4): set `GA_MEASUREMENT_ID` at the top of the `<script>` in `index.html`. Visitors get a small notice asking before analytics cookies are set (Consent Mode; ad storage is always off); until they say OK, Google only receives cookie-free pings. Local testing (`localhost`) is never sent. Besides page views it sends these events, with parameters: `city_view` / `choose_city` (city), `view_tab` (tab), `filter_genre` (genre), `search` (search_term), `open_show` (row — which row a show was opened from), `swipe_view_open` (from), `ticket_click` (platform, item_name), `wanna_go` (item_name), `share` (method, item_id), `onboarding` (result), `set_interest` (interest), `shared_link_open` (status), `not_for_me` (item_name). To see the parameters in GA's reports, register them under Admin → Custom definitions.

A show disappears from the page the moment its start time passes (or at the end of the day, if no time is listed) — the page re-checks every minute.

Every card has a share button. On a phone it opens the native share sheet; on a laptop it offers WhatsApp or Copy link. The shared link (`?event=<id>`) opens the dashboard with that show pinned at the top under "Your friend wants to go". The **Music/Theatre/Sports/Stand-up** tabs still give the old single-category, date-bucketed view for deep links like `?tab=comedy`.

## 1. See it locally

```bash
python -m http.server 8000
```
Open http://localhost:8000. Until you've run the collector it shows sample listings and says so.

## 2. Pull real listings

```bash
pip install -r requirements.txt
pip install playwright && playwright install chromium   # for sites that render in the browser
python run.py
```
Then reload the page. Each source prints how many events it found; `--dry-run` shows counts without writing, `--only District` runs one source.

What to expect on the first run, based on how each site is built:

| Source | Works with | Notes |
|---|---|---|
| District | plain fetch | Server-rendered listing pages per category and city. Reliable. |
| NCPA | plain fetch | WordPress. Reliable. Mumbai only. |
| thumpN | browser | Home page needs rendering to list event links; event pages are then read directly. |
| Skillbox | browser | Fully browser-rendered. |
| NMACC | browser | Fully browser-rendered. Mumbai only. |
| Prithvi Theatre | plain fetch | The site's own schedule feed (plays, concerts, poetry nights; talks and screenings left out). Mumbai only. |
| The Piano Man | plain fetch | One list per club (Safdarjung, Saket, Gurugram); each show's page adds its description and price. Delhi only. |
| BookMyShow | browser | Also blocks automated requests; expect this one to need tuning or to fail. |

If a browser-rendered source returns 0 events, open its URL in a normal browser, confirm the listing path is still right, and check what the event links look like (adjust `link_pattern` in `sources.yaml`).

## 3. Publish a shareable URL (GitHub Pages)

1. Create a GitHub repo and push this folder.
2. Settings → Pages → Source: *Deploy from a branch*, `main`, `/ (root)`.
3. Actions tab → enable workflows. Run "Refresh listings" once manually to seed it.
4. Your dashboard is at `https://<you>.github.io/<repo>/`.

This site lives at **https://gigsnshows.com** (repo `gigsnshows/gigsnshows`, domain DNS at GoDaddy pointing to GitHub Pages).

**Collectors.** Different sites refuse different machines, so each source's `runs_on` in `sources.yaml` says where it's read:
- **The AWS server** (Lightsail, Mumbai, `65.0.100.130`) reads everything except BookMyShow at 07:00 and 17:00 IST: `collect.sh` from a clone at `~/gigsnshows`, scheduled by the `ubuntu` user's crontab, log in `~/collect.log`. District refuses GitHub's servers but accepts this one.
- **The Mac** reads BookMyShow only (it refuses cloud servers, AWS included) at 07:30 / 17:30, or on wake if asleep: `collect-local.sh` from `~/.gigsnshows-collector`, scheduled by `~/Library/LaunchAgents/com.gigsnshows.collect.plist`, log in `~/Library/Logs/gigsnshows-collect.log`. To stop it: `launchctl bootout gui/$(id -u)/com.gigsnshows.collect`. While the Mac is shut, BookMyShow's shows stay as last collected.
- **GitHub Actions** ("Refresh listings") is now a manual backup only.

A source that returns nothing keeps its last known shows rather than vanishing. Both collectors upload with the repo deploy key `~/.ssh/gigsnshows_deploy`; if one finds the other uploaded first, it merges its fresh results into the newer listings (`run.py --remerge`) instead of overwriting them.

Friends get their own city with a link like `…/?city=delhi&tab=comedy`, or share a single show from its card.

## 4. Adding a source

Open `sources.yaml` and add a block. Three common shapes:

**A site whose pages carry schema.org Event data** (most ticketing sites; check by viewing page source for `application/ld+json`):
```yaml
- name: Insider
  parser: jsonld
  url: https://example.com/{city}/{category}
  cities: {Mumbai: mumbai, Delhi: delhi}
  categories: {music: music, comedy: comedy}
```

**A venue site that lists events with links to each event's page:**
```yaml
- name: Prithvi Theatre
  parser: detail_pages
  link_pattern: /event/
  default_category: theatre
  urls:
    - {url: https://example.com/whats-on, city: Mumbai}
```

**A page that only fills in with JavaScript:** add `render: true` to either shape.

If a site has its own layout and none of that works, add a parser function in `scrapers/parsers.py` (the `district` and `ncpa` ones are short examples) and reference it by name.

**Cities:** every show is filed under the city its own venue or address names (`scrapers/cities.py`), not the city page it was found on — the sites' city pages mix in shows from elsewhere. Neighbourhoods and nearby towns roll up to their metro (Thane → Mumbai, Gurgaon → Delhi). A city shows up in the dropdown as soon as any source lists a show there. To make sure a city's own pages get read, add it to the `cities` map of each source in `sources.yaml`; if its name isn't recognised yet, add it to `CITIES` in `scrapers/cities.py`.

## 5. Weekly email (optional, opt-in only)

Nothing is sent by default. Make a free list on Buttondown or Substack, paste the signup link into `SIGNUP_URL` at the top of the script in `index.html`, and the "Get the weekly picks" button appears. You write the picks yourself.

## A note on scraping

None of these sites offer public APIs, so this reads their public pages. One run a day is polite; check each platform's terms if you plan to share the page widely.
