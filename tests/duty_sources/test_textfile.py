from totems.duty_sources import DutySource
from totems.duty_sources.textfile import TextFileDutySource


def test_textfile_returns_lines(tmp_path):
    p = tmp_path / "duties.txt"
    p.write_text("3pm dentist\nprep slides\n")
    src = TextFileDutySource(p)
    assert src.today() == ["3pm dentist", "prep slides"]


def test_textfile_strips_blanks_and_comments(tmp_path):
    p = tmp_path / "duties.txt"
    p.write_text("  \n# comment\nreal item\n")
    src = TextFileDutySource(p)
    assert src.today() == ["real item"]


def test_textfile_returns_empty_when_missing(tmp_path):
    src = TextFileDutySource(tmp_path / "missing.txt")
    assert src.today() == []


def test_textfile_returns_empty_when_unreadable(tmp_path):
    p = tmp_path / "dir-not-file"
    p.mkdir()
    src = TextFileDutySource(p)
    assert src.today() == []


def test_textfile_implements_protocol(tmp_path):
    src: DutySource = TextFileDutySource(tmp_path / "x.txt")
    assert hasattr(src, "today")
