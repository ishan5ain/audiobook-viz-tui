from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import re
from pathlib import Path

from audiobook_viz.models import SubtitleCue

_SRT_TIMESTAMP = re.compile(r"^(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})$")
_VTT_TIMESTAMP = re.compile(
    r"^(?:(?P<h>\d{2,}):)?(?P<m>\d{2}):(?P<s>\d{2})\.(?P<ms>\d{3})$"
)


class SubtitleParseError(RuntimeError):
    """Raised when subtitle text cannot be parsed."""


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

    def __post_init__(self) -> None:
        self._starts = [cue.start_ms for cue in self.cues]

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
            effective_position = position_ms + subtitle_offset_ms
            anchor_index = bisect_right(self._starts, effective_position) - 1
            if anchor_index < 0:
                anchor_index = 0
            elif anchor_index >= len(self.cues):
                anchor_index = len(self.cues) - 1

        start_index = max(0, anchor_index - before_count)
        end_index = min(len(self.cues), anchor_index + after_count + 1)
        local_active_index = None if active_index is None else active_index - start_index
        return self.cues[start_index:end_index], local_active_index


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
