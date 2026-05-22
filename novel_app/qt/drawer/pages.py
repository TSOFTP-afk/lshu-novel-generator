from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QListWidgetItem, QWidget

from novel_app.qt.drawer import characters, outline, overview, review, shortcuts, skills, tasks, world


def build_outline_tab(window: Any) -> QWidget:
    return outline.build_outline_tab(window)


def build_overview_tab(window: Any) -> QWidget:
    return overview.build_overview_tab(window)


def build_shortcuts_tab(window: Any) -> QWidget:
    return shortcuts.build_shortcuts_tab(window)


def build_characters_tab(window: Any) -> QWidget:
    return characters.build_characters_tab(window)


def ensure_character_detail_dialog(window: Any) -> Any:
    return characters.ensure_character_detail_dialog(window)


def build_world_tab(window: Any) -> QWidget:
    return world.build_world_tab(window)


def build_skills_tab(window: Any) -> QWidget:
    return skills.build_skills_tab(window)


def build_review_tab(window: Any) -> QWidget:
    return review.build_review_tab(window)


def build_task_tab(window: Any) -> QWidget:
    return tasks.build_task_tab(window)


def refresh_overview(window: Any) -> None:
    return overview.refresh_overview(window)


def refresh_characters(window: Any) -> None:
    return characters.refresh_characters(window)


def refresh_character_list(window: Any) -> None:
    return characters.refresh_character_list(window)


def select_character_list_row(window: Any, character_id: int | None) -> None:
    return characters.select_character_list_row(window, character_id)


def open_character_from_list_item(window: Any, item: QListWidgetItem) -> None:
    return characters.open_character_from_list_item(window, item)


def open_character_detail_dialog(window: Any, character_id: int) -> None:
    return characters.open_character_detail_dialog(window, character_id)


def refresh_character_picker_label(window: Any) -> None:
    return characters.refresh_character_picker_label(window)


def show_character_picker_menu(window: Any) -> None:
    return characters.show_character_picker_menu(window)


def select_character_from_picker(window: Any, character_id: int) -> None:
    return characters.select_character_from_picker(window, character_id)


def refresh_world(window: Any) -> None:
    return world.refresh_world(window)


def refresh_skills(window: Any) -> None:
    return skills.refresh_skills(window)


def on_enabled_skill_selected(window: Any, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
    return skills.on_enabled_skill_selected(window, current, _previous)


def refresh_review_tab(window: Any) -> None:
    return review.refresh_review_tab(window)


def on_review_run_selected(window: Any, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
    return review.on_review_run_selected(window, current, _previous)


def render_review_run_detail(window: Any, run_id: int) -> None:
    return review.render_review_run_detail(window, run_id)


def selected_review_run(window: Any) -> dict[str, Any] | None:
    return review.selected_review_run(window)


def view_selected_review_snapshot(window: Any) -> None:
    return review.view_selected_review_snapshot(window)


def restore_selected_review_snapshot(window: Any) -> None:
    return review.restore_selected_review_snapshot(window)


def copy_selected_review_truth_file(window: Any) -> None:
    return review.copy_selected_review_truth_file(window)
