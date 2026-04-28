# Project Totems — Google Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Google Calendar duty source so the *Today* card shows actual calendar events fetched from one or more Google Calendar private iCal URLs, alongside the existing text-file source.

**Architecture:** A new `GoogleCalendarDutySource` slots into the existing `DutySource` Protocol. The factory becomes `make_duty_sources(cfg) -> list[DutySource]` so multiple sources coexist; the entrypoint loops and concatenates. Per-block fetch with stale-cache fallback. iCal parsing via `icalendar`; recurring expansion via `recurring-ical-events`.

**Tech Stack:** Python 3.12 (existing), `icalendar` and `recurring-ical-events` (new pure-Python runtime deps), tkinter (existing), pytest (existing).

**Spec reference:** `docs/superpowers/specs/2026-04-28-project-totems-google-calendar-design.md`

---

## File Structure

Files this plan creates or touches. Each one stays small and focused.

```
totems/
├── pyproject.toml                                  # add 2 runtime deps
├── README.md                                       # Project Totems section + URL example
├── src/totems/
│   ├── config.py                                   # Config field rename + new urls field
│   ├── __main__.py                                 # use make_duty_sources; --debug-calendar
│   ├── settings_window.py                          # add "Google Calendar URLs" section
│   └── duty_sources/
│       ├── __init__.py                             # make_duty_sources factory
│       └── google_calendar.py                      # NEW: source + iCal helpers
└── tests/
    ├── test_config.py                              # kinds + google_calendar urls
    ├── test_main.py                                # plumbing through make_duty_sources
    ├── test_settings_window.py                     # URLs section smoke
    └── duty_sources/
        ├── _fixtures.py                            # NEW: tiny iCal builders
        ├── test_factory.py                         # NEW: make_duty_sources behaviors
        └── test_google_calendar.py                 # NEW: parse/format/cache tests
```

**Notes on structure:**

- `google_calendar.py` exposes a small public surface: the `GoogleCalendarDutySource` class, plus a `_extract_today_items(ical_bytes, *, now)` helper that's exported as `extract_today_items` for tests. Keeping the pure logic in a function (not a method) makes Task 2 a self-contained, network-free unit.
- `_fixtures.py` is a tiny test helper exposing three iCal-bytes builders. Keeping fixtures out of the test file proper avoids 200 lines of `BEGIN:VEVENT` noise per test.
- `tests/duty_sources/test_factory.py` is new — the existing factory tests are inside `tests/duty_sources/test_textfile.py`, but with the factory growing they deserve their own file.

---

## Task 1: Config schema + factory shape

**Goal:** `Config` carries a tuple of duty source kinds and a tuple of Google Calendar URLs. Factory returns a list. Entrypoint loops. Build stays green; v1 textfile users keep working without editing their `config.toml` (back-compat).

**Files:**

- Modify: `src/totems/config.py`
- Modify: `src/totems/duty_sources/__init__.py`
- Modify: `src/totems/__main__.py`
- Modify: `tests/test_config.py`
- Create: `tests/duty_sources/test_factory.py`
- Modify: `tests/duty_sources/test_textfile.py` (drop the factory tests that move to test_factory.py)
- Modify: `tests/test_main.py` (update plumbing assertions if any reference `make_duty_source`)

### Step 1.1: Write failing config tests

In `tests/test_config.py`, add (and update existing tests to use the new field names):

```python
def test_load_config_accepts_kinds_list(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "p"\n'
        "[duty_source]\nkinds = [\"textfile\", \"google_calendar\"]\n"
        "[duty_source.google_calendar]\nurls = [\"https://example.com/cal.ics\"]\n"
    )
    cfg = load_config(p)
    assert cfg.duty_source_kinds == ("textfile", "google_calendar")
    assert cfg.google_calendar_urls == ("https://example.com/cal.ics",)


def test_load_config_back_compat_kind_string(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "p"\n[duty_source]\nkind = "textfile"\n')
    cfg = load_config(p)
    assert cfg.duty_source_kinds == ("textfile",)
    assert cfg.google_calendar_urls == ()


def test_load_config_default_kinds(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "p"\n')
    cfg = load_config(p)
    assert cfg.duty_source_kinds == ("textfile",)


def test_load_config_rejects_unknown_kind(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "p"\n[duty_source]\nkinds = ["nonsense"]\n')
    with pytest.raises(ConfigError, match="unknown duty source"):
        load_config(p)


def test_load_config_rejects_non_list_kinds(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "p"\n[duty_source]\nkinds = "textfile"\n')
    with pytest.raises(ConfigError, match="kinds"):
        load_config(p)


def test_load_config_rejects_google_urls_not_list(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "p"\n'
        "[duty_source]\nkinds = [\"google_calendar\"]\n"
        "[duty_source.google_calendar]\nurls = \"https://example.com/cal.ics\"\n"
    )
    with pytest.raises(ConfigError, match="urls"):
        load_config(p)


def test_load_config_rejects_google_url_empty_string(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "p"\n'
        "[duty_source]\nkinds = [\"google_calendar\"]\n"
        "[duty_source.google_calendar]\nurls = [\"\"]\n"
    )
    with pytest.raises(ConfigError, match="urls"):
        load_config(p)


def test_load_config_allows_empty_google_urls(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "p"\n'
        "[duty_source]\nkinds = [\"google_calendar\"]\n"
        "[duty_source.google_calendar]\nurls = []\n"
    )
    cfg = load_config(p)
    assert cfg.google_calendar_urls == ()


def test_write_config_emits_kinds_and_google_urls(tmp_path):
    p = tmp_path / "config.toml"
    cfg = Config(
        ritual_phrase="hello",
        duty_source_kinds=("textfile", "google_calendar"),
        google_calendar_urls=("https://example.com/cal.ics",),
    )
    write_config(p, cfg)
    text = p.read_text(encoding="utf-8")
    assert 'kinds = ["textfile", "google_calendar"]' in text
    assert "[duty_source.google_calendar]" in text
    assert 'urls = ["https://example.com/cal.ics"]' in text
    # Round-trip
    assert load_config(p) == cfg
```

