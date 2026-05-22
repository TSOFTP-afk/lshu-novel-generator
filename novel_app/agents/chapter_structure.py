from __future__ import annotations

import json
import re
from typing import Any, Callable


class ChapterStructureAgent:
    """Detect volume/chapter heading lines for smart import."""

    def __init__(self, post_chat: Callable[..., dict[str, Any]]) -> None:
        self._post_chat = post_chat

    def detect(self, text: str) -> list[dict[str, Any]]:
        structures: list[Any] = []
        for catalog in self._build_line_catalog_batches(text):
            structures.extend(self._detect_batch(catalog))
        return self._normalize_items(structures)

    def _detect_batch(self, catalog: str) -> list[Any]:
        prompt = (
            "请从下面的中文长篇小说文本行目录中识别真实卷/章结构。\n"
            "只返回 JSON，不要解释。JSON 格式：\n"
            "{\"structure\":[{\"kind\":\"volume|chapter\",\"line_number\":1,\"title\":\"标题\"}]}\n"
            "规则：\n"
            "- line_number 必须使用行目录左侧的原始行号，且为 1-based。\n"
            "- volume 表示卷/部/篇/集标题，例如“第一卷”“第2卷”。\n"
            "- chapter 表示章节标题，例如“第一章”“第12章”“序章”“番外”。\n"
            "- 只标记独立成行的结构标题，不要把正文句子、目录说明、人物设定项当章节。\n"
            "- 如果没有可靠章节结构，返回 {\"structure\":[]}。\n\n"
            f"行目录：\n{catalog}"
        )
        result = self._post_chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是长篇小说导入结构识别智能体，只负责找卷/章标题行并返回 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.05,
        )
        raw = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        payload = self._extract_json(raw)
        items = payload.get("structure", [])
        if not isinstance(items, list):
            return []
        return items

    @staticmethod
    def _build_line_catalog_batches(
        text: str,
        max_lines: int = 2200,
        max_chars: int = 48000,
        max_batches: int = 12,
    ) -> list[str]:
        lines = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        batches: list[str] = []
        current: list[str] = []
        total_chars = 0
        for line_number, raw_line in enumerate(lines, start=1):
            line = re.sub(r"\s+", " ", raw_line.strip())
            if not line:
                continue
            if len(line) > 120:
                continue
            entry = f"{line_number}: {line}"
            if current and (total_chars + len(entry) + 1 > max_chars or len(current) >= max_lines):
                batches.append("\n".join(current))
                if len(batches) >= max_batches:
                    return batches
                current = []
                total_chars = 0
            current.append(entry)
            total_chars += len(entry) + 1
        if current and len(batches) < max_batches:
            batches.append("\n".join(current))
        return batches

    @staticmethod
    def _build_line_catalog(text: str, max_lines: int = 2200, max_chars: int = 48000) -> str:
        batches = ChapterStructureAgent._build_line_catalog_batches(
            text,
            max_lines=max_lines,
            max_chars=max_chars,
            max_batches=1,
        )
        return batches[0] if batches else ""

    @staticmethod
    def _normalize_items(items: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "") or "").strip().lower()
            if kind not in {"volume", "chapter"}:
                continue
            try:
                line_number = int(item.get("line_number", item.get("line", 0)) or 0)
            except (TypeError, ValueError):
                continue
            if line_number <= 0:
                continue
            title = str(item.get("title", "") or "").strip()
            if not title:
                continue
            key = (kind, line_number)
            if key in seen:
                continue
            seen.add(key)
            normalized.append({"kind": kind, "line_number": line_number, "title": title[:120]})
        normalized.sort(key=lambda item: (int(item["line_number"]), 0 if item["kind"] == "volume" else 1))
        return normalized

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start : end + 1]
        return json.loads(stripped)
