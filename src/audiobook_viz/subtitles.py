from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import re
from pathlib import Path

from audiobook_viz.models import SubtitleCue
from audiobook_viz.subtitle_layout import BookLayoutEngine

_SRT_TIMESTAMP = re.compile(r"^(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})$")
_VTT_TIMESTAMP = re.compile(
    r"^(?:(?P<h>\d{2,}):)?(?P<m>\d{2}):(?P<s>\d{2})\.(?P<ms>\d{3})$"
)

# --- Configuration ---

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubtitleConfig:
    paragraph_split_gap_threshold_ms: int = 1500
    paragraph_split_char_threshold: int = 260
    paragraph_split_char_threshold_low: int = 180
    paragraph_split_word_threshold: int = 32
    paragraph_split_gap_threshold_low_ms: int = 700
    min_wrap_width: int = 18
    min_line_budget: int = 3


default_config = SubtitleConfig()

# Backwards-compatible aliases for internal use during migration.
PARAGRAPH_SPLIT_GAP_THRESHOLD_MS: int = default_config.paragraph_split_gap_threshold_ms
PARAGRAPH_SPLIT_CHAR_THRESHOLD: int = default_config.paragraph_split_char_threshold
PARAGRAPH_SPLIT_CHAR_THRESHOLD_LOW: int = default_config.paragraph_split_char_threshold_low
PARAGRAPH_SPLIT_WORD_THRESHOLD: int = default_config.paragraph_split_word_threshold
PARAGRAPH_SPLIT_GAP_THRESHOLD_LOW_MS: int = default_config.paragraph_split_gap_threshold_low_ms
MIN_WRAP_WIDTH: int = default_config.min_wrap_width
MIN_LINE_BUDGET: int = default_config.min_line_budget


class SubtitleParseError(RuntimeError):
    """Raised when subtitle text cannot be parsed."""


@dataclass(slots=True, frozen=True)
class BookCueSegment:
    cue_index: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(slots=True, frozen=True)
class BookLineFragment:
    cue_index: int
    text: str


@dataclass(slots=True, frozen=True)
class SubtitleBookLine:
    fragments: tuple[BookLineFragment, ...]
    cue_indices: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class SubtitleParagraph:
    text: str
    segments: tuple[BookCueSegment, ...]
    start_ms: int
    end_ms: int
    first_cue_index: int
    last_cue_index: int


@dataclass(slots=True, frozen=True)
class SubtitleBookPage:
    lines: tuple[SubtitleBookLine, ...]
    first_cue_index: int
    last_cue_index: int


@dataclass(slots=True, frozen=True)
class SubtitleBookLayout:
    pages: tuple[SubtitleBookPage, ...]
    cue_page_indices: tuple[int, ...]


def parse_subtitle_file(path: Path) -> list[SubtitleCue]:
    text = path.read_text(encoding="utf-8-sig")
    cues = parse_subtitle_text(text, path.suffix.lower())
    if not cues:
        raise SubtitleParseError(f"No subtitle cues found in {path}.")
    return cues


def parse_subtitle_text(text: str, suffix: str) -> list[SubtitleCue]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if suffix == ".vtt" or normalized.lstrip().startswith("WEBVTT"):
        return _parse_vtt(normalized)
    if suffix == ".srt":
        return _parse_srt(normalized)
    raise SubtitleParseError("Only .srt and .vtt subtitles are supported.")


