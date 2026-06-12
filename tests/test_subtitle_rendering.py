from __future__ import annotations

from pathlib import Path

import pytest

from audiobook_viz.subtitles import SubtitleCue, SubtitleTimeline, parse_subtitle_file
from audiobook_viz.ui.rendering import SubtitleRenderer, SubtitleViewState, _book_layout_metrics
from audiobook_viz.ui.enums import SubtitleDisplayMode


def _renderable_plain_text(renderable: object) -> str:
    if hasattr(renderable, "plain"):
        return renderable.plain
    nested = getattr(renderable, "renderable", None)
    if nested is not None:
        return _renderable_plain_text(nested)
    renderables = getattr(renderable, "renderables", None)
    if renderables is not None:
        return "\n".join(_renderable_plain_text(item) for item in renderables)
    return str(renderable)


def _renderable_styles(renderable: object) -> list[str]:
    styles: list[str] = []
    style = getattr(renderable, "style", None)
    if style is not None:
        styles.append(str(style))
    spans = getattr(renderable, "spans", None)
    if spans is not None:
        styles.extend(str(span.style) for span in spans if span.style is not None)
    nested = getattr(renderable, "renderable", None)
    if nested is not None:
        styles.extend(_renderable_styles(nested))
    renderables = getattr(renderable, "renderables", None)
    if renderables is not None:
        for item in renderables:
            styles.extend(_renderable_styles(item))
    return styles


def test_renderer_window_mode_renders_active_cue_with_accent(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nOne\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nTwo\n\n"
        "3\n00:00:02,000 --> 00:00:03,000\nThree\n",
        encoding="utf-8",
    )
    timeline = SubtitleTimeline(parse_subtitle_file(subtitle_path))
    renderer = SubtitleRenderer()
    state = SubtitleViewState(
        font_scale=1.0,
        book_page_density=1.0,
        help_accent_color="#ffbd14",
        subtitle_display_mode=SubtitleDisplayMode.WINDOW,
        subtitle_offset_ms=0,
        subtitle_context_before=1,
        subtitle_context_after=1,
        panel_width=80,
        panel_height=24,
    )

    renderable = renderer.render(timeline, 1500, state)
    text = _renderable_plain_text(renderable)

    assert "One" in text
    assert "Two" in text
    assert "Three" in text
    assert "bold #ffbd14 on #21414f" in _renderable_styles(renderable)


def test_renderer_book_mode_renders_page_with_active_highlight(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:00,800\nHello\n\n"
        "2\n00:00:00,900 --> 00:00:01,500\nworld\n\n"
        "3\n00:00:01,600 --> 00:00:02,200\nagain\n",
        encoding="utf-8",
    )
    timeline = SubtitleTimeline(parse_subtitle_file(subtitle_path))
    renderer = SubtitleRenderer()
    state = SubtitleViewState(
        font_scale=1.0,
        book_page_density=1.0,
        help_accent_color="#ffbd14",
        subtitle_display_mode=SubtitleDisplayMode.BOOK,
        subtitle_offset_ms=0,
        subtitle_context_before=3,
        subtitle_context_after=3,
        panel_width=80,
        panel_height=24,
    )

    renderable = renderer.render(timeline, 1000, state)
    text = _renderable_plain_text(renderable)

    assert "Hello world again" in text
    assert "bold #ffbd14 on #21414f" in _renderable_styles(renderable)


def test_book_layout_metrics_scales_with_font_and_density() -> None:
    wrap_width, line_budget = _book_layout_metrics(
        panel_width=80,
        panel_height=24,
        page_density=1.0,
        font_scale=1.0,
    )
    assert wrap_width == 72
    assert line_budget == 20

    wrap_width_2x, line_budget_2x = _book_layout_metrics(
        panel_width=80,
        panel_height=24,
        page_density=1.0,
        font_scale=2.0,
    )
    assert wrap_width_2x == 36
    assert line_budget_2x == 10
