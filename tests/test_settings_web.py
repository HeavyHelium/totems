import socket
import signal

import pytest

from totems.config import BlockPalette, Config, ConfigError
from totems.settings_window import SettingsState
from totems.settings_web import (
    SETTINGS_HTML,
    _install_shutdown_signal_handlers,
    _raise_keyboard_interrupt,
    _restore_signal_handlers,
    make_settings_server,
    payload_to_state,
    state_to_payload,
)


def test_settings_html_uses_tabs_and_record_editors():
    assert 'data-tab="content"' in SETTINGS_HTML
    assert 'data-panel="content"' in SETTINGS_HTML
    assert 'data-content-tab="quotes"' in SETTINGS_HTML
    assert 'data-content-panel="quotes"' in SETTINGS_HTML
    assert 'data-content-tab="wisdom"' in SETTINGS_HTML
    assert 'data-content-panel="wisdom"' in SETTINGS_HTML
    assert 'data-content-tab="duties"' in SETTINGS_HTML
    assert 'data-content-panel="duties"' in SETTINGS_HTML
    assert "--quote-tab" in SETTINGS_HTML
    assert "--wisdom-tab" in SETTINGS_HTML
    assert "--duties-tab" in SETTINGS_HTML
    assert 'data-record-editor="quotes"' in SETTINGS_HTML
    assert 'data-record-editor="wisdom"' in SETTINGS_HTML
    assert 'data-record-editor="duties"' in SETTINGS_HTML
    assert 'aria-label="Add record"' in SETTINGS_HTML
    assert 'title="Add record">+</button>' in SETTINGS_HTML
    assert 'data-action="update"' not in SETTINGS_HTML
    assert ">Update</button>" not in SETTINGS_HTML
    assert "makeRecordEditor" in SETTINGS_HTML
    assert "activateContentTab" in SETTINGS_HTML
    assert "scheduleAutosave" in SETTINGS_HTML
    assert "Autosaved." in SETTINGS_HTML


def test_settings_html_includes_favicon():
    assert '<link rel="icon"' in SETTINGS_HTML
    assert "data:image/svg+xml" in SETTINGS_HTML


def test_settings_html_has_per_box_bullet_preview_vars():
    assert "--wisdom-bullet" in SETTINGS_HTML
    assert "--today-bullet" in SETTINGS_HTML
    assert "--bullet-marker" not in SETTINGS_HTML


def test_make_settings_server_uses_next_port_when_requested_port_is_busy(tmp_path):
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    busy_port = busy.getsockname()[1]
    try:
        server = make_settings_server(tmp_path, port=busy_port)
        try:
            assert server.server_address[1] != busy_port
        finally:
            server.server_close()
    finally:
        busy.close()


def test_shutdown_signal_handler_raises_keyboard_interrupt():
    previous = _install_shutdown_signal_handlers()
    try:
        assert signal.getsignal(signal.SIGINT) is _raise_keyboard_interrupt
        with pytest.raises(KeyboardInterrupt):
            _raise_keyboard_interrupt(signal.SIGINT, None)
    finally:
        _restore_signal_handlers(previous)


def test_state_to_payload_flattens_editor_fields():
    state = SettingsState(
        config=Config(
            ritual_phrase="phrase",
            work_minutes=25,
            block_minutes=4,
            google_calendar_urls=("https://example.com/a.ics", "https://example.com/b.ics"),
            timebox_duties=True,
            timebox_phrase="begin",
            timebox_lead_minutes=4,
            timebox_reminder_seconds=15,
            content_mode="replace",
            block_palette=BlockPalette(quote="#111111"),
        ),
        quotes=["Q1", "Q2"],
        wisdom=["W"],
        duties=["D1\nD1 detail"],
    )

    payload = state_to_payload(state)

    assert payload["ritual_phrase"] == "phrase"
    assert payload["work_minutes"] == 25
    assert payload["google_calendar_urls"] == "https://example.com/a.ics\nhttps://example.com/b.ics"
    assert payload["timebox_duties"] is True
    assert payload["timebox_lead_minutes"] == 4
    assert payload["timebox_reminder_seconds"] == 15
    assert payload["content_mode"] == "replace"
    assert payload["colors"]["quote"] == "#111111"
    assert payload["quotes"] == ["Q1", "Q2"]
    assert payload["wisdom"] == ["W"]
    assert payload["duties"] == ["D1\nD1 detail"]
    assert payload["quotes_text"] == "Q1\n\nQ2"
    assert payload["duties_text"] == "D1\nD1 detail"