Update existing `test_load_config_parses_valid_toml` and any others that referenced `Config.duty_source_kind` to use `Config(... duty_source_kinds=("textfile",), google_calendar_urls=())` instead.

- [ ] **Step 1.2: Run, verify failures**

Run: `uv run pytest tests/test_config.py -v`
Expected: failures referencing the new fields / `unknown duty source` / `kinds`. The point is that the new tests fail and the rewritten old tests fail.

- [ ] **Step 1.3: Update `Config` dataclass and loader/writer**

In `src/totems/config.py`:

Replace the `Config` dataclass and known-kinds set:

```python
KNOWN_DUTY_SOURCE_KINDS: frozenset[str] = frozenset({"textfile", "google_calendar"})


@dataclass(frozen=True)
class Config:
    ritual_phrase: str
    work_minutes: int = 45
    block_minutes: int = 5
    duty_source_kinds: tuple[str, ...] = ("textfile",)
    google_calendar_urls: tuple[str, ...] = ()
    content_mode: str = "merge"
```

Replace `load_config` body (the parts after the timing section parse) with:

```python
    duty = _optional_table(data, "duty_source", path)
    duty_source_kinds = _parse_duty_source_kinds(duty, path)

    google = _optional_table(duty, "google_calendar", path)
    google_calendar_urls = _parse_google_calendar_urls(google, path)
    if "google_calendar" in duty_source_kinds and google_calendar_urls == () and "urls" not in google:
        # Defaults to no URLs is fine; explicit invalid types are caught above.
        pass

    content = _optional_table(data, "content", path)
    content_mode = content.get("mode", "merge")
    if content_mode not in {"merge", "replace"}:
        raise ConfigError(f"{path} has invalid config value: content.mode must be 'merge' or 'replace'")

    return Config(
        ritual_phrase=ritual_phrase,
        work_minutes=_positive_int(timing.get("work_minutes", 45), "timing.work_minutes", path),
        block_minutes=_positive_int(timing.get("block_minutes", 5), "timing.block_minutes", path),
        duty_source_kinds=duty_source_kinds,
        google_calendar_urls=google_calendar_urls,
        content_mode=content_mode,
    )


def _parse_duty_source_kinds(duty: dict, path: Path) -> tuple[str, ...]:
    if "kinds" in duty:
        kinds_raw = duty["kinds"]
        if not isinstance(kinds_raw, list) or not all(isinstance(k, str) for k in kinds_raw):
            raise ConfigError(f"{path} has invalid config value: duty_source.kinds must be a list of strings")
        kinds = tuple(k.strip() for k in kinds_raw)
    elif "kind" in duty:
        kind_raw = duty["kind"]
        if not isinstance(kind_raw, str) or not kind_raw.strip():
            raise ConfigError(f"{path} has invalid config value: duty_source.kind must be a non-empty string")
        kinds = (kind_raw.strip(),)
    else:
        kinds = ("textfile",)

    if not kinds:
        raise ConfigError(f"{path} has invalid config value: duty_source.kinds must not be empty")
    for k in kinds:
        if not k:
            raise ConfigError(f"{path} has invalid config value: duty_source.kinds entries must be non-empty")
        if k not in KNOWN_DUTY_SOURCE_KINDS:
            raise ConfigError(f"{path} has invalid config value: unknown duty source kind {k!r}")
    return kinds


def _parse_google_calendar_urls(google: dict, path: Path) -> tuple[str, ...]:
    if "urls" not in google:
        return ()
    urls_raw = google["urls"]
    if not isinstance(urls_raw, list) or not all(isinstance(u, str) for u in urls_raw):
        raise ConfigError(f"{path} has invalid config value: duty_source.google_calendar.urls must be a list of strings")
    if any(not u.strip() for u in urls_raw):
        raise ConfigError(f"{path} has invalid config value: duty_source.google_calendar.urls entries must be non-empty")
    return tuple(u.strip() for u in urls_raw)
```

Replace `write_config` body with:

