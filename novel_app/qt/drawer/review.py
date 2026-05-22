from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from novel_app.qt.dialogs import confirm, info


def build_review_tab(window: Any) -> QWidget:
    page = window._make_drawer_page()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(8)

    header = QHBoxLayout()
    title = QLabel("生成记录")
    title.setObjectName("SectionTitle")
    run_btn = QPushButton("长篇生成")
    run_btn.clicked.connect(window._start_multi_agent_generation)
    header.addWidget(title, 1)
    header.addWidget(run_btn)

    window.review_templates_label = QLabel("")
    window.review_templates_label.setObjectName("MetaLabel")
    window.review_templates_label.setWordWrap(True)
    window.review_runs_list = QListWidget()
    window.review_runs_list.setObjectName("DrawerList")
    window.review_runs_list.currentItemChanged.connect(window._on_review_run_selected)
    window.review_detail = QPlainTextEdit()
    window.review_detail.setReadOnly(True)
    window.review_detail.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

    actions = QHBoxLayout()
    view_snapshot = QPushButton("查看快照")
    restore_snapshot = QPushButton("恢复快照")
    copy_truth = QPushButton("复制 Truth File")
    restore_snapshot.setObjectName("DangerButton")
    view_snapshot.clicked.connect(window._view_selected_review_snapshot)
    restore_snapshot.clicked.connect(window._restore_selected_review_snapshot)
    copy_truth.clicked.connect(window._copy_selected_review_truth_file)
    actions.addWidget(view_snapshot)
    actions.addWidget(restore_snapshot)
    actions.addWidget(copy_truth)

    layout.addLayout(header)
    layout.addWidget(window.review_templates_label)
    layout.addWidget(window.review_runs_list, 1)
    layout.addWidget(window.review_detail, 2)
    layout.addLayout(actions)
    return page


def refresh_review_tab(window: Any) -> None:
    if not hasattr(window, "review_runs_list"):
        return
    window.review_runs_list.blockSignals(True)
    window.review_runs_list.clear()
    window.selected_review_run_id = None
    if not window.state.selected_book_id:
        window.review_templates_label.clear()
        window.review_detail.clear()
        window.review_runs_list.blockSignals(False)
        return
    templates = window.database.list_template_chapters(window.state.selected_book_id)
    if templates:
        names = "、".join(str(item["title"]) for item in templates[:3])
        window.review_templates_label.setText(f"对照模板：{names}")
    else:
        window.review_templates_label.setText("对照模板：未设置")
    chapter_id = window.state.selected_chapter_id if window.state.current_node_kind == "chapter" else None
    runs = window.database.list_review_runs(window.state.selected_book_id, chapter_id, limit=20)
    for run in runs:
        status = str(run["status"] or "unknown")
        score = int(run["overall_score"] or 0)
        verdict = str(run["final_verdict"] or "reject")
        stamp = str(run["created_at"] or "")
        chapter_label = f"章节 {run['chapter_id']}" if run["chapter_id"] is not None else str(run["scope_type"] or "book")
        summary = str(run["summary"] or "").replace("\n", " ")[:80]
        label = "\n".join(
            [
                f"{status} / {verdict} / {score}分",
                summary or "无摘要",
                f"{stamp[:16]} · {chapter_label}",
            ]
        )
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, int(run["id"]))
        item.setSizeHint(QSize(0, 62))
        window.review_runs_list.addItem(item)
    window.review_runs_list.blockSignals(False)
    if window.review_runs_list.count():
        window.review_runs_list.setCurrentRow(0)
    else:
        window.review_detail.setPlainText("暂无生成记录。")


