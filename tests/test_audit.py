from __future__ import annotations

import pytest

from novel_app.audit.dimensions import (
    AUDIT_DIMENSIONS,
    AUDIT_DIMENSION_MAP,
    get_active_dimensions,
    get_dimension_label,
)
from novel_app.audit.rules import BUILTIN_RULES, AuditEngine, AuditRule
from novel_app.audit.validator import OutputValidator


class TestAuditDimensions:
    def test_all_dimensions_have_ids(self) -> None:
        for dim in AUDIT_DIMENSIONS:
            assert "id" in dim
            assert "name" in dim
            assert "check_prompt" in dim
            assert "weight" in dim

    def test_dimension_map_is_complete(self) -> None:
        for dim in AUDIT_DIMENSIONS:
            assert dim["id"] in AUDIT_DIMENSION_MAP
            assert AUDIT_DIMENSION_MAP[dim["id"]] is dim

    def test_get_dimension_label(self) -> None:
        result = get_dimension_label("ooc_detection")
        assert result == "OOC 检测"

    def test_get_dimension_label_unknown(self) -> None:
        result = get_dimension_label("unknown_dim")
        assert result == "unknown_dim"

    def test_get_active_dimensions_all(self) -> None:
        active = get_active_dimensions()
        assert len(active) == len(AUDIT_DIMENSIONS)

    def test_get_active_dimensions_filtered(self) -> None:
        active = get_active_dimensions(["ooc_detection", "ai_flavor"])
        assert len(active) == 2
        assert all(d["id"] in {"ooc_detection", "ai_flavor"} for d in active)

    def test_dimension_count(self) -> None:
        count = len(AUDIT_DIMENSIONS)
        assert count == 12


class TestAuditRules:
    def test_builtin_rules_have_ids(self) -> None:
        for rule in BUILTIN_RULES:
            assert rule.rule_id
            assert rule.dimension_id
            assert rule.description

    def test_builtin_rules_count(self) -> None:
        assert len(BUILTIN_RULES) == 26

    def test_audit_engine_get_rules_for_dimension(self) -> None:
        engine = AuditEngine()
        rules = engine.get_rules_for_dimension("ooc_detection")
        assert len(rules) >= 1
        assert all(r.dimension_id == "ooc_detection" for r in rules)

    def test_audit_engine_generate_checklist(self) -> None:
        engine = AuditEngine()
        checklist = engine.generate_checklist(["plot_structure", "ooc_detection"])
        assert "情节结构" in checklist
        assert "OOC" in checklist
        assert "R001" in checklist or "场景开场" in checklist

    def test_score_findings_approve(self) -> None:
        engine = AuditEngine()
        result = engine.score_findings([])
        assert result["score"] == 100
        assert result["verdict"] == "approve"

    def test_score_findings_revise(self) -> None:
        engine = AuditEngine()
        result = engine.score_findings([
            {"severity": "high", "dimension_id": "ooc_detection"},
        ])
        assert result["verdict"] == "revise"

    def test_score_findings_reject_multiple_high(self) -> None:
        engine = AuditEngine()
        result = engine.score_findings([
            {"severity": "high"},
            {"severity": "high"},
            {"severity": "high"},
        ])
        assert result["verdict"] == "reject"

    def test_score_findings_weighted_penalty(self) -> None:
        engine = AuditEngine()
        result = engine.score_findings([
            {"severity": "high", "dimension_id": "ooc_detection"},
            {"severity": "medium", "dimension_id": "dialogue_quality"},
        ])
        assert 0 <= result["score"] <= 100


class TestOutputValidator:
    def test_validate_valid_payload(self) -> None:
        payload = {
            "summary": "审计通过",
            "overall_score": 85,
            "final_verdict": "approve",
            "findings": [],
            "revised_content": "修订正文",
            "revised_outline": "修订大纲",
            "risk_notes": "无",
            "template_comparison": "",
        }
        result = OutputValidator.validate_review_payload(payload)
        assert result["summary"] == "审计通过"
        assert result["overall_score"] == 85
        assert result["final_verdict"] == "approve"

    def test_validate_missing_fields_filled(self) -> None:
        payload = {"revised_content": "正文"}
        result = OutputValidator.validate_review_payload(payload)
        assert result["summary"] == ""
        assert result["overall_score"] == 0
        assert result["findings"] == []

    def test_validate_no_revised_content_rejects(self) -> None:
        payload = {"summary": "测试", "revised_content": ""}
        result = OutputValidator.validate_review_payload(payload)
        assert result["final_verdict"] == "reject"

    def test_validate_invalid_verdict_falls_back(self) -> None:
        payload = {"revised_content": "正文", "final_verdict": "unknown"}
        result = OutputValidator.validate_review_payload(payload)
        assert result["final_verdict"] == "revise"

    def test_validate_invalid_score_parsed(self) -> None:
        payload = {"revised_content": "正文", "overall_score": "评分85分"}
        result = OutputValidator.validate_review_payload(payload)
        assert result["overall_score"] == 85

    def test_validate_finding_fields(self) -> None:
        payload = {
            "revised_content": "正文",
            "findings": [
                {"agent": "test", "severity": "HIGH", "issue": "问题", "suggestion": "建议"},
                {"agent": "", "severity": "CRITICAL", "issue": "", "suggestion": ""},
            ],
        }
        result = OutputValidator.validate_review_payload(payload)
        assert len(result["findings"]) == 2
        assert result["findings"][0]["severity"] == "high"
        assert result["findings"][1]["severity"] == "low"

    def test_try_parse_json_plain(self) -> None:
        result = OutputValidator.try_parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_try_parse_json_code_block(self) -> None:
        result = OutputValidator.try_parse_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_try_parse_json_with_prefix(self) -> None:
        result = OutputValidator.try_parse_json('说明文字\n{"key": "value"}\n更多')
        assert result == {"key": "value"}


class TestDSLParser:
    def test_empty_text(self) -> None:
        from novel_app.audit.dsl_parser import DSLParser

        class FakeDB:
            def list_characters(self, book_id):
                return []

            def list_world_entries(self, book_id):
                return []

            def list_chapters(self, book_id):
                return []

            def list_relationships(self, book_id):
                return []

        parser = DSLParser(FakeDB())
        result = parser.resolve(1, "普通文本")
        assert result == "普通文本"

    def test_extract_references(self) -> None:
        from novel_app.audit.dsl_parser import DSLParser

        class FakeDB:
            pass

        parser = DSLParser(FakeDB())
        refs = parser.extract_references("测试 @角色.张三 @世界.魔法规则")
        assert "@角色.张三" in refs
        assert "@世界.魔法规则" in refs