# Project Totems — Google Calendar duty source

**Date:** 2026-04-28
**Status:** approved (brainstorm)
**Working name:** Project Totems (the whole block window is the totem; this feature
adds calendar-driven items to the *Today* card.)

## Purpose

Show today's actual calendar agenda inside each block window's *Today* card,
fetched directly from one or more Google Calendar private iCal URLs.
Coexists with the existing text-file duty source so ad-hoc reminders still
work.

## Decisions

| Decision | Choice |
| --- | --- |
| Connection method | **Private iCal URLs** (per-calendar "secret address" Google exposes) |
| Authentication | **None** — the URL itself is the credential |
| Recurring events | **Supported**, via the `recurring-ical-events` library (depends on `icalendar`) |
| Refresh cadence | **Per block** — fetch every time a block is about to render |
| Multiple calendars | **Supported** — `urls = [...]` is a list |
| Fetch failure behavior | **Stale-cache fallback** — last successful result on disk |
| Coexistence with textfile source | **Both can be active** — `kinds = [...]` is a list |
| Display format (timed) | `09:00 standup` (24h, leading zero, local TZ) |
| Display format (all-day) | `all day: vacation` |
| Sort order | All-day events first, then timed events ascending by start |
| Settings editor | New section "Google Calendar URLs", debounced autosave like existing fields |
| New runtime deps | `icalendar`, `recurring-ical-events` (both pure-Python) |

## Architecture

The existing `DutySource` Protocol (`today() -> list[str]`) and factory pattern
in `src/totems/duty_sources/__init__.py` were designed for exactly this
extension. Two real changes beyond adding a new source class:

- **Factory returns a list of sources, not a single source.** Today:
  `make_duty_source(kind, *, config_dir) -> DutySource`. New:
  `make_duty_sources(cfg, *, config_dir) -> list[DutySource]`. The entrypoint
  loops and concatenates.
- **Config `kind` becomes `kinds`** (a list). Backwards-compat: when `kind` is
  present and `kinds` isn't, treat as `kinds = [kind]`. No migration needed
  for existing users. Concretely: the `Config.duty_source_kind: str` field
  becomes `Config.duty_source_kinds: tuple[str, ...]` (tuple to keep the
  dataclass hashable), and `write_config` emits the new `kinds = [...]`
  array form.

### New module

`src/totems/duty_sources/google_calendar.py`:

```python
class GoogleCalendarDutySource:
    def __init__(
        self,
        urls: list[str],
        cache_path: Path,
        *,
        fetcher: Callable[[str], bytes] = _http_get,
        now: Callable[[], datetime] = _now_local,
    ) -> None: ...

    def today(self) -> list[str]: ...
```

`fetcher` is the network seam (mirroring the `urlopen=` pattern in `totem_symbols.py`).
`now` is the time seam so tests can pin "today" to a fixed date in a known
timezone.

### Cache location

`<config_dir>/.cache/google_calendar.json` — same `.cache/` parent the totem_symbols
module already uses.

## Configuration

### `config.toml` extension

```toml
[duty_source]
kinds = ["textfile", "google_calendar"]

[duty_source.google_calendar]
urls = [
    "https://calendar.google.com/calendar/ical/.../basic.ics",
]
```

### Backwards compatibility

The loader accepts the existing `kind = "..."` form: when `kind` is present
and `kinds` is absent, treat as `kinds = [kind]`. Existing v1 configs keep
working without edits. Writing config back out (via the settings editor or
`write_config`) emits the new `kinds` form.

### Validation rules

- `kinds` must be a list of non-empty strings; each must be known to the
  factory. Unknown kinds raise `ConfigError` at load time.
- `[duty_source.google_calendar].urls` must be a list of non-empty strings if
  `"google_calendar"` is in `kinds`. May be empty (the source returns `[]`).
- Validation errors are raised eagerly at `load_config` time, not at first
  block, so problems are visible at startup.

### Settings editor

A new section "Google Calendar URLs" — multiline text editor, one URL per
line. Debounced autosave at the same ~800 ms interval as the existing fields.
Empty content effectively disables the source (it stays in `kinds` but the
URL list is empty, so the source returns `[]` without hitting the network).

## Data flow

Per block, the entrypoint builds `BlockContent.duties` by:

1. Looping over the configured `DutySource` instances (from
   `make_duty_sources`).
2. Calling `today()` on each.
3. Concatenating results in source order.

Inside `GoogleCalendarDutySource.today()`:

1. **Short-circuit on empty `urls`** — return `[]` without invoking the
   fetcher.
2. **Fetch each URL** with the injected `fetcher`. Real implementation uses
   `urllib.request.urlopen(url, timeout=10)` and reads the bytes.
3. **Parse** the bytes via `icalendar.Calendar.from_ical(bytes)`.
4. **Expand recurring events** for today's date range using
   `recurring_ical_events.of(cal).between(start_of_today, end_of_today)`.
   The bounds are constructed from `now()` truncated to local midnight (start)
   and the next local midnight (end).
5. **Format each event:**
   - All-day: `"all day: <summary>"`.
   - Timed: `"HH:MM <summary>"` — 24h, zero-padded, in the user's local
     timezone (start time of the event converted via `astimezone()`).
6. **Sort:** all-day events first (alphabetical by summary among themselves),
   then timed events ascending by start time.
7. **Dedupe by formatted string** — collapses the same event appearing in
   multiple subscribed calendars.
