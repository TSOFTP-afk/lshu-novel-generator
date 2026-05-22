from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTabWidget, QWidget

from novel_app.qt.drawer import pages
from novel_app.structured_templates import world_form_defaults

DRAWER_TAB_SEQUENCE = ("overview", "outline", "characters", "world", "skills", "review", "tasks")


class DrawerController:
    def __init__(self, window: Any) -> None:
        self.window = window

    def build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("DrawerTabs")
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.window.drawer_tab_indexes = {}

        def add_tab(key: str, widget: QWidget, label: str) -> None:
            self.window.drawer_tab_indexes[key] = tabs.addTab(widget, label)

        add_tab("overview", pages.build_overview_tab(self.window), "概览")
        add_tab("shortcuts", pages.build_shortcuts_tab(self.window), "快键")
        add_tab("outline", pages.build_outline_tab(self.window), "生成")
        add_tab("characters", pages.build_characters_tab(self.window), "人物")
        add_tab("world", pages.build_world_tab(self.window), "世界观")
        add_tab("skills", pages.build_skills_tab(self.window), "Skills")
        add_tab("review", pages.build_review_tab(self.window), "记录")
        add_tab("tasks", pages.build_task_tab(self.window), "任务")
        tabs.currentChanged.connect(lambda _index: self.window._on_drawer_tab_changed())
        return tabs

    def make_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("DrawerPage")
        page.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        return page

    def refresh(self) -> None:
        book_id = self.window.state.selected_book_id
        if not book_id:
            self.window.global_skills = [dict(item) for item in self.window.database.list_bound_skills_for_global()]
            self.window.book_skills = []
            self.window.bound_skills = []
            self.window.characters = []
            self.window.world_entries = []
            if hasattr(self.window, "overview_title"):
                self.window.overview_title.setText("未选择书籍")
                self.window.overview_meta.setText("卷 0 · 章节 0 · Skills 0")
                self.window.sourcebook_preview.clear()
            if hasattr(self.window, "characters_list"):
                self.window._clear_character_form()
                self.window._refresh_character_list()
            if hasattr(self.window, "world_form"):
                self.window.world_form.set_data(world_form_defaults())
                self.window._world_form_book_id = None
                self.window._refresh_world_markdown_preview()
                self.window._world_form_dirty = False
            if hasattr(self.window, "enabled_skills_list"):
                self.window.enabled_skills_list.clear()
                self.window.skill_preview.clear()
            self.sync_overview_tab_visibility()
            return
        self.window._load_book_side_data(book_id)
        self.sync_overview_tab_visibility()
        self.sync_shortcuts_tab_visibility()
        self.sync_outline_tab_for_level()
        self.window._refresh_overview()
        self.window._drawer_tabs_stale = {"outline", "characters", "world", "skills", "shortcuts", "review", "tasks"}
        self.refresh_visible_tab()

    def on_tab_changed(self) -> None:
        self.sync_overview_tab_visibility()
        self.sync_shortcuts_tab_visibility()
        self.sync_outline_tab_for_level()
        self.update_title()
        self.refresh_visible_tab()

    def refresh_visible_tab(self) -> None:
        if not hasattr(self.window, "drawer_tabs"):
            return
        stale = getattr(self.window, "_drawer_tabs_stale", None)
        if stale is None:
            return
        key_map = {v: k for k, v in self.window.drawer_tab_indexes.items()}
        current_index = self.window.drawer_tabs.currentIndex()
        key = key_map.get(current_index)
        if key is None or key not in stale:
            return
        stale.discard(key)
        if key == "outline":
            self.window._refresh_generation_outline_context()
        elif key == "characters":
            self.window._refresh_characters()
        elif key == "world":
            self.window._refresh_world()
        elif key == "skills":
            self.window._refresh_skills()
        elif key == "review":
            self.window._refresh_review_tab()
        elif key == "shortcuts":
            self.window._refresh_shortcuts_list()

    def is_book_level_selected(self) -> bool:
        return bool(self.window.state.selected_book_id and self.window.state.current_node_kind == "book")

    def sync_overview_tab_visibility(self) -> None:
        if not hasattr(self.window, "drawer_tabs"):
            return
        index = self.window.drawer_tab_indexes.get("overview")
        if index is None:
            return
        visible = self.is_book_level_selected()
        self.set_tab_visible(index, visible, fallback_key="outline")

    def sync_shortcuts_tab_visibility(self) -> None:
        if not hasattr(self.window, "drawer_tabs"):
            return
        index = self.window.drawer_tab_indexes.get("shortcuts")
        if index is None:
            return
        visible = self.is_book_level_selected()
        self.set_tab_visible(index, visible, fallback_key="outline")
        if visible and self.window.state.selected_book_id:
            self.window._refresh_shortcuts_list()

    def sync_outline_tab_for_level(self) -> None:
        if not hasattr(self.window, "outline_tab_title"):
            return
        kind = self.window.state.current_node_kind
        if kind == "volume" and self.window.state.selected_volume_id:
            self.window.outline_tab_title.setText("卷大纲")
            self.window.outline_action_btn.setText("保存卷大纲")
            self.window.outline_sync_btn.hide()
            self.window.chapter_outline_editor.hide()
            self.window.volume_outline_editor.show()
            volume = self.window.database.get_volume(self.window.state.selected_volume_id)
            if volume:
                self.window.volume_outline_editor.blockSignals(True)
                self.window.volume_outline_editor.setPlainText(str(volume["outline_text"] or ""))
                self.window.volume_outline_editor.blockSignals(False)
        elif kind == "chapter":
            self.window.outline_tab_title.setText("章节生成大纲")
            self.window.outline_action_btn.setText("长篇生成")
            self.window.outline_sync_btn.show()
            self.window.volume_outline_editor.hide()
            self.window.chapter_outline_editor.show()
        else:
            self.window.outline_tab_title.setText("章节生成大纲")
            self.window.outline_action_btn.setText("长篇生成")
            self.window.outline_sync_btn.show()
            self.window.volume_outline_editor.hide()
            self.window.chapter_outline_editor.show()

    def set_tab_visible(self, index: int, visible: bool, *, fallback_key: str = "outline") -> None:
        if hasattr(self.window.drawer_tabs, "setTabVisible"):
            self.window.drawer_tabs.setTabVisible(index, visible)
        else:
            self.window.drawer_tabs.setTabEnabled(index, visible)
        if not visible and self.window.drawer_tabs.currentIndex() == index:
            fallback = self.window.drawer_tab_indexes.get(fallback_key, 0)
            self.window.drawer_tabs.setCurrentIndex(fallback)

    def set_tab(self, key: str) -> None:
        index = self.window.drawer_tab_indexes.get(key)
        if index is not None:
            self.window.drawer_tabs.setCurrentIndex(index)

    def update_title(self) -> None:
        if not hasattr(self.window, "drawer_tabs"):
            return
        tab_label = self.window.drawer_tabs.tabText(self.window.drawer_tabs.currentIndex()) or "详情"
        subject = (
            getattr(self.window.state, "selected_chapter_title", "")
            or getattr(self.window.state, "selected_volume_title", "")
            or self.window.state.selected_book_title
            or "当前书籍"
        )
        title = f"{tab_label} · {subject}" if subject else tab_label
        if hasattr(self.window, "drawer_title_label"):
            self.window.drawer_title_label.setText(title)

    def open(self, kind: str = "details") -> None:
        if kind == "star":
            kind = "details"
        self.window.state.drawer_kind = kind
        wide_drawer = kind in {"tasks", "review"}
        drawer_min_width = 340 if wide_drawer else 320
        base_width = 420 if wide_drawer else 380
        desired_width = max(self.window.qt_drawer_width, base_width)
        max_drawer_width = max(drawer_min_width, self.window.width() - 720)
        desired_width = min(desired_width, max_drawer_width)
        if kind == "tasks":
            self.set_tab("tasks")
        elif kind == "review":
            self.set_tab("review")
        else:
            self.set_tab("outline")
        self.update_title()
        self.window.drawer.setMinimumWidth(drawer_min_width)
        self.window.drawer.setVisible(True)
        self.window.drawer.setFixedWidth(desired_width)
        self.refresh()
