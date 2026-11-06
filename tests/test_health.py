import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import health  # noqa: E402


def check(count, failed):
    stamp = health.stamp()
    h = {"sources": {"X": {"count": count, "last_ok": stamp, "failed_cities": failed, "recent": [74, 76, 71, count]}}}
    return health.check_sources(h, [{"name": "X", "runs_on": ["mac"]}])


def test_a_big_drop_with_empty_cities_only_warns():
    errors, warnings, _ = check(24, ["Goa", "Pune"])
    assert not errors and any("earlier shows kept" in w for w in warnings)


def test_a_big_drop_with_no_empty_cities_is_an_error():
    errors, _, _ = check(24, [])
    assert errors


class FakeResp:
    def __init__(self, code, text="gigsnshows"):
        self.status_code, self.text, self.content = code, text, text.encode()

    def json(self):
        return {"count": 1, "updated_at": health.stamp(), "events": [{}]}


def run_site(monkeypatch, codes):
    import requests
    seq = iter(codes)
    monkeypatch.setattr(health, "RETRY_WAIT", 0)
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(next(seq, 200)))
    return health.site_checks()[0]


def test_one_server_error_on_the_home_page_is_retried(monkeypatch):
    errors = run_site(monkeypatch, [503, 200])
    assert not any("Home page" in e for e in errors)


def test_a_site_that_stays_down_still_fails(monkeypatch):
    errors = run_site(monkeypatch, [503, 503, 503])
    assert any("Home page: HTTP 503" in e for e in errors)
