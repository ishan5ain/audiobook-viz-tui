import importlib.util
import os

_ui_legacy_path = os.path.join(os.path.dirname(__file__), "..", "ui.py")
_legacy_spec = importlib.util.spec_from_file_location(
    "audiobook_viz._ui_legacy", _ui_legacy_path
)
_legacy_module = importlib.util.module_from_spec(_legacy_spec)
_legacy_spec.loader.exec_module(_legacy_module)
AudiobookVizApp = _legacy_module.AudiobookVizApp  # type: ignore[assignment]
HelpModal = _legacy_module.HelpModal  # type: ignore[assignment]
SleepTimerModal = _legacy_module.SleepTimerModal  # type: ignore[assignment]

__all__ = ["AudiobookVizApp", "HelpModal", "SleepTimerModal"]
