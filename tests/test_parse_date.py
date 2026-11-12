"""Dates written year-month-day must be read that way. Run: python -m pytest tests (from the repo root)."""
import os
import sys

import pytest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scrapers.base import parse_date  # noqa: E402


@pytest.mark.parametrize("text, expected", [
    ("2026-11-01T13:30:00.000Z", ("2026-11-01", "19:00")),   # District's A. R. Rahman, Mumbai: was read as 11 January
    ("2026-11-05T13:30:00.000Z", ("2026-11-05", "19:00")),
    ("2026-11-12T13:30:00Z", ("2026-11-12", "19:00")),
    ("2026-11-13T13:30:00Z", ("2026-11-13", "19:00")),
    ("2026-12-04", ("2026-12-04", "")),
    ("2026-12-04T19:30:00+05:30", ("2026-12-04", "19:30")),
    ("2026-10-14T20:00:00", ("2026-10-14", "20:00")),
    ("2026-10-14T20:30:00Z", ("2026-10-15", "02:00")),        # evening in UTC is after midnight in India
    ("4 Nov 2026", ("2026-11-04", "")),
])
def test_dates(text, expected):
    assert parse_date(text) == expected


def test_a_date_with_no_year_is_its_next_occurrence():
    day, time = parse_date("4 Nov, 7:00 PM")   # no year: this year until 4 November has passed, then next year
    assert day[5:] == "11-04" and time == "19:00" and day[:4] in (str(date.today().year), str(date.today().year + 1))
    assert day >= (date.today() - timedelta(days=31)).isoformat()
