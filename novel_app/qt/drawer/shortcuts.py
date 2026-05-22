from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget



def build_shortcuts_tab(window: Any) -> QWidget:
    page = window._make_drawer_page()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(8)

    header = QHBoxLayout()
    title = QLabel("人名快键")
    title.setObjectName("SectionTitle")
    header.addWidget(title, 1)
    layout.addLayout(header)

    hint = QLabel("格式：Ctrl+D = '张三'   按压快捷键时在正文光标处插入对应人名。")
    hint.setObjectName("MetaLabel")
    hint.setWordWrap(True)
    layout.addWidget(hint)

    window.shortcuts_list = QListWidget()
    window.shortcuts_list.setObjectName("DrawerList")
    layout.addWidget(window.shortcuts_list, 1)

    add_row = QHBoxLayout()
    add_row.setSpacing(6)
    window.shortcut_key_input = QLineEdit()
    window.shortcut_key_input.setPlaceholderText("快捷键（如 Ctrl+D）")
    window.shortcut_key_input.setMaximumWidth(150)
    window.shortcut_name_input = QLineEdit()
    window.shortcut_name_input.setPlaceholderText("人名（如 张三）")
    add_row.addWidget(window.shortcut_key_input)
    add_row.addWidget(window.shortcut_name_input, 1)
    layout.addLayout(add_row)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    add_btn = QPushButton("➕ 新增")
    add_btn.clicked.connect(window._add_name_shortcut)
    del_btn = QPushButton("🗑 删除")
    del_btn.clicked.connect(window._delete_name_shortcut)
    pick_btn = QPushButton("从人物列表选取")
    pick_btn.clicked.connect(window._pick_characters_for_shortcuts)
    btn_row.addWidget(add_btn)
    btn_row.addWidget(del_btn)
    btn_row.addWidget(pick_btn)
    btn_row.addStretch(1)
    layout.addLayout(btn_row)
    return page