def test_payload_to_state_preserves_existing_source_order_when_enabling_calendar():
    current = SettingsState(
        config=Config(ritual_phrase="phrase", duty_source_kinds=("textfile",)),
        quotes=[],
        wisdom=[],
        duties=[],
    )
    payload = {
        "ritual_phrase": "new phrase",
        "work_minutes": "30",
        "block_minutes": "6",
        "timebox_duties": True,
        "timebox_phrase": "begin",
        "timebox_lead_minutes": "5",
        "timebox_reminder_seconds": "15",
        "content_mode": "replace",
        "google_calendar_urls": "https://example.com/a.ics\n\n",
        "colors": BlockPalette(quote="#111111").as_dict(),
        "quotes": ["Q1\n\nstill Q1", "Q2"],
        "wisdom": ["W"],
        "duties": ["D"],
    }

    state = payload_to_state(payload, current)

    assert state.config.ritual_phrase == "new phrase"
    assert state.config.work_minutes == 30
    assert state.config.block_minutes == 6
    assert state.config.duty_source_kinds == ("textfile", "google_calendar")
    assert state.config.google_calendar_urls == ("https://example.com/a.ics",)
    assert state.config.timebox_duties is True
    assert state.config.timebox_phrase == "begin"
    assert state.config.timebox_lead_minutes == 5
    assert state.config.timebox_reminder_seconds == 15
    assert state.config.content_mode == "replace"
    assert state.config.block_palette.quote == "#111111"
    assert state.quotes == ["Q1\n\nstill Q1", "Q2"]
    assert state.wisdom == ["W"]
    assert state.duties == ["D"]


def test_payload_to_state_keeps_legacy_text_payload_for_compatibility():
    current = SettingsState(
        config=Config(ritual_phrase="phrase", duty_source_kinds=("textfile",)),
        quotes=[],
        wisdom=[],
        duties=[],
    )
    payload = {
        "ritual_phrase": "phrase",
        "work_minutes": "30",
        "block_minutes": "6",
        "timebox_duties": False,
        "timebox_phrase": "",
        "timebox_lead_minutes": "1",
        "timebox_reminder_seconds": "60",
        "content_mode": "merge",
        "google_calendar_urls": "",
        "colors": BlockPalette().as_dict(),
        "quotes_text": "Q1\n\nQ2",
        "wisdom_text": "W",
        "duties_text": "D",
    }

    state = payload_to_state(payload, current)

    assert state.quotes == ["Q1", "Q2"]
    assert state.wisdom == ["W"]
    assert state.duties == ["D"]


def test_payload_to_state_rejects_invalid_color():
    current = SettingsState(config=Config(ritual_phrase="phrase"), quotes=[], wisdom=[], duties=[])
    payload = {
        "ritual_phrase": "phrase",
        "work_minutes": 30,
        "block_minutes": 6,
        "timebox_duties": False,
        "timebox_phrase": "",
        "timebox_lead_minutes": 1,
        "timebox_reminder_seconds": 60,
        "content_mode": "merge",
        "google_calendar_urls": "",
        "colors": {"quote": "red"},
        "quotes": [],
        "wisdom": [],
        "duties": [],
    }

    with pytest.raises(ConfigError, match="colors.quote"):
        payload_to_state(payload, current)
