from __future__ import annotations

import random
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO


IMAGE_EXTS = {".png", ".gif"}
FALLBACK_URL = "https://cataas.com/cat/gif?type=square"
DEMO_SYMBOL_PATH = Path(__file__).resolve().parents[2] / "docs" / "assets" / "totem-readme.png"


UrlOpen = Callable[..., IO[bytes]]


def _response_content_type(resp: IO[bytes]) -> str:
    getheader = getattr(resp, "getheader", None)
    if callable(getheader):
        return str(getheader("Content-Type", "")).lower()

    headers = getattr(resp, "headers", None)
    if headers is not None:
        get = getattr(headers, "get", None)
        if callable(get):
            return str(get("Content-Type", "")).lower()

    return ""


def _list_local_symbols(symbols_dir: Path) -> list[Path]:
    if not symbols_dir.is_dir():
        return []
    out: list[Path] = []
    for child in symbols_dir.iterdir():
        if child.is_dir():
            continue  # skip .cache and any other dirs
        if child.suffix.lower() in IMAGE_EXTS:
            out.append(child)
    return sorted(out)


def _next_cache_path(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Use a monotonic timestamp so deletions don't cause filename collisions.
    return cache_dir / f"symbol-{time.time_ns()}.gif"


def _default_symbol_path() -> Path | None:
    if DEMO_SYMBOL_PATH.is_file():
        return DEMO_SYMBOL_PATH
    return None


def _is_gif(data: bytes) -> bool:
    return data.startswith((b"GIF87a", b"GIF89a"))


def get_totem_symbol(
    *,
    config_dir: Path,
    rng: random.Random,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> Path | None:
    symbols_dir = config_dir / "totem_symbols"
    locals_ = _list_local_symbols(symbols_dir)
    if locals_:
        return rng.choice(locals_)

    try:
        with urlopen(FALLBACK_URL, timeout=5) as resp:
            content_type = _response_content_type(resp)
            if content_type and not content_type.startswith("image/gif"):
                return _default_symbol_path()
            data = resp.read()
    except Exception:
        return _default_symbol_path()

    if not _is_gif(data):
        return _default_symbol_path()

    try:
        out = _next_cache_path(symbols_dir / ".cache")
        out.write_bytes(data)
    except OSError:
        return _default_symbol_path()
    return out
