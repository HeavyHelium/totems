from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import icalendar
import recurring_ical_events


_log = logging.getLogger("totems.duty_sources.google_calendar")


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    description: str
    starts_at: datetime
    all_day: bool
    ends_at: datetime | None = None

    @property
    def formatted(self) -> str:
        if self.all_day:
            return f"all day: {self.title}"
        return f"{self.starts_at.strftime('%H:%M')} {self.title}"

    @property
    def identity(self) -> tuple[str, str, str, bool, str]:
        ends_at = "" if self.ends_at is None else self.ends_at.isoformat()
        return (self.starts_at.isoformat(), self.title, self.description, self.all_day, ends_at)


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
        events: list[CalendarEvent] = []

        for url in self._urls:
            try:
                items = extract_today_events(self._fetcher(url), now=now)
            except Exception as e:
                _log.warning("google_calendar fetch/parse failed for %s: %s", url, e)
                continue
            any_success = True
            for item in items:
                if item.formatted not in seen:
                    seen.add(item.formatted)
                    events.append(item)

        if any_success:
            formatted = [event.formatted for event in events]
            self._write_cache(formatted, events, now=now)
            return formatted

        return self._read_cache(now=now)

    def today_events(self) -> list[CalendarEvent]:
        if not self._urls:
            return []

        now = self._now()
        any_success = False
        seen: set[tuple[str, str, str, bool]] = set()
        merged: list[CalendarEvent] = []

        for url in self._urls:
            try:
                events = extract_today_events(self._fetcher(url), now=now)
            except Exception as e:
                _log.warning("google_calendar fetch/parse failed for %s: %s", url, e)
                continue
            any_success = True
            for event in events:
                if event.identity not in seen:
                    seen.add(event.identity)
                    merged.append(event)

        if any_success:
            self._write_cache([event.formatted for event in merged], merged, now=now)
            return merged

        return self._read_event_cache(now=now)

    def _write_cache(self, items: list[str], events: list[CalendarEvent], *, now: datetime) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
                "local_date": now.date().isoformat(),
                "items": items,
                "events": [
                    {
                        "title": event.title,
                        "description": event.description,
                        "starts_at": event.starts_at.isoformat(),
                        "ends_at": None if event.ends_at is None else event.ends_at.isoformat(),
                        "all_day": event.all_day,
                    }
                    for event in events
                ],
            }
            self.cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as e:
            _log.warning("google_calendar cache write failed: %s", e)

    def _read_cache(self, *, now: datetime) -> list[str]:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if payload.get("local_date") != now.date().isoformat():
            return []
        items = payload.get("items")
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            return []
        return list(items)

    def _read_event_cache(self, *, now: datetime) -> list[CalendarEvent]:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if payload.get("local_date") != now.date().isoformat():
            return []
        events = payload.get("events")
        if not isinstance(events, list):
            return []

        out: list[CalendarEvent] = []
        for event in events:
            if not isinstance(event, dict):
                return []
            title = event.get("title")
            description = event.get("description", "")
            starts_at = event.get("starts_at")
            ends_at = event.get("ends_at")
            all_day = event.get("all_day")
            if (
                not isinstance(title, str)
                or not isinstance(description, str)
                or not isinstance(starts_at, str)
                or not (ends_at is None or isinstance(ends_at, str))
                or not isinstance(all_day, bool)
            ):
                return []
            try:
                parsed_start = datetime.fromisoformat(starts_at)
                parsed_end = None if ends_at is None else datetime.fromisoformat(ends_at)
            except ValueError:
                return []
            if parsed_start.tzinfo is None or (parsed_end is not None and parsed_end.tzinfo is None):
                return []
            out.append(
                CalendarEvent(
                    title=title,
                    description=description,
                    starts_at=parsed_start,
                    ends_at=parsed_end,
                    all_day=all_day,
                )
            )
        return out


def extract_today_items(ical_bytes: bytes, *, now: datetime) -> list[str]:
    return [event.formatted for event in extract_today_events(ical_bytes, now=now)]


def extract_today_events(ical_bytes: bytes, *, now: datetime) -> list[CalendarEvent]:
    """Parse iCal bytes and return today's event metadata.

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

    all_day: list[CalendarEvent] = []
    timed: list[CalendarEvent] = []

    for event in events:
        parsed = _parse_event(event, tz)
        if parsed is None:
            continue
        if not parsed.all_day and parsed.starts_at.date() != now.date():
            continue
        if parsed.all_day:
            all_day.append(parsed)
        else:
            timed.append(parsed)

    all_day.sort(key=lambda event: event.title)
    timed.sort(key=lambda event: event.starts_at)
    return all_day + timed


def _drop_events_without_dtstart(cal: icalendar.Calendar) -> icalendar.Calendar:
    cal.subcomponents = [
        component
        for component in cal.subcomponents
        if component.name != "VEVENT" or component.get("DTSTART") is not None
    ]
    return cal


def _parse_event(event: Any, tz: Any) -> CalendarEvent | None:
    summary = event.get("SUMMARY")
    if summary is None:
        return None
    summary_str = str(summary).strip()
    if not summary_str:
        return None
    description = event.get("DESCRIPTION")
    description_str = "" if description is None else str(description).strip()

    dtstart = event.get("DTSTART")
    if dtstart is None:
        return None
    raw = dtstart.dt

    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            local_start = raw.replace(tzinfo=tz)
        else:
            local_start = raw.astimezone(tz)
        return CalendarEvent(
            title=summary_str,
            description=description_str,
            starts_at=local_start,
            ends_at=_event_end(event, tz),
            all_day=False,
        )

    if isinstance(raw, date):
        local_start = datetime.combine(raw, time.min, tzinfo=tz)
        return CalendarEvent(
            title=summary_str,
            description=description_str,
            starts_at=local_start,
            ends_at=_event_end(event, tz),
            all_day=True,
        )

    return None


def _event_end(event: Any, tz: Any) -> datetime | None:
    dtend = event.get("DTEND")
    if dtend is None:
        return None
    raw = dtend.dt
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=tz)
        return raw.astimezone(tz)
    if isinstance(raw, date):
        return datetime.combine(raw, time.min, tzinfo=tz)
    return None
