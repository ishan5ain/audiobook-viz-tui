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
        chapter_index = 1 if seconds >= 30 else 0
        self.state = PlaybackState(
            position_ms=int(seconds * 1000),
            duration_ms=self.state.duration_ms,
            paused=self.state.paused,
            chapter_index=chapter_index,
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


def _renderable_plain_text(renderable: object) -> str:
    if hasattr(renderable, "plain"):
        return renderable.plain
    nested = getattr(renderable, "renderable", None)
    if nested is not None:
        return _renderable_plain_text(nested)
    renderables = getattr(renderable, "renderables", None)
    if renderables is not None:
        return "\n".join(_renderable_plain_text(item) for item in renderables)
    return str(renderable)


def test_textual_app_smoke(tmp_path: Path) -> None:
    asyncio.run(_run_ui_test(tmp_path))


def test_textual_app_survives_first_poll_error(tmp_path: Path) -> None:
    asyncio.run(_run_loading_ui_test(tmp_path))


def test_textual_app_book_mode_toggle_and_density_controls(tmp_path: Path) -> None:
    asyncio.run(_run_book_mode_ui_test(tmp_path))


def test_book_mode_turns_page_within_long_paragraph(tmp_path: Path) -> None:
    asyncio.run(_run_book_mode_paging_regression_test(tmp_path))


def test_chapter_progress_clock_uses_hour_format_only_when_needed(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")
    app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=7_200_000,
            chapters=[Chapter(index=0, title="Long", start_ms=0, end_ms=3_900_000)],
        ),
        timeline=SubtitleTimeline([SubtitleCue(0, 2000, "Hello world")]),
        playback_backend=FakeBackend(),
        subtitle_path=subtitle_path,
        state_store=StateStore(tmp_path / "state"),
        resume_enabled=True,
    )

    assert app._format_chapter_progress_clock(125_000, 3_500_000) == "02:05 / 58:20"
    assert app._format_chapter_progress_clock(125_000, 3_900_000) == "00:02:05 / 01:05:00"


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
        now_playing = app.query_one("#now_playing", Static)
        assert app._chapter_drawer_open is False
        assert drawer.styles.display == "none"
        assert list(app.query("#chapter-title").results()) == []
        assert list(app.query("#status").results()) == []
        assert "book.m4a" in str(now_playing.renderable)
        assert "One (1/2)" in str(now_playing.renderable)
        assert "\n\n" in str(now_playing.renderable)

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

        now_playing = app.query_one("#now_playing", Static)
        progress = app.query_one("#progress", Static)
        subtitle_panel = app.query_one("#subtitle-panel", Static)
        assert "Two (2/2)" in str(now_playing.renderable)
        assert ("play_pause", None) in backend.actions
        assert ("seek_relative", 10) in backend.actions
        progress_text = str(progress.renderable)
        progress_lines = progress_text.splitlines()
        assert len(progress_lines) == 4
        assert "00:10 / 00:30" in progress_lines[0]
        assert progress_lines[1] == ""
        chapter_bar = progress_lines[0].split("  ", maxsplit=1)[1]
        main_pane = app.query_one("#main-pane")
        expected_bar_width = max(10, max(progress.size.width, main_pane.size.width) - len("00:10 / 00:30") - 8)
        assert len(chapter_bar) == expected_bar_width
        assert "▶️" in progress_lines[2]
        assert "Playing" not in progress_lines[2]
        assert "00:00:40 / 00:01:00" in progress_lines[2]
        overall_bar = progress_lines[2].split("  ", maxsplit=2)[2]
        expected_overall_bar_width = max(
            10,
            max(progress.size.width, main_pane.size.width) - len("▶️") - len("00:00:40 / 00:01:00") - 10,
        )
        assert len(overall_bar) == expected_overall_bar_width
        assert "Subtitle size x1.2" in progress_lines[3]
        assert "Ctx 4/4" in progress_lines[3]
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
        now_playing = app.query_one("#now_playing", Static)
        progress = app.query_one("#progress", Static)
        assert list(app.query("#status").results()) == []
        assert "book.m4a" in str(now_playing.renderable)
        assert "One (1/1)" in str(now_playing.renderable)
        progress_text = str(progress.renderable)
        progress_lines = progress_text.splitlines()
        assert len(progress_lines) == 4
        assert "00:00 / 01:00" in progress_lines[0]
        assert progress_lines[1] == ""
        assert "⚠️  property unavailable" in progress_lines[2]
        assert "Subtitle size x1.0" in progress_lines[3]

        await pilot.pause(0.35)

        now_playing = app.query_one("#now_playing", Static)
        progress = app.query_one("#progress", Static)
        assert "book.m4a" in str(now_playing.renderable)
        assert "One (1/1)" in str(now_playing.renderable)
        progress_text = str(progress.renderable)
        progress_lines = progress_text.splitlines()
        assert len(progress_lines) == 4
        assert "00:02 / 01:00" in progress_lines[0]
        assert progress_lines[1] == ""
        assert "▶️" in progress_lines[2]
        assert "Playing" not in progress_lines[2]
        assert "00:00:02 / 00:01:00" in progress_lines[2]
        assert "Subtitle size x1.0" in progress_lines[3]

    app.shutdown_player()
    assert backend.closed is True