def on_review_run_selected(window: Any, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
    if not current:
        window.selected_review_run_id = None
        if hasattr(window, "review_detail"):
            window.review_detail.clear()
        return
    run_id = int(current.data(Qt.ItemDataRole.UserRole))
    window.selected_review_run_id = run_id
    window._render_review_run_detail(run_id)


def render_review_run_detail(window: Any, run_id: int) -> None:
    run_row = window.database.get_review_run(run_id)
    if not run_row:
        window.review_detail.setPlainText("生成记录不存在。")
        return
    run = dict(run_row)
    findings = [dict(item) for item in window.database.list_review_findings(run_id)]
    dimension_labels = {"character": "人物状态", "world": "世界观设定", "fact": "剧情事实"}
    cross_findings = [f for f in findings if f.get("is_cross_chapter")]
    single_findings = [f for f in findings if not f.get("is_cross_chapter")]
    lines = [
        f"状态：{run['status']}",
        f"判定：{run['final_verdict']}",
        f"分数：{run['overall_score']}",
        f"章节 ID：{run['chapter_id'] or '无'}",
        f"快照 ID：{run['snapshot_id'] or '无'}",
        f"创建：{run['created_at']}",
        f"应用：{run['applied_at'] or '未覆盖'}",
        "",
        "摘要：",
        str(run["summary"] or "无"),
        "",
    ]
    cross_summary = str(run.get("cross_summary") or "").strip()
    if cross_summary:
        lines.extend(["【跨章节一致性】", cross_summary, ""])
    lines.extend([
        "风险提示：",
        str(run["risk_notes"] or "无"),
        "",
        "模板对比：",
        str(run["template_comparison"] or "无"),
        "",
        "本章节问题：",
    ])
    if single_findings:
        for index, item in enumerate(single_findings, start=1):
            lines.extend(
                [
                    f"{index}. [{item['severity']}] {item['agent']} / {item['category']} / {item['location_hint']}",
                    f"问题：{item['issue_text']}",
                    f"建议：{item['suggestion_text']}",
                    f"引用：{item['quote_text'] or '无'}",
                    "",
                ]
            )
    else:
        lines.append("无")
    if cross_findings:
        lines.extend(["", "【跨章节一致性问题】"])
        for index, item in enumerate(cross_findings, start=1):
            dimension = dimension_labels.get(str(item.get("dimension", "")), str(item.get("dimension", "")))
            conflict_with = str(item.get("conflict_with", "")).strip() or "前序章节"
            lines.extend(
                [
                    f"{index}. [{item['severity']}] {dimension} / 与 {conflict_with} 冲突",
                    f"问题：{item['issue_text']}",
                    f"建议：{item['suggestion_text']}",
                    "",
                ]
            )
    window.review_detail.setPlainText("\n".join(lines).strip())


def selected_review_run(window: Any) -> dict[str, Any] | None:
    if not window.selected_review_run_id:
        return None
    run = window.database.get_review_run(window.selected_review_run_id)
    return dict(run) if run else None


def view_selected_review_snapshot(window: Any) -> None:
    run = window._selected_review_run()
    if not run or not run.get("snapshot_id"):
        info(window, "生成快照", "当前生成记录没有关联快照。")
        return
    snapshot = window.database.get_snapshot(int(run["snapshot_id"]))
    if not snapshot:
        info(window, "审查快照", "快照不存在或已被删除。")
        return
    window.review_detail.setPlainText(
        "\n".join(
            [
                f"快照：{snapshot['label']}",
                f"创建：{snapshot['created_at']}",
                "",
                "大纲：",
                str(snapshot["outline"] or ""),
                "",
                "正文：",
                str(snapshot["content"] or ""),
            ]
        )
    )


def restore_selected_review_snapshot(window: Any) -> None:
    run = window._selected_review_run()
    if not run or not run.get("snapshot_id"):
        info(window, "恢复快照", "当前生成记录没有关联快照。")
        return
    snapshot = window.database.get_snapshot(int(run["snapshot_id"]))
    if not snapshot:
        info(window, "恢复快照", "快照不存在或已被删除。")
        return
    chapter_id = int(snapshot["chapter_id"])
    if not confirm(window, "恢复审查前快照", "确定用审查前快照覆盖当前章节吗？", danger=True):
        return
    window.database.update_chapter(
        chapter_id,
        outline=str(snapshot["outline"] or ""),
        content=str(snapshot["content"] or ""),
        summary_text="",
    )
    window.database.delete_chapter_ai_spans(chapter_id)
    window.database.update_chapter_ai_probability(chapter_id, 0, "none")
    if window.state.selected_chapter_id == chapter_id:
        window._load_chapter(chapter_id)
    else:
        window._load_library_tree(window.current_tree_key)
    window._refresh_review_tab()
    window._set_status("已恢复审查前快照")


def copy_selected_review_truth_file(window: Any) -> None:
    run = window._selected_review_run()
    if not run:
        return
    truth = str(run.get("truth_snapshot", "") or "")
    if not truth:
        info(window, "Truth File", "当前生成记录没有 Truth File。")
        return
    QApplication.clipboard().setText(truth)
    window._set_status("Truth File 已复制")
