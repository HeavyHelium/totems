from __future__ import annotations

import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

from .config import Config, ConfigError, load_config, write_config
from .content import (
    ContentError,
    UserContent,
    load_user_content_json,
    write_user_content_json,
)
from .duty_sources.textfile import TextFileDutySource


@dataclass(frozen=True)
class SettingsState:
    config: Config
    quotes: list[str]
    wisdom: list[str]
    duties: list[str]


def editor_text_to_items(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def items_to_editor_text(items: list[str]) -> str:
    return "\n\n".join(items)


def google_urls_text_to_tuple(text: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in text.splitlines() if line.strip())


def duty_source_kinds_for_google_urls(kinds: tuple[str, ...], urls: tuple[str, ...]) -> tuple[str, ...]:
    if urls:
        out = list(kinds)
        if "google_calendar" not in out:
            out.append("google_calendar")
    else:
        out = [kind for kind in kinds if kind != "google_calendar"]
    if not out:
        out.append("textfile")
    return tuple(out)


def _dedupe_items(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        stripped = item.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            out.append(stripped)
    return out


def _summary(item: str) -> str:
    first_line = item.strip().splitlines()[0] if item.strip() else "(empty)"
    return first_line if len(first_line) <= 42 else f"{first_line[:39]}..."


def load_settings_state(config_dir: Path) -> SettingsState:
    config_path = config_dir / "config.toml"
    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ConfigError):
        cfg = Config(ritual_phrase="")

    content = load_user_content_json(config_dir / "content.json")
    if content is not None:
        return SettingsState(
            config=cfg,
            quotes=content.quotes or [],
            wisdom=content.wisdom or [],
            duties=content.duties or [],
        )

    return SettingsState(
        config=cfg,
        quotes=_read_text_items(config_dir / "quotes.txt"),
        wisdom=_read_text_items(config_dir / "wisdom.txt"),
        duties=TextFileDutySource(config_dir / "duties.txt").today(),
    )


def save_settings_state(config_dir: Path, state: SettingsState) -> None:
    if not state.config.ritual_phrase.strip():
        raise ConfigError("ritual phrase must be non-empty")
    if state.config.content_mode not in {"merge", "replace"}:
        raise ConfigError("content mode must be 'merge' or 'replace'")

    write_config(config_dir / "config.toml", state.config)
    write_user_content_json(
        config_dir / "content.json",
        UserContent(quotes=state.quotes, wisdom=state.wisdom, duties=state.duties),
    )


def run_settings_editor(config_dir: Path) -> None:
    state = load_settings_state(config_dir)
    editor = SettingsEditor(config_dir=config_dir, state=state)
    editor.run()


def _read_text_items(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(stripped)
    return out


class RecordEditor:
    def __init__(
        self,
        parent: tk.Frame,
        *,
        label: str,
        items: list[str],
        bg: str,
        on_change,
    ) -> None:
        self._items = list(items)
        self._selected_index: int | None = None
        self._bg = bg
        self._on_change = on_change
        self._loading_editor = False

        tk.Label(
            parent,
            text=label.upper(),
            bg=bg,
            fg="#2f6f5e",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            parent,
            text="Each record can contain real line breaks. Use Add/Update/Delete; no JSON escaping.",
            bg=bg,
            fg="#756f65",
            wraplength=310,
        ).pack(anchor="w", pady=(2, 10))

        list_wrap = tk.Frame(parent, bg=bg)
        list_wrap.pack(fill="x")
        self._listbox = tk.Listbox(
            list_wrap,
            height=6,
            exportselection=False,
            activestyle="dotbox",
        )
        list_scroll = tk.Scrollbar(list_wrap, orient="vertical", command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=list_scroll.set)
        list_scroll.pack(side="right", fill="y")
        self._listbox.pack(side="left", fill="both", expand=True)
        self._listbox.bind("<<ListboxSelect>>", lambda _event: self._on_select())

        button_row = tk.Frame(parent, bg=bg)
        button_row.pack(fill="x", pady=8)
        tk.Button(button_row, text="Add", command=self._add).pack(side="left", padx=(0, 5))
        tk.Button(button_row, text="Update", command=self._update).pack(side="left", padx=5)
        tk.Button(button_row, text="Delete", command=self._delete).pack(side="left", padx=5)
        tk.Button(button_row, text="Clear editor", command=self._clear_editor).pack(side="left", padx=5)

        text_wrap = tk.Frame(parent, bg=bg)
        text_wrap.pack(fill="both", expand=True)
        self._text = tk.Text(text_wrap, wrap="word", height=14, undo=True)
        text_scroll = tk.Scrollbar(text_wrap, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=text_scroll.set)
        text_scroll.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)
        self._text.bind("<<Modified>>", lambda _event: self._on_text_modified())

        self._refresh_list()
        if self._items:
            self._select(0)

    def items(self) -> list[str]:
        self._sync_current()
        text = self._current_text()
        if self._selected_index is None and text:
            return [*_dedupe_items(self._items), text]
        return _dedupe_items(self._items)

    def _on_select(self) -> None:
        selection = self._listbox.curselection()
        if not selection:
            return
        next_index = int(selection[0])
        if next_index == self._selected_index:
            return
        self._sync_current()
        self._select(next_index)

    def _select(self, index: int) -> None:
        if not (0 <= index < len(self._items)):
            return
        self._selected_index = index
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(index)
        self._listbox.activate(index)
        self._replace_editor_text(self._items[index])

    def _add(self) -> None:
        self._sync_current()
        text = self._current_text() or "New item"
        self._items.append(text)
        self._refresh_list()
        self._select(len(self._items) - 1)
        self._on_change()

    def _update(self) -> None:
        text = self._current_text()
        if self._selected_index is None:
            if text:
                self._items.append(text)
                self._selected_index = len(self._items) - 1
        elif text:
            self._items[self._selected_index] = text
        else:
            del self._items[self._selected_index]
            self._selected_index = None
        self._refresh_list()
        if self._items:
            self._select(min(self._selected_index or 0, len(self._items) - 1))
        else:
            self._replace_editor_text("")
        self._on_change()

    def _delete(self) -> None:
        if self._selected_index is None:
            self._replace_editor_text("")
            self._on_change()
            return
        del self._items[self._selected_index]
        self._selected_index = None
        self._refresh_list()
        if self._items:
            self._select(0)
        else:
            self._replace_editor_text("")
        self._on_change()

    def _clear_editor(self) -> None:
        self._replace_editor_text("")
        self._on_change()

    def _sync_current(self) -> None:
        if self._selected_index is None:
            return
        text = self._current_text()
        if text:
            self._items[self._selected_index] = text
        else:
            del self._items[self._selected_index]
            self._selected_index = None
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._listbox.delete(0, "end")
        for i, item in enumerate(self._items, start=1):
            self._listbox.insert("end", f"{i}. {_summary(item)}")

    def _current_text(self) -> str:
        return self._text.get("1.0", "end").strip()

    def _replace_editor_text(self, text: str) -> None:
        self._loading_editor = True
        self._text.delete("1.0", "end")
        if text:
            self._text.insert("1.0", text)
        self._text.edit_modified(False)
        self._loading_editor = False

    def _on_text_modified(self) -> None:
        if self._loading_editor:
            self._text.edit_modified(False)
            return
        if self._text.edit_modified():
            self._text.edit_modified(False)
            self._on_change()


class SettingsEditor:
    def __init__(self, *, config_dir: Path, state: SettingsState) -> None:
        self._config_dir = config_dir
        self._state = state

        self.root = tk.Tk()
        self.root.title("totems settings")
        self.root.geometry("1180x780")
        self.root.configure(bg="#f3eadb")

        self._content_mode = tk.StringVar(value=state.config.content_mode)
        self._status = tk.StringVar(value=f"Saving to {config_dir}")
        self._autosave_job: str | None = None

        self._build_ui()

    def run(self) -> None:
        self.root.mainloop()

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg="#f3eadb", padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="totems settings",
            bg="#f3eadb",
            fg="#2f6f5e",
            font=("TkDefaultFont", 20, "bold"),
        ).pack(anchor="w")

        config_card = self._card(outer, "#fff8ea")
        config_card.pack(fill="x", pady=(14, 12))

        self._phrase = self._entry_row(config_card, "Ritual phrase", self._state.config.ritual_phrase)
        self._work = self._entry_row(config_card, "Work minutes", str(self._state.config.work_minutes))
        self._block = self._entry_row(config_card, "Block minutes", str(self._state.config.block_minutes))

        mode_row = tk.Frame(config_card, bg="#fff8ea")
        mode_row.pack(fill="x", pady=6)
        tk.Label(mode_row, text="Content mode", bg="#fff8ea", width=16, anchor="w").pack(side="left")
        for value, label in (("merge", "Merge with defaults"), ("replace", "Use only my pools")):
            tk.Radiobutton(
                mode_row,
                text=label,
                value=value,
                variable=self._content_mode,
                command=self._schedule_autosave,
                bg="#fff8ea",
                activebackground="#fff8ea",
            ).pack(side="left", padx=(0, 16))

        google_card = tk.Frame(
            config_card,
            bg="#e7f2ed",
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground="#c6ddd3",
        )
        google_card.pack(fill="x", pady=(12, 2))
        tk.Label(
            google_card,
            text="GOOGLE CALENDAR URLS",
            bg="#e7f2ed",
            fg="#2f6f5e",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            google_card,
            text="Private iCal URLs, one per line. Any URL enables calendar duties; clearing the box disables them.",
            bg="#e7f2ed",
            fg="#756f65",
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(2, 8))
        google_text_wrap = tk.Frame(google_card, bg="#e7f2ed")
        google_text_wrap.pack(fill="x")
        self._google_urls_text = tk.Text(
            google_text_wrap,
            height=4,
            wrap="none",
            undo=True,
            bg="#fffcf4",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#c6ddd3",
        )
        google_scroll = tk.Scrollbar(
            google_text_wrap, orient="vertical", command=self._google_urls_text.yview
        )
        self._google_urls_text.configure(yscrollcommand=google_scroll.set)
        google_scroll.pack(side="right", fill="y")
        self._google_urls_text.pack(side="left", fill="both", expand=True)
        self._google_urls_text.insert("1.0", "\n".join(self._state.config.google_calendar_urls))
        self._google_urls_text.edit_modified(False)
        self._google_urls_text.bind("<<Modified>>", lambda _event: self._on_google_urls_modified())
        self._google_urls_text.bind("<FocusOut>", lambda _event: self._schedule_autosave(delay_ms=100))

        editors = tk.Frame(outer, bg="#f3eadb")
        editors.pack(fill="both", expand=True)

        self._quotes = self._record_card(editors, "Quotes", self._state.quotes, "#fff4cf")
        self._wisdom = self._record_card(editors, "Wisdom", self._state.wisdom, "#e4f0df")
        self._duties = self._record_card(editors, "Duties", self._state.duties, "#f9dfca")

        bottom = tk.Frame(outer, bg="#f3eadb")
        bottom.pack(fill="x", pady=(12, 0))
        tk.Label(bottom, textvariable=self._status, bg="#f3eadb", fg="#756f65").pack(side="left")
        tk.Button(bottom, text="Save", command=self._save, padx=18, pady=6).pack(side="right")

    def _card(self, parent: tk.Frame, bg: str) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=bg,
            padx=16,
            pady=14,
            highlightthickness=1,
            highlightbackground="#e0d2bf",
        )

    def _entry_row(self, parent: tk.Frame, label: str, value: str) -> tk.Entry:
        row = tk.Frame(parent, bg="#fff8ea")
        row.pack(fill="x", pady=6)
        tk.Label(row, text=label, bg="#fff8ea", width=16, anchor="w").pack(side="left")
        entry = tk.Entry(row)
        entry.insert(0, value)
        entry.bind("<KeyRelease>", lambda _event: self._schedule_autosave())
        entry.bind("<FocusOut>", lambda _event: self._schedule_autosave(delay_ms=100))
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def _record_card(self, parent: tk.Frame, label: str, items: list[str], bg: str) -> RecordEditor:
        card = self._card(parent, bg)
        card.pack(side="left", fill="both", expand=True, padx=6)
        return RecordEditor(
            card,
            label=label,
            items=items,
            bg=bg,
            on_change=self._schedule_autosave,
        )

    def _save(self) -> None:
        if self._autosave_job is not None:
            self.root.after_cancel(self._autosave_job)
            self._autosave_job = None
        try:
            save_settings_state(self._config_dir, self._collect_state())
        except (ConfigError, ContentError, ValueError) as e:
            messagebox.showerror("Could not save settings", str(e))
            return

        self._status.set("Saved.")

    def _schedule_autosave(self, *, delay_ms: int = 800) -> None:
        if self._autosave_job is not None:
            self.root.after_cancel(self._autosave_job)
        self._status.set("Unsaved changes...")
        self._autosave_job = self.root.after(delay_ms, self._autosave)

    def _autosave(self) -> None:
        self._autosave_job = None
        try:
            save_settings_state(self._config_dir, self._collect_state())
        except (ConfigError, ContentError, ValueError) as e:
            self._status.set(f"Autosave paused: {e}")
            return

        self._status.set("Autosaved.")

    def _collect_state(self) -> SettingsState:
        google_urls = google_urls_text_to_tuple(self._google_urls_text.get("1.0", "end"))
        kinds = duty_source_kinds_for_google_urls(self._state.config.duty_source_kinds, google_urls)
        return SettingsState(
            config=Config(
                ritual_phrase=self._phrase.get().strip(),
                work_minutes=_positive_int_from_entry(self._work.get(), "Work minutes"),
                block_minutes=_positive_int_from_entry(self._block.get(), "Block minutes"),
                duty_source_kinds=kinds,
                google_calendar_urls=google_urls,
                content_mode=self._content_mode.get(),
            ),
            quotes=self._quotes.items(),
            wisdom=self._wisdom.items(),
            duties=self._duties.items(),
        )

    def _on_google_urls_modified(self) -> None:
        if self._google_urls_text.edit_modified():
            self._google_urls_text.edit_modified(False)
            self._schedule_autosave()


def _positive_int_from_entry(value: str, label: str) -> int:
    try:
        out = int(value)
    except ValueError as e:
        raise ConfigError(f"{label} must be a positive integer") from e
    if out <= 0:
        raise ConfigError(f"{label} must be a positive integer")
    return out
