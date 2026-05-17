from __future__ import annotations

import textwrap
import tkinter as tk

from .config import BlockPalette, DEFAULT_BLOCK_PALETTE
from .content import BlockContent


WISDOM_WRAP_CHARS = 70


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


def _split_first_line(text: str) -> tuple[str, str]:
    first, sep, rest = text.partition("\n")
    return first, rest if sep else ""


BG = "#f3eadb"
INK = "#1f241f"
MUTED = "#756f65"
PANEL = "#fff8ea"
PANEL_DARK = "#d66b3d"
ACCENT = "#2f6f5e"
ENTRY_BG = "#fffdf6"
RITUAL_BG = DEFAULT_BLOCK_PALETTE.ritual
TODAY_BG = DEFAULT_BLOCK_PALETTE.today
SHADOW = DEFAULT_BLOCK_PALETTE.border


class BlockWindow:
    def __init__(
        self,
        *,
        content: BlockContent,
        ritual_phrase: str,
        block_seconds: int,
        palette: BlockPalette = DEFAULT_BLOCK_PALETTE,
    ) -> None:
        self._content = content
        self._phrase = ritual_phrase
        self._remaining = block_seconds
        self._palette = palette
        self._after_jobs: set[str] = set()
        self._tick_job: str | None = None
        self.reason: str | None = None

        self.root = tk.Tk()
        self.root.title("totems")
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
        outer = tk.Frame(self.root, bg=BG, padx=32, pady=18)
        outer.pack(fill="both", expand=True)

        self._timer_var = tk.StringVar(value=self._format_remaining())
        top = tk.Frame(outer, bg=BG)
        top.pack(fill="x")
        tk.Label(
            top,
            text="totems",
            bg=BG,
            fg=ACCENT,
            font=("TkDefaultFont", 16, "bold"),
        ).pack(side="left")
        tk.Label(
            top,
            textvariable=self._timer_var,
            bg=INK,
            fg="#fff8ea",
            padx=12,
            pady=8,
            font=("TkDefaultFont", 14, "bold"),
        ).pack(side="right")

        ritual_card = self._card(outer, bg=self._palette.ritual, padx=18, pady=10)
        ritual_card.pack(side="bottom", fill="x")
        tk.Label(
            ritual_card,
            text="Type your ritual phrase to skip early.",
            bg=self._palette.ritual,
            fg=MUTED,
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        entry_wrap = tk.Frame(ritual_card, bg=INK, padx=2, pady=2)
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
        self._entry.pack(fill="x", ipady=10, padx=0, pady=0)
        self._entry.bind("<Return>", lambda _e: self._on_submit())
        self.root.bind("<Return>", lambda _e: self._on_submit(), add="+")
        self._entry.focus_set()

        body_wrap = tk.Frame(outer, bg=BG)
        body_wrap.pack(fill="both", expand=True, pady=(22, 12))
        body = tk.Frame(body_wrap, bg=BG)
        body.pack(fill="both", expand=True)

        self._build_symbol_panel(body)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        quote_card = self._card(right, bg=self._palette.quote, padx=34, pady=18)
        quote_card.pack(fill="x", pady=(0, 12))

        self._card_kicker(quote_card, "Quote", bg=self._palette.quote, fg=PANEL_DARK)

        tk.Label(
            quote_card,
            name="quote_label",
            text=self._content.quote,
            wraplength=580,
            justify="left",
            bg=self._palette.quote,
            fg=INK,
            font=("TkDefaultFont", 24, "bold"),
        ).pack(anchor="w", pady=(12, 0))

        sections = tk.Frame(right, bg=BG)
        sections.pack(fill="both", expand=True)

        wisdom_card = self._card(sections, bg=self._palette.wisdom, padx=28, pady=24)
        wisdom_card.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._card_kicker(wisdom_card, "Wisdom", bg=self._palette.wisdom, fg=ACCENT)

        if self._content.wisdom:
            for w in self._content.wisdom:
                self._bullet(
                    wisdom_card,
                    _wrap_paragraphs(w, WISDOM_WRAP_CHARS),
                    bg=self._palette.wisdom,
                    marker_bg=self._palette.wisdom_bullet,
                )
        else:
            self._bullet(
                wisdom_card,
                "No reminders listed.",
                bg=self._palette.wisdom,
                marker_bg=self._palette.wisdom_bullet,
            )

        today_card = self._card(sections, bg=self._palette.today, padx=28, pady=24)
        today_card.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self._card_kicker(today_card, "Today", bg=self._palette.today, fg=PANEL_DARK)
        if self._content.duties:
            for d in self._content.duties:
                self._bullet(
                    today_card,
                    d,
                    bg=self._palette.today,
                    marker_bg=self._palette.today_bullet,
                    highlighted=d in self._content.highlighted_duties,
                )
        else:
            self._bullet(
                today_card,
                "No agenda items listed.",
                bg=self._palette.today,
                marker_bg=self._palette.today_bullet,
            )

    def _card(self, parent: tk.Frame, *, bg: str, padx: int, pady: int) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=bg,
            padx=padx,
            pady=pady,
            highlightthickness=1,
            highlightbackground=self._palette.border,
            highlightcolor=self._palette.border,
        )
        return card

    def _card_kicker(self, parent: tk.Frame, text: str, *, bg: str, fg: str) -> None:
        tk.Label(
            parent,
            name=f"{text.lower()}_heading",
            text=text.upper(),
            bg=bg,
            fg=fg,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")

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

    def _build_symbol_panel(self, parent: tk.Frame) -> None:
        panel = tk.Frame(
            parent,
            name="symbol_panel",
            bg=self._palette.totem_panel,
            width=330,
            padx=16,
            pady=16,
            highlightthickness=1,
            highlightbackground=self._palette.border,
            highlightcolor=self._palette.border,
        )
        panel.pack(side="left", fill="y", padx=(0, 24))
        panel.pack_propagate(False)

        tk.Label(
            panel,
            text="totem check",
            bg=self._palette.totem_panel,
            fg="#fff8ea",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w", pady=(0, 14))

        if self._content.symbol_path is None:
            self._symbol_placeholder(panel, "No totem symbol loaded.\nAdd .png/.gif files to ~/.config/totems/totem_symbols/")
            return

        try:
            self._symbol_img = self._load_symbol_image()
        except tk.TclError:
            self._symbol_placeholder(panel, "Totem symbol could not be displayed.")
            return

        image_wrap = tk.Frame(
            panel,
            bg=self._palette.border,
            padx=1,
            pady=1,
            highlightthickness=1,
            highlightbackground=self._palette.border,
            highlightcolor=self._palette.border,
        )
        image_wrap.pack(expand=True)
        tk.Label(image_wrap, image=self._symbol_img, bg=self._palette.totem_panel).pack()

    def _symbol_placeholder(self, parent: tk.Frame, text: str) -> None:
        tk.Label(
            parent,
            name="symbol_placeholder",
            text=text,
            bg=self._palette.totem_panel,
            fg="#fff8ea",
            wraplength=250,
            justify="center",
            font=("TkDefaultFont", 13, "bold"),
        ).pack(expand=True)

    def _load_symbol_image(self) -> tk.PhotoImage:
        img = tk.PhotoImage(file=str(self._content.symbol_path))
        max_w = 290
        max_h = 430
        factor = max((img.width() + max_w - 1) // max_w, (img.height() + max_h - 1) // max_h, 1)
        if factor > 1:
            img = img.subsample(factor, factor)
        return img

    def _bullet(
        self,
        parent: tk.Frame,
        text: str,
        *,
        bg: str,
        marker_bg: str,
        highlighted: bool = False,
    ) -> None:
        row = tk.Frame(parent, bg=bg)
        row.pack(anchor="w", fill="x", pady=4)
        row.grid_rowconfigure(0, minsize=22)
        row.grid_columnconfigure(1, weight=1)
        marker_bg = self._palette.highlight if highlighted else marker_bg
        text_bg = self._palette.highlight if highlighted else bg
        text_fg = INK if highlighted else MUTED
        first_line, continuation = _split_first_line(text)
        marker = tk.Frame(
            row,
            name="bullet_marker",
            bg=marker_bg,
            width=22,
            height=18,
            highlightthickness=2,
            highlightbackground=self._palette.border,
            highlightcolor=self._palette.border,
        )
        marker.grid(row=0, column=0, padx=(0, 8))
        marker.pack_propagate(False)
        label = tk.Label(
            row,
            name="bullet_text",
            text=first_line,
            bg=text_bg,
            fg=text_fg,
            anchor="w",
            justify="left",
            font=("TkDefaultFont", 16),
            padx=4 if highlighted else 0,
            pady=2 if highlighted else 0,
        )
        label.grid(row=0, column=1, sticky="ew")
        if continuation:
            continuation_label = tk.Label(
                row,
                name="bullet_continuation",
                text=continuation,
                bg=text_bg,
                fg=text_fg,
                anchor="w",
                justify="left",
                font=("TkDefaultFont", 16),
                padx=4 if highlighted else 0,
                pady=2 if highlighted else 0,
            )
            continuation_label.grid(row=1, column=1, sticky="ew")

    def _format_remaining(self) -> str:
        m, s = divmod(max(0, self._remaining), 60)
        return f"{m:02d}:{s:02d} remaining"

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
