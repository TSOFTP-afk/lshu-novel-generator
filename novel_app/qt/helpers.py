from __future__ import annotations

import re
from typing import Any


DEFAULT_AI_PROBABILITY_META = {
    "certain": {"label": "AI 100%", "fg": "#FFFFFF", "bg": "#D83A34", "tree": "#C92A2A"},
    "high": {"label": "AI 高", "fg": "#3A2A00", "bg": "#F2C94C", "tree": "#B7791F"},
    "medium": {"label": "AI 中", "fg": "#3A2A00", "bg": "#F7D774", "tree": "#B7791F"},
    "low": {"label": "AI 低", "fg": "#FFFFFF", "bg": "#2FA66A", "tree": "#258A55"},
    "none": {"label": "AI 无", "fg": "#FFFFFF", "bg": "#2F80ED", "tree": "#2F80ED"},
}

AI_PROBABILITY_META = {level: dict(meta) for level, meta in DEFAULT_AI_PROBABILITY_META.items()}
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def row_to_dict(row: Any | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _valid_hex_color(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not text.startswith("#"):
        text = f"#{text}"
    return text.upper() if _HEX_COLOR_RE.match(text) else None


def normalize_ai_color_config(overrides: Any | None = None) -> dict[str, dict[str, str]]:
    merged = {level: dict(meta) for level, meta in DEFAULT_AI_PROBABILITY_META.items()}
    if isinstance(overrides, dict):
        for level, raw_meta in overrides.items():
            if level not in merged or not isinstance(raw_meta, dict):
                continue
            for field in ("fg", "bg", "tree"):
                color = _valid_hex_color(raw_meta.get(field))
                if color:
                    merged[level][field] = color
    return merged


def set_ai_probability_meta(overrides: Any | None = None) -> dict[str, dict[str, str]]:
    AI_PROBABILITY_META.clear()
    AI_PROBABILITY_META.update(normalize_ai_color_config(overrides))
    return AI_PROBABILITY_META


def get_ai_probability_meta(overrides: Any | None = None) -> dict[str, dict[str, str]]:
    if overrides is None:
        return AI_PROBABILITY_META
    return normalize_ai_color_config(overrides)


def normalize_ai_probability_pair(level: str, probability: int) -> tuple[int, str]:
    probability = max(0, min(100, int(probability or 0)))
    if probability >= 92:
        derived = "certain"
    elif probability >= 68:
        derived = "high"
    elif probability >= 42:
        derived = "medium"
    elif probability >= 18:
        derived = "low"
    else:
        derived = "none"
    normalized = level if level in AI_PROBABILITY_META else derived
    if normalized == "certain" and probability >= 92:
        return 100, "certain"
    if normalized != derived:
        normalized = derived
    return probability, normalized


def format_chapter_tree_title(sort_order: Any, title: str) -> str:
    cleaned = str(title or "").strip()
    if re.match(r"^第\s*[\d零〇一二两三四五六七八九十百千万]+\s*[章节回幕](?:\s|[：:·、.．\-—_]|$)", cleaned):
        return cleaned
    if cleaned in {"序章", "楔子", "尾声"} or cleaned.startswith("番外"):
        return cleaned
    if re.match(r"^[|｜]\s*[\d零〇一二两三四五六七八九十百千万]+\s*[|｜]", cleaned):
        return cleaned
    return f"第{sort_order}章 {cleaned}"


def count_text_characters(text: Any) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def compute_template_stats(content: Any) -> dict[str, int]:
    text = str(content or "")
    word_count = count_text_characters(text)
    if word_count <= 0:
        return {"word_count": 0, "dialogue_density": 0, "description_ratio": 0}
    dialogue_chars = sum(len(match.group(0)) for match in re.finditer(r"[“「『].*?[”」』]", text, re.S))
    dialogue_density = max(0, min(100, int(round(dialogue_chars * 100 / max(1, len(text))))))
    description_ratio = max(0, min(100, 100 - dialogue_density))
    return {
        "word_count": word_count,
        "dialogue_density": dialogue_density,
        "description_ratio": description_ratio,
    }


def format_chapter_tree_display_title(
    sort_order: Any,
    title: str,
    *,
    word_count: int | None = None,
    is_template: bool = False,
) -> str:
    prefix = "⭐ " if is_template else ""
    base = f"{prefix}{format_chapter_tree_title(sort_order, title)}"
    if word_count is not None:
        return f"{base} · {max(0, int(word_count))}字"
    return base


def previous_chapter_ids_in_order(
    chapters: list[Any],
    current_chapter_id: int,
    limit: int = 3,
) -> list[int]:
    previous: list[int] = []
    for row in chapters:
        try:
            chapter_id = int(row["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if chapter_id == current_chapter_id:
            break
        previous.append(chapter_id)
    limit = max(0, int(limit))
    if limit <= 0:
        return []
    return previous[-limit:]