```python
def write_config(path: Path, cfg: Config) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kinds_array = "[" + ", ".join(f'"{_toml_escape(k)}"' for k in cfg.duty_source_kinds) + "]"
    urls_array = "[" + ", ".join(f'"{_toml_escape(u)}"' for u in cfg.google_calendar_urls) + "]"
    path.write_text(
        f'ritual_phrase = "{_toml_escape(cfg.ritual_phrase)}"\n'
        "\n"
        "[timing]\n"
        f"work_minutes = {cfg.work_minutes}\n"
        f"block_minutes = {cfg.block_minutes}\n"
        "\n"
        "[duty_source]\n"
        f"kinds = {kinds_array}\n"
        "\n"
        "[duty_source.google_calendar]\n"
        f"urls = {urls_array}\n"
        "\n"
        "[content]\n"
        '# "merge" keeps bundled defaults; "replace" uses only your quotes.txt and wisdom.txt.\n'
        f'mode = "{_toml_escape(cfg.content_mode)}"\n',
        encoding="utf-8",
    )
```

- [ ] **Step 1.4: Run config tests, verify pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: all config tests pass (the new ones plus the rewritten old ones).

- [ ] **Step 1.5: Move factory tests + write failing make_duty_sources tests**

Open `tests/duty_sources/test_textfile.py`. The two tests `test_factory_returns_textfile` and `test_factory_raises_on_unknown_kind` will be replaced. Delete them.

Create `tests/duty_sources/test_factory.py`:

```python
from pathlib import Path

import pytest

from totems.config import Config
from totems.duty_sources import make_duty_sources
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


def test_make_duty_sources_returns_in_kinds_order(tmp_path):
    sources = make_duty_sources(
        _cfg(
            duty_source_kinds=("google_calendar", "textfile"),
            google_calendar_urls=("https://example.com/cal.ics",),
        ),
        config_dir=tmp_path,
    )
    # First slot is the google_calendar source, second is textfile.
    # Type-checked by attribute presence rather than importing the class
    # so this test stays valid before Task 4 lands.
    assert len(sources) == 2
    assert sources[1].__class__ is TextFileDutySource


def test_make_duty_sources_empty_kinds_raises(tmp_path):
    with pytest.raises(ValueError, match="duty_source_kinds must not be empty"):
        make_duty_sources(_cfg(duty_source_kinds=()), config_dir=tmp_path)


def test_make_duty_sources_unknown_kind_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown duty source"):
        make_duty_sources(_cfg(duty_source_kinds=("nonsense",)), config_dir=tmp_path)
```

Note: the second test will pass for the textfile slot but fail for the google_calendar slot until Task 4 (where the real class lands). For Task 1 we make the factory raise `NotImplementedError` for `"google_calendar"`, and the test will be updated in Task 4. To keep Task 1 self-consistent, **delete the second test for now and re-add it in Task 4**. Replace with this Task-1-only stand-in:

```python
def test_make_duty_sources_google_calendar_not_yet_supported(tmp_path):
    with pytest.raises(NotImplementedError, match="google_calendar"):
        make_duty_sources(
            _cfg(
                duty_source_kinds=("google_calendar",),
                google_calendar_urls=("https://example.com/cal.ics",),
            ),
            config_dir=tmp_path,
        )
```

- [ ] **Step 1.6: Run factory tests, verify failures**

Run: `uv run pytest tests/duty_sources/ -v`
Expected: `make_duty_sources` not defined → ImportError.

- [ ] **Step 1.7: Implement `make_duty_sources`**

Replace `src/totems/duty_sources/__init__.py` entirely:

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .textfile import TextFileDutySource


@runtime_checkable
class DutySource(Protocol):
    def today(self) -> list[str]: ...


def make_duty_sources(cfg, *, config_dir: Path) -> list[DutySource]:
    """Build the configured duty sources, in the order they appear in cfg.duty_source_kinds."""
    if not cfg.duty_source_kinds:
        raise ValueError("duty_source_kinds must not be empty")

    sources: list[DutySource] = []
    for kind in cfg.duty_source_kinds:
        if kind == "textfile":
            sources.append(TextFileDutySource(config_dir / "duties.txt"))
        elif kind == "google_calendar":
            raise NotImplementedError("google_calendar duty source lands in Task 4")
        else:
            raise ValueError(f"unknown duty source: {kind!r}")
    return sources
```

The `cfg` parameter is intentionally untyped here; importing `Config` from `config.py` would create a cycle. A docstring + the duck-typed access (`cfg.duty_source_kinds`) is enough.

- [ ] **Step 1.8: Run factory tests, verify pass**

Run: `uv run pytest tests/duty_sources/ -v`
Expected: all pass (textfile tests + factory tests).

- [ ] **Step 1.9: Update entrypoint to use `make_duty_sources`**

In `src/totems/__main__.py`:

Change the import:

```python
from .duty_sources import DutySource, make_duty_sources
```

Change `_build_block_content`'s signature to take `duty_sources: list[DutySource]` and concatenate:

```python
def _build_block_content(
    cfg_dir: Path,
    cfg: Config,
    rng: random.Random,
    duty_sources: list[DutySource],
) -> BlockContent:
    user_content = load_user_content_json(cfg_dir / "content.json")
    if user_content is None:
        quotes = load_quotes(_read_text_or_none(cfg_dir / "quotes.txt"), mode=cfg.content_mode)
        wisdom_pool = load_wisdom(_read_text_or_none(cfg_dir / "wisdom.txt"), mode=cfg.content_mode)
        duties = _collect_duties(duty_sources)
    else:
        quotes = load_quotes_from_items(user_content.quotes, mode=cfg.content_mode)
        wisdom_pool = load_wisdom_from_items(user_content.wisdom, mode=cfg.content_mode)
        duties = (
            user_content.duties
            if user_content.duties is not None
            else _collect_duties(duty_sources)
        )
    return BlockContent(
        quote=pick_quote(quotes, rng),
        wisdom=pick_wisdom(wisdom_pool, rng, n=2),
        duties=duties,
        symbol_path=get_totem_symbol(config_dir=cfg_dir, rng=rng),
    )


