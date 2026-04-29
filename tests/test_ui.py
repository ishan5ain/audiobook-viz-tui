from __future__ import annotations

import asyncio
from pathlib import Path

from textual.containers import Container
from textual.widgets import Input, Label, ListView, Static

from audiobook_viz.models import Chapter, MediaMetadata, PlaybackState, SubtitleCue
from audiobook_viz.playback import PlaybackError
from audiobook_viz.state import StateStore
from audiobook_viz.subtitles import SubtitleTimeline
from audiobook_viz.ui import AudiobookVizApp, HelpModal, SleepTimerModal
from audiobook_viz.ui.enums import SubtitleDisplayMode


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
        self.actions.append(("set_pause", paused))
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


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


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


def _renderable_styles(renderable: object) -> list[str]:
    styles: list[str] = []
    style = getattr(renderable, "style", None)
    if style is not None:
        styles.append(str(style))
    spans = getattr(renderable, "spans", None)
    if spans is not None:
        styles.extend(str(span.style) for span in spans if span.style is not None)
    nested = getattr(renderable, "renderable", None)
    if nested is not None:
        styles.extend(_renderable_styles(nested))
    renderables = getattr(renderable, "renderables", None)
    if renderables is not None:
        for item in renderables:
            styles.extend(_renderable_styles(item))
    return styles


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


def test_help_accent_color_can_be_updated_and_persisted(tmp_path: Path) -> None:
    asyncio.run(_run_help_accent_color_ui_test(tmp_path))


def test_sleep_timer_modal_and_countdown(tmp_path: Path) -> None:
    asyncio.run(_run_sleep_timer_ui_test(tmp_path))


def test_sleep_timer_ignores_loading_and_backend_errors(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:10,000\nHello world\n", encoding="utf-8")
    clock = FakeClock()
    app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=60_000)],
        ),
        timeline=SubtitleTimeline([SubtitleCue(0, 10000, "Hello world")]),
        playback_backend=FakeBackend(),
        subtitle_path=subtitle_path,
        state_store=None,
        resume_enabled=False,
        time_source=clock.now,
    )
    app.playback_state = PlaybackState(position_ms=0, duration_ms=60_000, paused=False, chapter_index=0)
    app.set_sleep_timer_duration_ms(15 * 60 * 1000)

    app._backend_loading = True
    clock.advance(10)
    app._update_sleep_timer(clock.now())
    assert app.sleep_timer_remaining_ms == 15 * 60 * 1000

    app._backend_loading = False
    app._backend_error_message = "property unavailable"
    clock.advance(10)
    app._update_sleep_timer(clock.now())
    assert app.sleep_timer_remaining_ms == 15 * 60 * 1000


