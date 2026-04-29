from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from audiobook_viz.colors import DEFAULT_HELP_ACCENT_COLOR, normalize_help_accent_color


@dataclass(slots=True, frozen=True)
class Chapter:
    index: int
    title: str
    start_ms: int
    end_ms: int


@dataclass(slots=True, frozen=True)
class MediaMetadata:
    audio_path: Path
    duration_ms: int
    chapters: list[Chapter]


@dataclass(slots=True, frozen=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str


@dataclass(slots=True, frozen=True)
class PlaybackState:
    position_ms: int
    duration_ms: int
    paused: bool
    chapter_index: int


def _coerce_subtitle_display_mode(value: str) -> "SubtitleDisplayMode":
    from audiobook_viz.ui.enums import SubtitleDisplayMode

    try:
        return SubtitleDisplayMode(str(value))
    except ValueError:
        return SubtitleDisplayMode.WINDOW


@dataclass(slots=True, frozen=True)
class ResumeState:
    position_ms: int
    chapter_index: int
    font_scale: float
    subtitle_offset_ms: int
    subtitle_context_before: int
    subtitle_context_after: int
    subtitle_display_mode: SubtitleDisplayMode
    book_page_density: float
    help_accent_color: str

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["subtitle_display_mode"] = self.subtitle_display_mode.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ResumeState":
        help_accent_value = str(data.get("help_accent_color", DEFAULT_HELP_ACCENT_COLOR))
        try:
            help_accent_color = normalize_help_accent_color(help_accent_value)
        except ValueError:
            help_accent_color = DEFAULT_HELP_ACCENT_COLOR
        return cls(
            position_ms=int(data["position_ms"]),
            chapter_index=int(data["chapter_index"]),
            font_scale=float(data["font_scale"]),
            subtitle_offset_ms=int(data["subtitle_offset_ms"]),
            subtitle_context_before=max(0, int(data.get("subtitle_context_before", 3))),
            subtitle_context_after=max(0, int(data.get("subtitle_context_after", 3))),
            subtitle_display_mode=_coerce_subtitle_display_mode(str(data.get("subtitle_display_mode", "window"))),
            book_page_density=float(data.get("book_page_density", 1.0)),
            help_accent_color=help_accent_color,
        )
