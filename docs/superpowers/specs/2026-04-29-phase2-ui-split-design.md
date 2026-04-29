# Phase 2: ui/ Package Split + SubtitleDisplayMode Enum

## Scope

Two changes to improve code organization and type safety:

1. Split `ui.py` (1080 lines) into a `ui/` package with focused modules
2. Introduce `SubtitleDisplayMode` enum to replace string-based mode checks

## Change 1: ui/ Package Split

### New file structure

```
src/audiobook_viz/
  ui/
    __init__.py    — re-exports AudiobookVizApp, HelpModal, SleepTimerModal
    constants.py   — POLL_INTERVAL, SEEK_SECONDS, SLEEP_TIMER_STEP_MS, density bounds, layout bounds, _HELP_BAR_ITEMS
    enums.py       — SubtitleDisplayMode enum
    rendering.py   — _build_key_value_row, _help_modal_renderable, _sleep_timer_modal_renderable, _section_title, _help_line
    modals.py      — HelpModal, AccentColorModal, SleepTimerModal
    app.py         — AudiobookVizApp (main class, ~500 lines)
  ui.py            — deleted
```

### Module responsibilities

**`constants.py`** — All named constants extracted in Phase 1. No internal imports.

**`enums.py`** — `SubtitleDisplayMode` enum (see Change 2 below).

**`rendering.py`** — Pure helper functions that build Rich text/renderable objects:
- `_build_key_value_row(items, accent_color)` — key-value row for help bar
- `_help_modal_renderable(accent_color)` — full help modal content
- `_sleep_timer_modal_renderable(accent_color, current_label, selected_label)` — sleep timer modal content
- `_section_title(title)` — section heading text
- `_help_line(items, accent_color)` — help line with styled keys

These have no dependencies on the app class or modal screens.

**`modals.py`** — Three `ModalScreen` subclasses:
- `HelpModal` — keyboard shortcuts display, accent color editing
- `AccentColorModal` — hex color input with validation
- `SleepTimerModal` — timer selection with countdown

These depend on `rendering.py` helpers and `colors.py` for normalization.

**`app.py`** — `AudiobookVizApp` class. Depends on:
- `constants.py` for constants
- `enums.py` for `SubtitleDisplayMode`
- `modals.py` for modal screens
- `rendering.py` for `_help_bar_renderable`

### `__init__.py`

```python
from audiobook_viz.ui.app import AudiobookVizApp
from audiobook_viz.ui.modals import HelpModal, SleepTimerModal

__all__ = ["AudiobookVizApp", "HelpModal", "SleepTimerModal"]
```

External imports (`from audiobook_viz.ui import ...`) remain unchanged.

### Files that change

| File | Change |
|---|---|
| `src/audiobook_viz/ui.py` | Deleted |
| `src/audiobook_viz/ui/__init__.py` | Created |
| `src/audiobook_viz/ui/constants.py` | Created |
| `src/audiobook_viz/ui/enums.py` | Created |
| `src/audiobook_viz/ui/rendering.py` | Created |
| `src/audiobook_viz/ui/modals.py` | Created |
| `src/audiobook_viz/ui/app.py` | Created |
| `src/audiobook_viz/cli.py` | No changes (imports via `__init__.py` unchanged) |
| `tests/test_ui.py` | No import changes (imports via `__init__.py` unchanged) |

## Change 2: SubtitleDisplayMode Enum

### Enum definition

```python
class SubtitleDisplayMode(Enum):
    WINDOW = auto()
    BOOK = auto()
```

Plain `Enum` (not `str, Enum`). String comparisons replaced with explicit enum member comparisons.

### ResumeState changes

```python
@dataclass(frozen=True, slots=True)
class ResumeState:
    ...
    subtitle_display_mode: SubtitleDisplayMode  # was: str

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["subtitle_display_mode"] = self.subtitle_display_mode.value  # "window" or "book"
        return d

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ResumeState":
        ...
        display_mode = str(data.get("subtitle_display_mode", "window"))
        try:
            subtitle_display_mode = SubtitleDisplayMode(display_mode)
        except ValueError:
            subtitle_display_mode = SubtitleDisplayMode.WINDOW
        return cls(
            ...
            subtitle_display_mode=subtitle_display_mode,
            ...
        )
```

- Existing JSON state files stored as `"window"` / `"book"` continue to load correctly
- Invalid values fall back to `WINDOW`
- Serialization writes `.value` (string), not `.name`

### StartupConfig change

```python
@dataclass(frozen=True, slots=True)
class StartupConfig:
    ...
    subtitle_display_mode: SubtitleDisplayMode  # was: str
```

Updated in `_resolve_startup_config()`:
```python
initial_subtitle_display_mode = (
    resume_state.subtitle_display_mode if resume_state else SubtitleDisplayMode.WINDOW
)
```

### AudiobookVizApp changes

- `self.subtitle_display_mode: str` → `SubtitleDisplayMode`
- `_coerce_subtitle_display_mode(value: str) -> str` → removed (not needed with enum)
- `__init__` parameter: `initial_subtitle_display_mode: str = "window"` → `initial_subtitle_display_mode: SubtitleDisplayMode = SubtitleDisplayMode.WINDOW`
- All comparisons updated:
  - `self.subtitle_display_mode == "book"` → `self.subtitle_display_mode == SubtitleDisplayMode.BOOK`
  - `self.subtitle_display_mode == "window"` → `self.subtitle_display_mode == SubtitleDisplayMode.WINDOW`
  - `"window", "book"` → `SubtitleDisplayMode.WINDOW, SubtitleDisplayMode.BOOK`

### Test changes

- `test_book_mode_toggle_and_density_controls`: `app.subtitle_display_mode == "book"` → `== SubtitleDisplayMode.BOOK`
- `test_book_mode_toggle_and_density_controls`: `app.subtitle_display_mode == "window"` → `== SubtitleDisplayMode.WINDOW`
- `_run_book_mode_paging_regression_test`: `initial_subtitle_display_mode="book"` → `initial_subtitle_display_mode=SubtitleDisplayMode.BOOK`

## Dependencies

Both changes are tightly coupled — the enum is introduced as part of the package split. They must be applied together.

## Risk Assessment

- **ui/ split**: Zero risk. Pure extraction with no logic changes.
- **SubtitleDisplayMode enum**: Low risk. All comparisons are simple equality checks. Serialization handles backward compatibility. Tests need minor assertion updates.

## Success Criteria

- All 25 tests pass without modification (except enum assertion updates)
- No behavioral changes
- `from audiobook_viz.ui import AudiobookVizApp, HelpModal, SleepTimerModal` works unchanged
- No inline `"book"` / `"window"` string comparisons remain in ui code
