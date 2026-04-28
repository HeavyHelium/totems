# totems handoff

This repo contains the completed totems implementation plus post-plan
UX/content improvements and the completed "Project Totems" Google Calendar
duty-source feature. Work has continued directly on `main`, as the user
explicitly allowed.

## Active project: Project Totems — Google Calendar duty source

**Status:** spec ✅, plan ✅, implementation ✅.

**Working name:** "Project Totems" — the metaphor is that the whole block
window (quote, wisdom, today, totem symbol, ritual phrase) is the user's totem in
the *Inception* sense. Code identifiers stay neutral; the rename of
`duties` → `totems` was explicitly deferred.

**Spec:** `docs/superpowers/specs/2026-04-28-project-totems-google-calendar-design.md`
**Plan:** `docs/superpowers/plans/2026-04-28-project-totems-google-calendar.md`

Both passed their reviewer loops on the first pass with small advisory
folds applied.

### Decisions baked into the spec/plan (don't re-litigate)

- Connection method: **private iCal URLs** (per-calendar "secret address"
  Google exposes). No OAuth.
- Recurring events: **supported** via two new pure-Python runtime deps,
  `icalendar` and `recurring-ical-events`. **This is the explicit
  loosening of the previous "stdlib-only" constraint — only for this
  feature.**
- Refresh cadence: per block (every ~45 min). No retries inside `today()`.
- Multi-calendar: `urls` is a list. Multi-source: `kinds` becomes a list
  in `config.toml` (back-compat to the old `kind = "..."` form).
- Fetch failure: **stale-cache fallback** at
  `~/.config/totems/.cache/google_calendar.json`.
- Coexistence: textfile + google_calendar can both be active.
- Display: `09:00 standup` (24h, leading zero, local TZ),
  `all day: vacation`. All-day first, then timed ascending,
  per-URL sort + concatenate, deduped by formatted string.
- Settings UI: any URLs in the field → `google_calendar` is in `kinds`;
  zero URLs → it's removed. URLs *are* the toggle.
- Out of scope: OAuth, write access, calendar selection UI,
  stale-indicator UI, the `duties` → `totems` rename.

### Implemented tasks

1. **Task 1 — Config schema + factory shape.** `Config.duty_source_kind:
   str` becomes `duty_source_kinds: tuple[str, ...]`; new
   `google_calendar_urls: tuple[str, ...]`. Factory becomes
   `make_duty_sources(cfg, *, config_dir) -> list[DutySource]`. Entrypoint
   loops + concatenates.
2. **Task 2 — Pure iCal extraction helper.** `extract_today_items(bytes,
   *, now) -> list[str]`. No I/O. Three iCal fixture builders in
   `tests/duty_sources/_fixtures.py` (timed, all-day, weekly recurring).
   Adds the two runtime deps.
3. **Task 3 — `GoogleCalendarDutySource` class.** Wraps the helper with
   fetcher injection, cache, multi-URL, partial-failure semantics. Wires
   into `make_duty_sources` and drops `NotImplementedError` from the
   entrypoint's except-tuple.
4. **Task 4 — Settings editor URLs section.** Multiline text editor,
   debounced autosave, "URLs are the toggle" semantics for the kinds
   list. **Update both the explicit-save and the autosave call sites,
   not just one.**
5. **Task 5 — `--debug-calendar` CLI flag.** Prints today's calendar
   items and exits.
6. **Task 6 — README.** Add a "Project Totems" section with a metaphor
   blurb linking to https://inception.fandom.com/wiki/Totem; document
   the new `[duty_source.google_calendar]` config and the `.cache/`
   layout.

### Project Totems commits

- `30eb3bb` Switch duty sources to list config
- `6329047` Add iCal extraction helper
- `5543f8c` Add Google Calendar duty source
- `85802d0` Add Google Calendar URLs settings editor
- `3219c89` Add debug calendar CLI flag
- `a64309a` Document Project Totems calendar setup
- `0d7a677` Preserve duty source order in settings toggle

Final local whole-feature review found and fixed one important issue:
the settings URL toggle now preserves existing duty-source order instead of
moving `google_calendar` to the end on save.

---

## Background: completed totems (the existing app)

- Branch: `main`
- Latest implementation commit before Project Totems: `d24790c`
  (`Autosave settings editor changes`)
- Latest commit overall: `0d7a677`
- Status: app is implemented and runs.
- Current test status: `uv run pytest` -> `105 passed`

## What the app does

A Python/tkinter desktop app that interrupts the user on a wall-clock schedule.
It shows a fullscreen, always-on-top pause window with:

- a totem symbol panel
- a quote card
- a wisdom card
- a Today / duties card
- a ritual phrase entry
- a countdown timer

The block ends only when the configured ritual phrase is typed exactly or when
the block timer expires. The window is fullscreen, topmost, and reclaims focus
with throttling. It is still not a true OS/window-manager lock; `Ctrl-C` in the
terminal remains the hard escape hatch.