def _collect_duties(duty_sources: list[DutySource]) -> list[str]:
    out: list[str] = []
    for source in duty_sources:
        out.extend(source.today())
    return out
```

In `main`, replace the `make_duty_source` block:

```python
    try:
        duty_sources = make_duty_sources(cfg, config_dir=cfg_dir)
    except (ValueError, NotImplementedError) as e:
        print(f"totems: config error: {e}", file=sys.stderr)
        return 2
```

And update the closure call site:

```python
    def trigger_block() -> str:
        content = _build_block_content(cfg_dir, cfg, rng, duty_sources)
        ...
```

- [ ] **Step 1.10: Update `tests/test_main.py`**

Open `tests/test_main.py`. Anywhere it patches or asserts on `make_duty_source` (singular) or `cfg.duty_source_kind`, update to the new names. The existing test for "duty source error path" should now exercise `make_duty_sources` raising `ValueError` (e.g., by passing `duty_source_kinds=("nonsense",)` via a stub config).

- [ ] **Step 1.11: Run the full test suite, verify pass**

Run: `uv run pytest`
Expected: green. The settings_window tests are unaffected by this task; the block_window smoke tests skip without DISPLAY; the rest pass.

- [ ] **Step 1.12: Commit**

```bash
git add pyproject.toml \
        src/totems/config.py \
        src/totems/duty_sources/__init__.py \
        src/totems/__main__.py \
        tests/test_config.py \
        tests/duty_sources/test_factory.py \
        tests/duty_sources/test_textfile.py \
        tests/test_main.py
git commit -m "Switch duty sources to a list-based config schema"
```

(`pyproject.toml` is in the add list to keep diffs grouped; only the deps will change later in Task 3, but if you've added them already, fine.)

---

## Task 2: Pure iCal extraction helper

**Goal:** Given iCal bytes and a "now" datetime, return today's events as a sorted, formatted, deduped list of strings. No I/O. No class. This is the unit that exercises `icalendar` + `recurring_ical_events`.

**Files:**

- Modify: `pyproject.toml` (add runtime deps)
- Create: `src/totems/duty_sources/google_calendar.py` (helper only for now)
- Create: `tests/duty_sources/_fixtures.py`
- Create: `tests/duty_sources/test_google_calendar.py`

### Step 2.1: Add runtime deps to `pyproject.toml`

Edit `pyproject.toml`:

```toml
[project]
...
dependencies = [
    "icalendar>=5.0",
    "recurring-ical-events>=2.1",
]
```

Run `uv sync` to install.

- [ ] **Step 2.2: Create iCal fixture builders**

Create `tests/duty_sources/_fixtures.py`:

```python
"""Tiny iCal builders for tests. No real network or files."""

from __future__ import annotations

from datetime import date, datetime


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
    """Format a tz-aware datetime as iCal local-time-with-tz."""
    if dt.tzinfo is None:
        raise ValueError("fixture datetime must be tz-aware")
    return dt.strftime("%Y%m%dT%H%M%S")


def _dtstart_dtend(start: datetime, end: datetime) -> str:
    """Render DTSTART/DTEND lines, using the Z form for UTC and TZID otherwise.

    `icalendar` doesn't reliably accept TZID=UTC; convention is the trailing Z.
    """
    from datetime import timezone

    if start.tzinfo is timezone.utc:
        return (
            f"DTSTART:{_fmt_dt(start)}Z\r\n"
            f"DTEND:{_fmt_dt(end)}Z\r\n"
        )
    tzid = str(start.tzinfo)
    return (
        f"DTSTART;TZID={tzid}:{_fmt_dt(start)}\r\n"
        f"DTEND;TZID={tzid}:{_fmt_dt(end)}\r\n"
    )


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
    """A weekly recurrence on the same weekday as `first_start`."""
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
    """Glue multiple iCal-bytes blobs into one calendar (events from each merged).

    Strips per-blob VCALENDAR wrappers; keeps a single header/footer.
    """
    inner_parts: list[str] = []
    for cal in calendars:
        text = cal.decode("utf-8")
        body = text.split("BEGIN:VCALENDAR\r\n", 1)[1]
        body = body.rsplit("END:VCALENDAR\r\n", 1)[0]
        # Drop the VCALENDAR-level metadata lines (VERSION/PRODID/CALSCALE), keep VEVENTs.
        events = []
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
    """A VEVENT missing required fields, used to test 'skip bad events' behavior."""
    body = (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        # No SUMMARY, no DTSTART
        "END:VEVENT\r\n"
    )
    return _wrap(body)
