from __future__ import annotations

from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from novel_app.structured_templates import (
    BOOK_OUTLINE_FORM_SCHEMA,
    BOOK_OUTLINE_VOLUME_PLAN_FIELDS,
    WORLD_FORM_SCHEMA,
    book_outline_form_defaults,
    book_outline_form_to_markdown,
    character_profile_form_defaults,
    character_profile_form_to_markdown,
    character_profile_schema_for_role,
    normalize_book_outline_form,
    normalize_character_profile_form,
    normalize_world_form,
    world_form_defaults,
    world_form_to_markdown,
)


class BookOutlineFormWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._title = ""
        self._volume_specs: list[dict[str, Any]] = []
        self._field_widgets: dict[str, dict[str, Any]] = {}
        self._volume_plan_widgets: list[dict[str, Any]] = []
        self._supplement_rows: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        self.form_layout = QVBoxLayout(inner)
        self.form_layout.setContentsMargins(4, 4, 12, 12)
        self.form_layout.setSpacing(10)

        for section in BOOK_OUTLINE_FORM_SCHEMA:
            title = QLabel(str(section.get("title", "")))
            title.setObjectName("SectionTitle")
            self.form_layout.addWidget(title)
            if str(section.get("id", "")) == "volume_plan":
                self.volume_plan_layout = QVBoxLayout()
                self.volume_plan_layout.setSpacing(8)
                self.form_layout.addLayout(self.volume_plan_layout)
            for item in section.get("items", []):
                if isinstance(item, dict):
                    self._add_schema_item(item)

        supplements_header = QHBoxLayout()
        supplements_label = QLabel("补充内容")
        supplements_label.setObjectName("SectionTitle")
        add_supplement = QPushButton("新增补充")
        add_supplement.setObjectName("TinyButton")
        add_supplement.clicked.connect(lambda: self._add_supplement_row({"title": "用户补充", "content": ""}, emit=True))
        supplements_header.addWidget(supplements_label, 1)
        supplements_header.addWidget(add_supplement)
        self.form_layout.addLayout(supplements_header)
        self.supplements_layout = QVBoxLayout()
        self.supplements_layout.setSpacing(8)
        self.form_layout.addLayout(self.supplements_layout)
        self.form_layout.addStretch(1)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

    def _add_schema_item(self, item: dict[str, Any]) -> None:
        field_id = str(item.get("id", ""))
        field_type = str(item.get("type", "text"))
        label_text = str(item.get("label", ""))
        if not field_id:
            return
        if field_type == "checkbox":
            checkbox = QCheckBox(label_text)
            checkbox.toggled.connect(lambda _checked=False: self._emit_changed())
            self.form_layout.addWidget(checkbox)
            self._field_widgets[field_id] = {"type": field_type, "checkbox": checkbox}
            return
        if field_type == "checkbox_text":
            row = QHBoxLayout()
            checkbox = QCheckBox(label_text)
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("自定义")
            checkbox.toggled.connect(lambda _checked=False: self._emit_changed())
            line_edit.textChanged.connect(lambda _text="", cb=checkbox: self._on_checkbox_text_changed(cb))
            row.addWidget(checkbox)
            row.addWidget(line_edit, 1)
            self.form_layout.addLayout(row)
            self._field_widgets[field_id] = {"type": field_type, "checkbox": checkbox, "line": line_edit}
            return
        if field_type == "multiline":
            label = QLabel(label_text)
            label.setObjectName("MetaLabel")
            editor = QPlainTextEdit()
            editor.setPlaceholderText(str(item.get("placeholder", "")))
            editor.setMinimumHeight(108)
            editor.textChanged.connect(self._emit_changed)
            self.form_layout.addWidget(label)
            self.form_layout.addWidget(editor)
            self._field_widgets[field_id] = {"type": field_type, "editor": editor}
            return

        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setMinimumWidth(190)
        line_edit = QLineEdit()
        line_edit.textChanged.connect(lambda _text="": self._emit_changed())
        row.addWidget(label)
        row.addWidget(line_edit, 1)
        self.form_layout.addLayout(row)
        self._field_widgets[field_id] = {"type": "text", "line": line_edit}

    def _clear_volume_plan_rows(self) -> None:
        self._volume_plan_widgets = []
        layout = getattr(self, "volume_plan_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_nested_layout(child_layout)

    def _clear_nested_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_nested_layout(child_layout)

    def _build_volume_plan_rows(self, volume_plans: list[Any]) -> None:
        self._clear_volume_plan_rows()
        layout = getattr(self, "volume_plan_layout", None)
        if layout is None:
            return
        if not volume_plans:
            hint = QLabel("当前书籍尚未创建分卷。")
            hint.setObjectName("MetaLabel")
            layout.addWidget(hint)
            return
        for index, plan in enumerate(volume_plans, start=1):
            if not isinstance(plan, dict):
                continue
            self._add_volume_plan_row(index, plan)

    def _add_volume_plan_row(self, index: int, plan: dict[str, Any]) -> None:
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(6)
        volume_title = str(plan.get("volume_title", "") or "").strip()
        heading = QLabel(f"第{index}卷规划" + (f"：{volume_title}" if volume_title else ""))
        heading.setObjectName("MetaLabel")
        panel_layout.addWidget(heading)

        field_widgets: dict[str, QLineEdit] = {}
        plan_fields = plan.get("fields", {})
        if not isinstance(plan_fields, dict):
            plan_fields = {}
        for plan_item in BOOK_OUTLINE_VOLUME_PLAN_FIELDS:
            row = QHBoxLayout()
            label = QLabel(str(plan_item.get("label", "")))
            label.setMinimumWidth(110)
            line_edit = QLineEdit()
            plan_field = plan_fields.get(str(plan_item["id"]), {})
            if isinstance(plan_field, dict):
                line_edit.setText(str(plan_field.get("value", "") or ""))
            line_edit.textChanged.connect(lambda _text="": self._emit_changed())
            row.addWidget(label)
            row.addWidget(line_edit, 1)
            panel_layout.addLayout(row)
            field_widgets[str(plan_item["id"])] = line_edit

        self.volume_plan_layout.addWidget(panel)
        self._volume_plan_widgets.append(
            {
                "volume_id": str(plan.get("volume_id", "")),
                "volume_title": volume_title,
                "sort_order": int(plan.get("sort_order", index) or index),
                "fields": field_widgets,
            }
        )

    def _on_checkbox_text_changed(self, checkbox: QCheckBox) -> None:
        if not self._loading and not checkbox.isChecked():
            checkbox.blockSignals(True)
            checkbox.setChecked(True)
            checkbox.blockSignals(False)
        self._emit_changed()

    def _add_supplement_row(self, supplement: dict[str, Any], *, emit: bool = False) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        title_row = QHBoxLayout()
        title_field = QLineEdit(str(supplement.get("title", "") or "补充"))
        remove_button = QPushButton("删除")
        remove_button.setObjectName("TinyButton")
        content_editor = QPlainTextEdit()
        content_editor.setMinimumHeight(100)
        content_editor.setPlainText(str(supplement.get("content", "") or ""))
        title_field.textChanged.connect(lambda _text="": self._emit_changed())
        content_editor.textChanged.connect(self._emit_changed)
        title_row.addWidget(title_field, 1)
        title_row.addWidget(remove_button)
        layout.addLayout(title_row)
        layout.addWidget(content_editor)
        row = {"panel": panel, "title": title_field, "content": content_editor}
        remove_button.clicked.connect(lambda _checked=False, row=row: self._remove_supplement_row(row))
        self._supplement_rows.append(row)
        self.supplements_layout.addWidget(panel)
        if emit:
            self._emit_changed()

    def _remove_supplement_row(self, row: dict[str, Any]) -> None:
        if row not in self._supplement_rows:
            return
        self._supplement_rows.remove(row)
        panel = row.get("panel")
        if isinstance(panel, QWidget):
            panel.setParent(None)
            panel.deleteLater()
        self._emit_changed()

    def set_data(self, data: dict[str, Any] | None, title: str = "", volume_specs: list[Any] | None = None) -> None:
        self._loading = True
        self._title = str(title or "")
        self._volume_specs = [dict(item) for item in volume_specs] if isinstance(volume_specs, list) else []
        normalized = normalize_book_outline_form(data, self._title, self._volume_specs)
        fields = normalized.get("fields", {})
        try:
            for field_id, widgets in self._field_widgets.items():
                field = fields.get(field_id, {})
                field_type = str(widgets.get("type", "text"))
                if field_type == "checkbox":
                    widgets["checkbox"].setChecked(bool(field.get("checked", False)))
                elif field_type == "checkbox_text":
                    widgets["checkbox"].setChecked(bool(field.get("checked", False)))
                    widgets["line"].setText(str(field.get("value", "") or ""))
                elif field_type == "multiline":
                    widgets["editor"].setPlainText(str(field.get("value", "") or ""))
                else:
                    widgets["line"].setText(str(field.get("value", "") or ""))
            self._build_volume_plan_rows(normalized.get("volume_plans", []))
            for row in list(self._supplement_rows):
                self._remove_supplement_row(row)
            for supplement in normalized.get("supplements", []):
                if isinstance(supplement, dict):
                    self._add_supplement_row(supplement)
        finally:
            self._loading = False

    def to_data(self, title: str = "") -> dict[str, Any]:
        data = book_outline_form_defaults(title or self._title, self._volume_specs)
        fields = data["fields"]
        for field_id, widgets in self._field_widgets.items():
            field_type = str(widgets.get("type", "text"))
            if field_type == "checkbox":
                fields[field_id]["checked"] = widgets["checkbox"].isChecked()
            elif field_type == "checkbox_text":
                fields[field_id]["checked"] = widgets["checkbox"].isChecked()
                fields[field_id]["value"] = widgets["line"].text().strip()
            elif field_type == "multiline":
                fields[field_id]["value"] = widgets["editor"].toPlainText().strip()
            else:
                fields[field_id]["value"] = widgets["line"].text().strip()
        volume_plans: list[dict[str, Any]] = []
        for plan in self._volume_plan_widgets:
            plan_fields: dict[str, dict[str, str]] = {}
            for plan_item in BOOK_OUTLINE_VOLUME_PLAN_FIELDS:
                field_id = str(plan_item["id"])
                line_edit = plan.get("fields", {}).get(field_id)
                plan_fields[field_id] = {"value": line_edit.text().strip() if isinstance(line_edit, QLineEdit) else ""}
            volume_plans.append(
                {
                    "volume_id": str(plan.get("volume_id", "")),
                    "volume_title": str(plan.get("volume_title", "") or ""),
                    "sort_order": int(plan.get("sort_order", len(volume_plans) + 1) or len(volume_plans) + 1),
                    "fields": plan_fields,
                }
            )
        data["volume_plans"] = volume_plans
        supplements: list[dict[str, str]] = []
        for row in self._supplement_rows:
            title_text = row["title"].text().strip() or "补充"
            content = row["content"].toPlainText().strip()
            if content:
                supplements.append({"title": title_text, "content": content})
        data["supplements"] = supplements
        return normalize_book_outline_form(data, title or self._title, self._volume_specs)

    def to_markdown(self, title: str = "") -> str:
        return book_outline_form_to_markdown(self.to_data(title or self._title), title or self._title, self._volume_specs)

    def _emit_changed(self) -> None:
        if not self._loading:
            self.changed.emit()


class CharacterProfileFormWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._schema_key = ""
        self._name = ""
        self._role = ""
        self._field_widgets: dict[str, dict[str, Any]] = {}
        self._supplement_rows: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        self.form_layout = QVBoxLayout(self.inner)
        self.form_layout.setContentsMargins(4, 4, 12, 12)
        self.form_layout.setSpacing(10)
        scroll.setWidget(self.inner)
        root.addWidget(scroll, 1)

    def _clear_form_layout(self) -> None:
        self._field_widgets = {}
        self._supplement_rows = []
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_nested_layout(child_layout)

    def _clear_nested_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_nested_layout(child_layout)

    def _rebuild_schema(self, role: str, schema_key: str) -> None:
        self._clear_form_layout()
        schema = character_profile_schema_for_role(role, schema_key)
        for section in schema:
            title = QLabel(str(section.get("title", "")))
            title.setObjectName("SectionTitle")
            self.form_layout.addWidget(title)
            for item in section.get("items", []):
                if isinstance(item, dict):
                    self._add_schema_item(item)

        supplements_header = QHBoxLayout()
        supplements_label = QLabel("补充内容")
        supplements_label.setObjectName("SectionTitle")
        add_supplement = QPushButton("新增补充")
        add_supplement.setObjectName("TinyButton")
        add_supplement.clicked.connect(lambda: self._add_supplement_row({"title": "用户补充", "content": ""}, emit=True))
        supplements_header.addWidget(supplements_label, 1)
        supplements_header.addWidget(add_supplement)
        self.form_layout.addLayout(supplements_header)
        self.supplements_layout = QVBoxLayout()
        self.supplements_layout.setSpacing(8)
        self.form_layout.addLayout(self.supplements_layout)
        self.form_layout.addStretch(1)

    def _add_schema_item(self, item: dict[str, Any]) -> None:
        field_id = str(item.get("id", ""))
        field_type = str(item.get("type", "text"))
        label_text = str(item.get("label", ""))
        if not field_id:
            return
        if field_type == "checkbox":
            checkbox = QCheckBox(label_text)
            checkbox.toggled.connect(lambda _checked=False: self._emit_changed())
            self.form_layout.addWidget(checkbox)
            self._field_widgets[field_id] = {"type": field_type, "checkbox": checkbox}
            return
        if field_type == "checkbox_text":
            row = QHBoxLayout()
            checkbox = QCheckBox(label_text)
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("自定义")
            checkbox.toggled.connect(lambda _checked=False: self._emit_changed())
            line_edit.textChanged.connect(lambda _text="", cb=checkbox: self._on_checkbox_text_changed(cb))
            row.addWidget(checkbox)
            row.addWidget(line_edit, 1)
            self.form_layout.addLayout(row)
            self._field_widgets[field_id] = {"type": field_type, "checkbox": checkbox, "line": line_edit}
            return
        if field_type == "multiline":
            label = QLabel(label_text)
            label.setObjectName("MetaLabel")
            editor = QPlainTextEdit()
            editor.setPlaceholderText(str(item.get("placeholder", "")))
            editor.setMinimumHeight(108)
            editor.textChanged.connect(self._emit_changed)
            self.form_layout.addWidget(label)
            self.form_layout.addWidget(editor)
            self._field_widgets[field_id] = {"type": field_type, "editor": editor}
            return

        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setMinimumWidth(190)
        line_edit = QLineEdit()
        line_edit.textChanged.connect(lambda _text="": self._emit_changed())
        row.addWidget(label)
        row.addWidget(line_edit, 1)
        self.form_layout.addLayout(row)
        self._field_widgets[field_id] = {"type": "text", "line": line_edit}

    def _on_checkbox_text_changed(self, checkbox: QCheckBox) -> None:
        if not self._loading and not checkbox.isChecked():
            checkbox.blockSignals(True)
            checkbox.setChecked(True)
            checkbox.blockSignals(False)
        self._emit_changed()

    def _add_supplement_row(self, supplement: dict[str, Any], *, emit: bool = False) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        title_row = QHBoxLayout()
        title_field = QLineEdit(str(supplement.get("title", "") or "补充"))
        remove_button = QPushButton("删除")
        remove_button.setObjectName("TinyButton")
        content_editor = QPlainTextEdit()
        content_editor.setMinimumHeight(100)
        content_editor.setPlainText(str(supplement.get("content", "") or ""))
        title_field.textChanged.connect(lambda _text="": self._emit_changed())
        content_editor.textChanged.connect(self._emit_changed)
        title_row.addWidget(title_field, 1)
        title_row.addWidget(remove_button)
        layout.addLayout(title_row)
        layout.addWidget(content_editor)
        row = {"panel": panel, "title": title_field, "content": content_editor}
        remove_button.clicked.connect(lambda _checked=False, row=row: self._remove_supplement_row(row))
        self._supplement_rows.append(row)
        self.supplements_layout.addWidget(panel)
        if emit:
            self._emit_changed()

    def _remove_supplement_row(self, row: dict[str, Any]) -> None:
        if row not in self._supplement_rows:
            return
        self._supplement_rows.remove(row)
        panel = row.get("panel")
        if isinstance(panel, QWidget):
            panel.setParent(None)
            panel.deleteLater()
        self._emit_changed()

    def set_data(self, data: dict[str, Any] | None, name: str = "", role: str = "") -> None:
        self._loading = True
        self._name = str(name or "")
        self._role = str(role or "")
        normalized = normalize_character_profile_form(data, self._name, self._role)
        schema_key = str(normalized.get("schema", ""))
        try:
            if schema_key != self._schema_key:
                self._schema_key = schema_key
                self._rebuild_schema(self._role, self._schema_key)
            fields = normalized.get("fields", {})
            for field_id, widgets in self._field_widgets.items():
                field = fields.get(field_id, {})
                field_type = str(widgets.get("type", "text"))
                if field_type == "checkbox":
                    widgets["checkbox"].setChecked(bool(field.get("checked", False)))
                elif field_type == "checkbox_text":
                    widgets["checkbox"].setChecked(bool(field.get("checked", False)))
                    widgets["line"].setText(str(field.get("value", "") or ""))
                elif field_type == "multiline":
                    widgets["editor"].setPlainText(str(field.get("value", "") or ""))
                else:
                    widgets["line"].setText(str(field.get("value", "") or ""))
            for row in list(self._supplement_rows):
                self._remove_supplement_row(row)
            for supplement in normalized.get("supplements", []):
                if isinstance(supplement, dict):
                    self._add_supplement_row(supplement)
        finally:
            self._loading = False

    def to_data(self, name: str = "", role: str = "") -> dict[str, Any]:
        name = str(name or self._name)
        role = str(role or self._role)
        data = character_profile_form_defaults(name, role, self._schema_key)
        fields = data["fields"]
        for field_id, widgets in self._field_widgets.items():
            if field_id not in fields:
                continue
            field_type = str(widgets.get("type", "text"))
            if field_type == "checkbox":
                fields[field_id]["checked"] = widgets["checkbox"].isChecked()
            elif field_type == "checkbox_text":
                fields[field_id]["checked"] = widgets["checkbox"].isChecked()
                fields[field_id]["value"] = widgets["line"].text().strip()
            elif field_type == "multiline":
                fields[field_id]["value"] = widgets["editor"].toPlainText().strip()
            else:
                fields[field_id]["value"] = widgets["line"].text().strip()
        supplements: list[dict[str, str]] = []
        for row in self._supplement_rows:
            title_text = row["title"].text().strip() or "补充"
            content = row["content"].toPlainText().strip()
            if content:
                supplements.append({"title": title_text, "content": content})
        data["supplements"] = supplements
        return normalize_character_profile_form(data, name, role, self._schema_key)

    def to_markdown(self, name: str = "", role: str = "") -> str:
        name = str(name or self._name)
        role = str(role or self._role)
        return character_profile_form_to_markdown(self.to_data(name, role), name, role)

    def refresh_identity(self, name: str, role: str) -> None:
        data = self.to_data(name, role)
        normalized = normalize_character_profile_form(data, name, role)
        if str(normalized.get("schema", "")) != self._schema_key:
            self.set_data(normalized, name, role)
        else:
            self._name = str(name or "")
            self._role = str(role or "")
        self._emit_changed()

    def _emit_changed(self) -> None:
        if not self._loading:
            self.changed.emit()


class WorldFormWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._field_widgets: dict[str, dict[str, Any]] = {}
        self._supplement_rows: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        self.form_layout = QVBoxLayout(inner)
        self.form_layout.setContentsMargins(4, 4, 12, 12)
        self.form_layout.setSpacing(10)

        for section in WORLD_FORM_SCHEMA:
            title = QLabel(str(section.get("title", "")))
            title.setObjectName("SectionTitle")
            self.form_layout.addWidget(title)
            for item in section.get("items", []):
                if isinstance(item, dict):
                    self._add_schema_item(item)

        supplements_header = QHBoxLayout()
        supplements_label = QLabel("补充内容")
        supplements_label.setObjectName("SectionTitle")
        add_supplement = QPushButton("新增补充")
        add_supplement.setObjectName("TinyButton")
        add_supplement.clicked.connect(lambda: self._add_supplement_row({"title": "用户补充", "content": ""}, emit=True))
        supplements_header.addWidget(supplements_label, 1)
        supplements_header.addWidget(add_supplement)
        self.form_layout.addLayout(supplements_header)
        self.supplements_layout = QVBoxLayout()
        self.supplements_layout.setSpacing(8)
        self.form_layout.addLayout(self.supplements_layout)
        self.form_layout.addStretch(1)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

    def _add_schema_item(self, item: dict[str, Any]) -> None:
        field_id = str(item.get("id", ""))
        field_type = str(item.get("type", "text"))
        label_text = str(item.get("label", ""))
        if not field_id:
            return
        if field_type == "checkbox":
            checkbox = QCheckBox(label_text)
            checkbox.toggled.connect(lambda _checked=False: self._emit_changed())
            self.form_layout.addWidget(checkbox)
            self._field_widgets[field_id] = {"type": field_type, "checkbox": checkbox}
            return
        if field_type == "checkbox_text":
            row = QHBoxLayout()
            checkbox = QCheckBox(label_text)
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("自定义")
            checkbox.toggled.connect(lambda _checked=False: self._emit_changed())
            line_edit.textChanged.connect(lambda _text="", cb=checkbox: self._on_checkbox_text_changed(cb))
            row.addWidget(checkbox)
            row.addWidget(line_edit, 1)
            self.form_layout.addLayout(row)
            self._field_widgets[field_id] = {"type": field_type, "checkbox": checkbox, "line": line_edit}
            return
        if field_type == "multiline":
            label = QLabel(label_text)
            label.setObjectName("MetaLabel")
            editor = QPlainTextEdit()
            editor.setPlaceholderText(str(item.get("placeholder", "")))
            editor.setMinimumHeight(124)
            editor.textChanged.connect(self._emit_changed)
            self.form_layout.addWidget(label)
            self.form_layout.addWidget(editor)
            self._field_widgets[field_id] = {"type": field_type, "editor": editor}
            return

        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setMinimumWidth(150)
        line_edit = QLineEdit()
        line_edit.textChanged.connect(lambda _text="": self._emit_changed())
        row.addWidget(label)
        row.addWidget(line_edit, 1)
        self.form_layout.addLayout(row)
        self._field_widgets[field_id] = {"type": "text", "line": line_edit}

    def _on_checkbox_text_changed(self, checkbox: QCheckBox) -> None:
        if not self._loading and not checkbox.isChecked():
            checkbox.blockSignals(True)
            checkbox.setChecked(True)
            checkbox.blockSignals(False)
        self._emit_changed()

    def _add_supplement_row(self, supplement: dict[str, Any], *, emit: bool = False) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        title_row = QHBoxLayout()
        title_field = QLineEdit(str(supplement.get("title", "") or "补充"))
        remove_button = QPushButton("删除")
        remove_button.setObjectName("TinyButton")
        content_editor = QPlainTextEdit()
        content_editor.setMinimumHeight(100)
        content_editor.setPlainText(str(supplement.get("content", "") or ""))
        title_field.textChanged.connect(lambda _text="": self._emit_changed())
        content_editor.textChanged.connect(self._emit_changed)
        title_row.addWidget(title_field, 1)
        title_row.addWidget(remove_button)
        layout.addLayout(title_row)
        layout.addWidget(content_editor)
        row = {"panel": panel, "title": title_field, "content": content_editor}
        remove_button.clicked.connect(lambda _checked=False, row=row: self._remove_supplement_row(row))
        self._supplement_rows.append(row)
        self.supplements_layout.addWidget(panel)
        if emit:
            self._emit_changed()

    def _remove_supplement_row(self, row: dict[str, Any]) -> None:
        if row not in self._supplement_rows:
            return
        self._supplement_rows.remove(row)
        panel = row.get("panel")
        if isinstance(panel, QWidget):
            panel.setParent(None)
            panel.deleteLater()
        self._emit_changed()

    def set_data(self, data: dict[str, Any] | None) -> None:
        self._loading = True
        normalized = normalize_world_form(data)
        fields = normalized.get("fields", {})
        try:
            for field_id, widgets in self._field_widgets.items():
                field = fields.get(field_id, {})
                field_type = str(widgets.get("type", "text"))
                if field_type == "checkbox":
                    widgets["checkbox"].setChecked(bool(field.get("checked", False)))
                elif field_type == "checkbox_text":
                    widgets["checkbox"].setChecked(bool(field.get("checked", False)))
                    widgets["line"].setText(str(field.get("value", "") or ""))
                elif field_type == "multiline":
                    widgets["editor"].setPlainText(str(field.get("value", "") or ""))
                else:
                    widgets["line"].setText(str(field.get("value", "") or ""))
            for row in list(self._supplement_rows):
                self._remove_supplement_row(row)
            for supplement in normalized.get("supplements", []):
                if isinstance(supplement, dict):
                    self._add_supplement_row(supplement)
        finally:
            self._loading = False

    def to_data(self) -> dict[str, Any]:
        data = world_form_defaults()
        fields = data["fields"]
        for field_id, widgets in self._field_widgets.items():
            field_type = str(widgets.get("type", "text"))
            if field_type == "checkbox":
                fields[field_id]["checked"] = widgets["checkbox"].isChecked()
            elif field_type == "checkbox_text":
                fields[field_id]["checked"] = widgets["checkbox"].isChecked()
                fields[field_id]["value"] = widgets["line"].text().strip()
            elif field_type == "multiline":
                fields[field_id]["value"] = widgets["editor"].toPlainText().strip()
            else:
                fields[field_id]["value"] = widgets["line"].text().strip()
        supplements: list[dict[str, str]] = []
        for row in self._supplement_rows:
            title_text = row["title"].text().strip() or "补充"
            content = row["content"].toPlainText().strip()
            if content:
                supplements.append({"title": title_text, "content": content})
        data["supplements"] = supplements
        return normalize_world_form(data)

    def to_markdown(self) -> str:
        return world_form_to_markdown(self.to_data())

    def _emit_changed(self) -> None:
        if not self._loading:
            self.changed.emit()
