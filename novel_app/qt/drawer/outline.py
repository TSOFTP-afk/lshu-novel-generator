from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget



def build_outline_tab(window: Any) -> QWidget:
    page = window._make_drawer_page()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(8)

    header = QHBoxLayout()
    window.outline_tab_title = QLabel("章节生成大纲")
    window.outline_tab_title.setObjectName("SectionTitle")
    window.outline_action_btn = QPushButton("长篇生成")
    window.outline_action_btn.clicked.connect(window._on_outline_action_btn)
    window.outline_sync_btn = QPushButton("同步章节大纲")
    window.outline_sync_btn.clicked.connect(window._refresh_summary)
    header.addWidget(window.outline_tab_title, 1)
    header.addWidget(window.outline_action_btn)
    header.addWidget(window.outline_sync_btn)
    layout.addLayout(header)

    window.chapter_outline_editor = QPlainTextEdit()
    window.chapter_outline_editor.setPlaceholderText("本章生成时直接对接的目标、冲突、场景和结尾钩子。")
    window.chapter_outline_editor.textChanged.connect(window._on_editor_changed)
    window.chapter_outline_editor.selectionChanged.connect(window._update_selection_count)
    layout.addWidget(window.chapter_outline_editor, 1)

    window.volume_outline_editor = QPlainTextEdit()
    window.volume_outline_editor.setPlaceholderText("为这一卷设定主线推进、分章规划和节奏安排。")
    window.volume_outline_editor.textChanged.connect(window._on_editor_changed)
    layout.addWidget(window.volume_outline_editor, 1)
    window.volume_outline_editor.hide()
    return page