```

- [ ] **Step 2.3: Write failing helper tests**

Create `tests/duty_sources/test_google_calendar.py`:

```python
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from totems.duty_sources.google_calendar import extract_today_items

from ._fixtures import (
    malformed_event,
    merge,
    single_all_day_event,
    single_timed_event,
    weekly_recurring_event,
)


# Fix "now" for all tests so today is a Tuesday in PT.
LA = ZoneInfo("America/Los_Angeles")
NOW_LA = datetime(2026, 4, 28, 12, 30, tzinfo=LA)  # Tuesday lunchtime


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
    # First instance was last Tuesday; recurring weekly => today is included.
    cal = weekly_recurring_event(
        title="weekly review",
        first_start=datetime(2026, 4, 21, 14, 0, tzinfo=LA),
        first_end=datetime(2026, 4, 21, 15, 0, tzinfo=LA),
    )
    assert extract_today_items(cal, now=NOW_LA) == ["14:00 weekly review"]


def test_recurring_weekly_event_does_not_match_other_weekday():
    # First instance Mondays => Tuesday today does NOT include it.
    cal = weekly_recurring_event(
        title="monday meeting",
        first_start=datetime(2026, 4, 20, 14, 0, tzinfo=LA),
        first_end=datetime(2026, 4, 20, 15, 0, tzinfo=LA),
    )
    assert extract_today_items(cal, now=NOW_LA) == []


def test_utc_dtstart_converted_to_local():
    # 16:00 UTC == 09:00 PDT on 2026-04-28
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
```

- [ ] **Step 2.4: Run tests, verify failures**

Run: `uv run pytest tests/duty_sources/test_google_calendar.py -v`
Expected: ImportError (the module doesn't exist).

- [ ] **Step 2.5: Implement `extract_today_items`**

Create `src/totems/duty_sources/google_calendar.py`:

```python
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

import icalendar
import recurring_ical_events


