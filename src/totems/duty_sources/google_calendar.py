from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import icalendar
import recurring_ical_events


_log = logging.getLogger("totems.duty_sources.google_calendar")


def _http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.read()


def _now_local() -> datetime:
    return datetime.now().astimezone()


class GoogleCalendarDutySource:
    def __init__(
        self,
        urls: list[str],
        cache_path: Path,
        *,
        fetcher: Callable[[str], bytes] = _http_get,
        now: Callable[[], datetime] = _now_local,
    ) -> None:
        self._urls = list(urls)
        self.cache_path = cache_path
        self._fetcher = fetcher
        self._now = now

    def today(self) -> list[str]:
        if not self._urls:
            return []

        now = self._now()
        any_success = False
        seen: set[str] = set()
        merged: list[str] = []

        for url in self._urls:
            try:
                items = extract_today_items(self._fetcher(url), now=now)
            except Exception as e:
                _log.warning("google_calendar fetch/parse failed for %s: %s", url, e)
                continue
            any_success = True
            for item in items:
                if item not in seen:
                    seen.add(item)
                    merged.append(item)

        if any_success:
            self._write_cache(merged)
            return merged

        return self._read_cache()

    def _write_cache(self, items: list[str]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
                "items": items,
            }
            self.cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as e:
            _log.warning("google_calendar cache write failed: %s", e)

    def _read_cache(self) -> list[str]:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = payload.get("items")
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            return []
        return list(items)


def extract_today_items(ical_bytes: bytes, *, now: datetime) -> list[str]:
    """Parse iCal bytes and return today's events as formatted strings.

    "Today" is the calendar day containing the timezone-aware `now`.
    Output is sorted with all-day events first, then timed events by start.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    tz = now.tzinfo
    start_of_day = datetime.combine(now.date(), time.min, tzinfo=tz)
    end_of_day = start_of_day + timedelta(days=1)

    cal = _drop_events_without_dtstart(icalendar.Calendar.from_ical(ical_bytes))
    events = recurring_ical_events.of(cal, skip_bad_series=True).between(start_of_day, end_of_day)

    all_day: list[str] = []
    timed: list[tuple[datetime, str]] = []

    for event in events:
        formatted = _format_event(event, tz)
        if formatted is None:
            continue
        kind, sort_key, text = formatted
        if kind == "all_day":
            all_day.append(text)
        else:
            timed.append((sort_key, text))

    all_day.sort()
    timed.sort(key=lambda pair: pair[0])
    return all_day + [text for _, text in timed]


def _drop_events_without_dtstart(cal: icalendar.Calendar) -> icalendar.Calendar:
    cal.subcomponents = [
        component
        for component in cal.subcomponents
        if component.name != "VEVENT" or component.get("DTSTART") is not None
    ]
    return cal


def _format_event(event: Any, tz: Any) -> tuple[str, datetime, str] | None:
    summary = event.get("SUMMARY")
    if summary is None:
        return None
    summary_str = str(summary).strip()
    if not summary_str:
        return None

    dtstart = event.get("DTSTART")
    if dtstart is None:
        return None
    raw = dtstart.dt

    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            local_start = raw.replace(tzinfo=tz)
        else:
            local_start = raw.astimezone(tz)
        return ("timed", local_start, f"{local_start.strftime('%H:%M')} {summary_str}")

    if isinstance(raw, date):
        return ("all_day", datetime.min, f"all day: {summary_str}")

    return None