## How to run

```sh
uv run totems
uv run totems --debug-now
uv run totems --debug-calendar
uv run totems --fast
uv run totems --settings
```

Use `--settings` for normal configuration/content editing.
Use `--debug-calendar` to fetch configured Google Calendar URLs once and
print today's items without opening the block window.

## User files

Main config dir:

```text
~/.config/totems/
├── config.toml
├── content.json
├── quotes.txt
├── wisdom.txt
├── duties.txt
├── totem_symbols/
└── .cache/
    └── google_calendar.json
```

`content.json` is now the preferred content pool format. If it exists, it is
used for quotes, wisdom, and duties. The legacy text files still work as
fallback. The settings editor writes `content.json`.

Supported `content.json` shape:

```json
{
  "quotes": ["..."],
  "wisdom": ["..."],
  "duties": ["..."]
}
```

Each array item can contain real newline characters; the settings editor lets
users type those directly as multiline records. Users do not need to hand-edit
JSON escapes like `\n`.

## Config behavior

`config.toml` includes:

```toml
ritual_phrase = "..."

[timing]
work_minutes = 45
block_minutes = 5

[duty_source]
kinds = ["textfile"]

[duty_source.google_calendar]
urls = []

[content]
mode = "merge"
```

Back-compat remains: old `[duty_source] kind = "textfile"` configs still load.
For Google Calendar, paste private iCal URLs in the settings editor or set:

```toml
[duty_source]
kinds = ["textfile", "google_calendar"]

[duty_source.google_calendar]
urls = [
    "https://calendar.google.com/calendar/ical/.../basic.ics",
]
```

`[content].mode` can be:

- `merge`: bundled defaults + user pools
- `replace`: user pools replace bundled defaults

Validation rejects empty ritual phrases, non-positive/non-integer timings, and
unknown content modes.

## Major implementation commits

Original plan tasks:

- `9a81324` Bootstrap package + pytest
- `408e08d` / `f1080c6` Config module + TOML escaping
- `fccc26f` Content module
- `efeb0d6` DutySource textfile module
- `ea80df7` Cats module
- `348f090` Scheduler
- `8048a96` BlockWindow
- `37987aa` Entrypoint
- `bf0dde3` README

Important post-plan fixes/features:

- `c1cb148` Handle cat cache write failures gracefully
- `de7473c` Validate cat fallback response type
- `3caa9a4` Handle entrypoint config errors before scheduling
- `aff2bb3` Tighten config validation and cat GIF fallback
- `85c68a0` Reject non-integer timing config values
- `313abb2` Refresh block window visual design
- `fdf6e8c` Throttle block window focus reclaim
- `57b6a52` Make block window fullscreen
- `8a9c55a` Keep block content visible in fullscreen
- `b4a2853` Split block window content into visual sections
- `8320c42` Outline faults and antidotes wisdom defaults
- `6ed766e` Allow user content pools to replace defaults
- `533fe9e` Add JSON content pool support
- `387a7d4` Add graphical settings editor
- `af01fdf` Use record editors in settings UI
- `d24790c` Autosave settings editor changes

## Current UI/content notes

- Block window is fullscreen and sectioned into separate visual cards.
- Totem symbol source is local `.png`/`.gif` first, then cataas GIF fallback.
- Wisdom and duties text has been enlarged for readability.
- Bundled wisdom includes a web-checked five faults / eight antidotes outline.
- Settings UI autosaves after edits, debounced at about 800 ms.
- Invalid intermediate settings do not overwrite files; the UI status reports
  autosave pause/errors.
- Settings UI includes a "Google Calendar URLs" section. Any URLs in that
  field enable the `google_calendar` source; clearing it removes that source.
- Google Calendar source fetches private iCal URLs per block, supports weekly
  recurrence and all-day events, dedupes by formatted text, and falls back to
  `.cache/google_calendar.json` when every fetch fails.

## Tests

Run:

```sh
uv run pytest
```

GUI smoke tests require `$DISPLAY`; otherwise they skip.

## Untracked files

At this handoff, these are still untracked:

- `.python-version`
- `AGENTS.md`
- `uv.lock`

`AGENTS.md` has been updated as a handoff file but was never tracked in the
original repo. `uv.lock` was generated by `uv`; ask before deciding whether to
commit it.

## Development constraints

- Keep runtime dependencies stdlib-only unless the user explicitly changes
  that constraint. **Project Totems is one such explicit change: it adds
  `icalendar` and `recurring-ical-events`** (both pure-Python). Do not
  add other runtime deps without asking.
- Do not add Pillow; image support is intentionally PNG/GIF via tkinter.
- Do not switch off `main` unless the user asks.
- Preserve the terminal `Ctrl-C` escape hatch.
- Avoid true global keyboard/mouse grabs unless the user explicitly accepts the
  window-manager-specific risks.
