from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


KNOWN_DUTY_SOURCE_KINDS: frozenset[str] = frozenset({"textfile", "google_calendar"})


class ConfigError(Exception):
    """Raised when config.toml is missing required fields or malformed."""


class MissingRitualPhraseError(ConfigError):
    """Raised when config.toml lacks the first-run ritual phrase."""


def _toml_escape(s: str) -> str:
    """Escape a string for use as a TOML basic string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


@dataclass(frozen=True)
class Config:
    ritual_phrase: str
    work_minutes: int = 45
    block_minutes: int = 5
    duty_source_kinds: tuple[str, ...] = ("textfile",)
    google_calendar_urls: tuple[str, ...] = ()
    content_mode: str = "merge"


def user_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path(os.environ["HOME"]) / ".config"
    return base / "totems"


def load_config(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"Could not read {path}: {e}") from e

    if "ritual_phrase" not in data:
        raise MissingRitualPhraseError(f"{path} is missing required key 'ritual_phrase'")

    ritual_phrase = data["ritual_phrase"]
    if not isinstance(ritual_phrase, str) or not ritual_phrase.strip():
        raise ConfigError(f"{path} has invalid config value: ritual_phrase must be non-empty")

    timing = _optional_table(data, "timing", path)
    duty = _optional_table(data, "duty_source", path)
    content = _optional_table(data, "content", path)
    duty_source_kinds = _parse_duty_source_kinds(duty, path)
    google = _optional_table(duty, "google_calendar", path)
    google_calendar_urls = _parse_google_calendar_urls(google, path)
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


def _optional_table(data: dict, key: str, path: Path) -> dict:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{path} has invalid config value: [{key}] must be a table")
    return value


def _positive_int(value: object, key: str, path: Path) -> int:
    if type(value) is not int or value <= 0:
        raise ConfigError(f"{path} has invalid config value: {key} must be a positive integer")
    return value


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
    for kind in kinds:
        if not kind:
            raise ConfigError(f"{path} has invalid config value: duty_source.kinds entries must be non-empty")
        if kind not in KNOWN_DUTY_SOURCE_KINDS:
            raise ConfigError(f"{path} has invalid config value: unknown duty source kind {kind!r}")
    return kinds


def _parse_google_calendar_urls(google: dict, path: Path) -> tuple[str, ...]:
    if "urls" not in google:
        return ()
    urls_raw = google["urls"]
    if not isinstance(urls_raw, list) or not all(isinstance(u, str) for u in urls_raw):
        raise ConfigError(
            f"{path} has invalid config value: duty_source.google_calendar.urls must be a list of strings"
        )
    if any(not u.strip() for u in urls_raw):
        raise ConfigError(
            f"{path} has invalid config value: duty_source.google_calendar.urls entries must be non-empty"
        )
    return tuple(u.strip() for u in urls_raw)


def write_default_config(path: Path, *, ritual_phrase: str) -> None:
    write_config(path, Config(ritual_phrase=ritual_phrase))


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
