from __future__ import annotations

import time
from enum import Enum


class SleepTimer:
    class State(str, Enum):
        OFF = "off"
        RUNNING = "running"
        EXPIRED = "expired"

    def __init__(self, time_source: Callable[[], float] = time.monotonic) -> None:
        self._time_source = time_source
        self._remaining_ms: int | None = None
        self._last_tick_at: float | None = None
        self._state = self.State.OFF

    def set_duration(self, duration_ms: int | None) -> None:
        if duration_ms is None or duration_ms <= 0:
            self._remaining_ms = None
            self._last_tick_at = None
            self._state = self.State.OFF
        else:
            self._remaining_ms = duration_ms
            self._last_tick_at = self._time_source()
            self._state = self.State.RUNNING

    def tick(self, now: float, playing: bool) -> None:
        if self._state == self.State.OFF:
            self._last_tick_at = None
            return
        if self._state == self.State.EXPIRED:
            return
        if self._remaining_ms is None:
            return
        if self._last_tick_at is None:
            self._last_tick_at = now
            return
        if not playing:
            self._last_tick_at = now
            return
        elapsed_ms = max(0, int((now - self._last_tick_at) * 1000))
        self._last_tick_at = now
        if elapsed_ms <= 0:
            return
        remaining = self._remaining_ms - elapsed_ms
        if remaining > 0:
            self._remaining_ms = remaining
            return
        self._remaining_ms = None
        self._last_tick_at = None
        self._state = self.State.EXPIRED

    @property
    def remaining(self) -> int | None:
        return self._remaining_ms

    @property
    def state(self) -> State:
        return self._state

    def format_remaining(self) -> str:
        if self._remaining_ms is None:
            return "Off"
        total_seconds = max(0, (self._remaining_ms + 999) // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
