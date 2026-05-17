# Per-box Bullet Colors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single `bullet_marker` palette color with two per-box colors — `wisdom_bullet` and `today_bullet` — defaulting to the swapped ("crossed") box colors, surfaced in both settings UIs.

**Architecture:** The block-window palette is a frozen dataclass (`BlockPalette`) keyed by the `BLOCK_PALETTE_KEYS` tuple. Both settings UIs render color editors by iterating that tuple, so adding/removing keys propagates automatically. The block window draws bullet markers via `BlockWindow._bullet`, which already accepts an unused `marker_bg` argument. Work is: split the config key, feed per-box colors to `_bullet`, update the web preview, fix tests and docs.

**Tech Stack:** Python 3.12, `dataclasses`, `tomllib`, Tkinter, stdlib `http.server`, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-05-17-per-box-bullet-colors-design.md`

**Conventions:**
- Run tests with `uv run pytest`.
- GUI smoke tests need `$DISPLAY`; this environment has one (`:1`), so they run rather than skip.
- Commit messages: imperative summary; end with the `Co-Authored-By` trailer used in this repo's recent history.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `src/totems/config.py` | Palette keys, `BlockPalette` dataclass, parser | Modify |
| `src/totems/block_window.py` | Renders bullet markers per box | Modify |
| `src/totems/settings_window.py` | Tk color editor labels | Modify |
| `src/totems/settings_web.py` | Web color inputs + live preview | Modify |
| `tests/test_config.py` | Config parsing tests | Modify |
| `tests/test_block_window_smoke.py` | Block window render tests | Modify |
| `tests/test_settings_window.py` | Tk settings tests | Modify (add one test) |
| `tests/test_settings_web.py` | Web settings tests | Modify (add asserts) |
| `README.md` | `[colors]` example block | Modify |

---

## Task 1: Split the palette key in `config.py`

Replace `bullet_marker` with `wisdom_bullet` + `today_bullet`, crossed defaults, and silently skip the legacy key when parsing.

**Files:**
- Modify: `src/totems/config.py` (lines 12-21, 41-52, ~196-202)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`. First add `DEFAULT_BLOCK_PALETTE` to the existing import from `totems.config`:

```python
from totems.config import (
    DEFAULT_BLOCK_PALETTE,
    BlockPalette,
    Config,
    ConfigError,
    load_config,
    write_config,
    write_default_config,
    user_config_dir,
)
```

Then append these tests at the end of the file:

```python
def test_default_block_palette_bullets_are_crossed():
    palette = DEFAULT_BLOCK_PALETTE
    assert palette.wisdom_bullet == palette.today
    assert palette.today_bullet == palette.wisdom


def test_load_config_ignores_legacy_bullet_marker_key(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "phrase"\n[colors]\nbullet_marker = "#123456"\n'
    )
    cfg = load_config(p)
    assert cfg.block_palette.wisdom_bullet == "#f9dfca"
    assert cfg.block_palette.today_bullet == "#e4f0df"


def test_load_config_parses_per_box_bullet_colors(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "phrase"\n'
        "[colors]\n"
        'wisdom_bullet = "#AAAAAA"\n'
        'today_bullet = "#BBBBBB"\n'
    )
    cfg = load_config(p)
    assert cfg.block_palette.wisdom_bullet == "#aaaaaa"
    assert cfg.block_palette.today_bullet == "#bbbbbb"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -k "crossed or bullet" -v`
Expected: FAIL — `test_default_block_palette_bullets_are_crossed` and `test_load_config_parses_per_box_bullet_colors` fail (`BlockPalette` has no `wisdom_bullet`/`today_bullet`); `test_load_config_ignores_legacy_bullet_marker_key` fails with `ConfigError: unknown colors key 'bullet_marker'`.

- [ ] **Step 3: Update `BLOCK_PALETTE_KEYS`**

In `src/totems/config.py`, replace the `BLOCK_PALETTE_KEYS` tuple:

