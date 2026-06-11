from __future__ import annotations

from pathlib import Path

import pytest

from audiobook_viz.subtitles import SubtitleTimeline, parse_subtitle_file
from audiobook_viz.subtitle_layout import BookLayoutEngine


def _load_timeline(path: Path) -> SubtitleTimeline:
    return SubtitleTimeline(parse_subtitle_file(path))


def test_engine_matches_legacy_book_page_at(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nAlpha\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nBeta\n\n"
        "3\n00:00:06,000 --> 00:00:07,000\nGamma\n",
        encoding="utf-8",
    )
    timeline = _load_timeline(subtitle_path)
    engine = BookLayoutEngine()

    legacy_page, legacy_active = timeline.book_page_at(
        500,
        wrap_width=40,
        line_budget=3,
        page_density=1.0,
    )
    layout = engine.layout(
        timeline._paragraphs,
        wrap_width=40,
        line_budget=3,
        page_density=1.0,
    )
    page = layout.pages[0] if layout.pages else None
    active_index = timeline.active_index_at(500)

    assert page == legacy_page
    assert active_index == legacy_active


def test_engine_returns_cached_layout_for_same_params(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nAlpha\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nBeta\n",
        encoding="utf-8",
    )
    timeline = _load_timeline(subtitle_path)
    engine = BookLayoutEngine()

    first = engine.layout(timeline._paragraphs, wrap_width=40, line_budget=3, page_density=1.0)
    second = engine.layout(timeline._paragraphs, wrap_width=40, line_budget=3, page_density=1.0)

    assert first is second


def test_engine_produces_fresh_layout_when_params_change(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nAlpha beta gamma delta epsilon\n",
        encoding="utf-8",
    )
    timeline = _load_timeline(subtitle_path)
    engine = BookLayoutEngine()

    first = engine.layout(timeline._paragraphs, wrap_width=40, line_budget=4, page_density=1.0)
    second = engine.layout(timeline._paragraphs, wrap_width=20, line_budget=1, page_density=1.0)

    assert first is not second
    assert len(first.pages) != len(second.pages)
