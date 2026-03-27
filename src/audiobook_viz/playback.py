from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path
import shutil
from typing import Protocol

from audiobook_viz.models import PlaybackState

_TRANSIENT_PROPERTY_ERRORS = frozenset({"property unavailable"})


class PlaybackError(RuntimeError):
    """Raised when audio playback cannot be controlled."""


class PlaybackBackend(Protocol):
    def play_pause(self) -> None: ...

    def seek_relative(self, seconds: int) -> None: ...

    def seek_absolute(self, seconds: float) -> None: ...

    def next_chapter(self) -> None: ...

    def previous_chapter(self) -> None: ...

    def set_pause(self, paused: bool) -> None: ...

    def get_state(self) -> PlaybackState: ...

    def is_state_ready(self) -> bool: ...

    def close(self) -> None: ...


class JsonTransport(Protocol):
    def send(self, payload: dict[str, object]) -> dict[str, object]: ...

    def close(self) -> None: ...


def ensure_mpv_available(mpv_bin: str = "mpv") -> None:
    if shutil.which(mpv_bin):
        return
    raise PlaybackError("mpv was not found in PATH.")


class UnixSocketTransport:
    def __init__(self, socket_path: Path, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        last_error: OSError | None = None
        while time.monotonic() < deadline:
            try:
                self._socket.connect(str(socket_path))
                break
            except OSError as exc:
                last_error = exc
                time.sleep(0.05)
        else:
            self._socket.close()
            raise PlaybackError(f"Unable to connect to mpv IPC socket: {last_error}")
        self._buffer = b""

    def send(self, payload: dict[str, object]) -> dict[str, object]:
        message = json.dumps(payload).encode("utf-8") + b"\n"
        self._socket.sendall(message)
        request_id = payload.get("request_id")
        while True:
            raw = self._read_line()
            response = json.loads(raw.decode("utf-8"))
            if response.get("request_id") != request_id:
                continue
            return response

    def close(self) -> None:
        try:
            self._socket.close()
        except OSError:
            pass

    def _read_line(self) -> bytes:
        while b"\n" not in self._buffer:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise PlaybackError("mpv IPC socket closed unexpectedly.")
            self._buffer += chunk
        line, self._buffer = self._buffer.split(b"\n", 1)
        return line


class MpvBackend:
    def __init__(
        self,
        audio_path: Path,
        *,
        start_position_ms: int | None = None,
        paused: bool = False,
        initial_duration_ms: int = 0,
        mpv_bin: str = "mpv",
        transport: JsonTransport | None = None,
    ) -> None:
        self.audio_path = audio_path
        self._request_id = 0
        self._initial_duration_ms = max(0, initial_duration_ms)
        self._transport = transport
        self._process: subprocess.Popen[str] | None = None
        self._socket_dir: Path | None = None
        self._closed = False
        self._state_ready = False

        if self._transport is None:
            ensure_mpv_available(mpv_bin)
            self._transport = self._start_process(
                audio_path=audio_path,
                start_position_ms=start_position_ms,
                paused=paused,
                mpv_bin=mpv_bin,
            )

    def play_pause(self) -> None:
        self._command(["cycle", "pause"])

    def seek_relative(self, seconds: int) -> None:
        self._command(["seek", seconds, "relative"])

    def seek_absolute(self, seconds: float) -> None:
        self._command(["seek", seconds, "absolute"])

    def next_chapter(self) -> None:
        self._command(["add", "chapter", 1])

    def previous_chapter(self) -> None:
        self._command(["add", "chapter", -1])

    def set_pause(self, paused: bool) -> None:
        self._command(["set_property", "pause", paused])

    def get_state(self) -> PlaybackState:
        idle_active, idle_available = self._get_property("idle-active", default=False)
        if idle_available and bool(idle_active):
            self._state_ready = False
            return PlaybackState(
                position_ms=0,
                duration_ms=self._initial_duration_ms,
                paused=True,
                chapter_index=-1,
            )

        position_s, position_available = self._get_property("time-pos", default=0.0)
        duration_s, duration_available = self._get_property("duration", default=None)
        paused, paused_available = self._get_property("pause", default=True)
        chapter_index, chapter_available = self._get_property("chapter", default=-1)
        duration_ms = (
            self._initial_duration_ms
            if duration_s in (None, "")
            else max(0, int(float(duration_s) * 1000))
        )
        self._state_ready = all(
            (
                position_available,
                paused_available,
                chapter_available,
                duration_available or self._initial_duration_ms > 0,
            )
        )
        return PlaybackState(
            position_ms=0 if position_s in (None, "") else max(0, int(float(position_s) * 1000)),
            duration_ms=duration_ms,
            paused=bool(paused),
            chapter_index=-1 if chapter_index in (None, "") else int(chapter_index),
        )

    def is_state_ready(self) -> bool:
        return self._state_ready

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._transport is not None:
            try:
                self._command(["quit"])
            except PlaybackError:
                pass
            self._transport.close()
        if self._process is not None:
            try:
                self._process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                try:
                    self._process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._process.kill()
        if self._socket_dir is not None:
            shutil.rmtree(self._socket_dir, ignore_errors=True)

    def _command(
        self,
        command: list[object],
        *,
        accepted_errors: frozenset[str] | None = None,
    ) -> dict[str, object]:
        if self._transport is None:
            raise PlaybackError("Playback transport is not initialized.")
        self._request_id += 1
        payload = {"command": command, "request_id": self._request_id}
        response = self._transport.send(payload)
        accepted = accepted_errors or frozenset()
        if response.get("error") not in {None, "success", *accepted}:
            raise PlaybackError(str(response.get("error")))
        return response

    def _get_property(self, property_name: str, *, default: object) -> tuple[object, bool]:
        response = self._command(
            ["get_property", property_name],
            accepted_errors=_TRANSIENT_PROPERTY_ERRORS,
        )
        if response.get("error") in _TRANSIENT_PROPERTY_ERRORS:
            return default, False
        return response.get("data", default), True

    def _start_process(
        self,
        *,
        audio_path: Path,
        start_position_ms: int | None,
        paused: bool,
        mpv_bin: str,
    ) -> JsonTransport:
        self._socket_dir = Path(tempfile.mkdtemp(prefix="abv-", dir="/tmp"))
        socket_path = self._socket_dir / "mpv.sock"
        command = [
            mpv_bin,
            "--no-video",
            "--idle=no",
            "--force-window=no",
            "--input-terminal=no",
            "--really-quiet",
            f"--input-ipc-server={socket_path}",
        ]
        if paused:
            command.append("--pause=yes")
        if start_position_ms is not None and start_position_ms > 0:
            command.append(f"--start={start_position_ms / 1000:.3f}")
        command.append(str(audio_path))
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if socket_path.exists():
                break
            if self._process.poll() is not None:
                raise PlaybackError("mpv exited before the IPC socket became available.")
            time.sleep(0.05)
        else:
            raise PlaybackError("Timed out waiting for mpv IPC socket.")
        return UnixSocketTransport(socket_path)
