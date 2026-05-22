from __future__ import annotations

from importlib import import_module
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from novel_app.qt.character_dialog import CharacterDetailDialog
from novel_app.qt.dialogs import info
from novel_app.qt.forms import CharacterProfileFormWidget


def _qt_app_module() -> Any:
    return import_module("novel_app.qt_app")


def build_characters_tab(window: Any) -> QWidget:
    page = window._make_drawer_page()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)
    header = QHBoxLayout()
    header.setSpacing(8)
    title = QLabel("人物卡")
    title.setObjectName("SectionTitle")
    new_btn = QPushButton("新建")
    new_btn.setObjectName("TinyButton")
    new_btn.clicked.connect(window._create_character)
    header.addWidget(title, 1)
    header.addWidget(new_btn)
    layout.addLayout(header)

    window.characters_list = QListWidget()
    window.characters_list.setObjectName("DrawerList")
    window.characters_list.setToolTip("点击人物卡打开详细信息")
    window.characters_list.itemClicked.connect(window._open_character_from_list_item)
    window.characters_list.itemActivated.connect(window._open_character_from_list_item)
    layout.addWidget(window.characters_list, 1)

    window._ensure_character_detail_dialog()
    return page


def ensure_character_detail_dialog(window: Any) -> Any:
    if window.character_detail_dialog is not None:
        return window.character_detail_dialog
    dialog = CharacterDetailDialog(window)
    dialog.setWindowTitle("人物卡详情")
    root = QVBoxLayout(dialog)
    root.setContentsMargins(14, 14, 14, 14)
    root.setSpacing(10)

    editor_row = QHBoxLayout()
    editor_row.setSpacing(12)
    portrait_box = QVBoxLayout()
    window.character_image_preview = QLabel("立绘")
    window.character_image_preview.setObjectName("ImagePreview")
    window.character_image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.character_image_preview.setMinimumSize(120, 168)
    window.character_image_preview.setMaximumSize(170, 240)
    portrait_buttons = QHBoxLayout()
    portrait_choose = QPushButton("选择")
    portrait_clear = QPushButton("清除")
    portrait_choose.clicked.connect(window._choose_character_image)
    portrait_clear.clicked.connect(window._clear_character_image)
    portrait_buttons.addWidget(portrait_choose)
    portrait_buttons.addWidget(portrait_clear)
    portrait_box.addWidget(window.character_image_preview)
    portrait_box.addLayout(portrait_buttons)
    form = QFormLayout()
    window.character_name = QLineEdit()
    window.character_role = QLineEdit()
    window.character_profile_form = CharacterProfileFormWidget()
    window.character_profile_preview = QTextEdit()
    window.character_profile_preview.setReadOnly(True)
    window.character_profile_preview.setPlaceholderText("人物卡 Markdown 预览")
    profile_panel = QWidget()
    profile_layout = QVBoxLayout(profile_panel)
    profile_layout.setContentsMargins(0, 0, 0, 0)
    profile_header = QHBoxLayout()
    profile_hint = QLabel("人物卡")
    profile_hint.setObjectName("MetaLabel")
    window.character_markdown_toggle_btn = QPushButton("Markdown")
    window.character_markdown_toggle_btn.setObjectName("TinyButton")
    window.character_markdown_toggle_btn.clicked.connect(lambda: window._toggle_markdown_view("character"))
    window.character_template_btn = QPushButton("重置人物模板")
    window.character_template_btn.clicked.connect(window._fill_character_template)
    profile_header.addWidget(profile_hint, 1)
    profile_header.addWidget(window.character_markdown_toggle_btn)
    profile_header.addWidget(window.character_template_btn)
    window.character_markdown_stack = QStackedWidget()
    window.character_markdown_stack.addWidget(window.character_profile_form)
    window.character_markdown_stack.addWidget(window.character_profile_preview)
    profile_layout.addLayout(profile_header)
    profile_layout.addWidget(window.character_markdown_stack, 1)
    window.character_name.textChanged.connect(window._on_character_identity_changed)
    window.character_role.textChanged.connect(window._on_character_identity_changed)
    window.character_profile_form.changed.connect(window._on_character_form_changed)
    form.addRow("姓名", window.character_name)
    form.addRow("角色", window.character_role)
    form.addRow("人物设定", profile_panel)
    buttons = QHBoxLayout()
    save_btn = QPushButton("保存")
    import_btn = QPushButton("导入文件")
    del_btn = QPushButton("删除")
    close_btn = QPushButton("关闭")
    del_btn.setObjectName("DangerButton")
    save_btn.clicked.connect(window._save_character)
    import_btn.clicked.connect(window._import_character_file)
    del_btn.clicked.connect(window._delete_character)
    buttons.addWidget(save_btn)
    buttons.addWidget(import_btn)
    buttons.addWidget(del_btn)
    buttons.addStretch(1)
    close_btn.clicked.connect(dialog.close)
    buttons.addWidget(close_btn)
    editor_row.addLayout(portrait_box)
    editor_row.addLayout(form, 1)
    root.addLayout(editor_row)
    root.addLayout(buttons)

    dialog.destroyed.connect(lambda _obj=None: setattr(window, "character_detail_dialog", None))
    window.character_detail_dialog = dialog
    return dialog


