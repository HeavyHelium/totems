from __future__ import annotations

import random
from pathlib import Path

from totems import __main__ as main_mod
from totems.config import Config, load_config
from totems.duty_sources.google_calendar import GoogleCalendarDutySource


class _NoopScheduler:
    def __init__(self, *, work_seconds, on_block, **_kwargs):
        self.work_seconds = work_seconds
        self.on_block = on_block

    def run(self) -> None:
        return None


def test_main_returns_config_error_for_unknown_duty_source(monkeypatch, tmp_path, capsys):
    config_path = _write_config(
        tmp_path,
        'ritual_phrase = "phrase"\n[duty_source]\nkind = "nonsense"\n',
    )
    monkeypatch.setattr(main_mod, "user_config_dir", lambda: config_path.parent)
    monkeypatch.setattr(main_mod, "Scheduler", _NoopScheduler)

    result = main_mod.main([])

    assert result == 2
    assert "unknown duty source" in capsys.readouterr().err


def test_main_prompts_again_when_config_is_missing_ritual_phrase(monkeypatch, tmp_path):
    config_path = _write_config(tmp_path, "[timing]\nwork_minutes = 1\n")
    monkeypatch.setattr(main_mod, "user_config_dir", lambda: config_path.parent)
    monkeypatch.setattr(main_mod, "Scheduler", _NoopScheduler)
    monkeypatch.setattr("builtins.input", lambda _prompt: "new phrase")

    result = main_mod.main([])

    assert result == 0
    assert load_config(config_path).ritual_phrase == "new phrase"


def test_main_returns_config_error_for_invalid_timing(monkeypatch, tmp_path, capsys):
    config_path = _write_config(
        tmp_path,
        'ritual_phrase = "phrase"\n[timing]\nwork_minutes = "soon"\n',
    )
    monkeypatch.setattr(main_mod, "user_config_dir", lambda: config_path.parent)

    result = main_mod.main([])

    assert result == 2
    assert "invalid config value" in capsys.readouterr().err


def test_main_settings_opens_editor_and_exits(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(main_mod, "user_config_dir", lambda: tmp_path)
    monkeypatch.setattr(main_mod, "run_settings_editor", lambda cfg_dir: called.append(cfg_dir))

    result = main_mod.main(["--settings"])

    assert result == 0
    assert called == [tmp_path]


def test_main_debug_calendar_prints_google_source_items(monkeypatch, tmp_path, capsys):
    config_path = _write_config(tmp_path, 'ritual_phrase = "phrase"\n')
    source = GoogleCalendarDutySource(urls=[], cache_path=tmp_path / "cache.json")
    source.today = lambda: ["09:00 standup", "all day: vacation"]
    monkeypatch.setattr(main_mod, "user_config_dir", lambda: config_path.parent)
    monkeypatch.setattr(main_mod, "make_duty_sources", lambda cfg, *, config_dir: [source])

    result = main_mod.main(["--debug-calendar"])

    assert result == 0
    assert capsys.readouterr().out == "09:00 standup\nall day: vacation\n"


def test_main_debug_calendar_errors_without_google_source(monkeypatch, tmp_path, capsys):
    config_path = _write_config(tmp_path, 'ritual_phrase = "phrase"\n')
    monkeypatch.setattr(main_mod, "user_config_dir", lambda: config_path.parent)
    monkeypatch.setattr(main_mod, "make_duty_sources", lambda cfg, *, config_dir: [_StaticDutySource(["x"])])

    result = main_mod.main(["--debug-calendar"])

    assert result == 2
    assert "no google_calendar URLs configured" in capsys.readouterr().err


def test_build_block_content_replace_mode_uses_user_pools_only(monkeypatch, tmp_path):
    (tmp_path / "quotes.txt").write_text("User quote\n", encoding="utf-8")
    (tmp_path / "wisdom.txt").write_text("User wisdom\n", encoding="utf-8")
    cfg = Config(ritual_phrase="phrase", content_mode="replace")

    monkeypatch.setattr(main_mod, "get_totem_symbol", lambda *, config_dir, rng: None)

    content = main_mod._build_block_content(
        tmp_path,
        cfg,
        rng=random.Random(0),
        duty_sources=[_StaticDutySource(["User duty"])],
    )

    assert content.quote == "User quote"
    assert content.wisdom == ["User wisdom"]
    assert content.duties == ["User duty"]


def test_build_block_content_uses_json_pools_before_text_files(monkeypatch, tmp_path):
    (tmp_path / "quotes.txt").write_text("Text quote\n", encoding="utf-8")
    (tmp_path / "wisdom.txt").write_text("Text wisdom\n", encoding="utf-8")
    (tmp_path / "content.json").write_text(
        '{"quotes": ["JSON quote"], "wisdom": ["JSON wisdom"], "duties": ["JSON duty"]}',
        encoding="utf-8",
    )
    cfg = Config(ritual_phrase="phrase", content_mode="replace")

    monkeypatch.setattr(main_mod, "get_totem_symbol", lambda *, config_dir, rng: None)

    content = main_mod._build_block_content(
        tmp_path,
        cfg,
        rng=random.Random(0),
        duty_sources=[_StaticDutySource(["Text duty"])],
    )

    assert content.quote == "JSON quote"
    assert content.wisdom == ["JSON wisdom"]
    assert content.duties == ["JSON duty", "Text duty"]


def test_build_block_content_concatenates_multiple_duty_sources(monkeypatch, tmp_path):
    cfg = Config(ritual_phrase="phrase")
    monkeypatch.setattr(main_mod, "get_totem_symbol", lambda *, config_dir, rng: None)

    content = main_mod._build_block_content(
        tmp_path,
        cfg,
        rng=random.Random(0),
        duty_sources=[_StaticDutySource(["first"]), _StaticDutySource(["second"])],
    )

    assert content.duties == ["first", "second"]


def test_main_returns_content_error_for_malformed_json(monkeypatch, tmp_path, capsys):
    config_path = _write_config(tmp_path, 'ritual_phrase = "phrase"\n')
    (config_path.parent / "content.json").write_text('{"quotes": [123]}', encoding="utf-8")
    monkeypatch.setattr(main_mod, "user_config_dir", lambda: config_path.parent)

    result = main_mod.main([])

    assert result == 2
    assert "content error" in capsys.readouterr().err


def test_build_block_content_deduplicates_duties(monkeypatch, tmp_path):
    cfg = Config(ritual_phrase="phrase")
    monkeypatch.setattr(main_mod, "get_totem_symbol", lambda *, config_dir, rng: None)

    content = main_mod._build_block_content(
        tmp_path,
        cfg,
        rng=random.Random(0),
        duty_sources=[_StaticDutySource(["same"]), _StaticDutySource(["same", "different"])],
    )

    assert content.duties == ["same", "different"]


class _StaticDutySource:
    def __init__(self, duties: list[str]) -> None:
        self._duties = duties

    def today(self) -> list[str]:
        return self._duties


def _write_config(tmp_path: Path, text: str) -> Path:
    config_dir = tmp_path / "totems"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    config_path.write_text(text, encoding="utf-8")
    return config_path
