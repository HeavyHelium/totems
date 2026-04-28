import io
import random
from pathlib import Path

from totems.totem_symbols import get_totem_symbol


def _touch(p: Path, content: bytes = b"x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_returns_local_image_when_present(tmp_path):
    _touch(tmp_path / "totem_symbols" / "tabby.png")
    result = get_totem_symbol(config_dir=tmp_path, rng=random.Random(0), urlopen=_unreachable_urlopen)
    assert result == tmp_path / "totem_symbols" / "tabby.png"


def test_filters_to_image_extensions(tmp_path):
    _touch(tmp_path / "totem_symbols" / "notes.txt")
    result = get_totem_symbol(config_dir=tmp_path, rng=random.Random(0), urlopen=_fake_urlopen(b"http-bytes"))
    assert result is not None
    assert result.suffix.lower() == ".gif"
    assert result.name.startswith("symbol-")


def test_picks_deterministically_with_seed(tmp_path):
    for name in ["a.png", "b.png", "c.png"]:
        _touch(tmp_path / "totem_symbols" / name)
    r1 = get_totem_symbol(config_dir=tmp_path, rng=random.Random(7), urlopen=_unreachable_urlopen)
    r2 = get_totem_symbol(config_dir=tmp_path, rng=random.Random(7), urlopen=_unreachable_urlopen)
    assert r1 == r2


def test_falls_back_to_http_when_local_empty(tmp_path):
    result = get_totem_symbol(
        config_dir=tmp_path,
        rng=random.Random(0),
        urlopen=_fake_urlopen(b"http-bytes"),
    )
    assert result is not None
    assert result.read_bytes() == b"http-bytes"
    assert result.parent.name == ".cache"


def test_falls_back_to_http_when_only_cache_files_exist(tmp_path):
    _touch(tmp_path / "totem_symbols" / ".cache" / "symbol-old.gif", b"old")
    result = get_totem_symbol(
        config_dir=tmp_path,
        rng=random.Random(0),
        urlopen=_fake_urlopen(b"new-bytes"),
    )
    assert result is not None
    assert result.read_bytes() == b"new-bytes"


def test_returns_none_when_local_empty_and_http_fails(tmp_path):
    def _broken_urlopen(url, timeout=None):
        raise OSError("network down")

    result = get_totem_symbol(config_dir=tmp_path, rng=random.Random(0), urlopen=_broken_urlopen)
    assert result is None


def test_returns_none_when_http_returns_unsupported_content_type(tmp_path):
    result = get_totem_symbol(
        config_dir=tmp_path,
        rng=random.Random(0),
        urlopen=_fake_urlopen(b"<html>no image</html>", content_type="text/html"),
    )

    assert result is None


def test_returns_none_when_cache_cannot_be_written(tmp_path):
    (tmp_path / "totem_symbols").write_text("not a directory")

    result = get_totem_symbol(
        config_dir=tmp_path,
        rng=random.Random(0),
        urlopen=_fake_urlopen(b"http-bytes"),
    )

    assert result is None


def _fake_urlopen(payload: bytes, content_type: str = "image/gif"):
    def _impl(url, timeout=None):
        return _FakeResponse(payload, content_type)

    return _impl


class _FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, content_type: str) -> None:
        super().__init__(payload)
        self._content_type = content_type

    def getheader(self, name: str, default: str = "") -> str:
        if name.lower() == "content-type":
            return self._content_type
        return default


def _unreachable_urlopen(url, timeout=None):
    raise AssertionError("HTTP should not be called when local symbols exist")
