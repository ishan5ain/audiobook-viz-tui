from __future__ import annotations

import re

DEFAULT_HELP_ACCENT_COLOR = "#ffbd14"

_HEX_COLOR_PATTERN = re.compile(r"^#?[0-9a-fA-F]{6}$")


def normalize_help_accent_color(value: str) -> str:
    stripped = value.strip()
    if not _HEX_COLOR_PATTERN.fullmatch(stripped):
        raise ValueError("help accent color must be a 6-digit RGB hex code.")
    hex_digits = stripped[1:] if stripped.startswith("#") else stripped
    return f"#{hex_digits.lower()}"
