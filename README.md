# Audiobook Viz TUI

Textual-based terminal UI for playing chapterized `.m4a` audiobooks with synchronized `.srt` or `.vtt` subtitles.

The current build is focused on long-form audiobook playback:
- embedded chapter metadata via `ffprobe`
- audio playback via `mpv` JSON IPC
- resume state persistence per media file
- volatile sleep timer with playback-aware countdown
- subtitle offset adjustment
- switchable subtitle rendering modes:
  - `window` mode with configurable cue counts before and after the active cue
  - `book` mode with merged paragraph-like text, fixed-page reading flow, and persisted page density
- chapter-local progress row with adaptive progress bar and chapter-relative timing
- chapter drawer with explicit selection and jump behavior

## Current Status

This is an early but usable prototype.

Implemented today:
- single audiobook + single subtitle file per launch
- chapter navigation and chapter drawer
- playback controls, relative seeks, and subtitle offset
- sleep timer with modal controls and auto-pause on expiry
- subtitle rendering modes for both cue-window and book-style reading
- chapter-local and whole-book progress display
- persisted resume state for playback position, chapter, subtitle settings, subtitle mode, book density, and accent color
- automated test coverage for playback, subtitles, UI behavior, CLI parsing, bootstrap, subtitle layout, subtitle rendering, and sleep timer state machine

Known constraints:
- requires external `mpv`
- requires external `ffprobe`
- book-mode paragraph grouping is heuristic-driven and based on cue gaps / text size, not full sentence parsing
- "font size" is a terminal-safe display scaling approximation, not a real font-size change

## Requirements

- Python `>= 3.13`
- `mpv` available on `PATH`
- `ffprobe` available on `PATH`

On macOS with Homebrew, a typical runtime setup is:

```bash
brew install mpv ffmpeg
```

## Install

From the repo root:

```bash
python3 -m pip install -e .
```

If you use `pyenv` and the `audiobook-viz` command is not found after install, run:

```bash
pyenv rehash
```

## Usage

Basic launch:

```bash
audiobook-viz /path/to/book.m4a /path/to/book.vtt
```

With custom subtitle offset and context window:

```bash
audiobook-viz /path/to/book.m4a /path/to/book.srt \
  --subtitle-offset-ms 500 \
  --subtitle-context-before 4 \
  --subtitle-context-after 5 \
  --state-dir .state
```

CLI arguments:
- `audio_path`: path to a chapterized `.m4a`
- `subtitle_path`: path to a `.srt` or `.vtt`
- `--subtitle-offset-ms`: startup subtitle timing offset in milliseconds
- `--subtitle-context-before`: number of subtitle cues shown before the active cue
- `--subtitle-context-after`: number of subtitle cues shown after the active cue
- `--no-resume`: disable persisted resume state
- `--state-dir`: override the resume-state directory for the current run

## Subtitle Modes

The app uses the `SubtitleDisplayMode` enum (`src/audiobook_viz/ui/enums.py`) with two modes switchable at runtime via `m`:

- `window` mode:
  - shows the active cue with configurable cue context before and after it
  - keeps the active cue visually centered
- `book` mode:
  - merges adjacent short Whisper cues into paragraph-like text via the two-stage pipeline in `SubtitleTimeline` and `BookLayoutEngine`
  - **Stage 1**: cues are grouped into paragraphs based on gap heuristics (cue spacing, character/word thresholds)
  - **Stage 2**: paragraphs are wrapped into visual lines and then sliced into pages by `BookLayoutEngine` (with cached layouts keyed by wrap width, line budget, and page density)
  - fills the subtitle pane with a fixed "page" of wrapped lines
  - moves the highlight from top to bottom as playback advances
  - turns the page when the active cue would move beyond the visible page

Mode, subtitle offset, display scaling, context counts, book-page density, and accent color are all restored from resume state by default.

## Controls

Playback and navigation:
- `space`: play / pause
- `left` / `right`: seek `-10s` / `+10s`
- `up` / `down`: previous / next chapter when the drawer is hidden
- `t`: open the sleep timer modal
- `c`: toggle chapter drawer
- `enter`: jump to the selected chapter when the drawer is open
- `q`: quit

