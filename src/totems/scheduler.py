from __future__ import annotations

import time
from collections.abc import Callable


BlockResult = str  # "phrase" | "timeout"


class Scheduler:
    def __init__(
        self,
        *,
        work_seconds: float,
        on_block: Callable[[], BlockResult],
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
        on_tick: Callable[[float], None] | None = None,
        tick_seconds: float = 1.0,
        is_paused: Callable[[], bool] | None = None,
    ) -> None:
        self._work_seconds = work_seconds
        self._on_block = on_block
        self._sleep = sleep
        self._now = now
        self._on_tick = on_tick
        self._tick_seconds = tick_seconds
        self._is_paused = is_paused
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run_once(self) -> BlockResult:
        self._wait(self._work_seconds)
        return self._on_block()

    def _wait(self, seconds: float) -> None:
        if self._on_tick is None:
            self._sleep(seconds)
            return
        remaining = seconds
        while remaining > 0 and not self._stopped:
            self._on_tick(remaining)
            if self._is_paused is not None and self._is_paused():
                self._sleep(self._tick_seconds)
                continue
            chunk = min(self._tick_seconds, remaining)
            self._sleep(chunk)
            remaining -= chunk

    def run(self) -> None:
        while not self._stopped:
            self.run_once()
