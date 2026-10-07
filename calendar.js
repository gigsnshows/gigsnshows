/*
 * "Add to calendar" for gigsnshows: a Google Calendar link, or a .ics file that Apple Calendar,
 * Outlook and everything else understands. The .ics carries reminders (3 hours before a timed
 * show, plus a day before; 9 am the day before an all-day one), so the phone's own calendar does the reminding.
 *
 * Used by index.html (the /shows/ pages get a plain Google Calendar link from scrapers/seo.py). An event is:
 *   { id, title, date: "YYYY-MM-DD", time: "HH:MM" | "", venue, city, link: ticket url, page: gigsnshows url, hours: optional length }
 */
(function () {
  "use strict";
  var TZ = "Asia/Kolkata", DEFAULT_HOURS = 2;
  var pad = function (n) { return String(n).padStart(2, "0"); };

  function compact(date) { return date.replace(/-/g, ""); }
  function addDays(date, n) {
    var d = new Date(date + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate());
  }

  // When it starts and ends, in local (India) time. A show without a time becomes an all-day entry.
  function times(e) {
    if (!e.time) return { allDay: true, start: compact(e.date), end: compact(addDays(e.date, 1)) };
    var h = Number(e.time.slice(0, 2)), m = e.time.slice(3, 5), endH = h + (e.hours || DEFAULT_HOURS), endDate = e.date;
    if (endH >= 24) { endH -= 24; endDate = addDays(e.date, 1); }
    return { allDay: false, start: compact(e.date) + "T" + pad(h) + m + "00", end: compact(endDate) + "T" + pad(endH) + m + "00" };
  }

  function where(e) { return [e.venue, e.city].filter(Boolean).join(", "); }
  function details(e) {
    var lines = [];
    if (e.link) lines.push("Tickets: " + e.link);
    if (e.page) lines.push("On gigsnshows: " + e.page);
    return lines.join("\n");
  }

  function gcalUrl(e) {
    var t = times(e), p = new URLSearchParams({ action: "TEMPLATE", text: e.title, dates: t.start + "/" + t.end, details: details(e), location: where(e) });
    if (!t.allDay) p.set("ctz", TZ);
    return "https://calendar.google.com/calendar/render?" + p.toString();
  }

  // RFC 5545 text: escape \ ; , and newlines, and fold lines at 75 bytes (never inside a character).
  function esc(s) { return String(s || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n"); }
  function fold(line) {
    var enc = new TextEncoder(), out = [], cur = "", bytes = 0;
    Array.from(line).forEach(function (ch) {
      var n = enc.encode(ch).length;
      if (bytes + n > 75) { out.push(cur); cur = " "; bytes = 1; }
      cur += ch;
      bytes += n;
    });
    out.push(cur);
    return out.join("\r\n");
  }

  function icsText(events) {
    var now = new Date(), stamp = now.getUTCFullYear() + pad(now.getUTCMonth() + 1) + pad(now.getUTCDate()) + "T" + pad(now.getUTCHours()) + pad(now.getUTCMinutes()) + pad(now.getUTCSeconds()) + "Z";
    var L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//gigsnshows//Calendar//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:gigsnshows",
      "BEGIN:VTIMEZONE", "TZID:" + TZ, "BEGIN:STANDARD", "DTSTART:19700101T000000", "TZOFFSETFROM:+0530", "TZOFFSETTO:+0530", "TZNAME:IST", "END:STANDARD", "END:VTIMEZONE"];
    events.forEach(function (e) {
      var t = times(e);
      L.push("BEGIN:VEVENT", "UID:" + e.id + "@gigsnshows.com", "DTSTAMP:" + stamp);
      if (t.allDay) L.push("DTSTART;VALUE=DATE:" + t.start, "DTEND;VALUE=DATE:" + t.end);
      else L.push("DTSTART;TZID=" + TZ + ":" + t.start, "DTEND;TZID=" + TZ + ":" + t.end);
      L.push("SUMMARY:" + esc(e.title));
      if (where(e)) L.push("LOCATION:" + esc(where(e)));
      if (details(e)) L.push("DESCRIPTION:" + esc(details(e)));
      if (e.page) L.push("URL:" + e.page);
      if (t.allDay) {
        L.push("BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("Tomorrow: " + e.title), "TRIGGER:-PT15H", "END:VALARM");
      } else {
        L.push("BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("Today: " + e.title), "TRIGGER:-PT3H", "END:VALARM",
          "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("Tomorrow: " + e.title), "TRIGGER:-P1D", "END:VALARM");
      }
      L.push("END:VEVENT");
    });
    L.push("END:VCALENDAR");
    return L.map(fold).join("\r\n") + "\r\n";
  }

  function download(events, name) {
    var blob = new Blob([icsText(events)], { type: "text/calendar;charset=utf-8" });
    var url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url;
    a.download = (name || "gigsnshows") + ".ics";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  window.gigsCal = { gcalUrl: gcalUrl, icsText: icsText, download: download, times: times };
})();