```python
BLOCK_PALETTE_KEYS: tuple[str, ...] = (
    "quote",
    "wisdom",
    "wisdom_bullet",
    "today",
    "today_bullet",
    "ritual",
    "totem_panel",
    "highlight",
    "border",
)
```

- [ ] **Step 4: Update the `BlockPalette` dataclass**

Replace the `BlockPalette` field block:

```python
@dataclass(frozen=True)
class BlockPalette:
    quote: str = "#fff4cf"
    wisdom: str = "#e4f0df"
    wisdom_bullet: str = "#f9dfca"
    today: str = "#f9dfca"
    today_bullet: str = "#e4f0df"
    ritual: str = "#f7efe3"
    totem_panel: str = "#6ca695"
    highlight: str = "#ffe66d"
    border: str = "#e0d2bf"
```

(`bullet_marker` is removed; `wisdom_bullet` defaults to the `today` color and `today_bullet` to the `wisdom` color — the crossed default.)

- [ ] **Step 5: Skip the legacy key in `_parse_block_palette`**

Replace the loop body in `_parse_block_palette`:

```python
def _parse_block_palette(colors: dict[str, object], path: Path | None) -> BlockPalette:
    out = DEFAULT_BLOCK_PALETTE.as_dict()
    for key, value in colors.items():
        if key == "bullet_marker":
            continue  # legacy key, replaced by wisdom_bullet / today_bullet
        if key not in out:
            raise ConfigError(_config_error(path, f"unknown colors key {key!r}"))
        out[key] = _color_value(value, f"colors.{key}", path)
    return BlockPalette(**out)
```

- [ ] **Step 6: Run the full config test file**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS — all tests pass, including the three new ones and the existing `test_load_config_rejects_unknown_block_palette_key` (a non-legacy unknown key still raises) and `test_write_config_emits_kinds_and_google_urls` (round-trip still holds).

- [ ] **Step 7: Commit**

```bash
git add src/totems/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
Split bullet_marker into per-box bullet colors

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Render per-box markers in `block_window.py`

Feed each box's bullet color to `_bullet`, make `marker_bg` required, and name the marker frame so it is testable.

**Files:**
- Modify: `src/totems/block_window.py` (call sites ~195-215, `_bullet` ~316-347)
- Test: `tests/test_block_window_smoke.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_block_window_smoke.py`, first fix the existing `test_custom_palette_reaches_block_window_widgets` — replace the `bullet_marker="#666666",` line inside its `BlockPalette(...)` with:

```python
        wisdom_bullet="#666666",
        today_bullet="#999999",
```

Then add this new test after it, plus the helper:

```python
def _marker_beside(root: tk.Widget, label_text: str) -> tk.Widget:
    label = next(
        widget
        for widget in _walk_widgets(root)
        if str(widget).endswith("bullet_text") and widget.cget("text") == label_text
    )
    return next(
        child
        for child in label.master.winfo_children()
        if str(child).endswith("bullet_marker")
    )


def test_per_box_bullet_colors_reach_markers():
    bc = BlockContent(quote="q", wisdom=["w"], duties=["d"], symbol_path=None)
    palette = BlockPalette(wisdom_bullet="#abcabc", today_bullet="#defdef")
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1, palette=palette)
    win.root.update()

    assert _marker_beside(win.root, "w").cget("bg") == "#abcabc"
    assert _marker_beside(win.root, "d").cget("bg") == "#defdef"
    win.root.destroy()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_block_window_smoke.py -k "per_box or custom_palette" -v`
Expected: FAIL — `test_per_box_bullet_colors_reach_markers` fails because the marker frame is unnamed (`StopIteration`) and `BlockWindow` has no per-box marker wiring; `test_custom_palette_reaches_block_window_widgets` would also fail to construct `BlockPalette` if not for the Step 1 kwarg fix (it should now pass once the call sites are updated).

- [ ] **Step 3: Update the four `_bullet` call sites**

In `src/totems/block_window.py` `_build_ui`, add the `marker_bg` argument to each call.

Wisdom reminders (~line 195):
```python
                self._bullet(
                    wisdom_card,
                    _wrap_paragraphs(w, WISDOM_WRAP_CHARS),
                    bg=self._palette.wisdom,
                    marker_bg=self._palette.wisdom_bullet,
                )
