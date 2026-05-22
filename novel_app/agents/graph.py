from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Callable

from novel_app.agents.planner import PlannerAgent
from novel_app.agents.writer import WriterAgent
from novel_app.agents.auditor import AuditorAgent
from novel_app.agents.reviser import ReviserAgent
from novel_app.audit.rules import AuditEngine


@dataclass
class AgentState:
    book_title: str = ""
    chapter_title: str = ""
    outline: str = ""
    current_content: str = ""
    truth_file: str = ""
    sourcebook_context: str = ""
    template_content: str = ""
    style_voices_block: str = ""
    selected_skills: list[dict[str, Any]] = field(default_factory=list)

    plan: str = ""
    draft: str = ""
    audit_findings: list[dict[str, Any]] = field(default_factory=list)
    revised_content: str = ""
    revised_outline: str = ""

    overall_score: int = 0
    final_verdict: str = "reject"
    summary: str = ""
    risk_notes: str = ""
    template_comparison: str = ""

    _log: list[str] = field(default_factory=list)
    _cancel_event: Event | None = None
    _post_chat: Callable[..., dict[str, Any]] | None = None

    def log(self, message: str) -> None:
        self._log.append(message)

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event is not None and self._cancel_event.is_set()

    def to_result(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "overall_score": self.overall_score,
            "final_verdict": self.final_verdict,
            "findings": self.audit_findings,
            "revised_content": self.revised_content,
            "revised_outline": self.revised_outline,
            "template_comparison": self.template_comparison,
            "risk_notes": self.risk_notes,
        }


class AgentGraph:
    def __init__(
        self,
        post_chat: Callable[..., dict[str, Any]],
        model_router: Any | None = None,
        prompt_overrides: dict[str, str] | None = None,
    ) -> None:
        self._post_chat = post_chat
        self._model_router = model_router
        self.planner = PlannerAgent(self._routed_chat("Planner(大纲拆解)"))
        self.writer = WriterAgent(self._routed_chat("Writer(正文写手)"))
        self.auditor = AuditorAgent(self._routed_chat("Auditor(一致性审计)"))
        self.reviser = ReviserAgent(self._routed_chat("Reviser(修订润色)"))

        self._prompt_overrides = prompt_overrides or {}
        for agent in (self.planner, self.writer, self.auditor, self.reviser):
            agent._prompt_overrides = self._prompt_overrides

    def _routed_chat(self, agent_name: str) -> Callable[..., dict[str, Any]]:
        if self._model_router is not None:
            return self._model_router.wrap_post_chat(self._post_chat, agent_name)
        return self._post_chat

    def run_generation(self, state: AgentState) -> AgentState:
        state._post_chat = self._post_chat
        self._run_node("Planner(大纲拆解)", self.planner.plan, state)
        if state.is_cancelled:
            return state
        self._run_node("Writer(正文写手)", self.writer.write, state)
        if state.is_cancelled:
            return state
        self._run_node("Auditor(一致性审计)", self.auditor.audit, state)
        if state.is_cancelled:
            return state
        self._run_node("Reviser(修订润色)", self.reviser.revise, state)
        if state.is_cancelled:
            return state
        if not state.revised_content:
            state.final_verdict = "reject"
            state.risk_notes = "流水线未产出有效修订内容"
            return state

        high_count = sum(1 for f in state.audit_findings if f.get("severity") == "high")

        if high_count >= 2:
            state.final_verdict = "reject"
            state.risk_notes = f"存在 {high_count} 个严重问题需要人工处理"
        elif high_count >= 1:
            state.final_verdict = "revise"
        else:
            state.final_verdict = "approve"

        state.overall_score = self._compute_score(state.audit_findings)
        return state

    def run_review(self, state: AgentState) -> AgentState:
        state._post_chat = self._post_chat
        self._run_node("Auditor(长篇审查)", self.auditor.audit, state)
        if state.is_cancelled:
            return state
        self._run_node("Reviser(修订润色)", self.reviser.revise, state)
        if state.is_cancelled:
            return state
        if not state.revised_content:
            state.final_verdict = "reject"
            state.risk_notes = "审查流水线未产出有效修订内容"
            return state

        high_count = sum(1 for f in state.audit_findings if f.get("severity") == "high")

        if high_count >= 2:
            state.final_verdict = "reject"
            state.risk_notes = f"存在 {high_count} 个严重问题需要人工处理"
        elif high_count >= 1:
            state.final_verdict = "revise"
        else:
            state.final_verdict = "approve"

        state.overall_score = self._compute_score(state.audit_findings)
        return state

    @staticmethod
    def _run_node(name: str, node_fn: Callable[[AgentState], None], state: AgentState) -> None:
        state.log(f"[{name}] 开始...")
        try:
            node_fn(state)
            state.log(f"[{name}] 完成")
        except Exception as exc:
            state.log(f"[{name}] 异常: {exc}")
            raise

    @staticmethod
    def _compute_score(findings: list[dict[str, Any]]) -> int:
        engine = AuditEngine()
        result = engine.score_findings(findings)
        return result["score"]

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start:end + 1]
        return json.loads(stripped)


__all__ = ["AgentState", "AgentGraph"]
