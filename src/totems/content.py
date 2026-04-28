from __future__ import annotations

import json
import random
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


LAST_RESORT_QUOTE = "Take a breath."


class ContentError(Exception):
    """Raised when user content JSON is malformed."""


@dataclass(frozen=True)
class BlockContent:
    quote: str
    wisdom: list[str]
    duties: list[str]
    symbol_path: Path | None


@dataclass(frozen=True)
class UserContent:
    quotes: list[str] | None = None
    wisdom: list[str] | None = None
    duties: list[str] | None = None


def _read_default(filename: str) -> str:
    return resources.files("totems.defaults").joinpath(filename).read_text()


def _parse_lines(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return out


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _load_pool(default_filename: str, user_text: str | None, *, mode: str) -> list[str]:
    if mode not in {"merge", "replace"}:
        raise ValueError(f"unknown content mode: {mode!r}")

    user_items = _parse_lines(user_text or "")
    if mode == "replace":
        return dedupe(user_items)

    return dedupe([*_parse_lines(_read_default(default_filename)), *user_items])


def load_quotes(user_text: str | None, *, mode: str = "merge") -> list[str]:
    return _load_pool("quotes.txt", user_text, mode=mode)


def load_wisdom(user_text: str | None, *, mode: str = "merge") -> list[str]:
    return _load_pool("wisdom.txt", user_text, mode=mode)


def load_user_content_json(path: Path) -> UserContent | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ContentError(f"Could not read {path}: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ContentError(f"Could not parse {path}: {e}") from e

    if not isinstance(data, dict):
        raise ContentError(f"{path} must contain a JSON object")

    return UserContent(
        quotes=_optional_string_list(data, "quotes", path),
        wisdom=_optional_string_list(data, "wisdom", path),
        duties=_optional_string_list(data, "duties", path),
    )


def write_user_content_json(path: Path, content: UserContent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "quotes": content.quotes or [],
        "wisdom": content.wisdom or [],
        "duties": content.duties or [],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_quotes_from_items(user_items: list[str] | None, *, mode: str = "merge") -> list[str]:
    return _load_pool_from_items("quotes.txt", user_items, mode=mode)


def load_wisdom_from_items(user_items: list[str] | None, *, mode: str = "merge") -> list[str]:
    return _load_pool_from_items("wisdom.txt", user_items, mode=mode)


def _load_pool_from_items(
    default_filename: str,
    user_items: list[str] | None,
    *,
    mode: str,
) -> list[str]:
    if mode not in {"merge", "replace"}:
        raise ValueError(f"unknown content mode: {mode!r}")

    clean_user_items = dedupe([item.strip() for item in user_items or [] if item.strip()])
    if mode == "replace":
        return clean_user_items

    return dedupe([*_parse_lines(_read_default(default_filename)), *clean_user_items])


def _optional_string_list(data: dict, key: str, path: Path) -> list[str] | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, list):
        raise ContentError(f"{path}: {key!r} must be a list of strings")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ContentError(f"{path}: {key}[{i}] must be a string")
        stripped = item.strip()
        if stripped:
            out.append(stripped)
    return dedupe(out)


def pick_quote(quotes: list[str], rng: random.Random) -> str:
    if not quotes:
        return LAST_RESORT_QUOTE
    return rng.choice(quotes)


def pick_wisdom(wisdom: list[str], rng: random.Random, n: int) -> list[str]:
    if not wisdom:
        return []
    n = min(n, len(wisdom))
    return rng.sample(wisdom, n)
