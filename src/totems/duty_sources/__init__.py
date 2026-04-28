from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .google_calendar import GoogleCalendarDutySource
from .textfile import TextFileDutySource


@runtime_checkable
class DutySource(Protocol):
    def today(self) -> list[str]: ...


def make_duty_sources(cfg, *, config_dir: Path) -> list[DutySource]:
    """Build configured duty sources in cfg.duty_source_kinds order."""
    if not cfg.duty_source_kinds:
        raise ValueError("duty_source_kinds must not be empty")

    sources: list[DutySource] = []
    for kind in cfg.duty_source_kinds:
        if kind == "textfile":
            sources.append(TextFileDutySource(config_dir / "duties.txt"))
        elif kind == "google_calendar":
            sources.append(
                GoogleCalendarDutySource(
                    urls=list(cfg.google_calendar_urls),
                    cache_path=config_dir / ".cache" / "google_calendar.json",
                )
            )
        else:
            raise ValueError(f"unknown duty source: {kind!r}")
    return sources