```

Wisdom placeholder (~line 201):
```python
            self._bullet(
                wisdom_card,
                "No reminders listed.",
                bg=self._palette.wisdom,
                marker_bg=self._palette.wisdom_bullet,
            )
```

Today duties (~line 208):
```python
                self._bullet(
                    today_card,
                    d,
                    bg=self._palette.today,
                    marker_bg=self._palette.today_bullet,
                    highlighted=d in self._content.highlighted_duties,
                )
```

Today placeholder (~line 215):
```python
            self._bullet(
                today_card,
                "No agenda items listed.",
                bg=self._palette.today,
                marker_bg=self._palette.today_bullet,
            )
```

- [ ] **Step 4: Update the `_bullet` signature, fallback, and marker name**

Change the `marker_bg` parameter from optional to required and drop the dead `bullet_marker` fallback:

```python
    def _bullet(
        self,
        parent: tk.Frame,
        text: str,
        *,
        bg: str,
        marker_bg: str,
        highlighted: bool = False,
    ) -> None:
```

Replace the `marker_bg = (...)` assignment with:

```python
        marker_bg = self._palette.highlight if highlighted else marker_bg
```

Add `name="bullet_marker"` to the marker `tk.Frame`:

```python
        marker = tk.Frame(
            row,
            name="bullet_marker",
            bg=marker_bg,
            width=22,
            height=18,
            highlightthickness=1,
            highlightbackground=self._palette.border,
            highlightcolor=self._palette.border,
        )
```

- [ ] **Step 5: Run block window tests to verify they pass**

Run: `uv run pytest tests/test_block_window_smoke.py -v`
Expected: PASS — all tests pass, including `test_per_box_bullet_colors_reach_markers`, `test_custom_palette_reaches_block_window_widgets`, and `test_highlighted_duty_uses_highlighter_color` (highlighted duties still override the marker to `highlight`).

- [ ] **Step 6: Commit**

```bash
git add src/totems/block_window.py tests/test_block_window_smoke.py
git commit -m "$(cat <<'EOF'
Draw per-box bullet markers in the block window

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update Tk settings labels

The Tk color editor iterates `BLOCK_PALETTE_KEYS` and looks each key up in `COLOR_LABELS`; a missing entry would raise `KeyError`. Update the label map.

**Files:**
- Modify: `src/totems/settings_window.py` (`COLOR_LABELS`, ~lines 58-67)
- Test: `tests/test_settings_window.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings_window.py`. Add the import if not already present (`COLOR_LABELS` lives in `settings_window`, `BLOCK_PALETTE_KEYS` in `config`):

```python
def test_color_labels_cover_all_palette_keys():
    from totems.config import BLOCK_PALETTE_KEYS
    from totems.settings_window import COLOR_LABELS

    assert set(COLOR_LABELS) == set(BLOCK_PALETTE_KEYS)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_settings_window.py::test_color_labels_cover_all_palette_keys -v`
Expected: FAIL — `COLOR_LABELS` still has `bullet_marker` and lacks `wisdom_bullet`/`today_bullet`, so the sets differ.

- [ ] **Step 3: Update `COLOR_LABELS`**

In `src/totems/settings_window.py`, replace the `COLOR_LABELS` dict:

```python
COLOR_LABELS: dict[str, str] = {
    "quote": "Quote",
    "wisdom": "Wisdom",
    "wisdom_bullet": "Wisdom bullet",
    "today": "Today",
    "today_bullet": "Today bullet",
    "ritual": "Ritual",
    "totem_panel": "Totem panel",
    "highlight": "Highlight",
    "border": "Borders",
}
```

- [ ] **Step 4: Run the settings_window tests to verify they pass**

Run: `uv run pytest tests/test_settings_window.py -v`
Expected: PASS — the new test passes and existing tests are unaffected.

