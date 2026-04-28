"""Tiny iCal builders for tests. No real network or files."""

from __future__ import annotations

from datetime import date, datetime, timezone


_HEADER = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//totems-tests//EN\r\n"
    "CALSCALE:GREGORIAN\r\n"
)
_FOOTER = "END:VCALENDAR\r\n"


def _wrap(events: str) -> bytes:
    return (_HEADER + events + _FOOTER).encode("utf-8")


def _fmt_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("fixture datetime must be tz-aware")
    return dt.strftime("%Y%m%dT%H%M%S")


def _dtstart_dtend(start: datetime, end: datetime) -> str:
    if start.tzinfo is timezone.utc:
        return f"DTSTART:{_fmt_dt(start)}Z\r\n" f"DTEND:{_fmt_dt(end)}Z\r\n"

    tzid = str(start.tzinfo)
    return f"DTSTART;TZID={tzid}:{_fmt_dt(start)}\r\n" f"DTEND;TZID={tzid}:{_fmt_dt(end)}\r\n"


def single_timed_event(
    *,
    title: str,
    start: datetime,
    end: datetime,
    uid: str = "evt-1",
) -> bytes:
    body = (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"SUMMARY:{title}\r\n"
        f"{_dtstart_dtend(start, end)}"
        "END:VEVENT\r\n"
    )
    return _wrap(body)


def single_all_day_event(*, title: str, day: date, uid: str = "evt-1") -> bytes:
    next_day = date.fromordinal(day.toordinal() + 1)
    body = (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"SUMMARY:{title}\r\n"
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}\r\n"
        f"DTEND;VALUE=DATE:{next_day.strftime('%Y%m%d')}\r\n"
        "END:VEVENT\r\n"
    )
    return _wrap(body)


def weekly_recurring_event(
    *,
    title: str,
    first_start: datetime,
    first_end: datetime,
    uid: str = "evt-1",
) -> bytes:
    weekday_code = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][first_start.weekday()]
    body = (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"SUMMARY:{title}\r\n"
        f"{_dtstart_dtend(first_start, first_end)}"
        f"RRULE:FREQ=WEEKLY;BYDAY={weekday_code}\r\n"
        "END:VEVENT\r\n"
    )
    return _wrap(body)


def merge(*calendars: bytes) -> bytes:
    inner_parts: list[str] = []
    for cal in calendars:
        text = cal.decode("utf-8")
        body = text.split("BEGIN:VCALENDAR\r\n", 1)[1]
        body = body.rsplit("END:VCALENDAR\r\n", 1)[0]
        events: list[str] = []
        in_event = False
        for line in body.splitlines(keepends=True):
            if line.startswith("BEGIN:VEVENT"):
                in_event = True
            if in_event:
                events.append(line)
            if line.startswith("END:VEVENT"):
                in_event = False
        inner_parts.append("".join(events))
    return _wrap("".join(inner_parts))


def malformed_event(uid: str = "bad") -> bytes:
    body = (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        "END:VEVENT\r\n"
    )
    return _wrap(body)
