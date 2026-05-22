from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from novel_app.truth import TruthManager
from novel_app.truth.truth_manager import MAX_TRUTH_FILE_BYTES


class FakeDB:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def get_book(self, book_id: int) -> dict | None:
        return {"id": book_id, "title": "测试作品", "outline_text": "测试大纲：主角觉醒能力。"}

    def list_characters(self, book_id: int) -> list[dict]:
        return [
            {"id": 1, "name": "张三", "role": "主角", "profile_text": "一个普通少年，觉醒了时间回溯能力。"},
            {"id": 2, "name": "李四", "role": "反派", "profile_text": "神秘组织的首领。"},
            {"id": 3, "name": "王五", "role": "导师", "profile_text": "隐世高人，引导主角成长。"},
        ]

    def list_world_entries(self, book_id: int) -> list[dict]:
        return [
            {"id": 1, "name": "时间回溯", "category": "能力", "content_text": "可以回到过去某个时间点，但有冷却时间限制。"},
            {"id": 2, "name": "命运之剑", "category": "道具", "content_text": "一把上古神器。"},
        ]

    def list_chapters(self, book_id: int) -> list[dict]:
        return [
            {"id": 1, "title": "第一章：觉醒", "summary_text": "张三在车祸中觉醒了能力。", "outline": ""},
            {"id": 2, "title": "第二章：初战", "summary_text": "张三第一次使用能力与神秘人战斗。", "outline": ""},
            {"id": 3, "title": "第三章：真相", "summary_text": "张三发现了能力的秘密。", "outline": ""},
        ]

    def list_relationships(self, book_id: int) -> list[dict]:
        return [
            {"source_name": "张三", "target_name": "李四", "relationship_type": "敌人", "description": "立场对立。"},
            {"source_name": "张三", "target_name": "王五", "relationship_type": "师生", "description": "王五是张三的导师。"},
        ]

    def get_chapter(self, chapter_id: int) -> dict | None:
        chapters = self.list_chapters(0)
        for ch in chapters:
            if ch["id"] == chapter_id:
                return ch
        return None


@pytest.fixture
def truth_manager() -> TruthManager:
    with tempfile.TemporaryDirectory() as tmp:
        db = FakeDB(Path(tmp))
        tm = TruthManager(Path(tmp) / "data", db)
        yield tm


class TestTruthManager:
    def test_build_all_creates_seven_files(self, truth_manager: TruthManager) -> None:
        results = truth_manager.build_all(1)
        assert len(results) == 7
        for filename in [
            "current_state.md",
            "chapter_summaries.md",
            "character_matrix.md",
            "particle_ledger.md",
            "pending_hooks.md",
            "subplot_board.md",
            "emotional_arcs.md",
        ]:
            assert filename in results
            assert len(results[filename]) > 0

    def test_read_existing_file(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        content = truth_manager.read(1, "current_state.md")
        assert "测试作品" in content
        assert "张三" in content

    def test_read_nonexistent_file(self, truth_manager: TruthManager) -> None:
        content = truth_manager.read(1, "current_state.md")
        assert content == ""

    def test_read_invalid_filename(self, truth_manager: TruthManager) -> None:
        with pytest.raises(ValueError, match="Unknown truth file"):
            truth_manager.read(1, "invalid.md")

    def test_assemble_context_respects_max_chars(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        context = truth_manager.assemble_context(1, max_chars=500)
        assert len(context) <= 600

    def test_register_and_mark_hook(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        idx = truth_manager.register_hook(1, "主角的能力似乎有更大的秘密。", "第三章：真相")
        assert idx > 0
        pending = truth_manager.list_pending_hooks(1)
        assert any(h["index"] == idx for h in pending)
        resolved = truth_manager.mark_hook_resolved(1, idx, "已揭示能力来源。", "第五章")
        assert resolved
        pending_after = truth_manager.list_pending_hooks(1)
        assert not any(h["index"] == idx for h in pending_after)

    def test_list_all_hooks(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        truth_manager.register_hook(1, "伏笔A", "第一章")
        truth_manager.register_hook(1, "伏笔B", "第二章")
        truth_manager.mark_hook_resolved(1, 1, "已回收", "第三章")
        all_hooks = truth_manager.list_all_hooks(1)
        assert len(all_hooks) == 2

    def test_update_after_chapter_save(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        old_content = truth_manager.read(1, "chapter_summaries.md")
        truth_manager.update_after_chapter_save(1, 1)
        new_content = truth_manager.read(1, "chapter_summaries.md")
        assert len(new_content) > 0

    def test_current_state_includes_characters(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        content = truth_manager.read(1, "current_state.md")
        assert "张三" in content
        assert "主角" in content

    def test_current_state_includes_world_entries(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        content = truth_manager.read(1, "current_state.md")
        assert "世界观设定" in content
        assert "时间回溯" in content
        assert "冷却时间限制" in content

    def test_character_matrix_includes_relationships(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        content = truth_manager.read(1, "character_matrix.md")
        assert "张三" in content
        assert "李四" in content
        assert "敌人" in content or "师生" in content

    def test_particle_ledger_has_items(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        content = truth_manager.read(1, "particle_ledger.md")
        assert "命运之剑" in content

    def test_subplot_board_detects_keywords(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        content = truth_manager.read(1, "subplot_board.md")
        assert "支线" in content

    def test_emotional_arcs_has_characters(self, truth_manager: TruthManager) -> None:
        truth_manager.build_all(1)
        content = truth_manager.read(1, "emotional_arcs.md")
        assert "张三" in content

    def test_write_file_truncates_to_utf8_byte_limit(self, truth_manager: TruthManager) -> None:
        content = "标题\n" + ("这是很长的中文内容" * 4000)
        truth_manager._write_file(1, "current_state.md", content)

        path = truth_manager._truth_dir(1) / "current_state.md"
        written = path.read_text(encoding="utf-8")
        assert written
        assert len(written.encode("utf-8")) <= MAX_TRUTH_FILE_BYTES
