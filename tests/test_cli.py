from __future__ import annotations

from audiobook_viz.cli import build_parser


def test_cli_accepts_subtitle_context_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "book.m4a",
            "book.srt",
            "--subtitle-context-before",
            "5",
            "--subtitle-context-after",
            "2",
        ]
    )

    assert args.subtitle_context_before == 5
    assert args.subtitle_context_after == 2
