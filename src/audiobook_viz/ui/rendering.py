from __future__ import annotations

from rich.console import Group
from rich.text import Text


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
