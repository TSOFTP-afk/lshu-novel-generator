from __future__ import annotations

from typing import Any

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget



def build_task_tab(window: Any) -> QWidget:
    page = window._make_drawer_page()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(8)
    window.task_summary_panel = QFrame()
    window.task_summary_panel.setObjectName("Card")
    window.task_summary_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    window.task_summary_panel.setMinimumHeight(0)
    window.task_summary_panel.setMaximumHeight(0)
    window.task_summary_panel.setVisible(False)
    summary_layout = QVBoxLayout(window.task_summary_panel)
    summary_layout.setContentsMargins(12, 10, 12, 10)
    summary_layout.setSpacing(6)
    summary_header = QHBoxLayout()
    window.task_summary_title = QLabel("任务队列")
    window.task_summary_title.setObjectName("SectionTitle")
    window.task_summary_badge = QLabel("空闲")
    window.task_summary_badge.setObjectName("MetaLabel")
    summary_header.addWidget(window.task_summary_title, 1)
    summary_header.addWidget(window.task_summary_badge)
    window.task_summary_detail = QLabel("暂无运行任务")
    window.task_summary_detail.setObjectName("MetaLabel")
    window.task_summary_detail.setWordWrap(True)
    summary_layout.addLayout(summary_header)
    summary_layout.addWidget(window.task_summary_detail)
    window.task_state = QLabel("空闲")
    window.task_state.setObjectName("SectionTitle")
    window.task_progress = QProgressBar()
    window.task_progress.setRange(0, 1)
    window.task_progress.setValue(0)
    window.task_log = QPlainTextEdit()
    window.task_log.setReadOnly(True)
    window.task_log.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    window.task_log.setMinimumWidth(260)
    window.task_log.textChanged.connect(lambda: window.task_log.moveCursor(QTextCursor.MoveOperation.End))
    window.cancel_task_button = QPushButton("停止任务")
    window.cancel_task_button.clicked.connect(window._cancel_task)
    window.cancel_task_button.setEnabled(False)
    layout.addWidget(window.task_state)
    layout.addWidget(window.task_progress)
    layout.addWidget(window.task_log, 1)
    layout.addWidget(window.cancel_task_button)
    return page
