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
