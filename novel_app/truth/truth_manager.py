from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

TRUTH_FILES = [
    "current_state.md",
    "particle_ledger.md",
    "pending_hooks.md",
    "chapter_summaries.md",
    "subplot_board.md",
    "emotional_arcs.md",
    "character_matrix.md",
]

TRUTH_FILE_LABELS = {
    "current_state.md": "当前状态",
    "particle_ledger.md": "关键道具",
    "pending_hooks.md": "待回收伏笔",
    "chapter_summaries.md": "章节摘要",
    "subplot_board.md": "支线看板",
    "emotional_arcs.md": "情感弧光",
    "character_matrix.md": "人物矩阵",
}

MAX_TRUTH_FILE_BYTES = 18000


class TruthManager:
    def __init__(self, data_dir: Path, db: Any) -> None:
        self._data_dir = Path(data_dir)
        self._db = db

    def _truth_dir(self, book_id: int) -> Path:
        target = self._data_dir / str(book_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _read_file(self, book_id: int, filename: str) -> str:
        path = self._truth_dir(book_id) / filename
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _write_file(self, book_id: int, filename: str, content: str) -> None:
        path = self._truth_dir(book_id) / filename
        truncated = content.strip()
        if len(truncated.encode("utf-8")) > MAX_TRUTH_FILE_BYTES:
            truncated = truncated.encode("utf-8")[:MAX_TRUTH_FILE_BYTES].decode("utf-8", errors="ignore").rstrip()
            newline_index = truncated.rfind("\n")
            if newline_index > 0:
                truncated = truncated[:newline_index].rstrip()
        path.write_text(truncated, encoding="utf-8")

    def read(self, book_id: int, filename: str) -> str:
        if filename not in TRUTH_FILES:
            raise ValueError(f"Unknown truth file: {filename}")
        return self._read_file(book_id, filename)

    def build_all(self, book_id: int) -> dict[str, str]:
        book = self._db.get_book(book_id)
        if not book:
            return {}
        book_title = str(book["title"] or "未命名作品")
        book_outline = str(book["outline_text"] or "")

        characters = self._db.list_characters(book_id)
        world_entries = self._db.list_world_entries(book_id)
        chapters = self._db.list_chapters(book_id)
        relationships = self._db.list_relationships(book_id)

        results: dict[str, str] = {}

        current_state = self._build_current_state(book_title, book_outline, characters, world_entries, chapters)
        self._write_file(book_id, "current_state.md", current_state)
        results["current_state.md"] = current_state

        character_matrix = self._build_character_matrix(characters, relationships)
        self._write_file(book_id, "character_matrix.md", character_matrix)
        results["character_matrix.md"] = character_matrix

        chapter_summaries = self._build_chapter_summaries(book_title, chapters)
        self._write_file(book_id, "chapter_summaries.md", chapter_summaries)
        results["chapter_summaries.md"] = chapter_summaries

        particle_ledger = self._read_file(book_id, "particle_ledger.md")
        if not particle_ledger.strip():
            particle_ledger = self._build_particle_ledger(world_entries, chapters)
            self._write_file(book_id, "particle_ledger.md", particle_ledger)
        results["particle_ledger.md"] = particle_ledger

        pending_hooks = self._read_file(book_id, "pending_hooks.md")
        if not pending_hooks.strip():
            pending_hooks = self._build_pending_hooks_init()
            self._write_file(book_id, "pending_hooks.md", pending_hooks)
        results["pending_hooks.md"] = pending_hooks

        subplot_board = self._read_file(book_id, "subplot_board.md")
        if not subplot_board.strip():
            subplot_board = self._build_subplot_board(book_outline, chapters)
            self._write_file(book_id, "subplot_board.md", subplot_board)
        results["subplot_board.md"] = subplot_board

        emotional_arcs = self._read_file(book_id, "emotional_arcs.md")
        if not emotional_arcs.strip():
            emotional_arcs = self._build_emotional_arcs(characters)
            self._write_file(book_id, "emotional_arcs.md", emotional_arcs)
        results["emotional_arcs.md"] = emotional_arcs

        return results

    def assemble_context(
        self,
        book_id: int,
        chapter_id: int | None = None,
        max_chars: int = 14000,
    ) -> str:
        self.build_all(book_id)
        sections: list[str] = []
        total = 0
        priority_order = [
            "current_state.md",
            "character_matrix.md",
            "pending_hooks.md",
            "chapter_summaries.md",
            "subplot_board.md",
            "emotional_arcs.md",
            "particle_ledger.md",
        ]
        for filename in priority_order:
            label = TRUTH_FILE_LABELS.get(filename, filename)
            content = self._read_file(book_id, filename)
            if not content:
                continue
            block = f"## {label}\n{content}"
            block_len = len(block)
            if total + block_len > max_chars:
                remaining = max_chars - total - 120
                if remaining < 300:
                    break
                block = f"## {label}\n{content[:remaining]}\n..."
            sections.append(block)
            total += len(block)
        return "\n\n".join(sections)

    def update_after_chapter_save(self, book_id: int, chapter_id: int) -> None:
        chapter = self._db.get_chapter(chapter_id)
        if not chapter:
            return
        self.build_all(book_id)

    def register_hook(
        self,
        book_id: int,
        hook_description: str,
        source_chapter_title: str = "",
    ) -> int:
        hooks = self._parse_hooks(book_id)
        new_index = max([h.get("index", 0) for h in hooks], default=0) + 1
        hook_entry = {
            "index": new_index,
            "description": hook_description.strip(),
            "source": source_chapter_title.strip(),
            "status": "pending",
            "resolution": "",
            "resolved_in": "",
        }
        hooks.append(hook_entry)
        self._write_hooks(book_id, hooks)
        return new_index

    def mark_hook_resolved(
        self,
        book_id: int,
        hook_index: int,
        resolution_note: str = "",
        resolved_in: str = "",
    ) -> bool:
        hooks = self._parse_hooks(book_id)
        for h in hooks:
            if h.get("index") == hook_index:
                h["status"] = "resolved"
                h["resolution"] = resolution_note.strip()
                h["resolved_in"] = resolved_in.strip()
                self._write_hooks(book_id, hooks)
                return True
        return False

    def list_pending_hooks(self, book_id: int) -> list[dict[str, Any]]:
        hooks = self._parse_hooks(book_id)
        return [h for h in hooks if h.get("status") == "pending"]

    def list_all_hooks(self, book_id: int) -> list[dict[str, Any]]:
        return self._parse_hooks(book_id)

    def _parse_hooks(self, book_id: int) -> list[dict[str, Any]]:
        content = self._read_file(book_id, "pending_hooks.md")
        if not content:
            return []
        hooks: list[dict[str, Any]] = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "（暂无" in line:
                continue
            if line.startswith("{") or line.startswith("["):
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and "description" in entry:
                        hooks.append(entry)
                except json.JSONDecodeError:
                    continue
        return hooks

    def _write_hooks(self, book_id: int, hooks: list[dict[str, Any]]) -> None:
        lines: list[str] = [
            "# 待回收伏笔 / Pending Hooks",
            "",
            "每行一个 JSON 对象，描述一个伏笔。",
            "格式：{\"index\":1,\"description\":\"...\",\"source\":\"...\",\"status\":\"pending|resolved\",\"resolution\":\"\",\"resolved_in\":\"\"}",
            "",
        ]
        for h in hooks:
            lines.append(json.dumps(h, ensure_ascii=False))
        self._write_file(book_id, "pending_hooks.md", "\n".join(lines))

    def _build_current_state(
        self,
        book_title: str,
        book_outline: str,
        characters: list[Any],
        world_entries: list[Any],
        chapters: list[Any],
    ) -> str:
        lines = [f"# {book_title} — 当前状态", ""]
        if book_outline.strip():
            lines.append("## 全书大纲")
            lines.append(book_outline.strip())
            lines.append("")
        if characters:
            lines.append("## 人物总览")
            for ch_row in characters[:30]:
                ch = dict(ch_row) if not isinstance(ch_row, dict) else ch_row
                name = str(ch.get("name", "") or "").strip()
                role = str(ch.get("role", "") or "").strip()
                profile = str(ch.get("profile_text", "") or "").strip()
                if not name:
                    continue
                parts = [f"- **{name}**"]
                if role:
                    parts.append(f"（{role}）")
                if profile:
                    parts.append(f"：{profile[:200]}")
                lines.append("".join(parts))
            lines.append("")
        if world_entries:
            lines.append("## 世界观设定")
            for we_row in world_entries[:30]:
                item = dict(we_row) if not isinstance(we_row, dict) else we_row
                name = str(item.get("name", "") or "").strip()
                category = str(item.get("category", "") or "").strip()
                content = str(item.get("content_text", "") or "").strip()
                if not name:
                    continue
                label = f"- **{name}**"
                if category:
                    label += f"（{category}）"
                if content:
                    label += f"：{content[:300]}"
                lines.append(label)
            lines.append("")
        if chapters:
            lines.append("## 章节进度")
            last_few = chapters[-8:] if len(chapters) > 8 else chapters
            for ch_row in last_few:
                ch = dict(ch_row) if not isinstance(ch_row, dict) else ch_row
                title = str(ch.get("title", "") or "").strip()
                summary = str(ch.get("summary_text", "") or "").strip()
                if not title:
                    continue
                entry = f"- {title}"
                if summary:
                    entry += f"：{summary[:120]}"
                lines.append(entry)
            lines.append("")
        return "\n".join(lines)

    def _build_character_matrix(
        self,
        characters: list[Any],
        relationships: list[Any],
    ) -> str:
        lines = ["# 人物关系矩阵", ""]
        char_names: dict[int, str] = {}
        for ch_row in characters:
            ch = dict(ch_row) if not isinstance(ch_row, dict) else ch_row
            cid = int(ch.get("id", 0) or 0)
            name = str(ch.get("name", "") or "").strip()
            if cid and name:
                char_names[cid] = name
        if relationships:
            lines.append("## 关系列表")
            for rel_row in relationships:
                rel = dict(rel_row) if not isinstance(rel_row, dict) else rel_row
                source = str(rel.get("source_name", "") or rel.get("source", "")).strip()
                target = str(rel.get("target_name", "") or rel.get("target", "")).strip()
                rtype = str(rel.get("relationship_type", "") or "").strip()
                desc = str(rel.get("description", "") or "").strip()
                if not source or not target:
                    continue
                entry = f"- {source} ←→ {target}"
                if rtype:
                    entry += f" [{rtype}]"
                if desc:
                    entry += f"：{desc[:100]}"
                lines.append(entry)
        else:
            lines.append("## 关系列表")
            lines.append("（暂无人物关系数据）")
        lines.append("")
        return "\n".join(lines)

    def _build_chapter_summaries(
        self,
        book_title: str,
        chapters: list[Any],
    ) -> str:
        lines = [f"# {book_title} — 章节摘要", ""]
        if not chapters:
            lines.append("（暂无章节）")
            return "\n".join(lines)
        for ch_row in chapters:
            ch = dict(ch_row) if not isinstance(ch_row, dict) else ch_row
            title = str(ch.get("title", "") or "").strip()
            summary = str(ch.get("summary_text", "") or "").strip()
            outline = str(ch.get("outline", "") or "").strip()
            if not title:
                continue
            lines.append(f"## {title}")
            if outline:
                lines.append(f"**大纲**：{outline[:200]}")
            if summary:
                lines.append(f"**摘要**：{summary}")
            else:
                lines.append("（暂无摘要）")
            lines.append("")
        return "\n".join(lines)

    def _build_particle_ledger(
        self,
        world_entries: list[Any],
        chapters: list[Any],
    ) -> str:
        lines = ["# 关键道具账本 / Particle Ledger", ""]
        items: list[dict[str, Any]] = []
        for we_row in world_entries:
            we = dict(we_row) if not isinstance(we_row, dict) else we_row
            name = str(we.get("name", "") or "").strip()
            category = str(we.get("category", "") or "").strip()
            content = str(we.get("content_text", "") or "").strip()
            if not name:
                continue
            if category in {"道具", "物品", "神器", "宝物", "item", "artifact"}:
                items.append({"name": name, "category": category, "content": content})
        if items:
            for item in items:
                lines.append(f"## {item['name']}（{item['category']}）")
                if item["content"]:
                    lines.append(item["content"][:300])
                lines.append("")
        else:
            lines.append("（暂无关键道具记录——可在世界观条目中添加「道具/物品」分类）")
        return "\n".join(lines)

    def _build_pending_hooks_init(self) -> str:
        return "\n".join([
            "# 待回收伏笔 / Pending Hooks",
            "",
            "每行一个 JSON 对象，描述一个伏笔。",
            "格式：{\"index\":1,\"description\":\"...\",\"source\":\"...\",\"status\":\"pending|resolved\",\"resolution\":\"\",\"resolved_in\":\"\"}",
            "",
            "（暂无伏笔记录）",
        ])

    def _build_subplot_board(
        self,
        book_outline: str,
        chapters: list[Any],
    ) -> str:
        lines = ["# 支线看板 / Subplot Board", ""]
        lines.append("## 自动提取的支线提示")
        lines.append("")
        subplot_hints: set[str] = set()
        for ch_row in chapters:
            ch = dict(ch_row) if not isinstance(ch_row, dict) else ch_row
            outline = str(ch.get("outline", "") or "").strip()
            summary = str(ch.get("summary_text", "") or "").strip()
            combined = f"{outline}\n{summary}"
            for keyword in ["复仇", "调查", "成长", "守护", "逃亡", "寻宝", "权谋", "爱情", "友情", "背叛"]:
                if keyword in combined:
                    subplot_hints.add(keyword)
        if subplot_hints:
            for hint in sorted(subplot_hints):
                lines.append(f"- 检测到「{hint}」相关线索")
        else:
            if book_outline:
                lines.append(f"- 大纲概要：{book_outline[:200]}")
            else:
                lines.append("（暂无支线信息）")
        lines.append("")
        return "\n".join(lines)

    def _build_emotional_arcs(
        self,
        characters: list[Any],
    ) -> str:
        lines = ["# 情感弧光 / Emotional Arcs", ""]
        if not characters:
            lines.append("（暂无人物数据）")
            return "\n".join(lines)
        for ch_row in characters[:10]:
            ch = dict(ch_row) if not isinstance(ch_row, dict) else ch_row
            name = str(ch.get("name", "") or "").strip()
            role = str(ch.get("role", "") or "").strip()
            if not name:
                continue
            lines.append(f"## {name}")
            if role:
                lines.append(f"- 角色定位：{role}")
            lines.append("- 情感状态：[待追踪]")
            lines.append("- 关键节点：[]")
            lines.append("")
        return "\n".join(lines)
