from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def ask_text(parent: QWidget, title: str, prompt: str, initial: str = "") -> str | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    layout.addWidget(QLabel(prompt))
    field = QLineEdit(initial)
    field.selectAll()
    layout.addWidget(field)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    field.returnPressed.connect(dialog.accept)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    value = field.text().strip()
    return value or None


def ask_multiline(parent: QWidget, title: str, prompt: str, initial: str = "") -> str | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    layout.addWidget(QLabel(prompt))
    field = QPlainTextEdit(initial)
    field.setMinimumSize(520, 260)
    layout.addWidget(field)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return field.toPlainText().strip()


def confirm(parent: QWidget, title: str, message: str, danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No if danger else QMessageBox.StandardButton.Yes)
    return box.exec() == QMessageBox.StandardButton.Yes


def info(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def error(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def ask_unsaved(parent: QWidget) -> str:
    box = QMessageBox(parent)
    box.setWindowTitle("未保存的修改")
    box.setText("当前编辑区有未保存内容，离开前要保存吗？")
    save_button = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
    discard_button = box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
    cancel_button = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(save_button)
    box.exec()
    clicked = box.clickedButton()
    if clicked == save_button:
        return "save"
    if clicked == discard_button:
        return "discard"
    if clicked == cancel_button:
        return "cancel"
    return "cancel"


class AiSettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        profiles: dict[str, dict[str, str | bool]],
        purpose_labels: list[tuple[str, str]],
        request_retries: int = 2,
        book_analysis_concurrency: int = 3,
        book_analysis_fast_extra_body: str = "",
        book_analysis_final_extra_body: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 设置")
        self.setModal(True)
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        hint = QLabel("每个功能都必须配置对应用途的 API 才能使用；未配置的用途不会回退本地 Mock。")
        hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(hint)

        self.fields: dict[str, dict[str, QCheckBox | QLineEdit]] = {}
        self.unified_api_key = QLineEdit()
        self.unified_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.unified_base_url = QLineEdit()
        self.unified_model = QLineEdit()
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            if not self.unified_api_key.text() and str(profile.get("api_key", "")).strip():
                self.unified_api_key.setText(str(profile.get("api_key", "")))
            if not self.unified_base_url.text() and str(profile.get("base_url", "")).strip():
                self.unified_base_url.setText(str(profile.get("base_url", "")))
            if not self.unified_model.text() and str(profile.get("model", "")).strip():
                self.unified_model.setText(str(profile.get("model", "")))
        unified_box = QWidget()
        unified_layout = QVBoxLayout(unified_box)
        unified_layout.setContentsMargins(0, 0, 0, 0)
        unified_layout.setSpacing(8)
        unified_form = QFormLayout()
        unified_form.addRow("统一 API Key", self.unified_api_key)
        unified_form.addRow("统一 Base URL", self.unified_base_url)
        unified_form.addRow("统一模型", self.unified_model)
        self.request_retries = QSpinBox()
        self.request_retries.setRange(0, 5)
        self.request_retries.setValue(max(0, min(5, int(request_retries))))
        self.request_retries.setToolTip("AI 请求失败后的重试次数；0 表示不重试。")
        unified_form.addRow("API 失败重试次数", self.request_retries)
        self.book_analysis_concurrency = QSpinBox()
        self.book_analysis_concurrency.setRange(1, 8)
        self.book_analysis_concurrency.setValue(max(1, min(8, int(book_analysis_concurrency))))
        self.book_analysis_concurrency.setToolTip("全书分析一级/二级同层并发请求数。")
        unified_form.addRow("全书分析并发请求数", self.book_analysis_concurrency)
        self.book_analysis_fast_extra_body = QPlainTextEdit(book_analysis_fast_extra_body)
        self.book_analysis_fast_extra_body.setMinimumHeight(66)
        self.book_analysis_fast_extra_body.setToolTip("一级/二级分析请求体额外 JSON 对象。")
        unified_form.addRow("一级/二级额外请求参数 JSON", self.book_analysis_fast_extra_body)
        self.book_analysis_final_extra_body = QPlainTextEdit(book_analysis_final_extra_body)
        self.book_analysis_final_extra_body.setMinimumHeight(66)
        self.book_analysis_final_extra_body.setToolTip("三级终审请求体额外 JSON 对象。")
        unified_form.addRow("三级额外请求参数 JSON", self.book_analysis_final_extra_body)
        unified_layout.addLayout(unified_form)
        unified_actions = QHBoxLayout()
        apply_all = QPushButton("一键覆盖全部用途")
        apply_all.clicked.connect(self._apply_unified_profile)
        unified_actions.addStretch(1)
        unified_actions.addWidget(apply_all)
        unified_layout.addLayout(unified_actions)
        layout.addWidget(unified_box)

        tabs = QTabWidget()
        for purpose, label in purpose_labels:
            profile = profiles.get(purpose, {})
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(14, 14, 14, 14)
            page_layout.setSpacing(12)
            enabled_box = QCheckBox("启用该用途")
            enabled_box.setChecked(bool(profile.get("remote_enabled", False)))
            page_layout.addWidget(enabled_box)

            form = QFormLayout()
            api_key_field = QLineEdit(str(profile.get("api_key", "")))
            api_key_field.setEchoMode(QLineEdit.EchoMode.Password)
            base_url_field = QLineEdit(str(profile.get("base_url", "")))
            model_field = QLineEdit(str(profile.get("model", "")))
            form.addRow("API Key", api_key_field)
            form.addRow("Base URL", base_url_field)
            form.addRow("模型", model_field)
            page_layout.addLayout(form)
            page_layout.addStretch(1)
            tabs.addTab(page, label)
            self.fields[purpose] = {
                "remote_enabled": enabled_box,
                "api_key": api_key_field,
                "base_url": base_url_field,
                "model": model_field,
            }
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button:
            save_button.setText("保存")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_unified_profile(self) -> None:
        api_key = self.unified_api_key.text().strip()
        base_url = self.unified_base_url.text().strip()
        model = self.unified_model.text().strip()
        for fields in self.fields.values():
            enabled_box = fields["remote_enabled"]
            api_key_field = fields["api_key"]
            base_url_field = fields["base_url"]
            model_field = fields["model"]
            if isinstance(enabled_box, QCheckBox):
                enabled_box.setChecked(bool(api_key and model))
            if isinstance(api_key_field, QLineEdit):
                api_key_field.setText(api_key)
            if isinstance(base_url_field, QLineEdit):
                base_url_field.setText(base_url)
            if isinstance(model_field, QLineEdit):
                model_field.setText(model)

    def values(self) -> dict[str, Any]:
        profiles: dict[str, dict[str, str | bool]] = {}
        for purpose, fields in self.fields.items():
            enabled_box = fields["remote_enabled"]
            api_key_field = fields["api_key"]
            base_url_field = fields["base_url"]
            model_field = fields["model"]
            profiles[purpose] = {
                "remote_enabled": enabled_box.isChecked() if isinstance(enabled_box, QCheckBox) else False,
                "api_key": api_key_field.text().strip() if isinstance(api_key_field, QLineEdit) else "",
                "base_url": base_url_field.text().strip() if isinstance(base_url_field, QLineEdit) else "",
                "model": model_field.text().strip() if isinstance(model_field, QLineEdit) else "",
            }
        return {
            "profiles": profiles,
            "request_retries": self.request_retries.value(),
            "book_analysis_concurrency": self.book_analysis_concurrency.value(),
            "book_analysis_fast_extra_body": self.book_analysis_fast_extra_body.toPlainText().strip(),
            "book_analysis_final_extra_body": self.book_analysis_final_extra_body.toPlainText().strip(),
        }


class PromptSettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        entries: list[dict[str, str]],
        values: dict[str, str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Agent 与提示词配置")
        self.setModal(True)
        self.resize(980, 680)
        self.entries = [dict(item) for item in entries if item.get("key")]
        self.values = {str(item["key"]): str(values.get(str(item["key"]), item.get("default", ""))) for item in self.entries}
        self.current_key = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        hint = QLabel("可自定义所有内置 Agent 与提示词。默认已填入当前版本提示词；模板中的 {变量名} 会在运行时自动替换。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.prompt_list = QListWidget()
        self.prompt_list.setMinimumWidth(260)
        for item in self.entries:
            label = f"{item.get('category', '')} / {item.get('label', item['key'])}"
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, str(item["key"]))
            self.prompt_list.addItem(row)
        splitter.addWidget(self.prompt_list)

        editor_host = QWidget()
        editor_layout = QVBoxLayout(editor_host)
        editor_layout.setContentsMargins(10, 0, 0, 0)
        self.title_label = QLabel("")
        self.title_label.setObjectName("SectionTitle")
        self.placeholder_label = QLabel("")
        self.placeholder_label.setWordWrap(True)
        self.editor = QPlainTextEdit()
        self.editor.setMinimumHeight(420)
        editor_layout.addWidget(self.title_label)
        editor_layout.addWidget(self.placeholder_label)
        editor_layout.addWidget(self.editor, 1)

        actions = QHBoxLayout()
        reset_current = QPushButton("恢复当前默认")
        reset_all = QPushButton("全部恢复默认")
        reset_current.clicked.connect(self._reset_current)
        reset_all.clicked.connect(self._reset_all)
        actions.addStretch(1)
        actions.addWidget(reset_current)
        actions.addWidget(reset_all)
        editor_layout.addLayout(actions)
        splitter.addWidget(editor_host)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button:
            save_button.setText("保存")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.prompt_list.currentItemChanged.connect(self._on_current_changed)
        if self.prompt_list.count():
            self.prompt_list.setCurrentRow(0)

    def _entry_by_key(self, key: str) -> dict[str, str]:
        for item in self.entries:
            if str(item.get("key", "")) == key:
                return item
        return {}

    def _save_current_text(self) -> None:
        if self.current_key:
            self.values[self.current_key] = self.editor.toPlainText()

    def _on_current_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self._save_current_text()
        if current is None:
            self.current_key = ""
            self.editor.clear()
            return
        key = str(current.data(Qt.ItemDataRole.UserRole) or "")
        self.current_key = key
        entry = self._entry_by_key(key)
        self.title_label.setText(str(entry.get("label", key)))
        placeholders = str(entry.get("placeholders", "")).strip()
        if placeholders:
            self.placeholder_label.setText(f"可用变量：{placeholders}")
        else:
            self.placeholder_label.setText("此提示词不需要变量。")
        self.editor.setPlainText(str(self.values.get(key, entry.get("default", ""))))

    def _reset_current(self) -> None:
        if not self.current_key:
            return
        entry = self._entry_by_key(self.current_key)
        self.editor.setPlainText(str(entry.get("default", "")))

    def _reset_all(self) -> None:
        for item in self.entries:
            self.values[str(item["key"])] = str(item.get("default", ""))
        if self.current_key:
            self.editor.setPlainText(self.values.get(self.current_key, ""))

    def accept(self) -> None:  # noqa: D102
        self._save_current_text()
        super().accept()

    def result_values(self) -> dict[str, str]:
        self._save_current_text()
        return dict(self.values)
