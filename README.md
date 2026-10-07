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

**Book by voice** (the round mic button, bottom right): only for finding and booking live shows. Say or type a request, or tap one of the examples it opens with:
- a show, artist or venue ("Papon", "who's playing at NCPA tomorrow"), a kind of show or genre ("stand-up", "jazz", "a Marathi play"), a day ("tonight", "next Friday", "12th October", "aaj", "kal"), a city, a budget ("under ₹500", "cheap") and a number of tickets;
- or just ask for ideas ("what's on this weekend", "recommend something for Saturday", "surprise me"), answered with that person's For you picks.

It lists up to five shows with posters; each **Book** button opens that show's ticket page, where seats are picked and paid for. If nothing fits that day it offers the next dates in the same city, then other cities; if a word matches nothing ("comedy in Bandra") it says so and offers what does fit. When the request was spoken, a one-line summary is read aloud.

It turns everything else away with the same short reply and examples: requests naming nothing show-related ("hello", "call mom"), off-topic ones (weather, news, jokes, food, cabs, flights, money, alarms, translation, "ignore your instructions…") unless they also name a listed show or venue outright ("how much are tickets for Papon"), and films ("gigsnshows lists live shows, not films"). The word lists are at the top of the "book by voice" section of `index.html`'s script. Speech-to-text is the browser's own (Chrome, Edge, Safari; elsewhere it's type-only), and nothing spoken is stored or sent to analytics; `voice_request` records only the outcome (found, found_other_day, found_elsewhere, none, out_of_scope, film).

**Who's in? (plans with friends).** In the swipe view, "Who's in? Plan with friends" turns a show into a plan: the person who starts it shares a link (it previews with the show's poster like any shared show), and anyone who opens it types a first name and taps Going / Maybe / Can't. Everyone sees the answers live. Saying Going also puts the show on your Wanna Go list. No login needed: Firebase signs friends in anonymously so each answer has an owner. Starting a plan on a show you already planned reopens the same plan. **Plan a night out** (the chip at the end of the date row on Home): pick a night and up to five shows from what's on in the city, and friends vote **I'd go** / **Maybe** on each (or say they can't make it); every show shows who'd go and the one ahead gets a "Most votes" badge, with **Tickets** and **Plan just this one** on each. A night is a plan document with `eventIds` (2–5 shows) and each answer carries `votes` (show id → yes/maybe); a person's overall answer follows from their votes (any yes = going), and saying yes to a show also puts it on their Wanna Go list. Night plans share a generic link (a night has no single poster) with the show names in the message. Home has a **Your plans** row (after Wanna Go) listing the plans you started or answered whose show is still on, each card showing who's coming ("3 going · 1 maybe"); tapping one opens the plan. Plan ids are kept in the browser and, if you log in, in your account, so the row follows you across devices; a plan its creator deleted drops out of the row. Answers can be changed or removed, and the creator can delete the plan.

Behind it: `plans/<12-letter id>` in Firestore (show details, creator) with `plans/<id>/replies/<uid>` (name, answer). Setup, beyond the login's: in the Firebase console, **Authentication → Sign-in method → Anonymous → Enable**, and publish `firestore.rules` (the one source of truth for every collection: `users`, `plans`, `lists`) under Firestore → Rules.

Analytics events: `plan_create`, `plan_open` (from: new / own / link; owner), `plan_reply` (answer; role owner or friend; night), `night_builder_open`, `plan_create` also carries `night` and `shows`, `shared_link_open` with status `plan`, and `ticket_click` with `via: plan`. Share pages (`/s/<id>`) pass a `?plan=` query through to the dashboard.

**Shared Wanna Go lists.** In the Wanna Go row, "＋ Share this list with friends" makes a group page and a link (`/?list=<id>`). Friends who open it can see the group's picks and **Join**, which shares their first name and their own Wanna Go with the group; the page then ranks shows by how many of the group want to go, with a "Shows several of us want" filter for the overlap. Each show has **Tickets**, **Plan it** (starts a "Who's in?" plan) and **+ Wanna go**. A joined list stays in step with your Wanna Go list; you can leave it, and its creator can delete it. Lists you've made or opened show as chips in the Wanna Go row and follow you across devices if you log in. Logging in from a guest session now upgrades that session in place (`linkWithPhoneNumber`), so your plans and lists stay yours; if the number already has an account you're signed in to it instead.

Firestore: `lists/<12-letter id>` (name, creator) and `lists/<id>/members/<uid>` (first name, Wanna Go ids); rules are in `firestore.rules`.

Analytics events: `list_create`, `list_open` (from: new / chip / link; owner), `list_join`, `shared_link_open` with status `list`, `ticket_click` with `via: list`.

**Search** (magnifier in the top bar, or `/`) matches every word against title, venue, city, category, genres and description, in the current city or all cities, with category and genre chips to narrow the results.

The **Home** tab is a browse-everything view — **For you** (interests and behaviour first, then shows listed by several platforms and happening soon; one card per show), **Wanna Go** (tap the heart under any card; saved in your browser), Tonight, This Weekend, Just Announced (shows first seen in the last few days), **From Your Favourite Venues** (edit the `FAVOURITE_VENUES` list at the top of the `<script>` in `index.html` to change which venues get a row), then one row per category.

Each category tab has **genre chips** (Jazz & blues, Stand-up, Running, Marathi…) for the genres showing in that city. Genres are tagged by the collector from each show's title and description — the list and keywords are in `scrapers/genres.py`. Workshops and classes (pottery, painting dates…) are left out; see `NOT_SHOWS` in `scrapers/base.py`.

Shared links point to `/s/<id>`, a tiny page per show that the collector writes (`scrapers/sharepages.py`) so WhatsApp and other apps preview the link with the show's poster, title, date and venue; it forwards straight to the show on the dashboard. Pages are kept for 30 days after the show.

**Log in with a mobile number** (Firebase): optional. The account icon in the top bar texts a one-time code (Firebase Authentication, with an invisible reCAPTCHA); once logged in, the Wanna Go list, interests and For you history are kept in one Firestore document per person (`users/<uid>`) and merged with what the browser already had, so they follow the person to any device. Logging out keeps them in the account; **Delete my account** removes the number and the document. It stays switched off until `FIREBASE_CONFIG` at the top of the login section of `index.html`'s script is filled in. Firebase setup: create a project, add a Web app (its config goes into `FIREBASE_CONFIG`), enable **Authentication → Phone** (and **Anonymous**, for plans and lists), add `gigsnshows.com` under Authentication → Settings → Authorised domains, set the SMS region policy to allow India only, create a **Firestore** database (region `asia-south1`, Mumbai) and publish `firestore.rules` under its Rules tab. The web config is public by design: what protects the data is the rules.

`privacy.html` is the privacy policy the login and footer link to; people reach us through `contact.html`, a form that Web3Forms forwards to the inbox set up with its access key (`WEB3FORMS_KEY` in that file), so no address appears on the site. Analytics events: `login` / `sign_up` (method), `delete_account`.

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

**Reports, terms and abuse protection.** Every plan, night and shared list has a **Report** button (reason + optional note): it emails you through the same Web3Forms inbox as the Contact page, with the plan or list's link and id, no reporter details, and the person who made it isn't told. To take something down, delete its document in the Firebase console (Firestore → Data → `plans/<id>` or `lists/<id>`, plus its `replies` / `members` if you want them gone too); the page then says the plan was deleted. `terms.html` holds the plain-English terms (linked from the footer and the login sheet): not legal advice, worth a lawyer's read before money moves. Limits already in place: SMS only to India (Authentication → Settings → SMS region policy), Firestore rules that cap every field (`firestore.rules`), Firebase's default of 100 new anonymous accounts per hour per IP address, and the Google Cloud budget alert.

**App Check** (proves a request comes from the real site, so scripts can't create accounts, send paid login texts or fill the database): `APP_CHECK_SITE_KEY` in `index.html` (empty = off) takes the public site key of a reCAPTCHA Enterprise ("Fraud Defense") key for gigsnshows.com (Google Cloud project `gigsnshows`, label `gigsnshows`, made 8 Oct 2026), registered under Firebase console → App Check → Apps → the web app → Fraud Defense. It uses `ReCaptchaEnterpriseProvider`; there is no secret to keep. Roll-out order: register, put the key in `index.html`, let real use run, check App Check → APIs → Authentication shows requests as **verified**, and only then click **Enforce** for Authentication. Once enforced, scripts without a token (including REST tests that sign in anonymously) are refused; localhost doesn't load App Check. Not turned on: reCAPTCHA SMS defence (needs Firebase JS SDK 11+, the site uses 10.12).

**Search pages** (`scrapers/seo.py`, rebuilt by every collector run). The dashboard is one JavaScript page, which Google reads poorly, so the collector also writes plain HTML: `/shows/<name>-<id>/` (one page per show in a city, with every date and venue it runs and schema.org Event data), `/<city>/` and `/<city>/<category>/` (what's on, soonest first), `/cities/`, `sitemap.xml` and `robots.txt`. Pages for shows or cities that have gone are deleted (`seo-manifest.json` lists what's generated). The per-show share pages in `/s/` are for link previews only and are `noindex`. The home page carries a canonical tag and a link to `/cities/`. To look at them, open `/mumbai/` or any show page; the sitemap is at `/sitemap.xml`. Google Search Console (property `https://gigsnshows.com/`, verified with `googledb661ed3c526b2e1.html`: don't delete that file) is where to watch indexing; the sitemap was submitted there on 7 Oct 2026.

**Health check.** Every collector run records what each source returned in `data/health.json` (`health.py`). The scheduled **Health check** workflow (08:30 and 18:30 IST, after the collectors) reads that and the live site, and **fails the run when something is wrong, which makes GitHub email you**. Errors: a source that returned nothing or well under half its usual count, a collector that has stopped (a server-read source not refreshed for 20 hours, BookMyShow not for 4 days: the Mac must be awake sometimes), all listings together down by 30%, the home page or listings file unreachable or stale, the HTTPS certificate under a week from expiring, or the database refusing reads. Smaller things (a dip in a count, empty cities, BookMyShow quiet for 2 days, a certificate under 3 weeks) only appear in the run's summary. To see everything, open Actions → Health check → the latest run. To test that alerts reach you: Actions → Health check → Run workflow → tick "Fail on purpose". Run it by hand any time with `python health.py check`. Thresholds are the constants at the top of `health.py`.

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
