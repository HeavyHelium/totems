import pytest

from totems.config import Config
from totems.duty_sources import make_duty_sources
from totems.duty_sources.google_calendar import GoogleCalendarDutySource
from totems.duty_sources.textfile import TextFileDutySource


def _cfg(**kwargs) -> Config:
    base = dict(
        ritual_phrase="p",
        duty_source_kinds=("textfile",),
        google_calendar_urls=(),
    )
    base.update(kwargs)
    return Config(**base)


def test_make_duty_sources_textfile_only(tmp_path):
    sources = make_duty_sources(_cfg(), config_dir=tmp_path)
    assert len(sources) == 1
    assert isinstance(sources[0], TextFileDutySource)


def test_make_duty_sources_with_google_calendar(tmp_path):
    cfg = _cfg(
        duty_source_kinds=("google_calendar", "textfile"),
        google_calendar_urls=("https://example.com/cal.ics",),
    )
    sources = make_duty_sources(cfg, config_dir=tmp_path)
    assert len(sources) == 2
    assert isinstance(sources[0], GoogleCalendarDutySource)
    assert isinstance(sources[1], TextFileDutySource)


def test_make_duty_sources_google_calendar_uses_cache_path_in_config_dir(tmp_path):
    cfg = _cfg(
        duty_source_kinds=("google_calendar",),
        google_calendar_urls=("https://example.com/cal.ics",),
    )
    sources = make_duty_sources(cfg, config_dir=tmp_path)
    assert sources[0].cache_path == tmp_path / ".cache" / "google_calendar.json"


def test_make_duty_sources_empty_kinds_raises(tmp_path):
    with pytest.raises(ValueError, match="duty_source_kinds must not be empty"):
        make_duty_sources(_cfg(duty_source_kinds=()), config_dir=tmp_path)


def test_make_duty_sources_unknown_kind_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown duty source"):
        make_duty_sources(_cfg(duty_source_kinds=("nonsense",)), config_dir=tmp_path)
