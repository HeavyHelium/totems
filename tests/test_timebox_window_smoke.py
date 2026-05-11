import os
import tkinter as tk
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from totems.timebox_window import TimeboxWindow


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY"))


pytestmark = pytest.mark.skipif(not _has_display(), reason="needs an X display")


def test_timebox_window_renders_event_text():
    win = TimeboxWindow(
        title="standup",
        description="Daily sync",
        starts_at=datetime(2026, 4, 28, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
        phrase="begin",
        block_seconds=1,
    )
    win.root.update()

    texts = _widget_texts(win.root)

    assert "timebox" in texts
    assert "STARTS AT 09:00" in texts
    assert "standup" in texts
    assert "Daily sync" in texts
    win.root.destroy()


def _widget_texts(widget: tk.Widget) -> list[str]:
    out: list[str] = []
    try:
        text = widget.cget("text")
    except tk.TclError:
        text = ""
    if text:
        out.append(str(text))
    for child in widget.winfo_children():
        out.extend(_widget_texts(child))
    return out
