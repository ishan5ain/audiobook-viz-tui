from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from audiobook_viz.subtitles import (
        BookLineFragment,
        SubtitleBookLayout,
        SubtitleBookPage,
        SubtitleBookLine,
        SubtitleParagraph,
    )


class BookLayoutEngine:
    def __init__(self) -> None:
        self._cache: dict[tuple[int, int, int], SubtitleBookLayout] = {}

    def layout(
        self,
        paragraphs: list[SubtitleParagraph],
        *,
        wrap_width: int,
        line_budget: int,
        page_density: float,
    ) -> SubtitleBookLayout:
        density_key = int(round(page_density * 10))
        cache_key = (wrap_width, line_budget, density_key)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        from audiobook_viz.subtitles import SubtitleBookLine, SubtitleBookPage

        pages: list[SubtitleBookPage] = []
        cue_page_indices = [-1] * sum(len(p.segments) for p in paragraphs)
        current_page_lines: list[SubtitleBookLine] = []

        def flush_page() -> None:
            nonlocal current_page_lines
            if not current_page_lines:
                return
            cue_indices = _flatten_cue_indices(current_page_lines)
            if not cue_indices:
                current_page_lines = []
                return
            page_index = len(pages)
            for cue_index in cue_indices:
                if cue_page_indices[cue_index] < 0:
                    cue_page_indices[cue_index] = page_index
            pages.append(
                SubtitleBookPage(
                    lines=tuple(current_page_lines),
                    first_cue_index=cue_indices[0],
                    last_cue_index=cue_indices[-1],
                )
            )
            current_page_lines = []

        paragraph_gap = 0 if page_density >= 1.1 else 1
        for paragraph in paragraphs:
            paragraph_lines = _wrap_paragraph_lines(paragraph, wrap_width)
            if current_page_lines and paragraph_gap > 0:
                if len(current_page_lines) + paragraph_gap >= line_budget:
                    flush_page()
                else:
                    for _ in range(paragraph_gap):
                        current_page_lines.append(SubtitleBookLine(fragments=(), cue_indices=()))

            for line in paragraph_lines:
                if len(current_page_lines) >= line_budget:
                    flush_page()
                current_page_lines.append(line)

        flush_page()
        from audiobook_viz.subtitles import SubtitleBookLayout, SubtitleBookPage

        layout = SubtitleBookLayout(
            pages=tuple(pages),
            cue_page_indices=tuple(cue_page_indices),
        )
        self._cache[cache_key] = layout
        return layout


def _wrap_paragraph_lines(paragraph: SubtitleParagraph, width: int) -> list[SubtitleBookLine]:
    from audiobook_viz.subtitles import SubtitleBookLine, BookLineFragment

    lines: list[SubtitleBookLine] = []
    line_fragments: list[BookLineFragment] = []
    line_cue_indices: list[int] = []
    current_line_length = 0
    width = max(18, width)

    def flush_line() -> None:
        nonlocal line_fragments, line_cue_indices, current_line_length
        if not line_fragments:
            return
        lines.append(
            SubtitleBookLine(
                fragments=tuple(line_fragments),
                cue_indices=tuple(line_cue_indices),
            )
        )
        line_fragments = []
        line_cue_indices = []
        current_line_length = 0

    for segment in paragraph.segments:
        for word in segment.text.split():
            separator = "" if current_line_length == 0 else " "
            projected_length = current_line_length + len(separator) + len(word)
            if current_line_length > 0 and projected_length > width:
                flush_line()
                separator = ""
            if separator:
                _append_line_text(
                    line_fragments,
                    line_cue_indices,
                    cue_index=segment.cue_index,
                    text=separator,
                )
                current_line_length += len(separator)
            _append_line_text(
                line_fragments,
                line_cue_indices,
                cue_index=segment.cue_index,
                text=word,
            )
            current_line_length += len(word)

    flush_line()
    return lines


def _append_line_text(
    line_fragments: list[BookLineFragment],
    line_cue_indices: list[int],
    *,
    cue_index: int,
    text: str,
) -> None:
    from audiobook_viz.subtitles import BookLineFragment

    if not text:
        return
    if line_fragments and line_fragments[-1].cue_index == cue_index:
        previous = line_fragments[-1]
        line_fragments[-1] = BookLineFragment(cue_index=cue_index, text=previous.text + text)
    else:
        line_fragments.append(BookLineFragment(cue_index=cue_index, text=text))
    if cue_index not in line_cue_indices:
        line_cue_indices.append(cue_index)


def _flatten_cue_indices(lines: list[SubtitleBookLine]) -> list[int]:
    cue_indices: list[int] = []
    for line in lines:
        for cue_index in line.cue_indices:
            if not cue_indices or cue_indices[-1] != cue_index:
                cue_indices.append(cue_index)
    return cue_indices
