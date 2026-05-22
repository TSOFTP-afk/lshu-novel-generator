from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from threading import Event
from typing import Any

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from novel_app.ai_service import SimpleAIService


class ChatStreamWorker(QObject):
    chunk = pyqtSignal(str)
    done = pyqtSignal(str)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        ai_service: SimpleAIService,
        messages: list[dict[str, str]],
        cancel_event: Event,
    ) -> None:
        super().__init__()
        self.ai_service = ai_service
        self.messages = messages
        self.cancel_event = cancel_event

    def run(self) -> None:
        collected: list[str] = []
        try:
            for chunk in self.ai_service.stream_chat(self.messages, self.cancel_event, require_remote=True):
                if self.cancel_event.is_set():
                    self.cancelled.emit()
                    return
                collected.append(chunk)
                self.chunk.emit(chunk)
            self.done.emit("".join(collected))
        except Exception as exc:  # noqa: BLE001
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.error.emit(str(exc))


class CharacterSelectDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        character_provider: Callable[[], list[dict[str, Any]]],
        current_ai: dict[str, Any] | None = None,
        current_self: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择对话角色")
        self.setModal(True)
        self.resize(380, 220)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        self_label = QLabel("你扮演的角色")
        self_label.setObjectName("SectionLabel")
        root.addWidget(self_label)
        self.self_combo = QComboBox()
        self.self_combo.setMinimumWidth(300)
        root.addWidget(self.self_combo)

        ai_label = QLabel("AI 扮演的角色")
        ai_label.setObjectName("SectionLabel")
        root.addWidget(ai_label)
        self.ai_combo = QComboBox()
        self.ai_combo.setMinimumWidth(300)
        root.addWidget(self.ai_combo)

        characters = character_provider()
        char_list: list[dict[str, Any]] = list(characters) if characters else []

        self_ai_id = self._char_id(current_ai)
        self_self_id = self._char_id(current_self)

        self.self_combo.addItem("我（作者本人）", None)
        self.ai_combo.addItem("写作助手", None)

        self_sel_idx = 0
        ai_sel_idx = 0
        for i, ch in enumerate(char_list):
            name = str(ch.get("name", "") or "").strip()
            if not name:
                continue
            role = str(ch.get("role", "") or "").strip()
            label = f"{name} · {role}" if role else name
            item_data = dict(ch)
            self.self_combo.addItem(label, item_data)
            self.ai_combo.addItem(label, item_data)
            cid = int(ch.get("id", 0) or 0)
            if cid == self_self_id:
                self_sel_idx = self.self_combo.count() - 1
            if cid == self_ai_id:
                ai_sel_idx = self.ai_combo.count() - 1

        self.self_combo.setCurrentIndex(self_sel_idx)
        self.ai_combo.setCurrentIndex(ai_sel_idx)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("取消")
        ok_btn = QPushButton("确认")
        ok_btn.setDefault(True)
        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self.accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(ok_btn)
        root.addLayout(buttons)

    @staticmethod
    def _char_id(data: dict[str, Any] | None) -> int:
        if not data:
            return 0
        return int(data.get("id", 0) or 0)

    def selected_ai(self) -> dict[str, Any] | None:
        data = self.ai_combo.currentData()
        return dict(data) if isinstance(data, dict) else None

    def selected_self(self) -> dict[str, Any] | None:
        data = self.self_combo.currentData()
        return dict(data) if isinstance(data, dict) else None


class ChatDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        ai_service: SimpleAIService,
        context_builder: Callable[[dict[str, Any] | None, dict[str, Any] | None, str], str],
        character_provider: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 对话")
        self.setModal(False)
        self.resize(720, 640)
        self.ai_service = ai_service
        self.context_builder = context_builder
        self.character_provider = character_provider
        self.self_character: dict[str, Any] | None = None
        self.ai_character: dict[str, Any] | None = None
        self.chat_history: list[dict[str, str]] = []
        self.current_thread: QThread | None = None
        self.current_worker: ChatStreamWorker | None = None
        self.cancel_event: Event | None = None
        self.pending_text = ""
        self.current_ai_label: QLabel | None = None
        self.close_after_cancel = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.messages_host = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_host)
        self.messages_layout.setContentsMargins(4, 4, 4, 4)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch(1)
        self.scroll_area.setWidget(self.messages_host)
        root.addWidget(self.scroll_area, 1)

        input_box = QFrame()
        input_box.setObjectName("Card")
        input_layout = QVBoxLayout(input_box)
        input_layout.setContentsMargins(10, 10, 10, 10)
        self.input_editor = QPlainTextEdit()
        self.input_editor.setPlaceholderText("输入你想问 AI 或角色的问题... (Enter 发送)")
        self.input_editor.setMaximumHeight(108)
        self.input_editor.installEventFilter(self)
        input_layout.addWidget(self.input_editor)

        buttons = QHBoxLayout()
        self.role_btn = QPushButton("选择角色")
        self.role_btn.setToolTip("设置你扮演的角色和 AI 扮演的角色")
        self.role_btn.clicked.connect(self._open_character_select)
        self.role_label = QLabel("写作助手")
        self.role_label.setObjectName("MetaLabel")
        clear_btn = QPushButton("清空历史")
        self.cancel_btn = QPushButton("取消回复")
        self.send_btn = QPushButton("发送")
        clear_btn.clicked.connect(self.clear_history)
        self.cancel_btn.clicked.connect(self.cancel_reply)
        self.send_btn.clicked.connect(self.send_message)
        self.cancel_btn.setEnabled(False)
        buttons.addWidget(self.role_btn)
        buttons.addWidget(self.role_label)
        buttons.addWidget(clear_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.send_btn)
        input_layout.addLayout(buttons)
        root.addWidget(input_box)

        self.flush_timer = QTimer(self)
        self.flush_timer.setInterval(50)
        self.flush_timer.timeout.connect(self._flush_pending_text)

    def update_ai_service(self, ai_service: SimpleAIService) -> None:
        self.ai_service = ai_service

    def _open_character_select(self) -> None:
        if not self.character_provider:
            return
        dlg = CharacterSelectDialog(
            self,
            self.character_provider,
            current_ai=self.ai_character,
            current_self=self.self_character,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_self = dlg.selected_self()
            new_ai = dlg.selected_ai()
            if new_self != self.self_character or new_ai != self.ai_character:
                self.self_character = new_self
                self.ai_character = new_ai
                self._update_role_label()
                self.clear_history()

    def _update_role_label(self) -> None:
        parts: list[str] = []
        if self.self_character:
            parts.append(f"你：{self.self_character.get('name', '作者')}")
        if self.ai_character:
            parts.append(f"「{self.ai_character.get('name', '助手')}」")
        else:
            parts.append("写作助手")
        self.role_label.setText("  |  ".join(parts))

    def refresh_characters(self) -> None:
        pass

    def eventFilter(self, obj, event) -> bool:
        from PyQt6.QtCore import QEvent
        if obj is self.input_editor and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.send_message()
                return True
        return super().eventFilter(obj, event)

    def send_message(self) -> None:
        text = self.input_editor.toPlainText().strip()
        if not text or self.current_thread is not None:
            return
        self.input_editor.clear()
        self._append_bubble("user", text)
        self.chat_history.append({"role": "user", "content": text})
        self.current_ai_label = self._append_bubble("assistant", "")
        self.pending_text = ""

        context = self.context_builder(self.ai_character, self.self_character, text).strip()
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.extend(self.chat_history[-12:])

        self.cancel_event = Event()
        thread = QThread(self)
        worker = ChatStreamWorker(self.ai_service, messages, self.cancel_event)
        self.current_thread = thread
        self.current_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.chunk.connect(self._queue_chunk)
        worker.done.connect(self._finish_reply)
        worker.error.connect(self._fail_reply)
        worker.cancelled.connect(self._cancelled_reply)
        worker.done.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup_thread)
        self.send_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.flush_timer.start()
        thread.start()

    def cancel_reply(self) -> None:
        if self.cancel_event:
            self.cancel_event.set()
        self.cancel_btn.setEnabled(False)

    def clear_history(self) -> None:
        if self.current_thread is not None:
            return
        self.chat_history.clear()
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _append_bubble(self, role: str, text: str) -> QLabel:
        row_widget = QWidget()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row_widget.setLayout(row)
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setObjectName("ChatUserBubble" if role == "user" else "ChatAssistantBubble")
        bubble.setMinimumWidth(80)
        time_label = QLabel(datetime.now().strftime("%H:%M"))
        time_label.setObjectName("MetaLabel")
        box = QVBoxLayout()
        box.addWidget(bubble, 1)
        box.addWidget(time_label, 0, Qt.AlignmentFlag.AlignRight if role == "user" else Qt.AlignmentFlag.AlignLeft)
        holder = QWidget()
        holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        holder.setLayout(box)
        if role == "user":
            row.addStretch(2)
            row.addWidget(holder, 3)
        else:
            row.addWidget(holder, 3)
            row.addStretch(2)
        self.messages_layout.insertWidget(max(0, self.messages_layout.count() - 1), row_widget)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return bubble

    def _queue_chunk(self, chunk: str) -> None:
        self.pending_text += chunk

    def _flush_pending_text(self) -> None:
        if not self.pending_text or self.current_ai_label is None:
            return
        self.current_ai_label.setText(self.current_ai_label.text() + self.pending_text)
        self.pending_text = ""
        self._scroll_to_bottom()

    def _finish_reply(self, text: str) -> None:
        self._flush_pending_text()
        final_text = text.strip()
        if final_text:
            self.chat_history.append({"role": "assistant", "content": final_text})

    def _fail_reply(self, message: str) -> None:
        self._flush_pending_text()
        if self.current_ai_label is not None:
            self.current_ai_label.setText(f"对话失败：{message}")

    def _cancelled_reply(self) -> None:
        self._flush_pending_text()
        if self.current_ai_label is not None and not self.current_ai_label.text().strip():
            self.current_ai_label.setText("回复已取消。")

    def _cleanup_thread(self) -> None:
        self.flush_timer.stop()
        self.current_thread = None
        self.current_worker = None
        self.cancel_event = None
        self.send_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if self.close_after_cancel:
            self.close_after_cancel = False
            self.close()

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        if self.current_thread is not None:
            self.close_after_cancel = True
            self.cancel_reply()
            event.ignore()
            return
        super().closeEvent(event)