8. **Write the formatted list to the cache** as JSON.

### Cache shape

```json
{
  "fetched_at": "2026-04-28T09:14:22+00:00",
  "items": ["09:00 standup", "10:30 1:1 with mira", "all day: hold for offsite"]
}
```

`fetched_at` is informational only — the loader does not consult it. Reserved
for a possible future "(stale)" hint. The timestamp is wall-clock UTC
(serialized with `+00:00`) so it round-trips unambiguously across timezones.

The cache always reflects the most recent partial-or-full success. On a full
failure (every URL raised), the cache is read verbatim — items from a prior
partial success are returned even if some calendars never yielded data.

## Error handling

The principle stays "degrade gracefully, never trap the user."

| Condition | Behavior |
| --- | --- |
| All URL fetches fail | Read cache; return cached items. If no cache, return `[]`. |
| Some URLs fail, some succeed | Use the successes; cache the partial result. Next block retries the failed ones. |
| Single URL returns malformed iCal | Treat as fetch failure for that URL; continue with the others. |
| `recurring_ical_events` raises on a particular event | Skip that event; keep the rest of the events from that feed. |
| Event has no `SUMMARY` | Skip it. |
| Event has no `DTSTART` | Skip it. |
| `<config_dir>/.cache/google_calendar.json` corrupt | Treat as no cache; return `[]`. |
| `urls` list empty | Return `[]` immediately, without network. |
| Fetch hangs | 10-second timeout per URL; counts as failure for that URL. |

**No retries inside `today()`.** A failed fetch this block is retried
naturally by the next block (45 min later). Adding retries inside one call
just delays block rendering.

**Logging.** A single warning per failure via
`logging.getLogger("totems.duty_sources.google_calendar")`. Uses the
stdlib `logging` module — no new infrastructure.

## Testing

### Test seams

`GoogleCalendarDutySource(urls, cache_path, *, fetcher=..., now=...)`. Tests
inject a fake `fetcher` that returns canned iCal bytes and a fake `now` that
returns a fixed `datetime` in a known timezone.

### Fixtures

A small `_fixtures` helper exposing three iCal builders as Python string
literals:

- `single_timed_event(title, start)`
- `single_all_day_event(title, date)`
- `weekly_recurring_event(title, start, weekday)`

Tests compose these.

### Coverage (unit)

- **Parse + format**
  - Timed event → `"09:00 standup"` (leading zero, 24h, local TZ).
  - All-day event → `"all day: vacation"`.
  - UTC `DTSTART` correctly converted to a known local TZ.
- **Today filter:** yesterday's and tomorrow's events excluded.
- **Recurring:** weekly event included on its weekday, excluded on others.
- **Sort:** all-day first, then timed ascending.
- **Skip rules:** events without `SUMMARY` skipped; events without `DTSTART`
  skipped.
- **Multi-URL:** events from two URLs concatenated; identical formatted
  strings deduped.
- **Empty `urls` list:** `today()` returns `[]` and `fetcher` is never
  called.
- **Cache write on success:** successful fetch writes JSON to `cache_path`.
- **Cache read on full failure:** all fetchers raise → returns cached items.
- **Cache corrupt:** invalid JSON in cache → treated as no cache, returns
  `[]`.
- **Partial failure:** one URL raises, one succeeds → returns the success
  items, caches them.
- **Bad VEVENT survives:** one malformed event inside a feed is skipped, the
  rest kept.

### Coverage (config)

Extensions to existing `tests/test_config.py`:

- `kinds = ["textfile"]` parses correctly.
- Legacy `kind = "textfile"` still parses (compat path).
- Unknown kind raises `ConfigError` at `load_config` time.
- `urls` missing when `"google_calendar"` is in `kinds` raises `ConfigError`.
- `urls` accepts an empty list.

### Settings editor

Existing GUI smoke-test pattern — runs only under `$DISPLAY`. Verify the new
"Google Calendar URLs" section renders, accepts text, and triggers
autosave.

### Dev affordance

A new CLI flag `--debug-calendar` that:

1. Loads the current config.
2. Builds a `GoogleCalendarDutySource` from the configured URLs.
3. Calls `today()` once.
4. Prints the resulting list to stdout, one item per line.
5. Exits with status 0 on success, non-zero on full failure.

Mirrors `--debug-now` and `--fast`. No automated test for the flag itself —
it's a manual sanity-check.

## Documentation

The README gets a short "Project Totems" heading explaining the working
name and linking to the Inception totem reference:
[Totem (Inception wiki)](https://inception.fandom.com/wiki/Totem). The
metaphor: the whole block window — quote, wisdom, today, totem symbol, ritual phrase
— is the user's totem; checking it grounds you back in waking life.

A bullet under "Config files" calls out the new `[duty_source.google_calendar]`
sub-table with an example URL.

## Out of scope (this round)

- OAuth-based Google Calendar API access.
- Writing to the calendar (creating / updating events).
- Calendar selection UI within a Google account (we read whatever URL the
  user pastes).
- Stale-cache visual indicator on the block window — design leaves room
  via `fetched_at`, but no UI thread for it now.
- Renaming `duties` to `totems` everywhere — discussed and explicitly
  deferred. "Project Totems" is the working name for this feature; code
  identifiers stay neutral.
- Per-event metadata (location, attendees, description). The bullet line
  is the only surface.
