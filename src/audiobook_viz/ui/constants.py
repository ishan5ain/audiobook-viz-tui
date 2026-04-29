from __future__ import annotations

POLL_INTERVAL = 0.25
SEEK_SECONDS = 10
SUBTITLE_OFFSET_STEP_MS = 250
SLEEP_TIMER_STEP_MS = 15 * 60 * 1000

DENSITY_MIN = 0.7
DENSITY_MAX = 1.3

CHAPTER_CLOCK_THRESHOLD_MS = 3_600_000

MAX_CONTEXT = 12
MIN_CONTEXT = 0

MAX_FONT_SCALE = 3.0
MIN_FONT_SCALE = 1.0

MIN_BAR_WIDTH = 8
MIN_PROGRESS_BAR_WIDTH = 10
MIN_WRAP_WIDTH = 30
MIN_FONT_SCALED_WIDTH = 18
MIN_LINE_BUDGET = 4
MIN_SUBTITLE_PANEL_HEIGHT = 6
MIN_LINE_BUDGET_BOOK = 3
MIN_WRAP_WIDTH_BOOK = 18

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