Subtitle controls:
- `m`: toggle subtitle mode between `window` and `book`
- `+` / `-`: subtitle display scaling up / down
- `[` / `]`: subtitle offset `-250ms` / `+250ms`
- `a` / `z`: in `window` mode, increase / decrease subtitle context-before count
- `s` / `x`: in `window` mode, increase / decrease subtitle context-after count
- `a` / `s`: in `book` mode, increase page density
- `z` / `x`: in `book` mode, decrease page density

Chapter drawer behavior:
- when the drawer is open, `up` / `down` move the drawer selection
- the currently playing chapter remains marked separately from the selected row

Help customization:
- while the keyboard help modal is open, press `e` to edit the accent color
- enter `#RRGGBB` or `RRGGBB`; the app normalizes it, applies it to help UI accents and the active subtitle cue, and restores it on resume

Sleep timer:
- press `t` to open the sleep timer modal
- `up` / `down` adjust the selected duration in `15min` increments
- `space` starts or resets the selected timer; counting only happens while audio is playing
- decrease the selected timer to `0` to cancel the active timer
- sleep timer state is not restored on resume

Progress display:
- top row: chapter-relative progress with chapter-local position / duration and an adaptive progress bar
- bottom row: whole-book playback status, global progress bar, optional sleep-timer status, subtitle scale, offset, and mode-specific subtitle info

## Development

Run tests:

```bash
pytest -q
```

Quick import/bytecode sanity check:

```bash
python3 -m compileall src tests
```

Project layout:
- `src/audiobook_viz/`: application code
  - `cli.py` — argument parsing, entry point (delegates to `bootstrap()`)
  - `bootstrap.py` — startup pipeline: validates paths, probes media, parses subtitles, resolves config from args/resume state, wires up `MpvBackend` and `AudiobookVizApp`
  - `models.py` — core dataclasses: `StartupConfig`, `Chapter`, `MediaMetadata`, `SubtitleCue`, `PlaybackState`, `ResumeState`
  - `playback.py` — `MpvBackend` (mpv JSON IPC), `PlaybackConfig`, `PlaybackBackend` protocol
  - `subtitle_layout.py` — `BookLayoutEngine` (wrapped line pagination with cached layouts)
  - `subtitles.py` — `SubtitleConfig`, `SubtitleTimeline`, `.srt`/`.vtt` parsing, book-mode data types (`SubtitleBookPage`, `SubtitleParagraph`, etc.)
  - `media.py` — ffprobe metadata extraction
  - `state.py` — resume state persistence
  - `colors.py` — accent color normalization
  - `ui/` — Textual UI layer
    - `app.py` — `AudiobookVizApp` main widget (orchestrates rendering, delegates to subsystems)
    - `constants.py` — `UIConfig` dataclass with backwards-compatible constant aliases
    - `enums.py` — `SubtitleDisplayMode` enum (`WINDOW` / `BOOK`)
    - `rendering.py` — `SubtitleRenderer` (subtitle widget rendering, extracted from `app.py`)
    - `sleep_timer.py` — `SleepTimer` state machine (off / running / expired) with playback-aware countdown
    - `modals.py` — `SleepTimerModal`, `HelpModal`
- `tests/`: test suite
  - `test_bootstrap.py` — integration tests for the bootstrap pipeline
  - `test_sleep_timer.py` — state-machine tests for `SleepTimer`
  - `test_subtitle_layout.py` — tests for `BookLayoutEngine` pagination
  - `test_subtitle_rendering.py` — unit tests for `SubtitleRenderer`
  - (plus existing test files for playback, CLI, subtitles, UI, state)
- `.state/`: optional local runtime state when you pass `--state-dir .state`

## Future Work

Useful next iterations:
- better paragraph heuristics for Whisper subtitle merging and page composition
- richer chapter drawer styling and search
- better startup/loading feedback around `mpv` media readiness
- packaging and release workflow for easier installation
- subtitle theme customization and more display modes
- bookmark support for long audiobooks
- better handling of missing or inconsistent embedded chapter metadata