def test_help_bar_text_is_compact() -> None:
    app = AudiobookVizApp(
        metadata=MediaMetadata(audio_path=Path("book.m4a"), duration_ms=1, chapters=[]),
        timeline=SubtitleTimeline([]),
        playback_backend=FakeBackend(),
        subtitle_path=Path("book.srt"),
        state_store=None,
        resume_enabled=False,
    )

    assert app._help_bar_text() == (
        "Space Play  |  ←/→ Seek  |  ↑/↓ Chapter  |  c Chaps  |  m Mode  |  t Sleep  |  ? Help  |  q Quit"
    )
    app.playback_state = PlaybackState(position_ms=0, duration_ms=1, paused=False, chapter_index=-1)
    assert app._help_bar_text() == (
        "Space Pause  |  ←/→ Seek  |  ↑/↓ Chapter  |  c Chaps  |  m Mode  |  t Sleep  |  ? Help  |  q Quit"
    )


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
        help_bar = app.query_one("#help-bar", Static)
        assert app._chapter_drawer_open is False
        assert drawer.styles.display == "none"
        assert list(app.query("#chapter-title").results()) == []
        assert list(app.query("#status").results()) == []
        assert list(app.query("Footer").results()) == []
        assert "book.m4a" in str(now_playing.renderable)
        assert "One (1/2)" in str(now_playing.renderable)
        assert "\n\n" in str(now_playing.renderable)
        assert "←/→ Seek" in str(help_bar.renderable)
        assert "↑/↓ Chapter" in str(help_bar.renderable)
        assert "Space Play" in str(help_bar.renderable)
        assert "t Sleep" in str(help_bar.renderable)
        assert "? Help" in str(help_bar.renderable)
        assert "bold #ffbd14" in _renderable_styles(help_bar.renderable)
        assert "bold #ffbd14 on #21414f" in _renderable_styles(
            app.query_one("#subtitle-panel", Static).renderable
        )

        await pilot.press("?")
        await pilot.pause()
        help_modal = app.screen_stack[-1]
        assert isinstance(help_modal, HelpModal)
        assert "Keyboard Help" in _renderable_plain_text(help_modal.query_one("#help-title", Static).renderable)
        assert "Sleep Timer" in _renderable_plain_text(help_modal.query_one("#help-content", Static).renderable)
        assert "Window Mode" in _renderable_plain_text(help_modal.query_one("#help-content", Static).renderable)
        assert "bold #ffbd14" in _renderable_styles(help_modal.query_one("#help-content", Static).renderable)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen_stack[-1], HelpModal)

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
        help_bar = app.query_one("#help-bar", Static)
        assert "Two (2/2)" in str(now_playing.renderable)
        assert ("play_pause", None) in backend.actions
        assert ("seek_relative", 10) in backend.actions
        assert "Space Pause" in str(help_bar.renderable)
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
        assert list(app.query("Footer").results()) == []
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
        assert app.subtitle_display_mode == SubtitleDisplayMode.BOOK
        assert "Hello world again" in _renderable_plain_text(subtitle_panel.renderable)
        assert "bold #ffbd14 on #21414f" in _renderable_styles(subtitle_panel.renderable)

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
        assert app.subtitle_display_mode == SubtitleDisplayMode.WINDOW

        await pilot.press("h")
        await pilot.pause()
        help_modal = app.screen_stack[-1]
        assert isinstance(help_modal, HelpModal)
        assert "Book Mode" in _renderable_plain_text(help_modal.query_one("#help-content", Static).renderable)
        assert "Sleep Timer" in _renderable_plain_text(help_modal.query_one("#help-content", Static).renderable)
        await pilot.press("h")
        await pilot.pause()
        assert not isinstance(app.screen_stack[-1], HelpModal)

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
        initial_subtitle_display_mode=SubtitleDisplayMode.BOOK,
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


