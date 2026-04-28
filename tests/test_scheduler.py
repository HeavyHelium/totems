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
