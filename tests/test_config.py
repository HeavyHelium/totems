from pathlib import Path

import pytest

from totems.config import Config, ConfigError, load_config, write_config, write_default_config, user_config_dir


def test_user_config_dir_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert user_config_dir() == tmp_path / "totems"


def test_user_config_dir_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert user_config_dir() == tmp_path / ".config" / "totems"


def test_load_config_parses_valid_toml(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "I choose to skip"\n'
        "[timing]\nwork_minutes = 30\nblock_minutes = 10\n"
        '[duty_source]\nkind = "textfile"\n'
    )
    cfg = load_config(p)
    assert cfg == Config(
        ritual_phrase="I choose to skip",
        work_minutes=30,
        block_minutes=10,
        duty_source_kinds=("textfile",),
        google_calendar_urls=(),
        content_mode="merge",
    )


def test_load_config_uses_defaults_for_missing_optional_sections(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "phrase"\n')
    cfg = load_config(p)
    assert cfg.work_minutes == 45
    assert cfg.block_minutes == 5
    assert cfg.duty_source_kinds == ("textfile",)
    assert cfg.google_calendar_urls == ()
    assert cfg.content_mode == "merge"


def test_load_config_accepts_kinds_list(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "p"\n'
        '[duty_source]\nkinds = ["textfile", "google_calendar"]\n'
        '[duty_source.google_calendar]\nurls = ["https://example.com/cal.ics"]\n'
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
        '[duty_source]\nkinds = ["google_calendar"]\n'
        '[duty_source.google_calendar]\nurls = "https://example.com/cal.ics"\n'
    )
    with pytest.raises(ConfigError, match="urls"):
        load_config(p)


def test_load_config_rejects_google_url_empty_string(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "p"\n'
        '[duty_source]\nkinds = ["google_calendar"]\n'
        '[duty_source.google_calendar]\nurls = [""]\n'
    )
    with pytest.raises(ConfigError, match="urls"):
        load_config(p)


def test_load_config_allows_empty_google_urls(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'ritual_phrase = "p"\n'
        '[duty_source]\nkinds = ["google_calendar"]\n'
        '[duty_source.google_calendar]\nurls = []\n'
    )
    cfg = load_config(p)
    assert cfg.google_calendar_urls == ()


def test_load_config_parses_replace_content_mode(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "phrase"\n[content]\nmode = "replace"\n')
    cfg = load_config(p)
    assert cfg.content_mode == "replace"


def test_load_config_raises_on_invalid_content_mode(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "phrase"\n[content]\nmode = "append"\n')
    with pytest.raises(ConfigError, match="content.mode"):
        load_config(p)


def test_load_config_raises_on_missing_ritual_phrase(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[timing]\nwork_minutes = 30\n")
    with pytest.raises(ConfigError, match="ritual_phrase"):
        load_config(p)


def test_load_config_raises_on_malformed_toml(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("ritual_phrase = \n[timing")
    with pytest.raises(ConfigError):
        load_config(p)


def test_load_config_raises_on_invalid_timing_value(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "phrase"\n[timing]\nwork_minutes = "soon"\n')
    with pytest.raises(ConfigError, match="invalid config value"):
        load_config(p)


def test_load_config_raises_on_float_timing_value(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "phrase"\n[timing]\nwork_minutes = 1.9\n')
    with pytest.raises(ConfigError, match="positive integer"):
        load_config(p)


def test_load_config_raises_on_empty_ritual_phrase(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = ""\n')
    with pytest.raises(ConfigError, match="ritual_phrase"):
        load_config(p)


def test_load_config_raises_on_non_string_ritual_phrase(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("ritual_phrase = 123\n")
    with pytest.raises(ConfigError, match="ritual_phrase"):
        load_config(p)


def test_load_config_raises_on_non_positive_timing(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('ritual_phrase = "phrase"\n[timing]\nwork_minutes = 0\n')
    with pytest.raises(ConfigError, match="positive integer"):
        load_config(p)


def test_write_default_config_round_trips(tmp_path):
    p = tmp_path / "config.toml"
    write_default_config(p, ritual_phrase="hello world")
    cfg = load_config(p)
    assert cfg.ritual_phrase == "hello world"
    assert cfg.work_minutes == 45
    assert cfg.content_mode == "merge"


def test_write_default_config_escapes_special_characters_in_phrase(tmp_path):
    p = tmp_path / "config.toml"
    phrase = 'she said "hi" and \\ left'
    write_default_config(p, ritual_phrase=phrase)
    cfg = load_config(p)
    assert cfg.ritual_phrase == phrase


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
    assert load_config(p) == cfg
