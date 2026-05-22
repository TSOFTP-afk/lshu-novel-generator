from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QTextEdit, QVBoxLayout, QWidget

from novel_app.qt.forms import WorldFormWidget


def build_world_tab(window: Any) -> QWidget:
    page = window._make_drawer_page()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)

    window.world_form = WorldFormWidget()
    window.world_form.changed.connect(window._on_world_form_changed)
    window.world_content_preview = QTextEdit()
    window.world_content_preview.setReadOnly(True)
    window.world_content_preview.setPlaceholderText("世界观 Markdown 预览")
    world_header = QHBoxLayout()
    world_hint = QLabel("世界观")
    world_hint.setObjectName("MetaLabel")
    window.world_markdown_toggle_btn = QPushButton("预览")
    window.world_markdown_toggle_btn.setObjectName("TinyButton")
    window.world_markdown_toggle_btn.clicked.connect(lambda: window._toggle_markdown_view("world"))
    window.world_template_btn = QPushButton("重置世界观模板")
    window.world_template_btn.clicked.connect(window._fill_world_template)
    world_header.addWidget(world_hint, 1)
    world_header.addWidget(window.world_markdown_toggle_btn)
    world_header.addWidget(window.world_template_btn)
    window.world_markdown_stack = QStackedWidget()
    window.world_markdown_stack.addWidget(window.world_form)
    window.world_markdown_stack.addWidget(window.world_content_preview)
    buttons = QHBoxLayout()
    save_btn = QPushButton("保存")
    import_btn = QPushButton("导入文件")
    save_btn.clicked.connect(window._save_world_entry)
    import_btn.clicked.connect(window._import_world_file)
    buttons.addWidget(save_btn)
    buttons.addWidget(import_btn)
    layout.addLayout(world_header)
    layout.addWidget(window.world_markdown_stack, 1)
    layout.addLayout(buttons)
    return page


def refresh_world(window: Any) -> None:
    window._load_world_form_for_book(window.state.selected_book_id)
