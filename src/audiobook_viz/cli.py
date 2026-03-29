from __future__ import annotations

import argparse
from pathlib import Path

from audiobook_viz.colors import DEFAULT_HELP_ACCENT_COLOR
from audiobook_viz.media import MediaProbeError, probe_media_metadata
from audiobook_viz.playback import MpvBackend, PlaybackError, ensure_mpv_available
from audiobook_viz.state import StateStore
from audiobook_viz.subtitles import SubtitleParseError, SubtitleTimeline, parse_subtitle_file
from audiobook_viz.ui import AudiobookVizApp


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
        audio_path = _validate_audio_path(args.audio_path)
        subtitle_path = _validate_subtitle_path(args.subtitle_path)
        ensure_mpv_available()
        metadata = probe_media_metadata(audio_path)
        cues = parse_subtitle_file(subtitle_path)
        timeline = SubtitleTimeline(cues)
        state_store = None if args.no_resume else StateStore(args.state_dir)
        resume_state = None if state_store is None else state_store.load(audio_path)
        initial_offset_ms = (
            args.subtitle_offset_ms
            if args.subtitle_offset_ms is not None
            else (resume_state.subtitle_offset_ms if resume_state else 0)
        )
        initial_font_scale = resume_state.font_scale if resume_state else 1.0
        initial_context_before = (
            max(0, args.subtitle_context_before)
            if args.subtitle_context_before is not None
            else (resume_state.subtitle_context_before if resume_state else 3)
        )
        initial_context_after = (
            max(0, args.subtitle_context_after)
            if args.subtitle_context_after is not None
            else (resume_state.subtitle_context_after if resume_state else 3)
        )
        initial_subtitle_display_mode = (
            resume_state.subtitle_display_mode if resume_state else "window"
        )
        initial_book_page_density = resume_state.book_page_density if resume_state else 1.0
        initial_help_accent_color = (
            resume_state.help_accent_color if resume_state else DEFAULT_HELP_ACCENT_COLOR
        )
        start_position_ms = resume_state.position_ms if resume_state else None
        backend = MpvBackend(
            audio_path,
            start_position_ms=start_position_ms,
            initial_duration_ms=metadata.duration_ms,
        )
        app = AudiobookVizApp(
            metadata=metadata,
            timeline=timeline,
            playback_backend=backend,
            subtitle_path=subtitle_path,
            state_store=state_store,
            resume_enabled=not args.no_resume,
            initial_font_scale=initial_font_scale,
            initial_subtitle_offset_ms=initial_offset_ms,
            initial_subtitle_context_before=initial_context_before,
            initial_subtitle_context_after=initial_context_after,
            initial_subtitle_display_mode=initial_subtitle_display_mode,
            initial_book_page_density=initial_book_page_density,
            initial_help_accent_color=initial_help_accent_color,
        )
    except (MediaProbeError, PlaybackError, SubtitleParseError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
        return 2

    try:
        app.run()
    finally:
        app.shutdown_player()
    return 0


def _validate_audio_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() != ".m4a":
        raise ValueError("audio_path must point to a .m4a file.")
    if not resolved.is_file():
        raise ValueError(f"audio file not found: {resolved}")
    return resolved


def _validate_subtitle_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() not in {".srt", ".vtt"}:
        raise ValueError("subtitle_path must point to a .srt or .vtt file.")
    if not resolved.is_file():
        raise ValueError(f"subtitle file not found: {resolved}")
    return resolved