async def _run_help_accent_color_ui_test(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")
    state_store = StateStore(tmp_path / "state")
    backend = FakeBackend()
    app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=60_000)],
        ),
        timeline=SubtitleTimeline([SubtitleCue(0, 2000, "Hello world")]),
        playback_backend=backend,
        subtitle_path=subtitle_path,
        state_store=state_store,
        resume_enabled=True,
    )

    async with app.run_test() as pilot:
        help_bar = app.query_one("#help-bar", Static)
        assert "bold #ffbd14" in _renderable_styles(help_bar.renderable)

        await pilot.press("?")
        await pilot.pause()
        help_modal = app.screen_stack[-1]
        assert isinstance(help_modal, HelpModal)
        help_content = help_modal.query_one("#help-content", Static)
        assert "Current accent #ffbd14" in _renderable_plain_text(help_content.renderable)
        assert "bold #ffbd14" in _renderable_styles(help_content.renderable)
        assert "bold #ffbd14 on #21414f" in _renderable_styles(app.query_one("#subtitle-panel", Static).renderable)

        await pilot.press("e")
        await pilot.pause()
        accent_modal = app.screen_stack[-1]
        input_widget = accent_modal.query_one("#accent-color-input", Input)
        assert input_widget.value == "#ffbd14"

        await pilot.press("1", "1", "2", "2", "3", "3", "enter")
        await pilot.pause()
        assert isinstance(app.screen_stack[-1], HelpModal)
        assert app.help_accent_color == "#112233"
        assert "bold #112233" in _renderable_styles(app.query_one("#help-bar", Static).renderable)
        assert "bold #112233 on #21414f" in _renderable_styles(app.query_one("#subtitle-panel", Static).renderable)
        help_modal = app.screen_stack[-1]
        help_content = help_modal.query_one("#help-content", Static)
        assert "Current accent #112233" in _renderable_plain_text(help_content.renderable)
        assert "bold #112233" in _renderable_styles(help_content.renderable)

        await pilot.press("e")
        await pilot.pause()
        accent_modal = app.screen_stack[-1]
        await pilot.press("g", "g", "enter")
        await pilot.pause()
        assert accent_modal == app.screen_stack[-1]
        assert app.help_accent_color == "#112233"
        error_text = _renderable_plain_text(accent_modal.query_one("#accent-color-error", Static).renderable)
        assert "Enter a 6-digit RGB hex code" in error_text
        assert "bold #112233" in _renderable_styles(app.query_one("#help-bar", Static).renderable)

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen_stack[-1], HelpModal)

    app.shutdown_player()
    assert backend.closed is True

    loaded = state_store.load(audio_path)
    assert loaded is not None
    assert loaded.help_accent_color == "#112233"

    restored_app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=60_000)],
        ),
        timeline=SubtitleTimeline([SubtitleCue(0, 2000, "Hello world")]),
        playback_backend=FakeBackend(),
        subtitle_path=subtitle_path,
        state_store=state_store,
        resume_enabled=True,
        initial_help_accent_color=loaded.help_accent_color,
    )

    async with restored_app.run_test() as pilot:
        help_bar = restored_app.query_one("#help-bar", Static)
        assert "bold #112233" in _renderable_styles(help_bar.renderable)
        await pilot.press("?")
        await pilot.pause()
        help_modal = restored_app.screen_stack[-1]
        assert isinstance(help_modal, HelpModal)
        help_content = help_modal.query_one("#help-content", Static)
        assert "Current accent #112233" in _renderable_plain_text(help_content.renderable)
        assert "bold #112233" in _renderable_styles(help_content.renderable)
        assert "bold #112233 on #21414f" in _renderable_styles(
            restored_app.query_one("#subtitle-panel", Static).renderable
        )

    restored_app.shutdown_player()


