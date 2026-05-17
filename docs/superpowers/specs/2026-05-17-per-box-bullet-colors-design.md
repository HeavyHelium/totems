# Per-box bullet colors

## Problem

The block window draws a small square marker before every Wisdom reminder and
every Today agenda item. Both markers share a single configurable color,
`bullet_marker` (default `#d9eadf`). There is no way to give the Wisdom box and
the Today box different bullet colors.

We want two bullet colors — one per box — configurable in both settings UIs (Tk
and web). By default the bullet colors are the two box colors *crossed*: the
Wisdom box's bullets take the Today box's color, and the Today box's bullets
take the Wisdom box's color.

## Goal

Replace the single `bullet_marker` palette entry with `wisdom_bullet` and
`today_bullet`, defaulting to the swapped box colors, and surface both in the Tk
and web settings color editors.

## Design

### Config (`src/totems/config.py`)

- `BLOCK_PALETTE_KEYS`: remove `bullet_marker`; add `wisdom_bullet` and
  `today_bullet`, each placed immediately after its box key so the settings
  color grid groups them naturally:

  ```
  ("quote", "wisdom", "wisdom_bullet", "today", "today_bullet",
   "ritual", "totem_panel", "highlight", "border")
  ```

- `BlockPalette` dataclass: drop the `bullet_marker` field; add

  ```python
  wisdom_bullet: str = "#f9dfca"   # crossed default: the Today box color
  today_bullet: str = "#e4f0df"    # crossed default: the Wisdom box color
  ```

  The defaults are the literal `today` and `wisdom` box defaults swapped. They
  are independent config values initialized to these defaults — they do not
  track later edits to the box colors.

- `_parse_block_palette`: when a parsed `[colors]` key is not a known palette
  key, the parser currently raises `ConfigError`. Add a single exception — the
  legacy key `bullet_marker` is silently skipped (not validated, not stored)
  instead of raising. Any other unknown key still raises. This lets existing
  `config.toml` files that still contain `bullet_marker` load without error;
  the key is dropped the next time settings are saved.

- `write_config` already serializes `[colors]` from
  `parse_block_palette_values(cfg.block_palette.as_dict())`, so it picks up the
  new keys and stops writing `bullet_marker` with no further change.

### Block window (`src/totems/block_window.py`)

- `_bullet` already accepts a `marker_bg: str | None = None` keyword that no
  caller currently passes. Make it a required keyword argument and remove the
  now-dead `or self._palette.bullet_marker` fallback. The marker background
  becomes:

  ```python
  marker_bg = self._palette.highlight if highlighted else marker_bg
  ```

- Update the four `_bullet` call sites in `_build_ui`:
  - Wisdom reminders and the "No reminders listed." placeholder pass
    `marker_bg=self._palette.wisdom_bullet`.
  - Today duties and the "No agenda items listed." placeholder pass
    `marker_bg=self._palette.today_bullet`.

- Highlighted duties keep overriding the marker to `self._palette.highlight` —
  unchanged.

### Tk settings (`src/totems/settings_window.py`)

- `COLOR_LABELS`: remove `"bullet_marker": "Bullet marker"`; add
  `"wisdom_bullet": "Wisdom bullet"` and `"today_bullet": "Today bullet"`.

- `_color_editor` iterates `BLOCK_PALETTE_KEYS` to build the grid, so it picks
  up the two new keys automatically. The grid lays out at four columns per row
  (`index // 4`, `index % 4`); nine keys produce rows of 4, 4, 1 — no layout
  change needed.

### Web settings (`src/totems/settings_web.py`)

- `COLOR_INPUTS_HTML` iterates `BLOCK_PALETTE_KEYS`, so the two new color
  inputs appear automatically. Labels are derived as `key.replace("_", " ")` —
  "wisdom bullet" and "today bullet". The `.colors` grid is four columns; nine
  fields wrap cleanly.

- Preview: the Today preview card currently shows only a highlighted span. Add
  a bullet marker to it so both bullet colors are visible. Scope the marker
  color by parent card rather than a single shared `--bullet-marker` var:

  ```css
  .preview-wisdom .marker { background: var(--wisdom-bullet); }
  .preview-today  .marker { background: var(--today-bullet); }
  ```

  The shared `.marker` rule keeps the size/border styling. The Today preview
  card markup becomes `<span class="marker"></span><span class="highlight">09:00
  standup</span>`.

- The preview JS sets CSS custom properties from the form. Replace the single
  `preview.style.setProperty("--bullet-marker", colors.bullet_marker)` line with

  ```js
  preview.style.setProperty("--wisdom-bullet", colors.wisdom_bullet);
  preview.style.setProperty("--today-bullet", colors.today_bullet);
  ```

### Tests (`tests/`)

- `test_block_window_smoke.py` constructs `BlockPalette(bullet_marker="#666666")`
  — update to the new keys.
- Check `test_config.py`, `test_settings_window.py`, `test_settings_web.py` for
  `bullet_marker` references and update.
- New coverage:
  - A `config.toml` containing a legacy `bullet_marker` key loads without
    error and yields the default `wisdom_bullet` / `today_bullet`.
  - `DEFAULT_BLOCK_PALETTE.wisdom_bullet == DEFAULT_BLOCK_PALETTE.today` and
    `today_bullet == wisdom` (the crossed default).
  - A block window built with distinct `wisdom_bullet` / `today_bullet` colors
    renders each box's marker with its own color.

### Docs (`README.md`)

- The `[colors]` example block lists `bullet_marker = "#d9eadf"`. Replace with
  `wisdom_bullet` and `today_bullet` at their crossed defaults.

## Non-goals

- No migration of a *customized* legacy `bullet_marker` value into the new
  keys — it is dropped, and the crossed defaults apply (per user decision).
- Bullet colors do not auto-follow later box-color edits; they are plain
  independent palette values.
- No new bullet color for any box other than Wisdom and Today (the quote and
  ritual cards have no bullets).
