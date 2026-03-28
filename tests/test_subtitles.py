from __future__ import annotations

from pathlib import Path

from audiobook_viz.subtitles import SubtitleTimeline, parse_subtitle_file


def _page_lines(page) -> list[str]:
    return ["".join(fragment.text for fragment in line.fragments) for line in page.lines]


def test_parse_srt_and_resolve_active_cue(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nFirst line\n\n"
        "2\n00:00:04,000 --> 00:00:06,500\nSecond line\n",
        encoding="utf-8",
    )

    cues = parse_subtitle_file(subtitle_path)
    timeline = SubtitleTimeline(cues)

    assert len(cues) == 2
    assert cues[0].text == "First line"
    assert timeline.active_at(1500).text == "First line"
    assert timeline.active_at(4100).text == "Second line"


def test_parse_vtt_and_apply_offset(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.vtt"
    subtitle_path.write_text(
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:02.500 align:start\nHello there\n\n"
        "00:00:03.000 --> 00:00:04.000\nGeneral Kenobi\n",
        encoding="utf-8",
    )

    cues = parse_subtitle_file(subtitle_path)
    timeline = SubtitleTimeline(cues)

    assert len(cues) == 2
    assert timeline.active_at(1200).text == "Hello there"
    assert timeline.active_at(2600, subtitle_offset_ms=400).text == "General Kenobi"
    assert timeline.active_at(4500) is None


def test_subtitle_window_returns_context_and_active_index(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nOne\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nTwo\n\n"
        "3\n00:00:02,000 --> 00:00:03,000\nThree\n\n"
        "4\n00:00:03,000 --> 00:00:04,000\nFour\n\n"
        "5\n00:00:04,000 --> 00:00:05,000\nFive\n",
        encoding="utf-8",
    )

    timeline = SubtitleTimeline(parse_subtitle_file(subtitle_path))
    cues, active_index = timeline.window_at(2500, before_count=1, after_count=2)

    assert [cue.text for cue in cues] == ["Two", "Three", "Four", "Five"]
    assert active_index == 1


def test_subtitle_window_handles_no_active_cue(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nOne\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nTwo\n",
        encoding="utf-8",
    )

    timeline = SubtitleTimeline(parse_subtitle_file(subtitle_path))
    cues, active_index = timeline.window_at(2200, before_count=1, after_count=1)

    assert [cue.text for cue in cues] == ["One", "Two"]
    assert active_index is None


def test_book_mode_merges_short_adjacent_cues_into_one_paragraph(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:00,800\nHello\n\n"
        "2\n00:00:00,900 --> 00:00:01,500\nworld\n\n"
        "3\n00:00:01,600 --> 00:00:02,200\nagain\n",
        encoding="utf-8",
    )

    timeline = SubtitleTimeline(parse_subtitle_file(subtitle_path))
    page, active_index = timeline.book_page_at(
        1_000,
        wrap_width=40,
        line_budget=8,
        page_density=1.0,
    )

    assert page is not None
    assert _page_lines(page) == ["Hello world again"]
    assert active_index == 1


def test_book_mode_splits_paragraphs_on_long_gaps_and_turns_pages(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nAlpha\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nBeta\n\n"
        "3\n00:00:06,000 --> 00:00:07,000\nGamma\n",
        encoding="utf-8",
    )

    timeline = SubtitleTimeline(parse_subtitle_file(subtitle_path))
    assert [paragraph.text for paragraph in timeline._paragraphs] == ["Alpha", "Beta", "Gamma"]

    first_page, active_index = timeline.book_page_at(
        500,
        wrap_width=40,
        line_budget=3,
        page_density=1.0,
    )
    assert first_page is not None
    assert _page_lines(first_page) == ["Alpha", "", "Beta"]
    assert active_index == 0

    anchored_gap_page, gap_active_index = timeline.book_page_at(
        4_500,
        wrap_width=40,
        line_budget=3,
        page_density=1.0,
    )
    assert anchored_gap_page == first_page
    assert gap_active_index is None

    second_page, final_active_index = timeline.book_page_at(
        6_500,
        wrap_width=40,
        line_budget=3,
        page_density=1.0,
    )
    assert second_page is not None
    assert _page_lines(second_page) == ["Gamma"]
    assert final_active_index == 2


def test_book_mode_splits_long_paragraph_across_pages_and_keeps_active_cue_visible(tmp_path: Path) -> None:
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nAlbatross bravo\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nCharlotte delta\n\n"
        "3\n00:00:02,000 --> 00:00:03,000\nEvergreen foxtrot\n\n"
        "4\n00:00:03,000 --> 00:00:04,000\nJubilation hotel\n\n"
        "5\n00:00:04,000 --> 00:00:05,000\nMarigold juliet\n\n"
        "6\n00:00:05,000 --> 00:00:06,000\nNightfall kilo\n",
        encoding="utf-8",
    )

    timeline = SubtitleTimeline(parse_subtitle_file(subtitle_path))

    early_page, early_active_index = timeline.book_page_at(
        500,
        wrap_width=18,
        line_budget=2,
        page_density=1.0,
    )
    assert early_page is not None
    assert early_active_index == 0
    assert _page_lines(early_page) == ["Albatross bravo", "Charlotte delta", "Evergreen foxtrot"]

    late_page, late_active_index = timeline.book_page_at(
        4_500,
        wrap_width=18,
        line_budget=2,
        page_density=1.0,
    )
    assert late_page is not None
    assert late_active_index == 4
    assert _page_lines(late_page) == ["Jubilation hotel", "Marigold juliet", "Nightfall kilo"]