@dataclass(slots=True)
class SubtitleTimeline:
    cues: list[SubtitleCue]
    _starts: list[int] = field(init=False, repr=False)
    _paragraphs: list[SubtitleParagraph] = field(init=False, repr=False)
    _cue_to_paragraph: list[int] = field(init=False, repr=False)
    _layout_engine: BookLayoutEngine = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._starts = [cue.start_ms for cue in self.cues]
        self._paragraphs, self._cue_to_paragraph = self._build_paragraphs()
        self._layout_engine = BookLayoutEngine()

    def active_at(self, position_ms: int, subtitle_offset_ms: int = 0) -> SubtitleCue | None:
        active_index = self.active_index_at(position_ms, subtitle_offset_ms)
        if active_index is None:
            return None
        return self.cues[active_index]

    def active_index_at(self, position_ms: int, subtitle_offset_ms: int = 0) -> int | None:
        effective_position = position_ms + subtitle_offset_ms
        index = bisect_right(self._starts, effective_position) - 1
        if index < 0 or index >= len(self.cues):
            return None
        cue = self.cues[index]
        if cue.start_ms <= effective_position < cue.end_ms:
            return index
        return None

    def anchor_index_at(self, position_ms: int, subtitle_offset_ms: int = 0) -> int | None:
        if not self.cues:
            return None
        effective_position = position_ms + subtitle_offset_ms
        index = bisect_right(self._starts, effective_position) - 1
        if index < 0:
            return 0
        if index >= len(self.cues):
            return len(self.cues) - 1
        return index

    def window_at(
        self,
        position_ms: int,
        *,
        subtitle_offset_ms: int = 0,
        before_count: int = 3,
        after_count: int = 3,
    ) -> tuple[list[SubtitleCue], int | None]:
        if not self.cues:
            return [], None

        before_count = max(0, before_count)
        after_count = max(0, after_count)
        active_index = self.active_index_at(position_ms, subtitle_offset_ms)

        if active_index is not None:
            anchor_index = active_index
        else:
            anchor_index = self.anchor_index_at(position_ms, subtitle_offset_ms)
            if anchor_index is None:
                return [], None

        start_index = max(0, anchor_index - before_count)
        end_index = min(len(self.cues), anchor_index + after_count + 1)
        local_active_index = None if active_index is None else active_index - start_index
        return self.cues[start_index:end_index], local_active_index

    def book_page_at(
        self,
        position_ms: int,
        *,
        subtitle_offset_ms: int = 0,
        wrap_width: int,
        line_budget: int,
        page_density: float,
    ) -> tuple[SubtitleBookPage | None, int | None]:
        if not self.cues:
            return None, None
        layout = self._layout_engine.layout(
            self._paragraphs,
            wrap_width=max(MIN_WRAP_WIDTH, wrap_width),
            line_budget=max(MIN_LINE_BUDGET, line_budget),
            page_density=page_density,
        )
        if not layout.pages:
            return None, self.active_index_at(position_ms, subtitle_offset_ms)

        active_index = self.active_index_at(position_ms, subtitle_offset_ms)
        if active_index is not None:
            page_index = layout.cue_page_indices[active_index]
            if page_index >= 0:
                return layout.pages[page_index], active_index

        anchor_index = self.anchor_index_at(position_ms, subtitle_offset_ms)
        if anchor_index is None:
            return layout.pages[0], active_index

        page_index = layout.cue_page_indices[anchor_index]
        if page_index >= 0:
            return layout.pages[page_index], active_index
        return layout.pages[0], active_index

    def _build_paragraphs(self) -> tuple[list[SubtitleParagraph], list[int]]:
        if not self.cues:
            return [], []

        # Book mode has a two-stage layout pipeline:
        # 1. merge short Whisper cues into paragraph-sized chunks based on gaps and size
        # 2. wrap those paragraphs into visual lines and slice pages from those lines
        #
        # The page-turning bug came from stopping after stage 1 and paging whole paragraphs.
        # A long paragraph could overflow the pane while still being treated as a single page,
        # which let the active cue fall below the visible area. We keep paragraph merging here,
        # but paging now happens later from wrapped line ranges.
        paragraphs: list[SubtitleParagraph] = []
        cue_to_paragraph = [0] * len(self.cues)
        paragraph_segments: list[BookCueSegment] = []
        paragraph_char_count = 0
        paragraph_word_count = 0

        def flush() -> None:
            nonlocal paragraph_segments, paragraph_char_count, paragraph_word_count
            if not paragraph_segments:
                return
            text = " ".join(segment.text for segment in paragraph_segments)
            paragraph = SubtitleParagraph(
                text=text,
                segments=tuple(paragraph_segments),
                start_ms=paragraph_segments[0].start_ms,
                end_ms=paragraph_segments[-1].end_ms,
                first_cue_index=paragraph_segments[0].cue_index,
                last_cue_index=paragraph_segments[-1].cue_index,
            )
            paragraph_index = len(paragraphs)
            paragraphs.append(paragraph)
            for segment in paragraph_segments:
                cue_to_paragraph[segment.cue_index] = paragraph_index
            paragraph_segments = []
            paragraph_char_count = 0
            paragraph_word_count = 0

        previous_cue: SubtitleCue | None = None
        for cue_index, cue in enumerate(self.cues):
            normalized_text = _normalize_cue_text(cue.text)
            if not normalized_text:
                continue
            if previous_cue is not None:
                gap_ms = max(0, cue.start_ms - previous_cue.end_ms)
                if _should_split_paragraph(
                    gap_ms=gap_ms,
                    current_char_count=paragraph_char_count,
                    current_word_count=paragraph_word_count,
                ):
                    flush()

            segment = BookCueSegment(
                cue_index=cue_index,
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                text=normalized_text,
            )
            paragraph_segments.append(segment)
            paragraph_char_count += len(normalized_text)
            paragraph_word_count += len(normalized_text.split())
            previous_cue = cue

        flush()
        return paragraphs, cue_to_paragraph




