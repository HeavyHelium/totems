import os
import tkinter as tk

import pytest

from totems.block_window import BlockWindow
from totems.config import BlockPalette
from totems.content import BlockContent


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY"))


pytestmark = pytest.mark.skipif(not _has_display(), reason="needs an X display")


def test_renders_without_crashing():
    bc = BlockContent(
        quote="Test quote",
        wisdom=["sip water", "look away"],
        duties=["3pm dentist"],
        symbol_path=None,
    )
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1)
    win.root.update()  # force one render pass
    win.root.update_idletasks()
    assert bool(win.root.attributes("-fullscreen"))
    win.root.destroy()


def test_renders_quote_wisdom_and_duties_text():
    bc = BlockContent(
        quote="Visible quote",
        wisdom=["visible wisdom"],
        duties=["visible duty"],
        symbol_path=None,
    )
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1)
    win.root.update()

    texts = _widget_texts(win.root)

    assert "QUOTE" in texts
    assert "WISDOM" in texts
    assert "TODAY" in texts
    assert "Visible quote" in texts
    assert "visible wisdom" in texts
    assert "visible duty" in texts
    win.root.destroy()


def test_renders_symbol_and_agenda_placeholders_when_empty():
    bc = BlockContent(quote="q", wisdom=[], duties=[], symbol_path=None)
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1)
    win.root.update()

    texts = _widget_texts(win.root)

    assert any("No totem symbol loaded" in text for text in texts)
    assert "TODAY" in texts
    assert "No agenda items listed." in texts
    win.root.destroy()


def test_highlighted_duty_uses_highlighter_color():
    bc = BlockContent(
        quote="q",
        wisdom=[],
        duties=["09:00 standup"],
        symbol_path=None,
        highlighted_duties=frozenset({"09:00 standup"}),
    )
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1)
    win.root.update()

    duty_label = next(
        widget
        for widget in _walk_widgets(win.root)
        if str(widget).endswith("bullet_text") and widget.cget("text") == "09:00 standup"
    )
    assert duty_label.cget("bg") == "#ffe66d"
    assert _marker_beside(win.root, "09:00 standup").cget("bg") == "#ffe66d"
    win.root.destroy()


def test_custom_palette_reaches_block_window_widgets():
    bc = BlockContent(
        quote="q",
        wisdom=["w"],
        duties=["d"],
        symbol_path=None,
        highlighted_duties=frozenset({"d"}),
    )
    palette = BlockPalette(
        quote="#111111",
        wisdom="#222222",
        today="#333333",
        ritual="#444444",
        totem_panel="#555555",
        wisdom_bullet="#666666",
        today_bullet="#999999",
        highlight="#777777",
        border="#888888",
    )
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1, palette=palette)
    win.root.update()

    quote_label = next(
        widget for widget in _walk_widgets(win.root) if str(widget).endswith("quote_label")
    )
    symbol_panel = next(
        widget for widget in _walk_widgets(win.root) if str(widget).endswith("symbol_panel")
    )
    duty_label = next(
        widget
        for widget in _walk_widgets(win.root)
        if str(widget).endswith("bullet_text") and widget.cget("text") == "d"
    )

    assert quote_label.cget("bg") == "#111111"
    assert symbol_panel.cget("bg") == "#555555"
    assert duty_label.cget("bg") == "#777777"
    assert symbol_panel.cget("highlightbackground") == "#888888"
    win.root.destroy()


def test_per_box_bullet_colors_reach_markers():
    bc = BlockContent(quote="q", wisdom=["w"], duties=["d"], symbol_path=None)
    palette = BlockPalette(wisdom_bullet="#abcabc", today_bullet="#defdef")
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1, palette=palette)
    win.root.update()
    win.root.update_idletasks()

    assert _marker_beside(win.root, "w").cget("bg") == "#abcabc"
    assert _marker_beside(win.root, "d").cget("bg") == "#defdef"
    win.root.destroy()


def test_ritual_entry_stays_visible_with_long_wisdom():
    wisdom = ["\n".join(f"line {i}" for i in range(40))]
    bc = BlockContent(quote="q", wisdom=wisdom, duties=["d"], symbol_path=None)
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1)
    win.root.update()
    win.root.update_idletasks()

    assert win._entry.winfo_height() >= 30
    win.root.destroy()


def test_wisdom_text_is_pre_wrapped_at_fixed_width():
    long_line = "word " * 40
    bc = BlockContent(
        quote="q",
        wisdom=[long_line.strip()],
        duties=[],
        symbol_path=None,
    )
    win = BlockWindow(content=bc, ritual_phrase="hello", block_seconds=1)
    win.root.update()
    win.root.update_idletasks()

    bullet_labels = [
        child
        for child in _walk_widgets(win.root)
        if str(child).endswith("bullet_text") or str(child).endswith("bullet_continuation")
    ]
    assert bullet_labels
    wisdom_label = next(
        label for label in bullet_labels if str(label).endswith("bullet_continuation")
    )
    assert "\n" in wisdom_label.cget("text")
    assert all(label.cget("anchor") == "w" for label in bullet_labels)
    win.root.destroy()


def test_typing_phrase_returns_phrase_reason():
    bc = BlockContent(quote="q", wisdom=[], duties=[], symbol_path=None)
    win = BlockWindow(content=bc, ritual_phrase="open sesame", block_seconds=10)

    def type_and_submit():
        win._entry.insert(0, "open sesame")
        win._on_submit()

    win.root.after(50, type_and_submit)
    reason = win.run()
    assert reason == "phrase"


def test_startup_focus_targets_phrase_entry():
    bc = BlockContent(quote="q", wisdom=[], duties=[], symbol_path=None)
    win = BlockWindow(content=bc, ritual_phrase="open sesame", block_seconds=1)
    win.root.update()
    win.root.focus_force()
    win._focus_entry()
    win.root.update()

    assert win.root.focus_get() == win._entry
    win.root.destroy()


def test_close_cancels_pending_startup_focus_and_timer_callbacks():
    bc = BlockContent(quote="q", wisdom=[], duties=[], symbol_path=None)
    win = BlockWindow(content=bc, ritual_phrase="phrase", block_seconds=30)
    win.root.update()

    assert win._after_jobs

    win._close("probe")

    assert win._after_jobs == set()
    assert win._tick_job is None
    win.root.destroy()


def test_timeout_returns_timeout_reason():
    bc = BlockContent(quote="q", wisdom=[], duties=[], symbol_path=None)
    win = BlockWindow(content=bc, ritual_phrase="phrase", block_seconds=1)
    reason = win.run()
    assert reason == "timeout"


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


def _walk_widgets(widget: tk.Widget) -> list[tk.Widget]:
    out = [widget]
    for child in widget.winfo_children():
        out.extend(_walk_widgets(child))
    return out


def _marker_beside(root: tk.Widget, label_text: str) -> tk.Widget:
    label = next(
        widget
        for widget in _walk_widgets(root)
        if str(widget).endswith("bullet_text") and widget.cget("text") == label_text
    )
    return next(
        child
        for child in label.master.winfo_children()
        if str(child).endswith("bullet_marker")
    )


def test_wrong_phrase_does_not_dismiss():
    bc = BlockContent(quote="q", wisdom=[], duties=[], symbol_path=None)
    win = BlockWindow(content=bc, ritual_phrase="correct", block_seconds=1)

    def type_and_submit():
        win._entry.insert(0, "wrong")
        win._on_submit()

    win.root.after(50, type_and_submit)
    reason = win.run()
    assert reason == "timeout"
