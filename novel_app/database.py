from __future__ import annotations

import json
import sqlite3
import sys
import os
import hashlib
import shutil
from pathlib import Path
from typing import Any

from novel_app.structured_templates import (
    BOOK_OUTLINE_FORM_MIGRATION_ID,
    CHARACTER_PROFILE_FORM_MIGRATION_ID,
    STRUCTURED_TEMPLATE_MIGRATION_ID,
    WORLD_FORM_MIGRATION_ID,
    book_outline_form_defaults,
    book_outline_form_to_markdown,
    book_outline_markdown_to_form,
    character_profile_form_defaults,
    character_profile_form_to_markdown,
    character_profile_markdown_to_form,
    normalize_book_outline_form,
    normalize_character_profile_form,
    normalize_world_form,
    merge_world_supplement,
    world_form_defaults,
    world_form_to_markdown,
    world_markdown_to_form,
    world_entry_template,
)

ALL_VOLUMES = "__all__"
UNASSIGNED_VOLUMES = "__unassigned__"


class Database:
    def __init__(self, db_path: Path | None = None) -> None:
        configured_data_dir = os.environ.get("SIMPLE_AI_NOVEL_DATA_DIR", "").strip()
        legacy_data_dirs = self._legacy_data_dirs_from_env()
        if db_path is None:
            legacy_data_dirs.extend(self._known_legacy_data_dirs())
        if configured_data_dir:
            self.data_dir = Path(configured_data_dir).expanduser()
        else:
            if getattr(sys, "frozen", False):
                base_dir = Path(sys.executable).resolve().parent
                appdata = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
                legacy_data_dirs.append(appdata / "SimpleAINovelApp" / "data")
            else:
                base_dir = Path(__file__).resolve().parent.parent
            self.data_dir = base_dir / "data"
        self.legacy_data_dirs = self._dedupe_legacy_data_dirs(legacy_data_dirs)
        self.imported_legacy_data_dirs: list[Path] = []
        self.legacy_import_errors: list[tuple[Path, str]] = []
        self.legacy_data_dirs = [path for path in self.legacy_data_dirs if path.exists()]
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.references_dir = self.data_dir / "references" / "imported_books"
        self.references_dir.mkdir(parents=True, exist_ok=True)
        self.project_references_dir = self.data_dir / "references" / "github_projects"
        self.project_references_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir = self.data_dir / "media"
        self.book_covers_dir = self.media_dir / "book_covers"
        self.character_images_dir = self.media_dir / "character_images"
        self.book_covers_dir.mkdir(parents=True, exist_ok=True)
        self.character_images_dir.mkdir(parents=True, exist_ok=True)

        self.exports_dir = self.data_dir / "exports"
        self.exports_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path or self.data_dir / "novels.db"
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def _legacy_data_dirs_from_env(self) -> list[Path]:
        raw = os.environ.get("SIMPLE_AI_NOVEL_LEGACY_DATA_DIRS", "").strip()
        if not raw:
            return []
        return [Path(item).expanduser() for item in raw.split(os.pathsep) if item.strip()]

    def _known_legacy_data_dirs(self) -> list[Path]:
        candidates: list[Path] = []
        known_names = (
            "灵枢",
            "灵枢v1.2",
            "灵枢-v1.2",
            "SimpleAINovelApp",
        )
        for env_name in ("APPDATA", "LOCALAPPDATA"):
            root_text = os.environ.get(env_name, "").strip()
            if not root_text:
                continue
            root = Path(root_text).expanduser()
            for name in known_names:
                candidates.append(root / name / "data")
            try:
                for child in root.iterdir():
                    if not child.is_dir():
                        continue
                    if "灵枢" in child.name or "SimpleAINovel" in child.name:
                        candidates.append(child / "data")
            except OSError:
                continue
        return candidates

    def _dedupe_legacy_data_dirs(self, legacy_dirs: list[Path]) -> list[Path]:
        result: list[Path] = []
        seen: set[Path] = set()
        for legacy_dir in legacy_dirs:
            try:
                resolved = Path(legacy_dir).expanduser().resolve()
            except OSError:
                continue
            if resolved == self.data_dir.resolve() or resolved in seen:
                continue
            seen.add(resolved)
            result.append(resolved)
        return result

    def _is_pre_v13_data_dir(self, data_dir: Path) -> bool:
        db_path = data_dir / "novels.db"
        if not db_path.exists():
            return False
        try:
            connection = sqlite3.connect(db_path)
            try:
                books_columns = self._table_columns(connection, "books")
                if not books_columns:
                    return False
                if "outline_data_json" not in books_columns or "world_data_json" not in books_columns:
                    return True
                character_columns = self._table_columns(connection, "characters")
                if character_columns and "profile_data_json" not in character_columns:
                    return True
                return False
            finally:
                connection.close()
        except sqlite3.Error:
            return False

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
        try:
            rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        except sqlite3.Error:
            return set()
        return {str(row[1]) for row in rows}

    def _data_dir_has_user_data(self, data_dir: Path) -> bool:
        if not data_dir.exists():
            return False
        for filename in ("novels.db", "ai_settings.json", "ui_settings.json"):
            if (data_dir / filename).exists():
                return True
        for dirname in ("media", "references", "exports", "rag_vectors", "ui"):
            directory = data_dir / dirname
            if directory.exists() and any(directory.iterdir()):
                return True
        return any(child.is_dir() and child.name.isdigit() for child in data_dir.iterdir())

    def _ensure_legacy_imports_table(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_imports (
                source_key TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                source_size INTEGER NOT NULL DEFAULT 0,
                source_mtime_ns INTEGER NOT NULL DEFAULT 0,
                book_count INTEGER NOT NULL DEFAULT 0,
                imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _legacy_source_signature(self, db_path: Path) -> tuple[str, int, int]:
        resolved = db_path.expanduser().resolve()
        stat = resolved.stat()
        material = f"{resolved}\0{stat.st_size}\0{stat.st_mtime_ns}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest(), int(stat.st_size), int(stat.st_mtime_ns)

    def _legacy_source_imported(self, source_key: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM legacy_imports WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        return row is not None

    def _import_legacy_data_dirs(self) -> None:
        if not self.legacy_data_dirs:
            return
        for legacy_dir in self.legacy_data_dirs:
            db_path = legacy_dir / "novels.db"
            if not db_path.exists():
                continue
            try:
                current_db = self.db_path.expanduser().resolve()
                source_db = db_path.expanduser().resolve()
            except OSError as exc:
                self.legacy_import_errors.append((legacy_dir, str(exc)))
                continue
            if source_db == current_db:
                continue
            try:
                source_key, source_size, source_mtime_ns = self._legacy_source_signature(source_db)
                if self._legacy_source_imported(source_key):
                    continue
                book_count = self._import_legacy_database(legacy_dir, source_db)
                self._copy_legacy_sidecar_files(legacy_dir)
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO legacy_imports
                        (source_key, source_path, source_size, source_mtime_ns, book_count)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (source_key, str(source_db), source_size, source_mtime_ns, book_count),
                )
                self.imported_legacy_data_dirs.append(legacy_dir.expanduser().resolve())
            except Exception as exc:  # noqa: BLE001
                self.legacy_import_errors.append((legacy_dir, str(exc)))

    def _copy_legacy_sidecar_files(self, legacy_dir: Path) -> None:
        for filename in ("ai_settings.json", "ui_settings.json"):
            source = legacy_dir / filename
            target = self.data_dir / filename
            if source.exists() and not target.exists():
                try:
                    shutil.copy2(source, target)
                except OSError as exc:
                    self.legacy_import_errors.append((source, str(exc)))

    def _import_legacy_database(self, legacy_dir: Path, source_db: Path) -> int:
        source = sqlite3.connect(source_db)
        source.row_factory = sqlite3.Row
        try:
            book_rows = self._legacy_rows(source, "books", ("id",))
            if not book_rows:
                return 0
            book_id_map: dict[int, int] = {}
            volume_id_map: dict[int, int] = {}
            chapter_id_map: dict[int, int] = {}
            character_id_map: dict[int, int] = {}

            for row in book_rows:
                old_book_id = self._safe_int(self._legacy_value(row, "id"), 0)
                if old_book_id <= 0:
                    continue
                book_id_map[old_book_id] = self._insert_legacy_book(row)

            for row in self._legacy_rows(source, "volumes", ("book_id", "sort_order", "id")):
                old_book_id = self._safe_int(self._legacy_value(row, "book_id"), 0)
                new_book_id = book_id_map.get(old_book_id)
                if not new_book_id:
                    continue
                old_volume_id = self._safe_int(self._legacy_value(row, "id"), 0)
                new_volume_id = self._insert_legacy_volume(new_book_id, row)
                if old_volume_id > 0:
                    volume_id_map[old_volume_id] = new_volume_id

            for row in self._legacy_rows(source, "chapters", ("book_id", "volume_id", "sort_order", "id")):
                old_book_id = self._safe_int(self._legacy_value(row, "book_id"), 0)
                new_book_id = book_id_map.get(old_book_id)
                if not new_book_id:
                    continue
                old_volume_id = self._safe_int(self._legacy_value(row, "volume_id"), 0)
                new_volume_id = volume_id_map.get(old_volume_id) if old_volume_id > 0 else None
                old_chapter_id = self._safe_int(self._legacy_value(row, "id"), 0)
                new_chapter_id = self._insert_legacy_chapter(new_book_id, new_volume_id, row)
                if old_chapter_id > 0:
                    chapter_id_map[old_chapter_id] = new_chapter_id

            self._import_legacy_world_entries(source, book_id_map)
            self._refresh_imported_book_outlines(book_id_map.values())

            for row in self._legacy_rows(source, "characters", ("book_id", "id")):
                old_book_id = self._safe_int(self._legacy_value(row, "book_id"), 0)
                new_book_id = book_id_map.get(old_book_id)
                if not new_book_id:
                    continue
                old_character_id = self._safe_int(self._legacy_value(row, "id"), 0)
                new_character_id = self._insert_legacy_character(new_book_id, row)
                if old_character_id > 0:
                    character_id_map[old_character_id] = new_character_id

            self._import_legacy_relationships(source, book_id_map, character_id_map)
            self._import_legacy_chapter_tags(source, chapter_id_map)
            self._import_legacy_chapter_events(source, book_id_map, chapter_id_map)
            return len(book_id_map)
        finally:
            source.close()

    def _legacy_rows(self, source: sqlite3.Connection, table_name: str, order_columns: tuple[str, ...]) -> list[sqlite3.Row]:
        columns = self._table_columns(source, table_name)
        if not columns:
            return []
        order = [column for column in order_columns if column in columns]
        order_sql = f" ORDER BY {', '.join(order)}" if order else ""
        return list(source.execute(f"SELECT * FROM {table_name}{order_sql}").fetchall())

    @staticmethod
    def _legacy_value(row: sqlite3.Row, key: str, default: Any = "") -> Any:
        return row[key] if key in row.keys() else default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _insert_legacy_book(self, row: sqlite3.Row) -> int:
        title = str(self._legacy_value(row, "title", "") or "").strip() or "旧版书籍"
        volume_specs: list[dict[str, Any]] = []
        outline_data = self._book_outline_json_to_data(str(self._legacy_value(row, "outline_data_json", "") or ""), title, volume_specs)
        if outline_data is None:
            outline_data = book_outline_markdown_to_form(str(self._legacy_value(row, "outline_text", "") or ""), title, volume_specs)
        outline_text = book_outline_form_to_markdown(outline_data, title, volume_specs)

        world_data = self._world_form_json_to_data(str(self._legacy_value(row, "world_data_json", "") or ""))
        if world_data is None:
            world_text_source = str(self._legacy_value(row, "world_text", "") or "")
            world_data = world_markdown_to_form(world_text_source) if world_text_source.strip() else world_form_defaults()
        world_text = world_form_to_markdown(world_data)
        cursor = self.connection.execute(
            """
            INSERT INTO books (title, outline_text, outline_data_json, world_text, world_data_json, cover_image_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                outline_text,
                self._book_outline_data_to_json(outline_data, title, volume_specs),
                world_text,
                self._world_form_data_to_json(world_data),
                "",
            ),
        )
        return int(cursor.lastrowid)

    def _insert_legacy_volume(self, book_id: int, row: sqlite3.Row) -> int:
        title = str(self._legacy_value(row, "title", "") or "").strip() or "旧版分卷"
        sort_order = self._safe_int(self._legacy_value(row, "sort_order"), self._next_volume_sort_order(book_id))
        cursor = self.connection.execute(
            """
            INSERT INTO volumes (book_id, title, outline_text, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (book_id, title, str(self._legacy_value(row, "outline_text", "") or ""), sort_order),
        )
        return int(cursor.lastrowid)

    def _insert_legacy_chapter(self, book_id: int, volume_id: int | None, row: sqlite3.Row) -> int:
        title = str(self._legacy_value(row, "title", "") or "").strip() or "旧版章节"
        sort_order = self._safe_int(self._legacy_value(row, "sort_order"), self._next_chapter_sort_order(book_id, volume_id))
        cursor = self.connection.execute(
            """
            INSERT INTO chapters (
                book_id, volume_id, title, outline, content, summary_text,
                ai_probability, ai_probability_level, sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book_id,
                volume_id,
                title,
                str(self._legacy_value(row, "outline", "") or ""),
                str(self._legacy_value(row, "content", "") or ""),
                str(self._legacy_value(row, "summary_text", "") or ""),
                self._safe_int(self._legacy_value(row, "ai_probability"), 0),
                str(self._legacy_value(row, "ai_probability_level", "none") or "none"),
                sort_order,
            ),
        )
        return int(cursor.lastrowid)

    def _insert_legacy_character(self, book_id: int, row: sqlite3.Row) -> int:
        name = str(self._legacy_value(row, "name", "") or "").strip() or "旧版人物"
        role = str(self._legacy_value(row, "role", "") or "")
        profile_data = self._character_profile_json_to_data(str(self._legacy_value(row, "profile_data_json", "") or ""), name, role)
        if profile_data is None:
            profile_text, profile_data_json = self._character_profile_payload_from_text(
                str(self._legacy_value(row, "profile_text", "") or ""),
                name,
                role,
            )
        else:
            profile_text = character_profile_form_to_markdown(profile_data, name, role)
            profile_data_json = self._character_profile_data_to_json(profile_data, name, role)
        cursor = self.connection.execute(
            """
            INSERT INTO characters (
                book_id, name, role, profile_text, profile_data_json,
                image_path, graph_x, graph_y, pinned
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book_id,
                name,
                role,
                profile_text,
                profile_data_json,
                "",
                self._safe_float(self._legacy_value(row, "graph_x"), 0.0),
                self._safe_float(self._legacy_value(row, "graph_y"), 0.0),
                self._safe_int(self._legacy_value(row, "pinned"), 0),
            ),
        )
        return int(cursor.lastrowid)

    def _import_legacy_world_entries(self, source: sqlite3.Connection, book_id_map: dict[int, int]) -> None:
        grouped: dict[int, list[str]] = {}
        for row in self._legacy_rows(source, "world_entries", ("book_id", "id")):
            old_book_id = self._safe_int(self._legacy_value(row, "book_id"), 0)
            new_book_id = book_id_map.get(old_book_id)
            if not new_book_id:
                continue
            name = str(self._legacy_value(row, "name", "") or "").strip() or "旧版世界观"
            category = str(self._legacy_value(row, "category", "") or "").strip()
            content = str(self._legacy_value(row, "content_text", "") or "").strip()
            if not content:
                continue
            header = f"### {name}"
            if category:
                header += f"（{category}）"
            grouped.setdefault(new_book_id, []).append(f"{header}\n\n{content}")
        for book_id, chunks in grouped.items():
            book = self.get_book(book_id)
            if not book:
                continue
            data = self._world_form_json_to_data(str(book["world_data_json"] or "")) or world_form_defaults()
            data = merge_world_supplement(data, "\n\n".join(chunks), supplement_title="旧版世界观")
            self.connection.execute(
                "UPDATE books SET world_text = ?, world_data_json = ? WHERE id = ?",
                (world_form_to_markdown(data), self._world_form_data_to_json(data), book_id),
            )

    def _refresh_imported_book_outlines(self, book_ids: Any) -> None:
        for book_id in book_ids:
            self._refresh_book_outline_volume_plans(int(book_id))

    def _import_legacy_relationships(
        self,
        source: sqlite3.Connection,
        book_id_map: dict[int, int],
        character_id_map: dict[int, int],
    ) -> None:
        for row in self._legacy_rows(source, "character_relationships", ("book_id", "id")):
            old_book_id = self._safe_int(self._legacy_value(row, "book_id"), 0)
            source_old_id = self._safe_int(self._legacy_value(row, "source_character_id"), 0)
            target_old_id = self._safe_int(self._legacy_value(row, "target_character_id"), 0)
            new_book_id = book_id_map.get(old_book_id)
            source_new_id = character_id_map.get(source_old_id)
            target_new_id = character_id_map.get(target_old_id)
            if not new_book_id or not source_new_id or not target_new_id:
                continue
            self.connection.execute(
                """
                INSERT INTO character_relationships (
                    book_id, source_character_id, target_character_id, relationship_type, description
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    new_book_id,
                    source_new_id,
                    target_new_id,
                    str(self._legacy_value(row, "relationship_type", "") or ""),
                    str(self._legacy_value(row, "description", "") or ""),
                ),
            )

    def _import_legacy_chapter_tags(self, source: sqlite3.Connection, chapter_id_map: dict[int, int]) -> None:
        for row in self._legacy_rows(source, "chapter_tags", ("chapter_id", "tag")):
            old_chapter_id = self._safe_int(self._legacy_value(row, "chapter_id"), 0)
            new_chapter_id = chapter_id_map.get(old_chapter_id)
            tag = str(self._legacy_value(row, "tag", "") or "").strip()
            if not new_chapter_id or not tag:
                continue
            self.connection.execute(
                "INSERT OR IGNORE INTO chapter_tags (chapter_id, tag) VALUES (?, ?)",
                (new_chapter_id, tag),
            )

    def _import_legacy_chapter_events(
        self,
        source: sqlite3.Connection,
        book_id_map: dict[int, int],
        chapter_id_map: dict[int, int],
    ) -> None:
        for row in self._legacy_rows(source, "chapter_events", ("book_id", "chapter_id", "sort_order", "id")):
            old_book_id = self._safe_int(self._legacy_value(row, "book_id"), 0)
            old_chapter_id = self._safe_int(self._legacy_value(row, "chapter_id"), 0)
            new_book_id = book_id_map.get(old_book_id)
            new_chapter_id = chapter_id_map.get(old_chapter_id)
            label = str(self._legacy_value(row, "label", "") or "").strip()
            if not new_book_id or not new_chapter_id or not label:
                continue
            self.connection.execute(
                """
                INSERT INTO chapter_events (book_id, chapter_id, label, description, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    new_book_id,
                    new_chapter_id,
                    label,
                    str(self._legacy_value(row, "description", "") or ""),
                    self._safe_int(self._legacy_value(row, "sort_order"), 0),
                ),
            )

    def initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                outline_text TEXT NOT NULL DEFAULT '',
                outline_data_json TEXT NOT NULL DEFAULT '',
                world_text TEXT NOT NULL DEFAULT '',
                world_data_json TEXT NOT NULL DEFAULT '',
                cover_image_path TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS volumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                outline_text TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                volume_id INTEGER,
                title TEXT NOT NULL,
                outline TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                summary_text TEXT NOT NULL DEFAULT '',
                ai_probability INTEGER NOT NULL DEFAULT 0,
                ai_probability_level TEXT NOT NULL DEFAULT 'none',
                sort_order INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY (volume_id) REFERENCES volumes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS reference_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                source_path TEXT NOT NULL,
                rights_note TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT 'book',
                source_url TEXT NOT NULL DEFAULT '',
                source_license TEXT NOT NULL DEFAULT '',
                reusable_level TEXT NOT NULL DEFAULT 'pattern_only',
                attribution_note TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS distilled_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                instruction_text TEXT NOT NULL,
                use_cases_text TEXT NOT NULL DEFAULT '',
                risk_note TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES reference_sources(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS skill_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_type TEXT NOT NULL,
                scope_id INTEGER NOT NULL,
                skill_id INTEGER NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(scope_type, scope_id, skill_id),
                FOREIGN KEY (skill_id) REFERENCES distilled_skills(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                profile_text TEXT NOT NULL DEFAULT '',
                profile_data_json TEXT NOT NULL DEFAULT '',
                image_path TEXT NOT NULL DEFAULT '',
                graph_x REAL NOT NULL DEFAULT 0,
                graph_y REAL NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS character_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                source_character_id INTEGER NOT NULL,
                target_character_id INTEGER NOT NULL,
                relationship_type TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY (source_character_id) REFERENCES characters(id) ON DELETE CASCADE,
                FOREIGN KEY (target_character_id) REFERENCES characters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chapter_ai_spans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL,
                start_offset INTEGER NOT NULL,
                end_offset INTEGER NOT NULL,
                source_task_id TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chapter_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                chapter_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS world_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '设定',
                content_text TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chapter_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                outline TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chapter_tags (
                chapter_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chapter_id, tag),
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS review_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                chapter_id INTEGER,
                scope_type TEXT NOT NULL DEFAULT 'chapter',
                status TEXT NOT NULL DEFAULT 'completed',
                truth_snapshot TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                overall_score INTEGER NOT NULL DEFAULT 0,
                snapshot_id INTEGER,
                revised_content TEXT NOT NULL DEFAULT '',
                revised_outline TEXT NOT NULL DEFAULT '',
                final_verdict TEXT NOT NULL DEFAULT '',
                template_comparison TEXT NOT NULL DEFAULT '',
                risk_notes TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                applied_at DATETIME,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
                FOREIGN KEY (snapshot_id) REFERENCES chapter_snapshots(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS review_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                agent TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'low',
                category TEXT NOT NULL DEFAULT '',
                location_hint TEXT NOT NULL DEFAULT '',
                quote_text TEXT NOT NULL DEFAULT '',
                issue_text TEXT NOT NULL DEFAULT '',
                suggestion_text TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES review_runs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_volumes_book ON volumes(book_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_chapters_book ON chapters(book_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_chapters_book_volume ON chapters(book_id, volume_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_reference_sources_title ON reference_sources(title);
            CREATE INDEX IF NOT EXISTS idx_skills_source ON distilled_skills(source_id);
            CREATE INDEX IF NOT EXISTS idx_bindings_scope ON skill_bindings(scope_type, scope_id);
            CREATE INDEX IF NOT EXISTS idx_characters_book ON characters(book_id);
            CREATE INDEX IF NOT EXISTS idx_relationships_book ON character_relationships(book_id);
            CREATE INDEX IF NOT EXISTS idx_relationships_source ON character_relationships(source_character_id);
            CREATE INDEX IF NOT EXISTS idx_relationships_target ON character_relationships(target_character_id);
            CREATE INDEX IF NOT EXISTS idx_world_entries_book ON world_entries(book_id);
            CREATE INDEX IF NOT EXISTS idx_snapshots_chapter ON chapter_snapshots(chapter_id);
            CREATE INDEX IF NOT EXISTS idx_chapter_tags_tag ON chapter_tags(tag, chapter_id);
            CREATE INDEX IF NOT EXISTS idx_ai_spans_chapter ON chapter_ai_spans(chapter_id, start_offset);
            CREATE INDEX IF NOT EXISTS idx_chapter_events_book ON chapter_events(book_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_chapter_events_chapter ON chapter_events(chapter_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_review_runs_book ON review_runs(book_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_review_runs_chapter ON review_runs(chapter_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_review_findings_run ON review_findings(run_id);

            CREATE TABLE IF NOT EXISTS node_styles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                background TEXT NOT NULL DEFAULT '#FFFFFF',
                border_color TEXT NOT NULL DEFAULT '#D6DFEA',
                border_width REAL NOT NULL DEFAULT 1.5,
                text_color TEXT NOT NULL DEFAULT '#1F2A36',
                icon_type TEXT NOT NULL DEFAULT 'default',
                is_preset INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS relationship_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '#5F7088',
                line_style TEXT NOT NULL DEFAULT 'dotted',
                arrow_type TEXT NOT NULL DEFAULT 'bi-directional',
                is_directed INTEGER NOT NULL DEFAULT 0,
                is_preset INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS character_node_styles (
                character_id INTEGER PRIMARY KEY,
                style_id INTEGER NOT NULL,
                FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                FOREIGN KEY (style_id) REFERENCES node_styles(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_node_styles_book ON node_styles(book_id);
            CREATE INDEX IF NOT EXISTS idx_relationship_types_book ON relationship_types(book_id);

            CREATE TABLE IF NOT EXISTS sticky_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '#FFF9C4',
                pos_x INTEGER NOT NULL DEFAULT 100,
                pos_y INTEGER NOT NULL DEFAULT 100,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_sticky_notes_book ON sticky_notes(book_id);
            """
        )
        self._migrate_schema()
        self._ensure_column("character_relationships", "relationship_type_id", "INTEGER REFERENCES relationship_types(id) ON DELETE SET NULL")
        self._ensure_column("character_relationships", "description", "TEXT NOT NULL DEFAULT ''")
        self._ensure_legacy_imports_table()
        self._apply_app_migrations()
        self._import_legacy_data_dirs()
        self._normalize_all_volume_orders()
        self._normalize_all_chapter_orders()

    def update_character_pinned(self, character_id: int, pinned: bool) -> None:
        self.connection.execute(
            "UPDATE characters SET pinned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if pinned else 0, character_id),
        )
        self.connection.commit()

    def list_sticky_notes(self, book_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            "SELECT id, book_id, content, color, pos_x, pos_y, created_at FROM sticky_notes WHERE book_id = ? ORDER BY id ASC",
            (book_id,),
        )
        return list(cursor.fetchall())

    def create_sticky_note(self, book_id: int, content: str = "", color: str = "#FFF9C4", pos_x: int = 100, pos_y: int = 100) -> int:
        cursor = self.connection.execute(
            "INSERT INTO sticky_notes (book_id, content, color, pos_x, pos_y) VALUES (?, ?, ?, ?, ?)",
            (book_id, content, color, pos_x, pos_y),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def update_sticky_note(self, note_id: int, content: str = "", color: str = "#FFF9C4", pos_x: int | None = None, pos_y: int | None = None) -> None:
        if pos_x is not None and pos_y is not None:
            self.connection.execute(
                "UPDATE sticky_notes SET content = ?, color = ?, pos_x = ?, pos_y = ? WHERE id = ?",
                (content, color, pos_x, pos_y, note_id),
            )
        else:
            self.connection.execute(
                "UPDATE sticky_notes SET content = ?, color = ? WHERE id = ?",
                (content, color, note_id),
            )
        self.connection.commit()

    def delete_sticky_note(self, note_id: int) -> None:
        self.connection.execute("DELETE FROM sticky_notes WHERE id = ?", (note_id,))
        self.connection.commit()

    def _migrate_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS volumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                outline_text TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            )
            """
        )
        self._ensure_column("books", "outline_text", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("books", "outline_data_json", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("books", "world_text", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("books", "world_data_json", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("books", "cover_image_path", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("volumes", "outline_text", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("chapters", "summary_text", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("chapters", "volume_id", "INTEGER")
        self._ensure_column("chapters", "ai_probability", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("chapters", "ai_probability_level", "TEXT NOT NULL DEFAULT 'none'")
        self._ensure_column("characters", "image_path", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("characters", "profile_data_json", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("characters", "graph_x", "REAL NOT NULL DEFAULT 0")
        self._ensure_column("characters", "graph_y", "REAL NOT NULL DEFAULT 0")
        self._ensure_column("reference_sources", "source_type", "TEXT NOT NULL DEFAULT 'book'")
        self._ensure_column("reference_sources", "source_url", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("reference_sources", "source_license", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("reference_sources", "reusable_level", "TEXT NOT NULL DEFAULT 'pattern_only'")
        self._ensure_column("reference_sources", "attribution_note", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("review_runs", "snapshot_id", "INTEGER")
        self._ensure_column("review_runs", "applied_at", "DATETIME")
        self._ensure_column("review_runs", "template_comparison", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("review_runs", "cross_summary", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("review_findings", "dimension", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("review_findings", "conflict_with", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("review_findings", "is_cross_chapter", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("characters", "pinned", "INTEGER NOT NULL DEFAULT 0")
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chapters_volume ON chapters(volume_id, sort_order, id)"
        )
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS chapter_tags (
                chapter_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chapter_id, tag),
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS character_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                source_character_id INTEGER NOT NULL,
                target_character_id INTEGER NOT NULL,
                relationship_type TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY (source_character_id) REFERENCES characters(id) ON DELETE CASCADE,
                FOREIGN KEY (target_character_id) REFERENCES characters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chapter_ai_spans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL,
                start_offset INTEGER NOT NULL,
                end_offset INTEGER NOT NULL,
                source_task_id TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chapter_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                chapter_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS review_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                chapter_id INTEGER,
                scope_type TEXT NOT NULL DEFAULT 'chapter',
                status TEXT NOT NULL DEFAULT 'completed',
                truth_snapshot TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                overall_score INTEGER NOT NULL DEFAULT 0,
                snapshot_id INTEGER,
                revised_content TEXT NOT NULL DEFAULT '',
                revised_outline TEXT NOT NULL DEFAULT '',
                final_verdict TEXT NOT NULL DEFAULT '',
                template_comparison TEXT NOT NULL DEFAULT '',
                risk_notes TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                applied_at DATETIME,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
                FOREIGN KEY (snapshot_id) REFERENCES chapter_snapshots(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS review_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                agent TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'low',
                category TEXT NOT NULL DEFAULT '',
                location_hint TEXT NOT NULL DEFAULT '',
                quote_text TEXT NOT NULL DEFAULT '',
                issue_text TEXT NOT NULL DEFAULT '',
                suggestion_text TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES review_runs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_relationships_book ON character_relationships(book_id);
            CREATE INDEX IF NOT EXISTS idx_relationships_source ON character_relationships(source_character_id);
            CREATE INDEX IF NOT EXISTS idx_relationships_target ON character_relationships(target_character_id);
            CREATE INDEX IF NOT EXISTS idx_ai_spans_chapter ON chapter_ai_spans(chapter_id, start_offset);
            CREATE INDEX IF NOT EXISTS idx_chapter_tags_tag ON chapter_tags(tag, chapter_id);
            CREATE INDEX IF NOT EXISTS idx_chapter_events_book ON chapter_events(book_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_chapter_events_chapter ON chapter_events(chapter_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_review_runs_book ON review_runs(book_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_review_runs_chapter ON review_runs(chapter_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_review_findings_run ON review_findings(run_id);

            CREATE TABLE IF NOT EXISTS name_shortcuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                key_seq TEXT NOT NULL DEFAULT '',
                character_name TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_name_shortcuts_book ON name_shortcuts(book_id);
            """
        )

    def _ensure_column(self, table_name: str, column_name: str, definition: str) -> None:
        try:
            self.connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

    def _apply_app_migrations(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_migrations (
                id TEXT PRIMARY KEY,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        structured_applied = self.connection.execute(
            "SELECT 1 FROM app_migrations WHERE id = ?",
            (STRUCTURED_TEMPLATE_MIGRATION_ID,),
        ).fetchone()
        if not structured_applied:
            characters = self.connection.execute("SELECT id, name, role FROM characters").fetchall()
            for character in characters:
                name = str(character["name"] or "")
                role = str(character["role"] or "")
                profile_data = character_profile_form_defaults(name, role)
                profile_text = character_profile_form_to_markdown(profile_data, name, role)
                self.connection.execute(
                    "UPDATE characters SET profile_text = ?, profile_data_json = ? WHERE id = ?",
                    (profile_text, self._character_profile_data_to_json(profile_data, name, role), int(character["id"])),
                )

            self.connection.execute(
                "INSERT INTO app_migrations (id) VALUES (?)",
                (STRUCTURED_TEMPLATE_MIGRATION_ID,),
            )

        outline_form_applied = self.connection.execute(
            "SELECT 1 FROM app_migrations WHERE id = ?",
            (BOOK_OUTLINE_FORM_MIGRATION_ID,),
        ).fetchone()
        if not outline_form_applied:
            books = self.connection.execute("SELECT id, title, outline_text, outline_data_json FROM books").fetchall()
            for book in books:
                title = str(book["title"] or "")
                volume_specs = self._book_outline_volume_specs(int(book["id"]))
                data = self._book_outline_json_to_data(str(book["outline_data_json"] or ""), title, volume_specs)
                if not data:
                    data = book_outline_markdown_to_form(str(book["outline_text"] or ""), title, volume_specs)
                markdown = book_outline_form_to_markdown(data, title, volume_specs)
                self.connection.execute(
                    "UPDATE books SET outline_text = ?, outline_data_json = ? WHERE id = ?",
                    (markdown, self._book_outline_data_to_json(data, title, volume_specs), int(book["id"])),
                )

            self.connection.execute(
                "INSERT INTO app_migrations (id) VALUES (?)",
                (BOOK_OUTLINE_FORM_MIGRATION_ID,),
            )

        world_form_applied = self.connection.execute(
            "SELECT 1 FROM app_migrations WHERE id = ?",
            (WORLD_FORM_MIGRATION_ID,),
        ).fetchone()
        if not world_form_applied:
            books = self.connection.execute("SELECT id FROM books").fetchall()
            for book in books:
                book_id = int(book["id"])
                world_data = world_form_defaults()
                self.connection.execute(
                    "UPDATE books SET world_text = ?, world_data_json = ? WHERE id = ?",
                    (world_form_to_markdown(world_data), self._world_form_data_to_json(world_data), book_id),
                )
                self.connection.execute("DELETE FROM world_entries WHERE book_id = ?", (book_id,))
            self.connection.execute(
                "INSERT INTO app_migrations (id) VALUES (?)",
                (WORLD_FORM_MIGRATION_ID,),
            )

        character_form_applied = self.connection.execute(
            "SELECT 1 FROM app_migrations WHERE id = ?",
            (CHARACTER_PROFILE_FORM_MIGRATION_ID,),
        ).fetchone()
        if not character_form_applied:
            characters = self.connection.execute("SELECT id, name, role FROM characters").fetchall()
            for character in characters:
                name = str(character["name"] or "")
                role = str(character["role"] or "")
                profile_data = character_profile_form_defaults(name, role)
                profile_text = character_profile_form_to_markdown(profile_data, name, role)
                self.connection.execute(
                    "UPDATE characters SET profile_text = ?, profile_data_json = ? WHERE id = ?",
                    (profile_text, self._character_profile_data_to_json(profile_data, name, role), int(character["id"])),
                )
            self.connection.execute(
                "INSERT INTO app_migrations (id) VALUES (?)",
                (CHARACTER_PROFILE_FORM_MIGRATION_ID,),
            )

    def _normalize_all_volume_orders(self) -> None:
        books = self.connection.execute("SELECT id FROM books").fetchall()
        for row in books:
            self._normalize_volume_order(int(row["id"]))

    def _normalize_volume_order(self, book_id: int) -> None:
        rows = self.connection.execute(
            """
            SELECT id
            FROM volumes
            WHERE book_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (book_id,),
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            self.connection.execute(
                "UPDATE volumes SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (index, int(row["id"])),
            )

    def _normalize_all_chapter_orders(self) -> None:
        rows = self.connection.execute(
            """
            SELECT DISTINCT book_id, volume_id
            FROM chapters
            ORDER BY book_id ASC, volume_id ASC
            """
        ).fetchall()
        for row in rows:
            self._normalize_chapter_order(int(row["book_id"]), row["volume_id"])

    def _normalize_chapter_order(self, book_id: int, volume_id: int | None) -> None:
        clause, params = self._build_volume_clause(volume_id)
        rows = self.connection.execute(
            f"""
            SELECT id
            FROM chapters
            WHERE book_id = ? AND {clause}
            ORDER BY sort_order ASC, id ASC
            """,
            (book_id, *params),
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            self.connection.execute(
                "UPDATE chapters SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (index, int(row["id"])),
            )

    def _build_volume_clause(self, volume_id: int | None, column_name: str = "volume_id") -> tuple[str, tuple[Any, ...]]:
        ALLOWED_COLUMNS = {"volume_id", "book_id", "sort_order"}
        if column_name not in ALLOWED_COLUMNS:
            raise ValueError(f"Invalid column name for volume clause: {column_name}")
        if volume_id is None:
            return f"{column_name} IS NULL", ()
        return f"{column_name} = ?", (volume_id,)

    def _book_outline_volume_specs(self, book_id: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, title, sort_order
            FROM volumes
            WHERE book_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (book_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _book_outline_json_to_data(
        self,
        raw_json: str,
        title: str,
        volume_specs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        raw_json = str(raw_json or "").strip()
        if not raw_json:
            return None
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return normalize_book_outline_form(payload, title, volume_specs)

    def _book_outline_data_to_json(
        self,
        data: dict[str, Any] | None,
        title: str,
        volume_specs: list[dict[str, Any]] | None = None,
    ) -> str:
        normalized = normalize_book_outline_form(data, title, volume_specs)
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))

    def _book_outline_payload_from_text(
        self,
        outline_text: str,
        title: str,
        volume_specs: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str]:
        data = book_outline_markdown_to_form(outline_text, title, volume_specs)
        markdown = book_outline_form_to_markdown(data, title, volume_specs)
        return markdown, self._book_outline_data_to_json(data, title, volume_specs)

    def _refresh_book_outline_volume_plans(self, book_id: int) -> None:
        book = self.get_book(book_id)
        if not book:
            return
        title = str(book["title"] or "")
        volume_specs = self._book_outline_volume_specs(book_id)
        data = self._book_outline_json_to_data(str(book["outline_data_json"] or ""), title, volume_specs)
        if data is None:
            data = book_outline_markdown_to_form(str(book["outline_text"] or ""), title, volume_specs)
        markdown = book_outline_form_to_markdown(data, title, volume_specs)
        self.connection.execute(
            """
            UPDATE books
            SET outline_text = ?, outline_data_json = ?
            WHERE id = ?
            """,
            (markdown, self._book_outline_data_to_json(data, title, volume_specs), book_id),
        )

    def _world_form_json_to_data(self, raw_json: str) -> dict[str, Any] | None:
        raw_json = str(raw_json or "").strip()
        if not raw_json:
            return None
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return normalize_world_form(payload)

    def _world_form_data_to_json(self, data: dict[str, Any] | None) -> str:
        return json.dumps(normalize_world_form(data), ensure_ascii=False, separators=(",", ":"))

    def _world_payload_from_text(self, world_text: str) -> tuple[str, str]:
        data = world_markdown_to_form(world_text)
        markdown = world_form_to_markdown(data)
        return markdown, self._world_form_data_to_json(data)

    def _character_profile_json_to_data(self, raw_json: str, name: str, role: str) -> dict[str, Any] | None:
        raw_json = str(raw_json or "").strip()
        if not raw_json:
            return None
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return normalize_character_profile_form(payload, name, role)

    def _character_profile_data_to_json(self, data: dict[str, Any] | None, name: str, role: str) -> str:
        normalized = normalize_character_profile_form(data, name, role)
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))

    def _character_profile_payload_from_text(self, profile_text: str, name: str, role: str) -> tuple[str, str]:
        data = character_profile_markdown_to_form(profile_text, name, role)
        markdown = character_profile_form_to_markdown(data, name, role)
        return markdown, self._character_profile_data_to_json(data, name, role)

    def normalize_media_path(self, path: str | Path) -> str:
        value = str(path).strip()
        if not value:
            return ""
        candidate = Path(value)
        try:
            resolved = candidate.resolve()
        except OSError:
            return value
        try:
            return resolved.relative_to(self.data_dir.resolve()).as_posix()
        except ValueError:
            return str(resolved)

    def resolve_media_path(self, stored_path: str | Path) -> Path:
        value = str(stored_path).strip()
        if not value:
            return Path()
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return self.data_dir / candidate

    def _next_volume_sort_order(self, book_id: int) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM volumes WHERE book_id = ?",
            (book_id,),
        ).fetchone()
        return int(row["next_order"]) if row else 1

    def _next_chapter_sort_order(self, book_id: int, volume_id: int | None) -> int:
        clause, params = self._build_volume_clause(volume_id)
        row = self.connection.execute(
            f"""
            SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order
            FROM chapters
            WHERE book_id = ? AND {clause}
            """,
            (book_id, *params),
        ).fetchone()
        return int(row["next_order"]) if row else 1

    def list_books(self) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            "SELECT id, title FROM books ORDER BY id DESC"
        )
        return list(cursor.fetchall())

    def create_book(self, title: str) -> int:
        outline_data = book_outline_form_defaults(title)
        outline_text = book_outline_form_to_markdown(outline_data, title)
        world_data = world_form_defaults()
        world_text = world_form_to_markdown(world_data)
        cursor = self.connection.execute(
            """
            INSERT INTO books (title, outline_text, outline_data_json, world_text, world_data_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title,
                outline_text,
                self._book_outline_data_to_json(outline_data, title),
                world_text,
                self._world_form_data_to_json(world_data),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def get_book(self, book_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT id, title, outline_text, outline_data_json, world_text, world_data_json, cover_image_path
            FROM books
            WHERE id = ?
            """,
            (book_id,),
        )
        return cursor.fetchone()

    def rename_book(self, book_id: int, title: str) -> None:
        self.connection.execute(
            """
            UPDATE books
            SET title = ?
            WHERE id = ?
            """,
            (title, book_id),
        )
        self.connection.commit()

    def update_book_outline(self, book_id: int, outline_text: str, outline_data: dict[str, Any] | None = None) -> None:
        book = self.get_book(book_id)
        title = str(book["title"] or "") if book else ""
        volume_specs = self._book_outline_volume_specs(book_id)
        if outline_data is None:
            outline_text, outline_data_json = self._book_outline_payload_from_text(outline_text, title, volume_specs)
        else:
            normalized = normalize_book_outline_form(outline_data, title, volume_specs)
            outline_text = book_outline_form_to_markdown(normalized, title, volume_specs)
            outline_data_json = self._book_outline_data_to_json(normalized, title, volume_specs)
        self.connection.execute(
            """
            UPDATE books
            SET outline_text = ?, outline_data_json = ?
            WHERE id = ?
            """,
            (outline_text, outline_data_json, book_id),
        )
        self.connection.commit()

    def update_book_outline_form(self, book_id: int, outline_data: dict[str, Any]) -> None:
        self.update_book_outline(book_id, "", outline_data=outline_data)

    def get_book_outline_form(self, book_id: int) -> dict[str, Any]:
        book = self.get_book(book_id)
        if not book:
            return book_outline_form_defaults("")
        title = str(book["title"] or "")
        volume_specs = self._book_outline_volume_specs(book_id)
        data = self._book_outline_json_to_data(str(book["outline_data_json"] or ""), title, volume_specs)
        if data is None:
            data = book_outline_markdown_to_form(str(book["outline_text"] or ""), title, volume_specs)
        return normalize_book_outline_form(data, title, volume_specs)

    def update_book_world(self, book_id: int, world_text: str, world_data: dict[str, Any] | None = None) -> None:
        if world_data is None:
            world_text, world_data_json = self._world_payload_from_text(world_text)
        else:
            normalized = normalize_world_form(world_data)
            world_text = world_form_to_markdown(normalized)
            world_data_json = self._world_form_data_to_json(normalized)
        self.connection.execute(
            """
            UPDATE books
            SET world_text = ?, world_data_json = ?
            WHERE id = ?
            """,
            (world_text, world_data_json, book_id),
        )
        self.connection.commit()

    def update_book_world_form(self, book_id: int, world_data: dict[str, Any]) -> None:
        self.update_book_world(book_id, "", world_data=world_data)

    def get_book_world_form(self, book_id: int) -> dict[str, Any]:
        book = self.get_book(book_id)
        if not book:
            return world_form_defaults()
        data = self._world_form_json_to_data(str(book["world_data_json"] or ""))
        if data is None:
            data = world_markdown_to_form(str(book["world_text"] or ""))
        return normalize_world_form(data)

    def update_book_cover(self, book_id: int, cover_image_path: str) -> None:
        self.connection.execute(
            """
            UPDATE books
            SET cover_image_path = ?
            WHERE id = ?
            """,
            (cover_image_path, book_id),
        )
        self.connection.commit()

    def delete_book(self, book_id: int) -> None:
        self.connection.execute(
            "DELETE FROM books WHERE id = ?",
            (book_id,),
        )
        self.connection.commit()

    def list_volumes(self, book_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                v.id,
                v.book_id,
                v.title,
                v.outline_text,
                v.sort_order,
                COUNT(c.id) AS chapter_count
            FROM volumes AS v
            LEFT JOIN chapters AS c ON c.volume_id = v.id
            WHERE v.book_id = ?
            GROUP BY v.id, v.book_id, v.title, v.outline_text, v.sort_order
            ORDER BY v.sort_order ASC, v.id ASC
            """,
            (book_id,),
        )
        return list(cursor.fetchall())

    def count_unassigned_chapters(self, book_id: int) -> int:
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM chapters
            WHERE book_id = ? AND volume_id IS NULL
            """,
            (book_id,),
        ).fetchone()
        return int(row["count"]) if row else 0

    def create_volume(self, book_id: int, title: str) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO volumes (book_id, title, sort_order)
            VALUES (?, ?, ?)
            """,
            (book_id, title, self._next_volume_sort_order(book_id)),
        )
        volume_id = int(cursor.lastrowid)
        self._refresh_book_outline_volume_plans(book_id)
        self.connection.commit()
        return volume_id

    def get_volume(self, volume_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT id, book_id, title, outline_text, sort_order
            FROM volumes
            WHERE id = ?
            """,
            (volume_id,),
        )
        return cursor.fetchone()

    def rename_volume(self, volume_id: int, title: str) -> None:
        self.connection.execute(
            """
            UPDATE volumes
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, volume_id),
        )
        updated = self.get_volume(volume_id)
        if updated:
            self._refresh_book_outline_volume_plans(int(updated["book_id"]))
        self.connection.commit()

    def update_volume_outline(self, volume_id: int, outline_text: str) -> None:
        self.connection.execute(
            """
            UPDATE volumes
            SET outline_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (outline_text, volume_id),
        )
        self.connection.commit()

    def delete_volume(self, volume_id: int) -> None:
        volume = self.get_volume(volume_id)
        if not volume:
            return

        book_id = int(volume["book_id"])
        self.connection.execute(
            "DELETE FROM volumes WHERE id = ?",
            (volume_id,),
        )
        self._normalize_volume_order(book_id)
        self._normalize_all_chapter_orders()
        self._refresh_book_outline_volume_plans(book_id)
        self.connection.commit()

    def move_volume(self, volume_id: int, direction: int) -> bool:
        if direction == 0:
            return False
        current = self.get_volume(volume_id)
        if not current:
            return False

        with self.connection:
            comparator = "<" if direction < 0 else ">"
            order = "DESC" if direction < 0 else "ASC"
            neighbor = self.connection.execute(
                f"""
                SELECT id, sort_order
                FROM volumes
                WHERE book_id = ? AND sort_order {comparator} ?
                ORDER BY sort_order {order}, id {order}
                LIMIT 1
                """,
                (int(current["book_id"]), int(current["sort_order"])),
            ).fetchone()
            if not neighbor:
                return False

            self.connection.execute(
                "UPDATE volumes SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (int(neighbor["sort_order"]), volume_id),
            )
            self.connection.execute(
                "UPDATE volumes SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (int(current["sort_order"]), int(neighbor["id"])),
            )
            self._normalize_volume_order(int(current["book_id"]))
            self._refresh_book_outline_volume_plans(int(current["book_id"]))
        return True

    def list_chapters(self, book_id: int, volume_filter: int | str = ALL_VOLUMES) -> list[sqlite3.Row]:
        base_sql = """
            SELECT
                c.id,
                c.title,
                c.sort_order,
                c.volume_id,
                LENGTH(COALESCE(c.content, '')) AS word_count,
                c.ai_probability,
                c.ai_probability_level,
                COALESCE(tmpl.is_template, 0) AS is_template,
                COALESCE(v.title, '未分卷') AS volume_title,
                COALESCE(v.sort_order, 2147483647) AS volume_sort_order
            FROM chapters AS c
            LEFT JOIN volumes AS v ON v.id = c.volume_id
            LEFT JOIN (
                SELECT chapter_id, 1 AS is_template
                FROM chapter_tags
                WHERE tag = 'template'
            ) AS tmpl ON tmpl.chapter_id = c.id
            WHERE c.book_id = ?
        """
        params: list[Any] = [book_id]

        if volume_filter == UNASSIGNED_VOLUMES:
            base_sql += " AND c.volume_id IS NULL"
            order_sql = " ORDER BY c.sort_order ASC, c.id ASC"
        elif volume_filter != ALL_VOLUMES:
            base_sql += " AND c.volume_id = ?"
            params.append(volume_filter)
            order_sql = " ORDER BY c.sort_order ASC, c.id ASC"
        else:
            order_sql = """
                ORDER BY
                    CASE WHEN c.volume_id IS NULL THEN 1 ELSE 0 END ASC,
                    COALESCE(v.sort_order, 2147483647) ASC,
                    c.sort_order ASC,
                    c.id ASC
            """

        cursor = self.connection.execute(base_sql + order_sql, params)
        return list(cursor.fetchall())

    def create_chapter(self, book_id: int, title: str, volume_id: int | None = None) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO chapters (book_id, volume_id, title, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (book_id, volume_id, title, self._next_chapter_sort_order(book_id, volume_id)),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def get_chapter(self, chapter_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT
                c.id,
                c.book_id,
                c.volume_id,
                c.title,
                c.outline,
                c.content,
                c.summary_text,
                c.ai_probability,
                c.ai_probability_level,
                c.sort_order,
                COALESCE(v.title, '未分卷') AS volume_title,
                EXISTS(
                    SELECT 1 FROM chapter_tags AS ct
                    WHERE ct.chapter_id = c.id AND ct.tag = 'template'
                ) AS is_template
            FROM chapters AS c
            LEFT JOIN volumes AS v ON v.id = c.volume_id
            WHERE c.id = ?
            """,
            (chapter_id,),
        )
        return cursor.fetchone()

    def rename_chapter(self, chapter_id: int, title: str) -> None:
        self.connection.execute(
            """
            UPDATE chapters
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, chapter_id),
        )
        self.connection.commit()

    def delete_chapter(self, chapter_id: int) -> None:
        chapter = self.connection.execute(
            """
            SELECT id, book_id, volume_id
            FROM chapters
            WHERE id = ?
            """,
            (chapter_id,),
        ).fetchone()
        if not chapter:
            return

        self.connection.execute(
            "DELETE FROM chapters WHERE id = ?",
            (chapter_id,),
        )
        self._normalize_chapter_order(int(chapter["book_id"]), chapter["volume_id"])
        self.connection.commit()

    def update_chapter(
        self,
        chapter_id: int,
        outline: str,
        content: str,
        summary_text: str = "",
    ) -> None:
        self.connection.execute(
            """
            UPDATE chapters
            SET outline = ?, content = ?, summary_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (outline, content, summary_text, chapter_id),
        )
        self.connection.commit()

    def update_chapter_ai_probability(self, chapter_id: int, probability: int, level: str) -> None:
        probability = max(0, min(100, int(probability)))
        normalized_level = level if level in {"certain", "high", "medium", "low", "none"} else "none"
        self.connection.execute(
            """
            UPDATE chapters
            SET ai_probability = ?, ai_probability_level = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (probability, normalized_level, chapter_id),
        )
        self.connection.commit()

    def set_chapter_tag(self, chapter_id: int, tag: str) -> None:
        cleaned = str(tag or "").strip()
        if not cleaned:
            return
        self.connection.execute(
            """
            INSERT OR IGNORE INTO chapter_tags (chapter_id, tag)
            VALUES (?, ?)
            """,
            (chapter_id, cleaned),
        )
        self.connection.commit()

    def remove_chapter_tag(self, chapter_id: int, tag: str) -> None:
        self.connection.execute(
            "DELETE FROM chapter_tags WHERE chapter_id = ? AND tag = ?",
            (chapter_id, str(tag or "").strip()),
        )
        self.connection.commit()

    def has_chapter_tag(self, chapter_id: int, tag: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM chapter_tags
            WHERE chapter_id = ? AND tag = ?
            LIMIT 1
            """,
            (chapter_id, str(tag or "").strip()),
        ).fetchone()
        return row is not None

    def list_template_chapters(self, book_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                c.id,
                c.book_id,
                c.volume_id,
                c.title,
                c.outline,
                c.content,
                c.sort_order,
                COALESCE(v.title, '未分卷') AS volume_title
            FROM chapter_tags AS tag
            JOIN chapters AS c ON c.id = tag.chapter_id
            LEFT JOIN volumes AS v ON v.id = c.volume_id
            WHERE c.book_id = ? AND tag.tag = 'template'
            ORDER BY
                CASE WHEN c.volume_id IS NULL THEN 1 ELSE 0 END ASC,
                COALESCE(v.sort_order, 2147483647) ASC,
                c.sort_order ASC,
                c.id ASC
            """,
            (book_id,),
        )
        return list(cursor.fetchall())

    def list_chapter_ai_spans(self, chapter_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT id, chapter_id, start_offset, end_offset, source_task_id, created_at
            FROM chapter_ai_spans
            WHERE chapter_id = ?
            ORDER BY start_offset ASC, id ASC
            """,
            (chapter_id,),
        )
        return list(cursor.fetchall())

    def add_chapter_ai_span(
        self,
        chapter_id: int,
        start_offset: int,
        end_offset: int,
        source_task_id: str = "",
    ) -> int:
        start = max(0, int(start_offset))
        end = max(start, int(end_offset))
        if end <= start:
            return 0
        cursor = self.connection.execute(
            """
            INSERT INTO chapter_ai_spans (chapter_id, start_offset, end_offset, source_task_id)
            VALUES (?, ?, ?, ?)
            """,
            (chapter_id, start, end, source_task_id),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def delete_chapter_ai_spans(self, chapter_id: int) -> None:
        self.connection.execute(
            "DELETE FROM chapter_ai_spans WHERE chapter_id = ?",
            (chapter_id,),
        )
        self.connection.commit()

    def delete_chapter_ai_spans_in_range(self, chapter_id: int, start_offset: int, end_offset: int) -> None:
        start = max(0, int(start_offset))
        end = max(start, int(end_offset))
        self.connection.execute(
            """
            DELETE FROM chapter_ai_spans
            WHERE chapter_id = ?
              AND start_offset < ?
              AND end_offset > ?
            """,
            (chapter_id, end, start),
        )
        self.connection.commit()

    def update_chapter_summary(self, chapter_id: int, summary_text: str) -> None:
        self.connection.execute(
            """
            UPDATE chapters
            SET summary_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (summary_text, chapter_id),
        )
        self.connection.commit()

    def update_chapter_volume(self, chapter_id: int, volume_id: int | None) -> None:
        chapter = self.connection.execute(
            """
            SELECT id, book_id, volume_id
            FROM chapters
            WHERE id = ?
            """,
            (chapter_id,),
        ).fetchone()
        if not chapter:
            return

        old_volume_id = chapter["volume_id"]
        if old_volume_id == volume_id:
            return

        book_id = int(chapter["book_id"])
        new_order = self._next_chapter_sort_order(book_id, volume_id)
        self.connection.execute(
            """
            UPDATE chapters
            SET volume_id = ?, sort_order = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (volume_id, new_order, chapter_id),
        )
        self._normalize_chapter_order(book_id, old_volume_id)
        self._normalize_chapter_order(book_id, volume_id)
        self.connection.commit()

    def move_chapter(self, chapter_id: int, direction: int) -> bool:
        if direction == 0:
            return False
        current = self.connection.execute(
            """
            SELECT id, book_id, volume_id, sort_order
            FROM chapters
            WHERE id = ?
            """,
            (chapter_id,),
        ).fetchone()
        if not current:
            return False

        with self.connection:
            comparator = "<" if direction < 0 else ">"
            order = "DESC" if direction < 0 else "ASC"
            clause, params = self._build_volume_clause(current["volume_id"])
            neighbor = self.connection.execute(
                f"""
                SELECT id, sort_order
                FROM chapters
                WHERE book_id = ? AND {clause} AND sort_order {comparator} ?
                ORDER BY sort_order {order}, id {order}
                LIMIT 1
                """,
                (int(current["book_id"]), *params, int(current["sort_order"])),
            ).fetchone()
            if not neighbor:
                return False

            self.connection.execute(
                "UPDATE chapters SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (int(neighbor["sort_order"]), chapter_id),
            )
            self.connection.execute(
                "UPDATE chapters SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (int(current["sort_order"]), int(neighbor["id"])),
            )
            self._normalize_chapter_order(int(current["book_id"]), current["volume_id"])
        return True

    def create_snapshot(
        self,
        chapter_id: int,
        label: str,
        outline: str,
        content: str,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO chapter_snapshots (chapter_id, label, outline, content)
            VALUES (?, ?, ?, ?)
            """,
            (chapter_id, label, outline, content),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def list_snapshots(self, chapter_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT id, label, created_at
            FROM chapter_snapshots
            WHERE chapter_id = ?
            ORDER BY id DESC
            """,
            (chapter_id,),
        )
        return list(cursor.fetchall())

    def get_snapshot(self, snapshot_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT id, chapter_id, label, outline, content, created_at
            FROM chapter_snapshots
            WHERE id = ?
            """,
            (snapshot_id,),
        )
        return cursor.fetchone()

    def create_review_run(
        self,
        *,
        book_id: int,
        chapter_id: int | None,
        scope_type: str,
        status: str,
        truth_snapshot: str = "",
        summary: str = "",
        overall_score: int = 0,
        snapshot_id: int | None = None,
        revised_content: str = "",
        revised_outline: str = "",
        final_verdict: str = "",
        template_comparison: str = "",
        risk_notes: str = "",
        cross_summary: str = "",
        applied: bool = False,
    ) -> int:
        score = max(0, min(100, int(overall_score or 0)))
        cursor = self.connection.execute(
            """
            INSERT INTO review_runs (
                book_id,
                chapter_id,
                scope_type,
                status,
                truth_snapshot,
                summary,
                overall_score,
                snapshot_id,
                revised_content,
                revised_outline,
                final_verdict,
                template_comparison,
                risk_notes,
                cross_summary,
                applied_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
            """,
            (
                book_id,
                chapter_id,
                scope_type or "chapter",
                status or "completed",
                truth_snapshot,
                summary,
                score,
                snapshot_id,
                revised_content,
                revised_outline,
                final_verdict,
                template_comparison,
                risk_notes,
                cross_summary,
                1 if applied else 0,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def replace_review_findings(self, run_id: int, findings: list[dict[str, Any]]) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM review_findings WHERE run_id = ?", (run_id,))
            for item in findings:
                if not isinstance(item, dict):
                    continue
                issue = str(item.get("issue") or item.get("issue_text") or "").strip()
                suggestion = str(item.get("suggestion") or item.get("suggestion_text") or "").strip()
                if not issue and not suggestion:
                    continue
                severity = str(item.get("severity", "low")).strip().lower()
                if severity not in {"high", "medium", "low"}:
                    severity = "low"
                self.connection.execute(
                    """
                    INSERT INTO review_findings (
                        run_id,
                        agent,
                        severity,
                        category,
                        location_hint,
                        quote_text,
                        issue_text,
                        suggestion_text,
                        dimension,
                        conflict_with,
                        is_cross_chapter
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        str(item.get("agent", "")).strip(),
                        severity,
                        str(item.get("category", "")).strip(),
                        str(item.get("location_hint", "")).strip(),
                        str(item.get("quote") or item.get("quote_text") or "").strip(),
                        issue,
                        suggestion,
                        str(item.get("dimension", "")).strip(),
                        str(item.get("conflict_with", "")).strip(),
                        1 if item.get("is_cross_chapter") else 0,
                    ),
                )

    def list_review_runs(
        self,
        book_id: int,
        chapter_id: int | None = None,
        limit: int = 20,
    ) -> list[sqlite3.Row]:
        sql = """
            SELECT
                id,
                book_id,
                chapter_id,
                scope_type,
                status,
                summary,
                overall_score,
                snapshot_id,
                final_verdict,
                template_comparison,
                risk_notes,
                cross_summary,
                created_at,
                updated_at,
                applied_at
            FROM review_runs
            WHERE book_id = ?
        """
        params: list[Any] = [book_id]
        if chapter_id is not None:
            sql += " AND chapter_id = ?"
            params.append(chapter_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        cursor = self.connection.execute(sql, params)
        return list(cursor.fetchall())

    def get_review_run(self, run_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT
                id,
                book_id,
                chapter_id,
                scope_type,
                status,
                truth_snapshot,
                summary,
                overall_score,
                snapshot_id,
                revised_content,
                revised_outline,
                final_verdict,
                template_comparison,
                risk_notes,
                cross_summary,
                created_at,
                updated_at,
                applied_at
            FROM review_runs
            WHERE id = ?
            """,
            (run_id,),
        )
        return cursor.fetchone()

    def list_review_findings(self, run_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                id,
                run_id,
                agent,
                severity,
                category,
                location_hint,
                quote_text,
                issue_text,
                suggestion_text,
                created_at,
                IFNULL(dimension, '') as dimension,
                IFNULL(conflict_with, '') as conflict_with,
                IFNULL(is_cross_chapter, 0) as is_cross_chapter
            FROM review_findings
            WHERE run_id = ?
            ORDER BY
                CASE severity
                    WHEN 'high' THEN 0
                    WHEN 'medium' THEN 1
                    ELSE 2
                END,
                id ASC
            """,
            (run_id,),
        )
        return list(cursor.fetchall())

    def list_chapter_events(self, book_id: int, chapter_id: int | None = None) -> list[sqlite3.Row]:
        sql = """
            SELECT
                e.id,
                e.book_id,
                e.chapter_id,
                e.label,
                e.description,
                e.sort_order,
                c.title AS chapter_title,
                c.sort_order AS chapter_sort_order
            FROM chapter_events AS e
            JOIN chapters AS c ON c.id = e.chapter_id
            WHERE e.book_id = ?
        """
        params: list[Any] = [book_id]
        if chapter_id is not None:
            sql += " AND e.chapter_id = ?"
            params.append(chapter_id)
        sql += " ORDER BY c.sort_order ASC, e.sort_order ASC, e.id ASC"
        cursor = self.connection.execute(sql, params)
        return list(cursor.fetchall())

    def create_chapter_event(
        self,
        book_id: int,
        chapter_id: int,
        label: str,
        description: str = "",
        sort_order: int | None = None,
    ) -> int:
        if sort_order is None:
            row = self.connection.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM chapter_events WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()
            sort_order = int(row["next_order"]) if row else 1
        cursor = self.connection.execute(
            """
            INSERT INTO chapter_events (book_id, chapter_id, label, description, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (book_id, chapter_id, label, description, sort_order),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def update_chapter_event(
        self,
        event_id: int,
        label: str,
        description: str = "",
        sort_order: int | None = None,
    ) -> None:
        if sort_order is None:
            self.connection.execute(
                """
                UPDATE chapter_events
                SET label = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (label, description, event_id),
            )
        else:
            self.connection.execute(
                """
                UPDATE chapter_events
                SET label = ?, description = ?, sort_order = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (label, description, sort_order, event_id),
            )
        self.connection.commit()

    def delete_chapter_event(self, event_id: int) -> None:
        self.connection.execute("DELETE FROM chapter_events WHERE id = ?", (event_id,))
        self.connection.commit()

    def list_reference_sources(self) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                id,
                title,
                author,
                source_path,
                rights_note,
                source_type,
                source_url,
                source_license,
                reusable_level,
                attribution_note,
                created_at
            FROM reference_sources
            ORDER BY id DESC
            """
        )
        return list(cursor.fetchall())

    def create_reference_source(
        self,
        title: str,
        source_path: str,
        author: str = "",
        rights_note: str = "",
        source_type: str = "book",
        source_url: str = "",
        source_license: str = "",
        reusable_level: str = "pattern_only",
        attribution_note: str = "",
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO reference_sources (
                title,
                author,
                source_path,
                rights_note,
                source_type,
                source_url,
                source_license,
                reusable_level,
                attribution_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                author,
                source_path,
                rights_note,
                source_type,
                source_url,
                source_license,
                reusable_level,
                attribution_note,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def get_reference_source(self, source_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT
                id,
                title,
                author,
                source_path,
                rights_note,
                source_type,
                source_url,
                source_license,
                reusable_level,
                attribution_note,
                created_at
            FROM reference_sources
            WHERE id = ?
            """,
            (source_id,),
        )
        return cursor.fetchone()

    def delete_reference_source(self, source_id: int) -> None:
        self.connection.execute("DELETE FROM reference_sources WHERE id = ?", (source_id,))
        self.connection.commit()

    def get_reference_source_by_url(self, source_url: str) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT
                id,
                title,
                author,
                source_path,
                rights_note,
                source_type,
                source_url,
                source_license,
                reusable_level,
                attribution_note,
                created_at
            FROM reference_sources
            WHERE source_url = ?
            """,
            (source_url,),
        )
        return cursor.fetchone()

    def replace_skills_for_source(self, source_id: int, skills: list[dict[str, Any]]) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM distilled_skills WHERE source_id = ?",
                (source_id,),
            )

            for skill in skills:
                self.connection.execute(
                    """
                    INSERT INTO distilled_skills (
                        source_id,
                        name,
                        category,
                        summary,
                        instruction_text,
                        use_cases_text,
                        risk_note
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        skill["name"],
                        skill["category"],
                        skill["summary"],
                        skill["instruction"],
                        skill.get("use_cases", ""),
                        skill.get("risk_note", ""),
                    ),
                )

    def list_skills(self, source_id: int | None = None) -> list[sqlite3.Row]:
        sql = """
            SELECT
                ds.id,
                ds.source_id,
                ds.name,
                ds.category,
                ds.summary,
                ds.instruction_text,
                ds.use_cases_text,
                ds.risk_note,
                rs.title AS source_title,
                rs.source_type AS source_type,
                rs.source_url AS source_url,
                rs.source_license AS source_license,
                rs.reusable_level AS reusable_level,
                rs.attribution_note AS attribution_note
            FROM distilled_skills AS ds
            JOIN reference_sources AS rs ON rs.id = ds.source_id
        """
        params: tuple[Any, ...] = ()
        if source_id is not None:
            sql += " WHERE ds.source_id = ?"
            params = (source_id,)
        sql += " ORDER BY ds.id DESC"
        cursor = self.connection.execute(sql, params)
        return list(cursor.fetchall())

    def delete_skill(self, skill_id: int) -> None:
        self.connection.execute("DELETE FROM distilled_skills WHERE id = ?", (skill_id,))
        self.connection.commit()

    def bind_skill_to_book(self, book_id: int, skill_id: int, weight: float = 1.0) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO skill_bindings (scope_type, scope_id, skill_id, weight)
            VALUES ('book', ?, ?, ?)
            """,
            (book_id, skill_id, weight),
        )
        self.connection.commit()

    def bind_skill_to_global(self, skill_id: int, weight: float = 1.0) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO skill_bindings (scope_type, scope_id, skill_id, weight)
            VALUES ('global', 0, ?, ?)
            """,
            (skill_id, weight),
        )
        self.connection.commit()

    def unbind_skill_from_global(self, skill_id: int) -> None:
        self.connection.execute(
            """
            DELETE FROM skill_bindings
            WHERE scope_type = 'global' AND scope_id = 0 AND skill_id = ?
            """,
            (skill_id,),
        )
        self.connection.commit()

    def list_bound_skills_for_global(self) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                ds.id,
                ds.source_id,
                ds.name,
                ds.category,
                ds.summary,
                ds.instruction_text,
                ds.use_cases_text,
                ds.risk_note,
                sb.weight,
                rs.title AS source_title,
                rs.source_type AS source_type,
                rs.source_url AS source_url,
                rs.source_license AS source_license,
                rs.reusable_level AS reusable_level,
                rs.attribution_note AS attribution_note
            FROM skill_bindings AS sb
            JOIN distilled_skills AS ds ON ds.id = sb.skill_id
            JOIN reference_sources AS rs ON rs.id = ds.source_id
            WHERE sb.scope_type = 'global' AND sb.scope_id = 0
            ORDER BY sb.id DESC
            """
        )
        return list(cursor.fetchall())

    def unbind_skill_from_book(self, book_id: int, skill_id: int) -> None:
        self.connection.execute(
            """
            DELETE FROM skill_bindings
            WHERE scope_type = 'book' AND scope_id = ? AND skill_id = ?
            """,
            (book_id, skill_id),
        )
        self.connection.commit()

    def list_bound_skills_for_book(self, book_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                ds.id,
                ds.source_id,
                ds.name,
                ds.category,
                ds.summary,
                ds.instruction_text,
                ds.use_cases_text,
                ds.risk_note,
                sb.weight,
                rs.title AS source_title,
                rs.source_type AS source_type,
                rs.source_url AS source_url,
                rs.source_license AS source_license,
                rs.reusable_level AS reusable_level,
                rs.attribution_note AS attribution_note
            FROM skill_bindings AS sb
            JOIN distilled_skills AS ds ON ds.id = sb.skill_id
            JOIN reference_sources AS rs ON rs.id = ds.source_id
            WHERE sb.scope_type = 'book' AND sb.scope_id = ?
            ORDER BY sb.id DESC
            """,
            (book_id,),
        )
        return list(cursor.fetchall())

    def bind_skill_to_chapter(self, chapter_id: int, skill_id: int, weight: float = 1.0) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO skill_bindings (scope_type, scope_id, skill_id, weight)
            VALUES ('chapter', ?, ?, ?)
            """,
            (chapter_id, skill_id, weight),
        )
        self.connection.commit()

    def unbind_skill_from_chapter(self, chapter_id: int, skill_id: int) -> None:
        self.connection.execute(
            """
            DELETE FROM skill_bindings
            WHERE scope_type = 'chapter' AND scope_id = ? AND skill_id = ?
            """,
            (chapter_id, skill_id),
        )
        self.connection.commit()

    def list_bound_skills_for_chapter(self, chapter_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                ds.id,
                ds.source_id,
                ds.name,
                ds.category,
                ds.summary,
                ds.instruction_text,
                ds.use_cases_text,
                ds.risk_note,
                sb.weight,
                rs.title AS source_title,
                rs.source_type AS source_type,
                rs.source_url AS source_url,
                rs.source_license AS source_license,
                rs.reusable_level AS reusable_level,
                rs.attribution_note AS attribution_note
            FROM skill_bindings AS sb
            JOIN distilled_skills AS ds ON ds.id = sb.skill_id
            JOIN reference_sources AS rs ON rs.id = ds.source_id
            WHERE sb.scope_type = 'chapter' AND sb.scope_id = ?
            ORDER BY sb.id DESC
            """,
            (chapter_id,),
        )
        return list(cursor.fetchall())

    def list_characters(self, book_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT id, name, role, profile_text, profile_data_json, image_path, graph_x, graph_y, pinned
            FROM characters
            WHERE book_id = ?
            ORDER BY pinned DESC, id ASC
            """,
            (book_id,),
        )
        return list(cursor.fetchall())

    def create_character(self, book_id: int, name: str) -> int:
        profile_data = character_profile_form_defaults(name, "")
        profile_text = character_profile_form_to_markdown(profile_data, name, "")
        cursor = self.connection.execute(
            """
            INSERT INTO characters (book_id, name, profile_text, profile_data_json)
            VALUES (?, ?, ?, ?)
            """,
            (book_id, name, profile_text, self._character_profile_data_to_json(profile_data, name, "")),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def get_character(self, character_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT id, book_id, name, role, profile_text, profile_data_json, image_path, graph_x, graph_y, pinned
            FROM characters
            WHERE id = ?
            """,
            (character_id,),
        )
        return cursor.fetchone()

    def update_character(
        self,
        character_id: int,
        name: str,
        role: str,
        profile_text: str,
        image_path: str | None = None,
    ) -> None:
        existing = self.get_character(character_id)
        existing_text = str(existing["profile_text"] or "") if existing is not None else ""
        incoming_text = str(profile_text or "")
        if existing is not None and incoming_text.strip() == existing_text.strip():
            profile_data = character_profile_form_defaults(name, role)
            profile_text = character_profile_form_to_markdown(profile_data, name, role)
            profile_data_json = self._character_profile_data_to_json(profile_data, name, role)
        else:
            profile_text, profile_data_json = self._character_profile_payload_from_text(incoming_text, name, role)
        pinned = 1 if role in ("男主", "女主") else 0
        if image_path is None:
            self.connection.execute(
                "UPDATE characters SET name = ?, role = ?, profile_text = ?, profile_data_json = ?, pinned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, role, profile_text, profile_data_json, pinned, character_id),
            )
        else:
            self.connection.execute(
                "UPDATE characters SET name = ?, role = ?, profile_text = ?, profile_data_json = ?, image_path = ?, pinned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, role, profile_text, profile_data_json, image_path, pinned, character_id),
            )
        self.connection.commit()

    def update_character_form(
        self,
        character_id: int,
        name: str,
        role: str,
        profile_data: dict[str, Any],
        image_path: str | None = None,
    ) -> None:
        normalized = normalize_character_profile_form(profile_data, name, role)
        profile_text = character_profile_form_to_markdown(normalized, name, role)
        profile_data_json = self._character_profile_data_to_json(normalized, name, role)
        pinned = 1 if role in ("男主", "女主") else 0
        if image_path is None:
            self.connection.execute(
                "UPDATE characters SET name = ?, role = ?, profile_text = ?, profile_data_json = ?, pinned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, role, profile_text, profile_data_json, pinned, character_id),
            )
        else:
            self.connection.execute(
                "UPDATE characters SET name = ?, role = ?, profile_text = ?, profile_data_json = ?, image_path = ?, pinned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, role, profile_text, profile_data_json, image_path, pinned, character_id),
            )
        self.connection.commit()

    def get_character_profile_form(self, character_id: int) -> dict[str, Any]:
        character = self.get_character(character_id)
        if not character:
            return character_profile_form_defaults("", "")
        name = str(character["name"] or "")
        role = str(character["role"] or "")
        data = self._character_profile_json_to_data(str(character["profile_data_json"] or ""), name, role)
        if data is None:
            data = character_profile_form_defaults(name, role)
        return normalize_character_profile_form(data, name, role)

    def update_character_image(self, character_id: int, image_path: str) -> None:
        self.connection.execute(
            """
            UPDATE characters
            SET image_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (image_path, character_id),
        )
        self.connection.commit()

    def update_character_position(self, character_id: int, graph_x: float, graph_y: float) -> None:
        self.connection.execute(
            """
            UPDATE characters
            SET graph_x = ?, graph_y = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (float(graph_x), float(graph_y), character_id),
        )
        self.connection.commit()

    def delete_character(self, character_id: int) -> None:
        self.connection.execute(
            "DELETE FROM characters WHERE id = ?",
            (character_id,),
        )
        self.connection.commit()

    def list_relationships(self, book_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                r.id,
                r.book_id,
                r.source_character_id,
                r.target_character_id,
                r.relationship_type,
                r.description,
                source.name AS source_name,
                target.name AS target_name
            FROM character_relationships AS r
            JOIN characters AS source ON source.id = r.source_character_id
            JOIN characters AS target ON target.id = r.target_character_id
            WHERE r.book_id = ?
            ORDER BY r.id ASC
            """,
            (book_id,),
        )
        return list(cursor.fetchall())

    def get_relationship(self, relationship_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT
                r.id,
                r.book_id,
                r.source_character_id,
                r.target_character_id,
                r.relationship_type,
                r.description,
                source.name AS source_name,
                target.name AS target_name
            FROM character_relationships AS r
            JOIN characters AS source ON source.id = r.source_character_id
            JOIN characters AS target ON target.id = r.target_character_id
            WHERE r.id = ?
            """,
            (relationship_id,),
        )
        return cursor.fetchone()

    def create_relationship(
        self,
        book_id: int,
        source_character_id: int,
        target_character_id: int,
        relationship_type: str = "",
        description: str = "",
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO character_relationships (
                book_id,
                source_character_id,
                target_character_id,
                relationship_type,
                description
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (book_id, source_character_id, target_character_id, relationship_type, description),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def create_chapter_after(
        self,
        after_chapter_id: int,
        title: str,
        outline: str = "",
        content: str = "",
    ) -> int:
        current = self.connection.execute(
            """
            SELECT id, book_id, volume_id, sort_order
            FROM chapters
            WHERE id = ?
            """,
            (after_chapter_id,),
        ).fetchone()
        if not current:
            raise ValueError("Chapter not found.")
        book_id = int(current["book_id"])
        volume_id = current["volume_id"]
        sort_order = int(current["sort_order"])
        clause, params = self._build_volume_clause(volume_id)
        with self.connection:
            self.connection.execute(
                f"""
                UPDATE chapters
                SET sort_order = sort_order + 1, updated_at = CURRENT_TIMESTAMP
                WHERE book_id = ? AND {clause} AND sort_order > ?
                """,
                (book_id, *params, sort_order),
            )
            cursor = self.connection.execute(
                """
                INSERT INTO chapters (book_id, volume_id, title, outline, content, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (book_id, volume_id, title, outline, content, sort_order + 1),
            )
            new_id = int(cursor.lastrowid)
            self._normalize_chapter_order(book_id, volume_id)
        return new_id

    def replace_book_relationships(self, book_id: int, relationships: list[dict[str, Any]]) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM character_relationships WHERE book_id = ?",
                (book_id,),
            )
            for item in relationships:
                source_id = int(item.get("source_character_id", 0) or 0)
                target_id = int(item.get("target_character_id", 0) or 0)
                if not source_id or not target_id or source_id == target_id:
                    continue
                self.connection.execute(
                    """
                    INSERT INTO character_relationships (
                        book_id,
                        source_character_id,
                        target_character_id,
                        relationship_type,
                        description
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        book_id,
                        source_id,
                        target_id,
                        str(item.get("relationship_type", "") or "关联").strip(),
                        str(item.get("description", "") or "").strip(),
                    ),
                )

    def update_relationship(
        self,
        relationship_id: int,
        relationship_type: str,
        description: str = "",
    ) -> None:
        self.connection.execute(
            """
            UPDATE character_relationships
            SET relationship_type = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (relationship_type, description, relationship_id),
        )
        self.connection.commit()

    def delete_relationship(self, relationship_id: int) -> None:
        self.connection.execute(
            "DELETE FROM character_relationships WHERE id = ?",
            (relationship_id,),
        )
        self.connection.commit()

    def list_relationships_by_character(self, character_id: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                r.id,
                r.book_id,
                r.source_character_id,
                r.target_character_id,
                r.relationship_type,
                r.description,
                source.name AS source_name,
                target.name AS target_name
            FROM character_relationships AS r
            JOIN characters AS source ON source.id = r.source_character_id
            JOIN characters AS target ON target.id = r.target_character_id
            WHERE r.source_character_id = ? OR r.target_character_id = ?
            ORDER BY r.id ASC
            """,
            (character_id, character_id),
        )
        return list(cursor.fetchall())

    def list_world_entries(self, book_id: int) -> list[Any]:
        rows = self.connection.execute(
            """
            SELECT id, book_id, name, category, content_text
            FROM world_entries
            WHERE book_id = ?
            ORDER BY id ASC
            """,
            (book_id,),
        ).fetchall()
        entries = [dict(row) for row in rows]
        book = self.get_book(book_id)
        if book:
            content = str(book["world_text"] or "").strip()
            if not content:
                content = world_form_to_markdown(self.get_book_world_form(book_id))
            if content.strip():
                entries.insert(0, {
                    "id": 0,
                    "book_id": book_id,
                    "name": "世界观总设定",
                    "category": "总设定",
                    "content_text": content,
                })
        return entries

    def create_world_entry(self, book_id: int, name: str, category: str = "设定") -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO world_entries (book_id, name, category, content_text)
            VALUES (?, ?, ?, ?)
            """,
            (book_id, name, category, world_entry_template(name, category)),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def get_world_entry(self, entry_id: int) -> sqlite3.Row | None:
        cursor = self.connection.execute(
            """
            SELECT id, book_id, name, category, content_text
            FROM world_entries
            WHERE id = ?
            """,
            (entry_id,),
        )
        return cursor.fetchone()

    def update_world_entry(
        self,
        entry_id: int,
        name: str,
        category: str,
        content_text: str,
    ) -> None:
        self.connection.execute(
            """
            UPDATE world_entries
            SET name = ?, category = ?, content_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, category, content_text, entry_id),
        )
        self.connection.commit()

    def delete_world_entry(self, entry_id: int) -> None:
        self.connection.execute(
            "DELETE FROM world_entries WHERE id = ?",
            (entry_id,),
        )
        self.connection.commit()

    def count_book_words(self, book_id: int) -> int:
        rows = self.connection.execute(
            "SELECT content FROM chapters WHERE book_id = ?",
            (book_id,),
        ).fetchall()
        return sum(len(str(row["content"] or "")) for row in rows)

    def count_volume_words(self, volume_id: int) -> int:
        rows = self.connection.execute(
            "SELECT content FROM chapters WHERE volume_id = ?",
            (volume_id,),
        ).fetchall()
        return sum(len(str(row["content"] or "")) for row in rows)

    def get_book_export_data(self, book_id: int) -> dict[str, Any]:
        book = self.get_book(book_id)
        if not book:
            raise ValueError("Book not found.")

        volumes = self.list_volumes(book_id)
        chapters = self.connection.execute(
            """
            SELECT
                c.id,
                c.title,
                c.outline,
                c.content,
                c.summary_text,
                c.sort_order,
                c.volume_id,
                COALESCE(v.title, '未分卷') AS volume_title,
                COALESCE(v.sort_order, 2147483647) AS volume_sort_order
            FROM chapters AS c
            LEFT JOIN volumes AS v ON v.id = c.volume_id
            WHERE c.book_id = ?
            ORDER BY
                CASE WHEN c.volume_id IS NULL THEN 1 ELSE 0 END ASC,
                COALESCE(v.sort_order, 2147483647) ASC,
                c.sort_order ASC,
                c.id ASC
            """,
            (book_id,),
        ).fetchall()

        characters = self.connection.execute(
            """
            SELECT name, role, profile_text
            FROM characters
            WHERE book_id = ?
            ORDER BY id ASC
            """,
            (book_id,),
        ).fetchall()

        return {
            "book": dict(book),
            "volumes": [dict(item) for item in volumes],
            "chapters": [dict(item) for item in chapters],
            "characters": [dict(item) for item in characters],
            "world_entries": [dict(item) for item in self.list_world_entries(book_id)],
            "unassigned_chapter_count": self.count_unassigned_chapters(book_id),
        }

    def list_name_shortcuts(self, book_id: int) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT id, book_id, key_seq, character_name FROM name_shortcuts WHERE book_id = ? ORDER BY id ASC",
            (book_id,),
        ).fetchall()

    def add_name_shortcut(self, book_id: int, key_seq: str, character_name: str) -> int:
        cursor = self.connection.execute(
            "INSERT INTO name_shortcuts (book_id, key_seq, character_name) VALUES (?, ?, ?)",
            (book_id, key_seq, character_name),
        )
        self.connection.commit()
        return cursor.lastrowid or 0

    def delete_name_shortcut(self, shortcut_id: int) -> None:
        self.connection.execute("DELETE FROM name_shortcuts WHERE id = ?", (shortcut_id,))
        self.connection.commit()

    def close(self) -> None:
        try:
            self.connection.close()
        except Exception:
            pass

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def get_node_styles(self, book_id: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, book_id, name, display_name, background, border_color,
                   border_width, text_color, icon_type, is_preset
            FROM node_styles
            WHERE book_id = ?
            ORDER BY is_preset DESC, name
            """,
            (book_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_relationship_types(self, book_id: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, book_id, name, display_name, color, line_style,
                   arrow_type, is_directed, is_preset
            FROM relationship_types
            WHERE book_id = ?
            ORDER BY is_preset DESC, name
            """,
            (book_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_character_node_style(self, character_id: int, style_id: int) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO character_node_styles (character_id, style_id) VALUES (?, ?)",
            (character_id, style_id),
        )
        self.connection.commit()

    def get_character_node_style(self, character_id: int) -> int | None:
        row = self.connection.execute(
            "SELECT style_id FROM character_node_styles WHERE character_id = ?",
            (character_id,),
        ).fetchone()
        return int(row["style_id"]) if row else None

    def update_relationship_type_info(
        self, relationship_id: int, relationship_type_id: int | None, description: str = ""
    ) -> None:
        self.connection.execute(
            """
            UPDATE character_relationships
            SET relationship_type_id = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (relationship_type_id, description, relationship_id),
        )
        self.connection.commit()

    def initialize_book_star_graph_defaults(self, book_id: int) -> None:
        from novel_app.qt.star_graph_models import PRESET_NODE_STYLES, PRESET_RELATIONSHIP_TYPES

        for style in PRESET_NODE_STYLES:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO node_styles
                (book_id, name, display_name, background, border_color, border_width, text_color, icon_type, is_preset)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    book_id,
                    style.name,
                    style.display_name,
                    style.background,
                    style.border_color,
                    style.border_width,
                    style.text_color,
                    style.icon_type,
                ),
            )

        for rtype in PRESET_RELATIONSHIP_TYPES:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO relationship_types
                (book_id, name, display_name, color, line_style, arrow_type, is_directed, is_preset)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    book_id,
                    rtype.name,
                    rtype.display_name,
                    rtype.color,
                    rtype.line_style,
                    rtype.arrow_type,
                    1 if rtype.is_directed else 0,
                ),
            )
        self.connection.commit()

    def create_custom_node_style(
        self,
        book_id: int,
        name: str,
        display_name: str,
        background: str,
        border_color: str,
        border_width: float,
        text_color: str,
        icon_type: str,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO node_styles
            (book_id, name, display_name, background, border_color, border_width, text_color, icon_type, is_preset)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                book_id,
                name,
                display_name,
                background,
                border_color,
                border_width,
                text_color,
                icon_type,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def create_custom_relationship_type(
        self,
        book_id: int,
        name: str,
        display_name: str,
        color: str,
        line_style: str,
        arrow_type: str,
        is_directed: bool,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO relationship_types
            (book_id, name, display_name, color, line_style, arrow_type, is_directed, is_preset)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                book_id,
                name,
                display_name,
                color,
                line_style,
                arrow_type,
                1 if is_directed else 0,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)
