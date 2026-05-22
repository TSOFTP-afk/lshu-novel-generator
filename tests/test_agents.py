from __future__ import annotations

import json
from threading import Event

import pytest

from novel_app.agents.graph import AgentState
from novel_app.agents.prompts import (
    PLANNER_TEMPLATE,
    WRITER_TEMPLATE,
    AUDITOR_GENERATION_TEMPLATE,
    AUDITOR_REVIEW_TEMPLATE,
    REVISER_TEMPLATE,
)


class TestAgentState:
    def test_default_values(self) -> None:
        state = AgentState()
        assert state.book_title == ""
        assert state.outline == ""
        assert state.plan == ""
        assert state.draft == ""
        assert state.final_verdict == "reject"
        assert state.overall_score == 0
        assert state.selected_skills == []
        assert state.audit_findings == []
        assert state._log == []

    def test_log_appends_message(self) -> None:
        state = AgentState()
        state.log("测试消息")
        assert "测试消息" in state._log
        assert len(state._log) == 1

    def test_is_cancelled_no_event(self) -> None:
        state = AgentState()
        assert not state.is_cancelled

    def test_is_cancelled_with_event_not_set(self) -> None:
        state = AgentState(_cancel_event=Event())
        assert not state.is_cancelled

    def test_is_cancelled_with_event_set(self) -> None:
        event = Event()
        event.set()
        state = AgentState(_cancel_event=event)
        assert state.is_cancelled

    def test_to_result_structure(self) -> None:
        state = AgentState(
            overall_score=85,
            final_verdict="approve",
            summary="审计通过",
            revised_content="修订后的内容",
            revised_outline="修订后的大纲",
            template_comparison="风格一致",
            risk_notes="无风险",
            audit_findings=[{"severity": "low", "issue": "小问题"}],
        )
        result = state.to_result()
        assert result["overall_score"] == 85
        assert result["final_verdict"] == "approve"
        assert result["summary"] == "审计通过"
        assert result["revised_content"] == "修订后的内容"
        assert len(result["findings"]) == 1


class TestPromptTemplates:
    def test_planner_template_renders(self) -> None:
        rendered = PLANNER_TEMPLATE.format(
            book_title="测试",
            chapter_title="测试章",
            outline="测试大纲",
            truth_file="真相文件内容",
            sourcebook_context="上下文",
        )
        assert "测试" in rendered
        assert "scene_plan" in rendered
        assert "truth_file" not in rendered

    def test_writer_template_renders(self) -> None:
        rendered = WRITER_TEMPLATE.format(
            book_title="测试",
            chapter_title="测试章",
            outline="测试大纲",
            plan="场景计划",
            current_content="当前正文",
            skills="无",
            truth_file="真相文件",
            sourcebook_context="上下文",
            template_content="模板",
            style_voices_block="风格约束",
        )
        assert "测试" in rendered
        assert "不要提纲" in rendered
        assert "不要解释" in rendered

    def test_auditor_generation_template_renders(self) -> None:
        rendered = AUDITOR_GENERATION_TEMPLATE.format(
            book_title="测试",
            chapter_title="测试章",
            outline="测试大纲",
            draft="生成正文",
            truth_file="真相文件",
            sourcebook_context="上下文",
        )
        assert "overall_score" in rendered
        assert "findings" in rendered
        assert "plot_auditor" in rendered
        assert "ooc_auditor" in rendered
        assert "ai_detector" in rendered

    def test_auditor_review_template_renders(self) -> None:
        rendered = AUDITOR_REVIEW_TEMPLATE.format(
            book_title="测试",
            chapter_title="测试章",
            outline="测试大纲",
            content="原文",
            truth_file="真相文件",
            template_content="模板",
        )
        assert "overall_score" in rendered
        assert "findings" in rendered

    def test_reviser_template_renders(self) -> None:
        rendered = REVISER_TEMPLATE.format(
            book_title="测试",
            chapter_title="测试章",
            outline="测试大纲",
            content="原文",
            findings="- [high] 问题",
            template_content="模板",
        )
        assert "revised_content" in rendered
        assert "revised_outline" in rendered
        assert "risk_notes" in rendered


class TestChapterStructureAgent:
    def test_detect_normalizes_volume_and_chapter_markers(self) -> None:
        from novel_app.agents import ChapterStructureAgent

        captured: dict[str, str] = {}

        def fake_post_chat(**kwargs):
            captured["prompt"] = kwargs["messages"][1]["content"]
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "```json\n"
                                "{\"structure\":["
                                "{\"kind\":\"volume\",\"line_number\":2,\"title\":\"第一卷 风起\"},"
                                "{\"kind\":\"chapter\",\"line_number\":4,\"title\":\"第一章 雨夜\"}"
                                "]}\n"
                                "```"
                            )
                        }
                    }
                ]
            }

        text = "书名\n第一卷 风起\n说明\n第一章 雨夜\n正文"
        markers = ChapterStructureAgent(fake_post_chat).detect(text)

        assert "2: 第一卷 风起" in captured["prompt"]
        assert markers == [
            {"kind": "volume", "line_number": 2, "title": "第一卷 风起"},
            {"kind": "chapter", "line_number": 4, "title": "第一章 雨夜"},
        ]


class TestAgentGraphComputeScore:
    def test_no_findings_returns_85(self) -> None:
        from novel_app.agents.graph import AgentGraph
        score = AgentGraph._compute_score([])
        assert score == 100

    def test_one_high_returns_75(self) -> None:
        from novel_app.agents.graph import AgentGraph
        score = AgentGraph._compute_score([{"severity": "high"}])
        assert score == 88

    def test_two_high_returns_60(self) -> None:
        from novel_app.agents.graph import AgentGraph
        score = AgentGraph._compute_score([{"severity": "high"}, {"severity": "high"}])
        assert score == 76

    def test_mixed_severity(self) -> None:
        from novel_app.agents.graph import AgentGraph
        score = AgentGraph._compute_score([
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "low"},
        ])
        assert score == 83

    def test_score_clamped_at_zero(self) -> None:
        from novel_app.agents.graph import AgentGraph
        score = AgentGraph._compute_score([{"severity": "high"}] * 10)
        assert score == 0

    def test_score_clamped_at_100(self) -> None:
        from novel_app.agents.graph import AgentGraph
        score = AgentGraph._compute_score([{"severity": "low"}])
        assert score == 99


class TestAgentGraphExtractJson:
    def test_plain_json(self) -> None:
        from novel_app.agents.graph import AgentGraph
        result = AgentGraph._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_code_block(self) -> None:
        from novel_app.agents.graph import AgentGraph
        result = AgentGraph._extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_json_with_prefix_text(self) -> None:
        from novel_app.agents.graph import AgentGraph
        result = AgentGraph._extract_json('一些说明文字\n{"key": "value"}\n更多文字')
        assert result == {"key": "value"}
