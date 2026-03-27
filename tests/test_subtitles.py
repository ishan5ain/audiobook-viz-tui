from __future__ import annotations

from pathlib import Path

from audiobook_viz.subtitles import SubtitleTimeline, parse_subtitle_file


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
