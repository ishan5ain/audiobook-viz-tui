from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class UIConfig:
    poll_interval: float = 0.25
    seek_seconds: int = 10
    subtitle_offset_step_ms: int = 250
    sleep_timer_step_ms: int = 15 * 60 * 1000
    density_min: float = 0.7
    density_max: float = 1.3
    chapter_clock_threshold_ms: int = 3_600_000
    max_context: int = 12
    min_context: int = 0
    max_font_scale: float = 3.0
    min_font_scale: float = 1.0
    min_bar_width: int = 8
    min_progress_bar_width: int = 10
    min_wrap_width: int = 30
    min_font_scaled_width: int = 18
    min_line_budget: int = 4
    min_subtitle_panel_height: int = 6


_default_config = UIConfig()

# Backwards-compatible aliases for internal use during migration.
POLL_INTERVAL: Final = _default_config.poll_interval
SEEK_SECONDS: Final = _default_config.seek_seconds
SUBTITLE_OFFSET_STEP_MS: Final = _default_config.subtitle_offset_step_ms
SLEEP_TIMER_STEP_MS: Final = _default_config.sleep_timer_step_ms
DENSITY_MIN: Final = _default_config.density_min
DENSITY_MAX: Final = _default_config.density_max
CHAPTER_CLOCK_THRESHOLD_MS: Final = _default_config.chapter_clock_threshold_ms
MAX_CONTEXT: Final = _default_config.max_context
MIN_CONTEXT: Final = _default_config.min_context
MAX_FONT_SCALE: Final = _default_config.max_font_scale
MIN_FONT_SCALE: Final = _default_config.min_font_scale
MIN_BAR_WIDTH: Final = _default_config.min_bar_width
MIN_PROGRESS_BAR_WIDTH: Final = _default_config.min_progress_bar_width
MIN_WRAP_WIDTH: Final = _default_config.min_wrap_width
MIN_FONT_SCALED_WIDTH: Final = _default_config.min_font_scaled_width
MIN_LINE_BUDGET: Final = _default_config.min_line_budget
MIN_SUBTITLE_PANEL_HEIGHT: Final = _default_config.min_subtitle_panel_height

_HELP_BAR_ITEMS: list[tuple[str, str]] = [
    ("Space", "Play"),
    ("←/→", "Seek"),
    ("↑/↓", "Chapter"),
    ("c", "Chaps"),
    ("m", "Mode"),
    ("t", "Sleep"),
    ("?", "Help"),
    ("q", "Quit"),
]
