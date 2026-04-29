from __future__ import annotations

import argparse
import random
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from .block_window import BlockWindow
from .totem_symbols import get_totem_symbol
from .config import (
    Config,
    ConfigError,
    MissingRitualPhraseError,
    load_config,
    user_config_dir,
    write_default_config,
)
from .content import (
    BlockContent,
    ContentError,
    dedupe,
    load_quotes,
    load_quotes_from_items,
    load_user_content_json,
    load_wisdom,
    load_wisdom_from_items,
    pick_quote,
    pick_wisdom,
)
from .duty_sources import DutySource, make_duty_sources
from .scheduler import Scheduler
from .settings_window import run_settings_editor


class _RunControls:
    def __init__(self) -> None:
        self.paused = False


def _start_keyboard_listener(controls: _RunControls) -> Callable[[], None]:
    if not sys.stdin.isatty():
        return lambda: None

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(fd)
    except termios.error:
        return lambda: None
    tty.setcbreak(fd)
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.2)
            except (OSError, ValueError):
                return
            if r:
                try:
                    ch = sys.stdin.read(1)
                except (OSError, ValueError):
                    return
                if ch.lower() == "p":
                    controls.paused = not controls.paused

    threading.Thread(target=loop, daemon=True).start()

    def cleanup() -> None:
        stop.set()
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except termios.error:
            pass

    return cleanup


def _read_text_or_none(p: Path) -> str | None:
    try:
        return p.read_text()
    except OSError:
        return None


def _build_block_content(
    cfg_dir: Path,
    cfg: Config,
    rng: random.Random,
    duty_sources: list[DutySource],
) -> BlockContent:
    user_content = load_user_content_json(cfg_dir / "content.json")
    if user_content is None:
        quotes = load_quotes(_read_text_or_none(cfg_dir / "quotes.txt"), mode=cfg.content_mode)
        wisdom_pool = load_wisdom(_read_text_or_none(cfg_dir / "wisdom.txt"), mode=cfg.content_mode)
        duties = dedupe(_collect_duties(duty_sources))
    else:
        quotes = load_quotes_from_items(user_content.quotes, mode=cfg.content_mode)
        wisdom_pool = load_wisdom_from_items(user_content.wisdom, mode=cfg.content_mode)
        duties = dedupe((user_content.duties or []) + _collect_duties(duty_sources))
    return BlockContent(
        quote=pick_quote(quotes, rng),
        wisdom=pick_wisdom(wisdom_pool, rng, n=1),
        duties=duties,
        symbol_path=get_totem_symbol(config_dir=cfg_dir, rng=rng),
    )


def _collect_duties(duty_sources: list[DutySource]) -> list[str]:
    out: list[str] = []
    for source in duty_sources:
        out.extend(source.today())
    return out


def _first_run(config_path: Path) -> None:
    print("First-run setup for totems.")
    print("Pick a ritual phrase you'll type to dismiss a block early.")
    print("Long sentences work best - the friction is the point.")
    while True:
        phrase = input("Ritual phrase: ").strip()
        if phrase:
            break
        print("Phrase can't be empty.")
    write_default_config(config_path, ritual_phrase=phrase)
    print(f"Wrote {config_path}. You can edit it later.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="totems")
    parser.add_argument(
        "--debug-now",
        action="store_true",
        help="trigger one block immediately and exit",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="use 5-second timers for end-to-end smoke testing",
    )
    parser.add_argument(
        "--settings",
        action="store_true",
        help="open the graphical settings editor and exit",
    )
    parser.add_argument(
        "--debug-calendar",
        action="store_true",
        help="fetch configured Google Calendar URLs once, print today's items, and exit",
    )
    args = parser.parse_args(argv)

    cfg_dir = user_config_dir()
    if args.settings:
        run_settings_editor(cfg_dir)
        return 0

    config_path = cfg_dir / "config.toml"
    if not config_path.exists():
        _first_run(config_path)

    try:
        cfg = load_config(config_path)
    except MissingRitualPhraseError:
        _first_run(config_path)
        try:
            cfg = load_config(config_path)
        except ConfigError as retry_error:
            print(f"totems: config error: {retry_error}", file=sys.stderr)
            return 2
    except ConfigError as e:
        print(f"totems: config error: {e}", file=sys.stderr)
        return 2

    try:
        duty_sources = make_duty_sources(cfg, config_dir=cfg_dir)
    except ValueError as e:
        print(f"totems: config error: {e}", file=sys.stderr)
        return 2

    if args.debug_calendar:
        from .duty_sources.google_calendar import GoogleCalendarDutySource

        google_sources = [source for source in duty_sources if isinstance(source, GoogleCalendarDutySource)]
        if not google_sources:
            print("totems: no google_calendar URLs configured", file=sys.stderr)
            return 2
        for source in google_sources:
            for item in source.today():
                print(item)
        return 0

    try:
        load_user_content_json(cfg_dir / "content.json")
    except ContentError as e:
        print(f"totems: content error: {e}", file=sys.stderr)
        return 2

    rng = random.Random()

    def trigger_block() -> str:
        content = _build_block_content(cfg_dir, cfg, rng, duty_sources)
        if args.fast:
            block_seconds = 5
        elif args.debug_now:
            block_seconds = 60
        else:
            block_seconds = cfg.block_minutes * 60

        win = BlockWindow(
            content=content,
            ritual_phrase=cfg.ritual_phrase,
            block_seconds=block_seconds,
        )
        return win.run()

    if args.debug_now:
        trigger_block()
        return 0

    work_seconds = 5 if args.fast else cfg.work_minutes * 60

    controls = _RunControls()

    def print_countdown(remaining: float) -> None:
        if controls.paused:
            msg = "paused (press p to resume)"
        else:
            m, s = divmod(int(remaining), 60)
            msg = f"next block in {m:02d}:{s:02d}"
        sys.stdout.write(f"\r\x1b[K{msg}")
        sys.stdout.flush()

    cleanup_keyboard = _start_keyboard_listener(controls)
    if sys.stdin.isatty() and sys.stdout.isatty():
        print("totems: press 'p' to pause/resume; Ctrl-C to quit")

    sched = Scheduler(
        work_seconds=work_seconds,
        on_block=trigger_block,
        on_tick=print_countdown if sys.stdout.isatty() else None,
        is_paused=lambda: controls.paused,
    )
    try:
        sched.run()
    except KeyboardInterrupt:
        print("\ntotems: bye")
    finally:
        cleanup_keyboard()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
