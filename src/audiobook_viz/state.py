from __future__ import annotations

import hashlib
import json
from pathlib import Path

from platformdirs import user_state_path

from audiobook_viz.models import ResumeState


class StateStore:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or user_state_path("audiobook-viz")
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def load(self, audio_path: Path) -> ResumeState | None:
        path = self._state_path(audio_path)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            return ResumeState.from_dict(payload)
        except (KeyError, TypeError, ValueError):
            return None

    def save(self, audio_path: Path, resume_state: ResumeState) -> None:
        path = self._state_path(audio_path)
        path.write_text(json.dumps(resume_state.to_dict(), indent=2), encoding="utf-8")

    def _state_path(self, audio_path: Path) -> Path:
        return self.state_dir / f"{media_identity(audio_path)}.json"


def media_identity(audio_path: Path) -> str:
    stat = audio_path.stat()
    resolved = audio_path.resolve()
    digest = hashlib.sha256(
        f"{resolved}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()
    return digest[:24]