async def _run_book_mode_ui_test(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:00,800\nHello\n\n"
        "2\n00:00:00,900 --> 00:00:01,500\nworld\n\n"
        "3\n00:00:01,600 --> 00:00:02,200\nagain\n",
        encoding="utf-8",
    )
    app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=60_000)],
        ),
        timeline=SubtitleTimeline(
            [
                SubtitleCue(0, 800, "Hello"),
                SubtitleCue(900, 1500, "world"),
                SubtitleCue(1600, 2200, "again"),
            ]
        ),
        playback_backend=FakeBackend(),
        subtitle_path=subtitle_path,
        state_store=StateStore(tmp_path / "state"),
        resume_enabled=True,
    )

    async with app.run_test() as pilot:
        progress = app.query_one("#progress", Static)
        subtitle_panel = app.query_one("#subtitle-panel", Static)

        await pilot.press("m")
        await pilot.pause()
        progress_lines = str(progress.renderable).splitlines()
        assert "Mode book" in progress_lines[3]
        assert "Book density x1.0" in progress_lines[3]
        assert app.subtitle_display_mode == "book"
        assert "Hello world again" in _renderable_plain_text(subtitle_panel.renderable)

        await pilot.press("a")
        await pilot.pause()
        progress_lines = str(progress.renderable).splitlines()
        assert "Book density x1.1" in progress_lines[3]
        assert app.book_page_density == 1.1
        assert app.subtitle_context_before == 3
        assert app.subtitle_context_after == 3

        await pilot.press("m")
        await pilot.press("a")
        await pilot.pause()
        progress_lines = str(progress.renderable).splitlines()
        assert "Mode window" in progress_lines[3]
        assert "Ctx 4/3" in progress_lines[3]
        assert app.subtitle_display_mode == "window"

    app.shutdown_player()


async def _run_book_mode_paging_regression_test(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    cue_texts = [
        "Albatross bravo",
        "Charlotte delta",
        "Evergreen foxtrot",
        "Jubilation hotel",
        "Marigold juliet",
        "Nightfall kilo",
        "Orchestra lima",
        "Paragon mike",
    ]
    subtitle_path.write_text(
        "".join(
            f"{index + 1}\n00:00:{index:02d},000 --> 00:00:{index + 1:02d},000\n{text}\n\n"
            for index, text in enumerate(cue_texts)
        ),
        encoding="utf-8",
    )
    backend = FakeBackend()
    backend.state = PlaybackState(
        position_ms=500,
        duration_ms=60_000,
        paused=False,
        chapter_index=0,
    )
    app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=60_000)],
        ),
        timeline=SubtitleTimeline(
            [SubtitleCue(index * 1000, (index + 1) * 1000, text) for index, text in enumerate(cue_texts)]
        ),
        playback_backend=backend,
        subtitle_path=subtitle_path,
        state_store=StateStore(tmp_path / "state"),
        resume_enabled=True,
        initial_font_scale=3.0,
        initial_subtitle_display_mode="book",
    )

    async with app.run_test() as pilot:
        subtitle_panel = app.query_one("#subtitle-panel", Static)
        await pilot.pause()
        initial_page_text = _renderable_plain_text(subtitle_panel.renderable)
        assert "Albatross bravo" in initial_page_text
        assert "Orchestra lima" not in initial_page_text

        backend.state = PlaybackState(
            position_ms=6_500,
            duration_ms=60_000,
            paused=False,
            chapter_index=0,
        )
        app._poll_backend()
        await pilot.pause()

        updated_page_text = _renderable_plain_text(subtitle_panel.renderable)
        assert "Orchestra lima" in updated_page_text
        assert "Albatross bravo" not in updated_page_text

    app.shutdown_player()
