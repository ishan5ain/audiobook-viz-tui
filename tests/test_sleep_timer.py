from __future__ import annotations

import pytest

from audiobook_viz.ui.sleep_timer import SleepTimer


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_timer_counts_down_while_playing() -> None:
    clock = FakeClock(1000.0)
    timer = SleepTimer(time_source=clock.now)
    timer.set_duration(15 * 60 * 1000)  # 15 minutes

    assert timer.state == SleepTimer.State.RUNNING
    assert timer.remaining == 900000

    clock.advance(10)
    timer.tick(clock.now(), playing=True)
    assert timer.remaining == 890000

    # Expiry
    clock.advance(890)
    timer.tick(clock.now(), playing=True)
    assert timer.state == SleepTimer.State.EXPIRED
    assert timer.remaining is None


def test_timer_pauses_countdown_while_paused() -> None:
    clock = FakeClock(1000.0)
    timer = SleepTimer(time_source=clock.now)
    timer.set_duration(15 * 60 * 1000)

    clock.advance(10)
    timer.tick(clock.now(), playing=False)
    assert timer.remaining == 900000  # unchanged


def test_timer_cancel_returns_to_off() -> None:
    clock = FakeClock(1000.0)
    timer = SleepTimer(time_source=clock.now)
    timer.set_duration(15 * 60 * 1000)

    timer.set_duration(None)
    assert timer.state == SleepTimer.State.OFF
    assert timer.remaining is None


def test_format_remaining_formats_seconds_and_hours() -> None:
    clock = FakeClock(1000.0)
    timer = SleepTimer(time_source=clock.now)

    timer.set_duration(125 * 1000)  # 2:05
    assert timer.format_remaining() == "02:05"

    timer.set_duration(3661000)  # 1:01:01
    assert timer.format_remaining() == "01:01:01"
