# totems — Design

**Date:** 2026-04-27
**Status:** approved (brainstorm)

## Purpose

A small Python desktop app that interrupts you every 45 minutes of wall-clock time with a 5-minute "soft block" — an always-on-top window showing a quote, a few wisdom reminders, today's agenda, and a totem symbol. You can end the block early by typing a ritual phrase you set yourself.

The goal is to make screen-time pauses *deliberate*: easy to honor, friction-y to skip.

## Decisions

| Decision | Choice |
| --- | --- |
| Block style | **Soft** — always-on-top window, user can step around it |
| Timer | **Wall clock** — every 45 min real time triggers a block |
| Cycle on early unlock | **Reset** — typing the phrase ends the block and starts a fresh 45 min |
| Quote / wisdom source | **Bundled defaults + user files**, merged & deduped |
| Totem symbol source | **Local folder first**, fall back to `cataas.com`, hide panel if both fail |
| Skip mechanism | **Ritual phrase** — long sentence, set once, plaintext in config |
| Duty source (today's agenda) | **Pluggable** — v1 reads a plain text file; Google Calendar source planned later |
| Lifecycle | **Manual launch** (`uv run`) on X11 with stdlib tkinter |
| Window | **Fixed 700×450, centered** on the primary monitor; close button disabled |
| Layout | **Side-by-side** — totem symbol on left; quote header + wisdom + today on right; phrase input across the bottom |

## Architecture

Five small modules, one entrypoint. Each piece talks to the next through dataclass interfaces, so the scheduler doesn't know about file paths and the window doesn't know about HTTP.

**Module boundary in one line:** the scheduler decides *when*, content/totem_symbols decide *what*, the block window decides *how it looks*, config decides *what's allowed*.

### Modules

- **`scheduler`** — main loop. `sleep(work_minutes) → trigger_block() → wait_for_unlock_or(block_minutes) → repeat`. Uses `time.monotonic` and `time.sleep` (both injected for testability) — chosen specifically because `time.sleep` pauses with the system across suspend/resume, which is the behavior we want. On early unlock, the next work timer starts fresh.
- **`content`** — three loaders:
  - `quotes`: bundled defaults + `~/.config/totems/quotes.txt`, merged, deduped, random pick of one.
  - `wisdom_reminders`: same pattern; random pick of 1–3.
  - `duties`: delegates to the configured `DutySource`.
- **`duty_sources/`** — small package:
  - `DutySource` protocol: `today() -> list[str]`.
  - v1 impl: `TextFileDutySource` reading `~/.config/totems/duties.txt` (one item per line; blank lines and `#` comments stripped).
  - Future impl slot: `GoogleCalendarDutySource`.
- **`totem_symbols`** — returns `Path | None` for one totem symbol: tries `~/.config/totems/totem_symbols/` first (filtered to `.jpg .jpeg .png .gif .webp`); if empty, fetches from `cataas.com` and writes the bytes to `~/.config/totems/totem_symbols/.cache/` so the return type stays a `Path`; if both fail, returns `None`.
- **`block_window`** — tkinter `Toplevel`, always-on-top, 700×450 centered on primary monitor, side-by-side layout. Close button disabled (`WM_DELETE_WINDOW` no-op). Returns when the user types the ritual phrase or the 15-min timer fires.
- **`config`** — reads/writes `~/.config/totems/config.toml`. First run prompts in the terminal for the ritual phrase and writes the file.

### Data shape

```python
@dataclass
class BlockContent:
    quote: str
    wisdom: list[str]      # 1-3 items
    duties: list[str]      # whatever the source returns; possibly empty
    symbol_path: Path | None  # None → UI hides the totem symbol panel
```

### Visual layout (chosen: B — side-by-side)

```
+---------------------------------------------------+
|                          14:32 remaining          |
|  +----------+  +-------------------------------+  |
|  |          |  |  "The cure for boredom is     |  |
|  |  symbol  |  |   curiosity. There is no      |  |
|  |  image   |  |   cure for curiosity."        |  |
|  |          |  |                               |  |
|  |          |  |  Wisdom                       |  |
|  |          |  |  · drink water                |  |
|  |          |  |  · look at something far away |  |
|  |          |  |                               |  |
|  |          |  |  Today                        |  |
|  |          |  |  · 3pm dentist                |  |
|  |          |  |  · prep slides for review     |  |
|  +----------+  +-------------------------------+  |
|  [ type your ritual phrase…                    ]  |
+---------------------------------------------------+
```

When `symbol_path` is `None`, the right column expands to fill. When `duties` is empty, the *Today* section doesn't render.

## Files & on-disk layout

User config (XDG-compliant, falls back to `$HOME/.config/totems/`):

```
~/.config/totems/
├── config.toml        # ritual phrase, intervals, duty source choice
├── quotes.txt         # one quote per line; merged with built-ins
├── wisdom.txt         # one wisdom reminder per line; merged with built-ins
├── duties.txt         # today's agenda — one item per line
└── totem_symbols/              # local symbol images; empty → cataas.com fallback
```

Bundled defaults ship inside the package as `totems/defaults/quotes.txt` and `totems/defaults/wisdom.txt` — small starter lists.

### `config.toml`

```toml
ritual_phrase = "I am choosing to skip my break right now."

[timing]
work_minutes = 45
block_minutes = 5

[duty_source]
kind = "textfile"     # future: "google_calendar"
```

**Phrase storage** — plaintext, not hashed. This is friction, not security; if you forget the phrase, opening the file to remind yourself is itself a small ritual penalty for skipping.

**First-run UX** — if `config.toml` is missing, the terminal prints a one-time prompt asking for the ritual phrase via `input()`, writes the file, then starts the loop. Blocking-`input()` is fine because v1's lifecycle is "manual launch from a terminal" — if we later add a desktop launcher, first-run will need a different surface (e.g., a small tk dialog).

## Error handling & edge cases

The principle: **degrade gracefully, never trap the user.**

| Condition | Behavior |
| --- | --- |
| `cataas.com` unreachable AND `totem_symbols/` empty | Totem symbol panel hides; quote + reminders still show |
| `duties.txt` missing / empty / unreadable | *Today* section doesn't render |
| No quotes available at all | Single hardcoded last-resort quote |
| `config.toml` malformed | Exit with a clear message pointing at the bad line — never silently fall back |
| Ritual phrase missing on startup | Re-run first-run prompt |
| `totem_symbols/` contains non-image files | Filter by extension, ignore the rest silently |
| System suspend during the 45-min wait | `time.sleep` pauses with the system; timer naturally extends across suspend |

**Window close behavior:** the WM close button is disabled. The only ways out of a block are typing the ritual phrase or waiting 5 min. The literal escape hatch is `Ctrl-C` on the terminal running the app — that's the user's "right to stop." A one-click X button bypass would gut the whole point.

## Testing

Framework: **pytest** (`uv add --dev pytest`).

### Unit-tested

- **`content`** — merge/dedup logic given strings (not paths); random pick is deterministic when given a seeded `random.Random`.
- **`duty_sources.TextFileDutySource`** — parses `duties.txt`; missing file returns `[]`; blank lines and `#`-comments stripped.
- **`totem_symbols`** — extension filtering; deterministic random pick with a seeded RNG; HTTP fallback tested with a stub `urlopen` (no real network).
- **`config`** — parses valid TOML; raises a clear error on malformed input; round-trips a generated default file.

### Scheduler — by dependency injection

```python
def run(self, sleep=time.sleep, now=time.monotonic): ...
```

Tests pass a fake `sleep` that records calls and a fake `now` that advances on demand. Assert the sequence:
`sleep(45*60) → trigger_block() → wait_for_unlock_or(15*60) → sleep(45*60) → …`. No real waiting.

### Block window — smoke-tested only

- One "renders without crashing" test: constructs a `BlockWindow` with mock `BlockContent`, iterates the mainloop once, destroys it. Catches import/wiring breakage.
- Real visual testing is manual via dev CLI flags:
  - `--debug-now` — triggers a block immediately on startup so you see the layout in seconds.
  - `--fast` — uses 5-second intervals instead of minutes for end-to-end smoke runs.

### Explicitly not tested

tkinter rendering, real `cataas.com` calls, real wall-clock timing. Those are integration concerns covered by manual testing with the debug flags.

## Out of scope (v1)

- Google Calendar integration (designed for, not built — `DutySource` protocol is the seam).
- Tray icon, autostart, multi-monitor handling, Wayland support.
- Hashed phrase / phrase rotation / per-block challenges.
- Active-time idle detection — explicitly chose wall-clock simplicity.
- Stats / history / "you skipped N today" tracking.
- GUI configuration; everything is files.
