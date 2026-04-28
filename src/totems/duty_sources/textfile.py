from __future__ import annotations

from pathlib import Path


class TextFileDutySource:
    def __init__(self, path: Path) -> None:
        self._path = path

    def today(self) -> list[str]:
        try:
            text = self._path.read_text()
        except (OSError, IsADirectoryError):
            return []
        out = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out.append(stripped)
        return out
