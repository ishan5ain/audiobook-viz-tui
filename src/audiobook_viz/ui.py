from __future__ import annotations

import textwrap
from pathlib import Path

from rich.align import Align
from rich.console import Group
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from audiobook_viz.models import MediaMetadata, PlaybackState, ResumeState
from audiobook_viz.playback import PlaybackBackend, PlaybackError
from audiobook_viz.state import StateStore
from audiobook_viz.subtitles import SubtitleTimeline


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
        padding: 1 2;
    }

    #status {
        height: 3;
        content-align: center middle;
        background: #1b2430;
        border: round #3a4a5e;
        margin-bottom: 1;
    }

    #chapter-title {
        height: 3;
        content-align: center middle;
        background: #162029;
        border: round #314557;
        margin-bottom: 1;
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
        height: 3;
        content-align: center middle;
        background: #1b2430;
        border: round #3a4a5e;
        margin-top: 1;
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
    """

    BINDINGS = [
        Binding("space", "toggle_playback", "Play/Pause"),
        Binding("left", "seek_backward", "-10s"),
        Binding("right", "seek_forward", "+10s"),
        Binding("up", "previous_chapter", "Prev Chapter"),
        Binding("down", "next_chapter", "Next Chapter"),
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
                yield Static(id="status")
                yield Static(id="chapter-title")
                yield Static(id="subtitle-panel")
                yield Static(id="progress")
            with Container(id="chapter-drawer", classes="hidden"):
                yield Label("Chapters", id="chapter-heading")
                yield ListView(id="chapter-list")
        yield Footer()

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
        self.subtitle_context_before = min(12, self.subtitle_context_before + 1)
        self._refresh_subtitle()
        self._refresh_progress()

    def action_decrease_context_before(self) -> None:
        self.subtitle_context_before = max(0, self.subtitle_context_before - 1)
        self._refresh_subtitle()
        self._refresh_progress()

    def action_increase_context_after(self) -> None:
        self.subtitle_context_after = min(12, self.subtitle_context_after + 1)
        self._refresh_subtitle()
        self._refresh_progress()

    def action_decrease_context_after(self) -> None:
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
                    subtitle_path=str(self.subtitle_path),
                ),
            )
        self.playback_backend.close()

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
        self._refresh_status()
        self._refresh_chapter_title()
        self._refresh_chapter_list()
        self._refresh_subtitle()
        self._refresh_progress()
        self._sync_chapter_selection()

    def _refresh_status(self) -> None:
        if self._backend_error_message is not None:
            self.query_one("#status", Static).update(f"Playback backend error: {self._backend_error_message}")
            return
        if self._backend_loading:
            self.query_one("#status", Static).update("Loading playback metadata...")
            return
        playback = "Paused" if self.playback_state.paused else "Playing"
        chapter_summary = (
            f"{len(self.metadata.chapters)} chapters" if self.metadata.chapters else "No chapters"
        )
        subtitle_name = self.subtitle_path.name
        self.query_one("#status", Static).update(
            f"{playback} | {chapter_summary} | Subtitles: {subtitle_name}"
        )

    def _refresh_chapter_title(self) -> None:
        if not self.metadata.chapters or self.playback_state.chapter_index < 0:
            text = "Chapter navigation unavailable"
        else:
            current_index = min(self.playback_state.chapter_index, len(self.metadata.chapters) - 1)
            chapter = self.metadata.chapters[current_index]
            text = f"Current chapter: {chapter.title}"
        self.query_one("#chapter-title", Static).update(text)

    def _refresh_subtitle(self) -> None:
        cues, active_index = self.timeline.window_at(
            self.playback_state.position_ms,
            subtitle_offset_ms=self.subtitle_offset_ms,
            before_count=self.subtitle_context_before,
            after_count=self.subtitle_context_after,
        )
        renderable = self._build_subtitle_renderable(cues, active_index)
        self.query_one("#subtitle-panel", Static).update(Align.center(renderable, vertical="middle"))

    def _refresh_progress(self) -> None:
        duration_ms = max(self.playback_state.duration_ms, self.metadata.duration_ms)
        position_ms = min(self.playback_state.position_ms, duration_ms or self.playback_state.position_ms)
        bar = self._build_progress_bar(position_ms, duration_ms)
        offset_label = f"{self.subtitle_offset_ms:+}ms"
        info = (
            f"{self._format_clock(position_ms)} / {self._format_clock(duration_ms)}  "
            f"{bar}  Subtitle size x{self.font_scale:.1f}  Offset {offset_label}  "
            f"Ctx {self.subtitle_context_before}/{self.subtitle_context_after}"
        )
        self.query_one("#progress", Static).update(info)

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

    def _build_subtitle_renderable(self, cues: list, active_index: int | None) -> Group | Text:
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
        style = "bold #ffffff on #21414f" if is_active else "dim #9cb2c7"
        return Text("\n".join(block_lines), justify="center", style=style)

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

    def _build_progress_bar(self, position_ms: int, duration_ms: int) -> str:
        if duration_ms <= 0:
            return "░" * 24
        width = 24
        ratio = min(1.0, max(0.0, position_ms / duration_ms))
        filled = int(ratio * width)
        return "█" * filled + "░" * (width - filled)

    def _format_clock(self, value_ms: int) -> str:
        total_seconds = max(0, value_ms // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
