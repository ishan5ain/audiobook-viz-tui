from __future__ import annotations

import time
from pathlib import Path

from audiobook_viz.models import ResumeState
from audiobook_viz.state import StateStore, media_identity


def test_state_store_round_trip(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    store = StateStore(tmp_path / "state")
    resume_state = ResumeState(
        position_ms=1000,
        chapter_index=2,
        font_scale=1.4,
        subtitle_offset_ms=-250,
        subtitle_context_before=4,
        subtitle_context_after=2,
        subtitle_path="/tmp/book.srt",
    )

    store.save(audio_path, resume_state)
    loaded = store.load(audio_path)

    assert loaded == resume_state


def test_resume_state_loads_defaults_for_older_state_shape() -> None:
    resume_state = ResumeState.from_dict(
        {
            "position_ms": 1000,
            "chapter_index": 1,
            "font_scale": 1.1,
            "subtitle_offset_ms": 0,
            "subtitle_path": "/tmp/book.srt",
        }
    )

    assert resume_state.subtitle_context_before == 3
    assert resume_state.subtitle_context_after == 3


def test_media_identity_changes_when_file_changes(tmp_path: Path) -> None:
    audio_path = tmp_path / "book.m4a"
    audio_path.write_bytes(b"audio")
    first_identity = media_identity(audio_path)
    time.sleep(0.001)
    audio_path.write_bytes(b"audio-updated")

    assert media_identity(audio_path) != first_identity
