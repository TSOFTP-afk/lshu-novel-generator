from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def prompt_value(overrides: Any, key: str, default: str = "") -> str:
    if isinstance(overrides, Mapping) and key in overrides:
        return str(overrides.get(key, ""))
    return default


def render_prompt(template: str, values: Mapping[str, Any]) -> str:
    text = str(template or "")
    for key, value in values.items():
        text = text.replace("{" + str(key) + "}", str(value))
    return text

