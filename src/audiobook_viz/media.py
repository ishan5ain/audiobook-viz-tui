from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from audiobook_viz.models import Chapter, MediaMetadata


class MediaProbeError(RuntimeError):
    """Raised when ffprobe metadata cannot be loaded."""


def ensure_ffprobe_available(ffprobe_bin: str = "ffprobe") -> None:
    if shutil.which(ffprobe_bin):
        return
    raise MediaProbeError("ffprobe was not found in PATH.")


def probe_media_metadata(audio_path: Path, ffprobe_bin: str = "ffprobe") -> MediaMetadata:
    ensure_ffprobe_available(ffprobe_bin)
    command = [
        ffprobe_bin,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_chapters",
        str(audio_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "unknown ffprobe error"
        raise MediaProbeError(f"ffprobe failed for {audio_path}: {stderr}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError("ffprobe returned invalid JSON.") from exc
    return parse_ffprobe_payload(payload, audio_path)


def parse_ffprobe_payload(payload: dict[str, object], audio_path: Path) -> MediaMetadata:
    format_payload = payload.get("format")
    if not isinstance(format_payload, dict):
        raise MediaProbeError("ffprobe payload is missing format metadata.")
    duration_value = format_payload.get("duration")
    try:
        duration_ms = max(0, int(float(duration_value) * 1000))
    except (TypeError, ValueError) as exc:
        raise MediaProbeError("ffprobe payload is missing a usable duration.") from exc

    raw_chapters = payload.get("chapters")
    chapters: list[Chapter] = []
    if isinstance(raw_chapters, list):
        for index, chapter_payload in enumerate(raw_chapters):
            if not isinstance(chapter_payload, dict):
                continue
            start_ms = _parse_time_ms(chapter_payload.get("start_time"))
            end_ms = _parse_time_ms(chapter_payload.get("end_time"))
            if end_ms <= start_ms:
                end_ms = duration_ms
            tags = chapter_payload.get("tags")
            title = f"Chapter {index + 1}"
            if isinstance(tags, dict):
                candidate = tags.get("title")
                if isinstance(candidate, str) and candidate.strip():
                    title = candidate.strip()
            chapters.append(
                Chapter(
                    index=index,
                    title=title,
                    start_ms=start_ms,
                    end_ms=min(end_ms, duration_ms),
                )
            )

    return MediaMetadata(audio_path=audio_path, duration_ms=duration_ms, chapters=chapters)


def _parse_time_ms(value: object) -> int:
    try:
        return max(0, int(float(value) * 1000))
    except (TypeError, ValueError):
        return 0