def _parse_srt(text: str) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    blocks = text.strip().split("\n\n")
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if len(lines) >= 2 and lines[0].isdigit() and "-->" in lines[1]:
            timing_line = lines[1]
            content_lines = lines[2:]
        elif "-->" in lines[0]:
            timing_line = lines[0]
            content_lines = lines[1:]
        else:
            continue
        cue = _build_cue(timing_line, content_lines, is_vtt=False)
        if cue is not None:
            cues.append(cue)
    return cues


def _parse_vtt(text: str) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    blocks = text.strip().split("\n\n")
    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        header = lines[0].strip()
        if header == "WEBVTT" or header.startswith("NOTE") or header.startswith("STYLE"):
            continue
        if "-->" in lines[0]:
            timing_line = lines[0]
            content_lines = lines[1:]
        elif len(lines) >= 2 and "-->" in lines[1]:
            timing_line = lines[1]
            content_lines = lines[2:]
        else:
            continue
        cue = _build_cue(timing_line, content_lines, is_vtt=True)
        if cue is not None:
            cues.append(cue)
    return cues


def _build_cue(timing_line: str, content_lines: list[str], *, is_vtt: bool) -> SubtitleCue | None:
    parts = timing_line.split("-->")
    if len(parts) != 2:
        return None
    start_raw = parts[0].strip().split()[0]
    end_raw = parts[1].strip().split()[0]
    start_ms = _parse_timestamp(start_raw, is_vtt=is_vtt)
    end_ms = _parse_timestamp(end_raw, is_vtt=is_vtt)
    if end_ms <= start_ms:
        return None
    text = "\n".join(line.strip() for line in content_lines).strip()
    if not text:
        return None
    return SubtitleCue(start_ms=start_ms, end_ms=end_ms, text=text)


def _parse_timestamp(value: str, *, is_vtt: bool) -> int:
    matcher = _VTT_TIMESTAMP.match(value) if is_vtt else _SRT_TIMESTAMP.match(value)
    if not matcher:
        raise SubtitleParseError(f"Invalid subtitle timestamp: {value}")
    hours = int(matcher.group("h") or 0)
    minutes = int(matcher.group("m"))
    seconds = int(matcher.group("s"))
    milliseconds = int(matcher.group("ms"))
    total_ms = (((hours * 60) + minutes) * 60 + seconds) * 1000 + milliseconds
    return total_ms


def _normalize_cue_text(text: str) -> str:
    return " ".join(text.split())


def _should_split_paragraph(
    *,
    gap_ms: int,
    current_char_count: int,
    current_word_count: int,
) -> bool:
    if gap_ms >= PARAGRAPH_SPLIT_GAP_THRESHOLD_MS:
        return True
    if current_char_count >= PARAGRAPH_SPLIT_CHAR_THRESHOLD:
        return True
    return (
        current_char_count >= PARAGRAPH_SPLIT_CHAR_THRESHOLD_LOW
        and current_word_count >= PARAGRAPH_SPLIT_WORD_THRESHOLD
        and gap_ms >= PARAGRAPH_SPLIT_GAP_THRESHOLD_LOW_MS
    )


def _wrap_paragraph_lines(paragraph: SubtitleParagraph, width: int) -> list[SubtitleBookLine]:
    lines: list[SubtitleBookLine] = []
    line_fragments: list[BookLineFragment] = []
    line_cue_indices: list[int] = []
    current_line_length = 0
    width = max(MIN_WRAP_WIDTH, width)

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
