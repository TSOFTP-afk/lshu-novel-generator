from __future__ import annotations

from typing import Any

from novel_app.audit.dimensions import AUDIT_DIMENSIONS, AUDIT_DIMENSION_MAP


class AuditRule:
    def __init__(
        self,
        rule_id: str,
        dimension_id: str,
        description: str,
        check_fn_name: str = "default",
        severity_threshold: str = "medium",
    ) -> None:
        self.rule_id = rule_id
        self.dimension_id = dimension_id
        self.description = description
        self.check_fn_name = check_fn_name
        self.severity_threshold = severity_threshold

    @property
    def dimension(self) -> dict[str, Any] | None:
        return AUDIT_DIMENSION_MAP.get(self.dimension_id)

    @property
    def label(self) -> str:
        dim = self.dimension
        return f"[{dim['name']}] {self.description}" if dim else self.description


BUILTIN_RULES: list[AuditRule] = [
    AuditRule("R001", "plot_structure", "章节必须有明确的场景开场"),
    AuditRule("R002", "plot_structure", "章节结尾应提供悬念或阶段性收束"),
    AuditRule("R003", "plot_structure", "至少有1-2个推动主线的关键事件"),
    AuditRule("R004", "character_continuity", "角色状态应与上一章结尾保持一致"),
    AuditRule("R005", "character_continuity", "角色之间关系不应出现跳跃性变化"),
    AuditRule("R006", "character_continuity", "角色不应突然拥有未设定的能力或知识"),
    AuditRule("R007", "world_consistency", "世界观规则在本章中没有被违反"),
    AuditRule("R008", "world_consistency", "时间线前后一致，无矛盾"),
    AuditRule("R009", "world_consistency", "地理/空间描述与设定一致"),
    AuditRule("R010", "logic_coherence", "事件因果链条清晰，无逻辑跳跃"),
    AuditRule("R011", "logic_coherence", "角色决策有合理动机"),
    AuditRule("R012", "logic_coherence", "信息展示足以让读者理解剧情"),
    AuditRule("R013", "style_stability", "叙事风格与全书保持一致"),
    AuditRule("R014", "style_stability", "节奏分布合理，无拖沓或仓促"),
    AuditRule("R015", "ooc_detection", "关键角色无OOC行为"),
    AuditRule("R016", "ooc_detection", "角色对话符合其语言习惯和知识水平"),
    AuditRule("R017", "ai_flavor", "无明显AI模板化表达（如'总的来说''值得注意的是'）"),
    AuditRule("R018", "ai_flavor", "无不自然的上下文总结句"),
    AuditRule("R019", "ai_flavor", "段落开头无重复句式"),
    AuditRule("R020", "hook_tracking", "已设伏笔有推进或回收"),
    AuditRule("R021", "hook_tracking", "新设伏笔记录到待回收列表"),
    AuditRule("R022", "emotion_arc", "角色情感变化有铺垫"),
    AuditRule("R023", "dialogue_quality", "不同角色对话有辨识度"),
    AuditRule("R024", "dialogue_quality", "对话推动情节或展露人物"),
    AuditRule("R025", "pacing", "叙事节奏合理，快慢段落分布恰当"),
    AuditRule("R026", "template_alignment", "与对照模板的风格、结构和节奏保持一致"),
]


class AuditEngine:
    def __init__(self, rules: list[AuditRule] | None = None) -> None:
        self._rules = rules or BUILTIN_RULES

    def get_rules_for_dimension(self, dimension_id: str) -> list[AuditRule]:
        return [r for r in self._rules if r.dimension_id == dimension_id]

    def get_all_dimensions(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for r in self._rules:
            if r.dimension_id not in seen:
                seen.add(r.dimension_id)
                result.append(r.dimension_id)
        return result

    def generate_checklist(self, selected_dimensions: list[str] | None = None) -> str:
        selected = selected_dimensions or self.get_all_dimensions()
        lines = ["## 审计规则检查清单"]
        for dim_id in selected:
            dim = AUDIT_DIMENSION_MAP.get(dim_id)
            lines.append(f"\n### {dim['name'] if dim else dim_id}")
            rules = self.get_rules_for_dimension(dim_id)
            for i, rule in enumerate(rules, 1):
                lines.append(f"{i}. {rule.description}")
        return "\n".join(lines)

    def score_findings(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        total_issues = len(findings)
        high = sum(1 for f in findings if f.get("severity") == "high")
        medium = sum(1 for f in findings if f.get("severity") == "medium")
        low = sum(1 for f in findings if f.get("severity") == "low")

        base_score = 100.0
        weighted_penalty = 0.0
        for f in findings:
            severity = f.get("severity", "low")
            dim_id = f.get("dimension_id") or f.get("dimension") or f.get("agent", "")
            weight = AUDIT_DIMENSION_MAP.get(dim_id, {}).get("weight", 1.0)
            if severity == "high":
                weighted_penalty += 12.0 * weight
            elif severity == "medium":
                weighted_penalty += 4.0 * weight
            else:
                weighted_penalty += 1.0 * weight

        final_score = max(0, min(100, int(base_score - weighted_penalty)))

        overall = "approve"
        if high >= 3:
            overall = "reject"
        elif high >= 1:
            overall = "revise"
        elif final_score < 60:
            overall = "reject"
        elif final_score < 80:
            overall = "revise"

        return {
            "score": final_score,
            "verdict": overall,
            "summary": f"问题：高={high} 中={medium} 低={low} | 得分={final_score}",
            "high_count": high,
            "medium_count": medium,
            "low_count": low,
        }