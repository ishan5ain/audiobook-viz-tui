from __future__ import annotations

from pathlib import Path

from audiobook_viz.media import parse_ffprobe_payload


def test_parse_ffprobe_payload_builds_chapters() -> None:
    payload = {
        "format": {"duration": "120.25"},
        "chapters": [
            {"start_time": "0.0", "end_time": "30.0", "tags": {"title": "Intro"}},
            {"start_time": "30.0", "end_time": "120.25", "tags": {}},
        ],
    }

    metadata = parse_ffprobe_payload(payload, Path("/tmp/book.m4a"))

    assert metadata.duration_ms == 120250
    assert len(metadata.chapters) == 2
    assert metadata.chapters[0].title == "Intro"
    assert metadata.chapters[1].title == "Chapter 2"
    assert metadata.chapters[1].end_ms == 120250