- [ ] **Step 5: Commit**

```bash
git add src/totems/settings_window.py tests/test_settings_window.py
git commit -m "$(cat <<'EOF'
Show per-box bullet colors in Tk settings

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update web settings preview

The web color inputs auto-generate from `BLOCK_PALETTE_KEYS`, so they already include the new keys. The live preview must show a marker in both the Wisdom and Today preview cards, each colored by its own variable.

**Files:**
- Modify: `src/totems/settings_web.py` (`.marker` CSS ~line 312, preview HTML ~lines 385-386, `applyPreview` JS ~line 620)
- Test: `tests/test_settings_web.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings_web.py` (it already imports `SETTINGS_HTML`):

```python
def test_settings_html_has_per_box_bullet_preview_vars():
    assert "--wisdom-bullet" in SETTINGS_HTML
    assert "--today-bullet" in SETTINGS_HTML
    assert "--bullet-marker" not in SETTINGS_HTML
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_settings_web.py::test_settings_html_has_per_box_bullet_preview_vars -v`
Expected: FAIL — `SETTINGS_HTML` still references `--bullet-marker` and not the per-box vars.

- [ ] **Step 3: Update the `.marker` CSS**

In `src/totems/settings_web.py`, replace the `.marker` rule (note the doubled braces — this string is an f-string) with a base rule plus two scoped rules:

```python
    .marker {{ display: inline-block; width: 22px; height: 16px; margin-right: 8px; vertical-align: -2px; border: 1px solid var(--border); }}
    .preview-wisdom .marker {{ background: var(--wisdom-bullet); }}
    .preview-today .marker {{ background: var(--today-bullet); }}
```

- [ ] **Step 4: Add a marker to the Today preview card**

Replace the Today preview card line (~line 386):

```html
          <div class="preview-card preview-today"><span class="marker"></span><span class="highlight">09:00 standup</span></div>
```

- [ ] **Step 5: Update the `applyPreview` JS**

Replace the `--bullet-marker` line (~line 620) with two lines:

```javascript
      preview.style.setProperty("--wisdom-bullet", colors.wisdom_bullet);
      preview.style.setProperty("--today-bullet", colors.today_bullet);
```

- [ ] **Step 6: Run the settings_web tests to verify they pass**

Run: `uv run pytest tests/test_settings_web.py -v`
Expected: PASS — the new test passes and existing tests are unaffected.

- [ ] **Step 7: Commit**

```bash
git add src/totems/settings_web.py tests/test_settings_web.py
git commit -m "$(cat <<'EOF'
Show per-box bullet colors in web settings preview

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update the README `[colors]` example

**Files:**
- Modify: `README.md` (`[colors]` TOML block, ~lines 145-154)

- [ ] **Step 1: Update the example**

In `README.md`, in the `[colors]` TOML block, replace the `bullet_marker` line so the block reads:

```toml
[colors]
quote = "#fff4cf"
wisdom = "#e4f0df"
wisdom_bullet = "#f9dfca"
today = "#f9dfca"
today_bullet = "#e4f0df"
ritual = "#f7efe3"
totem_panel = "#6ca695"
highlight = "#ffe66d"
border = "#e0d2bf"
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest`
Expected: PASS — entire suite green (was `105 passed`; now higher with the added tests). No skips for GUI tests since `$DISPLAY` is set.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
Document per-box bullet colors in README

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Verification Checklist

- [ ] `uv run pytest` is fully green.
- [ ] A `config.toml` with a legacy `bullet_marker` key loads without error.
- [ ] `uv run totems --settings` (Tk) shows "Wisdom bullet" and "Today bullet" color fields.
- [ ] The web settings Colors tab shows `wisdom bullet` / `today bullet` inputs, and the preview shows a marker in both the Wisdom and Today cards that updates live.
- [ ] No remaining references to `bullet_marker` outside the legacy-skip line in `config.py`: `grep -rn bullet_marker src/ tests/ README.md` returns only that one line.
