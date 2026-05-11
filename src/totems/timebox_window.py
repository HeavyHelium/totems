from __future__ import annotations

import textwrap
import tkinter as tk
from datetime import datetime

from .block_window import ACCENT, BG, ENTRY_BG, INK, MUTED, PANEL_DARK, RITUAL_BG, SHADOW, TODAY_BG


class TimeboxWindow:
    def __init__(
        self,
        *,
        title: str,
        description: str,
        starts_at: datetime,
        phrase: str,
        block_seconds: int = 60,
    ) -> None:
        self._title = title
        self._description = description
        self._starts_at = starts_at
        self._phrase = phrase
        self._remaining = block_seconds
        self._after_jobs: set[str] = set()
        self._tick_job: str | None = None
        self.reason: str | None = None

        self.root = tk.Tk()
        self.root.title("totems timebox")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        self._build_ui()
        self._after(0, self._after_init)
        self._tick_job = self._after(1000, self._tick)

    def _after(self, delay_ms: int, callback) -> str:
        holder: dict[str, str] = {}

        def run_callback() -> None:
            job = holder["job"]
            self._after_jobs.discard(job)
            if self.reason is not None:
                return
            callback()

        job = self.root.after(delay_ms, run_callback)
        holder["job"] = job
        self._after_jobs.add(job)
        return job

    def _cancel_after_jobs(self) -> None:
        for job in list(self._after_jobs):
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._after_jobs.clear()
        self._tick_job = None

    def _after_init(self) -> None:
        self._make_fullscreen()
        for delay_ms in (0, 75, 250, 750):
            self._after(delay_ms, self._focus_entry)

    def _make_fullscreen(self) -> None:
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG, padx=42, pady=28)
        outer.pack(fill="both", expand=True)

        top = tk.Frame(outer, bg=BG)
        top.pack(fill="x")
        tk.Label(
            top,
            text="timebox",
            bg=BG,
            fg=ACCENT,
            font=("TkDefaultFont", 16, "bold"),
        ).pack(side="left")
        self._timer_var = tk.StringVar(value=self._format_remaining())
        tk.Label(
            top,
            textvariable=self._timer_var,
            bg=INK,
            fg="#fff8ea",
            padx=12,
            pady=8,
            font=("TkDefaultFont", 14, "bold"),
        ).pack(side="right")

        body = tk.Frame(
            outer,
            bg=TODAY_BG,
            padx=42,
            pady=36,
            highlightthickness=1,
            highlightbackground=SHADOW,
            highlightcolor=SHADOW,
        )
        body.pack(fill="both", expand=True, pady=(32, 18))

        tk.Label(
            body,
            text=f"STARTS AT {self._starts_at.strftime('%H:%M')}",
            bg=TODAY_BG,
            fg=PANEL_DARK,
            font=("TkDefaultFont", 13, "bold"),
        ).pack(anchor="w")

        tk.Label(
            body,
            name="timebox_title",
            text=self._title,
            wraplength=940,
            justify="left",
            bg=TODAY_BG,
            fg=INK,
            font=("TkDefaultFont", 34, "bold"),
        ).pack(anchor="w", pady=(18, 20))

        desc = self._description or "No description."
        tk.Label(
            body,
            name="timebox_description",
            text=_wrap_paragraphs(desc, 86),
            wraplength=940,
            justify="left",
            bg=TODAY_BG,
            fg=MUTED,
            font=("TkDefaultFont", 18),
        ).pack(anchor="w", fill="x")

        ritual = tk.Frame(
            outer,
            bg=RITUAL_BG,
            padx=18,
            pady=10,
            highlightthickness=1,
            highlightbackground=SHADOW,
            highlightcolor=SHADOW,
        )
        ritual.pack(side="bottom", fill="x")
        tk.Label(
            ritual,
            text="Type the dismissal phrase to close early.",
            bg=RITUAL_BG,
            fg=MUTED,
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        entry_wrap = tk.Frame(ritual, bg=INK, padx=2, pady=2)
        entry_wrap.pack(fill="x")
        self._entry = tk.Entry(
            entry_wrap,
            name="phrase_entry",
            bg=ENTRY_BG,
            fg=INK,
            insertbackground=ACCENT,
            relief="flat",
            font=("TkDefaultFont", 16),
        )
        self._entry.pack(fill="x", ipady=10)
        self._entry.bind("<Return>", lambda _e: self._on_submit())
        self.root.bind("<Return>", lambda _e: self._on_submit(), add="+")
        self._entry.focus_set()

    def _focus_entry(self) -> None:
        if self.reason is not None:
            return
        try:
            self.root.lift()
            self._entry.configure(state="normal")
            self._entry.focus_set()
            self._entry.icursor("end")
        except tk.TclError:
            return

    def _format_remaining(self) -> str:
        m, s = divmod(max(0, self._remaining), 60)
        return f"{m:02d}:{s:02d} to start"

    def _tick(self) -> None:
        self._tick_job = None
        self._remaining -= 1
        self._timer_var.set(self._format_remaining())
        if self._remaining <= 0:
            self._close("timeout")
            return
        self._tick_job = self._after(1000, self._tick)

    def _on_submit(self) -> None:
        if self._entry.get() == self._phrase:
            self._close("phrase")

    def _close(self, reason: str) -> None:
        if self.reason is None:
            self.reason = reason
            self._cancel_after_jobs()
            self.root.quit()

    def run(self) -> str:
        self.root.mainloop()
        self.root.destroy()
        return self.reason or "timeout"


def _wrap_paragraphs(text: str, width: int) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out.append("")
            continue
        out.append(
            textwrap.fill(
                line,
                width=width,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return "\n".join(out)
