from totems.scheduler import Scheduler


def test_run_once_sleeps_then_triggers_block():
    sleeps: list[float] = []
    triggers: list[int] = []

    def fake_sleep(s):
        sleeps.append(s)

    def fake_block():
        triggers.append(1)
        return "timeout"

    sched = Scheduler(work_seconds=2700, on_block=fake_block, sleep=fake_sleep)
    sched.run_once()

    assert sleeps == [2700]
    assert triggers == [1]


def test_run_loops_until_stopped():
    sleeps: list[float] = []
    iterations = {"n": 0}

    def fake_sleep(s):
        sleeps.append(s)
        iterations["n"] += 1
        if iterations["n"] >= 3:
            sched.stop()

    def fake_block():
        return "timeout"

    sched = Scheduler(work_seconds=10, on_block=fake_block, sleep=fake_sleep)
    sched.run()

    assert sleeps == [10, 10, 10]


def test_on_tick_emits_remaining_seconds_before_each_sleep_chunk():
    sleeps: list[float] = []
    ticks: list[float] = []

    def fake_sleep(s):
        sleeps.append(s)

    sched = Scheduler(
        work_seconds=3,
        on_block=lambda: "timeout",
        sleep=fake_sleep,
        on_tick=lambda r: ticks.append(r),
        tick_seconds=1,
    )
    sched.run_once()

    assert sleeps == [1, 1, 1]
    assert ticks == [3, 2, 1]


def test_is_paused_freezes_remaining_until_unpaused():
    sleeps: list[float] = []
    ticks: list[float] = []
    paused_state = {"value": False}

    def fake_sleep(s):
        sleeps.append(s)
        # pause for the first two ticks, then resume
        if len(ticks) == 1:
            paused_state["value"] = True
        elif len(ticks) == 3:
            paused_state["value"] = False

    sched = Scheduler(
        work_seconds=3,
        on_block=lambda: "timeout",
        sleep=fake_sleep,
        on_tick=lambda r: ticks.append(r),
        tick_seconds=1,
        is_paused=lambda: paused_state["value"],
    )
    sched.run_once()

    # Pause kicks in after the 1st sleep and lifts after the 3rd: tick 2 and 3
    # repeat remaining=2 (frozen), then tick 4 and 5 keep decrementing as normal.
    assert ticks == [3, 2, 2, 2, 1]
    assert sleeps == [1, 1, 1, 1, 1]


def test_no_on_tick_keeps_single_sleep_call():
    sleeps: list[float] = []

    sched = Scheduler(
        work_seconds=2700,
        on_block=lambda: "timeout",
        sleep=sleeps.append,
    )
    sched.run_once()

    assert sleeps == [2700]


def test_phrase_unlock_resets_timer():
    sleeps: list[float] = []

    def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) >= 2:
            sched.stop()

    sched = Scheduler(
        work_seconds=10,
        on_block=lambda: "phrase",
        sleep=fake_sleep,
    )
    sched.run()

    # both sleeps are full work_seconds - early unlock doesn't shorten the next wait
    assert sleeps == [10, 10]