async def _run_sleep_timer_ui_test(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:10,000\nHello world\n", encoding="utf-8")
    state_store = StateStore(tmp_path / "state")
    backend = FakeBackend()
    clock = FakeClock()
    app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=60_000)],
        ),
        timeline=SubtitleTimeline([SubtitleCue(0, 10000, "Hello world")]),
        playback_backend=backend,
        subtitle_path=subtitle_path,
        state_store=state_store,
        resume_enabled=True,
        time_source=clock.now,
    )

    async with app.run_test() as pilot:
        progress = app.query_one("#progress", Static)
        progress_lines = str(progress.renderable).splitlines()
        assert len(progress_lines) == 4
        assert "Sleep" not in progress_lines[2]

        await pilot.press("t")
        await pilot.pause()
        sleep_modal = app.screen_stack[-1]
        assert isinstance(sleep_modal, SleepTimerModal)
        sleep_content = sleep_modal.query_one("#sleep-timer-content", Static)
        assert "Current" in _renderable_plain_text(sleep_content.renderable)
        assert "Off" in _renderable_plain_text(sleep_content.renderable)

        await pilot.press("t")
        await pilot.pause()
        assert not isinstance(app.screen_stack[-1], SleepTimerModal)

        backend.set_pause(False)
        app._poll_backend()
        await pilot.pause()

        await pilot.press("t")
        await pilot.pause()
        sleep_modal = app.screen_stack[-1]
        assert isinstance(sleep_modal, SleepTimerModal)

        await pilot.press("up")
        await pilot.pause()
        sleep_content = sleep_modal.query_one("#sleep-timer-content", Static)
        assert "15:00" in _renderable_plain_text(sleep_content.renderable)

        await pilot.press("space")
        await pilot.pause()
        assert not isinstance(app.screen_stack[-1], SleepTimerModal)
        assert app.sleep_timer_remaining_ms == 15 * 60 * 1000
        progress_lines = str(app.query_one("#progress", Static).renderable).splitlines()
        assert len(progress_lines) == 4
        assert "Sleep 15:00" in progress_lines[2]
        overall_bar = progress_lines[2].split("  ", maxsplit=3)[2]
        main_pane = app.query_one("#main-pane")
        expected_bar_width = max(
            10,
            max(progress.size.width, main_pane.size.width)
            - len("▶️")
            - len("00:00:00 / 00:01:00")
            - len("Sleep 15:00")
            - 12,
        )
        assert len(overall_bar) == expected_bar_width

        clock.advance(10)
        app._poll_backend()
        await pilot.pause()
        progress_lines = str(app.query_one("#progress", Static).renderable).splitlines()
        assert "Sleep 14:50" in progress_lines[2]

        backend.set_pause(True)
        app._poll_backend()
        await pilot.pause()
        paused_label = app._sleep_timer_progress_label()
        assert paused_label == "Sleep 14:50"
        clock.advance(20)
        app._poll_backend()
        await pilot.pause()
        assert app._sleep_timer_progress_label() == "Sleep 14:50"

        backend.set_pause(False)
        app._poll_backend()
        await pilot.pause()
        clock.advance(890)
        pause_true_calls_before_expiry = backend.actions.count(("set_pause", True))
        app._poll_backend()
        await pilot.pause()
        assert app.sleep_timer_remaining_ms is None
        assert backend.actions.count(("set_pause", True)) == pause_true_calls_before_expiry + 1
        assert backend.state.paused is True
        progress_lines = str(app.query_one("#progress", Static).renderable).splitlines()
        assert "Sleep" not in progress_lines[2]

        await pilot.press("t")
        await pilot.pause()
        sleep_modal = app.screen_stack[-1]
        assert isinstance(sleep_modal, SleepTimerModal)
        await pilot.press("up", "up")
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert app.sleep_timer_remaining_ms == 30 * 60 * 1000

        await pilot.press("t")
        await pilot.pause()
        sleep_modal = app.screen_stack[-1]
        assert isinstance(sleep_modal, SleepTimerModal)
        await pilot.press("down", "down")
        await pilot.pause()
        assert app.sleep_timer_remaining_ms is None
        sleep_content = sleep_modal.query_one("#sleep-timer-content", Static)
        assert "Off" in _renderable_plain_text(sleep_content.renderable)
        await pilot.press("escape")
        await pilot.pause()

    app.shutdown_player()
    loaded = state_store.load(audio_path)
    assert loaded is not None

    restored_app = AudiobookVizApp(
        metadata=MediaMetadata(
            audio_path=audio_path,
            duration_ms=60_000,
            chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=60_000)],
        ),
        timeline=SubtitleTimeline([SubtitleCue(0, 10000, "Hello world")]),
        playback_backend=FakeBackend(),
        subtitle_path=subtitle_path,
        state_store=state_store,
        resume_enabled=True,
        time_source=clock.now,
    )

    async with restored_app.run_test() as pilot:
        progress_lines = str(restored_app.query_one("#progress", Static).renderable).splitlines()
        assert "Sleep" not in progress_lines[2]
        await pilot.press("t")
        await pilot.pause()
        sleep_modal = restored_app.screen_stack[-1]
        assert isinstance(sleep_modal, SleepTimerModal)
        sleep_content = sleep_modal.query_one("#sleep-timer-content", Static)
        assert "Off" in _renderable_plain_text(sleep_content.renderable)

    restored_app.shutdown_player()
