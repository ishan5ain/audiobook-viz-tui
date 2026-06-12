from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from audiobook_viz.cli import build_parser
from audiobook_viz.bootstrap import bootstrap
from audiobook_viz.models import MediaMetadata, Chapter
from audiobook_viz.playback import PlaybackState
from audiobook_viz.subtitles import SubtitleTimeline
from audiobook_viz.ui.enums import SubtitleDisplayMode


class FakeBackend:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.init_args = args
        self.init_kwargs = kwargs
        self.state = PlaybackState(
            position_ms=0,
            duration_ms=60_000,
            paused=True,
            chapter_index=0,
        )
        self.closed = False

    def play_pause(self) -> None: ...
    def seek_relative(self, seconds: int) -> None: ...
    def seek_absolute(self, seconds: float) -> None: ...
    def next_chapter(self) -> None: ...
    def previous_chapter(self) -> None: ...
    def set_pause(self, paused: bool) -> None: ...
    def get_state(self) -> PlaybackState: ...
    def is_state_ready(self) -> bool: ...
    def close(self) -> None:
        self.closed = True


def _fake_metadata(audio_path: Path) -> MediaMetadata:
    return MediaMetadata(
        audio_path=audio_path,
        duration_ms=120_000,
        chapters=[
            Chapter(index=0, title="One", start_ms=0, end_ms=60_000),
            Chapter(index=1, title="Two", start_ms=60_000, end_ms=120_000),
        ],
    )


def test_bootstrap_returns_app_with_fake_dependencies(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello world\n",
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args([str(audio_path), str(subtitle_path)])

    fake_metadata = _fake_metadata(audio_path)

    with patch("audiobook_viz.bootstrap.probe_media_metadata", return_value=fake_metadata), \
         patch("audiobook_viz.bootstrap.MpvBackend", FakeBackend), \
         patch("audiobook_viz.bootstrap.ensure_mpv_available"):
        app = bootstrap(args)

    assert app.metadata == fake_metadata
    assert isinstance(app.playback_backend, FakeBackend)
    assert app.subtitle_path == subtitle_path
    assert app.subtitle_display_mode == SubtitleDisplayMode.WINDOW
    assert app.font_scale == pytest.approx(1.0)
    assert app.subtitle_offset_ms == 0
    assert app.book_page_density == pytest.approx(1.0)
    assert app.help_accent_color == "#ffbd14"
    assert app.playback_state.position_ms == 0
    assert app.playback_state.duration_ms == 120_000


def test_bootstrap_propagates_media_probe_error(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello world\n",
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args([str(audio_path), str(subtitle_path)])

    with patch("audiobook_viz.bootstrap.probe_media_metadata", side_effect=Exception("boom")):
        with pytest.raises(Exception, match="boom"):
            bootstrap(args)


def test_bootstrap_loads_resume_state_when_enabled(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    subtitle_path = tmp_path / "book.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello world\n",
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args([str(audio_path), str(subtitle_path)])

    fake_metadata = _fake_metadata(audio_path)
    fake_backend = FakeBackend()

    with patch("audiobook_viz.bootstrap.probe_media_metadata", return_value=fake_metadata), \
         patch("audiobook_viz.bootstrap.MpvBackend", return_value=fake_backend), \
         patch("audiobook_viz.bootstrap.ensure_mpv_available"), \
         patch("audiobook_viz.bootstrap.StateStore") as mock_state_store:
        store = MagicMock()
        store.load.return_value = None
        mock_state_store.return_value = store
        app = bootstrap(args)

    assert app.font_scale == pytest.approx(1.0)
    assert app.subtitle_context_before == 3
    assert app.subtitle_context_after == 3