def refresh_characters(window: Any) -> None:
    selected_id = window.selected_character_id
    form_dirty = bool(getattr(window, "_character_form_dirty", False))
    selected_exists = any(selected_id is not None and int(item["id"]) == selected_id for item in window.characters)
    window._refresh_character_list()
    if form_dirty and selected_exists:
        window.selected_character_id = selected_id
        window._select_character_list_row(selected_id)
        return
    if selected_exists and selected_id is not None:
        if window.character_detail_dialog and window.character_detail_dialog.isVisible():
            window._load_character_form(selected_id)
        else:
            window._select_character_list_row(selected_id)
    else:
        window.selected_character_id = None
        window._select_character_list_row(None)
        if window.character_detail_dialog and window.character_detail_dialog.isVisible():
            window._clear_character_form()


def refresh_character_list(window: Any) -> None:
    ID_ROLE = _qt_app_module().ID_ROLE

    if not hasattr(window, "characters_list"):
        return
    window.characters_list.clear()
    if not window.state.selected_book_id:
        item = QListWidgetItem("请先选择一本书")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        window.characters_list.addItem(item)
        return
    if not window.characters:
        item = QListWidgetItem("暂无人物卡")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        window.characters_list.addItem(item)
        return
    for character in window.characters:
        character_id = int(character["id"])
        name = str(character.get("name", "") or "未命名人物")
        role = str(character.get("role", "") or "未设定")
        item = QListWidgetItem(f"{name} · {role}")
        item.setData(ID_ROLE, character_id)
        window.characters_list.addItem(item)
    window._select_character_list_row(window.selected_character_id)


def select_character_list_row(window: Any, character_id: int | None) -> None:
    ID_ROLE = _qt_app_module().ID_ROLE

    if not hasattr(window, "characters_list"):
        return
    window.characters_list.clearSelection()
    if character_id is None:
        return
    for index in range(window.characters_list.count()):
        item = window.characters_list.item(index)
        if item and item.data(ID_ROLE) == character_id:
            window.characters_list.setCurrentItem(item)
            return


def open_character_from_list_item(window: Any, item: QListWidgetItem) -> None:
    ID_ROLE = _qt_app_module().ID_ROLE

    character_id = item.data(ID_ROLE)
    if character_id is None:
        return
    window._open_character_detail_dialog(int(character_id))


def open_character_detail_dialog(window: Any, character_id: int) -> None:
    dialog = window._ensure_character_detail_dialog()
    if window.selected_character_id != character_id:
        if not window._confirm_character_edit_navigation():
            window._select_character_list_row(window.selected_character_id)
            return
        window._load_character_form(character_id)
    else:
        window._select_character_list_row(character_id)
    character = window.database.get_character(character_id)
    title = str(character["name"] or "人物卡详情") if character else "人物卡详情"
    dialog.setWindowTitle(f"人物卡详情 - {title}")
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def refresh_character_picker_label(window: Any) -> None:
    window._refresh_character_list()


def show_character_picker_menu(window: Any) -> None:
    if not window.state.selected_book_id:
        info(window, "提示", "请先选择一本书。")
        return
    window._refresh_character_list()


def select_character_from_picker(window: Any, character_id: int) -> None:
    window._open_character_detail_dialog(character_id)
