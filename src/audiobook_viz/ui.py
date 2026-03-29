from __future__ import annotations

import textwrap
from pathlib import Path

from rich.align import Align
from rich.console import Group
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Header, Input, Label, ListItem, ListView, Static

from audiobook_viz.colors import DEFAULT_HELP_ACCENT_COLOR, normalize_help_accent_color
from audiobook_viz.models import MediaMetadata, PlaybackState, ResumeState
from audiobook_viz.playback import PlaybackBackend, PlaybackError
from audiobook_viz.state import StateStore
from audiobook_viz.subtitles import SubtitleBookPage, SubtitleBookLine, SubtitleTimeline


class AudiobookVizApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #11161c;
        color: #e8ecef;
    }

    #body {
        layout: horizontal;
        height: 1fr;
    }

    #main-pane {
        width: 1fr;
        padding: 0 2;
    }

    #now_playing {
        height: 5;
        content-align: center middle;
        text-align: center;
        # background: #1b2430;
        # background: black;
        # border: round #3a4a5e;
        margin-bottom: 0;
    }

    #subtitle-panel {
        height: 1fr;
        content-align: center middle;
        background: #101820;
        border: round #5fb3b3;
        color: #f6f8fa;
        padding: 1 2;
    }

    #progress {
        height: 6;
        content-align: center middle;
        text-align: center;
        # background: #1b2430;
        # border: round #3a4a5e;
        margin-top: 0;
    }

    #help-bar {
        height: 1;
        color: #aebbc8;
        background: #121920;
        content-align: center middle;
        text-align: center;
    }

    #chapter-drawer {
        width: 34;
        background: #171d24;
        border-left: solid #324250;
        padding: 1;
    }

    #chapter-drawer.hidden {
        display: none;
    }

    #chapter-heading {
        height: 1;
        margin-bottom: 1;
        color: #8dc6ff;
    }

    #chapter-list {
        height: 1fr;
        border: round #3a4a5e;
    }

    HelpModal {
        align: center middle;
    }

    #help-modal {
        width: 78;
        max-width: 90%;
        height: auto;
        background: #161d25;
        border: round #5fb3b3;
        padding: 1 2;
    }

    #help-title {
        color: #ffffff;
        text-style: bold;
        margin-bottom: 1;
    }

    #help-content {
        color: #d6e0e8;
    }

    AccentColorModal {
        align: center middle;
    }

    #accent-color-modal {
        width: 56;
        max-width: 90%;
        height: auto;
        background: #161d25;
        border: round #5fb3b3;
        padding: 1 2;
    }

    #accent-color-title {
        color: #ffffff;
        text-style: bold;
        margin-bottom: 1;
    }

    #accent-color-note {
        color: #93a7b7;
        margin-bottom: 1;
    }

    #accent-color-input {
        margin-bottom: 1;
    }

    #accent-color-error {
        color: #ff8a80;
        min-height: 1;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_playback", "Play/Pause"),
        Binding("left", "seek_backward", "-10s"),
        Binding("right", "seek_forward", "+10s"),
        Binding("up", "previous_chapter", "Prev Chapter"),
        Binding("down", "next_chapter", "Next Chapter"),
        Binding("m", "toggle_subtitle_mode", "Sub Mode"),
        Binding("a", "increase_context_before", "Before+"),
        Binding("z", "decrease_context_before", "Before-"),
        Binding("s", "increase_context_after", "After+"),
        Binding("x", "decrease_context_after", "After-"),
        Binding("plus,=", "increase_font_scale", "Sub+"),
        Binding("minus,-", "decrease_font_scale", "Sub-"),
        Binding("[", "subtitle_offset_down", "Offset-"),
        Binding("]", "subtitle_offset_up", "Offset+"),
        Binding("c", "toggle_chapters", "Chapters"),
        Binding("j", "drawer_down", "Drawer Down", show=False),
        Binding("k", "drawer_up", "Drawer Up", show=False),
        Binding("enter", "select_chapter", "Jump Chapter", show=False),
        Binding("question_mark", "show_help", "Help"),
        Binding("h", "show_help", "Help"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        *,
        metadata: MediaMetadata,
        timeline: SubtitleTimeline,
        playback_backend: PlaybackBackend,
        subtitle_path: Path,
        state_store: StateStore | None,
        resume_enabled: bool,
        initial_font_scale: float = 1.0,
        initial_subtitle_offset_ms: int = 0,
        initial_subtitle_context_before: int = 3,
        initial_subtitle_context_after: int = 3,
        initial_subtitle_display_mode: str = "window",
        initial_book_page_density: float = 1.0,
        initial_help_accent_color: str = DEFAULT_HELP_ACCENT_COLOR,
    ) -> None:
        super().__init__()
        self.metadata = metadata
        self.timeline = timeline
        self.playback_backend = playback_backend
        self.subtitle_path = subtitle_path
        self.state_store = state_store
        self.resume_enabled = resume_enabled
        self.font_scale = max(1.0, initial_font_scale)
        self.subtitle_offset_ms = initial_subtitle_offset_ms
        self.subtitle_context_before = max(0, initial_subtitle_context_before)
        self.subtitle_context_after = max(0, initial_subtitle_context_after)
        self.subtitle_display_mode = self._coerce_subtitle_display_mode(initial_subtitle_display_mode)
        self.book_page_density = min(1.3, max(0.7, round(initial_book_page_density, 1)))
        try:
            self.help_accent_color = normalize_help_accent_color(initial_help_accent_color)
        except ValueError:
            self.help_accent_color = DEFAULT_HELP_ACCENT_COLOR
        self.playback_state = PlaybackState(
            position_ms=0,
            duration_ms=metadata.duration_ms,
            paused=True,
            chapter_index=0 if metadata.chapters else -1,
        )
        self._chapter_drawer_open = False
        self._chapter_selection_index = 0 if metadata.chapters else None
        self._player_closed = False
        self._poll_handle = None
        self._backend_loading = True
        self._backend_error_message: str | None = None
        self._chapter_labels: list[Label] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="main-pane"):
                yield Static(id="now_playing")
                yield Static(id="subtitle-panel")
                yield Static(id="progress")
            with Container(id="chapter-drawer", classes="hidden"):
                yield Label("Chapters", id="chapter-heading")
                yield ListView(id="chapter-list")
        yield Static(self._help_bar_renderable(), id="help-bar")

    def on_mount(self) -> None:
        chapter_list = self.query_one("#chapter-list", ListView)
        for chapter in self.metadata.chapters:
            label = Label(chapter.title)
            self._chapter_labels.append(label)
            chapter_list.append(ListItem(label))
        if self.metadata.chapters:
            chapter_list.index = 0
        self._refresh_ui()
        self._poll_backend()
        self._poll_handle = self.set_interval(0.25, self._poll_backend)

    def action_toggle_playback(self) -> None:
        self.playback_backend.play_pause()
        self._poll_backend()

    def action_seek_backward(self) -> None:
        self.playback_backend.seek_relative(-10)
        self._poll_backend()

    def action_seek_forward(self) -> None:
        self.playback_backend.seek_relative(10)
        self._poll_backend()

    def action_previous_chapter(self) -> None:
        if not self.metadata.chapters:
            return
        if self._chapter_drawer_open:
            self.action_drawer_up()
            return
        self.playback_backend.previous_chapter()
        self._poll_backend()

    def action_next_chapter(self) -> None:
        if not self.metadata.chapters:
            return
        if self._chapter_drawer_open:
            self.action_drawer_down()
            return
        self.playback_backend.next_chapter()
        self._poll_backend()

    def action_increase_context_before(self) -> None:
        if self.subtitle_display_mode == "book":
            self._adjust_book_page_density(0.1)
            return
        self.subtitle_context_before = min(12, self.subtitle_context_before + 1)
        self._refresh_subtitle()
        self._refresh_progress()

    def action_decrease_context_before(self) -> None:
        if self.subtitle_display_mode == "book":
            self._adjust_book_page_density(-0.1)
            return
        self.subtitle_context_before = max(0, self.subtitle_context_before - 1)
        self._refresh_subtitle()
        self._refresh_progress()

    def action_increase_context_after(self) -> None:
        if self.subtitle_display_mode == "book":
            self._adjust_book_page_density(0.1)
            return
        self.subtitle_context_after = min(12, self.subtitle_context_after + 1)
        self._refresh_subtitle()
        self._refresh_progress()

    def action_decrease_context_after(self) -> None:
        if self.subtitle_display_mode == "book":
            self._adjust_book_page_density(-0.1)
            return
        self.subtitle_context_after = max(0, self.subtitle_context_after - 1)
        self._refresh_subtitle()
        self._refresh_progress()

    def action_increase_font_scale(self) -> None:
        self.font_scale = min(3.0, round(self.font_scale + 0.2, 2))
        self._refresh_subtitle()
        self._refresh_progress()

    def action_decrease_font_scale(self) -> None:
        self.font_scale = max(1.0, round(self.font_scale - 0.2, 2))
        self._refresh_subtitle()
        self._refresh_progress()

    def action_subtitle_offset_down(self) -> None:
        self.subtitle_offset_ms -= 250
        self._refresh_subtitle()
        self._refresh_progress()

    def action_subtitle_offset_up(self) -> None:
        self.subtitle_offset_ms += 250
        self._refresh_subtitle()
        self._refresh_progress()

    def action_toggle_subtitle_mode(self) -> None:
        self.subtitle_display_mode = "book" if self.subtitle_display_mode == "window" else "window"
        self._refresh_subtitle()
        self._refresh_progress()

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def set_help_accent_color(self, value: str) -> None:
        self.help_accent_color = normalize_help_accent_color(value)
        if self.is_mounted:
            self.query_one("#help-bar", Static).update(self._help_bar_renderable())
            self._refresh_subtitle()

    def action_toggle_chapters(self) -> None:
        if not self.metadata.chapters:
            return
        drawer = self.query_one("#chapter-drawer", Container)
        self._chapter_drawer_open = not self._chapter_drawer_open
        drawer.styles.display = "block" if self._chapter_drawer_open else "none"
        if self._chapter_drawer_open:
            drawer.remove_class("hidden")
            self._apply_drawer_selection()
            self.query_one("#chapter-list", ListView).focus()
        else:
            drawer.add_class("hidden")
            self.set_focus(None)

    def action_drawer_down(self) -> None:
        if self._chapter_drawer_open:
            if self._chapter_selection_index is None:
                self._chapter_selection_index = 0
            else:
                self._chapter_selection_index = min(
                    len(self.metadata.chapters) - 1,
                    self._chapter_selection_index + 1,
                )
            self._apply_drawer_selection()

    def action_drawer_up(self) -> None:
        if self._chapter_drawer_open:
            if self._chapter_selection_index is None:
                self._chapter_selection_index = 0
            else:
                self._chapter_selection_index = max(0, self._chapter_selection_index - 1)
            self._apply_drawer_selection()

    def action_select_chapter(self) -> None:
        if not self._chapter_drawer_open:
            return
        self._jump_to_selected_chapter(self.query_one("#chapter-list", ListView).index)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "chapter-list" or not self._chapter_drawer_open:
            return
        self._jump_to_selected_chapter(event.index)

    def action_quit_app(self) -> None:
        self.shutdown_player()
        self.exit()

    def shutdown_player(self) -> None:
        if self._player_closed:
            return
        self._player_closed = True
        if self._poll_handle is not None:
            self._poll_handle.stop()
        if self.resume_enabled and self.state_store is not None:
            chapter_index = self.playback_state.chapter_index
            if chapter_index < 0 and self.metadata.chapters:
                chapter_index = 0
            self.state_store.save(
                self.metadata.audio_path,
                ResumeState(
                    position_ms=self.playback_state.position_ms,
                    chapter_index=chapter_index,
                    font_scale=self.font_scale,
                    subtitle_offset_ms=self.subtitle_offset_ms,
                    subtitle_context_before=self.subtitle_context_before,
                    subtitle_context_after=self.subtitle_context_after,
                    subtitle_display_mode=self.subtitle_display_mode,
                    book_page_density=self.book_page_density,
                    help_accent_color=self.help_accent_color,
                    subtitle_path=str(self.subtitle_path),
                ),
            )
        self.playback_backend.close()

    def on_resize(self) -> None:
        if not self.is_mounted:
            return
        self._refresh_subtitle()
        self._refresh_progress()

    def _poll_backend(self) -> None:
        try:
            self.playback_state = self.playback_backend.get_state()
            self._backend_loading = not self.playback_backend.is_state_ready()
            self._backend_error_message = None
        except PlaybackError as exc:
            self._backend_loading = True
            self._backend_error_message = str(exc)
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        self._refresh_now_playing()
        self._refresh_chapter_list()
        self._refresh_subtitle()
        self._refresh_progress()
        self._sync_chapter_selection()

    def _refresh_now_playing(self) -> None:
        audiobook_name = self.metadata.audio_path.name
        if not self.metadata.chapters:
            chapter_line = "Chapter 0/0 | No chapters"
        else:
            current_index = self._resolved_chapter_index()
            chapter = self.metadata.chapters[current_index]
            # chapter_line = f"Chapter {current_index + 1}/{len(self.metadata.chapters)} | {chapter.title}"
            chapter_line = f"{chapter.title} ({current_index + 1}/{len(self.metadata.chapters)})"
        self.query_one("#now_playing", Static).update(f"{audiobook_name}\n\n{chapter_line}")

    def _refresh_subtitle(self) -> None:
        if self.subtitle_display_mode == "book":
            wrap_width, line_budget = self._book_layout_metrics()
            page, active_index = self.timeline.book_page_at(
                self.playback_state.position_ms,
                subtitle_offset_ms=self.subtitle_offset_ms,
                wrap_width=wrap_width,
                line_budget=line_budget,
                page_density=self.book_page_density,
            )
            renderable = self._build_book_subtitle_renderable(page, active_index)
            aligned = Align.left(renderable, vertical="top")
        else:
            cues, active_index = self.timeline.window_at(
                self.playback_state.position_ms,
                subtitle_offset_ms=self.subtitle_offset_ms,
                before_count=self.subtitle_context_before,
                after_count=self.subtitle_context_after,
            )
            renderable = self._build_window_subtitle_renderable(cues, active_index)
            aligned = Align.center(renderable, vertical="middle")
        self.query_one("#subtitle-panel", Static).update(aligned)

    def _refresh_progress(self) -> None:
        duration_ms = max(self.playback_state.duration_ms, self.metadata.duration_ms)
        position_ms = min(self.playback_state.position_ms, duration_ms or self.playback_state.position_ms)
        lines: list[str] = []
        chapter_line = self._chapter_progress_line(position_ms)
        if chapter_line is not None:
            lines.append(chapter_line)
            lines.append("")

        offset_label = f"{self.subtitle_offset_ms:+}ms"
        status_prefix = self._progress_status_prefix()
        time_label = f"{self._format_clock(position_ms)} / {self._format_clock(duration_ms)}"
        bar = self._build_overall_progress_bar(
            position_ms,
            duration_ms,
            status_prefix=status_prefix,
            time_label=time_label,
        )
        lines.append(
            f"{status_prefix}  {time_label}  {bar}"
        )
        lines.append(
            f"Subtitle size x{self.font_scale:.1f}  Offset {offset_label}  "
            f"{self._subtitle_progress_details()}"
        )
        self.query_one("#progress", Static).update("\n".join(lines))
        self.query_one("#help-bar", Static).update(self._help_bar_renderable())

    def _sync_chapter_selection(self) -> None:
        if not self.metadata.chapters:
            return
        if self._chapter_drawer_open:
            self._chapter_selection_index = self.query_one("#chapter-list", ListView).index
            return
        if 0 <= self.playback_state.chapter_index < len(self.metadata.chapters):
            self._chapter_selection_index = self.playback_state.chapter_index
            self._apply_drawer_selection()

    def _refresh_chapter_list(self) -> None:
        if not self._chapter_labels:
            return
        current_index = self.playback_state.chapter_index
        for chapter, label in zip(self.metadata.chapters, self._chapter_labels, strict=False):
            prefix = "▶ " if chapter.index == current_index else "  "
            label.update(f"{prefix}{chapter.title}")

    def _build_window_subtitle_renderable(self, cues: list, active_index: int | None) -> Group | Text:
        if not cues:
            return Text("...", justify="center", style="dim")

        styled_blocks: list[Text] = []
        for index, cue in enumerate(cues):
            is_active = active_index == index
            styled_blocks.append(
                self._format_cue_text(
                    cue.text,
                    is_active=is_active,
                )
            )
        return Group(*styled_blocks)

    def _format_cue_text(self, text: str, *, is_active: bool) -> Text:
        available_width = max(30, self.size.width - 10)
        scaled_width = max(18, int(available_width / self.font_scale))
        wrapped_lines: list[str] = []
        for line in text.splitlines() or [""]:
            wrapped_lines.extend(textwrap.wrap(line, width=scaled_width) or [""])
        vertical_padding = max(0, int(round((self.font_scale - 1.0) * 2)))
        padding = [""] * vertical_padding
        block_lines = padding + wrapped_lines + padding
        style = f"bold {self.help_accent_color} on #21414f" if is_active else "dim #9cb2c7"
        return Text("\n".join(block_lines), justify="center", style=style)

    def _build_book_subtitle_renderable(
        self,
        page: SubtitleBookPage | None,
        active_cue_index: int | None,
    ) -> Group | Text:
        if page is None or not page.lines:
            return Text("...", justify="left", style="dim")

        blocks: list[Text] = []
        for line in page.lines:
            blocks.append(self._format_book_line(line, active_cue_index))
        return Group(*blocks)

    def _format_book_line(
        self,
        line: SubtitleBookLine,
        active_cue_index: int | None,
    ) -> Text:
        if not line.fragments:
            return Text("")

        rendered = Text(justify="left")
        default_style = "#c7d5e0"
        active_style = f"bold {self.help_accent_color} on #21414f"
        for fragment in line.fragments:
            style = active_style if fragment.cue_index == active_cue_index else default_style
            rendered.append(fragment.text, style=style)
        return rendered

    def _subtitle_progress_details(self) -> str:
        if self.subtitle_display_mode == "book":
            return f"Mode book  Book density x{self.book_page_density:.1f}"
        return (
            f"Mode window  Ctx {self.subtitle_context_before}/{self.subtitle_context_after}"
        )

    def _book_layout_metrics(self) -> tuple[int, int]:
        subtitle_widget = self.query_one("#subtitle-panel", Static)
        base_width = max(24, subtitle_widget.size.width - 8)
        density_width = min(1.0, self.book_page_density)
        wrap_width = max(18, int((base_width * density_width) / self.font_scale))
        line_budget = max(4, int((max(6, subtitle_widget.size.height - 4)) / self.font_scale))
        return wrap_width, line_budget

    def _adjust_book_page_density(self, delta: float) -> None:
        self.book_page_density = min(1.3, max(0.7, round(self.book_page_density + delta, 1)))
        self._refresh_subtitle()
        self._refresh_progress()

    def _coerce_subtitle_display_mode(self, value: str) -> str:
        return value if value in {"window", "book"} else "window"

    def _help_bar_text(self) -> str:
        play_label = "Play" if self.playback_state.paused else "Pause"
        return (
            f"Space {play_label}  |  ←/→ Seek  |  ↑/↓ Chapter  |  "
            "c Chaps  |  m Mode  |  ? Help  |  q Quit"
        )

    def _help_bar_renderable(self) -> Text:
        play_label = "Play" if self.playback_state.paused else "Pause"
        return _build_key_value_row(
            [
                ("Space", play_label),
                ("←/→", "Seek"),
                ("↑/↓", "Chapter"),
                ("c", "Chaps"),
                ("m", "Mode"),
                ("?", "Help"),
                ("q", "Quit"),
            ],
            accent_color=self.help_accent_color,
        )

    def _apply_drawer_selection(self) -> None:
        if self._chapter_selection_index is None:
            return
        chapter_list = self.query_one("#chapter-list", ListView)
        if 0 <= self._chapter_selection_index < len(self.metadata.chapters):
            chapter_list.index = self._chapter_selection_index

    def _jump_to_selected_chapter(self, chapter_index: int | None) -> None:
        if chapter_index is None or not (0 <= chapter_index < len(self.metadata.chapters)):
            return
        self._chapter_selection_index = chapter_index
        chapter = self.metadata.chapters[chapter_index]
        self.playback_backend.seek_absolute(chapter.start_ms / 1000)
        self._poll_backend()

    def _resolved_chapter_index(self) -> int:
        if not self.metadata.chapters:
            return 0
        if 0 <= self.playback_state.chapter_index < len(self.metadata.chapters):
            return self.playback_state.chapter_index
        return 0

    def _progress_status_prefix(self) -> str:
        if self._backend_error_message is not None:
            return f"⚠️  {self._backend_error_message}"
        if self._backend_loading:
            return "⏳  Loading"
        if self.playback_state.paused:
            return "⏸️"
        return "▶️"

    def _chapter_progress_line(self, position_ms: int) -> str | None:
        if not self.metadata.chapters:
            return None
        chapter = self.metadata.chapters[self._resolved_chapter_index()]
        chapter_duration_ms = max(0, chapter.end_ms - chapter.start_ms)
        chapter_position_ms = min(max(0, position_ms - chapter.start_ms), chapter_duration_ms)
        time_label = self._format_chapter_progress_clock(chapter_position_ms, chapter_duration_ms)
        chapter_bar = self._build_chapter_progress_bar(
            chapter_position_ms,
            chapter_duration_ms,
            time_label=time_label,
        )
        return f"{time_label}  {chapter_bar}"

    def _build_progress_bar(self, position_ms: int, duration_ms: int) -> str:
        return self._render_progress_bar(position_ms, duration_ms, width=24)

    def _build_overall_progress_bar(
        self,
        position_ms: int,
        duration_ms: int,
        *,
        status_prefix: str,
        time_label: str,
    ) -> str:
        progress_widget = self.query_one("#progress", Static)
        main_pane = self.query_one("#main-pane")
        row_width = max(progress_widget.size.width, main_pane.size.width)
        available_width = max(10, row_width - len(status_prefix) - len(time_label) - 10)
        return self._render_progress_bar(position_ms, duration_ms, width=available_width)

    def _build_chapter_progress_bar(
        self,
        position_ms: int,
        duration_ms: int,
        *,
        time_label: str,
    ) -> str:
        progress_widget = self.query_one("#progress", Static)
        main_pane = self.query_one("#main-pane")
        row_width = max(progress_widget.size.width, main_pane.size.width)
        available_width = max(10, row_width - len(time_label) - 8)
        return self._render_progress_bar(position_ms, duration_ms, width=available_width)

    def _render_progress_bar(self, position_ms: int, duration_ms: int, *, width: int) -> str:
        width = max(8, width)
        if duration_ms <= 0:
            return "░" * width
        ratio = min(1.0, max(0.0, position_ms / duration_ms))
        filled = int(ratio * width)
        return "█" * filled + "░" * (width - filled)

    def _format_clock(self, value_ms: int) -> str:
        total_seconds = max(0, value_ms // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _format_chapter_progress_clock(self, position_ms: int, duration_ms: int) -> str:
        if position_ms < 3_600_000 and duration_ms < 3_600_000:
            return (
                f"{self._format_minutes_seconds(position_ms)} / "
                f"{self._format_minutes_seconds(duration_ms)}"
            )
        return f"{self._format_clock(position_ms)} / {self._format_clock(duration_ms)}"

    def _format_minutes_seconds(self, value_ms: int) -> str:
        total_seconds = max(0, value_ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"


class HelpModal(ModalScreen[None]):
    BINDINGS = [
        Binding("e", "edit_help_accent", "Accent", show=False),
        Binding("escape", "close_help", "Close", show=False),
        Binding("q", "close_help", "Close", show=False),
        Binding("question_mark", "close_help", "Close", show=False),
        Binding("h", "close_help", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-modal"):
            yield Static("Keyboard Help", id="help-title")
            yield Static(self._help_content_renderable(), id="help-content")

    def action_edit_help_accent(self) -> None:
        self.app.push_screen(
            AccentColorModal(self._app().help_accent_color),
            callback=self._apply_help_accent_color,
        )

    def action_close_help(self) -> None:
        self.dismiss()

    def _apply_help_accent_color(self, value: str | None) -> None:
        if value is None:
            return
        self._app().set_help_accent_color(value)
        self._refresh_content()

    def _app(self) -> AudiobookVizApp:
        return self.app  # type: ignore[return-value]

    def _help_content_renderable(self) -> Group:
        return _help_modal_renderable(self._app().help_accent_color)

    def _refresh_content(self) -> None:
        self.query_one("#help-content", Static).update(self._help_content_renderable())


class AccentColorModal(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, current_color: str) -> None:
        super().__init__()
        self.current_color = current_color

    def compose(self) -> ComposeResult:
        with Container(id="accent-color-modal"):
            yield Static("Set Help Accent Color", id="accent-color-title")
            yield Static(
                "Enter #RRGGBB or RRGGBB. Press Enter to apply or Esc to cancel.",
                id="accent-color-note",
            )
            yield Input(self.current_color, placeholder="#ffbd14", id="accent-color-input")
            yield Static("", id="accent-color-error")

    def on_mount(self) -> None:
        self.query_one("#accent-color-input", Input).focus()

    def on_input_changed(self, _: Input.Changed) -> None:
        self.query_one("#accent-color-error", Static).update("")

    def on_input_submitted(self, _: Input.Submitted) -> None:
        input_widget = self.query_one("#accent-color-input", Input)
        try:
            normalized = normalize_help_accent_color(input_widget.value)
        except ValueError:
            self.query_one("#accent-color-error", Static).update(
                "Enter a 6-digit RGB hex code, for example #ffbd14."
            )
            return
        self.dismiss(normalized)

    def action_cancel(self) -> None:
        self.dismiss(None)


def _build_key_value_row(items: list[tuple[str, str]], *, accent_color: str) -> Text:
    row = Text(justify="center")
    for index, (key, label) in enumerate(items):
        if index > 0:
            row.append("  |  ", style="dim #5c6c7b")
        row.append(key, style=f"bold {accent_color}")
        row.append(f" {label}", style="#d6e0e8")
    return row


def _help_modal_renderable(accent_color: str) -> Group:
    return Group(
        _section_title("Playback"),
        _help_line(
            [("space", "play/pause"), ("left/right", "seek -10s/+10s"), ("q", "quit")],
            accent_color=accent_color,
        ),
        Text(""),
        _section_title("Chapters"),
        _help_line(
            [
                ("c", "toggle drawer"),
                ("up/down", "chapter or drawer move"),
                ("enter", "jump to selected chapter"),
            ],
            accent_color=accent_color,
        ),
        Text(""),
        _section_title("Subtitle Controls"),
        _help_line([("m", "toggle mode"), ("+/-", "scale"), ("[ ]", "offset")], accent_color=accent_color),
        Text(""),
        _section_title("Window Mode"),
        _help_line(
            [("a/z", "context before +/-"), ("s/x", "context after +/-")],
            accent_color=accent_color,
        ),
        Text(""),
        _section_title("Book Mode"),
        _help_line([("a/s", "density +"), ("z/x", "density -")], accent_color=accent_color),
        Text(""),
        _section_title("Help"),
        _help_line([("e", "edit accent color"), ("esc", "close input dialog")], accent_color=accent_color),
        Text(f"  Current accent {accent_color}", style="#93a7b7"),
    )


def _section_title(title: str) -> Text:
    return Text(title, style="bold #8dc6ff")


def _help_line(items: list[tuple[str, str]], *, accent_color: str) -> Text:
    line = Text()
    line.append("  ")
    for index, (key, description) in enumerate(items):
        if index > 0:
            line.append("   ", style="#5c6c7b")
        line.append(key, style=f"bold {accent_color}")
        line.append(f" {description}", style="#d6e0e8")
    return line
