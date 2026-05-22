from __future__ import annotations

import unittest
import sqlite3
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from novel_app.database import Database, UNASSIGNED_VOLUMES
from novel_app.structured_templates import (
    BOOK_OUTLINE_FORM_MIGRATION_ID,
    CHARACTER_PROFILE_FORM_MIGRATION_ID,
    STRUCTURED_TEMPLATE_MIGRATION_ID,
    WORLD_FORM_MIGRATION_ID,
)


class DatabaseExtensionTests(unittest.TestCase):
    def test_relationships_ai_spans_and_events_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("测试书")
            source_id = db.create_character(book_id, "甲")
            target_id = db.create_character(book_id, "乙")
            db.update_character_position(source_id, 12.5, -8.0)
            relationship_id = db.create_relationship(book_id, source_id, target_id, "师徒", "旧识")
            chapter_id = db.create_chapter(book_id, "第一章")
            source_ref_id = db.create_reference_source("参考", source_path=str(Path(tmp) / "ref.txt"))
            db.replace_skills_for_source(
                source_ref_id,
                [
                    {
                        "name": "全局风格",
                        "category": "style",
                        "summary": "summary",
                        "instruction": "instruction",
                    }
                ],
            )
            skill_id = int(db.list_skills(source_ref_id)[0]["id"])
            db.bind_skill_to_global(skill_id)
            db.bind_skill_to_book(book_id, skill_id)
            db.bind_skill_to_chapter(chapter_id, skill_id)
            snapshot_id = db.create_snapshot(chapter_id, "before review", "old outline", "old content")
            span_id = db.add_chapter_ai_span(chapter_id, 2, 9, "job-1")
            event_id = db.create_chapter_event(book_id, chapter_id, "相遇", "甲乙初见")

            relationship = db.get_relationship(relationship_id)
            self.assertIsNotNone(relationship)
            self.assertEqual(relationship["relationship_type"], "师徒")
            self.assertEqual(len(db.list_relationships_by_character(source_id)), 1)
            db.replace_book_relationships(
                book_id,
                [
                    {
                        "source_character_id": target_id,
                        "target_character_id": source_id,
                        "relationship_type": "同盟",
                        "description": "AI 分析刷新",
                    }
                ],
            )
            replaced_relationships = db.list_relationships(book_id)
            self.assertEqual(len(replaced_relationships), 1)
            self.assertEqual(replaced_relationships[0]["relationship_type"], "同盟")
            self.assertEqual(replaced_relationships[0]["description"], "AI 分析刷新")
            self.assertEqual(len(db.list_bound_skills_for_global()), 1)
            self.assertEqual(len(db.list_bound_skills_for_book(book_id)), 1)
            self.assertEqual(len(db.list_bound_skills_for_chapter(chapter_id)), 1)
            db.unbind_skill_from_global(skill_id)
            self.assertEqual(db.list_bound_skills_for_global(), [])

            character = db.get_character(source_id)
            self.assertIsNotNone(character)
            self.assertEqual(float(character["graph_x"]), 12.5)
            self.assertEqual(float(character["graph_y"]), -8.0)

            spans = db.list_chapter_ai_spans(chapter_id)
            self.assertEqual(len(spans), 1)
            self.assertEqual(int(spans[0]["id"]), span_id)

            events = db.list_chapter_events(book_id)
            self.assertEqual(len(events), 1)
            self.assertEqual(int(events[0]["id"]), event_id)

            run_id = db.create_review_run(
                book_id=book_id,
                chapter_id=chapter_id,
                scope_type="chapter",
                status="applied",
                truth_snapshot="truth",
                summary="summary",
                overall_score=86,
                snapshot_id=snapshot_id,
                revised_content="content",
                revised_outline="outline",
                final_verdict="approve",
                risk_notes="risk",
                template_comparison="template delta",
                applied=True,
            )
            db.replace_review_findings(
                run_id,
                [
                    {
                        "agent": "plot_auditor",
                        "severity": "high",
                        "category": "plot",
                        "location_hint": "chapter",
                        "quote": "quote",
                        "issue": "issue",
                        "suggestion": "suggestion",
                    }
                ],
            )
            runs = db.list_review_runs(book_id, chapter_id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(int(runs[0]["id"]), run_id)
            self.assertEqual(int(runs[0]["snapshot_id"]), snapshot_id)
            self.assertEqual(runs[0]["template_comparison"], "template delta")
            self.assertTrue(runs[0]["applied_at"])
            stored_run = db.get_review_run(run_id)
            self.assertIsNotNone(stored_run)
            self.assertEqual(int(stored_run["snapshot_id"]), snapshot_id)
            self.assertEqual(stored_run["template_comparison"], "template delta")
            findings = db.list_review_findings(run_id)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["severity"], "high")
            db.close()

    def test_review_run_migration_adds_snapshot_columns(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "novels.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE review_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    chapter_id INTEGER,
                    scope_type TEXT NOT NULL DEFAULT 'chapter',
                    status TEXT NOT NULL DEFAULT 'completed',
                    truth_snapshot TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    overall_score INTEGER NOT NULL DEFAULT 0,
                    revised_content TEXT NOT NULL DEFAULT '',
                    revised_outline TEXT NOT NULL DEFAULT '',
                    final_verdict TEXT NOT NULL DEFAULT '',
                    risk_notes TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.close()

            db = Database(path)
            db.initialize()
            columns = {row["name"] for row in db.connection.execute("PRAGMA table_info(review_runs)").fetchall()}
            self.assertIn("snapshot_id", columns)
            self.assertIn("applied_at", columns)
            self.assertIn("template_comparison", columns)
            tag_columns = {row["name"] for row in db.connection.execute("PRAGMA table_info(chapter_tags)").fetchall()}
            self.assertEqual({"chapter_id", "tag", "created_at"}, tag_columns)
            db.close()

    def test_chapter_template_tags_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("Template Book")
            volume_id = db.create_volume(book_id, "Volume")
            first_id = db.create_chapter(book_id, "Template A", volume_id=volume_id)
            second_id = db.create_chapter(book_id, "Normal B", volume_id=volume_id)
            db.update_chapter(first_id, "outline", '“hi” scene')
            db.update_chapter(second_id, "", "body")

            self.assertFalse(db.has_chapter_tag(first_id, "template"))
            db.set_chapter_tag(first_id, "template")
            self.assertTrue(db.has_chapter_tag(first_id, "template"))
            templates = db.list_template_chapters(book_id)
            self.assertEqual([int(row["id"]) for row in templates], [first_id])
            self.assertEqual(templates[0]["volume_title"], "Volume")

            chapters = db.list_chapters(book_id)
            by_id = {int(row["id"]): row for row in chapters}
            self.assertEqual(int(by_id[first_id]["is_template"]), 1)
            self.assertEqual(int(by_id[second_id]["is_template"]), 0)
            self.assertGreater(int(by_id[first_id]["word_count"]), 0)

            db.remove_chapter_tag(first_id, "template")
            self.assertFalse(db.has_chapter_tag(first_id, "template"))
            self.assertEqual(db.list_template_chapters(book_id), [])
            db.close()

    def test_media_path_normalization_keeps_data_dir_relative(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            image = db.book_covers_dir / "cover.png"
            image.write_bytes(b"not-a-real-image")
            stored = db.normalize_media_path(image)
            self.assertEqual(stored, "media/book_covers/cover.png")
            self.assertEqual(db.resolve_media_path(stored), image)
            db.close()

    def test_configured_data_dir_imports_pre_v13_legacy_data_once(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_data = root / "exe" / "data"
            legacy_data = root / "appdata" / "灵枢" / "data"
            legacy_data.mkdir(parents=True)
            connection = sqlite3.connect(legacy_data / "novels.db")
            connection.execute(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    outline_text TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute("INSERT INTO books (title, outline_text) VALUES ('旧库书', '旧内容')")
            connection.commit()
            connection.close()
            (legacy_data / "ai_settings.json").write_text('{"remote_enabled": true}', encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "SIMPLE_AI_NOVEL_DATA_DIR": str(target_data),
                    "SIMPLE_AI_NOVEL_LEGACY_DATA_DIRS": str(legacy_data),
                    "APPDATA": str(root / "appdata"),
                    "LOCALAPPDATA": str(root / "localappdata"),
                },
            ):
                db = Database()
                db.initialize()
                self.assertEqual(db.data_dir, target_data)
                self.assertTrue((target_data / "novels.db").exists())
                self.assertTrue(legacy_data.exists())
                self.assertTrue((target_data / "ai_settings.json").exists())
                self.assertIn(legacy_data.resolve(), db.imported_legacy_data_dirs)
                book = db.get_book(1)
                self.assertIsNotNone(book)
                assert book is not None
                self.assertEqual(book["title"], "旧库书")
                self.assertIn("旧内容", book["outline_text"])
                self.assertEqual(len(db.list_books()), 1)
                db.close()

                db = Database()
                db.initialize()
                self.assertEqual(len(db.list_books()), 1)
                db.close()

    def test_configured_data_dir_imports_v13_legacy_data_without_deleting_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_data = root / "exe" / "data"
            legacy_data = root / "appdata" / "灵枢" / "data"
            legacy_data.mkdir(parents=True)
            connection = sqlite3.connect(legacy_data / "novels.db")
            connection.executescript(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    outline_text TEXT NOT NULL DEFAULT '',
                    outline_data_json TEXT NOT NULL DEFAULT '',
                    world_text TEXT NOT NULL DEFAULT '',
                    world_data_json TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    profile_text TEXT NOT NULL DEFAULT '',
                    profile_data_json TEXT NOT NULL DEFAULT ''
                );
                """
            )
            connection.execute("INSERT INTO books (title) VALUES ('v13 book')")
            connection.commit()
            connection.close()

            with patch.dict(
                os.environ,
                {
                    "SIMPLE_AI_NOVEL_DATA_DIR": str(target_data),
                    "SIMPLE_AI_NOVEL_LEGACY_DATA_DIRS": str(legacy_data),
                    "APPDATA": str(root / "appdata"),
                    "LOCALAPPDATA": str(root / "localappdata"),
                },
            ):
                db = Database()
                db.initialize()
                self.assertTrue(legacy_data.exists())
                self.assertIn(legacy_data.resolve(), db.imported_legacy_data_dirs)
                books = db.list_books()
                self.assertEqual(len(books), 1)
                self.assertEqual(books[0]["title"], "v13 book")
                db.close()

    def test_configured_current_data_dir_migrates_pre_v13_database(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_data = root / "exe" / "data"
            target_data.mkdir(parents=True)
            connection = sqlite3.connect(target_data / "novels.db")
            connection.execute(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    outline_text TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute("INSERT INTO books (title, outline_text) VALUES ('old current', 'old')")
            connection.commit()
            connection.close()

            with patch.dict(
                os.environ,
                {
                    "SIMPLE_AI_NOVEL_DATA_DIR": str(target_data),
                    "SIMPLE_AI_NOVEL_LEGACY_DATA_DIRS": "",
                    "APPDATA": str(root / "appdata"),
                    "LOCALAPPDATA": str(root / "localappdata"),
                },
            ):
                db = Database()
                db.initialize()
                self.assertTrue((target_data / "novels.db").exists())
                book = db.get_book(1)
                self.assertIsNotNone(book)
                assert book is not None
                self.assertEqual(book["title"], "old current")
                self.assertIn("old", book["outline_text"])
                db.close()

    def test_structured_template_migration_preserves_legacy_book_outline_once(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "novels.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    outline_text TEXT NOT NULL DEFAULT '',
                    cover_image_path TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    profile_text TEXT NOT NULL DEFAULT '',
                    image_path TEXT NOT NULL DEFAULT '',
                    graph_x REAL NOT NULL DEFAULT 0,
                    graph_y REAL NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE world_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '设定',
                    content_text TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO books (title, outline_text) VALUES ('旧书', '旧版书籍大纲');
                INSERT INTO characters (book_id, name, role, profile_text) VALUES (1, '林一', '男主', '旧版人物卡');
                INSERT INTO world_entries (book_id, name, category, content_text) VALUES (1, '旧世界', '世界', '旧版世界观');
                """
            )
            connection.close()

            db = Database(path)
            db.initialize()
            self.assertIn("# 书籍大纲模板", db.get_book(1)["outline_text"])
            self.assertIn("旧版内容", db.get_book(1)["outline_text"])
            self.assertIn("旧版书籍大纲", db.get_book(1)["outline_text"])
            self.assertIn("outline_data_json", db.get_book(1).keys())
            self.assertIn("旧版书籍大纲", db.get_book(1)["outline_data_json"])
            self.assertIn("# 主角设定模板", db.get_character(1)["profile_text"])
            self.assertNotIn("旧版人物卡", db.get_character(1)["profile_text"])
            self.assertIn("profile_data_json", db.get_character(1).keys())
            self.assertIn("character_profile_form_v1", db.get_character(1)["profile_data_json"])
            self.assertIn("# 世界观设定模板", db.get_book(1)["world_text"])
            self.assertNotIn("旧版世界观：旧世界", db.get_book(1)["world_text"])
            self.assertNotIn("旧版世界观", db.get_book(1)["world_text"])
            self.assertIn("shape_fictional", db.get_book(1)["world_data_json"])
            self.assertEqual(db.connection.execute("SELECT COUNT(*) AS count FROM world_entries").fetchone()["count"], 0)
            structured_applied = db.connection.execute(
                "SELECT 1 FROM app_migrations WHERE id = ?",
                (STRUCTURED_TEMPLATE_MIGRATION_ID,),
            ).fetchone()
            outline_form_applied = db.connection.execute(
                "SELECT 1 FROM app_migrations WHERE id = ?",
                (BOOK_OUTLINE_FORM_MIGRATION_ID,),
            ).fetchone()
            world_form_applied = db.connection.execute(
                "SELECT 1 FROM app_migrations WHERE id = ?",
                (WORLD_FORM_MIGRATION_ID,),
            ).fetchone()
            character_form_applied = db.connection.execute(
                "SELECT 1 FROM app_migrations WHERE id = ?",
                (CHARACTER_PROFILE_FORM_MIGRATION_ID,),
            ).fetchone()
            self.assertIsNotNone(structured_applied)
            self.assertIsNotNone(outline_form_applied)
            self.assertIsNotNone(world_form_applied)
            self.assertIsNotNone(character_form_applied)
            db.update_book_outline(1, "用户新版本内容")
            db.close()

            db = Database(path)
            db.initialize()
            self.assertIn("# 书籍大纲模板", db.get_book(1)["outline_text"])
            self.assertIn("用户新版本内容", db.get_book(1)["outline_text"])
            db.close()

    def test_create_book_writes_outline_form_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("表单书")
            book = db.get_book(book_id)
            self.assertIsNotNone(book)
            assert book is not None
            self.assertIn("# 书籍大纲模板", book["outline_text"])
            self.assertIn("表单书", book["outline_text"])
            self.assertIn("working_title", book["outline_data_json"])
            self.assertIn("# 世界观设定模板", book["world_text"])
            self.assertIn("shape_fictional", book["world_data_json"])
            form = db.get_book_outline_form(book_id)
            form["fields"]["length_long"]["checked"] = True
            db.update_book_outline_form(book_id, form)
            updated = db.get_book(book_id)
            self.assertIn("- [x] 长篇（60 万-200 万字）", updated["outline_text"])
            self.assertIn('"length_long"', updated["outline_data_json"])
            db.close()

    def test_create_character_writes_profile_form_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("人物表单书")
            character_id = db.create_character(book_id, "林一")

            character = db.get_character(character_id)
            self.assertIsNotNone(character)
            assert character is not None
            self.assertIn("# 配角设定模板", character["profile_text"])
            self.assertIn("character_profile_form_v1", character["profile_data_json"])
            self.assertIn("relationship_to_protagonist", character["profile_data_json"])
            db.close()

    def test_book_world_form_is_single_book_level_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("世界书")
            form = db.get_book_world_form(book_id)
            form["fields"]["shape_fictional"]["checked"] = True
            form["fields"]["tech_level"]["value"] = "蒸汽"
            form["fields"]["world_rules_table"]["value"] = "世界名称：雾海"
            db.update_book_world_form(book_id, form)

            book = db.get_book(book_id)
            self.assertIn("- [x] 架空世界", book["world_text"])
            self.assertIn("- 科技水平：蒸汽", book["world_text"])
            self.assertIn("世界名称：雾海", book["world_text"])
            worlds = db.list_world_entries(book_id)
            self.assertEqual(len(worlds), 1)
            self.assertEqual(worlds[0]["name"], "世界观总设定")
            self.assertIn("世界名称：雾海", worlds[0]["content_text"])
            db.close()

    def test_book_outline_volume_plans_follow_current_volumes(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("分卷书")
            first_volume = db.create_volume(book_id, "第一阶段")
            second_volume = db.create_volume(book_id, "第二阶段")

            form = db.get_book_outline_form(book_id)
            self.assertEqual([plan["volume_title"] for plan in form["volume_plans"]], ["第一阶段", "第二阶段"])
            form["volume_plans"][0]["fields"]["core_events"]["value"] = "主角觉醒"
            form["volume_plans"][1]["fields"]["stage_goal"]["value"] = "抵达王都"
            db.update_book_outline_form(book_id, form)
            book = db.get_book(book_id)
            self.assertIn("### 第1卷规划：第一阶段", book["outline_text"])
            self.assertIn("### 第2卷规划：第二阶段", book["outline_text"])
            self.assertIn("- 核心事件：主角觉醒", book["outline_text"])
            self.assertIn("- 阶段目标：抵达王都", book["outline_text"])

            db.rename_volume(second_volume, "第二卷")
            renamed = db.get_book(book_id)
            self.assertIn("### 第2卷规划：第二卷", renamed["outline_text"])
            self.assertIn("- 阶段目标：抵达王都", renamed["outline_text"])

            db.delete_volume(first_volume)
            deleted = db.get_book(book_id)
            self.assertNotIn("### 第2卷规划：第二卷", deleted["outline_text"])
            self.assertIn("### 第1卷规划：第二卷", deleted["outline_text"])
            self.assertNotIn("主角觉醒", deleted["outline_text"])
            db.close()

    def test_design_lists_include_markdown_content_for_truth_context(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("结构化")
            character_id = db.create_character(book_id, "林一")
            db.update_character(character_id, "林一", "男主", "# 主角设定模板\n\n用户填写人物内容")
            world_form = db.get_book_world_form(book_id)
            world_form["fields"]["world_rules_table"]["value"] = "用户填写世界观"
            db.update_book_world_form(book_id, world_form)

            characters = db.list_characters(book_id)
            worlds = db.list_world_entries(book_id)
            self.assertIn("用户填写人物内容", characters[0]["profile_text"])
            self.assertIn("用户填写世界观", worlds[0]["content_text"])
            db.close()

    def test_character_update_wraps_plain_text_in_template(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("人物模板书")
            character_id = db.create_character(book_id, "林一")

            db.update_character(character_id, "林一", "导师", "旧人物卡自由文本")

            character = db.get_character(character_id)
            self.assertIsNotNone(character)
            assert character is not None
            self.assertIn("# 配角设定模板", character["profile_text"])
            self.assertIn("## AI/用户补充", character["profile_text"])
            self.assertIn("旧人物卡自由文本", character["profile_text"])
            db.close()

    def test_character_blank_template_role_change_replaces_template(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("人物模板书")
            character_id = db.create_character(book_id, "林一")
            original = db.get_character(character_id)

            db.update_character(character_id, "林一", "男主", str(original["profile_text"]))

            character = db.get_character(character_id)
            self.assertIsNotNone(character)
            assert character is not None
            self.assertIn("# 主角设定模板", character["profile_text"])
            self.assertIn("- 身份/职业：男主", character["profile_text"])
            self.assertNotIn("# 配角设定模板", character["profile_text"])
            self.assertNotIn("## AI/用户补充", character["profile_text"])
            db.close()

    def test_create_chapter_after_keeps_volume_and_inserts_outline(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("长篇")
            volume_id = db.create_volume(book_id, "第一卷")
            first_id = db.create_chapter(book_id, "第一章", volume_id=volume_id)
            second_id = db.create_chapter(book_id, "第二章", volume_id=volume_id)

            inserted_id = db.create_chapter_after(first_id, "插入章", outline="新章大纲", content="")

            chapters = db.list_chapters(book_id, volume_id)
            self.assertEqual([int(row["id"]) for row in chapters], [first_id, inserted_id, second_id])
            inserted = db.get_chapter(inserted_id)
            self.assertIsNotNone(inserted)
            self.assertEqual(int(inserted["volume_id"]), volume_id)
            self.assertEqual(inserted["outline"], "新章大纲")
            self.assertEqual(inserted["content"], "")
            db.close()

    def test_create_chapter_after_keeps_anchor_scope_for_other_volumes_and_unassigned(self) -> None:
        with TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "novels.db")
            db.initialize()
            book_id = db.create_book("长篇")
            first_volume_id = db.create_volume(book_id, "第一卷")
            second_volume_id = db.create_volume(book_id, "第二卷")
            first_a = db.create_chapter(book_id, "第一卷 A", volume_id=first_volume_id)
            first_b = db.create_chapter(book_id, "第一卷 B", volume_id=first_volume_id)
            second_a = db.create_chapter(book_id, "第二卷 A", volume_id=second_volume_id)
            second_b = db.create_chapter(book_id, "第二卷 B", volume_id=second_volume_id)
            unassigned_a = db.create_chapter(book_id, "未分卷 A")
            unassigned_b = db.create_chapter(book_id, "未分卷 B")

            inserted_second = db.create_chapter_after(second_a, "第二卷插入章")
            inserted_unassigned = db.create_chapter_after(unassigned_a, "未分卷插入章")

            first_volume = db.list_chapters(book_id, first_volume_id)
            second_volume = db.list_chapters(book_id, second_volume_id)
            unassigned = db.list_chapters(book_id, UNASSIGNED_VOLUMES)
            self.assertEqual([int(row["id"]) for row in first_volume], [first_a, first_b])
            self.assertEqual([int(row["id"]) for row in second_volume], [second_a, inserted_second, second_b])
            self.assertEqual([int(row["id"]) for row in unassigned], [unassigned_a, inserted_unassigned, unassigned_b])
            self.assertEqual(db.get_chapter(inserted_second)["volume_id"], second_volume_id)
            self.assertIsNone(db.get_chapter(inserted_unassigned)["volume_id"])
            db.close()


if __name__ == "__main__":
    unittest.main()
