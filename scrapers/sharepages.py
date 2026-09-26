"""
One tiny page per show at /s/<id>, so a shared link previews with that show's poster,
title, date and venue in WhatsApp, iMessage, Instagram etc. — link previewers read these
tags and don't run the dashboard's JavaScript. People who open the link are sent straight
on to the show on the dashboard.

Pages stay up for a month after the show so old links still land somewhere sensible
(the dashboard then says the show has happened). s/index.json remembers each page's date.
"""

import json
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from urllib.parse import urlencode

KEEP_DAYS_AFTER = 30

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · gigsnshows</title>
<meta name="description" content="{desc}">
<meta property="og:site_name" content="gigsnshows">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
{image}<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{url}">
<meta http-equiv="refresh" content="0; url={target}">
<script>location.replace({target_js})</script>
</head>
<body style="background:#000;color:#fff;font-family:-apple-system,Helvetica,Arial,sans-serif;padding:2rem">
<a href="{target}" style="color:#0a84ff">{title} — see it on gigsnshows</a>
</body>
</html>
"""


def _when(e):
    d = datetime.strptime(e["date"], "%Y-%m-%d")
    out = f"{d:%a} {d.day} {d:%b}"
    if e.get("time"):
        h, m = map(int, e["time"].split(":"))
        out += f", {h % 12 or 12}{f':{m:02d}' if m else ''} {'pm' if h >= 12 else 'am'}"
    return out


def _description(e):
    place = ", ".join(p for p in (e.get("venue"), e.get("city")) if p)
    price = f" · from ₹{int(e['price_from']):,}" if e.get("price_from") else ""
    return f"{_when(e)} · {place}{price}"


def write(events, root, site_url):
    """Write s/<id>.html for every show; remove pages whose show ended over a month ago."""
    folder = Path(root) / "s"
    folder.mkdir(exist_ok=True)
    manifest_path = folder / "index.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    for e in events:
        target = "/?" + urlencode({"city": e["city"].lower(), "event": e["id"]})
        image = f'<meta property="og:image" content="{escape(e["image"])}">\n' if e.get("image") else ""
        html = PAGE.format(title=escape(e["title"]), desc=escape(_description(e)), image=image,
                           url=f"{site_url}/s/{e['id']}", target=escape(target), target_js=json.dumps(target))
        page = folder / f"{e['id']}.html"
        if not page.exists() or page.read_text() != html:
            page.write_text(html)
        manifest[e["id"]] = e["date"]

    cutoff = (date.today() - timedelta(days=KEEP_DAYS_AFTER)).isoformat()
    for sid, day in list(manifest.items()):
        if day < cutoff:
            (folder / f"{sid}.html").unlink(missing_ok=True)
            del manifest[sid]
    manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), indent=0))