def extract_today_items(ical_bytes: bytes, *, now: datetime) -> list[str]:
    """Parse an iCal byte string and return today's events as formatted strings.

    `now` must be timezone-aware. "Today" is the calendar day containing `now`
    in `now`'s timezone. Output is sorted: all-day events first (alphabetical),
    then timed events ascending by start.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tz = now.tzinfo
    today: date = now.date()
    start_of_day = datetime.combine(today, time.min, tzinfo=tz)
    end_of_day = start_of_day + timedelta(days=1)

    cal = icalendar.Calendar.from_ical(ical_bytes)
    events = recurring_ical_events.of(cal).between(start_of_day, end_of_day)

    all_day: list[str] = []
    timed: list[tuple[datetime, str]] = []

    for event in events:
        formatted = _format_event(event, tz)
        if formatted is None:
            continue
        kind, key, text = formatted
        if kind == "all_day":
            all_day.append(text)
        else:
            timed.append((key, text))

    all_day.sort()
    timed.sort(key=lambda pair: pair[0])
    return all_day + [t for _, t in timed]


def _format_event(event: Any, tz) -> tuple[str, datetime, str] | None:
    """Return (kind, sort_key, text) or None if the event should be skipped."""
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
        local_start = raw.astimezone(tz)
        text = f"{local_start.strftime('%H:%M')} {summary_str}"
        return ("timed", local_start, text)
    if isinstance(raw, date):
        return ("all_day", datetime.min, f"all day: {summary_str}")
    return None
```

- [ ] **Step 2.6: Run tests, verify pass**

Run: `uv run pytest tests/duty_sources/test_google_calendar.py -v`
Expected: 9 passed.

- [ ] **Step 2.7: Commit**

```bash
git add pyproject.toml uv.lock \
        src/totems/duty_sources/google_calendar.py \
        tests/duty_sources/_fixtures.py \
        tests/duty_sources/test_google_calendar.py
git commit -m "Add iCal extract_today_items helper with parse/format/sort/skip rules"
```

(`uv.lock` may or may not be tracked. If it's gitignored or untracked-by-design, drop it from the add list — check `git status` first.)

---

## Task 3: GoogleCalendarDutySource class — fetcher, cache, multi-URL, partial failure

**Goal:** Wrap the pure helper in a class that handles the I/O concerns: fetching multiple URLs, dedupe across URLs, on-disk cache, partial-failure semantics. Wire the class into `make_duty_sources`.

**Files:**

- Modify: `src/totems/duty_sources/google_calendar.py` (add class)
- Modify: `src/totems/duty_sources/__init__.py` (factory branch)
- Modify: `tests/duty_sources/test_google_calendar.py` (add class tests)
- Modify: `tests/duty_sources/test_factory.py` (replace the not-yet-supported stand-in)

### Step 3.1: Write failing class tests

Add to `tests/duty_sources/test_google_calendar.py`:

```python
import json
from datetime import date, datetime
from pathlib import Path

from zoneinfo import ZoneInfo

from totems.duty_sources.google_calendar import GoogleCalendarDutySource

from ._fixtures import single_all_day_event, single_timed_event


# (re-uses LA and NOW_LA defined earlier)


def _src(urls, cache_path, fetcher):
    return GoogleCalendarDutySource(
        urls=urls,
        cache_path=cache_path,
        fetcher=fetcher,
        now=lambda: NOW_LA,
    )


def test_today_returns_concatenated_results(tmp_path):
    # The all-day URL comes first so the per-URL sort + concatenate rule
    # yields ["all day: vacation", "09:00 standup"]. (Per-URL sort, not
    # global re-sort across URLs — see Step 3.3 commentary.)
    cal_a = single_all_day_event(title="vacation", day=date(2026, 4, 28))
    cal_b = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
    )

    def fetcher(url):
        return cal_a if "a" in url else cal_b

    src = _src(["a.ics", "b.ics"], tmp_path / "cache.json", fetcher)
    items = src.today()
    assert items == ["all day: vacation", "09:00 standup"]


def test_today_dedupes_across_urls(tmp_path):
    cal = single_timed_event(
        title="standup",
        start=datetime(2026, 4, 28, 9, 0, tzinfo=LA),
        end=datetime(2026, 4, 28, 9, 30, tzinfo=LA),
    )

    def fetcher(url):
        return cal

    src = _src(["a.ics", "b.ics"], tmp_path / "cache.json", fetcher)
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

    payload = json.loads(cache.read_text())
    assert payload["items"] == ["09:00 standup"]
    assert payload["fetched_at"].endswith("+00:00")


def test_today_reads_cache_on_full_failure(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({
        "fetched_at": "2026-04-27T00:00:00+00:00",
        "items": ["09:00 stale-standup"],
    }))

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
    cache.write_text("{not valid json")

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
    payload = json.loads(cache.read_text())
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
```

Update `tests/duty_sources/test_factory.py`: delete the `test_make_duty_sources_google_calendar_not_yet_supported` stand-in. Add real tests:

```python
from totems.duty_sources.google_calendar import GoogleCalendarDutySource


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
    expected_cache = tmp_path / ".cache" / "google_calendar.json"
    assert sources[0].cache_path == expected_cache
```

- [ ] **Step 3.2: Run, verify failures**

Run: `uv run pytest tests/duty_sources/ -v`
Expected: ImportError on `GoogleCalendarDutySource`.

- [ ] **Step 3.3: Implement `GoogleCalendarDutySource`**

Append to `src/totems/duty_sources/google_calendar.py`:

```python
import json
import logging
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path


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
                ical_bytes = self._fetcher(url)
                items = extract_today_items(ical_bytes, now=now)
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
```

Note: dedupe inside `today()` (not inside `extract_today_items`) is intentional — `extract_today_items` works on a single calendar; cross-URL dedupe needs the multi-URL view.

Important — the multi-URL sort/all-day-first ordering is preserved per-URL but **not** re-applied across URLs. The simpler invariant is "events from earlier URLs come first; within a URL, the helper's sort order applies." That matches what the spec says ("concatenated in source order"). The test `test_today_returns_concatenated_results` asserts the all-day-first-within-each-URL outcome and works because both URLs each have one item.

If the spec's "all-day first across the merged result" reading bites later, this is the place to add a re-sort. **Decision for v1: per-URL sort, concatenate.** The dedupe pass preserves first occurrence, which is consistent with this rule.

- [ ] **Step 3.4a: Drop the `NotImplementedError` stand-in from the entrypoint**

In `src/totems/__main__.py`, the existing `make_duty_sources` call is wrapped in
`except (ValueError, NotImplementedError)`. Now that the google_calendar branch
returns a real instance, drop `NotImplementedError`:

```python
    try:
        duty_sources = make_duty_sources(cfg, config_dir=cfg_dir)
    except ValueError as e:
        print(f"totems: config error: {e}", file=sys.stderr)
        return 2
```

Otherwise a future genuine `NotImplementedError` would be silently misclassified
as a config error.

- [ ] **Step 3.4b: Wire `google_calendar` into the factory**

In `src/totems/duty_sources/__init__.py`, replace the `NotImplementedError` branch:

```python
from .google_calendar import GoogleCalendarDutySource


def make_duty_sources(cfg, *, config_dir: Path) -> list[DutySource]:
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
```

- [ ] **Step 3.5: Run all duty source tests**

Run: `uv run pytest tests/duty_sources/ -v`
Expected: all pass (textfile + factory + google_calendar = 9 helper + 9 class + 4 factory = ~22+ tests).

- [ ] **Step 3.6: Run the full test suite**

Run: `uv run pytest`
Expected: green.

- [ ] **Step 3.7: Commit**

```bash
git add src/totems/duty_sources/google_calendar.py \
        src/totems/duty_sources/__init__.py \
        tests/duty_sources/test_google_calendar.py \
        tests/duty_sources/test_factory.py
git commit -m "Add GoogleCalendarDutySource with multi-URL fetch, cache, partial-failure"
```

---

## Task 4: Settings editor — Google Calendar URLs section

**Goal:** A new section in the settings editor lets the user paste/edit URLs as a multiline list. Empty content effectively disables the Google source. Autosaves with the same debounce as the existing fields.

**Files:**

- Modify: `src/totems/settings_window.py`
- Modify: `tests/test_settings_window.py`

### Step 4.1: Read settings_window.py

(Plan for the implementer — at the start of this task, read `src/totems/settings_window.py` to see the existing autosave debounce pattern. The new field should mirror it: a `tk.Text` widget bound to a debounced save handler.)

### Step 4.2: Write a failing smoke test

Add to `tests/test_settings_window.py`:

```python
import os

import pytest


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY"))


pytestmark = pytest.mark.skipif(not _has_display(), reason="needs an X display")


def test_settings_editor_renders_google_urls_section(tmp_path):
    from totems.settings_window import SettingsWindow
    from totems.config import Config, write_config

    cfg = Config(
        ritual_phrase="p",
        duty_source_kinds=("textfile", "google_calendar"),
        google_calendar_urls=("https://example.com/cal.ics",),
    )
    write_config(tmp_path / "config.toml", cfg)

    win = SettingsWindow(config_dir=tmp_path)
    win.root.update()
    win.root.update_idletasks()
    text = win._google_urls_text.get("1.0", "end").strip()
    assert text == "https://example.com/cal.ics"
    win.root.destroy()


def test_settings_editor_save_writes_google_urls(tmp_path):
    from totems.settings_window import SettingsWindow
    from totems.config import Config, load_config, write_config

    cfg = Config(ritual_phrase="p")
    write_config(tmp_path / "config.toml", cfg)

    win = SettingsWindow(config_dir=tmp_path)
    win._google_urls_text.insert("1.0", "https://example.com/a.ics\nhttps://example.com/b.ics\n")
    win._save_now()  # bypass debounce for the test
    win.root.destroy()

    saved = load_config(tmp_path / "config.toml")
    assert saved.google_calendar_urls == (
        "https://example.com/a.ics",
        "https://example.com/b.ics",
    )
    # google_calendar should be in kinds because the user just added URLs
    assert "google_calendar" in saved.duty_source_kinds
```

(The exact attribute names — `_google_urls_text`, `_save_now` — are implementer choices but should match the existing settings_window patterns. If the existing module uses different conventions, mirror those.)

### Step 4.3: Run tests, verify failures

Run: `DISPLAY="${DISPLAY:-:0}" uv run pytest tests/test_settings_window.py -v`
Expected: AttributeError or similar.

### Step 4.4: Implement the URLs section

**Important:** the existing settings_window has both a `_save_now` (or
similar) explicit-save and an `_autosave` debounced path. Both go through the
same "collect current state into a `Config`" code path. Update both call
sites — don't update only one. Sketch below shows the shared collector.



In `src/totems/settings_window.py`:

1. Add a new `tk.Text` widget for "Google Calendar URLs" placed in the layout near the existing fields. Match the existing typography and spacing.
2. Pre-fill it from `cfg.google_calendar_urls`, one URL per line.
3. Bind to the existing debounced save handler.
4. In the save handler, read the text widget's content, split on newline, strip whitespace, drop blanks. Pass as `tuple` to a new `Config(...)` along with the existing fields.
5. **Auto-toggle the kind:** if the URLs list is non-empty and `"google_calendar"` is not in `duty_source_kinds`, append it. If the URLs list becomes empty, optionally remove `"google_calendar"`. Choose the cleaner rule: **always include `"google_calendar"` in `duty_source_kinds` whenever any URL is set; remove it when there are zero URLs.** This keeps the user-facing model simple — "the URLs are the toggle."
6. Errors during save (e.g., the user's text doesn't validate) should set the existing autosave-status indicator to a warning, same as the other validation flows.

Concretely, the save flow becomes (sketch — adapt to the actual file's structure):

```python
def _collect_config_for_save(self) -> Config:
    raw = self._google_urls_text.get("1.0", "end")
    urls = tuple(line.strip() for line in raw.splitlines() if line.strip())
    kinds = list(self._current_cfg.duty_source_kinds)
    if urls and "google_calendar" not in kinds:
        kinds.append("google_calendar")
    elif not urls and "google_calendar" in kinds:
        kinds.remove("google_calendar")
    if not kinds:  # never let the kinds list go empty
        kinds = ["textfile"]
    return Config(
        ritual_phrase=self._ritual_phrase_var.get(),
        work_minutes=self._work_minutes_var.get(),
        block_minutes=self._block_minutes_var.get(),
        duty_source_kinds=tuple(kinds),
        google_calendar_urls=urls,
        content_mode=self._content_mode_var.get(),
    )
```

### Step 4.5: Run, verify pass

Run: `DISPLAY="${DISPLAY:-:0}" uv run pytest tests/test_settings_window.py -v`
Expected: pass on a machine with a display, skip otherwise.

### Step 4.6: Commit

```bash
git add src/totems/settings_window.py tests/test_settings_window.py
git commit -m "Add Google Calendar URLs section to settings editor"
```

---

## Task 5: `--debug-calendar` CLI flag

**Goal:** A no-block sanity check the user can run after pasting a URL: prints today's items to stdout and exits.

**Files:**

- Modify: `src/totems/__main__.py`

### Step 5.1: Add the flag and dispatch

In `src/totems/__main__.py`:

```python
parser.add_argument(
    "--debug-calendar",
    action="store_true",
    help="fetch the configured Google Calendar URLs once, print today's items, and exit",
)
```

After config loading and `make_duty_sources` succeed, before the scheduler block:

```python
    if args.debug_calendar:
        from .duty_sources.google_calendar import GoogleCalendarDutySource

        google_sources = [s for s in duty_sources if isinstance(s, GoogleCalendarDutySource)]
        if not google_sources:
            print("totems: no google_calendar URLs configured", file=sys.stderr)
            return 2
        for source in google_sources:
            for item in source.today():
                print(item)
        return 0
```

(Place this branch right next to the existing `args.debug_now` / `args.fast` handling — the order of CLI branches in `main` should stay readable.)

### Step 5.2: Manual smoke test

Run:
```bash
uv run totems --debug-calendar
```

Expected: prints today's iCal events one per line, exits 0. If no URLs configured, prints the error and exits 2.

(No automated test — `--debug-calendar` is a manual sanity-check flag.)

### Step 5.3: Commit

```bash
git add src/totems/__main__.py
git commit -m "Add --debug-calendar CLI flag for one-shot calendar inspection"
```

---

## Task 6: README — Project Totems framing

**Goal:** Add a Project Totems heading to the README explaining the metaphor and linking to the Inception wiki, and add a config example for the new sub-table.

**Files:**

- Modify: `README.md`

### Step 6.1: Read the current README

(Implementer: read `README.md`. The current structure is a short intro, "Run", "Config files", "Tests" sections.)

### Step 6.2: Add the Project Totems section

Insert a new section near the top of the README, after the intro paragraph and before "Run":

```markdown
## Project Totems

Working name for the Google-Calendar-aware version. The metaphor: in
*Inception*, a [totem](https://inception.fandom.com/wiki/Totem) is a small
personal object you check to ground yourself in waking life. In this app, the
whole block window — the quote, the wisdom items, today's agenda, the totem symbol,
your ritual phrase — is the totem. It's *yours*, customizable end to end, and
it's what pulls you out of the work-trance.
```

### Step 6.3: Update the Config files section

In the "Config files" section, add to the `~/.config/totems/` tree:

```text
~/.config/totems/
├── config.toml
├── content.json
├── quotes.txt
├── wisdom.txt
├── duties.txt
├── totem_symbols/
└── .cache/
    └── google_calendar.json   # auto-managed; stale-cache fallback
```

Add a `config.toml` example to that section:

```markdown
### Connecting Google Calendar

Open a calendar in Google Calendar's web UI → Settings → "Integrate calendar"
→ "Secret address in iCal format" → copy the URL. Paste one or more into
the settings editor under "Google Calendar URLs" (or edit `config.toml`
directly):

```toml
[duty_source]
kinds = ["textfile", "google_calendar"]

[duty_source.google_calendar]
urls = [
    "https://calendar.google.com/calendar/ical/.../basic.ics",
]
```

The URL is itself the credential — keep it private. The app fetches each
configured URL once per block and falls back to the last successful result
on network errors.
```

(Note: the inner code fence is `\`\`\`toml`, not nested triple-fences; the
README should render it as a code block.)

### Step 6.4: Manual check

Run: `cat README.md` and confirm the new section flows correctly.

### Step 6.5: Commit

```bash
git add README.md
git commit -m "Document Project Totems framing and Google Calendar setup in README"
```

---

## Final verification

After Task 6, run the full suite once more:

```bash
uv run pytest
```

Expected: all tests pass (GUI smoke tests skip without DISPLAY).

Manual sanity:

```bash
uv run totems --debug-calendar       # prints today's events from your real calendar
uv run totems --debug-now            # one block now, with the Today card populated from the calendar
```

---

## Decision summary baked into this plan

These were settled in brainstorming and you should not need to revisit during
implementation:

- **Connection method:** private iCal URLs (per-calendar secret addresses).
- **Auth:** none (URL is the credential).
- **Recurring events:** supported via `icalendar` + `recurring-ical-events`.
- **Refresh cadence:** per block; no in-call retries.
- **Multiple calendars:** supported (`urls` is a list).
- **Failure mode:** stale cache fallback; partial successes cached.
- **Coexistence with textfile:** both can be active (`kinds` is a list).
- **Display format:** `09:00 standup` / `all day: vacation`, 24h, local TZ.
- **Sort:** all-day first (alphabetical), then timed ascending. Across URLs: per-URL sort, concatenated in source order, deduped by formatted string.
- **Settings UI:** URLs are the toggle (any URLs → kind active; no URLs → kind removed).
- **Cache shape:** `{"fetched_at": "...UTC...", "items": [...]}` at `~/.config/totems/.cache/google_calendar.json`.
- **Logging:** stdlib `logging`, single warning per failure.
- **Out of scope this round:** OAuth, write access, calendar selection UI, stale-indicator UI, `duties` → `totems` rename.
