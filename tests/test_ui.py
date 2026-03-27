from __future__ import annotations

import asyncio
from pathlib import Path

from textual.containers import Container
from textual.widgets import Label, ListView, Static

from audiobook_viz.models import Chapter, MediaMetadata, PlaybackState, SubtitleCue
from audiobook_viz.playback import PlaybackError
from audiobook_viz.state import StateStore
from audiobook_viz.subtitles import SubtitleTimeline
from audiobook_viz.ui import AudiobookVizApp


class FakeBackend:
    def __init__(self) -> None:
        self.state = PlaybackState(
            position_ms=0,
            duration_ms=60_000,
            paused=True,
            chapter_index=0,
        )
        self.actions: list[tuple[str, object]] = []
        self.closed = False

    def play_pause(self) -> None:
        self.actions.append(("play_pause", None))
        self.state = PlaybackState(
            position_ms=self.state.position_ms,
            duration_ms=self.state.duration_ms,
            paused=not self.state.paused,
            chapter_index=self.state.chapter_index,
        )

    def seek_relative(self, seconds: int) -> None:
        self.actions.append(("seek_relative", seconds))
        new_position = max(0, self.state.position_ms + seconds * 1000)
        self.state = PlaybackState(
            position_ms=new_position,
            duration_ms=self.state.duration_ms,
            paused=self.state.paused,
            chapter_index=self.state.chapter_index,
        )

    def seek_absolute(self, seconds: float) -> None:
        self.actions.append(("seek_absolute", seconds))
        self.state = PlaybackState(
            position_ms=int(seconds * 1000),
            duration_ms=self.state.duration_ms,
            paused=self.state.paused,
            chapter_index=self.state.chapter_index,
        )

    def next_chapter(self) -> None:
        self.actions.append(("next_chapter", None))
        self.state = PlaybackState(
            position_ms=self.state.position_ms,
            duration_ms=self.state.duration_ms,
            paused=self.state.paused,
            chapter_index=min(1, self.state.chapter_index + 1),
        )

    def previous_chapter(self) -> None:
        self.actions.append(("previous_chapter", None))
        self.state = PlaybackState(
            position_ms=self.state.position_ms,
            duration_ms=self.state.duration_ms,
            paused=self.state.paused,
            chapter_index=max(0, self.state.chapter_index - 1),
        )

    def set_pause(self, paused: bool) -> None:
        self.state = PlaybackState(
            position_ms=self.state.position_ms,
            duration_ms=self.state.duration_ms,
            paused=paused,
            chapter_index=self.state.chapter_index,
        )

    def get_state(self) -> PlaybackState:
        return self.state

    def is_state_ready(self) -> bool:
        return True

    def close(self) -> None:
        self.closed = True


class FlakyBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def get_state(self) -> PlaybackState:
        self.calls += 1
        if self.calls == 1:
            raise PlaybackError("property unavailable")
        self.state = PlaybackState(
            position_ms=2_000,
            duration_ms=60_000,
            paused=False,
            chapter_index=0,
        )
        return self.state

    def is_state_ready(self) -> bool:
        return self.calls > 1


def test_textual_app_smoke(tmp_path: Path) -> None:
    asyncio.run(_run_ui_test(tmp_path))


def test_textual_app_survives_first_poll_error(tmp_path: Path) -> None:
    asyncio.run(_run_loading_ui_test(tmp_path))


async def _run_ui_test(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")
    backend = FakeBackend()
    app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[
                Chapter(index=0, title="One", start_ms=0, end_ms=30_000),
                Chapter(index=1, title="Two", start_ms=30_000, end_ms=60_000),
            ],
        ),
        timeline=SubtitleTimeline([SubtitleCue(0, 2000, "Hello world")]),
        playback_backend=backend,
        subtitle_path=subtitle_path,
        state_store=StateStore(tmp_path / "state"),
        resume_enabled=True,
    )

    async with app.run_test() as pilot:
        drawer = app.query_one("#chapter-drawer", Container)
        assert app._chapter_drawer_open is False
        assert drawer.styles.display == "none"

        await pilot.press("c")
        assert app._chapter_drawer_open is True

        chapter_list = app.query_one("#chapter-list", ListView)
        assert chapter_list.index == 0

        await pilot.press("down")
        assert chapter_list.index == 1
        assert ("next_chapter", None) not in backend.actions

        await pilot.pause(0.35)
        assert chapter_list.index == 1

        first_label = chapter_list.children[0].query_one(Label)
        assert str(first_label.renderable).startswith("▶ ")

        await pilot.press("enter")
        assert ("seek_absolute", 30.0) in backend.actions

        await pilot.press("space")
        await pilot.press("right")
        await pilot.press("a")
        await pilot.press("s")
        await pilot.press("=")
        await pilot.pause()

        progress = app.query_one("#progress", Static)
        subtitle_panel = app.query_one("#subtitle-panel", Static)
        assert ("play_pause", None) in backend.actions
        assert ("seek_relative", 10) in backend.actions
        assert "Subtitle size x1.2" in str(progress.renderable)
        assert "Ctx 4/4" in str(progress.renderable)
        subtitle_group = subtitle_panel.renderable.renderable
        subtitle_plain = "\n".join(renderable.plain for renderable in subtitle_group.renderables)
        assert "Hello world" in subtitle_plain

    app.shutdown_player()
    assert backend.closed is True


async def _run_loading_ui_test(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")
    backend = FlakyBackend()
    app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=60_000)],
        ),
        timeline=SubtitleTimeline([SubtitleCue(0, 2000, "Hello world")]),
        playback_backend=backend,
        subtitle_path=subtitle_path,
        state_store=StateStore(tmp_path / "state"),
        resume_enabled=True,
    )

    async with app.run_test() as pilot:
        status = app.query_one("#status", Static)
        assert "Playback backend error" in str(status.renderable)

        await pilot.pause(0.35)

        status = app.query_one("#status", Static)
        progress = app.query_one("#progress", Static)
        assert "Playing" in str(status.renderable)
        assert "00:00:02 / 00:01:00" in str(progress.renderable)

    app.shutdown_player()
    assert backend.closed is True
