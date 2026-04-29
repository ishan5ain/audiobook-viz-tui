from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import Reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from audiobook_viz.colors import normalize_help_accent_color
from audiobook_viz.ui.constants import POLL_INTERVAL, SLEEP_TIMER_STEP_MS
from audiobook_viz.ui.rendering import _help_modal_renderable, _sleep_timer_modal_renderable

if TYPE_CHECKING:
    from audiobook_viz.ui.app import AudiobookVizApp
    from rich.console import Group


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

    def _app(self) -> "AudiobookVizApp":
        return self.app  # type: ignore[return-value]

    def _help_content_renderable(self) -> "Group":
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
            yield Static("Set Accent Color", id="accent-color-title")
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


class SleepTimerModal(ModalScreen[None]):
    BINDINGS = [
        Binding("up", "increase_sleep_timer", "Increase", show=False),
        Binding("down", "decrease_sleep_timer", "Decrease", show=False),
        Binding("space", "apply_sleep_timer", "Start", show=False),
        Binding("t", "close_sleep_timer", "Close", show=False),
        Binding("escape", "close_sleep_timer", "Close", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.selected_duration_ms = 0
        self._refresh_handle: Reactive | None = None

    def compose(self) -> ComposeResult:
        with Container(id="sleep-timer-modal"):
            yield Static("Sleep Timer", id="sleep-timer-title")
            yield Static(id="sleep-timer-content")

    def on_mount(self) -> None:
        self.selected_duration_ms = self._app().sleep_timer_remaining_ms or 0
        self._refresh_content()
        self._refresh_handle = self.set_interval(POLL_INTERVAL, self._refresh_content)

    def action_increase_sleep_timer(self) -> None:
        self.selected_duration_ms += SLEEP_TIMER_STEP_MS
        self._refresh_content()

    def action_decrease_sleep_timer(self) -> None:
        self.selected_duration_ms = max(0, self.selected_duration_ms - SLEEP_TIMER_STEP_MS)
        if self.selected_duration_ms == 0:
            self._app().cancel_sleep_timer()
        self._refresh_content()

    def action_apply_sleep_timer(self) -> None:
        if self.selected_duration_ms > 0:
            self._app().set_sleep_timer_duration_ms(self.selected_duration_ms)
        self.dismiss()

    def action_close_sleep_timer(self) -> None:
        self.dismiss()

    def _app(self) -> "AudiobookVizApp":
        return self.app  # type: ignore[return-value]

    def _refresh_content(self) -> None:
        self.query_one("#sleep-timer-content", Static).update(
            _sleep_timer_modal_renderable(
                accent_color=self._app().help_accent_color,
                current_label=self._app()._sleep_timer_current_state_label(),
                selected_label=(
                    "Off"
                    if self.selected_duration_ms <= 0
                    else self._app()._format_sleep_timer_duration(self.selected_duration_ms)
                ),
            )
        )
