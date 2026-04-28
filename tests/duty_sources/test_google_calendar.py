import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from totems.duty_sources.google_calendar import GoogleCalendarDutySource, extract_today_items

from ._fixtures import (
    malformed_event,
    merge,
    single_all_day_event,
    single_timed_event,
    weekly_recurring_event,
)


LA = ZoneInfo("America/Los_Angeles")
NOW_LA = datetime(2026, 4, 28, 12, 30, tzinfo=LA)


def test_extracts_timed_event_today():
    cal = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
    )
    assert extract_today_items(cal, now=NOW_LA) == ["09:00 standup"]


def test_extracts_all_day_event_today():
    cal = single_all_day_event(title="vacation", day=date(2026, 4, 28))
    assert extract_today_items(cal, now=NOW_LA) == ["all day: vacation"]


def test_excludes_yesterday_and_tomorrow():
    cal = merge(
        single_timed_event(
            title="yesterday",
            start=datetime(2026, 4, 27, 9, 0, tzinfo=LA),
            end=datetime(2026, 4, 27, 9, 30, tzinfo=LA),
            uid="y",
        ),
        single_timed_event(
            title="tomorrow",
            start=datetime(2026, 4, 29, 9, 0, tzinfo=LA),
            end=datetime(2026, 4, 29, 9, 30, tzinfo=LA),
            uid="t",
        ),
    )
    assert extract_today_items(cal, now=NOW_LA) == []


def test_recurring_weekly_event_lands_on_today():
    cal = weekly_recurring_event(
        title="weekly review",
        first_start=datetime(2026, 4, 21, 14, 0, tzinfo=LA),
        first_end=datetime(2026, 4, 21, 15, 0, tzinfo=LA),
    )
    assert extract_today_items(cal, now=NOW_LA) == ["14:00 weekly review"]


def test_recurring_weekly_event_does_not_match_other_weekday():
    cal = weekly_recurring_event(
        title="monday meeting",
        first_start=datetime(2026, 4, 20, 14, 0, tzinfo=LA),
        first_end=datetime(2026, 4, 20, 15, 0, tzinfo=LA),
    )
    assert extract_today_items(cal, now=NOW_LA) == []


def test_utc_dtstart_converted_to_local():
    utc_start = datetime(2026, 4, 28, 16, 0, tzinfo=timezone.utc)
    utc_end = datetime(2026, 4, 28, 16, 30, tzinfo=timezone.utc)
    cal = single_timed_event(title="utc-event", start=utc_start, end=utc_end)
    assert extract_today_items(cal, now=NOW_LA) == ["09:00 utc-event"]


def test_sort_all_day_first_then_timed_ascending():
    cal = merge(
        single_timed_event(
            title="b-late",
            start=datetime(2026, 4, 28, 15, 0, tzinfo=LA),
            end=datetime(2026, 4, 28, 16, 0, tzinfo=LA),
            uid="late",
        ),
        single_timed_event(
            title="a-early",
            start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
            end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
            uid="early",
        ),
        single_all_day_event(title="vacation", day=date(2026, 4, 28), uid="vac"),
    )
    assert extract_today_items(cal, now=NOW_LA) == [
        "all day: vacation",
        "09:00 a-early",
        "15:00 b-late",
    ]


def test_skip_event_without_summary():
    cal = malformed_event()
    assert extract_today_items(cal, now=NOW_LA) == []


def test_skip_event_without_dtstart_keeps_others():
    bad = malformed_event(uid="bad")
    good = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
        uid="good",
    )
    cal = merge(bad, good)
    assert extract_today_items(cal, now=NOW_LA) == ["09:00 standup"]


def test_requires_timezone_aware_now():
    cal = single_all_day_event(title="vacation", day=date(2026, 4, 28))
    with pytest.raises(ValueError, match="timezone-aware"):
        extract_today_items(cal, now=datetime(2026, 4, 28, 12, 30))


def _src(urls, cache_path, fetcher):
    return GoogleCalendarDutySource(
        urls=urls,
        cache_path=cache_path,
        fetcher=fetcher,
        now=lambda: NOW_LA,
    )


def test_today_returns_concatenated_results(tmp_path):
    cal_a = single_all_day_event(title="vacation", day=date(2026, 4, 28))
    cal_b = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
    )

    def fetcher(url):
        return cal_a if "a" in url else cal_b

    src = _src(["a.ics", "b.ics"], tmp_path / "cache.json", fetcher)
    assert src.today() == ["all day: vacation", "09:00 standup"]


def test_today_dedupes_across_urls(tmp_path):
    cal = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
    )

    src = _src(["a.ics", "b.ics"], tmp_path / "cache.json", lambda url: cal)
    assert src.today() == ["09:00 standup"]


def test_today_writes_cache_on_success(tmp_path):
    cal = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
    )
    cache = tmp_path / "cache.json"
    src = _src(["a.ics"], cache, fetcher=lambda url: cal)
    src.today()

    payload = json.loads(cache.read_text(encoding="utf-8"))
    assert payload["items"] == ["09:00 standup"]
    assert payload["fetched_at"].endswith("+00:00")


def test_today_reads_cache_on_full_failure(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            {
                "fetched_at": "2026-04-27T00:00:00+00:00",
                "items": ["09:00 stale-standup"],
            }
        ),
        encoding="utf-8",
    )

    def fetcher(url):
        raise OSError("network down")

    src = _src(["a.ics"], cache, fetcher)
    assert src.today() == ["09:00 stale-standup"]


def test_today_returns_empty_when_no_cache_and_full_failure(tmp_path):
    def fetcher(url):
        raise OSError("network down")

    src = _src(["a.ics"], tmp_path / "missing.json", fetcher)
    assert src.today() == []


def test_today_corrupt_cache_treated_as_no_cache(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text("{not valid json", encoding="utf-8")

    def fetcher(url):
        raise OSError("network down")

    src = _src(["a.ics"], cache, fetcher)
    assert src.today() == []


def test_today_partial_failure_caches_and_returns_successes(tmp_path):
    cal = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
    )
    cache = tmp_path / "cache.json"

    def fetcher(url):
        if "broken" in url:
            raise OSError("403")
        return cal

    src = _src(["broken.ics", "ok.ics"], cache, fetcher)
    assert src.today() == ["09:00 standup"]
    payload = json.loads(cache.read_text(encoding="utf-8"))
    assert payload["items"] == ["09:00 standup"]


def test_today_empty_urls_skips_network(tmp_path):
    calls: list[str] = []

    def fetcher(url):
        calls.append(url)
        return b""

    src = _src([], tmp_path / "cache.json", fetcher)
    assert src.today() == []
    assert calls == []


def test_today_malformed_ical_in_one_url_kept_in_others(tmp_path):
    cal = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
    )

    def fetcher(url):
        if "broken" in url:
            return b"NOT AN ICS FILE"
        return cal

    src = _src(["broken.ics", "ok.ics"], tmp_path / "cache.json", fetcher)
    assert src.today() == ["09:00 standup"]
