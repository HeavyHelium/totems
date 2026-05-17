import pytest

from totems.config import BlockPalette, Config, ConfigError
from totems.settings_window import (
    SettingsState,
    duty_source_kinds_for_google_urls,
    editor_text_to_items,
    google_urls_text_to_tuple,
    items_to_editor_text,
    load_settings_state,
    save_settings_state,
)


def test_editor_text_uses_blank_lines_between_items():
    text = "First line\nstill first\n\nSecond item\n\n\nThird item\n"
    assert editor_text_to_items(text) == ["First line\nstill first", "Second item", "Third item"]


def test_items_to_editor_text_round_trips_multiline_items():
    items = ["First line\nstill first", "Second item"]
    assert editor_text_to_items(items_to_editor_text(items)) == items


def test_google_urls_text_to_tuple_strips_blanks():
    text = "\n https://example.com/a.ics \n\nhttps://example.com/b.ics\n"
    assert google_urls_text_to_tuple(text) == (
        "https://example.com/a.ics",
        "https://example.com/b.ics",
    )


def test_duty_source_kinds_for_google_urls_treats_urls_as_toggle():
    assert duty_source_kinds_for_google_urls(("textfile",), ("https://example.com/a.ics",)) == (
        "textfile",
        "google_calendar",
    )
    assert duty_source_kinds_for_google_urls(("google_calendar", "textfile"), ("url",)) == (
        "google_calendar",
        "textfile",
    )
    assert duty_source_kinds_for_google_urls(("textfile", "google_calendar"), ()) == ("textfile",)
    assert duty_source_kinds_for_google_urls(("google_calendar",), ()) == ("textfile",)


def test_save_settings_state_writes_config_and_content_json(tmp_path):
    state = SettingsState(
        config=Config(
            ritual_phrase="phrase",
            work_minutes=20,
            block_minutes=5,
            duty_source_kinds=("textfile", "google_calendar"),
            google_calendar_urls=("https://example.com/cal.ics",),
            timebox_duties=True,
            timebox_phrase="begin",
            timebox_lead_minutes=4,
            timebox_reminder_seconds=15,
            content_mode="replace",
            block_palette=BlockPalette(quote="#111111", today="#222222"),
        ),
        quotes=["Q1\nQ1 continuation", "Q2"],
        wisdom=["W"],
        duties=["D"],
    )

    save_settings_state(tmp_path, state)
    loaded = load_settings_state(tmp_path)

    assert loaded.config.ritual_phrase == "phrase"
    assert loaded.config.work_minutes == 20
    assert loaded.config.block_minutes == 5
    assert loaded.config.duty_source_kinds == ("textfile", "google_calendar")
    assert loaded.config.google_calendar_urls == ("https://example.com/cal.ics",)
    assert loaded.config.timebox_duties is True
    assert loaded.config.timebox_phrase == "begin"
    assert loaded.config.timebox_lead_minutes == 4
    assert loaded.config.timebox_reminder_seconds == 15
    assert loaded.config.content_mode == "replace"
    assert loaded.config.block_palette.quote == "#111111"
    assert loaded.config.block_palette.today == "#222222"
    assert loaded.quotes == ["Q1\nQ1 continuation", "Q2"]
    assert loaded.wisdom == ["W"]
    assert loaded.duties == ["D"]


def test_save_settings_state_rejects_empty_phrase(tmp_path):
    state = SettingsState(
        config=Config(ritual_phrase=""),
        quotes=[],
        wisdom=[],
        duties=[],
    )

    try:
        save_settings_state(tmp_path, state)
    except Exception as e:
        assert "ritual phrase" in str(e)
    else:
        raise AssertionError("expected validation error")


def test_save_settings_state_rejects_invalid_palette_color(tmp_path):
    state = SettingsState(
        config=Config(ritual_phrase="phrase", block_palette=BlockPalette(quote="red")),
        quotes=[],
        wisdom=[],
        duties=[],
    )

    with pytest.raises(ConfigError, match="colors.quote"):
        save_settings_state(tmp_path, state)


def test_settings_editor_collect_state_writes_google_urls(tmp_path, monkeypatch):
    import os

    if not os.environ.get("DISPLAY"):
        pytest.skip("needs an X display")

    from totems.config import load_config
    from totems.settings_window import SettingsEditor

    state = SettingsState(
        config=Config(ritual_phrase="phrase"),
        quotes=[],
        wisdom=[],
        duties=[],
    )
    editor = SettingsEditor(config_dir=tmp_path, state=state)
    editor._google_urls_text.insert("1.0", "https://example.com/a.ics\nhttps://example.com/b.ics\n")
    editor._timebox_duties.set(True)
    editor._timebox_phrase.delete(0, "end")
    editor._timebox_phrase.insert(0, "begin")
    editor._timebox_lead.delete(0, "end")
    editor._timebox_lead.insert(0, "4")
    editor._timebox_reminder.delete(0, "end")
    editor._timebox_reminder.insert(0, "15")
    editor._color_entries["quote"].delete(0, "end")
    editor._color_entries["quote"].insert(0, "#111111")
    editor._save()
    editor.root.destroy()

    saved = load_config(tmp_path / "config.toml")
    assert saved.google_calendar_urls == (
        "https://example.com/a.ics",
        "https://example.com/b.ics",
    )
    assert saved.duty_source_kinds == ("textfile", "google_calendar")
    assert saved.timebox_duties is True
    assert saved.timebox_phrase == "begin"
    assert saved.timebox_lead_minutes == 4
    assert saved.timebox_reminder_seconds == 15
    assert saved.block_palette.quote == "#111111"


def test_color_labels_cover_all_palette_keys():
    from totems.config import BLOCK_PALETTE_KEYS
    from totems.settings_window import COLOR_LABELS

    assert set(COLOR_LABELS) == set(BLOCK_PALETTE_KEYS)
