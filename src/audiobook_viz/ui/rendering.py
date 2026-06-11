from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.align import Align
from rich.console import Group, RenderableType
from rich.text import Text
from textual.widgets import Static

from audiobook_viz.subtitles import SubtitleBookPage, SubtitleBookLine, SubtitleTimeline
from audiobook_viz.ui.constants import _default_config
from audiobook_viz.ui.enums import SubtitleDisplayMode


@dataclass(frozen=True)
class SubtitleViewState:
    font_scale: float
    book_page_density: float
    help_accent_color: str
    subtitle_display_mode: SubtitleDisplayMode
    subtitle_offset_ms: int
    subtitle_context_before: int
    subtitle_context_after: int
    panel_width: int
    panel_height: int


class SubtitleRenderer:
    def render(
        self,
        timeline: SubtitleTimeline,
        position_ms: int,
        state: SubtitleViewState,
    ) -> RenderableType:
        if state.subtitle_display_mode == SubtitleDisplayMode.BOOK:
            wrap_width, line_budget = _book_layout_metrics(
                state.panel_width,
                state.panel_height,
                state.book_page_density,
                state.font_scale,
            )
            page, active_index = timeline.book_page_at(
                position_ms,
                subtitle_offset_ms=state.subtitle_offset_ms,
                wrap_width=wrap_width,
                line_budget=line_budget,
                page_density=state.book_page_density,
            )
            renderable = self._build_book_subtitle_renderable(page, active_index, state.help_accent_color)
            aligned = Align.left(renderable, vertical="top")
        else:
            cues, active_index = timeline.window_at(
                position_ms,
                subtitle_offset_ms=state.subtitle_offset_ms,
                before_count=state.subtitle_context_before,
                after_count=state.subtitle_context_after,
            )
            renderable = self._build_window_subtitle_renderable(
                cues, active_index, state.font_scale, state.help_accent_color
            )
            aligned = Align.center(renderable, vertical="middle")
        return aligned

    def _build_window_subtitle_renderable(
        self,
        cues: list,
        active_index: int | None,
        font_scale: float,
        accent_color: str,
    ) -> Group | Text:
        if not cues:
            return Text("...", justify="center", style="dim")

        styled_blocks: list[Text] = []
        for index, cue in enumerate(cues):
            is_active = active_index == index
            styled_blocks.append(
                self._format_cue_text(
                    cue.text,
                    font_scale=font_scale,
                    is_active=is_active,
                    accent_color=accent_color,
                )
            )
        return Group(*styled_blocks)

    def _format_cue_text(self, text: str, *, font_scale: float, is_active: bool, accent_color: str) -> Text:
        available_width = max(_default_config.min_wrap_width, 80 - 10)
        scaled_width = max(_default_config.min_font_scaled_width, int(available_width / font_scale))
        wrapped_lines: list[str] = []
        for line in text.splitlines() or [""]:
            wrapped_lines.extend(textwrap.wrap(line, width=scaled_width) or [""])
        vertical_padding = max(0, int(round((font_scale - 1.0) * 2)))
        padding = [""] * vertical_padding
        block_lines = padding + wrapped_lines + padding
        style = f"bold {accent_color} on #21414f" if is_active else "dim #9cb2c7"
        return Text("\n".join(block_lines), justify="center", style=style)

    def _build_book_subtitle_renderable(
        self,
        page: SubtitleBookPage | None,
        active_cue_index: int | None,
        accent_color: str,
    ) -> Group | Text:
        if page is None or not page.lines:
            return Text("...", justify="left", style="dim")

        blocks: list[Text] = []
        for line in page.lines:
            blocks.append(self._format_book_line(line, active_cue_index, accent_color))
        return Group(*blocks)

    def _format_book_line(
        self,
        line: SubtitleBookLine,
        active_cue_index: int | None,
        accent_color: str,
    ) -> Text:
        if not line.fragments:
            return Text("")

        rendered = Text(justify="left")
        default_style = "#c7d5e0"
        active_style = f"bold {accent_color} on #21414f"
        for fragment in line.fragments:
            style = active_style if fragment.cue_index == active_cue_index else default_style
            rendered.append(fragment.text, style=style)
        return rendered


def _book_layout_metrics(panel_width: int, panel_height: int, page_density: float, font_scale: float) -> tuple[int, int]:
    base_width = max(24, panel_width - 8)
    density_width = min(1.0, page_density)
    wrap_width = max(18, int((base_width * density_width) / font_scale))
    panel_height = max(_default_config.min_subtitle_panel_height, panel_height - 4)
    line_budget = max(_default_config.min_line_budget, int(panel_height / font_scale))
    return wrap_width, line_budget


def _build_key_value_row(
    items: list[tuple[str, str]],
    *,
    accent_color: str,
) -> Text:
    row = Text(justify="center")
    for index, (key, label) in enumerate(items):
        if index > 0:
            row.append("  |  ", style="dim #5c6c7b")
        row.append(key, style=f"bold {accent_color}")
        row.append(f" {label}", style="#d6e0e8")
    return row


def _section_title(title: str) -> Text:
    return Text(title, style="bold #8dc6ff")


def _help_line(items: list[tuple[str, str]], *, accent_color: str) -> Text:
    line = Text()
    line.append("  ")
    for index, (key, description) in enumerate(items):
        if index > 0:
            line.append("  ", style="#5c6c7b")
        line.append(key, style=f"bold {accent_color}")
        line.append(f" {description}", style="#d6e0e8")
    return line


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
        _section_title("Sleep Timer"),
        _help_line([("t", "open sleep timer")], accent_color=accent_color),
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


def _sleep_timer_modal_renderable(
    *, accent_color: str, current_label: str, selected_label: str
) -> Group:
    return Group(
        _section_title("Current"),
        Text(f"  {current_label}", style="#d6e0e8"),
        Text(""),
        _section_title("Selected"),
        Text(
            f"  {selected_label}",
            style=(f"bold {accent_color}" if selected_label != "Off" else "#d6e0e8"),
        ),
        Text(""),
        _section_title("Controls"),
        _help_line(
            [("up/down", "+/- 15 min"), ("space", "start"), ("esc", "close")],
            accent_color=accent_color,
        ),
        Text(""),
        Text("  Use down to zero to cancel the active timer.", style="#93a7b7"),
    )
