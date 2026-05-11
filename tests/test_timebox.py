from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from totems.duty_sources.google_calendar import CalendarEvent
from totems.timebox import TimeboxDuty, TimeboxScheduler, parse_timeboxed_duty


TZ = ZoneInfo("America/Los_Angeles")


class _Clock:
    def __init__(self, wall: datetime) -> None:
        self.wall = wall
        self.mono = 0.0

    def sleep(self, seconds: float) -> None:
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds


class _Source:
    def __init__(self, events: list[CalendarEvent]) -> None:
        self.events = events
        self.calls = 0

    def today_events(self) -> list[CalendarEvent]:
        self.calls += 1
        return self.events


def test_timebox_scheduler_triggers_one_minute_before_timed_calendar_duty():
    start = datetime(2026, 4, 28, 9, 0, tzinfo=TZ)
    clock = _Clock(start - timedelta(seconds=65))
    source = _Source(
        [
            CalendarEvent(
                title="standup",
                description="Daily sync",
                starts_at=start,
                all_day=False,
            )
        ]
    )
    reminders: list[tuple[TimeboxDuty, int]] = []

    def on_timebox(duty: TimeboxDuty, seconds: int) -> str:
        reminders.append((duty, seconds))
        sched.stop()
        return "timeout"

    sched = TimeboxScheduler(
        work_seconds=3600,
        on_block=lambda: "timeout",
        calendar_sources=[source],  # type: ignore[list-item]
        on_timebox=on_timebox,
        sleep=clock.sleep,
        now=lambda: clock.wall,
        monotonic=lambda: clock.mono,
        tick_seconds=1,
        lead_seconds=60,
    )
    sched.run()

    assert len(reminders) == 1
    duty, seconds = reminders[0]
    assert duty.title == "standup"
    assert duty.description == "Daily sync"
    assert duty.starts_at == start
    assert seconds == 60


def test_timebox_scheduler_skips_all_day_events():
    start = datetime(2026, 4, 28, 9, 0, tzinfo=TZ)
    clock = _Clock(start - timedelta(seconds=65))
    source = _Source(
        [
            CalendarEvent(
                title="vacation",
                description="",
                starts_at=start,
                all_day=True,
            )
        ]
    )
    reminders: list[TimeboxDuty] = []
    sleeps = 0

    def sleep(seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        clock.sleep(seconds)
        if sleeps >= 3:
            sched.stop()

    sched = TimeboxScheduler(
        work_seconds=3600,
        on_block=lambda: "timeout",
        calendar_sources=[source],  # type: ignore[list-item]
        on_timebox=lambda duty, seconds: reminders.append(duty) or "timeout",
        sleep=sleep,
        now=lambda: clock.wall,
        monotonic=lambda: clock.mono,
        tick_seconds=1,
        lead_seconds=60,
    )
    sched.run()

    assert reminders == []


def test_parse_timeboxed_duty_accepts_24_hour_time():
    duty = parse_timeboxed_duty(
        "09:30 standup\nBring notebook",
        now=datetime(2026, 4, 28, 8, 0, tzinfo=TZ),
    )

    assert duty is not None
    assert duty.title == "standup"
    assert duty.description == "Bring notebook"
    assert duty.starts_at == datetime(2026, 4, 28, 9, 30, tzinfo=TZ)


def test_parse_timeboxed_duty_accepts_ampm_time():
    duty = parse_timeboxed_duty(
        "3pm dentist",
        now=datetime(2026, 4, 28, 8, 0, tzinfo=TZ),
    )

    assert duty is not None
    assert duty.title == "dentist"
    assert duty.starts_at == datetime(2026, 4, 28, 15, 0, tzinfo=TZ)


def test_parse_timeboxed_duty_ignores_untimed_text():
    assert parse_timeboxed_duty("review notes", now=datetime(2026, 4, 28, 8, 0, tzinfo=TZ)) is None


def test_timebox_scheduler_triggers_static_duty_items_without_calendar_sources():
    start = datetime(2026, 4, 28, 9, 0, tzinfo=TZ)
    clock = _Clock(start - timedelta(seconds=65))
    reminders: list[TimeboxDuty] = []

    def on_timebox(duty: TimeboxDuty, seconds: int) -> str:
        reminders.append(duty)
        sched.stop()
        return "timeout"

    sched = TimeboxScheduler(
        work_seconds=3600,
        on_block=lambda: "timeout",
        calendar_sources=[],
        static_duty_items=["09:00 standup"],
        on_timebox=on_timebox,
        sleep=clock.sleep,
        now=lambda: clock.wall,
        monotonic=lambda: clock.mono,
        tick_seconds=1,
        lead_seconds=60,
    )
    sched.run()

    assert len(reminders) == 1
    assert reminders[0].title == "standup"
