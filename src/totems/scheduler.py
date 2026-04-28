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
    ) -> None:
        self._work_seconds = work_seconds
        self._on_block = on_block
        self._sleep = sleep
        self._now = now
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run_once(self) -> BlockResult:
        self._sleep(self._work_seconds)
        return self._on_block()

    def run(self) -> None:
        while not self._stopped:
            self.run_once()
