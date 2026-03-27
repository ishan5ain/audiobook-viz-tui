# Audiobook Viz TUI

Textual-based terminal UI for playing chapterized `.m4a` audiobooks with synchronized `.srt` or `.vtt` subtitles.

The current build is focused on long-form audiobook playback:
- embedded chapter metadata via `ffprobe`
- audio playback via `mpv` JSON IPC
- resume state persistence per media file
- subtitle offset adjustment
- contextual subtitle window with configurable cue counts before and after the active cue
- chapter drawer with explicit selection and jump behavior

## Current Status

This is an early but usable prototype.

Implemented today:
- single audiobook + single subtitle file per launch
- chapter navigation and chapter drawer
- playback controls, relative seeks, and subtitle offset
- contextual subtitle rendering around the active cue
- persisted resume state for playback position, chapter, subtitle settings, and context counts
- automated test coverage for playback, subtitles, UI behavior, CLI parsing, and state loading

Known constraints:
- requires external `mpv`
- requires external `ffprobe`
- subtitle context is cue-based, not sentence-merged
- “font size” is a terminal-safe display scaling approximation, not a real font-size change

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

## Controls

Playback and navigation:
- `space`: play / pause
- `left` / `right`: seek `-10s` / `+10s`
- `up` / `down`: previous / next chapter when the drawer is hidden
- `c`: toggle chapter drawer
- `enter`: jump to the selected chapter when the drawer is open
- `q`: quit

Subtitle controls:
- `+` / `-`: subtitle display scaling up / down
- `[` / `]`: subtitle offset `-250ms` / `+250ms`
- `a` / `z`: increase / decrease subtitle context-before count
- `s` / `x`: increase / decrease subtitle context-after count

Chapter drawer behavior:
- when the drawer is open, `up` / `down` move the drawer selection
- the currently playing chapter remains marked separately from the selected row

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
- `tests/`: test suite
- `.state/`: optional local runtime state when you pass `--state-dir .state`

## Future Work

Useful next iterations:
- merged-phrase subtitle mode for very short Whisper cues
- richer chapter drawer styling and search
- better startup/loading feedback around `mpv` media readiness
- packaging and release workflow for easier installation
- subtitle theme customization and more display modes
- bookmark support for long audiobooks
- better handling of missing or inconsistent embedded chapter metadata
