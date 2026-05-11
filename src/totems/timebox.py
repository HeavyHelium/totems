from __future__ import annotations

import time
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .duty_sources.google_calendar import CalendarEvent, GoogleCalendarDutySource
from .scheduler import BlockResult


_TIMED_DUTY_RE = re.compile(
    r"^\s*(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?\b\s+(?P<title>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TimeboxDuty:
    title: str
    description: str
    starts_at: datetime

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.starts_at.isoformat(), self.title, self.description)


class TimeboxScheduler:
    def __init__(
        self,
        *,
        work_seconds: float,
        on_block: Callable[[], BlockResult],
        calendar_sources: list[GoogleCalendarDutySource],
        on_timebox: Callable[[TimeboxDuty, int], BlockResult],
        static_duty_items: list[str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        on_tick: Callable[[float], None] | None = None,
        tick_seconds: float = 1.0,
        is_paused: Callable[[], bool] | None = None,
        lead_seconds: int = 60,
        refresh_seconds: int = 60,
    ) -> None:
        self._work_seconds = work_seconds
        self._on_block = on_block
        self._calendar_sources = calendar_sources
        self._on_timebox = on_timebox
        self._static_duty_items = static_duty_items or []
        self._sleep = sleep
        self._now = now or (lambda: datetime.now().astimezone())
        self._monotonic = monotonic
        self._on_tick = on_tick
        self._tick_seconds = tick_seconds
        self._is_paused = is_paused
        self._lead_seconds = lead_seconds
        self._refresh_seconds = refresh_seconds
        self._stopped = False
        self._events: list[TimeboxDuty] = []
        self._fired: set[tuple[str, str, str]] = set()
        self._last_refresh = float("-inf")
        self._next_block_at = self._monotonic() + self._work_seconds

    def stop(self) -> None:
        self._stopped = True

    def run(self) -> None:
        self._refresh_events(force=True)
        while not self._stopped:
            if self._is_paused is not None and self._is_paused():
                self._tick()
                continue

            self._refresh_events()
            duty = self._next_due_duty()
            if duty is not None:
                remaining = max(1, min(self._lead_seconds, int((duty.starts_at - self._now()).total_seconds())))
                self._fired.add(duty.identity)
                self._on_timebox(duty, remaining)
                continue

            remaining_to_block = max(0.0, self._next_block_at - self._monotonic())
            if remaining_to_block <= 0:
                self._on_block()
                self._next_block_at = self._monotonic() + self._work_seconds
                continue

            self._tick(remaining_to_block)

    def _tick(self, remaining_to_block: float | None = None) -> None:
        if remaining_to_block is None:
            remaining_to_block = max(0.0, self._next_block_at - self._monotonic())
        if self._on_tick is not None:
            self._on_tick(remaining_to_block)
        sleep_for = self._tick_seconds if remaining_to_block <= 0 else min(self._tick_seconds, remaining_to_block)
        self._sleep(sleep_for)

    def _refresh_events(self, *, force: bool = False) -> None:
        now_mono = self._monotonic()
        if not force and now_mono - self._last_refresh < self._refresh_seconds:
            return
        self._last_refresh = now_mono

        events: list[TimeboxDuty] = []
        seen: set[tuple[str, str, str]] = set()
        for duty in parse_timeboxed_duties(self._static_duty_items, now=self._now()):
            if duty.identity in seen:
                continue
            seen.add(duty.identity)
            events.append(duty)
        for source in self._calendar_sources:
            for event in source.today_events():
                duty = _timebox_duty_from_event(event)
                if duty is None or duty.identity in seen:
                    continue
                seen.add(duty.identity)
                events.append(duty)
        events.sort(key=lambda duty: duty.starts_at)
        self._events = events

    def _next_due_duty(self) -> TimeboxDuty | None:
        now = self._now()
        lead = timedelta(seconds=self._lead_seconds)
        for duty in self._events:
            if duty.identity in self._fired:
                continue
            if now >= duty.starts_at:
                self._fired.add(duty.identity)
                continue
            if now >= duty.starts_at - lead:
                return duty
        return None


def _timebox_duty_from_event(event: CalendarEvent) -> TimeboxDuty | None:
    if event.all_day:
        return None
    return TimeboxDuty(
        title=event.title,
        description=event.description,
        starts_at=event.starts_at,
    )


def parse_timeboxed_duties(items: list[str], *, now: datetime) -> list[TimeboxDuty]:
    out: list[TimeboxDuty] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        duty = parse_timeboxed_duty(item, now=now)
        if duty is None or duty.identity in seen:
            continue
        seen.add(duty.identity)
        out.append(duty)
    out.sort(key=lambda duty: duty.starts_at)
    return out


def parse_timeboxed_duty(item: str, *, now: datetime) -> TimeboxDuty | None:
    lines = [line.strip() for line in item.strip().splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None

    match = _TIMED_DUTY_RE.match(lines[0])
    if match is None:
        return None
    if ":" not in lines[0] and match.group("ampm") is None:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or "0")
    ampm = match.group("ampm")
    if ampm is None:
        if hour > 23:
            return None
    else:
        if hour < 1 or hour > 12:
            return None
        if ampm.lower() == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    if minute > 59:
        return None

    title = match.group("title").strip()
    if not title:
        return None
    description = "\n".join(lines[1:]).strip()
    starts_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return TimeboxDuty(title=title, description=description, starts_at=starts_at)
