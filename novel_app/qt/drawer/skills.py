from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget



def build_skills_tab(window: Any) -> QWidget:
    page = window._make_drawer_page()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    window.enabled_skills_list = QListWidget()
    window.enabled_skills_list.setObjectName("DrawerList")
    window.skill_preview = QPlainTextEdit()
    window.skill_preview.setReadOnly(True)
    manage = QPushButton("完整管理")
    manage.clicked.connect(window._open_book_settings)
    layout.addWidget(QLabel("已启用 Skills（全局 / 书籍 / 章节）"))
    layout.addWidget(window.enabled_skills_list, 1)
    layout.addWidget(window.skill_preview, 1)
    layout.addWidget(manage)
    window.enabled_skills_list.currentItemChanged.connect(window._on_enabled_skill_selected)
    return page


def refresh_skills(window: Any) -> None:
    window.enabled_skills_list.clear()
    scoped_items = [
        ("全局", item) for item in window.global_skills
    ] + [
        ("书籍", item) for item in window.book_skills
    ] + [
        ("章节", item) for item in window.bound_skills
    ]
    seen: set[int] = set()
    for scope_label, item in scoped_items:
        skill_id = int(item["id"])
        if skill_id in seen:
            continue
        seen.add(skill_id)
        list_item = QListWidgetItem(f"{scope_label} · {item.get('name', '')} · {item.get('category', '')}")
        list_item.setData(Qt.ItemDataRole.UserRole, item)
        window.enabled_skills_list.addItem(list_item)


def on_enabled_skill_selected(window: Any, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
    if not current:
        window.skill_preview.clear()
        return
    item = current.data(Qt.ItemDataRole.UserRole) or {}
    window.skill_preview.setPlainText(
        "\n".join(
            [
                str(item.get("summary", "")),
                "",
                str(item.get("instruction_text", "")),
                "",
                f"来源：{item.get('source_title', '')}",
                f"许可：{item.get('source_license', '') or '未记录'}",
            ]
        ).strip()
    )
