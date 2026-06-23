"""Debug logging for tracing chapter navigation flow.

Writes to /tmp/abv-debug.log so it doesn't interfere with the TUI display.
Tail with: tail -f /tmp/abv-debug.log
"""

import datetime
import logging
import os
from pathlib import Path

# Set to False to enable debug logging to /tmp/abv-debug.log
DISABLED = True

_LOG_PATH = Path("/tmp/abv-debug.log")

if not DISABLED:
    # Truncate log on each run
    _LOG_PATH.write_text("")

    _handler = logging.FileHandler(str(_LOG_PATH), mode="a")
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d [%(name)s] %(message)s", datefmt="%H:%M:%S"))

    _logger = logging.getLogger("abv")
    _logger.setLevel(logging.DEBUG)
    _logger.addHandler(_handler)
    _logger.propagate = False
else:
    _logger = logging.getLogger("abv")
    _logger.addHandler(logging.NullHandler())


def log(label: str, **kwargs: object) -> None:
    if DISABLED:
        return
    parts = [label]
    for k, v in kwargs.items():
        parts.append(f"  {k}={v}")
    _logger.debug(" | ".join(parts))
