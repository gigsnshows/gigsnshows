# gigsnshows

One page for live music, theatre, sports and stand-up across India's cities, collated from District, NCPA, thumpN, Skillbox, NMACC and BookMyShow.

- `index.html` – the dashboard (static, works on mobile and desktop)
- `data/events.json` – the listings the page reads
- `sources.yaml` – **where listings come from; edit this to add sites**
- `run.py` + `scrapers/` – reads every source and writes the JSON
- `.github/workflows/update.yml` – runs the collector twice a day and publishes

The **Home** tab is a browse-everything view — Tonight, This Weekend, Just Announced (shows first seen in the last few days), **Wanna Go** (tap *+ Wanna go* on any card to save it there; saved locally in your browser, and a show drops off once its date is gone from `events.json` — until you save something, this slot shows Top Recommendations instead), **From Your Favourite Venues** (edit the `FAVOURITE_VENUES` list at the top of the `<script>` in `index.html` to change which venues get a row), then one row per category.

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
| BookMyShow | browser | Also blocks automated requests; expect this one to need tuning or to fail. |

If a browser-rendered source returns 0 events, open its URL in a normal browser, confirm the listing path is still right, and check what the event links look like (adjust `link_pattern` in `sources.yaml`).

## 3. Publish a shareable URL (GitHub Pages)

1. Create a GitHub repo and push this folder.
2. Settings → Pages → Source: *Deploy from a branch*, `main`, `/ (root)`.
3. Actions tab → enable workflows. Run "Refresh listings" once manually to seed it.
4. Your dashboard is at `https://<you>.github.io/<repo>/`. It refreshes at 07:00 and 17:00 IST daily.

This site lives at **https://gigsnshows.com** (repo `gigsnshows/gigsnshows`, domain DNS at GoDaddy pointing to GitHub Pages).

**Two collectors.** District and BookMyShow refuse GitHub's cloud servers, so:
- GitHub's scheduled run (07:00 / 17:00 IST) refreshes NCPA, NMACC, Skillbox and thumpN, and keeps District/BookMyShow's last known shows (a source that returns nothing never wipes its listings).
- `collect-local.sh` runs the full collection from a Mac at 07:30 / 17:30 (or on wake if asleep) and uploads it, using a repo deploy key at `~/.ssh/gigsnshows_deploy`. It runs from its own clone at `~/.gigsnshows-collector`, scheduled by `~/Library/LaunchAgents/com.gigsnshows.collect.plist`; log in `~/Library/Logs/gigsnshows-collect.log`. To stop it: `launchctl bootout gui/$(id -u)/com.gigsnshows.collect`.

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
