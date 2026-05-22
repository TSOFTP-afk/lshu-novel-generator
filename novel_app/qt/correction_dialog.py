from __future__ import annotations

from datetime import datetime
from threading import Event
from typing import Any

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from novel_app.ai_service import SimpleAIService
from novel_app.prompt_settings import CORRECTION_SYSTEM_PROMPT as DEFAULT_CORRECTION_SYSTEM_PROMPT
from novel_app.prompt_utils import prompt_value


class CorrectionChatWorker(QObject):
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
        except Exception as exc:
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.error.emit(str(exc))


CORRECTION_SYSTEM_PROMPT = """你是 AI 输出纠正助手。你的任务是帮助作者修正 AI 生成的章节正文。

纠正原则：
1. 只修正作者明确指出的问题
2. 保持原文的优点和风格
3. 每次只输出需要修改的段落或完整的修改后正文
4. 修改要具体可操作，给出 Before/After 对比
5. 如果不确定作者的意图，反问确认

你可以帮作者：
- 修正角色 OOC 问题
- 调整不符合设定的描述
- 修复逻辑矛盾
- 优化不自然的 AI 表达
- 调整段落节奏
- 增强角色对话辨识度"""


CORRECTION_SYSTEM_PROMPT = DEFAULT_CORRECTION_SYSTEM_PROMPT


class CorrectionChatDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        ai_service: SimpleAIService,
        ai_output: str = "",
        chapter_context: str = "",
        prompt_overrides: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 输出纠正对话")
        self.setModal(False)
        self.resize(800, 700)
        self.ai_service = ai_service
        self.prompt_overrides = prompt_overrides or {}
        self.system_prompt = prompt_value(self.prompt_overrides, "correction.system", CORRECTION_SYSTEM_PROMPT)
        self.chat_history: list[dict[str, str]] = []
        self.current_thread: QThread | None = None
        self.current_worker: CorrectionChatWorker | None = None
        self.cancel_event: Event | None = None
        self.pending_text = ""
        self.current_ai_label: QLabel | None = None
        self.close_after_cancel = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QLabel("AI 输出纠正 — 指出问题，AI 帮你修改")
        header.setObjectName("SectionTitle")
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Vertical)

        orig_panel = QFrame()
        orig_panel.setObjectName("Card")
        orig_layout = QVBoxLayout(orig_panel)
        orig_layout.addWidget(QLabel("原始 AI 输出（只读）"))
        self.orig_viewer = QTextEdit()
        self.orig_viewer.setReadOnly(True)
        self.orig_viewer.setPlainText(ai_output[:8000])
        self.orig_viewer.setMinimumHeight(120)
        orig_layout.addWidget(self.orig_viewer)
        splitter.addWidget(orig_panel)

        chat_panel = QFrame()
        chat_panel.setObjectName("Card")
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.addWidget(QLabel("纠正对话"))

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.messages_host = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_host)
        self.messages_layout.setContentsMargins(4, 4, 4, 4)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch(1)
        self.scroll_area.setWidget(self.messages_host)
        chat_layout.addWidget(self.scroll_area, 1)

        input_box = QFrame()
        input_layout = QVBoxLayout(input_box)
        input_layout.setContentsMargins(10, 10, 10, 10)
        self.input_editor = QPlainTextEdit()
        self.input_editor.setPlaceholderText("指出需要修改的部分，例如：'第三段李四的对话不符合他的性格，请改为更冷酷的语气。'")
        self.input_editor.setMaximumHeight(96)
        input_layout.addWidget(self.input_editor)

        buttons = QHBoxLayout()
        clear_btn = QPushButton("清空对话")
        self.cancel_btn = QPushButton("停止")
        self.send_btn = QPushButton("发送纠正请求")
        clear_btn.clicked.connect(self.clear_history)
        self.cancel_btn.clicked.connect(self.cancel_reply)
        self.send_btn.clicked.connect(self.send_message)
        self.cancel_btn.setEnabled(False)
        buttons.addWidget(clear_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.send_btn)
        input_layout.addLayout(buttons)
        chat_layout.addWidget(input_box)

        splitter.addWidget(chat_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        self.chat_history.append({"role": "system", "content": self.system_prompt})
        if chapter_context.strip():
            self.chat_history.append({"role": "system", "content": f"章节上下文：\n{chapter_context[:3000]}"})
        if ai_output.strip():
            self.chat_history.append({"role": "system", "content": f"需要纠正的 AI 输出：\n{ai_output[:6000]}"})

        self.flush_timer = QTimer(self)
        self.flush_timer.setInterval(50)
        self.flush_timer.timeout.connect(self._flush_pending_text)

    def update_ai_service(self, ai_service: SimpleAIService) -> None:
        self.ai_service = ai_service

    def set_ai_output(self, ai_output: str) -> None:
        self.orig_viewer.setPlainText(ai_output[:8000])
        self.chat_history[:] = [m for m in self.chat_history if m.get("content", "").startswith("章节上下文")]
        self.chat_history.insert(0, {"role": "system", "content": self.system_prompt})
        self.chat_history.append({"role": "system", "content": f"需要纠正的 AI 输出：\n{ai_output[:6000]}"})

    def send_message(self) -> None:
        text = self.input_editor.toPlainText().strip()
        if not text or self.current_thread is not None:
            return
        self.input_editor.clear()
        self._append_bubble("user", text)
        self.chat_history.append({"role": "user", "content": text})
        self.current_ai_label = self._append_bubble("assistant", "")
        self.pending_text = ""

        messages = self.chat_history[-16:]

        self.cancel_event = Event()
        thread = QThread(self)
        worker = CorrectionChatWorker(self.ai_service, messages, self.cancel_event)
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
        base = [m for m in self.chat_history if m["role"] == "system"]
        self.chat_history = base
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def get_corrected_output(self) -> str:
        assistant_messages = [m["content"] for m in self.chat_history if m["role"] == "assistant"]
        return "\n\n".join(assistant_messages[-3:]) if assistant_messages else ""

    def _append_bubble(self, role: str, text: str) -> QLabel:
        row_widget = QWidget()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row_widget.setLayout(row)
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setObjectName("ChatUserBubble" if role == "user" else "ChatAssistantBubble")
        bubble.setMinimumWidth(120)
        bubble.setMaximumWidth(520)
        time_label = QLabel(datetime.now().strftime("%H:%M"))
        time_label.setObjectName("MetaLabel")
        box = QVBoxLayout()
        box.addWidget(bubble)
        box.addWidget(time_label, 0, Qt.AlignmentFlag.AlignRight if role == "user" else Qt.AlignmentFlag.AlignLeft)
        holder = QWidget()
        holder.setLayout(box)
        if role == "user":
            row.addStretch(1)
            row.addWidget(holder)
        else:
            row.addWidget(holder)
            row.addStretch(1)
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
            self.current_ai_label.setText(f"纠正请求失败：{message}")

    def _cancelled_reply(self) -> None:
        self._flush_pending_text()
        if self.current_ai_label is not None and not self.current_ai_label.text().strip():
            self.current_ai_label.setText("已停止。")

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

    def closeEvent(self, event: Any) -> None:
        if self.current_thread is not None:
            self.close_after_cancel = True
            self.cancel_reply()
            event.ignore()
            return
        super().closeEvent(event)
