from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget



def build_overview_tab(window: Any) -> QWidget:
    page = window._make_drawer_page()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(8)

    title_row = QHBoxLayout()
    window.overview_title = QLabel("")
    window.overview_title.setObjectName("SectionTitle")
    window.ai_summarize_btn = QPushButton("AI 总结全书")
    window.ai_summarize_btn.clicked.connect(window._start_ai_book_summary)
    title_row.addWidget(window.overview_title, 1)
    title_row.addWidget(window.ai_summarize_btn)
    layout.addLayout(title_row)

    window.overview_meta = QLabel("")
    window.overview_meta.setObjectName("MetaLabel")
    window.sourcebook_preview = QPlainTextEdit()
    window.sourcebook_preview.setReadOnly(True)
    layout.addWidget(window.overview_meta)
    layout.addWidget(window.sourcebook_preview, 1)
    return page


def refresh_overview(window: Any) -> None:
    if not window.state.selected_book_id:
        return
    volumes = window.database.list_volumes(window.state.selected_book_id)
    chapters = window.database.list_chapters(window.state.selected_book_id)
    window.overview_title.setText(window.state.selected_book_title or "未命名书籍")
    window.overview_meta.setText(
        f"卷 {len(volumes)} · 章节 {len(chapters)} · Skills 全局 {len(window.global_skills)} / 书籍 {len(window.book_skills)} / 章节 {len(window.bound_skills)}"
    )
    window.sourcebook_preview.setPlainText(window._build_sourcebook_context())
