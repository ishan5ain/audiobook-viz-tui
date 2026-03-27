from __future__ import annotations

from pathlib import Path

import pytest

from audiobook_viz.playback import MpvBackend, PlaybackError


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send(self, payload: dict[str, object]) -> dict[str, object]:
        self.sent.append(payload)
        command = payload["command"]
        if command == ["get_property", "time-pos"]:
            return {"request_id": payload["request_id"], "error": "success", "data": 12.5}
        if command == ["get_property", "duration"]:
            return {"request_id": payload["request_id"], "error": "success", "data": 90.0}
        if command == ["get_property", "pause"]:
            return {"request_id": payload["request_id"], "error": "success", "data": False}
        if command == ["get_property", "chapter"]:
            return {"request_id": payload["request_id"], "error": "success", "data": 3}
        return {"request_id": payload["request_id"], "error": "success"}

    def close(self) -> None:
        return None


class PropertyUnavailableTransport(FakeTransport):
    def send(self, payload: dict[str, object]) -> dict[str, object]:
        self.sent.append(payload)
        command = payload["command"]
        if command == ["get_property", "idle-active"]:
            return {"request_id": payload["request_id"], "error": "success", "data": False}
        if command == ["get_property", "time-pos"]:
            return {"request_id": payload["request_id"], "error": "property unavailable"}
        if command == ["get_property", "duration"]:
            return {"request_id": payload["request_id"], "error": "property unavailable"}
        if command == ["get_property", "pause"]:
            return {"request_id": payload["request_id"], "error": "property unavailable"}
        if command == ["get_property", "chapter"]:
            return {"request_id": payload["request_id"], "error": "property unavailable"}
        return {"request_id": payload["request_id"], "error": "success"}


class ControlErrorTransport(FakeTransport):
    def send(self, payload: dict[str, object]) -> dict[str, object]:
        self.sent.append(payload)
        return {"request_id": payload["request_id"], "error": "command failed"}


def test_backend_emits_commands_and_maps_state() -> None:
    transport = FakeTransport()
    backend = MpvBackend(
        Path("/tmp/book.m4a"),
        initial_duration_ms=1000,
        transport=transport,
    )

    backend.play_pause()
    backend.seek_relative(10)
    backend.next_chapter()
    state = backend.get_state()

    assert transport.sent[0]["command"] == ["cycle", "pause"]
    assert transport.sent[1]["command"] == ["seek", 10, "relative"]
    assert transport.sent[2]["command"] == ["add", "chapter", 1]
    assert state.position_ms == 12500
    assert state.duration_ms == 90000
    assert state.paused is False
    assert state.chapter_index == 3


def test_backend_returns_fallback_state_when_properties_unavailable() -> None:
    backend = MpvBackend(
        Path("/tmp/book.m4a"),
        initial_duration_ms=91_000,
        transport=PropertyUnavailableTransport(),
    )

    state = backend.get_state()

    assert state.position_ms == 0
    assert state.duration_ms == 91_000
    assert state.paused is True
    assert state.chapter_index == -1
    assert backend.is_state_ready() is False


def test_control_commands_still_raise_on_non_success_errors() -> None:
    backend = MpvBackend(
        Path("/tmp/book.m4a"),
        initial_duration_ms=1000,
        transport=ControlErrorTransport(),
    )

    with pytest.raises(PlaybackError, match="command failed"):
        backend.seek_relative(10)
