from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from audiobook_viz.bootstrap import bootstrap
from audiobook_viz.media import MediaProbeError
from audiobook_viz.models import StartupConfig
from audiobook_viz.playback import PlaybackError
from audiobook_viz.subtitles import SubtitleParseError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audiobook-viz",
        description="Chapterized audiobook TUI player with live subtitle rendering.",
    )
    parser.add_argument("audio_path", type=Path)
    parser.add_argument("subtitle_path", type=Path)
    parser.add_argument("--subtitle-offset-ms", type=int, default=None)
    parser.add_argument(
        "--subtitle-context-before",
        type=int,
        default=None,
        help="Number of subtitle cues to show before the active cue (default: 3).",
    )
    parser.add_argument(
        "--subtitle-context-after",
        type=int,
        default=None,
        help="Number of subtitle cues to show after the active cue (default: 3).",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--state-dir", type=Path, default=None)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        app = bootstrap(args)
    except (MediaProbeError, PlaybackError, SubtitleParseError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
        return 2

    try:
        app.run()
    finally:
        app.shutdown_player()
    return 0
